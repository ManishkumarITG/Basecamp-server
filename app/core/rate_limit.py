"""Tiny in-process sliding-window rate limiter.

Keyed by an arbitrary string (e.g. "verify:user@x.com"). Good enough for a single
uvicorn process; a multi-worker deploy would use Redis instead. Raises HTTP 429
when a key exceeds its allowance within the window.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from app.core.config import settings

_hits: dict[str, deque] = defaultdict(deque)


def hit(key: str, limit: int, window_seconds: int) -> None:
    """Record one attempt for ``key``; raise 429 if it exceeds ``limit``/window.

    No-op when rate limiting is disabled (RATE_LIMIT_ENABLED=false).
    """
    if not settings.rate_limit_enabled:
        return
    now = time.monotonic()
    cutoff = now - window_seconds
    bucket = _hits[key]
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_in = int(bucket[0] + window_seconds - now) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many attempts. Please try again in {retry_in} seconds.",
            headers={"Retry-After": str(retry_in)},
        )
    bucket.append(now)


def reset(key: str) -> None:
    """Clear a key's counter (e.g. after a successful verification)."""
    _hits.pop(key, None)
