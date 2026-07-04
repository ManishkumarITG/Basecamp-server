"""Beanie document models (the persistence layer).

``document_models`` is the canonical list passed to ``init_beanie``. Register any
new Document here so it is initialized on startup.
"""

from app.models.activity import Activity
from app.models.card import Card
from app.models.class_ import Class
from app.models.comment import Comment
from app.models.doc import Doc
from app.models.pending_email import PendingEmail
from app.models.pending_notification import PendingNotification
from app.models.team import Team
from app.models.todo import Todo
from app.models.user import User

document_models = [
    User, Class, Team, Card, Todo, Doc, Activity, Comment, PendingNotification, PendingEmail
]

__all__ = [
    "User", "Class", "Team", "Card", "Todo", "Doc", "Activity", "Comment",
    "PendingNotification", "PendingEmail", "document_models",
]
