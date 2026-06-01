from app.database import get_db
from app.models import Order, Refund


def _seed_order(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Order(id="O1", customer_id="C1001", status="已签收", amount=299.0))
    db.commit()


def test_get_refund_status_none(client):
    _seed_order(client)
    resp = client.get("/refunds", params={"order_id": "O1"})
    assert resp.status_code == 200
    assert resp.json() == {"order_id": "O1", "status": "无", "refund": None}


def test_create_refund(client):
    _seed_order(client)
    resp = client.post("/refunds", json={"order_id": "O1", "amount": 299.0, "reason": "物流停滞"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["order_id"] == "O1"
    assert body["status"] == "处理中"
    assert body["id"].startswith("RF")


def test_get_refund_status_after_create(client):
    _seed_order(client)
    client.post("/refunds", json={"order_id": "O1", "amount": 299.0})
    resp = client.get("/refunds", params={"order_id": "O1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "处理中"


def test_create_refund_order_not_found(client):
    resp = client.post("/refunds", json={"order_id": "NOPE", "amount": 10.0})
    assert resp.status_code == 404
