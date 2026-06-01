# cs-agent 核心能力层（子计划②a）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 cs-agent 服务的"核心能力层"——业务系统 HTTP 客户端（重试/超时/结构化错误）、内置高质量检索（云端 embedding + Chroma + 云端 rerank + 引用出处）、以及由风险分级表驱动的 10 个工具。**不含 LLM 推理与 LangGraph 编排**（那是子计划②b）。

**Architecture:** 独立 FastAPI 项目 `cs-agent/`，与 `business-system/` 平级。本层是纯"能力"代码：工具层是访问外部的唯一出口，只读/低风险工具直接执行，高风险工具只产出一个"待确认意图"对象（不执行、不碰 LLM）。业务系统通过 HTTP 调用（httpx），检索通过百炼（DashScope）云端 embedding + rerank。所有外部依赖（业务系统 HTTP、DashScope）都封装在独立 client 后面，单测用 mock，不依赖网络与运行中的服务。

**Tech Stack:** Python 3.14、FastAPI、httpx（调业务系统 + DashScope）、chromadb（本地持久化向量库）、pydantic v2 + pydantic-settings、pytest + respx（mock httpx）。

---

## 前置约定（来自已完成的子计划①与项目决策）

**业务系统 API 契约**（①已实现并真库验证，本层据此调用）：

| 方法 | 路径 | 入参 | 出参要点 |
|---|---|---|---|
| GET | `/customers/{id}` | path | CustomerOut；404 customer not found |
| GET | `/customers?phone=` | query | CustomerOut；404 |
| GET | `/orders/{id}` | path | OrderOut；404 order not found |
| GET | `/orders?customer_id=` | query | list[OrderOut] |
| PATCH | `/orders/{id}/address` | `{"new_address": str}` | OrderOut；404 |
| GET | `/logistics?order_id=` | query | LogisticsOut；404 logistics not found |
| GET | `/refunds?order_id=` | query | `{"order_id","status","refund": RefundOut|null}` |
| POST | `/refunds` | `{"order_id","amount","reason","channel"}` | RefundOut(201)；404 order not found |
| GET | `/tickets?customer_id=` | query | list[TicketOut] |
| POST | `/tickets` | `{"customer_id","order_id","category","summary","priority"}` | TicketOut(201)；404 customer not found |
| PATCH | `/tickets/{id}` | `{"note","status","assignee"}` | TicketOut；404 ticket not found |
| POST | `/coupons` | `{"customer_id","value","reason"}` | CouponOut(201)；404 customer not found |

**关键技术决策**（已与用户确认）：
- LLM/embedding/rerank 提供方：**阿里云百炼 DashScope**（OpenAI 兼容）。embedding 用 `text-embedding-v4`（实测 1024 维），rerank 用 `qwen3-rerank`，chat（②b 用）用 `qwen3-max`。**以上模型名与端点均已用真实 key 实测可用、返回格式与本计划假设一致。**
- 检索第一版**一步到位含 rerank**：embedding → Chroma 向量召回 top-N → rerank 精排 top-K → 带引用出处返回。
- 本层**不接 LLM 推理**；DashScope 只用于 embedding 与 rerank，且封装在 client 后，单测 mock。
- 真实检索集成需要 `.env` 配 `DASHSCOPE_API_KEY`；无 key 时单测照常全过（mock），仅"真实集成测试"会 skip。

**风险分级**（安全红线，由 `TOOL_RISK` 配置表驱动）：
- 只读（readonly）：`search_knowledge` / `get_customer` / `get_order` / `get_logistics` / `get_refund_status` / `list_customer_tickets`
- 低风险写（low_write）：`create_ticket` / `update_ticket`
- 高风险写（high_write）：`apply_refund` / `change_address` / `issue_coupon`
- **高风险工具在本层不执行业务 API**，只返回 `PendingActionIntent`（编排层②b 据此写 pending_actions 表并走人工确认）。这条由测试守住。

---

## 文件结构

```
cs-agent/
├─ app/
│  ├─ __init__.py
│  ├─ config.py              # 配置：业务系统 base_url、DashScope key/base_url/模型名、chroma 路径
│  ├─ clients/
│  │  ├─ __init__.py
│  │  ├─ business_client.py  # 业务系统 HTTP 客户端（重试/超时/结构化错误）
│  │  └─ dashscope_client.py # DashScope embedding + rerank 客户端
│  ├─ errors.py              # 结构化错误类型（ToolError 等）
│  ├─ retrieval/
│  │  ├─ __init__.py
│  │  ├─ chunking.py         # 知识文档切块
│  │  ├─ store.py            # Chroma 封装：建库、灌库、向量召回
│  │  └─ retriever.py        # 检索编排：embed→召回→rerank→带引用返回
│  ├─ tools/
│  │  ├─ __init__.py
│  │  ├─ risk.py             # TOOL_RISK 风险分级表 + 查询函数
│  │  ├─ schemas.py          # 工具入参/出参/PendingActionIntent 模型
│  │  └─ registry.py         # 10 个工具的实现与注册表
│  └─ knowledge/
│     └─ aftersale_policy.md # 售后政策/FAQ 语料（演示用）
├─ tests/
│  ├─ conftest.py
│  ├─ test_business_client.py
│  ├─ test_dashscope_client.py
│  ├─ test_chunking.py
│  ├─ test_retriever.py
│  ├─ test_risk.py
│  ├─ test_tools_readonly.py
│  ├─ test_tools_write.py
│  └─ test_tools_highrisk.py
├─ requirements.txt
├─ pyproject.toml
└─ .env.example
```

**职责边界：** `clients/` 是唯一的外部 I/O 出口；`retrieval/` 只管检索；`tools/` 把 clients + retrieval 包装成 Agent 可调用的工具并打风险标签；`errors.py` 定义跨层的结构化错误。每个文件单一职责。

---

## Task 1: 项目脚手架 + 配置

**Files:**
- Create: `cs-agent/requirements.txt`
- Create: `cs-agent/pyproject.toml`
- Create: `cs-agent/.env.example`
- Create: `cs-agent/app/__init__.py`
- Create: `cs-agent/app/config.py`

- [ ] **Step 1: 写依赖清单**

`cs-agent/requirements.txt`:
```
fastapi==0.115.5
uvicorn[standard]==0.32.1
httpx==0.28.1
chromadb==0.5.23
pydantic==2.13.4
pydantic-settings==2.6.1
pytest==8.3.4
respx==0.21.1
```
> 注：沿用子计划①的 Python 3.14 经验——pydantic 用 2.13.4。若某包在 3.14 下装不上，放宽到兼容版本并在文件内注释记录。chromadb 若拉起过多重依赖或装不上，记录为 BLOCKED 反馈（不要私自换向量库）。

