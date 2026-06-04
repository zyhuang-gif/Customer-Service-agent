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
_ORDER_TOKEN = re.compile(r"(?<![A-Za-z0-9-])([A-Za-z0-9][A-Za-z0-9-]{2,63})(?![A-Za-z0-9-])")
_ORDER_CONTEXT = re.compile(r"(?:订单号|订单|单号)(?:是|为|[:：#])?\s*$")
_PHONE_CONTEXT = re.compile(r"(?:手机号|手机号码|电话|电话号码)(?:是|为|[:：#])?\s*$")


@dataclass(frozen=True)
class CustomerRequest:
    is_personal: bool
    order_ids: set[str]


def _normalize_order_id(value: str) -> str:
    return value.upper()


def _has_nearby_context(pattern: re.Pattern[str], message: str, token_start: int) -> bool:
    return bool(pattern.search(message[max(0, token_start - 12) : token_start]))


def _looks_like_order_id(value: str, *, has_order_context: bool, has_phone_context: bool) -> bool:
    if has_order_context:
        return any(char.isdigit() for char in value)
    if value.isdigit():
        return len(value) >= 8 and not has_phone_context
    if not any(char.isdigit() for char in value):
        return False
    upper = _normalize_order_id(value)
    return "-" in value or upper.startswith(("O", "ORD"))


def classify_customer_request(message: str) -> CustomerRequest:
    order_ids = set()
    for match in _ORDER_TOKEN.finditer(message):
        value = match.group(1)
        if _looks_like_order_id(
            value,
            has_order_context=_has_nearby_context(_ORDER_CONTEXT, message, match.start()),
            has_phone_context=_has_nearby_context(_PHONE_CONTEXT, message, match.start()),
        ):
            order_ids.add(_normalize_order_id(value))
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
