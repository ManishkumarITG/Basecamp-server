"""Card Table routes: board reads, card create, detail read, and updates."""

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.card import Board, CardPublic, CreateCardRequest, UpdateCardRequest
from app.services import card_service
from app.ws.manager import manager

router = APIRouter(tags=["cards"])


@router.get("/teams/{team_id}/board", response_model=Board)
async def get_board(team_id: str, current_user: User = Depends(get_current_user)) -> Board:
    return await card_service.get_board(current_user, team_id)


@router.post("/teams/{team_id}/cards", response_model=CardPublic, status_code=status.HTTP_201_CREATED)
async def create_card(
    team_id: str, payload: CreateCardRequest, current_user: User = Depends(get_current_user)
) -> CardPublic:
    card = await card_service.create_card(current_user, team_id, payload)
    await manager.broadcast(team_id, {"type": "card.created", "teamId": team_id, "cardId": card.id})
    return card


@router.get("/cards/{card_id}", response_model=CardPublic)
async def get_card(card_id: str, current_user: User = Depends(get_current_user)) -> CardPublic:
    return await card_service.get_card(current_user, card_id)


@router.patch("/cards/{card_id}", response_model=CardPublic)
async def update_card(
    card_id: str, payload: UpdateCardRequest, current_user: User = Depends(get_current_user)
) -> CardPublic:
    card = await card_service.update_card(current_user, card_id, payload)
    await manager.broadcast(
        card.team_id, {"type": "card.updated", "teamId": card.team_id, "cardId": card.id}
    )
    return card


@router.post("/cards/{card_id}/subscribe", response_model=CardPublic)
async def subscribe(card_id: str, current_user: User = Depends(get_current_user)) -> CardPublic:
    card = await card_service.set_subscribed(current_user, card_id, True)
    await manager.broadcast(
        card.team_id, {"type": "card.updated", "teamId": card.team_id, "cardId": card.id}
    )
    return card


@router.delete("/cards/{card_id}/subscribe", response_model=CardPublic)
async def unsubscribe(card_id: str, current_user: User = Depends(get_current_user)) -> CardPublic:
    card = await card_service.set_subscribed(current_user, card_id, False)
    await manager.broadcast(
        card.team_id, {"type": "card.updated", "teamId": card.team_id, "cardId": card.id}
    )
    return card