- [ ] **Step 2: 写 pytest 配置**

`cs-agent/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "-v"
markers = [
    "integration: 需要真实 DASHSCOPE_API_KEY 的集成测试（无 key 时自动 skip）",
]
```

- [ ] **Step 3: 写环境样例**

`cs-agent/.env.example`:
```
# 业务系统服务地址（docker-compose 内为服务名）
BUSINESS_BASE_URL=http://localhost:8100

# 阿里云百炼 DashScope（OpenAI 兼容）
# 注意：真实 key 只写进 .env（已被 .gitignore 忽略），此样例文件保持空值
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v4
RERANK_MODEL=qwen3-rerank

# 检索参数
RETRIEVE_TOP_N=10
RETRIEVE_TOP_K=3

# Chroma 本地持久化目录
CHROMA_DIR=./chroma_db
KNOWLEDGE_DIR=./app/knowledge
```

- [ ] **Step 4: 写配置类**

`cs-agent/app/__init__.py`: （空文件）

`cs-agent/app/config.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    business_base_url: str = "http://localhost:8100"

    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v4"
    rerank_model: str = "qwen3-rerank"

    retrieve_top_n: int = 10
    retrieve_top_k: int = 3

    chroma_dir: str = "./chroma_db"
    knowledge_dir: str = "./app/knowledge"

    # HTTP 客户端
    business_timeout: float = 3.0
    business_retries: int = 1


settings = Settings()
```

- [ ] **Step 5: 安装依赖并验证导入**

Run（Windows PowerShell）:
```
cd cs-agent
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -c "from app.config import settings; print('ok', settings.embedding_model, settings.retrieve_top_k)"
```
Expected: 打印 `ok text-embedding-v4 3`，无导入错误。

- [ ] **Step 6: 提交**

```
git add cs-agent/requirements.txt cs-agent/pyproject.toml cs-agent/.env.example cs-agent/app/__init__.py cs-agent/app/config.py
git commit -m "chore: cs-agent 脚手架与配置"
```
（commit message 末尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`，下同，不再重复。）

---

## Task 2: 结构化错误类型

**Files:**
- Create: `cs-agent/app/errors.py`
- Test: `cs-agent/tests/test_business_client.py`（本任务先建文件占位，下一任务补满）

工具调用失败时，Agent 不能崩、不能编造，要拿到一个结构化错误对象。

- [ ] **Step 1: 写错误类型**

`cs-agent/app/errors.py`:
```python
"""跨层的结构化错误。工具层捕获后返回给 Agent，Agent 据此如实回复，绝不编造。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolError:
    """结构化工具错误。kind 用于 Agent/编排层判断如何处置。"""

    kind: str  # "not_found" | "upstream_unavailable" | "bad_request" | "internal"
    message: str  # 给人看的中文说明
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"error": True, "kind": self.kind, "message": self.message, "details": self.details}


class BusinessUnavailable(Exception):
    """业务系统重试后仍不可用（超时/连接失败/5xx）。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
```

- [ ] **Step 2: 写最小验证测试**

`cs-agent/tests/test_business_client.py`（先只测 errors，下个任务补 client 测试）:
```python
from app.errors import ToolError


def test_tool_error_to_dict():
    e = ToolError(kind="not_found", message="订单不存在", details={"order_id": "X"})
    d = e.to_dict()
    assert d["error"] is True
    assert d["kind"] == "not_found"
    assert d["message"] == "订单不存在"
    assert d["details"]["order_id"] == "X"
```

- [ ] **Step 3: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_business_client.py -v`
Expected: PASS

- [ ] **Step 4: 提交**

```
git add cs-agent/app/errors.py cs-agent/tests/test_business_client.py
git commit -m "feat: cs-agent 结构化错误类型"
```

---

## Task 3: 业务系统 HTTP 客户端（重试/超时/结构化错误）

**Files:**
- Create: `cs-agent/app/clients/__init__.py`
- Create: `cs-agent/app/clients/business_client.py`
- Test: `cs-agent/tests/test_business_client.py`（追加）

设计要点：所有方法捕获 httpx 异常与超时，重试 `settings.business_retries` 次；最终失败抛 `BusinessUnavailable`；404 不是错误而是返回 `None`（由工具层翻译为 not_found ToolError）。用 **respx** mock httpx，不依赖运行中的业务系统。

- [ ] **Step 1: 写测试（先失败）**

在 `cs-agent/tests/test_business_client.py` 追加：
```python
import httpx
import pytest
import respx

from app.clients.business_client import BusinessClient
from app.errors import BusinessUnavailable

BASE = "http://biz.test"


@respx.mock
def test_get_order_success():
    respx.get(f"{BASE}/orders/O1").mock(
        return_value=httpx.Response(200, json={"id": "O1", "status": "已发货"})
    )
    c = BusinessClient(base_url=BASE, timeout=1.0, retries=1)
    data = c.get_order("O1")
    assert data["id"] == "O1"
    assert data["status"] == "已发货"


@respx.mock
def test_get_order_404_returns_none():
    respx.get(f"{BASE}/orders/NOPE").mock(
        return_value=httpx.Response(404, json={"detail": "order not found"})
    )
    c = BusinessClient(base_url=BASE, timeout=1.0, retries=1)
    assert c.get_order("NOPE") is None


@respx.mock
def test_get_order_retries_then_raises_on_5xx():
    route = respx.get(f"{BASE}/orders/O1").mock(return_value=httpx.Response(500))
    c = BusinessClient(base_url=BASE, timeout=1.0, retries=1)
    with pytest.raises(BusinessUnavailable):
        c.get_order("O1")
    # retries=1 → 共 2 次请求
    assert route.call_count == 2


@respx.mock
def test_get_order_retries_then_raises_on_timeout():
    route = respx.get(f"{BASE}/orders/O1").mock(side_effect=httpx.ConnectTimeout("timeout"))
    c = BusinessClient(base_url=BASE, timeout=1.0, retries=1)
    with pytest.raises(BusinessUnavailable):
        c.get_order("O1")
    assert route.call_count == 2


@respx.mock
def test_create_ticket_posts_payload():
    respx.post(f"{BASE}/tickets").mock(
        return_value=httpx.Response(201, json={"id": "TK1", "status": "待处理"})
    )
    c = BusinessClient(base_url=BASE, timeout=1.0, retries=1)
    data = c.create_ticket(customer_id="C1", order_id="O1", category="物流", summary="催办", priority="高")
    assert data["id"] == "TK1"


@respx.mock
def test_create_ticket_404_returns_none():
    respx.post(f"{BASE}/tickets").mock(
        return_value=httpx.Response(404, json={"detail": "customer not found"})
    )
    c = BusinessClient(base_url=BASE, timeout=1.0, retries=1)
    assert c.create_ticket(customer_id="NOPE", order_id=None, category="物流", summary="x", priority="中") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_business_client.py -v`
