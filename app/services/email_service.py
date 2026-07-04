"""Email sending.

If SMTP is configured (SMTP_HOST set) emails are sent for real; otherwise they are
written to the server log ("dev mode") so OTP codes and notifications are visible
during local development without a mail server. Sending uses the stdlib smtplib on
a worker thread so the event loop is never blocked.

Reliability (Gmail SMTP fails intermittently — transient 4xx, dropped connections,
timeouts):
  * ``send_email`` retries each send with exponential backoff before giving up.
  * Anything that still can't go out inline is persisted to a durable outbox
    (``PendingEmail``) and retried by ``run_outbox_loop`` until it delivers, so a
    transient Gmail hiccup never silently drops a message — it just arrives late.
  * OTP/reset mail is sent inline (the user is waiting). Because the code is a
    short-lived secret, a failed OTP send is NOT persisted — the caller asks the
    user to request a new one. Notifications/digests go to the durable outbox.
"""

import asyncio
import html
import logging
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import httpx

from app.core.config import settings
from app.models.pending_email import PendingEmail

logger = logging.getLogger("basecamp.email")

# Minimal, email-client-safe layout (light, inline styles).
_LAYOUT = """\
<div style="background:#f4f5f7;padding:28px 0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e6e8ee;border-radius:14px;overflow:hidden;">
    <div style="padding:18px 28px;border-bottom:1px solid #eef0f4;font-weight:700;color:#4f46e5;">Basecamp</div>
    <div style="padding:26px 28px;color:#1b1e26;font-size:15px;line-height:1.6;">{body}</div>
    <div style="padding:16px 28px;border-top:1px solid #eef0f4;color:#8b93a2;font-size:12px;">
      You're receiving this because you're involved in this work on Basecamp.
    </div>
  </div>
</div>"""


def _button(label: str, url: str) -> str:
    return (
        f'<a href="{url}" style="display:inline-block;margin-top:18px;background:#4f46e5;'
        f'color:#ffffff;text-decoration:none;padding:10px 18px;border-radius:10px;'
        f'font-weight:600;font-size:14px;">{label}</a>'
    )


def _strip_html(value: str | None) -> str:
    """Plain-text version of sanitized HTML, for the text/* part of an email."""
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return re.sub(r"\s+([,.!?;:])", r"\1", text)  # drop space before punctuation


def _summary_row(label: str, value_html: str) -> str:
    return (
        f'<tr><td style="color:#8b93a2;padding:4px 0;width:120px;vertical-align:top;'
        f'font-size:13px;">{label}</td>'
        f'<td style="color:#1b1e26;padding:4px 0;font-size:14px;">{value_html}</td></tr>'
    )


def _summary_html(summary: dict) -> str:
    """Render the task-summary panel from a notification's summary dict."""
    status = html.escape(str(summary.get("status") or ""))
    rows = [
        _summary_row(
            "Status",
            f'<span style="display:inline-block;background:#eef0ff;color:#4f46e5;'
            f'padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;">{status}</span>',
        ),
        _summary_row("Assigned to", html.escape(str(summary.get("assignees") or "Unassigned"))),
    ]
    if summary.get("due"):
        rows.append(_summary_row("Due", html.escape(str(summary["due"]))))
    if summary.get("notes"):
        rows.append(_summary_row("Notes", html.escape(str(summary["notes"]))))
    rows.append(_summary_row("Comments", str(summary.get("comments", 0))))
    return (
        '<div style="border:1px solid #e6e8ee;border-radius:10px;padding:14px 16px;'
        'margin:18px 0;background:#fafbfc;">'
        '<div style="font-size:11px;text-transform:uppercase;letter-spacing:.06em;'
        'color:#8b93a2;margin-bottom:8px;font-weight:700;">Task summary</div>'
        f'<table style="width:100%;border-collapse:collapse;">{"".join(rows)}</table>'
        "</div>"
    )


def _send_smtp(to: str, subject: str, html: str, text: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.from_address
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    if settings.smtp_starttls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)


class EmailSendError(Exception):
    """A transport (e.g. the Resend HTTP API) returned a non-success status."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code


async def _send_resend(to: str, subject: str, html: str, text: str) -> None:
    """Send via the Resend HTTP API. Raises EmailSendError on a non-2xx response."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.from_address,
                "to": [to],
                "subject": subject,
                "html": html,
                "text": text,
            },
        )
    # Only a 2xx is a real accept; treat 3xx (unexpected redirect) as a failure too.
    if not 200 <= resp.status_code < 300:
        raise EmailSendError(resp.status_code, resp.text[:300])


def _active_transport() -> str | None:
    """Which transport to use, or None for dev-log mode.

    Provider is explicit: with EMAIL_PROVIDER=resend a missing key means dev-log,
    NOT a silent fall-back to SMTP (which would keep using the path we're retiring).
    """
    if settings.email_provider == "resend":
        return "resend" if settings.resend_api_key else None
    if settings.smtp_host:
        return "smtp"
    return None


