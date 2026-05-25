from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.telegram_bot_service import TelegramBotService


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

    def add(self, _row):
        return None

    def commit(self):
        return None

    def refresh(self, _row):
        return None


class _FakeTelegramService:
    def __init__(self):
        self.messages = []

    def send_message(self, chat_id: str, text: str, reply_markup: dict | None = None):
        self.messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return {"message_id": 1}


class _FakeGmailService:
    def __init__(self, latest_rows=None, raise_on_latest: bool = False):
        self.latest_rows = latest_rows or []
        self.raise_on_latest = raise_on_latest

    @staticmethod
    def get_google_oauth_start_url(state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"

    def fetch_latest_primary_inbox(self, user, db, limit: int = 10):
        if self.raise_on_latest:
            raise RuntimeError("gmail unavailable")
        return self.latest_rows[:limit]


class _FakeAuthStateService:
    @staticmethod
    def create(chat_id: str) -> str:
        return f"state-for-{chat_id}"


class _FakeOrchestrationService:
    pass


def _linked_user(chat_id: str):
    return SimpleNamespace(
        id=uuid4(),
        email="linked@example.com",
        telegram_chat_id=chat_id,
        scheduled_digest_enabled=False,
        digest_schedule_times=[],
        timezone="UTC",
    )


def _build_service(telegram, gmail=None):
    return TelegramBotService(
        telegram_service=telegram,
        gmail_service=gmail or _FakeGmailService(),
        auth_state_service=_FakeAuthStateService(),
        orchestration_service=_FakeOrchestrationService(),
    )


def test_start_unlinked_prompts_connect():
    db = _FakeDb(users=[])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/start", "chat": {"id": "1001"}}})
    assert result["message"] == "start_unlinked"
    assert telegram.messages[-1]["text"] == "Welcome. To connect Gmail, send /connect."


def test_connect_sends_oauth_button():
    db = _FakeDb(users=[])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/connect", "chat": {"id": "1002"}}})
    assert result["message"] == "connect_prompted"
    payload = telegram.messages[-1]
    assert payload["reply_markup"]["inline_keyboard"][0][0]["text"] == "Connect Gmail"
    assert "state=state-for-1002" in payload["reply_markup"]["inline_keyboard"][0][0]["url"]


def test_status_returns_linked_email():
    user = _linked_user("1003")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/status", "chat": {"id": "1003"}}})
    assert result["message"] == "status"
    assert telegram.messages[-1]["text"] == "Linked account: linked@example.com"


def test_help_lists_latest_command():
    user = _linked_user("1004")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/help", "chat": {"id": "1004"}}})
    assert result["message"] == "help"
    assert "/latest - show 10 latest primary inbox emails" in telegram.messages[-1]["text"]


def test_latest_returns_compact_lines():
    user = _linked_user("1005")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    gmail = _FakeGmailService(
        latest_rows=[
            {
                "sender_email": "alice@example.com",
                "subject": "Project update",
                "received_at": datetime(2026, 5, 25, 9, 30, tzinfo=timezone.utc),
                "is_read": False,
            },
            {
                "sender_email": "bob@example.com",
                "subject": None,
                "received_at": datetime(2026, 5, 25, 8, 0, tzinfo=timezone.utc),
                "is_read": True,
            },
        ]
    )
    service = _build_service(telegram, gmail=gmail)

    result = service.handle_update(db=db, update={"message": {"text": "/latest", "chat": {"id": "1005"}}})
    assert result["message"] == "latest"
    text = telegram.messages[-1]["text"]
    assert "Latest 10 emails in Primary Inbox:" in text
    assert "1. alice@example.com | Project update | 2026-05-25 09:30 UTC | unread" in text
    assert "2. bob@example.com | (No subject) | 2026-05-25 08:00 UTC | read" in text


def test_latest_empty_state():
    user = _linked_user("1006")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram, gmail=_FakeGmailService(latest_rows=[]))

    result = service.handle_update(db=db, update={"message": {"text": "/latest", "chat": {"id": "1006"}}})
    assert result["message"] == "latest_empty"
    assert telegram.messages[-1]["text"] == "No emails found in your Primary Inbox."


def test_latest_handles_gmail_failure():
    user = _linked_user("1007")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram, gmail=_FakeGmailService(raise_on_latest=True))

    result = service.handle_update(db=db, update={"message": {"text": "/latest", "chat": {"id": "1007"}}})
    assert result["message"] == "latest_fetch_failed"
    assert telegram.messages[-1]["text"] == "Unable to fetch latest emails from Gmail right now. Please try again."


def test_digest_schedule_set_auto_enables_and_sorts_times():
    user = _linked_user("1008")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={"message": {"text": "/digest_schedule set 19:00,09:00,14:00", "chat": {"id": "1008"}}},
    )
    assert result["message"] == "digest_schedule_set"
    assert user.scheduled_digest_enabled is True
    assert user.digest_schedule_times == ["09:00", "14:00", "19:00"]


def test_digest_schedule_rejects_duplicate_times():
    user = _linked_user("1009")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={"message": {"text": "/digest_schedule set 09:00,09:00", "chat": {"id": "1009"}}},
    )
    assert result["message"] == "digest_schedule_invalid"
    assert telegram.messages[-1]["text"] == "Duplicate times are not allowed."


def test_digest_schedule_status_displays_toggle_timezone_and_times():
    user = _linked_user("1010")
    user.scheduled_digest_enabled = True
    user.digest_schedule_times = ["14:00", "09:00"]
    user.timezone = "Asia/Singapore"
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/digest_schedule status", "chat": {"id": "1010"}}})
    assert result["message"] == "digest_schedule_status"
    text = telegram.messages[-1]["text"]
    assert "Digest schedule is enabled." in text
    assert "Timezone: Asia/Singapore" in text
    assert "Times: 09:00, 14:00" in text


def test_timezone_set_updates_user():
    user = _linked_user("1011")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/timezone set Asia/Singapore", "chat": {"id": "1011"}}})
    assert result["message"] == "timezone_set"
    assert user.timezone == "Asia/Singapore"
