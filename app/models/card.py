"""Card Table card — a unit of work that moves through board columns."""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import BaseModel, Field

from beanie import Document, Indexed

from app.core.board import DEFAULT_COLUMN


class Subtask(BaseModel):
    """An embedded checklist item on a card."""

    id: str
    text: str
    done: bool = False


class Card(Document):
    """A card on a team's Card Table. ``column`` is one of the board column keys."""

    class_id: str
    team_id: Annotated[str, Indexed()]
    title: str
    column: str = DEFAULT_COLUMN
    created_by: str  # str(User.id)
    creator_name: str = ""  # denormalized for fast board rendering
    comment_count: int = 0

    # Detail fields
    notes_html: str = ""
    assignee_ids: list[str] = Field(default_factory=list)
    subscriber_ids: list[str] = Field(default_factory=list)  # who gets notified
    due_type: str = "none"  # "none" | "date"
    due_date: Optional[str] = None  # ISO date string when due_type == "date"
    subtasks: list[Subtask] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "cards"
