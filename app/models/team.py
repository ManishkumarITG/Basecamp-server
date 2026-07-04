"""Team persistence model — a group inside a Class with admins and members."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import Field

from beanie import Document, Indexed


class Team(Document):
    """A team belonging to a Class (referenced by the class's public code)."""

    class_id: Annotated[str, Indexed()]
    name: str
    description: str = ""
    admin_ids: list[str] = Field(default_factory=list)  # str(User.id)
    member_ids: list[str] = Field(default_factory=list)  # str(User.id)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "teams"
