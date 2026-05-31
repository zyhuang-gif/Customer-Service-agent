from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer
from app.schemas import CustomerOut

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=CustomerOut)
def get_customer_by_phone(phone: str = Query(...), db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.phone == phone).first()
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")
    return c


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")
    return c
