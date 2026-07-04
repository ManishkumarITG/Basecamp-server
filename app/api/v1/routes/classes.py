"""Class routes: make, join, and view the current user's class."""

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.class_ import ClassOverview, ClassPublic, JoinClassRequest, MakeClassRequest
from app.services import class_service

router = APIRouter(prefix="/classes", tags=["classes"])


@router.post("", response_model=ClassPublic, status_code=status.HTTP_201_CREATED)
async def make_class(
    payload: MakeClassRequest, current_user: User = Depends(get_current_user)
) -> ClassPublic:
    """Create a class and become its Super Admin."""
    return await class_service.make_class(current_user, payload)


@router.post("/join", response_model=ClassPublic)
async def join_class(
    payload: JoinClassRequest, current_user: User = Depends(get_current_user)
) -> ClassPublic:
    """Join an existing class as a Member."""
    return await class_service.join_class(current_user, payload)


@router.get("/me", response_model=ClassOverview)
async def my_class(current_user: User = Depends(get_current_user)) -> ClassOverview:
    """Return the current user's class with its members and teams."""
    return await class_service.get_class_overview(current_user)
