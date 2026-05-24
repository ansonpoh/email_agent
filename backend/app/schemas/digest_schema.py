from datetime import datetime

from pydantic import BaseModel, Field


class DigestBucketItem(BaseModel):
    email_id: int
    subject: str
    sender_email: str
    note: str


class DigestOutput(BaseModel):
    priority_emails: list[DigestBucketItem] = Field(default_factory=list)
    needs_reply: list[DigestBucketItem] = Field(default_factory=list)
    deadlines: list[DigestBucketItem] = Field(default_factory=list)
    low_priority: list[DigestBucketItem] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)
    digest_text: str


class DigestGenerateRequest(BaseModel):
    user_id: int


class DigestSendTelegramRequest(BaseModel):
    user_id: int


class DigestRead(BaseModel):
    id: int
    user_id: int
    period_start: datetime
    period_end: datetime
    digest_text: str
    sent_to_telegram: bool
