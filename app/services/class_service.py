"""Class business logic: make/join a class and read the class overview.

Enforces the core rule that a user belongs to at most one class. Routes call into
this module; this module talks to the models (routes -> services -> models).
"""

from fastapi import HTTPException, status

from app.models.class_ import Class
from app.models.enums import ClassRole
from app.models.team import Team
from app.models.user import User
from app.schemas.class_ import ClassOverview, ClassPublic, JoinClassRequest, MakeClassRequest
from app.services import auth_service, team_service
from app.utils.codes import generate_code


def to_public(klass: Class) -> ClassPublic:
    """Map a Class document to its public DTO."""
    return ClassPublic(
        id=str(klass.id),
        name=klass.name,
        class_id=klass.class_id,
        invitation_code=klass.invitation_code,
        super_admin_id=klass.super_admin_id,
        created_at=klass.created_at,
    )


def _ensure_no_class(user: User) -> None:
    """Reject the action if the user already belongs to a class."""
    if user.class_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already belong to a class.",
        )


async def _generate_unique_class_id() -> str:
    """Generate a Class ID code that is not already in use."""
    for _ in range(10):
        code = generate_code(8)
        if await Class.find_one(Class.class_id == code) is None:
            return code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a unique Class ID. Please try again.",
    )


async def make_class(user: User, payload: MakeClassRequest) -> ClassPublic:
    """Create a class, making the user its Super Admin."""
    _ensure_no_class(user)

    class_code = await _generate_unique_class_id()
    klass = Class(
        name=payload.name,
        class_id=class_code,
        invitation_code=generate_code(8),
        super_admin_id=str(user.id),
    )
    await klass.insert()

    user.class_id = klass.class_id
    user.class_role = ClassRole.SUPER_ADMIN
    await user.save()

    return to_public(klass)


async def join_class(user: User, payload: JoinClassRequest) -> ClassPublic:
    """Join an existing class as a Member after verifying ID + invitation code."""
    _ensure_no_class(user)

    klass = await Class.find_one(Class.class_id == payload.class_id)
    # Single combined error so we don't reveal which field was wrong.
    if klass is None or klass.invitation_code != payload.invitation_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Class ID or Invitation Code.",
        )

    user.class_id = klass.class_id
    user.class_role = ClassRole.MEMBER
    await user.save()

    return to_public(klass)


async def get_class_overview(user: User) -> ClassOverview:
    """Return the user's class along with its members and teams."""
    if user.class_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You do not belong to a class yet.",
        )

    klass = await Class.find_one(Class.class_id == user.class_id)
    if klass is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found.")

    members = await User.find(User.class_id == user.class_id).to_list()
    teams = await Team.find(Team.class_id == user.class_id).to_list()

    return ClassOverview(
        class_=to_public(klass),
        members=[auth_service.to_public(member) for member in members],
        teams=[team_service.to_public(team) for team in teams],
    )
