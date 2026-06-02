"""工具风险分级表（安全红线的配置化来源）。调档位改这里，不动逻辑。"""
from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    READONLY = "readonly"
    LOW_WRITE = "low_write"
    HIGH_WRITE = "high_write"
    CONTROL = "control"


TOOL_RISK: dict[str, RiskLevel] = {
    "search_knowledge": RiskLevel.READONLY,
    "get_customer": RiskLevel.READONLY,
    "get_order": RiskLevel.READONLY,
    "get_logistics": RiskLevel.READONLY,
    "get_refund_status": RiskLevel.READONLY,
    "list_customer_tickets": RiskLevel.READONLY,
    "create_ticket": RiskLevel.LOW_WRITE,
    "update_ticket": RiskLevel.LOW_WRITE,
    "apply_refund": RiskLevel.HIGH_WRITE,
    "change_address": RiskLevel.HIGH_WRITE,
    "issue_coupon": RiskLevel.HIGH_WRITE,
    "transfer_to_human": RiskLevel.CONTROL,
}


def risk_of(tool_name: str) -> RiskLevel:
    return TOOL_RISK[tool_name]


def is_high_risk(tool_name: str) -> bool:
    return TOOL_RISK.get(tool_name) == RiskLevel.HIGH_WRITE
