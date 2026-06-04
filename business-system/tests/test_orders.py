from datetime import datetime

from app.database import get_db
from app.models import Customer, Order


def _seed(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Customer(id="C1001", name="张三", phone="13800000001"))
    db.add(Order(id="O1", customer_id="C1001", status="已发货",
                 items=[{"name": "鞋", "qty": 1}], amount=299.0, address="北京"))
    db.commit()


def test_get_order_by_id(client):
    _seed(client)
    resp = client.get("/orders/O1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "已发货"


def test_list_orders_by_customer(client):
    _seed(client)
    resp = client.get("/orders", params={"customer_id": "C1001"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == "O1"


def test_list_orders_is_stably_sorted_by_created_at_then_id_desc(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Customer(id="C1001", name="张三", phone="13800000001"))
    db.add_all([
        Order(id="O1", customer_id="C1001", status="已发货", created_at=datetime(2026, 6, 1)),
        Order(id="O3", customer_id="C1001", status="已发货", created_at=datetime(2026, 6, 2)),
        Order(id="O2", customer_id="C1001", status="已发货", created_at=datetime(2026, 6, 2)),
    ])
    db.commit()

    resp = client.get("/orders", params={"customer_id": "C1001"})

    assert resp.status_code == 200
    assert [order["id"] for order in resp.json()] == ["O3", "O2", "O1"]


def test_get_order_not_found(client):
    resp = client.get("/orders/NOPE")
    assert resp.status_code == 404


def test_change_address(client):
    _seed(client)
    resp = client.patch("/orders/O1/address", json={"new_address": "上海浦东"})
    assert resp.status_code == 200
    assert resp.json()["address"] == "上海浦东"


def test_change_address_not_found(client):
    resp = client.patch("/orders/NOPE/address", json={"new_address": "上海"})
    assert resp.status_code == 404
