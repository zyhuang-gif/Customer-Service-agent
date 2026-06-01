from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.ids import new_ticket_id
from app.models import Ticket
from app.schemas import TicketCreate, TicketOut, TicketUpdate

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
def list_tickets(customer_id: str = Query(...), db: Session = Depends(get_db)):
    return db.query(Ticket).filter(Ticket.customer_id == customer_id).all()


@router.post("", response_model=TicketOut, status_code=201)
def create_ticket(body: TicketCreate, db: Session = Depends(get_db)):
    tk = Ticket(
        id=new_ticket_id(),
        customer_id=body.customer_id,
        order_id=body.order_id,
        category=body.category,
        summary=body.summary,
        priority=body.priority,
        status="待处理",
        history=[],
    )
    db.add(tk)
    db.commit()
    db.refresh(tk)
    return tk


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: str, body: TicketUpdate, db: Session = Depends(get_db)):
    tk = db.get(Ticket, ticket_id)
    if not tk:
        raise HTTPException(status_code=404, detail="ticket not found")
    history = list(tk.history or [])
    entry = {"time": datetime.utcnow().isoformat()}
    if body.status is not None:
        tk.status = body.status
        entry["status"] = body.status
    if body.assignee is not None:
        tk.assignee = body.assignee
        entry["assignee"] = body.assignee
    if body.note is not None:
        entry["note"] = body.note
    history.append(entry)
    tk.history = history
    tk.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(tk)
    return tk
