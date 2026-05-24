from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import agent_service, gmail_service
from app.models.agent_action import AgentAction
from app.models.email import Email
from app.models.email_analysis import EmailAnalysis
from app.models.user import User
from app.schemas.email_schema import EmailAnalysisResponse, EmailListResponse, EmailSyncRequest

router = APIRouter(prefix="/emails", tags=["emails"])


@router.post("/sync")
def sync_emails(payload: EmailSyncRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    incoming = gmail_service.fetch_emails_since(user_id=user.id, since=user.last_checked_at)
    created = 0

    for item in incoming:
        exists = db.query(Email).filter(Email.gmail_message_id == item["gmail_message_id"]).first()
        if exists:
            continue

        db_email = Email(**item)
        db.add(db_email)
        created += 1

    user.last_checked_at = datetime.utcnow()
    db.commit()
    return {"synced": created, "last_checked_at": user.last_checked_at}


@router.get("", response_model=EmailListResponse)
def list_emails(user_id: int, db: Session = Depends(get_db)):
    rows = db.query(Email).filter(Email.user_id == user_id).order_by(Email.received_at.desc()).all()
    return EmailListResponse(items=rows)


@router.get("/{email_id}")
def get_email(email_id: int, db: Session = Depends(get_db)):
    row = db.query(Email).filter(Email.id == email_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")
    return row


@router.post("/{email_id}/analyse", response_model=EmailAnalysisResponse)
def analyse_email(email_id: int, db: Session = Depends(get_db)):
    row = db.query(Email).filter(Email.id == email_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")

    analysis_output = agent_service.analyse_email(subject=row.subject, body_text=row.body_text)

    existing = db.query(EmailAnalysis).filter(EmailAnalysis.email_id == email_id).first()
    if existing:
        existing.category = analysis_output.category
        existing.priority_score = analysis_output.priority_score
        existing.summary = analysis_output.summary
        existing.key_points = analysis_output.key_points
        existing.extracted_tasks = analysis_output.extracted_tasks
        existing.extracted_deadlines = analysis_output.extracted_deadlines
        existing.suggested_action = analysis_output.suggested_action
        existing.confidence_score = analysis_output.confidence_score
    else:
        existing = EmailAnalysis(
            email_id=email_id,
            category=analysis_output.category,
            priority_score=analysis_output.priority_score,
            summary=analysis_output.summary,
            key_points=analysis_output.key_points,
            extracted_tasks=analysis_output.extracted_tasks,
            extracted_deadlines=analysis_output.extracted_deadlines,
            suggested_action=analysis_output.suggested_action,
            confidence_score=analysis_output.confidence_score,
        )
        db.add(existing)

    # Audit log entry for explainable agent suggestion.
    db.add(
        AgentAction(
            email_id=email_id,
            action_type="reply_suggestion",
            status="pending",
            suggested_payload={"suggested_action": analysis_output.suggested_action},
            requires_approval=True,
        )
    )

    db.commit()
    return EmailAnalysisResponse(email_id=email_id, analysis=analysis_output)
