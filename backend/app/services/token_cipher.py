import base64
import hashlib
import hmac
import logging
import secrets

from app.config import settings


class TokenCipher:
    """Symmetric token cipher using stdlib primitives.

    Format:
    enc.v1.<base64url(nonce[16] + ciphertext + mac[32])>
    """

    PREFIX = "enc.v1."

    def __init__(self, secret: str):
        self.logger = logging.getLogger(__name__)
        if not secret or secret == "CHANGE_ME_WITH_32_CHAR_MIN_SECRET":
            self.logger.warning(
                "ENCRYPTION_KEY is using default value; configure a strong secret for production."
            )
        material = secret.encode("utf-8")
        self._enc_key = hashlib.sha256(b"enc:" + material).digest()
        self._mac_key = hashlib.sha256(b"mac:" + material).digest()

    def encrypt(self, plaintext: str) -> str:
        if plaintext.startswith(self.PREFIX):
            return plaintext

        nonce = secrets.token_bytes(16)
        ciphertext = self._xor_keystream(plaintext.encode("utf-8"), nonce)
        mac = hmac.new(self._mac_key, nonce + ciphertext, hashlib.sha256).digest()
        blob = nonce + ciphertext + mac
        return self.PREFIX + base64.urlsafe_b64encode(blob).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value.startswith(self.PREFIX):
            # Backwards compatibility for already-stored plaintext tokens.
            return value

        raw = value[len(self.PREFIX) :]
        blob = base64.urlsafe_b64decode(raw.encode("ascii"))
        if len(blob) < 16 + 32:
            raise ValueError("Encrypted token payload is too short.")

        nonce = blob[:16]
        mac = blob[-32:]
        ciphertext = blob[16:-32]

        expected = hmac.new(self._mac_key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("Encrypted token failed integrity check.")

        plaintext = self._xor_keystream(ciphertext, nonce)
        return plaintext.decode("utf-8")

    def _xor_keystream(self, data: bytes, nonce: bytes) -> bytes:
        out = bytearray()
        counter = 0
        remaining = len(data)
        index = 0

        while remaining > 0:
            block = hmac.new(
                self._enc_key,
                nonce + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
            take = min(remaining, len(block))
            for i in range(take):
                out.append(data[index + i] ^ block[i])
            index += take
            remaining -= take
            counter += 1

        return bytes(out)


token_cipher = TokenCipher(settings.encryption_key)
