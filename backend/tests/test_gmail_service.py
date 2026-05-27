from datetime import datetime, timezone
import base64

from app.services.gmail_service import GmailService
from app.services.token_cipher import TokenCipher


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload


def test_gmail_service_create_draft_returns_id(monkeypatch):
    service = GmailService(token_cipher=TokenCipher("super-secret-key"))
    captured = {}

    def _fake_request(**kwargs):
        captured["json"] = kwargs["json"]
        return _FakeResponse({"id": "draft-123"})

    monkeypatch.setattr(service, "_gmail_request", _fake_request)

    draft_id = service.create_gmail_draft(user=object(), db=object(), draft_body="Hello", subject="Test")
    assert draft_id == "draft-123"
    assert "raw" in captured["json"]["message"]


def test_gmail_service_parses_recipients():
    service = GmailService(token_cipher=TokenCipher("super-secret-key"))
    recipients = service._parse_recipients("Alice <alice@example.com>, bob@example.com")
    assert recipients == ["alice@example.com", "bob@example.com"]


def test_fetch_primary_inbox_between_builds_after_before_query(monkeypatch):
    service = GmailService(token_cipher=TokenCipher("super-secret-key"))
    captured = {}

    def _fake_request(**kwargs):
        captured["params"] = kwargs["params"]
        return _FakeResponse({"messages": [{"id": "m1"}]})

    def _fake_detail(user, message_id, db):
        return {
            "id": message_id,
            "sender_email": "a@example.com",
            "subject": "Test",
            "snippet": "Body",
            "body_text": "Body",
            "received_at": datetime(2026, 5, 25, 8, 0, tzinfo=timezone.utc),
            "is_read": False,
        }

    monkeypatch.setattr(service, "_gmail_request", _fake_request)
    monkeypatch.setattr(service, "_get_message_detail", _fake_detail)

    rows = service.fetch_primary_inbox_between(
        user=object(),
        db=object(),
        start_utc=datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 26, 0, 0, tzinfo=timezone.utc),
        limit=50,
    )
    expected_after = int(datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc).timestamp())
    expected_before = int(datetime(2026, 5, 26, 0, 0, tzinfo=timezone.utc).timestamp())
    assert len(rows) == 1
    assert "in:inbox category:primary" in captured["params"]["q"]
    assert f"after:{expected_after}" in captured["params"]["q"]
    assert f"before:{expected_before}" in captured["params"]["q"]


def test_gmail_service_create_reply_draft_sets_thread_and_headers(monkeypatch):
    service = GmailService(token_cipher=TokenCipher("super-secret-key"))
    captured = {}

    def _fake_request(**kwargs):
        captured["json"] = kwargs["json"]
        return _FakeResponse({"id": "draft-reply-1"})

    monkeypatch.setattr(service, "_gmail_request", _fake_request)
    user = type("U", (), {"email": "me@example.com"})()
    draft_id = service.create_gmail_reply_draft(
        user=user,
        db=object(),
        original_email={
            "sender_email": "sender@example.com",
            "subject": "Interview follow-up",
            "threadId": "thread-123",
            "message_id_header": "<msg-123@example.com>",
            "references_header": "<ref-111@example.com> <ref-112@example.com>",
        },
        draft_body="Thanks for the follow-up. I will confirm by [DATE].",
    )

    assert draft_id == "draft-reply-1"
    message_payload = captured["json"]["message"]
    assert message_payload["threadId"] == "thread-123"
    raw = base64.urlsafe_b64decode(message_payload["raw"].encode("ascii")).decode("utf-8", errors="replace")
    assert "To: sender@example.com" in raw
    assert "From: me@example.com" in raw
    assert "Subject: Re: Interview follow-up" in raw
    assert "In-Reply-To: <msg-123@example.com>" in raw
    assert "References: <ref-111@example.com> <ref-112@example.com>" in raw
