import pytest
from pydantic import ValidationError

from app.schemas.agent_schema import DraftReplyOutput
from app.schemas.digest_schema import DigestImportantEmail, DigestOutput
from app.schemas.email_schema import EmailAnalysisOutput
from app.schemas.followup_schema import FollowupExtractionOutput
from app.schemas.inbox_schema import InboxQuestionAnswerOutput


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
    assert output.overview == ""
    assert output.important_emails == []
    assert output.priority_emails == []
    assert output.suggested_next_steps == []


def test_digest_important_emails_limit():
    with pytest.raises(ValidationError):
        DigestOutput(
            digest_text="hello",
            important_emails=[
                {
                    "email_id": "f5af2c78-709e-4f8e-86a2-ef47b5600cb0",
                    "sender_email": "a@example.com",
                    "subject": "A",
                    "status": "unread",
                    "summary": "s",
                    "priority_score": 5,
                    "reason": "r",
                    "recommended_action": "act",
                    "deadlines": [],
                },
                {
                    "email_id": "f5af2c78-709e-4f8e-86a2-ef47b5600cb1",
                    "sender_email": "b@example.com",
                    "subject": "B",
                    "status": "unread",
                    "summary": "s",
                    "priority_score": 4,
                    "reason": "r",
                    "recommended_action": "act",
                    "deadlines": [],
                },
                {
                    "email_id": "f5af2c78-709e-4f8e-86a2-ef47b5600cb2",
                    "sender_email": "c@example.com",
                    "subject": "C",
                    "status": "unread",
                    "summary": "s",
                    "priority_score": 3,
                    "reason": "r",
                    "recommended_action": "act",
                    "deadlines": [],
                },
                {
                    "email_id": "f5af2c78-709e-4f8e-86a2-ef47b5600cb3",
                    "sender_email": "d@example.com",
                    "subject": "D",
                    "status": "unread",
                    "summary": "s",
                    "priority_score": 2,
                    "reason": "r",
                    "recommended_action": "act",
                    "deadlines": [],
                },
            ],
        )


def test_digest_ai_source_index_must_be_positive():
    with pytest.raises(ValidationError):
        DigestImportantEmail(source_index=0, reason="x", recommended_action="y")


def test_draft_reply_output_requires_user_review_field():
    draft = DraftReplyOutput(
        subject="Re: Example",
        body="Body",
        tone="professional",
        requires_user_review=True,
    )
    assert draft.requires_user_review is True


def test_followup_extraction_limits_items():
    with pytest.raises(ValidationError):
        FollowupExtractionOutput(
            items=[
                {
                    "task": f"Task {idx}",
                    "due_at_iso": None,
                    "due_label": None,
                    "needs_reply": False,
                    "confidence_score": 0.5,
                    "source_quote": None,
                }
                for idx in range(9)
            ]
        )


def test_inbox_answer_citation_source_index_must_be_positive():
    with pytest.raises(ValidationError):
        InboxQuestionAnswerOutput(
            answer="x",
            citations=[{"source_index": 0, "reason": "bad"}],
            suggested_actions=[],
        )
