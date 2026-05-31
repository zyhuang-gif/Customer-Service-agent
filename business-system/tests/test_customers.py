from app.database import get_db
from app.models import Customer


def _seed_customer(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Customer(id="C1001", name="张三", phone="13800000001", member_level="金"))
    db.commit()


def test_get_customer_by_id(client):
    _seed_customer(client)
    resp = client.get("/customers/C1001")
    assert resp.status_code == 200
    assert resp.json()["name"] == "张三"
    assert resp.json()["member_level"] == "金"


def test_get_customer_by_phone(client):
    _seed_customer(client)
    resp = client.get("/customers", params={"phone": "13800000001"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "C1001"


def test_get_customer_not_found(client):
    resp = client.get("/customers/NOPE")
    assert resp.status_code == 404
