"""有剧情的种子数据：可被脚本调用，也可被测试导入。"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.ids import new_refund_id
from app.models import Customer, Logistics, Order, Refund, Ticket

now = datetime.utcnow


def seed(db: Session) -> None:
    # 客户：普通客户 + 高风险投诉客户
    c_normal = Customer(id="C1001", name="张三", phone="13800000001", member_level="金")
    c_risk = Customer(id="C1002", name="李四", phone="13800000002", member_level="普通")
    db.add_all([c_normal, c_risk])

    # 剧情①：正常已签收
    db.add(Order(id="20260531001", customer_id="C1001", status="已签收",
                 items=[{"name": "运动鞋", "qty": 1}], amount=299.0, address="北京朝阳",
                 created_at=now() - timedelta(days=10), shipped_at=now() - timedelta(days=8)))
    db.add(Logistics(id="LG001", order_id="20260531001", carrier="顺丰", tracking_no="SF0001",
                     status="已签收", last_update=now() - timedelta(days=6),
                     traces=[{"time": "2026-05-23", "desc": "已签收"}]))

    # 剧情②：物流停滞 3 天（已发货但 3 天未更新）
    db.add(Order(id="20260531002", customer_id="C1001", status="已发货",
                 items=[{"name": "蓝牙耳机", "qty": 1}], amount=499.0, address="北京朝阳",
                 created_at=now() - timedelta(days=5), shipped_at=now() - timedelta(days=4)))
    db.add(Logistics(id="LG002", order_id="20260531002", carrier="圆通", tracking_no="YT0002",
                     status="运输中", last_update=now() - timedelta(days=3),
                     eta=now() - timedelta(days=1),
                     traces=[{"time": "2026-05-28", "desc": "到达转运中心后无更新"}]))

    # 剧情③：退款 5 天未到账（退款处理中超 5 天）
    db.add(Order(id="20260531003", customer_id="C1001", status="已取消",
                 items=[{"name": "保温杯", "qty": 2}], amount=158.0, address="北京朝阳",
                 created_at=now() - timedelta(days=12)))
    db.add(Refund(id=new_refund_id(), order_id="20260531003", status="处理中",
                  amount=158.0, reason="七天无理由", applied_at=now() - timedelta(days=5)))

    # 剧情④：高风险客户近 7 天 3 次投诉（使用固定 ID 避免时间戳碰撞）
    for i in range(3):
        db.add(Ticket(id=f"TK_COMPLAINT_{i + 1:03d}", customer_id="C1002",
                      category="投诉", priority="高", status="待处理",
                      summary=f"第{i + 1}次投诉：服务态度问题",
                      created_at=now() - timedelta(days=i + 1)))

    db.commit()


def run() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Customer).count() > 0:
            print("已有数据，跳过种子。")
            return
        seed(db)
        print("种子数据写入完成。")
    finally:
        db.close()


if __name__ == "__main__":
    run()
