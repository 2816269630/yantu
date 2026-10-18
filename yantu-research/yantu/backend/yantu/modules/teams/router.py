"""HTTP endpoints for teams."""

from __future__ import annotations
from fastapi import Body
from fastapi import Depends
from fastapi import Query
from fastapi import Request
from sqlalchemy.orm import Session
from ...core.models import User
from ...modules.teams.schemas import PlaneBinding, TeamInput

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.post("/api/v1/teams")
def create_team(
    payload: TeamInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.create_team(payload=payload, user=user, db=db, services=services)


@router.patch("/api/v1/teams/{team_id}/plane")
def bind_plane(
    team_id: str,
    payload: PlaneBinding,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.bind_plane(team_id=team_id, payload=payload, user=user, db=db, services=services)


@router.get("/api/v1/me/teams")
def my_teams(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.my_teams(user=user, db=db, services=services)


@router.get("/api/v1/teams/{team_id}")
def get_team(
    team_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.get_team(team_id=team_id, user=user, db=db, services=services)


@router.patch("/api/v1/teams/{team_id}")
def edit_team(
    team_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.edit_team(team_id=team_id, payload=payload, user=user, db=db, services=services)


@router.get("/api/v1/teams/{team_id}/members")
def members(
    team_id: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.members(team_id=team_id, page=page, pageSize=pageSize, user=user, db=db)


@router.patch("/api/v1/teams/{team_id}/members/{user_id}")
def edit_member(
    team_id: str,
    user_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.edit_member(team_id=team_id, user_id=user_id, payload=payload, user=user, db=db)


@router.delete("/api/v1/teams/{team_id}/members/{user_id}")
def remove_member(
    team_id: str, user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.remove_member(team_id=team_id, user_id=user_id, user=user, db=db)


@router.get("/api/v1/teams/{team_id}/invitations")
def invitations(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.invitations(team_id=team_id, user=user, db=db)


@router.post("/api/v1/teams/{team_id}/invitations")
def invite(
    team_id: str,
    request: Request,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.invite(team_id=team_id, request=request, payload=payload, user=user, db=db)


@router.post("/api/v1/invitations/{token}/accept")
def accept_invitation(
    token: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.accept_invitation(token=token, user=user, db=db)


@router.get("/api/v1/teams/{team_id}/export")
def export_team(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.export_team(team_id=team_id, user=user, db=db)


@router.get("/api/v1/plane/projects")
def plane_projects(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.plane_projects(user=user, db=db, services=services)
