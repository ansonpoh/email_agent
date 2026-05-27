from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
from app.models.digest import Digest
from app.models.email import Email
from app.models.email_analysis import EmailAnalysis
from app.models.user import User
from app.services.agent_service import AgentService
from app.services.digest_service import DigestService
from app.services.gmail_service import GmailService


class PipelineService:
    def __init__(self, gmail_service: GmailService, digest_service: DigestService, agent_service: AgentService):
        self.gmail_service = gmail_service
        self.digest_service = digest_service
        self.agent_service = agent_service

    def sync_user_emails(self, db: Session, user: User, since: datetime | None = None) -> dict:
        sync_since = since if since is not None else user.last_checked_at
        incoming = self.gmail_service.fetch_emails_since(user=user, since=sync_since, db=db)
        created = 0
        created_email_ids: list = []

        for item in incoming:
            exists = db.query(Email).filter(Email.gmail_message_id == item["gmail_message_id"]).first()
            if exists:
                continue
            row = Email(**item)
            db.add(row)
            db.flush()
            created_email_ids.append(row.id)
            created += 1

        user.last_checked_at = datetime.utcnow()
        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "synced": created,
            "fetched": len(incoming),
            "last_checked_at": user.last_checked_at,
            "created_email_ids": created_email_ids,
        }

    def generate_digest_for_user(
        self,
        db: Session,
        user: User,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> dict:
        period_end_value = period_end or datetime.utcnow()
        period_start_value = period_start or user.last_checked_at or (period_end_value - timedelta(days=1))
        window_start = period_end_value - timedelta(minutes=settings.digest_idempotency_window_minutes)

        existing_query = (
            db.query(Digest)
            .filter(Digest.user_id == user.id)
            .filter(Digest.period_start == period_start_value)
            .filter(Digest.period_end == period_end_value)
        )
        if period_start is None or period_end is None:
            existing_query = existing_query.filter(Digest.created_at >= window_start)
        existing = existing_query.order_by(Digest.created_at.desc()).first()

        rows = (
            db.query(Email, EmailAnalysis)
            .outerjoin(EmailAnalysis, Email.id == EmailAnalysis.email_id)
            .filter(Email.user_id == user.id)
            .filter(Email.received_at >= period_start_value)
            .filter(Email.received_at < period_end_value)
            .order_by(Email.received_at.desc())
            .all()
        )

        digest_input: list[dict] = []
        for email_row, analysis_row in rows:
            digest_input.append(
                {
                    "id": email_row.id,
                    "subject": email_row.subject,
                    "sender_email": email_row.sender_email,
                    "received_at": email_row.received_at,
                    "is_read": email_row.is_read,
                    "snippet": email_row.snippet,
                    "body_text": email_row.body_text,
                    "summary": analysis_row.summary if analysis_row else None,
                    "priority_score": analysis_row.priority_score if analysis_row else 3,
                    "extracted_deadlines": analysis_row.extracted_deadlines if analysis_row else [],
                    "suggested_action": analysis_row.suggested_action if analysis_row else "",
                }
            )

        timezone_name = self._resolved_timezone_name(user.timezone)
        ai_summary = self.agent_service.summarize_digest_window(
            emails=digest_input,
            user_timezone=timezone_name,
        )
        output = self.digest_service.build_digest(
            email_rows=digest_input,
            ai_summary=ai_summary,
            period_start=period_start_value,
            period_end=period_end_value,
            user_timezone=timezone_name,
        )
        digest_data = {
            "email_rows": digest_input,
            "timezone_name": timezone_name,
            "generated_at": period_end_value,
        }

        if existing:
            return {"digest": existing, "output": output, "digest_data": digest_data, "idempotent_reuse": True}

        record = Digest(
            user_id=user.id,
            period_start=period_start_value,
            period_end=period_end_value,
            digest_text=output.digest_text,
            sent_to_telegram=False,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return {"digest": record, "output": output, "digest_data": digest_data, "idempotent_reuse": False}

    @staticmethod
    def _resolved_timezone_name(value: str | None) -> str:
        timezone_name = (value or "UTC").strip() or "UTC"
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return "UTC"
        return timezone_name
