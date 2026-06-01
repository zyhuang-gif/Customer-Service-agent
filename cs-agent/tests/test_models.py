from app.models import AuditLog, Conversation, Message, PendingAction, User


def test_create_conversation_and_message(db_session):
    conv = Conversation(id="conv-1", customer_ref="13800000001", status="ai_handling")
    db_session.add(conv)
    db_session.commit()
    db_session.add(Message(conversation_id="conv-1", role="customer", content="我的订单到哪了"))
    db_session.commit()
    msgs = db_session.query(Message).filter_by(conversation_id="conv-1").all()
    assert len(msgs) == 1
    assert msgs[0].role == "customer"


def test_pending_action_defaults(db_session):
    db_session.add(Conversation(id="conv-1", customer_ref="x"))
    db_session.commit()
    pa = PendingAction(conversation_id="conv-1", tool_name="apply_refund", params={"order_id": "O1", "amount": 100})
    db_session.add(pa)
    db_session.commit()
    assert pa.status == "pending"
    assert pa.proposed_by == "ai"
    assert pa.params["order_id"] == "O1"


def test_user_and_audit(db_session):
    db_session.add(User(username="agent1", password_hash="x", role="agent", display_name="客服一号"))
    db_session.add(AuditLog(actor="ai", action_type="tool_call", tool_name="get_order", status="ok"))
    db_session.commit()
    assert db_session.query(User).count() == 1
    assert db_session.query(AuditLog).count() == 1
