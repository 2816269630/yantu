"""modules.dashboard.service business operations."""

from __future__ import annotations
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy import select
from ...core.models import Experience, Meeting, Resource, Route, Task, User, utcnow


def health():
    return {"status": "ok"}


def search(
    team_id: str,
    q: str = None,
    page: int = 1,
    pageSize: int = 20,
    user: User = None,
    db: Session = None,
):
    from ...core.permissions import team_member
    from ...modules.drive.permissions import resource_visible

    _, membership = team_member(db, team_id, user)
    term = f"%{q}%"
    result = []
    for model, kind, title_field, summary_field in (
        (Route, "route", Route.title, Route.description),
        (Experience, "experience", Experience.title, Experience.content),
        (Meeting, "meeting", Meeting.title, Meeting.agenda),
        (Resource, "resource", Resource.title, Resource.description),
    ):
        items = db.scalars(
            select(model).where(
                model.team_id == team_id, or_(title_field.ilike(term), summary_field.ilike(term))
            )
        ).all()
        result.extend(
            (
                {
                    "id": r.id,
                    "type": kind,
                    "title": r.title,
                    "summary": str(getattr(r, summary_field.key, ""))[:180],
                }
                for r in items
                if model is not Resource or resource_visible(db, r, user)
            )
        )
    visible = (
        True
        if membership.role == "owner"
        else or_(Task.assignee_id == user.id, Task.reviewer_id == user.id)
    )
    own_tasks = db.scalars(
        select(Task).where(
            Task.team_id == team_id,
            visible,
            or_(Task.title.ilike(term), Task.description.ilike(term)),
        )
    ).all()
    result.extend(
        (
            {"id": t.id, "type": "task", "title": t.title, "summary": t.description[:180]}
            for t in own_tasks
        )
    )
    start = (page - 1) * pageSize
    return {"data": {"items": result[start : start + pageSize], "total": len(result)}}


def drive_dashboard(teamId: str, user: User = None, db: Session = None):
    from ...core.presentation import iso
    from ...core.permissions import team_member
    from ...core.metadata import get_meta
    from ...modules.learning.service import my_enrollments
    from ...modules.tasks.service import review_queue
    from ...modules.tasks.service import task_json

    _, member = team_member(db, teamId, user)
    tasks = db.scalars(
        select(Task).where(
            Task.team_id == teamId, Task.assignee_id == user.id, Task.status != "done"
        )
    ).all()
    tasks.sort(key=lambda t: (get_meta(db, "task", t.id).get("dueAt") or "9999", t.id))
    plans = my_enrollments(teamId, user, db)["data"]["items"]
    upcoming = db.scalar(
        select(Meeting)
        .where(
            Meeting.team_id == teamId, Meeting.status == "scheduled", Meeting.starts_at >= utcnow()
        )
        .order_by(Meeting.starts_at)
        .limit(1)
    )
    reviews = (
        review_queue(teamId, 1, 100, user, db)["data"]["total"]
        if member.role in ("owner", "mentor")
        else 0
    )
    return {
        "data": {
            "currentTask": task_json(db, tasks[0]) if tasks else None,
            "progress": {
                "completed": sum((p["progress"]["completed"] for p in plans)),
                "total": sum((p["progress"]["total"] for p in plans)),
            },
            "reviewCount": reviews,
            "nextMeeting": (
                {
                    "id": upcoming.id,
                    "title": upcoming.title,
                    "startsAt": iso(upcoming.starts_at),
                    "location": upcoming.location,
                    "status": upcoming.status,
                }
                if upcoming
                else None
            ),
        }
    }
