from pydantic import BaseModel, Field


class FollowupExtractionItem(BaseModel):
    task: str = Field(min_length=1, max_length=400)
    due_at_iso: str | None = None
    due_label: str | None = None
    needs_reply: bool = False
    confidence_score: float = Field(ge=0.0, le=1.0)
    source_quote: str | None = None


class FollowupExtractionOutput(BaseModel):
    items: list[FollowupExtractionItem] = Field(default_factory=list, max_length=8)

