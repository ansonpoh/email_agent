from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    google_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    encrypted_access_token: Mapped[str] = mapped_column(String, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(String, nullable=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_link_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    telegram_link_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    digest_frequency: Mapped[str] = mapped_column(String(32), default="hourly", nullable=False)
    scheduled_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    digest_schedule_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    digest_schedule_times: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    urgent_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    emails = relationship("Email", back_populates="user", cascade="all, delete-orphan")
    digests = relationship("Digest", back_populates="user", cascade="all, delete-orphan")
    rules = relationship("UserRule", back_populates="user", cascade="all, delete-orphan")
