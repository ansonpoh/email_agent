from fastapi import APIRouter
from pydantic import BaseModel

from app.deps import gmail_service

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleAuthStartRequest(BaseModel):
    state: str = "local-dev"


@router.post("/google/start")
def google_start(payload: GoogleAuthStartRequest):
    # TODO: Validate GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET before production use.
    auth_url = gmail_service.get_google_oauth_start_url(state=payload.state)
    return {"auth_url": auth_url, "state": payload.state}


@router.get("/google/callback")
def google_callback(code: str, state: str):
    # TODO: Exchange auth code for tokens, encrypt tokens, persist to users table.
    return {
        "message": "OAuth callback received. Token exchange is not yet implemented.",
        "code": code,
        "state": state,
    }
