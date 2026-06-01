from pydantic import BaseModel, Field


class InboxAnswerCitation(BaseModel):
    source_index: int = Field(ge=1)
    reason: str


class InboxQuestionAnswerOutput(BaseModel):
    answer: str
    citations: list[InboxAnswerCitation] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list, max_length=3)

