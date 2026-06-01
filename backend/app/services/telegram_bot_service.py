from datetime import datetime, timezone
import re
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.agent_action import AgentAction
from app.models.user import User
from app.services.country_timezone_service import resolve_country_timezone
from app.services.gmail_service import GmailService
from app.services.telegram_auth_state_service import TelegramAuthStateService
from app.services.telegram_orchestration_service import TelegramOrchestrationService
from app.services.telegram_service import TelegramService


class TelegramBotService:
    TELEGRAM_MAX_MESSAGE_LEN = 4096
    QUICK_COMMAND_MAP = {
        "connect": "/connect",
        "status": "/status",
        "latest": "/latest",
        "today": "/today",
        "followups": "/followups",
        "schedule_status": "/schedule status",
        "help": "/help",
    }

    def __init__(
        self,
        telegram_service: TelegramService,
        gmail_service: GmailService,
        auth_state_service: TelegramAuthStateService,
        orchestration_service: TelegramOrchestrationService,
    ):
        self.telegram_service = telegram_service
        self.gmail_service = gmail_service
        self.auth_state_service = auth_state_service
        self.orchestration_service = orchestration_service

    def handle_update(self, db: Session, update: dict) -> dict:
        if "callback_query" in update:
            return self._handle_callback_query(db=db, callback=update["callback_query"])

        message = update.get("message", {})
        text = str(message.get("text") or "").strip()
        chat_id = str((message.get("chat") or {}).get("id") or "")
        if not text or not chat_id:
            return {"ok": True, "ignored": True}

        if text.startswith("/start"):
            user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
            if user:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=f"Welcome back. Linked to {user.email}. Send /help for commands.",
                    reply_markup=self.telegram_service.quick_actions_markup(),
                )
                return {"ok": True, "message": "start_linked", "user_id": str(user.id)}

            self.telegram_service.send_message(
                chat_id=chat_id,
                text="Welcome. To connect Gmail, send /connect.",
            )
            return {"ok": True, "message": "start_unlinked"}

        if text == "/connect":
            state = self.auth_state_service.create(chat_id=chat_id)
            auth_url = self.gmail_service.get_google_oauth_start_url(state=state)
            self.telegram_service.send_message(
                chat_id=chat_id,
                text="Connect your Gmail account:",
                reply_markup={
                    "inline_keyboard": [[{"text": "Connect Gmail", "url": auth_url}]],
                },
            )
            return {"ok": True, "message": "connect_prompted"}

        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if not user:
            self.telegram_service.send_message(
                chat_id=chat_id,
                text="This chat is not linked. Send /connect to connect Gmail.",
            )
            return {"ok": True, "message": "unlinked_chat"}

        return self._handle_linked_command(db=db, user=user, chat_id=chat_id, text=text)

    def _handle_linked_command(self, db: Session, user: User, chat_id: str, text: str) -> dict:

        if text == "/help":
            self.telegram_service.send_message(
                chat_id=chat_id,
                text=(
                    "Commands:\n"
                    "/connect - connect or reconnect Gmail\n"
                    "/status - show linked account\n"
                    "/latest - show 10 latest primary inbox emails\n"
                    "/today - summarize today's primary inbox emails with AI\n"
                    "/ask <question> - ask questions about recent inbox emails\n"
                    "/followups - list unresolved follow-up tasks\n"
                    "/due-today - list follow-up items due today\n"
                    "/schedule status|country|count|times|on|off - manage scheduled digests\n"
                ),
                reply_markup=self.telegram_service.quick_actions_markup(),
            )
            return {"ok": True, "message": "help"}

        if text == "/status":
            self.telegram_service.send_message(
                chat_id=chat_id,
                text=f"Linked account: {user.email}",
            )
            return {"ok": True, "message": "status", "user_id": str(user.id)}

        if text.startswith("/schedule"):
            if text == "/schedule":
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=(
                        "Usage:\n"
                        "/schedule status\n"
                        "/schedule country <country>\n"
                        "/schedule count <1-3>\n"
                        "/schedule times <8am,1015am[,620pm]>\n"
                        "/schedule on\n"
                        "/schedule off"
                    ),
                )
                return {"ok": True, "message": "digest_schedule_usage"}

            if text == "/schedule status":
                times = self._normalized_schedule_times(user.digest_schedule_times)
                status = "enabled" if user.scheduled_digest_enabled else "disabled"
                count_value = getattr(user, "digest_schedule_count", None)
                count_label = str(count_value) if isinstance(count_value, int) and 1 <= count_value <= 3 else "(not set)"
                times_label = ", ".join(times) if times else "(not set)"
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=(
                        f"Digest schedule is {status}.\nTimezone: {user.timezone}\n"
                        f"Count: {count_label}\nTimes: {times_label}"
                    ),
                )
                return {"ok": True, "message": "digest_schedule_status"}

            if text.startswith("/schedule country "):
                raw_country = text.removeprefix("/schedule country ").strip()
                resolution = resolve_country_timezone(raw_country)
                if resolution.error:
                    self.telegram_service.send_message(chat_id=chat_id, text=resolution.error)
                    return {"ok": True, "message": "digest_schedule_invalid_country"}

                user.timezone = str(resolution.timezone)
                db.add(user)
                db.commit()
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=f"Country set to {raw_country}. Timezone resolved to {user.timezone}.",
                )
                return {
                    "ok": True,
                    "message": "digest_schedule_country_set",
                    "timezone": user.timezone,
                    "country_code": resolution.country_code,
                }

            if text.startswith("/schedule count "):
                raw_count = text.removeprefix("/schedule count ").strip()
                count_value, validation_error = self._parse_digest_schedule_count(raw_count)
                if validation_error:
                    self.telegram_service.send_message(chat_id=chat_id, text=validation_error)
                    return {"ok": True, "message": "digest_schedule_invalid"}

                user.digest_schedule_count = count_value
                user.scheduled_digest_enabled = False
                db.add(user)
                db.commit()
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=f"Digest count set to {count_value} per day. Next: /schedule times <8am,1015am>",
                )
                return {"ok": True, "message": "digest_schedule_count_set", "count": count_value}

            if text.startswith("/schedule times "):
                raw_times = text.removeprefix("/schedule times ").strip()
                expected_count = getattr(user, "digest_schedule_count", None)
                schedule_times, validation_error = self._parse_digest_schedule_times_12h(
                    raw_times=raw_times,
                    expected_count=expected_count,
                )
                if validation_error:
                    self.telegram_service.send_message(chat_id=chat_id, text=validation_error)
                    return {"ok": True, "message": "digest_schedule_invalid"}

                user.digest_schedule_times = schedule_times
                user.scheduled_digest_enabled = True
                db.add(user)
                db.commit()
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=f"Digest schedule updated: {', '.join(schedule_times)}. Scheduled digests enabled.",
                )
                return {"ok": True, "message": "digest_schedule_set", "times": schedule_times}

            if text == "/schedule on":
                count_value = getattr(user, "digest_schedule_count", None)
                times = self._normalized_schedule_times(user.digest_schedule_times)
                if not isinstance(count_value, int) or not (1 <= count_value <= 3):
                    self.telegram_service.send_message(
                        chat_id=chat_id,
                        text="Set count first: /schedule count <1-3>",
                    )
                    return {"ok": True, "message": "digest_schedule_on_missing_count"}
                if len(times) != count_value:
                    self.telegram_service.send_message(
                        chat_id=chat_id,
                        text=(
                            "Complete setup first: /schedule country <country>, "
                            "/schedule count <1-3>, /schedule times <8am,1015am>"
                        ),
                    )
                    return {"ok": True, "message": "digest_schedule_on_missing_times"}

                user.scheduled_digest_enabled = True
                db.add(user)
                db.commit()
                self.telegram_service.send_message(chat_id=chat_id, text="Scheduled digests enabled.")
                return {"ok": True, "message": "digest_schedule_on"}

            if text == "/schedule off":
                user.scheduled_digest_enabled = False
                db.add(user)
                db.commit()
                self.telegram_service.send_message(chat_id=chat_id, text="Scheduled digests disabled.")
                return {"ok": True, "message": "digest_schedule_off"}

            self.telegram_service.send_message(
                chat_id=chat_id,
                text=(
                    "Usage:\n"
                    "/schedule status\n"
                    "/schedule country <country>\n"
                    "/schedule count <1-3>\n"
                    "/schedule times <8am,1015am[,620pm]>\n"
                    "/schedule on\n"
                    "/schedule off"
                ),
            )
            return {"ok": True, "message": "digest_schedule_usage"}

        if text == "/latest":
            try:
                rows = self.gmail_service.fetch_latest_primary_inbox(user=user, db=db, limit=10)
            except Exception:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="Unable to fetch latest emails from Gmail right now. Please try again.",
                )
                return {"ok": True, "message": "latest_fetch_failed"}

            if not rows:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="No emails found in your Primary Inbox.",
                )
                return {"ok": True, "message": "latest_empty"}

            lines = ["Latest 10 emails in Primary Inbox:"]
            for idx, row in enumerate(rows[:10], start=1):
                received_at = row["received_at"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                sender = row.get("sender_email") or "unknown@example.com"
                subject = row.get("subject") or "(No subject)"
                status = "read" if row.get("is_read") else "unread"
                lines.append(f"{idx}. {sender} | {subject} | {received_at} | {status}")

            self.telegram_service.send_message(chat_id=chat_id, text="\n".join(lines))
            return {"ok": True, "message": "latest", "count": len(rows[:10])}

        if text == "/today":
            try:
                result = self.orchestration_service.generate_today_summary(db=db, user=user)
            except Exception:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="Unable to generate today's summary right now. Please try again.",
                )
                return {"ok": True, "message": "today_failed"}

            if result.get("empty"):
                day = result["start_local"].strftime("%Y-%m-%d")
                timezone_name = result.get("timezone", "UTC")
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=f"No emails found in your Primary Inbox for {day} ({timezone_name}).",
                )
                return {"ok": True, "message": "today_empty"}

            text_payload = self._format_today_summary_text(result)
            self.telegram_service.send_message(
                chat_id=chat_id,
                text=self._truncate_telegram_text(text_payload),
            )
            return {"ok": True, "message": "today", "count": int(result.get("count", 0))}

        if text == "/followups":
            rows = self.orchestration_service.list_open_followups(db=db, user=user, limit=10)
            if not rows:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="No open follow-up items right now.",
                )
                return {"ok": True, "message": "followups_empty"}

            self.telegram_service.send_message(
                chat_id=chat_id,
                text=self._truncate_telegram_text(self._format_followup_rows(rows=rows, heading="Open follow-ups")),
            )
            return {"ok": True, "message": "followups", "count": len(rows)}

        if text == "/due-today":
            rows = self.orchestration_service.list_due_today_followups(db=db, user=user, limit=20)
            if not rows:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="No follow-up items are due today.",
                )
                return {"ok": True, "message": "due_today_empty"}

            self.telegram_service.send_message(
                chat_id=chat_id,
                text=self._truncate_telegram_text(self._format_followup_rows(rows=rows, heading="Due today")),
            )
            return {"ok": True, "message": "due_today", "count": len(rows)}

        if text == "/ask":
            self.telegram_service.send_message(
                chat_id=chat_id,
                text="Usage: /ask <question about your inbox>",
            )
            return {"ok": True, "message": "ask_usage"}

        if text.startswith("/ask "):
            question = text.removeprefix("/ask ").strip()
            if not question:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="Usage: /ask <question about your inbox>",
                )
                return {"ok": True, "message": "ask_usage"}

            try:
                result = self.orchestration_service.answer_inbox_question(db=db, user=user, question=question)
            except Exception:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="Unable to answer that inbox question right now. Please try again.",
                )
                return {"ok": True, "message": "ask_failed"}

            if result.get("empty"):
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="I couldn't find recent Primary Inbox emails to answer that.",
                )
                return {"ok": True, "message": "ask_empty"}

            answer_lines = [f"Q: {question}", "", f"A: {result.get('answer') or 'No answer available.'}"]
            citations = list(result.get("citations") or [])
            if citations:
                answer_lines.append("")
                answer_lines.append("Sources:")
                answer_lines.extend(f"- {line}" for line in citations[:5])

            self.telegram_service.send_message(
                chat_id=chat_id,
                text=self._truncate_telegram_text("\n".join(answer_lines)),
            )
            return {"ok": True, "message": "ask_answered", "count": int(result.get("count", 0))}

        self.telegram_service.send_message(chat_id=chat_id, text="Unknown command. Send /help.")
        return {"ok": True, "message": "unknown_command"}

    def _handle_callback_query(self, db: Session, callback: dict) -> dict:
        data = str(callback.get("data") or "")
        callback_query_id = str(callback.get("id") or "")
        message = callback.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id") or "")

        if data.startswith("cmd:"):
            command_key = data.removeprefix("cmd:").strip()
            command_text = self.QUICK_COMMAND_MAP.get(command_key)
            if not command_text or not chat_id:
                if callback_query_id:
                    self.telegram_service.answer_callback_query(callback_query_id, "Unknown command.")
                return {"ok": True, "message": "unknown_callback_command"}

            if callback_query_id:
                self.telegram_service.answer_callback_query(callback_query_id, "Running command...")

            if command_text == "/connect":
                state = self.auth_state_service.create(chat_id=chat_id)
                auth_url = self.gmail_service.get_google_oauth_start_url(state=state)
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="Connect your Gmail account:",
                    reply_markup={"inline_keyboard": [[{"text": "Connect Gmail", "url": auth_url}]]},
                )
                return {"ok": True, "message": "connect_prompted"}

            user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
            if not user:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="This chat is not linked. Send /connect to connect Gmail.",
                )
                return {"ok": True, "message": "unlinked_callback_chat"}

            return self._handle_linked_command(db=db, user=user, chat_id=chat_id, text=command_text)

        if not data or ":" not in data or not chat_id:
            if callback_query_id:
                self.telegram_service.answer_callback_query(callback_query_id, "Invalid action.")
            return {"ok": True, "message": "invalid_callback"}

        action, raw_action_id = data.split(":", 1)
        try:
            action_id = UUID(raw_action_id)
        except ValueError:
            if callback_query_id:
                self.telegram_service.answer_callback_query(callback_query_id, "Invalid action id.")
            return {"ok": True, "message": "invalid_action_id"}
        if action not in {"approve", "reject"}:
            if callback_query_id:
                self.telegram_service.answer_callback_query(callback_query_id, "Unknown action.")
            return {"ok": True, "message": "unknown_action"}

        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if not user:
            if callback_query_id:
                self.telegram_service.answer_callback_query(callback_query_id, "Chat not linked.")
            return {"ok": True, "message": "unlinked_callback_chat"}

        decision = action
        result = self.orchestration_service.apply_action_callback(
            db=db,
            user=user,
            action_id=action_id,
            decision=decision,
            callback_query_id=callback_query_id,
        )

        if result.get("ok") and not result.get("already_handled"):
            row = db.query(AgentAction).filter(AgentAction.id == action_id).first()
            if row and row.execution_payload:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=f"Action {row.status}. Execution: {row.execution_payload}",
                )
        return result

    @staticmethod
    def _valid_schedule_time(raw: str) -> bool:
        if len(raw) != 5 or raw[2] != ":":
            return False
        hour_text, minute_text = raw.split(":", 1)
        if not (hour_text.isdigit() and minute_text.isdigit()):
            return False
        hour = int(hour_text)
        minute = int(minute_text)
        return 0 <= hour <= 23 and 0 <= minute <= 59

    @classmethod
    def _normalized_schedule_times(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if cls._valid_schedule_time(text):
                out.append(text)
        return sorted(set(out))

    @classmethod
    def _parse_digest_schedule_count(cls, raw_count: str) -> tuple[int | None, str | None]:
        if not raw_count:
            return None, "Usage: /schedule count <1-3>"
        if not raw_count.isdigit():
            return None, "Count must be a number from 1 to 3."

        count_value = int(raw_count)
        if not (1 <= count_value <= 3):
            return None, "Count must be between 1 and 3."
        return count_value, None

    @staticmethod
    def _parse_12h_hour_token(raw: str) -> str | None:
        normalized = raw.strip().lower().replace(" ", "")
        match = re.fullmatch(r"(1[0-2]|0?[1-9])(?::?([0-5][0-9]))?(am|pm)", normalized)
        if not match:
            return None

        hour_12 = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        suffix = match.group(3)
        if suffix == "am":
            hour_24 = 0 if hour_12 == 12 else hour_12
        else:
            hour_24 = 12 if hour_12 == 12 else hour_12 + 12
        return f"{hour_24:02d}:{minute:02d}"

    @classmethod
    def _parse_digest_schedule_times_12h(
        cls,
        raw_times: str,
        expected_count: int | None,
    ) -> tuple[list[str], str | None]:
        if not isinstance(expected_count, int) or not (1 <= expected_count <= 3):
            return [], "Set count first: /schedule count <1-3>"

        entries = [item.strip() for item in raw_times.split(",") if item.strip()]
        if not entries:
            return [], "Provide times using 12-hour format: /schedule times <8am,1015am[,620pm]>"
        if len(entries) != expected_count:
            return [], f"Count mismatch. You set {expected_count}; please provide exactly {expected_count} time(s)."

        normalized: list[str] = []
        for item in entries:
            slot = cls._parse_12h_hour_token(item)
            if slot is None:
                return [], f"Invalid time '{item}'. Use 12-hour format like 8am, 1015am, or 6:20pm."
            normalized.append(slot)

        unique = sorted(set(normalized))
        if len(unique) != len(normalized):
            return [], "Duplicate times are not allowed."
        return unique, None

    @staticmethod
    def _summary_section_lines(items: list[str]) -> list[str]:
        if not items:
            return ["- None"]
        return [f"- {item}" for item in items]

    def _format_today_summary_text(self, result: dict) -> str:
        summary = result.get("summary")
        if summary is None:
            return "Today's summary is unavailable. Please try again."

        if isinstance(summary, dict):
            overview = summary.get("overview") or "No overview provided."
            priority_items = list(summary.get("priority_items") or [])
            suggested_actions = list(summary.get("suggested_actions") or [])
        else:
            overview = getattr(summary, "overview", None) or "No overview provided."
            priority_items = list(getattr(summary, "priority_items", None) or [])
            suggested_actions = list(getattr(summary, "suggested_actions", None) or [])

        timezone_name = str(result.get("timezone", "UTC"))
        start_local = result.get("start_local")
        day_label = start_local.strftime("%Y-%m-%d") if isinstance(start_local, datetime) else "today"
        count = int(result.get("count", 0))

        lines = [
            "Today's AI Email Summary (Primary Inbox)",
            f"Date: {day_label} ({timezone_name})",
            f"Emails analyzed: {count}",
            "",
            "Overview:",
            str(overview).strip(),
            "",
            "Priority items:",
            *self._summary_section_lines(priority_items),
            "",
            "Suggested actions:",
            *self._summary_section_lines(suggested_actions),
        ]
        return "\n".join(lines)

    @classmethod
    def _truncate_telegram_text(cls, text: str) -> str:
        if len(text) <= cls.TELEGRAM_MAX_MESSAGE_LEN:
            return text

        suffix = "\n\n[Message truncated to fit Telegram limits.]"
        max_body_length = cls.TELEGRAM_MAX_MESSAGE_LEN - len(suffix)
        if max_body_length <= 0:
            return text[: cls.TELEGRAM_MAX_MESSAGE_LEN]
        return text[:max_body_length].rstrip() + suffix

    @staticmethod
    def _format_followup_rows(*, rows: list, heading: str) -> str:
        lines = [heading]
        for idx, row in enumerate(rows, start=1):
            due_label = row.due_at.strftime("%Y-%m-%d %H:%M UTC") if row.due_at else (row.due_label or "No due time")
            lines.append(f"{idx}. {row.task_text} | due: {due_label}")
        return "\n".join(lines)
