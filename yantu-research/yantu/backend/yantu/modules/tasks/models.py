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


class Task(Base):
    __tablename__ = "yt_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    assignee_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    meeting_id: Mapped[str | None] = mapped_column(ForeignKey("yt_meetings.id"), nullable=True)
    enrollment_id: Mapped[str | None] = mapped_column(
        ForeignKey("yt_enrollments.id"), nullable=True
    )
    route_stage_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="todo")
    blocker: Mapped[str] = mapped_column(Text, default="")
    plane_work_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    plane_sync: Mapped[str] = mapped_column(String(20), default="pending")
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    latest_submission_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    route_stage_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Submission(Base):
    __tablename__ = "yt_submissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("yt_tasks.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    summary: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2048), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Review(Base):
    __tablename__ = "yt_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("yt_submissions.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    comment: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
