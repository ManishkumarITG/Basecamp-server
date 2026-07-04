"""Activity feed entry. Recorded on meaningful actions (card added, comment, etc.).

Actor and target details are denormalized so the feed renders without extra
lookups (the feed is read far more often than it is written).
"""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import Field

from beanie import Document, Indexed


class Activity(Document):
    class_id: Annotated[str, Indexed()]
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    actor_id: str
    actor_name: str
    verb: str  # e.g. "added a card", "commented on", "moved this card to"
    target_type: Optional[str] = None  # "card" | "doc" | "todo" | "team"
    target_title: Optional[str] = None
    target_id: Optional[str] = None
    to_column: Optional[str] = None  # set for "moved this card to" events (column key)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "activities"
