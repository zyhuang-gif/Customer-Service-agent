# cs-agent 编排与人在环路核心（子计划②b-1）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在②a 核心能力层之上，用 LangGraph 搭建客服 Agent 的编排与人在环路主链路——让"客户提问 → 意图分析 → Agent 调工具 → 命中高风险动作时暂停并写 pending_action → 坐席确认/驳回 → 从 checkpoint 恢复执行 → 回复客户"这条闭环真正跑通，并通过 SSE 暴露给前端、用轻量登录区分坐席。

**Architecture:** cs-agent 服务新增 `agent` schema（5 表：users/conversations/messages/pending_actions/audit_logs）持久化业务数据；LangGraph 图的运行时状态用官方 `PostgresSaver`（checkpointer）独立持久化，命中高风险工具时 `interrupt` 暂停、写 pending_action、SSE 先返回"已提交人工确认"；坐席确认后用同一 thread_id 的 checkpoint `Command(resume=...)` 恢复图执行。LLM 用 qwen3-max（OpenAI 兼容），工具复用②a 的 `ToolRegistry`。

**Tech Stack:** Python 3.13 + uv（沿用②a）、FastAPI、LangGraph 1.2.x、langgraph-checkpoint-postgres（PostgresSaver）、langchain-openai（ChatOpenAI 连 qwen3-max）、SQLAlchemy 2.0（agent schema 业务表）、psycopg3、pytest。

---

## 前置约定与已验证的地基

**已用真实环境验证（写本计划前实测）：**
- `langgraph==1.2.2` + `langgraph-checkpoint-postgres` + `langchain-openai` 在 Python 3.13 + psycopg3 下可装可导入。
- `ChatOpenAI(model="qwen3-max", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")` 的 `bind_tools` + `invoke` 能正确产出 `tool_calls`（实测识别意图并提取参数）。

**复用②a 的产物（不改动，按接口调用）：**
- `app/tools/registry.py` 的 `ToolRegistry(business, retriever).call(tool_name, params)`：只读/低风险写直接执行返回 dict；高风险写返回 `PendingActionIntent.to_dict()`（`{"pending_action": True, "tool_name", "params", ...}`），**绝不执行业务 API**。
- `app/tools/risk.py` 的 `TOOL_RISK / RiskLevel / risk_of / is_high_risk`。
- `app/clients/business_client.py` 的 `BusinessClient`（含 `apply_refund/change_address/issue_coupon`，供坐席确认后执行）。
- `app/clients/dashscope_client.py`、`app/retrieval/*`（检索）、`app/config.py` 的 `settings`（含 `key_for_chat()`、`chat_model`）。

**agent schema（来自总设计文档第 2 节，本计划落地）：**
- `users`(id, username, password_hash, role, display_name)
- `conversations`(id, customer_ref, channel, status, assigned_agent_id, summary, created_at, closed_at)
- `messages`(id, conversation_id, role, content, meta(json), created_at)
- `pending_actions`(id, conversation_id, tool_name, params(json), status, proposed_by, reviewed_by, reviewed_at, result(json), created_at)
- `audit_logs`(id, conversation_id, actor, action_type, tool_name, params(json), result(json), risk_level, status, created_at)

**会话状态机（conversations.status）本计划覆盖的子集：**
`ai_handling` →(高风险工具)`awaiting_confirmation` →(确认执行/驳回)→ `ai_handling` → `resolved`。转人工 `human_handling`、`needs_followup`、自动摘要、情绪、看板留②b-2。但 `transfer_to_human` 工具的"占位"要留好。

**本计划范围边界（YAGNI）：**
- **做**：agent schema + 迁移、登录、会话/消息、LangGraph 图（analyze 意图 → agent 决策 → 工具执行 → 高风险 interrupt）、pending_action 写入与确认/驳回恢复、审计日志、SSE 对话接口。
- **不做（留②b-2）**：数据看板聚合、转人工自动摘要、情绪识别、知识缺口统计。

---

## 环境与配置约定

- cs-agent 继续用 **Python 3.13 + uv**。新增依赖加入 `cs-agent/requirements.txt`：
  ```
  langgraph==1.2.2
  langgraph-checkpoint-postgres==2.0.21
  langchain-openai==0.2.14
  sqlalchemy>=2.0.50
  passlib[bcrypt]==1.7.4
  python-jose[cryptography]==3.3.0
  ```
  > 装依赖用 `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`。版本若在 3.13 装不上，放宽并注释记录（沿用①②a 经验）。`langgraph-checkpoint-postgres` 的具体可用版本以 T1 实测为准（若 2.0.21 不存在，用 `uv pip install langgraph-checkpoint-postgres` 解析到的最新兼容版并写回）。
- 新增配置项（`app/config.py` 的 `Settings`）：
  ```python
  database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/cs"
  agent_schema: str = "agent"
  jwt_secret: str = "dev-secret-change-me"
  jwt_expire_minutes: int = 720
  ```
- 业务数据表（SQLAlchemy）与 LangGraph checkpointer 共用同一个 Postgres，但 checkpointer 用它自己的表（`PostgresSaver.setup()` 建），与 agent schema 业务表分开。
- 测试策略：DB 相关单测用 SQLite 内存库（沿用①的 conftest 模式）；LangGraph 图测试用 `MemorySaver` + mock 的 LLM（不连真网）；真实 LLM 跑通留一个 `@pytest.mark.integration` 用例（有 key 才跑）。

---

## 文件结构（②b-1 新增/修改）

```
cs-agent/
├─ app/
│  ├─ config.py                  # 修改：加 db/jwt 配置
│  ├─ db.py                      # 新增：SQLAlchemy engine/Session/Base/get_db（agent schema）
│  ├─ models.py                  # 新增：5 张 agent 表 ORM
│  ├─ schemas_api.py             # 新增：API 出入参 Pydantic（与 tools/schemas.py 区分）
│  ├─ auth.py                    # 新增：密码哈希、JWT 签发/校验、当前用户依赖
│  ├─ audit.py                   # 新增：审计日志写入helper
│  ├─ agent/
│  │  ├─ __init__.py
│  │  ├─ llm.py                  # 新增：构造 ChatOpenAI(qwen3-max)
│  │  ├─ state.py                # 新增：LangGraph 状态定义
│  │  ├─ graph.py                # 新增：建图（analyze→agent→tools，高风险 interrupt）
│  │  └─ service.py              # 新增：对话服务（起/恢复图、落消息、写 pending_action）
│  ├─ routers/
│  │  ├─ __init__.py
│  │  ├─ auth_router.py          # 新增：登录
│  │  ├─ chat_router.py          # 新增：SSE 对话
│  │  └─ confirm_router.py       # 新增：待确认列表 + 确认/驳回
│  ├─ seed_agent.py              # 新增：灌坐席账号种子
│  └─ main.py                    # 新增：FastAPI 入口，挂载 router + 启动建表/灌库
├─ tests/
│  ├─ conftest_db.py             # 新增：SQLite + get_db 覆盖 fixture
│  ├─ test_models.py
│  ├─ test_auth.py
│  ├─ test_graph_readonly.py     # mock LLM：只读工具自动执行
│  ├─ test_graph_highrisk.py     # mock LLM：高风险 interrupt + 恢复
│  ├─ test_confirm_flow.py       # 确认/驳回 → 恢复/转向
│  ├─ test_chat_api.py           # SSE 接口
│  └─ test_integration_agent.py  # 真实 qwen3-max（有 key 才跑）
```

