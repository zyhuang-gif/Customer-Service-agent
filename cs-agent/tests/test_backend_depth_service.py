from langchain_core.messages import AIMessage, ToolMessage

from app.agent.service import ConversationService
from app.models import AuditLog, Conversation, Message


class FakeGraph:
    def __init__(self, result):
        self.result = result
        self.invoked = False

    def invoke(self, state, config=None):
        self.invoked = True
        return self.result


class FakeBusiness:
    pass


def _service(db_session, result):
    return ConversationService(db=db_session, graph=FakeGraph(result), business=FakeBusiness())


def test_start_turn_persists_customer_sentiment_meta(db_session):
    db_session.add(Conversation(id="conv-1", customer_ref="C1"))
    db_session.commit()
    svc = _service(db_session, {"messages": [AIMessage(content="我来帮您处理")]})

    out = svc.start_turn("conv-1", "你们太离谱了")

    msg = db_session.query(Message).filter_by(conversation_id="conv-1", role="customer").one()
    assert msg.meta["sentiment"] == "angry"
    assert msg.meta["risk"] == "high"
    assert out["status"] == "ai_handling"


def test_explicit_handoff_sets_status_summary_and_audit_without_graph(db_session):
    db_session.add(Conversation(id="conv-1", customer_ref="C1"))
    db_session.commit()
    graph = FakeGraph({"messages": [AIMessage(content="should not run")]})
    svc = ConversationService(db=db_session, graph=graph, business=FakeBusiness())

    out = svc.start_turn("conv-1", "我要转人工")

    conv = db_session.get(Conversation, "conv-1")
    audit = db_session.query(AuditLog).filter_by(action_type="handoff").one()
    assert out["status"] == "human_handling"
    assert conv.status == "human_handling"
    assert "客户问题：我要转人工" in conv.summary
    assert audit.status == "human_handling"
    assert graph.invoked is False


def test_transfer_tool_result_sets_human_handling(db_session):
    db_session.add(Conversation(id="conv-1", customer_ref="C1"))
    db_session.commit()
    tool = ToolMessage(
        content=str({"handoff": True, "reason": "客户要求人工", "draft_summary": "客户要人工"}),
        tool_call_id="tc-1",
        name="transfer_to_human",
    )
    svc = _service(db_session, {"messages": [tool, AIMessage(content="已为您转人工")]})

    out = svc.start_turn("conv-1", "继续处理这个问题")

    conv = db_session.get(Conversation, "conv-1")
    assert out["status"] == "human_handling"
    assert conv.summary == "客户要人工"
    assert db_session.query(AuditLog).filter_by(action_type="handoff").count() == 1


def test_uncovered_knowledge_search_writes_gap_audit(db_session):
    db_session.add(Conversation(id="conv-1", customer_ref="C1"))
    db_session.commit()
    tool = ToolMessage(
        content=str({"hits": [], "covered": False, "query": "七天无理由"}),
        tool_call_id="tc-1",
        name="search_knowledge",
    )
    svc = _service(db_session, {"messages": [tool, AIMessage(content="知识库暂未覆盖")]})

    svc.start_turn("conv-1", "七天无理由怎么算")

    audit = db_session.query(AuditLog).filter_by(action_type="knowledge_gap").one()
    tool_audit = db_session.query(AuditLog).filter_by(action_type="tool_call", tool_name="search_knowledge").one()
    assert audit.tool_name == "search_knowledge"
    assert audit.params["query"] == "七天无理由"
    assert audit.status == "uncovered"
    assert tool_audit.status == "miss"
