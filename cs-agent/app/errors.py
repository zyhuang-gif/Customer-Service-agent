"""跨层的结构化错误。工具层捕获后返回给 Agent，Agent 据此如实回复，绝不编造。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolError:
    """结构化工具错误。kind 用于 Agent/编排层判断如何处置。"""

    kind: str  # "not_found" | "upstream_unavailable" | "bad_request" | "internal"
    message: str  # 给人看的中文说明
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"error": True, "kind": self.kind, "message": self.message, "details": self.details}


class BusinessUnavailable(Exception):
    """业务系统重试后仍不可用（超时/连接失败/5xx）。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
