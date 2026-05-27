from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.direct_email_schema import DirectEmailClassificationOutput
from app.services.direct_email_watcher_service import DirectEmailWatcherService
from app.services.telegram_direct_email_formatter import TelegramDirectEmailFormatter


class _FakeGmailService:
    def __init__(self, candidates=None, raise_on_create_for=None):
        self._candidates = candidates or []
        self.raise_on_create_for = set(raise_on_create_for or [])

    def fetch_direct_email_candidates(self, user, db, max_results, lookback_hours):
        return self._candidates

    def create_gmail_reply_draft(self, user, db, original_email, draft_body):
        message_id = str(original_email.get("id"))
        if message_id in self.raise_on_create_for:
            raise RuntimeError("gmail draft create failed")
        return f"draft-{message_id}"


class _FakeAgentService:
    def classify_direct_email(self, email_content):
        if "CLASSIFY_FAIL" in email_content:
            raise RuntimeError("classification failed")
        if "NOT_DIRECT" in email_content:
            return DirectEmailClassificationOutput(
                is_direct_email=False,
                needs_reply=False,
                urgency="low",
                category="newsletter",
                summary="Automated content.",
                reason="Bulk email.",
                suggested_action="Archive.",
                reply_intent="none",
            )
        if "NO_REPLY" in email_content:
            return DirectEmailClassificationOutput(
                is_direct_email=True,
                needs_reply=False,
                urgency="low",
                category="announcement",
                summary="Informational note.",
                reason="No direct question.",
                suggested_action="No action needed.",
                reply_intent="none",
            )
        return DirectEmailClassificationOutput(
            is_direct_email=True,
            needs_reply=True,
            urgency="medium",
            category="follow_up",
            summary="Sender asks for a response.",
            reason="Direct question.",
            suggested_action="Reply with requested details.",
            reply_intent="Provide a concise follow-up.",
        )

    def generate_direct_email_reply(self, *, email_content, classification):
        if "DRAFT_FAIL" in email_content:
            raise RuntimeError("draft generation failed")
        return "Thanks for your message. I will share [DETAILS] by [DATE]."


class _FakeTelegramService:
    def send_message(self, chat_id, text, parse_mode=None):
        return {"ok": True}


def _build_service(candidates=None, raise_on_create_for=None):
    return DirectEmailWatcherService(
        gmail_service=_FakeGmailService(candidates=candidates, raise_on_create_for=raise_on_create_for),
        agent_service=_FakeAgentService(),
        telegram_service=_FakeTelegramService(),
        formatter=TelegramDirectEmailFormatter(),
    )


def test_prefilter_rejects_automated_sender_and_headers():
    user = SimpleNamespace(email="me@example.com")
    automated = {
        "sender_email": "no-reply@linkedin.com",
        "subject": "Your weekly update",
        "list_unsubscribe_header": "<mailto:unsubscribe@example.com>",
        "auto_submitted_header": "auto-generated",
        "precedence_header": "bulk",
    }
    assert DirectEmailWatcherService.is_likely_direct_human_email(candidate=automated, user=user) is False


def test_prefilter_accepts_likely_human_direct_email():
    user = SimpleNamespace(email="me@example.com")
    candidate = {
        "sender_email": "recruiter@example.com",
        "subject": "Quick follow-up about your interview",
        "list_unsubscribe_header": "",
        "auto_submitted_header": "",
        "precedence_header": "",
    }
    assert DirectEmailWatcherService.is_likely_direct_human_email(candidate=candidate, user=user) is True


def test_process_user_records_expected_statuses(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        email="me@example.com",
        telegram_chat_id="chat-1",
        encrypted_access_token="x",
        encrypted_refresh_token="y",
    )
    now = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    candidates = [
        {"id": "1", "threadId": "t1", "sender_email": "no-reply@github.com", "subject": "Alert", "body_text": "Ignored"},
        {"id": "2", "threadId": "t2", "sender_email": "a@example.com", "subject": "FYI", "body_text": "NOT_DIRECT"},
        {"id": "3", "threadId": "t3", "sender_email": "b@example.com", "subject": "Info", "body_text": "NO_REPLY"},
        {"id": "4", "threadId": "t4", "sender_email": "c@example.com", "subject": "Need response", "body_text": "normal"},
        {"id": "5", "threadId": "t5", "sender_email": "d@example.com", "subject": "Need response", "body_text": "normal"},
        {"id": "6", "threadId": "t6", "sender_email": "e@example.com", "subject": "Need response", "body_text": "CLASSIFY_FAIL"},
        {"id": "7", "threadId": "t7", "sender_email": "f@example.com", "subject": "Need response", "body_text": "DRAFT_FAIL"},
    ]
    service = _build_service(candidates=candidates, raise_on_create_for={"5"})
    statuses = []

    def _fake_upsert_email_row(db, user, candidate):
        return SimpleNamespace(
            id=f"email-{candidate['id']}",
            user_id=user.id,
            gmail_message_id=candidate["id"],
            gmail_thread_id=candidate.get("threadId") or "",
        )

    monkeypatch.setattr(service, "_upsert_email_row", _fake_upsert_email_row)
    monkeypatch.setattr(service, "_is_already_processed", lambda db, email_row: False)
    monkeypatch.setattr(service, "_already_has_gmail_draft", lambda db, email_row: False)
    monkeypatch.setattr(service, "_record_draft_reply", lambda db, email_row, draft_body, gmail_draft_id: None)
    monkeypatch.setattr(service, "_create_event", lambda **kwargs: statuses.append(kwargs["status"]))

    result = service._process_user(db=object(), user=user, now_utc=now)
    assert statuses == [
        "filtered_out",
        "not_direct",
        "no_reply_needed",
        "draft_created",
        "draft_creation_failed",
        "classification_failed",
        "draft_generation_failed",
    ]
    assert result["processed_emails"] == 7
    assert result["created_drafts"] == 1
    assert result["failures"] == 3


def test_process_user_skips_when_already_processed(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        email="me@example.com",
        telegram_chat_id="chat-1",
        encrypted_access_token="x",
        encrypted_refresh_token="y",
    )
    candidates = [{"id": "1", "threadId": "t1", "sender_email": "a@example.com", "subject": "Hello", "body_text": "Body"}]
    service = _build_service(candidates=candidates)
    calls = {"events": 0}

    monkeypatch.setattr(
        service,
        "_upsert_email_row",
        lambda db, user, candidate: SimpleNamespace(
            id="email-1",
            user_id=user.id,
            gmail_message_id="1",
            gmail_thread_id="t1",
        ),
    )
    monkeypatch.setattr(service, "_is_already_processed", lambda db, email_row: True)
    monkeypatch.setattr(service, "_create_event", lambda **kwargs: calls.__setitem__("events", calls["events"] + 1))

    result = service._process_user(db=object(), user=user, now_utc=datetime.now(timezone.utc))
    assert result == {"processed_emails": 0, "created_drafts": 0, "failures": 0}
    assert calls["events"] == 0
