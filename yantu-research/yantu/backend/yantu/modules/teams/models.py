from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from ...core.database import Base, new_id, utcnow


class Team(Base):
    __tablename__ = "yt_teams"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    plane_workspace_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plane_project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Member(Base):
    __tablename__ = "yt_team_members"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("team_id", "user_id"),
        CheckConstraint("role IN ('student', 'mentor', 'owner')"),
    )


class Invitation(Base):
    __tablename__ = "yt_invitations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
