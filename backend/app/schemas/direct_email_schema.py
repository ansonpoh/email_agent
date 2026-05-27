from typing import Literal

from pydantic import BaseModel


class DirectEmailClassificationOutput(BaseModel):
    is_direct_email: bool
    needs_reply: bool
    urgency: Literal["low", "medium", "high"]
    category: str
    summary: str
    reason: str
    suggested_action: str
    reply_intent: str


class DirectEmailDraftOutput(BaseModel):
    draft_reply_body: str
