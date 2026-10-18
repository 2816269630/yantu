"""Request validation contracts for learning."""

from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class ExperienceInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    startingPoint: str = Field(min_length=1, max_length=3000)
    content: str = Field(min_length=1, max_length=50000)