Expected: FAIL（`app.clients.business_client` 不存在）

- [ ] **Step 3: 写客户端实现**

`cs-agent/app/clients/__init__.py`: （空文件）

`cs-agent/app/clients/business_client.py`:
```python
"""业务系统 HTTP 客户端。所有对业务系统的调用经此唯一出口。

约定：
- 2xx → 返回解析后的 dict / list
- 404 → 返回 None（资源不存在，不是异常）
- 超时 / 连接失败 / 5xx → 重试 retries 次后抛 BusinessUnavailable
"""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.errors import BusinessUnavailable


class BusinessClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None, retries: int | None = None):
        self.base_url = (base_url or settings.business_base_url).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.business_timeout
        self.retries = retries if retries is not None else settings.business_retries

    def _request(self, method: str, path: str, **kwargs) -> Any | None:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        attempts = self.retries + 1
        for _ in range(attempts):
            try:
                resp = httpx.request(method, url, timeout=self.timeout, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code >= 500:
                last_exc = BusinessUnavailable(
                    f"业务系统返回 {resp.status_code}", {"status": resp.status_code, "url": url}
                )
                continue
            if resp.status_code >= 400:
                # 4xx（非 404）按可重现的请求错误抛出，不重试
                raise BusinessUnavailable(
                    f"业务系统请求错误 {resp.status_code}", {"status": resp.status_code, "url": url}
                )
            return resp.json()
        raise BusinessUnavailable(
            "业务系统暂时不可用", {"url": url, "cause": str(last_exc)}
        )

    # ---- 只读 ----
    def get_customer(self, customer_id: str) -> dict | None:
        return self._request("GET", f"/customers/{customer_id}")

    def get_customer_by_phone(self, phone: str) -> dict | None:
        return self._request("GET", "/customers", params={"phone": phone})

    def get_order(self, order_id: str) -> dict | None:
        return self._request("GET", f"/orders/{order_id}")

    def list_orders(self, customer_id: str) -> list | None:
        return self._request("GET", "/orders", params={"customer_id": customer_id})

    def get_logistics(self, order_id: str) -> dict | None:
        return self._request("GET", "/logistics", params={"order_id": order_id})

    def get_refund_status(self, order_id: str) -> dict | None:
        return self._request("GET", "/refunds", params={"order_id": order_id})

    def list_customer_tickets(self, customer_id: str) -> list | None:
        return self._request("GET", "/tickets", params={"customer_id": customer_id})

    # ---- 低风险写 ----
    def create_ticket(self, customer_id: str, order_id: str | None, category: str, summary: str, priority: str) -> dict | None:
        return self._request("POST", "/tickets", json={
            "customer_id": customer_id, "order_id": order_id,
            "category": category, "summary": summary, "priority": priority,
        })

    def update_ticket(self, ticket_id: str, note: str | None = None, status: str | None = None, assignee: str | None = None) -> dict | None:
        return self._request("PATCH", f"/tickets/{ticket_id}", json={
            "note": note, "status": status, "assignee": assignee,
        })

    # ---- 高风险写（仅在编排层确认后才调用）----
    def apply_refund(self, order_id: str, amount: float, reason: str = "", channel: str = "原路退回") -> dict | None:
        return self._request("POST", "/refunds", json={
            "order_id": order_id, "amount": amount, "reason": reason, "channel": channel,
        })

    def change_address(self, order_id: str, new_address: str) -> dict | None:
        return self._request("PATCH", f"/orders/{order_id}/address", json={"new_address": new_address})

    def issue_coupon(self, customer_id: str, value: float, reason: str = "") -> dict | None:
        return self._request("POST", "/coupons", json={
            "customer_id": customer_id, "value": value, "reason": reason,
        })
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_business_client.py -v`
Expected: PASS（errors 1 个 + client 6 个）

- [ ] **Step 5: 提交**

```
git add cs-agent/app/clients/__init__.py cs-agent/app/clients/business_client.py cs-agent/tests/test_business_client.py
git commit -m "feat: cs-agent 业务系统 HTTP 客户端（重试/超时/结构化错误）"
```

---

## Task 4: DashScope embedding + rerank 客户端

**Files:**
- Create: `cs-agent/app/clients/dashscope_client.py`
- Test: `cs-agent/tests/test_dashscope_client.py`

DashScope 兼容模式：embedding 走 `POST {base}/embeddings`（OpenAI 格式），rerank 走 DashScope 原生 `POST https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank`。两者都用 respx mock。无 key 时构造客户端不报错，只有真实调用才需要 key。

- [ ] **Step 1: 写测试（先失败）**

`cs-agent/tests/test_dashscope_client.py`:
```python
import httpx
import respx

from app.clients.dashscope_client import DashScopeClient

EMB_BASE = "http://ds.test/v1"
RERANK_URL = "http://ds.test/api/v1/services/rerank/text-rerank/text-rerank"


@respx.mock
def test_embed_texts_returns_vectors():
    respx.post(f"{EMB_BASE}/embeddings").mock(
        return_value=httpx.Response(200, json={
            "data": [
                {"embedding": [0.1, 0.2, 0.3], "index": 0},
                {"embedding": [0.4, 0.5, 0.6], "index": 1},
            ]
        })
    )
    c = DashScopeClient(api_key="k", base_url=EMB_BASE, rerank_url=RERANK_URL,
                        embedding_model="m", rerank_model="r")
    vecs = c.embed_texts(["a", "b"])
    assert len(vecs) == 2
    assert vecs[0] == [0.1, 0.2, 0.3]


@respx.mock
def test_embed_single_query():
    respx.post(f"{EMB_BASE}/embeddings").mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0], "index": 0}]})
    )
    c = DashScopeClient(api_key="k", base_url=EMB_BASE, rerank_url=RERANK_URL,
                        embedding_model="m", rerank_model="r")
    v = c.embed_query("hello")
    assert v == [1.0, 0.0]


@respx.mock
def test_rerank_returns_sorted_indices_and_scores():
    respx.post(RERANK_URL).mock(
        return_value=httpx.Response(200, json={
            "output": {"results": [
                {"index": 2, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.5},
                {"index": 1, "relevance_score": 0.1},
            ]}
        })
    )
    c = DashScopeClient(api_key="k", base_url=EMB_BASE, rerank_url=RERANK_URL,
                        embedding_model="m", rerank_model="r")
    results = c.rerank("query", ["d0", "d1", "d2"], top_k=2)
    # 返回按分数降序的 (index, score)，截断到 top_k
    assert results == [(2, 0.9), (0, 0.5)]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_dashscope_client.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写实现**

`cs-agent/app/clients/dashscope_client.py`:
```python
"""DashScope（百炼）embedding + rerank 客户端。封装云端调用，单测用 respx mock。"""
from __future__ import annotations

