from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User


class TelegramLinkService:
    def create_link_token(self, db: Session, user: User) -> dict:
        token = secrets.token_urlsafe(24)
        token_hash = self._hash_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.telegram_link_token_ttl_minutes)

        user.telegram_link_token_hash = token_hash
        user.telegram_link_token_expires_at = expires_at
        if not user.digest_frequency:
            user.digest_frequency = settings.telegram_default_digest_frequency
        if not user.timezone:
            user.timezone = settings.telegram_default_timezone
        db.add(user)
        db.commit()
        db.refresh(user)

        deep_link = None
        if settings.telegram_bot_username:
            deep_link = f"https://t.me/{settings.telegram_bot_username}?start={token}"

        return {"token": token, "expires_at": expires_at, "deep_link": deep_link}

    def confirm_link(self, db: Session, token: str, chat_id: str) -> User | None:
        token_hash = self._hash_token(token)
        now = datetime.now(timezone.utc)
        user = (
            db.query(User)
            .filter(User.telegram_link_token_hash == token_hash)
            .filter(User.telegram_link_token_expires_at.is_not(None))
            .filter(User.telegram_link_token_expires_at >= now)
            .first()
        )
        if not user:
            return None

        user.telegram_chat_id = chat_id
        user.telegram_link_token_hash = None
        user.telegram_link_token_expires_at = None
        user.digest_frequency = user.digest_frequency or settings.telegram_default_digest_frequency
        user.timezone = user.timezone or settings.telegram_default_timezone
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
