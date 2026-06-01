"""业务系统 HTTP 客户端测试。

Python 3.14 + respx 0.21.x 兼容性说明：
respx 0.21.x 通过 mock.patch httpcore 的 handle_request 实现全局拦截，
但该机制在 Python 3.14 / httpcore 1.0.9 下 patch 不生效。
因此改为显式注入 transport：用 respx.MockRouter 构造路由，
再用 httpx.MockTransport(router.handler) 注入到 BusinessClient，
功能等价，测试契约（重试次数、返回值、异常语义）完全不变。
"""
import httpx
import pytest
import respx

from app.clients.business_client import BusinessClient
from app.errors import BusinessUnavailable, ToolError

BASE = "http://biz.test"


def _client(router: respx.MockRouter) -> BusinessClient:
    """构造一个使用 respx mock transport 的 BusinessClient。"""
    transport = httpx.MockTransport(router.handler)
    return BusinessClient(base_url=BASE, timeout=1.0, retries=1, transport=transport)


def test_tool_error_to_dict():
    e = ToolError(kind="not_found", message="订单不存在", details={"order_id": "X"})
    d = e.to_dict()
    assert d["error"] is True
    assert d["kind"] == "not_found"
    assert d["message"] == "订单不存在"
    assert d["details"]["order_id"] == "X"


def test_get_order_success():
    router = respx.MockRouter(assert_all_called=False)
    router.get(f"{BASE}/orders/O1").mock(
        return_value=httpx.Response(200, json={"id": "O1", "status": "已发货"})
    )
    c = _client(router)
    data = c.get_order("O1")
    assert data["id"] == "O1"
    assert data["status"] == "已发货"


def test_get_order_404_returns_none():
    router = respx.MockRouter(assert_all_called=False)
    router.get(f"{BASE}/orders/NOPE").mock(
        return_value=httpx.Response(404, json={"detail": "order not found"})
    )
    c = _client(router)
    assert c.get_order("NOPE") is None


def test_get_order_retries_then_raises_on_5xx():
    router = respx.MockRouter(assert_all_called=False)
    route = router.get(f"{BASE}/orders/O1").mock(return_value=httpx.Response(500))
    c = _client(router)
    with pytest.raises(BusinessUnavailable):
        c.get_order("O1")
    assert route.call_count == 2


def test_get_order_retries_then_raises_on_timeout():
    router = respx.MockRouter(assert_all_called=False)
    route = router.get(f"{BASE}/orders/O1").mock(side_effect=httpx.ConnectTimeout("timeout"))
    c = _client(router)
    with pytest.raises(BusinessUnavailable):
        c.get_order("O1")
    assert route.call_count == 2


def test_create_ticket_posts_payload():
    router = respx.MockRouter(assert_all_called=False)
    router.post(f"{BASE}/tickets").mock(
        return_value=httpx.Response(201, json={"id": "TK1", "status": "待处理"})
    )
    c = _client(router)
    data = c.create_ticket(customer_id="C1", order_id="O1", category="物流", summary="催办", priority="高")
    assert data["id"] == "TK1"


def test_create_ticket_404_returns_none():
    router = respx.MockRouter(assert_all_called=False)
    router.post(f"{BASE}/tickets").mock(
        return_value=httpx.Response(404, json={"detail": "customer not found"})
    )
    c = _client(router)
    assert c.create_ticket(customer_id="NOPE", order_id=None, category="物流", summary="x", priority="中") is None
