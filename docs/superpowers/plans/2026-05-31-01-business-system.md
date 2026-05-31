# 业务系统服务（business-system）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建"被集成的电商业务后台"——一个独立的 FastAPI + Postgres 服务，提供订单/物流/退款/工单/客户/优惠券的 REST API 和有剧情的种子数据，对客服 Agent 一无所知。

**Architecture:** 单 FastAPI 应用，SQLAlchemy 2.0 ORM 映射到 Postgres `biz` schema；按资源拆分 router；Pydantic v2 做出入参校验；测试用内存 SQLite + 依赖覆盖，不依赖运行中的 Postgres。所有表用通用 SQLAlchemy 类型（`JSON` 而非 Postgres 专有 `JSONB`），保证测试可跨库。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy 2.0、Pydantic v2 + pydantic-settings、psycopg2-binary（Postgres 驱动）、pytest + httpx（TestClient）。

---

## 文件结构

```
business-system/
├─ app/
│  ├─ __init__.py
│  ├─ config.py            # 配置（数据库 URL 等）
│  ├─ database.py          # SQLAlchemy engine / SessionLocal / Base / get_db
│  ├─ models.py            # 全部 ORM 模型（6 张表）
│  ├─ schemas.py           # Pydantic 出入参模型
│  ├─ ids.py               # 业务编号生成（退款/工单/优惠券）
│  ├─ main.py              # FastAPI app + 健康检查 + 挂载 router
│  ├─ seed.py              # 有剧情的种子数据脚本
│  └─ routers/
│     ├─ __init__.py
│     ├─ customers.py
│     ├─ orders.py
│     ├─ logistics.py
│     ├─ refunds.py
│     ├─ tickets.py
│     └─ coupons.py
├─ tests/
│  ├─ conftest.py          # SQLite 内存库 + TestClient fixture
│  ├─ test_health.py
│  ├─ test_customers.py
│  ├─ test_orders.py
│  ├─ test_logistics.py
│  ├─ test_refunds.py
│  ├─ test_tickets.py
│  └─ test_coupons.py
├─ requirements.txt
├─ pyproject.toml          # pytest 配置
├─ Dockerfile
└─ .env.example
```

**职责边界：** `models.py` 只定义表；`schemas.py` 只定义 API 契约；每个 router 文件只管一个资源的端点；`database.py` 是唯一的会话来源（测试通过覆盖 `get_db` 注入 SQLite）。

**ID 约定：** `customers.id`、`orders.id` 用有业务含义的字符串编号（种子里指定，如 `C1001`、`20260531001`）。新建实体（退款/工单/优惠券）的 id 由 `app/ids.py` 生成带前缀的短编号（`RF`/`TK`/`CP` + 时间戳序号）。

---

## Task 1: 项目脚手架 + 配置 + 数据库基础

**Files:**
- Create: `business-system/requirements.txt`
- Create: `business-system/pyproject.toml`
- Create: `business-system/app/__init__.py`
- Create: `business-system/app/config.py`
- Create: `business-system/app/database.py`

- [ ] **Step 1: 写依赖清单**

`business-system/requirements.txt`:
```
fastapi==0.115.5
uvicorn[standard]==0.32.1
sqlalchemy==2.0.36
pydantic==2.10.3
pydantic-settings==2.6.1
psycopg2-binary==2.9.10
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 2: 写 pytest 配置**

`business-system/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "-v"
```

- [ ] **Step 3: 创建包标记与配置**

`business-system/app/__init__.py`: （空文件）

`business-system/app/config.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 默认本地 Postgres；docker-compose 会用环境变量覆盖
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/cs"
    db_schema: str = "biz"


settings = Settings()
```

- [ ] **Step 4: 创建数据库会话基础**

`business-system/app/database.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: 安装依赖并提交**

Run:
```bash
cd business-system && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
```
Expected: 安装成功，无报错。

```bash
git add business-system/requirements.txt business-system/pyproject.toml business-system/app/__init__.py business-system/app/config.py business-system/app/database.py
git commit -m "chore: business-system 脚手架与数据库基础"
```

---

## Task 2: ORM 模型（6 张表）

**Files:**
- Create: `business-system/app/models.py`
- Test: `business-system/tests/conftest.py`、`business-system/tests/test_health.py`（建表冒烟）

- [ ] **Step 1: 写 ORM 模型**

