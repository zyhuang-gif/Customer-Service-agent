from app.tools.risk import TOOL_RISK, RiskLevel, risk_of, is_high_risk


def test_all_ten_tools_classified():
    expected = {
        "search_knowledge", "get_customer", "get_order", "get_logistics",
        "get_refund_status", "list_customer_tickets",
        "create_ticket", "update_ticket",
        "apply_refund", "change_address", "issue_coupon",
    }
    assert set(TOOL_RISK.keys()) == expected


def test_readonly_classification():
    assert risk_of("get_order") == RiskLevel.READONLY
    assert risk_of("search_knowledge") == RiskLevel.READONLY


def test_low_write_classification():
    assert risk_of("create_ticket") == RiskLevel.LOW_WRITE
    assert risk_of("update_ticket") == RiskLevel.LOW_WRITE


def test_high_write_classification():
    assert risk_of("apply_refund") == RiskLevel.HIGH_WRITE
    assert risk_of("change_address") == RiskLevel.HIGH_WRITE
    assert risk_of("issue_coupon") == RiskLevel.HIGH_WRITE


def test_is_high_risk_helper():
    assert is_high_risk("apply_refund") is True
    assert is_high_risk("get_order") is False
    assert is_high_risk("create_ticket") is False
