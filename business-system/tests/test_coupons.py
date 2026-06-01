from app.database import get_db
from app.models import Customer


def _seed_customer(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Customer(id="C1001", name="张三", phone="13800000001"))
    db.commit()


def test_issue_coupon(client):
    _seed_customer(client)
    resp = client.post("/coupons", json={"customer_id": "C1001", "value": 20.0, "reason": "补偿"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("CP")
    assert body["value"] == 20.0


def test_issue_coupon_customer_not_found(client):
    resp = client.post("/coupons", json={"customer_id": "NOPE", "value": 20.0})
    assert resp.status_code == 404
