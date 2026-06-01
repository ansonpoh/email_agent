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
        self.callback_answers = []

    @staticmethod
    def quick_actions_markup():
        return {
            "inline_keyboard": [
                [{"text": "Today", "callback_data": "cmd:today"}, {"text": "Latest", "callback_data": "cmd:latest"}],
                [{"text": "Status", "callback_data": "cmd:status"}, {"text": "Follow-ups", "callback_data": "cmd:followups"}],
                [{"text": "Schedule", "callback_data": "cmd:schedule_status"}],
            ]
        }

    def send_message(self, chat_id: str, text: str, reply_markup: dict | None = None, parse_mode: str | None = None):
        self.messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return {"message_id": 1}

    def answer_callback_query(self, callback_query_id: str, text: str):
        self.callback_answers.append({"id": callback_query_id, "text": text})
        return True


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
    def __init__(
        self,
        today_result=None,
        raise_on_today: bool = False,
        followups=None,
        due_today=None,
        ask_result=None,
        raise_on_ask: bool = False,
    ):
        self.today_result = today_result
        self.raise_on_today = raise_on_today
        self.followups = followups or []
        self.due_today = due_today or []
        self.ask_result = ask_result
        self.raise_on_ask = raise_on_ask

    def generate_today_summary(self, db, user):
        if self.raise_on_today:
            raise RuntimeError("today summary failed")
        if self.today_result is not None:
            return self.today_result
        return {
            "empty": True,
            "count": 0,
            "timezone": "UTC",
            "start_local": datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc),
            "end_local": datetime(2026, 5, 26, 0, 0, tzinfo=timezone.utc),
        }

    def list_open_followups(self, db, user, limit=10):
        return self.followups[:limit]

    def list_due_today_followups(self, db, user, limit=20):
        return self.due_today[:limit]

    def answer_inbox_question(self, db, user, question: str):
        if self.raise_on_ask:
            raise RuntimeError("ask failed")
        if self.ask_result is not None:
            return self.ask_result
        return {
            "empty": False,
            "count": 2,
            "answer": f"Answer for: {question}",
            "citations": ["1. alice@example.com | Subject A (Relevant context)"],
            "suggested_actions": ["Reply to Alice"],
        }

def _linked_user(chat_id: str):
    return SimpleNamespace(
        id=uuid4(),
        email="linked@example.com",
        telegram_chat_id=chat_id,
        scheduled_digest_enabled=False,
        digest_schedule_count=None,
        digest_schedule_times=[],
        timezone="UTC",
    )


def _build_service(telegram, gmail=None, orchestration=None):
    return TelegramBotService(
        telegram_service=telegram,
        gmail_service=gmail or _FakeGmailService(),
        auth_state_service=_FakeAuthStateService(),
        orchestration_service=orchestration or _FakeOrchestrationService(),
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
    assert "/today - summarize today's primary inbox emails with AI" in telegram.messages[-1]["text"]
    assert "/ask <question> - ask questions about recent inbox emails" in telegram.messages[-1]["text"]
    assert "/followups - list unresolved follow-up tasks" in telegram.messages[-1]["text"]
    assert "/due-today - list follow-up items due today" in telegram.messages[-1]["text"]
    assert "/sync - sync inbox and analyze new messages" not in telegram.messages[-1]["text"]
    assert "/digest - send latest digest" not in telegram.messages[-1]["text"]
    assert "/timezone set <IANA>" not in telegram.messages[-1]["text"]
    assert "/rules - list active rules" not in telegram.messages[-1]["text"]
    buttons = telegram.messages[-1]["reply_markup"]["inline_keyboard"]
    assert buttons[0][0]["callback_data"] == "cmd:today"
    assert buttons[0][1]["callback_data"] == "cmd:latest"


def test_start_linked_includes_quick_action_buttons():
    user = _linked_user("2020")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/start", "chat": {"id": "2020"}}})
    assert result["message"] == "start_linked"
    markup = telegram.messages[-1]["reply_markup"]
    assert markup["inline_keyboard"][1][0]["callback_data"] == "cmd:status"
    assert markup["inline_keyboard"][1][1]["callback_data"] == "cmd:followups"


def test_callback_quick_command_status_dispatches():
    user = _linked_user("2121")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={
            "callback_query": {
                "id": "cb-1",
                "data": "cmd:status",
                "message": {"chat": {"id": "2121"}},
            }
        },
    )

    assert result["message"] == "status"
    assert telegram.callback_answers[-1]["id"] == "cb-1"
    assert telegram.messages[-1]["text"] == "Linked account: linked@example.com"


def test_followups_command_lists_open_items():
    user = _linked_user("3331")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    followups = [
        SimpleNamespace(task_text="Reply to Alice about contract", due_at=datetime(2026, 5, 26, 9, 0, tzinfo=timezone.utc), due_label=None),
        SimpleNamespace(task_text="Share updated proposal", due_at=None, due_label="this week"),
    ]
    orchestration = _FakeOrchestrationService(followups=followups)
    service = _build_service(telegram, orchestration=orchestration)

    result = service.handle_update(db=db, update={"message": {"text": "/followups", "chat": {"id": "3331"}}})
    assert result["message"] == "followups"
    text = telegram.messages[-1]["text"]
    assert "Open follow-ups" in text
    assert "Reply to Alice about contract" in text
    assert "Share updated proposal" in text


