from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- 出参 ----
class CustomerOut(ORMModel):
    id: str
    name: str
    phone: str
    member_level: str
    register_date: datetime


class OrderOut(ORMModel):
    id: str
    customer_id: str
    status: str
    items: list
    amount: float
    address: str
    created_at: datetime
    shipped_at: datetime | None


class LogisticsOut(ORMModel):
    id: str
    order_id: str
    carrier: str
    tracking_no: str
    status: str
    last_update: datetime
    eta: datetime | None
    traces: list


class RefundOut(ORMModel):
    id: str
    order_id: str
    status: str
    amount: float
    channel: str
    reason: str
    applied_at: datetime
    completed_at: datetime | None


class TicketOut(ORMModel):
    id: str
    customer_id: str
    order_id: str | None
    category: str
    priority: str
    status: str
    assignee: str | None
    summary: str
    history: list
    created_at: datetime
    updated_at: datetime


class CouponOut(ORMModel):
    id: str
    customer_id: str
    value: float
    reason: str
    issued_at: datetime


# ---- 入参 ----
class RefundCreate(BaseModel):
    order_id: str
    amount: float
    reason: str = ""
    channel: str = "原路退回"


class TicketCreate(BaseModel):
    customer_id: str
    order_id: str | None = None
    category: str
    summary: str = ""
    priority: str = "中"


class TicketUpdate(BaseModel):
    note: str | None = None
    status: str | None = None
    assignee: str | None = None


class AddressUpdate(BaseModel):
    new_address: str


class CouponCreate(BaseModel):
    customer_id: str
    value: float
    reason: str = ""
