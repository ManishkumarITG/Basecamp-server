"""To-do — a simple checklist task within a team."""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import Field

from beanie import Document, Indexed


class Todo(Document):
    class_id: str
    team_id: Annotated[str, Indexed()]
    title: str
    done: bool = False
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None  # denormalized
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "todos"