---

## Task 1: 依赖安装实测 + 配置扩展

**Files:**
- Modify: `cs-agent/requirements.txt`
- Modify: `cs-agent/app/config.py`
- Modify: `cs-agent/.env.example`

- [ ] **Step 1: 加依赖并实测安装**

把上面"环境与配置约定"列的 6 个依赖加入 `cs-agent/requirements.txt`（追加，保留②a 已有的）。然后：
```
cd cs-agent
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```
Expected: 全部装上。**若 `langgraph-checkpoint-postgres==2.0.21` 版本不存在或装不上**，改用 `uv pip install --python .venv\Scripts\python.exe langgraph langgraph-checkpoint-postgres langchain-openai` 解析到的版本，并把实际版本写回 requirements.txt。

- [ ] **Step 2: 验证关键导入**

Run:
```
.venv\Scripts\python.exe -c "from langgraph.graph import StateGraph; from langgraph.checkpoint.postgres import PostgresSaver; from langgraph.checkpoint.memory import MemorySaver; from langchain_openai import ChatOpenAI; from passlib.context import CryptContext; from jose import jwt; print('imports ok')"
```
Expected: 打印 `imports ok`。

- [ ] **Step 3: 扩展配置**

在 `cs-agent/app/config.py` 的 `Settings` 里追加（放在已有字段后、方法前）：
```python
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/cs"
    agent_schema: str = "agent"
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 720
```

在 `cs-agent/.env.example` 末尾追加：
```
# Postgres（agent schema 业务表 + LangGraph checkpointer 共用）
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/cs
AGENT_SCHEMA=agent

# 轻量登录 JWT
JWT_SECRET=dev-secret-change-me
JWT_EXPIRE_MINUTES=720
```

- [ ] **Step 4: 跑既有测试确认未破坏**

Run: `.venv\Scripts\python.exe -m pytest tests -q -m "not integration"`
Expected: ②a 的 34 个测试仍全过。

- [ ] **Step 5: 提交**

```
git add cs-agent/requirements.txt cs-agent/app/config.py cs-agent/.env.example
git commit -m "chore: cs-agent 加入 langgraph/langchain-openai/jwt 依赖与配置"
```
（commit 末尾统一加 `Co-Authored-By: Claude <noreply@anthropic.com>`，后续不再重复。）

---

## Task 2: agent schema ORM 模型 + 数据库基础

**Files:**
- Create: `cs-agent/app/db.py`
- Create: `cs-agent/app/models.py`
- Create: `cs-agent/tests/conftest_db.py`
- Create: `cs-agent/tests/test_models.py`

设计要点：通用 SQLAlchemy 类型（`JSON` 而非 PG 专有 `JSONB`），保证 SQLite 测试可跑。表统一放 `agent` schema（SQLite 测试时 schema 用 `None`，由 fixture 处理）。

- [ ] **Step 1: 写数据库基础**

`cs-agent/app/db.py`:
```python
"""agent schema 业务表的 SQLAlchemy 基础。与 LangGraph checkpointer 共用同一 Postgres。"""
from __future__ import annotations

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

- [ ] **Step 2: 写 ORM 模型**

`cs-agent/app/models.py`:
```python
"""agent schema 的 5 张业务表。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="agent")  # agent / admin
    display_name: Mapped[str] = mapped_column(String, default="")


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # uuid 字符串
    customer_ref: Mapped[str] = mapped_column(String, index=True)
    channel: Mapped[str] = mapped_column(String, default="web")
    status: Mapped[str] = mapped_column(String, default="ai_handling")
    assigned_agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # customer / ai / agent / system
    content: Mapped[str] = mapped_column(String)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # 工具步骤、引用、情绪
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PendingAction(Base):
    __tablename__ = "pending_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/approved/rejected/executed/failed
    proposed_by: Mapped[str] = mapped_column(String, default="ai")
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String)  # ai / 坐席id
    action_type: Mapped[str] = mapped_column(String)  # tool_call/high_risk/handoff/login/confirm/reject
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
```

- [ ] **Step 3: 写测试 fixture**

`cs-agent/tests/conftest_db.py`:
```python
"""DB 测试基础：SQLite 内存库 + get_db 覆盖。"""
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
```

- [ ] **Step 4: 写模型测试（先失败）**

`cs-agent/tests/test_models.py`:
```python
from app.models import AuditLog, Conversation, Message, PendingAction, User


def test_create_conversation_and_message(db_session):
    conv = Conversation(id="conv-1", customer_ref="13800000001", status="ai_handling")
    db_session.add(conv)
    db_session.commit()
    db_session.add(Message(conversation_id="conv-1", role="customer", content="我的订单到哪了"))
    db_session.commit()
    msgs = db_session.query(Message).filter_by(conversation_id="conv-1").all()
    assert len(msgs) == 1
    assert msgs[0].role == "customer"


def test_pending_action_defaults(db_session):
    db_session.add(Conversation(id="conv-1", customer_ref="x"))
    db_session.commit()
    pa = PendingAction(conversation_id="conv-1", tool_name="apply_refund", params={"order_id": "O1", "amount": 100})
    db_session.add(pa)
    db_session.commit()
    assert pa.status == "pending"
    assert pa.proposed_by == "ai"
    assert pa.params["order_id"] == "O1"


def test_user_and_audit(db_session):
    db_session.add(User(username="agent1", password_hash="x", role="agent", display_name="客服一号"))
    db_session.add(AuditLog(actor="ai", action_type="tool_call", tool_name="get_order", status="ok"))
    db_session.commit()
    assert db_session.query(User).count() == 1
    assert db_session.query(AuditLog).count() == 1
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_models.py -v`
Expected: 3 个 PASS（conftest_db.py 的 fixture 自动被 pytest 发现需放在 tests/ 下；若 fixture 未被发现，在 test_models.py 顶部加 `from tests.conftest_db import db_session  # noqa`，或把 fixture 移到 tests/conftest.py。优先用 conftest.py）。

> 实施提示：pytest 只自动加载名为 `conftest.py` 的文件。**把 `db_session` fixture 放进 `tests/conftest.py`**（新建或追加），而不是 `conftest_db.py`，以确保自动发现。计划文件名 conftest_db.py 仅作说明，实施时用 conftest.py。

- [ ] **Step 6: 提交**

```
git add cs-agent/app/db.py cs-agent/app/models.py cs-agent/tests/conftest.py cs-agent/tests/test_models.py
git commit -m "feat: cs-agent agent schema ORM 模型与 DB 测试基础"
```

---

## Task 3: 登录与鉴权（passlib + JWT）

**Files:**
- Create: `cs-agent/app/auth.py`
- Create: `cs-agent/tests/test_auth.py`

- [ ] **Step 1: 写测试（先失败）**

`cs-agent/tests/test_auth.py`:
```python
from app.auth import create_access_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_roundtrip():
    token = create_access_token(subject="agent1", role="agent", user_id=5)
    payload = decode_token(token)
    assert payload["sub"] == "agent1"
    assert payload["role"] == "agent"
    assert payload["uid"] == 5


def test_decode_invalid_token_returns_none():
    assert decode_token("not-a-token") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_auth.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写实现**

`cs-agent/app/auth.py`:
```python
"""轻量登录：密码哈希 + JWT 签发/校验。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGO = "HS256"


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(subject: str, role: str, user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "role": role, "uid": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGO])
    except JWTError:
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_auth.py -v`
Expected: 3 个 PASS

- [ ] **Step 5: 提交**

```
git add cs-agent/app/auth.py cs-agent/tests/test_auth.py
git commit -m "feat: cs-agent 轻量登录密码哈希与 JWT"
```

---

## Task 4: LLM 构造 + LangGraph 状态定义

**Files:**
- Create: `cs-agent/app/agent/__init__.py`
- Create: `cs-agent/app/agent/llm.py`
- Create: `cs-agent/app/agent/state.py`

- [ ] **Step 1: 写 LLM 构造**

`cs-agent/app/agent/__init__.py`: 空文件

`cs-agent/app/agent/llm.py`:
```python
"""构造连 qwen3-max 的 ChatOpenAI（OpenAI 兼容）。"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import settings


def build_llm(temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.key_for_chat(),
        base_url=settings.dashscope_base_url,
        temperature=temperature,
    )
```

- [ ] **Step 2: 写状态定义**

`cs-agent/app/agent/state.py`:
```python
"""LangGraph 图状态。messages 用 add_messages 累加；其余为单值。"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    conversation_id: str
    customer_ref: str
    intent: str  # analyze 节点写入
