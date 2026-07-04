"""DB-backed tests for the collaboration layer (teams, board, todos, docs, feed)."""

import asyncio

from mongomock_motor import AsyncMongoMockClient

from beanie import init_beanie

from app.models import document_models
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.schemas.card import CreateCardRequest, UpdateCardRequest
from app.schemas.class_ import MakeClassRequest
from app.schemas.comment import CreateCommentRequest
from app.schemas.doc import CreateDocRequest
from app.schemas.team import CreateTeamRequest
from app.schemas.todo import CreateTodoRequest, UpdateTodoRequest
from app.services import (
    activity_service,
    auth_service,
    card_service,
    class_service,
    comment_service,
    doc_service,
    team_service,
    todo_service,
)


def run(coro):
    return asyncio.run(coro)


async def _init_db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=document_models)


async def _owner_with_class():
    await auth_service.register_user(
        RegisterRequest(email="owner@x.com", name="Owner", password="password123")
    )
    owner = await User.find_one(User.email == "owner@x.com")
    await class_service.make_class(owner, MakeClassRequest(name="Acme"))
    return owner


def test_team_create_board_and_card_move():
    async def scenario():
        await _init_db()
        owner = await _owner_with_class()

        team = await team_service.create_team(
            owner, CreateTeamRequest(name="SEO-Dev", description="SEO work")
        )
        assert team.description == "SEO work"
        assert team.member_count == 1  # creator is a team admin

        board = await card_service.get_board(owner, team.id)
        assert len(board.columns) == 7
        assert board.cards == []

        card = await card_service.create_card(owner, team.id, CreateCardRequest(title="Bison"))
        assert card.column == "triage"

        moved = await card_service.update_card(
            owner, card.id, UpdateCardRequest(column="in_progress")
        )
        assert moved.column == "in_progress"

        comment = await comment_service.create_comment(
            owner, card.id, CreateCommentRequest(body_html="<b>hi</b><script>x()</script>")
        )
        # body is sanitized (script stripped) and the card's count is bumped
        assert "<b>hi</b>" in comment.body_html and "script" not in comment.body_html
        refreshed = await card_service.get_card(owner, card.id)
        assert refreshed.comment_count == 1
        timeline = await comment_service.get_timeline(owner, card.id)
        kinds = [i.kind for i in timeline.items]
        assert "comment" in kinds and "event" in kinds  # comment + the earlier move

    run(scenario())


def test_star_toggle_and_todos_and_docs():
    async def scenario():
        await _init_db()
        owner = await _owner_with_class()
        team = await team_service.create_team(owner, CreateTeamRequest(name="SEO-Dev"))

        starred = await team_service.set_starred(owner, team.id, True)
        assert starred.starred is True
        # reload owner to confirm persistence
        owner_reloaded = await User.find_one(User.email == "owner@x.com")
        assert team.id in owner_reloaded.starred_team_ids

        todo = await todo_service.create_todo(
            owner_reloaded, team.id, CreateTodoRequest(title="Fix nav link")
        )
        assert todo.done is False
        done = await todo_service.update_todo(owner_reloaded, todo.id, UpdateTodoRequest(done=True))
        assert done.done is True

        doc = await doc_service.create_doc(
            owner_reloaded, team.id, CreateDocRequest(title="Audit", kind="file")
        )
        assert doc.kind == "file"
        docs = await doc_service.list_docs(owner_reloaded, team.id)
        assert len(docs) == 1

    run(scenario())


def test_activity_feed_records_real_actions():
    async def scenario():
        await _init_db()
        owner = await _owner_with_class()

        # Real actions record activity entries.
        team = await team_service.create_team(owner, CreateTeamRequest(name="SEO-Dev"))
        await card_service.create_card(owner, team.id, CreateCardRequest(title="Bison"))

        feed = await activity_service.get_feed(class_id=owner.class_id, limit=20)
        assert len(feed.items) >= 2  # "created the team" + "added a card"
        assert feed.active_window_label == "the last 24 hours"
        assert len(feed.active_users) >= 1

    run(scenario())