`business-system/app/models.py`:
```python
from datetime import datetime

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
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Logistics(Base):
    __tablename__ = "logistics"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    carrier: Mapped[str] = mapped_column(String)
    tracking_no: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # 揽收/运输中/派送中/已签收/异常
    last_update: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    eta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    category: Mapped[str] = mapped_column(String)  # 物流/退款/售后/投诉/咨询
    priority: Mapped[str] = mapped_column(String, default="中")  # 低/中/高/紧急
    status: Mapped[str] = mapped_column(String, default="待处理")
    assignee: Mapped[str | None] = mapped_column(String, nullable=True)
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
```

- [ ] **Step 2: 写测试 fixture（SQLite 内存库 + TestClient）**

`business-system/tests/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 3: 写健康检查测试（先失败）**

`business-system/tests/test_health.py`:
```python
def test_health_live(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 4: 跑测试确认失败**

Run: `cd business-system && .venv/Scripts/pytest tests/test_health.py -v`
Expected: FAIL（`app.main` 尚不存在，ImportError）

- [ ] **Step 5: 提交模型**

```bash
git add business-system/app/models.py business-system/tests/conftest.py business-system/tests/test_health.py
git commit -m "feat: business-system ORM 模型与测试 fixture"
```

---

## Task 3: FastAPI 应用入口 + 健康检查

**Files:**
- Create: `business-system/app/main.py`

- [ ] **Step 1: 写应用入口（先只挂健康检查）**

`business-system/app/main.py`:
```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表（Postgres 与本地均适用；测试用 fixture 自建表，不走这里）
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="业务系统服务", lifespan=lifespan)


@app.get("/health/live")
def health_live():
    return {"status": "ok"}
```

> 注意：测试 fixture 用 `TestClient(app)` 会触发 lifespan，进而对 `engine`（默认 Postgres）建表。为避免测试连 Postgres，下一步把建表挪到只在非测试时执行。

- [ ] **Step 2: 让 lifespan 建表对测试无害**

把 `app/main.py` 的 lifespan 改为容错——建表失败（如无 Postgres）不阻断启动，测试 fixture 已自行建表：
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        # 测试环境无 Postgres；fixture 已用 SQLite 建表
        pass
    yield
```

- [ ] **Step 3: 跑测试确认通过**

Run: `cd business-system && .venv/Scripts/pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add business-system/app/main.py
git commit -m "feat: business-system FastAPI 入口与健康检查"
```

---

## Task 4: Pydantic schemas + ID 生成器

**Files:**
- Create: `business-system/app/ids.py`
- Create: `business-system/app/schemas.py`

- [ ] **Step 1: 写 ID 生成器**

`business-system/app/ids.py`:
```python
from datetime import datetime


def _gen(prefix: str) -> str:
    return f"{prefix}{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[:-3]}"


def new_refund_id() -> str:
    return _gen("RF")


def new_ticket_id() -> str:
    return _gen("TK")


def new_coupon_id() -> str:
    return _gen("CP")
```

- [ ] **Step 2: 写 Pydantic schemas**

`business-system/app/schemas.py`:
```python
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
```

- [ ] **Step 3: 提交**

```bash
git add business-system/app/ids.py business-system/app/schemas.py
git commit -m "feat: business-system Pydantic schemas 与 ID 生成器"
```

---

## Task 5: 客户与订单只读 API

**Files:**
- Create: `business-system/app/routers/__init__.py`（空）
- Create: `business-system/app/routers/customers.py`
- Create: `business-system/app/routers/orders.py`
- Modify: `business-system/app/main.py`（挂载 router）
- Test: `business-system/tests/test_customers.py`、`business-system/tests/test_orders.py`

- [ ] **Step 1: 写测试（先失败）**

`business-system/tests/test_customers.py`:
```python
from app.database import get_db
from app.models import Customer


def _seed_customer(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Customer(id="C1001", name="张三", phone="13800000001", member_level="金"))
    db.commit()


def test_get_customer_by_id(client):
    _seed_customer(client)
    resp = client.get("/customers/C1001")
    assert resp.status_code == 200
    assert resp.json()["name"] == "张三"
    assert resp.json()["member_level"] == "金"


def test_get_customer_by_phone(client):
    _seed_customer(client)
    resp = client.get("/customers", params={"phone": "13800000001"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "C1001"


def test_get_customer_not_found(client):
    resp = client.get("/customers/NOPE")
    assert resp.status_code == 404
```

`business-system/tests/test_orders.py`:
```python
from app.database import get_db
from app.models import Customer, Order


def _seed(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Customer(id="C1001", name="张三", phone="13800000001"))
    db.add(Order(id="O1", customer_id="C1001", status="已发货",
                 items=[{"name": "鞋", "qty": 1}], amount=299.0, address="北京"))
    db.commit()


def test_get_order_by_id(client):
    _seed(client)
    resp = client.get("/orders/O1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "已发货"


def test_list_orders_by_customer(client):
    _seed(client)
    resp = client.get("/orders", params={"customer_id": "C1001"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == "O1"


def test_get_order_not_found(client):
    resp = client.get("/orders/NOPE")
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd business-system && .venv/Scripts/pytest tests/test_customers.py tests/test_orders.py -v`
Expected: FAIL（404 路由不存在 / 返回 404 但 import 路径 OK）

- [ ] **Step 3: 写 customers 路由**

`business-system/app/routers/__init__.py`: （空文件）

`business-system/app/routers/customers.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer
from app.schemas import CustomerOut

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=CustomerOut)
def get_customer_by_phone(phone: str = Query(...), db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.phone == phone).first()
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")
    return c


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="customer not found")
    return c
```

- [ ] **Step 4: 写 orders 路由**

`business-system/app/routers/orders.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order
from app.schemas import OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
def list_orders(customer_id: str = Query(...), db: Session = Depends(get_db)):
    return db.query(Order).filter(Order.customer_id == customer_id).all()


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: str, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="order not found")
    return o
```

- [ ] **Step 5: 挂载 router 到 main**

修改 `business-system/app/main.py`，在 `app = FastAPI(...)` 之后加：
```python
from app.routers import customers, orders

app.include_router(customers.router)
app.include_router(orders.router)
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd business-system && .venv/Scripts/pytest tests/test_customers.py tests/test_orders.py -v`
Expected: PASS（6 个测试全过）

- [ ] **Step 7: 提交**

```bash
git add business-system/app/routers/__init__.py business-system/app/routers/customers.py business-system/app/routers/orders.py business-system/app/main.py business-system/tests/test_customers.py business-system/tests/test_orders.py
git commit -m "feat: business-system 客户与订单只读 API"
```

---

## Task 6: 改地址 API（PATCH /orders/{id}/address）

**Files:**
- Modify: `business-system/app/routers/orders.py`
- Test: `business-system/tests/test_orders.py`（追加）

- [ ] **Step 1: 追加测试（先失败）**

在 `business-system/tests/test_orders.py` 末尾追加：
```python
def test_change_address(client):
    _seed(client)
    resp = client.patch("/orders/O1/address", json={"new_address": "上海浦东"})
    assert resp.status_code == 200
    assert resp.json()["address"] == "上海浦东"


def test_change_address_not_found(client):
    resp = client.patch("/orders/NOPE/address", json={"new_address": "上海"})
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd business-system && .venv/Scripts/pytest tests/test_orders.py -v`
Expected: FAIL（405/404，端点不存在）

- [ ] **Step 3: 实现改地址端点**

在 `business-system/app/routers/orders.py` 顶部 import 追加 `AddressUpdate`：
```python
from app.schemas import AddressUpdate, OrderOut
```
文件末尾追加：
```python
@router.patch("/{order_id}/address", response_model=OrderOut)
def change_address(order_id: str, body: AddressUpdate, db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="order not found")
    o.address = body.new_address
    db.commit()
    db.refresh(o)
    return o
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd business-system && .venv/Scripts/pytest tests/test_orders.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add business-system/app/routers/orders.py business-system/tests/test_orders.py
git commit -m "feat: business-system 订单改地址 API"
```

---

## Task 7: 物流只读 API

**Files:**
- Create: `business-system/app/routers/logistics.py`
- Modify: `business-system/app/main.py`
- Test: `business-system/tests/test_logistics.py`

- [ ] **Step 1: 写测试（先失败）**

`business-system/tests/test_logistics.py`:
```python
from datetime import datetime, timedelta

from app.database import get_db
from app.models import Logistics, Order


def _seed(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Order(id="O1", customer_id="C1001", status="已发货"))
    db.add(Logistics(id="L1", order_id="O1", carrier="顺丰", tracking_no="SF123",
                     status="运输中", last_update=datetime.utcnow() - timedelta(days=3),
                     traces=[{"time": "2026-05-28", "desc": "已揽收"}]))
    db.commit()


def test_get_logistics_by_order(client):
    _seed(client)
    resp = client.get("/logistics", params={"order_id": "O1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "运输中"
    assert resp.json()["carrier"] == "顺丰"


def test_get_logistics_not_found(client):
    resp = client.get("/logistics", params={"order_id": "NOPE"})
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd business-system && .venv/Scripts/pytest tests/test_logistics.py -v`
Expected: FAIL

- [ ] **Step 3: 写 logistics 路由**

`business-system/app/routers/logistics.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Logistics
from app.schemas import LogisticsOut

router = APIRouter(prefix="/logistics", tags=["logistics"])


@router.get("", response_model=LogisticsOut)
def get_logistics(order_id: str = Query(...), db: Session = Depends(get_db)):
    lg = db.query(Logistics).filter(Logistics.order_id == order_id).first()
    if not lg:
        raise HTTPException(status_code=404, detail="logistics not found")
    return lg
```

- [ ] **Step 4: 挂载到 main**

修改 `business-system/app/main.py`，import 行改为：
```python
from app.routers import customers, logistics, orders
```
并追加：
```python
app.include_router(logistics.router)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd business-system && .venv/Scripts/pytest tests/test_logistics.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add business-system/app/routers/logistics.py business-system/app/main.py business-system/tests/test_logistics.py
git commit -m "feat: business-system 物流只读 API"
```

---

## Task 8: 退款 API（查询 + 创建）

**Files:**
- Create: `business-system/app/routers/refunds.py`
- Modify: `business-system/app/main.py`
- Test: `business-system/tests/test_refunds.py`

- [ ] **Step 1: 写测试（先失败）**

`business-system/tests/test_refunds.py`:
```python
from app.database import get_db
from app.models import Order, Refund


def _seed_order(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Order(id="O1", customer_id="C1001", status="已签收", amount=299.0))
    db.commit()


def test_get_refund_status_none(client):
    _seed_order(client)
    resp = client.get("/refunds", params={"order_id": "O1"})
    assert resp.status_code == 200
    assert resp.json() == {"order_id": "O1", "status": "无", "refund": None}


def test_create_refund(client):
    _seed_order(client)
    resp = client.post("/refunds", json={"order_id": "O1", "amount": 299.0, "reason": "物流停滞"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["order_id"] == "O1"
    assert body["status"] == "处理中"
    assert body["id"].startswith("RF")


def test_get_refund_status_after_create(client):
    _seed_order(client)
    client.post("/refunds", json={"order_id": "O1", "amount": 299.0})
    resp = client.get("/refunds", params={"order_id": "O1"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "处理中"


def test_create_refund_order_not_found(client):
    resp = client.post("/refunds", json={"order_id": "NOPE", "amount": 10.0})
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd business-system && .venv/Scripts/pytest tests/test_refunds.py -v`
Expected: FAIL

- [ ] **Step 3: 写 refunds 路由**

`business-system/app/routers/refunds.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.ids import new_refund_id
from app.models import Order, Refund
from app.schemas import RefundCreate, RefundOut

router = APIRouter(prefix="/refunds", tags=["refunds"])


@router.get("")
def get_refund_status(order_id: str = Query(...), db: Session = Depends(get_db)):
    rf = (
        db.query(Refund)
        .filter(Refund.order_id == order_id)
        .order_by(Refund.applied_at.desc())
        .first()
    )
    if not rf:
        return {"order_id": order_id, "status": "无", "refund": None}
    return {"order_id": order_id, "status": rf.status, "refund": RefundOut.model_validate(rf).model_dump(mode="json")}


@router.post("", response_model=RefundOut, status_code=201)
def create_refund(body: RefundCreate, response: Response, db: Session = Depends(get_db)):
    if not db.get(Order, body.order_id):
        raise HTTPException(status_code=404, detail="order not found")
    rf = Refund(
        id=new_refund_id(),
        order_id=body.order_id,
        amount=body.amount,
        reason=body.reason,
        channel=body.channel,
        status="处理中",
    )
    db.add(rf)
    db.commit()
    db.refresh(rf)
    return rf
```

- [ ] **Step 4: 挂载到 main**

修改 `business-system/app/main.py`，import 行改为：
```python
from app.routers import customers, logistics, orders, refunds
```
并追加：
```python
app.include_router(refunds.router)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd business-system && .venv/Scripts/pytest tests/test_refunds.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add business-system/app/routers/refunds.py business-system/app/main.py business-system/tests/test_refunds.py
git commit -m "feat: business-system 退款查询与创建 API"
```

---

## Task 9: 工单 API（查询 + 创建 + 更新）

**Files:**
- Create: `business-system/app/routers/tickets.py`
- Modify: `business-system/app/main.py`
- Test: `business-system/tests/test_tickets.py`

- [ ] **Step 1: 写测试（先失败）**

`business-system/tests/test_tickets.py`:
```python
from app.database import get_db
from app.models import Customer


def _seed_customer(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Customer(id="C1001", name="张三", phone="13800000001"))
    db.commit()


def test_create_ticket(client):
    _seed_customer(client)
    resp = client.post("/tickets", json={
        "customer_id": "C1001", "order_id": "O1",
        "category": "物流", "summary": "物流停滞催办", "priority": "高",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("TK")
    assert body["status"] == "待处理"
    assert body["category"] == "物流"


def test_list_tickets_by_customer(client):
    _seed_customer(client)
    client.post("/tickets", json={"customer_id": "C1001", "category": "投诉", "summary": "a"})
    client.post("/tickets", json={"customer_id": "C1001", "category": "退款", "summary": "b"})
    resp = client.get("/tickets", params={"customer_id": "C1001"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_update_ticket_status_and_note(client):
    _seed_customer(client)
    tk = client.post("/tickets", json={"customer_id": "C1001", "category": "物流", "summary": "x"}).json()
    resp = client.patch(f"/tickets/{tk['id']}", json={"status": "已解决", "note": "已联系物流"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "已解决"
    assert any(h.get("note") == "已联系物流" for h in body["history"])


def test_update_ticket_not_found(client):
    resp = client.patch("/tickets/NOPE", json={"status": "已解决"})
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd business-system && .venv/Scripts/pytest tests/test_tickets.py -v`
Expected: FAIL

- [ ] **Step 3: 写 tickets 路由**

`business-system/app/routers/tickets.py`:
```python
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.ids import new_ticket_id
from app.models import Ticket
from app.schemas import TicketCreate, TicketOut, TicketUpdate

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
def list_tickets(customer_id: str = Query(...), db: Session = Depends(get_db)):
    return db.query(Ticket).filter(Ticket.customer_id == customer_id).all()


@router.post("", response_model=TicketOut, status_code=201)
def create_ticket(body: TicketCreate, db: Session = Depends(get_db)):
    tk = Ticket(
        id=new_ticket_id(),
        customer_id=body.customer_id,
        order_id=body.order_id,
        category=body.category,
        summary=body.summary,
        priority=body.priority,
        status="待处理",
        history=[],
    )
    db.add(tk)
    db.commit()
    db.refresh(tk)
    return tk


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: str, body: TicketUpdate, db: Session = Depends(get_db)):
    tk = db.get(Ticket, ticket_id)
    if not tk:
        raise HTTPException(status_code=404, detail="ticket not found")
    history = list(tk.history or [])
    entry = {"time": datetime.utcnow().isoformat()}
    if body.status is not None:
        tk.status = body.status
        entry["status"] = body.status
    if body.assignee is not None:
        tk.assignee = body.assignee
        entry["assignee"] = body.assignee
    if body.note is not None:
        entry["note"] = body.note
    history.append(entry)
    tk.history = history
    tk.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(tk)
    return tk
```

- [ ] **Step 4: 挂载到 main**

修改 `business-system/app/main.py`，import 行改为：
```python
from app.routers import customers, logistics, orders, refunds, tickets
```
并追加：
```python
app.include_router(tickets.router)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd business-system && .venv/Scripts/pytest tests/test_tickets.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add business-system/app/routers/tickets.py business-system/app/main.py business-system/tests/test_tickets.py
git commit -m "feat: business-system 工单查询/创建/更新 API"
```

---

## Task 10: 优惠券 API（创建）

**Files:**
- Create: `business-system/app/routers/coupons.py`
- Modify: `business-system/app/main.py`
- Test: `business-system/tests/test_coupons.py`

- [ ] **Step 1: 写测试（先失败）**

`business-system/tests/test_coupons.py`:
```python
from app.database import get_db
from app.models import Customer


def _seed_customer(client):
    db = next(client.app.dependency_overrides[get_db]())
    db.add(Customer(id="C1001", name="张三", phone="13800000001"))
    db.commit()


def test_issue_coupon(client):
    _seed_customer(client)
    resp = client.post("/coupons", json={"customer_id": "C1001", "value": 20.0, "reason": "补偿"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("CP")
    assert body["value"] == 20.0


def test_issue_coupon_customer_not_found(client):
    resp = client.post("/coupons", json={"customer_id": "NOPE", "value": 20.0})
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd business-system && .venv/Scripts/pytest tests/test_coupons.py -v`
Expected: FAIL

- [ ] **Step 3: 写 coupons 路由**

`business-system/app/routers/coupons.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.ids import new_coupon_id
from app.models import Coupon, Customer
from app.schemas import CouponCreate, CouponOut

router = APIRouter(prefix="/coupons", tags=["coupons"])


@router.post("", response_model=CouponOut, status_code=201)
def issue_coupon(body: CouponCreate, db: Session = Depends(get_db)):
    if not db.get(Customer, body.customer_id):
        raise HTTPException(status_code=404, detail="customer not found")
    cp = Coupon(
        id=new_coupon_id(),
        customer_id=body.customer_id,
        value=body.value,
        reason=body.reason,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp
```

- [ ] **Step 4: 挂载到 main**

修改 `business-system/app/main.py`，import 行改为：
```python
from app.routers import coupons, customers, logistics, orders, refunds, tickets
```
并追加：
```python
app.include_router(coupons.router)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd business-system && .venv/Scripts/pytest tests/test_coupons.py -v`
Expected: PASS

- [ ] **Step 6: 全量回归 + 提交**

Run: `cd business-system && .venv/Scripts/pytest -v`
Expected: 全部 PASS

```bash
git add business-system/app/routers/coupons.py business-system/app/main.py business-system/tests/test_coupons.py
git commit -m "feat: business-system 优惠券创建 API"
```

---

## Task 11: 有剧情的种子数据脚本

**Files:**
- Create: `business-system/app/seed.py`
- Test: `business-system/tests/test_seed.py`

种子要覆盖设计第 6 节四种剧情：①正常已签收 ②物流停滞 3 天 ③退款 5 天未到账 ④近 7 天投诉 3 次的高风险客户。

- [ ] **Step 1: 写种子脚本**

`business-system/app/seed.py`:
```python
"""有剧情的种子数据：可被脚本调用，也可被测试导入。"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.ids import new_refund_id, new_ticket_id
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

    # 剧情④：高风险客户近 7 天 3 次投诉
    for i in range(3):
        db.add(Ticket(id=new_ticket_id() + f"X{i}", customer_id="C1002",
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
```

- [ ] **Step 2: 写种子测试（用 SQLite session 验证剧情）**

`business-system/tests/test_seed.py`:
```python
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
```

- [ ] **Step 3: 跑测试确认通过**

Run: `cd business-system && .venv/Scripts/pytest tests/test_seed.py -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add business-system/app/seed.py business-system/tests/test_seed.py
git commit -m "feat: business-system 有剧情的种子数据脚本"
```

---

## Task 12: Dockerfile + 环境样例 + 手动冒烟

**Files:**
- Create: `business-system/Dockerfile`
- Create: `business-system/.env.example`

- [ ] **Step 1: 写 Dockerfile**

`business-system/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

- [ ] **Step 2: 写环境样例**

`business-system/.env.example`:
```
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/cs
DB_SCHEMA=biz
```

- [ ] **Step 3: 手动冒烟（需本地 Postgres 或先跳过到 docker-compose 阶段）**

如本地有 Postgres：
```bash
cd business-system
.venv/Scripts/python -m app.seed
.venv/Scripts/uvicorn app.main:app --port 8100
```
另开终端：
```bash
curl http://localhost:8100/health/live
curl http://localhost:8100/orders/20260531002
curl "http://localhost:8100/logistics?order_id=20260531002"
```
Expected: 健康检查返回 `{"status":"ok"}`；订单返回"已发货"；物流返回"运输中"。

> 若本地无 Postgres，此手动冒烟留到子计划④的 docker-compose 阶段统一验证；自动化测试（SQLite）已覆盖全部端点逻辑。

- [ ] **Step 4: 提交**

```bash
git add business-system/Dockerfile business-system/.env.example
git commit -m "chore: business-system Dockerfile 与环境样例"
```

---

## 完成标准（子计划①）

- [ ] `cd business-system && .venv/Scripts/pytest -v` 全绿（约 20+ 用例）。
- [ ] 6 张表、对应 REST API 齐全：客户(查)、订单(查/改地址)、物流(查)、退款(查/建)、工单(查/建/改)、优惠券(建)。
- [ ] 种子脚本能造出四种剧情数据。
- [ ] Dockerfile 可构建，监听 8100。
- [ ] 这是一个能**独立 curl / pytest 验证**的服务，完全不认识 cs-agent。

> 下一步：子计划②（cs-agent）会通过 HTTP 调用本服务的这些端点。届时本服务的 API 契约即为 ②的工具层 mock 依据。
