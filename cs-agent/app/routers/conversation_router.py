from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Conversation, Message
from app.routers.auth_router import current_user

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
def list_conversations(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(current_user),
):
    q = db.query(Conversation)
    if status:
        q = q.filter(Conversation.status == status)
    rows = q.order_by(Conversation.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "customer_ref": c.customer_ref,
            "status": c.status,
            "assigned_agent_id": c.assigned_agent_id,
            "summary": c.summary,
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
    ]


@router.get("/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    user=Depends(current_user),
):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = (
        db.query(Message)
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at, Message.id)
        .all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "meta": m.meta,
            "created_at": m.created_at.isoformat(),
        }
        for m in rows
    ]
