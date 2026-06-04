"""LangGraph 图：analyze -> agent ->（条件）tools / high_risk(interrupt)。"""
from __future__ import annotations

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from app.agent.routing import route_customer_message
from app.agent.state import AgentState
from app.agent.tools_bind import ALL_TOOLS
from app.tools.risk import is_high_risk


SYSTEM_PROMPT = """你是电商售后客服 Agent。请优先使用工具查询事实，不要臆测。

工具选择规则：
- 用户询问物流、订单、退款进度、客户资料、历史工单时，调用对应查询工具。
- 用户明确要求退款、改地址或发券时，必须调用 apply_refund、change_address 或 issue_coupon。
- apply_refund、change_address、issue_coupon 是高风险操作，系统会自动转入人工确认；你只负责提出工具调用，不要改用创建工单来替代明确的高风险请求。
- 用户要求人工、情绪强烈升级、或问题无法独立解决时，调用 transfer_to_human 并给出摘要。
"""


def build_graph(llm, registry, checkpointer, tool_specs=None):
    """llm: 可 bind_tools 的对象；registry: ToolRegistry；checkpointer。"""
    bound_llm = llm.bind_tools(tool_specs if tool_specs is not None else ALL_TOOLS)

    def analyze(state: AgentState) -> dict:
        user_text = ""
        for m in reversed(state["messages"]):
            content = getattr(m, "content", "") or (m.get("content", "") if isinstance(m, dict) else "")
            if content:
                user_text = content
                break
        decision = route_customer_message(user_text)
        return {"intent": decision["task_type"], "coordinator_decision": decision}

    def agent(state: AgentState) -> dict:
        resp = bound_llm.invoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
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
            if hasattr(registry, "authorize_customer_call"):
                result = registry.call(
                    tc["name"],
                    tc["args"],
                    customer_ref=state.get("customer_ref"),
                )
            else:
                result = registry.call(tc["name"], tc["args"])
            out_msgs.append(ToolMessage(content=str(result), tool_call_id=tc["id"], name=tc["name"]))
        return {"messages": out_msgs}

    def high_risk(state: AgentState) -> dict:
        last = state["messages"][-1]
        for tc in last.tool_calls:
            if is_high_risk(tc["name"]):
                denied = (
                    registry.authorize_customer_call(
                        tc["name"],
                        tc["args"],
                        customer_ref=state.get("customer_ref"),
                    )
                    if hasattr(registry, "authorize_customer_call")
                    else None
                )
                if denied:
                    return {
                        "messages": [
                            ToolMessage(
                                content=str(denied),
                                tool_call_id=tc["id"],
                                name=tc["name"],
                            )
                        ]
                    }
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
