"""User-facing DTOs. Documents are never returned directly from the API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.models.enums import ClassRole


class UserPublic(BaseModel):
    """User fields that are safe to expose over the API."""

    id: str
    email: EmailStr
    name: str
    is_active: bool
    class_id: Optional[str] = None
    class_role: Optional[ClassRole] = None
    digest_enabled: bool = False
    created_at: datetime
