from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Conversation, Message


def add_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    meta: dict | None = None,
) -> Message:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError(f"conversation not found: {conversation_id}")

    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        meta=meta or {},
    )
    db.add(message)
    conversation.last_message_at = datetime.now(timezone.utc)
    return message
