"""Tests for email verification, password reset, and notification recipients.

Email itself runs in dev-log mode (no SMTP), so we read the OTP from the stored
user and capture notification recipients by monkeypatching the email service.
"""

import asyncio
import smtplib

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from beanie import init_beanie

from app.models import document_models
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.schemas.card import CreateCardRequest, UpdateCardRequest
from app.schemas.class_ import JoinClassRequest, MakeClassRequest
from app.schemas.comment import CreateCommentRequest
from app.schemas.team import CreateTeamRequest
from app.models.pending_email import PendingEmail
from app.models.pending_notification import PendingNotification
from app.services import (
    auth_service,
    card_service,
    class_service,
    comment_service,
    digest_service,
    email_service,
    team_service,
)


def run(coro):
    return asyncio.run(coro)


async def _init_db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=document_models)


def test_signup_otp_and_login_gate():
    async def scenario():
        await _init_db()
        await auth_service.register_user(
            RegisterRequest(email="dev@x.com", name="Dev", password="password123")
        )
        user = await User.find_one(User.email == "dev@x.com")
        assert user.is_verified is False and user.otp_code  # unverified + code issued

        # Can't log in until verified.
        with pytest.raises(HTTPException) as exc:
            await auth_service.authenticate_user(LoginRequest(email="dev@x.com", password="password123"))
        assert exc.value.status_code == 403

        # Wrong code rejected, correct code verifies + logs in.
        with pytest.raises(HTTPException):
            await auth_service.verify_email(VerifyEmailRequest(email="dev@x.com", otp="000000"))
        token = await auth_service.verify_email(
            VerifyEmailRequest(email="dev@x.com", otp=user.otp_code)
        )
        assert token.access_token and token.user.email == "dev@x.com"

        # Now login works.
        ok = await auth_service.authenticate_user(LoginRequest(email="dev@x.com", password="password123"))
        assert ok.access_token

    run(scenario())


def test_password_reset():
    async def scenario():
        await _init_db()
        await auth_service.register_user(
            RegisterRequest(email="dev@x.com", name="Dev", password="password123")
        )
        user = await User.find_one(User.email == "dev@x.com")
        await auth_service.verify_email(VerifyEmailRequest(email="dev@x.com", otp=user.otp_code))

        await auth_service.forgot_password(ForgotPasswordRequest(email="dev@x.com"))
        user = await User.find_one(User.email == "dev@x.com")
        assert user.otp_purpose == "reset" and user.otp_code

        await auth_service.reset_password(
            ResetPasswordRequest(email="dev@x.com", otp=user.otp_code, new_password="newpass456")
        )
        # Old password fails, new one works.
        with pytest.raises(HTTPException):
            await auth_service.authenticate_user(LoginRequest(email="dev@x.com", password="password123"))
        ok = await auth_service.authenticate_user(LoginRequest(email="dev@x.com", password="newpass456"))
        assert ok.access_token

    run(scenario())


def test_assigner_and_assignee_get_notified_on_third_party_comment(monkeypatch):
    async def scenario():
        await _init_db()
        sent = []

        async def fake_notify(to, *a, **k):
            sent.append(to)

        monkeypatch.setattr(email_service, "send_card_notification", fake_notify)

        # Manager makes the class + team; two others join.
        await auth_service.register_user(RegisterRequest(email="manager@x.com", name="Manager", password="password123"))
        manager = await User.find_one(User.email == "manager@x.com")
        klass = await class_service.make_class(manager, MakeClassRequest(name="Acme"))

        async def join(email, name):
            await auth_service.register_user(RegisterRequest(email=email, name=name, password="password123"))
            u = await User.find_one(User.email == email)
            await class_service.join_class(
                u, JoinClassRequest(class_id=klass.class_id, invitation_code=klass.invitation_code)
            )
            return await User.find_one(User.email == email)

        me = await join("me@x.com", "Me")
        third = await join("third@x.com", "Third")

        team = await team_service.create_team(manager, CreateTeamRequest(name="SEO"))
        card = await card_service.create_card(manager, team.id, CreateCardRequest(title="The Hat Girls"))

        # Manager assigns the card to me -> I get an assignment email + I'm subscribed.
        await card_service.update_card(manager, card.id, UpdateCardRequest(assignee_ids=[str(me.id)]))
        assert sent == [me.email]
        sent.clear()

        # A third person comments -> manager AND me are notified (not the third).
        await comment_service.create_comment(
            third, card.id, CreateCommentRequest(body_html="Looks good")
        )
        assert set(sent) == {manager.email, me.email}

    run(scenario())