import httpx

from app.config import settings

DEFAULT_RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"


class DashScopeClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        rerank_url: str | None = None,
        embedding_model: str | None = None,
        rerank_model: str | None = None,
        timeout: float = 10.0,
    ):
        self.api_key = api_key if api_key is not None else settings.dashscope_api_key
        self.base_url = (base_url or settings.dashscope_base_url).rstrip("/")
        self.rerank_url = rerank_url or DEFAULT_RERANK_URL
        self.embedding_model = embedding_model or settings.embedding_model
        self.rerank_model = rerank_model or settings.rerank_model
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        resp = httpx.post(
            f"{self.base_url}/embeddings",
            headers=self._headers,
            json={"model": self.embedding_model, "input": texts},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def rerank(self, query: str, documents: list[str], top_k: int) -> list[tuple[int, float]]:
        resp = httpx.post(
            self.rerank_url,
            headers=self._headers,
            json={
                "model": self.rerank_model,
                "input": {"query": query, "documents": documents},
                "parameters": {"top_n": top_k, "return_documents": False},
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        results = resp.json()["output"]["results"]
        ranked = sorted(results, key=lambda r: r["relevance_score"], reverse=True)
        return [(r["index"], r["relevance_score"]) for r in ranked[:top_k]]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_dashscope_client.py -v`
Expected: PASS（3 个）

- [ ] **Step 5: 提交**

```
git add cs-agent/app/clients/dashscope_client.py cs-agent/tests/test_dashscope_client.py
git commit -m "feat: cs-agent DashScope embedding 与 rerank 客户端"
```

---

## Task 5: 知识语料 + 切块

**Files:**
- Create: `cs-agent/app/knowledge/aftersale_policy.md`
- Create: `cs-agent/app/retrieval/__init__.py`
- Create: `cs-agent/app/retrieval/chunking.py`
- Test: `cs-agent/tests/test_chunking.py`

切块策略：按 Markdown 的二级标题（`## `）切分，每个 chunk 携带 `title`（所属标题）、`source`（文件名）、`text`。FAQ 一问一答适合按标题切。

- [ ] **Step 1: 写售后政策语料**

`cs-agent/app/knowledge/aftersale_policy.md`:
```markdown
# 电商售后政策与常见问题

## 物流催办政策
订单发货后，如物流信息超过 72 小时（3 天）未更新，可申请物流催办，我们会联系承运方核实。催办工单通常 24 小时内有反馈。

## 退款时效政策
退款申请审核通过后，款项将原路退回。一般 1-7 个工作日到账，具体以支付渠道为准。若超过 7 个工作日仍未到账，请联系客服核查。

## 物流停滞退款政策
若订单已发货但物流停滞超过 7 天仍未送达，您可以申请退款。停滞 3 天以上、未满 7 天的，建议先创建物流催办工单。

## 七天无理由退货政策
自签收次日起 7 天内，商品完好、不影响二次销售的，支持无理由退货。定制类、生鲜类商品除外。

## 发票申请政策
支持开具电子发票。订单完成后可在订单详情页申请，电子发票一般 1-3 个工作日开具并发送至预留邮箱。

## 会员权益说明
金卡及以上会员享受优先客服、专属优惠券和更快的退款审核。会员等级根据累计消费自动评定。

## 收货地址修改政策
订单在"待发货"状态下可修改收货地址。已发货订单原则上不支持修改，如有特殊情况请联系客服协助。
```

- [ ] **Step 2: 写切块测试（先失败）**

`cs-agent/tests/test_chunking.py`:
```python
from app.retrieval.chunking import chunk_markdown


def test_chunk_by_h2_headings():
    md = "# 标题\n\n## A 政策\n内容A1\n内容A2\n\n## B 政策\n内容B1\n"
    chunks = chunk_markdown(md, source="x.md")
    assert len(chunks) == 2
    assert chunks[0]["title"] == "A 政策"
    assert "内容A1" in chunks[0]["text"]
    assert "内容A2" in chunks[0]["text"]
    assert chunks[0]["source"] == "x.md"
    assert chunks[1]["title"] == "B 政策"


def test_chunk_skips_empty_sections():
    md = "# 大标题\n\n## 只有标题没内容\n\n## 有内容\n正文\n"
    chunks = chunk_markdown(md, source="x.md")
    # 空 section（标题后无正文）被跳过
    titles = [c["title"] for c in chunks]
    assert "有内容" in titles
    assert "只有标题没内容" not in titles
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_chunking.py -v`
Expected: FAIL

- [ ] **Step 4: 写切块实现**

`cs-agent/app/retrieval/__init__.py`: （空文件）

`cs-agent/app/retrieval/chunking.py`:
```python
"""按 Markdown 二级标题(## )切块。每块带 title/source/text。"""
from __future__ import annotations


def chunk_markdown(md: str, source: str) -> list[dict]:
    chunks: list[dict] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush():
        if current_title is not None:
            text = "\n".join(current_lines).strip()
            if text:  # 跳过空 section
                chunks.append({"title": current_title, "source": source, "text": text})

    for line in md.splitlines():
        if line.startswith("## "):
            flush()
            current_title = line[3:].strip()
            current_lines = []
        elif line.startswith("# "):
            # 一级标题不单独成块
            continue
        else:
            if current_title is not None:
                current_lines.append(line)
    flush()
    return chunks
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_chunking.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```
git add cs-agent/app/knowledge/aftersale_policy.md cs-agent/app/retrieval/__init__.py cs-agent/app/retrieval/chunking.py cs-agent/tests/test_chunking.py
git commit -m "feat: cs-agent 售后政策语料与 Markdown 切块"
```

---

## Task 6: Chroma 向量库封装

**Files:**
- Create: `cs-agent/app/retrieval/store.py`
- Test: `cs-agent/tests/test_chunking.py`（追加 store 测试，或新建 test_store.py）

设计要点：`VectorStore` 用注入的 embedding 函数（默认 DashScopeClient.embed_texts，测试注入假函数），把 chunk 灌入 Chroma 内存/临时目录 collection，提供 `add_chunks` 和 `query`（按 query 向量召回 top_n，返回 chunk + 距离）。**embedding 函数注入**使其可单测，不连网。

- [ ] **Step 1: 写测试（先失败）**

`cs-agent/tests/test_store.py`:
```python
from app.retrieval.store import VectorStore


def _fake_embed(texts):
    # 极简可控向量：按是否含关键词映射到不同方向
    vecs = []
    for t in texts:
        if "物流" in t:
            vecs.append([1.0, 0.0])
        elif "退款" in t:
            vecs.append([0.0, 1.0])
        else:
            vecs.append([0.5, 0.5])
    return vecs


def test_add_and_query(tmp_path):
    store = VectorStore(embed_fn=_fake_embed, persist_dir=str(tmp_path), collection="t")
    store.add_chunks([
        {"title": "物流催办", "source": "x.md", "text": "物流超过72小时未更新可催办"},
        {"title": "退款时效", "source": "x.md", "text": "退款1-7个工作日到账"},
    ])
    hits = store.query("我的物流怎么还没动", top_n=1)
    assert len(hits) == 1
    assert hits[0]["title"] == "物流催办"
    assert "source" in hits[0] and "text" in hits[0]


def test_query_empty_store_returns_empty(tmp_path):
    store = VectorStore(embed_fn=_fake_embed, persist_dir=str(tmp_path), collection="empty")
    assert store.query("任意", top_n=3) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_store.py -v`
Expected: FAIL

- [ ] **Step 3: 写 Chroma 封装**

`cs-agent/app/retrieval/store.py`:
```python
"""Chroma 向量库封装。embedding 函数注入，便于单测不连网。"""
from __future__ import annotations

from typing import Callable

import chromadb

EmbedFn = Callable[[list[str]], list[list[float]]]


class VectorStore:
    def __init__(self, embed_fn: EmbedFn, persist_dir: str, collection: str = "knowledge"):
        self.embed_fn = embed_fn
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, chunks: list[dict]) -> None:
        if not chunks:
            return
        texts = [c["text"] for c in chunks]
        embeddings = self.embed_fn(texts)
        ids = [f"chunk-{i}" for i in range(len(chunks))]
        metadatas = [{"title": c["title"], "source": c["source"]} for c in chunks]
        self.collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    def count(self) -> int:
        return self.collection.count()

    def query(self, query_text: str, top_n: int) -> list[dict]:
        if self.collection.count() == 0:
            return []
        qvec = self.embed_fn([query_text])[0]
        res = self.collection.query(query_embeddings=[qvec], n_results=top_n)
        hits: list[dict] = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            hits.append({
                "title": meta.get("title", ""),
                "source": meta.get("source", ""),
                "text": doc,
                "distance": dist,
            })
        return hits
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_store.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```
git add cs-agent/app/retrieval/store.py cs-agent/tests/test_store.py
git commit -m "feat: cs-agent Chroma 向量库封装"
```

---

## Task 7: 检索编排（embed→召回→rerank→带引用）

**Files:**
- Create: `cs-agent/app/retrieval/retriever.py`
- Test: `cs-agent/tests/test_retriever.py`

设计要点：`Retriever` 组合 `VectorStore`（向量召回 top_n）+ rerank 函数（精排 top_k）。返回结果带引用出处（title/source）。rerank 函数注入，测试用假函数。无命中返回空列表（工具层据此告知"知识库未覆盖"）。

- [ ] **Step 1: 写测试（先失败）**

`cs-agent/tests/test_retriever.py`:
```python
from app.retrieval.retriever import Retriever


def _fake_embed(texts):
    vecs = []
    for t in texts:
        if "物流" in t:
            vecs.append([1.0, 0.0])
        elif "退款" in t:
            vecs.append([0.0, 1.0])
        else:
            vecs.append([0.5, 0.5])
    return vecs


def _fake_rerank(query, documents, top_k):
    # 假 rerank：含"物流"的文档排第一
    scored = []
    for i, d in enumerate(documents):
        score = 1.0 if "物流" in d else 0.1
        scored.append((i, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def _build(tmp_path):
    from app.retrieval.store import VectorStore
    store = VectorStore(embed_fn=_fake_embed, persist_dir=str(tmp_path), collection="r")
    store.add_chunks([
        {"title": "物流催办", "source": "x.md", "text": "物流超过72小时未更新可催办"},
        {"title": "退款时效", "source": "x.md", "text": "退款1-7个工作日到账"},
        {"title": "发票", "source": "x.md", "text": "电子发票1-3个工作日开具"},
    ])
    return Retriever(store=store, rerank_fn=_fake_rerank, top_n=3, top_k=2)


def test_retrieve_returns_reranked_with_citation(tmp_path):
    r = _build(tmp_path)
    results = r.retrieve("物流停了怎么办")
    assert len(results) == 2  # top_k
    assert results[0]["title"] == "物流催办"
    # 带引用出处
    assert results[0]["source"] == "x.md"
    assert "text" in results[0]
    assert "score" in results[0]


def test_retrieve_empty_store_returns_empty(tmp_path):
    from app.retrieval.store import VectorStore
    store = VectorStore(embed_fn=_fake_embed, persist_dir=str(tmp_path), collection="empty")
    r = Retriever(store=store, rerank_fn=_fake_rerank, top_n=3, top_k=2)
    assert r.retrieve("任意问题") == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_retriever.py -v`
Expected: FAIL

- [ ] **Step 3: 写检索编排**

`cs-agent/app/retrieval/retriever.py`:
```python
"""检索编排：向量召回 top_n → rerank 精排 top_k → 带引用出处返回。"""
from __future__ import annotations

from typing import Callable

from app.retrieval.store import VectorStore

RerankFn = Callable[[str, list[str], int], list[tuple[int, float]]]


class Retriever:
    def __init__(self, store: VectorStore, rerank_fn: RerankFn, top_n: int, top_k: int):
        self.store = store
        self.rerank_fn = rerank_fn
        self.top_n = top_n
        self.top_k = top_k

    def retrieve(self, query: str) -> list[dict]:
        candidates = self.store.query(query, top_n=self.top_n)
        if not candidates:
            return []
        docs = [c["text"] for c in candidates]
        ranked = self.rerank_fn(query, docs, self.top_k)
        results: list[dict] = []
        for idx, score in ranked:
            c = candidates[idx]
            results.append({
                "title": c["title"],
                "source": c["source"],
                "text": c["text"],
                "score": score,
            })
        return results
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_retriever.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```
git add cs-agent/app/retrieval/retriever.py cs-agent/tests/test_retriever.py
git commit -m "feat: cs-agent 检索编排（召回+rerank+引用）"
```

---

## Task 8: 工具风险分级表 + 工具 schema

**Files:**
- Create: `cs-agent/app/tools/__init__.py`
- Create: `cs-agent/app/tools/risk.py`
- Create: `cs-agent/app/tools/schemas.py`
- Test: `cs-agent/tests/test_risk.py`

- [ ] **Step 1: 写风险表测试（先失败）**

`cs-agent/tests/test_risk.py`:
```python
from app.tools.risk import TOOL_RISK, RiskLevel, risk_of, is_high_risk


def test_all_ten_tools_classified():
    expected = {
        "search_knowledge", "get_customer", "get_order", "get_logistics",
        "get_refund_status", "list_customer_tickets",
        "create_ticket", "update_ticket",
        "apply_refund", "change_address", "issue_coupon",
    }
    assert set(TOOL_RISK.keys()) == expected


def test_readonly_classification():
    assert risk_of("get_order") == RiskLevel.READONLY
    assert risk_of("search_knowledge") == RiskLevel.READONLY


def test_low_write_classification():
    assert risk_of("create_ticket") == RiskLevel.LOW_WRITE
    assert risk_of("update_ticket") == RiskLevel.LOW_WRITE


def test_high_write_classification():
    assert risk_of("apply_refund") == RiskLevel.HIGH_WRITE
    assert risk_of("change_address") == RiskLevel.HIGH_WRITE
    assert risk_of("issue_coupon") == RiskLevel.HIGH_WRITE


def test_is_high_risk_helper():
    assert is_high_risk("apply_refund") is True
    assert is_high_risk("get_order") is False
    assert is_high_risk("create_ticket") is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_risk.py -v`
Expected: FAIL

- [ ] **Step 3: 写风险表与 schema**

`cs-agent/app/tools/__init__.py`: （空文件）

`cs-agent/app/tools/risk.py`:
```python
"""工具风险分级表（安全红线的配置化来源）。调档位改这里，不动逻辑。"""
from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    READONLY = "readonly"
    LOW_WRITE = "low_write"
    HIGH_WRITE = "high_write"


TOOL_RISK: dict[str, RiskLevel] = {
    # 只读
    "search_knowledge": RiskLevel.READONLY,
    "get_customer": RiskLevel.READONLY,
    "get_order": RiskLevel.READONLY,
    "get_logistics": RiskLevel.READONLY,
    "get_refund_status": RiskLevel.READONLY,
    "list_customer_tickets": RiskLevel.READONLY,
    # 低风险写
    "create_ticket": RiskLevel.LOW_WRITE,
    "update_ticket": RiskLevel.LOW_WRITE,
    # 高风险写
    "apply_refund": RiskLevel.HIGH_WRITE,
    "change_address": RiskLevel.HIGH_WRITE,
    "issue_coupon": RiskLevel.HIGH_WRITE,
}


def risk_of(tool_name: str) -> RiskLevel:
    return TOOL_RISK[tool_name]


def is_high_risk(tool_name: str) -> bool:
    return TOOL_RISK.get(tool_name) == RiskLevel.HIGH_WRITE
```

`cs-agent/app/tools/schemas.py`:
```python
"""工具的统一返回结构与高风险待确认意图。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingActionIntent:
    """高风险工具不执行业务 API，只产出此意图。编排层据此写 pending_actions 表。"""

    tool_name: str
    params: dict[str, Any]
    risk_level: str = "high_write"
    requires_confirmation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "pending_action": True,
            "tool_name": self.tool_name,
            "params": self.params,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
        }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_risk.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```
git add cs-agent/app/tools/__init__.py cs-agent/app/tools/risk.py cs-agent/app/tools/schemas.py cs-agent/tests/test_risk.py
git commit -m "feat: cs-agent 工具风险分级表与待确认意图 schema"
```

---

## Task 9: 只读工具实现

**Files:**
- Create: `cs-agent/app/tools/registry.py`
- Test: `cs-agent/tests/test_tools_readonly.py`

设计要点：`ToolRegistry` 持有 `BusinessClient` 和 `Retriever`。只读工具调用对应 client 方法；业务对象不存在（client 返回 None）→ 返回 `ToolError(kind="not_found")` 的 dict；业务系统不可用（抛 BusinessUnavailable）→ 返回 `ToolError(kind="upstream_unavailable")` 的 dict；**工具绝不向上抛异常**（Agent 要拿到结构化结果）。`search_knowledge` 命中为空 → 返回 `{"hits": [], "covered": False}`。

- [ ] **Step 1: 写测试（先失败）**

`cs-agent/tests/test_tools_readonly.py`:
```python
import pytest

from app.errors import BusinessUnavailable
from app.tools.registry import ToolRegistry


class FakeBusiness:
    def __init__(self):
        self.raise_unavailable = False

    def get_order(self, order_id):
        if self.raise_unavailable:
            raise BusinessUnavailable("down")
        if order_id == "O1":
            return {"id": "O1", "status": "已发货"}
        return None

    def get_customer(self, customer_id):
        return {"id": customer_id, "name": "张三"} if customer_id == "C1" else None

    def get_logistics(self, order_id):
        return {"order_id": order_id, "status": "运输中"} if order_id == "O1" else None

    def get_refund_status(self, order_id):
        return {"order_id": order_id, "status": "处理中", "refund": None}

    def list_customer_tickets(self, customer_id):
        return [{"id": "TK1", "category": "投诉"}]


class FakeRetriever:
    def __init__(self, results):
        self._results = results

    def retrieve(self, query):
        return self._results


def _registry(retriever_results=None):
    return ToolRegistry(
        business=FakeBusiness(),
        retriever=FakeRetriever(retriever_results or []),
    )


def test_get_order_found():
    reg = _registry()
    out = reg.call("get_order", {"order_id": "O1"})
    assert out["status"] == "已发货"


def test_get_order_not_found_returns_tool_error():
    reg = _registry()
    out = reg.call("get_order", {"order_id": "NOPE"})
    assert out["error"] is True
    assert out["kind"] == "not_found"


def test_get_order_upstream_unavailable():
    reg = _registry()
    reg.business.raise_unavailable = True
    out = reg.call("get_order", {"order_id": "O1"})
    assert out["error"] is True
    assert out["kind"] == "upstream_unavailable"


def test_search_knowledge_hit():
    reg = _registry(retriever_results=[{"title": "物流催办", "source": "x.md", "text": "...", "score": 0.9}])
    out = reg.call("search_knowledge", {"query": "物流停了"})
    assert out["covered"] is True
    assert len(out["hits"]) == 1
    assert out["hits"][0]["title"] == "物流催办"


def test_search_knowledge_no_hit_marks_uncovered():
    reg = _registry(retriever_results=[])
    out = reg.call("search_knowledge", {"query": "未知问题"})
    assert out["covered"] is False
    assert out["hits"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_tools_readonly.py -v`
Expected: FAIL

- [ ] **Step 3: 写 registry（只读部分 + call 分发）**

`cs-agent/app/tools/registry.py`:
```python
"""工具注册表：把 BusinessClient + Retriever 包装成 Agent 可调用的工具。

约定：
- 工具绝不向上抛异常，失败返回 ToolError.to_dict()
- 只读 / 低风险写：直接执行
- 高风险写：不执行业务 API，返回 PendingActionIntent.to_dict()
"""
from __future__ import annotations

from typing import Any

from app.errors import BusinessUnavailable, ToolError
from app.tools.risk import RiskLevel, risk_of
from app.tools.schemas import PendingActionIntent


class ToolRegistry:
    def __init__(self, business, retriever):
        self.business = business
        self.retriever = retriever

    # ---- 分发入口 ----
    def call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any] | list:
        level = risk_of(tool_name)
        if level == RiskLevel.HIGH_WRITE:
            # 高风险：不执行，返回待确认意图
            return PendingActionIntent(tool_name=tool_name, params=params).to_dict()
        handler = getattr(self, f"_tool_{tool_name}")
        try:
            return handler(params)
        except BusinessUnavailable as exc:
            return ToolError("upstream_unavailable", "业务系统暂时不可用，正在为您转人工", exc.details).to_dict()

    # ---- 只读工具 ----
    def _tool_search_knowledge(self, params):
        hits = self.retriever.retrieve(params["query"])
        return {"hits": hits, "covered": bool(hits)}

    def _tool_get_customer(self, params):
        data = self.business.get_customer(params["customer_id"])
        return data if data is not None else ToolError("not_found", "未找到该客户").to_dict()

    def _tool_get_order(self, params):
        data = self.business.get_order(params["order_id"])
        return data if data is not None else ToolError("not_found", "未找到该订单，请核对订单号").to_dict()

    def _tool_get_logistics(self, params):
        data = self.business.get_logistics(params["order_id"])
        return data if data is not None else ToolError("not_found", "未找到该订单的物流信息").to_dict()

    def _tool_get_refund_status(self, params):
        data = self.business.get_refund_status(params["order_id"])
        return data if data is not None else ToolError("not_found", "未找到该订单的退款记录").to_dict()

    def _tool_list_customer_tickets(self, params):
        data = self.business.list_customer_tickets(params["customer_id"])
        return {"tickets": data if data is not None else []}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_tools_readonly.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```
git add cs-agent/app/tools/registry.py cs-agent/tests/test_tools_readonly.py
git commit -m "feat: cs-agent 只读工具实现"
```

---

## Task 10: 低风险写工具实现

**Files:**
- Modify: `cs-agent/app/tools/registry.py`
- Test: `cs-agent/tests/test_tools_write.py`

- [ ] **Step 1: 写测试（先失败）**

`cs-agent/tests/test_tools_write.py`:
```python
from app.tools.registry import ToolRegistry


class FakeBusiness:
    def __init__(self):
        self.created = None
        self.updated = None

    def create_ticket(self, customer_id, order_id, category, summary, priority):
        if customer_id == "NOPE":
            return None
        self.created = dict(customer_id=customer_id, order_id=order_id, category=category, summary=summary, priority=priority)
        return {"id": "TK1", "status": "待处理", **self.created}

    def update_ticket(self, ticket_id, note=None, status=None, assignee=None):
        if ticket_id == "NOPE":
            return None
        self.updated = dict(ticket_id=ticket_id, note=note, status=status, assignee=assignee)
        return {"id": ticket_id, "status": status or "待处理"}


def _registry():
    return ToolRegistry(business=FakeBusiness(), retriever=None)


def test_create_ticket_success():
    reg = _registry()
    out = reg.call("create_ticket", {"customer_id": "C1", "order_id": "O1", "category": "物流", "summary": "催办", "priority": "高"})
    assert out["id"] == "TK1"
    assert reg.business.created["category"] == "物流"


def test_create_ticket_customer_not_found():
    reg = _registry()
    out = reg.call("create_ticket", {"customer_id": "NOPE", "order_id": None, "category": "物流", "summary": "x", "priority": "中"})
    assert out["error"] is True
    assert out["kind"] == "not_found"


def test_update_ticket_success():
    reg = _registry()
    out = reg.call("update_ticket", {"ticket_id": "TK1", "status": "已解决", "note": "已处理"})
    assert out["status"] == "已解决"


def test_update_ticket_not_found():
    reg = _registry()
    out = reg.call("update_ticket", {"ticket_id": "NOPE", "status": "已解决"})
    assert out["error"] is True
    assert out["kind"] == "not_found"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_tools_write.py -v`
Expected: FAIL（`_tool_create_ticket` 不存在）

- [ ] **Step 3: 在 registry 追加低风险写工具**

在 `cs-agent/app/tools/registry.py` 的 `ToolRegistry` 类末尾追加：
```python
    # ---- 低风险写工具 ----
    def _tool_create_ticket(self, params):
        data = self.business.create_ticket(
            customer_id=params["customer_id"],
            order_id=params.get("order_id"),
            category=params["category"],
            summary=params.get("summary", ""),
            priority=params.get("priority", "中"),
        )
        return data if data is not None else ToolError("not_found", "建单失败：未找到该客户").to_dict()

    def _tool_update_ticket(self, params):
        data = self.business.update_ticket(
            ticket_id=params["ticket_id"],
            note=params.get("note"),
            status=params.get("status"),
            assignee=params.get("assignee"),
        )
        return data if data is not None else ToolError("not_found", "更新失败：未找到该工单").to_dict()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_tools_write.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```
git add cs-agent/app/tools/registry.py cs-agent/tests/test_tools_write.py
git commit -m "feat: cs-agent 低风险写工具实现"
```

---

## Task 11: 高风险工具的安全红线（不执行，只产意图）

**Files:**
- Test: `cs-agent/tests/test_tools_highrisk.py`

这一任务**不加新实现代码**（高风险分支在 Task 9 的 `call` 里已实现），而是用安全测试钉死红线：高风险工具在任何情况下都不调用业务系统、只返回待确认意图。

- [ ] **Step 1: 写安全测试**

`cs-agent/tests/test_tools_highrisk.py`:
```python
import pytest

from app.tools.registry import ToolRegistry
from app.tools.risk import RiskLevel, risk_of


class SpyBusiness:
    """任何方法被调用都记录——高风险工具绝不能碰它。"""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _rec(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return {"should": "never be called"}
        return _rec


@pytest.mark.parametrize("tool,params", [
    ("apply_refund", {"order_id": "O1", "amount": 100.0, "reason": "x"}),
    ("change_address", {"order_id": "O1", "new_address": "上海"}),
    ("issue_coupon", {"customer_id": "C1", "value": 20.0, "reason": "补偿"}),
])
def test_high_risk_returns_pending_and_never_calls_business(tool, params):
    spy = SpyBusiness()
    reg = ToolRegistry(business=spy, retriever=None)
    out = reg.call(tool, params)
    # 返回待确认意图，不是执行结果
    assert out["pending_action"] is True
    assert out["requires_confirmation"] is True
    assert out["tool_name"] == tool
    assert out["params"] == params
    # 红线：业务系统一次都没被调用
    assert spy.calls == []


def test_all_high_risk_tools_are_high_write():
    for tool in ("apply_refund", "change_address", "issue_coupon"):
        assert risk_of(tool) == RiskLevel.HIGH_WRITE
```

- [ ] **Step 2: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_tools_highrisk.py -v`
Expected: PASS（4 个：3 个参数化 + 1 个）

> 若任一用例显示 `spy.calls` 非空，说明高风险红线被破坏，必须停下修复 registry，不得放行。

- [ ] **Step 3: 提交**

```
git add cs-agent/tests/test_tools_highrisk.py
git commit -m "test: cs-agent 高风险工具安全红线（不执行只产意图）"
```

---

## Task 12: 知识库灌入脚本 + 真实检索集成测试（可选 key）

**Files:**
- Create: `cs-agent/app/retrieval/ingest.py`
- Test: `cs-agent/tests/test_integration_retrieval.py`

`ingest.py` 把 `knowledge/` 下文档切块并用真实 DashScope embedding 灌入 Chroma（启动时调用）。集成测试用 `@pytest.mark.integration`，无 `DASHSCOPE_API_KEY` 时 skip。

- [ ] **Step 1: 写灌入脚本**

`cs-agent/app/retrieval/ingest.py`:
```python
"""把 knowledge/ 下的文档切块并灌入 Chroma。用真实 DashScope embedding。"""
from __future__ import annotations

import pathlib

from app.clients.dashscope_client import DashScopeClient
from app.config import settings
from app.retrieval.chunking import chunk_markdown
from app.retrieval.store import VectorStore


def build_store() -> VectorStore:
    """构造一个使用真实 DashScope embedding 的 VectorStore。"""
    client = DashScopeClient()
    return VectorStore(
        embed_fn=client.embed_texts,
        persist_dir=settings.chroma_dir,
        collection="knowledge",
    )


def ingest() -> int:
    """读取知识目录、切块、灌库。返回灌入的 chunk 数。"""
    store = build_store()
    if store.count() > 0:
        print(f"知识库已有 {store.count()} 个 chunk，跳过灌入。")
        return store.count()

    kdir = pathlib.Path(settings.knowledge_dir)
    all_chunks: list[dict] = []
    for md_file in kdir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        all_chunks.extend(chunk_markdown(text, source=md_file.name))

    store.add_chunks(all_chunks)
    print(f"灌入 {len(all_chunks)} 个 chunk。")
    return len(all_chunks)


if __name__ == "__main__":
    ingest()
```

- [ ] **Step 2: 写集成测试（无 key 自动 skip）**

`cs-agent/tests/test_integration_retrieval.py`:
```python
import os

import pytest

from app.config import settings

pytestmark = pytest.mark.integration

skip_no_key = pytest.mark.skipif(
    not settings.dashscope_api_key,
    reason="需要 DASHSCOPE_API_KEY 才能跑真实检索集成测试",
)


@skip_no_key
def test_real_retrieve_logistics_question(tmp_path):
    """真实 embedding + rerank：问物流问题应召回物流催办政策。"""
    from app.clients.dashscope_client import DashScopeClient
    from app.retrieval.chunking import chunk_markdown
    from app.retrieval.retriever import Retriever
    from app.retrieval.store import VectorStore

    client = DashScopeClient()
    store = VectorStore(embed_fn=client.embed_texts, persist_dir=str(tmp_path), collection="it")
    text = open(f"{settings.knowledge_dir}/aftersale_policy.md", encoding="utf-8").read()
    store.add_chunks(chunk_markdown(text, source="aftersale_policy.md"))

    retriever = Retriever(store=store, rerank_fn=client.rerank, top_n=5, top_k=2)
    results = retriever.retrieve("我的快递好几天没动了怎么办")
    assert len(results) >= 1
    titles = [r["title"] for r in results]
    assert any("物流" in t for t in titles)
```

- [ ] **Step 3: 跑测试（无 key 时确认 skip）**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_integration_retrieval.py -v`
Expected: 无 key → SKIPPED；有 key → PASS（召回含"物流"的政策）

- [ ] **Step 4: 全量回归 + 提交**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest -v`
Expected: 全部 PASS（集成测试 skip 或 pass）

```
git add cs-agent/app/retrieval/ingest.py cs-agent/tests/test_integration_retrieval.py
git commit -m "feat: cs-agent 知识库灌入脚本与真实检索集成测试"
```

---

## 完成标准（子计划②a）

- [ ] `cd cs-agent && .venv\Scripts\python.exe -m pytest -v` 全绿（集成测试无 key 时 skip）。
- [ ] 业务系统 HTTP 客户端：覆盖 12 个端点，重试/超时/404/5xx 行为有测试。
- [ ] DashScope 客户端：embedding + rerank，respx mock 测试。
- [ ] 检索链路：切块 → Chroma 召回 → rerank → 带引用，单测用注入的假函数全覆盖。
- [ ] 10 个工具齐全，风险三分级由 `TOOL_RISK` 驱动。
- [ ] **安全红线测试通过**：高风险工具只产意图、绝不调用业务系统。
- [ ] 工具失败返回结构化 ToolError，绝不抛异常、绝不编造。

> 下一步：子计划②b（LangGraph 编排层）会消费本层——把 `ToolRegistry` 接进 LangGraph 节点，高风险工具返回的 `PendingActionIntent` 写入 `pending_actions` 表并触发 interrupt 人工确认。本层的 `ToolRegistry.call()` 即为②b 的工具执行入口。
