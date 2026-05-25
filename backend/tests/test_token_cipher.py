from app.services.token_cipher import TokenCipher


def test_token_cipher_round_trip():
    cipher = TokenCipher("super-secret-key")
    token = "ya29.a0AfH6SM..."
    encrypted = cipher.encrypt(token)

    assert encrypted.startswith("enc.v1.")
    assert encrypted != token
    assert cipher.decrypt(encrypted) == token


def test_token_cipher_accepts_legacy_plaintext():
    cipher = TokenCipher("super-secret-key")
    token = "legacy-token-value"
    assert cipher.decrypt(token) == token
