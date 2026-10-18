"""HTTP endpoints for auth."""

from __future__ import annotations
from fastapi import Body
from fastapi import Depends
from fastapi import Request
from fastapi import Response
from sqlalchemy.orm import Session
from ...core.models import User
from ...modules.auth.schemas import ProfileChange

from fastapi import APIRouter
from ...core.dependencies import current_user, get_db, get_services, ServiceContext
from . import service

router = APIRouter()


@router.get("/api/v1/me")
def me(user: User = Depends(current_user)):
    return service.me(user=user)


@router.patch("/api/v1/me")
def edit_me(
    payload: ProfileChange, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return service.edit_me(payload=payload, user=user, db=db)


@router.get("/api/v1/system/status")
def system_status(db: Session = Depends(get_db)):
    return service.system_status(db=db)


@router.post("/api/v1/auth/setup")
def setup(
    request: Request, response: Response, payload: dict = Body(), db: Session = Depends(get_db)
):
    return service.setup(request=request, response=response, payload=payload, db=db)


@router.post("/api/v1/auth/register")
def register(payload: dict = Body(), db: Session = Depends(get_db)):
    return service.register(payload=payload, db=db)


@router.post("/api/v1/auth/login")
def login(
    request: Request, response: Response, payload: dict = Body(), db: Session = Depends(get_db)
):
    return service.login(request=request, response=response, payload=payload, db=db)


@router.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    return service.logout(request=request, response=response, db=db)


@router.post("/api/v1/auth/refresh")
def refresh(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return service.refresh(request=request, response=response, user=user, db=db)