def describe_transport() -> str:
    """Human label for the active transport (used in the startup log)."""
    transport = _active_transport()
    if transport == "resend":
        return "Resend (API)"
    if transport == "smtp":
        return f"SMTP via {settings.smtp_host}"
    return "dev-log (no provider configured)"


def resend_from_unset() -> bool:
    """True when Resend is active but EMAIL_FROM is unset.

    Then ``from_address`` falls back to the placeholder ``smtp_from`` default, whose
    domain isn't verified on Resend, so every send is rejected (4xx). Surfaced as a
    loud startup warning so this misconfig isn't a silent dead-letter.
    """
    return _active_transport() == "resend" and not settings.email_from


def _is_permanent(exc: Exception) -> bool:
    """True for failures that retrying won't fix (bad auth, refused recipient, 4xx/5xx)."""
    if isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused)):
        return True
    if isinstance(exc, EmailSendError):
        # 4xx (bad request / from / recipient) won't fix by retrying; 429 + 5xx are transient.
        return 400 <= exc.status_code < 500 and exc.status_code != 429
    code = getattr(exc, "smtp_code", None)
    return isinstance(code, int) and 500 <= code < 600


async def send_email(to: str, subject: str, html: str, text: str) -> str:
    """Send (or, in dev mode, log) one email with retry/backoff. Never raises.

    Returns one of:
      "sent"      — delivered (or logged in dev mode),
      "transient" — all attempts failed on retryable errors,
      "permanent" — failed on an error retrying won't fix (so the outbox can stop
                    immediately instead of burning every attempt).
    """
    transport = _active_transport()
    if transport is None:
        logger.info("[email:dev] to=%s | %s\n%s", to, subject, text)
        return "sent"

    attempts = max(1, settings.email_max_retries)
    for attempt in range(1, attempts + 1):
        try:
            if transport == "resend":
                await _send_resend(to, subject, html, text)
            else:
                await asyncio.to_thread(_send_smtp, to, subject, html, text)
            logger.info("[email] sent via=%s to=%s | %s", transport, to, subject)
            return "sent"
        except Exception as exc:  # noqa: BLE001 - email must never break the caller
            permanent = _is_permanent(exc)
            done = permanent or attempt == attempts
            log = logger.warning if done else logger.info
            log(
                "[email] attempt %s/%s via=%s failed to=%s | %s | %s",
                attempt, attempts, transport, to, subject, exc,
            )
            if done:
                return "permanent" if permanent else "transient"
            await asyncio.sleep(settings.email_retry_backoff_seconds * (2 ** (attempt - 1)))
    return "transient"


# --- Durable outbox --------------------------------------------------------

async def enqueue_email(to: str, subject: str, html: str, text: str, kind: str) -> None:
    """Persist an email for the background worker to deliver (with retries)."""
    if _active_transport() is None:
        logger.info("[email:dev] to=%s | %s\n%s", to, subject, text)
        return
    await PendingEmail(to=to, subject=subject, html=html, text=text, kind=kind).insert()
    logger.info("[email] queued kind=%s to=%s | %s", kind, to, subject)


async def process_outbox() -> int:
    """Try to deliver due queued emails. Returns how many were delivered this pass."""
    pending = (
        await PendingEmail.find(PendingEmail.status == "pending")
        .sort("created_at")
        .limit(50)
        .to_list()
    )
    now = datetime.now(timezone.utc)
    delivered = 0
    for row in pending:
        due = row.next_attempt_at
        if due is not None:
            if due.tzinfo is None:  # Mongo round-trips datetimes as naive UTC
                due = due.replace(tzinfo=timezone.utc)
            if due > now:
                continue
        status = await send_email(row.to, row.subject, row.html, row.text)
        if status == "sent":
            await row.delete()
            delivered += 1
            continue
        # Failed: back off and try again later, or give up — immediately on a
        # permanent error, otherwise once the attempt cap is hit.
        row.attempts += 1
        row.last_error = "send failed (see [email] attempt logs)"
        if status == "permanent" or row.attempts >= settings.outbox_max_attempts:
            row.status = "failed"
            logger.warning(
                "[email] giving up (%s) after %s attempts to=%s | %s",
                status, row.attempts, row.to, row.subject,
            )
        else:
            backoff = settings.email_retry_backoff_seconds * (2 ** row.attempts)
            row.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
        await row.save()
    return delivered


async def run_outbox_loop() -> None:
    """Background loop (started in the app lifespan): drain the outbox on an interval."""
    interval = max(2, settings.outbox_poll_seconds)
    while True:
        try:
            await asyncio.sleep(interval)
            delivered = await process_outbox()
            if delivered:
                logger.info("[email] outbox delivered %s queued email(s)", delivered)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("[email] outbox loop error: %s", exc)


# --- Concrete emails -------------------------------------------------------