def test_due_today_command_lists_items():
    user = _linked_user("3332")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    due_today = [
        SimpleNamespace(task_text="Send budget draft", due_at=datetime(2026, 5, 26, 2, 0, tzinfo=timezone.utc), due_label=None),
    ]
    orchestration = _FakeOrchestrationService(due_today=due_today)
    service = _build_service(telegram, orchestration=orchestration)

    result = service.handle_update(db=db, update={"message": {"text": "/due-today", "chat": {"id": "3332"}}})
    assert result["message"] == "due_today"
    assert "Due today" in telegram.messages[-1]["text"]
    assert "Send budget draft" in telegram.messages[-1]["text"]


def test_ask_command_answers_with_sources():
    user = _linked_user("3333")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    orchestration = _FakeOrchestrationService(
        ask_result={
            "empty": False,
            "count": 3,
            "answer": "The hiring manager asked for availability this week.",
            "citations": ["1. hr@company.com | Interview follow-up (Contains scheduling request)"],
            "suggested_actions": ["Reply with 3 time slots."],
        }
    )
    service = _build_service(telegram, orchestration=orchestration)

    result = service.handle_update(db=db, update={"message": {"text": "/ask what needs reply today?", "chat": {"id": "3333"}}})
    assert result["message"] == "ask_answered"
    text = telegram.messages[-1]["text"]
    assert "Q: what needs reply today?" in text
    assert "Sources:" in text
    assert "Suggested actions:" not in text


def test_callback_unknown_quick_command_returns_error():
    user = _linked_user("2222")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={
            "callback_query": {
                "id": "cb-2",
                "data": "cmd:not-real",
                "message": {"chat": {"id": "2222"}},
            }
        },
    )
    assert result["message"] == "unknown_callback_command"
    assert telegram.callback_answers[-1]["text"] == "Unknown command."


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


def test_today_empty_state():
    user = _linked_user("1012")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    orchestration = _FakeOrchestrationService(
        today_result={
            "empty": True,
            "count": 0,
            "timezone": "Asia/Singapore",
            "start_local": datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc),
            "end_local": datetime(2026, 5, 26, 0, 0, tzinfo=timezone.utc),
        }
    )
    service = _build_service(telegram, orchestration=orchestration)

    result = service.handle_update(db=db, update={"message": {"text": "/today", "chat": {"id": "1012"}}})
    assert result["message"] == "today_empty"
    assert "No emails found in your Primary Inbox" in telegram.messages[-1]["text"]


def test_today_success_summary():
    user = _linked_user("1013")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    orchestration = _FakeOrchestrationService(
        today_result={
            "empty": False,
            "count": 3,
            "timezone": "UTC",
            "start_local": datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc),
            "end_local": datetime(2026, 5, 26, 0, 0, tzinfo=timezone.utc),
            "summary": {
                "overview": "Three important threads need review.",
                "priority_items": ["Finance approval pending", "Customer escalation from Alice"],
                "suggested_actions": ["Reply to Alice", "Review and approve invoice"],
            },
        }
    )
    service = _build_service(telegram, orchestration=orchestration)

    result = service.handle_update(db=db, update={"message": {"text": "/today", "chat": {"id": "1013"}}})
    assert result["message"] == "today"
    text = telegram.messages[-1]["text"]
    assert "Today's AI Email Summary (Primary Inbox)" in text
    assert "Emails analyzed: 3" in text
    assert "Priority items:" in text
    assert "Suggested actions:" in text


def test_today_handles_orchestration_failure():
    user = _linked_user("1014")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram, orchestration=_FakeOrchestrationService(raise_on_today=True))

    result = service.handle_update(db=db, update={"message": {"text": "/today", "chat": {"id": "1014"}}})
    assert result["message"] == "today_failed"
    assert telegram.messages[-1]["text"] == "Unable to generate today's summary right now. Please try again."


def test_digest_schedule_country_sets_timezone_for_single_timezone_country():
    user = _linked_user("1008")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule country Singapore", "chat": {"id": "1008"}}},
    )
    assert result["message"] == "digest_schedule_country_set"
    assert user.timezone == "Asia/Singapore"


def test_digest_schedule_country_uses_capital_override_for_multi_timezone_country():
    user = _linked_user("1009")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule country USA", "chat": {"id": "1009"}}},
    )
    assert result["message"] == "digest_schedule_country_set"
    assert user.timezone == "America/New_York"


def test_digest_schedule_count_accepts_1_to_3_and_rejects_invalid():
    user = _linked_user("1010")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    ok_result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule count 2", "chat": {"id": "1010"}}},
    )
    assert ok_result["message"] == "digest_schedule_count_set"
    assert user.digest_schedule_count == 2
    assert user.scheduled_digest_enabled is False

    invalid_result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule count 4", "chat": {"id": "1010"}}},
    )
    assert invalid_result["message"] == "digest_schedule_invalid"
    assert telegram.messages[-1]["text"] == "Count must be between 1 and 3."


