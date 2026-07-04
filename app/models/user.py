"""User persistence model."""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import EmailStr, Field

from beanie import Document, Indexed

from app.models.enums import ClassRole


class User(Document):
    """A registered user stored in the ``users`` collection.

    Class membership is modeled as a single scalar (``class_id``, the class's
    public code). Because it is one field, a user can structurally belong to at
    most one class — the core "one class per user" rule is enforced by the schema
    itself, not just by application logic.
    """

    email: Annotated[EmailStr, Indexed(unique=True)]
    name: str
    hashed_password: str
    is_active: bool = True

    # Email verification + OTP (signup confirmation / password reset).
    # Defaults to True so pre-existing accounts (created before this field) keep
    # working; register() explicitly creates new users as unverified.
    is_verified: bool = True
    otp_code: Optional[str] = None
    otp_purpose: Optional[str] = None  # "signup" | "reset"
    otp_expires_at: Optional[datetime] = None

    # Notification preference: False = email on every event; True = periodic digest.
    digest_enabled: bool = False

    # Membership (None until the user makes or joins a class).
    class_id: Annotated[Optional[str], Indexed()] = None
    class_role: Optional[ClassRole] = None

    # Per-user favorites: ids of teams the user has starred.
    starred_team_ids: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "users"