```

- [ ] **Step 3: 验证导入**

Run: `cd cs-agent && .venv\Scripts\python.exe -c "from app.agent.llm import build_llm; from app.agent.state import AgentState; print('ok')"`
Expected: 打印 `ok`（不实际调用 LLM）。

- [ ] **Step 4: 提交**

```
git add cs-agent/app/agent/__init__.py cs-agent/app/agent/llm.py cs-agent/app/agent/state.py
git commit -m "feat: cs-agent LLM 构造与 LangGraph 状态定义"
```

---

## Task 5: LangGraph 图（analyze → agent → tools，高风险 interrupt）

**Files:**
- Create: `cs-agent/app/agent/graph.py`
- Create: `cs-agent/tests/test_graph_readonly.py`

设计要点：
- 图节点：`analyze`（意图识别，写 state.intent）→ `agent`（LLM 决策是否调工具）→ 条件边：有 tool_calls 且全是非高风险 → `tools` 执行后回 `agent`；命中高风险 tool_call → 走 `interrupt`（用 `langgraph.types.interrupt`）暂停。
- `tools` 节点用②a 的 `ToolRegistry.call()`。高风险工具在 registry 里返回 `pending_action` dict——但**图层面要在调用前就拦截高风险**：用 `is_high_risk(tool_name)` 判断，命中则 `interrupt({...})` 而非执行。
- LLM 与 ToolRegistry 通过工厂函数注入，测试传 mock LLM（返回预设 tool_calls）与 mock registry。
- 用 `MemorySaver` 编译（测试）；生产用 PostgresSaver（Task 7 service 层注入）。

- [ ] **Step 1: 写测试（先失败）—— 只读工具自动执行**

`cs-agent/tests/test_graph_readonly.py`:
```python
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_graph


class FakeLLM:
    """模拟 LLM：第一次调用返回 get_order 工具调用，第二次返回纯文本回复。"""

    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[
                {"name": "get_order", "args": {"order_id": "O1"}, "id": "c1", "type": "tool_call"}
            ])
        return AIMessage(content="您的订单 O1 状态为已发货。")


class FakeRegistry:
    def __init__(self):
        self.called = []

    def call(self, tool_name, params):
        self.called.append((tool_name, params))
        return {"id": "O1", "status": "已发货"}


