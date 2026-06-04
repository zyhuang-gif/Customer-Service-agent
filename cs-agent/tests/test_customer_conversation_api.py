from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.auth import create_access_token, create_customer_access_token
from app.config import settings
from app.models import Conversation, Message


def _customer_headers(customer_ref: str = "C1001") -> dict[str, str]:
    token, _ = create_customer_access_token(customer_ref)
    return {"Authorization": f"Bearer {token}"}


def _expired_customer_headers() -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": "C1001",
            "role": "customer",
            "customer_ref": "C1001",
            "exp": 0,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _add_conversation(
    db_session,
    conversation_id: str,
    customer_ref: str = "C1001",
    *,
    last_message_at: datetime,
    created_at: datetime | None = None,
    status: str = "ai_handling",
    summary: str = "",
):
    db_session.add(
        Conversation(
            id=conversation_id,
            customer_ref=customer_ref,
            status=status,
            summary=summary,
            created_at=created_at or last_message_at,
            last_message_at=last_message_at,
        )
    )


@pytest.mark.parametrize(
    "headers",
    [
        None,
        {"Authorization": "Bearer invalid-token"},
        _expired_customer_headers(),
        {"Authorization": f"Bearer {create_access_token('agent', 'agent', 1)}"},
    ],
)
def test_customer_conversation_endpoints_require_valid_customer_token(client, headers):
    response = client.get("/customer/conversations", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "客户登录已失效"


def test_customer_conversation_token_requires_customer_ref(client):
    token = jwt.encode(
        {"sub": "C1001", "role": "customer"},
        settings.jwt_secret,
        algorithm="HS256",
    )

    response = client.get(
        "/customer/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "客户登录已失效"


def test_list_customer_conversations_filters_owner_and_sorts_stably(client, db_session):
    older = datetime(2026, 6, 4, 8, 0)
    newer = datetime(2026, 6, 4, 10, 0)
    _add_conversation(
        db_session,
        "conv-a",
        last_message_at=newer,
        created_at=older,
        status="resolved",
        summary="已解决",
    )
    _add_conversation(db_session, "conv-b", last_message_at=newer)
    _add_conversation(db_session, "conv-old", last_message_at=older)
    _add_conversation(db_session, "conv-other", "C2002", last_message_at=newer)
    db_session.commit()

    response = client.get("/customer/conversations", headers=_customer_headers())

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == ["conv-b", "conv-a", "conv-old"]
    assert body[1] == {
        "id": "conv-a",
        "status": "resolved",
        "summary": "已解决",
        "created_at": older.isoformat(),
        "last_message_at": newer.isoformat(),
    }


def test_recent_customer_conversation_returns_null_without_history(client):
    response = client.get("/customer/conversations/recent", headers=_customer_headers())

    assert response.status_code == 200
    assert response.json() == {"conversation": None, "should_resume": False}


@pytest.mark.parametrize(
    ("age", "should_resume"),
    [
        (timedelta(minutes=30), True),
        (timedelta(hours=2), True),
        (timedelta(hours=2, microseconds=1), False),
    ],
)
def test_recent_customer_conversation_uses_inclusive_two_hour_window(
    client, db_session, monkeypatch, age, should_resume
):
    now = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
    last_message_at = (now - age).replace(tzinfo=None)
    _add_conversation(db_session, "conv-recent", last_message_at=last_message_at)
    _add_conversation(
        db_session,
        "conv-other",
        "C2002",
        last_message_at=now.replace(tzinfo=None),
    )
    db_session.commit()

    import app.routers.customer_conversation_router as customer_router

    monkeypatch.setattr(customer_router, "utc_now", lambda: now)
    response = client.get("/customer/conversations/recent", headers=_customer_headers())

    assert response.status_code == 200
    assert response.json() == {
        "conversation": {
            "id": "conv-recent",
            "status": "ai_handling",
            "summary": "",
            "created_at": last_message_at.isoformat(),
            "last_message_at": last_message_at.isoformat(),
        },
        "should_resume": should_resume,
    }


def test_customer_messages_return_owned_messages_in_stable_order_with_meta(
    client, db_session
):
    created_at = datetime(2026, 6, 4, 9, 0)
    _add_conversation(db_session, "conv-owned", last_message_at=created_at)
    first = Message(
        conversation_id="conv-owned",
        role="customer",
        content="订单在哪里？",
        meta={"source": "web"},
        created_at=created_at,
    )
    second = Message(
        conversation_id="conv-owned",
        role="ai",
        content="正在查询。",
        meta={"tool": "order_lookup"},
        created_at=created_at,
    )
    db_session.add_all([first, second])
    db_session.commit()

    response = client.get(
        "/customer/conversations/conv-owned/messages",
        headers=_customer_headers(),
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": first.id,
            "role": "customer",
            "content": "订单在哪里？",
            "meta": {"source": "web"},
            "created_at": created_at.isoformat(),
        },
        {
            "id": second.id,
            "role": "ai",
            "content": "正在查询。",
            "meta": {"tool": "order_lookup"},
            "created_at": created_at.isoformat(),
        },
    ]


@pytest.mark.parametrize("conversation_id", ["conv-other", "missing"])
def test_customer_messages_hide_foreign_and_missing_conversations(
    client, db_session, conversation_id
):
    _add_conversation(
        db_session,
        "conv-other",
        "C2002",
        last_message_at=datetime(2026, 6, 4, 9, 0),
    )
    db_session.commit()

    response = client.get(
        f"/customer/conversations/{conversation_id}/messages",
        headers=_customer_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在"
