from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Customer, Logistics, Refund, Ticket
from app.seed import seed


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_seed_creates_scenarios():
    db = _session()
    seed(db)
    # 两个客户
    assert db.query(Customer).count() == 2
    # 剧情②：物流停滞约 3 天
    lg = db.get(Logistics, "LG002")
    assert (datetime.utcnow() - lg.last_update) >= timedelta(days=2)
    # 剧情③：退款处理中
    rf = db.query(Refund).filter(Refund.order_id == "20260531003").first()
    assert rf.status == "处理中"
    # 剧情④：高风险客户 3 条投诉
    complaints = db.query(Ticket).filter(Ticket.customer_id == "C1002", Ticket.category == "投诉").count()
    assert complaints == 3
