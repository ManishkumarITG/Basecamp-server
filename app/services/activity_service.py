"""Activity feed: recording events and reading scoped feeds + active users."""

from datetime import datetime, timedelta, timezone

from beanie import PydanticObjectId

from app.models.activity import Activity
from app.models.user import User
from app.schemas.activity import ActiveUser, ActivityFeed, ActivityPublic


def to_public(activity: Activity) -> ActivityPublic:
    return ActivityPublic(
        id=str(activity.id),
        actor_id=activity.actor_id,
        actor_name=activity.actor_name,
        verb=activity.verb,
        target_type=activity.target_type,
        target_title=activity.target_title,
        target_id=activity.target_id,
        team_id=activity.team_id,
        team_name=activity.team_name,
        created_at=activity.created_at,
    )


async def record(
    *,
    class_id: str,
    actor: User,
    verb: str,
    team_id: str | None = None,
    team_name: str | None = None,
    target_type: str | None = None,
    target_title: str | None = None,
    target_id: str | None = None,
    to_column: str | None = None,
) -> Activity:
    """Append an activity entry. Called by the other services after an action."""
    activity = Activity(
        class_id=class_id,
        actor_id=str(actor.id),
        actor_name=actor.name,
        verb=verb,
        team_id=team_id,
        team_name=team_name,
        target_type=target_type,
        target_title=target_title,
        target_id=target_id,
        to_column=to_column,
    )
    await activity.insert()
    return activity


async def _active_users(class_id: str, team_id: str | None, window_hours: int) -> list[ActiveUser]:
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    conditions = [Activity.class_id == class_id, Activity.created_at >= since]
    if team_id:
        conditions.append(Activity.team_id == team_id)
    recent = await Activity.find(*conditions).sort("-created_at").to_list()

    seen: list[str] = []
    for activity in recent:
        if activity.actor_id not in seen:
            seen.append(activity.actor_id)

    users: list[ActiveUser] = []
    for actor_id in seen[:12]:
        try:
            user = await User.get(PydanticObjectId(actor_id))
        except (ValueError, TypeError):
            user = None
        if user is not None:
            users.append(ActiveUser(id=str(user.id), name=user.name, email=user.email))
    return users


async def get_feed(
    *,
    class_id: str,
    team_id: str | None = None,
    limit: int = 20,
    window_hours: int = 24,
    window_label: str = "the last 24 hours",
) -> ActivityFeed:
    conditions = [Activity.class_id == class_id]
    if team_id:
        conditions.append(Activity.team_id == team_id)
    items = await Activity.find(*conditions).sort("-created_at").limit(limit).to_list()

    return ActivityFeed(
        items=[to_public(item) for item in items],
        active_users=await _active_users(class_id, team_id, window_hours),
        active_window_label=window_label,
    )
