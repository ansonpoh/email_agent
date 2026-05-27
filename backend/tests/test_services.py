from datetime import datetime
from uuid import uuid4

import pytest

from app.config import settings
from fastapi import HTTPException
from app.services.agent_service import AgentService
from app.services.digest_service import DigestService
from app.services.draft_service import DraftService


def _fake_completion(parsed):
    class _Message:
        def __init__(self, parsed_value):
            self.parsed = parsed_value

    class _Choice:
        def __init__(self, parsed_value):
            self.message = _Message(parsed_value)

    class _Completion:
        def __init__(self, parsed_value):
            self.choices = [_Choice(parsed_value)]

    return _Completion(parsed)


def test_agent_service_structured_output(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_max_retries", 1)

    service = AgentService()
    expected = {
        "category": "urgent",
        "priority_score": 5,
        "summary": "Action needed.",
        "key_points": ["Need reply"],
        "extracted_tasks": ["Reply"],
        "extracted_deadlines": ["Tomorrow"],
        "suggested_action": "Draft reply",
        "confidence_score": 0.9,
    }

    class _FakeClient:
        class beta:
            class chat:
                class completions:
                    @staticmethod
                    def parse(**_kwargs):
                        from app.schemas.email_schema import EmailAnalysisOutput

                        return _fake_completion(EmailAnalysisOutput(**expected))

    monkeypatch.setattr(service, "_client_instance", lambda: _FakeClient())
    result = service.analyse_email(subject="Urgent", body_text="Please reply ASAP")
    assert result.priority_score == 5
    assert result.category == "urgent"


def test_agent_service_retries_on_parse_failure(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_max_retries", 1)

    service = AgentService()
    calls = {"count": 0}

    class _FakeClient:
        class beta:
            class chat:
                class completions:
                    @staticmethod
                    def parse(**_kwargs):
                        calls["count"] += 1
                        if calls["count"] == 1:
                            return _fake_completion(None)
                        from app.schemas.email_schema import EmailAnalysisOutput

                        return _fake_completion(
                            EmailAnalysisOutput(
                                category="general",
                                priority_score=3,
                                summary="OK",
                                key_points=[],
                                extracted_tasks=[],
                                extracted_deadlines=[],
                                suggested_action="Review",
                                confidence_score=0.5,
                            )
                        )

    monkeypatch.setattr(service, "_client_instance", lambda: _FakeClient())
    result = service.analyse_email(subject="Hello", body_text="FYI")
    assert result.category == "general"
    assert calls["count"] == 2


def test_agent_service_raises_when_api_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    service = AgentService()
    with pytest.raises(HTTPException):
        service.analyse_email(subject="Hi", body_text="Body")


def test_agent_service_today_summary_structured_output(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_max_retries", 1)

    service = AgentService()

    class _FakeClient:
        class beta:
            class chat:
                class completions:
                    @staticmethod
                    def parse(**_kwargs):
                        from app.schemas.email_schema import TodaySummaryOutput

                        return _fake_completion(
                            TodaySummaryOutput(
                                overview="Two high-priority threads need action.",
                                priority_items=["Legal review request", "Contract renewal notice"],
                                suggested_actions=["Reply to legal team", "Schedule renewal follow-up"],
                            )
                        )

    monkeypatch.setattr(service, "_client_instance", lambda: _FakeClient())
    result = service.summarize_emails_for_today(
        emails=[{"sender_email": "a@example.com", "subject": "Hi", "received_at": "2026-05-25T10:00:00Z"}],
        user_timezone="UTC",
    )
    assert "high-priority" in result.overview
    assert len(result.priority_items) == 2


def test_agent_service_today_summary_retries_on_parse_failure(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_max_retries", 1)

    service = AgentService()
    calls = {"count": 0}

    class _FakeClient:
        class beta:
            class chat:
                class completions:
                    @staticmethod
                    def parse(**_kwargs):
                        calls["count"] += 1
                        if calls["count"] == 1:
                            return _fake_completion(None)
                        from app.schemas.email_schema import TodaySummaryOutput

                        return _fake_completion(
                            TodaySummaryOutput(
                                overview="Inbox is mostly informational.",
                                priority_items=[],
                                suggested_actions=["Archive newsletters"],
                            )
                        )

    monkeypatch.setattr(service, "_client_instance", lambda: _FakeClient())
    result = service.summarize_emails_for_today(
        emails=[{"sender_email": "a@example.com", "subject": "FYI"}],
        user_timezone="Asia/Singapore",
    )
    assert result.overview == "Inbox is mostly informational."
    assert calls["count"] == 2


def test_agent_service_today_summary_raises_when_api_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    service = AgentService()
    with pytest.raises(HTTPException):
        service.summarize_emails_for_today(emails=[{"subject": "Hi"}], user_timezone="UTC")


def test_agent_service_digest_summary_structured_output(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_max_retries", 1)

    service = AgentService()

    class _FakeClient:
        class beta:
            class chat:
                class completions:
                    @staticmethod
                    def parse(**_kwargs):
                        from app.schemas.digest_schema import AIDigestSummaryOutput, DigestImportantEmail

                        return _fake_completion(
                            AIDigestSummaryOutput(
                                overview="Two urgent threads need attention.",
                                important_emails=[
                                    DigestImportantEmail(
                                        source_index=1,
                                        reason="Payment is overdue.",
                                        recommended_action="Reply with payment confirmation timeline.",
                                    )
                                ],
                                suggested_actions=["Reply to finance thread."],
                                additional_notes=["One thread includes a due date this week."],
                            )
                        )

    monkeypatch.setattr(service, "_client_instance", lambda: _FakeClient())
    result = service.summarize_digest_window(
        emails=[{"sender_email": "a@example.com", "subject": "Invoice", "received_at": "2026-05-25T10:00:00Z"}],
        user_timezone="UTC",
    )
    assert "urgent" in result.overview
    assert result.important_emails[0].source_index == 1


def test_agent_service_digest_summary_retries_on_parse_failure(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_max_retries", 1)

    service = AgentService()
    calls = {"count": 0}

    class _FakeClient:
        class beta:
            class chat:
                class completions:
                    @staticmethod
                    def parse(**_kwargs):
                        calls["count"] += 1
                        if calls["count"] == 1:
                            return _fake_completion(None)
                        from app.schemas.digest_schema import AIDigestSummaryOutput

                        return _fake_completion(
                            AIDigestSummaryOutput(
                                overview="No urgent risks.",
                                important_emails=[],
                                suggested_actions=["Archive newsletters."],
                                additional_notes=[],
                            )
                        )

    monkeypatch.setattr(service, "_client_instance", lambda: _FakeClient())
    result = service.summarize_digest_window(
        emails=[{"sender_email": "a@example.com", "subject": "FYI"}],
        user_timezone="Asia/Singapore",
    )
    assert result.overview == "No urgent risks."
    assert calls["count"] == 2


def test_agent_service_digest_summary_raises_when_api_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    service = AgentService()
    with pytest.raises(HTTPException):
        service.summarize_digest_window(emails=[{"subject": "Hi"}], user_timezone="UTC")


def test_digest_service_builds_ai_text():
    service = DigestService()
    from app.schemas.digest_schema import AIDigestSummaryOutput, DigestImportantEmail

    output = service.build_digest(
        email_rows=[
            {
                "id": uuid4(),
                "subject": "Test",
                "sender_email": "a@example.com",
                "received_at": datetime.fromisoformat("2026-05-26T09:00:00+00:00"),
                "is_read": False,
                "summary": "Summary",
                "priority_score": 4,
                "extracted_deadlines": ["Tomorrow"],
                "suggested_action": "Reply",
            },
            {
                "id": uuid4(),
                "subject": "Info",
                "sender_email": "b@example.com",
                "received_at": datetime.fromisoformat("2026-05-26T08:00:00+00:00"),
                "is_read": True,
                "summary": "Informational update.",
                "priority_score": 2,
                "extracted_deadlines": [],
                "suggested_action": "",
            },
        ],
        ai_summary=AIDigestSummaryOutput(
            overview="One high-priority thread requires a quick response.",
            important_emails=[
                DigestImportantEmail(
                    source_index=1,
                    reason="Contains an explicit deadline.",
                    recommended_action="Respond and confirm delivery timeline.",
                )
            ],
            suggested_actions=["Reply to the first thread."],
            additional_notes=["Watch for follow-up from finance."],
        ),
        period_start=datetime.fromisoformat("2026-05-26T00:00:00+00:00"),
        period_end=datetime.fromisoformat("2026-05-26T10:00:00+00:00"),
        user_timezone="UTC",
    )

    assert "Date and time:" in output.digest_text
    assert "Summary:" in output.digest_text
    assert "Top Important Emails:" in output.digest_text
    assert "Coverage window:" not in output.digest_text
    assert "Suggested actions:" in output.digest_text
    assert "Additional important context:" in output.digest_text
    assert output.digest_text.index("Additional important context:") < output.digest_text.index("Suggested actions:")
    assert len(output.important_emails) == 1
    assert len(output.priority_emails) == 1
    assert len(output.deadlines) == 1


def test_digest_service_empty_window_message():
    service = DigestService()
    from app.schemas.digest_schema import AIDigestSummaryOutput

    output = service.build_digest(
        email_rows=[],
        ai_summary=AIDigestSummaryOutput(
            overview="No new important activity.",
            important_emails=[],
            suggested_actions=[],
            additional_notes=[],
        ),
        period_start=datetime.fromisoformat("2026-05-26T00:00:00+00:00"),
        period_end=datetime.fromisoformat("2026-05-26T10:00:00+00:00"),
        user_timezone="UTC",
    )
    assert "Top Important Emails:\n- None" in output.digest_text


def test_draft_service_structured_output(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_max_retries", 1)

    service = DraftService(gmail_service=None)

    class _FakeClient:
        class beta:
            class chat:
                class completions:
                    @staticmethod
                    def parse(**_kwargs):
                        from app.schemas.agent_schema import DraftReplyOutput

                        return _fake_completion(
                            DraftReplyOutput(
                                subject="Re: Status update",
                                body="Thanks for the update. I will review and get back shortly.",
                                tone="friendly",
                                requires_user_review=False,
                            )
                        )

    monkeypatch.setattr(service, "_client_instance", lambda: _FakeClient())
    result = service.generate_draft(subject="Status update", body_text="Please respond", tone="professional")
    assert result.subject == "Re: Status update"
    assert result.tone == "professional"
    assert result.requires_user_review is True


def test_draft_service_retries_on_parse_failure(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_max_retries", 1)

    service = DraftService(gmail_service=None)
    calls = {"count": 0}

    class _FakeClient:
        class beta:
            class chat:
                class completions:
                    @staticmethod
                    def parse(**_kwargs):
                        calls["count"] += 1
                        if calls["count"] == 1:
                            return _fake_completion(None)
                        from app.schemas.agent_schema import DraftReplyOutput

                        return _fake_completion(
                            DraftReplyOutput(
                                subject="Re: Hello",
                                body="Thanks for the note. I will follow up shortly.",
                                tone="professional",
                                requires_user_review=True,
                            )
                        )

    monkeypatch.setattr(service, "_client_instance", lambda: _FakeClient())
    result = service.generate_draft(subject="Hello", body_text="Body")
    assert result.subject == "Re: Hello"
    assert calls["count"] == 2
