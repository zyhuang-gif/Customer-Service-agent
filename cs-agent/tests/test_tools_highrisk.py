import pytest

from app.tools.registry import ToolRegistry
from app.tools.risk import RiskLevel, risk_of


class SpyBusiness:
    """任何方法被调用都记录——高风险工具绝不能碰它。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _rec(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"should": "never be called"}
        return _rec


@pytest.mark.parametrize("tool,params", [
    ("apply_refund", {"order_id": "O1", "amount": 100.0, "reason": "x"}),
    ("change_address", {"order_id": "O1", "new_address": "上海"}),
    ("issue_coupon", {"customer_id": "C1", "value": 20.0, "reason": "补偿"}),
])
def test_high_risk_returns_pending_and_never_calls_business(tool, params):
    spy = SpyBusiness()
    reg = ToolRegistry(business=spy, retriever=None)
    out = reg.call(tool, params)
    assert out["pending_action"] is True
    assert out["requires_confirmation"] is True
    assert out["tool_name"] == tool
    assert out["params"] == params
    assert spy.calls == []


def test_all_high_risk_tools_are_high_write():
    for tool in ("apply_refund", "change_address", "issue_coupon"):
        assert risk_of(tool) == RiskLevel.HIGH_WRITE
