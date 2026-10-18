"""Request-scoped database, identity and integration dependencies."""

from dataclasses import dataclass
from pathlib import Path
from datetime import timezone
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from .models import SessionToken, User, utcnow
from .security import token_digest
from ..integrations.plane import PlaneClient
from ..integrations.ollama import OllamaResearchAssistant


@dataclass(frozen=True)
class ServiceContext:
    plane: PlaneClient
    uploads: Path
    assistant: OllamaResearchAssistant


def get_services(request: Request) -> ServiceContext:
    return request.app.state.services


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        yield db


def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    raw_token = (
        authorization[7:]
        if authorization and authorization.startswith("Bearer ")
        else request.cookies.get("yantu_session")
    )
    if not raw_token:
        raise HTTPException(401, "请先登录")
    session = db.get(SessionToken, token_digest(raw_token))
    if (
        session is None
        or not session.expires_at
        or session.expires_at.replace(tzinfo=timezone.utc) < utcnow()
    ):
        raise HTTPException(401, "登录已过期，请重新登录")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "用户不存在")
    return user
