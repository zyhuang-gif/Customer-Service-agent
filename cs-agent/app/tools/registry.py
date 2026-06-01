"""工具注册表：把 BusinessClient + Retriever 包装成 Agent 可调用的工具。

约定：
- 工具绝不向上抛异常，失败返回 ToolError.to_dict()
- 只读 / 低风险写：直接执行
- 高风险写：不执行业务 API，返回 PendingActionIntent.to_dict()
"""
from __future__ import annotations

from typing import Any

from app.errors import BusinessUnavailable, ToolError
from app.tools.risk import RiskLevel, risk_of
from app.tools.schemas import PendingActionIntent


class ToolRegistry:
    def __init__(self, business, retriever):
        self.business = business
        self.retriever = retriever

    def call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any] | list:
        level = risk_of(tool_name)
        if level == RiskLevel.HIGH_WRITE:
            return PendingActionIntent(tool_name=tool_name, params=params).to_dict()
        handler = getattr(self, f"_tool_{tool_name}")
        try:
            return handler(params)
        except BusinessUnavailable as exc:
            return ToolError("upstream_unavailable", "业务系统暂时不可用，正在为您转人工", exc.details).to_dict()

    # ---- 只读工具 ----
    def _tool_search_knowledge(self, params):
        hits = self.retriever.retrieve(params["query"])
        return {"hits": hits, "covered": bool(hits)}

    def _tool_get_customer(self, params):
        data = self.business.get_customer(params["customer_id"])
        return data if data is not None else ToolError("not_found", "未找到该客户").to_dict()

    def _tool_get_order(self, params):
        data = self.business.get_order(params["order_id"])
        return data if data is not None else ToolError("not_found", "未找到该订单，请核对订单号").to_dict()

    def _tool_get_logistics(self, params):
        data = self.business.get_logistics(params["order_id"])
        return data if data is not None else ToolError("not_found", "未找到该订单的物流信息").to_dict()

    def _tool_get_refund_status(self, params):
        data = self.business.get_refund_status(params["order_id"])
        return data if data is not None else ToolError("not_found", "未找到该订单的退款记录").to_dict()

    def _tool_list_customer_tickets(self, params):
        data = self.business.list_customer_tickets(params["customer_id"])
        return {"tickets": data if data is not None else []}

    # ---- 低风险写工具 ----
    def _tool_create_ticket(self, params):
        data = self.business.create_ticket(
            customer_id=params["customer_id"],
            order_id=params.get("order_id"),
            category=params["category"],
            summary=params.get("summary", ""),
            priority=params.get("priority", "中"),
        )
        return data if data is not None else ToolError("not_found", "建单失败：未找到该客户").to_dict()

    def _tool_update_ticket(self, params):
        data = self.business.update_ticket(
            ticket_id=params["ticket_id"],
            note=params.get("note"),
            status=params.get("status"),
            assignee=params.get("assignee"),
        )
        return data if data is not None else ToolError("not_found", "更新失败：未找到该工单").to_dict()
