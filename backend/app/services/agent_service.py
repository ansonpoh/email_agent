import logging
from typing import Any

from fastapi import HTTPException
from openai import OpenAI
from openai import APIError, APITimeoutError, RateLimitError

from app.config import settings
from app.schemas.digest_schema import AIDigestSummaryOutput
from app.schemas.direct_email_schema import DirectEmailClassificationOutput, DirectEmailDraftOutput
from app.schemas.email_schema import EmailAnalysisOutput, TodaySummaryOutput
from app.schemas.followup_schema import FollowupExtractionOutput
from app.schemas.inbox_schema import InboxQuestionAnswerOutput


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

    def summarize_digest_window(self, emails: list[dict], user_timezone: str) -> AIDigestSummaryOutput:
        if not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured.")

        max_attempts = max(settings.openai_max_retries + 1, 1)
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                completion = self._client_instance().beta.chat.completions.parse(
                    model=settings.openai_model,
                    temperature=0.2,
                    messages=self._digest_summary_messages(emails=emails, user_timezone=user_timezone),
                    response_format=AIDigestSummaryOutput,
                )

                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("OpenAI parsed digest summary response was empty.")
                return parsed
            except (APITimeoutError, RateLimitError, APIError, ValueError) as exc:
                last_error = exc
                self.logger.warning("OpenAI summarize_digest_window attempt %s/%s failed: %s", attempt, max_attempts, exc)

        raise HTTPException(
            status_code=502,
            detail=f"OpenAI digest summary failed after retries: {last_error}",
        )

    def classify_direct_email(self, email_content: str) -> DirectEmailClassificationOutput:
        if not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured.")

        max_attempts = max(settings.openai_max_retries + 1, 1)
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                completion = self._client_instance().beta.chat.completions.parse(
                    model=settings.openai_model,
                    temperature=0.1,
                    messages=self._direct_classifier_messages(email_content=email_content),
                    response_format=DirectEmailClassificationOutput,
                )
                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("OpenAI parsed direct email classification was empty.")
                return parsed
            except (APITimeoutError, RateLimitError, APIError, ValueError) as exc:
                last_error = exc
                self.logger.warning(
                    "OpenAI classify_direct_email attempt %s/%s failed: %s",
                    attempt,
                    max_attempts,
                    exc,
                )

        raise HTTPException(
            status_code=502,
            detail=f"OpenAI direct-email classification failed after retries: {last_error}",
        )

    def answer_inbox_question(self, *, question: str, emails: list[dict], user_timezone: str) -> InboxQuestionAnswerOutput:
        if not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured.")

        max_attempts = max(settings.openai_max_retries + 1, 1)
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                completion = self._client_instance().beta.chat.completions.parse(
                    model=settings.openai_model,
                    temperature=0.1,
                    messages=self._inbox_question_messages(question=question, emails=emails, user_timezone=user_timezone),
                    response_format=InboxQuestionAnswerOutput,
                )

                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("OpenAI parsed inbox answer was empty.")
                return parsed
            except (APITimeoutError, RateLimitError, APIError, ValueError) as exc:
                last_error = exc
                self.logger.warning("OpenAI answer_inbox_question attempt %s/%s failed: %s", attempt, max_attempts, exc)

        raise HTTPException(
            status_code=502,
            detail=f"OpenAI inbox question answering failed after retries: {last_error}",
        )

    def extract_followups_from_email(
        self,
        *,
        email_content: str,
        analysis_summary: str,
        user_timezone: str,
    ) -> FollowupExtractionOutput:
        if not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured.")

        max_attempts = max(settings.openai_max_retries + 1, 1)
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                completion = self._client_instance().beta.chat.completions.parse(
                    model=settings.openai_model,
                    temperature=0.1,
                    messages=self._followup_extraction_messages(
                        email_content=email_content,
                        analysis_summary=analysis_summary,
                        user_timezone=user_timezone,
                    ),
                    response_format=FollowupExtractionOutput,
                )
                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("OpenAI parsed followup extraction was empty.")
                return parsed
            except (APITimeoutError, RateLimitError, APIError, ValueError) as exc:
                last_error = exc
                self.logger.warning(
                    "OpenAI extract_followups_from_email attempt %s/%s failed: %s",
                    attempt,
                    max_attempts,
                    exc,
                )

        raise HTTPException(
            status_code=502,
            detail=f"OpenAI followup extraction failed after retries: {last_error}",
        )

    def generate_direct_email_reply(
        self,
        *,
        email_content: str,
        classification: DirectEmailClassificationOutput,
    ) -> str:
        if not settings.openai_api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not configured.")

        max_attempts = max(settings.openai_max_retries + 1, 1)
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                completion = self._client_instance().beta.chat.completions.parse(
                    model=settings.openai_model,
                    temperature=0.2,
                    messages=self._direct_reply_messages(
                        email_content=email_content,
                        classification_json=classification.model_dump_json(),
                    ),
                    response_format=DirectEmailDraftOutput,
                )
                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("OpenAI parsed direct-email reply was empty.")
                body = parsed.draft_reply_body.strip()
                if not body:
                    raise ValueError("OpenAI generated an empty direct-email draft body.")
                return body
            except (APITimeoutError, RateLimitError, APIError, ValueError) as exc:
                last_error = exc
                self.logger.warning(
                    "OpenAI generate_direct_email_reply attempt %s/%s failed: %s",
                    attempt,
                    max_attempts,
                    exc,
                )

        raise HTTPException(
            status_code=502,
            detail=f"OpenAI direct-email reply generation failed after retries: {last_error}",
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

    @staticmethod
    def _digest_summary_messages(emails: list[dict], user_timezone: str) -> list[dict[str, Any]]:
        items: list[str] = []
        for idx, row in enumerate(emails, start=1):
            sender = str(row.get("sender_email") or "unknown@example.com")
            subject = str(row.get("subject") or "(No subject)")
            received_at = row.get("received_at")
            received_label = str(received_at) if received_at is not None else "unknown"
            status = "read" if row.get("is_read") else "unread"
            summary = str(row.get("summary") or "No summary")
            priority = int(row.get("priority_score", 3))
            deadlines = row.get("extracted_deadlines") or []
            suggested_action = str(row.get("suggested_action") or "")
            snippet = str(row.get("snippet") or row.get("body_text") or "").replace("\n", " ").strip()
            if len(snippet) > 240:
                snippet = snippet[:240].rstrip() + "..."
            items.append(
                (
                    f"{idx}. from={sender}; subject={subject}; received={received_label}; status={status}; "
                    f"priority={priority}; summary={summary}; deadlines={deadlines}; "
                    f"suggested_action={suggested_action}; snippet={snippet}"
                )
            )

        return [
            {
                "role": "system",
                "content": (
                    "You summarize a digest window of inbox emails for a Telegram assistant. "
                    "Return concise, high-signal structured output. "
                    "overview should be 2-4 sentences. "
                    "important_emails must include at most 3 items and each item must reference only valid "
                    "source_index values from the provided email facts. "
                    "Do not hallucinate email facts or indexes. "
                    "recommended_action and suggested_actions should be concrete and practical."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Timezone: {user_timezone}\n"
                    f"Emails in digest window: {len(emails)}\n\n"
                    "Email facts:\n"
                    + ("\n".join(items) if items else "(none)")
                ),
            },
        ]

    @staticmethod
    def _direct_classifier_messages(email_content: str) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are an email triage assistant.\n\n"
                    "Analyze the email and determine whether it is a direct human email that likely requires "
                    "the user's attention.\n\n"
                    "Return only valid JSON.\n\n"
                    "Fields:\n"
                    "- is_direct_email: boolean\n"
                    "- needs_reply: boolean\n"
                    "- urgency: \"low\" | \"medium\" | \"high\"\n"
                    "- category: string\n"
                    "- summary: string\n"
                    "- reason: string\n"
                    "- suggested_action: string\n"
                    "- reply_intent: string\n\n"
                    "Exclude newsletters, no-reply emails, system notifications, job alerts, promotions, "
                    "receipts, OTPs, and automated messages."
                ),
            },
            {"role": "user", "content": f"Email:\n{email_content}"},
        ]

    @staticmethod
    def _direct_reply_messages(email_content: str, classification_json: str) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are an email reply assistant.\n\n"
                    "Write a concise draft reply to the email below.\n\n"
                    "Rules:\n"
                    "- Do not invent facts.\n"
                    "- Do not make commitments unless explicitly supported by the email or user context.\n"
                    "- Use placeholders where the user needs to fill in information.\n"
                    "- Keep the tone professional and natural.\n"
                    "- Do not include a subject line unless needed.\n"
                    "- Return only the draft reply body."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Original email:\n{email_content}\n\n"
                    f"Classification:\n{classification_json}"
                ),
            },
        ]

    @staticmethod
    def _inbox_question_messages(question: str, emails: list[dict], user_timezone: str) -> list[dict[str, Any]]:
        lines: list[str] = []
        for idx, row in enumerate(emails, start=1):
            sender = str(row.get("sender_email") or "unknown@example.com")
            subject = str(row.get("subject") or "(No subject)")
            received_at = row.get("received_at")
            received_label = str(received_at) if received_at is not None else "unknown"
            snippet = str(row.get("snippet") or row.get("body_text") or "").replace("\n", " ").strip()
            if len(snippet) > 260:
                snippet = snippet[:260].rstrip() + "..."
            lines.append(
                f"{idx}. from={sender}; subject={subject}; received={received_label}; content={snippet}"
            )

        return [
            {
                "role": "system",
                "content": (
                    "You answer user questions about their inbox. "
                    "Only use provided email facts. "
                    "If facts are insufficient, say so clearly. "
                    "Keep answer concise and practical. "
                    "citations must reference valid source_index values from email facts."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Timezone: {user_timezone}\n"
                    f"Question: {question}\n"
                    f"Emails available: {len(emails)}\n\n"
                    "Email facts:\n"
                    + ("\n".join(lines) if lines else "(none)")
                ),
            },
        ]

    @staticmethod
    def _followup_extraction_messages(
        *,
        email_content: str,
        analysis_summary: str,
        user_timezone: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": (
                    "Extract actionable follow-up commitments from this email. "
                    "Focus on tasks, promises, and response obligations that should be tracked. "
                    "Return no more than 5 items. "
                    "If a concrete due date/time is present, output due_at_iso in ISO-8601 format with timezone. "
                    "If no concrete due date/time is present, leave due_at_iso null and optionally set due_label. "
                    "Do not invent dates."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User timezone: {user_timezone}\n"
                    f"Email analysis summary: {analysis_summary}\n\n"
                    f"Email content:\n{email_content}"
                ),
            },
        ]
