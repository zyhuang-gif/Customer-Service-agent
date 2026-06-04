from datetime import datetime, timezone

import pytest

from app.conversation_activity import add_message
from app.models import Conversation, Message


def test_add_message_creates_message_and_updates_last_message_at(db_session):
    previous_activity = datetime(2020, 1, 1, tzinfo=timezone.utc)
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
    assert message in db_session.new
    assert message.conversation_id == "conv-1"
    assert message.role == "customer"
    assert message.content == "我的订单到哪了"
    assert message.meta == {"channel": "web"}
    assert conversation.last_message_at.replace(tzinfo=timezone.utc) > previous_activity


def test_add_message_raises_for_missing_conversation(db_session):
    with pytest.raises(ValueError, match="conversation not found"):
        add_message(
            db_session,
            conversation_id="missing",
            role="customer",
            content="你好",
        )
