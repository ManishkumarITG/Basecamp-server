"""Team routes: list, create, read, update, favorites, and membership."""

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.team import (
    AddTeamMemberRequest,
    CreateTeamRequest,
    TeamPublic,
    UpdateTeamRequest,
)
from app.services import team_service

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("", response_model=list[TeamPublic])
async def list_teams(current_user: User = Depends(get_current_user)) -> list[TeamPublic]:
    return await team_service.list_teams(current_user)


@router.post("", response_model=TeamPublic, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: CreateTeamRequest, current_user: User = Depends(get_current_user)
) -> TeamPublic:
    return await team_service.create_team(current_user, payload)


@router.get("/{team_id}", response_model=TeamPublic)
async def get_team(team_id: str, current_user: User = Depends(get_current_user)) -> TeamPublic:
    return await team_service.get_team(current_user, team_id)


@router.patch("/{team_id}", response_model=TeamPublic)
async def update_team(
    team_id: str, payload: UpdateTeamRequest, current_user: User = Depends(get_current_user)
) -> TeamPublic:
    return await team_service.update_team(current_user, team_id, payload)


@router.post("/{team_id}/star", response_model=TeamPublic)
async def star_team(team_id: str, current_user: User = Depends(get_current_user)) -> TeamPublic:
    return await team_service.set_starred(current_user, team_id, True)


@router.delete("/{team_id}/star", response_model=TeamPublic)
async def unstar_team(team_id: str, current_user: User = Depends(get_current_user)) -> TeamPublic:
    return await team_service.set_starred(current_user, team_id, False)


@router.post("/{team_id}/members", response_model=TeamPublic)
async def add_team_member(
    team_id: str,
    payload: AddTeamMemberRequest,
    current_user: User = Depends(get_current_user),
) -> TeamPublic:
    return await team_service.add_team_member(current_user, team_id, payload)
