"""HTTP endpoints for assistant."""

from __future__ import annotations
from fastapi import Body
from fastapi import Depends
from sqlalchemy.orm import Session
from ...core.models import User

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.post("/api/v1/me/drive/questions")
@router.post("/api/v1/teams/{team_id}/questions")
def questions(
    payload: dict = Body(),
    team_id: str = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.questions(payload=payload, team_id=team_id, user=user, db=db, services=services)