async def _class_with_members(emails):
    await auth_service.register_user(RegisterRequest(email="owner@x.com", name="Owner", password="password123"))
    owner = await User.find_one(User.email == "owner@x.com")
    klass = await class_service.make_class(owner, MakeClassRequest(name="Acme"))
    members = {}
    for email, name in emails:
        await auth_service.register_user(RegisterRequest(email=email, name=name, password="password123"))
        u = await User.find_one(User.email == email)
        await class_service.join_class(
            u, JoinClassRequest(class_id=klass.class_id, invitation_code=klass.invitation_code)
        )
        members[email] = await User.find_one(User.email == email)
    return owner, members


def test_mention_emails_a_specific_person(monkeypatch):
    async def scenario():
        await _init_db()
        sent = []

        async def fake_notify(to, recipient_name, actor_name, action, *a, **k):
            sent.append((to, action))

        monkeypatch.setattr(email_service, "send_card_notification", fake_notify)
        owner, members = await _class_with_members([("me@x.com", "Me"), ("third@x.com", "Third")])
        me, third = members["me@x.com"], members["third@x.com"]
        team = await team_service.create_team(owner, CreateTeamRequest(name="SEO"))
        card = await card_service.create_card(owner, team.id, CreateCardRequest(title="The Hat Girls"))

        # Third comments and @mentions me -> I get a "mentioned you" email.
        await comment_service.create_comment(
            third, card.id, CreateCommentRequest(body_html="cc you", mention_ids=[str(me.id)])
        )
        me_actions = [action for (to, action) in sent if to == me.email]
        assert any("mentioned you" in a for a in me_actions)
        # Owner (a subscriber, not mentioned) got the standard "commented on".
        assert (owner.email, "commented on") in sent

    run(scenario())


def test_comment_notification_includes_message_and_summary(monkeypatch):
    """A comment/@mention email carries the message text AND a task summary."""
    async def scenario():
        await _init_db()
        captured = []

        async def fake_notify(
            to, recipient_name, actor_name, action, card_title, team_name, url,
            summary=None, message_html=None,
        ):
            captured.append({"to": to, "action": action, "summary": summary, "message_html": message_html})

        monkeypatch.setattr(email_service, "send_card_notification", fake_notify)
        owner, members = await _class_with_members([("me@x.com", "Me")])
        me = members["me@x.com"]
        team = await team_service.create_team(owner, CreateTeamRequest(name="SEO"))
        card = await card_service.create_card(owner, team.id, CreateCardRequest(title="The Hat Girls"))

        await comment_service.create_comment(
            owner, card.id,
            CreateCommentRequest(body_html="<p>please review this</p>", mention_ids=[str(me.id)]),
        )

        mine = [c for c in captured if c["to"] == me.email]
        assert mine, "the @mentioned user should be notified"
        event = mine[0]
        assert "mentioned you" in event["action"]
        assert "please review this" in (event["message_html"] or "")  # message included
        assert event["summary"]["status"] == "Triage"                 # default column label
        assert event["summary"]["assignees"] == "Unassigned"
        assert event["summary"]["comments"] >= 1

    run(scenario())


