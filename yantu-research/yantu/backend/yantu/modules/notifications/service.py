"""modules.notifications.service business operations."""

from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import update
from ...core.models import Member, Notification, User
from ...modules.notifications.schemas import ReadInput


def note(db: Session, user_id: str, title: str):
    db.add(Notification(user_id=user_id, title=title))


def notifications(page: int = 1, pageSize: int = 20, user: User = None, db: Session = None):
    from ...core.presentation import iso

    total = (
        db.scalar(
            select(func.count()).select_from(Notification).where(Notification.user_id == user.id)
        )
        or 0
    )
    items = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * pageSize)
        .limit(pageSize)
    ).all()
    return {
        "data": {
            "items": [
                {"id": n.id, "title": n.title, "read": n.read, "createdAt": iso(n.created_at)}
                for n in items
            ],
            "total": total,
        }
    }


def read_notification(
    notification_id: str, payload: ReadInput, user: User = None, db: Session = None
):
    item = db.get(Notification, notification_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "通知不存在")
    item.read = payload.read
    db.commit()
    return {"data": {"id": item.id, "read": item.read}}


def notify(db, user_id, title, team_id=None, kind=None, ident=None):
    db.add(
        Notification(
            user_id=user_id, title=title[:255], team_id=team_id, target_type=kind, target_id=ident
        )
    )


def team_notify(db, team_id, title, except_user=None, kind=None, ident=None):
    for member in db.scalars(select(Member).where(Member.team_id == team_id)).all():
        if member.user_id != except_user:
            notify(db, member.user_id, title, team_id, kind, ident)


def read_all(user: User = None, db: Session = None):
    db.execute(update(Notification).where(Notification.user_id == user.id).values(read=True))
    db.commit()
    return {"data": None}
