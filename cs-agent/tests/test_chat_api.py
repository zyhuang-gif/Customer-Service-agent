from app.auth import hash_password
from app.models import User


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
    body = r.text
    assert "data:" in body
    assert "done" in body
