from app.auth import hash_password
from app.dashboard import build_dashboard_summary
from app.models import AuditLog, Conversation, PendingAction, User


def test_build_dashboard_summary_counts_core_metrics(db_session):
    db_session.add_all([
        Conversation(id="c1", customer_ref="C1", status="resolved"),
        Conversation(id="c2", customer_ref="C2", status="human_handling"),
        Conversation(id="c3", customer_ref="C3", status="awaiting_confirmation"),
        PendingAction(conversation_id="c3", tool_name="apply_refund", params={}, status="pending"),
        AuditLog(conversation_id="c1", actor="ai", action_type="knowledge_gap",
                 tool_name="search_knowledge", params={"query": "保价"}, status="uncovered"),
        AuditLog(conversation_id="c2", actor="ai", action_type="handoff", status="human_handling"),
        AuditLog(conversation_id="c1", actor="ai", action_type="tool_call",
                 tool_name="search_knowledge", status="hit"),
        AuditLog(conversation_id="c3", actor="ai", action_type="tool_call",
                 tool_name="search_knowledge", status="miss"),
    ])
    db_session.commit()

    out = build_dashboard_summary(db_session)

    assert out["conversation_total"] == 3
    assert out["status_counts"]["human_handling"] == 1
    assert out["pending_actions"] == 1
    assert out["ai_resolution_rate"] == 1 / 3
    assert out["handoff_rate"] == 1 / 3
    assert out["knowledge_hit_rate"] == 0.5
    assert out["knowledge_gaps"] == [{"query": "保价", "count": 1}]


def test_dashboard_summary_api_requires_auth(client):
    r = client.get("/dashboard/summary")
    assert r.status_code == 401


def test_dashboard_summary_api_returns_metrics(client, db_session):
    db_session.add(User(username="agent1", password_hash=hash_password("pw"), role="agent"))
    db_session.add(Conversation(id="c1", customer_ref="C1", status="resolved"))
    db_session.commit()

    token = client.post("/auth/login", json={"username": "agent1", "password": "pw"}).json()["access_token"]
    r = client.get("/dashboard/summary", headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    assert r.json()["conversation_total"] == 1
