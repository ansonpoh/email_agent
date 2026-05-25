from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.agent_action import AgentAction
from app.models.draft_reply import DraftReply
from app.models.email import Email
from app.models.user import User
from app.models.user_rule import UserRule
from app.services.draft_service import DraftService


class ActionExecutionService:
    def __init__(self, draft_service: DraftService):
        self.draft_service = draft_service

    def approve_action(self, db: Session, action: AgentAction) -> dict:
        if action.status in {"approved", "rejected"} and action.executed_at:
            return action.execution_payload or {"status": action.status}

        action.status = "approved"
        action.approved_by_user = True
        action.executed_at = datetime.utcnow()

        payload: dict = {"action_type": action.action_type, "status": "approved"}
        try:
            if action.action_type == "reply_suggestion":
                payload = self._execute_reply_suggestion(db=db, action=action)
            action.execution_payload = payload
            action.execution_error = None
        except Exception as exc:
            action.execution_error = str(exc)
            action.execution_payload = {"action_type": action.action_type, "status": "approved_execution_failed"}

        db.add(action)
        db.commit()
        db.refresh(action)
        return action.execution_payload

    def reject_action(self, db: Session, action: AgentAction) -> dict:
        action.status = "rejected"
        action.approved_by_user = False
        action.executed_at = datetime.utcnow()
        action.execution_payload = {"action_type": action.action_type, "status": "rejected"}
        action.execution_error = None
        db.add(action)
        db.commit()
        db.refresh(action)
        return action.execution_payload

    def _execute_reply_suggestion(self, db: Session, action: AgentAction) -> dict:
        email_row = db.query(Email).filter(Email.id == action.email_id).first()
        if not email_row:
            raise HTTPException(status_code=404, detail="Related email not found")

        user = db.query(User).filter(User.id == email_row.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Related user not found")

        rules = (
            db.query(UserRule.rule_text)
            .filter(UserRule.user_id == user.id)
            .filter(UserRule.is_active.is_(True))
            .order_by(UserRule.created_at.desc())
            .all()
        )
        rule_texts = [row[0] for row in rules]
        tone = str(action.suggested_payload.get("tone") or "professional")

        output = self.draft_service.generate_draft(
            subject=email_row.subject,
            body_text=email_row.body_text,
            tone=tone,
            user_rules=rule_texts,
        )

        draft = DraftReply(
            email_id=email_row.id,
            draft_body=output.body,
            tone=output.tone,
            status="generated",
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)

        gmail_draft_id = self.draft_service.create_in_gmail(
            user=user,
            db=db,
            subject=output.subject,
            body=output.body,
        )
        draft.gmail_draft_id = gmail_draft_id
        draft.status = "created_in_gmail"
        db.add(draft)
        db.commit()
        db.refresh(draft)

        return {
            "action_type": action.action_type,
            "status": "approved_executed",
            "email_id": str(email_row.id),
            "draft_id": str(draft.id),
            "gmail_draft_id": gmail_draft_id,
        }
