"""HTTP endpoints for tasks."""

from __future__ import annotations
from fastapi import Body
from fastapi import Depends
from fastapi import Query
from sqlalchemy.orm import Session
from ...core.models import User

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.get("/api/v1/teams/{team_id}/review-queue")
def review_queue(team_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.team_review_queue(team_id=team_id, user=user, db=db)


@router.get("/api/v1/teams/{team_id}/plane-work-items")
def plane_tasks(
    team_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.plane_tasks(team_id=team_id, user=user, db=db, services=services)


@router.post("/api/v1/teams/{team_id}/tasks")
def create_task(
    team_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.create_task(
        team_id=team_id, payload=payload, user=user, db=db, services=services
    )


@router.get("/api/v1/me/tasks")
def my_tasks(
    teamId: str,
    status: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.my_tasks(
        teamId=teamId, status=status, page=page, pageSize=pageSize, user=user, db=db
    )


@router.get("/api/v1/teams/{team_id}/tasks")
def team_tasks(
    team_id: str,
    status: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.team_tasks(
        team_id=team_id, status=status, page=page, pageSize=pageSize, user=user, db=db
    )


@router.get("/api/v1/me/review-queue")
def review_queue(
    teamId: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.review_queue(teamId=teamId, page=page, pageSize=pageSize, user=user, db=db)


@router.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.get_task(task_id=task_id, user=user, db=db)


@router.patch("/api/v1/tasks/{task_id}")
def edit_task(
    task_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.edit_task(task_id=task_id, payload=payload, user=user, db=db, services=services)


@router.post("/api/v1/tasks/{task_id}/submissions")
def submit_task(
    task_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.submit_task(
        task_id=task_id, payload=payload, user=user, db=db, services=services
    )


@router.post("/api/v1/submissions/{submission_id}/reviews")
def review_submission(
    submission_id: str,
    payload: dict = Body(),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    *,
    services: ServiceContext = Depends(get_services),
):
    return service.review_submission(
        submission_id=submission_id, payload=payload, user=user, db=db, services=services
    )
