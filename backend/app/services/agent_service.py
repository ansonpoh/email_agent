from app.schemas.email_schema import EmailAnalysisOutput


class AgentService:
    """Agent logic for structured email analysis."""

    def analyse_email(self, subject: str | None, body_text: str) -> EmailAnalysisOutput:
        # TODO: Replace with OpenAI structured output call once OPENAI_API_KEY is configured.
        text = f"{subject or ''} {body_text}".lower()

        priority = 3
        category = "general"
        extracted_tasks: list[str] = []
        extracted_deadlines: list[str] = []

        if "urgent" in text or "asap" in text:
            priority = 5
            category = "urgent"
        elif "invoice" in text or "payment" in text:
            priority = 4
            category = "finance"

        if "please" in text or "can you" in text:
            extracted_tasks.append("Respond to sender request")

        if "tomorrow" in text:
            extracted_deadlines.append("Tomorrow")

        summary = (body_text[:200] + "...") if len(body_text) > 200 else body_text
        key_points = [summary] if summary else []

        return EmailAnalysisOutput(
            category=category,
            priority_score=priority,
            summary=summary or "No body text available.",
            key_points=key_points,
            extracted_tasks=extracted_tasks,
            extracted_deadlines=extracted_deadlines,
            suggested_action="Draft a concise reply and confirm timeline.",
            confidence_score=0.65,
        )
