"""Comment routes: thread CRUD, reactions, and the card timeline.

Every mutation broadcasts a small event to the card's team over WebSocket so all
connected clients refetch and update instantly.
"""

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.comment import (
    CardTimeline,
    CommentPublic,
    CreateCommentRequest,
    EditCommentRequest,
    ReactRequest,
)
from app.services import comment_service
from app.ws.manager import manager

router = APIRouter(tags=["comments"])


async def _broadcast(event_type: str, comment: CommentPublic) -> None:
    await manager.broadcast(
        comment.team_id,
        {"type": event_type, "teamId": comment.team_id, "cardId": comment.card_id},
    )


@router.get("/cards/{card_id}/comments", response_model=list[CommentPublic])
async def list_comments(
    card_id: str, current_user: User = Depends(get_current_user)
) -> list[CommentPublic]:
    return await comment_service.list_comments(current_user, card_id)


@router.get("/cards/{card_id}/timeline", response_model=CardTimeline)
async def card_timeline(
    card_id: str, current_user: User = Depends(get_current_user)
) -> CardTimeline:
    return await comment_service.get_timeline(current_user, card_id)


@router.post(
    "/cards/{card_id}/comments", response_model=CommentPublic, status_code=status.HTTP_201_CREATED
)
async def create_comment(
    card_id: str, payload: CreateCommentRequest, current_user: User = Depends(get_current_user)
) -> CommentPublic:
    comment = await comment_service.create_comment(current_user, card_id, payload)
    await _broadcast("comment.created", comment)
    return comment


@router.patch("/comments/{comment_id}", response_model=CommentPublic)
async def edit_comment(
    comment_id: str, payload: EditCommentRequest, current_user: User = Depends(get_current_user)
) -> CommentPublic:
    comment = await comment_service.edit_comment(current_user, comment_id, payload)
    await _broadcast("comment.updated", comment)
    return comment


@router.delete("/comments/{comment_id}", response_model=CommentPublic)
async def delete_comment(
    comment_id: str, current_user: User = Depends(get_current_user)
) -> CommentPublic:
    comment = await comment_service.delete_comment(current_user, comment_id)
    await _broadcast("comment.deleted", comment)
    return comment


@router.post("/comments/{comment_id}/reactions", response_model=CommentPublic)
async def react(
    comment_id: str, payload: ReactRequest, current_user: User = Depends(get_current_user)
) -> CommentPublic:
    comment = await comment_service.toggle_reaction(current_user, comment_id, payload.emoji)
    await _broadcast("comment.reacted", comment)
    return comment
