from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.agent_action import AgentAction

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("/pending")
def pending_actions(user_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(AgentAction)
        .join(AgentAction.email)
        .filter(AgentAction.status == "pending")
        .filter(AgentAction.email.has(user_id=user_id))
        .order_by(AgentAction.created_at.desc())
        .all()
    )
    return {"items": rows}


@router.post("/{action_id}/approve")
def approve_action(action_id: int, db: Session = Depends(get_db)):
    row = db.query(AgentAction).filter(AgentAction.id == action_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")

    row.status = "approved"
    row.approved_by_user = True
    row.executed_at = datetime.utcnow()
    db.commit()

    return {"action_id": action_id, "status": row.status}


@router.post("/{action_id}/reject")
def reject_action(action_id: int, db: Session = Depends(get_db)):
    row = db.query(AgentAction).filter(AgentAction.id == action_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")

    row.status = "rejected"
    row.approved_by_user = False
    row.executed_at = datetime.utcnow()
    db.commit()

    return {"action_id": action_id, "status": row.status}
