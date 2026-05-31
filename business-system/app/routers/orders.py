from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order
from app.schemas import AddressUpdate, OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
def list_orders(customer_id: str = Query(...), db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.customer_id == customer_id).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: str, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="order not found")
    return o


@router.patch("/{order_id}/address", response_model=OrderOut)
def change_address(order_id: str, body: AddressUpdate, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="order not found")
    o.address = body.new_address
    db.commit()
    db.refresh(o)
    return o
