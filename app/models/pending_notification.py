"""A queued notification awaiting the next digest flush (for digest-mode users)."""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import Field

from beanie import Document, Indexed


class PendingNotification(Document):
    recipient_id: Annotated[str, Indexed()]
    recipient_email: str
    recipient_name: str
    actor_name: str
    action: str
    card_id: str
    card_title: str
    team_name: str
    url: str
    # The comment text (sanitized HTML) when this event was a comment/@mention, so
    # the digest can show a snippet. None for card-change events (move/assign).
    message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "pending_notifications"
