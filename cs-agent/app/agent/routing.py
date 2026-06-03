"""结构化客服路由决策。

第一版用确定性规则，保证演示与测试稳定；后续可替换为 LLM structured output。
"""
from __future__ import annotations

from typing import Any


def _decision(
    task_type: str,
    *,
    need_knowledge: bool = False,
    need_action: bool = False,
    action_type: str | None = None,
    need_ticket: bool = False,
    need_human_handoff: bool = False,
    risk_level: str = "normal",
    reason: str,
) -> dict[str, Any]:
    return {
        "task_type": task_type,
        "need_knowledge": need_knowledge,
        "need_action": need_action,
        "action_type": action_type,
        "need_ticket": need_ticket,
        "need_human_handoff": need_human_handoff,
        "risk_level": risk_level,
        "reason": reason,
    }


def route_customer_message(text: str) -> dict[str, Any]:
    content = text.strip()

    if any(word in content for word in ("投诉", "举报", "曝光", "起诉", "消协")):
        return _decision(
            "complaint",
            need_human_handoff=True,
            risk_level="high",
            reason="用户表达投诉或升级风险，需要优先转人工处理。",
        )

    if any(word in content for word in ("人工", "真人", "客服专员")):
        return _decision(
            "human_handoff",
            need_human_handoff=True,
            risk_level="high",
            reason="用户明确要求人工客服介入。",
        )

    if "退款" in content:
        if any(word in content for word in ("到账", "进度", "状态", "到哪", "没到")):
            return _decision(
                "refund_status_query",
                need_knowledge=True,
                need_action=True,
                action_type="get_refund_status",
                reason="用户询问退款状态或到账时间，需要查询退款进度并结合退款政策说明。",
            )
        return _decision(
            "after_sales_request",
            need_knowledge=True,
            need_action=True,
            action_type="apply_refund",
            risk_level="high",
            reason="用户提出退款诉求，可能涉及资金操作，需要进入风险控制流程。",
        )

    if any(word in content for word in ("物流", "快递", "到哪", "派送", "签收")):
        return _decision(
            "logistics_query",
            need_knowledge=True,
            need_action=True,
            action_type="get_logistics",
            reason="用户询问物流状态，需要查询物流并结合物流规则说明。",
        )

    if "订单" in content:
        return _decision(
            "order_status_query",
            need_action=True,
            action_type="get_order",
            reason="用户询问订单状态，需要查询订单业务数据。",
        )

    if any(word in content for word in ("工单", "登记", "催办")):
        return _decision(
            "ticket_creation",
            need_action=True,
            action_type="create_ticket",
            need_ticket=True,
            reason="用户要求登记或催办，需要创建客服工单。",
        )

    if any(word in content for word in ("规则", "政策", "几天", "多久", "退货", "无理由", "补偿")):
        return _decision(
            "faq_qa",
            need_knowledge=True,
            reason="用户咨询客服政策，需要检索知识库回答。",
        )

    return _decision(
        "unknown",
        reason="未识别到明确业务意图，按普通客服对话处理。",
    )
