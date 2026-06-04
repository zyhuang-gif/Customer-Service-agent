import json

import pytest
from jose import jwt

from app.auth import create_access_token, create_customer_access_token, hash_password
from app.clients.business_client import BusinessClient
from app.config import settings
from app.errors import BusinessUnavailable
from app.models import Conversation, User


def _events(response):
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def _customer_headers(customer_ref="C1001"):
    token, _ = create_customer_access_token(customer_ref)
    return {"Authorization": f"Bearer {token}"}


def _customer_orders(monkeypatch, orders, *, customer_ref="C1001"):
    customer = {"id": customer_ref, "phone": customer_ref}
    monkeypatch.setattr(
        BusinessClient,
        "get_customer_by_phone",
        lambda self, phone: customer if phone == customer_ref else None,
    )
    monkeypatch.setattr(
        BusinessClient,
        "list_orders",
        lambda self, customer_id: orders if customer_id == customer_ref else [],
    )


def test_login_and_pending_list(client, db_session):
    db_session.add(User(username="agent1", password_hash=hash_password("pw"), role="agent", display_name="一号"))
    db_session.commit()
    r = client.post("/auth/login", json={"username": "agent1", "password": "pw"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    r2 = client.get("/pending-actions", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json() == []


def test_login_wrong_password(client, db_session):
    db_session.add(User(username="agent1", password_hash=hash_password("pw"), role="agent"))
    db_session.commit()
    r = client.post("/auth/login", json={"username": "agent1", "password": "bad"})
    assert r.status_code == 401


def test_pending_list_requires_auth(client):
    r = client.get("/pending-actions")
    assert r.status_code == 401


def test_chat_sse_returns_response(client):
    r = client.post("/chat", json={"customer_ref": "13800000001", "message": "你好"})
    assert r.status_code == 200
    assert [event["type"] for event in _events(r)] == ["start", "response", "done"]


def test_customer_token_overrides_forged_body_customer_ref(client, db_session):
    response = client.post(
        "/chat",
        headers=_customer_headers("C1001"),
        json={"customer_ref": "C9999", "message": "你好"},
    )

    assert response.status_code == 200
    conversation_id = _events(response)[0]["conversation_id"]
    conversation = db_session.get(Conversation, conversation_id)
    assert conversation.customer_ref == "C1001"
    assert conversation.last_message_at is not None


def test_customer_cannot_continue_foreign_conversation(client, db_session):
    db_session.add(Conversation(id="foreign", customer_ref="C2002"))
    db_session.commit()

    response = client.post(
        "/chat",
        headers=_customer_headers("C1001"),
        json={"conversation_id": "foreign", "customer_ref": "C2002", "message": "继续"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在"
    assert client.service_calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer invalid-token"},
        {"Authorization": f"Bearer {create_access_token('agent', 'agent', 1)}"},
        {
            "Authorization": "Bearer "
            + jwt.encode(
                {
                    "sub": "C1001",
                    "role": "customer",
                    "customer_ref": "C1001",
                    "exp": 0,
                },
                settings.jwt_secret,
                algorithm="HS256",
            )
        },
    ],
)
def test_chat_rejects_invalid_non_customer_or_expired_bearer(client, headers):
    response = client.post(
        "/chat",
        headers=headers,
        json={"customer_ref": "anonymous", "message": "退货规则是什么"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "客户登录已失效"
    assert client.service_calls == []


@pytest.mark.parametrize(
    "message",
    ["我的订单到哪了", "查订单", "查询订单", "查物流", "物流进度", "退款进度", "退款状态"],
)
def test_anonymous_personal_request_requires_identity_without_calling_agent(client, message):
    response = client.post(
        "/chat",
        json={"customer_ref": "anonymous", "message": message},
    )

    events = _events(response)
    assert [event["type"] for event in events] == ["identity_required", "done"]
    assert "登录" in events[0]["content"]
    assert client.service_calls == []


@pytest.mark.parametrize("message", ["退货规则是什么", "退款多久到账", "满100元可以退货吗"])
def test_anonymous_policy_question_can_chat(client, message):
    response = client.post(
        "/chat",
        json={"customer_ref": "anonymous", "message": message},
    )

    assert [event["type"] for event in _events(response)] == ["start", "response", "done"]
    assert len(client.service_calls) == 1


def test_anonymous_product_model_question_can_chat(client):
    response = client.post(
        "/chat",
        json={"customer_ref": "anonymous", "message": "型号 iPhone15 支持七天无理由吗"},
    )

    assert [event["type"] for event in _events(response)] == ["start", "response", "done"]
    assert len(client.service_calls) == 1


def test_logged_in_customer_can_chat_about_owned_order(client, monkeypatch):
    _customer_orders(monkeypatch, [{"id": "20260531001"}])

    response = client.post(
        "/chat",
        headers=_customer_headers(),
        json={"customer_ref": "forged", "message": "查一下订单20260531001的物流"},
    )

    assert [event["type"] for event in _events(response)] == ["start", "response", "done"]
    assert len(client.service_calls) == 1


def test_logged_in_customer_order_ownership_is_case_insensitive(client, monkeypatch):
    _customer_orders(monkeypatch, [{"id": "O-ABC123"}])

    response = client.post(
        "/chat",
        headers=_customer_headers(),
        json={"customer_ref": "forged", "message": "查订单o-abc123的物流"},
    )

    assert [event["type"] for event in _events(response)] == ["start", "response", "done"]
    assert len(client.service_calls) == 1


@pytest.mark.parametrize(
    "message",
    [
        "查一下订单20260531002的物流",
        "对比订单20260531001和O-FOREIGN-9的退款状态",
    ],
)
def test_logged_in_customer_is_denied_when_any_order_is_foreign(
    client, monkeypatch, message
):
    _customer_orders(monkeypatch, [{"id": "20260531001"}])

    response = client.post(
        "/chat",
        headers=_customer_headers(),
        json={"customer_ref": "forged", "message": message},
    )

    events = _events(response)
    assert [event["type"] for event in events] == ["access_denied", "done"]
    assert "订单" not in events[0]["content"]
    assert client.service_calls == []


def test_logged_in_personal_request_without_order_id_can_chat(client):
    response = client.post(
        "/chat",
        headers=_customer_headers(),
        json={"customer_ref": "forged", "message": "查我的订单"},
    )

    assert [event["type"] for event in _events(response)] == ["start", "response", "done"]
    assert len(client.service_calls) == 1


def test_order_ownership_service_unavailable_is_safe_and_does_not_call_agent(
    client, monkeypatch
):
    monkeypatch.setattr(
        BusinessClient,
        "get_customer_by_phone",
        lambda self, phone: (_ for _ in ()).throw(BusinessUnavailable("secret detail")),
    )

    response = client.post(
        "/chat",
        headers=_customer_headers(),
        json={"customer_ref": "forged", "message": "查订单20260531001"},
    )

    events = _events(response)
    assert [event["type"] for event in events] == ["service_unavailable", "done"]
    assert "secret detail" not in response.text
    assert client.service_calls == []


@pytest.mark.parametrize(
    ("message", "expected_ids", "personal"),
    [
        ("订单20260531001和O-ABC123的物流进度", {"20260531001", "O-ABC123"}, True),
        ("查询订单号ABC123", {"ABC123"}, True),
        ("帮我看看87654321", {"87654321"}, True),
        ("帮我看看ABC-123", {"ABC-123"}, True),
        ("查订单o-abc123", {"O-ABC123"}, True),
        ("退货规则是什么", set(), False),
        ("退款多久到账", set(), False),
        ("这件商品299元", set(), False),
        ("型号 iPhone15 支持七天无理由吗", set(), False),
        ("手机号是13800000001", set(), False),
        ("今天是2026年6月4日", set(), False),
        ("普通中文内容", set(), False),
    ],
)
def test_customer_access_classifies_personal_requests_without_false_order_ids(
    message, expected_ids, personal
):
    from app.customer_access import classify_customer_request

    result = classify_customer_request(message)

    assert result.order_ids == expected_ids
    assert result.is_personal is personal
