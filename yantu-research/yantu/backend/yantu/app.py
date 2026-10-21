from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, or_, select, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Base, Enrollment, Experience, Invitation, LoginFailure, Meeting, Member, Notification,
    Resource, Review, Route, SessionToken, Submission, Task, Team, User, utcnow,
)
from .plane_client import PlaneClient, PlaneError
from .research_assistant import AssistantUnavailable, OllamaResearchAssistant, extract_document_text
from .security import check_password, hash_password, new_token, token_digest
from .migrations import migrate
from .version import VERSION


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class Registration(Credentials):
    displayName: str = Field(min_length=1, max_length=100)
    invitationToken: str | None = None


class ProfileChange(BaseModel):
    displayName: str = Field(min_length=1, max_length=100)
    direction: str = Field(default="", max_length=255)


class TeamInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    planeWorkspaceSlug: str | None = Field(default=None, max_length=100)
    planeProjectId: str | None = Field(default=None, max_length=36)


class PlaneBinding(BaseModel):
    planeWorkspaceSlug: str = Field(min_length=1, max_length=100)
    planeProjectId: str = Field(min_length=36, max_length=36)


class InviteInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str


class ExperienceInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    startingPoint: str = Field(min_length=1, max_length=3000)
    content: str = Field(min_length=1, max_length=50000)


class RouteInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    stages: list[dict] = Field(default_factory=list, max_length=40)


class MeetingInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    startsAt: datetime
    location: str = Field(min_length=1, max_length=200)
    agenda: str = Field(min_length=1, max_length=20000)


class MinutesInput(BaseModel):
    content: str = Field(min_length=1, max_length=50000)


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    acceptanceCriteria: str = ""
    assigneeId: str
    reviewerId: str
    meetingId: str | None = None


class StatusInput(BaseModel):
    status: str
    blocker: str = ""


class SubmissionInput(BaseModel):
    summary: str = Field(min_length=1, max_length=50000)
    url: str = Field(default="", max_length=2048)


class ReviewInput(BaseModel):
    comment: str = Field(min_length=1, max_length=50000)
    decision: str


class ReadInput(BaseModel):
    read: bool


