"""灌入坐席账号种子。"""
from __future__ import annotations

from app.auth import hash_password
from app.db import Base, get_engine, get_session_factory
from app.models import User


def seed_users() -> None:
    Base.metadata.create_all(bind=get_engine())
    db = get_session_factory()()
    try:
        if db.query(User).count() > 0:
            print("已有用户，跳过。")
            return
        db.add_all([
            User(username="agent", password_hash=hash_password("agent123"), role="agent", display_name="客服一号"),
            User(username="admin", password_hash=hash_password("admin123"), role="admin", display_name="主管"),
        ])
        db.commit()
        print("坐席种子写入完成：agent/agent123, admin/admin123")
    finally:
        db.close()


if __name__ == "__main__":
    seed_users()
