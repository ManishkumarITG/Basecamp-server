"""Team request/response DTOs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import TeamRole


class TeamPublic(BaseModel):
    """A team exposed over the API. ``starred`` is per requesting-user."""

    id: str
    class_id: str
    name: str
    description: str
    admin_ids: list[str]
    member_ids: list[str]
    member_count: int
    starred: bool = False
    created_at: datetime


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class UpdateTeamRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)


class AddTeamMemberRequest(BaseModel):
    user_id: str
    role: TeamRole = TeamRole.MEMBER
