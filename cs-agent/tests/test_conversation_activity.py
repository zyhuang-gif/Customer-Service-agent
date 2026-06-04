from datetime import datetime, timedelta, timezone

import pytest

from app.conversation_activity import add_message
from app.models import Conversation, Message


def test_add_message_creates_message_and_updates_last_message_at(db_session):
    previous_activity = datetime(2020, 1, 1)
    conversation = Conversation(
        id="conv-1",
        customer_ref="C1",
        last_message_at=previous_activity,
    )
    db_session.add(conversation)
    db_session.commit()

    message = add_message(
        db_session,
        conversation_id="conv-1",
        role="customer",
        content="我的订单到哪了",
        meta={"channel": "web"},
    )

    assert isinstance(message, Message)
    assert message.conversation_id == "conv-1"
    assert message.role == "customer"
    assert message.content == "我的订单到哪了"
    assert message.meta == {"channel": "web"}

    db_session.commit()
    db_session.expire_all()

    reloaded_message = db_session.get(Message, message.id)
    reloaded_conversation = db_session.get(Conversation, "conv-1")
    assert reloaded_message.meta == {"channel": "web"}
    assert reloaded_conversation.last_message_at > previous_activity
    assert reloaded_conversation.last_message_at.tzinfo is None


def test_add_message_does_not_move_last_message_at_backwards(db_session):
    future_activity = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    db_session.add(Conversation(
        id="conv-1",
        customer_ref="C1",
        last_message_at=future_activity,
    ))
    db_session.commit()

    add_message(db_session, "conv-1", "customer", "你好")
    db_session.commit()
    db_session.expire_all()

    reloaded_conversation = db_session.get(Conversation, "conv-1")
    assert reloaded_conversation.last_message_at == future_activity
    assert reloaded_conversation.last_message_at.tzinfo is None


def test_add_message_raises_for_missing_conversation(db_session):
    with pytest.raises(ValueError, match="conversation not found"):
        add_message(
            db_session,
            conversation_id="missing",
            role="customer",
            content="你好",
        )
