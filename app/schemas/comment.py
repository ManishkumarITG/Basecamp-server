"""Comment and card-timeline DTOs."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CommentPublic(BaseModel):
    id: str
    card_id: str
    team_id: str
    author_id: str
    author_name: str
    body_html: str
    reactions: dict[str, list[str]] = Field(default_factory=dict)
    edited: bool = False
    created_at: datetime


class CreateCommentRequest(BaseModel):
    body_html: str = Field(min_length=1, max_length=20000)
    mention_ids: list[str] = Field(default_factory=list)  # users @mentioned in the body


class EditCommentRequest(BaseModel):
    body_html: str = Field(min_length=1, max_length=20000)


class ReactRequest(BaseModel):
    emoji: str = Field(min_length=1, max_length=16)


class TimelineEvent(BaseModel):
    """A card move event in the timeline."""

    id: str
    actor_id: str
    actor_name: str
    to_column: str
    created_at: datetime


class TimelineItem(BaseModel):
    """A unified timeline entry: either a comment or a move event."""

    kind: Literal["comment", "event"]
    created_at: datetime
    comment: Optional[CommentPublic] = None
    event: Optional[TimelineEvent] = None


class CardTimeline(BaseModel):
    items: list[TimelineItem]
