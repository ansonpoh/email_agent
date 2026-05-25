from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models.user import User


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._conditions = []

    def filter(self, *conditions):
        self._conditions.extend(conditions)
        return self

    def first(self):
        rows = self.all()
        return rows[0] if rows else None

    def all(self):
        out = []
        for row in self._rows:
            if all(self._match(row, condition) for condition in self._conditions):
                out.append(row)
        return out

    @staticmethod
    def _match(row, condition):
        left_name = getattr(condition.left, "name", None) or getattr(condition.left, "key", None)
        if not left_name:
            return True

        left_value = getattr(row, left_name)
        right = getattr(condition.right, "value", condition.right)
        op_name = getattr(condition.operator, "__name__", "")
        if op_name == "eq":
            return left_value == right
        if op_name == "ne":
            return left_value != right
        return True


class _FakeDb:
    def __init__(self, users):
        self.users = users

    def query(self, _model):
        return _FakeQuery(self.users)

    def add(self, user):
        if user not in self.users:
            self.users.append(user)

    def flush(self):
        return None

    def commit(self):
        return None

    def refresh(self, _user):
        return None


def _override_db(fake_db):
    def _provider():
        yield fake_db

    return _provider


def test_google_callback_links_chat_and_returns_html(monkeypatch):
    from app.api import auth as auth_api

    fake_db = _FakeDb(users=[])
    app.dependency_overrides[get_db] = _override_db(fake_db)

    monkeypatch.setattr(
        auth_api.telegram_auth_state_service,
        "parse_and_verify",
        lambda _state: SimpleNamespace(chat_id="777", nonce="n1", issued_at=1),
    )
    monkeypatch.setattr(auth_api.gmail_service, "exchange_code_for_tokens", lambda code: {"access_token": "a1", "refresh_token": "r1"})
    monkeypatch.setattr(auth_api.gmail_service, "fetch_google_user_profile", lambda access_token: {"id": "g-1", "email": "u1@example.com"})
    sent = {}
    monkeypatch.setattr(auth_api.telegram_service, "send_message", lambda chat_id, text: sent.update({"chat_id": chat_id, "text": text}))

    with TestClient(app) as client:
        response = client.get("/auth/google/callback", params={"code": "abc", "state": "valid-state"})

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert "Connection Successful" in response.text
    assert len(fake_db.users) == 1
    assert fake_db.users[0].telegram_chat_id == "777"
    assert sent["chat_id"] == "777"


def test_google_callback_rejects_invalid_state(monkeypatch):
    from app.api import auth as auth_api

    fake_db = _FakeDb(users=[])
    app.dependency_overrides[get_db] = _override_db(fake_db)
    monkeypatch.setattr(auth_api.telegram_auth_state_service, "parse_and_verify", lambda _state: (_ for _ in ()).throw(ValueError("State payload has expired.")))

    with TestClient(app) as client:
        response = client.get("/auth/google/callback", params={"code": "abc", "state": "bad"})

    app.dependency_overrides.clear()
    assert response.status_code == 400
    assert "expired" in response.text
    assert len(fake_db.users) == 0


def test_google_callback_relinks_same_chat_to_new_account(monkeypatch):
    from app.api import auth as auth_api

    old_user = User(
        id=uuid4(),
        email="old@example.com",
        google_user_id="old-google",
        encrypted_access_token="enc-a",
        encrypted_refresh_token="enc-r",
        telegram_chat_id="555",
        digest_frequency="hourly",
        urgent_alerts_enabled=True,
        timezone="UTC",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    fake_db = _FakeDb(users=[old_user])
    app.dependency_overrides[get_db] = _override_db(fake_db)

    monkeypatch.setattr(
        auth_api.telegram_auth_state_service,
        "parse_and_verify",
        lambda _state: SimpleNamespace(chat_id="555", nonce="n2", issued_at=1),
    )
    monkeypatch.setattr(auth_api.gmail_service, "exchange_code_for_tokens", lambda code: {"access_token": "a2", "refresh_token": "r2"})
    monkeypatch.setattr(auth_api.gmail_service, "fetch_google_user_profile", lambda access_token: {"id": "new-google", "email": "new@example.com"})
    monkeypatch.setattr(auth_api.telegram_service, "send_message", lambda *_args, **_kwargs: None)

    with TestClient(app) as client:
        response = client.get("/auth/google/callback", params={"code": "abc", "state": "valid-state"})

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert old_user.telegram_chat_id is None
    linked = [row for row in fake_db.users if row.google_user_id == "new-google"][0]
    assert linked.telegram_chat_id == "555"


def test_google_callback_relinks_same_google_user_to_new_chat(monkeypatch):
    from app.api import auth as auth_api

    existing = User(
        id=uuid4(),
        email="same@example.com",
        google_user_id="same-google",
        encrypted_access_token="enc-a",
        encrypted_refresh_token="enc-r",
        telegram_chat_id="111",
        digest_frequency="hourly",
        urgent_alerts_enabled=True,
        timezone="UTC",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    fake_db = _FakeDb(users=[existing])
    app.dependency_overrides[get_db] = _override_db(fake_db)

    monkeypatch.setattr(
        auth_api.telegram_auth_state_service,
        "parse_and_verify",
        lambda _state: SimpleNamespace(chat_id="222", nonce="n3", issued_at=1),
    )
    monkeypatch.setattr(auth_api.gmail_service, "exchange_code_for_tokens", lambda code: {"access_token": "a3", "refresh_token": "r3"})
    monkeypatch.setattr(auth_api.gmail_service, "fetch_google_user_profile", lambda access_token: {"id": "same-google", "email": "same@example.com"})
    monkeypatch.setattr(auth_api.telegram_service, "send_message", lambda *_args, **_kwargs: None)

    with TestClient(app) as client:
        response = client.get("/auth/google/callback", params={"code": "abc", "state": "valid-state"})

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert existing.telegram_chat_id == "222"
