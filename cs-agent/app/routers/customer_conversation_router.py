from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import decode_token
from app.config import settings
from app.db import get_db
from app.models import Conversation, Message

router = APIRouter(prefix="/customer/conversations", tags=["customer-conversations"])
_bearer = HTTPBearer(auto_error=False)
_AUTH_ERROR = "客户登录已失效"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
        "created_at": utc_iso(conversation.created_at),
        "last_message_at": utc_iso(conversation.last_message_at),
    }


@router.get("")
def list_customer_conversations(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    customer_ref: str = Depends(current_customer),
):
    rows = (
        db.query(Conversation)
        .filter(Conversation.customer_ref == customer_ref)
        .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
        .offset(offset)
        .limit(limit)
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
    should_resume = utc_now() - last_message_at <= timedelta(
        hours=settings.customer_resume_hours
    )
    return {
        "conversation": _conversation_out(conversation),
        "should_resume": should_resume,
    }


@router.get("/{conversation_id}/messages")
def get_customer_messages(
    conversation_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
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
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "meta": message.meta,
            "created_at": utc_iso(message.created_at),
        }
        for message in rows
    ]
