from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import pipeline_service, telegram_service
from app.models.digest import Digest
from app.models.user import User
from app.schemas.digest_schema import DigestGenerateRequest

router = APIRouter(prefix="/digests", tags=["digests"])


@router.post("/generate")
def generate_digest(payload: DigestGenerateRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = pipeline_service.generate_digest_for_user(db=db, user=user)
    record = result["digest"]
    output = result["output"]
    return {"digest_id": record.id, "output": output.model_dump(), "idempotent_reuse": result["idempotent_reuse"]}


@router.get("/latest")
def latest_digest(user_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Digest).filter(Digest.user_id == user_id).order_by(Digest.created_at.desc()).first()
    if not row:
        raise HTTPException(status_code=404, detail="Digest not found")
    return row


@router.post("/{digest_id}/send-telegram")
def send_digest_to_telegram(digest_id: UUID, user_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Digest).filter(Digest.id == digest_id, Digest.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Digest not found")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.telegram_chat_id:
        raise HTTPException(status_code=400, detail="User Telegram chat id is not linked")

    sent = telegram_service.send_message(chat_id=user.telegram_chat_id, text=row.digest_text)
    if not sent:
        raise HTTPException(status_code=502, detail="Telegram send failed.")
    row.sent_to_telegram = True
    db.commit()

    return {"digest_id": row.id, "sent": True}
