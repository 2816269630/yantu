"""modules.progress.service business operations."""

from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from ...core.models import ProgressComment, ProgressPost, User


def progress(
    team_id: str, page: int = 1, pageSize: int = 100, user: User = None, db: Session = None
):
    from ...core.presentation import iso
    from ...core.permissions import team_member
    from ...core.presentation import user_name
    from ...core.presentation import page_data

    team_member(db, team_id, user)
    rows = db.scalars(
        select(ProgressPost)
        .where(ProgressPost.team_id == team_id)
        .order_by(ProgressPost.created_at.desc())
    ).all()
    items = []
    for r in rows:
        comments = db.scalars(select(ProgressComment).where(ProgressComment.post_id == r.id)).all()
        items.append(
            {
                "id": r.id,
                "authorId": r.author_id,
                "author": user_name(db, r.author_id),
                "content": r.content,
                "blockers": r.blockers,
                "nextPlan": r.next_plan,
                "kind": r.kind,
                "status": r.status,
                "createdAt": iso(r.created_at),
                "comments": [
                    {
                        "id": c.id,
                        "author": user_name(db, c.author_id),
                        "content": c.content,
                        "createdAt": iso(c.created_at),
                    }
                    for c in comments
                ],
            }
        )
    return page_data(items, page, pageSize)


def add_progress(team_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...core.permissions import team_member
    from ...core.validation import text_value

    team_member(db, team_id, user)
    row = ProgressPost(
        team_id=team_id,
        author_id=user.id,
        content=text_value(payload, "content", required=True),
        blockers=text_value(payload, "blockers"),
        next_plan=text_value(payload, "nextPlan"),
        kind=payload.get("kind") if payload.get("kind") in ("progress", "help") else "progress",
    )
    db.add(row)
    db.commit()
    return {"data": {"id": row.id}}


def add_progress_comment(post_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...core.permissions import team_member
    from ...core.validation import text_value

    post = db.get(ProgressPost, post_id)
    if not post:
        raise HTTPException(404, "记录不存在")
    team_member(db, post.team_id, user)
    row = ProgressComment(
        post_id=post.id, author_id=user.id, content=text_value(payload, "content", required=True)
    )
    db.add(row)
    db.commit()
    return {"data": {"id": row.id}}


def resolve_progress(post_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...core.permissions import team_member

    row = db.get(ProgressPost, post_id)
    if not row:
        raise HTTPException(404, "记录不存在")
    _, member = team_member(db, row.team_id, user)
    if row.author_id != user.id and member.role != "owner":
        raise HTTPException(403, "无权操作")
    row.status = "resolved" if payload.get("status") == "resolved" else "open"
    db.commit()
    return {"data": {"id": row.id, "status": row.status}}