async def send_otp_email(to: str, name: str, code: str, purpose: str) -> bool:
    """Send a signup/reset code inline (the user is waiting). Returns True if it
    went out.

    The code is a short-lived secret, so a failed send is deliberately NOT queued
    to the durable outbox (which would store the code at rest) — the caller asks
    the user to request a new code instead. The code is also kept OUT of the
    subject: subjects are logged, and a code in the subject reads as phishing to
    spam filters.
    """
    is_signup = purpose == "signup"
    heading = "Confirm your email" if is_signup else "Reset your password"
    lead = (
        "Welcome to Basecamp! Use the code below to verify your email address."
        if is_signup
        else "Use the code below to reset your password."
    )
    body = (
        f"<p>Hi {name},</p><p>{lead}</p>"
        f'<div style="margin:18px 0;font-size:30px;font-weight:800;letter-spacing:8px;'
        f'color:#1b1e26;">{code}</div>'
        f"<p style='color:#8b93a2;font-size:13px;'>This code expires in "
        f"{settings.otp_expire_minutes} minutes. If you didn't request it, you can ignore this email.</p>"
    )
    text = f"{heading}\n\nHi {name},\n{lead}\n\nCode: {code}\n(expires in {settings.otp_expire_minutes} minutes)"
    html = _LAYOUT.format(body=body)
    return await send_email(to, heading, html, text) == "sent"


async def send_card_notification(
    to: str,
    recipient_name: str,
    actor_name: str,
    action: str,
    card_title: str,
    team_name: str,
    url: str,
    summary: dict | None = None,
    message_html: str | None = None,
) -> None:
    """A card/@mention notification: who did what, the message they wrote (if any),
    and a snapshot of the task. Plain-text fields are escaped; ``message_html`` is
    already sanitized (clean_html) upstream, so it's embedded as-is."""
    r_name = html.escape(recipient_name or "")
    a_name = html.escape(actor_name or "")
    c_title = html.escape(card_title or "")
    t_name = html.escape(team_name or "")
    act = html.escape(action or "")

    message_block = ""
    if message_html:
        message_block = (
            '<div style="margin:16px 0;padding:12px 16px;border-left:3px solid #4f46e5;'
            'background:#f7f8fb;border-radius:0 8px 8px 0;font-size:14px;color:#1b1e26;">'
            f'<div style="font-size:12px;color:#8b93a2;margin-bottom:6px;">{a_name} wrote</div>'
            f"{message_html}"
            "</div>"
        )

    summary_block = _summary_html(summary) if summary else ""

    body = (
        f"<p>Hi {r_name},</p>"
        f"<p><strong>{a_name}</strong> {act} <strong>{c_title}</strong> in <em>{t_name}</em>.</p>"
        f"{message_block}"
        f"{summary_block}"
        f"{_button('Open the card', url)}"
    )

    lines = [f"{actor_name} {action} {card_title} in {team_name}.", ""]
    if message_html:
        lines += [f"{actor_name} wrote:", _strip_html(message_html), ""]
    if summary:
        lines.append("Task summary:")
        lines.append(f"- Status: {summary.get('status', '')}")
        lines.append(f"- Assigned to: {summary.get('assignees', 'Unassigned')}")
        if summary.get("due"):
            lines.append(f"- Due: {summary['due']}")
        if summary.get("notes"):
            lines.append(f"- Notes: {summary['notes']}")
        lines.append(f"- Comments: {summary.get('comments', 0)}")
        lines.append("")
    lines.append(f"Open: {url}")
    text = "\n".join(lines)

    subject = f"{actor_name} {action} {card_title}"
    await enqueue_email(to, subject, _LAYOUT.format(body=body), text, "notification")


async def send_digest_email(to: str, name: str, items: list[dict]) -> None:
    """One summary email batching several updates for a digest-mode recipient.

    Each item shows who did what to which card, plus a short message snippet when
    the event was a comment/@mention.
    """
    def _row(i: dict) -> str:
        line = (
            f"<li style='margin:10px 0;'><strong>{html.escape(i['actor_name'])}</strong> "
            f"{html.escape(i['action'])} "
            f'<a href="{i["url"]}" style="color:#4f46e5;text-decoration:none;">'
            f"{html.escape(i['card_title'])}</a> "
            f"<span style='color:#8b93a2;'>in {html.escape(i['team_name'])}</span>"
        )
        if i.get("message"):
            line += (
                "<div style='color:#5b6472;font-size:13px;margin-top:3px;'>"
                f"“{html.escape(i['message'])}”</div>"
            )
        return line + "</li>"

    rows = "".join(_row(i) for i in items)
    body = (
        f"<p>Hi {html.escape(name)},</p><p>Here's what happened on your cards:</p>"
        f"<ul style='padding-left:18px;margin:10px 0;'>{rows}</ul>"
    )

    text_lines = []
    for i in items:
        line = f"- {i['actor_name']} {i['action']} {i['card_title']} ({i['team_name']}) {i['url']}"
        if i.get("message"):
            line += f"\n    “{i['message']}”"
        text_lines.append(line)
    text = "\n".join(text_lines)

    await enqueue_email(
        to, f"Your Basecamp digest ({len(items)} updates)", _LAYOUT.format(body=body), text, "digest"
    )
