"""Explicit metadata registry: imports register all domain tables."""

from .database import Base, new_id, utcnow
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from ..modules.auth.models import User, SessionToken, LoginFailure, SystemSetting
from ..modules.teams.models import Team, Member, Invitation
from ..modules.learning.models import Route, Enrollment, Experience, RouteVersion, Bookmark
from ..modules.tasks.models import Task, Submission, Review
from ..modules.meetings.models import Meeting, MeetingQuestion
from ..modules.drive.models import (
    DriveFolder,
    ResourceShare,
    ResourceReference,
    UploadReceipt,
    Resource,
    ResourceVersion,
)
from ..modules.notifications.models import Notification
from ..modules.progress.models import ProgressPost, ProgressComment
from ..modules.handovers.models import Handover


class EntityData(Base):
    """Optional product metadata, kept separate from legacy extension tables."""

    __tablename__ = "yt_entity_data"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
