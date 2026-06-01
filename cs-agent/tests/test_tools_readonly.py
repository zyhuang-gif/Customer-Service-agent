from app.errors import BusinessUnavailable
from app.tools.registry import ToolRegistry


class FakeBusiness:
    def __init__(self):
        self.raise_unavailable = False

    def get_order(self, order_id):
        if self.raise_unavailable:
            raise BusinessUnavailable("down")
        if order_id == "O1":
            return {"id": "O1", "status": "已发货"}
        return None

    def get_customer(self, customer_id):
        return {"id": customer_id, "name": "张三"} if customer_id == "C1" else None

    def get_logistics(self, order_id):
        return {"order_id": order_id, "status": "运输中"} if order_id == "O1" else None

    def get_refund_status(self, order_id):
        return {"order_id": order_id, "status": "处理中", "refund": None}

    def list_customer_tickets(self, customer_id):
        return [{"id": "TK1", "category": "投诉"}]


class FakeRetriever:
    def __init__(self, results):
        self._results = results

    def retrieve(self, query):
        return self._results


def _registry(retriever_results=None):
    return ToolRegistry(business=FakeBusiness(), retriever=FakeRetriever(retriever_results or []))


def test_get_order_found():
    out = _registry().call("get_order", {"order_id": "O1"})
    assert out["status"] == "已发货"


def test_get_order_not_found_returns_tool_error():
    out = _registry().call("get_order", {"order_id": "NOPE"})
    assert out["error"] is True
    assert out["kind"] == "not_found"


def test_get_order_upstream_unavailable():
    reg = _registry()
    reg.business.raise_unavailable = True
    out = reg.call("get_order", {"order_id": "O1"})
    assert out["error"] is True
    assert out["kind"] == "upstream_unavailable"


def test_search_knowledge_hit():
    reg = _registry(retriever_results=[{"title": "物流催办", "source": "x.md", "text": "...", "score": 0.9}])
    out = reg.call("search_knowledge", {"query": "物流停了"})
    assert out["covered"] is True
    assert len(out["hits"]) == 1
    assert out["hits"][0]["title"] == "物流催办"


def test_search_knowledge_no_hit_marks_uncovered():
    reg = _registry(retriever_results=[])
    out = reg.call("search_knowledge", {"query": "未知问题"})
    assert out["covered"] is False
    assert out["hits"] == []
