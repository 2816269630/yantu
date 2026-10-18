"""HTTP endpoints for notifications."""

from __future__ import annotations
from fastapi import Depends
from fastapi import Query
from sqlalchemy.orm import Session
from ...core.models import User
from ...modules.notifications.schemas import ReadInput

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.get("/api/v1/me/notifications")
def notifications(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.notifications(page=page, pageSize=pageSize, user=user, db=db)


@router.patch("/api/v1/me/notifications/{notification_id}")
def read_notification(
    notification_id: str,
    payload: ReadInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.read_notification(
        notification_id=notification_id, payload=payload, user=user, db=db
    )


@router.post("/api/v1/me/notifications/read-all")
def read_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.read_all(user=user, db=db)
