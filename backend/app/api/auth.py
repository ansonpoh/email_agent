from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.deps import gmail_service, telegram_auth_state_service, telegram_service
from app.models.user import User
from app.services.token_cipher import token_cipher

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleAuthStartRequest(BaseModel):
    state: str = "local-dev"


@router.post("/google/start")
def google_start(payload: GoogleAuthStartRequest):
    auth_url = gmail_service.get_google_oauth_start_url(state=payload.state)
    return {"auth_url": auth_url, "state": payload.state}


def _callback_page(title: str, message: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=(
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{title}</title></head><body style='font-family:Arial,sans-serif;padding:24px;'>"
            f"<h2>{title}</h2><p>{message}</p>"
            "<p>You can return to Telegram now.</p></body></html>"
        ),
        status_code=status_code,
    )


def _notify_link_result(chat_id: str, message: str) -> None:
    try:
        telegram_service.send_message(chat_id=chat_id, text=message)
    except Exception:
        # Best-effort notification only.
        pass


@router.get("/google/callback")
def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    try:
        state_payload = telegram_auth_state_service.parse_and_verify(state)
    except ValueError as exc:
        return _callback_page("Connection Failed", str(exc), status_code=400)

    chat_id = state_payload.chat_id

    try:
        tokens = gmail_service.exchange_code_for_tokens(code=code)
        profile = gmail_service.fetch_google_user_profile(access_token=tokens["access_token"])

        existing = db.query(User).filter(User.google_user_id == profile["id"]).first()
        if existing:
            existing.email = profile["email"]
            existing.encrypted_access_token = token_cipher.encrypt(tokens["access_token"])
            refresh_token = tokens.get("refresh_token")
            if refresh_token:
                existing.encrypted_refresh_token = token_cipher.encrypt(refresh_token)
            if not existing.digest_frequency:
                existing.digest_frequency = settings.telegram_default_digest_frequency
            existing.scheduled_digest_enabled = (
                existing.scheduled_digest_enabled
                if existing.scheduled_digest_enabled is not None
                else False
            )
            if existing.digest_schedule_count is not None and not (1 <= int(existing.digest_schedule_count) <= 3):
                existing.digest_schedule_count = None
            if existing.digest_schedule_times is None:
                existing.digest_schedule_times = []
            existing.urgent_alerts_enabled = (
                existing.urgent_alerts_enabled
                if existing.urgent_alerts_enabled is not None
                else settings.telegram_default_urgent_alerts_enabled
            )
            if not existing.timezone:
                existing.timezone = settings.telegram_default_timezone
            existing.updated_at = datetime.now(timezone.utc)
            user = existing
        else:
            refresh_token = tokens.get("refresh_token")
            if not refresh_token:
                raise HTTPException(
                    status_code=400,
                    detail="Google did not return a refresh token. Re-run OAuth with consent prompt.",
                )

            user = User(
                email=profile["email"],
                google_user_id=profile["id"],
                encrypted_access_token=token_cipher.encrypt(tokens["access_token"]),
                encrypted_refresh_token=token_cipher.encrypt(refresh_token),
                digest_frequency=settings.telegram_default_digest_frequency,
                scheduled_digest_enabled=False,
                digest_schedule_count=None,
                digest_schedule_times=[],
                urgent_alerts_enabled=settings.telegram_default_urgent_alerts_enabled,
                timezone=settings.telegram_default_timezone,
            )
            db.add(user)
            db.flush()

        # One chat can be linked to only one account.
        for conflict in db.query(User).filter(User.telegram_chat_id == chat_id).filter(User.id != user.id).all():
            conflict.telegram_chat_id = None
            db.add(conflict)

        user.telegram_chat_id = chat_id
        user.telegram_link_token_hash = None
        user.telegram_link_token_expires_at = None
        db.add(user)
        db.commit()
        db.refresh(user)

        _notify_link_result(chat_id, f"Google account connected: {user.email}. You can now use /sync.")
        return _callback_page("Connection Successful", f"Your Gmail account {user.email} is connected.")
    except HTTPException as exc:
        _notify_link_result(chat_id, f"Gmail connect failed: {exc.detail}")
        return _callback_page("Connection Failed", str(exc.detail), status_code=exc.status_code)
    except Exception:
        _notify_link_result(chat_id, "Gmail connect failed due to an internal error.")
        return _callback_page("Connection Failed", "Internal server error.", status_code=500)