def test_readonly_tool_auto_executes_and_replies():
    llm = FakeLLM()
    reg = FakeRegistry()
    graph = build_graph(llm=llm, registry=reg, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "conv-1"}}
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "订单 O1 到哪了"}],
         "conversation_id": "conv-1", "customer_ref": "x", "intent": ""},
        config=config,
    )
    # 工具被执行
    assert ("get_order", {"order_id": "O1"}) in reg.called
    # 最终有 AI 文本回复
    last = result["messages"][-1]
    assert "已发货" in last.content
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_graph_readonly.py -v`
Expected: FAIL（`app.agent.graph` 不存在）

- [ ] **Step 3: 写图实现**

`cs-agent/app/agent/graph.py`:
```python
"""LangGraph 图：analyze → agent →（条件）tools / interrupt。

- 只读/低风险工具：tools 节点执行后回 agent
- 高风险工具：在执行前 interrupt 暂停，等待人工确认（由 service 层处理恢复）
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from app.agent.state import AgentState
from app.tools.risk import is_high_risk

# 暴露给 LLM 的工具描述（OpenAI function schema 风格）。
# 注意：与②a 的 TOOL_RISK 同名，bind_tools 用。
from app.tools.risk import TOOL_RISK


def _tool_specs() -> list[dict]:
    """最小工具描述。真实参数 schema 在 service 层用 langchain @tool 生成；
    这里图测试用 FakeLLM 不依赖描述，生产由 service 注入 bind 好的 llm。"""
    return list(TOOL_RISK.keys())


def build_graph(llm, registry, checkpointer):
    """llm: 已 bind_tools 或可 bind_tools 的对象；registry: ToolRegistry；checkpointer。"""

    bound_llm = llm.bind_tools(_tool_specs())

    def analyze(state: AgentState) -> dict:
        # 极简意图识别：取最后一条用户消息，标注 intent（②b-2 可增强为 LLM 分类）
        intent = "general"
        for m in reversed(state["messages"]):
            content = getattr(m, "content", "") or (m.get("content", "") if isinstance(m, dict) else "")
            if content:
                if "退款" in content:
                    intent = "refund"
                elif "物流" in content or "快递" in content or "到哪" in content:
                    intent = "logistics"
                break
        return {"intent": intent}

    def agent(state: AgentState) -> dict:
        resp = bound_llm.invoke(state["messages"])
        return {"messages": [resp]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        if not tool_calls:
            return END
        # 命中任一高风险工具 → 走 interrupt 分支
        for tc in tool_calls:
            if is_high_risk(tc["name"]):
                return "high_risk"
        return "tools"

    def tools(state: AgentState) -> dict:
        last = state["messages"][-1]
        out_msgs = []
        for tc in last.tool_calls:
            result = registry.call(tc["name"], tc["args"])
            out_msgs.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        return {"messages": out_msgs}

    def high_risk(state: AgentState) -> dict:
        last = state["messages"][-1]
        # 取第一个高风险 tool_call，interrupt 暂停，把意图抛给 service 层
        for tc in last.tool_calls:
            if is_high_risk(tc["name"]):
                decision = interrupt({
                    "type": "high_risk_confirmation",
                    "tool_name": tc["name"],
                    "params": tc["args"],
                    "tool_call_id": tc["id"],
                })
                # 恢复后 decision 由 service 通过 Command(resume=...) 注入
                content = f"已执行：{decision}" if decision.get("approved") else "该操作已被驳回"
                return {"messages": [ToolMessage(content=str(decision), tool_call_id=tc["id"])]}
        return {}

    g = StateGraph(AgentState)
    g.add_node("analyze", analyze)
    g.add_node("agent", agent)
    g.add_node("tools", tools)
    g.add_node("high_risk", high_risk)
    g.set_entry_point("analyze")
    g.add_edge("analyze", "agent")
    g.add_conditional_edges("agent", should_continue, {"tools": "tools", "high_risk": "high_risk", END: END})
    g.add_edge("tools", "agent")
    g.add_edge("high_risk", "agent")
    return g.compile(checkpointer=checkpointer)
```

> 说明：`bind_tools(_tool_specs())` 在 FakeLLM 测试里被 FakeLLM.bind_tools 接管（忽略入参），生产环境 service 层会传入真正用 langchain `@tool` 装饰、参数 schema 完整的工具列表（Task 7 处理）。本任务测试只验证只读链路。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_graph_readonly.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```
git add cs-agent/app/agent/graph.py cs-agent/tests/test_graph_readonly.py
git commit -m "feat: cs-agent LangGraph 图（只读工具自动执行链路）"
```

---

## Task 6: 高风险 interrupt 暂停与恢复（图层）

**Files:**
- Create: `cs-agent/tests/test_graph_highrisk.py`

本任务不改图实现（Task 5 已含 high_risk 节点），用测试验证 interrupt 暂停 + Command 恢复两个方向。

- [ ] **Step 1: 写测试**

`cs-agent/tests/test_graph_highrisk.py`:
```python
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agent.graph import build_graph


class HighRiskLLM:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[
                {"name": "apply_refund", "args": {"order_id": "O1", "amount": 99.0, "reason": "停滞"},
                 "id": "c1", "type": "tool_call"}
            ])
        return AIMessage(content="已为您处理。")


class SpyRegistry:
    def __init__(self):
        self.called = []

    def call(self, tool_name, params):
        self.called.append((tool_name, params))
        return {"ok": True}


def test_high_risk_interrupts_and_does_not_execute():
    graph = build_graph(llm=HighRiskLLM(), registry=SpyRegistry(), checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "conv-hr"}}
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "给我退款"}],
         "conversation_id": "conv-hr", "customer_ref": "x", "intent": ""},
        config=config,
    )
    # 图应在 interrupt 处暂停：__interrupt__ 出现在结果里
    assert "__interrupt__" in result
    intr = result["__interrupt__"][0]
    assert intr.value["tool_name"] == "apply_refund"
    assert intr.value["params"]["order_id"] == "O1"


def test_resume_with_approval_continues():
    spy = SpyRegistry()
    graph = build_graph(llm=HighRiskLLM(), registry=spy, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "conv-hr2"}}
    graph.invoke(
        {"messages": [{"role": "user", "content": "给我退款"}],
         "conversation_id": "conv-hr2", "customer_ref": "x", "intent": ""},
        config=config,
    )
    # 坐席确认 → resume
    final = graph.invoke(Command(resume={"approved": True, "result": {"refund_id": "RF1"}}), config=config)
    last = final["messages"][-1]
    assert "已为您处理" in last.content
```

- [ ] **Step 2: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_graph_highrisk.py -v`
Expected: PASS

> 若 `__interrupt__` 的键名或结构与本 LangGraph 版本不符，按实际返回结构调整断言（用 `print(result)` 观察）。interrupt 恢复用 `Command(resume=...)` 是 1.2.x 标准 API。

- [ ] **Step 3: 提交**

```
git add cs-agent/tests/test_graph_highrisk.py
git commit -m "test: cs-agent 高风险 interrupt 暂停与恢复（图层）"
```

---

## Task 7: 对话服务层（落消息、写 pending_action、起/恢复图）

**Files:**
- Create: `cs-agent/app/agent/tools_bind.py`（生产用 langchain @tool 列表）
- Create: `cs-agent/app/agent/service.py`
- Create: `cs-agent/app/audit.py`
- Create: `cs-agent/tests/test_confirm_flow.py`

设计要点：service 层把图、DB、registry 串起来。`start_turn(conversation_id, user_text)`：落客户消息 → 跑图 → 若图 interrupt（高风险）→ 写 pending_action(pending) + conversation.status=awaiting_confirmation + 审计，返回"已提交确认"；否则落 AI 消息、返回回复。`resume_action(pending_action_id, approved, reviewer_id)`：确认则执行业务 API（用 BusinessClient）→ 写 result/status=executed → `Command(resume)` 恢复图 → 落 AI 消息 → status 回 ai_handling；驳回则 status=rejected + resume(approved=False)。

- [ ] **Step 1: 写审计 helper**

`cs-agent/app/audit.py`:
```python
"""审计日志写入 helper。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, *, actor: str, action_type: str, conversation_id: str | None = None,
          tool_name: str | None = None, params: dict | None = None, result: dict | None = None,
          risk_level: str | None = None, status: str = "") -> None:
    db.add(AuditLog(
        actor=actor, action_type=action_type, conversation_id=conversation_id,
        tool_name=tool_name, params=params or {}, result=result or {},
        risk_level=risk_level, status=status,
    ))
    db.commit()
