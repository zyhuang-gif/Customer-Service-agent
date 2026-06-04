from datetime import datetime, timezone

from sqlalchemy import update
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute(
        update(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.last_message_at < now,
        )
        .values(last_message_at=now)
        .execution_options(synchronize_session=False)
    )
    db.refresh(conversation, attribute_names=["last_message_at"])
    return message
