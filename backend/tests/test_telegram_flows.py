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


def test_startup_lifecycle_starts_and_stops_inproc_scheduler(monkeypatch):
    from app import main as app_main

    captured: dict[str, object] = {"started": False, "stopped": False, "jobs": []}

    class _FakeScheduler:
        def __init__(self, timezone):
            captured["timezone"] = timezone

        def add_job(self, func, trigger, seconds, id, replace_existing, max_instances, coalesce):
            captured["jobs"].append(
                {
                    "func_name": getattr(func, "__name__", ""),
                    "trigger": trigger,
                    "seconds": seconds,
                    "id": id,
                    "replace_existing": replace_existing,
                    "max_instances": max_instances,
                    "coalesce": coalesce,
                }
            )

        def start(self):
            captured["started"] = True

        def shutdown(self, wait=False):
            captured["stopped"] = True
            captured["wait"] = wait

    monkeypatch.setattr(settings, "run_db_migrations_on_startup", False)
    monkeypatch.setattr(settings, "inproc_scheduler_enabled", True)
    monkeypatch.setattr(settings, "inproc_scheduler_tick_seconds", 60)
    monkeypatch.setattr(settings, "direct_email_watcher_enabled", True)
    monkeypatch.setattr(settings, "direct_email_watch_interval_minutes", 10)
    monkeypatch.setattr(app_main, "AsyncIOScheduler", _FakeScheduler)
    monkeypatch.setattr(app_main.telegram_service, "register_webhook_from_settings", lambda: True)

    with TestClient(app):
        pass

    assert captured["started"] is True
    assert captured["stopped"] is True
    assert captured["wait"] is False
    assert captured["timezone"] == "UTC"
    assert len(captured["jobs"]) == 2
    assert captured["jobs"][0]["trigger"] == "interval"
    assert captured["jobs"][0]["seconds"] == 60
    assert captured["jobs"][0]["id"] == "inproc-telegram-cycle"
    assert captured["jobs"][1]["id"] == "inproc-direct-email-watcher-cycle"
    assert captured["jobs"][1]["seconds"] == 600


def test_telegram_approval_markup_shape():
    markup = TelegramService.approval_markup("abc-123")
    buttons = markup["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "approve:abc-123"
    assert buttons[1]["callback_data"] == "reject:abc-123"


def test_telegram_quick_actions_markup_shape():
    markup = TelegramService.quick_actions_markup()
    keyboard = markup["inline_keyboard"]
    assert keyboard[0][0]["callback_data"] == "cmd:today"
    assert keyboard[0][1]["callback_data"] == "cmd:latest"
    assert keyboard[1][0]["callback_data"] == "cmd:status"
    assert keyboard[1][1]["callback_data"] == "cmd:followups"
    assert keyboard[2][0]["callback_data"] == "cmd:schedule_status"
