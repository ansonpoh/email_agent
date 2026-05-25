from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.telegram_service import TelegramService

client = TestClient(app)


def test_telegram_webhook_dispatches_to_bot_service(monkeypatch):
    from app.api import telegram as telegram_api

    monkeypatch.setattr(settings, "telegram_webhook_secret_token", None)
    captured = {}

    def _fake_handle_update(db, update):
        captured["payload"] = update
        return {"ok": True, "message": "handled"}

    monkeypatch.setattr(telegram_api.telegram_bot_service, "handle_update", _fake_handle_update)
    response = client.post("/telegram/webhook", json={"update_id": 123, "message": {"text": "/help"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["message"] == "handled"
    assert captured["payload"]["update_id"] == 123


def test_telegram_webhook_rejects_invalid_secret(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret_token", "expected-secret")
    response = client.post("/telegram/webhook", json={"update_id": 123}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid Telegram webhook secret token."


def test_telegram_webhook_accepts_valid_secret(monkeypatch):
    from app.api import telegram as telegram_api

    monkeypatch.setattr(settings, "telegram_webhook_secret_token", "expected-secret")

    def _fake_handle_update(db, update):
        return {"ok": True, "message": "handled"}

    monkeypatch.setattr(telegram_api.telegram_bot_service, "handle_update", _fake_handle_update)
    response = client.post(
        "/telegram/webhook",
        json={"update_id": 123, "message": {"text": "/help"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["message"] == "handled"


def test_startup_registers_webhook(monkeypatch):
    from app import main as app_main

    captured = {}
    monkeypatch.setattr(settings, "telegram_bot_token", "token-123")
    monkeypatch.setattr(settings, "telegram_webhook_base_url", "https://agent.example.com/")
    monkeypatch.setattr(settings, "telegram_webhook_secret_token", "expected-secret")

    def _fake_set_webhook(webhook_url: str, secret_token: str | None = None):
        captured["webhook_url"] = webhook_url
        captured["secret_token"] = secret_token
        return True

    monkeypatch.setattr(app_main.telegram_service, "set_webhook", _fake_set_webhook)
    with TestClient(app):
        pass

    assert captured["webhook_url"] == "https://agent.example.com/telegram/webhook"
    assert captured["secret_token"] == "expected-secret"


def test_telegram_approval_markup_shape():
    markup = TelegramService.approval_markup("abc-123")
    buttons = markup["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "approve:abc-123"
    assert buttons[1]["callback_data"] == "reject:abc-123"
