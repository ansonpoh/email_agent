import httpx
import logging

from app.config import settings


class TelegramService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_message(self, chat_id: str, text: str, reply_markup: dict | None = None) -> dict | None:
        if not settings.telegram_bot_token:
            self.logger.warning("Telegram send skipped because TELEGRAM_BOT_TOKEN is not configured.")
            return None

        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            data = self._post("sendMessage", payload)
            if not data.get("ok"):
                return None
            return data.get("result")
        except Exception:
            self.logger.exception("Telegram send failed for chat_id=%s", chat_id)
            return None

    def answer_callback_query(self, callback_query_id: str, text: str) -> bool:
        if not settings.telegram_bot_token:
            return False
        try:
            data = self._post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})
            return bool(data.get("ok"))
        except Exception:
            self.logger.exception("Telegram callback answer failed for callback_query_id=%s", callback_query_id)
            return False

    def build_webhook_url(self, base_url: str | None = None) -> str | None:
        resolved_base = (base_url or settings.telegram_webhook_base_url or "").rstrip("/")
        if not resolved_base:
            return None
        return f"{resolved_base}/telegram/webhook"

    def set_webhook(self, webhook_url: str, secret_token: str | None = None) -> bool:
        payload = {"url": webhook_url}
        if secret_token:
            payload["secret_token"] = secret_token
        try:
            data = self._post("setWebhook", payload)
            return bool(data.get("ok"))
        except Exception:
            self.logger.exception("Telegram webhook registration failed webhook_url=%s", webhook_url)
            return False

    def get_webhook_info(self) -> dict | None:
        try:
            data = self._post("getWebhookInfo", {})
            if not data.get("ok"):
                return None
            return data.get("result")
        except Exception:
            self.logger.exception("Telegram webhook info fetch failed.")
            return None

    def register_webhook_from_settings(self) -> bool:
        if not settings.telegram_bot_token:
            self.logger.info("Telegram webhook registration skipped because TELEGRAM_BOT_TOKEN is not configured.")
            return False
        webhook_url = self.build_webhook_url()
        if not webhook_url:
            self.logger.info(
                "Telegram webhook registration skipped because TELEGRAM_WEBHOOK_BASE_URL is not configured."
            )
            return False

        registered = self.set_webhook(
            webhook_url=webhook_url,
            secret_token=settings.telegram_webhook_secret_token,
        )
        if registered:
            self.logger.info("Telegram webhook registered webhook_url=%s", webhook_url)
        else:
            self.logger.warning("Telegram webhook registration returned non-ok response webhook_url=%s", webhook_url)
        return registered

    @staticmethod
    def approval_markup(action_id: str) -> dict:
        return {
            "inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": f"approve:{action_id}"},
                    {"text": "Reject", "callback_data": f"reject:{action_id}"},
                ]
            ]
        }

    def _post(self, method: str, payload: dict) -> dict:
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()
