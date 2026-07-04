"""FastAPI application factory and entry point.

Run locally with::

    uvicorn app.main:app --reload   # from inside basecamp-server/

================================================================================
HOW THE BACKEND FITS TOGETHER (start here)
================================================================================

Strict layering, top to bottom. Each layer only talks to the one below it:

    HTTP / WebSocket  ->  routes  ->  services  ->  models (Beanie)  ->  MongoDB
                            (thin)     (logic)       (persistence)

  * routes/   (app/api/v1/routes/*)  -- thin. Parse the request DTO, call ONE
                service function, return a response DTO. No business logic here.
                The only extra thing routes do is transport concerns the service
                shouldn't know about: e.g. broadcasting a live WebSocket event
                AFTER the service has done the write (see cards.py / comments.py).
  * services/ (app/services/*)       -- all business logic + rules + side effects
                (emails, notifications, activity). Services never return a Beanie
                document; they map it to a Pydantic DTO from schemas/ first.
  * models/   (app/models/*)         -- Beanie Documents = the MongoDB collections.
                Registered in models/__init__.py as `document_models` so Beanie
                knows about them at startup.
  * schemas/  (app/schemas/*)        -- Pydantic request/response DTOs (the shapes
                that cross the HTTP boundary). Models stay internal.

Cross-cutting helpers:
  * core/config.py    -- Settings (env vars), cached singleton `settings`.
  * core/database.py  -- Motor client + init_beanie; connect/close + health ping.
  * core/security.py  -- bcrypt password hashing + JWT create/decode.
  * api/deps.py       -- get_current_user: the auth dependency every protected
                         route depends on.
  * utils/            -- codes (Class IDs / OTPs), HTML sanitizing.

--------------------------------------------------------------------------------
LIFECYCLE OF A NORMAL HTTP REQUEST  (e.g. GET /api/v1/teams)
--------------------------------------------------------------------------------
  1. Uvicorn hands the request to this `app` (built by create_app below).
  2. CORS middleware checks the Origin against CORS_ORIGINS.
  3. api_router (api/v1/router.py) matches the path to a route handler.
  4. For a protected route, `Depends(get_current_user)` runs FIRST: it pulls the
     Bearer token, decodes the JWT (core/security), loads the User (auth_service).
     A bad/expired token -> 401 before the handler body ever runs.
  5. The handler validates the body into a request DTO, then calls its service.
  6. The service applies rules, reads/writes Beanie documents, and maps the
     result to a response DTO (schemas/).
  7. FastAPI serializes that DTO to JSON. JSON keys are snake_case.

--------------------------------------------------------------------------------
AUTH & ONBOARDING (the entry path)
--------------------------------------------------------------------------------
  register -> account created UNVERIFIED + 6-digit OTP emailed
  verify-email -> OTP checked, user marked verified, JWT returned (logged in)
  login -> credentials checked (must be verified) -> JWT returned
  Then onboarding: make a class (become super_admin) OR join one (become member).
  The "one class per user" rule is structural: membership is the single scalar
  User.class_id, and class_service raises 409 if a user already has a class.
  (Full auth logic: services/auth_service.py.)

--------------------------------------------------------------------------------
BACKGROUND & REALTIME (not request/response)
--------------------------------------------------------------------------------
  * Digest loop: started here in `lifespan` as an asyncio task. Every
    DIGEST_INTERVAL_MINUTES it calls digest_service.flush_digests(), which batches
    each recipient's queued PendingNotification rows into ONE summary email.
  * WebSockets: clients connect to /ws/teams/{team_id} (ws.py) and only LISTEN.
    The server pushes events; after a card/comment write, the ROUTE calls
    manager.broadcast(team_id, ...) so every connected client refetches live.
    The hub (ws/manager.py) is in-memory -> single-process only.

--------------------------------------------------------------------------------
WORKED EXAMPLE -- "Maria comments on a card"
--------------------------------------------------------------------------------
  POST /api/v1/cards/{id}/comments
   -> get_current_user resolves Maria from her JWT
   -> comment_service.create_comment:
        sanitizes the HTML, inserts the Comment,
        subscribes Maria (and any @mentioned members) to the card,
        records an Activity row (feeds the activity timeline),
        notifies @mentioned users ("mentioned you") then the other
        subscribers ("commented on") -- minus the actor and minus anyone
        already mentioned (no double-emails).
   -> notification_service._deliver picks, PER RECIPIENT: send an email NOW, or
        queue a PendingNotification for the next digest (recipient.digest_enabled).
   -> back in the route: manager.broadcast(team_id, {"type": "comment.created"...})
        so everyone viewing that team's board updates instantly.

The detail for any step lives in that module's own docstring. This map is just
the thread that ties them together.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_database_connection, connect_to_database
from app.services import digest_service, email_service

# Give our own "basecamp" logger a visible handler. By default Python only prints
# WARNING+ (the "last resort" handler), so [email] sent / queued / outbox INFO
# lines were invisible while [email] FAILED warnings showed — which made it look
# like "logs appear but nothing sends". Scoped to "basecamp" so uvicorn's own
# logging is untouched.
_basecamp_logger = logging.getLogger("basecamp")
if not _basecamp_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _basecamp_logger.addHandler(_handler)
    _basecamp_logger.setLevel(logging.INFO)
    _basecamp_logger.propagate = False
logger = _basecamp_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the DB connection + start the background loops on startup; clean up on shutdown.

    Two background tasks run for the life of the app: the digest flusher and the
    email outbox worker (retries any email that couldn't be sent inline).
    """
    await connect_to_database()
    # Surface the active email transport once so a missing/blank provider config
    # (dev-log instead of real send) is obvious in the logs.
    logger.info("[startup] email mode: %s", email_service.describe_transport())
    if email_service.resend_from_unset():
        logger.warning(
            "[startup] EMAIL_PROVIDER=resend but EMAIL_FROM is unset — sends will be "
            "rejected by Resend (the default From domain isn't verified). Set "
            "EMAIL_FROM to a Resend-verified address, e.g. 'Basecamp <noreply@itgeeks.com>'."
        )
    digest_task = asyncio.create_task(digest_service.run_loop())
    outbox_task = asyncio.create_task(email_service.run_outbox_loop())
    try:
        yield
    finally:
        digest_task.cancel()
        outbox_task.cancel()
        await close_database_connection()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
