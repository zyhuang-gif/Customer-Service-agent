from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Logistics
from app.schemas import LogisticsOut

router = APIRouter(prefix="/logistics", tags=["logistics"])


@router.get("", response_model=LogisticsOut)
def get_logistics(order_id: str = Query(...), db: Session = Depends(get_db)):
    lg = db.query(Logistics).filter(Logistics.order_id == order_id).first()
    if not lg:
        raise HTTPException(status_code=404, detail="logistics not found")
    return lg
