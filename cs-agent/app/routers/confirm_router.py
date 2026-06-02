from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.deps import build_service
from app.db import get_db
from app.models import PendingAction
from app.routers.auth_router import current_user
from app.schemas_api import ConfirmIn

router = APIRouter(tags=["confirm"])


@router.get("/pending-actions")
def list_pending(db: Session = Depends(get_db), user=Depends(current_user)):
    rows = db.query(PendingAction).filter_by(status="pending").all()
    return [{"id": r.id, "conversation_id": r.conversation_id, "tool_name": r.tool_name,
             "params": r.params, "created_at": r.created_at.isoformat()} for r in rows]


@router.post("/pending-actions/{action_id}/review")
def review(action_id: int, body: ConfirmIn, db: Session = Depends(get_db), user=Depends(current_user)):
    svc = build_service(db)
    return svc.resume_action(action_id, approved=body.approved, reviewer_id=user.id)
