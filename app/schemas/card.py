"""Card Table DTOs."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SubtaskDTO(BaseModel):
    id: str
    text: str
    done: bool = False


class CardPublic(BaseModel):
    id: str
    team_id: str
    title: str
    column: str
    created_by: str
    creator_name: str
    comment_count: int
    notes_html: str = ""
    assignee_ids: list[str] = Field(default_factory=list)
    subscriber_ids: list[str] = Field(default_factory=list)
    due_type: str = "none"
    due_date: Optional[str] = None
    subtasks: list[SubtaskDTO] = Field(default_factory=list)
    created_at: datetime


class BoardColumn(BaseModel):
    key: str
    label: str
    accent: str


class Board(BaseModel):
    """Everything the Card Table needs: the column set and all cards."""

    columns: list[BoardColumn]
    cards: list[CardPublic]


class CreateCardRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    column: Optional[str] = None  # defaults to the first column server-side


class UpdateCardRequest(BaseModel):
    """Move/rename/edit a card. All fields optional; only provided ones change."""

    column: Optional[str] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    notes_html: Optional[str] = None
    assignee_ids: Optional[list[str]] = None
    due_type: Optional[Literal["none", "date"]] = None
    due_date: Optional[str] = None
    subtasks: Optional[list[SubtaskDTO]] = None
