from fastapi import APIRouter, HTTPException

from app.auth import create_customer_access_token
from app.clients.business_client import BusinessClient
from app.schemas_api import CustomerAuthIn, CustomerAuthOut

router = APIRouter(prefix="/customer-auth", tags=["customer-auth"])
_AUTH_ERROR = "手机号或最近订单号不匹配"


def _mask_phone(phone: str) -> str:
    if len(phone) != 11:
        return "*" * len(phone)
    return f"{phone[:3]}****{phone[-4:]}"


@router.post("/verify", response_model=CustomerAuthOut)
def verify_customer(body: CustomerAuthIn):
    client = BusinessClient()
    customer = client.get_customer_by_phone(body.phone)
    if not customer:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)

    orders = client.list_orders(customer["id"])
    if not orders:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)

    latest_order = max(orders, key=lambda order: (order["created_at"], order["id"]))
    if latest_order["id"] != body.recent_order_id:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)

    customer_ref = customer["id"]
    token, expires_at = create_customer_access_token(customer_ref)
    return CustomerAuthOut(
        access_token=token,
        masked_phone=_mask_phone(customer.get("phone", body.phone)),
        expires_at=expires_at,
    )
