from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmailAnalysisOutput(BaseModel):
    category: str
    priority_score: int = Field(ge=1, le=5)
    summary: str
    key_points: list[str]
    extracted_tasks: list[str]
    extracted_deadlines: list[str]
    suggested_action: str
    confidence_score: float = Field(ge=0.0, le=1.0)


class EmailBase(BaseModel):
    sender_email: str
    sender_name: str | None = None
    recipients: list[str] = Field(default_factory=list)
    subject: str | None = None
    snippet: str | None = None
    body_text: str
    received_at: datetime
    is_read: bool = False


class EmailRead(EmailBase):
    id: UUID
    user_id: UUID
    gmail_message_id: str
    gmail_thread_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EmailSyncRequest(BaseModel):
    user_id: UUID


class EmailAnalysisResponse(BaseModel):
    email_id: UUID
    analysis: EmailAnalysisOutput


class EmailListResponse(BaseModel):
    items: list[EmailRead]
