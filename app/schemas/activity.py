"""Activity feed DTOs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ActivityPublic(BaseModel):
    id: str
    actor_id: str
    actor_name: str
    verb: str
    target_type: Optional[str] = None
    target_title: Optional[str] = None
    target_id: Optional[str] = None
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    created_at: datetime


class ActiveUser(BaseModel):
    id: str
    name: str
    email: str


class ActivityFeed(BaseModel):
    """A scope's recent activity plus who's been active in the window."""

    items: list[ActivityPublic]
    active_users: list[ActiveUser]
    active_window_label: str
