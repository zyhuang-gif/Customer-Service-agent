from app.tools.registry import ToolRegistry


class FakeBusiness:
    def __init__(self):
        self.created = None
        self.updated = None

    def create_ticket(self, customer_id, order_id, category, summary, priority):
        if customer_id == "NOPE":
            return None
        self.created = dict(customer_id=customer_id, order_id=order_id, category=category, summary=summary, priority=priority)
        return {"id": "TK1", "status": "待处理", **self.created}

    def update_ticket(self, ticket_id, note=None, status=None, assignee=None):
        if ticket_id == "NOPE":
            return None
        self.updated = dict(ticket_id=ticket_id, note=note, status=status, assignee=assignee)
        return {"id": ticket_id, "status": status or "待处理"}


def _registry():
    return ToolRegistry(business=FakeBusiness(), retriever=None)


def test_create_ticket_success():
    reg = _registry()
    out = reg.call("create_ticket", {"customer_id": "C1", "order_id": "O1", "category": "物流", "summary": "催办", "priority": "高"})
    assert out["id"] == "TK1"
    assert reg.business.created["category"] == "物流"


def test_create_ticket_customer_not_found():
    reg = _registry()
    out = reg.call("create_ticket", {"customer_id": "NOPE", "order_id": None, "category": "物流", "summary": "x", "priority": "中"})
    assert out["error"] is True
    assert out["kind"] == "not_found"


def test_update_ticket_success():
    reg = _registry()
    out = reg.call("update_ticket", {"ticket_id": "TK1", "status": "已解决", "note": "已处理"})
    assert out["status"] == "已解决"


def test_update_ticket_not_found():
    reg = _registry()
    out = reg.call("update_ticket", {"ticket_id": "NOPE", "status": "已解决"})
    assert out["error"] is True
    assert out["kind"] == "not_found"
