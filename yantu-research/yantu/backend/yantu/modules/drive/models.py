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


class DriveFolder(Base):
    __tablename__ = "yt_drive_folders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("yt_drive_folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("owner_id", "parent_id", "name"),)


class ResourceShare(Base):
    __tablename__ = "yt_resource_shares"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resource_id: Mapped[str] = mapped_column(ForeignKey("yt_resources.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"), index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("resource_id", "user_id", "team_id"),)


class ResourceReference(Base):
    __tablename__ = "yt_resource_references"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resource_id: Mapped[str] = mapped_column(ForeignKey("yt_resources.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("resource_id", "target_type", "target_id"),)


class UploadReceipt(Base):
    __tablename__ = "yt_upload_receipts"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Resource(Base):
    __tablename__ = "yt_resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("yt_teams.id"), index=True, nullable=True
    )
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("yt_drive_folders.id"), nullable=True, index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text, default="")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    meeting_id: Mapped[str | None] = mapped_column(ForeignKey("yt_meetings.id"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("yt_tasks.id"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(36), unique=True)
    size: Mapped[int] = mapped_column(Integer)
    visibility: Mapped[str] = mapped_column(String(20), default="team", server_default="team")
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class ResourceVersion(Base):
    __tablename__ = "yt_resource_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    resource_id: Mapped[str] = mapped_column(ForeignKey("yt_resources.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    file_name: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(36))
    size: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("resource_id", "version"),)
