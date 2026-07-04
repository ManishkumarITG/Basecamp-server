"""Health check endpoint."""

from fastapi import APIRouter

from app.core.config import settings
from app.core.database import ping_database

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Report app status and a live database ping result."""
    db_ok = await ping_database()
    return {
        "status": "ok",
        "app": settings.app_name,
        "db": "up" if db_ok else "down",
    }
