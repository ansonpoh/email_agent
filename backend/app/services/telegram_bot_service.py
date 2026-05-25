from uuid import UUID

from sqlalchemy.orm import Session

from app.models.agent_action import AgentAction
from app.models.user import User
from app.models.user_rule import UserRule
from app.services.telegram_link_service import TelegramLinkService
from app.services.telegram_orchestration_service import TelegramOrchestrationService
from app.services.telegram_service import TelegramService


class TelegramBotService:
    def __init__(
        self,
        telegram_service: TelegramService,
        link_service: TelegramLinkService,
        orchestration_service: TelegramOrchestrationService,
    ):
        self.telegram_service = telegram_service
        self.link_service = link_service
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
            parts = text.split(maxsplit=1)
            token = parts[1].strip() if len(parts) > 1 else ""
            if not token:
                self.telegram_service.send_message(
                    chat_id=chat_id,
                    text="Welcome. Use your link token from backend setup: /start <token>",
                )
                return {"ok": True, "message": "start_without_token"}

            user = self.link_service.confirm_link(db=db, token=token, chat_id=chat_id)
            if not user:
                self.telegram_service.send_message(chat_id=chat_id, text="Link token invalid or expired.")
                return {"ok": True, "message": "link_failed"}

            self.telegram_service.send_message(chat_id=chat_id, text=f"Linked successfully to {user.email}.")
            return {"ok": True, "message": "linked", "user_id": str(user.id)}

        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if not user:
            self.telegram_service.send_message(
                chat_id=chat_id,
                text="This chat is not linked. Generate a /start link token from backend setup first.",
            )
            return {"ok": True, "message": "unlinked_chat"}

        if text == "/help":
            self.telegram_service.send_message(
                chat_id=chat_id,
                text=(
                    "Commands:\n"
                    "/sync - sync inbox and analyze new messages\n"
                    "/digest - send latest digest\n"
                    "/pending - list pending approvals\n"
                    "/rules - list active rules\n"
                    "/rule add <text> - add a rule\n"
                    "/rule del <rule-id> - delete a rule"
                ),
            )
            return {"ok": True, "message": "help"}

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
