import json

import pytest
from jose import jwt
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_graph
from app.agent.service import ConversationService
from app.auth import create_access_token, create_customer_access_token, hash_password
from app.clients.business_client import BusinessClient
from app.config import settings
from app.errors import BusinessUnavailable
from app.models import Conversation, PendingAction, User
from app.tools.registry import ToolRegistry


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
        "get_customer",
        lambda self, customer_id: customer if customer_id == customer_ref else None,
    )
    order_by_id = {str(order["id"]).upper(): order for order in orders}
    for order in orders:
        order.setdefault("customer_id", customer_ref)
    monkeypatch.setattr(
        BusinessClient,
        "get_order",
        lambda self, order_id: order_by_id.get(str(order_id).upper()),
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


def test_anonymous_body_customer_ref_cannot_pollute_customer_history(client, db_session):
    response = client.post("/chat", json={"customer_ref": "C1001", "message": "你好"})

    conversation_id = _events(response)[0]["conversation_id"]
    conversation = db_session.get(Conversation, conversation_id)
    history = client.get("/customer/conversations", headers=_customer_headers("C1001"))

    assert conversation.customer_ref.startswith("anon-")
    assert conversation.customer_ref != "C1001"
    assert history.json() == []


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


def test_anonymous_cannot_continue_existing_conversation(client, db_session):
    db_session.add(Conversation(id="existing", customer_ref="anonymous"))
    db_session.commit()

    response = client.post(
        "/chat",
        json={"conversation_id": "existing", "customer_ref": "anonymous", "message": "继续"},
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
    [
        "我的订单到哪了",
        "查订单",
        "查询订单",
        "查物流",
        "物流进度",
        "退款进度",
        "退款状态",
        "查一下 O-FOREIGN-9 的物流",
        "我要退款 ABC123 100元",
        "改地址",
        "发券",
    ],
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


@pytest.mark.parametrize(
    "message",
    [
        "退货规则是什么",
        "退款多久到账",
        "满100元可以退货吗",
        "型号 ABC-123 支持七天无理由吗",
        "20260604购买的商品能退货吗",
    ],
)
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


def test_logged_in_customer_is_denied_for_contextual_foreign_order(client, monkeypatch):
    _customer_orders(monkeypatch, [{"id": "OWNED-ORDER"}])

    response = client.post(
        "/chat",
        headers=_customer_headers(),
        json={"customer_ref": "forged", "message": "查询订单 FOREIGN-ORDER"},
    )

    assert [event["type"] for event in _events(response)] == ["access_denied", "done"]
    assert client.service_calls == []


@pytest.mark.parametrize(
    "message",
    [
        "查一下订单20260531002的物流",
        "对比订单20260531001和O-FOREIGN-9的退款状态",
        "对比订单号 20260531001、O-FOREIGN-9",
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
    "customer,order",
    [
        ({}, {"id": "O1", "customer_id": "C1001"}),
        ({"id": "C2002"}, {"id": "O1", "customer_id": "C2002"}),
        ({"id": "C1001"}, []),
        ({"id": "C1001"}, {"customer_id": "C1001"}),
        ({"id": "C1001"}, {"id": "O1"}),
    ],
)
def test_malformed_customer_or_order_response_is_safe(
    client, monkeypatch, customer, order
):
    monkeypatch.setattr(BusinessClient, "get_customer", lambda self, customer_id: customer)
    monkeypatch.setattr(BusinessClient, "get_customer_by_phone", lambda self, phone: customer)
    monkeypatch.setattr(BusinessClient, "get_order", lambda self, order_id: order)

    response = client.post(
        "/chat",
        headers=_customer_headers(),
        json={"customer_ref": "forged", "message": "查订单 O1"},
    )

    assert [event["type"] for event in _events(response)] == ["service_unavailable", "done"]
    assert client.service_calls == []


def test_explicit_order_validation_uses_get_order_not_full_order_list(client, monkeypatch):
    calls = []
    monkeypatch.setattr(
        BusinessClient,
        "get_customer",
        lambda self, customer_id: {"id": "C1001"},
    )
    monkeypatch.setattr(
        BusinessClient,
        "get_customer_by_phone",
        lambda self, phone: {"id": "C1001"},
    )
    monkeypatch.setattr(
        BusinessClient,
        "get_order",
        lambda self, order_id: calls.append(("get_order", order_id))
        or {"id": order_id, "customer_id": "C1001"},
    )
    monkeypatch.setattr(
        BusinessClient,
        "list_orders",
        lambda self, customer_id: (_ for _ in ()).throw(
            AssertionError("explicit order validation must not list all orders")
        ),
    )

    response = client.post(
        "/chat",
        headers=_customer_headers(),
        json={"customer_ref": "forged", "message": "查订单 O1 和 O2"},
    )

    assert [event["type"] for event in _events(response)] == ["start", "response", "done"]
    assert sorted(calls) == [("get_order", "O1"), ("get_order", "O2")]


class _ToolCallingLLM:
    def __init__(self, tool_name, params):
        self.tool_name = tool_name
        self.params = params
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": self.tool_name,
                        "args": self.params,
                        "id": "tool-1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="无法访问该信息。")


class _BoundaryBusiness:
    def __init__(self):
        self.personal_calls = []

    def get_order(self, order_id):
        return {"id": order_id, "customer_id": "C2002"}

    def get_logistics(self, order_id):
        self.personal_calls.append(("get_logistics", order_id))
        return {"order_id": order_id, "status": "运输中"}

    def apply_refund(self, order_id, amount, reason=""):
        self.personal_calls.append(("apply_refund", order_id))
        return {"id": "RF1"}


class _EmptyRetriever:
    def retrieve(self, query):
        return []


@pytest.mark.parametrize(
    ("identity_verified", "customer_ref", "tool_name", "params", "expected_status"),
    [
        (False, None, "get_order", {"order_id": "O-OWNED"}, "identity_required"),
        (
            False,
            None,
            "apply_refund",
            {"order_id": "O-OWNED", "amount": 100.0, "reason": "test"},
            "identity_required",
        ),
        (
            True,
            "C1001",
            "get_logistics",
            {"order_id": "O-FOREIGN"},
            "access_denied",
        ),
    ],
)
def test_real_service_tool_boundary_denies_unscoped_personal_calls(
    db_session, identity_verified, customer_ref, tool_name, params, expected_status
):
    business = _BoundaryBusiness()
    registry = ToolRegistry(business=business, retriever=_EmptyRetriever())
    graph = build_graph(
        llm=_ToolCallingLLM(tool_name, params),
        registry=registry,
        checkpointer=MemorySaver(),
    )
    db_session.add(
        Conversation(id=f"boundary-{tool_name}", customer_ref=customer_ref or "anonymous")
    )
    db_session.commit()
    service = ConversationService(
        db=db_session,
        graph=graph,
        business=business,
        registry=registry,
    )

    out = service.start_turn(
        f"boundary-{tool_name}",
        "请处理",
        verified_customer_id=customer_ref if identity_verified else None,
    )

    assert out["status"] == expected_status
    assert business.personal_calls == []
    assert (
        db_session.query(PendingAction)
        .filter_by(conversation_id=f"boundary-{tool_name}")
        .count()
        == 0
    )


@pytest.mark.parametrize(
    ("customer_ref", "tool_name", "params", "expected_event"),
    [
        (None, "get_order", {"order_id": "O-OWNED"}, "identity_required"),
        ("C1001", "get_order", {"order_id": "O-FOREIGN"}, "access_denied"),
    ],
)
def test_chat_preserves_service_access_status_as_sse_event(
    client, db_session, monkeypatch, customer_ref, tool_name, params, expected_event
):
    business = _BoundaryBusiness()
    registry = ToolRegistry(business=business, retriever=_EmptyRetriever())
    service = ConversationService(
        db=db_session,
        graph=build_graph(
            llm=_ToolCallingLLM(tool_name, params),
            registry=registry,
            checkpointer=MemorySaver(),
        ),
        business=business,
        registry=registry,
    )
    import app.routers.chat_router as chat_router

    monkeypatch.setattr(chat_router, "build_service", lambda db: service)
    headers = _customer_headers(customer_ref) if customer_ref else None

    response = client.post(
        "/chat",
        headers=headers,
        json={"customer_ref": "forged", "message": "普通问题"},
    )

    assert [event["type"] for event in _events(response)] == [
        "start",
        expected_event,
        "done",
    ]


def test_chat_maps_service_unavailable_status_to_sse_event(client, monkeypatch):
    class UnavailableService:
        def start_turn(self, *args, **kwargs):
            return {"status": "service_unavailable", "message": "暂时不可用"}

    import app.routers.chat_router as chat_router

    monkeypatch.setattr(chat_router, "build_service", lambda db: UnavailableService())

    response = client.post("/chat", json={"customer_ref": "forged", "message": "普通问题"})

    assert [event["type"] for event in _events(response)] == [
        "start",
        "service_unavailable",
        "done",
    ]


def test_resume_action_rechecks_customer_scope_before_business_write(db_session):
    business = _BoundaryBusiness()
    registry = ToolRegistry(business=business, retriever=_EmptyRetriever())
    db_session.add(Conversation(id="resume-boundary", customer_ref="C1001"))
    db_session.add(
        PendingAction(
            conversation_id="resume-boundary",
            customer_ref="C1001",
            tool_name="apply_refund",
            params={"order_id": "O-FOREIGN", "amount": 100.0},
            status="pending",
        )
    )
    db_session.commit()
    pending = db_session.query(PendingAction).filter_by(conversation_id="resume-boundary").one()
    service = ConversationService(
        db=db_session,
        graph=None,
        business=business,
        registry=registry,
    )

    out = service.resume_action(pending.id, approved=True, reviewer_id=1)

    assert out["pending_status"] == "failed"
    assert business.personal_calls == []


def test_tool_authorization_converts_unexpected_order_check_error():
    class BrokenBusiness:
        def get_order(self, order_id):
            raise ValueError("malformed upstream payload")

    registry = ToolRegistry(business=BrokenBusiness(), retriever=_EmptyRetriever())

    out = registry.call("get_order", {"order_id": "O1"}, customer_ref="C1001")

    assert out["error"] is True
    assert out["kind"] == "internal"


@pytest.mark.parametrize(
    ("tool_name", "params"),
    [
        ("get_order", {}),
        ("get_logistics", {"order_id": ""}),
        ("get_refund_status", {"order_id": None}),
        ("apply_refund", {"amount": 10.0}),
        ("change_address", {"new_address": "上海"}),
        ("get_customer", {}),
        ("list_customer_tickets", {"customer_id": ""}),
        ("issue_coupon", {"value": 10.0}),
        ("create_ticket", {"category": "物流", "summary": "催办"}),
        ("update_ticket", {"ticket_id": "TK1"}),
    ],
)
def test_tool_authorization_rejects_missing_scope_parameters(tool_name, params):
    registry = ToolRegistry(business=_BoundaryBusiness(), retriever=_EmptyRetriever())

    out = registry.call(tool_name, params, customer_ref="C1001")

    assert out["error"] is True
    assert out["kind"] == "access_denied"


@pytest.mark.parametrize(
    ("message", "expected_ids", "personal"),
    [
        ("订单20260531001和O-ABC123的物流进度", {"20260531001", "O-ABC123"}, True),
        ("订单号 A、B 和 C", {"A", "B", "C"}, True),
        ("订单号是 ABC123", {"ABC123"}, True),
        ("订单号为ABC123", {"ABC123"}, True),
        ("订单#ABC123", {"ABC123"}, True),
        ("查询订单号ABC123", {"ABC123"}, True),
        ("查询订单 FOREIGN-ORDER", {"FOREIGN-ORDER"}, True),
        ("查一下 O-FOREIGN-9 的物流", {"O-FOREIGN-9"}, True),
        ("我要退款 ABC123 100元", {"ABC123"}, True),
        ("改地址", set(), True),
        ("发券", set(), True),
        ("订单编号：LETTERS", {"LETTERS"}, True),
        ("单号: 87654321", {"87654321"}, True),
        ("查订单o-abc123", {"O-ABC123"}, True),
        ("退货规则是什么", set(), False),
        ("退款多久到账", set(), False),
        ("这件商品299元", set(), False),
        ("帮我看看87654321", set(), False),
        ("帮我看看ABC-123", set(), False),
        ("20260604购买的商品能退货吗", set(), False),
        ("型号 ABC-123 支持七天无理由吗", set(), False),
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
