from datetime import datetime
from urllib.parse import urlencode

from app.config import settings


class GmailService:
    """Gmail integration facade.

    This service intentionally does not expose any email-sending method.
    Draft creation is supported; sending must happen manually in Gmail.
    """

    def get_google_oauth_start_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": settings.google_client_id or "",
                "redirect_uri": settings.google_redirect_uri,
                "response_type": "code",
                "scope": "openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify",
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    def fetch_emails_since(self, user_id: int, since: datetime | None) -> list[dict]:
        # TODO: Replace with real Gmail API fetch using stored OAuth tokens.
        base_time = since or datetime.utcnow()
        return [
            {
                "user_id": user_id,
                "gmail_message_id": f"mock-message-{int(base_time.timestamp())}",
                "gmail_thread_id": f"mock-thread-{int(base_time.timestamp())}",
                "sender_email": "manager@example.com",
                "sender_name": "Manager",
                "recipients": ["you@example.com"],
                "subject": "Status update needed",
                "snippet": "Can you share a status update by tomorrow?",
                "body_text": "Hi, please share your project status by tomorrow EOD.",
                "received_at": datetime.utcnow(),
                "is_read": False,
            }
        ]

    def create_gmail_draft(self, draft_body: str, subject: str) -> str:
        # TODO: Implement Gmail draft API call.
        return f"mock-gmail-draft-{abs(hash(subject + draft_body)) % 1000000}"
