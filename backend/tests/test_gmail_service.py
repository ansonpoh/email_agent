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
