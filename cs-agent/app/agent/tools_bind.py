"""把 10 个工具暴露成 langchain @tool（带参数 schema），供 ChatOpenAI.bind_tools。

工具体不直接执行——只是 schema 载体；真正执行在图的 tools 节点经 ToolRegistry。
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def search_knowledge(query: str) -> str:
    """检索售后政策/FAQ 知识库，返回相关条款。"""
    return ""


@tool
def get_customer(customer_id: str) -> str:
    """按客户ID查询客户资料与会员等级。"""
    return ""


@tool
def get_order(order_id: str) -> str:
    """查询订单状态、金额、时间。"""
    return ""


@tool
def get_logistics(order_id: str) -> str:
    """查询订单的物流轨迹与当前状态。"""
    return ""


@tool
def get_refund_status(order_id: str) -> str:
    """查询订单的退款进度。"""
    return ""


@tool
def list_customer_tickets(customer_id: str) -> str:
    """查询客户的历史工单与投诉。"""
    return ""


@tool
def create_ticket(customer_id: str, category: str, summary: str, order_id: str = "", priority: str = "中") -> str:
    """创建工单（如物流催办）。不涉及钱，自动执行。"""
    return ""


@tool
def update_ticket(ticket_id: str, note: str = "", status: str = "", assignee: str = "") -> str:
    """更新工单状态或备注。"""
    return ""


@tool
def apply_refund(order_id: str, amount: float, reason: str = "") -> str:
    """发起退款（高风险，需人工确认）。"""
    return ""


@tool
def change_address(order_id: str, new_address: str) -> str:
    """修改收货地址（高风险，需人工确认）。"""
    return ""


@tool
def issue_coupon(customer_id: str, value: float, reason: str = "") -> str:
    """发放优惠券（高风险，需人工确认）。"""
    return ""


ALL_TOOLS = [
    search_knowledge, get_customer, get_order, get_logistics, get_refund_status,
    list_customer_tickets, create_ticket, update_ticket,
    apply_refund, change_address, issue_coupon,
]
