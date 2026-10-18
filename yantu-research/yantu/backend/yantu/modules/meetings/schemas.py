"""Request validation contracts for meetings."""

from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class MeetingInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    startsAt: datetime
    location: str = Field(min_length=1, max_length=200)
    agenda: str = Field(min_length=1, max_length=20000)


class MinutesInput(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
