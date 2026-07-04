"""Docs & Files DTOs."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DocPublic(BaseModel):
    id: str
    team_id: str
    title: str
    kind: str
    url: Optional[str] = None
    created_at: datetime


class CreateDocRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["doc", "file"] = "doc"
    url: Optional[str] = None
