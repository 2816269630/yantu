"""HTTP endpoints for handovers."""

from __future__ import annotations
from fastapi import Body
from fastapi import Depends
from sqlalchemy.orm import Session
from ...core.models import User

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.get("/api/v1/teams/{team_id}/handovers")
def list_handovers(
    team_id: str,
    page: int = 1,
    pageSize: int = 100,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.list_handovers(team_id=team_id, page=page, pageSize=pageSize, user=user, db=db)


@router.post("/api/v1/teams/{team_id}/handovers")
def create_handover(
    team_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.create_handover(team_id=team_id, payload=payload, user=user, db=db)


@router.post("/api/v1/handovers/{handover_id}/accept")
def accept_handover(
    handover_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.accept_handover(handover_id=handover_id, user=user, db=db)
