"""MongoDB connection lifecycle and Beanie initialization.

The Motor client is created on app startup and closed on shutdown (wired via the
FastAPI lifespan handler in ``app.main``). Beanie is initialized with the project
document models so they are ready to use across the app.
"""

from motor.motor_asyncio import AsyncIOMotorClient

from beanie import init_beanie

from app.core.config import settings
from app.models import document_models


class _Database:
    """Holds the single shared Motor client for the process."""

    client: AsyncIOMotorClient | None = None


db = _Database()


async def connect_to_database() -> None:
    """Open the Mongo connection and initialize Beanie with all models."""
    db.client = AsyncIOMotorClient(settings.mongodb_uri)
    await init_beanie(
        database=db.client[settings.db_name],
        document_models=document_models,
    )


async def close_database_connection() -> None:
    """Close the Mongo connection if it is open."""
    if db.client is not None:
        db.client.close()
        db.client = None


async def ping_database() -> bool:
    """Return True if the database responds to a ``ping`` command."""
    if db.client is None:
        return False
    try:
        await db.client.admin.command("ping")
        return True
    except Exception:  # noqa: BLE001 - any failure means the DB is unreachable
        return False
