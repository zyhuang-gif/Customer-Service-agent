from datetime import datetime

import pytest
from jose import jwt

from app.auth import create_access_token, create_customer_access_token, hash_password
from app.clients.business_client import BusinessClient
from app.config import settings
from app.customer_auth_rate_limit import FixedWindowRateLimiter, customer_auth_limiter
from app.errors import BusinessUnavailable
from app.models import User
from app.routers.customer_auth_router import _mask_phone


@pytest.fixture(autouse=True)
def reset_customer_auth_limiter():
    customer_auth_limiter.reset()
    yield
    customer_auth_limiter.reset()


def _patch_customer(monkeypatch, customer=None, orders=None):
    def fake_get_customer_by_phone(self, phone):
        assert phone == "13800000001"
        return customer

    def fake_list_orders(self, customer_id):
        assert customer_id == customer["id"]
        return orders

    monkeypatch.setattr(BusinessClient, "get_customer_by_phone", fake_get_customer_by_phone)
    monkeypatch.setattr(BusinessClient, "list_orders", fake_list_orders)


def test_verify_customer_with_latest_order_trims_input_and_returns_token(client, monkeypatch):
    customer = {"id": "C1001", "phone": "13800000001"}
    orders = [
        {"id": "O3", "created_at": "2026-06-01T12:00:00"},
        {"id": "O2", "created_at": "2026-06-01T12:00:00"},
        {"id": "O1", "created_at": "2026-05-01T12:00:00"},
    ]
    _patch_customer(monkeypatch, customer=customer, orders=orders)

    response = client.post(
        "/customer-auth/verify",
        json={"phone": " 13800000001 ", "recent_order_id": " O3 "},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["masked_phone"] == "138****0001"
    assert datetime.fromisoformat(body["expires_at"])
    assert body["access_token"]


def test_verify_customer_rejects_order_that_is_not_first(client, monkeypatch):
    _patch_customer(
        monkeypatch,
        customer={"id": "C1001", "phone": "13800000001"},
        orders=[
            {"id": "O2", "created_at": "2026-06-01T12:00:00"},
            {"id": "O1", "created_at": "2026-05-01T12:00:00"},
        ],
    )

    response = client.post(
        "/customer-auth/verify",
        json={"phone": "13800000001", "recent_order_id": "O1"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "手机号或最近订单号不匹配"


@pytest.mark.parametrize("customer,orders", [(None, []), ({"id": "C1001"}, [])])
def test_verify_customer_uses_same_error_for_missing_customer_or_orders(
    client, monkeypatch, customer, orders
):
    def fake_get_customer_by_phone(self, phone):
        return customer

    def fake_list_orders(self, customer_id):
        if customer is None:
            assert customer_id == "__customer_auth_dummy__"
        return orders

    monkeypatch.setattr(BusinessClient, "get_customer_by_phone", fake_get_customer_by_phone)
    monkeypatch.setattr(BusinessClient, "list_orders", fake_list_orders)

    response = client.post(
        "/customer-auth/verify",
        json={"phone": "13800000001", "recent_order_id": "O1"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "手机号或最近订单号不匹配"


def test_mask_phone_handles_short_abnormal_value_safely():
    assert _mask_phone("123") == "***"


@pytest.mark.parametrize(
    "body",
    [
        {"phone": "123", "recent_order_id": "O1"},
        {"phone": "1" * 33, "recent_order_id": "O1"},
        {"phone": "13800000001", "recent_order_id": " "},
        {"phone": "13800000001", "recent_order_id": "O" * 65},
    ],
)
def test_verify_customer_rejects_malformed_input(client, body):
    assert client.post("/customer-auth/verify", json=body).status_code == 422


@pytest.mark.parametrize("failed_call", ["customer", "orders"])
def test_verify_customer_hides_business_unavailable_details(
    client, monkeypatch, failed_call
):
    customer = {"id": "C1001", "phone": "13800000001"}

    def fake_get_customer_by_phone(self, phone):
        if failed_call == "customer":
            raise BusinessUnavailable("secret upstream detail")
        return customer

    def fake_list_orders(self, customer_id):
        if failed_call == "orders":
            raise BusinessUnavailable("secret upstream detail")
        return []

    monkeypatch.setattr(BusinessClient, "get_customer_by_phone", fake_get_customer_by_phone)
    monkeypatch.setattr(BusinessClient, "list_orders", fake_list_orders)

    response = client.post(
        "/customer-auth/verify",
        json={"phone": "13800000001", "recent_order_id": "O1"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "身份验证服务暂时不可用"


def test_failed_attempts_are_rate_limited_by_ip_and_normalized_phone(client, monkeypatch):
    monkeypatch.setattr(BusinessClient, "get_customer_by_phone", lambda self, phone: None)
    monkeypatch.setattr(BusinessClient, "list_orders", lambda self, customer_id: [])

    for phone in [" 13800000001 ", "13800000001"] * 2 + ["13800000001"]:
        response = client.post(
            "/customer-auth/verify",
            json={"phone": phone, "recent_order_id": "wrong"},
        )
        assert response.status_code == 401

    response = client.post(
        "/customer-auth/verify",
        json={"phone": "13800000001", "recent_order_id": "wrong"},
    )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_success_clears_failed_attempts(client, monkeypatch):
    customer = {"id": "C1001", "phone": "13800000001"}
    monkeypatch.setattr(BusinessClient, "get_customer_by_phone", lambda self, phone: customer)
    monkeypatch.setattr(
        BusinessClient,
        "list_orders",
        lambda self, customer_id: [{"id": "O1", "created_at": "2026-06-01T12:00:00"}],
    )

    for _ in range(4):
        assert client.post(
            "/customer-auth/verify",
            json={"phone": "13800000001", "recent_order_id": "wrong"},
        ).status_code == 401

    assert client.post(
        "/customer-auth/verify",
        json={"phone": "13800000001", "recent_order_id": "O1"},
    ).status_code == 200

    for _ in range(5):
        assert client.post(
            "/customer-auth/verify",
            json={"phone": "13800000001", "recent_order_id": "wrong"},
        ).status_code == 401


def test_fixed_window_limiter_supports_injected_time_and_reset():
    now = [100.0]
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])

    assert limiter.retry_after("key") == 0
    limiter.record_failure("key")
    limiter.record_failure("key")
    assert limiter.retry_after("key") == 60

    now[0] = 161.0
    assert limiter.retry_after("key") == 0
    limiter.record_failure("key")
    limiter.reset()
    assert limiter.retry_after("key") == 0


def test_customer_token_cannot_access_agent_endpoint(client):
    token, _ = create_customer_access_token("C1001")

    response = client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_expired_customer_token_is_rejected(client):
    token = jwt.encode(
        {
            "sub": "C1001",
            "customer_ref": "C1001",
            "role": "customer",
            "exp": 0,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )

    response = client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_non_agent_user_cannot_access_agent_endpoint_with_agent_claim(
    client, db_session
):
    user = User(
        username="customer-user",
        password_hash=hash_password("pw"),
        role="customer",
        display_name="客户",
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token(user.username, "agent", user.id)

    response = client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
