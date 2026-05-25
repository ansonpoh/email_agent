from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.digest import Digest
from app.models.email import Email
from app.models.email_analysis import EmailAnalysis
from app.models.user import User
from app.services.digest_service import DigestService
from app.services.gmail_service import GmailService


class PipelineService:
    def __init__(self, gmail_service: GmailService, digest_service: DigestService):
        self.gmail_service = gmail_service
        self.digest_service = digest_service

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

    def generate_digest_for_user(self, db: Session, user: User) -> dict:
        period_end = datetime.utcnow()
        period_start = user.last_checked_at or (period_end - timedelta(days=1))
        window_start = period_end - timedelta(minutes=settings.digest_idempotency_window_minutes)

        existing = (
            db.query(Digest)
            .filter(Digest.user_id == user.id)
            .filter(Digest.period_start == period_start)
            .filter(Digest.created_at >= window_start)
            .order_by(Digest.created_at.desc())
            .first()
        )

        rows = (
            db.query(Email, EmailAnalysis)
            .outerjoin(EmailAnalysis, Email.id == EmailAnalysis.email_id)
            .filter(Email.user_id == user.id)
            .filter(Email.received_at >= period_start)
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
                    "summary": analysis_row.summary if analysis_row else None,
                    "priority_score": analysis_row.priority_score if analysis_row else 3,
                    "extracted_deadlines": analysis_row.extracted_deadlines if analysis_row else [],
                    "suggested_action": analysis_row.suggested_action if analysis_row else "",
                }
            )

        output = self.digest_service.build_digest(digest_input)
        if existing:
            return {"digest": existing, "output": output, "idempotent_reuse": True}

        record = Digest(
            user_id=user.id,
            period_start=period_start,
            period_end=period_end,
            digest_text=output.digest_text,
            sent_to_telegram=False,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return {"digest": record, "output": output, "idempotent_reuse": False}
