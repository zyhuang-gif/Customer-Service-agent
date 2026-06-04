from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.deps import warmup
from app.db import Base, get_engine
from app.schema_migrations import ensure_conversation_last_message_at
from app.routers import (
    auth_router,
    agent_desk_router,
    chat_router,
    confirm_router,
    conversation_router,
    customer_auth_router,
    dashboard_router,
    knowledge_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass
    else:
        ensure_conversation_last_message_at(engine)
    # 预热：提前灌知识库 + 构造图/checkpointer，避免首个 /chat 请求超时。
    # 失败不阻断启动（如测试环境无 Postgres/无 key）。测试会 monkeypatch warmup。
    try:
        warmup()
    except Exception:
        pass
    yield


app = FastAPI(title="客服 Agent 服务", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(customer_auth_router.router)
app.include_router(agent_desk_router.router)
app.include_router(chat_router.router)
app.include_router(confirm_router.router)
app.include_router(conversation_router.router)
app.include_router(dashboard_router.router)
app.include_router(knowledge_router.router)


@app.get("/health/live")
def health_live():
    return {"status": "ok"}
