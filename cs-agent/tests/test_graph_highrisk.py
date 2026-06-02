from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agent.graph import build_graph


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
        return AIMessage(content="已为您处理。")


class SpyRegistry:
    def __init__(self):
        self.called = []

    def call(self, tool_name, params):
        self.called.append((tool_name, params))
        return {"ok": True}


def test_high_risk_interrupts_and_does_not_execute():
    graph = build_graph(llm=HighRiskLLM(), registry=SpyRegistry(), checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "conv-hr"}}
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "给我退款"}],
         "conversation_id": "conv-hr", "customer_ref": "x", "intent": ""},
        config=config,
    )
    assert "__interrupt__" in result
    intr = result["__interrupt__"][0]
    assert intr.value["tool_name"] == "apply_refund"
    assert intr.value["params"]["order_id"] == "O1"


def test_resume_with_approval_continues():
    spy = SpyRegistry()
    graph = build_graph(llm=HighRiskLLM(), registry=spy, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "conv-hr2"}}
    graph.invoke(
        {"messages": [{"role": "user", "content": "给我退款"}],
         "conversation_id": "conv-hr2", "customer_ref": "x", "intent": ""},
        config=config,
    )
    final = graph.invoke(Command(resume={"approved": True, "result": {"refund_id": "RF1"}}), config=config)
    last = final["messages"][-1]
    assert "已为您处理" in last.content
