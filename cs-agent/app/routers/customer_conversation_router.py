from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import decode_token
from app.db import get_db
from app.models import Conversation, Message

router = APIRouter(prefix="/customer/conversations", tags=["customer-conversations"])
_bearer = HTTPBearer(auto_error=False)
_AUTH_ERROR = "客户登录已失效"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def current_customer(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    payload = decode_token(cred.credentials) if cred else None
    customer_ref = payload.get("customer_ref") if payload else None
    if not payload or payload.get("role") != "customer" or not customer_ref:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)
    return customer_ref


def _conversation_out(conversation: Conversation) -> dict:
    return {
        "id": conversation.id,
        "status": conversation.status,
        "summary": conversation.summary,
        "created_at": conversation.created_at.isoformat(),
        "last_message_at": conversation.last_message_at.isoformat(),
    }


@router.get("")
def list_customer_conversations(
    db: Session = Depends(get_db),
    customer_ref: str = Depends(current_customer),
):
    rows = (
        db.query(Conversation)
        .filter(Conversation.customer_ref == customer_ref)
        .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
        .all()
    )
    return [_conversation_out(conversation) for conversation in rows]


@router.get("/recent")
def get_recent_customer_conversation(
    db: Session = Depends(get_db),
    customer_ref: str = Depends(current_customer),
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.customer_ref == customer_ref)
        .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
        .first()
    )
    if conversation is None:
        return {"conversation": None, "should_resume": False}

    last_message_at = conversation.last_message_at
    if last_message_at.tzinfo is None:
        last_message_at = last_message_at.replace(tzinfo=timezone.utc)
    should_resume = utc_now() - last_message_at <= timedelta(hours=2)
    return {
        "conversation": _conversation_out(conversation),
        "should_resume": should_resume,
    }


@router.get("/{conversation_id}/messages")
def get_customer_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    customer_ref: str = Depends(current_customer),
):
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.customer_ref == customer_ref,
        )
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
        .all()
    )
    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "meta": message.meta,
            "created_at": message.created_at.isoformat(),
        }
        for message in rows
    ]
