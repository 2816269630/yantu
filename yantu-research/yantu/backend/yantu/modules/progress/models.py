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


class ProgressPost(Base):
    __tablename__ = "yt_progress_posts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    content: Mapped[str] = mapped_column(Text)
    blockers: Mapped[str] = mapped_column(Text, default="")
    next_plan: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20), default="progress")
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProgressComment(Base):
    __tablename__ = "yt_progress_comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    post_id: Mapped[str] = mapped_column(ForeignKey("yt_progress_posts.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
