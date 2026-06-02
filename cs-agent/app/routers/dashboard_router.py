from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dashboard import build_dashboard_summary
from app.db import get_db
from app.routers.auth_router import current_user

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), user=Depends(current_user)):
    return build_dashboard_summary(db)
