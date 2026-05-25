from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.deps import telegram_bot_service, telegram_service
from app.models.user import User

router = APIRouter(prefix="/telegram", tags=["telegram"])


class TelegramTestRequest(BaseModel):
    user_id: UUID
    message: str = "Telegram connectivity test from Gmail Agent Assistant."


@router.post("/webhook")
def telegram_webhook(
    payload: dict,
    db: Session = Depends(get_db),
    telegram_secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    expected_secret = settings.telegram_webhook_secret_token
    if expected_secret and telegram_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret token.")

    result = telegram_bot_service.handle_update(db=db, update=payload)
    return {"ok": True, "result": result, "processed_at": datetime.now(timezone.utc)}


@router.post("/test")
def test_telegram(payload: TelegramTestRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.telegram_chat_id:
        raise HTTPException(status_code=400, detail="User Telegram chat id is not linked")

    sent = telegram_service.send_message(chat_id=user.telegram_chat_id, text=payload.message)
    if not sent:
        raise HTTPException(status_code=502, detail="Telegram message send failed.")
    return {"ok": True, "sent": True}
