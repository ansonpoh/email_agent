from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import gmail_service
from app.config import settings
from app.models.user import User
from app.services.token_cipher import token_cipher

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleAuthStartRequest(BaseModel):
    state: str = "local-dev"


@router.post("/google/start")
def google_start(payload: GoogleAuthStartRequest):
    auth_url = gmail_service.get_google_oauth_start_url(state=payload.state)
    return {"auth_url": auth_url, "state": payload.state}


@router.get("/google/callback")
def google_callback(code: str, state: str, db: Session = Depends(get_db)):
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
        existing.urgent_alerts_enabled = existing.urgent_alerts_enabled if existing.urgent_alerts_enabled is not None else settings.telegram_default_urgent_alerts_enabled
        if not existing.timezone:
            existing.timezone = settings.telegram_default_timezone
        existing.updated_at = datetime.utcnow()
        db.add(existing)
        db.commit()
        db.refresh(existing)
        user = existing
    else:
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            # Google often omits refresh token if user already granted consent.
            # Require full re-consent for first-time local user creation.
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
            urgent_alerts_enabled=settings.telegram_default_urgent_alerts_enabled,
            timezone=settings.telegram_default_timezone,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return {
        "message": "Google account connected.",
        "user_id": str(user.id),
        "email": user.email,
        "state": state,
    }
