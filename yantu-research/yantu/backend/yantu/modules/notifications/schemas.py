"""Request validation contracts for notifications."""

from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class ReadInput(BaseModel):
    read: bool
