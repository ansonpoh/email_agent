from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.digest_schema import DigestImportantEmailDetail, DigestOutput


class TelegramDigestFormatter:
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

        summary = self._compact_text(digest.overview or "No summary available.", max_len=420)
        tasks = self._collect_tasks(email_rows=email_rows, important_emails=digest.important_emails)
        cards = self._format_important_email_cards(digest.important_emails, timezone_name=timezone_name, local_tz=tz)
        suggested_actions = self._format_checklist_items(digest.suggested_actions, empty_text="No suggested actions.")

        lines = [
            "📬 *AI Email Digest*",
            "",
            f"🕐 *{generated_at_local.strftime('%Y-%m-%d %H:%M')} ({self.escape_telegram_markdown(timezone_name)})*",
            f"📨 *{emails_analyzed} emails analyzed* | *{unread_count} unread*",
            "",
            "---",
            "",
            "🔎 *Summary*",
            "",
            self.escape_telegram_markdown(summary),
            "",
            "---",
            "",
            "🚨 *Top Important Emails*",
            "",
            cards,
            "",
            "---",
            "",
            "📅 *Tasks / Deadlines*",
            "",
            self._format_tasks(tasks),
            "",
            "---",
            "",
            "✅ *Suggested Actions*",
            "",
            suggested_actions,
        ]
        return "\n".join(lines).strip()

    def _format_important_email_cards(
        self,
        important_emails: list[DigestImportantEmailDetail],
        *,
        timezone_name: str,
        local_tz: ZoneInfo | timezone,
    ) -> str:
        if not important_emails:
            return "No high-priority emails found."

        cards: list[str] = []
        for index, email in enumerate(important_emails, start=1):
            cards.append(
                self.format_email_card(
                    email=email,
                    index=index,
                    timezone_name=timezone_name,
                    local_tz=local_tz,
                )
            )
        return "\n\n---\n\n".join(cards)

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
            received_text = self._as_utc(email.received_at).astimezone(local_tz).strftime("%Y-%m-%d %H:%M")

        subject = self._compact_text(email.subject or "(No subject)", max_len=120)
        sender = self._compact_text(email.sender_email or "unknown@example.com", max_len=100)
        why = self._compact_text(email.reason or "Marked important by AI.", max_len=220)
        action = self._compact_text(email.recommended_action or "Review this thread.", max_len=180)
        status = self._compact_text(email.status or "unknown", max_len=20)
        priority_icon = self.priority_to_icon(email.priority_score)

        return "\n".join(
            [
                f"*{index}. {self.escape_telegram_markdown(subject)}*",
                f"From: {self.escape_telegram_markdown(sender)}",
                f"Received: {self.escape_telegram_markdown(received_text)} ({self.escape_telegram_markdown(timezone_name)})",
                f"Priority: {self.escape_telegram_markdown(priority_icon)} {email.priority_score}/5",
                f"Status: {self.escape_telegram_markdown(status)}",
                "",
                f"*Why it matters:* {self.escape_telegram_markdown(why)}",
                f"*Action:* {self.escape_telegram_markdown(action)}",
            ]
        )

    def _collect_tasks(
        self,
        *,
        email_rows: list[dict] | None,
        important_emails: list[DigestImportantEmailDetail],
    ) -> list[str]:
        tasks: list[str] = []

        if email_rows:
            for row in email_rows:
                for deadline in row.get("extracted_deadlines") or []:
                    text = self._compact_text(str(deadline), max_len=140)
                    if text:
                        tasks.append(text)

        if not tasks:
            for item in important_emails:
                for deadline in item.deadlines:
                    text = self._compact_text(str(deadline), max_len=140)
                    if text:
                        tasks.append(text)

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

    def _format_tasks(self, tasks: list[str]) -> str:
        return self._format_checklist_items(tasks, empty_text="No deadlines found.")

    def _format_checklist_items(self, items: list[str], *, empty_text: str) -> str:
        if not items:
            return empty_text
        return "\n".join(f"• {self.escape_telegram_markdown(self._compact_text(item, max_len=180))}" for item in items[:8])

    @staticmethod
    def priority_to_icon(priority: int) -> str:
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
        return normalized[: max_len - 1].rstrip() + "…"

    @staticmethod
    def escape_telegram_markdown(text: str) -> str:
        escaped = str(text or "")
        for char in ("\\", "_", "*", "[", "]", "`"):
            escaped = escaped.replace(char, f"\\{char}")
        return escaped

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
