"""Shared test fixtures.

Force dev-log email mode for every test so the suite never touches a real SMTP
server even when the developer's .env points at one (e.g. Gmail). Without this,
tests would attempt real sends to fake addresses (slow, flaky, and actually
emailing). Tests read OTPs from the stored user and capture notification
recipients by monkeypatching the email service.
"""

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _force_dev_log_email():
    # Blank out every transport's credentials so _active_transport() is None
    # (dev-log) no matter what the developer's .env configures (SMTP or Resend).
    saved = (settings.smtp_host, settings.resend_api_key, settings.email_provider)
    settings.smtp_host = ""
    settings.resend_api_key = ""
    settings.email_provider = "smtp"
    try:
        yield
    finally:
        settings.smtp_host, settings.resend_api_key, settings.email_provider = saved