def test_digest_schedule_times_parses_12h_and_enables_schedule():
    user = _linked_user("1011")
    user.digest_schedule_count = 2
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule times 8am,1pm", "chat": {"id": "1011"}}},
    )
    assert result["message"] == "digest_schedule_set"
    assert user.scheduled_digest_enabled is True
    assert user.digest_schedule_times == ["08:00", "13:00"]


def test_digest_schedule_times_parses_12h_with_minutes_and_enables_schedule():
    user = _linked_user("1111")
    user.digest_schedule_count = 2
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule times 1015am,620pm", "chat": {"id": "1111"}}},
    )
    assert result["message"] == "digest_schedule_set"
    assert user.scheduled_digest_enabled is True
    assert user.digest_schedule_times == ["10:15", "18:20"]


def test_digest_schedule_times_count_mismatch_preserves_previous_schedule():
    user = _linked_user("1012")
    user.digest_schedule_count = 3
    user.digest_schedule_times = ["08:00", "13:00", "18:00"]
    user.scheduled_digest_enabled = True
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule times 8am,1pm", "chat": {"id": "1012"}}},
    )
    assert result["message"] == "digest_schedule_invalid"
    assert user.digest_schedule_times == ["08:00", "13:00", "18:00"]
    assert user.scheduled_digest_enabled is True


def test_digest_schedule_old_set_format_is_rejected():
    user = _linked_user("1013")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule set 09:00", "chat": {"id": "1013"}}},
    )
    assert result["message"] == "digest_schedule_usage"


def test_digest_schedule_on_rejects_until_count_and_times_are_complete():
    user = _linked_user("1014")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    first = service.handle_update(db=db, update={"message": {"text": "/schedule on", "chat": {"id": "1014"}}})
    assert first["message"] == "digest_schedule_on_missing_count"

    user.digest_schedule_count = 2
    second = service.handle_update(db=db, update={"message": {"text": "/schedule on", "chat": {"id": "1014"}}})
    assert second["message"] == "digest_schedule_on_missing_times"


def test_digest_schedule_three_step_flow_auto_enables_schedule():
    user = _linked_user("1015")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    country_result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule country Singapore", "chat": {"id": "1015"}}},
    )
    count_result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule count 2", "chat": {"id": "1015"}}},
    )
    times_result = service.handle_update(
        db=db,
        update={"message": {"text": "/schedule times 8am,1pm", "chat": {"id": "1015"}}},
    )

    assert country_result["message"] == "digest_schedule_country_set"
    assert count_result["message"] == "digest_schedule_count_set"
    assert times_result["message"] == "digest_schedule_set"
    assert user.scheduled_digest_enabled is True
    assert user.timezone == "Asia/Singapore"
    assert user.digest_schedule_count == 2
    assert user.digest_schedule_times == ["08:00", "13:00"]


def test_digest_schedule_status_displays_toggle_timezone_count_and_times():
    user = _linked_user("1016")
    user.scheduled_digest_enabled = True
    user.digest_schedule_count = 2
    user.digest_schedule_times = ["14:00", "09:00"]
    user.timezone = "Asia/Singapore"
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/schedule status", "chat": {"id": "1016"}}})
    assert result["message"] == "digest_schedule_status"
    text = telegram.messages[-1]["text"]
    assert "Digest schedule is enabled." in text
    assert "Timezone: Asia/Singapore" in text
    assert "Count: 2" in text
    assert "Times: 09:00, 14:00" in text


def test_removed_digest_command_returns_unknown():
    user = _linked_user("1017")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/digest", "chat": {"id": "1017"}}})
    assert result["message"] == "unknown_command"
    assert telegram.messages[-1]["text"] == "Unknown command. Send /help."


def test_removed_timezone_command_returns_unknown():
    user = _linked_user("1018")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/timezone set Asia/Singapore", "chat": {"id": "1018"}}})
    assert result["message"] == "unknown_command"
    assert telegram.messages[-1]["text"] == "Unknown command. Send /help."


def test_removed_rules_commands_return_unknown():
    user = _linked_user("1019")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    commands = ["/rules", "/rule add Be concise", f"/rule del {uuid4()}"]
    for command in commands:
        result = service.handle_update(db=db, update={"message": {"text": command, "chat": {"id": "1019"}}})
        assert result["message"] == "unknown_command"
        assert telegram.messages[-1]["text"] == "Unknown command. Send /help."


def test_removed_sync_command_returns_unknown():
    user = _linked_user("1020")
    db = _FakeDb(users=[user])
    telegram = _FakeTelegramService()
    service = _build_service(telegram)

    result = service.handle_update(db=db, update={"message": {"text": "/sync", "chat": {"id": "1020"}}})
    assert result["message"] == "unknown_command"
    assert telegram.messages[-1]["text"] == "Unknown command. Send /help."
