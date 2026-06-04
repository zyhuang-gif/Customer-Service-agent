from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.conversation_activity import add_message
from app.db import get_db
from app.models import Conversation, Message
from app.routers.auth_router import current_user
from app.schemas_api import AgentReplyIn

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


@router.post("/conversations/{conversation_id}/messages")
def agent_reply(
    conversation_id: str,
    body: AgentReplyIn,
    db: Session = Depends(get_db),
    user=Depends(current_user),
):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    if conv.status != "human_handling":
        raise HTTPException(status_code=409, detail="只有人工处理中的会话可以由坐席回复")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="回复内容不能为空")

    conv.assigned_agent_id = user.id
    msg = add_message(
        db,
        conversation_id,
        "agent",
        content,
        {"agent_id": user.id, "agent_name": user.display_name or user.username},
    )
    db.commit()
    db.refresh(msg)
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "meta": msg.meta,
        "created_at": msg.created_at.isoformat(),
    }
