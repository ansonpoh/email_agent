from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/telegram", tags=["telegram"])


class TelegramLinkRequest(BaseModel):
    user_id: int
    telegram_chat_id: str


@router.post("/link")
def link_telegram(payload: TelegramLinkRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.telegram_chat_id = payload.telegram_chat_id
    db.commit()
    return {"linked": True, "telegram_chat_id": payload.telegram_chat_id}


@router.post("/test")
def test_telegram():
    # TODO: Wire to TelegramService with configured TELEGRAM_BOT_TOKEN.
    return {"ok": True, "message": "Telegram test endpoint is ready. Configure token to send real test messages."}
