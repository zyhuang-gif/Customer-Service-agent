import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session, monkeypatch):
    from app.main import app
    from app.db import get_db
    import app.main as _main_module
    import app.db as _db_module

    # 让 lifespan 里的 get_engine() 返回同一个 SQLite engine，避免连 Postgres 超时
    # main.py 用 `from app.db import get_engine` 直接绑定了函数引用，
    # 需要同时 patch app.main 和 app.db 两处
    _sqlite_engine = db_session.bind
    monkeypatch.setattr(_main_module, "get_engine", lambda: _sqlite_engine)
    monkeypatch.setattr(_db_module, "get_engine", lambda: _sqlite_engine)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    class MockService:
        def __init__(self, db):
            self.db = db

        def start_turn(self, conversation_id, user_text):
            from app.models import Message
            self.db.add(Message(conversation_id=conversation_id, role="ai", content="您好，已收到。"))
            self.db.commit()
            return {"status": "ai_handling", "message": "您好，已收到。"}

        def resume_action(self, pid, approved, reviewer_id):
            return {"status": "ai_handling", "pending_status": "executed" if approved else "rejected", "message": "ok"}

    import app.routers.chat_router as chat_router
    import app.routers.confirm_router as confirm_router
    monkeypatch.setattr(chat_router, "build_service", lambda db: MockService(db))
    monkeypatch.setattr(confirm_router, "build_service", lambda db: MockService(db))

    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
