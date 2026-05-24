from app.services.agent_service import AgentService
from app.services.digest_service import DigestService


def test_agent_service_detects_urgency():
    service = AgentService()
    result = service.analyse_email(subject="Urgent", body_text="Please reply ASAP")
    assert result.priority_score == 5
    assert result.category == "urgent"


def test_digest_service_builds_text():
    service = DigestService()
    output = service.build_digest(
        [
            {
                "id": 1,
                "subject": "Test",
                "sender_email": "a@example.com",
                "summary": "Summary",
                "priority_score": 4,
                "extracted_deadlines": ["Tomorrow"],
                "suggested_action": "Reply",
            }
        ]
    )

    assert "Priority emails: 1" in output.digest_text
    assert len(output.priority_emails) == 1
    assert len(output.deadlines) == 1
