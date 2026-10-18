"""core.permissions business operations."""

from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.orm import Session
import os
from sqlalchemy import select
from ..core.models import Member, Task, Team, User


def team_member(db: Session, team_id: str, user: User) -> tuple[Team, Member]:
    team = db.get(Team, team_id)
    membership = db.scalar(
        select(Member).where(Member.team_id == team_id, Member.user_id == user.id)
    )
    if team is None or membership is None:
        raise HTTPException(403, "无权访问该课题组")
    return (team, membership)


def can_manage(member: Member) -> None:
    if member.role not in ("mentor", "owner"):
        raise HTTPException(403, "需要前辈或负责人权限")


def allowed_plane_project(slug: str, project: str) -> None:
    allowed = {
        item.strip() for item in os.getenv("PLANE_ALLOWED_PROJECTS", "").split(",") if item.strip()
    }
    if f"{slug}:{project}" not in allowed:
        raise HTTPException(403, "此 Plane 项目尚未列入服务器的课题组绑定白名单")


def task_for(db: Session, task_id: str, user: User) -> tuple[Task, Team, Member]:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    team, membership = team_member(db, task.team_id, user)
    if task.assignee_id != user.id and task.reviewer_id != user.id and (membership.role != "owner"):
        raise HTTPException(403, "无权访问该任务")
    return (task, team, membership)


def require_owner(db, team_id, user):
    team, member = team_member(db, team_id, user)
    if member.role != "owner":
        raise HTTPException(403, "只有负责人可以操作")
    return team
