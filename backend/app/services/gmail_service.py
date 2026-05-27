import base64
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
import logging
import math
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.services.token_cipher import TokenCipher


class GmailService:
    """Gmail integration facade.

    This service intentionally does not expose any email-sending method.
    Draft creation is supported; sending must happen manually in Gmail.
    """

    def __init__(self, token_cipher: TokenCipher):
        self.token_cipher = token_cipher
        self.logger = logging.getLogger(__name__)

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

    def exchange_code_for_tokens(self, code: str) -> dict:
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(status_code=400, detail="Google OAuth credentials are not configured.")

        payload = {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        }

        with httpx.Client(timeout=20.0) as client:
            response = client.post("https://oauth2.googleapis.com/token", data=payload)

        if response.status_code >= 400:
            raise HTTPException(
                status_code=400,
                detail=f"Google token exchange failed: {response.text}",
            )
        return response.json()

    def fetch_google_user_profile(self, access_token: str) -> dict:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if response.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Google profile fetch failed: {response.text}")

        profile = response.json()
        if not profile.get("id") or not profile.get("email"):
            raise HTTPException(status_code=400, detail="Google profile response is missing id/email.")
        return profile

    def fetch_emails_since(self, user: User, since: datetime | None, db: Session) -> list[dict]:
        messages = self._list_messages(user=user, since=since, db=db)
        incoming: list[dict] = []

        for message in messages:
            parsed = self._get_message_detail(user=user, message_id=message["id"], db=db)
            incoming.append(
                {
                    "user_id": user.id,
                    "gmail_message_id": parsed["id"],
                    "gmail_thread_id": parsed.get("threadId", ""),
                    "sender_email": parsed["sender_email"],
                    "sender_name": parsed["sender_name"],
                    "recipients": parsed["recipients"],
                    "subject": parsed["subject"],
                    "snippet": parsed.get("snippet"),
                    "body_text": parsed["body_text"],
                    "received_at": parsed["received_at"],
                    "is_read": parsed["is_read"],
                }
            )

        return incoming

    def fetch_latest_primary_inbox(self, user: User, db: Session, limit: int = 10) -> list[dict]:
        response = self._gmail_request(
            user=user,
            db=db,
            method="GET",
            url="https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={
                "q": "in:inbox category:primary",
                "maxResults": max(1, min(limit, 50)),
            },
        )
        payload = response.json()
        messages = payload.get("messages", [])
        incoming: list[dict] = []
        for message in messages:
            parsed = self._get_message_detail(user=user, message_id=message["id"], db=db)
            incoming.append(parsed)
        return incoming

    def fetch_primary_inbox_between(
        self,
        user: User,
        db: Session,
        start_utc: datetime,
        end_utc: datetime,
        limit: int = 50,
    ) -> list[dict]:
        safe_limit = max(1, min(limit, 50))
        start_epoch = int(start_utc.astimezone(timezone.utc).timestamp())
        end_epoch = int(end_utc.astimezone(timezone.utc).timestamp())
        query = f"in:inbox category:primary after:{start_epoch} before:{end_epoch}"

        response = self._gmail_request(
            user=user,
            db=db,
            method="GET",
            url="https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={"q": query, "maxResults": safe_limit},
        )
        payload = response.json()
        messages = payload.get("messages", [])

        incoming: list[dict] = []
        for message in messages:
            parsed = self._get_message_detail(user=user, message_id=message["id"], db=db)
            incoming.append(parsed)

        incoming.sort(key=lambda row: row.get("received_at", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        return incoming[:safe_limit]

    def fetch_direct_email_candidates(
        self,
        user: User,
        db: Session,
        *,
        max_results: int = 30,
        lookback_hours: int = 48,
    ) -> list[dict]:
        safe_limit = max(1, min(max_results, 50))
        safe_lookback_hours = max(1, lookback_hours)
        lookback_days = max(1, math.ceil(safe_lookback_hours / 24))
        query = f"in:inbox category:primary newer_than:{lookback_days}d"
        cutoff = datetime.now(timezone.utc) - timedelta(hours=safe_lookback_hours)

        response = self._gmail_request(
            user=user,
            db=db,
            method="GET",
            url="https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={"q": query, "maxResults": safe_limit},
        )
        payload = response.json()
        messages = payload.get("messages", [])

        incoming: list[dict] = []
        for message in messages:
            parsed = self._get_message_detail(user=user, message_id=message["id"], db=db)
            if (not parsed.get("is_read")) or parsed.get("received_at", cutoff) >= cutoff:
                incoming.append(parsed)

        incoming.sort(key=lambda row: row.get("received_at", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        return incoming[:safe_limit]

    def create_gmail_draft(self, user: User, db: Session, draft_body: str, subject: str) -> str:
        message = (
            f"Subject: {subject}\r\n"
            "Content-Type: text/plain; charset=\"UTF-8\"\r\n"
            "\r\n"
            f"{draft_body}"
        )
        raw_message = base64.urlsafe_b64encode(message.encode("utf-8")).decode("ascii")
        response = self._gmail_request(
            user=user,
            db=db,
            method="POST",
            url="https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            json={"message": {"raw": raw_message}},
        )
        payload = response.json()
        draft = payload.get("id") or payload.get("draft", {}).get("id")
        if not draft:
            raise HTTPException(status_code=502, detail="Gmail draft API response did not include draft id.")
        return str(draft)

    def create_gmail_reply_draft(self, user: User, db: Session, original_email: dict, draft_body: str) -> str:
        recipient = str(original_email.get("sender_email") or "").strip()
        if not recipient:
            raise HTTPException(status_code=400, detail="Cannot create reply draft without sender email.")

        message = EmailMessage()
        message["To"] = recipient
        message["From"] = user.email
        message["Subject"] = self._ensure_re_subject(original_email.get("subject"))

        in_reply_to = self._clean_single_header(
            original_email.get("message_id_header") or original_email.get("in_reply_to_header")
        )
        references = self._clean_single_header(original_email.get("references_header"))
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        if references:
            message["References"] = references
        elif in_reply_to:
            message["References"] = in_reply_to

        message.set_content(draft_body or "")
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

        payload: dict[str, Any] = {"raw": encoded_message}
        thread_id = str(original_email.get("threadId") or "").strip()
        if thread_id:
            payload["threadId"] = thread_id

        response = self._gmail_request(
            user=user,
            db=db,
            method="POST",
            url="https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            json={"message": payload},
        )
        response_payload = response.json()
        draft_id = response_payload.get("id") or response_payload.get("draft", {}).get("id")
        if not draft_id:
            raise HTTPException(status_code=502, detail="Gmail reply draft API response did not include draft id.")
        return str(draft_id)

    def _list_messages(self, user: User, since: datetime | None, db: Session) -> list[dict]:
        params: dict[str, str | int] = {"maxResults": 50}
        query_parts = ["in:inbox", "category:primary"]
        if since:
            query_parts.append(f"after:{int(since.timestamp())}")
        params["q"] = " ".join(query_parts)

        response = self._gmail_request(
            user=user,
            db=db,
            method="GET",
            url="https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params=params,
        )
        payload = response.json()
        return payload.get("messages", [])

    def _get_message_detail(self, user: User, message_id: str, db: Session) -> dict:
        response = self._gmail_request(
            user=user,
            db=db,
            method="GET",
            url=f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            params={"format": "full"},
        )
        message = response.json()

        payload = message.get("payload", {})
        headers = self._headers_map(payload.get("headers", []))
        sender_name, sender_email = self._parse_from(headers.get("from"))
        recipients = self._parse_recipients(headers.get("to"))

        return {
            "id": message.get("id", message_id),
            "threadId": message.get("threadId", ""),
            "sender_name": sender_name,
            "sender_email": sender_email,
            "recipients": recipients,
            "subject": headers.get("subject"),
            "snippet": message.get("snippet"),
            "body_text": self._extract_body_text(payload) or (message.get("snippet") or ""),
            "received_at": self._received_at(
                internal_date_ms=message.get("internalDate"),
                date_header=headers.get("date"),
            ),
            "is_read": "UNREAD" not in set(message.get("labelIds", [])),
            "message_id_header": headers.get("message-id"),
            "references_header": headers.get("references"),
            "in_reply_to_header": headers.get("in-reply-to"),
            "list_unsubscribe_header": headers.get("list-unsubscribe"),
            "auto_submitted_header": headers.get("auto-submitted"),
            "precedence_header": headers.get("precedence"),
        }

    def _gmail_request(
        self,
        user: User,
        db: Session,
        method: str,
        url: str,
        params: dict | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        access_token = self._decrypt_token(user.encrypted_access_token)
        if not access_token:
            raise HTTPException(status_code=400, detail="User has no Google access token.")

        with httpx.Client(timeout=20.0) as client:
            response = client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if response.status_code != 401:
            if response.status_code >= 400:
                lowered = response.text.lower()
                if "insufficient authentication scopes" in lowered or "insufficient_permissions" in lowered:
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            "Gmail API request failed due to insufficient scope. "
                            "Reconnect Gmail to grant draft permissions (gmail.compose or gmail.modify)."
                        ),
                    )
                raise HTTPException(status_code=400, detail=f"Gmail API request failed: {response.text}")
            return response

        refresh_token = self._decrypt_token(user.encrypted_refresh_token)
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Google access token expired and no refresh token is stored.")

        refreshed = self._refresh_access_token(refresh_token=refresh_token)
        new_access_token = refreshed["access_token"]
        user.encrypted_access_token = self._encrypt_token(new_access_token)
        maybe_new_refresh = refreshed.get("refresh_token")
        if maybe_new_refresh:
            user.encrypted_refresh_token = self._encrypt_token(maybe_new_refresh)
        db.add(user)
        db.commit()
        db.refresh(user)

        with httpx.Client(timeout=20.0) as client:
            retry = client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {new_access_token}"},
            )

        if retry.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Gmail API request failed after token refresh: {retry.text}")
        return retry

    def _refresh_access_token(self, refresh_token: str) -> dict[str, str]:
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(status_code=400, detail="Google OAuth credentials are not configured.")

        payload = {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        with httpx.Client(timeout=20.0) as client:
            response = client.post("https://oauth2.googleapis.com/token", data=payload)

        if response.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Google token refresh failed: {response.text}")

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise HTTPException(status_code=400, detail="Google token refresh did not return an access token.")
        return {
            "access_token": str(token),
            "refresh_token": str(payload.get("refresh_token")) if payload.get("refresh_token") else "",
        }

    def _encrypt_token(self, value: str) -> str:
        try:
            return self.token_cipher.encrypt(value)
        except Exception as exc:
            self.logger.exception("Token encryption failed.")
            raise HTTPException(status_code=500, detail="Token encryption failure.") from exc

    def _decrypt_token(self, value: str) -> str:
        try:
            return self.token_cipher.decrypt(value)
        except Exception as exc:
            self.logger.exception("Token decryption failed.")
            raise HTTPException(status_code=500, detail="Token decryption failure.") from exc

    @staticmethod
    def _headers_map(headers: list[dict]) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in headers:
            name = str(item.get("name", "")).strip().lower()
            value = str(item.get("value", "")).strip()
            if name and value and name not in out:
                out[name] = value
        return out

    @staticmethod
    def _parse_from(raw_from: str | None) -> tuple[str | None, str]:
        if not raw_from:
            return None, "unknown@example.com"

        raw = raw_from.strip()
        if "<" in raw and ">" in raw:
            name = raw.split("<", 1)[0].strip().strip('"') or None
            email = raw.split("<", 1)[1].split(">", 1)[0].strip() or "unknown@example.com"
            return name, email
        return None, raw

    @staticmethod
    def _parse_recipients(raw_to: str | None) -> list[str]:
        if not raw_to:
            return []
        items = [piece.strip() for piece in raw_to.split(",") if piece.strip()]
        recipients: list[str] = []
        for item in items:
            if "<" in item and ">" in item:
                recipients.append(item.split("<", 1)[1].split(">", 1)[0].strip())
            else:
                recipients.append(item)
        return recipients

    def _extract_body_text(self, payload: dict) -> str:
        data = payload.get("body", {}).get("data")
        mime_type = str(payload.get("mimeType", "")).lower()
        if data and (mime_type == "text/plain" or not payload.get("parts")):
            return self._decode_base64url(data)

        for part in payload.get("parts", []):
            body = self._extract_body_text(part)
            if body.strip():
                return body

        for part in payload.get("parts", []):
            if str(part.get("mimeType", "")).lower() == "text/html":
                html_data = part.get("body", {}).get("data")
                if html_data:
                    return self._decode_base64url(html_data)
        return ""

    @staticmethod
    def _decode_base64url(data: str) -> str:
        padded = data + "=" * (-len(data) % 4)
        try:
            return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _received_at(internal_date_ms: str | None, date_header: str | None) -> datetime:
        if internal_date_ms:
            try:
                return datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc)
            except (TypeError, ValueError):
                pass

        if date_header:
            try:
                parsed = parsedate_to_datetime(date_header)
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed
            except (TypeError, ValueError):
                pass

        return datetime.now(timezone.utc)

    @staticmethod
    def _ensure_re_subject(subject: str | None) -> str:
        clean_subject = (subject or "").strip()
        if not clean_subject:
            return "Re: (No subject)"
        if clean_subject.lower().startswith("re:"):
            return clean_subject
        return f"Re: {clean_subject}"

    @staticmethod
    def _clean_single_header(value: str | None) -> str | None:
        if not value:
            return None
        clean = " ".join(str(value).split()).strip()
        return clean or None
