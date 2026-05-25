import logging
from typing import Any

from fastapi import HTTPException
from openai import OpenAI
from openai import APIError, APITimeoutError, RateLimitError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.schemas.agent_schema import DraftReplyOutput
from app.services.gmail_service import GmailService


class DraftService:
    def __init__(self, gmail_service: GmailService):
        self.logger = logging.getLogger(__name__)
        self.gmail_service = gmail_service
        self._client: OpenAI | None = None

    def generate_draft(
        self,
        subject: str | None,
        body_text: str,
        tone: str = "professional",
        user_rules: list[str] | None = None,
    ) -> DraftReplyOutput:
        if not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured.")

        max_attempts = max(settings.openai_max_retries + 1, 1)
        last_error: Exception | None = None
        fallback_subject = f"Re: {subject}" if subject else "Re: Your email"

        for attempt in range(1, max_attempts + 1):
            try:
                completion = self._client_instance().beta.chat.completions.parse(
                    model=settings.openai_model,
                    temperature=0.4,
                    messages=self._messages(subject=subject, body_text=body_text, tone=tone, user_rules=user_rules or []),
                    response_format=DraftReplyOutput,
                )
                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("OpenAI parsed response was empty.")

                draft_subject = parsed.subject.strip() or fallback_subject
                draft_body = parsed.body.strip()
                if not draft_body:
                    raise ValueError("OpenAI generated an empty draft body.")

                return DraftReplyOutput(
                    subject=draft_subject,
                    body=draft_body,
                    tone=tone,
                    requires_user_review=True,
                )
            except (APITimeoutError, RateLimitError, APIError, ValueError) as exc:
                last_error = exc
                self.logger.warning("OpenAI generate_draft attempt %s/%s failed: %s", attempt, max_attempts, exc)

        raise HTTPException(
            status_code=502,
            detail=f"OpenAI draft generation failed after retries: {last_error}",
        )

    def create_in_gmail(self, user: User, db: Session, subject: str, body: str) -> str:
        return self.gmail_service.create_gmail_draft(user=user, db=db, draft_body=body, subject=subject)

    def _client_instance(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
                max_retries=0,
            )
        return self._client

    @staticmethod
    def _messages(subject: str | None, body_text: str, tone: str, user_rules: list[str]) -> list[dict[str, Any]]:
        rules_text = "\n".join(f"- {rule}" for rule in user_rules if rule.strip())
        rules_suffix = (
            f"\n\nFollow these user preferences when drafting:\n{rules_text}"
            if rules_text
            else "\n\nNo extra user drafting preferences were provided."
        )
        return [
            {
                "role": "system",
                "content": (
                    "You write high-quality email replies for an assistant tool. "
                    "Generate a concise, ready-to-edit draft reply for the inbound message. "
                    "Keep it factual, avoid inventing commitments, and maintain the requested tone. "
                    "The draft must always require human review before sending."
                    f"{rules_suffix}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Requested tone: {tone}\n"
                    f"Original subject: {subject or '(No subject)'}\n\n"
                    f"Original email body:\n{body_text}"
                ),
            },
        ]
