from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.digest_schema import DigestImportantEmailDetail, DigestOutput
from app.services.telegram_digest_formatter import TelegramDigestFormatter


def test_formatter_renders_grouped_html_digest_with_descriptive_deadlines():
    formatter = TelegramDigestFormatter()
    security_email_id = uuid4()
    event_email_id = uuid4()

    digest = DigestOutput(
        overview="Two important updates need your review.",
        important_emails=[
            DigestImportantEmailDetail(
                email_id=security_email_id,
                sender_email="security@github.com",
                subject="GitHub OAuth authorization alert",
                received_at=datetime(2026, 5, 26, 9, 30, tzinfo=timezone.utc),
                status="unread",
                summary="Suspicious OAuth authorization detected.",
                priority_score=5,
                reason="Security alert requires immediate review.",
                recommended_action="Review and revoke unknown app access.",
                deadlines=[],
            ),
            DigestImportantEmailDetail(
                email_id=event_email_id,
                sender_email="tickets@example.com",
                subject="CJ Hendry's Flower Market",
                received_at=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
                status="unread",
                summary="Event confirmation received.",
                priority_score=3,
                reason="Confirmed event with scheduled date.",
                recommended_action="Add this event to calendar.",
                deadlines=["Wed 10 Jun - 02:00 pm"],
            ),
        ],
        suggested_actions=["Review GitHub OAuth authorization", "Redeem gift code"],
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
                "id": security_email_id,
                "sender_email": "security@github.com",
                "subject": "GitHub OAuth authorization alert",
                "is_read": False,
                "summary": "Suspicious OAuth authorization detected.",
                "priority_score": 5,
                "extracted_deadlines": [],
                "suggested_action": "Review and revoke unknown app access.",
            },
            {
                "id": event_email_id,
                "sender_email": "tickets@example.com",
                "subject": "CJ Hendry's Flower Market",
                "is_read": False,
                "summary": "Event confirmation received.",
                "priority_score": 3,
                "extracted_deadlines": ["May 28", "Wed 10 Jun - 02:00 pm"],
                "suggested_action": "Reply to lunch meeting request",
            },
            {
                "id": uuid4(),
                "sender_email": "jobs@board.example",
                "subject": "New internship opportunities",
                "is_read": True,
                "summary": "3 roles match your profile.",
                "priority_score": 2,
                "extracted_deadlines": [],
                "suggested_action": "Review relevant roles.",
            },
            {
                "id": uuid4(),
                "sender_email": "promo@shop.example",
                "subject": "20% discount gift code",
                "is_read": True,
                "summary": "Promotional offer.",
                "priority_score": 1,
                "extracted_deadlines": [],
                "suggested_action": "Redeem gift code",
            },
        ],
        generated_at=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
        timezone_name="UTC",
    )

    assert "<b>📬 AI Email Digest</b>" in message
    assert "<b>🔎 Summary</b>" in message
    assert "<b>🚨 Needs Attention</b>" in message
    assert "Priority: 🔴 High 5/5" in message
    assert "<b>📅 Events / Deadlines</b>" in message
    assert "• May 28 — Reply to lunch meeting request" in message
    assert "• Jun 10, 2:00 PM — Reply to lunch meeting request" in message
    assert "<b>💼 Jobs / Opportunities</b>" in message
    assert "• New internship opportunities" in message
    assert "<b>ℹ️ Optional / Informational</b>" in message
    assert "• 20% discount gift code" in message
    assert "<b>✅ Suggested Actions</b>" in message
    assert "☐ Review GitHub OAuth authorization" in message
    assert "☐ Redeem gift code" not in message
    assert "Optional:" in message
    assert "• Redeem gift code" in message


def test_formatter_falls_back_when_sections_empty():
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

    assert "No urgent items found." in message
    assert "No deadlines found." in message
    assert "No job/opportunity emails found." in message
    assert "No optional informational emails highlighted." in message
    assert "No suggested actions." in message


def test_escape_telegram_text_html_safe_without_markdown_backslashes():
    escaped = TelegramDigestFormatter.escape_telegram_text("<b>[GitHub]</b> & status")
    assert escaped == "&lt;b&gt;[GitHub]&lt;/b&gt; &amp; status"
