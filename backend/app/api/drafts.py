from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import draft_service
from app.models.draft_reply import DraftReply
from app.models.email import Email
from app.models.user import User
from app.models.user_rule import UserRule

router = APIRouter(prefix="/drafts", tags=["drafts"])


class DraftGenerateRequest(BaseModel):
    email_id: UUID
    tone: str = "professional"


@router.post("/generate")
def generate_draft(payload: DraftGenerateRequest, db: Session = Depends(get_db)):
    email_row = db.query(Email).filter(Email.id == payload.email_id).first()
    if not email_row:
        raise HTTPException(status_code=404, detail="Email not found")

    rules = (
        db.query(UserRule.rule_text)
        .filter(UserRule.user_id == email_row.user_id)
        .filter(UserRule.is_active.is_(True))
        .order_by(UserRule.created_at.desc())
        .all()
    )
    rule_texts = [row[0] for row in rules]

    output = draft_service.generate_draft(
        subject=email_row.subject,
        body_text=email_row.body_text,
        tone=payload.tone,
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

    return {"draft_id": draft.id, "output": output.model_dump()}


@router.post("/{draft_id}/create-in-gmail")
def create_in_gmail(draft_id: UUID, db: Session = Depends(get_db)):
    draft = db.query(DraftReply).filter(DraftReply.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    email_row = db.query(Email).filter(Email.id == draft.email_id).first()
    if not email_row:
        raise HTTPException(status_code=404, detail="Related email not found")

    user = db.query(User).filter(User.id == email_row.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Related user not found")

    gmail_draft_id = draft_service.create_in_gmail(
        user=user,
        db=db,
        subject=f"Re: {email_row.subject or 'Email'}",
        body=draft.draft_body,
    )
    draft.gmail_draft_id = gmail_draft_id
    draft.status = "created_in_gmail"
    db.commit()

    return {
        "draft_id": draft.id,
        "gmail_draft_id": gmail_draft_id,
        "note": "Draft created in Gmail. Sending must be done manually by user.",
        "created_at": datetime.utcnow(),
    }
