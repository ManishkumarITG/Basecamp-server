"""Doc / File entry within a team's Docs & Files tool."""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import Field

from beanie import Document, Indexed


class Doc(Document):
    class_id: str
    team_id: Annotated[str, Indexed()]
    title: str
    kind: str = "doc"  # "doc" | "file"
    url: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "docs"
