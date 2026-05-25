from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import pipeline_service, telegram_orchestration_service
from app.models.email import Email
from app.models.user import User
from app.schemas.email_schema import EmailAnalysisOutput, EmailAnalysisResponse, EmailListResponse, EmailSyncRequest

router = APIRouter(prefix="/emails", tags=["emails"])


@router.post("/sync")
def sync_emails(payload: EmailSyncRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = pipeline_service.sync_user_emails(db=db, user=user)
    return {"synced": result["synced"], "fetched": result["fetched"], "last_checked_at": result["last_checked_at"]}


@router.get("", response_model=EmailListResponse)
def list_emails(user_id: UUID, db: Session = Depends(get_db)):
    rows = db.query(Email).filter(Email.user_id == user_id).order_by(Email.received_at.desc()).all()
    return EmailListResponse(items=rows)


@router.get("/{email_id}")
def get_email(email_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Email).filter(Email.id == email_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")
    return row


@router.post("/{email_id}/analyse", response_model=EmailAnalysisResponse)
def analyse_email(email_id: UUID, db: Session = Depends(get_db)):
    row = db.query(Email).filter(Email.id == email_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    analysis, _action = telegram_orchestration_service.analyze_existing_email(db=db, user=user, email_row=row)
    analysis_output = EmailAnalysisOutput(
        category=analysis.category,
        priority_score=analysis.priority_score,
        summary=analysis.summary,
        key_points=analysis.key_points,
        extracted_tasks=analysis.extracted_tasks,
        extracted_deadlines=analysis.extracted_deadlines,
        suggested_action=analysis.suggested_action,
        confidence_score=analysis.confidence_score,
    )
    return EmailAnalysisResponse(email_id=email_id, analysis=analysis_output)
