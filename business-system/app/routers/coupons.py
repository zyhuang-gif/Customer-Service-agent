from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.ids import new_coupon_id
from app.models import Coupon, Customer
from app.schemas import CouponCreate, CouponOut

router = APIRouter(prefix="/coupons", tags=["coupons"])


@router.post("", response_model=CouponOut, status_code=201)
def issue_coupon(body: CouponCreate, db: Session = Depends(get_db)):
    if not db.get(Customer, body.customer_id):
        raise HTTPException(status_code=404, detail="customer not found")
    cp = Coupon(
        id=new_coupon_id(),
        customer_id=body.customer_id,
        value=body.value,
        reason=body.reason,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp
