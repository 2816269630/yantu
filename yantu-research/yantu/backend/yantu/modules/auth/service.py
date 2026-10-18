"""modules.auth.service business operations."""

from __future__ import annotations
from fastapi import HTTPException
from fastapi import Request
from fastapi import Response
from sqlalchemy.orm import Session
from sqlalchemy import delete
from sqlalchemy import func
import os
from sqlalchemy import select
from datetime import timedelta
from sqlalchemy import update
from ...core.models import (
    Invitation,
    LoginFailure,
    Member,
    SessionToken,
    SystemSetting,
    Team,
    User,
    utcnow,
)
from ...modules.auth.schemas import ProfileChange
from ...core.security import check_password, hash_password, new_token, token_digest


def me(user: User = None):
    return {
        "data": {
            "id": user.id,
            "email": user.email,
            "displayName": user.display_name,
            "direction": user.direction,
        }
    }


def edit_me(payload: ProfileChange, user: User = None, db: Session = None):
    user.display_name = payload.displayName.strip()
    user.direction = payload.direction.strip()
    db.commit()
    return {
        "data": {
            "id": user.id,
            "email": user.email,
            "displayName": user.display_name,
            "direction": user.direction,
        }
    }


def bind_session(db, user, response, request):
    from ...core.presentation import actor

    token = new_token()
    db.add(
        SessionToken(
            token_hash=token_digest(token), user_id=user.id, expires_at=utcnow() + timedelta(days=7)
        )
    )
    db.commit()
    response.set_cookie(
        "yantu_session",
        token,
        max_age=7 * 86400,
        httponly=True,
        secure=request.url.scheme == "https" or os.getenv("COOKIE_SECURE") == "1",
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"accessToken": token, "user": actor(user)}


def request_token(request):
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.startswith("Bearer ") else request.cookies.get("yantu_session", "")


def system_status(db: Session = None):
    return {
        "data": {
            "initialized": bool(db.scalar(select(func.count()).select_from(User))),
            "registrationOpen": os.getenv("ALLOW_PUBLIC_SIGNUP", "0") == "1",
            "planeConfigured": bool(os.getenv("PLANE_API_KEY")),
            "assistantConfigured": bool(os.getenv("AI_BASE_URL") and os.getenv("AI_MODEL")),
        }
    }


def validate_identity(payload):
    from ...core.validation import text_value

    email = text_value(payload, "email", maximum=254, required=True).lower()
    password = text_value(payload, "password", maximum=1024, required=True)
    display_name = text_value(payload, "displayName", maximum=100, required=True)
    if "@" not in email or email.startswith("@") or email.endswith("@") or (len(password) < 12):
        raise HTTPException(400, "请输入有效邮箱及至少 12 位的密码")
    return (email, password, display_name)


def setup(request: Request, response: Response, payload: dict = None, db: Session = None):
    from ...core.presentation import iso
    from ...core.validation import text_value

    email, password, display_name = validate_identity(payload)
    team_name = text_value(payload, "teamName", maximum=100, required=True)
    if db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(409, "系统已初始化，请直接登录")
    db.add(SystemSetting(key="initialized", value=iso(utcnow())))
    db.flush()
    user = User(email=email, display_name=display_name, password_hash=hash_password(password))
    team = Team(name=team_name)
    db.add_all([user, team])
    db.flush()
    db.add(Member(team_id=team.id, user_id=user.id, role="owner"))
    result = bind_session(db, user, response, request)
    return {"data": {**result, "teamId": team.id}}


def invite_record(db, token, email):
    from ...core.presentation import iso
    from ...core.validation import timestamp

    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(token)))
    if (
        invitation is None
        or invitation.accepted_at is not None
        or timestamp(iso(invitation.expires_at)) <= utcnow()
        or (invitation.email != email)
    ):
        raise HTTPException(403, "邀请与邮箱不匹配、已使用或已过期")
    return invitation


def claim_invitation(db, invitation):
    result = db.execute(
        update(Invitation)
        .where(
            Invitation.id == invitation.id,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > utcnow(),
        )
        .values(accepted_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise HTTPException(409, "邀请已被使用，请刷新")


def register(payload: dict = None, db: Session = None):
    email, password, display_name = validate_identity(payload)
    invitation = (
        invite_record(db, str(payload["invitationToken"]), email)
        if payload.get("invitationToken")
        else None
    )
    if not invitation and os.getenv("ALLOW_PUBLIC_SIGNUP", "0") != "1":
        raise HTTPException(403, "请先取得课题组邀请")
    if invitation:
        claim_invitation(db, invitation)
    user = User(email=email, display_name=display_name, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    if invitation:
        db.add(Member(team_id=invitation.team_id, user_id=user.id, role=invitation.role))
    db.commit()
    return {"data": {"id": user.id}}


def login(request: Request, response: Response, payload: dict = None, db: Session = None):
    from ...core.presentation import iso
    from ...core.validation import text_value
    from ...core.validation import timestamp

    email = text_value(payload, "email", maximum=254, required=True).lower()
    password = text_value(payload, "password", maximum=1024, required=True)
    failure = db.get(LoginFailure, email)
    if failure and failure.locked_until and (timestamp(iso(failure.locked_until)) > utcnow()):
        raise HTTPException(429, "登录尝试过多，请稍后再试")
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not check_password(password, user.password_hash):
        if failure is None:
            failure = LoginFailure(email=email, count=0)
            db.add(failure)
        if failure.locked_until:
            failure.count = 0
            failure.locked_until = None
        failure.count += 1
        if failure.count >= 5:
            failure.locked_until = utcnow() + timedelta(minutes=15)
        db.commit()
        raise HTTPException(401, "邮箱或密码错误")
    if failure:
        db.delete(failure)
    return {"data": bind_session(db, user, response, request)}


def logout(request: Request, response: Response, db: Session = None):
    db.execute(
        delete(SessionToken).where(SessionToken.token_hash == token_digest(request_token(request)))
    )
    db.commit()
    response.delete_cookie("yantu_session", path="/")
    return {"data": None}


def refresh(request: Request, response: Response, user: User = None, db: Session = None):
    result = db.execute(
        delete(SessionToken).where(SessionToken.token_hash == token_digest(request_token(request)))
    )
    if result.rowcount != 1:
        raise HTTPException(401, "会话已失效")
    return {"data": bind_session(db, user, response, request)}
