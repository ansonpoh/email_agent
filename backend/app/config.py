import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    app_name: str = os.getenv("APP_NAME", "Gmail Agent Assistant")
    environment: str = os.getenv("ENVIRONMENT", "development")
    backend_host: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/email_agent",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    google_client_id: str | None = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret: str | None = os.getenv("GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )

    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")

    encryption_key: str = os.getenv("ENCRYPTION_KEY", "CHANGE_ME_WITH_32_CHAR_MIN_SECRET")


settings = Settings()
