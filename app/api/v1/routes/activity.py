"""Activity feed routes (class-wide and team-scoped)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.activity import ActivityFeed
from app.services import activity_service, team_service

router = APIRouter(tags=["activity"])


@router.get("/activity", response_model=ActivityFeed)
async def class_activity(
    limit: int = 20, current_user: User = Depends(get_current_user)
) -> ActivityFeed:
    """Recent activity across the whole class (Home feed). Active = last 24h."""
    return await activity_service.get_feed(
        class_id=current_user.class_id,
        limit=limit,
        window_hours=24,
        window_label="the last 24 hours",
    )


@router.get("/teams/{team_id}/activity", response_model=ActivityFeed)
async def team_activity(
    team_id: str, limit: int = 20, current_user: User = Depends(get_current_user)
) -> ActivityFeed:
    """Recent activity for one team. Active = last 7 days."""
    await team_service.get_team_doc(current_user, team_id)
    return await activity_service.get_feed(
        class_id=current_user.class_id,
        team_id=team_id,
        limit=limit,
        window_hours=24 * 7,
        window_label="the last 7 days",
    )
