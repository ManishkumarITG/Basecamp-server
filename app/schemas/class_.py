"""Class request/response DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.team import TeamPublic
from app.schemas.user import UserPublic


class MakeClassRequest(BaseModel):
    """Payload for creating a new class."""

    name: str = Field(min_length=1, max_length=120)


class JoinClassRequest(BaseModel):
    """Payload for joining an existing class."""

    class_id: str = Field(min_length=1)
    invitation_code: str = Field(min_length=1)


class ClassPublic(BaseModel):
    """A class exposed over the API."""

    id: str
    name: str
    class_id: str
    invitation_code: str
    super_admin_id: str
    created_at: datetime


class ClassOverview(BaseModel):
    """A class together with its members and teams (the dashboard payload)."""

    # ``class`` is a reserved word, so the field is ``class_`` with a JSON alias.
    model_config = ConfigDict(populate_by_name=True)

    class_: ClassPublic = Field(alias="class")
    members: list[UserPublic]
    teams: list[TeamPublic]
