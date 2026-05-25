from datetime import timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.agent_action import AgentAction
from app.models.user import User
from app.models.user_rule import UserRule
from app.services.gmail_service import GmailService
from app.services.telegram_auth_state_service import TelegramAuthStateService
from app.services.telegram_orchestration_service import TelegramOrchestrationService
from app.services.telegram_service import TelegramService


class TelegramBotService:
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

        if text == "/help":
            self.telegram_service.send_message(
                chat_id=chat_id,
                text=(
                    "Commands:\n"
                    "/connect - connect or reconnect Gmail\n"
                    "/status - show linked account\n"
                    "/latest - show 10 latest primary inbox emails\n"
                    "/sync - sync inbox and analyze new messages\n"
                    "/digest - send latest digest\n"
                    "/digest_schedule status|set|on|off - manage scheduled digests\n"
                    "/timezone set <IANA> - set timezone for schedule windows\n"
                    "/pending - list pending approvals\n"
                    "/rules - list active rules\n"
                    "/rule add <text> - add a rule\n"
                    "/rule del <rule-id> - delete a rule"
                ),
            )
            return {"ok": True, "message": "help"}

        if text == "/status":
            self.telegram_service.send_message(
                chat_id=chat_id,
                text=f"Linked account: {user.email}",
            )
            return {"ok": True, "message": "status", "user_id": str(user.id)}

        if text.startswith("/timezone"):
            if text == "/timezone":
                self.telegram_service.send_message(chat_id=chat_id, text=f"Current timezone: {user.timezone}")
                return {"ok": True, "message": "timezone_status"}
            if text.startswith("/timezone set "):
                timezone_name = text.removeprefix("/timezone set ").strip()
                if not timezone_name:
                    self.telegram_service.send_message(chat_id=chat_id, text="Usage: /timezone set <IANA timezone>")
                    return {"ok": True, "message": "timezone_invalid"}
                try:
                    ZoneInfo(timezone_name)
                except ZoneInfoNotFoundError:
                    self.telegram_service.send_message(
                        chat_id=chat_id,
                        text="Invalid timezone. Example: /timezone set Asia/Singapore",
                    )
                    return {"ok": True, "message": "timezone_invalid"}

                user.timezone = timezone_name
                db.add(user)
                db.commit()
                self.telegram_service.send_message(chat_id=chat_id, text=f"Timezone updated to {timezone_name}.")
                return {"ok": True, "message": "timezone_set", "timezone": timezone_name}

            self.telegram_service.send_message(chat_id=chat_id, text="Usage: /timezone set <IANA timezone>")
            return {"ok": True, "message": "timezone_invalid"}

        if text.startswith("/digest_schedule"):
            if text == "/digest_schedule":
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=(
                        "Usage:\n"
                        "/digest_schedule status\n"
                        "/digest_schedule set HH:MM[,HH:MM[,HH:MM]]\n"
                        "/digest_schedule on\n"
                        "/digest_schedule off"
                    ),
                )
                return {"ok": True, "message": "digest_schedule_usage"}

            if text == "/digest_schedule status":
                times = self._normalized_schedule_times(user.digest_schedule_times)
                status = "enabled" if user.scheduled_digest_enabled else "disabled"
                times_label = ", ".join(times) if times else "(not set)"
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text=f"Digest schedule is {status}.\nTimezone: {user.timezone}\nTimes: {times_label}",
                )
                return {"ok": True, "message": "digest_schedule_status"}

            if text.startswith("/digest_schedule set "):
                raw_times = text.removeprefix("/digest_schedule set ").strip()
                schedule_times, validation_error = self._parse_digest_schedule_times(raw_times)
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

            if text == "/digest_schedule on":
                times = self._normalized_schedule_times(user.digest_schedule_times)
                if not times:
                    self.telegram_service.send_message(
                        chat_id=chat_id,
                        text="Set times first: /digest_schedule set HH:MM[,HH:MM[,HH:MM]]",
                    )
                    return {"ok": True, "message": "digest_schedule_on_missing_times"}

                user.scheduled_digest_enabled = True
                db.add(user)
                db.commit()
                self.telegram_service.send_message(chat_id=chat_id, text="Scheduled digests enabled.")
                return {"ok": True, "message": "digest_schedule_on"}

            if text == "/digest_schedule off":
                user.scheduled_digest_enabled = False
                db.add(user)
                db.commit()
                self.telegram_service.send_message(chat_id=chat_id, text="Scheduled digests disabled.")
                return {"ok": True, "message": "digest_schedule_off"}

            self.telegram_service.send_message(
                chat_id=chat_id,
                text=(
                    "Usage:\n"
                    "/digest_schedule status\n"
                    "/digest_schedule set HH:MM[,HH:MM[,HH:MM]]\n"
                    "/digest_schedule on\n"
                    "/digest_schedule off"
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

        if text == "/sync":
            result = self.orchestration_service.sync_and_analyze(db=db, user=user)
            self.telegram_service.send_message(
                chat_id=chat_id,
                text=(
                    f"Sync complete.\nFetched: {result['fetched']}\nNew: {result['synced']}\n"
                    f"Analysed: {result['analysed']}\nUrgent alerts: {result['urgent_alerts']}"
                ),
            )
            return {"ok": True, "message": "sync", "result": result}

        if text == "/digest":
            result = self.orchestration_service.generate_and_send_digest(db=db, user=user)
            if result.get("sent"):
                self.telegram_service.send_message(chat_id=chat_id, text="Digest delivered.")
            else:
                self.telegram_service.send_message(chat_id=chat_id, text=f"Digest not sent: {result}")
            return {"ok": True, "message": "digest", "result": result}

        if text == "/pending":
            result = self.orchestration_service.send_pending_actions(db=db, user=user)
            if result.get("pending", 0) == 0:
                self.telegram_service.send_message(chat_id=chat_id, text="No pending actions.")
            return {"ok": True, "message": "pending", "result": result}

        if text == "/rules":
            rows = (
                db.query(UserRule)
                .filter(UserRule.user_id == user.id)
                .filter(UserRule.is_active.is_(True))
                .order_by(UserRule.created_at.desc())
                .all()
            )
            if not rows:
                self.telegram_service.send_message(chat_id=chat_id, text="No active rules.")
            else:
                lines = [f"{rule.id}: {rule.rule_text}" for rule in rows[:20]]
                self.telegram_service.send_message(chat_id=chat_id, text="Active rules:\n" + "\n".join(lines))
            return {"ok": True, "message": "rules_list"}

        if text.startswith("/rule add "):
            rule_text = text.removeprefix("/rule add ").strip()
            if not rule_text:
                self.telegram_service.send_message(chat_id=chat_id, text="Usage: /rule add <text>")
                return {"ok": True, "message": "rule_add_invalid"}
            row = UserRule(user_id=user.id, rule_text=rule_text, is_active=True)
            db.add(row)
            db.commit()
            db.refresh(row)
            self.telegram_service.send_message(chat_id=chat_id, text=f"Rule added: {row.id}")
            return {"ok": True, "message": "rule_added", "rule_id": str(row.id)}

        if text.startswith("/rule del "):
            raw_id = text.removeprefix("/rule del ").strip()
            try:
                rule_id = UUID(raw_id)
            except ValueError:
                self.telegram_service.send_message(chat_id=chat_id, text="Invalid rule id.")
                return {"ok": True, "message": "rule_delete_invalid_id"}

            row = db.query(UserRule).filter(UserRule.id == rule_id, UserRule.user_id == user.id).first()
            if not row:
                self.telegram_service.send_message(chat_id=chat_id, text="Rule not found.")
                return {"ok": True, "message": "rule_not_found"}
            db.delete(row)
            db.commit()
            self.telegram_service.send_message(chat_id=chat_id, text="Rule deleted.")
            return {"ok": True, "message": "rule_deleted"}

        self.telegram_service.send_message(chat_id=chat_id, text="Unknown command. Send /help.")
        return {"ok": True, "message": "unknown_command"}

    def _handle_callback_query(self, db: Session, callback: dict) -> dict:
        data = str(callback.get("data") or "")
        callback_query_id = str(callback.get("id") or "")
        message = callback.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id") or "")
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
    def _parse_digest_schedule_times(cls, raw_times: str) -> tuple[list[str], str | None]:
        entries = [item.strip() for item in raw_times.split(",") if item.strip()]
        if not entries:
            return [], "Please provide 1-3 times: /digest_schedule set HH:MM[,HH:MM[,HH:MM]]"
        if len(entries) > 3:
            return [], "You can set at most 3 times per day."

        normalized: list[str] = []
        for item in entries:
            if not cls._valid_schedule_time(item):
                return [], f"Invalid time '{item}'. Use 24-hour HH:MM format."
            normalized.append(item)

        unique = sorted(set(normalized))
        if len(unique) != len(normalized):
            return [], "Duplicate times are not allowed."
        return unique, None
