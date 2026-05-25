import time

import pytest

from app.services.telegram_auth_state_service import TelegramAuthStateService


def test_telegram_auth_state_roundtrip():
    service = TelegramAuthStateService(ttl_seconds=600)
    state = service.create(chat_id="123456")
    parsed = service.parse_and_verify(state)
    assert parsed.chat_id == "123456"
    assert parsed.nonce
    assert isinstance(parsed.issued_at, int)


def test_telegram_auth_state_rejects_tampered_payload():
    service = TelegramAuthStateService(ttl_seconds=600)
    state = service.create(chat_id="123456")
    payload, signature = state.split(".", 1)
    tampered = f"{payload}x.{signature}"
    with pytest.raises(ValueError, match="Invalid state signature"):
        service.parse_and_verify(tampered)


def test_telegram_auth_state_rejects_expired(monkeypatch):
    service = TelegramAuthStateService(ttl_seconds=10)
    now = int(time.time())
    monkeypatch.setattr(time, "time", lambda: now)
    state = service.create(chat_id="999")
    monkeypatch.setattr(time, "time", lambda: now + 11)
    with pytest.raises(ValueError, match="expired"):
        service.parse_and_verify(state)


def test_telegram_auth_state_rejects_malformed():
    service = TelegramAuthStateService(ttl_seconds=600)
    with pytest.raises(ValueError, match="Malformed state payload"):
        service.parse_and_verify("not-a-valid-state")
