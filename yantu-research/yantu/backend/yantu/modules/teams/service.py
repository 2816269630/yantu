"""modules.teams.service business operations."""

from __future__ import annotations
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi import Request
from sqlalchemy.orm import Session
from datetime import datetime
from sqlalchemy import or_
import os
from sqlalchemy import select
from datetime import timedelta
from datetime import timezone
from ...core.models import (
    Experience,
    Invitation,
    Meeting,
    Member,
    Resource,
    ResourceShare,
    Task,
    Team,
    User,
    utcnow,
)
from ...modules.teams.schemas import PlaneBinding, TeamInput
from ...core.security import new_token, token_digest
from ...integrations.plane import PlaneError


def create_team(payload: TeamInput, user: User = None, db: Session = None, *, services):
    from ...core.permissions import allowed_plane_project

    if bool(payload.planeWorkspaceSlug) != bool(payload.planeProjectId):
        raise HTTPException(400, "Plane 工作区和项目 ID 必须同时填写")
    if payload.planeWorkspaceSlug and payload.planeProjectId:
        allowed_plane_project(payload.planeWorkspaceSlug.strip(), payload.planeProjectId.strip())
    team = Team(
        name=payload.name.strip(),
        plane_workspace_slug=payload.planeWorkspaceSlug or None,
        plane_project_id=payload.planeProjectId or None,
    )
    if team.plane_workspace_slug:
        try:
            services.plane.list_work_items(team)
        except PlaneError as exc:
            raise HTTPException(502, str(exc)) from exc
    db.add(team)
    db.flush()
    db.add(Member(team_id=team.id, user_id=user.id, role="owner"))
    db.commit()
    return {
        "data": {
            "id": team.id,
            "name": team.name,
            "planeConnected": services.plane.configured(team),
        }
    }


def bind_plane(
    team_id: str, payload: PlaneBinding, user: User = None, db: Session = None, *, services
):
    from ...core.permissions import allowed_plane_project
    from ...core.permissions import team_member

    team, membership = team_member(db, team_id, user)
    if membership.role != "owner":
        raise HTTPException(403, "只有负责人可绑定 Plane")
    if not payload.planeWorkspaceSlug or not payload.planeProjectId:
        raise HTTPException(400, "请填写 Plane Workspace slug 和 Project UUID")
    allowed_plane_project(payload.planeWorkspaceSlug.strip(), payload.planeProjectId.strip())
    team.plane_workspace_slug = payload.planeWorkspaceSlug.strip()
    team.plane_project_id = payload.planeProjectId.strip()
    if not services.plane.configured(team):
        raise HTTPException(503, "服务端尚未配置 Plane API Key")
    try:
        services.plane.list_work_items(team)
    except PlaneError as exc:
        raise HTTPException(502, str(exc)) from exc
    db.commit()
    return {"data": {"id": team.id, "name": team.name, "planeConnected": True}}


def my_teams(user: User = None, db: Session = None, *, services):
    memberships = db.scalars(
        select(Member).where(Member.user_id == user.id).order_by(Member.id)
    ).all()
    return {
        "data": {
            "items": [
                {
                    "id": m.team_id,
                    "name": db.get(Team, m.team_id).name,
                    "role": m.role,
                    "planeConnected": services.plane.configured(db.get(Team, m.team_id)),
                }
                for m in memberships
            ],
            "total": len(memberships),
        }
    }


def get_team(team_id: str, user: User = None, db: Session = None, *, services):
    from ...core.permissions import team_member
    from ...core.metadata import get_meta

    team, member = team_member(db, team_id, user)
    return {
        "data": {
            "id": team.id,
            "name": team.name,
            "role": member.role,
            "description": get_meta(db, "team", team.id).get("description", ""),
            "planeConnected": services.plane.configured(team),
            "planeWorkspaceSlug": team.plane_workspace_slug,
            "planeProjectId": team.plane_project_id,
        }
    }


