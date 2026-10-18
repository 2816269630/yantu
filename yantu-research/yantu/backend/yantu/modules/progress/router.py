"""HTTP endpoints for progress."""

from __future__ import annotations
from fastapi import Body
from fastapi import Depends
from sqlalchemy.orm import Session
from ...core.models import User

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.get("/api/v1/teams/{team_id}/progress")
def progress(
    team_id: str,
    page: int = 1,
    pageSize: int = 100,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.progress(team_id=team_id, page=page, pageSize=pageSize, user=user, db=db)


@router.post("/api/v1/teams/{team_id}/progress")
def add_progress(
    team_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.add_progress(team_id=team_id, payload=payload, user=user, db=db)


@router.post("/api/v1/progress/{post_id}/comments")
def add_progress_comment(
    post_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.add_progress_comment(post_id=post_id, payload=payload, user=user, db=db)


@router.patch("/api/v1/progress/{post_id}")
def resolve_progress(
    post_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.resolve_progress(post_id=post_id, payload=payload, user=user, db=db)
