from fastapi import APIRouter, HTTPException, Request

from app.auth import create_customer_access_token
from app.clients.business_client import BusinessClient
from app.customer_auth_rate_limit import customer_auth_limiter
from app.errors import BusinessUnavailable
from app.schemas_api import CustomerAuthIn, CustomerAuthOut

router = APIRouter(prefix="/customer-auth", tags=["customer-auth"])
_AUTH_ERROR = "手机号或最近订单号不匹配"
_DUMMY_CUSTOMER_ID = "__customer_auth_dummy__"


def _mask_phone(phone: str) -> str:
    if len(phone) != 11:
        return "*" * len(phone)
    return f"{phone[:3]}****{phone[-4:]}"


@router.post("/verify", response_model=CustomerAuthOut)
def verify_customer(body: CustomerAuthIn, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{body.phone}"
    retry_after = customer_auth_limiter.retry_after(rate_limit_key)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="尝试次数过多，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )

    client = BusinessClient()
    try:
        customer = client.get_customer_by_phone(body.phone)
        customer_id = customer["id"] if customer else _DUMMY_CUSTOMER_ID
        orders = client.list_orders(customer_id)
    except BusinessUnavailable as exc:
        raise HTTPException(status_code=503, detail="身份验证服务暂时不可用") from exc

    if not customer or not orders or orders[0]["id"] != body.recent_order_id:
        customer_auth_limiter.record_failure(rate_limit_key)
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)

    customer_ref = customer["id"]
    token, expires_at = create_customer_access_token(customer_ref)
    customer_auth_limiter.clear(rate_limit_key)
    return CustomerAuthOut(
        access_token=token,
        masked_phone=_mask_phone(customer.get("phone", body.phone)),
        expires_at=expires_at,
    )
