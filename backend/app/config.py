import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _normalize_database_url(raw_url: str) -> str:
    # Keep .env unchanged while forcing SQLAlchemy to use psycopg (v3) driver.
    if raw_url.startswith("postgresql+psycopg://"):
        return raw_url
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+psycopg://", 1)
    return raw_url


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_bool(raw: str, default: bool) -> bool:
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_base_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    value = raw_url.strip().rstrip("/")
    return value or None


@dataclass
class Settings:
    app_name: str = os.getenv("APP_NAME", "Gmail Agent Assistant")
    environment: str = os.getenv("ENVIRONMENT", "development")
    backend_host: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
    cors_origins: list[str] = field(
        default_factory=lambda: _parse_csv(
            os.getenv("CORS_ORIGINS", "")
        )
    )

    database_url: str = _normalize_database_url(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5432/email_agent",
        )
    )
    database_schema: str = os.getenv("DATABASE_SCHEMA", "email_agent")
    run_db_migrations_on_startup: bool = _parse_bool(os.getenv("RUN_DB_MIGRATIONS_ON_STARTUP", "true"), True)
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    openai_timeout_seconds: float = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "25"))
    openai_max_retries: int = int(os.getenv("OPENAI_MAX_RETRIES", "2"))

    google_client_id: str | None = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret: str | None = os.getenv("GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )

    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_bot_username: str | None = os.getenv("TELEGRAM_BOT_USERNAME")
    telegram_webhook_base_url: str | None = _normalize_base_url(os.getenv("TELEGRAM_WEBHOOK_BASE_URL"))
    telegram_webhook_secret_token: str | None = os.getenv("TELEGRAM_WEBHOOK_SECRET_TOKEN")
    telegram_default_digest_frequency: str = os.getenv("TELEGRAM_DEFAULT_DIGEST_FREQUENCY", "hourly")
    telegram_default_timezone: str = os.getenv("TELEGRAM_DEFAULT_TIMEZONE", "UTC")
    telegram_default_urgent_alerts_enabled: bool = _parse_bool(
        os.getenv("TELEGRAM_DEFAULT_URGENT_ALERTS_ENABLED", "true"),
        True,
    )
    telegram_urgent_threshold: int = int(os.getenv("TELEGRAM_URGENT_THRESHOLD", "5"))
    telegram_scheduler_enabled: bool = _parse_bool(os.getenv("TELEGRAM_SCHEDULER_ENABLED", "true"), True)
    inproc_scheduler_enabled: bool = _parse_bool(os.getenv("INPROC_SCHEDULER_ENABLED", "true"), True)
    inproc_scheduler_tick_seconds: int = int(os.getenv("INPROC_SCHEDULER_TICK_SECONDS", "60"))
    inproc_scheduler_grace_minutes: int = int(os.getenv("INPROC_SCHEDULER_GRACE_MINUTES", "20"))
    direct_email_watcher_enabled: bool = _parse_bool(os.getenv("DIRECT_EMAIL_WATCHER_ENABLED", "true"), True)
    direct_email_watch_interval_minutes: int = int(os.getenv("DIRECT_EMAIL_WATCH_INTERVAL_MINUTES", "5"))
    direct_email_watch_lookback_hours: int = int(os.getenv("DIRECT_EMAIL_WATCH_LOOKBACK_HOURS", "48"))
    direct_email_watch_max_messages: int = int(os.getenv("DIRECT_EMAIL_WATCH_MAX_MESSAGES", "30"))
    direct_email_watch_notify_no_reply: bool = _parse_bool(
        os.getenv("DIRECT_EMAIL_WATCH_NOTIFY_NO_REPLY", "false"),
        False,
    )

    encryption_key: str = os.getenv("ENCRYPTION_KEY", "CHANGE_ME_WITH_32_CHAR_MIN_SECRET")
    digest_idempotency_window_minutes: int = int(os.getenv("DIGEST_IDEMPOTENCY_WINDOW_MINUTES", "15"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
