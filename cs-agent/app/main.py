from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, get_engine
from app.routers import auth_router, chat_router, confirm_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=get_engine())
    except Exception:
        pass
    yield


app = FastAPI(title="客服 Agent 服务", lifespan=lifespan)
app.include_router(auth_router.router)
app.include_router(chat_router.router)
app.include_router(confirm_router.router)


@app.get("/health/live")
def health_live():
    return {"status": "ok"}
