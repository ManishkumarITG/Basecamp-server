"""Comment business logic: thread CRUD, reactions, and the card timeline."""

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.models.activity import Activity
from app.models.card import Card
from app.models.comment import Comment
from app.models.user import User
from app.schemas.comment import (
    CardTimeline,
    CommentPublic,
    CreateCommentRequest,
    EditCommentRequest,
    TimelineEvent,
    TimelineItem,
)
from app.services import activity_service, card_service, notification_service, team_service
from app.utils.sanitize import clean_html


def to_public(comment: Comment) -> CommentPublic:
    return CommentPublic(
        id=str(comment.id),
        card_id=comment.card_id,
        team_id=comment.team_id,
        author_id=comment.author_id,
        author_name=comment.author_name,
        body_html=comment.body_html,
        reactions=comment.reactions,
        edited=comment.edited,
        created_at=comment.created_at,
    )


async def list_comments(user, card_id: str) -> list[CommentPublic]:
    await card_service.get_card_doc(user, card_id)
    comments = await Comment.find(Comment.card_id == card_id).sort("created_at").to_list()
    return [to_public(c) for c in comments]


async def create_comment(user, card_id: str, payload: CreateCommentRequest) -> CommentPublic:
    card = await card_service.get_card_doc(user, card_id)
    body = clean_html(payload.body_html)
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment is empty.")

    comment = Comment(
        card_id=card_id,
        class_id=user.class_id,
        team_id=card.team_id,
        author_id=str(user.id),
        author_name=user.name,
        body_html=body,
    )
    await comment.insert()

    # Validate @mentions are real members of this class.
    valid_mentions = await _valid_member_ids(payload.mention_ids, user.class_id)

    card.comment_count += 1
    followers = set(card.subscriber_ids)
    followers.add(str(user.id))  # commenting subscribes you to the card
    followers.update(valid_mentions)  # mentioning someone subscribes them too
    card.subscriber_ids = list(followers)
    await card.save()

    team = await team_service.get_team_doc(user, card.team_id)
    await activity_service.record(
        class_id=user.class_id,
        actor=user,
        verb="commented on",
        team_id=card.team_id,
        team_name=team.name,
        target_type="card",
        target_title=card.title,
        target_id=card_id,
    )
    # Mentioned people get a direct "mentioned you" notice; everyone else the
    # standard "commented on" one (and we don't double-notify the mentioned set).
    await notification_service.notify_mentions(
        card, user, valid_mentions, team.name, message_html=body
    )
    mentioned = set(valid_mentions)
    all_subscribers = card.subscriber_ids
    # Mentioned users already got a "mentioned you" email, so exclude them here.
    card.subscriber_ids = [sid for sid in all_subscribers if sid not in mentioned]
    await notification_service.notify_subscribers(
        card, user, "commented on", team.name, message_html=body
    )
    card.subscriber_ids = all_subscribers  # restore (not persisted)
    return to_public(comment)


async def _valid_member_ids(ids: list[str], class_id: str) -> list[str]:
    valid: list[str] = []
    for i in ids:
        try:
            member = await User.get(PydanticObjectId(i))
        except (ValueError, TypeError):
            member = None
        if member is not None and member.class_id == class_id:
            valid.append(i)
    return valid


async def edit_comment(user, comment_id: str, payload: EditCommentRequest) -> CommentPublic:
    comment = await _get_comment(user, comment_id)
    if comment.author_id != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own comments."
        )
    body = clean_html(payload.body_html)
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment is empty.")
    comment.body_html = body
    comment.edited = True
    await comment.save()
    return to_public(comment)


async def delete_comment(user, comment_id: str) -> CommentPublic:
    comment = await _get_comment(user, comment_id)
    if comment.author_id != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own comments."
        )
    snapshot = to_public(comment)
    await comment.delete()
    try:
        card = await Card.get(PydanticObjectId(comment.card_id))
    except (ValueError, TypeError):
        card = None
    if card is not None and card.comment_count > 0:
        card.comment_count -= 1
        await card.save()
    return snapshot


async def toggle_reaction(user, comment_id: str, emoji: str) -> CommentPublic:
    comment = await _get_comment(user, comment_id)
    uid = str(user.id)
    reactions = dict(comment.reactions)
    people = list(reactions.get(emoji, []))
    if uid in people:
        people = [p for p in people if p != uid]
    else:
        people.append(uid)
    if people:
        reactions[emoji] = people
    else:
        reactions.pop(emoji, None)
    comment.reactions = reactions
    await comment.save()
    return to_public(comment)


async def get_timeline(user, card_id: str) -> CardTimeline:
    await card_service.get_card_doc(user, card_id)
    comments = await Comment.find(Comment.card_id == card_id).to_list()
    activities = await Activity.find(Activity.target_id == card_id).to_list()

    items: list[TimelineItem] = []
    for c in comments:
        items.append(TimelineItem(kind="comment", created_at=c.created_at, comment=to_public(c)))
    for a in activities:
        if a.to_column:  # only move events
            items.append(
                TimelineItem(
                    kind="event",
                    created_at=a.created_at,
                    event=TimelineEvent(
                        id=str(a.id),
                        actor_id=a.actor_id,
                        actor_name=a.actor_name,
                        to_column=a.to_column,
                        created_at=a.created_at,
                    ),
                )
            )
    items.sort(key=lambda i: i.created_at)
    return CardTimeline(items=items)


async def _get_comment(user, comment_id: str) -> Comment:
    if user.class_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found.")
    try:
        object_id = PydanticObjectId(comment_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found.")
    comment = await Comment.get(object_id)
    if comment is None or comment.class_id != user.class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found.")
    return comment
