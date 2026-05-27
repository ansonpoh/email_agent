from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.digest_schema import DigestImportantEmailDetail, DigestOutput
from app.services.telegram_digest_formatter import TelegramDigestFormatter


def test_formatter_renders_compact_markdown_digest():
    formatter = TelegramDigestFormatter()
    digest = DigestOutput(
        overview="Two important updates need your review.",
        important_emails=[
            DigestImportantEmailDetail(
                email_id=uuid4(),
                sender_email="finance_team@example.com",
                subject="Invoice follow-up for Q3 billing cycle",
                received_at=datetime(2026, 5, 26, 9, 30, tzinfo=timezone.utc),
                status="unread",
                summary="Invoice due this week.",
                priority_score=5,
                reason="Contains a payment deadline and requires response.",
                recommended_action="Reply with confirmation and timeline.",
                deadlines=["Submit payment confirmation by Friday"],
            )
        ],
        suggested_actions=["Reply to finance thread", "Schedule payment review"],
        additional_notes=[],
        priority_emails=[],
        needs_reply=[],
        deadlines=[],
        low_priority=[],
        suggested_next_steps=[],
        digest_text="legacy digest text",
    )

    message = formatter.format_email_digest_for_telegram(
        digest=digest,
        email_rows=[
            {
                "is_read": False,
                "extracted_deadlines": ["Submit payment confirmation by Friday"],
            }
        ],
        generated_at=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
        timezone_name="UTC",
    )

    assert "📬 *AI Email Digest*" in message
    assert "📨 *1 emails analyzed* | *0 unread*" not in message
    assert "📨 *1 emails analyzed* | *1 unread*" in message
    assert "🔎 *Summary*" in message
    assert "🚨 *Top Important Emails*" in message
    assert "Priority: 🔴 High 5/5" in message
    assert "📅 *Tasks / Deadlines*" in message
    assert "• Submit payment confirmation by Friday" in message
    assert "✅ *Suggested Actions*" in message
    assert "• Reply to finance thread" in message


def test_formatter_falls_back_when_tasks_and_actions_empty():
    formatter = TelegramDigestFormatter()
    digest = DigestOutput(
        overview="No urgent updates.",
        important_emails=[],
        suggested_actions=[],
        additional_notes=[],
        priority_emails=[],
        needs_reply=[],
        deadlines=[],
        low_priority=[],
        suggested_next_steps=[],
        digest_text="legacy digest text",
    )

    message = formatter.format_email_digest_for_telegram(
        digest=digest,
        email_rows=[],
        generated_at=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
        timezone_name="UTC",
    )

    assert "No high-priority emails found." in message
    assert "No deadlines found." in message
    assert "No suggested actions." in message


def test_escape_telegram_markdown_escapes_reserved_chars():
    escaped = TelegramDigestFormatter.escape_telegram_markdown(r"a_b*c[d]`\z")
    assert escaped == r"a\_b\*c\[d\]\`\\z"
