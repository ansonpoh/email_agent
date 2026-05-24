from app.schemas.agent_schema import DraftReplyOutput
from app.services.gmail_service import GmailService


class DraftService:
    def __init__(self, gmail_service: GmailService):
        self.gmail_service = gmail_service

    def generate_draft(self, subject: str | None, body_text: str, tone: str = "professional") -> DraftReplyOutput:
        draft_subject = f"Re: {subject}" if subject else "Re: Your email"
        draft_body = (
            "Hi,\n\n"
            "Thanks for your message. I reviewed your note and will follow up shortly.\n\n"
            "Best,\n"
            "[Your Name]"
        )

        if tone == "friendly":
            draft_body = (
                "Hi there,\n\n"
                "Thanks for reaching out. I have seen your email and will get back with details shortly.\n\n"
                "Best,\n"
                "[Your Name]"
            )

        return DraftReplyOutput(
            subject=draft_subject,
            body=draft_body,
            tone=tone,
            requires_user_review=True,
        )

    def create_in_gmail(self, subject: str, body: str) -> str:
        return self.gmail_service.create_gmail_draft(draft_body=body, subject=subject)
