"""Class persistence model — the top-level organization entity.

Module is named ``class_`` because ``class`` is a Python keyword.
"""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import Field

from beanie import Document, Indexed


class Class(Document):
    """A Class (organization). Created and owned by a Super Admin.

    ``class_id`` is the public, human-shareable identifier users type when
    joining — distinct from the internal Mongo ``_id``.
    """

    name: str
    class_id: Annotated[str, Indexed(unique=True)]
    invitation_code: str
    super_admin_id: str  # str(User.id) of the owner
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "classes"
