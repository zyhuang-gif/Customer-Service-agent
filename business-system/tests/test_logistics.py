from datetime import datetime, timedelta

from app.database import get_db
from app.models import Logistics, Order


def _seed(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Order(id="O1", customer_id="C1001", status="已发货"))
    db.add(Logistics(id="L1", order_id="O1", carrier="顺丰", tracking_no="SF123",
                     status="运输中", last_update=datetime.utcnow() - timedelta(days=3),
                     traces=[{"time": "2026-05-28", "desc": "已揽收"}]))
    db.commit()


def test_get_logistics_by_order(client):
    _seed(client)
    resp = client.get("/logistics", params={"order_id": "O1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "运输中"
    assert resp.json()["carrier"] == "顺丰"


def test_get_logistics_not_found(client):
    resp = client.get("/logistics", params={"order_id": "NOPE"})
    assert resp.status_code == 404