def test_outbox_retries_then_delivers(monkeypatch):
    """A transient SMTP failure must not drop the email: it's queued and retried
    by the outbox worker until it delivers."""
    async def scenario():
        await _init_db()
        # Real-send mode, but no backoff/extra inline retries so we can step the
        # worker pass by pass.
        monkeypatch.setattr(email_service.settings, "smtp_host", "smtp.test")
        monkeypatch.setattr(email_service.settings, "email_max_retries", 1)
        monkeypatch.setattr(email_service.settings, "email_retry_backoff_seconds", 0)
        monkeypatch.setattr(email_service.settings, "outbox_max_attempts", 5)

        attempts = {"n": 0}

        def flaky_send(to, subject, html, text):
            attempts["n"] += 1
            if attempts["n"] < 3:  # first two attempts fail, third succeeds
                raise smtplib.SMTPServerDisconnected("transient")

        monkeypatch.setattr(email_service, "_send_smtp", flaky_send)

        await email_service.enqueue_email("x@x.com", "Hi", "<p>Hi</p>", "Hi", "otp")
        assert await PendingEmail.find_all().count() == 1

        # Two passes fail (row stays queued, attempts grow); the third delivers it.
        assert await email_service.process_outbox() == 0
        assert await email_service.process_outbox() == 0
        assert await email_service.process_outbox() == 1
        assert await PendingEmail.find_all().count() == 0
        assert attempts["n"] == 3

    run(scenario())


def test_digest_mode_queues_then_flushes(monkeypatch):
    async def scenario():
        await _init_db()
        instant, digests = [], []

        async def fake_notify(to, *a, **k):
            instant.append(to)

        async def fake_digest(to, *a, **k):
            digests.append(to)

        monkeypatch.setattr(email_service, "send_card_notification", fake_notify)
        monkeypatch.setattr(email_service, "send_digest_email", fake_digest)

        owner, members = await _class_with_members([("me@x.com", "Me")])
        me = members["me@x.com"]
        # I switch to digest mode.
        me.digest_enabled = True
        await me.save()

        team = await team_service.create_team(owner, CreateTeamRequest(name="SEO"))
        card = await card_service.create_card(owner, team.id, CreateCardRequest(title="Card"))
        await card_service.update_card(owner, card.id, UpdateCardRequest(assignee_ids=[str(me.id)]))

        # Owner comments -> I'm a subscriber but in digest mode, so NO instant email;
        # a pending row is queued instead.
        await comment_service.create_comment(owner, card.id, CreateCommentRequest(body_html="update"))
        assert me.email not in instant
        assert await PendingNotification.find_all().count() >= 1

        # Flushing sends one digest email and clears the queue.
        sent_count = await digest_service.flush_digests()
        assert sent_count >= 1
        assert me.email in digests
        assert await PendingNotification.find_all().count() == 0

    run(scenario())


def test_resend_transport_dispatch(monkeypatch):
    """When EMAIL_PROVIDER=resend with a key, send_email routes to the Resend
    transport (no SMTP)."""
    async def scenario():
        monkeypatch.setattr(email_service.settings, "email_provider", "resend")
        monkeypatch.setattr(email_service.settings, "resend_api_key", "re_test")
        monkeypatch.setattr(email_service.settings, "email_from", "Basecamp <noreply@itgeeks.com>")

        calls = []

        async def fake_resend(to, subject, html, text):
            calls.append((to, subject))

        monkeypatch.setattr(email_service, "_send_resend", fake_resend)

        ok = await email_service.send_email("a@b.com", "Hi", "<p>Hi</p>", "Hi")
        assert ok == "sent"
        assert calls == [("a@b.com", "Hi")]
        assert email_service.describe_transport() == "Resend (API)"

    run(scenario())


