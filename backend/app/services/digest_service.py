from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.digest_schema import (
    AIDigestSummaryOutput,
    DigestBucketItem,
    DigestImportantEmailDetail,
    DigestOutput,
)


class DigestService:
    def build_digest(
        self,
        *,
        email_rows: list[dict],
        ai_summary: AIDigestSummaryOutput,
        period_start: datetime,
        period_end: datetime,
        user_timezone: str | None,
    ) -> DigestOutput:
        timezone_name = user_timezone or "UTC"
        tz = self._resolved_timezone(timezone_name)
        generated_at_local = datetime.now(timezone.utc).astimezone(tz)

        important_items = self._important_email_details(email_rows=email_rows, ai_summary=ai_summary)
        priority_emails, needs_reply, deadlines, low_priority = self._legacy_buckets(email_rows)
        suggested_next_steps = list(ai_summary.suggested_actions or [])
        additional_notes = list(ai_summary.additional_notes or [])
        stats_notes = self._stats_notes(email_rows=email_rows)
        merged_notes = stats_notes + additional_notes

        digest_text = self._compose_text(
            timezone_name=timezone_name,
            generated_at_local=generated_at_local,
            email_count=len(email_rows),
            overview=ai_summary.overview,
            important_emails=important_items,
            suggested_actions=suggested_next_steps,
            additional_notes=merged_notes,
        )

        return DigestOutput(
            overview=ai_summary.overview,
            important_emails=important_items,
            suggested_actions=suggested_next_steps,
            additional_notes=merged_notes,
            priority_emails=priority_emails,
            needs_reply=needs_reply,
            deadlines=deadlines,
            low_priority=low_priority,
            suggested_next_steps=suggested_next_steps,
            digest_text=digest_text,
        )

    @staticmethod
    def _resolved_timezone(timezone_name: str):
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return timezone.utc

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _important_email_details(
        self,
        *,
        email_rows: list[dict],
        ai_summary: AIDigestSummaryOutput,
    ) -> list[DigestImportantEmailDetail]:
        selected: list[DigestImportantEmailDetail] = []
        used_indexes: set[int] = set()
        max_index = len(email_rows)
        for item in ai_summary.important_emails[:3]:
            source_index = int(item.source_index)
            if source_index < 1 or source_index > max_index or source_index in used_indexes:
                continue
            used_indexes.add(source_index)
            row = email_rows[source_index - 1]
            selected.append(
                DigestImportantEmailDetail(
                    email_id=row["id"],
                    sender_email=row.get("sender_email") or "unknown@example.com",
                    subject=row.get("subject") or "(No subject)",
                    received_at=row.get("received_at"),
                    status="read" if row.get("is_read") else "unread",
                    summary=row.get("summary") or "No summary",
                    priority_score=max(1, min(int(row.get("priority_score", 3)), 5)),
                    reason=item.reason.strip() or "Marked important by AI.",
                    recommended_action=item.recommended_action.strip()
                    or str(row.get("suggested_action") or "Review this thread."),
                    deadlines=[str(deadline) for deadline in (row.get("extracted_deadlines") or [])],
                )
            )
        return selected

    def _legacy_buckets(
        self,
        email_rows: list[dict],
    ) -> tuple[list[DigestBucketItem], list[DigestBucketItem], list[DigestBucketItem], list[DigestBucketItem]]:
        priority_emails: list[DigestBucketItem] = []
        needs_reply: list[DigestBucketItem] = []
        deadlines: list[DigestBucketItem] = []
        low_priority: list[DigestBucketItem] = []

        for row in email_rows:
            item = DigestBucketItem(
                email_id=row["id"],
                subject=row.get("subject") or "(No subject)",
                sender_email=row["sender_email"],
                note=row.get("summary") or "No summary",
            )

            priority = row.get("priority_score", 3)
            if priority >= 4:
                priority_emails.append(item)
            else:
                low_priority.append(item)

            if row.get("suggested_action"):
                needs_reply.append(item)

            if row.get("extracted_deadlines"):
                deadlines.append(item)

        return priority_emails, needs_reply, deadlines, low_priority

    @staticmethod
    def _stats_notes(email_rows: list[dict]) -> list[str]:
        total = len(email_rows)
        unread = sum(1 for row in email_rows if not row.get("is_read"))
        high_priority = sum(1 for row in email_rows if int(row.get("priority_score", 3)) >= 4)
        with_deadlines = sum(1 for row in email_rows if row.get("extracted_deadlines"))
        return [
            f"Quick stats: {total} emails, {unread} unread.",
            f"High-priority threads: {high_priority}; threads with deadlines/tasks: {with_deadlines}.",
        ]

    def _compose_text(
        self,
        *,
        timezone_name: str,
        generated_at_local: datetime,
        email_count: int,
        overview: str,
        important_emails: list[DigestImportantEmailDetail],
        suggested_actions: list[str],
        additional_notes: list[str],
    ) -> str:
        lines = [
            "AI Email Digest",
            f"Date and time: {generated_at_local.strftime('%Y-%m-%d %H:%M')} ({timezone_name})",
            f"Emails analyzed: {email_count}",
            "",
            "Summary:",
            overview.strip() or "No summary available.",
            "",
            "Top Important Emails:",
        ]
        if important_emails:
            for idx, item in enumerate(important_emails, start=1):
                received_label = (
                    self._as_utc(item.received_at).astimezone(generated_at_local.tzinfo).strftime("%Y-%m-%d %H:%M")
                    if item.received_at
                    else "unknown"
                )
                lines.extend(
                    [
                        f"{idx}. {item.subject}",
                        f"   From: {item.sender_email}",
                        f"   Received: {received_label} ({timezone_name})",
                        f"   Status/Priority: {item.status}; {item.priority_score}/5",
                        f"   Details: {item.summary}",
                        f"   Why important: {item.reason}",
                        f"   Suggested action: {item.recommended_action}",
                    ]
                )
                if item.deadlines:
                    lines.append(f"   Deadlines/tasks: {', '.join(item.deadlines)}")
        else:
            lines.append("- None")

        lines.append("")
        lines.append("Additional important context:")
        if additional_notes:
            lines.extend(f"- {note}" for note in additional_notes)
        else:
            lines.append("- None")

        lines.append("")
        lines.append("Suggested actions:")
        if suggested_actions:
            lines.extend(f"- {action}" for action in suggested_actions)
        else:
            lines.append("- None")
        return "\n".join(lines)
