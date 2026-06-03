from fastapi import APIRouter, Depends, HTTPException

from app.clients.business_client import BusinessClient
from app.errors import BusinessUnavailable
from app.routers.auth_router import current_user

router = APIRouter(prefix="/agent-desk", tags=["agent-desk"])


@router.get("/orders/{order_id}")
def get_order_detail(order_id: str, user=Depends(current_user)):
    client = BusinessClient()
    try:
        order = client.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")

        customer_id = order.get("customer_id")
        customer = client.get_customer(customer_id) if customer_id else None
        logistics = client.get_logistics(order_id)
        refund = client.get_refund_status(order_id)
        tickets = client.list_customer_tickets(customer_id) if customer_id else []
    except HTTPException:
        raise
    except BusinessUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    order_tickets = [
        ticket for ticket in (tickets or [])
        if ticket.get("order_id") == order_id
    ]
    return {
        "order": order,
        "customer": customer,
        "logistics": logistics,
        "refund": refund,
        "tickets": order_tickets,
    }
