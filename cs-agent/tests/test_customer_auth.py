from datetime import datetime

import pytest

from app.auth import create_access_token, create_customer_access_token, hash_password
from app.clients.business_client import BusinessClient
from app.models import User


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
        {"id": "O2", "created_at": "2026-06-01T12:00:00"},
        {"id": "O3", "created_at": "2026-06-01T12:00:00"},
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


def test_verify_customer_rejects_order_that_is_not_latest(client, monkeypatch):
    _patch_customer(
        monkeypatch,
        customer={"id": "C1001", "phone": "13800000001"},
        orders=[
            {"id": "O1", "created_at": "2026-05-01T12:00:00"},
            {"id": "O2", "created_at": "2026-06-01T12:00:00"},
        ],
    )

    response = client.post(
        "/customer-auth/verify",
        json={"phone": "13800000001", "recent_order_id": "O1"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "手机号或最近订单号不匹配"


@pytest.mark.parametrize("customer,orders", [(None, None), ({"id": "C1001"}, [])])
def test_verify_customer_uses_same_error_for_missing_customer_or_orders(
    client, monkeypatch, customer, orders
):
    def fake_get_customer_by_phone(self, phone):
        return customer

    def fake_list_orders(self, customer_id):
        return orders

    monkeypatch.setattr(BusinessClient, "get_customer_by_phone", fake_get_customer_by_phone)
    monkeypatch.setattr(BusinessClient, "list_orders", fake_list_orders)

    response = client.post(
        "/customer-auth/verify",
        json={"phone": "13800000001", "recent_order_id": "O1"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "手机号或最近订单号不匹配"


def test_verify_customer_masks_short_abnormal_phone_safely(client, monkeypatch):
    customer = {"id": "C1", "phone": "123"}

    monkeypatch.setattr(BusinessClient, "get_customer_by_phone", lambda self, phone: customer)
    monkeypatch.setattr(
        BusinessClient,
        "list_orders",
        lambda self, customer_id: [{"id": "O1", "created_at": "2026-06-01T12:00:00"}],
    )

    response = client.post(
        "/customer-auth/verify",
        json={"phone": "123", "recent_order_id": "O1"},
    )

    assert response.status_code == 200
    assert response.json()["masked_phone"] == "***"


def test_customer_token_cannot_access_agent_endpoint(client):
    token, _ = create_customer_access_token("C1001")

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
