from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.digest_schema import DigestImportantEmailDetail, DigestOutput


class TelegramDigestFormatter:
    PARSE_MODE = "HTML"

    _SECURITY_KEYWORDS = (
        "security",
        "security alert",
        "oauth",
        "password",
        "verification",
        "2fa",
        "sign in",
        "signin",
        "suspicious",
        "unauthorized",
    )
    _EVENT_KEYWORDS = (
        "meeting",
        "event",
        "ticket",
        "appointment",
        "calendar",
        "invite",
        "invitation",
        "reservation",
        "confirmed",
        "confirmation",
    )
    _JOB_KEYWORDS = (
        "job",
        "career",
        "recruiter",
        "hiring",
        "internship",
        "application",
        "position",
        "opportunity",
        "interview",
        "role",
    )
    _PROMO_KEYWORDS = (
        "promo",
        "promotion",
        "discount",
        "offer",
        "coupon",
        "gift code",
        "deal",
        "sale",
        "receipt",
        "welcome",
        "newsletter",
    )

    def format_email_digest_for_telegram(
        self,
        *,
        digest: DigestOutput,
        email_rows: list[dict] | None = None,
        generated_at: datetime | None = None,
        timezone_name: str = "UTC",
    ) -> str:
        tz = self._resolved_timezone(timezone_name)
        generated_at_local = self._as_utc(generated_at or datetime.now(timezone.utc)).astimezone(tz)
        emails_analyzed = len(email_rows) if email_rows is not None else (len(digest.priority_emails) + len(digest.low_priority))
        unread_count = sum(1 for row in (email_rows or []) if not row.get("is_read"))

        row_lookup = self._email_row_lookup(email_rows=email_rows)
        important_grouped = self._group_by_display_type(digest.important_emails, row_lookup=row_lookup)
        all_grouped = self._group_rows_by_display_type(email_rows=email_rows)

        tasks = self._collect_descriptive_tasks(
            email_rows=email_rows,
            important_emails=digest.important_emails,
            reference_year=generated_at_local.year,
        )
        summary = self.format_summary_section(
            digest=digest,
            needs_attention_emails=important_grouped["needs_attention"],
            security_count=self._security_count(email_rows=email_rows, important_emails=digest.important_emails),
            event_count=len(tasks),
            jobs_count=len(all_grouped["jobs"]),
        )
        needs_attention_section = self.format_needs_attention_section(
            emails=important_grouped["needs_attention"],
            timezone_name=timezone_name,
            local_tz=tz,
        )
        events_deadlines_section = self.format_events_deadlines_section(tasks=tasks, emails=important_grouped["events"])
        jobs_section = self.format_jobs_section(all_grouped["jobs"])
        optional_info_section = self.format_optional_information_section(all_grouped["optional"])
        main_actions, optional_actions = self._split_actions(digest.suggested_actions)
        suggested_actions = self.format_suggested_actions(main_actions, optional_actions)

        lines = [
            "<b>📬 AI Email Digest</b>",
            "",
            f"🕐 {self.escape_telegram_text(generated_at_local.strftime('%Y-%m-%d %H:%M'))} ({self.escape_telegram_text(timezone_name)})",
            f"📨 {emails_analyzed} emails analyzed | {unread_count} unread",
            "",
            "---",
            "",
            "<b>🔎 Summary</b>",
            "",
            summary,
            "",
            "---",
            "",
            "<b>🚨 Needs Attention</b>",
            "",
            needs_attention_section,
            "",
            "---",
            "",
            "<b>📅 Events / Deadlines</b>",
            "",
            events_deadlines_section,
            "",
            "---",
            "",
            "<b>💼 Jobs / Opportunities</b>",
            "",
            jobs_section,
            "",
            "---",
            "",
            "<b>ℹ️ Optional / Informational</b>",
            "",
            optional_info_section,
            "",
            "---",
            "",
            "<b>✅ Suggested Actions</b>",
            "",
            suggested_actions,
        ]
        return "\n".join(lines).strip()

    def format_summary_section(
        self,
        *,
        digest: DigestOutput,
        needs_attention_emails: list[DigestImportantEmailDetail],
        security_count: int,
        event_count: int,
        jobs_count: int,
    ) -> str:
        bullets: list[str] = []

        if needs_attention_emails:
            top_subject = self._compact_text(needs_attention_emails[0].subject or "(No subject)", max_len=72)
            count = len(needs_attention_emails)
            verb = "need" if count != 1 else "needs"
            bullets.append(f"• {count} email{'s' if count != 1 else ''} {verb} attention: {top_subject}")
        if security_count:
            bullets.append(f"• {security_count} security alert{'s' if security_count != 1 else ''} need review")
        if event_count:
            bullets.append(f"• {event_count} event/deadline item{'s' if event_count != 1 else ''} with clear context")
        if jobs_count:
            bullets.append(f"• {jobs_count} job/opportunity email{'s' if jobs_count != 1 else ''} identified")

        if not bullets:
            summary_text = self._compact_text(digest.overview or "No summary available.", max_len=320)
            bullets = [f"• {part}" for part in self._split_summary_sentences(summary_text)]

        return "\n".join(self.escape_telegram_text(item) for item in bullets[:4])

    def categorize_email_for_display(self, email: DigestImportantEmailDetail | dict) -> str:
        fields = self._email_fields(email)
        text_blob = " ".join(
            [
                fields["subject"],
                fields["summary"],
                fields["reason"],
                fields["recommended_action"],
                fields["status"],
            ]
        ).casefold()
        has_deadline = bool(fields["deadlines"])
        priority_score = fields["priority_score"]

        if self._contains_keyword(text_blob, self._SECURITY_KEYWORDS):
            return "needs_attention"
        if self._contains_keyword(text_blob, self._JOB_KEYWORDS):
            return "jobs"
        if has_deadline or self._contains_keyword(text_blob, self._EVENT_KEYWORDS):
            return "events"
        if priority_score >= 4 or "reply" in text_blob or "urgent" in text_blob or "action required" in text_blob:
            return "needs_attention"
        if self._contains_keyword(text_blob, self._PROMO_KEYWORDS):
            return "optional"
        return "optional"

    def format_needs_attention_section(
        self,
        *,
        emails: list[DigestImportantEmailDetail],
        timezone_name: str,
        local_tz: ZoneInfo | timezone,
    ) -> str:
        if not emails:
            return "No urgent items found."

        cards: list[str] = []
        for index, email in enumerate(emails, start=1):
            cards.append(
                self.format_email_card(
                    email=email,
                    index=index,
                    timezone_name=timezone_name,
                    local_tz=local_tz,
                )
            )
        return "\n\n---\n\n".join(cards)

    def format_events_deadlines_section(
        self,
        *,
        tasks: list[str],
        emails: list[DigestImportantEmailDetail],
    ) -> str:
        if tasks:
            return "\n".join(f"• {self.escape_telegram_text(task)}" for task in tasks[:8])
        if emails:
            fallback = [
                f"• {self.escape_telegram_text(self._compact_text(email.subject or '(No subject)', max_len=100))}"
                for email in emails[:5]
            ]
            return "\n".join(fallback)
        return "No deadlines found."

    def format_jobs_section(self, emails: list[dict]) -> str:
        if not emails:
            return "No job/opportunity emails found."

        lines: list[str] = []
        for item in emails[:5]:
            title = self._compact_text(item.get("subject") or "(No subject)", max_len=100)
            sender = self._compact_text(item.get("sender_email") or "unknown@example.com", max_len=100)
            action = self._compact_text(item.get("suggested_action") or "Review and follow up if relevant.", max_len=160)
            lines.extend(
                [
                    f"• {self.escape_telegram_text(title)}",
                    f"From: {self.escape_telegram_text(sender)}",
                    f"Action: {self.escape_telegram_text(action)}",
                    "",
                ]
            )
        return "\n".join(lines).strip()

    def format_optional_information_section(self, emails: list[dict]) -> str:
        if not emails:
            return "No optional informational emails highlighted."
        items = [
            self._compact_text(item.get("subject") or "(No subject)", max_len=120)
            for item in emails[:6]
        ]
        return "\n".join(f"• {self.escape_telegram_text(item)}" for item in items)

    def format_suggested_actions(self, actions: list[str], optional_actions: list[str]) -> str:
        lines: list[str] = []

        if actions:
            lines.extend(f"☐ {self.escape_telegram_text(action)}" for action in actions[:8])
        else:
            lines.append("No suggested actions.")

        if optional_actions:
            lines.append("")
            lines.append("Optional:")
            lines.extend(f"• {self.escape_telegram_text(action)}" for action in optional_actions[:6])

        return "\n".join(lines)

    def format_email_card(
        self,
        *,
        email: DigestImportantEmailDetail,
        index: int,
        timezone_name: str,
        local_tz: ZoneInfo | timezone,
    ) -> str:
        received_text = "unknown"
        if email.received_at:
            received_text = self._format_datetime(self._as_utc(email.received_at).astimezone(local_tz))

        subject = self._compact_text(email.subject or "(No subject)", max_len=120)
        sender = self._compact_text(email.sender_email or "unknown@example.com", max_len=100)
        why = self._compact_text(email.reason or "Marked important by AI.", max_len=220)
        action = self._compact_text(email.recommended_action or "Review this thread.", max_len=180)
        status = self._compact_text(email.status or "unknown", max_len=20)
        priority_label = self.priority_to_label(email.priority_score)

        return "\n".join(
            [
                f"{index}. <b>{self.escape_telegram_text(subject)}</b>",
                f"From: {self.escape_telegram_text(sender)}",
                f"Received: {self.escape_telegram_text(received_text)} ({self.escape_telegram_text(timezone_name)})",
                f"Priority: {self.escape_telegram_text(priority_label)} {email.priority_score}/5",
                f"Status: {self.escape_telegram_text(status)}",
                "",
                f"Why it matters: {self.escape_telegram_text(why)}",
                f"Action: {self.escape_telegram_text(action)}",
            ]
        )

    def _collect_descriptive_tasks(
        self,
        *,
        email_rows: list[dict] | None,
        important_emails: list[DigestImportantEmailDetail],
        reference_year: int,
    ) -> list[str]:
        tasks: list[str] = []

        if email_rows:
            for row in email_rows:
                for deadline in row.get("extracted_deadlines") or []:
                    deadline_label = self._normalize_deadline_label(str(deadline), reference_year=reference_year)
                    description = self._task_description_from_row(row)
                    item = self._compact_text(f"{deadline_label} — {description}", max_len=190)
                    if item:
                        tasks.append(item)

        row_ids = {str(row.get("id")) for row in (email_rows or []) if row.get("id") is not None}
        for item in important_emails:
            if str(item.email_id) in row_ids:
                continue
            for deadline in item.deadlines:
                deadline_label = self._normalize_deadline_label(str(deadline), reference_year=reference_year)
                description = self._compact_text(item.subject or "(No subject)", max_len=120)
                task = self._compact_text(f"{deadline_label} — {description}", max_len=190)
                if task:
                    tasks.append(task)

        deduped: list[str] = []
        seen: set[str] = set()
        for task in tasks:
            key = task.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(task)
            if len(deduped) >= 8:
                break

        return deduped

    @staticmethod
    def priority_to_label(priority: int) -> str:
        if priority >= 4:
            return "🔴 High"
        if priority >= 2:
            return "🟡 Medium"
        return "🟢 Low"

    @staticmethod
    def _compact_text(value: str, *, max_len: int) -> str:
        normalized = " ".join((value or "").split())
        if len(normalized) <= max_len:
            return normalized
        return normalized[: max_len - 1].rstrip() + "..."

    @staticmethod
    def escape_telegram_text(text: str) -> str:
        return html.escape(str(text or ""), quote=False)

    @classmethod
    def _contains_keyword(cls, text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)

    @classmethod
    def _email_row_lookup(cls, *, email_rows: list[dict] | None) -> dict[str, dict]:
        lookup: dict[str, dict] = {}
        for row in email_rows or []:
            row_id = row.get("id")
            if row_id is None:
                continue
            lookup[str(row_id)] = row
        return lookup

    def _group_by_display_type(
        self,
        important_emails: list[DigestImportantEmailDetail],
        *,
        row_lookup: dict[str, dict],
    ) -> dict[str, list[DigestImportantEmailDetail]]:
        grouped: dict[str, list[DigestImportantEmailDetail]] = {
            "needs_attention": [],
            "events": [],
            "jobs": [],
            "optional": [],
        }
        for item in important_emails:
            category = self.categorize_email_for_display(row_lookup.get(str(item.email_id)) or item)
            grouped[category].append(item)
        if not grouped["needs_attention"] and important_emails:
            grouped["needs_attention"] = list(important_emails)
        return grouped

    def _group_rows_by_display_type(self, *, email_rows: list[dict] | None) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {
            "needs_attention": [],
            "events": [],
            "jobs": [],
            "optional": [],
        }
        dedupe: dict[str, set[str]] = {key: set() for key in grouped}
        for row in email_rows or []:
            category = self.categorize_email_for_display(row)
            key = self._row_dedupe_key(row)
            if key in dedupe[category]:
                continue
            dedupe[category].add(key)
            grouped[category].append(row)
        return grouped

    def _security_count(self, *, email_rows: list[dict] | None, important_emails: list[DigestImportantEmailDetail]) -> int:
        count = 0
        row_ids: set[str] = set()
        for row in email_rows or []:
            row_id = row.get("id")
            if row_id is not None:
                row_ids.add(str(row_id))
            fields = self._email_fields(row)
            blob = " ".join([fields["subject"], fields["summary"], fields["recommended_action"]]).casefold()
            if self._contains_keyword(blob, self._SECURITY_KEYWORDS):
                count += 1
        for item in important_emails:
            if str(item.email_id) in row_ids:
                continue
            fields = self._email_fields(item)
            blob = " ".join([fields["subject"], fields["summary"], fields["reason"], fields["recommended_action"]]).casefold()
            if self._contains_keyword(blob, self._SECURITY_KEYWORDS):
                count += 1
        return count

    def _split_actions(self, actions: list[str]) -> tuple[list[str], list[str]]:
        main_actions: list[str] = []
        optional_actions: list[str] = []
        seen: set[str] = set()

        for action in actions:
            text = self._compact_text(str(action), max_len=180)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            if self._contains_keyword(key, self._PROMO_KEYWORDS):
                optional_actions.append(text)
            else:
                main_actions.append(text)
        return main_actions, optional_actions

    @staticmethod
    def _split_summary_sentences(summary: str) -> list[str]:
        parts = [part.strip(" .") for part in re.split(r"[.!?]+", summary) if part.strip()]
        if not parts:
            return ["No summary available"]
        return parts[:3]

    @staticmethod
    def _task_description_from_row(row: dict) -> str:
        action = " ".join(str(row.get("suggested_action") or "").split())
        subject = " ".join(str(row.get("subject") or "").split())
        summary = " ".join(str(row.get("summary") or row.get("snippet") or "").split())
        if action:
            return action
        if subject:
            return subject
        if summary:
            return summary
        return "Review this thread"

    def _normalize_deadline_label(self, value: str, *, reference_year: int) -> str:
        text = self._compact_text(value, max_len=120)
        parsed = self._try_parse_deadline(text, reference_year=reference_year)
        if parsed is None:
            return text

        dt, has_time = parsed
        date_label = f"{dt.strftime('%b')} {dt.day}"
        if has_time:
            time_label = dt.strftime("%I:%M %p").lstrip("0")
            return f"{date_label}, {time_label}"
        return date_label

    def _try_parse_deadline(self, text: str, *, reference_year: int) -> tuple[datetime, bool] | None:
        if not text:
            return None

        cleaned = re.sub(r"\s+", " ", text).strip()
        cleaned = re.sub(r"\b(am|pm)\b", lambda m: m.group(1).upper(), cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?i)\b(by|before|on)\s+", "", cleaned).strip()

        patterns: list[tuple[str, bool]] = [
            ("%a %d %b - %I:%M %p", True),
            ("%a %d %b %I:%M %p", True),
            ("%d %b - %I:%M %p", True),
            ("%d %b %I:%M %p", True),
            ("%b %d - %I:%M %p", True),
            ("%b %d %I:%M %p", True),
            ("%B %d - %I:%M %p", True),
            ("%B %d %I:%M %p", True),
            ("%b %d", False),
            ("%B %d", False),
            ("%Y-%m-%d", False),
            ("%Y-%m-%d %H:%M", True),
        ]

        for pattern, has_time in patterns:
            try:
                if "%Y" in pattern:
                    parsed = datetime.strptime(cleaned, pattern)
                else:
                    parsed = datetime.strptime(f"{cleaned} {reference_year}", f"{pattern} %Y")
                return parsed, has_time
            except ValueError:
                continue

        try:
            iso_candidate = cleaned.replace("Z", "+00:00")
            parsed_iso = datetime.fromisoformat(iso_candidate)
            return parsed_iso, True
        except ValueError:
            return None

    @staticmethod
    def _row_dedupe_key(row: dict) -> str:
        subject = str(row.get("subject") or "").casefold()
        sender = str(row.get("sender_email") or "").casefold()
        return f"{sender}|{subject}"

    @staticmethod
    def _email_fields(email: DigestImportantEmailDetail | dict) -> dict:
        if isinstance(email, dict):
            return {
                "subject": str(email.get("subject") or ""),
                "sender_email": str(email.get("sender_email") or ""),
                "summary": str(email.get("summary") or email.get("snippet") or ""),
                "reason": str(email.get("reason") or ""),
                "recommended_action": str(email.get("suggested_action") or ""),
                "status": str(email.get("status") or ("read" if email.get("is_read") else "unread")),
                "deadlines": [str(item) for item in (email.get("extracted_deadlines") or [])],
                "priority_score": max(1, min(int(email.get("priority_score", 3)), 5)),
            }

        return {
            "subject": str(email.subject or ""),
            "sender_email": str(email.sender_email or ""),
            "summary": str(email.summary or ""),
            "reason": str(email.reason or ""),
            "recommended_action": str(email.recommended_action or ""),
            "status": str(email.status or "unknown"),
            "deadlines": [str(item) for item in email.deadlines],
            "priority_score": max(1, min(int(email.priority_score), 5)),
        }

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        return f"{value.strftime('%b')} {value.day}, {value.strftime('%I:%M %p').lstrip('0')}"

    @staticmethod
    def _resolved_timezone(timezone_name: str) -> ZoneInfo | timezone:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return timezone.utc

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