class QuestionInput(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    resourceIds: list[str] = Field(default_factory=list, max_length=100)


def create_app(
    database_url: str | None = None,
    upload_dir: Path | None = None,
    frontend_dir: Path | None = None,
    plane: PlaneClient | None = None,
    research_assistant: OllamaResearchAssistant | None = None,
) -> FastAPI:
    database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./yantu.db")
    uploads = Path(upload_dir or os.getenv("UPLOAD_DIR", "./uploads")).resolve()
    front = Path(frontend_dir or Path(__file__).resolve().parents[2] / "frontend")
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": 30} if database_url.startswith("sqlite") else {},
    )
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def sqlite_options(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    plane = plane or PlaneClient(os.getenv("PLANE_BASE_URL", ""), os.getenv("PLANE_API_KEY", ""))
    research_assistant = research_assistant or OllamaResearchAssistant(
        os.getenv("AI_BASE_URL", ""), os.getenv("AI_MODEL", "")
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        uploads.mkdir(parents=True, exist_ok=True)
        migrate(engine)
        yield
        engine.dispose()

    app = FastAPI(title="研途 API", version=VERSION, lifespan=lifespan)
    app.state.plane = plane

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": "REQUEST_FAILED", "message": str(exc.detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"code": "INVALID_INPUT", "message": "输入字段格式不正确"})

    def get_db():
        with SessionLocal() as db:
            yield db

    def current_user(
        request: Request, authorization: str | None = Header(default=None), db: Session = Depends(get_db)
    ) -> User:
        raw_token = authorization[7:] if authorization and authorization.startswith("Bearer ") else request.cookies.get("yantu_session")
        if not raw_token:
            raise HTTPException(401, "请先登录")
        digest = token_digest(raw_token)
        session = db.get(SessionToken, digest)
        if session is None or not session.expires_at or session.expires_at.replace(tzinfo=timezone.utc) < utcnow():
            raise HTTPException(401, "登录已过期，请重新登录")
        user = db.get(User, session.user_id)
        if user is None:
            raise HTTPException(401, "用户不存在")
        return user

    def team_member(db: Session, team_id: str, user: User) -> tuple[Team, Member]:
        team = db.get(Team, team_id)
        membership = db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == user.id))
        if team is None or membership is None:
            raise HTTPException(403, "无权访问该课题组")
        return team, membership

    def can_manage(member: Member) -> None:
        if member.role not in ("mentor", "owner"):
            raise HTTPException(403, "需要前辈或负责人权限")

    def allowed_plane_project(slug: str, project: str) -> None:
        allowed = {item.strip() for item in os.getenv("PLANE_ALLOWED_PROJECTS", "").split(",") if item.strip()}
        if f"{slug}:{project}" not in allowed:
            raise HTTPException(403, "此 Plane 项目尚未列入服务器的课题组绑定白名单")

    def task_for(db: Session, task_id: str, user: User) -> tuple[Task, Team, Member]:
        task = db.get(Task, task_id)
        if task is None:
            raise HTTPException(404, "任务不存在")
        team, membership = team_member(db, task.team_id, user)
        if task.assignee_id != user.id and task.reviewer_id != user.id and membership.role != "owner":
            raise HTTPException(403, "无权访问该任务")
        return task, team, membership

    def note(db: Session, user_id: str, title: str):
        db.add(Notification(user_id=user_id, title=title))

    def item_page(db: Session, model, team_id: str, page: int, page_size: int):
        total = db.scalar(select(func.count()).select_from(model).where(model.team_id == team_id)) or 0
        rows = db.scalars(
            select(model).where(model.team_id == team_id).order_by(model.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        return rows, total

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": VERSION}

    @app.post("/api/v1/auth/register")
    def register(payload: Registration, db: Session = Depends(get_db)):
        email = payload.email.strip().lower()
        if "@" not in email or len(payload.password) < 12:
            raise HTTPException(400, "邮箱格式错误或密码少于 12 位")
        invite = None
        if payload.invitationToken:
            invite = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(payload.invitationToken)))
            if invite is None or invite.accepted_at or invite.expires_at.replace(tzinfo=timezone.utc) < utcnow() or invite.email != email:
                raise HTTPException(403, "邀请令牌与注册邮箱不匹配或已过期")
        if not invite and os.getenv("ALLOW_PUBLIC_SIGNUP", "0") != "1":
            raise HTTPException(403, "请先取得课题组邀请")
        user = User(email=email, display_name=payload.displayName.strip(), password_hash=hash_password(payload.password))
        db.add(user)
        try:
            db.flush()
            if invite:
                db.add(Member(team_id=invite.team_id, user_id=user.id, role=invite.role))
                invite.accepted_at = utcnow()
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "邮箱已注册")
        return {"data": {"id": user.id}}

    @app.post("/api/v1/auth/login")
    def login(payload: Credentials, db: Session = Depends(get_db)):
        email = payload.email.strip().lower()
        failures = db.get(LoginFailure, email)
        if failures and failures.locked_until and failures.locked_until.replace(tzinfo=timezone.utc) > utcnow():
            raise HTTPException(429, "登录尝试过多，请稍后再试")
        user = db.scalar(select(User).where(User.email == email))
        if user is None or not check_password(payload.password, user.password_hash):
            if failures is None:
                failures = LoginFailure(email=email, count=0)
                db.add(failures)
            if failures.locked_until and failures.locked_until.replace(tzinfo=timezone.utc) <= utcnow():
                failures.count = 0
                failures.locked_until = None
            failures.count += 1
            if failures.count >= 5:
                failures.locked_until = utcnow() + timedelta(minutes=15)
            db.commit()
            raise HTTPException(401, "邮箱或密码错误")
        if failures:
            db.delete(failures)
        token = new_token()
        db.add(SessionToken(token_hash=token_digest(token), user_id=user.id, expires_at=utcnow() + timedelta(hours=24)))
        db.commit()
        return {"data": {"accessToken": token, "user": {"id": user.id, "displayName": user.display_name}}}

    @app.post("/api/v1/auth/logout")
    def logout(authorization: str | None = Header(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
        if authorization:
            session = db.get(SessionToken, token_digest(authorization[7:]))
            if session:
                db.delete(session)
                db.commit()
        return {"data": None}

    @app.get("/api/v1/me")
    def me(user: User = Depends(current_user)):
        return {"data": {"id": user.id, "email": user.email, "displayName": user.display_name, "direction": user.direction}}

    @app.patch("/api/v1/me")
    def edit_me(payload: ProfileChange, user: User = Depends(current_user), db: Session = Depends(get_db)):
        user.display_name = payload.displayName.strip()
        user.direction = payload.direction.strip()
        db.commit()
        return {"data": {"id": user.id, "email": user.email, "displayName": user.display_name, "direction": user.direction}}

    @app.get("/api/v1/me/teams")
    def my_teams(user: User = Depends(current_user), db: Session = Depends(get_db)):
        memberships = db.scalars(select(Member).where(Member.user_id == user.id)).all()
        return {"data": {"items": [
            {"id": m.team_id, "name": db.get(Team, m.team_id).name, "role": m.role}
            for m in memberships
        ], "total": len(memberships)}}

    @app.post("/api/v1/teams")
    def create_team(payload: TeamInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
        if bool(payload.planeWorkspaceSlug) != bool(payload.planeProjectId):
            raise HTTPException(400, "Plane 工作区和项目 ID 必须同时填写")
        if payload.planeWorkspaceSlug and payload.planeProjectId:
            allowed_plane_project(payload.planeWorkspaceSlug.strip(), payload.planeProjectId.strip())
        team = Team(name=payload.name.strip(), plane_workspace_slug=payload.planeWorkspaceSlug or None, plane_project_id=payload.planeProjectId or None)
        if team.plane_workspace_slug:
            try:
                plane.list_work_items(team)
            except PlaneError as exc:
                raise HTTPException(502, str(exc)) from exc
        db.add(team)
        db.flush()
        db.add(Member(team_id=team.id, user_id=user.id, role="owner"))
        db.commit()
        return {"data": {"id": team.id, "name": team.name, "planeConnected": plane.configured(team)}}

    @app.patch("/api/v1/teams/{team_id}/plane")
    def bind_plane(team_id: str, payload: PlaneBinding, user: User = Depends(current_user), db: Session = Depends(get_db)):
        team, membership = team_member(db, team_id, user)
        if membership.role != "owner":
            raise HTTPException(403, "只有负责人可绑定 Plane")
        if not payload.planeWorkspaceSlug or not payload.planeProjectId:
            raise HTTPException(400, "请填写 Plane Workspace slug 和 Project UUID")
        allowed_plane_project(payload.planeWorkspaceSlug.strip(), payload.planeProjectId.strip())
        team.plane_workspace_slug = payload.planeWorkspaceSlug.strip()
        team.plane_project_id = payload.planeProjectId.strip()
        if not plane.configured(team):
            raise HTTPException(503, "服务端尚未配置 Plane API Key")
        try:
            plane.list_work_items(team)
        except PlaneError as exc:
            raise HTTPException(502, str(exc)) from exc
        db.commit()
        return {"data": {"id": team.id, "name": team.name, "planeConnected": True}}

    @app.get("/api/v1/teams/{team_id}/members")
    def members(team_id: str, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, team_id, user)
        all_members = db.scalars(select(Member).where(Member.team_id == team_id).order_by(Member.id)).all()
        part = all_members[(page - 1) * pageSize:page * pageSize]
        return {"data": {"items": [
            {"id": m.user_id, "name": db.get(User, m.user_id).display_name, "role": m.role}
            for m in part
        ], "total": len(all_members)}}

    @app.post("/api/v1/teams/{team_id}/invitations")
    def invite(team_id: str, payload: InviteInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, membership = team_member(db, team_id, user)
        if membership.role != "owner":
            raise HTTPException(403, "只有负责人可以邀请成员")
        if payload.role not in ("student", "mentor"):
            raise HTTPException(400, "角色无效")
        token = new_token()
        invitation = Invitation(team_id=team_id, email=payload.email.strip().lower(), role=payload.role,
                                token_hash=token_digest(token), expires_at=utcnow() + timedelta(days=7))
        db.add(invitation)
        db.commit()
        # The link is visible to the owner once; no SMTP dependency is required for the first deploy.
        return {"data": {"id": invitation.id, "status": "pending", "inviteToken": token}}

    @app.post("/api/v1/invitations/{token}/accept")
    def accept_invite(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        invite = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(token)))
        if invite is None or invite.accepted_at or invite.expires_at.replace(tzinfo=timezone.utc) < utcnow():
            raise HTTPException(404, "邀请不存在或已过期")
        if invite.email != user.email:
            raise HTTPException(403, "请用受邀邮箱登录")
        if db.scalar(select(Member).where(Member.team_id == invite.team_id, Member.user_id == user.id)):
            raise HTTPException(409, "已经加入课题组")
        db.add(Member(team_id=invite.team_id, user_id=user.id, role=invite.role))
        invite.accepted_at = utcnow()
        db.commit()
        return {"data": {"teamId": invite.team_id}}

    @app.get("/api/v1/teams/{team_id}/experiences")
    def list_experiences(team_id: str, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, team_id, user)
        items, total = item_page(db, Experience, team_id, page, pageSize)
        return {"data": {"items": [
            {"id": e.id, "title": e.title, "author": db.get(User, e.author_id).display_name,
             "createdAt": iso(e.created_at)} for e in items
        ], "total": total}}

    @app.post("/api/v1/teams/{team_id}/experiences")
    def create_experience(team_id: str, payload: ExperienceInput,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, team_id, user)
        experience = Experience(team_id=team_id, author_id=user.id, title=payload.title.strip(),
                                starting_point=payload.startingPoint, content=payload.content)
        db.add(experience)
        db.commit()
        return {"data": {"id": experience.id}}

    @app.get("/api/v1/experiences/{experience_id}")
    def get_experience(experience_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        item = db.get(Experience, experience_id)
        if item is None:
            raise HTTPException(404, "经验不存在")
        team_member(db, item.team_id, user)
        return {"data": {"id": item.id, "title": item.title, "startingPoint": item.starting_point,
                         "content": item.content, "author": db.get(User, item.author_id).display_name,
                         "createdAt": iso(item.created_at)}}

    def validate_stages(stages: list[dict]) -> list[dict]:
        result = []
        for stage in stages:
            if not isinstance(stage, dict) or not isinstance(stage.get("title"), str) or not stage["title"].strip():
                raise HTTPException(400, "每个阶段都需要标题")
            tasks = stage.get("tasks", [])
            if not isinstance(tasks, list) or len(tasks) > 100:
                raise HTTPException(400, "阶段任务数量超限")
            clean_tasks = []
            for item in tasks:
                if not isinstance(item, dict) or not str(item.get("title", "")).strip():
                    raise HTTPException(400, "阶段任务需要标题")
                clean_tasks.append({"id": str(uuid4()), "title": str(item["title"])[:200],
                                    "acceptanceCriteria": str(item.get("acceptanceCriteria", ""))[:10000],
                                    "description": str(item.get("description", ""))[:20000]})
            result.append({"id": str(uuid4()), "title": stage["title"].strip()[:200],
                           "description": str(stage.get("description", ""))[:20000],
                           "resources": [], "tasks": clean_tasks})
        return result

    @app.get("/api/v1/teams/{team_id}/routes")
    def list_routes(team_id: str, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, team_id, user)
        items, total = item_page(db, Route, team_id, page, pageSize)
        return {"data": {"items": [
            {"id": r.id, "title": r.title, "author": db.get(User, r.author_id).display_name,
             "stageCount": len(r.stages)} for r in items
        ], "total": total}}

    @app.post("/api/v1/teams/{team_id}/routes")
    def create_route(team_id: str, payload: RouteInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, membership = team_member(db, team_id, user)
        can_manage(membership)
        route = Route(team_id=team_id, author_id=user.id, title=payload.title.strip(),
                      description=payload.description, stages=validate_stages(payload.stages))
        db.add(route)
        db.commit()
        return {"data": {"id": route.id}}

    @app.get("/api/v1/routes/{route_id}")
    def get_route(route_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        route = db.get(Route, route_id)
        if route is None:
            raise HTTPException(404, "路线不存在")
        team_member(db, route.team_id, user)
        return {"data": {"id": route.id, "title": route.title, "description": route.description,
                         "author": db.get(User, route.author_id).display_name, "stages": route.stages}}

    @app.patch("/api/v1/routes/{route_id}")
    def edit_route(route_id: str, payload: RouteInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
        route = db.get(Route, route_id)
        if route is None:
            raise HTTPException(404, "路线不存在")
        _, membership = team_member(db, route.team_id, user)
        can_manage(membership)
        route.title = payload.title.strip()
        route.description = payload.description
        route.stages = validate_stages(payload.stages)
        db.commit()
        return {"data": {"id": route.id}}

    @app.post("/api/v1/routes/{route_id}/enrollments")
    def enroll(route_id: str, _payload: dict = Body(default={}), user: User = Depends(current_user), db: Session = Depends(get_db)):
        route = db.get(Route, route_id)
        if route is None:
            raise HTTPException(404, "路线不存在")
        team, _ = team_member(db, route.team_id, user)
        existing = db.scalar(select(Enrollment).where(Enrollment.route_id == route_id, Enrollment.user_id == user.id))
        if existing is None:
            enrollment = Enrollment(route_id=route_id, user_id=user.id)
            db.add(enrollment)
            db.flush()
            for stage in route.stages:
                for template in stage["tasks"]:
                    db.add(Task(team_id=route.team_id, enrollment_id=enrollment.id,
                                route_stage_title=stage["title"], assignee_id=user.id, reviewer_id=route.author_id,
                                title=template["title"], description=template.get("description", ""),
                                acceptance_criteria=template.get("acceptanceCriteria", ""), plane_sync="pending"))
            db.commit()
        else:
            enrollment = existing
        pending = db.scalars(select(Task).where(Task.enrollment_id == enrollment.id,
                                                Task.plane_work_item_id.is_(None))).all()
        if plane.configured(team):
            for task in pending:
                try:
                    task.plane_work_item_id = plane.create_work_item(
                        team, task.title, task.description, external_id=task.id
                    )
                    task.plane_sync = "linked"
                    db.commit()
                except PlaneError:
                    task.plane_sync = "retry_needed"
                    db.commit()
                    break
        else:
            for task in pending:
                task.plane_sync = "unlinked"
            db.commit()
        remaining = db.scalar(select(func.count()).select_from(Task).where(
            Task.enrollment_id == enrollment.id, Task.plane_work_item_id.is_(None))) or 0
        return {"data": {"id": enrollment.id, "routeId": route_id, "status": "active",
                         "planeSync": "linked" if remaining == 0 else "retry_needed" if plane.configured(team) else "unlinked"}}

    @app.get("/api/v1/teams/{team_id}/meetings")
    def list_meetings(team_id: str, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, team_id, user)
        items, total = item_page(db, Meeting, team_id, page, pageSize)
        return {"data": {"items": [
            {"id": m.id, "title": m.title, "startsAt": iso(m.starts_at), "location": m.location} for m in items
        ], "total": total}}

    @app.post("/api/v1/teams/{team_id}/meetings")
    def create_meeting(team_id: str, payload: MeetingInput,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, membership = team_member(db, team_id, user)
        can_manage(membership)
        if payload.startsAt.tzinfo is None:
            raise HTTPException(400, "会议时间需要包含时区")
        meeting = Meeting(team_id=team_id, title=payload.title.strip(), starts_at=payload.startsAt.astimezone(timezone.utc),
                          location=payload.location, agenda=payload.agenda)
        db.add(meeting)
        db.commit()
        return {"data": {"id": meeting.id}}

    @app.get("/api/v1/meetings/{meeting_id}")
    def get_meeting(meeting_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            raise HTTPException(404, "组会不存在")
        team_member(db, meeting.team_id, user)
        resources = db.scalars(select(Resource).where(Resource.meeting_id == meeting_id)).all()
        tasks = db.scalars(select(Task).where(Task.meeting_id == meeting_id)).all()
        return {"data": {"id": meeting.id, "title": meeting.title, "startsAt": iso(meeting.starts_at),
                         "location": meeting.location, "agenda": meeting.agenda,
                         "resources": [{"id": r.id, "title": r.title} for r in resources],
                         "minutes": {"content": meeting.minutes_content, "updatedAt": iso(meeting.minutes_updated_at)}
                         if meeting.minutes_content is not None else None,
                         "tasks": [{"id": t.id, "title": t.title} for t in tasks]}}

    @app.put("/api/v1/meetings/{meeting_id}/minutes")
    def save_minutes(meeting_id: str, payload: MinutesInput,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            raise HTTPException(404, "组会不存在")
        _, membership = team_member(db, meeting.team_id, user)
        can_manage(membership)
        meeting.minutes_content = payload.content
        meeting.minutes_updated_at = utcnow()
        meeting.minutes_author_id = user.id
        db.commit()
        return {"data": {"id": meeting.id, "content": meeting.minutes_content,
                         "updatedAt": iso(meeting.minutes_updated_at)}}

    def task_summary(db: Session, task: Task) -> dict:
        reviewer = db.get(User, task.reviewer_id)
        return {"id": task.id, "title": task.title, "status": task.status,
                "reviewer": reviewer.display_name if reviewer else "—"}

    @app.get("/api/v1/me/tasks")
    def my_tasks(teamId: str, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, teamId, user)
        clause = (Task.team_id == teamId, Task.assignee_id == user.id)
        total = db.scalar(select(func.count()).select_from(Task).where(*clause)) or 0
        items = db.scalars(select(Task).where(*clause).order_by(Task.id.desc())
                           .offset((page - 1) * pageSize).limit(pageSize)).all()
        return {"data": {"items": [task_summary(db, t) for t in items], "total": total}}

    @app.get("/api/v1/teams/{team_id}/review-queue")
    def review_queue(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, membership = team_member(db, team_id, user)
        can_manage(membership)
        clause = [Task.team_id == team_id, Task.status == "review"]
        if membership.role != "owner":
            clause.append(Task.reviewer_id == user.id)
        items = db.scalars(select(Task).where(*clause).order_by(Task.id.desc()).limit(100)).all()
        return {"data": {"items": [task_summary(db, t) for t in items], "total": len(items)}}

    @app.post("/api/v1/teams/{team_id}/tasks")
    def create_task(team_id: str, payload: TaskInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
        team, membership = team_member(db, team_id, user)
        can_manage(membership)
        assignee = db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == payload.assigneeId))
        reviewer = db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == payload.reviewerId))
        if assignee is None or reviewer is None:
            raise HTTPException(400, "任务负责人和反馈人必须是本组成员")
        if reviewer.role not in ("mentor", "owner"):
            raise HTTPException(400, "反馈人必须是前辈或负责人")
        if payload.meetingId:
            meeting = db.get(Meeting, payload.meetingId)
            if meeting is None or meeting.team_id != team_id:
                raise HTTPException(400, "关联组会不属于当前课题组")
        task = Task(team_id=team_id, title=payload.title, description=payload.description,
                    acceptance_criteria=payload.acceptanceCriteria, assignee_id=payload.assigneeId,
                    reviewer_id=payload.reviewerId, meeting_id=payload.meetingId or None,
                    plane_sync="pending")
        db.add(task)
        db.flush()
        try:
            plane_id = plane.create_work_item(team, payload.title, payload.description, external_id=task.id)
        except PlaneError as exc:
            db.rollback()
            raise HTTPException(502, str(exc)) from exc
        task.plane_work_item_id = plane_id
        task.plane_sync = "linked" if plane_id else "unlinked"
        note(db, task.assignee_id, f"新任务：{task.title}")
        db.commit()
        return {"data": {"id": task.id, "planeWorkItemId": plane_id, "planeSync": task.plane_sync}}

    @app.get("/api/v1/teams/{team_id}/plane-work-items")
    def plane_tasks(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        team, _ = team_member(db, team_id, user)
        try:
            raw = plane.list_work_items(team)
        except PlaneError as exc:
            raise HTTPException(502, str(exc)) from exc
        items = []
        for item in raw.get("results", []):
            state = item.get("state")
            items.append({"id": item.get("id"), "title": item.get("name", ""),
                          "status": state.get("name", "—") if isinstance(state, dict) else "—",
                          "reviewer": "—"})
        return {"data": {"items": items, "total": raw.get("total_results", len(items))}}

    @app.get("/api/v1/tasks/{task_id}")
    def get_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        task, _, _ = task_for(db, task_id, user)
        submissions = db.scalars(select(Submission).where(Submission.task_id == task_id)
                                 .order_by(Submission.created_at, Submission.id)).all()
        result = []
        for sub in submissions:
            reviews = db.scalars(select(Review).where(Review.submission_id == sub.id)).all()
            result.append({"id": sub.id, "summary": sub.summary, "url": sub.url,
                           "createdAt": iso(sub.created_at), "reviews": [
                               {"id": r.id, "comment": r.comment, "decision": r.decision,
                                "createdAt": iso(r.created_at)} for r in reviews
                           ]})
        resources = db.scalars(select(Resource).where(Resource.task_id == task_id)).all()
        return {"data": {**task_summary(db, task), "description": task.description,
                         "acceptanceCriteria": task.acceptance_criteria,
                         "planeWorkItemId": task.plane_work_item_id, "planeSync": task.plane_sync,
                         "resources": [{"id": r.id, "title": r.title} for r in resources],
                         "submissions": result}}

    @app.patch("/api/v1/tasks/{task_id}")
    def update_task(task_id: str, payload: StatusInput,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
        task, _, _ = task_for(db, task_id, user)
        if task.assignee_id != user.id or task.status in ("review", "done"):
            raise HTTPException(409, "此任务当前不能由本人更新")
        if payload.status not in ("todo", "doing", "blocked"):
            raise HTTPException(400, "只能设置待办、进行中或遇到困难")
        task.status = payload.status
        task.blocker = payload.blocker
        db.commit()
        return {"data": {**task_summary(db, task), "blocker": task.blocker}}

    @app.post("/api/v1/tasks/{task_id}/submissions")
    def submit_task(task_id: str, payload: SubmissionInput,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
        task, team, _ = task_for(db, task_id, user)
        if task.assignee_id != user.id:
            raise HTTPException(403, "只能提交自己的任务")
        if task.status in ("review", "done"):
            raise HTTPException(409, "任务正在等待反馈或已经完成")
        if payload.url and not payload.url.startswith(("https://", "http://")):
            raise HTTPException(400, "成果链接需以 http:// 或 https:// 开头")
        submission = Submission(task_id=task_id, user_id=user.id,
                                summary=payload.summary, url=payload.url)
        db.add(submission)
        task.status = "review"
        note(db, task.reviewer_id, f"待反馈：{task.title}")
        db.commit()
        try:
            plane.add_comment(team, task.plane_work_item_id, f"研途提交：{payload.summary}")
        except PlaneError:
            task.plane_sync = "comment_failed"
            db.commit()
        return {"data": {"id": submission.id, "taskId": task.id, "status": task.status,
                         "planeSync": task.plane_sync}}

    @app.post("/api/v1/submissions/{submission_id}/reviews")
    def review_submission(submission_id: str, payload: ReviewInput,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
        submission = db.get(Submission, submission_id)
        if submission is None:
            raise HTTPException(404, "提交记录不存在")
        task, team, membership = task_for(db, submission.task_id, user)
        if user.id != task.reviewer_id and membership.role != "owner":
            raise HTTPException(403, "不是指定反馈人")
        can_manage(membership)
        if payload.decision not in ("approved", "changes_requested"):
            raise HTTPException(400, "反馈结果无效")
        latest = db.scalar(select(Submission).where(Submission.task_id == task.id)
                           .order_by(Submission.created_at.desc(), Submission.id.desc()).limit(1))
        if task.status != "review" or latest is None or latest.id != submission.id:
            raise HTTPException(409, "提交已被处理或不是最新版本")
        review = Review(submission_id=submission.id, reviewer_id=user.id,
                        comment=payload.comment, decision=payload.decision)
        db.add(review)
        task.status = "done" if payload.decision == "approved" else "doing"
        note(db, task.assignee_id, f"任务反馈：{task.title}（{task.status}）")
        db.commit()
        try:
            plane.add_comment(team, task.plane_work_item_id, f"研途反馈：{payload.comment}")
        except PlaneError:
            task.plane_sync = "comment_failed"
            db.commit()
        return {"data": {"id": review.id, "taskStatus": task.status, "planeSync": task.plane_sync}}

    @app.get("/api/v1/teams/{team_id}/resources")
    def list_resources(team_id: str, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, team_id, user)
        items, total = item_page(db, Resource, team_id, page, pageSize)
        return {"data": {"items": [
            {"id": r.id, "title": r.title, "type": r.type,
             "owner": db.get(User, r.owner_id).display_name} for r in items
        ], "total": total}}

    @app.post("/api/v1/teams/{team_id}/resources")
    async def upload_resource(
        team_id: str, title: str = Form(min_length=1, max_length=200),
        type: str = Form(), description: str = Form(""), visibility: str = Form("team"), tags: str = Form(""), meetingId: str = Form(""),
        taskId: str = Form(""), file: UploadFile = File(),
        user: User = Depends(current_user), db: Session = Depends(get_db),
    ):
        team_member(db, team_id, user)
        if type not in ("paper", "note", "slides", "other"):
            raise HTTPException(400, "资料类型不正确")
        if visibility not in ("team", "private"):
            raise HTTPException(400, "资料可见范围不正确")
        if meetingId:
            meeting = db.get(Meeting, meetingId)
            if meeting is None or meeting.team_id != team_id:
                raise HTTPException(400, "关联组会不属于当前课题组")
        if taskId:
            task = db.get(Task, taskId)
            if task is None or task.team_id != team_id:
                raise HTTPException(400, "关联任务不属于当前课题组")
            _, membership = team_member(db, team_id, user)
            if user.id not in (task.assignee_id, task.reviewer_id) and membership.role != "owner":
                raise HTTPException(403, "无权向此任务关联资料")
        max_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
        contents = await file.read(max_bytes + 1)
        if not contents or len(contents) > max_bytes:
            raise HTTPException(413, "文件为空或超过上传限制")
        filename = (file.filename or "file").replace("\\", "/").split("/")[-1]
        filename = filename.replace("\r", "").replace("\n", "")[:255] or "file"
        storage_name = str(uuid4())
        destination = uploads / storage_name
        destination.write_bytes(contents)
        resource = Resource(team_id=team_id, owner_id=user.id, title=title.strip(), type=type,
                            description=description, extracted_text=extract_document_text(filename, contents),
                            meeting_id=meetingId or None, task_id=taskId or None,
                            file_name=filename, storage_name=storage_name, size=len(contents), visibility=visibility)
        db.add(resource)
        try:
            db.commit()
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return {"data": {"id": resource.id, "title": resource.title}}

    @app.get("/api/v1/resources/{resource_id}")
    def get_resource(resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        item = db.get(Resource, resource_id)
        if item is None:
            raise HTTPException(404, "资料不存在")
        team_member(db, item.team_id, user)
        return {"data": {"id": item.id, "title": item.title, "type": item.type,
                         "description": item.description, "owner": db.get(User, item.owner_id).display_name,
                         "fileName": item.file_name, "size": item.size,
                         "meetingId": item.meeting_id, "taskId": item.task_id}}

    @app.get("/api/v1/resources/{resource_id}/download")
    def download_resource(resource_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        item = db.get(Resource, resource_id)
        if item is None:
            raise HTTPException(404, "资料不存在")
        team_member(db, item.team_id, user)
        location = uploads / item.storage_name
        if not location.is_file():
            raise HTTPException(404, "文件暂时不可用")
        return FileResponse(location, media_type="application/octet-stream", filename=item.file_name)

    @app.get("/api/v1/me/dashboard")
    def dashboard(teamId: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        team_member(db, teamId, user)
        tasks = db.scalars(select(Task).where(Task.team_id == teamId, Task.assignee_id == user.id)).all()
        current = next((t for t in tasks if t.status in ("doing", "review", "blocked", "todo")), None)
        upcoming = db.scalar(select(Meeting).where(Meeting.team_id == teamId, Meeting.starts_at >= utcnow())
                             .order_by(Meeting.starts_at).limit(1))
        return {"data": {"currentTask": {"id": current.id, "title": current.title} if current else None,
                         "progress": {"completed": sum(t.status == "done" for t in tasks), "total": len(tasks)},
                         "nextMeeting": {"id": upcoming.id, "title": upcoming.title,
                                         "startsAt": iso(upcoming.starts_at)} if upcoming else None}}

    @app.get("/api/v1/teams/{team_id}/search")
    def search(team_id: str, q: str = Query(min_length=1, max_length=100),
               page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, membership = team_member(db, team_id, user)
        from .cloud_drive import resource_visible
        term = f"%{q}%"
        result = []
        for model, kind, title_field, summary_field in (
            (Route, "route", Route.title, Route.description),
            (Experience, "experience", Experience.title, Experience.content),
            (Meeting, "meeting", Meeting.title, Meeting.agenda),
            (Resource, "resource", Resource.title, Resource.description),
        ):
            items = db.scalars(select(model).where(model.team_id == team_id,
                                                    or_(title_field.ilike(term), summary_field.ilike(term)))).all()
            result.extend({"id": r.id, "type": kind, "title": r.title,
                           "summary": str(getattr(r, summary_field.key, ""))[:180]} for r in items if (model is not Resource or resource_visible(db,r,user)))
        visible = True if membership.role == "owner" else or_(Task.assignee_id == user.id, Task.reviewer_id == user.id)
        own_tasks = db.scalars(select(Task).where(Task.team_id == team_id, visible,
                                                   or_(Task.title.ilike(term), Task.description.ilike(term)))).all()
        result.extend({"id": t.id, "type": "task", "title": t.title,
                       "summary": t.description[:180]} for t in own_tasks)
        start = (page - 1) * pageSize
        return {"data": {"items": result[start:start + pageSize], "total": len(result)}}

    @app.get("/api/v1/me/notifications")
    def notifications(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
        total = db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id)) or 0
        items = db.scalars(select(Notification).where(Notification.user_id == user.id)
                           .order_by(Notification.created_at.desc())
                           .offset((page - 1) * pageSize).limit(pageSize)).all()
        return {"data": {"items": [{"id": n.id, "title": n.title, "read": n.read,
                                    "createdAt": iso(n.created_at)} for n in items], "total": total}}

    @app.patch("/api/v1/me/notifications/{notification_id}")
    def read_notification(notification_id: str, payload: ReadInput,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
        item = db.get(Notification, notification_id)
        if item is None or item.user_id != user.id:
            raise HTTPException(404, "通知不存在")
        item.read = payload.read
        db.commit()
        return {"data": {"id": item.id, "read": item.read}}

    @app.post("/api/v1/teams/{team_id}/questions")
    def ask_question(team_id: str, payload: QuestionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
        _, membership = team_member(db, team_id, user)
        criteria = [Resource.team_id == team_id, Resource.extracted_text != "", Resource.archived.is_(False),
                    or_(Resource.visibility == "team", Resource.owner_id == user.id, membership.role == "owner")]
        if payload.resourceIds:
            criteria.append(Resource.id.in_(payload.resourceIds))
        resources = db.scalars(select(Resource).where(*criteria).order_by(Resource.id.desc()).limit(100)).all()
        try:
            return {"data": research_assistant.answer(payload.question, resources)}
        except AssistantUnavailable as error:
            raise HTTPException(503, str(error)) from error

    # Upgrade the original extension handlers while retaining its Plane / assistant integrations.
    from .features import register_features
    register_features(app, {**globals(), **locals()})

    # The API routes are registered first. Browsers use the same origin for pages and requests.
    if front.is_dir():
        app.mount("/", StaticFiles(directory=front, html=True), name="frontend")
    return app


app = create_app()
