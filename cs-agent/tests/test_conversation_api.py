from app.auth import hash_password
from app.models import Conversation, Message, User


def test_cors_headers_present(client):
    r = client.options("/health/live", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    })
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def _login(client, db_session):
    db_session.add(User(username="a1", password_hash=hash_password("pw"), role="agent", display_name="一号"))
    db_session.commit()
    token = client.post("/auth/login", json={"username": "a1", "password": "pw"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_list_conversations(client, db_session):
    h = _login(client, db_session)
    db_session.add(Conversation(id="c1", customer_ref="138", status="ai_handling"))
    db_session.add(Conversation(id="c2", customer_ref="139", status="awaiting_confirmation"))
    db_session.commit()
    r = client.get("/conversations", headers=h)
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert "c1" in ids and "c2" in ids


def test_list_conversations_filter_status(client, db_session):
    h = _login(client, db_session)
    db_session.add(Conversation(id="c1", customer_ref="138", status="ai_handling"))
    db_session.add(Conversation(id="c2", customer_ref="139", status="awaiting_confirmation"))
    db_session.commit()
    r = client.get("/conversations", params={"status": "awaiting_confirmation"}, headers=h)
    assert r.status_code == 200
    assert [c["id"] for c in r.json()] == ["c2"]


def test_get_conversation_messages(client, db_session):
    h = _login(client, db_session)
    db_session.add(Conversation(id="c1", customer_ref="138", status="ai_handling"))
    db_session.add(Message(conversation_id="c1", role="customer", content="你好"))
    db_session.add(Message(conversation_id="c1", role="ai", content="您好，有什么可以帮您"))
    db_session.commit()
    r = client.get("/conversations/c1/messages", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["role"] == "customer"
    assert body[1]["content"] == "您好，有什么可以帮您"


def test_conversations_require_auth(client):
    assert client.get("/conversations").status_code == 401
