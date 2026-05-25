from pydantic import BaseModel
from uuid import UUID


class DraftReplyOutput(BaseModel):
    subject: str
    body: str
    tone: str
    requires_user_review: bool


class AgentDecisionLog(BaseModel):
    email_id: UUID
    decision_type: str
    reason: str
    requires_approval: bool
    payload: dict
