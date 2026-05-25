from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AgentActionRead(BaseModel):
    id: UUID
    email_id: UUID
    action_type: str
    status: str
    suggested_payload: dict
    requires_approval: bool
    approved_by_user: bool | None
    executed_at: datetime | None
    execution_payload: dict
    execution_error: str | None
    telegram_chat_id: str | None
    telegram_message_id: str | None
    telegram_callback_data: str | None
    telegram_callback_handled_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentActionDecision(BaseModel):
    decision: Literal["approve", "reject"]
