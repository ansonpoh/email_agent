from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DigestBucketItem(BaseModel):
    email_id: UUID
    subject: str
    sender_email: str
    note: str


class DigestImportantEmail(BaseModel):
    source_index: int = Field(ge=1)
    reason: str
    recommended_action: str


class AIDigestSummaryOutput(BaseModel):
    overview: str
    important_emails: list[DigestImportantEmail] = Field(default_factory=list, max_length=3)
    suggested_actions: list[str] = Field(default_factory=list)
    additional_notes: list[str] = Field(default_factory=list)


class DigestImportantEmailDetail(BaseModel):
    email_id: UUID
    sender_email: str
    subject: str
    received_at: datetime | None = None
    status: str
    summary: str
    priority_score: int = Field(ge=1, le=5)
    reason: str
    recommended_action: str
    deadlines: list[str] = Field(default_factory=list)


class DigestOutput(BaseModel):
    overview: str = ""
    important_emails: list[DigestImportantEmailDetail] = Field(default_factory=list, max_length=3)
    suggested_actions: list[str] = Field(default_factory=list)
    additional_notes: list[str] = Field(default_factory=list)

    priority_emails: list[DigestBucketItem] = Field(default_factory=list)
    needs_reply: list[DigestBucketItem] = Field(default_factory=list)
    deadlines: list[DigestBucketItem] = Field(default_factory=list)
    low_priority: list[DigestBucketItem] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)
    digest_text: str


class DigestGenerateRequest(BaseModel):
    user_id: UUID


class DigestSendTelegramRequest(BaseModel):
    user_id: UUID


class DigestRead(BaseModel):
    id: UUID
    user_id: UUID
    period_start: datetime
    period_end: datetime
    digest_text: str
    sent_to_telegram: bool
