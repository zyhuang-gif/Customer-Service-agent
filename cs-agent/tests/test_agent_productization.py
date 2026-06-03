from langchain_core.messages import AIMessage, ToolMessage

from app.agent.service import ConversationService
from app.models import Conversation, Message


class FakeGraph:
    def __init__(self, result):
        self.result = result

    def invoke(self, state, config=None):
        self.state = state
        return self.result


class FakeBusiness:
    pass


def test_start_turn_persists_trace_decision_and_citations(db_session):
    db_session.add(Conversation(id="conv-1", customer_ref="C1"))
    db_session.commit()
    tool = ToolMessage(
        content=str({
            "hits": [{
                "title": "退款到账时间",
                "source": "refund_policy.md",
                "text": "银行卡退款通常需要 1-5 个工作日到账。",
                "score": 0.91,
            }],
            "covered": True,
            "query": "退款多久到账",
        }),
        tool_call_id="tc-1",
        name="search_knowledge",
    )
    graph = FakeGraph({"messages": [tool, AIMessage(content="退款通常需要 1-5 个工作日到账。")]})
    svc = ConversationService(db=db_session, graph=graph, business=FakeBusiness())

    out = svc.start_turn("conv-1", "我的退款怎么还没到账？订单号是 20260531003")

    msg = db_session.query(Message).filter_by(conversation_id="conv-1", role="ai").one()
    assert out["citations"] == msg.meta["citations"]
    assert out["agent_trace"] == msg.meta["agent_trace"]
    assert msg.meta["coordinator_decision"]["task_type"] == "refund_status_query"
    assert msg.meta["citations"] == [{
        "title": "退款到账时间",
        "source": "refund_policy.md",
        "text": "银行卡退款通常需要 1-5 个工作日到账。",
        "score": 0.91,
    }]
    assert [step["agent"] for step in msg.meta["agent_trace"]] == [
        "CoordinatorAgent",
        "KnowledgeAgent",
        "CoordinatorAgent",
    ]


def test_chat_sse_includes_trace_and_citations(client):
    r = client.post("/chat", json={"customer_ref": "13800000001", "message": "退款多久到账？"})

    assert r.status_code == 200
    body = r.text
    assert '"agent_trace"' in body
    assert '"citations"' in body
