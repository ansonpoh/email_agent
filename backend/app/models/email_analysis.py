from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.schema import schema_fk


class EmailAnalysis(Base):
    __tablename__ = "email_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(schema_fk("emails"), ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    extracted_tasks: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    extracted_deadlines: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    urgent_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    email = relationship("Email", back_populates="analysis")
