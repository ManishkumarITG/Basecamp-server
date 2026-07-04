"""To-do DTOs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TodoPublic(BaseModel):
    id: str
    team_id: str
    title: str
    done: bool
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    created_at: datetime


class CreateTodoRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    assignee_id: Optional[str] = None


class UpdateTodoRequest(BaseModel):
    done: Optional[bool] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    assignee_id: Optional[str] = None
