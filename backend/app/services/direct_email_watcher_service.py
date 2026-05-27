from datetime import datetime, timezone
import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.models.direct_email_watch_event import DirectEmailWatchEvent
from app.models.draft_reply import DraftReply
from app.models.email import Email
from app.models.user import User
from app.schemas.direct_email_schema import DirectEmailClassificationOutput
from app.services.agent_service import AgentService
from app.services.gmail_service import GmailService
from app.services.telegram_direct_email_formatter import TelegramDirectEmailFormatter
from app.services.telegram_service import TelegramService


class DirectEmailWatcherService:
    def __init__(
        self,
        *,
        gmail_service: GmailService,
        agent_service: AgentService,
        telegram_service: TelegramService,
        formatter: TelegramDirectEmailFormatter,
    ):
        self.gmail_service = gmail_service
        self.agent_service = agent_service
        self.telegram_service = telegram_service
        self.formatter = formatter
        self.logger = logging.getLogger(__name__)

    def run_cycle(self, db: Session, *, now_utc: datetime | None = None) -> dict:
        if not settings.direct_email_watcher_enabled:
            return {"status": "skipped", "reason": "direct_email_watcher_disabled"}

        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        users = (
            db.query(User)
            .filter(User.telegram_chat_id.is_not(None))
            .filter(User.encrypted_access_token.is_not(None))
            .filter(User.encrypted_refresh_token.is_not(None))
            .all()
        )
        processed_users = 0
        processed_emails = 0
        created_drafts = 0
        failures = 0

        for user in users:
            try:
                result = self._process_user(db=db, user=user, now_utc=now)
                processed_users += 1
                processed_emails += result["processed_emails"]
                created_drafts += result["created_drafts"]
                failures += result["failures"]
            except Exception as exc:
                db.rollback()
                failures += 1
                self.logger.exception("direct_email_watcher_user_failed user_id=%s error=%s", user.id, exc)

        return {
            "status": "completed",
            "processed_users": processed_users,
            "processed_emails": processed_emails,
            "created_drafts": created_drafts,
            "failures": failures,
        }

    def _process_user(self, db: Session, user: User, now_utc: datetime) -> dict:
        candidates = self.gmail_service.fetch_direct_email_candidates(
            user=user,
            db=db,
            max_results=settings.direct_email_watch_max_messages,
            lookback_hours=settings.direct_email_watch_lookback_hours,
        )
        processed_emails = 0
        created_drafts = 0
        failures = 0

        for candidate in candidates:
            email_row = self._upsert_email_row(db=db, user=user, candidate=candidate)

            if self._is_already_processed(db=db, email_row=email_row):
                continue

            if self._already_has_gmail_draft(db=db, email_row=email_row):
                self._create_event(
                    db=db,
                    email_row=email_row,
                    status="draft_already_exists",
                    classification=None,
                    draft_preview=None,
                    gmail_draft_id=None,
                    error_summary=None,
                    telegram_notified=False,
                )
                processed_emails += 1
                continue

            if not self.is_likely_direct_human_email(candidate=candidate, user=user):
                self._create_event(
                    db=db,
                    email_row=email_row,
                    status="filtered_out",
                    classification=None,
                    draft_preview=None,
                    gmail_draft_id=None,
                    error_summary=None,
                    telegram_notified=False,
                )
                processed_emails += 1
                continue

            email_content = self._email_content(candidate=candidate)
            try:
                classification = self.agent_service.classify_direct_email(email_content=email_content)
            except Exception as exc:
                self._create_event(
                    db=db,
                    email_row=email_row,
                    status="classification_failed",
                    classification=None,
                    draft_preview=None,
                    gmail_draft_id=None,
                    error_summary=self._safe_error_summary(exc),
                    telegram_notified=False,
                )
                failures += 1
                processed_emails += 1
                continue

            if not classification.is_direct_email:
                self._create_event(
                    db=db,
                    email_row=email_row,
                    status="not_direct",
                    classification=classification,
                    draft_preview=None,
                    gmail_draft_id=None,
                    error_summary=None,
                    telegram_notified=False,
                )
                processed_emails += 1
                continue

            if not classification.needs_reply:
                telegram_notified = False
                if settings.direct_email_watch_notify_no_reply and user.telegram_chat_id:
                    text = self.formatter.format_success_notification(
                        sender=candidate.get("sender_email") or "unknown@example.com",
                        subject=candidate.get("subject") or "(No subject)",
                        received_at=candidate.get("received_at"),
                        urgency=classification.urgency,
                        summary=classification.summary,
                        suggested_action=classification.suggested_action,
                        draft_preview="No draft generated because no reply is needed.",
                        draft_id="N/A",
                    )
                    telegram_notified = bool(
                        self.telegram_service.send_message(
                            chat_id=user.telegram_chat_id,
                            text=text,
                            parse_mode="Markdown",
                        )
                    )
                self._create_event(
                    db=db,
                    email_row=email_row,
                    status="no_reply_needed",
                    classification=classification,
                    draft_preview=None,
                    gmail_draft_id=None,
                    error_summary=None,
                    telegram_notified=telegram_notified,
                )
                processed_emails += 1
                continue

            try:
                draft_reply = self.agent_service.generate_direct_email_reply(
                    email_content=email_content,
                    classification=classification,
                )
            except Exception as exc:
                self._create_event(
                    db=db,
                    email_row=email_row,
                    status="draft_generation_failed",
                    classification=classification,
                    draft_preview=None,
                    gmail_draft_id=None,
                    error_summary=self._safe_error_summary(exc),
                    telegram_notified=False,
                )
                failures += 1
                processed_emails += 1
                continue

            try:
                gmail_draft_id = self.gmail_service.create_gmail_reply_draft(
                    user=user,
                    db=db,
                    original_email=candidate,
                    draft_body=draft_reply,
                )
                self._record_draft_reply(db=db, email_row=email_row, draft_body=draft_reply, gmail_draft_id=gmail_draft_id)
                telegram_notified = self._send_draft_created_notification(
                    user=user,
                    candidate=candidate,
                    classification=classification,
                    draft_reply=draft_reply,
                    draft_id=gmail_draft_id,
                )
                self._create_event(
                    db=db,
                    email_row=email_row,
                    status="draft_created",
                    classification=classification,
                    draft_preview=draft_reply,
                    gmail_draft_id=gmail_draft_id,
                    error_summary=None,
                    telegram_notified=telegram_notified,
                )
                created_drafts += 1
                processed_emails += 1
            except Exception as exc:
                telegram_notified = self._send_draft_creation_failed_notification(
                    user=user,
                    candidate=candidate,
                    classification=classification,
                    draft_reply=draft_reply,
                    error_summary=self._safe_error_summary(exc),
                )
                self._create_event(
                    db=db,
                    email_row=email_row,
                    status="draft_creation_failed",
                    classification=classification,
                    draft_preview=draft_reply,
                    gmail_draft_id=None,
                    error_summary=self._safe_error_summary(exc),
                    telegram_notified=telegram_notified,
                )
                failures += 1
                processed_emails += 1

        return {
            "processed_emails": processed_emails,
            "created_drafts": created_drafts,
            "failures": failures,
        }

    @staticmethod
    def is_likely_direct_human_email(*, candidate: dict, user: User) -> bool:
        sender = str(candidate.get("sender_email") or "").strip().lower()
        subject = str(candidate.get("subject") or "").strip().lower()
        if not sender:
            return False
        if sender == user.email.strip().lower():
            return False

        blocked_terms = [
            "noreply",
            "no-reply",
            "do-not-reply",
            "donotreply",
            "notification",
            "notifications",
            "newsletter",
            "jobalerts",
            "job-alerts",
            "jobs-noreply",
            "updates",
            "marketing",
            "promo",
            "support@",
            "security",
            "github",
            "linkedin",
            "google",
            "telegram",
            "alerts",
            "receipt",
        ]
        if any(term in sender for term in blocked_terms):
            return False
        if any(term in subject for term in ("newsletter", "unsubscribe", "otp", "verification code", "receipt")):
            return False

        list_unsubscribe = str(candidate.get("list_unsubscribe_header") or "").strip()
        if list_unsubscribe:
            return False

        auto_submitted = str(candidate.get("auto_submitted_header") or "").strip().lower()
        if auto_submitted and auto_submitted != "no":
            return False

        precedence = str(candidate.get("precedence_header") or "").strip().lower()
        if precedence in {"bulk", "list", "junk", "auto_reply"}:
            return False

        if bool(candidate.get("is_bulk")):
            return False
        return True

    def _is_already_processed(self, *, db: Session, email_row: Email) -> bool:
        existing = db.query(DirectEmailWatchEvent).filter(DirectEmailWatchEvent.email_id == email_row.id).first()
        return existing is not None

    def _already_has_gmail_draft(self, *, db: Session, email_row: Email) -> bool:
        row = (
            db.query(DraftReply)
            .filter(DraftReply.email_id == email_row.id)
            .filter(DraftReply.gmail_draft_id.is_not(None))
            .first()
        )
        return row is not None

    def _record_draft_reply(self, *, db: Session, email_row: Email, draft_body: str, gmail_draft_id: str) -> None:
        draft = DraftReply(
            email_id=email_row.id,
            draft_body=draft_body,
            tone="professional",
            status="created_in_gmail",
            gmail_draft_id=gmail_draft_id,
        )
        db.add(draft)
        db.commit()

    def _create_event(
        self,
        *,
        db: Session,
        email_row: Email,
        status: str,
        classification: DirectEmailClassificationOutput | None,
        draft_preview: str | None,
        gmail_draft_id: str | None,
        error_summary: str | None,
        telegram_notified: bool,
    ) -> None:
        event = DirectEmailWatchEvent(
            email_id=email_row.id,
            user_id=email_row.user_id,
            gmail_message_id=email_row.gmail_message_id,
            gmail_thread_id=email_row.gmail_thread_id,
            status=status,
            classification_json=classification.model_dump() if classification else {},
            urgency=classification.urgency if classification else None,
            summary=classification.summary if classification else None,
            suggested_action=classification.suggested_action if classification else None,
            reply_intent=classification.reply_intent if classification else None,
            draft_preview=draft_preview,
            gmail_draft_id=gmail_draft_id,
            error_summary=error_summary,
            telegram_notified=telegram_notified,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()

    def _send_draft_created_notification(
        self,
        *,
        user: User,
        candidate: dict,
        classification: DirectEmailClassificationOutput,
        draft_reply: str,
        draft_id: str,
    ) -> bool:
        if not user.telegram_chat_id:
            return False
        text = self.formatter.format_success_notification(
            sender=candidate.get("sender_email") or "unknown@example.com",
            subject=candidate.get("subject") or "(No subject)",
            received_at=candidate.get("received_at"),
            urgency=classification.urgency,
            summary=classification.summary,
            suggested_action=classification.suggested_action,
            draft_preview=draft_reply,
            draft_id=draft_id,
        )
        return bool(
            self.telegram_service.send_message(
                chat_id=user.telegram_chat_id,
                text=text,
                parse_mode="Markdown",
            )
        )

    def _send_draft_creation_failed_notification(
        self,
        *,
        user: User,
        candidate: dict,
        classification: DirectEmailClassificationOutput,
        draft_reply: str,
        error_summary: str,
    ) -> bool:
        if not user.telegram_chat_id:
            return False
        text = self.formatter.format_failure_notification(
            sender=candidate.get("sender_email") or "unknown@example.com",
            subject=candidate.get("subject") or "(No subject)",
            urgency=classification.urgency,
            summary=classification.summary,
            suggested_action=classification.suggested_action,
            draft_preview=draft_reply,
            error_summary=error_summary,
        )
        return bool(
            self.telegram_service.send_message(
                chat_id=user.telegram_chat_id,
                text=text,
                parse_mode="Markdown",
            )
        )

    @staticmethod
    def _safe_error_summary(exc: Exception, max_len: int = 300) -> str:
        summary = " ".join(str(exc).split()).strip() or "Unknown error"
        if len(summary) <= max_len:
            return summary
        return summary[: max_len - 3].rstrip() + "..."

    @staticmethod
    def _email_content(candidate: dict) -> str:
        return (
            f"From: {candidate.get('sender_name') or ''} <{candidate.get('sender_email') or ''}>\n"
            f"To: {', '.join(candidate.get('recipients') or [])}\n"
            f"Subject: {candidate.get('subject') or '(No subject)'}\n"
            f"Received: {candidate.get('received_at')}\n\n"
            f"{candidate.get('body_text') or candidate.get('snippet') or ''}"
        )

    def _upsert_email_row(self, *, db: Session, user: User, candidate: dict) -> Email:
        gmail_message_id = str(candidate.get("id") or "").strip()
        existing = db.query(Email).filter(Email.gmail_message_id == gmail_message_id).first() if gmail_message_id else None
        if existing:
            return existing

        row = Email(
            user_id=user.id,
            gmail_message_id=gmail_message_id,
            gmail_thread_id=str(candidate.get("threadId") or ""),
            sender_email=str(candidate.get("sender_email") or "unknown@example.com"),
            sender_name=candidate.get("sender_name"),
            recipients=list(candidate.get("recipients") or []),
            subject=candidate.get("subject"),
            snippet=candidate.get("snippet"),
            body_text=str(candidate.get("body_text") or candidate.get("snippet") or ""),
            received_at=candidate.get("received_at") or datetime.now(timezone.utc),
            is_read=bool(candidate.get("is_read")),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
