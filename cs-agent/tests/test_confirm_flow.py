from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_graph
from app.agent.service import ConversationService
from app.models import Conversation, PendingAction


class HighRiskLLM:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[
                {"name": "apply_refund", "args": {"order_id": "O1", "amount": 99.0, "reason": "停滞"},
                 "id": "c1", "type": "tool_call"}
            ])
        return AIMessage(content="退款已为您提交处理。")


class FakeBusiness:
    def __init__(self):
        self.refunded = None

    def apply_refund(self, order_id, amount, reason="", channel="原路退回"):
        self.refunded = {"order_id": order_id, "amount": amount}
        return {"id": "RF1", "order_id": order_id, "status": "处理中"}


class FakeRegistry:
    def call(self, tool_name, params):
        return {"ok": True}


def _service(db_session):
    biz = FakeBusiness()
    graph = build_graph(llm=HighRiskLLM(), registry=FakeRegistry(), checkpointer=MemorySaver())
    return ConversationService(db=db_session, graph=graph, business=biz), biz


def test_high_risk_creates_pending_and_awaits(db_session):
    db_session.add(Conversation(id="c1", customer_ref="x", status="ai_handling"))
    db_session.commit()
    svc, _ = _service(db_session)
    out = svc.start_turn("c1", "给我退款")
    assert out["status"] == "awaiting_confirmation"
    pa = db_session.query(PendingAction).filter_by(conversation_id="c1").one()
    assert pa.tool_name == "apply_refund"
    assert pa.status == "pending"
    conv = db_session.get(Conversation, "c1")
    assert conv.status == "awaiting_confirmation"


def test_confirm_executes_business_and_resumes(db_session):
    db_session.add(Conversation(id="c1", customer_ref="x", status="ai_handling"))
    db_session.commit()
    svc, biz = _service(db_session)
    svc.start_turn("c1", "给我退款")
    pa = db_session.query(PendingAction).filter_by(conversation_id="c1").one()
    out = svc.resume_action(pa.id, approved=True, reviewer_id=1)
    assert biz.refunded == {"order_id": "O1", "amount": 99.0}
    db_session.refresh(pa)
    assert pa.status == "executed"
    assert pa.result.get("id") == "RF1"
    conv = db_session.get(Conversation, "c1")
    assert conv.status == "ai_handling"


def test_reject_marks_rejected_and_no_business_call(db_session):
    db_session.add(Conversation(id="c1", customer_ref="x", status="ai_handling"))
    db_session.commit()
    svc, biz = _service(db_session)
    svc.start_turn("c1", "给我退款")
    pa = db_session.query(PendingAction).filter_by(conversation_id="c1").one()
    svc.resume_action(pa.id, approved=False, reviewer_id=1)
    assert biz.refunded is None
    db_session.refresh(pa)
    assert pa.status == "rejected"


def test_double_confirm_is_idempotent(db_session):
    db_session.add(Conversation(id="c1", customer_ref="x", status="ai_handling"))
    db_session.commit()
    svc, biz = _service(db_session)
    svc.start_turn("c1", "给我退款")
    pa = db_session.query(PendingAction).filter_by(conversation_id="c1").one()
    svc.resume_action(pa.id, approved=True, reviewer_id=1)
    assert biz.refunded == {"order_id": "O1", "amount": 99.0}
    biz.refunded = None
    out = svc.resume_action(pa.id, approved=True, reviewer_id=1)
    assert out["status"] == "noop"
    assert biz.refunded is None
