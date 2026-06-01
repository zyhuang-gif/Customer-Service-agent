from app.database import get_db
from app.models import Customer


def _seed_customer(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Customer(id="C1001", name="张三", phone="13800000001"))
    db.commit()


def test_create_ticket(client):
    _seed_customer(client)
    resp = client.post("/tickets", json={
        "customer_id": "C1001", "order_id": "O1",
        "category": "物流", "summary": "物流停滞催办", "priority": "高",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("TK")
    assert body["status"] == "待处理"
    assert body["category"] == "物流"


def test_list_tickets_by_customer(client):
    _seed_customer(client)
    client.post("/tickets", json={"customer_id": "C1001", "category": "投诉", "summary": "a"})
    client.post("/tickets", json={"customer_id": "C1001", "category": "退款", "summary": "b"})
    resp = client.get("/tickets", params={"customer_id": "C1001"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_update_ticket_status_and_note(client):
    _seed_customer(client)
    tk = client.post("/tickets", json={"customer_id": "C1001", "category": "物流", "summary": "x"}).json()
    resp = client.patch(f"/tickets/{tk['id']}", json={"status": "已解决", "note": "已联系物流"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "已解决"
    assert any(h.get("note") == "已联系物流" for h in body["history"])


def test_update_ticket_not_found(client):
    resp = client.patch("/tickets/NOPE", json={"status": "已解决"})
    assert resp.status_code == 404


def test_create_ticket_customer_not_found(client):
    resp = client.post("/tickets", json={"customer_id": "NOPE", "category": "物流", "summary": "x"})
    assert resp.status_code == 404
