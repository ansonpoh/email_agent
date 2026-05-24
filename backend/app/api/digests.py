from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import digest_service, telegram_service
from app.models.digest import Digest
from app.models.email import Email
from app.models.email_analysis import EmailAnalysis
from app.models.user import User
from app.schemas.digest_schema import DigestGenerateRequest

router = APIRouter(prefix="/digests", tags=["digests"])


@router.post("/generate")
def generate_digest(payload: DigestGenerateRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    period_end = datetime.utcnow()
    period_start = user.last_checked_at or (period_end - timedelta(days=1))

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

    output = digest_service.build_digest(digest_input)
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

    return {"digest_id": record.id, "output": output.model_dump()}


@router.get("/latest")
def latest_digest(user_id: int, db: Session = Depends(get_db)):
    row = db.query(Digest).filter(Digest.user_id == user_id).order_by(Digest.created_at.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail="Digest not found")
    return row


@router.post("/{digest_id}/send-telegram")
async def send_digest_to_telegram(digest_id: int, user_id: int, db: Session = Depends(get_db)):
    row = db.query(Digest).filter(Digest.id == digest_id, Digest.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Digest not found")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.telegram_chat_id:
        raise HTTPException(status_code=400, detail="User Telegram chat id is not linked")

    sent = await telegram_service.send_message(chat_id=user.telegram_chat_id, text=row.digest_text)
    row.sent_to_telegram = sent
    db.commit()

    return {"digest_id": row.id, "sent": sent}
