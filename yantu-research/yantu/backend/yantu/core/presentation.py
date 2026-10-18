"""core.presentation business operations."""

from __future__ import annotations
from sqlalchemy.orm import Session
from datetime import datetime
from sqlalchemy import func
from sqlalchemy import select
from datetime import timezone
from ..core.models import User


def item_page(db: Session, model, team_id: str, page: int, page_size: int):
    total = db.scalar(select(func.count()).select_from(model).where(model.team_id == team_id)) or 0
    rows = db.scalars(
        select(model)
        .where(model.team_id == team_id)
        .order_by(model.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return (rows, total)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def user_name(db, user_id):
    row = db.get(User, user_id)
    return row.display_name if row else "已离组成员"


def actor(user):
    return {
        "id": user.id,
        "displayName": user.display_name,
        "email": user.email,
        "direction": user.direction or "",
    }


def page_data(items, page, page_size):
    return {
        "data": {"items": items[(page - 1) * page_size : page * page_size], "total": len(items)}
    }


def result(data):
    return {"data": data}


def paginate(items, page, page_size):
    return result(
        {
            "items": items[(page - 1) * page_size : page * page_size],
            "total": len(items),
            "page": page,
            "pageSize": page_size,
        }
    )
