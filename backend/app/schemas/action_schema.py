from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AgentActionRead(BaseModel):
    id: int
    email_id: int
    action_type: str
    status: str
    suggested_payload: dict
    requires_approval: bool
    approved_by_user: bool | None
    executed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentActionDecision(BaseModel):
    decision: Literal["approve", "reject"]
