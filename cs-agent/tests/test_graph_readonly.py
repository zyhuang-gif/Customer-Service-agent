from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_graph


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[
                {"name": "get_order", "args": {"order_id": "O1"}, "id": "c1", "type": "tool_call"}
            ])
        return AIMessage(content="您的订单 O1 状态为已发货。")


class FakeRegistry:
    def __init__(self):
        self.called = []

    def authorize_customer_call(self, tool_name, params, *, customer_ref):
        return None

    def call(self, tool_name, params, *, customer_ref):
        self.called.append((tool_name, params))
        return {"id": "O1", "status": "已发货"}


def test_readonly_tool_auto_executes_and_replies():
    llm = FakeLLM()
    reg = FakeRegistry()
    graph = build_graph(llm=llm, registry=reg, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "conv-1"}}
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "订单 O1 到哪了"}],
         "conversation_id": "conv-1", "customer_ref": "x", "intent": ""},
        config=config,
    )
    assert ("get_order", {"order_id": "O1"}) in reg.called
    last = result["messages"][-1]
    assert "已发货" in last.content


def test_readonly_tool_fails_closed_without_authorizing_registry():
    llm = FakeLLM()
    graph = build_graph(llm=llm, registry=None, checkpointer=MemorySaver())

    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "订单 O1 到哪了"}],
            "conversation_id": "conv-no-registry",
            "customer_ref": "C1",
            "intent": "",
        },
        config={"configurable": {"thread_id": "conv-no-registry"}},
    )

    tool_message = next(message for message in result["messages"] if message.type == "tool")
    assert "access_denied" in tool_message.content


def test_readonly_tool_fails_closed_without_registry_call():
    class AuthorizerOnly:
        def authorize_customer_call(self, tool_name, params, *, customer_ref):
            return None

    graph = build_graph(
        llm=FakeLLM(),
        registry=AuthorizerOnly(),
        checkpointer=MemorySaver(),
    )

    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "订单 O1 到哪了"}],
            "conversation_id": "conv-no-call",
            "customer_ref": "C1",
            "intent": "",
        },
        config={"configurable": {"thread_id": "conv-no-call"}},
    )

    tool_message = next(message for message in result["messages"] if message.type == "tool")
    assert "access_denied" in tool_message.content
