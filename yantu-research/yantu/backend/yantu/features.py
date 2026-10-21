"""Research workflows on the isolated yt_ schema. No Plane core table access."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse, quote
from uuid import uuid4

from fastapi import Body, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import *
from .security import check_password, hash_password, new_token, token_digest
from .version import VERSION
from .plane_client import PlaneError
from .research_assistant import extract_document_text, AssistantUnavailable


def register_features(app, context):
    previous = list(app.routes)
    get_db = context["get_db"]
    current_user = context["current_user"]
    team_member = context["team_member"]
    can_manage = context["can_manage"]
    task_for = context["task_for"]
    plane = context["plane"]
    uploads = context["uploads"]
    iso = context["iso"]
    assistant = context["research_assistant"]

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request, _error):
        return JSONResponse(status_code=409, content={"code": "CONFLICT", "message": "记录已存在或状态已变化，请刷新后重试"})

    @app.middleware("http")
    async def same_origin_mutations(request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            allowed_origin = os.getenv("APP_ORIGIN", "").rstrip("/")
            if urlparse(origin).netloc != request.headers.get("host") and origin.rstrip("/") != allowed_origin:
                return JSONResponse(status_code=403, content={"code": "FORBIDDEN", "message": "不允许跨站写入"})
        return await call_next(request)

    def text_value(payload, key, default="", maximum=50000, required=False):
        value = payload.get(key, default)
        if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
            raise HTTPException(400, f"{key} 不能为空或超过长度限制")
        return value.strip()

    def timestamp(value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            raise HTTPException(400, "时间必须包含时区")

    def tags(payload):
        value = payload.get("tags", [])
        if isinstance(value, str):
            value = [x.strip() for x in value.split(",") if x.strip()]
        if not isinstance(value, list) or len(value) > 30 or any(not isinstance(x, str) or len(x) > 60 for x in value):
            raise HTTPException(400, "标签格式错误")
        return list(dict.fromkeys(value))

    def get_meta(db, kind, ident):
        row = db.get(EntityData, f"{kind}:{ident}")
        return dict(row.data) if row else {}

    def put_meta(db, kind, ident, values):
        key = f"{kind}:{ident}"
        row = db.get(EntityData, key)
        if row is None:
            row = EntityData(key=key, data={})
            db.add(row)
        row.data = {**row.data, **values}
        return row.data

    def name(db, user_id):
        row = db.get(User, user_id)
        return row.display_name if row else "已离组成员"

    def actor(user):
        return {"id": user.id, "displayName": user.display_name, "email": user.email, "direction": user.direction or ""}

    def require_owner(db, team_id, user):
        team, member = team_member(db, team_id, user)
        if member.role != "owner":
            raise HTTPException(403, "只有负责人可以操作")
        return team

    def notify(db, user_id, title, team_id=None, kind=None, ident=None):
        db.add(Notification(user_id=user_id, title=title[:255], team_id=team_id, target_type=kind, target_id=ident))

    def team_notify(db, team_id, title, except_user=None, kind=None, ident=None):
        for member in db.scalars(select(Member).where(Member.team_id == team_id)).all():
            if member.user_id != except_user:
                notify(db, member.user_id, title, team_id, kind, ident)

    def page_data(items, page, page_size):
        return {"data": {"items": items[(page-1)*page_size:page*page_size], "total": len(items)}}

    from .cloud_drive import resource_visible, resource_for

    def preview_media_type(filename):
        media_type = mimetypes.guess_type(filename or "")[0] or ""
        if media_type == "application/pdf" or media_type.startswith(("image/", "audio/", "video/")) or media_type in ("text/plain", "text/markdown", "text/csv"):
            if media_type not in ("image/svg+xml",):
                return media_type
        return None

    def resource_json(db, resource, user):
        meta = get_meta(db, "resource", resource.id)
        membership = db.scalar(select(Member).where(Member.team_id == resource.team_id, Member.user_id == user.id))
        return {"id": resource.id, "title": resource.title, "type": resource.type,
                "description": resource.description, "ownerId": resource.owner_id,
                "owner": name(db, resource.owner_id), "fileName": resource.file_name,
                "size": resource.size, "version": resource.version,
                "visibility": resource.visibility, "tags": meta.get("tags", []),
                "meetingId": resource.meeting_id, "taskId": resource.task_id,
                "previewable": bool(preview_media_type(resource.file_name)),
                "previewType": preview_media_type(resource.file_name),
                "folderId": resource.folder_id, "canEdit": resource.owner_id == user.id,
                "permissions": {"canRead": True, "canDownload": True, "canEdit": resource.owner_id == user.id, "canShare": resource.owner_id == user.id},
                "references": [{"id": ref.id, "targetType": ref.target_type, "targetId": ref.target_id} for ref in db.scalars(select(ResourceReference).where(ResourceReference.resource_id == resource.id))]}

    def task_visible(task, membership, user):
        return task.assignee_id == user.id or task.reviewer_id == user.id or membership.role == "owner"

    def task_json(db, task):
        info = get_meta(db, "task", task.id)
        return {"id": task.id, "title": task.title, "status": task.status,
                "description": task.description, "acceptanceCriteria": task.acceptance_criteria,
                "assigneeId": task.assignee_id, "assignee": name(db, task.assignee_id),
                "reviewerId": task.reviewer_id, "reviewer": name(db, task.reviewer_id),
                "blocker": task.blocker, "meetingId": task.meeting_id,
                "enrollmentId": task.enrollment_id, "stageId": task.route_stage_id,
                "stageTitle": task.route_stage_title, "revision": task.revision,
                "latestSubmissionId": task.latest_submission_id,
                "planeSync": task.plane_sync, "planeWorkItemId": task.plane_work_item_id,
                "dueAt": info.get("dueAt"), "priority": info.get("priority", "normal")}

    def bind_session(db, user, response, request):
        token = new_token()
        db.add(SessionToken(token_hash=token_digest(token), user_id=user.id, expires_at=utcnow()+timedelta(days=7)))
        db.commit()
        response.set_cookie("yantu_session", token, max_age=7*86400, httponly=True,
                            secure=request.url.scheme == "https" or os.getenv("COOKIE_SECURE") == "1",
                            samesite="lax", path="/")
        response.headers["Cache-Control"] = "no-store"
        return {"accessToken": token, "user": actor(user)}

    def request_token(request):
        auth = request.headers.get("authorization", "")
        return auth[7:] if auth.startswith("Bearer ") else request.cookies.get("yantu_session", "")

    @app.get("/api/v1/system/status")
    def system_status(db: Session = Depends(get_db)):
        return {"data": {"version": VERSION,
                         "initialized": bool(db.scalar(select(func.count()).select_from(User))),
                         "registrationOpen": os.getenv("ALLOW_PUBLIC_SIGNUP", "0") == "1",
                         "planeConfigured": bool(os.getenv("PLANE_API_KEY")),
                         "assistantConfigured": bool(os.getenv("AI_BASE_URL") and os.getenv("AI_MODEL"))}}

    def validate_identity(payload):
        email = text_value(payload, "email", maximum=254, required=True).lower()
        password = text_value(payload, "password", maximum=1024, required=True)
        display_name = text_value(payload, "displayName", maximum=100, required=True)
        if "@" not in email or email.startswith("@") or email.endswith("@") or len(password) < 12:
            raise HTTPException(400, "请输入有效邮箱及至少 12 位的密码")
        return email, password, display_name

    @app.post("/api/v1/auth/setup")
    def setup(request: Request, response: Response, payload: dict = Body(), db: Session = Depends(get_db)):
        email, password, display_name = validate_identity(payload)
        team_name = text_value(payload, "teamName", maximum=100, required=True)
        if db.scalar(select(func.count()).select_from(User)):
            raise HTTPException(409, "系统已初始化，请直接登录")
        db.add(SystemSetting(key="initialized", value=iso(utcnow())))
        db.flush()  # Unique key claims the one-time setup transaction across workers.
        user = User(email=email, display_name=display_name, password_hash=hash_password(password))
        team = Team(name=team_name)
        db.add_all([user, team])
        db.flush()
        db.add(Member(team_id=team.id, user_id=user.id, role="owner"))
        result = bind_session(db, user, response, request)
        return {"data": {**result, "teamId": team.id}}

    def invite_record(db, token, email):
        invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(token)))
        if (invitation is None or invitation.accepted_at is not None or
            timestamp(iso(invitation.expires_at)) <= utcnow() or invitation.email != email):
            raise HTTPException(403, "邀请与邮箱不匹配、已使用或已过期")
        return invitation

    def claim_invitation(db, invitation):
        result = db.execute(update(Invitation).where(Invitation.id == invitation.id,
            Invitation.accepted_at.is_(None), Invitation.expires_at > utcnow()).values(accepted_at=utcnow())
            .execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise HTTPException(409, "邀请已被使用，请刷新")

    @app.post("/api/v1/auth/register")
    def register(payload: dict = Body(), db: Session = Depends(get_db)):
        email, password, display_name = validate_identity(payload)
        invitation = invite_record(db, str(payload["invitationToken"]), email) if payload.get("invitationToken") else None
        if not invitation and os.getenv("ALLOW_PUBLIC_SIGNUP", "0") != "1":
            raise HTTPException(403, "请先取得课题组邀请")
        if invitation:
            claim_invitation(db, invitation)
        user = User(email=email, display_name=display_name, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        if invitation:
            db.add(Member(team_id=invitation.team_id, user_id=user.id, role=invitation.role))
        db.commit()
        return {"data": {"id": user.id}}

    @app.post("/api/v1/auth/login")
    def login(request: Request, response: Response, payload: dict = Body(), db: Session = Depends(get_db)):
        email = text_value(payload, "email", maximum=254, required=True).lower()
        password = text_value(payload, "password", maximum=1024, required=True)
        failure = db.get(LoginFailure, email)
        if failure and failure.locked_until and timestamp(iso(failure.locked_until)) > utcnow():
            raise HTTPException(429, "登录尝试过多，请稍后再试")
        user = db.scalar(select(User).where(User.email == email))
        if user is None or not check_password(password, user.password_hash):
            if failure is None:
                failure = LoginFailure(email=email, count=0)
                db.add(failure)
            if failure.locked_until:
                failure.count = 0
                failure.locked_until = None
            failure.count += 1
            if failure.count >= 5:
                failure.locked_until = utcnow()+timedelta(minutes=15)
            db.commit()
            raise HTTPException(401, "邮箱或密码错误")
        if failure:
            db.delete(failure)
        return {"data": bind_session(db, user, response, request)}

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, response: Response, db: Session = Depends(get_db)):
        db.execute(delete(SessionToken).where(SessionToken.token_hash == token_digest(request_token(request))))
        db.commit()
        response.delete_cookie("yantu_session", path="/")
        return {"data": None}

    @app.post("/api/v1/auth/refresh")
    def refresh(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
        result = db.execute(delete(SessionToken).where(SessionToken.token_hash == token_digest(request_token(request))))
        if result.rowcount != 1:
            raise HTTPException(401, "会话已失效")
        return {"data": bind_session(db, user, response, request)}

    @app.get("/api/v1/me/teams")
    def my_teams(user: User = Depends(current_user), db: Session = Depends(get_db)):
        memberships = db.scalars(select(Member).where(Member.user_id == user.id).order_by(Member.id)).all()
        return {"data": {"items": [{"id": m.team_id, "name": db.get(Team, m.team_id).name,
            "role": m.role, "planeConnected": plane.configured(db.get(Team, m.team_id))} for m in memberships], "total": len(memberships)}}

    @app.get("/api/v1/teams/{team_id}")
    def get_team(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        team, member = team_member(db, team_id, user)
        return {"data": {"id": team.id, "name": team.name, "role": member.role,
            "description": get_meta(db, "team", team.id).get("description", ""), "planeConnected": plane.configured(team),
            "planeWorkspaceSlug": team.plane_workspace_slug, "planeProjectId": team.plane_project_id}}

    @app.patch("/api/v1/teams/{team_id}")
    def edit_team(team_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        team = require_owner(db, team_id, user)
        if "name" in payload:
            team.name = text_value(payload, "name", maximum=100, required=True)
        if "description" in payload:
            put_meta(db, "team", team.id, {"description": text_value(payload, "description")})
        db.commit()
        return get_team(team_id, user, db)

    @app.get("/api/v1/teams/{team_id}/members")
    def members(team_id: str, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, team_id, user)
        result = []
        for member in db.scalars(select(Member).where(Member.team_id == team_id).order_by(Member.id)).all():
            person = db.get(User, member.user_id)
            result.append({"id": person.id, "name": person.display_name, "displayName": person.display_name,
                           "email": person.email, "direction": person.direction, "role": member.role})
        return page_data(result, page, pageSize)

    @app.patch("/api/v1/teams/{team_id}/members/{user_id}")
    def edit_member(team_id: str, user_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_owner(db, team_id, user)
        row = db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == user_id))
        if row is None:
            raise HTTPException(404, "成员不存在")
        if row.role == "owner":
            raise HTTPException(409, "不能降级负责人")
        role = payload.get("role")
        if role not in ("student", "mentor"):
            raise HTTPException(400, "角色无效")
        if role == "student" and db.scalar(select(Task.id).where(Task.team_id == team_id, Task.reviewer_id == user_id, Task.status != "done").limit(1)):
            raise HTTPException(409, "请先交接此成员的待反馈任务")
        row.role = role
        db.commit()
        return {"data": {"id": user_id, "role": role}}

    @app.delete("/api/v1/teams/{team_id}/members/{user_id}")
    def remove_member(team_id: str, user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_owner(db, team_id, user)
        row = db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == user_id))
        if row is None:
            raise HTTPException(404, "成员不存在")
        if row.role == "owner":
            raise HTTPException(409, "不能移除负责人")
        if db.scalar(select(Task.id).where(Task.team_id == team_id, Task.status != "done", or_(Task.assignee_id == user_id, Task.reviewer_id == user_id)).limit(1)):
            raise HTTPException(409, "请先完成或交接成员的未完成任务")
        for share in db.scalars(select(ResourceShare).where(ResourceShare.team_id == team_id, ResourceShare.active.is_(True))):
            resource = db.get(Resource, share.resource_id)
            if share.user_id == user_id or (resource and resource.owner_id == user_id): share.active = False
        db.delete(row)
        db.commit()
        return {"data": None}

    @app.get("/api/v1/teams/{team_id}/invitations")
    def invitations(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_owner(db, team_id, user)
        rows = db.scalars(select(Invitation).where(Invitation.team_id == team_id).order_by(Invitation.expires_at.desc())).all()
        return {"data": {"items": [{"id": r.id, "email": r.email, "role": r.role, "expiresAt": iso(r.expires_at),
            "status": "accepted" if r.accepted_at else "expired" if timestamp(iso(r.expires_at)) <= utcnow() else "pending"} for r in rows], "total": len(rows)}}

    @app.post("/api/v1/teams/{team_id}/invitations")
    def invite(team_id: str, request: Request, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_owner(db, team_id, user)
        email = text_value(payload, "email", maximum=254, required=True).lower()
        if "@" not in email or payload.get("role") not in ("student", "mentor"):
            raise HTTPException(400, "邮箱或角色无效")
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user and db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == existing_user.id)):
            raise HTTPException(409, "此用户已在课题组中")
        token = new_token()
        row = Invitation(team_id=team_id, email=email, role=payload["role"], token_hash=token_digest(token), expires_at=utcnow()+timedelta(days=7))
        db.add(row)
        db.commit()
        return {"data": {"id": row.id, "status": "pending", "inviteToken": token,
                         "inviteUrl": str(request.base_url).rstrip("/")+"/?invite="+token, "expiresAt": iso(row.expires_at)}}

    @app.post("/api/v1/invitations/{token}/accept")
    def accept_invitation(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = invite_record(db, token, user.email)
        if db.scalar(select(Member).where(Member.team_id == row.team_id, Member.user_id == user.id)):
            raise HTTPException(409, "已经加入课题组")
        claim_invitation(db, row)
        db.add(Member(team_id=row.team_id, user_id=user.id, role=row.role))
        db.commit()
        return {"data": {"teamId": row.team_id}}

    def route_for(db, route_id, user, write=False):
        route = db.get(Route, route_id)
        if route is None or route.archived:
            raise HTTPException(404, "路线不存在")
        _, member = team_member(db, route.team_id, user)
        if write:
            can_manage(member)
        return route

    def filter_materials(db, snapshot, user):
        value = deepcopy(snapshot)
        if user:
            for stage in value.get("stages", []):
                stage["resources"] = [item for item in stage.get("resources", [])
                    if (r := db.get(Resource, item.get("id"))) and resource_visible(db, r, user)]
        return value

    def route_json(db, route, user=None):
        meta = get_meta(db, "route", route.id)
        enrollment = db.scalar(select(Enrollment).where(Enrollment.route_id == route.id, Enrollment.user_id == user.id)) if user else None
        return {"id": route.id, "teamId": route.team_id, "title": route.title, "description": route.description,
                "authorId": route.author_id, "author": name(db, route.author_id), "version": route.version,
                "stageCount": len(route.stages or []),
                "direction": meta.get("direction", ""), "difficulty": meta.get("difficulty", "入门"),
                "tags": meta.get("tags", []), "stages": filter_materials(db, {"stages": route.stages}, user)["stages"],
                "enrolled": enrollment is not None, "enrollmentId": enrollment.id if enrollment else None}

    def route_stages(db, team_id, stages, user):
        if not isinstance(stages, list) or len(stages) > 40:
            raise HTTPException(400, "路线最多包含 40 个阶段")
        result, seen = [], set()
        for stage in stages:
            if not isinstance(stage, dict):
                raise HTTPException(400, "阶段格式错误")
            sid = str(stage.get("id") or uuid4())
            if sid in seen or len(sid) > 36:
                raise HTTPException(400, "阶段编号重复或过长")
            seen.add(sid)
            resources = []
            for value in stage.get("resources", []):
                rid = value.get("id") if isinstance(value, dict) else value
                resource, _ = resource_for(db, rid, user)
                if resource.team_id != team_id or resource.visibility != "team":
                    raise HTTPException(400, "公共路线仅能引用本组共享资料")
                resources.append({"id": resource.id, "title": resource.title})
            task_values = stage.get("tasks", [])
            if not isinstance(task_values, list) or len(task_values) > 100:
                raise HTTPException(400, "每个阶段最多包含 100 个任务")
            tasks = []
            for item in task_values:
                if not isinstance(item, dict):
                    raise HTTPException(400, "任务格式错误")
                tasks.append({"id": str(item.get("id") or uuid4()), "title": text_value(item, "title", maximum=200, required=True),
                              "description": text_value(item, "description"), "acceptanceCriteria": text_value(item, "acceptanceCriteria")})
            result.append({"id": sid, "title": text_value(stage, "title", maximum=200, required=True),
                           "description": text_value(stage, "description"), "resources": resources, "tasks": tasks})
        return result

    def route_metadata(payload):
        return {"direction": text_value(payload, "direction", maximum=255),
                "difficulty": text_value(payload, "difficulty", "入门", 60), "tags": tags(payload)}

    @app.get("/api/v1/teams/{team_id}/routes")
    def routes(team_id: str, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, team_id, user)
        rows = db.scalars(select(Route).where(Route.team_id == team_id, Route.archived.is_(False)).order_by(Route.id)).all()
        return page_data([route_json(db, row, user) for row in rows], page, pageSize)

    @app.post("/api/v1/teams/{team_id}/routes")
    def create_route(team_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, member = team_member(db, team_id, user)
        can_manage(member)
        row = Route(team_id=team_id, author_id=user.id, title=text_value(payload, "title", maximum=200, required=True),
                    description=text_value(payload, "description"), stages=route_stages(db, team_id, payload.get("stages", []), user))
        db.add(row)
        db.flush()
        put_meta(db, "route", row.id, route_metadata(payload))
        db.flush()
        db.add(RouteVersion(route_id=row.id, version=1, snapshot=route_json(db, row), author_id=user.id))
        team_notify(db, team_id, f"新路线：{row.title}", user.id, "route", row.id)
        db.commit()
        return {"data": route_json(db, row, user)}

    @app.get("/api/v1/routes/{route_id}")
    def get_route(route_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        return {"data": route_json(db, route_for(db, route_id, user), user)}

    @app.patch("/api/v1/routes/{route_id}")
    def edit_route(route_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        route = route_for(db, route_id, user, True)
        expected = route.version
        if "version" in payload and payload["version"] != expected:
            raise HTTPException(409, "路线已有新版本，请刷新后编辑")
        before = route_json(db, route)
        values = {"version": expected+1}
        for key in ("title", "description"):
            if key in payload:
                values[key] = text_value(payload, key, maximum=200 if key == "title" else 50000, required=key == "title")
        if "stages" in payload:
            values["stages"] = route_stages(db, route.team_id, payload["stages"], user)
        if db.execute(update(Route).where(Route.id == route.id, Route.version == expected).values(**values)).rowcount != 1:
            raise HTTPException(409, "路线已有新版本，请刷新后编辑")
        if not db.scalar(select(RouteVersion.id).where(RouteVersion.route_id == route.id, RouteVersion.version == expected)):
            db.add(RouteVersion(route_id=route.id, version=expected, snapshot=before, author_id=route.author_id))
        meta = get_meta(db, "route", route.id)
        put_meta(db, "route", route.id, route_metadata({**meta, **payload}))
        db.flush()
        db.refresh(route)
        db.add(RouteVersion(route_id=route.id, version=route.version, snapshot=route_json(db, route), author_id=user.id))
        db.commit()
        return {"data": route_json(db, route, user)}

    @app.get("/api/v1/routes/{route_id}/versions")
    def route_versions(route_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        route = route_for(db, route_id, user)
        rows = db.scalars(select(RouteVersion).where(RouteVersion.route_id == route_id).order_by(RouteVersion.version.desc())).all()
        items = [{"id": r.id, "version": r.version, "snapshot": filter_materials(db, r.snapshot, user), "author": name(db, r.author_id), "createdAt": iso(r.created_at)} for r in rows]
        if not items:
            items = [{"id": route.id, "version": route.version, "snapshot": route_json(db, route), "author": name(db, route.author_id), "createdAt": None}]
        return {"data": {"items": items, "total": len(items)}}

    @app.delete("/api/v1/routes/{route_id}")
    def archive_route(route_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        route_for(db, route_id, user, True).archived = True
        db.commit()
        return {"data": None}

    def sync_task(db, task, team, comment=None):
        if not plane.configured(team):
            task.plane_sync = "not_configured"
            db.commit()
            return
        try:
            if not task.plane_work_item_id:
                task.plane_work_item_id = plane.create_work_item(team, task.title, task.description, external_id=task.id)
            elif hasattr(plane, "update_work_item"):
                meta = get_meta(db, "task", task.id)
                plane.update_work_item(team, task.plane_work_item_id, task.title, task.description, task.status,
                                       priority=meta.get("priority", "none"), due_at=meta.get("dueAt"))
            if comment and task.plane_work_item_id:
                plane.add_comment(team, task.plane_work_item_id, comment)
            task.plane_sync = "linked" if task.plane_work_item_id else "retry_needed"
        except PlaneError:
            task.plane_sync = "retry_needed"
        db.commit()

    def enrollment_for(db, enrollment_id, user):
        row = db.get(Enrollment, enrollment_id)
        if row is None:
            raise HTTPException(404, "个人计划不存在")
        route = db.get(Route, row.route_id)
        _, member = team_member(db, route.team_id, user)
        if row.user_id != user.id and member.role != "owner":
            raise HTTPException(403, "无权查看该个人计划")
        return row, route

    def enrollment_json(db, row, user):
        route = db.get(Route, row.route_id)
        snapshot = filter_materials(db, row.snapshot or route_json(db, route), user)
        tasks = db.scalars(select(Task).where(Task.enrollment_id == row.id).order_by(Task.id)).all()
        stages, completed = [], 0
        for stage in snapshot.get("stages", []):
            members = [t for t in tasks if t.route_stage_id == stage.get("id") or (not t.route_stage_id and t.route_stage_title == stage.get("title"))]
            done = bool(members) and all(t.status == "done" for t in members)
            completed += int(done)
            stages.append({**stage, "tasks": [task_json(db, t) for t in members], "completed": done})
        meta = get_meta(db, "enrollment", row.id)
        return {"id": row.id, "routeId": row.route_id, "routeVersion": row.route_version,
                "title": snapshot.get("title", route.title), "description": snapshot.get("description", ""),
                "status": row.status, "stages": stages, "progress": {"completed": completed, "total": len(stages)},
                "note": meta.get("note", ""), "targetDate": meta.get("targetDate"), "userId": row.user_id,
                "planeSync": "retry_needed" if any(t.plane_sync == "retry_needed" for t in tasks) else "linked" if any(t.plane_sync == "linked" for t in tasks) else "not_configured"}

    @app.post("/api/v1/routes/{route_id}/enrollments")
    def enroll(route_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        route = route_for(db, route_id, user)
        row = db.scalar(select(Enrollment).where(Enrollment.route_id == route_id, Enrollment.user_id == user.id))
        if row is None:
            snapshot = route_json(db, route)
            row = Enrollment(route_id=route_id, user_id=user.id, snapshot=snapshot, route_version=route.version)
            try:
                db.add(row)
                db.flush()  # The existing (route_id, user_id) unique key serializes concurrent joins.
                reviewer = route.author_id
                if reviewer == user.id:
                    other = db.scalar(select(Member).where(Member.team_id == route.team_id, Member.role.in_(("mentor", "owner")), Member.user_id != user.id))
                    if other:
                        reviewer = other.user_id
                for stage in snapshot["stages"]:
                    for source in stage.get("tasks", []):
                        task = Task(team_id=route.team_id, title=source["title"], description=source.get("description", ""),
                                    acceptance_criteria=source.get("acceptanceCriteria", ""), assignee_id=user.id, reviewer_id=reviewer,
                                    enrollment_id=row.id, route_stage_title=stage["title"], route_stage_id=stage.get("id"))
                        db.add(task)
                        db.flush()
                        put_meta(db, "task", task.id, {"resourceIds": [r["id"] for r in stage.get("resources", [])]})
                db.commit()
            except IntegrityError:
                db.rollback()
                row = db.scalar(select(Enrollment).where(Enrollment.route_id == route_id, Enrollment.user_id == user.id))
                if row is None:
                    raise
        team = db.get(Team, route.team_id)
        tasks = db.scalars(select(Task).where(Task.enrollment_id == row.id)).all()
        for task in tasks:
            if task.plane_sync != "linked":
                sync_task(db, task, team)
        return {"data": enrollment_json(db, row, user)}

    @app.get("/api/v1/me/enrollments")
    def my_enrollments(teamId: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, teamId, user)
        rows = db.scalars(select(Enrollment).join(Route).where(Route.team_id == teamId, Enrollment.user_id == user.id).order_by(Enrollment.id)).all()
        return {"data": {"items": [enrollment_json(db, row, user) for row in rows], "total": len(rows)}}

    @app.get("/api/v1/enrollments/{enrollment_id}")
    def get_enrollment(enrollment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, _ = enrollment_for(db, enrollment_id, user)
        return {"data": enrollment_json(db, row, user)}

    @app.patch("/api/v1/enrollments/{enrollment_id}")
    def edit_enrollment(enrollment_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, _ = enrollment_for(db, enrollment_id, user)
        if row.user_id != user.id:
            raise HTTPException(403, "只有计划本人可调整")
        if "status" in payload:
            if payload["status"] not in ("active", "paused"):
                raise HTTPException(400, "计划状态无效")
            row.status = payload["status"]
        changes = {}
        if "note" in payload:
            changes["note"] = text_value(payload, "note")
        if "targetDate" in payload:
            raw = payload["targetDate"]
            try:
                changes["targetDate"] = datetime.strptime(raw, "%Y-%m-%d").date().isoformat() if raw else None
            except (ValueError, TypeError):
                raise HTTPException(400, "目标日期格式应为 YYYY-MM-DD")
        put_meta(db, "enrollment", row.id, changes)
        db.commit()
        return {"data": enrollment_json(db, row, user)}

    def validate_assignment(db, team_id, assignee_id, reviewer_id):
        members = {m.user_id: m for m in db.scalars(select(Member).where(Member.team_id == team_id)).all()}
        if assignee_id not in members or reviewer_id not in members or members[reviewer_id].role not in ("mentor", "owner"):
            raise HTTPException(400, "执行人与审核人须在本组，审核人须为前辈或负责人")
        if assignee_id == reviewer_id:
            raise HTTPException(400, "执行人与审核人不能相同")

    def task_metadata(payload):
        priority = payload.get("priority", "normal")
        if priority not in ("none", "low", "normal", "medium", "high", "urgent"):
            raise HTTPException(400, "优先级无效")
        return {"priority": priority, "dueAt": iso(timestamp(payload.get("dueAt")))}

    @app.post("/api/v1/teams/{team_id}/tasks")
    def create_task(team_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        team, member = team_member(db, team_id, user)
        can_manage(member)
        validate_assignment(db, team_id, payload.get("assigneeId"), payload.get("reviewerId"))
        meeting_id = payload.get("meetingId") or None
        if meeting_id:
            meeting = db.get(Meeting, meeting_id)
            if meeting is None or meeting.team_id != team_id or meeting.status == "archived":
                raise HTTPException(400, "组会不属于本组或已归档")
        task = Task(team_id=team_id, title=text_value(payload, "title", maximum=200, required=True),
                    description=text_value(payload, "description"), acceptance_criteria=text_value(payload, "acceptanceCriteria"),
                    assignee_id=payload["assigneeId"], reviewer_id=payload["reviewerId"], meeting_id=meeting_id)
        db.add(task)
        db.flush()
        put_meta(db, "task", task.id, task_metadata(payload))
        notify(db, task.assignee_id, f"新任务：{task.title}", team_id, "task", task.id)
        db.commit()
        sync_task(db, task, team)
        return {"data": task_json(db, task)}

    @app.post("/api/v1/enrollments/{enrollment_id}/tasks")
    def plan_task(enrollment_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row, route = enrollment_for(db, enrollment_id, user)
        if row.user_id != user.id:
            raise HTTPException(403, "只有计划本人可添加任务")
        stages = (row.snapshot or route_json(db, route)).get("stages", [])
        stage = next((s for s in stages if s.get("id") == payload.get("stageId")), None)
        if stage is None:
            raise HTTPException(400, "请选择个人计划中的阶段")
        reviewer = payload.get("reviewerId") or route.author_id
        validate_assignment(db, route.team_id, user.id, reviewer)
        task = Task(team_id=route.team_id, title=text_value(payload, "title", maximum=200, required=True),
                    description=text_value(payload, "description"), acceptance_criteria=text_value(payload, "acceptanceCriteria"),
                    assignee_id=user.id, reviewer_id=reviewer, enrollment_id=row.id, route_stage_id=stage["id"], route_stage_title=stage["title"])
        db.add(task)
        db.flush()
        put_meta(db, "task", task.id, task_metadata(payload))
        db.commit()
        sync_task(db, task, db.get(Team, route.team_id))
        return {"data": task_json(db, task)}

    @app.get("/api/v1/me/tasks")
    def my_tasks(teamId: str, status: str | None = None, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, teamId, user)
        query = select(Task).where(Task.team_id == teamId, Task.assignee_id == user.id)
        if status:
            query = query.where(Task.status == status)
        return page_data([task_json(db, t) for t in db.scalars(query.order_by(Task.id)).all()], page, pageSize)

    @app.get("/api/v1/teams/{team_id}/tasks")
    def team_tasks(team_id: str, status: str | None = None, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, member = team_member(db, team_id, user)
        rows = db.scalars(select(Task).where(Task.team_id == team_id).order_by(Task.id)).all()
        return page_data([task_json(db, t) for t in rows if task_visible(t, member, user) and (not status or t.status == status)], page, pageSize)

    @app.get("/api/v1/me/review-queue")
    def review_queue(teamId: str, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, member = team_member(db, teamId, user)
        can_manage(member)
        rows = db.scalars(select(Task).where(Task.team_id == teamId, Task.status == "review", Task.assignee_id != user.id)).all()
        return page_data([task_json(db, t) for t in rows if t.reviewer_id == user.id or member.role == "owner"], page, pageSize)

    def task_detail(db, task, user):
        submissions = db.scalars(select(Submission).where(Submission.task_id == task.id).order_by(Submission.created_at.desc(), Submission.id)).all()
        resource_ids = get_meta(db, "task", task.id).get("resourceIds", [])
        resources = db.scalars(select(Resource).where(or_(Resource.task_id == task.id, Resource.id.in_(resource_ids)))).all()
        resources = list({r.id:r for r in resources + referenced_resources(db, "task", task.id)}.values())
        return {**task_json(db, task), "resources": [resource_json(db, r, user) for r in resources if resource_visible(db, r, user)],
                "submissions": [{"id": s.id, "summary": s.summary, "url": s.url, "createdAt": iso(s.created_at), "userId": s.user_id,
                    "reviews": [{"id": r.id, "decision": r.decision, "comment": r.comment, "reviewer": name(db, r.reviewer_id),
                                 "createdAt": iso(r.created_at)} for r in db.scalars(select(Review).where(Review.submission_id == s.id).order_by(Review.created_at)).all()]}
                    for s in submissions]}

    @app.get("/api/v1/tasks/{task_id}")
    def get_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        task, _, _ = task_for(db, task_id, user)
        return {"data": task_detail(db, task, user)}

    @app.patch("/api/v1/tasks/{task_id}")
    def edit_task(task_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        task, _, member = task_for(db, task_id, user)
        expected = task.revision
        if "revision" in payload and payload["revision"] != expected:
            raise HTTPException(409, "任务已更新，请刷新")
        values = {"revision": expected+1}
        if "status" in payload:
            if payload["status"] not in ("todo", "doing", "blocked"):
                raise HTTPException(400, "完成状态必须通过成果审核变更")
            if task.status in ("review", "done"):
                raise HTTPException(409, "待审或已完成任务不可直接修改状态")
            values["status"] = payload["status"]
        if "blocker" in payload:
            values["blocker"] = text_value(payload, "blocker")
        management_fields = {"title", "description", "acceptanceCriteria", "reviewerId", "dueAt", "priority"} & payload.keys()
        if management_fields:
            can_manage(member)
            if task.status in ("review", "done"):
                raise HTTPException(409, "待审或已完成任务的验收要求不可修改")
            for key, column in (("title", "title"), ("description", "description"), ("acceptanceCriteria", "acceptance_criteria")):
                if key in payload:
                    values[column] = text_value(payload, key, maximum=200 if key == "title" else 50000, required=key == "title")
            if "reviewerId" in payload:
                validate_assignment(db, task.team_id, task.assignee_id, payload["reviewerId"])
                values["reviewer_id"] = payload["reviewerId"]
        if db.execute(update(Task).where(Task.id == task.id, Task.revision == expected).values(**values)).rowcount != 1:
            raise HTTPException(409, "任务已更新，请刷新")
        if management_fields:
            put_meta(db, "task", task.id, task_metadata({**get_meta(db, "task", task.id), **payload}))
        db.commit()
        db.refresh(task)
        sync_task(db, task, db.get(Team, task.team_id))
        return {"data": task_json(db, task)}

    @app.post("/api/v1/tasks/{task_id}/submissions")
    def submit_task(task_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        task, _, _ = task_for(db, task_id, user)
        if task.assignee_id != user.id:
            raise HTTPException(403, "只有任务执行人可以提交")
        summary = text_value(payload, "summary", required=True)
        url = text_value(payload, "url", maximum=2048)
        if url and (urlparse(url).scheme not in ("https", "http") or not urlparse(url).netloc):
            raise HTTPException(400, "成果链接必须是有效的 HTTP(S) 地址")
        ident = str(uuid4())
        result = db.execute(update(Task).where(Task.id == task.id, Task.revision == task.revision, Task.status.in_(("todo", "doing", "blocked")))
                            .values(status="review", blocker="", latest_submission_id=ident, revision=Task.revision+1))
        if result.rowcount != 1:
            raise HTTPException(409, "已有待审提交或任务已完成，请刷新")
        db.add(Submission(id=ident, task_id=task.id, user_id=user.id, summary=summary, url=url))
        notify(db, task.reviewer_id, f"待审核：{task.title}", task.team_id, "task", task.id)
        db.commit()
        db.refresh(task)
        sync_task(db, task, db.get(Team, task.team_id), f"提交成果：{summary}\n{url}")
        return {"data": {"id": ident, "taskStatus": "review"}}

    @app.post("/api/v1/submissions/{submission_id}/reviews")
    def review_submission(submission_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        submission = db.get(Submission, submission_id)
        if submission is None:
            raise HTTPException(404, "成果提交不存在")
        task, _, member = task_for(db, submission.task_id, user)
        can_manage(member)
        if user.id == submission.user_id or user.id == task.assignee_id or (task.reviewer_id != user.id and member.role != "owner"):
            raise HTTPException(403, "只能由独立审核人或负责人审批，禁止自审")
        decision = payload.get("decision")
        if decision not in ("approved", "changes_requested"):
            raise HTTPException(400, "审批决定无效")
        comment = text_value(payload, "comment", required=True)
        latest = task.latest_submission_id
        if not latest:
            latest = db.scalar(select(Submission.id).where(Submission.task_id == task.id).order_by(Submission.created_at.desc(), Submission.id.desc()).limit(1))
        if latest != submission_id:
            raise HTTPException(409, "只能审批最新提交")
        state = "done" if decision == "approved" else "doing"
        result = db.execute(update(Task).where(Task.id == task.id, Task.revision == task.revision, Task.status == "review",
                            Task.latest_submission_id == task.latest_submission_id).values(status=state, revision=Task.revision+1))
        if result.rowcount != 1 or db.scalar(select(Review.id).where(Review.submission_id == submission_id)):
            raise HTTPException(409, "该成果已被审批，请刷新")
        review = Review(submission_id=submission_id, reviewer_id=user.id, comment=comment, decision=decision)
        db.add(review)
        notify(db, task.assignee_id, f"{'审核通过' if state == 'done' else '需要修改'}：{task.title}", task.team_id, "task", task.id)
        db.commit()
        db.refresh(task)
        sync_task(db, task, db.get(Team, task.team_id), f"{decision}：{comment}")
        return {"data": {"id": review.id, "taskStatus": state}}

    @app.patch("/api/v1/experiences/{experience_id}")
    def edit_experience(experience_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row=db.get(Experience,experience_id)
        if row is None: raise HTTPException(404,"经验不存在")
        _,member=team_member(db,row.team_id,user)
        if row.author_id!=user.id and member.role!="owner": raise HTTPException(403,"无权编辑")
        row.title=text_value(payload,"title",row.title,100,True); row.starting_point=text_value(payload,"startingPoint",row.starting_point,3000,True); row.content=text_value(payload,"content",row.content,50000,True)
        put_meta(db,"experience",row.id,{"tags":tags(payload)}); db.commit()
        return {"data":{"id":row.id}}

    @app.put("/api/v1/experiences/{experience_id}/bookmark")
    def bookmark(experience_id: str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=db.get(Experience,experience_id)
        if row is None: raise HTTPException(404,"经验不存在")
        team_member(db,row.team_id,user)
        if not db.scalar(select(Bookmark).where(Bookmark.user_id==user.id,Bookmark.experience_id==experience_id)): db.add(Bookmark(user_id=user.id,experience_id=experience_id));db.commit()
        return {"data":{"experienceId":experience_id}}

    @app.delete("/api/v1/experiences/{experience_id}/bookmark")
    def unbookmark(experience_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        db.execute(delete(Bookmark).where(Bookmark.user_id==user.id,Bookmark.experience_id==experience_id));db.commit();return {"data":None}

    @app.get("/api/v1/me/bookmarks")
    def bookmarks(teamId:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        team_member(db,teamId,user); rows=db.scalars(select(Bookmark).join(Experience,Experience.id==Bookmark.experience_id).where(Bookmark.user_id==user.id,Experience.team_id==teamId)).all()
        return {"data":{"items":[{"id":r.id,"experienceId":r.experience_id} for r in rows],"total":len(rows)}}

    @app.patch("/api/v1/meetings/{meeting_id}")
    def edit_meeting(meeting_id:str,payload:dict=Body(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=db.get(Meeting,meeting_id)
        if row is None: raise HTTPException(404,"组会不存在")
        _,member=team_member(db,row.team_id,user);can_manage(member)
        if "title" in payload: row.title=text_value(payload,"title",maximum=200,required=True)
        if "startsAt" in payload: row.starts_at=timestamp(payload["startsAt"])
        if "location" in payload: row.location=text_value(payload,"location",maximum=200,required=True)
        if "agenda" in payload: row.agenda=text_value(payload,"agenda",required=True)
        if "status" in payload:
            if payload["status"] not in ("scheduled","completed","archived"): raise HTTPException(400,"组会状态无效")
            row.status=payload["status"]
        db.commit();return {"data":{"id":row.id,"status":row.status}}

    @app.get("/api/v1/teams/{team_id}/meetings")
    def rich_meetings(team_id:str,page:int=1,pageSize:int=20,user:User=Depends(current_user),db:Session=Depends(get_db)):
        team_member(db,team_id,user);rows=db.scalars(select(Meeting).where(Meeting.team_id==team_id).order_by(Meeting.starts_at.desc())).all();items=[{"id":r.id,"title":r.title,"startsAt":iso(r.starts_at),"location":r.location,"agenda":r.agenda,"status":r.status} for r in rows];return page_data(items,page,pageSize)

    @app.get("/api/v1/meetings/{meeting_id}")
    def rich_meeting(meeting_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=db.get(Meeting,meeting_id)
        if not row: raise HTTPException(404,"组会不存在")
        team_member(db,row.team_id,user);questions=db.scalars(select(MeetingQuestion).where(MeetingQuestion.meeting_id==row.id).order_by(MeetingQuestion.created_at)).all();tasks=db.scalars(select(Task).where(Task.meeting_id==row.id)).all();resources=db.scalars(select(Resource).where(Resource.meeting_id==row.id)).all()
        resources = list({r.id:r for r in resources + referenced_resources(db, "meeting", row.id)}.values())
        return {"data":{"id":row.id,"title":row.title,"startsAt":iso(row.starts_at),"location":row.location,"agenda":row.agenda,"status":row.status,"minutes":{"content":row.minutes_content,"updatedAt":iso(row.minutes_updated_at)} if row.minutes_content is not None else None,"questions":[{"id":q.id,"authorId":q.author_id,"author":name(db,q.author_id),"content":q.content,"answer":q.answer,"status":q.status,"createdAt":iso(q.created_at)} for q in questions],"tasks":[task_json(db,t) for t in tasks],"resources":[resource_json(db,r,user) for r in resources if resource_visible(db,r,user)]}}

    @app.post("/api/v1/meetings/{meeting_id}/questions")
    def add_meeting_question(meeting_id:str,payload:dict=Body(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        meeting=db.get(Meeting,meeting_id)
        if meeting is None: raise HTTPException(404,"组会不存在")
        team_member(db,meeting.team_id,user);row=MeetingQuestion(meeting_id=meeting_id,author_id=user.id,content=text_value(payload,"content",required=True));db.add(row);db.commit();return {"data":{"id":row.id}}

    @app.patch("/api/v1/meeting-questions/{question_id}")
    def answer_question(question_id:str,payload:dict=Body(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=db.get(MeetingQuestion,question_id);meeting=db.get(Meeting,row.meeting_id) if row else None
        if not row or not meeting: raise HTTPException(404,"问题不存在")
        _,member=team_member(db,meeting.team_id,user);can_manage(member);row.answer=text_value(payload,"answer",required=True);row.status="resolved";db.commit();return {"data":{"id":row.id}}

    @app.patch("/api/v1/resources/{resource_id}")
    def edit_resource(resource_id:str,payload:dict=Body(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        row,member=resource_for(db,resource_id,user,True)
        if "title" in payload: row.title=text_value(payload,"title",maximum=200,required=True)
        if "description" in payload: row.description=text_value(payload,"description")
        if payload.get("visibility") in ("team","private"): row.visibility=payload["visibility"]
        put_meta(db,"resource",row.id,{"tags":tags(payload)});db.commit();return {"data":{"id":row.id}}

    @app.get("/api/v1/resources/{resource_id}/versions")
    def resource_versions(resource_id:str,page:int=1,pageSize:int=100,user:User=Depends(current_user),db:Session=Depends(get_db)):
        resource_for(db,resource_id,user);rows=db.scalars(select(ResourceVersion).where(ResourceVersion.resource_id==resource_id).order_by(ResourceVersion.version)).all();items=[{"id":r.id,"version":r.version,"note":r.note,"size":r.size,"createdAt":iso(r.created_at),"author":name(db,r.author_id)} for r in rows];return page_data(items,page,pageSize)

    @app.post("/api/v1/resources/{resource_id}/versions")
    async def add_resource_version(resource_id:str,note:str=Form(""),file:UploadFile=File(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        row,_=resource_for(db,resource_id,user,True);content=await file.read(int(os.getenv("MAX_UPLOAD_BYTES",20*1024*1024))+1)
        if not content or len(content)>int(os.getenv("MAX_UPLOAD_BYTES",20*1024*1024)): raise HTTPException(413,"文件为空或过大")
        storage=str(uuid4());(uploads/storage).write_bytes(content);row.version+=1;version=ResourceVersion(resource_id=row.id,version=row.version,file_name=(file.filename or "file")[:255],storage_name=storage,size=len(content),note=note[:50000],author_id=user.id);db.add(version);db.commit();return {"data":{"id":version.id,"version":version.version}}

    @app.get("/api/v1/teams/{team_id}/progress")
    def progress(team_id:str,page:int=1,pageSize:int=100,user:User=Depends(current_user),db:Session=Depends(get_db)):
        team_member(db,team_id,user);rows=db.scalars(select(ProgressPost).where(ProgressPost.team_id==team_id).order_by(ProgressPost.created_at.desc())).all();items=[]
        for r in rows:
            comments=db.scalars(select(ProgressComment).where(ProgressComment.post_id==r.id)).all();items.append({"id":r.id,"authorId":r.author_id,"author":name(db,r.author_id),"content":r.content,"blockers":r.blockers,"nextPlan":r.next_plan,"kind":r.kind,"status":r.status,"createdAt":iso(r.created_at),"comments":[{"id":c.id,"author":name(db,c.author_id),"content":c.content,"createdAt":iso(c.created_at)} for c in comments]})
        return page_data(items,page,pageSize)

    @app.post("/api/v1/teams/{team_id}/progress")
    def add_progress(team_id:str,payload:dict=Body(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        team_member(db,team_id,user);row=ProgressPost(team_id=team_id,author_id=user.id,content=text_value(payload,"content",required=True),blockers=text_value(payload,"blockers"),next_plan=text_value(payload,"nextPlan"),kind=payload.get("kind") if payload.get("kind") in ("progress","help") else "progress");db.add(row);db.commit();return {"data":{"id":row.id}}

    @app.post("/api/v1/progress/{post_id}/comments")
    def add_progress_comment(post_id:str,payload:dict=Body(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        post=db.get(ProgressPost,post_id)
        if not post: raise HTTPException(404,"记录不存在")
        team_member(db,post.team_id,user);row=ProgressComment(post_id=post.id,author_id=user.id,content=text_value(payload,"content",required=True));db.add(row);db.commit();return {"data":{"id":row.id}}

    @app.patch("/api/v1/progress/{post_id}")
    def resolve_progress(post_id:str,payload:dict=Body(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=db.get(ProgressPost,post_id)
        if not row: raise HTTPException(404,"记录不存在")
        _,member=team_member(db,row.team_id,user)
        if row.author_id!=user.id and member.role!="owner": raise HTTPException(403,"无权操作")
        row.status="resolved" if payload.get("status")=="resolved" else "open";db.commit();return {"data":{"id":row.id,"status":row.status}}

    @app.post("/api/v1/me/notifications/read-all")
    def read_all(user:User=Depends(current_user),db:Session=Depends(get_db)):
        db.execute(update(Notification).where(Notification.user_id==user.id).values(read=True));db.commit();return {"data":None}

    @app.get("/api/v1/teams/{team_id}/handovers")
    def list_handovers(team_id:str,page:int=1,pageSize:int=100,user:User=Depends(current_user),db:Session=Depends(get_db)):
        team_member(db,team_id,user);rows=db.scalars(select(Handover).where(Handover.team_id==team_id).order_by(Handover.created_at.desc())).all()
        items=[{"id":r.id,"title":r.title,"content":r.content,"fromUserId":r.from_user_id,"fromUserName":name(db,r.from_user_id),"toUserId":r.to_user_id,"toUserName":name(db,r.to_user_id),"taskIds":r.task_ids or [],"resourceIds":r.resource_ids or [],"status":r.status,"createdAt":iso(r.created_at),"acceptedAt":iso(r.accepted_at)} for r in rows]
        return page_data(items,page,pageSize)

    @app.post("/api/v1/teams/{team_id}/handovers")
    def create_handover(team_id:str,payload:dict=Body(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        team_member(db,team_id,user);to_user=text_value(payload,"toUserId",maximum=36,required=True)
        if to_user==user.id or not db.scalar(select(Member.id).where(Member.team_id==team_id,Member.user_id==to_user)): raise HTTPException(400,"请选择课题组内的接收人")
        task_ids=[str(x) for x in payload.get("taskIds",[])];resource_ids=[str(x) for x in payload.get("resourceIds",[])]
        for rid in resource_ids:
            resource_for(db,rid,user)
        for tid in task_ids:
            task_for(db,tid,user)
        row=Handover(team_id=team_id,from_user_id=user.id,to_user_id=to_user,title=text_value(payload,"title",maximum=200,required=True),content=text_value(payload,"content",required=True),task_ids=task_ids,resource_ids=resource_ids)
        db.add(row);notify(db,to_user,f"收到科研交接：{row.title}",team_id,"handover",row.id);db.commit();return {"data":{"id":row.id}}

    @app.post("/api/v1/handovers/{handover_id}/accept")
    def accept_handover(handover_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row=db.get(Handover,handover_id)
        if not row: raise HTTPException(404,"交接记录不存在")
        team_member(db,row.team_id,user)
        if row.to_user_id!=user.id: raise HTTPException(403,"只有接收人可以确认交接")
        if row.status!="accepted":
            row.status="accepted";row.accepted_at=datetime.now(timezone.utc)
            for rid in row.resource_ids or []:
                resource=db.get(Resource,rid)
                # Ownership transfer is deliberately not inferred from a legacy handover.
                if resource and not resource_visible(db,resource,user): raise HTTPException(403,"请先由所有者明确共享交接资料")
            db.commit()
        return {"data":{"id":row.id,"status":row.status,"acceptedAt":iso(row.accepted_at)}}

    @app.get("/api/v1/teams/{team_id}/export")
    def export_team(team_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        team,member_of_team=team_member(db,team_id,user)
        tasks=db.scalars(select(Task).where(Task.team_id==team_id)).all();meetings=db.scalars(select(Meeting).where(Meeting.team_id==team_id)).all();resources=db.scalars(select(Resource).where(Resource.team_id==team_id)).all();experiences=db.scalars(select(Experience).where(Experience.team_id==team_id)).all()
        content={"exportedAt":iso(datetime.now(timezone.utc)),"team":{"id":team.id,"name":team.name},"tasks":[task_json(db,r) for r in tasks if task_visible(r,member_of_team,user)],"meetings":[{"id":r.id,"title":r.title,"startsAt":iso(r.starts_at),"location":r.location,"agenda":r.agenda,"status":r.status} for r in meetings],"resources":[resource_json(db,r,user) for r in resources if resource_visible(db,r,user)],"experiences":[{"id":r.id,"title":r.title,"startingPoint":r.starting_point,"content":r.content,"author":name(db,r.author_id),"createdAt":iso(r.created_at)} for r in experiences]}
        return JSONResponse(content=content,headers={"Content-Disposition":f'attachment; filename="research-export-{team_id}.json"'})

    @app.get("/api/v1/teams/{team_id}/resources")
    def rich_resources(team_id:str,page:int=1,pageSize:int=20,user:User=Depends(current_user),db:Session=Depends(get_db)):
        team_member(db,team_id,user);rows=db.scalars(select(Resource).where(Resource.team_id==team_id).order_by(Resource.title,Resource.id)).all();items=[resource_json(db,r,user) for r in rows if resource_visible(db,r,user)];return page_data(items,page,pageSize)

    @app.get("/api/v1/resources/{resource_id}")
    def rich_resource(resource_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row,_=resource_for(db,resource_id,user);return {"data":resource_json(db,row,user)}

    @app.get("/api/v1/resources/{resource_id}/download")
    def versioned_download(resource_id:str,versionId:str="",user:User=Depends(current_user),db:Session=Depends(get_db)):
        row,_=resource_for(db,resource_id,user);filename=row.file_name;storage=row.storage_name
        if versionId:
            version=db.get(ResourceVersion,versionId)
            if not version or version.resource_id!=row.id: raise HTTPException(404,"资料版本不存在")
            filename=version.file_name;storage=version.storage_name
        location=uploads/storage
        if not location.is_file(): raise HTTPException(404,"文件暂时不可用")
        return FileResponse(location,media_type="application/octet-stream",filename=filename)

    @app.get("/api/v1/resources/{resource_id}/preview")
    def preview_resource(resource_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        row,_=resource_for(db,resource_id,user);media_type=preview_media_type(row.file_name)
        if not media_type: raise HTTPException(415,"该文件格式不支持浏览器在线预览，请下载后查看")
        location=uploads/row.storage_name
        if not location.is_file(): raise HTTPException(404,"文件暂时不可用")
        safe_name=quote(row.file_name.encode("utf-8"))
        return FileResponse(location,media_type=media_type,headers={"Content-Disposition":f"inline; filename*=UTF-8''{safe_name}","X-Content-Type-Options":"nosniff"})

    @app.get("/api/v1/resources/{resource_id}/reading-progress")
    def get_reading_progress(resource_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
        resource_for(db,resource_id,user);return {"data":get_meta(db,"reading",f"{resource_id}:{user.id}")}

    @app.patch("/api/v1/resources/{resource_id}/reading-progress")
    def save_reading_progress(resource_id:str,payload:dict=Body(),user:User=Depends(current_user),db:Session=Depends(get_db)):
        resource_for(db,resource_id,user);values={}
        if "ratio" in payload: values["ratio"]=max(0.0,min(1.0,float(payload["ratio"])))
        if "page" in payload: values["page"]=max(1,min(100000,int(payload["page"])))
        if "time" in payload: values["time"]=max(0.0,float(payload["time"]))
        if "notes" in payload: values["notes"]=str(payload["notes"])[:50000]
        values["updatedAt"]=iso(datetime.now(timezone.utc));put_meta(db,"reading",f"{resource_id}:{user.id}",values);db.commit();return {"data":values}

    @app.get("/api/v1/plane/projects")
    def plane_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
        if not db.scalar(select(Member.id).where(Member.user_id == user.id, Member.role.in_(("owner", "mentor")))):
            raise HTTPException(403, "需要前辈或负责人权限")
        try:
            rows = plane.list_allowed_projects(os.getenv("PLANE_ALLOWED_PROJECTS", "")) if hasattr(plane, "list_allowed_projects") else []
        except PlaneError as error:
            raise HTTPException(502, str(error)) from error
        return {"data": {"items": rows, "total": len(rows)}}

    @app.get("/api/v1/me/dashboard")
    def drive_dashboard(teamId: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, member = team_member(db, teamId, user)
        tasks = db.scalars(select(Task).where(Task.team_id == teamId, Task.assignee_id == user.id, Task.status != "done")).all()
        tasks.sort(key=lambda t: (get_meta(db, "task", t.id).get("dueAt") or "9999", t.id))
        plans = my_enrollments(teamId, user, db)["data"]["items"]
        upcoming = db.scalar(select(Meeting).where(Meeting.team_id == teamId, Meeting.status == "scheduled", Meeting.starts_at >= utcnow()).order_by(Meeting.starts_at).limit(1))
        reviews = review_queue(teamId, 1, 100, user, db)["data"]["total"] if member.role in ("owner", "mentor") else 0
        return {"data": {"currentTask": task_json(db, tasks[0]) if tasks else None,
            "progress": {"completed": sum(p["progress"]["completed"] for p in plans), "total": sum(p["progress"]["total"] for p in plans)},
            "reviewCount": reviews, "nextMeeting": {"id": upcoming.id, "title": upcoming.title, "startsAt": iso(upcoming.starts_at), "location": upcoming.location, "status": upcoming.status} if upcoming else None}}

    def referenced_resources(db, kind, ident):
        ids = db.scalars(select(ResourceReference.resource_id).where(ResourceReference.target_type == kind, ResourceReference.target_id == ident)).all()
        return list(db.scalars(select(Resource).where(Resource.id.in_(ids)))) if ids else []

    from .cloud_drive import register_cloud_drive
    before_drive = list(app.router.routes)
    register_cloud_drive(app, locals())
    drive_routes = [r for r in app.router.routes if r not in before_drive]
    replaced = {(r.path, m) for r in drive_routes for m in r.methods}
    app.router.routes[:] = drive_routes + [r for r in before_drive if not any((getattr(r, 'path', ''), m) in replaced for m in (getattr(r, 'methods', None) or []))]
    # Remove superseded compatibility routes so runtime and OpenAPI agree.
    seen, unique = set(), []
    for route in app.router.routes:
        keys = {(getattr(route, 'path', ''), m) for m in (getattr(route, 'methods', None) or [])}
        # features handlers win over app.py handlers, except drive overrides above.
        if id(route) in {id(r) for r in previous}:
            continue
        if not keys.intersection(seen): unique.append(route); seen.update(keys)
    for route in previous:
        keys = {(getattr(route, 'path', ''), m) for m in (getattr(route, 'methods', None) or [])}
        if not keys.intersection(seen): unique.append(route); seen.update(keys)
    app.router.routes[:] = unique
