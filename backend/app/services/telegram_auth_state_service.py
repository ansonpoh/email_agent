import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from app.config import settings


@dataclass
class TelegramAuthState:
    chat_id: str
    nonce: str
    issued_at: int


class TelegramAuthStateService:
    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds

    def create(self, chat_id: str) -> str:
        payload = {
            "chat_id": str(chat_id),
            "nonce": secrets.token_urlsafe(12),
            "issued_at": int(time.time()),
        }
        payload_raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        payload_b64 = self._b64encode(payload_raw)
        signature = self._sign(payload_b64.encode("ascii"))
        signature_b64 = self._b64encode(signature)
        return f"{payload_b64}.{signature_b64}"

    def parse_and_verify(self, state: str) -> TelegramAuthState:
        try:
            payload_b64, signature_b64 = state.split(".", 1)
        except ValueError as exc:
            raise ValueError("Malformed state payload.") from exc

        expected_signature = self._sign(payload_b64.encode("ascii"))
        provided_signature = self._b64decode(signature_b64)
        if not hmac.compare_digest(expected_signature, provided_signature):
            raise ValueError("Invalid state signature.")

        try:
            payload = json.loads(self._b64decode(payload_b64).decode("utf-8"))
        except Exception as exc:
            raise ValueError("Malformed state payload.") from exc

        chat_id = str(payload.get("chat_id") or "").strip()
        nonce = str(payload.get("nonce") or "").strip()
        issued_at = payload.get("issued_at")
        if not chat_id or not nonce or not isinstance(issued_at, int):
            raise ValueError("Malformed state payload.")

        now = int(time.time())
        if issued_at > now + 60:
            raise ValueError("State timestamp is in the future.")
        if now - issued_at > self.ttl_seconds:
            raise ValueError("State payload has expired.")

        return TelegramAuthState(chat_id=chat_id, nonce=nonce, issued_at=issued_at)

    @staticmethod
    def _b64encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _b64decode(raw: str) -> bytes:
        padded = raw + "=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    @staticmethod
    def _sign(raw: bytes) -> bytes:
        secret = settings.encryption_key.encode("utf-8")
        return hmac.new(secret, raw, digestmod=hashlib.sha256).digest()
