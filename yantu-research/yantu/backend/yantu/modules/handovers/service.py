"""modules.handovers.service business operations."""

from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from sqlalchemy import select
from datetime import timezone
from ...core.models import Handover, Member, Resource, User


def list_handovers(
    team_id: str, page: int = 1, pageSize: int = 100, user: User = None, db: Session = None
):
    from ...core.presentation import iso
    from ...core.permissions import team_member
    from ...core.presentation import user_name
    from ...core.presentation import page_data

    team_member(db, team_id, user)
    rows = db.scalars(
        select(Handover).where(Handover.team_id == team_id).order_by(Handover.created_at.desc())
    ).all()
    items = [
        {
            "id": r.id,
            "title": r.title,
            "content": r.content,
            "fromUserId": r.from_user_id,
            "fromUserName": user_name(db, r.from_user_id),
            "toUserId": r.to_user_id,
            "toUserName": user_name(db, r.to_user_id),
            "taskIds": r.task_ids or [],
            "resourceIds": r.resource_ids or [],
            "status": r.status,
            "createdAt": iso(r.created_at),
            "acceptedAt": iso(r.accepted_at),
        }
        for r in rows
    ]
    return page_data(items, page, pageSize)


def create_handover(team_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...core.permissions import task_for
    from ...core.permissions import team_member
    from ...modules.drive.permissions import resource_for
    from ...modules.notifications.service import notify
    from ...core.validation import text_value

    team_member(db, team_id, user)
    to_user = text_value(payload, "toUserId", maximum=36, required=True)
    if to_user == user.id or not db.scalar(
        select(Member.id).where(Member.team_id == team_id, Member.user_id == to_user)
    ):
        raise HTTPException(400, "请选择课题组内的接收人")
    task_ids = [str(x) for x in payload.get("taskIds", [])]
    resource_ids = [str(x) for x in payload.get("resourceIds", [])]
    for rid in resource_ids:
        resource_for(db, rid, user)
    for tid in task_ids:
        task_for(db, tid, user)
    row = Handover(
        team_id=team_id,
        from_user_id=user.id,
        to_user_id=to_user,
        title=text_value(payload, "title", maximum=200, required=True),
        content=text_value(payload, "content", required=True),
        task_ids=task_ids,
        resource_ids=resource_ids,
    )
    db.add(row)
    notify(db, to_user, f"收到科研交接：{row.title}", team_id, "handover", row.id)
    db.commit()
    return {"data": {"id": row.id}}


def accept_handover(handover_id: str, user: User = None, db: Session = None):
    from ...core.presentation import iso
    from ...core.permissions import team_member
    from ...modules.drive.permissions import resource_visible

    row = db.get(Handover, handover_id)
    if not row:
        raise HTTPException(404, "交接记录不存在")
    team_member(db, row.team_id, user)
    if row.to_user_id != user.id:
        raise HTTPException(403, "只有接收人可以确认交接")
    if row.status != "accepted":
        row.status = "accepted"
        row.accepted_at = datetime.now(timezone.utc)
        for rid in row.resource_ids or []:
            resource = db.get(Resource, rid)
            if resource and (not resource_visible(db, resource, user)):
                raise HTTPException(403, "请先由所有者明确共享交接资料")
        db.commit()
    return {"data": {"id": row.id, "status": row.status, "acceptedAt": iso(row.accepted_at)}}
