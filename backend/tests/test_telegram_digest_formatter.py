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
                "extracted_deadlines": ["Wed 10 Jun - 02:00 pm", "May 28"],
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
    assert message.index("May 28 — Reply to lunch meeting request") < message.index(
        "Jun 10, 2:00 PM — Reply to lunch meeting request"
    )
    assert "<b>💼 Jobs / Opportunities</b>" not in message
    assert "• New internship opportunities" in message
    assert "From: jobs@board.example" in message
    assert "<b>ℹ️ Optional / Informational</b>" in message
    assert "• 20% discount gift code" in message
    assert "From: promo@shop.example" in message
    assert "<b>✅ Suggested Actions</b>" in message
    assert "• Review GitHub OAuth authorization" in message
    assert "Optional:" in message
    assert "Optional:\n• Redeem gift code" in message
    assert message.count("• Redeem gift code") == 1
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
    assert "No optional informational emails highlighted." in message
    assert "No suggested actions." in message


def test_escape_telegram_text_html_safe_without_markdown_backslashes():
    escaped = TelegramDigestFormatter.escape_telegram_text("<b>[GitHub]</b> & status")
    assert escaped == "&lt;b&gt;[GitHub]&lt;/b&gt; &amp; status"


def test_collect_descriptive_tasks_preserves_order_for_same_date():
    formatter = TelegramDigestFormatter()

    tasks = formatter._collect_descriptive_tasks(
        email_rows=[
            {
                "id": uuid4(),
                "subject": "Reminder A",
                "summary": "Summary A",
                "suggested_action": "First action",
                "extracted_deadlines": ["May 28"],
            },
            {
                "id": uuid4(),
                "subject": "Reminder B",
                "summary": "Summary B",
                "suggested_action": "Second action",
                "extracted_deadlines": ["May 28"],
            },
        ],
        important_emails=[],
        reference_year=2026,
    )

    assert tasks[:2] == ["May 28 — First action", "May 28 — Second action"]


def test_collect_descriptive_tasks_places_unparseable_after_parseable():
    formatter = TelegramDigestFormatter()

    tasks = formatter._collect_descriptive_tasks(
        email_rows=[
            {
                "id": uuid4(),
                "subject": "Unclear deadline",
                "summary": "Custom follow-up text",
                "suggested_action": "Handle custom timeline",
                "extracted_deadlines": ["sometime next sprint"],
            },
            {
                "id": uuid4(),
                "subject": "Known date",
                "summary": "Date is clear",
                "suggested_action": "Handle dated item",
                "extracted_deadlines": ["May 28"],
            },
        ],
        important_emails=[],
        reference_year=2026,
    )

    assert tasks[:2] == ["May 28 — Handle dated item", "sometime next sprint — Handle custom timeline"]


def test_collect_descriptive_tasks_keeps_earliest_eight_after_sorting():
    formatter = TelegramDigestFormatter()

    tasks = formatter._collect_descriptive_tasks(
        email_rows=[
            {
                "id": uuid4(),
                "subject": "Project milestones",
                "summary": "Milestone planning",
                "suggested_action": "Prepare milestone",
                "extracted_deadlines": [
                    "Jun 10",
                    "Jun 09",
                    "Jun 08",
                    "Jun 07",
                    "Jun 06",
                    "Jun 05",
                    "Jun 04",
                    "Jun 03",
                    "Jun 02",
                    "Jun 01",
                ],
            }
        ],
        important_emails=[],
        reference_year=2026,
    )

    assert tasks == [
        "Jun 1 — Prepare milestone",
        "Jun 2 — Prepare milestone",
        "Jun 3 — Prepare milestone",
        "Jun 4 — Prepare milestone",
        "Jun 5 — Prepare milestone",
        "Jun 6 — Prepare milestone",
        "Jun 7 — Prepare milestone",
        "Jun 8 — Prepare milestone",
    ]


