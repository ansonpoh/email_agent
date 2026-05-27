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
    _REPLY_NEEDED_KEYWORDS = (
        "reply",
        "respond",
        "confirm",
        "availability",
        "schedule",
        "meeting",
        "lunch",
        "interview",
        "follow up",
        "propose time",
    )
    _AUTOMATED_SENDER_TERMS = (
        "noreply",
        "no-reply",
        "do-not-reply",
        "donotreply",
        "notification",
        "notifications",
        "newsletter",
        "jobalerts",
        "job-alerts",
        "jobs-noreply",
        "updates",
        "marketing",
        "promo",
        "alerts",
        "receipt",
    )
    _AUTOMATED_TEXT_KEYWORDS = (
        "newsletter",
        "unsubscribe",
        "job alert",
        "job alerts",
        "promotion",
        "promotional",
        "discount",
        "deal",
        "receipt",
        "invoice",
        "verification code",
        "otp",
        "system notification",
        "automated notification",
        "do not reply",
        "no reply",
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
        events_deadlines_entries = self._events_deadlines_entries(
            tasks=tasks,
            event_emails=important_grouped["events"],
        )
        summary_groups = self._summary_display_groups(
            needs_attention_emails=important_grouped["needs_attention"],
            events_deadlines_entries=events_deadlines_entries,
            grouped_rows=all_grouped,
        )
        summary = self.format_summary_section(
            digest=digest,
            display_groups=summary_groups,
        )
        needs_attention_section = self.format_needs_attention_section(
            emails=important_grouped["needs_attention"],
            timezone_name=timezone_name,
            local_tz=tz,
        )
        events_deadlines_section = self.format_events_deadlines_section(tasks=events_deadlines_entries, emails=[])
        optional_info_section = self.format_optional_information_section(self._visible_optional_rows(grouped_rows=all_grouped))
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
        display_groups: dict[str, list],
    ) -> str:
        bullets: list[str] = []
        needs_attention_emails = display_groups["needs_attention"]
        security_emails = display_groups["security"]
        events_deadlines = display_groups["events_deadlines"]
        jobs_emails = display_groups["jobs_opportunities"]

        if needs_attention_emails:
            top_subject = self._compact_text(needs_attention_emails[0].subject or "(No subject)", max_len=72)
            count = len(needs_attention_emails)
            verb = "need" if count != 1 else "needs"
            bullets.append(f"• {count} email{'s' if count != 1 else ''} {verb} attention: {top_subject}")
        if security_emails:
            security_count = len(security_emails)
            if security_count == 1:
                subject = self._compact_text(security_emails[0].subject or "(No subject)", max_len=72)
                bullets.append(f"• 1 security alert needs review: {subject}")
            else:
                bullets.append(f"• {security_count} security alerts need review")
        if events_deadlines:
            event_count = len(events_deadlines)
            bullets.append(f"• {event_count} event/deadline item{'s' if event_count != 1 else ''} with clear context")
        if jobs_emails:
            jobs_count = len(jobs_emails)
            bullets.append(f"• {jobs_count} job/opportunity email{'s' if jobs_count != 1 else ''} identified")

        if not bullets:
            summary_text = self._compact_text(digest.overview or "No summary available.", max_len=320)
            bullets = [f"• {part}" for part in self._split_summary_sentences(summary_text)]

        return "\n".join(self.escape_telegram_text(item) for item in bullets[:4])

    def _summary_display_groups(
        self,
        *,
        needs_attention_emails: list[DigestImportantEmailDetail],
        events_deadlines_entries: list[str],
        grouped_rows: dict[str, list[dict]],
    ) -> dict[str, list]:
        visible_jobs = grouped_rows["jobs"][:6]
        visible_optional = grouped_rows["optional"][: max(0, 6 - len(visible_jobs))]
        security_emails = [email for email in needs_attention_emails if self._is_security_email(email)]
        return {
            "needs_attention": needs_attention_emails,
            "security": security_emails,
            "events_deadlines": events_deadlines_entries,
            "jobs_opportunities": visible_jobs,
            "optional": visible_optional,
        }

    def _visible_optional_rows(self, *, grouped_rows: dict[str, list[dict]]) -> list[dict]:
        merged_optional_rows = [*grouped_rows["jobs"], *grouped_rows["optional"]]
        return merged_optional_rows[:6]

    def _events_deadlines_entries(
        self,
        *,
        tasks: list[str],
        event_emails: list[DigestImportantEmailDetail],
    ) -> list[str]:
        if tasks:
            return tasks[:8]
        return [self._compact_text(email.subject or "(No subject)", max_len=100) for email in event_emails[:5]]

    def _is_security_email(self, email: DigestImportantEmailDetail | dict) -> bool:
        fields = self._email_fields(email)
        text_blob = self._normalized_display_text(fields)
        return self._contains_keyword(text_blob, self._SECURITY_KEYWORDS)

    def categorize_email_for_display(self, email: DigestImportantEmailDetail | dict) -> str:
        fields = self._email_fields(email)
        text_blob = self._normalized_display_text(fields)
        has_deadline = bool(fields["deadlines"])

        if self._contains_keyword(text_blob, self._SECURITY_KEYWORDS):
            return "needs_attention"
        if (
            self._is_human_sender(fields)
            and self._is_reply_needed(fields)
            and not self._is_excluded_automated_email(fields)
        ):
            return "needs_attention"
        if self._contains_keyword(text_blob, self._JOB_KEYWORDS):
            return "jobs"
        if has_deadline or self._contains_keyword(text_blob, self._EVENT_KEYWORDS):
            return "events"
        if fields["priority_score"] >= 4 or "urgent" in text_blob or "action required" in text_blob:
            return "needs_attention"
        if self._contains_keyword(text_blob, self._PROMO_KEYWORDS):
            return "optional"
        return "optional"

    def _is_human_sender(self, fields: dict) -> bool:
        sender = str(fields.get("sender_email") or "").casefold().strip()
        if not sender or "@" not in sender:
            return False
        return not self._contains_keyword(sender, self._AUTOMATED_SENDER_TERMS)

    def _is_reply_needed(self, fields: dict) -> bool:
        text_blob = self._normalized_display_text(fields)
        return self._contains_keyword(text_blob, self._REPLY_NEEDED_KEYWORDS)

    def _is_excluded_automated_email(self, fields: dict) -> bool:
        sender = str(fields.get("sender_email") or "").casefold()
        if self._contains_keyword(sender, self._AUTOMATED_SENDER_TERMS):
            return True

        text_blob = self._normalized_display_text(fields)
        return self._contains_keyword(text_blob, self._AUTOMATED_TEXT_KEYWORDS)

    @staticmethod
    def _normalized_display_text(fields: dict) -> str:
        pieces = [
            str(fields.get("sender_email") or ""),
            str(fields.get("subject") or ""),
            str(fields.get("summary") or ""),
            str(fields.get("reason") or ""),
            str(fields.get("why_important") or ""),
            str(fields.get("recommended_action") or ""),
            str(fields.get("status") or ""),
            str(fields.get("category") or ""),
            str(fields.get("priority") or ""),
            str(fields.get("priority_score") or ""),
        ]
        return " ".join(pieces).casefold()

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
        lines: list[str] = []
        for item in emails[:6]:
            subject = self._compact_text(item.get("subject") or "(No subject)", max_len=120)
            sender = self._compact_text(item.get("sender_email") or "unknown@example.com", max_len=100)
            lines.extend(
                [
                    f"• {self.escape_telegram_text(subject)}",
                    f"From: {self.escape_telegram_text(sender)}",
                    "",
                ]
            )
        return "\n".join(lines).strip()

    def format_suggested_actions(self, actions: list[str], optional_actions: list[str]) -> str:
        lines: list[str] = []

        if actions:
            lines.extend(f"• {self.escape_telegram_text(action)}" for action in actions[:8])
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
        entries: list[tuple[str, datetime | None, int]] = []
        original_index = 0

        if email_rows:
            for row in email_rows:
                for deadline in row.get("extracted_deadlines") or []:
                    deadline_text = str(deadline)
                    deadline_label = self._normalize_deadline_label(deadline_text, reference_year=reference_year)
                    parsed_deadline = self._try_parse_deadline(deadline_text, reference_year=reference_year)
                    parsed_dt = parsed_deadline[0] if parsed_deadline else None
                    description = self._task_description_from_row(row)
                    item = self._compact_text(f"{deadline_label} — {description}", max_len=190)
                    if item:
                        entries.append((item, parsed_dt, original_index))
                        original_index += 1

        row_ids = {str(row.get("id")) for row in (email_rows or []) if row.get("id") is not None}
        for item in important_emails:
            if str(item.email_id) in row_ids:
                continue
            for deadline in item.deadlines:
                deadline_text = str(deadline)
                deadline_label = self._normalize_deadline_label(deadline_text, reference_year=reference_year)
                parsed_deadline = self._try_parse_deadline(deadline_text, reference_year=reference_year)
                parsed_dt = parsed_deadline[0] if parsed_deadline else None
                description = self._compact_text(item.subject or "(No subject)", max_len=120)
                task = self._compact_text(f"{deadline_label} — {description}", max_len=190)
                if task:
                    entries.append((task, parsed_dt, original_index))
                    original_index += 1

        deduped: list[tuple[str, datetime | None, int]] = []
        seen: set[str] = set()
        for task, parsed_dt, index in entries:
            key = task.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append((task, parsed_dt, index))

        deduped.sort(key=lambda entry: (entry[1] is None, entry[1] or datetime.max, entry[2]))

        return [task for task, _, _ in deduped[:8]]

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
        range_parts = self._split_deadline_range(text)
        if range_parts is not None:
            start_text, end_text = range_parts
            parsed_start = self._try_parse_deadline(start_text, reference_year=reference_year)
            if parsed_start is None:
                return text

            start_dt, start_has_time = parsed_start
            parsed_end = self._try_parse_deadline(end_text, reference_year=reference_year)
            if parsed_end is None:
                parsed_end = self._try_parse_range_end(end_text, start_dt=start_dt)

            start_label = self._format_deadline_label(start_dt, has_time=start_has_time)
            if parsed_end is None:
                return start_label

            end_dt, end_has_time = parsed_end
            if self._is_full_day_same_date_range(
                start_dt=start_dt,
                end_dt=end_dt,
                start_has_time=start_has_time,
                end_has_time=end_has_time,
            ):
                return self._format_deadline_label(start_dt, has_time=False)
            if start_dt.date() == end_dt.date() and end_has_time:
                end_label = end_dt.strftime("%I:%M %p").lstrip("0")
                return f"{start_label} to {end_label}"
            end_label = self._format_deadline_label(end_dt, has_time=end_has_time)
            return f"{start_label} to {end_label}"

        parsed = self._try_parse_deadline(text, reference_year=reference_year)
        if parsed is None:
            return text

        dt, has_time = parsed
        return self._format_deadline_label(dt, has_time=has_time)

    def _try_parse_deadline(self, text: str, *, reference_year: int) -> tuple[datetime, bool] | None:
        if not text:
            return None

        cleaned = self._clean_deadline_text(text)
        range_parts = self._split_deadline_range(cleaned)
        if range_parts is not None:
            start_text, _ = range_parts
            return self._try_parse_deadline(start_text, reference_year=reference_year)

        parsed = self._try_parse_deadline_single(cleaned, reference_year=reference_year)
        if parsed is not None:
            return parsed

        try:
            iso_candidate = cleaned.replace("Z", "+00:00")
            parsed_iso = datetime.fromisoformat(iso_candidate)
            return parsed_iso, True
        except ValueError:
            return None

    @staticmethod
    def _format_deadline_label(value: datetime, *, has_time: bool) -> str:
        date_label = f"{value.strftime('%b')} {value.day}"
        if has_time:
            return f"{date_label}, {value.strftime('%I:%M %p').lstrip('0')}"
        return date_label

    @staticmethod
    def _split_deadline_range(value: str) -> tuple[str, str] | None:
        match = re.match(r"(?is)^(?P<start>.+?)\s+(?:to|until|through|thru)\s+(?P<end>.+)$", value.strip())
        if not match:
            return None
        return match.group("start").strip(" ,.-"), match.group("end").strip(" ,.-")

    @staticmethod
    def _clean_deadline_text(value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        cleaned = re.sub(r"\b(am|pm)\b", lambda m: m.group(1).upper(), cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"(?i)\b(by|before|on)\s+", "", cleaned).strip()
        cleaned = re.sub(r"(?i)\s*\((?:UTC|GMT)?\s*[A-Z0-9:+-]{2,}\)\s*$", "", cleaned).strip()
        cleaned = re.sub(r"(?i)\s+(?:UTC|GMT)\s*[+-]\d{1,2}(?::?\d{2})?\s*$", "", cleaned).strip()
        cleaned = re.sub(r"(?i)\s+(?:UTC|GMT)[+-]\d{1,2}(?::?\d{2})?\s*$", "", cleaned).strip()
        cleaned = re.sub(r"(?<=\d)\s+[A-Z]{3,5}\s*$", "", cleaned).strip()
        cleaned = re.sub(r"(?:(?<=AM)|(?<=PM))\s+[A-Z]{3,5}\s*$", "", cleaned).strip()
        return cleaned

    def _try_parse_deadline_single(self, cleaned: str, *, reference_year: int) -> tuple[datetime, bool] | None:
        patterns: list[tuple[str, bool]] = [
            ("%a %d %b - %I:%M %p", True),
            ("%a %d %b %I:%M %p", True),
            ("%d %b - %I:%M %p", True),
            ("%d %b %I:%M %p", True),
            ("%d %b, %I:%M %p", True),
            ("%d %B - %I:%M %p", True),
            ("%d %B %I:%M %p", True),
            ("%d %B, %I:%M %p", True),
            ("%d %b %H:%M", True),
            ("%d %B %H:%M", True),
            ("%b %d - %I:%M %p", True),
            ("%b %d %I:%M %p", True),
            ("%b %d, %I:%M %p", True),
            ("%b %d %H:%M", True),
            ("%B %d - %I:%M %p", True),
            ("%B %d %I:%M %p", True),
            ("%B %d, %I:%M %p", True),
            ("%B %d %H:%M", True),
            ("%d %b", False),
            ("%d %B", False),
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

        fallback = self._try_parse_deadline_fallback(cleaned, reference_year=reference_year)
        if fallback is not None:
            return fallback
        return None

    def _try_parse_deadline_fallback(self, cleaned: str, *, reference_year: int) -> tuple[datetime, bool] | None:
        patterns = [
            re.compile(
                r"^(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]{3,9})(?:,)?(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?:\s*(?P<ampm>AM|PM))?)?$",
                re.IGNORECASE,
            ),
            re.compile(
                r"^(?P<month>[A-Za-z]{3,9})\s+(?P<day>\d{1,2})(?:,)?(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})(?:\s*(?P<ampm>AM|PM))?)?$",
                re.IGNORECASE,
            ),
        ]

        for pattern in patterns:
            match = pattern.match(cleaned)
            if not match:
                continue
            month_value = self._month_number(match.group("month"))
            if month_value is None:
                continue
            try:
                day_value = int(match.group("day"))
            except (TypeError, ValueError):
                continue

            hour_text = match.group("hour")
            minute_text = match.group("minute")
            ampm = match.group("ampm")
            if hour_text is None or minute_text is None:
                try:
                    return datetime(reference_year, month_value, day_value), False
                except ValueError:
                    continue

            converted_hour = self._converted_hour(hour_text, minute_text, ampm)
            if converted_hour is None:
                continue
            hour_value, minute_value = converted_hour
            try:
                return datetime(reference_year, month_value, day_value, hour_value, minute_value), True
            except ValueError:
                continue
        return None

    def _try_parse_range_end(self, end_text: str, *, start_dt: datetime) -> tuple[datetime, bool] | None:
        cleaned_end = self._clean_deadline_text(end_text).strip(" ,.-")
        parsed_with_date = self._try_parse_deadline_single(cleaned_end, reference_year=start_dt.year)
        if parsed_with_date is not None:
            return parsed_with_date

        time_match = re.match(
            r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})(?:\s*(?P<ampm>AM|PM))?$",
            cleaned_end,
            re.IGNORECASE,
        )
        if not time_match:
            return None

        converted_hour = self._converted_hour(
            time_match.group("hour"),
            time_match.group("minute"),
            time_match.group("ampm"),
        )
        if converted_hour is None:
            return None
        hour_value, minute_value = converted_hour
        return start_dt.replace(hour=hour_value, minute=minute_value, second=0, microsecond=0), True

    @staticmethod
    def _month_number(token: str) -> int | None:
        if not token:
            return None
        normalized = token.strip()
        for fmt in ("%b", "%B"):
            try:
                return datetime.strptime(normalized, fmt).month
            except ValueError:
                continue
        return None

    @staticmethod
    def _converted_hour(hour_text: str, minute_text: str, ampm: str | None) -> tuple[int, int] | None:
        try:
            hour = int(hour_text)
            minute = int(minute_text)
        except (TypeError, ValueError):
            return None
        if minute < 0 or minute > 59:
            return None

        if ampm:
            marker = ampm.upper()
            if hour < 1 or hour > 12:
                return None
            if marker == "AM":
                hour = 0 if hour == 12 else hour
            elif marker == "PM":
                hour = 12 if hour == 12 else hour + 12
            else:
                return None
            return hour, minute

        if hour < 0 or hour > 23:
            return None
        return hour, minute

    @staticmethod
    def _is_full_day_same_date_range(
        *,
        start_dt: datetime,
        end_dt: datetime,
        start_has_time: bool,
        end_has_time: bool,
    ) -> bool:
        if not (start_has_time and end_has_time):
            return False
        if start_dt.date() != end_dt.date():
            return False
        is_start_of_day = (start_dt.hour, start_dt.minute, start_dt.second) == (0, 0, 0)
        is_end_of_day = (end_dt.hour, end_dt.minute) == (23, 59)
        return is_start_of_day and is_end_of_day

    @staticmethod
    def _row_dedupe_key(row: dict) -> str:
        subject = str(row.get("subject") or "").casefold()
        sender = str(row.get("sender_email") or "").casefold()
        return f"{sender}|{subject}"

    @staticmethod
    def _email_fields(email: DigestImportantEmailDetail | dict) -> dict:
        if isinstance(email, dict):
            priority_source = email.get("priority_score", email.get("priority", 3))
            try:
                priority_score = int(priority_source)
            except (TypeError, ValueError):
                priority_score = 3
            return {
                "subject": str(email.get("subject") or ""),
                "sender_email": str(email.get("sender_email") or ""),
                "summary": str(email.get("summary") or email.get("snippet") or ""),
                "reason": str(email.get("reason") or email.get("why_important") or ""),
                "why_important": str(email.get("why_important") or email.get("reason") or ""),
                "recommended_action": str(email.get("suggested_action") or ""),
                "status": str(email.get("status") or ("read" if email.get("is_read") else "unread")),
                "category": str(email.get("category") or ""),
                "priority": str(email.get("priority") or ""),
                "deadlines": [str(item) for item in (email.get("extracted_deadlines") or [])],
                "priority_score": max(1, min(priority_score, 5)),
            }

        return {
            "subject": str(email.subject or ""),
            "sender_email": str(email.sender_email or ""),
            "summary": str(email.summary or ""),
            "reason": str(email.reason or ""),
            "why_important": str(email.reason or ""),
            "recommended_action": str(email.recommended_action or ""),
            "status": str(email.status or "unknown"),
            "category": "",
            "priority": "",
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
