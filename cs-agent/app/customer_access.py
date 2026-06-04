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
    "我要退款",
    "申请退款",
    "要求退款",
    "提交退款",
    "退钱",
    "改地址",
    "修改地址",
    "更换地址",
    "发券",
    "补偿券",
)
_ORDER_CONTEXT = re.compile(
    r"(?:订单编号|订单号|订单|单号)(?:\s*(?:是|为|#|[:：]))?\s*"
)
_ORDER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,63}(?![A-Za-z0-9-])")
_ORDER_SEPARATOR = re.compile(r"(?:\s*(?:和|与|、|,)\s*|\s+)")
_ACTION_ORDER = re.compile(
    r"(?:查(?:一下)?|查询|我要退款|申请退款|要求退款|提交退款|退钱)"
    r"\s*([A-Za-z0-9][A-Za-z0-9-]{0,63})(?![A-Za-z0-9-])"
)
_ORDER_BEFORE_PERSONAL_DETAIL = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9-]{0,63})(?![A-Za-z0-9-])\s*的?"
    r"(?:物流|退款(?:进度|状态)?|收货地址)"
)


class CustomerAccessValidationError(RuntimeError):
    """Business-system data was too malformed to make a safe access decision."""


@dataclass(frozen=True)
class CustomerRequest:
    is_personal: bool
    order_ids: set[str]


def _normalize_order_id(value: str) -> str:
    return value.upper()


def _order_ids_after_context(message: str, start: int) -> set[str]:
    order_ids = set()
    position = start
    while match := _ORDER_ID.match(message, position):
        order_ids.add(_normalize_order_id(match.group()))
        separator = _ORDER_SEPARATOR.match(message, match.end())
        if not separator:
            break
        position = separator.end()
    return order_ids


def classify_customer_request(message: str) -> CustomerRequest:
    order_ids = set()
    for match in _ORDER_CONTEXT.finditer(message):
        order_ids.update(_order_ids_after_context(message, match.end()))
    for pattern in (_ACTION_ORDER, _ORDER_BEFORE_PERSONAL_DETAIL):
        order_ids.update(_normalize_order_id(match.group(1)) for match in pattern.finditer(message))
    return CustomerRequest(
        is_personal=bool(order_ids) or any(phrase in message for phrase in _PERSONAL_PHRASES),
        order_ids=order_ids,
    )


def customer_owns_orders(customer_ref: str, order_ids: set[str]) -> bool:
    client = BusinessClient()
    customer = client.get_customer(customer_ref)
    if customer is None:
        return False
    if not isinstance(customer, dict) or not customer.get("id"):
        raise CustomerAccessValidationError("malformed customer response")
    if str(customer["id"]) != customer_ref:
        raise CustomerAccessValidationError("mismatched customer response")

    customer_id = str(customer["id"])
    for requested_id in order_ids:
        order = client.get_order(requested_id)
        if order is None:
            return False
        if not isinstance(order, dict) or not order.get("id") or not order.get("customer_id"):
            raise CustomerAccessValidationError("malformed order response")
        if _normalize_order_id(str(order["id"])) != _normalize_order_id(requested_id):
            raise CustomerAccessValidationError("mismatched order response")
        if str(order["customer_id"]) != customer_id:
            return False
    return True
