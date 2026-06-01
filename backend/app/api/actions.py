from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import action_execution_service
from app.models.agent_action import AgentAction

router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/{action_id}/approve")
def approve_action(action_id: UUID, execute: bool = True, db: Session = Depends(get_db)):
    row = db.query(AgentAction).filter(AgentAction.id == action_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")

    if execute:
        payload = action_execution_service.approve_action(db=db, action=row)
    else:
        row.status = "approved"
        row.approved_by_user = True
        row.executed_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        payload = {"status": row.status}

    return {"action_id": action_id, "status": row.status, "execution": payload}


@router.post("/{action_id}/reject")
def reject_action(action_id: UUID, db: Session = Depends(get_db)):
    row = db.query(AgentAction).filter(AgentAction.id == action_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Action not found")

    payload = action_execution_service.reject_action(db=db, action=row)

    return {"action_id": action_id, "status": row.status, "execution": payload}
