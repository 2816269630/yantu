from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "yt_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(250))
    display_name: Mapped[str] = mapped_column(String(100))
    direction: Mapped[str] = mapped_column(String(255), default="")


class SessionToken(Base):
    __tablename__ = "yt_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginFailure(Base):
    __tablename__ = "yt_login_failures"
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class Route(Base):
    __tablename__ = "yt_routes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    # Snapshots are copied into personal tasks when a member enrolls.
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


class Meeting(Base):
    __tablename__ = "yt_meetings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str] = mapped_column(String(200))
    agenda: Mapped[str] = mapped_column(Text)
    minutes_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    minutes_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    minutes_author_id: Mapped[str | None] = mapped_column(ForeignKey("yt_users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", server_default="scheduled")


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
    enrollment_id: Mapped[str | None] = mapped_column(ForeignKey("yt_enrollments.id"), nullable=True)
    route_stage_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="todo")
    blocker: Mapped[str] = mapped_column(Text, default="")
    plane_work_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # An explicit state makes it clear if a remote sync still needs attention.
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


class Resource(Base):
    __tablename__ = "yt_resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
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


class Notification(Base):
    __tablename__ = "yt_notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    team_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class EntityData(Base):
    """Optional product metadata, kept separate from legacy extension tables."""
    __tablename__ = "yt_entity_data"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class SystemSetting(Base):
    __tablename__ = "yt_system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class RouteVersion(Base):
    __tablename__ = "yt_route_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    route_id: Mapped[str] = mapped_column(ForeignKey("yt_routes.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("route_id", "version"),)


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


class Bookmark(Base):
    __tablename__ = "yt_bookmarks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    experience_id: Mapped[str] = mapped_column(ForeignKey("yt_experiences.id"))
    __table_args__ = (UniqueConstraint("user_id", "experience_id"),)


class MeetingQuestion(Base):
    __tablename__ = "yt_meeting_questions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("yt_meetings.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    content: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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


class Handover(Base):
    __tablename__ = "yt_handovers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("yt_teams.id"), index=True)
    from_user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    to_user_id: Mapped[str] = mapped_column(ForeignKey("yt_users.id"))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    task_ids: Mapped[list] = mapped_column(JSON, default=list)
    resource_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
