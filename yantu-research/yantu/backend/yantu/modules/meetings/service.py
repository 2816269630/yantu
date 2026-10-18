"""modules.meetings.service business operations."""

from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import timezone
from ...core.models import Meeting, MeetingQuestion, Resource, Task, User, utcnow
from ...modules.meetings.schemas import MeetingInput, MinutesInput


def create_meeting(team_id: str, payload: MeetingInput, user: User = None, db: Session = None):
    from ...core.permissions import can_manage
    from ...core.permissions import team_member

    _, membership = team_member(db, team_id, user)
    can_manage(membership)
    if payload.startsAt.tzinfo is None:
        raise HTTPException(400, "会议时间需要包含时区")
    meeting = Meeting(
        team_id=team_id,
        title=payload.title.strip(),
        starts_at=payload.startsAt.astimezone(timezone.utc),
        location=payload.location,
        agenda=payload.agenda,
    )
    db.add(meeting)
    db.commit()
    return {"data": {"id": meeting.id}}


def save_minutes(meeting_id: str, payload: MinutesInput, user: User = None, db: Session = None):
    from ...core.permissions import can_manage
    from ...core.presentation import iso
    from ...core.permissions import team_member

    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(404, "组会不存在")
    _, membership = team_member(db, meeting.team_id, user)
    can_manage(membership)
    meeting.minutes_content = payload.content
    meeting.minutes_updated_at = utcnow()
    meeting.minutes_author_id = user.id
    db.commit()
    return {
        "data": {
            "id": meeting.id,
            "content": meeting.minutes_content,
            "updatedAt": iso(meeting.minutes_updated_at),
        }
    }


def edit_meeting(meeting_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...core.permissions import can_manage
    from ...core.permissions import team_member
    from ...core.validation import text_value
    from ...core.validation import timestamp

    row = db.get(Meeting, meeting_id)
    if row is None:
        raise HTTPException(404, "组会不存在")
    _, member = team_member(db, row.team_id, user)
    can_manage(member)
    if "title" in payload:
        row.title = text_value(payload, "title", maximum=200, required=True)
    if "startsAt" in payload:
        row.starts_at = timestamp(payload["startsAt"])
    if "location" in payload:
        row.location = text_value(payload, "location", maximum=200, required=True)
    if "agenda" in payload:
        row.agenda = text_value(payload, "agenda", required=True)
    if "status" in payload:
        if payload["status"] not in ("scheduled", "completed", "archived"):
            raise HTTPException(400, "组会状态无效")
        row.status = payload["status"]
    db.commit()
    return {"data": {"id": row.id, "status": row.status}}


def rich_meetings(
    team_id: str, page: int = 1, pageSize: int = 20, user: User = None, db: Session = None
):
    from ...core.presentation import iso
    from ...core.permissions import team_member
    from ...core.presentation import page_data

    team_member(db, team_id, user)
    rows = db.scalars(
        select(Meeting).where(Meeting.team_id == team_id).order_by(Meeting.starts_at.desc())
    ).all()
    items = [
        {
            "id": r.id,
            "title": r.title,
            "startsAt": iso(r.starts_at),
            "location": r.location,
            "agenda": r.agenda,
            "status": r.status,
        }
        for r in rows
    ]
    return page_data(items, page, pageSize)


def rich_meeting(meeting_id: str, user: User = None, db: Session = None):
    from ...core.presentation import iso
    from ...core.permissions import team_member
    from ...modules.drive.permissions import resource_visible
    from ...core.presentation import user_name
    from ...modules.drive.service import referenced_resources
    from ...modules.drive.service import resource_json
    from ...modules.tasks.service import task_json

    row = db.get(Meeting, meeting_id)
    if not row:
        raise HTTPException(404, "组会不存在")
    team_member(db, row.team_id, user)
    questions = db.scalars(
        select(MeetingQuestion)
        .where(MeetingQuestion.meeting_id == row.id)
        .order_by(MeetingQuestion.created_at)
    ).all()
    tasks = db.scalars(select(Task).where(Task.meeting_id == row.id)).all()
    resources = db.scalars(select(Resource).where(Resource.meeting_id == row.id)).all()
    resources = list(
        {r.id: r for r in resources + referenced_resources(db, "meeting", row.id)}.values()
    )
    return {
        "data": {
            "id": row.id,
            "title": row.title,
            "startsAt": iso(row.starts_at),
            "location": row.location,
            "agenda": row.agenda,
            "status": row.status,
            "minutes": (
                {"content": row.minutes_content, "updatedAt": iso(row.minutes_updated_at)}
                if row.minutes_content is not None
                else None
            ),
            "questions": [
                {
                    "id": q.id,
                    "authorId": q.author_id,
                    "author": user_name(db, q.author_id),
                    "content": q.content,
                    "answer": q.answer,
                    "status": q.status,
                    "createdAt": iso(q.created_at),
                }
                for q in questions
            ],
            "tasks": [task_json(db, t) for t in tasks],
            "resources": [
                resource_json(db, r, user) for r in resources if resource_visible(db, r, user)
            ],
        }
    }


def add_meeting_question(
    meeting_id: str, payload: dict = None, user: User = None, db: Session = None
):
    from ...core.permissions import team_member
    from ...core.validation import text_value

    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(404, "组会不存在")
    team_member(db, meeting.team_id, user)
    row = MeetingQuestion(
        meeting_id=meeting_id,
        author_id=user.id,
        content=text_value(payload, "content", required=True),
    )
    db.add(row)
    db.commit()
    return {"data": {"id": row.id}}


def answer_question(question_id: str, payload: dict = None, user: User = None, db: Session = None):
    from ...core.permissions import can_manage
    from ...core.permissions import team_member
    from ...core.validation import text_value

    row = db.get(MeetingQuestion, question_id)
    meeting = db.get(Meeting, row.meeting_id) if row else None
    if not row or not meeting:
        raise HTTPException(404, "问题不存在")
    _, member = team_member(db, meeting.team_id, user)
    can_manage(member)
    row.answer = text_value(payload, "answer", required=True)
    row.status = "resolved"
    db.commit()
    return {"data": {"id": row.id}}
