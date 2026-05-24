from pydantic import BaseModel


class DraftReplyOutput(BaseModel):
    subject: str
    body: str
    tone: str
    requires_user_review: bool


class AgentDecisionLog(BaseModel):
    email_id: int
    decision_type: str
    reason: str
    requires_approval: bool
    payload: dict
