"""A comment on a card. Body is sanitized rich HTML; reactions are emoji -> user ids."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import Field

from beanie import Document, Indexed


class Comment(Document):
    card_id: Annotated[str, Indexed()]
    class_id: str
    team_id: str
    author_id: str
    author_name: str  # denormalized for fast thread rendering
    body_html: str
    reactions: dict[str, list[str]] = Field(default_factory=dict)  # emoji -> [user_id]
    edited: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "comments"
