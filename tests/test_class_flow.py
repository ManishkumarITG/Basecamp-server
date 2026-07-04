"""DB-backed tests for the onboarding flow, using an in-memory Mongo.

``mongomock-motor`` provides an async Mongo compatible with Motor/Beanie, so these
run without a real MongoDB server. Each test runs its whole scenario in one event
loop (Beanie binds documents to the loop that initialized them).
"""

import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from beanie import init_beanie

from app.models import document_models
from app.models.enums import ClassRole, TeamRole
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.schemas.class_ import JoinClassRequest, MakeClassRequest
from app.schemas.team import AddTeamMemberRequest, CreateTeamRequest
from app.services import auth_service, class_service, team_service


def run(coro):
    """Run an async scenario in a fresh event loop."""
    return asyncio.run(coro)


async def _init_db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=document_models)


async def _register(email, name="User"):
    await auth_service.register_user(
        RegisterRequest(email=email, name=name, password="password123")
    )
    return await User.find_one(User.email == email)


def test_make_class_makes_creator_super_admin_with_codes():
    async def scenario():
        await _init_db()
        owner = await _register("owner@x.com", "Owner")

        klass = await class_service.make_class(owner, MakeClassRequest(name="Acme"))

        assert owner.class_role == ClassRole.SUPER_ADMIN
        assert owner.class_id == klass.class_id
        assert klass.class_id and klass.invitation_code
        assert klass.super_admin_id == str(owner.id)

    run(scenario())


def test_one_class_per_user_rule_blocks_make_and_join():
    async def scenario():
        await _init_db()
        owner = await _register("owner@x.com", "Owner")
        await class_service.make_class(owner, MakeClassRequest(name="Acme"))

        # Already a super admin -> cannot make another class.
        with pytest.raises(HTTPException) as make_exc:
            await class_service.make_class(owner, MakeClassRequest(name="Second"))
        assert make_exc.value.status_code == 409

        # ...nor join one.
        with pytest.raises(HTTPException) as join_exc:
            await class_service.join_class(
                owner, JoinClassRequest(class_id="WHATEVER", invitation_code="X")
            )
        assert join_exc.value.status_code == 409

    run(scenario())


def test_join_with_valid_codes_adds_member_invalid_is_rejected():
    async def scenario():
        await _init_db()
        owner = await _register("owner@x.com", "Owner")
        member = await _register("member@x.com", "Member")
        klass = await class_service.make_class(owner, MakeClassRequest(name="Acme"))

        # Wrong invitation code -> 400.
        with pytest.raises(HTTPException) as bad:
            await class_service.join_class(
                member, JoinClassRequest(class_id=klass.class_id, invitation_code="WRONG")
            )
        assert bad.value.status_code == 400

        # Unknown class id -> 400.
        with pytest.raises(HTTPException) as missing:
            await class_service.join_class(
                member,
                JoinClassRequest(class_id="NOPE", invitation_code=klass.invitation_code),
            )
        assert missing.value.status_code == 400

        # Correct codes -> joined as member.
        await class_service.join_class(
            member,
            JoinClassRequest(class_id=klass.class_id, invitation_code=klass.invitation_code),
        )
        assert member.class_role == ClassRole.MEMBER
        assert member.class_id == klass.class_id

    run(scenario())


def test_overview_lists_members_and_team_permissions():
    async def scenario():
        await _init_db()
        owner = await _register("owner@x.com", "Owner")
        member = await _register("member@x.com", "Member")
        klass = await class_service.make_class(owner, MakeClassRequest(name="Acme"))
        await class_service.join_class(
            member,
            JoinClassRequest(class_id=klass.class_id, invitation_code=klass.invitation_code),
        )

        overview = await class_service.get_class_overview(owner)
        assert len(overview.members) == 2
        assert overview.class_.class_id == klass.class_id

        # Only the super admin can create teams.
        team = await team_service.create_team(owner, CreateTeamRequest(name="Engineering"))
        with pytest.raises(HTTPException) as exc:
            await team_service.create_team(member, CreateTeamRequest(name="Sales"))
        assert exc.value.status_code == 403

        # Assign the member to the team as an admin.
        updated = await team_service.add_team_member(
            owner, team.id, AddTeamMemberRequest(user_id=str(member.id), role=TeamRole.ADMIN)
        )
        assert str(member.id) in updated.admin_ids

    run(scenario())
