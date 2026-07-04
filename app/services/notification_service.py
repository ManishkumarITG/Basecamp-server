"""Turns card activity into notifications for the card's subscribers / mentions.

A user becomes a subscriber by creating the card, being assigned to it,
commenting on it, being @mentioned, or opting in. When anyone else acts, every
other subscriber is notified (the actor never notifies themselves).

Each notification carries a **task summary** (status, assignees, due, notes) built
once per event, plus — for comments/@mentions — the **message** itself, so the
email is useful on its own.

Delivery respects each recipient's preference: instant email, or queued for the
periodic digest (see digest_service).
"""

import re

from beanie import PydanticObjectId

from app.core.board import COLUMN_LABELS
from app.core.config import settings
from app.models.pending_notification import PendingNotification
from app.models.user import User
from app.services import email_service


def card_url(card) -> str:
    base = settings.app_base_url.rstrip("/")
    return f"{base}/teams/{card.team_id}/cards/{card.id}"


async def _user(user_id: str):
    try:
        return await User.get(PydanticObjectId(user_id))
    except (ValueError, TypeError):
        return None


def _text_excerpt(html_str: str | None, limit: int = 180) -> str | None:
    """Plain-text excerpt from sanitized HTML (for the summary / digest snippet)."""
    if not html_str:
        return None
    text = re.sub(r"<[^>]+>", " ", html_str)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


async def _assignee_names(card) -> str:
    names = []
    for aid in card.assignee_ids:
        member = await _user(aid)
        if member is not None:
            names.append(member.name)
    return ", ".join(names) if names else "Unassigned"


async def _build_card_summary(card) -> dict:
    """A compact, presentation-ready snapshot of the card for the email body.

    Built once per event (not per recipient), since it's the same for everyone.
    """
    return {
        "status": COLUMN_LABELS.get(card.column, card.column),
        "assignees": await _assignee_names(card),
        "due": card.due_date if (card.due_type == "date" and card.due_date) else None,
        "notes": _text_excerpt(card.notes_html),
        "comments": card.comment_count,
    }


async def _deliver(
    recipient: User,
    actor_name: str,
    action: str,
    card,
    team_name: str,
    summary: dict,
    message_html: str | None = None,
) -> None:
    """Email now, or queue for the next digest, per the recipient's preference."""
    url = card_url(card)
    if recipient.digest_enabled:
        await PendingNotification(
            recipient_id=str(recipient.id),
            recipient_email=recipient.email,
            recipient_name=recipient.name,
            actor_name=actor_name,
            action=action,
            card_id=str(card.id),
            card_title=card.title,
            team_name=team_name,
            url=url,
            message=_text_excerpt(message_html, 200),
        ).insert()
    else:
        await email_service.send_card_notification(
            recipient.email,
            recipient.name,
            actor_name,
            action,
            card.title,
            team_name,
            url,
            summary=summary,
            message_html=message_html,
        )


async def notify_subscribers(
    card, actor, action: str, team_name: str, message_html: str | None = None
) -> None:
    """Notify every subscriber except the actor (e.g. action='commented on')."""
    summary = await _build_card_summary(card)
    actor_id = str(actor.id)
    for sid in card.subscriber_ids:
        if sid == actor_id:
            continue
        recipient = await _user(sid)
        if recipient is None or not recipient.email:
            continue
        await _deliver(recipient, actor.name, action, card, team_name, summary, message_html)


async def notify_assignment(card, actor, assignee_ids, team_name: str) -> None:
    """Notify people who were just assigned to the card."""
    summary = await _build_card_summary(card)
    actor_id = str(actor.id)
    for aid in assignee_ids:
        if aid == actor_id:
            continue
        recipient = await _user(aid)
        if recipient is None or not recipient.email:
            continue
        await _deliver(recipient, actor.name, "assigned you to", card, team_name, summary)


async def notify_mentions(
    card, actor, mention_ids, team_name: str, message_html: str | None = None
) -> None:
    """Notify people @mentioned in a comment (only class members are emailed)."""
    summary = await _build_card_summary(card)
    actor_id = str(actor.id)
    for mid in mention_ids:
        if mid == actor_id:
            continue
        recipient = await _user(mid)
        if recipient is None or recipient.class_id != actor.class_id or not recipient.email:
            continue
        await _deliver(
            recipient, actor.name, "mentioned you in a comment on", card, team_name, summary, message_html
        )
