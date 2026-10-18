"""Request validation contracts for teams."""

from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class TeamInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    planeWorkspaceSlug: str | None = Field(default=None, max_length=100)
    planeProjectId: str | None = Field(default=None, max_length=36)


class PlaneBinding(BaseModel):
    planeWorkspaceSlug: str = Field(min_length=1, max_length=100)
    planeProjectId: str = Field(min_length=36, max_length=36)