def test_send_resend_payload_and_error_mapping(monkeypatch):
    """The real _send_resend body: correct URL/header/JSON, and status mapping
    (2xx ok, 3xx/4xx -> EmailSendError)."""
    import httpx

    async def scenario():
        monkeypatch.setattr(email_service.settings, "resend_api_key", "re_test")
        monkeypatch.setattr(email_service.settings, "email_from", "Basecamp <noreply@itgeeks.com>")

        captured = {}
        status = {"code": 200}

        class FakeResp:
            def __init__(self, code):
                self.status_code = code
                self.text = "body"

        async def fake_post(self, url, headers=None, json=None):
            captured.update(url=url, headers=headers, json=json)
            return FakeResp(status["code"])

        monkeypatch.setattr(email_service.httpx.AsyncClient, "post", fake_post)

        # 2xx: no raise, and the payload contract holds.
        await email_service._send_resend("a@b.com", "Hi", "<p>Hi</p>", "Hi")
        assert captured["url"] == "https://api.resend.com/emails"
        assert captured["headers"]["Authorization"] == "Bearer re_test"
        assert captured["json"]["to"] == ["a@b.com"]  # must be a list
        assert captured["json"]["from"] == "Basecamp <noreply@itgeeks.com>"
        assert captured["json"]["subject"] == "Hi"

        # 4xx -> EmailSendError carrying the status.
        status["code"] = 422
        with pytest.raises(email_service.EmailSendError) as ei:
            await email_service._send_resend("a@b.com", "Hi", "<p>Hi</p>", "Hi")
        assert ei.value.status_code == 422

        # 3xx is NOT a success (2xx-only).
        status["code"] = 302
        with pytest.raises(email_service.EmailSendError):
            await email_service._send_resend("a@b.com", "Hi", "<p>Hi</p>", "Hi")

    run(scenario())


def test_resend_retries_transient_then_delivers(monkeypatch):
    """Transient Resend errors (5xx) retry then deliver; permanent (4xx) stops at once."""
    async def scenario():
        monkeypatch.setattr(email_service.settings, "email_provider", "resend")
        monkeypatch.setattr(email_service.settings, "resend_api_key", "re_test")
        monkeypatch.setattr(email_service.settings, "email_max_retries", 3)
        monkeypatch.setattr(email_service.settings, "email_retry_backoff_seconds", 0)

        calls = {"n": 0}

        async def flaky(to, subject, html, text):
            calls["n"] += 1
            if calls["n"] < 3:
                raise email_service.EmailSendError(503, "service down")

        monkeypatch.setattr(email_service, "_send_resend", flaky)
        assert await email_service.send_email("a@b.com", "Hi", "<p>Hi</p>", "Hi") == "sent"
        assert calls["n"] == 3

        calls["n"] = 0

        async def permanent(to, subject, html, text):
            calls["n"] += 1
            raise email_service.EmailSendError(422, "unverified from")

        monkeypatch.setattr(email_service, "_send_resend", permanent)
        assert await email_service.send_email("a@b.com", "Hi", "<p>Hi</p>", "Hi") == "permanent"
        assert calls["n"] == 1  # permanent => no retries

    run(scenario())


def test_dev_log_mode_sends_nothing_and_does_not_enqueue():
    """In dev-log mode (no provider configured) send_email reports sent but nothing
    is transmitted, and enqueue_email skips the durable outbox."""
    async def scenario():
        await _init_db()
        assert email_service._active_transport() is None  # conftest forces dev-log
        assert await email_service.send_email("a@b.com", "Hi", "<p>Hi</p>", "Hi") == "sent"
        await email_service.enqueue_email("a@b.com", "Hi", "<p>Hi</p>", "Hi", "notification")
        assert await PendingEmail.find_all().count() == 0

    run(scenario())


def test_is_permanent_classifies_errors():
    """4xx (except 429) permanent; 429/5xx and httpx network errors transient."""
    import httpx

    from app.services.email_service import EmailSendError, _is_permanent

    assert _is_permanent(EmailSendError(422, "invalid from")) is True
    assert _is_permanent(EmailSendError(403, "forbidden")) is True
    assert _is_permanent(EmailSendError(429, "rate limited")) is False
    assert _is_permanent(EmailSendError(503, "service down")) is False
    assert _is_permanent(smtplib.SMTPAuthenticationError(535, b"bad creds")) is True
    assert _is_permanent(httpx.TimeoutException("timeout")) is False
    assert _is_permanent(httpx.ConnectError("refused")) is False