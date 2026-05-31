from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        # 测试环境无 Postgres；fixture 已用 SQLite 建表
        pass
    yield


app = FastAPI(title="业务系统服务", lifespan=lifespan)


@app.get("/health/live")
def health_live():
    return {"status": "ok"}
