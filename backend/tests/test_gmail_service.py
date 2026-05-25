from datetime import datetime, timezone

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
