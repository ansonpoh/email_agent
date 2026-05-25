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


class _FakeTelegramService:
    def __init__(self):
        self.messages = []

    def send_message(self, chat_id: str, text: str, reply_markup: dict | None = None):
        self.messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return {"message_id": 1}


class _FakeGmailService:
    @staticmethod
    def get_google_oauth_start_url(state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"


class _FakeAuthStateService:
    @staticmethod
    def create(chat_id: str) -> str:
        return f"state-for-{chat_id}"


class _FakeOrchestrationService:
    pass


def _build_service(telegram):
    return TelegramBotService(
        telegram_service=telegram,
        gmail_service=_FakeGmailService(),
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
    user = SimpleNamespace(id=uuid4(), email="linked@example.com", telegram_chat_id="1003")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/status", "chat": {"id": "1003"}}})
    assert result["message"] == "status"
    assert telegram.messages[-1]["text"] == "Linked account: linked@example.com"
