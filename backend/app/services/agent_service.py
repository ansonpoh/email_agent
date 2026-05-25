import logging
from typing import Any

from fastapi import HTTPException
from openai import OpenAI
from openai import APIError, APITimeoutError, RateLimitError

from app.config import settings
from app.schemas.email_schema import EmailAnalysisOutput, TodaySummaryOutput


class AgentService:
    """Agent logic for structured email analysis."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._client: OpenAI | None = None

    def analyse_email(self, subject: str | None, body_text: str, user_rules: list[str] | None = None) -> EmailAnalysisOutput:
        if not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured.")

        max_attempts = max(settings.openai_max_retries + 1, 1)
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                completion = self._client_instance().beta.chat.completions.parse(
                    model=settings.openai_model,
                    temperature=0.2,
                    messages=self._messages(subject=subject, body_text=body_text, user_rules=user_rules or []),
                    response_format=EmailAnalysisOutput,
                )

                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("OpenAI parsed response was empty.")
                return parsed
            except (APITimeoutError, RateLimitError, APIError, ValueError) as exc:
                last_error = exc
                self.logger.warning("OpenAI analyse_email attempt %s/%s failed: %s", attempt, max_attempts, exc)

        raise HTTPException(
            status_code=502,
            detail=f"OpenAI structured analysis failed after retries: {last_error}",
        )

    def summarize_emails_for_today(self, emails: list[dict], user_timezone: str) -> TodaySummaryOutput:
        if not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured.")

        max_attempts = max(settings.openai_max_retries + 1, 1)
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                completion = self._client_instance().beta.chat.completions.parse(
                    model=settings.openai_model,
                    temperature=0.2,
                    messages=self._today_summary_messages(emails=emails, user_timezone=user_timezone),
                    response_format=TodaySummaryOutput,
                )

                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("OpenAI parsed summary response was empty.")
                return parsed
            except (APITimeoutError, RateLimitError, APIError, ValueError) as exc:
                last_error = exc
                self.logger.warning("OpenAI summarize_emails_for_today attempt %s/%s failed: %s", attempt, max_attempts, exc)

        raise HTTPException(
            status_code=502,
            detail=f"OpenAI today summary failed after retries: {last_error}",
        )

    def _client_instance(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
                max_retries=0,
            )
        return self._client

    @staticmethod
    def _messages(subject: str | None, body_text: str, user_rules: list[str]) -> list[dict[str, Any]]:
        rules_text = "\n".join(f"- {rule}" for rule in user_rules if rule.strip())
        rules_suffix = (
            f"\n\nRespect these user rules when proposing actions:\n{rules_text}"
            if rules_text
            else "\n\nNo custom user rules provided."
        )
        return [
            {
                "role": "system",
                "content": (
                    "You analyze inbound emails for a personal assistant tool. "
                    "Return concise, high-signal structured output. "
                    "Use priority_score from 1 (low) to 5 (critical). "
                    "If information is missing, leave arrays empty and be explicit in summary."
                    f"{rules_suffix}"
                ),
            },
            {
                "role": "user",
                "content": f"Subject: {subject or '(No subject)'}\n\nBody:\n{body_text}",
            },
        ]

    @staticmethod
    def _today_summary_messages(emails: list[dict], user_timezone: str) -> list[dict[str, Any]]:
        items: list[str] = []
        for idx, row in enumerate(emails, start=1):
            sender = str(row.get("sender_email") or "unknown@example.com")
            subject = str(row.get("subject") or "(No subject)")
            received_at = row.get("received_at")
            received_label = str(received_at) if received_at is not None else "unknown"
            status = "read" if row.get("is_read") else "unread"
            snippet = str(row.get("snippet") or row.get("body_text") or "").replace("\n", " ").strip()
            if len(snippet) > 200:
                snippet = snippet[:200].rstrip() + "..."
            items.append(
                f"{idx}. from={sender}; subject={subject}; received={received_label}; status={status}; content={snippet}"
            )

        return [
            {
                "role": "system",
                "content": (
                    "You summarize today's inbox emails for a Telegram assistant. "
                    "Return concise, high-signal output. Keep overview to 2-4 sentences. "
                    "priority_items should highlight urgent or important threads. "
                    "suggested_actions should be practical next actions, each under 140 characters."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Timezone: {user_timezone}\n"
                    f"Emails today: {len(emails)}\n\n"
                    "Email facts:\n"
                    + "\n".join(items)
                ),
            },
        ]