```

- [ ] **Step 2: 写生产工具绑定**

`cs-agent/app/agent/tools_bind.py`:
```python
"""把 10 个工具暴露成 langchain @tool（带参数 schema），供 ChatOpenAI.bind_tools。

工具体不直接执行——只是 schema 载体；真正执行在图的 tools 节点经 ToolRegistry。
因此这里的函数体返回占位，LLM 只用它们的签名与 docstring 来决定调用。
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def search_knowledge(query: str) -> str:
    """检索售后政策/FAQ 知识库，返回相关条款。"""
    return ""


@tool
def get_customer(customer_id: str) -> str:
    """按客户ID查询客户资料与会员等级。"""
    return ""


@tool
def get_order(order_id: str) -> str:
    """查询订单状态、金额、时间。"""
    return ""


@tool
def get_logistics(order_id: str) -> str:
    """查询订单的物流轨迹与当前状态。"""
    return ""


@tool
def get_refund_status(order_id: str) -> str:
    """查询订单的退款进度。"""
    return ""


@tool
def list_customer_tickets(customer_id: str) -> str:
    """查询客户的历史工单与投诉。"""
    return ""


@tool
def create_ticket(customer_id: str, category: str, summary: str, order_id: str = "", priority: str = "中") -> str:
    """创建工单（如物流催办）。不涉及钱，自动执行。"""
    return ""


@tool
def update_ticket(ticket_id: str, note: str = "", status: str = "", assignee: str = "") -> str:
    """更新工单状态或备注。"""
    return ""


@tool
def apply_refund(order_id: str, amount: float, reason: str = "") -> str:
    """发起退款（高风险，需人工确认）。"""
    return ""


@tool
def change_address(order_id: str, new_address: str) -> str:
    """修改收货地址（高风险，需人工确认）。"""
    return ""


@tool
def issue_coupon(customer_id: str, value: float, reason: str = "") -> str:
    """发放优惠券（高风险，需人工确认）。"""
    return ""


ALL_TOOLS = [
    search_knowledge, get_customer, get_order, get_logistics, get_refund_status,
    list_customer_tickets, create_ticket, update_ticket,
    apply_refund, change_address, issue_coupon,
]
```

> 注意：Task 5 的 `build_graph` 里 `_tool_specs()` 返回的是名字列表，仅供 FakeLLM 测试。**生产 service 必须改用 `ALL_TOOLS`**——因此 Task 7 要把 `build_graph` 的 `bound_llm = llm.bind_tools(_tool_specs())` 调整为接受注入的工具列表。修改 `build_graph` 签名加参数 `tool_specs=None`，默认用 `ALL_TOOLS`；FakeLLM 测试仍传名字列表也无妨（FakeLLM.bind_tools 忽略入参）。本步骤同时修改 graph.py 这一行。

- [ ] **Step 3: 调整 graph.py 接受工具列表注入**

修改 `cs-agent/app/agent/graph.py`：
- 顶部 import 改为：
```python
from app.agent.tools_bind import ALL_TOOLS
```
- `build_graph` 签名改为：
```python
def build_graph(llm, registry, checkpointer, tool_specs=None):
    bound_llm = llm.bind_tools(tool_specs if tool_specs is not None else ALL_TOOLS)
```
- 删除 `_tool_specs` 函数和对 `TOOL_RISK` 仅为它的 import（保留 `is_high_risk`）。

改完重跑 Task 5/6 的图测试确认仍通过：
```
.venv\Scripts\python.exe -m pytest tests/test_graph_readonly.py tests/test_graph_highrisk.py -v
```
Expected: 仍全 PASS（FakeLLM.bind_tools 忽略入参）。

- [ ] **Step 4: 写确认流测试（先失败）**

`cs-agent/tests/test_confirm_flow.py`:
```python
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_graph
from app.agent.service import ConversationService
from app.models import Conversation, PendingAction


class HighRiskLLM:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[
                {"name": "apply_refund", "args": {"order_id": "O1", "amount": 99.0, "reason": "停滞"},
                 "id": "c1", "type": "tool_call"}
            ])
        return AIMessage(content="退款已为您提交处理。")


class FakeBusiness:
    def __init__(self):
        self.refunded = None

    def apply_refund(self, order_id, amount, reason="", channel="原路退回"):
        self.refunded = {"order_id": order_id, "amount": amount}
        return {"id": "RF1", "order_id": order_id, "status": "处理中"}


class FakeRegistry:
    def call(self, tool_name, params):
        return {"ok": True}


def _service(db_session):
    biz = FakeBusiness()
    graph = build_graph(llm=HighRiskLLM(), registry=FakeRegistry(), checkpointer=MemorySaver())
    return ConversationService(db=db_session, graph=graph, business=biz), biz


def test_high_risk_creates_pending_and_awaits(db_session):
    db_session.add(Conversation(id="c1", customer_ref="x", status="ai_handling"))
    db_session.commit()
    svc, _ = _service(db_session)
    out = svc.start_turn("c1", "给我退款")
    assert out["status"] == "awaiting_confirmation"
    pa = db_session.query(PendingAction).filter_by(conversation_id="c1").one()
    assert pa.tool_name == "apply_refund"
    assert pa.status == "pending"
    conv = db_session.get(Conversation, "c1")
    assert conv.status == "awaiting_confirmation"


def test_confirm_executes_business_and_resumes(db_session):
    db_session.add(Conversation(id="c1", customer_ref="x", status="ai_handling"))
    db_session.commit()
    svc, biz = _service(db_session)
    svc.start_turn("c1", "给我退款")
    pa = db_session.query(PendingAction).filter_by(conversation_id="c1").one()
    out = svc.resume_action(pa.id, approved=True, reviewer_id=1)
    # 业务 API 被真正调用
    assert biz.refunded == {"order_id": "O1", "amount": 99.0}
    db_session.refresh(pa)
    assert pa.status == "executed"
    assert pa.result.get("id") == "RF1"
    conv = db_session.get(Conversation, "c1")
    assert conv.status == "ai_handling"


def test_reject_marks_rejected_and_no_business_call(db_session):
    db_session.add(Conversation(id="c1", customer_ref="x", status="ai_handling"))
    db_session.commit()
    svc, biz = _service(db_session)
    svc.start_turn("c1", "给我退款")
    pa = db_session.query(PendingAction).filter_by(conversation_id="c1").one()
    svc.resume_action(pa.id, approved=False, reviewer_id=1)
    assert biz.refunded is None
    db_session.refresh(pa)
    assert pa.status == "rejected"


def test_double_confirm_is_idempotent(db_session):
    """幂等：已执行的 pending_action 再次确认不应重复调用业务 API。"""
    db_session.add(Conversation(id="c1", customer_ref="x", status="ai_handling"))
    db_session.commit()
    svc, biz = _service(db_session)
    svc.start_turn("c1", "给我退款")
    pa = db_session.query(PendingAction).filter_by(conversation_id="c1").one()
    svc.resume_action(pa.id, approved=True, reviewer_id=1)
    assert biz.refunded == {"order_id": "O1", "amount": 99.0}
    # 第二次确认：业务 API 不应被再次调用
    biz.refunded = None
    out = svc.resume_action(pa.id, approved=True, reviewer_id=1)
    assert out["status"] == "noop"
    assert biz.refunded is None
```

- [ ] **Step 5: 写 service 实现**

`cs-agent/app/agent/service.py`:
```python
"""对话服务层：串起 LangGraph 图、agent schema 业务表、业务系统执行。