def edit_team(
    team_id: str, payload: dict = None, user: User = None, db: Session = None, *, services
):
    from ...core.metadata import put_meta
    from ...core.permissions import require_owner
    from ...core.validation import text_value

    team = require_owner(db, team_id, user)
    if "name" in payload:
        team.name = text_value(payload, "name", maximum=100, required=True)
    if "description" in payload:
        put_meta(db, "team", team.id, {"description": text_value(payload, "description")})
    db.commit()
    return get_team(team_id, user, db, services=services)


def members(team_id: str, page: int = 1, pageSize: int = 20, user: User = None, db: Session = None):
    from ...core.permissions import team_member
    from ...core.presentation import page_data

    team_member(db, team_id, user)
    result = []
    for member in db.scalars(
        select(Member).where(Member.team_id == team_id).order_by(Member.id)
    ).all():
        person = db.get(User, member.user_id)
        result.append(
            {
                "id": person.id,
                "name": person.display_name,
                "displayName": person.display_name,
                "email": person.email,
                "direction": person.direction,
                "role": member.role,
            }
        )
    return page_data(result, page, pageSize)


def edit_member(
    team_id: str, user_id: str, payload: dict = None, user: User = None, db: Session = None
):
    from ...core.permissions import require_owner

    require_owner(db, team_id, user)
    row = db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == user_id))
    if row is None:
        raise HTTPException(404, "成员不存在")
    if row.role == "owner":
        raise HTTPException(409, "不能降级负责人")
    role = payload.get("role")
    if role not in ("student", "mentor"):
        raise HTTPException(400, "角色无效")
    if role == "student" and db.scalar(
        select(Task.id)
        .where(Task.team_id == team_id, Task.reviewer_id == user_id, Task.status != "done")
        .limit(1)
    ):
        raise HTTPException(409, "请先交接此成员的待反馈任务")
    row.role = role
    db.commit()
    return {"data": {"id": user_id, "role": role}}


def remove_member(team_id: str, user_id: str, user: User = None, db: Session = None):
    from ...core.permissions import require_owner

    require_owner(db, team_id, user)
    row = db.scalar(select(Member).where(Member.team_id == team_id, Member.user_id == user_id))
    if row is None:
        raise HTTPException(404, "成员不存在")
    if row.role == "owner":
        raise HTTPException(409, "不能移除负责人")
    if db.scalar(
        select(Task.id)
        .where(
            Task.team_id == team_id,
            Task.status != "done",
            or_(Task.assignee_id == user_id, Task.reviewer_id == user_id),
        )
        .limit(1)
    ):
        raise HTTPException(409, "请先完成或交接成员的未完成任务")
    for share in db.scalars(
        select(ResourceShare).where(
            ResourceShare.team_id == team_id, ResourceShare.active.is_(True)
        )
    ):
        resource = db.get(Resource, share.resource_id)
        if share.user_id == user_id or (resource and resource.owner_id == user_id):
            share.active = False
    db.delete(row)
    db.commit()
    return {"data": None}


def invitations(team_id: str, user: User = None, db: Session = None):
    from ...core.presentation import iso
    from ...core.permissions import require_owner
    from ...core.validation import timestamp

    require_owner(db, team_id, user)
    rows = db.scalars(
        select(Invitation)
        .where(Invitation.team_id == team_id)
        .order_by(Invitation.expires_at.desc())
    ).all()
    return {
        "data": {
            "items": [
                {
                    "id": r.id,
                    "email": r.email,
                    "role": r.role,
                    "expiresAt": iso(r.expires_at),
                    "status": (
                        "accepted"
                        if r.accepted_at
                        else "expired" if timestamp(iso(r.expires_at)) <= utcnow() else "pending"
                    ),
                }
                for r in rows
            ],
            "total": len(rows),
        }
    }


