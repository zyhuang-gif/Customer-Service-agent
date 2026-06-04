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
_ORDER_TOKEN = re.compile(r"(?<![A-Za-z0-9-])([A-Za-z0-9][A-Za-z0-9-]{5,63})(?![A-Za-z0-9-])")


@dataclass(frozen=True)
class CustomerRequest:
    is_personal: bool
    order_ids: set[str]


def _looks_like_order_id(value: str) -> bool:
    if value.isdigit():
        return value.startswith("20") and len(value) >= 10
    upper = value.upper()
    return (
        upper.startswith("O-")
        or (any(char.isalpha() for char in value) and any(char.isdigit() for char in value))
    )


def classify_customer_request(message: str) -> CustomerRequest:
    order_ids = {
        match.group(1)
        for match in _ORDER_TOKEN.finditer(message)
        if _looks_like_order_id(match.group(1))
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
    owned_ids = {str(order.get("id")) for order in orders}
    return order_ids <= owned_ids