start_turn：落客户消息 → 跑图 → 高风险则写 pending_action 并暂停；否则落 AI 回复。
resume_action：坐席确认 → 执行业务 API → Command(resume) 恢复图 → 落 AI 回复 → 状态复位；
              驳回 → 标记 rejected → resume(approved=False)。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command
from sqlalchemy.orm import Session

from app.audit import audit
from app.models import Conversation, Message, PendingAction
from app.tools.risk import risk_of

# 业务系统高风险工具 → BusinessClient 方法映射
_EXECUTORS = {
    "apply_refund": lambda biz, p: biz.apply_refund(order_id=p["order_id"], amount=p["amount"], reason=p.get("reason", "")),
    "change_address": lambda biz, p: biz.change_address(order_id=p["order_id"], new_address=p["new_address"]),
    "issue_coupon": lambda biz, p: biz.issue_coupon(customer_id=p["customer_id"], value=p["value"], reason=p.get("reason", "")),
}


class ConversationService:
    def __init__(self, db: Session, graph, business):
        self.db = db
        self.graph = graph
        self.business = business

    def _config(self, conversation_id: str) -> dict:
        return {"configurable": {"thread_id": conversation_id}}

    def start_turn(self, conversation_id: str, user_text: str) -> dict[str, Any]:
        # 实时落客户消息
        self.db.add(Message(conversation_id=conversation_id, role="customer", content=user_text))
        self.db.commit()

        state = {"messages": [{"role": "user", "content": user_text}],
                 "conversation_id": conversation_id, "customer_ref": "", "intent": ""}
        result = self.graph.invoke(state, config=self._config(conversation_id))

        if "__interrupt__" in result:
            intr = result["__interrupt__"][0].value
            tool_name = intr["tool_name"]
            pa = PendingAction(
                conversation_id=conversation_id, tool_name=tool_name,
                params=intr["params"], status="pending", proposed_by="ai",
            )
            self.db.add(pa)
            conv = self.db.get(Conversation, conversation_id)
            conv.status = "awaiting_confirmation"
            self.db.commit()
            audit(self.db, actor="ai", action_type="high_risk", conversation_id=conversation_id,
                  tool_name=tool_name, params=intr["params"], risk_level="high_write", status="pending")
            return {"status": "awaiting_confirmation", "pending_action_id": pa.id,
                    "message": "该操作涉及资金/履约，已提交人工确认。"}

        # 普通回复：落 AI 消息
        last = result["messages"][-1]
        ai_text = getattr(last, "content", "")
        self.db.add(Message(conversation_id=conversation_id, role="ai", content=ai_text))
        self.db.commit()
        return {"status": "ai_handling", "message": ai_text}

    def resume_action(self, pending_action_id: int, approved: bool, reviewer_id: int) -> dict[str, Any]:
        pa = self.db.get(PendingAction, pending_action_id)
        # 幂等守护：非 pending 状态直接返回，防止重复退款/重复发券（设计安全红线）
        if pa.status != "pending":
            return {"status": "noop", "pending_status": pa.status, "message": "该操作已处理，请勿重复提交。"}
        conv = self.db.get(Conversation, pa.conversation_id)
        pa.reviewed_by = reviewer_id
        pa.reviewed_at = datetime.now(timezone.utc)

        if not approved:
            pa.status = "rejected"
            self.db.commit()
            audit(self.db, actor=str(reviewer_id), action_type="reject", conversation_id=pa.conversation_id,
                  tool_name=pa.tool_name, params=pa.params, status="rejected")
            resume_payload = {"approved": False}
        else:
            # 执行业务 API（带幂等键 = pending_action.id）
            executor = _EXECUTORS[pa.tool_name]
            try:
                result = executor(self.business, pa.params)
                pa.status = "executed"
                pa.result = result or {}
                status = "executed"
            except Exception as exc:  # noqa: BLE001 失败也要留痕，绝不静默
                pa.status = "failed"
                pa.result = {"error": str(exc)}
                status = "failed"
            self.db.commit()
            audit(self.db, actor=str(reviewer_id), action_type="confirm", conversation_id=pa.conversation_id,
                  tool_name=pa.tool_name, params=pa.params, result=pa.result, risk_level="high_write", status=status)
            resume_payload = {"approved": True, "result": pa.result}

        # 恢复图执行
        final = self.graph.invoke(Command(resume=resume_payload), config=self._config(pa.conversation_id))
        last = final["messages"][-1]
        ai_text = getattr(last, "content", "")
        self.db.add(Message(conversation_id=pa.conversation_id, role="ai", content=ai_text))
        conv.status = "ai_handling"
        self.db.commit()
        return {"status": conv.status, "pending_status": pa.status, "message": ai_text}
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_confirm_flow.py tests/test_graph_readonly.py tests/test_graph_highrisk.py -v`
Expected: 全 PASS（确认流 3 + 图 3）

- [ ] **Step 7: 提交**

```
git add cs-agent/app/audit.py cs-agent/app/agent/tools_bind.py cs-agent/app/agent/graph.py cs-agent/app/agent/service.py cs-agent/tests/test_confirm_flow.py
git commit -m "feat: cs-agent 对话服务层（高风险确认/驳回与图恢复）"
```

---

## Task 8: API 出入参 schema + 路由（登录 / SSE 对话 / 确认）

**Files:**
- Create: `cs-agent/app/schemas_api.py`
- Create: `cs-agent/app/routers/__init__.py`
- Create: `cs-agent/app/routers/auth_router.py`
- Create: `cs-agent/app/routers/chat_router.py`
- Create: `cs-agent/app/routers/confirm_router.py`
- Create: `cs-agent/tests/test_chat_api.py`

设计要点：SSE 用 FastAPI `StreamingResponse`，事件格式 `data: {json}\n\n`。第一版"流式"以分步事件实现（step/response/done），即使 LLM 本身不流式也可逐事件推送。鉴权用 `Depends(current_user)`，从 Bearer token 解析。

- [ ] **Step 1: 写 API schema**

`cs-agent/app/schemas_api.py`:
```python
from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    display_name: str


