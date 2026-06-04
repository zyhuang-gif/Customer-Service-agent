import re
from dataclasses import dataclass

from app.clients.business_client import BusinessClient


_PERSONAL_PHRASES = (
    "我的订单",
    "查订单",
    "查询订单",
    "查物流",
    "物流进度",
    "退款进度",
    "退款状态",
)
_ORDER_REFERENCE = re.compile(
    r"(?:订单编号|订单号|订单|单号)\s*(?:[:：]\s*)?"
    r"([A-Za-z0-9][A-Za-z0-9-]{0,63})(?![A-Za-z0-9-])"
)


@dataclass(frozen=True)
class CustomerRequest:
    is_personal: bool
    order_ids: set[str]


def _normalize_order_id(value: str) -> str:
    return value.upper()


def classify_customer_request(message: str) -> CustomerRequest:
    order_ids = {
        _normalize_order_id(match.group(1))
        for match in _ORDER_REFERENCE.finditer(message)
    }
    return CustomerRequest(
        is_personal=bool(order_ids) or any(phrase in message for phrase in _PERSONAL_PHRASES),
        order_ids=order_ids,
    )


def customer_owns_orders(customer_ref: str, order_ids: set[str]) -> bool:
    client = BusinessClient()
    customer = client.get_customer_by_phone(customer_ref)
    if not customer:
        return False
    orders = client.list_orders(customer["id"]) or []
    owned_ids = {_normalize_order_id(str(order.get("id"))) for order in orders}
    normalized_order_ids = {_normalize_order_id(order_id) for order_id in order_ids}
    return normalized_order_ids <= owned_ids
