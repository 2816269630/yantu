"""HTTP endpoints for learning."""

from __future__ import annotations
from fastapi import Body
from fastapi import Depends
from fastapi import Query
from sqlalchemy.orm import Session
from ...core.models import User
from ...modules.learning.schemas import ExperienceInput

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.get("/api/v1/teams/{team_id}/experiences")
def list_experiences(
    team_id: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.list_experiences(team_id=team_id, page=page, pageSize=pageSize, user=user, db=db)


@router.post("/api/v1/teams/{team_id}/experiences")
def create_experience(
    team_id: str,
    payload: ExperienceInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.create_experience(team_id=team_id, payload=payload, user=user, db=db)


@router.get("/api/v1/experiences/{experience_id}")
def get_experience(
    experience_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.get_experience(experience_id=experience_id, user=user, db=db)


@router.get("/api/v1/teams/{team_id}/routes")
def routes(
    team_id: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.routes(team_id=team_id, page=page, pageSize=pageSize, user=user, db=db)


@router.post("/api/v1/teams/{team_id}/routes")
def create_route(
    team_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.create_route(team_id=team_id, payload=payload, user=user, db=db)


@router.get("/api/v1/routes/{route_id}")
def get_route(route_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.get_route(route_id=route_id, user=user, db=db)


@router.patch("/api/v1/routes/{route_id}")
def edit_route(
    route_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.edit_route(route_id=route_id, payload=payload, user=user, db=db)


@router.get("/api/v1/routes/{route_id}/versions")
def route_versions(
    route_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.route_versions(route_id=route_id, user=user, db=db)


@router.delete("/api/v1/routes/{route_id}")
def archive_route(route_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.archive_route(route_id=route_id, user=user, db=db)


@router.post("/api/v1/routes/{route_id}/enrollments")
def enroll(
    route_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.enroll(route_id=route_id, user=user, db=db, services=services)


@router.get("/api/v1/me/enrollments")
def my_enrollments(teamId: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.my_enrollments(teamId=teamId, user=user, db=db)


@router.get("/api/v1/enrollments/{enrollment_id}")
def get_enrollment(
    enrollment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.get_enrollment(enrollment_id=enrollment_id, user=user, db=db)


@router.patch("/api/v1/enrollments/{enrollment_id}")
def edit_enrollment(
    enrollment_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.edit_enrollment(enrollment_id=enrollment_id, payload=payload, user=user, db=db)


@router.post("/api/v1/enrollments/{enrollment_id}/tasks")
def plan_task(
    enrollment_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.plan_task(
        enrollment_id=enrollment_id, payload=payload, user=user, db=db, services=services
    )


@router.patch("/api/v1/experiences/{experience_id}")
def edit_experience(
    experience_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.edit_experience(experience_id=experience_id, payload=payload, user=user, db=db)


@router.put("/api/v1/experiences/{experience_id}/bookmark")
def bookmark(experience_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.bookmark(experience_id=experience_id, user=user, db=db)


@router.delete("/api/v1/experiences/{experience_id}/bookmark")
def unbookmark(
    experience_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.unbookmark(experience_id=experience_id, user=user, db=db)


@router.get("/api/v1/me/bookmarks")
def bookmarks(teamId: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.bookmarks(teamId=teamId, user=user, db=db)