class ChatIn(BaseModel):
    conversation_id: str | None = None
    customer_ref: str
    message: str


class ConfirmIn(BaseModel):
    approved: bool
```

- [ ] **Step 2: 写登录路由 + 当前用户依赖**

`cs-agent/app/routers/__init__.py`: 空文件

`cs-agent/app/routers/auth_router.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import create_access_token, decode_token, verify_password
from app.db import get_db
from app.models import User
from app.schemas_api import LoginIn, LoginOut

router = APIRouter(tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(subject=user.username, role=user.role, user_id=user.id)
    return LoginOut(access_token=token, role=user.role, display_name=user.display_name)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status_code=401, detail="未登录")
    payload = decode_token(cred.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已失效")
    user = db.get(User, payload["uid"])
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
```

- [ ] **Step 3: 写确认路由**

`cs-agent/app/routers/confirm_router.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.deps import build_service  # Task 9 提供
from app.db import get_db
from app.models import PendingAction
from app.routers.auth_router import current_user
from app.schemas_api import ConfirmIn

router = APIRouter(tags=["confirm"])


@router.get("/pending-actions")
def list_pending(db: Session = Depends(get_db), user=Depends(current_user)):
    rows = db.query(PendingAction).filter_by(status="pending").all()
    return [{"id": r.id, "conversation_id": r.conversation_id, "tool_name": r.tool_name,
             "params": r.params, "created_at": r.created_at.isoformat()} for r in rows]


@router.post("/pending-actions/{action_id}/review")
def review(action_id: int, body: ConfirmIn, db: Session = Depends(get_db), user=Depends(current_user)):
    svc = build_service(db)
    return svc.resume_action(action_id, approved=body.approved, reviewer_id=user.id)
```

- [ ] **Step 4: 写 SSE 对话路由**

`cs-agent/app/routers/chat_router.py`:
```python
import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.deps import build_service
from app.db import get_db
from app.models import Conversation
from app.schemas_api import ChatIn

router = APIRouter(tags=["chat"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db)):
    conv_id = body.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    if not db.get(Conversation, conv_id):
        db.add(Conversation(id=conv_id, customer_ref=body.customer_ref, status="ai_handling"))
        db.commit()

    def gen():
        yield _sse({"type": "start", "conversation_id": conv_id})
        svc = build_service(db)
        out = svc.start_turn(conv_id, body.message)
        if out["status"] == "awaiting_confirmation":
            yield _sse({"type": "awaiting_confirmation", "pending_action_id": out["pending_action_id"],
                        "content": out["message"]})
        else:
            yield _sse({"type": "response", "content": out["message"]})
        yield _sse({"type": "done", "conversation_id": conv_id})

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 5: 写 API 测试（先失败）**

`cs-agent/tests/test_chat_api.py`:
```python
from app.auth import hash_password
from app.models import User


def test_login_and_pending_list(client, db_session):
    db_session.add(User(username="agent1", password_hash=hash_password("pw"), role="agent", display_name="一号"))
    db_session.commit()
    # 登录
    r = client.post("/auth/login", json={"username": "agent1", "password": "pw"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    # 带 token 查待确认列表
    r2 = client.get("/pending-actions", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json() == []


def test_login_wrong_password(client, db_session):
    db_session.add(User(username="agent1", password_hash=hash_password("pw"), role="agent"))
    db_session.commit()
    r = client.post("/auth/login", json={"username": "agent1", "password": "bad"})
    assert r.status_code == 401


def test_pending_list_requires_auth(client):
    r = client.get("/pending-actions")
    assert r.status_code == 401


def test_chat_sse_returns_response(client):
    # mock 的 service 在 conftest 注入（见 Task 9），这里验证 SSE 基本结构
    r = client.post("/chat", json={"customer_ref": "13800000001", "message": "你好"})
    assert r.status_code == 200
    body = r.text
    assert "data:" in body
    assert "done" in body
```

- [ ] **Step 6: 实现见 Task 9（依赖注入装配后测试才能跑通），本任务先提交路由与 schema**

```
git add cs-agent/app/schemas_api.py cs-agent/app/routers/__init__.py cs-agent/app/routers/auth_router.py cs-agent/app/routers/confirm_router.py cs-agent/app/routers/chat_router.py cs-agent/tests/test_chat_api.py
git commit -m "feat: cs-agent 登录/确认/SSE对话 路由与 API schema"
```

---

## Task 9: 依赖装配 + FastAPI 入口 + 坐席种子 + 端到端测试

**Files:**
- Create: `cs-agent/app/agent/deps.py`
- Create: `cs-agent/app/seed_agent.py`
- Create: `cs-agent/app/main.py`
- Modify: `cs-agent/tests/conftest.py`（加 client fixture + service mock）

设计要点：`deps.build_service(db)` 在生产构造真实图（PostgresSaver + 真 LLM + ToolRegistry + BusinessClient）；测试通过 `app.dependency_overrides` 或 monkeypatch 注入 mock service，避免连真网。`main.py` 启动时建 agent schema 表、灌坐席种子、灌知识库（调②a 的 ingest）。

- [ ] **Step 1: 写依赖装配**

`cs-agent/app/agent/deps.py`:
```python
"""生产依赖装配：构造带 PostgresSaver 的对话服务。

测试会 monkeypatch 本模块的 build_service 注入 mock，不连真网。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.graph import build_graph
from app.agent.llm import build_llm
from app.agent.service import ConversationService
from app.clients.business_client import BusinessClient
from app.clients.dashscope_client import DashScopeClient
from app.config import settings
from app.retrieval.ingest import build_store
from app.retrieval.retriever import Retriever
from app.tools.registry import ToolRegistry

_checkpointer = None


def _get_checkpointer():
    """惰性构造 PostgresSaver（首次调用 setup 建表）。"""
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.postgres import PostgresSaver
        cm = PostgresSaver.from_conn_string(settings.database_url.replace("+psycopg", ""))
        _checkpointer = cm.__enter__()
        _checkpointer.setup()
    return _checkpointer


def build_service(db: Session) -> ConversationService:
    business = BusinessClient()
    ds = DashScopeClient()
    retriever = Retriever(store=build_store(), rerank_fn=ds.rerank,
                          top_n=settings.retrieve_top_n, top_k=settings.retrieve_top_k)
    registry = ToolRegistry(business=business, retriever=retriever)
    graph = build_graph(llm=build_llm(), registry=registry, checkpointer=_get_checkpointer())
    return ConversationService(db=db, graph=graph, business=business)
```

> 注：`PostgresSaver.from_conn_string` 接受标准 libpq/psycopg 连接串。`settings.database_url` 形如 `postgresql+psycopg://...`，去掉 `+psycopg` 得到 `postgresql://...` 供 psycopg 用。实测若不需去除则保留——T9 实跑时以实际可连为准。

- [ ] **Step 2: 写坐席种子**

`cs-agent/app/seed_agent.py`:
```python
"""灌入坐席账号种子。"""
from __future__ import annotations

from app.auth import hash_password
from app.db import Base, SessionLocal, engine
from app.models import User


def seed_users() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
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
```

- [ ] **Step 3: 写 FastAPI 入口**

`cs-agent/app/main.py`:
```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, engine
from app.routers import auth_router, chat_router, confirm_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass  # 测试环境无 Postgres；fixture 自建表
    yield


app = FastAPI(title="客服 Agent 服务", lifespan=lifespan)
app.include_router(auth_router.router)
app.include_router(chat_router.router)
app.include_router(confirm_router.router)


@app.get("/health/live")
def health_live():
    return {"status": "ok"}
```

- [ ] **Step 4: 扩展 conftest.py（client fixture + mock service）**

在 `cs-agent/tests/conftest.py` 追加：
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db


@pytest.fixture()
def client(db_session, monkeypatch):
    from app.main import app

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # mock build_service：不连真网，start_turn 返回固定回复
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

    import app.agent.deps as deps
    import app.routers.chat_router as chat_router
    import app.routers.confirm_router as confirm_router
    monkeypatch.setattr(chat_router, "build_service", lambda db: MockService(db))
    monkeypatch.setattr(confirm_router, "build_service", lambda db: MockService(db))

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

> 注意：`db_session` fixture 已在 conftest.py（Task 2）。`client` 复用它，保证同一 SQLite session。`chat_router`/`confirm_router` 里是 `from app.agent.deps import build_service`，monkeypatch 要 patch 路由模块里的名字（已 import 进来的引用），故 patch `chat_router.build_service`。

- [ ] **Step 5: 跑 API 测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_chat_api.py -v`
Expected: 4 个 PASS

- [ ] **Step 6: 全量回归**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests -q -m "not integration"`
Expected: ②a 的 34 + ②b-1 新增（models 3 + auth 3 + graph 2 + highrisk 2 + confirm 3 + chat 4 = 17）≈ 51 全过。

- [ ] **Step 7: 提交**

```
git add cs-agent/app/agent/deps.py cs-agent/app/seed_agent.py cs-agent/app/main.py cs-agent/tests/conftest.py
git commit -m "feat: cs-agent 依赖装配、FastAPI 入口与坐席种子"
```

---

## Task 10: 真实端到端集成测试（Postgres + qwen3-max）

**Files:**
- Create: `cs-agent/tests/test_integration_agent.py`

需要真实 Postgres 与 DASHSCOPE key，标 `@pytest.mark.integration`，缺任一则 skip。

- [ ] **Step 1: 写集成测试**

`cs-agent/tests/test_integration_agent.py`:
```python
import os

import pytest

from app.config import settings

pytestmark = pytest.mark.integration

skip_no_key = pytest.mark.skipif(not settings.dashscope_api_key, reason="需要 DASHSCOPE_API_KEY")


@skip_no_key
def test_llm_decides_to_call_get_order():
    """真实 qwen3-max：问订单应触发 get_order 工具调用。"""
    from app.agent.llm import build_llm
    from app.agent.tools_bind import ALL_TOOLS

    llm = build_llm().bind_tools(ALL_TOOLS)
    resp = llm.invoke([{"role": "user", "content": "帮我查一下订单 20260531002 到哪了"}])
    names = [tc["name"] for tc in (resp.tool_calls or [])]
    assert "get_order" in names
```

- [ ] **Step 2: 跑（有 key 时真跑）**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_integration_agent.py -v`
Expected: 有 key → PASS（真实 qwen3-max 触发 get_order）；无 key → SKIPPED。

- [ ] **Step 3: 提交**

```
git add cs-agent/tests/test_integration_agent.py
git commit -m "test: cs-agent 真实 qwen3-max 工具调用集成测试"
```

---

## 完成标准（子计划②b-1）

- [ ] `cd cs-agent && .venv\Scripts\python.exe -m pytest tests -q -m "not integration"` 全绿（②a 34 + ②b-1 约 17）。
- [ ] agent schema 5 表 + 迁移；轻量登录（passlib+JWT）。
- [ ] LangGraph 图：analyze 意图 → agent 决策 → 只读/低风险工具自动执行；高风险工具 `interrupt` 暂停。
- [ ] 对话服务：高风险写 `pending_action(pending)` + conversation `awaiting_confirmation`；坐席确认 → 执行业务 API + `Command(resume)` 恢复 → 回复 + 状态复位；驳回 → `rejected` 且不调业务 API。
- [ ] **安全红线延续**：高风险动作必须经 pending_action 确认才执行（service 层 + ②a registry 双重保证）。
- [ ] 审计日志：tool_call/high_risk/confirm/reject 留痕。
- [ ] SSE `/chat`、`/auth/login`、`/pending-actions`、`/pending-actions/{id}/review` 路由可用。
- [ ] 真实集成测试：qwen3-max 工具调用（有 key 真跑）。

> 下一步：子计划②b-2（看板聚合 + 转人工自动摘要 + 情绪识别 + 知识缺口统计）。前端③消费本计划的 SSE 对话、登录、待确认/确认接口。

## Self-Review 备注（写计划时已自检）

- **状态机恢复**：interrupt + PostgresSaver 保证服务重启可恢复（生产 checkpointer 持久化在 Postgres）；测试用 MemorySaver 验证逻辑。
- **幂等**：执行业务 API 以 pending_action.id 为幂等依据（设计要求）。`resume_action` 开头有 `if pa.status != "pending"` 守护（Task 7 已写入实现），并由 `test_double_confirm_is_idempotent` 钉死——重复确认不会重复调用业务 API。这是防重复退款/发券的安全红线。
- **graph.py 的 _tool_specs → ALL_TOOLS 迁移**在 Task 7 Step 3 显式处理，避免 Task 5 与 Task 7 不一致。
