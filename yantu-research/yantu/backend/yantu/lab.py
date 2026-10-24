"""Membership-protected API for one laboratory and its research projects.

The previous extension tables remain intact. Registering this surface removes
obsolete routes, including the old personal-drive permission bypasses.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import mimetypes
import os
from pathlib import Path
import re
from urllib.parse import quote
from uuid import uuid4

from fastapi import Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .lab_models import BrowseHistory, JoinRequest, LabComment, LabMessage
from .models import EntityData, Meeting, Member, Resource, ResourceReference, ResourceShare, ResourceVersion, Task, Team, User, utcnow
from .cloud_drive import resource_for as accessible_resource, resource_visible
from .security import hash_password
from .version import VERSION


DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".md", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip"}
VIDEO_TYPES = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".m4v": "video/mp4", ".avi": "video/x-msvideo", ".mkv": "video/x-matroska"}


def register_lab(app, context):
    get_db = context["get_db"]
    current_user = context["current_user"]
    team_member = context["team_member"]
    uploads = context["uploads"]
    iso = context["iso"]

    # Retain only the personal-drive routes using the unified resource policy.
    # Legacy invitations, learning, assistant and task-feedback routes stay closed.
    retained = {"/healthz", "/api/v1/auth/login",
                "/api/v1/auth/logout", "/api/v1/auth/refresh", "/api/v1/me"}
    cloud_paths = {"/api/v1/me/drive/" + suffix for suffix in (
        "config", "folders/tree", "children", "folders", "folders/{folder_id}",
        "search", "shared", "available-resources", "files")}
    cloud_routes = {(path, method) for path in cloud_paths for method in ("GET", "POST", "PATCH", "DELETE")}
    cloud_routes |= {("/api/v1/resources/{resource_id}", "PATCH")}
    cloud_routes |= {("/api/v1/resources/{resource_id}/versions", method) for method in ("GET", "POST")}
    cloud_routes |= {("/api/v1/resources/{resource_id}/shares", "GET"),
                     ("/api/v1/resources/{resource_id}/shares/{user_id}", "PUT"),
                     ("/api/v1/resources/{resource_id}/shares/{user_id}", "DELETE")}
    app.router.routes[:] = [route for route in app.router.routes
                           if not getattr(route, "path", "").startswith("/api/v1/")
                           or getattr(route, "path", "") in retained
                           or any((getattr(route, "path", ""), method) in cloud_routes for method in (getattr(route, "methods", None) or []))]
    app.openapi_schema = None

    def text_value(payload, key, default="", maximum=50000, required=False):
        value = payload.get(key, default)
        if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
            raise HTTPException(400, f"{key} 不能为空或超过长度限制")
        return value.strip()

    def timestamp(value, required=False):
        if value is None or value == "":
            if required:
                raise HTTPException(400, "请选择时间")
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            raise HTTPException(400, "时间必须包含时区")

    def meta(db, kind, ident):
        row = db.get(EntityData, f"{kind}:{ident}")
        return dict(row.data or {}) if row else {}

    def put_meta(db, kind, ident, values):
        key = f"{kind}:{ident}"
        row = db.get(EntityData, key)
        if row is None:
            row = EntityData(key=key, data={})
            db.add(row)
        row.data = {**(row.data or {}), **values}
        return row.data

    def user_name(db, user_id):
        person = db.get(User, user_id)
        return person.display_name if person else "已离组成员"

    def project_for(db, project_id):
        project = db.get(Team, project_id)
        if project is None:
            raise HTTPException(404, "课题不存在")
        return project

    def membership(db, project_id, user_id):
        return db.scalar(select(Member).where(Member.team_id == project_id, Member.user_id == user_id))

    def require_role(db, project_id, user, roles=("owner",)):
        project, member = team_member(db, project_id, user)
        if member.role not in roles:
            raise HTTPException(403, "需要课题负责人权限" if roles == ("owner",) else "需要前辈或负责人权限")
        return project

    def project_json(db, project, user):
        member = membership(db, project.id, user.id)
        request = db.scalar(select(JoinRequest).where(JoinRequest.team_id == project.id, JoinRequest.user_id == user.id))
        status = "member" if member else request.status if request and request.status in ("pending", "rejected") else "none"
        pending = db.scalar(select(func.count()).select_from(JoinRequest).where(JoinRequest.team_id == project.id, JoinRequest.status == "pending")) if member and member.role == "owner" else 0
        return {"id": project.id, "name": project.name, "description": meta(db, "team", project.id).get("description", ""),
                "role": member.role if member else None, "membershipStatus": status,
                "memberCount": db.scalar(select(func.count()).select_from(Member).where(Member.team_id == project.id)) or 0,
                "pendingCount": pending or 0}

    def request_json(db, row):
        person = db.get(User, row.user_id)
        return {"id": row.id, "userId": row.user_id, "displayName": person.display_name, "email": person.email,
                "message": row.message, "status": row.status, "createdAt": iso(row.created_at)}

    def list_data(items, **extra):
        return {"data": {"items": items, "total": len(items), **extra}}

    @app.get("/api/v1/system/status")
    def system_status(db: Session = Depends(get_db)):
        return {"data": {"version": VERSION, "edition": "laboratory", "initialized": bool(db.scalar(select(func.count()).select_from(User))), "registrationOpen": True}}

    @app.post("/api/v1/auth/register", status_code=201)
    def register(payload: dict = Body(), db: Session = Depends(get_db)):
        email = text_value(payload, "email", maximum=254, required=True).lower()
        display_name = text_value(payload, "displayName", maximum=100, required=True)
        password = payload.get("password")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not isinstance(password, str) or not 12 <= len(password) <= 1024:
            raise HTTPException(400, "请输入有效邮箱及至少 12 位的密码")
        if db.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(409, "此邮箱已注册，请直接登录")
        user = User(email=email, display_name=display_name, password_hash=hash_password(password))
        db.add(user)
        db.commit()
        return {"data": {"id": user.id}}

    @app.get("/api/v1/lab/projects")
    def projects(scope: str = Query("all", pattern="^(all|joined)$"), user: User = Depends(current_user), db: Session = Depends(get_db)):
        query = select(Team).order_by(Team.name, Team.id)
        if scope == "joined":
            query = query.join(Member, Member.team_id == Team.id).where(Member.user_id == user.id)
        return list_data([project_json(db, row, user) for row in db.scalars(query)])

    @app.post("/api/v1/lab/projects", status_code=201)
    def create_project(payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = Team(name=text_value(payload, "name", maximum=100, required=True))
        description = text_value(payload, "description", maximum=10000)
        db.add(row)
        db.flush()
        db.add(Member(team_id=row.id, user_id=user.id, role="owner"))
        put_meta(db, "team", row.id, {"description": description})
        db.commit()
        return {"data": project_json(db, row, user)}

    @app.get("/api/v1/lab/projects/{project_id}")
    def project_detail(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        return {"data": project_json(db, project_for(db, project_id), user)}

    @app.patch("/api/v1/lab/projects/{project_id}")
    def update_project(project_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = require_role(db, project_id, user)
        if "name" in payload:
            row.name = text_value(payload, "name", maximum=100, required=True)
        if "description" in payload:
            put_meta(db, "team", row.id, {"description": text_value(payload, "description", maximum=10000)})
        db.commit()
        return {"data": project_json(db, row, user)}

    @app.post("/api/v1/lab/projects/{project_id}/join-requests")
    def request_join(project_id: str, payload: dict = Body(default={}), user: User = Depends(current_user), db: Session = Depends(get_db)):
        project_for(db, project_id)
        if membership(db, project_id, user.id):
            raise HTTPException(409, "你已加入此课题")
        row = db.scalar(select(JoinRequest).where(JoinRequest.team_id == project_id, JoinRequest.user_id == user.id))
        if row and row.status == "pending":
            return {"data": request_json(db, row)}
        message = text_value(payload, "message", maximum=3000)
        if row is None:
            row = JoinRequest(team_id=project_id, user_id=user.id)
            db.add(row)
        row.message, row.status, row.created_at = message, "pending", utcnow()
        row.decided_at = row.decided_by = None
        db.commit()
        return {"data": request_json(db, row)}

    @app.get("/api/v1/lab/projects/{project_id}/join-requests")
    def requests_for_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_role(db, project_id, user)
        rows = db.scalars(select(JoinRequest).where(JoinRequest.team_id == project_id).order_by(JoinRequest.created_at.desc()))
        return list_data([request_json(db, row) for row in rows])

    @app.post("/api/v1/lab/projects/{project_id}/join-requests/{request_id}/decision")
    def decide_request(project_id: str, request_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_role(db, project_id, user)
        decision = payload.get("decision")
        if decision not in ("approved", "rejected"):
            raise HTTPException(400, "请选择通过或拒绝")
        row = db.scalar(select(JoinRequest).where(JoinRequest.id == request_id, JoinRequest.team_id == project_id).with_for_update())
        if row is None:
            raise HTTPException(404, "申请不存在")
        if row.status != "pending":
            raise HTTPException(409, "申请已处理，请刷新")
        if decision == "approved" and not membership(db, project_id, row.user_id):
            db.add(Member(team_id=project_id, user_id=row.user_id, role="student"))
        row.status, row.decided_at, row.decided_by = decision, utcnow(), user.id
        db.commit()
        return {"data": request_json(db, row)}

    @app.get("/api/v1/teams/{team_id}/members")
    def members(team_id: str, page: int = Query(1, ge=1), pageSize: int = Query(100, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, team_id, user)
        rows = db.execute(select(Member, User).join(User, User.id == Member.user_id).where(Member.team_id == team_id).order_by(User.display_name, User.id)).all()
        items = [{"id": person.id, "name": person.display_name, "displayName": person.display_name, "email": person.email,
                  "direction": person.direction, "role": member.role} for member, person in rows]
        return {"data": {"items": items[(page - 1) * pageSize:page * pageSize], "total": len(items)}}

    @app.patch("/api/v1/teams/{team_id}/members/{user_id}")
    def edit_member(team_id: str, user_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_role(db, team_id, user)
        row = membership(db, team_id, user_id)
        if row is None:
            raise HTTPException(404, "成员不存在")
        if row.role == "owner":
            raise HTTPException(409, "不能降级负责人")
        if payload.get("role") not in ("student", "mentor"):
            raise HTTPException(400, "角色无效")
        row.role = payload["role"]
        db.commit()
        return {"data": {"id": user_id, "role": row.role}}

    @app.delete("/api/v1/teams/{team_id}/members/{user_id}")
    def remove_member(team_id: str, user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_role(db, team_id, user)
        row = membership(db, team_id, user_id)
        if row is None:
            raise HTTPException(404, "成员不存在")
        if row.role == "owner":
            raise HTTPException(409, "不能移除负责人")
        if db.scalar(select(Task.id).where(Task.team_id == team_id, Task.assignee_id == user_id, Task.status != "done").limit(1)):
            raise HTTPException(409, "请先完成或重新分配该成员的未完成任务")
        for share in db.scalars(select(ResourceShare).where(ResourceShare.team_id == team_id, ResourceShare.user_id == user_id)):
            share.active = False
        owned = select(Resource.id).where(Resource.owner_id == user_id)
        for share in db.scalars(select(ResourceShare).where(ResourceShare.team_id == team_id, ResourceShare.resource_id.in_(owned))):
            share.active = False
        db.delete(row)
        db.commit()
        return {"data": None}

    def meeting_for(db, meeting_id, user):
        row = db.get(Meeting, meeting_id)
        if row is None:
            raise HTTPException(404, "组会不存在")
        team_member(db, row.team_id, user)
        return row

    def meeting_json(db, row):
        project = project_for(db, row.team_id)
        return {"id": row.id, "projectId": row.team_id, "projectName": project.name, "title": row.title,
                "startsAt": iso(row.starts_at), "location": row.location, "agenda": row.agenda,
                "status": row.status, "minutes": row.minutes_content or ""}

    def preview_type(filename):
        suffix = Path(filename).suffix.lower()
        if suffix in VIDEO_TYPES:
            return VIDEO_TYPES[suffix]
        mime = mimetypes.guess_type(filename)[0]
        if mime == "application/pdf" or mime in ("text/plain", "text/markdown", "text/csv") or (mime and mime.startswith("image/") and mime != "image/svg+xml"):
            return mime
        return None

    def resource_for(db, resource_id, user):
        return accessible_resource(db, resource_id, user)[0]

    def resource_json(db, row, user=None):
        info = meta(db, "resource", row.id)
        return {"id": row.id, "projectId": row.team_id, "meetingId": row.meeting_id, "title": row.title,
                "description": row.description, "fileName": row.file_name, "size": row.size,
                "type": row.type if row.visibility == "private" else "recording" if Path(row.file_name).suffix.lower() in VIDEO_TYPES else "document",
                "ownerId": row.owner_id, "ownerName": user_name(db, row.owner_id), "version": row.version,
                "owner": user_name(db, row.owner_id), "visibility": row.visibility, "folderId": row.folder_id,
                "canEdit": bool(user and row.owner_id == user.id and row.visibility == "private"),
                "previewable": bool(preview_type(row.file_name)), "tags": info.get("tags", []),
                "source": "cloud" if row.visibility == "private" else "project",
                "previewType": preview_type(row.file_name), "createdAt": info.get("createdAt")}

    def referenced_materials(db, kind, ident, user):
        refs = db.scalars(select(ResourceReference).where(ResourceReference.target_type == kind, ResourceReference.target_id == ident))
        result = []
        for ref in refs:
            resource = db.get(Resource, ref.resource_id)
            if resource and resource_visible(db, resource, user):
                result.append({**resource_json(db, resource, user), "referenceId": ref.id})
        return result

    @app.get("/api/v1/lab/projects/{project_id}/meetings")
    def meetings(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, project_id, user)
        rows = db.scalars(select(Meeting).where(Meeting.team_id == project_id).order_by(Meeting.starts_at.desc(), Meeting.id))
        return list_data([meeting_json(db, row) for row in rows])

    @app.post("/api/v1/lab/projects/{project_id}/meetings", status_code=201)
    def create_meeting(project_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_role(db, project_id, user, ("owner", "mentor"))
        row = Meeting(team_id=project_id, title=text_value(payload, "title", maximum=200, required=True),
                      starts_at=timestamp(payload.get("startsAt"), required=True),
                      location=text_value(payload, "location", maximum=200), agenda=text_value(payload, "agenda", maximum=20000))
        db.add(row)
        db.commit()
        return {"data": meeting_json(db, row)}

    @app.get("/api/v1/lab/meetings/{meeting_id}")
    def meeting_detail(meeting_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = meeting_for(db, meeting_id, user)
        resources = [resource_json(db, item, user) for item in db.scalars(select(Resource).where(Resource.team_id == row.team_id, Resource.meeting_id == row.id, Resource.archived.is_(False)).order_by(Resource.id))]
        resources += referenced_materials(db, "meeting", row.id, user)
        return {"data": {**meeting_json(db, row), "materials": [item for item in resources if item["type"] != "recording"],
                         "recordings": [item for item in resources if item["type"] == "recording"]}}

    @app.patch("/api/v1/lab/meetings/{meeting_id}")
    def edit_meeting(meeting_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = meeting_for(db, meeting_id, user)
        require_role(db, row.team_id, user, ("owner", "mentor"))
        for key, attr, limit in (("title", "title", 200), ("location", "location", 200), ("agenda", "agenda", 20000), ("minutes", "minutes_content", 50000)):
            if key in payload:
                setattr(row, attr, text_value(payload, key, maximum=limit, required=key == "title"))
        if "startsAt" in payload:
            row.starts_at = timestamp(payload["startsAt"], required=True)
        if "status" in payload:
            if payload["status"] not in ("scheduled", "completed", "archived"):
                raise HTTPException(400, "组会状态无效")
            row.status = payload["status"]
        if "minutes" in payload:
            row.minutes_author_id, row.minutes_updated_at = user.id, utcnow()
        db.commit()
        return meeting_detail(meeting_id, user, db)

    @app.get("/api/v1/lab/next-meeting")
    def next_meeting(user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = db.scalar(select(Meeting).join(Member, Member.team_id == Meeting.team_id).where(Member.user_id == user.id, Meeting.starts_at > utcnow(), Meeting.status == "scheduled").order_by(Meeting.starts_at, Meeting.id).limit(1))
        if row is None:
            return {"data": None}
        return {"data": {key: value for key, value in meeting_json(db, row).items() if key in ("id", "projectId", "projectName", "title", "startsAt")}}

    @app.get("/api/v1/lab/projects/{project_id}/materials")
    def materials(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, project_id, user)
        rows = db.scalars(select(Resource).where(Resource.team_id == project_id, Resource.meeting_id.is_(None), Resource.archived.is_(False)).order_by(Resource.id))
        return list_data([resource_json(db, row, user) for row in rows] + referenced_materials(db, "project", project_id, user))

    @app.post("/api/v1/lab/projects/{project_id}/materials/references", status_code=201)
    def reference_material(project_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, project_id, user)
        row = resource_for(db, text_value(payload, "resourceId", maximum=36, required=True), user)
        if row.owner_id != user.id or row.visibility != "private":
            raise HTTPException(403, "只能引用自己云盘中的文件")
        meeting_id = text_value(payload, "meetingId", maximum=36)
        if meeting_id and meeting_for(db, meeting_id, user).team_id != project_id:
            raise HTTPException(400, "组会不属于此课题")
        if payload.get("grantReadAccess") is not True:
            raise HTTPException(400, "请明确确认向课题当前成员授予此文件的只读访问权限")
        kind, ident = ("meeting", meeting_id) if meeting_id else ("project", project_id)
        for member in db.scalars(select(Member).where(Member.team_id == project_id, Member.user_id != user.id)):
            share = db.scalar(select(ResourceShare).where(ResourceShare.resource_id == row.id, ResourceShare.user_id == member.user_id, ResourceShare.team_id == project_id))
            if share is None:
                share = ResourceShare(resource_id=row.id, user_id=member.user_id, team_id=project_id)
                db.add(share)
            share.active = True
        ref = db.scalar(select(ResourceReference).where(ResourceReference.resource_id == row.id, ResourceReference.target_type == kind, ResourceReference.target_id == ident))
        if ref is None:
            ref = ResourceReference(resource_id=row.id, target_type=kind, target_id=ident)
            db.add(ref)
        db.commit()
        return {"data": {**resource_json(db, row, user), "referenceId": ref.id}}

    @app.post("/api/v1/lab/projects/{project_id}/materials", status_code=201)
    async def upload_material(project_id: str, file: UploadFile = File(), title: str = Form(""), description: str = Form(""), meetingId: str = Form(""), user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, project_id, user)
        filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        if not filename or len(filename) > 255 or any(ord(char) < 32 for char in filename):
            raise HTTPException(400, "文件名无效或过长")
        suffix = Path(filename).suffix.lower()
        is_video = suffix in VIDEO_TYPES
        if suffix not in DOCUMENT_EXTENSIONS and not is_video:
            raise HTTPException(415, "暂不支持此文件类型")
        if is_video and not meetingId:
            raise HTTPException(400, "录像需要归属一次组会")
        if meetingId:
            meeting = meeting_for(db, meetingId, user)
            if meeting.team_id != project_id:
                raise HTTPException(400, "组会不属于此课题")
        values = {"title": title or filename, "description": description}
        clean_title = text_value(values, "title", maximum=200, required=True)
        clean_description = text_value(values, "description", maximum=10000)
        limit = int(os.getenv("MAX_VIDEO_UPLOAD_BYTES", str(1024 ** 3))) if is_video else int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 ** 2)))
        if file.size is not None and file.size > limit:
            raise HTTPException(413, f"文件超过大小限制（{limit // (1024 ** 2)} MiB）")
        storage_name = str(uuid4())
        uploads.mkdir(parents=True, exist_ok=True)
        location = uploads / storage_name
        size = 0
        try:
            with location.open("xb") as destination:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, f"文件超过大小限制（{limit // (1024 ** 2)} MiB）")
                    destination.write(chunk)
            if not size:
                raise HTTPException(400, "不能上传空文件")
            row = Resource(team_id=project_id, owner_id=user.id, title=clean_title, description=clean_description,
                           type="recording" if is_video else "document", meeting_id=meetingId or None,
                           file_name=filename, storage_name=storage_name, size=size, visibility="team")
            db.add(row)
            db.flush()
            put_meta(db, "resource", row.id, {"createdAt": iso(utcnow())})
            db.commit()
            return {"data": resource_json(db, row)}
        except BaseException:
            db.rollback()
            location.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.get("/api/v1/lab/resources/{resource_id}")
    @app.get("/api/v1/resources/{resource_id}")
    def resource_detail(resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        return {"data": resource_json(db, resource_for(db, resource_id, user), user)}

    def resource_file(storage):
        location = (uploads / storage).resolve()
        if location.parent != uploads.resolve() or not location.is_file():
            raise HTTPException(404, "文件暂时不可用")
        return location

    def file_response(location, filename, media_type, request, disposition):
        headers = {"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}", "X-Content-Type-Options": "nosniff", "Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
        raw_range = request.headers.get("range")
        if not raw_range:
            return FileResponse(location, media_type=media_type, headers=headers)
        size = location.stat().st_size
        matched = re.fullmatch(r"bytes=(\d*)-(\d*)", raw_range.strip())
        try:
            if not matched or not size or not any(matched.groups()):
                raise ValueError()
            first, last = matched.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                length = int(last)
                if length <= 0:
                    raise ValueError()
                start, end = max(0, size - length), size - 1
            if start >= size or end < start:
                raise ValueError()
        except ValueError:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
        length = end - start + 1
        def chunks():
            with location.open("rb") as stream:
                stream.seek(start)
                remaining = length
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        return StreamingResponse(chunks(), status_code=206, media_type=media_type, headers={**headers, "Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(length)})

    @app.get("/api/v1/resources/{resource_id}/download")
    def download(resource_id: str, request: Request, versionId: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = resource_for(db, resource_id, user)
        filename, storage = row.file_name, row.storage_name
        if versionId:
            version = db.get(ResourceVersion, versionId)
            if version is None or version.resource_id != row.id:
                raise HTTPException(404, "资料版本不存在")
            filename, storage = version.file_name, version.storage_name
        return file_response(resource_file(storage), filename, "application/octet-stream", request, "attachment")

    @app.get("/api/v1/resources/{resource_id}/preview")
    def preview(resource_id: str, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = resource_for(db, resource_id, user)
        mime = preview_type(row.file_name)
        if not mime:
            raise HTTPException(415, "此格式请下载后查看")
        return file_response(resource_file(row.storage_name), row.file_name, mime, request, "inline")

    @app.get("/api/v1/resources/{resource_id}/reading-progress")
    def reading_progress(resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        resource_for(db, resource_id, user)
        return {"data": meta(db, "reading", f"{resource_id}:{user.id}")}

    @app.patch("/api/v1/resources/{resource_id}/reading-progress")
    def save_reading_progress(resource_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        resource_for(db, resource_id, user)
        values = {}
        try:
            for key in ("ratio", "page", "time"):
                if key in payload:
                    value = float(payload[key])
                    if not math.isfinite(value):
                        raise ValueError()
                    values[key] = max(1, min(100000, int(value))) if key == "page" else max(0, min(1, value)) if key == "ratio" else max(0, value)
        except (TypeError, ValueError, OverflowError):
            raise HTTPException(400, "阅读进度格式无效")
        if "notes" in payload:
            values["notes"] = text_value(payload, "notes", maximum=50000)
        values["updatedAt"] = iso(utcnow())
        result = put_meta(db, "reading", f"{resource_id}:{user.id}", values)
        db.commit()
        return {"data": result}

    def task_json(db, row):
        return {"id": row.id, "projectId": row.team_id, "projectName": project_for(db, row.team_id).name,
                "title": row.title, "description": row.description, "status": row.status,
                "dueAt": meta(db, "task", row.id).get("dueAt"), "assigneeId": row.assignee_id,
                "assigneeName": user_name(db, row.assignee_id)}

    @app.get("/api/v1/lab/tasks")
    def my_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)):
        rows = db.scalars(select(Task).join(Member, Member.team_id == Task.team_id).where(Member.user_id == user.id, Task.assignee_id == user.id).order_by(Task.id))
        return list_data([task_json(db, row) for row in rows])

    @app.get("/api/v1/lab/projects/{project_id}/tasks")
    def project_tasks(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_role(db, project_id, user)
        return list_data([task_json(db, row) for row in db.scalars(select(Task).where(Task.team_id == project_id).order_by(Task.id))])

    def assignee(db, project_id, payload):
        ident = text_value(payload, "assigneeId", maximum=36, required=True)
        if not membership(db, project_id, ident):
            raise HTTPException(400, "只能分配给已加入此课题的成员")
        return ident

    @app.post("/api/v1/lab/projects/{project_id}/tasks", status_code=201)
    def create_task(project_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_role(db, project_id, user)
        row = Task(team_id=project_id, title=text_value(payload, "title", maximum=200, required=True),
                   description=text_value(payload, "description", maximum=20000), assignee_id=assignee(db, project_id, payload),
                   reviewer_id=user.id, status="todo", plane_sync="disabled")
        due_at = timestamp(payload.get("dueAt"))
        db.add(row)
        db.flush()
        put_meta(db, "task", row.id, {"dueAt": iso(due_at)})
        db.commit()
        return {"data": task_json(db, row)}

    @app.patch("/api/v1/lab/projects/{project_id}/tasks/{task_id}")
    def edit_task(project_id: str, task_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        require_role(db, project_id, user)
        row = db.get(Task, task_id)
        if row is None or row.team_id != project_id:
            raise HTTPException(404, "任务不存在")
        for key, limit in (("title", 200), ("description", 20000)):
            if key in payload:
                setattr(row, key, text_value(payload, key, maximum=limit, required=key == "title"))
        if "assigneeId" in payload:
            row.assignee_id = assignee(db, project_id, payload)
        if "dueAt" in payload:
            put_meta(db, "task", row.id, {"dueAt": iso(timestamp(payload["dueAt"]))})
        if "status" in payload:
            if payload["status"] not in ("todo", "doing", "done"):
                raise HTTPException(400, "任务状态无效")
            row.status = payload["status"]
        db.commit()
        return {"data": task_json(db, row)}

    def message_for(db, message_id):
        row = db.get(LabMessage, message_id)
        if row is None:
            raise HTTPException(404, "留言不存在")
        return row

    def message_json(db, row):
        return {"id": row.id, "title": row.title, "content": row.content, "authorId": row.author_id,
                "authorName": user_name(db, row.author_id), "createdAt": iso(row.created_at)}

    @app.get("/api/v1/lab/messages")
    def messages(user: User = Depends(current_user), db: Session = Depends(get_db)):
        rows = db.scalars(select(LabMessage).order_by(LabMessage.created_at.desc(), LabMessage.id))
        return list_data([message_json(db, row) for row in rows], canPublish=True)

    @app.post("/api/v1/lab/messages", status_code=201)
    def create_message(payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = LabMessage(author_id=user.id, title=text_value(payload, "title", maximum=200, required=True),
                         content=text_value(payload, "content", required=True))
        db.add(row)
        db.commit()
        return {"data": message_json(db, row)}

    @app.get("/api/v1/lab/messages/{message_id}")
    def message_detail(message_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        return {"data": message_json(db, message_for(db, message_id))}

    @app.patch("/api/v1/lab/messages/{message_id}")
    def edit_message(message_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = message_for(db, message_id)
        if row.author_id != user.id:
            raise HTTPException(403, "只能修改自己发布的留言")
        for key, limit in (("title", 200), ("content", 50000)):
            if key in payload:
                setattr(row, key, text_value(payload, key, maximum=limit, required=True))
        db.commit()
        return {"data": message_json(db, row)}

    @app.delete("/api/v1/lab/messages/{message_id}")
    def delete_message(message_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        row = message_for(db, message_id)
        if row.author_id != user.id:
            raise HTTPException(403, "只能删除自己发布的留言")
        db.execute(delete(LabComment).where(LabComment.target_type == "message", LabComment.target_id == message_id))
        db.delete(row)
        db.commit()
        return {"data": None}

    def target_for(db, kind, ident, user, history=False):
        if kind == "project" and history:
            row = project_for(db, ident)
            return row.name, row.id, row.name
        if kind == "meeting":
            row = meeting_for(db, ident, user)
            return row.title, row.team_id, project_for(db, row.team_id).name
        if kind == "resource":
            row = resource_for(db, ident, user)
            return row.title, row.team_id, project_for(db, row.team_id).name if row.team_id else None
        if kind == "message":
            return message_for(db, ident).title, None, None
        raise HTTPException(400, "记录类型无效")

    def comment_json(db, row):
        return {"id": row.id, "authorId": row.author_id, "authorName": user_name(db, row.author_id),
                "content": row.content, "createdAt": iso(row.created_at)}

    @app.get("/api/v1/lab/comments/{kind}/{target_id}")
    def comments(kind: str, target_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        target_for(db, kind, target_id, user)
        rows = db.scalars(select(LabComment).where(LabComment.target_type == kind, LabComment.target_id == target_id).order_by(LabComment.created_at, LabComment.id))
        return list_data([comment_json(db, row) for row in rows])

    @app.post("/api/v1/lab/comments/{kind}/{target_id}", status_code=201)
    def create_comment(kind: str, target_id: str, payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        target_for(db, kind, target_id, user)
        row = LabComment(target_type=kind, target_id=target_id, author_id=user.id, content=text_value(payload, "content", maximum=10000, required=True))
        db.add(row)
        db.commit()
        return {"data": comment_json(db, row)}

    def history_json(db, row, user):
        title, project_id, project_name = target_for(db, row.target_type, row.target_id, user, history=True)
        return {"id": row.id, "targetType": row.target_type, "targetId": row.target_id, "title": title,
                "projectId": project_id, "projectName": project_name, "visitedAt": iso(row.visited_at)}

    @app.post("/api/v1/lab/history")
    def record_history(payload: dict = Body(), user: User = Depends(current_user), db: Session = Depends(get_db)):
        kind = text_value(payload, "targetType", maximum=20, required=True)
        ident = text_value(payload, "targetId", maximum=36, required=True)
        target_for(db, kind, ident, user, history=True)
        row = db.scalar(select(BrowseHistory).where(BrowseHistory.user_id == user.id, BrowseHistory.target_type == kind, BrowseHistory.target_id == ident))
        if row is None:
            row = BrowseHistory(user_id=user.id, target_type=kind, target_id=ident)
            db.add(row)
        row.visited_at = utcnow()
        db.commit()
        return {"data": history_json(db, row, user)}

    @app.get("/api/v1/lab/history")
    def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
        items = []
        rows = db.scalars(select(BrowseHistory).where(BrowseHistory.user_id == user.id).order_by(BrowseHistory.visited_at.desc(), BrowseHistory.id))
        for row in rows:
            try:
                items.append(history_json(db, row, user))
            except HTTPException as exc:
                if exc.status_code not in (403, 404):
                    raise
        return list_data(items)

    @app.delete("/api/v1/lab/history")
    def clear_history(user: User = Depends(current_user), db: Session = Depends(get_db)):
        db.execute(delete(BrowseHistory).where(BrowseHistory.user_id == user.id))
        db.commit()
        return {"data": None}