def test_collect_descriptive_tasks_sorts_mixed_formats_from_earliest_to_latest():
    formatter = TelegramDigestFormatter()

    tasks = formatter._collect_descriptive_tasks(
        email_rows=[
            {
                "id": uuid4(),
                "subject": "May 31 confirmation",
                "summary": "",
                "suggested_action": "Check calendar for availability on May 31 and respond to confirm or propose alternative date.",
                "extracted_deadlines": ["May 31"],
            },
            {
                "id": uuid4(),
                "subject": "May 28 confirmation",
                "summary": "",
                "suggested_action": "Check calendar for availability on May 28 and reply to Anson confirming or proposing an alternative time.",
                "extracted_deadlines": ["May 28"],
            },
            {
                "id": uuid4(),
                "subject": "Ticket event",
                "summary": "",
                "suggested_action": "Add event to calendar and prepare to attend on the specified date and time. Review ticket instructions and keep digital tickets accessible.",
                "extracted_deadlines": ["Jun 10, 2:00 PM"],
            },
            {
                "id": uuid4(),
                "subject": "Lunch planning",
                "summary": "",
                "suggested_action": "Respond with proposed time and place for lunch on 31 May.",
                "extracted_deadlines": ["31 May"],
            },
            {
                "id": uuid4(),
                "subject": "Promo window",
                "summary": "",
                "suggested_action": "Review promotional offers if interested; no immediate action required.",
                "extracted_deadlines": ["May 27 00:00 to 23:59"],
            },
        ],
        important_emails=[],
        reference_year=2026,
    )

    assert tasks[:5] == [
        "May 27 00:00 to 23:59 — Review promotional offers if interested; no immediate action required.",
        "May 28 — Check calendar for availability on May 28 and reply to Anson confirming or proposing an alternative time.",
        "May 31 — Check calendar for availability on May 31 and respond to confirm or propose alternative date.",
        "May 31 — Respond with proposed time and place for lunch on 31 May.",
        "Jun 10, 2:00 PM — Add event to calendar and prepare to attend on the specified date and time. Review ticket instructions and keep digital tickets accessible.",
    ]


def test_try_parse_deadline_supports_day_first_and_range_start():
    formatter = TelegramDigestFormatter()

    day_first = formatter._try_parse_deadline("31 May", reference_year=2026)
    assert day_first == (datetime(2026, 5, 31), False)

    with_time = formatter._try_parse_deadline("31 May 2:00 PM", reference_year=2026)
    assert with_time == (datetime(2026, 5, 31, 14, 0), True)

    range_start = formatter._try_parse_deadline("May 27 00:00 to 23:59", reference_year=2026)
    assert range_start == (datetime(2026, 5, 27, 0, 0), True)


def test_categorize_email_for_display_direct_human_reply_with_deadline_is_needs_attention():
    formatter = TelegramDigestFormatter()

    category = formatter.categorize_email_for_display(
        {
            "sender_email": "teammate@example.com",
            "subject": "Lunch meeting this Friday",
            "summary": "Can you confirm availability?",
            "suggested_action": "Reply and propose time options.",
            "extracted_deadlines": ["May 28"],
            "priority_score": 3,
            "category": "meeting_request",
        }
    )

    assert category == "needs_attention"


def test_categorize_email_for_display_recruiter_professor_and_teammate_threads_are_needs_attention():
    formatter = TelegramDigestFormatter()

    recruiter = formatter.categorize_email_for_display(
        {
            "sender_email": "recruiter@company.com",
            "subject": "Interview follow up",
            "summary": "Please confirm your availability.",
            "suggested_action": "Respond with available time slots.",
            "priority_score": 2,
        }
    )
    professor = formatter.categorize_email_for_display(
        {
            "sender_email": "professor@university.edu",
            "subject": "Schedule office hours",
            "summary": "Can we meet next week?",
            "suggested_action": "Reply with proposed times.",
            "priority_score": 2,
        }
    )
    teammate = formatter.categorize_email_for_display(
        {
            "sender_email": "colleague@example.com",
            "subject": "Meeting follow up",
            "summary": "Respond with your availability.",
            "suggested_action": "Confirm and propose time.",
            "priority_score": 2,
        }
    )

    assert recruiter == "needs_attention"
    assert professor == "needs_attention"
    assert teammate == "needs_attention"


