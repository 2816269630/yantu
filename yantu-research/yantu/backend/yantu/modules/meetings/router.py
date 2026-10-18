"""HTTP endpoints for meetings."""

from __future__ import annotations
from fastapi import Body
from fastapi import Depends
from sqlalchemy.orm import Session
from ...core.models import User
from ...modules.meetings.schemas import MeetingInput, MinutesInput

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.post("/api/v1/teams/{team_id}/meetings")
def create_meeting(
    team_id: str,
    payload: MeetingInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.create_meeting(team_id=team_id, payload=payload, user=user, db=db)


@router.put("/api/v1/meetings/{meeting_id}/minutes")
def save_minutes(
    meeting_id: str,
    payload: MinutesInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.save_minutes(meeting_id=meeting_id, payload=payload, user=user, db=db)


@router.patch("/api/v1/meetings/{meeting_id}")
def edit_meeting(
    meeting_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.edit_meeting(meeting_id=meeting_id, payload=payload, user=user, db=db)


@router.get("/api/v1/teams/{team_id}/meetings")
def rich_meetings(
    team_id: str,
    page: int = 1,
    pageSize: int = 20,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.rich_meetings(team_id=team_id, page=page, pageSize=pageSize, user=user, db=db)


@router.get("/api/v1/meetings/{meeting_id}")
def rich_meeting(
    meeting_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.rich_meeting(meeting_id=meeting_id, user=user, db=db)


@router.post("/api/v1/meetings/{meeting_id}/questions")
def add_meeting_question(
    meeting_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.add_meeting_question(meeting_id=meeting_id, payload=payload, user=user, db=db)


@router.patch("/api/v1/meeting-questions/{question_id}")
def answer_question(
    question_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.answer_question(question_id=question_id, payload=payload, user=user, db=db)
