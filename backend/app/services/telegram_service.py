import httpx

from app.config import settings


class TelegramService:
    async def send_message(self, chat_id: str, text: str) -> bool:
        if not settings.telegram_bot_token:
            # TODO: Configure TELEGRAM_BOT_TOKEN in environment for live sends.
            return False

        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return bool(data.get("ok"))
