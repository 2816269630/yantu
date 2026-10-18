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


class Meeting(Base):
    __tablename__ = "yt_meetings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str] = mapped_column(String(200))
    agenda: Mapped[str] = mapped_column(Text)
    minutes_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    minutes_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    minutes_author_id: Mapped[str | None] = mapped_column(ForeignKey("yt_users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", server_default="scheduled")


class MeetingQuestion(Base):
    __tablename__ = "yt_meeting_questions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("yt_meetings.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    content: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
