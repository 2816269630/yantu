"""Request validation contracts for auth."""

from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class ProfileChange(BaseModel):
    displayName: str = Field(min_length=1, max_length=100)
    direction: str = Field(default="", max_length=255)
