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


class Route(Base):
    __tablename__ = "yt_routes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    stages: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Enrollment(Base):
    __tablename__ = "yt_enrollments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    route_id: Mapped[str] = mapped_column(ForeignKey("yt_routes.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    route_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    __table_args__ = (UniqueConstraint("route_id", "user_id"),)


class Experience(Base):
    __tablename__ = "yt_experiences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    title: Mapped[str] = mapped_column(String(100))
    starting_point: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class RouteVersion(Base):
    __tablename__ = "yt_route_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    route_id: Mapped[str] = mapped_column(ForeignKey("yt_routes.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("route_id", "version"),)


class Bookmark(Base):
    __tablename__ = "yt_bookmarks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    experience_id: Mapped[str] = mapped_column(ForeignKey("yt_experiences.id"))
    __table_args__ = (UniqueConstraint("user_id", "experience_id"),)
