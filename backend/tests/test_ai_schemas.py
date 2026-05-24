import pytest
from pydantic import ValidationError

from app.schemas.agent_schema import DraftReplyOutput
from app.schemas.digest_schema import DigestOutput
from app.schemas.email_schema import EmailAnalysisOutput


def test_email_analysis_output_validates_ranges():
    with pytest.raises(ValidationError):
        EmailAnalysisOutput(
            category="general",
            priority_score=6,
            summary="x",
            key_points=[],
            extracted_tasks=[],
            extracted_deadlines=[],
            suggested_action="reply",
            confidence_score=0.5,
        )

    with pytest.raises(ValidationError):
        EmailAnalysisOutput(
            category="general",
            priority_score=3,
            summary="x",
            key_points=[],
            extracted_tasks=[],
            extracted_deadlines=[],
            suggested_action="reply",
            confidence_score=1.5,
        )


def test_digest_output_shape():
    output = DigestOutput(digest_text="hello")
    assert output.priority_emails == []
    assert output.suggested_next_steps == []


def test_draft_reply_output_requires_user_review_field():
    draft = DraftReplyOutput(
        subject="Re: Example",
        body="Body",
        tone="professional",
        requires_user_review=True,
    )
    assert draft.requires_user_review is True
