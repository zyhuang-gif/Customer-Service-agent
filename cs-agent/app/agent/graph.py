"""LangGraph 图：analyze -> agent ->（条件）tools / high_risk(interrupt)。"""
from __future__ import annotations

from langchain_core.messages import ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from app.agent.state import AgentState
from app.agent.tools_bind import ALL_TOOLS
from app.tools.risk import is_high_risk


def build_graph(llm, registry, checkpointer, tool_specs=None):
    """llm: 可 bind_tools 的对象；registry: ToolRegistry；checkpointer。"""
    bound_llm = llm.bind_tools(tool_specs if tool_specs is not None else ALL_TOOLS)

    def analyze(state: AgentState) -> dict:
        intent = "general"
        for m in reversed(state["messages"]):
            content = getattr(m, "content", "") or (m.get("content", "") if isinstance(m, dict) else "")
            if content:
                if "退款" in content:
                    intent = "refund"
                elif "物流" in content or "快递" in content or "到哪" in content:
                    intent = "logistics"
                break
        return {"intent": intent}

    def agent(state: AgentState) -> dict:
        resp = bound_llm.invoke(state["messages"])
        return {"messages": [resp]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        if not tool_calls:
            return END
        for tc in tool_calls:
            if is_high_risk(tc["name"]):
                return "high_risk"
        return "tools"

    def tools(state: AgentState) -> dict:
        last = state["messages"][-1]
        out_msgs = []
        for tc in last.tool_calls:
            result = registry.call(tc["name"], tc["args"])
            out_msgs.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        return {"messages": out_msgs}

    def high_risk(state: AgentState) -> dict:
        last = state["messages"][-1]
        for tc in last.tool_calls:
            if is_high_risk(tc["name"]):
                decision = interrupt({
                    "type": "high_risk_confirmation",
                    "tool_name": tc["name"],
                    "params": tc["args"],
                    "tool_call_id": tc["id"],
                })
                return {"messages": [ToolMessage(content=str(decision), tool_call_id=tc["id"])]}
        return {}

    g = StateGraph(AgentState)
    g.add_node("analyze", analyze)
    g.add_node("agent", agent)
    g.add_node("tools", tools)
    g.add_node("high_risk", high_risk)
    g.set_entry_point("analyze")
    g.add_edge("analyze", "agent")
    g.add_conditional_edges("agent", should_continue, {"tools": "tools", "high_risk": "high_risk", END: END})
    g.add_edge("tools", "agent")
    g.add_edge("high_risk", "agent")
    return g.compile(checkpointer=checkpointer)
