"""HTTP endpoints for dashboard."""

from __future__ import annotations
from fastapi import Depends
from fastapi import Query
from sqlalchemy.orm import Session
from ...core.models import User

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.get("/healthz")
def health():
    return service.health()


@router.get("/api/v1/teams/{team_id}/search")
def search(
    team_id: str,
    q: str = Query(min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.search(team_id=team_id, q=q, page=page, pageSize=pageSize, user=user, db=db)


@router.get("/api/v1/me/dashboard")
def drive_dashboard(teamId: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.drive_dashboard(teamId=teamId, user=user, db=db)
