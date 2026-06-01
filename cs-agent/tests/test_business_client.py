from app.errors import ToolError


def test_tool_error_to_dict():
    e = ToolError(kind="not_found", message="订单不存在", details={"order_id": "X"})
    d = e.to_dict()
    assert d["error"] is True
    assert d["kind"] == "not_found"
    assert d["message"] == "订单不存在"
    assert d["details"]["order_id"] == "X"
