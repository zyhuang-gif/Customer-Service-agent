from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.ids import new_refund_id
from app.models import Order, Refund
from app.schemas import RefundCreate, RefundOut

router = APIRouter(prefix="/refunds", tags=["refunds"])


@router.get("")
def get_refund_status(order_id: str = Query(...), db: Session = Depends(get_db)):
    rf = (
        db.query(Refund)
        .filter(Refund.order_id == order_id)
        .order_by(Refund.applied_at.desc())
        .first()
    )
    if not rf:
        return {"order_id": order_id, "status": "无", "refund": None}
    return {"order_id": order_id, "status": rf.status, "refund": RefundOut.model_validate(rf).model_dump(mode="json")}


@router.post("", response_model=RefundOut, status_code=201)
def create_refund(body: RefundCreate, response: Response, db: Session = Depends(get_db)):
    if not db.get(Order, body.order_id):
        raise HTTPException(status_code=404, detail="order not found")
    rf = Refund(
        id=new_refund_id(),
        order_id=body.order_id,
        amount=body.amount,
        reason=body.reason,
        channel=body.channel,
        status="处理中",
    )
    db.add(rf)
    db.commit()
    db.refresh(rf)
    return rf
