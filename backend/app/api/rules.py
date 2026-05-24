from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.user_rule import UserRule

router = APIRouter(prefix="/rules", tags=["rules"])


class RuleCreateRequest(BaseModel):
    user_id: int
    rule_text: str


@router.get("")
def list_rules(user_id: int, db: Session = Depends(get_db)):
    rows = db.query(UserRule).filter(UserRule.user_id == user_id).order_by(UserRule.created_at.desc()).all()
    return {"items": rows}


@router.post("")
def create_rule(payload: RuleCreateRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    rule = UserRule(user_id=payload.user_id, rule_text=payload.rule_text, is_active=True)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    row = db.query(UserRule).filter(UserRule.id == rule_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")

    db.delete(row)
    db.commit()
    return {"deleted": True, "rule_id": rule_id}
