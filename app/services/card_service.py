"""Card Table business logic: board reads, card create, detail read, and updates."""

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.board import COLUMN_KEYS, COLUMN_LABELS, DEFAULT_COLUMN, DEFAULT_COLUMNS
from app.models.card import Card, Subtask
from app.schemas.card import (
    Board,
    BoardColumn,
    CardPublic,
    CreateCardRequest,
    SubtaskDTO,
    UpdateCardRequest,
)
from app.services import activity_service, notification_service, team_service
from app.utils.sanitize import clean_html


def to_public(card: Card) -> CardPublic:
    return CardPublic(
        id=str(card.id),
        team_id=card.team_id,
        title=card.title,
        column=card.column,
        created_by=card.created_by,
        creator_name=card.creator_name,
        comment_count=card.comment_count,
        notes_html=card.notes_html,
        assignee_ids=card.assignee_ids,
        subscriber_ids=card.subscriber_ids,
        due_type=card.due_type,
        due_date=card.due_date,
        subtasks=[SubtaskDTO(id=s.id, text=s.text, done=s.done) for s in card.subtasks],
        created_at=card.created_at,
    )


async def get_card_doc(user, card_id: str) -> Card:
    """Load a card and assert it belongs to the user's class (else 404)."""
    if user.class_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found.")
    try:
        object_id = PydanticObjectId(card_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found.")
    card = await Card.get(object_id)
    if card is None or card.class_id != user.class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found.")
    return card


async def get_board(user, team_id: str) -> Board:
    await team_service.get_team_doc(user, team_id)  # validates class membership
    cards = await Card.find(Card.team_id == team_id).sort("-created_at").to_list()
    return Board(
        columns=[BoardColumn(**column) for column in DEFAULT_COLUMNS],
        cards=[to_public(card) for card in cards],
    )


async def get_card(user, card_id: str) -> CardPublic:
    card = await get_card_doc(user, card_id)
    return to_public(card)


async def create_card(user, team_id: str, payload: CreateCardRequest) -> CardPublic:
    team = await team_service.get_team_doc(user, team_id)
    column = payload.column if payload.column in COLUMN_KEYS else DEFAULT_COLUMN
    card = Card(
        class_id=user.class_id,
        team_id=team_id,
        title=payload.title,
        column=column,
        created_by=str(user.id),
        creator_name=user.name,
        subscriber_ids=[str(user.id)],  # the creator follows the card
    )
    await card.insert()
    await activity_service.record(
        class_id=user.class_id,
        actor=user,
        verb="added a card",
        team_id=team_id,
        team_name=team.name,
        target_type="card",
        target_title=card.title,
        target_id=str(card.id),
    )
    return to_public(card)


async def update_card(user, card_id: str, payload: UpdateCardRequest) -> CardPublic:
    card = await get_card_doc(user, card_id)
    moved_to = None
    newly_assigned: list[str] = []
    changed_other = False

    if payload.column is not None and payload.column != card.column:
        if payload.column not in COLUMN_KEYS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown board column."
            )
        card.column = payload.column
        moved_to = payload.column
    if payload.title is not None and payload.title != card.title:
        card.title = payload.title
        changed_other = True
    if payload.notes_html is not None:
        card.notes_html = clean_html(payload.notes_html)
        changed_other = True
    if payload.assignee_ids is not None:
        before = set(card.assignee_ids)
        card.assignee_ids = payload.assignee_ids
        newly_assigned = [a for a in payload.assignee_ids if a not in before]
    if payload.due_type is not None:
        card.due_type = payload.due_type
        if payload.due_type == "none":
            card.due_date = None
        changed_other = True
    if payload.due_date is not None:
        card.due_date = payload.due_date
        changed_other = True
    if payload.subtasks is not None:
        card.subtasks = [Subtask(id=s.id, text=s.text, done=s.done) for s in payload.subtasks]
        changed_other = True

    # Anyone who acts on or is assigned to a card starts following it.
    followers = set(card.subscriber_ids)
    followers.add(str(user.id))
    followers.update(newly_assigned)
    card.subscriber_ids = list(followers)

    await card.save()

    team = await team_service.get_team_doc(user, card.team_id)
    if moved_to is not None:
        await activity_service.record(
            class_id=user.class_id,
            actor=user,
            verb="moved this card to",
            team_id=card.team_id,
            team_name=team.name,
            target_type="card",
            target_title=card.title,
            target_id=str(card.id),
            to_column=moved_to,
        )
        await notification_service.notify_subscribers(
            card, user, f"moved this card to {COLUMN_LABELS.get(moved_to, moved_to)}", team.name
        )
    if newly_assigned:
        await notification_service.notify_assignment(card, user, newly_assigned, team.name)
    if changed_other and moved_to is None:
        await notification_service.notify_subscribers(card, user, "updated this card", team.name)

    return to_public(card)


async def set_subscribed(user, card_id: str, subscribed: bool) -> CardPublic:
    """Follow / unfollow a card for the current user (the "Notify me" toggle)."""
    card = await get_card_doc(user, card_id)
    uid = str(user.id)
    ids = set(card.subscriber_ids)
    if subscribed:
        ids.add(uid)
    else:
        ids.discard(uid)
    card.subscriber_ids = list(ids)
    await card.save()
    return to_public(card)
