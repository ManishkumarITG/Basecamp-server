"""Team business logic: create, read, update, membership, and favorites."""

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.models.enums import ClassRole, TeamRole
from app.models.team import Team
from app.models.user import User
from app.schemas.team import AddTeamMemberRequest, CreateTeamRequest, TeamPublic, UpdateTeamRequest
from app.services import activity_service


def to_public(team: Team, starred: bool = False) -> TeamPublic:
    """Map a Team document to its public DTO. ``starred`` is per requesting-user."""
    member_count = len(set(team.admin_ids) | set(team.member_ids))
    return TeamPublic(
        id=str(team.id),
        class_id=team.class_id,
        name=team.name,
        description=team.description,
        admin_ids=team.admin_ids,
        member_ids=team.member_ids,
        member_count=member_count,
        starred=starred,
        created_at=team.created_at,
    )


def _require_class(user: User) -> str:
    if user.class_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You must belong to a class first."
        )
    return user.class_id


async def get_team_doc(user: User, team_id: str) -> Team:
    """Load a team and assert it belongs to the user's class (else 404)."""
    _require_class(user)
    try:
        object_id = PydanticObjectId(team_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")
    team = await Team.get(object_id)
    if team is None or team.class_id != user.class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")
    return team


def _can_manage(user: User, team: Team) -> bool:
    return user.class_role == ClassRole.SUPER_ADMIN or str(user.id) in team.admin_ids


async def create_team(user: User, payload: CreateTeamRequest) -> TeamPublic:
    """Create a team in the user's class. Only the Super Admin may do this."""
    class_id = _require_class(user)
    if user.class_role != ClassRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the class Super Admin can create teams.",
        )
    team = Team(
        class_id=class_id,
        name=payload.name,
        description=payload.description,
        admin_ids=[str(user.id)],  # creator administers the new team
    )
    await team.insert()
    await activity_service.record(
        class_id=class_id,
        actor=user,
        verb="created the team",
        team_id=str(team.id),
        team_name=team.name,
        target_type="team",
        target_title=team.name,
        target_id=str(team.id),
    )
    return to_public(team, starred=False)


async def list_teams(user: User) -> list[TeamPublic]:
    """All teams in the user's class, with the user's star state."""
    class_id = _require_class(user)
    teams = await Team.find(Team.class_id == class_id).sort("-created_at").to_list()
    starred = set(user.starred_team_ids)
    return [to_public(team, starred=str(team.id) in starred) for team in teams]


async def get_team(user: User, team_id: str) -> TeamPublic:
    team = await get_team_doc(user, team_id)
    return to_public(team, starred=team_id in set(user.starred_team_ids))


async def update_team(user: User, team_id: str, payload: UpdateTeamRequest) -> TeamPublic:
    team = await get_team_doc(user, team_id)
    if not _can_manage(user, team):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can't manage this team."
        )
    if payload.name is not None:
        team.name = payload.name
    if payload.description is not None:
        team.description = payload.description
    await team.save()
    return to_public(team, starred=team_id in set(user.starred_team_ids))


async def set_starred(user: User, team_id: str, starred: bool) -> TeamPublic:
    """Star/unstar a team for the current user."""
    team = await get_team_doc(user, team_id)
    ids = set(user.starred_team_ids)
    if starred:
        ids.add(team_id)
    else:
        ids.discard(team_id)
    user.starred_team_ids = list(ids)
    await user.save()
    return to_public(team, starred=starred)


async def add_team_member(
    user: User, team_id: str, payload: AddTeamMemberRequest
) -> TeamPublic:
    """Assign a class member to a team as admin or member."""
    team = await get_team_doc(user, team_id)
    if not _can_manage(user, team):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You're not allowed to manage this team."
        )

    target = await _get_class_member(payload.user_id, team.class_id)
    target_id = str(target.id)

    team.admin_ids = [uid for uid in team.admin_ids if uid != target_id]
    team.member_ids = [uid for uid in team.member_ids if uid != target_id]
    if payload.role == TeamRole.ADMIN:
        team.admin_ids.append(target_id)
    else:
        team.member_ids.append(target_id)

    await team.save()
    return to_public(team, starred=team_id in set(user.starred_team_ids))


async def _get_class_member(user_id: str, class_id: str) -> User:
    try:
        object_id = PydanticObjectId(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this class.",
        )
    member = await User.get(object_id)
    if member is None or member.class_id != class_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this class.",
        )
    return member
