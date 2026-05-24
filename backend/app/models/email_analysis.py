from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class EmailAnalysis(Base):
    __tablename__ = "email_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id", ondelete="CASCADE"), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    extracted_tasks: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    extracted_deadlines: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    email = relationship("Email", back_populates="analysis")
