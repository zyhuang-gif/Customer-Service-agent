"""工具的统一返回结构与高风险待确认意图。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingActionIntent:
    """高风险工具不执行业务 API，只产出此意图。编排层据此写 pending_actions 表。"""

    tool_name: str
    params: dict[str, Any]
    risk_level: str = "high_write"
    requires_confirmation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "pending_action": True,
            "tool_name": self.tool_name,
            "params": self.params,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
        }
