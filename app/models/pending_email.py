"""An outbound email persisted in the durable outbox.

Any email that can't be delivered inline (e.g. Gmail SMTP had a transient
failure) is stored here so a background worker can retry it until it sends —
nothing is silently dropped, and the queue survives a restart. See
``email_service.process_outbox`` / ``run_outbox_loop``.
"""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import Field

from beanie import Document, Indexed


class PendingEmail(Document):
    to: str
    subject: str
    html: str
    text: str
    kind: str  # "otp" | "notification" | "digest"

    status: Annotated[str, Indexed()] = "pending"  # pending | sent | failed
    attempts: int = 0
    last_error: str | None = None
    # When the worker may next try this row (None = due immediately).
    next_attempt_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "pending_emails"
