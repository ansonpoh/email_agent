from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_action import AgentAction
from app.models.email import Email
from app.models.email_analysis import EmailAnalysis
from app.models.scheduled_run import ScheduledRun
from app.models.user import User
from app.services.action_execution_service import ActionExecutionService
from app.services.agent_service import AgentService
from app.services.pipeline_service import PipelineService
from app.services.telegram_digest_formatter import TelegramDigestFormatter
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)


class TelegramOrchestrationService:
    TELEGRAM_MAX_MESSAGE_LEN = 4096

    def __init__(
        self,
        pipeline_service: PipelineService,
        agent_service: AgentService,
        telegram_service: TelegramService,
        action_execution_service: ActionExecutionService,
        telegram_digest_formatter: TelegramDigestFormatter,
    ):
        self.pipeline_service = pipeline_service
        self.agent_service = agent_service
        self.telegram_service = telegram_service
        self.action_execution_service = action_execution_service
        self.telegram_digest_formatter = telegram_digest_formatter

    def sync_and_analyze(self, db: Session, user: User) -> dict:
        sync_result = self.pipeline_service.sync_user_emails(db=db, user=user)
        email_ids = sync_result.get("created_email_ids", [])
        emails = db.query(Email).filter(Email.id.in_(email_ids)).order_by(Email.received_at.desc()).all() if email_ids else []

        analysed = 0
        urgent_alerts = 0
        for email_row in emails:
            analysis, action_row = self._create_or_update_analysis_action(
                db=db,
                user=user,
                email_row=email_row,
                user_rules=[],
            )
            analysed += 1
            if self._maybe_send_urgent_alert(db=db, user=user, email_row=email_row, analysis=analysis, action_row=action_row):
                urgent_alerts += 1

        return {
            "synced": sync_result["synced"],
            "fetched": sync_result["fetched"],
            "analysed": analysed,
            "urgent_alerts": urgent_alerts,
            "last_checked_at": sync_result["last_checked_at"],
        }

    def analyze_existing_email(self, db: Session, user: User, email_row: Email) -> tuple[EmailAnalysis, AgentAction | None]:
        analysis, action_row = self._create_or_update_analysis_action(
            db=db,
            user=user,
            email_row=email_row,
            user_rules=[],
        )
        self._maybe_send_urgent_alert(db=db, user=user, email_row=email_row, analysis=analysis, action_row=action_row)
        return analysis, action_row

    def generate_and_send_digest(
        self,
        db: Session,
        user: User,
        run_key: str | None = None,
        job_type: str = "manual_digest",
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> dict:
        if not user.telegram_chat_id:
            return {"sent": False, "reason": "telegram_not_linked"}

        if run_key:
            if not self._reserve_scheduled_run(db=db, user=user, job_type=job_type, run_key=run_key):
                return {"sent": False, "skipped_duplicate": True}

        try:
            result = self.pipeline_service.generate_digest_for_user(
                db=db,
                user=user,
                period_start=period_start,
                period_end=period_end,
            )
        except Exception as exc:
            db.rollback()
            logger.warning("digest_generation_failed user_id=%s error=%s", user.id, exc)
            return {"sent": False, "reason": "digest_generation_failed", "error": str(exc)}

        digest = result["digest"]
        digest_data = result.get("digest_data") or {}
        formatted_digest_message = self.telegram_digest_formatter.format_email_digest_for_telegram(
            digest=result["output"],
            email_rows=digest_data.get("email_rows"),
            generated_at=digest_data.get("generated_at"),
            timezone_name=digest_data.get("timezone_name") or (user.timezone or "UTC"),
        )
        sent_payload = self.telegram_service.send_message(
            chat_id=user.telegram_chat_id,
            text=self._truncate_telegram_text(formatted_digest_message),
            parse_mode=self.telegram_digest_formatter.PARSE_MODE,
        )
        if not sent_payload:
            return {"sent": False, "digest_id": str(digest.id)}

        digest.sent_to_telegram = True
        db.add(digest)
        db.commit()
        return {"sent": True, "digest_id": str(digest.id), "idempotent_reuse": result["idempotent_reuse"]}

    def send_pending_actions(self, db: Session, user: User) -> dict:
        if not user.telegram_chat_id:
            return {"sent": 0, "reason": "telegram_not_linked"}

        actions = (
            db.query(AgentAction)
            .join(AgentAction.email)
            .filter(AgentAction.status == "pending")
            .filter(AgentAction.email.has(user_id=user.id))
            .order_by(AgentAction.created_at.desc())
            .all()
        )

        sent = 0
        for action in actions:
            email_row = action.email
            text = (
                f"Pending action: {action.action_type}\n"
                f"Email: {(email_row.subject or '(No subject)')}\n"
                f"Sender: {email_row.sender_email}\n"
                f"Suggestion: {action.suggested_payload.get('suggested_action', 'Review in app')}"
            )
            callback_data = f"approve:{action.id}"
            result = self.telegram_service.send_message(
                chat_id=user.telegram_chat_id,
                text=text,
                reply_markup=self.telegram_service.approval_markup(str(action.id)),
            )
            if result:
                action.telegram_chat_id = user.telegram_chat_id
                action.telegram_message_id = str(result.get("message_id"))
                action.telegram_callback_data = callback_data
                db.add(action)
                sent += 1

        db.commit()
        return {"sent": sent, "pending": len(actions)}

    def generate_today_summary(self, db: Session, user: User) -> dict:
        timezone_name = user.timezone or "UTC"
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            timezone_name = "UTC"
            tz = ZoneInfo("UTC")

        now_local = datetime.now(tz)
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        rows = self.pipeline_service.gmail_service.fetch_primary_inbox_between(
            user=user,
            db=db,
            start_utc=start_utc,
            end_utc=end_utc,
            limit=50,
        )
        if not rows:
            return {
                "empty": True,
                "count": 0,
                "timezone": timezone_name,
                "start_local": start_local,
                "end_local": end_local,
            }

        summary = self.agent_service.summarize_emails_for_today(
            emails=rows,
            user_timezone=timezone_name,
        )
        return {
            "empty": False,
            "count": len(rows),
            "timezone": timezone_name,
            "start_local": start_local,
            "end_local": end_local,
            "summary": summary,
        }

    def apply_action_callback(
        self,
        db: Session,
        user: User,
        action_id: UUID,
        decision: str,
        callback_query_id: str | None = None,
    ) -> dict:
        row = db.query(AgentAction).filter(AgentAction.id == action_id).first()
        if not row or row.email.user_id != user.id:
            return {"ok": False, "message": "Action not found"}

        if row.status != "pending":
            if callback_query_id:
                self.telegram_service.answer_callback_query(callback_query_id, "Action already handled.")
            return {"ok": True, "already_handled": True, "status": row.status}

        if decision == "approve":
            execution = self.action_execution_service.approve_action(db=db, action=row)
        else:
            execution = self.action_execution_service.reject_action(db=db, action=row)

        row.telegram_callback_handled_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)

        if callback_query_id:
            self.telegram_service.answer_callback_query(callback_query_id, f"Action {row.status}.")
        return {"ok": True, "status": row.status, "action_id": str(row.id), "execution": execution}

    def _reserve_scheduled_run(self, db: Session, user: User, job_type: str, run_key: str) -> bool:
        lock_key = f"{user.id}:{run_key}"
        row = ScheduledRun(user_id=user.id, job_type=job_type, run_key=lock_key)
        db.add(row)
        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False

    def _create_or_update_analysis_action(
        self,
        db: Session,
        user: User,
        email_row: Email,
        user_rules: list[str],
    ) -> tuple[EmailAnalysis, AgentAction | None]:
        analysis_output = self.agent_service.analyse_email(
            subject=email_row.subject,
            body_text=email_row.body_text,
            user_rules=user_rules,
        )

        analysis = db.query(EmailAnalysis).filter(EmailAnalysis.email_id == email_row.id).first()
        if analysis:
            analysis.category = analysis_output.category
            analysis.priority_score = analysis_output.priority_score
            analysis.summary = analysis_output.summary
            analysis.key_points = analysis_output.key_points
            analysis.extracted_tasks = analysis_output.extracted_tasks
            analysis.extracted_deadlines = analysis_output.extracted_deadlines
            analysis.suggested_action = analysis_output.suggested_action
            analysis.confidence_score = analysis_output.confidence_score
        else:
            analysis = EmailAnalysis(
                email_id=email_row.id,
                category=analysis_output.category,
                priority_score=analysis_output.priority_score,
                summary=analysis_output.summary,
                key_points=analysis_output.key_points,
                extracted_tasks=analysis_output.extracted_tasks,
                extracted_deadlines=analysis_output.extracted_deadlines,
                suggested_action=analysis_output.suggested_action,
                confidence_score=analysis_output.confidence_score,
            )
            db.add(analysis)

        action_row: AgentAction | None = None
        if analysis_output.suggested_action:
            action_row = (
                db.query(AgentAction)
                .filter(AgentAction.email_id == email_row.id)
                .filter(AgentAction.action_type == "reply_suggestion")
                .filter(AgentAction.status == "pending")
                .first()
            )
            if action_row is None:
                action_row = AgentAction(
                    email_id=email_row.id,
                    action_type="reply_suggestion",
                    status="pending",
                    suggested_payload={"suggested_action": analysis_output.suggested_action, "tone": "professional"},
                    requires_approval=True,
                )
                db.add(action_row)

        db.commit()
        db.refresh(analysis)
        if action_row:
            db.refresh(action_row)
        return analysis, action_row

    def _maybe_send_urgent_alert(
        self,
        db: Session,
        user: User,
        email_row: Email,
        analysis: EmailAnalysis,
        action_row: AgentAction | None,
    ) -> bool:
        if not user.telegram_chat_id:
            return False
        if not user.urgent_alerts_enabled:
            return False
        if analysis.priority_score < settings.telegram_urgent_threshold:
            return False
        if analysis.urgent_alert_sent:
            return False

        text = (
            "Urgent email detected\n"
            f"From: {email_row.sender_email}\n"
            f"Subject: {email_row.subject or '(No subject)'}\n"
            f"Summary: {analysis.summary}"
        )
        markup = self.telegram_service.approval_markup(str(action_row.id)) if action_row else None
        result = self.telegram_service.send_message(chat_id=user.telegram_chat_id, text=text, reply_markup=markup)
        if not result:
            return False

        analysis.urgent_alert_sent = True
        db.add(analysis)
        if action_row:
            action_row.telegram_chat_id = user.telegram_chat_id
            action_row.telegram_message_id = str(result.get("message_id"))
            action_row.telegram_callback_data = f"approve:{action_row.id}"
            db.add(action_row)
        db.commit()
        return True

    @classmethod
    def _truncate_telegram_text(cls, text: str) -> str:
        if len(text) <= cls.TELEGRAM_MAX_MESSAGE_LEN:
            return text

        suffix = "\n\n[Message truncated to fit Telegram limits.]"
        max_body_length = cls.TELEGRAM_MAX_MESSAGE_LEN - len(suffix)
        if max_body_length <= 0:
            return text[: cls.TELEGRAM_MAX_MESSAGE_LEN]
        return text[:max_body_length].rstrip() + suffix
