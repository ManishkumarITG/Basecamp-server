"""Periodic digest: batches queued notifications into one email per recipient.

A background task (started in the app lifespan) calls ``flush_digests`` every
``DIGEST_INTERVAL_MINUTES``. Users with ``digest_enabled`` accumulate
PendingNotification rows instead of getting one email per event.
"""

import asyncio
import logging

from app.core.config import settings
from app.models.pending_notification import PendingNotification
from app.services import email_service

logger = logging.getLogger("basecamp.digest")


async def flush_digests() -> int:
    """Send one summary email per recipient and clear the queue. Returns count sent."""
    pending = await PendingNotification.find_all().sort("created_at").to_list()
    if not pending:
        return 0

    grouped: dict[str, list[PendingNotification]] = {}
    for item in pending:
        grouped.setdefault(item.recipient_id, []).append(item)

    for items in grouped.values():
        first = items[0]
        await email_service.send_digest_email(
            first.recipient_email,
            first.recipient_name,
            [
                {
                    "actor_name": i.actor_name,
                    "action": i.action,
                    "card_title": i.card_title,
                    "team_name": i.team_name,
                    "url": i.url,
                    "message": i.message,
                }
                for i in items
            ],
        )

    for item in pending:
        await item.delete()
    return len(pending)


async def run_loop() -> None:
    """Background loop: flush the digest queue on an interval until cancelled."""
    interval = max(60, settings.digest_interval_minutes * 60)
    while True:
        try:
            await asyncio.sleep(interval)
            sent = await flush_digests()
            if sent:
                logger.info("[digest] flushed %s notifications", sent)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("[digest] flush failed: %s", exc)
