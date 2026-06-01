from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.routers import customers, logistics, orders, refunds


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        # 测试环境无 Postgres；fixture 已用 SQLite 建表
        pass
    yield


app = FastAPI(title="业务系统服务", lifespan=lifespan)

app.include_router(customers.router)
app.include_router(orders.router)
app.include_router(logistics.router)
app.include_router(refunds.router)


@app.get("/health/live")
def health_live():
    return {"status": "ok"}