def invite(
    team_id: str, request: Request, payload: dict = None, user: User = None, db: Session = None
):
    from ...core.presentation import iso
    from ...core.permissions import require_owner
    from ...core.validation import text_value

    require_owner(db, team_id, user)
    email = text_value(payload, "email", maximum=254, required=True).lower()
    if "@" not in email or payload.get("role") not in ("student", "mentor"):
        raise HTTPException(400, "邮箱或角色无效")
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user and db.scalar(
        select(Member).where(Member.team_id == team_id, Member.user_id == existing_user.id)
    ):
        raise HTTPException(409, "此用户已在课题组中")
    token = new_token()
    row = Invitation(
        team_id=team_id,
        email=email,
        role=payload["role"],
        token_hash=token_digest(token),
        expires_at=utcnow() + timedelta(days=7),
    )
    db.add(row)
    db.commit()
    return {
        "data": {
            "id": row.id,
            "status": "pending",
            "inviteToken": token,
            "inviteUrl": str(request.base_url).rstrip("/") + "/?invite=" + token,
            "expiresAt": iso(row.expires_at),
        }
    }


def accept_invitation(token: str, user: User = None, db: Session = None):
    from ...modules.auth.service import claim_invitation
    from ...modules.auth.service import invite_record

    row = invite_record(db, token, user.email)
    if db.scalar(select(Member).where(Member.team_id == row.team_id, Member.user_id == user.id)):
        raise HTTPException(409, "已经加入课题组")
    claim_invitation(db, row)
    db.add(Member(team_id=row.team_id, user_id=user.id, role=row.role))
    db.commit()
    return {"data": {"teamId": row.team_id}}


def export_team(team_id: str, user: User = None, db: Session = None):
    from ...core.presentation import iso
    from ...core.permissions import team_member
    from ...modules.drive.permissions import resource_visible
    from ...core.presentation import user_name
    from ...modules.drive.service import resource_json
    from ...modules.tasks.service import task_json
    from ...modules.tasks.service import task_visible

    team, member_of_team = team_member(db, team_id, user)
    tasks = db.scalars(select(Task).where(Task.team_id == team_id)).all()
    meetings = db.scalars(select(Meeting).where(Meeting.team_id == team_id)).all()
    resources = db.scalars(select(Resource).where(Resource.team_id == team_id)).all()
    experiences = db.scalars(select(Experience).where(Experience.team_id == team_id)).all()
    content = {
        "exportedAt": iso(datetime.now(timezone.utc)),
        "team": {"id": team.id, "name": team.name},
        "tasks": [task_json(db, r) for r in tasks if task_visible(r, member_of_team, user)],
        "meetings": [
            {
                "id": r.id,
                "title": r.title,
                "startsAt": iso(r.starts_at),
                "location": r.location,
                "agenda": r.agenda,
                "status": r.status,
            }
            for r in meetings
        ],
        "resources": [
            resource_json(db, r, user) for r in resources if resource_visible(db, r, user)
        ],
        "experiences": [
            {
                "id": r.id,
                "title": r.title,
                "startingPoint": r.starting_point,
                "content": r.content,
                "author": user_name(db, r.author_id),
                "createdAt": iso(r.created_at),
            }
            for r in experiences
        ],
    }
    return JSONResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="research-export-{team_id}.json"'},
    )


def plane_projects(user: User = None, db: Session = None, *, services):
    if not db.scalar(
        select(Member.id).where(Member.user_id == user.id, Member.role.in_(("owner", "mentor")))
    ):
        raise HTTPException(403, "需要前辈或负责人权限")
    try:
        rows = (
            services.plane.list_allowed_projects(os.getenv("PLANE_ALLOWED_PROJECTS", ""))
            if hasattr(services.plane, "list_allowed_projects")
            else []
        )
    except PlaneError as error:
        raise HTTPException(502, str(error)) from error
    return {"data": {"items": rows, "total": len(rows)}}
