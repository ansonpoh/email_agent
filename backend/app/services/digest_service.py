from app.schemas.digest_schema import DigestBucketItem, DigestOutput


class DigestService:
    def build_digest(self, email_rows: list[dict]) -> DigestOutput:
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

        suggested_next_steps = [
            "Review high-priority threads first.",
            "Open Gmail and send approved drafts manually.",
            "Confirm tasks with explicit deadlines.",
        ]

        digest_text = self._compose_text(priority_emails, needs_reply, deadlines, low_priority, suggested_next_steps)

        return DigestOutput(
            priority_emails=priority_emails,
            needs_reply=needs_reply,
            deadlines=deadlines,
            low_priority=low_priority,
            suggested_next_steps=suggested_next_steps,
            digest_text=digest_text,
        )

    def _compose_text(
        self,
        priority_emails: list[DigestBucketItem],
        needs_reply: list[DigestBucketItem],
        deadlines: list[DigestBucketItem],
        low_priority: list[DigestBucketItem],
        steps: list[str],
    ) -> str:
        lines = ["Gmail Digest", ""]
        lines.append(f"Priority emails: {len(priority_emails)}")
        lines.append(f"Needs reply: {len(needs_reply)}")
        lines.append(f"Deadlines/tasks: {len(deadlines)}")
        lines.append(f"Low priority: {len(low_priority)}")
        if not (priority_emails or needs_reply or deadlines or low_priority):
            lines.append("No new emails in this period.")
        lines.append("")
        lines.append("Suggested next steps:")
        lines.extend(f"- {step}" for step in steps)
        return "\n".join(lines)
