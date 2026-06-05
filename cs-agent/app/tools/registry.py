"""工具注册表：把 BusinessClient + Retriever 包装成 Agent 可调用的工具。

约定：
- 工具绝不向上抛异常，失败返回 ToolError.to_dict()
- 只读 / 低风险写：直接执行
- 高风险写：不执行业务 API，返回 PendingActionIntent.to_dict()
"""
from __future__ import annotations

from typing import Any

from app.errors import BusinessUnavailable, ToolError
from app.tools.risk import TOOL_RISK, RiskLevel, risk_of
from app.tools.schemas import PendingActionIntent

_PUBLIC_TOOLS = {"search_knowledge", "transfer_to_human"}
_ORDER_SCOPED_TOOLS = {
    "get_order",
    "get_logistics",
    "get_refund_status",
    "apply_refund",
    "change_address",
}
_CUSTOMER_SCOPED_TOOLS = {
    "get_customer",
    "list_customer_tickets",
    "create_ticket",
    "issue_coupon",
}


def _authorization_error(message: str, kind: str = "access_denied") -> dict[str, Any]:
    return ToolError(kind, message, {"authorization": True}).to_dict()


class ToolRegistry:
    def __init__(self, business, retriever):
        self.business = business
        self.retriever = retriever

    def authorize_customer_call(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        customer_ref: str | None,
    ) -> dict[str, Any] | None:
        if tool_name in _PUBLIC_TOOLS:
            return None
        if not customer_ref:
            return _authorization_error("请先完成客户身份验证")
        if not isinstance(params, dict):
            return _authorization_error("无法安全验证工具参数")

        if tool_name in _CUSTOMER_SCOPED_TOOLS:
            customer_id = params.get("customer_id")
            if not isinstance(customer_id, str) or not customer_id.strip():
                return _authorization_error("缺少客户作用域参数")
            if customer_id != customer_ref:
                return _authorization_error("无法访问其他客户的信息")

        order_id = params.get("order_id")
        requires_order = tool_name in _ORDER_SCOPED_TOOLS
        validates_optional_order = tool_name == "create_ticket" and order_id is not None
        if requires_order or validates_optional_order:
            if not isinstance(order_id, str) or not order_id.strip():
                return _authorization_error("缺少订单作用域参数")
            try:
                order = self.business.get_order(order_id)
            except BusinessUnavailable:
                return _authorization_error("业务系统暂时不可用", "upstream_unavailable")
            except Exception:
                return _authorization_error("无法安全验证订单归属", "internal")
            if order is None:
                return _authorization_error("无法验证订单归属")
            if not isinstance(order, dict) or not order.get("id") or not order.get("customer_id"):
                return _authorization_error("无法安全验证订单归属", "internal")
            if str(order["id"]).upper() != str(order_id).upper():
                return _authorization_error("无法安全验证订单归属", "internal")
            if str(order["customer_id"]) != customer_ref:
                return _authorization_error("无法访问其他客户的订单")

        if tool_name == "update_ticket":
            return _authorization_error("无法安全验证工单归属")
        if tool_name not in _ORDER_SCOPED_TOOLS | _CUSTOMER_SCOPED_TOOLS:
            return _authorization_error("工具缺少明确的客户作用域策略")
        return None

    def call(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        customer_ref: str | None,
    ) -> dict[str, Any] | list:
        # 未知工具名（如 LLM 幻觉）→ 返回结构化错误，绝不向上抛异常
        if tool_name not in TOOL_RISK:
            return ToolError("bad_request", f"未知工具：{tool_name}", {"tool_name": tool_name}).to_dict()
        denied = self.authorize_customer_call(
            tool_name,
            params,
            customer_ref=customer_ref,
        )
        if denied:
            return denied
        level = risk_of(tool_name)
        if level == RiskLevel.HIGH_WRITE:
            return PendingActionIntent(tool_name=tool_name, params=params).to_dict()
        handler = getattr(self, f"_tool_{tool_name}")
        try:
            return handler(params)
        except BusinessUnavailable as exc:
            return ToolError("upstream_unavailable", "业务系统暂时不可用，正在为您转人工", exc.details).to_dict()
        except Exception as exc:  # noqa: BLE001 兜底：任何工具内部异常都转结构化错误，绝不向上抛、绝不让 Agent 崩
            return ToolError("internal", "处理时发生内部错误，正在为您转人工", {"cause": str(exc)}).to_dict()

    # ---- 只读工具 ----
    def _tool_search_knowledge(self, params):
        query = params["query"]
        hits = self.retriever.retrieve(query)
        return {"hits": hits, "covered": bool(hits), "query": query}

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

    # ---- 控制工具 ----
    def _tool_transfer_to_human(self, params):
        return {
            "handoff": True,
            "reason": params.get("reason", "需要人工处理"),
            "draft_summary": params.get("draft_summary", ""),
        }
