from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String, index=True)
    member_level: Mapped[str] = mapped_column(String, default="普通")  # 普通/银/金/钻
    register_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String)  # 待付款/待发货/已发货/已签收/已取消
    items: Mapped[list] = mapped_column(JSON, default=list)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    address: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Logistics(Base):
    __tablename__ = "logistics"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    carrier: Mapped[str] = mapped_column(String)
    tracking_no: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # 揽收/运输中/派送中/已签收/异常
    last_update: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    eta: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    traces: Mapped[list] = mapped_column(JSON, default=list)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="处理中")  # 处理中/已到账/失败
    amount: Mapped[float] = mapped_column(Float)
    channel: Mapped[str] = mapped_column(String, default="原路退回")
    reason: Mapped[str] = mapped_column(String, default="")
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[Optional[str]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    category: Mapped[str] = mapped_column(String)  # 物流/退款/售后/投诉/咨询
    priority: Mapped[str] = mapped_column(String, default="中")  # 低/中/高/紧急
    status: Mapped[str] = mapped_column(String, default="待处理")
    assignee: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    summary: Mapped[str] = mapped_column(String, default="")
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Coupon(Base):
    __tablename__ = "coupons"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    value: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String, default="")
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