def test_categorize_email_for_display_excludes_automated_sources_from_human_reply_rule():
    formatter = TelegramDigestFormatter()

    no_reply = formatter.categorize_email_for_display(
        {
            "sender_email": "no-reply@calendar.example.com",
            "subject": "Meeting confirmation",
            "summary": "Please do not reply.",
            "suggested_action": "No action needed.",
            "priority_score": 2,
        }
    )
    newsletter = formatter.categorize_email_for_display(
        {
            "sender_email": "digest@news.example.com",
            "subject": "Weekly newsletter",
            "summary": "Top stories and updates.",
            "suggested_action": "Archive.",
            "priority_score": 2,
            "category": "newsletter",
        }
    )
    job_alert = formatter.categorize_email_for_display(
        {
            "sender_email": "alerts@jobs.example.com",
            "subject": "Job alert: new positions",
            "summary": "Recommended jobs this week.",
            "suggested_action": "Browse if interested.",
            "priority_score": 2,
        }
    )
    receipt = formatter.categorize_email_for_display(
        {
            "sender_email": "billing@vendor.example.com",
            "subject": "Payment receipt",
            "summary": "Thanks for your purchase.",
            "suggested_action": "Keep for records.",
            "priority_score": 2,
        }
    )
    system_notice = formatter.categorize_email_for_display(
        {
            "sender_email": "updates@platform.example.com",
            "subject": "System notification",
            "summary": "Automated account update.",
            "suggested_action": "No response required.",
            "priority_score": 2,
        }
    )

    assert no_reply != "needs_attention"
    assert newsletter != "needs_attention"
    assert job_alert != "needs_attention"
    assert receipt != "needs_attention"
    assert system_notice != "needs_attention"


def test_categorize_email_for_display_security_still_maps_to_needs_attention():
    formatter = TelegramDigestFormatter()

    category = formatter.categorize_email_for_display(
        {
            "sender_email": "security@github.com",
            "subject": "Security alert",
            "summary": "Suspicious sign in attempt detected.",
            "suggested_action": "Review immediately.",
            "priority_score": 2,
        }
    )

    assert category == "needs_attention"


def test_group_by_display_type_fallback_to_needs_attention_when_none_classified():
    formatter = TelegramDigestFormatter()
    digest_item = DigestImportantEmailDetail(
        email_id=uuid4(),
        sender_email="tickets@example.com",
        subject="Event invitation",
        received_at=datetime(2026, 5, 27, 8, 0, tzinfo=timezone.utc),
        status="unread",
        summary="Invitation details.",
        priority_score=2,
        reason="Event details",
        recommended_action="Review event info.",
        deadlines=["Jun 10"],
    )

    grouped = formatter._group_by_display_type([digest_item], row_lookup={})

    assert grouped["events"] == [digest_item]
    assert grouped["needs_attention"] == [digest_item]


def test_summary_security_count_uses_displayed_needs_attention_items_only():
    formatter = TelegramDigestFormatter()
    security_email_id = uuid4()
    digest = DigestOutput(
        overview="Security activity detected.",
        important_emails=[
            DigestImportantEmailDetail(
                email_id=security_email_id,
                sender_email="security@github.com",
                subject="GitHub OAuth authorization",
                received_at=datetime(2026, 5, 26, 9, 30, tzinfo=timezone.utc),
                status="unread",
                summary="Suspicious OAuth authorization detected.",
                priority_score=5,
                reason="Security alert requires immediate review.",
                recommended_action="Review and revoke unknown app access.",
                deadlines=[],
            )
        ],
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
        email_rows=[
            {
                "id": security_email_id,
                "sender_email": "security@github.com",
                "subject": "GitHub OAuth authorization",
                "is_read": False,
                "summary": "Suspicious OAuth authorization detected.",
                "priority_score": 5,
                "extracted_deadlines": [],
                "suggested_action": "Review and revoke unknown app access.",
            },
            {
                "id": uuid4(),
                "sender_email": "security@other-app.com",
                "subject": "Security alert for another account",
                "is_read": True,
                "summary": "Security notification.",
                "priority_score": 1,
                "extracted_deadlines": [],
                "suggested_action": "Archive",
            },
            {
                "id": uuid4(),
                "sender_email": "alerts@service.example.com",
                "subject": "OAuth token issued",
                "is_read": True,
                "summary": "Automated security info.",
                "priority_score": 1,
                "extracted_deadlines": [],
                "suggested_action": "Archive",
            },
        ],
        generated_at=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
        timezone_name="UTC",
    )

    assert "1 security alert needs review: GitHub OAuth authorization" in message
    assert "2 security alerts need review" not in message


def test_summary_job_count_respects_visible_optional_section_limit():
    formatter = TelegramDigestFormatter()
    rows: list[dict] = []
    for idx in range(8):
        rows.append(
            {
                "id": uuid4(),
                "sender_email": f"jobs{idx}@board.example",
                "subject": f"Job opportunity {idx}",
                "is_read": False,
                "summary": "A new role matches your profile.",
                "priority_score": 2,
                "extracted_deadlines": [],
                "suggested_action": "Review role details.",
            }
        )

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
        email_rows=rows,
        generated_at=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
        timezone_name="UTC",
    )

    assert "6 job/opportunity emails identified" in message
    assert "8 job/opportunity emails identified" not in message

