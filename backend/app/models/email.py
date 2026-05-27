from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.schema import schema_fk


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(schema_fk("users"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gmail_message_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sender_email: Mapped[str] = mapped_column(String(320), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipients: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="emails")
    analysis = relationship("EmailAnalysis", back_populates="email", uselist=False, cascade="all, delete-orphan")
    actions = relationship("AgentAction", back_populates="email", cascade="all, delete-orphan")
    drafts = relationship("DraftReply", back_populates="email", cascade="all, delete-orphan")
    direct_watch_events = relationship("DirectEmailWatchEvent", back_populates="email", cascade="all, delete-orphan")
