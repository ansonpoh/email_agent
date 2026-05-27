from datetime import datetime, timezone


class TelegramDirectEmailFormatter:
    @classmethod
    def urgency_label(cls, urgency: str | None) -> str:
        value = (urgency or "low").strip().lower()
        if value == "high":
            return "🔴 High"
        if value == "medium":
            return "🟡 Medium"
        return "🟢 Low"

    @classmethod
    def format_success_notification(
        cls,
        *,
        sender: str,
        subject: str,
        received_at: datetime | None,
        urgency: str,
        summary: str,
        suggested_action: str,
        draft_preview: str,
        draft_id: str,
    ) -> str:
        received_label = cls._format_received_at(received_at)
        return (
            "📩 *Direct Email Detected*\n\n"
            f"*From:* {cls.escape_telegram_markdown(sender)}\n"
            f"*Subject:* {cls.escape_telegram_markdown(subject)}\n"
            f"*Received:* {cls.escape_telegram_markdown(received_label)}\n"
            f"*Urgency:* {cls.escape_telegram_markdown(cls.urgency_label(urgency))}\n\n"
            "*Summary:*\n"
            f"{cls.escape_telegram_markdown(summary)}\n\n"
            "*Suggested action:*\n"
            f"{cls.escape_telegram_markdown(suggested_action)}\n\n"
            "---\n\n"
            "✍️ *Gmail Draft Created*\n\n"
            f"{cls.escape_telegram_markdown(cls._preview(draft_preview))}\n\n"
            "---\n\n"
            "*Status:* Gmail draft created. Please review and send manually.\n"
            f"*Draft ID:* {cls.escape_telegram_markdown(draft_id)}"
        )

    @classmethod
    def format_failure_notification(
        cls,
        *,
        sender: str,
        subject: str,
        urgency: str,
        summary: str,
        suggested_action: str,
        draft_preview: str,
        error_summary: str,
    ) -> str:
        return (
            "📩 *Direct Email Detected*\n\n"
            f"*From:* {cls.escape_telegram_markdown(sender)}\n"
            f"*Subject:* {cls.escape_telegram_markdown(subject)}\n"
            f"*Urgency:* {cls.escape_telegram_markdown(cls.urgency_label(urgency))}\n\n"
            "*Summary:*\n"
            f"{cls.escape_telegram_markdown(summary)}\n\n"
            "*Suggested action:*\n"
            f"{cls.escape_telegram_markdown(suggested_action)}\n\n"
            "---\n\n"
            "⚠️ *Draft creation failed*\n\n"
            "The AI generated a reply, but the Gmail draft could not be created.\n\n"
            "*Draft preview:*\n"
            f"{cls.escape_telegram_markdown(cls._preview(draft_preview))}\n\n"
            f"*Error:* {cls.escape_telegram_markdown(error_summary)}"
        )

    @staticmethod
    def escape_telegram_markdown(text: str) -> str:
        escaped = str(text or "")
        for char in ("\\", "_", "*", "[", "]", "`"):
            escaped = escaped.replace(char, f"\\{char}")
        return escaped

    @staticmethod
    def _format_received_at(value: datetime | None) -> str:
        if not value:
            return "Unknown"
        if value.tzinfo is None:
            resolved = value.replace(tzinfo=timezone.utc)
        else:
            resolved = value.astimezone(timezone.utc)
        return resolved.strftime("%Y-%m-%d %H:%M UTC")

    @staticmethod
    def _preview(text: str, max_len: int = 500) -> str:
        compact = " ".join((text or "").split()).strip()
        if len(compact) <= max_len:
            return compact
        return compact[: max_len - 3].rstrip() + "..."
