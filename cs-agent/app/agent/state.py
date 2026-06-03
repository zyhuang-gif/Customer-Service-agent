"""LangGraph 图状态。messages 用 add_messages 累加；其余为单值。"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    conversation_id: str
    customer_ref: str
    intent: str
    coordinator_decision: dict
