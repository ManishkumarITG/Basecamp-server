"""Application configuration.

Settings are loaded once from environment variables / a local ``.env`` file via
pydantic-settings. Import the cached ``settings`` instance anywhere in the app.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Field names map to environment variables case-insensitively, e.g. the
    ``mongodb_uri`` field is populated from ``MONGODB_URI``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = "Basecamp API"
    api_v1_prefix: str = "/api/v1"

    # --- Database ---
    mongodb_uri: str = "mongodb://localhost:27017"
    db_name: str = "basecamp"

    # --- Auth / JWT ---
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 1 day

    # Throttle the OTP endpoints (verify / resend / forgot / reset).
    # Set RATE_LIMIT_ENABLED=false to turn it off for local testing.
    rate_limit_enabled: bool = True

    # --- CORS ---
    # Comma-separated list of allowed origins, e.g.
    # "http://localhost:5173,http://localhost:3000".
    cors_origins: str = "http://localhost:5173"

    # --- Email / SMTP ---
    # Leave SMTP_HOST blank to run in "dev log" mode: emails (including OTP codes)
    # are written to the server log instead of sent. Set these to send for real.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Basecamp <no-reply@basecamp.local>"
    smtp_starttls: bool = True

    # --- Email provider (transactional) ---
    # "smtp" uses the SMTP_* settings above; "resend" sends via the Resend HTTP API
    # (better deliverability: send from your own verified domain, not a personal
    # Gmail). If the chosen provider's credentials are blank, email falls back to
    # dev-log mode (codes printed to the server log, nothing sent).
    email_provider: str = "smtp"  # "smtp" | "resend"
    resend_api_key: str = ""
    # Canonical From for all mail; falls back to smtp_from when blank. With a
    # provider use a verified-domain address, e.g. "Basecamp <noreply@itgeeks.com>".
    email_from: str = ""

    # Public URL of the frontend, used to build links inside emails.
    app_base_url: str = "http://localhost:5173"

    # --- Email reliability ---
    # Real sends fail intermittently (transient 4xx, dropped connections, timeouts).
    # Total send attempts per email (1 initial + retries) with exponential backoff
    # between them before it's considered failed. e.g. 3 => up to 3 attempts.
    email_max_retries: int = 3
    email_retry_backoff_seconds: float = 1.0  # 1s, 2s, 4s, ...

    # The durable outbox: any email that can't be sent inline is persisted and a
    # background worker retries it on this interval until it delivers (or gives up
    # after outbox_max_attempts). Survives restarts, so nothing is silently dropped.
    outbox_poll_seconds: int = 10
    outbox_max_attempts: int = 8

    # OTP / token lifetime (minutes) for signup verification and password reset.
    otp_expire_minutes: int = 15

    # How often (minutes) to flush batched digest emails for digest-mode users.
    digest_interval_minutes: int = 15

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins into a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def from_address(self) -> str:
        """The From header used by every transport (single source of truth)."""
        return self.email_from or self.smtp_from


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read .env only once)."""
    return Settings()


settings = get_settings()
