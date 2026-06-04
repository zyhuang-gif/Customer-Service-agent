# Customer Chat Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a customer-facing chat session center that resumes the latest conversation within two hours, starts fresh after two hours, verifies customers with phone plus most recent order, and exposes authorized server-side history for seven days.

**Architecture:** Add a customer-specific JWT flow and customer-owned conversation API beside the existing agent authentication and agent conversation API. Track conversation activity with a persisted `last_message_at` field updated through one helper, then let the Vue customer store initialize `/chat` from the authorized recent-conversation endpoint instead of trusting old local message cache.

**Tech Stack:** FastAPI, SQLAlchemy, python-jose JWT, httpx business client, Vue 3 Composition API, Pinia, Element Plus, Vitest, pytest.

---

## File Structure

### Backend

- Create `cs-agent/app/conversation_activity.py`: single helper for creating messages and updating `Conversation.last_message_at`.
- Create `cs-agent/app/schema_migrations.py`: idempotent startup migration and backfill for the new conversation activity column.
- Create `cs-agent/app/routers/customer_auth_router.py`: phone plus most-recent-order verification and customer JWT issuance.
- Create `cs-agent/app/routers/customer_conversation_router.py`: customer-owned history, recent conversation, and message reads.
- Create `cs-agent/app/customer_access.py`: identify personal-data requests and reject unauthenticated or foreign-order access.
- Modify `cs-agent/app/auth.py`: support customer tokens with a seven-day lifetime.
- Modify `cs-agent/app/config.py`: define customer token and resume-window settings.
- Modify `cs-agent/app/models.py`: add `Conversation.last_message_at`.
- Modify `cs-agent/app/schemas_api.py`: add customer authentication schemas.
- Modify `cs-agent/app/main.py`: run migration and register customer routers.
- Modify `cs-agent/app/routers/chat_router.py`: accept optional customer JWT and enforce conversation ownership.
- Modify `cs-agent/app/routers/conversation_router.py`: update activity timestamp for agent replies.
- Modify `cs-agent/app/agent/service.py`: use the activity helper for customer and AI messages.

### Frontend

- Create `web/src/stores/customerSession.js`: customer token lifecycle, expiry, verification, history, and recent-session initialization.
- Create `web/src/components/CustomerVerifyDialog.vue`: phone and most recent order verification form.
- Create `web/src/components/CustomerHistoryDrawer.vue`: authorized server-side conversation list.
- Modify `web/src/api/sse.js`: attach optional customer Bearer token.
- Modify `web/src/views/ChatView.vue`: focused single-column customer UI, account menu, two-hour resume initialization, history, and new consultation action.
- Modify `web/tests/ChatView.spec.js`: replace local-cache assumptions with recent-session behavior.
- Create `web/tests/customerSession.spec.js`: store expiry and API behavior tests.

### Tests

- Create `cs-agent/tests/test_customer_auth.py`.
- Create `cs-agent/tests/test_customer_conversation_api.py`.
- Create `cs-agent/tests/test_conversation_activity.py`.
- Modify `cs-agent/tests/test_auth.py`.
- Modify `cs-agent/tests/test_chat_api.py`.
- Modify `cs-agent/tests/test_conversation_api.py`.
- Modify `cs-agent/tests/conftest.py`.

---

### Task 1: Add Conversation Activity Timestamp and Existing-Database Migration

**Files:**
- Create: `cs-agent/app/schema_migrations.py`
- Modify: `cs-agent/app/models.py`
- Modify: `cs-agent/app/main.py`
- Create: `cs-agent/tests/test_schema_migrations.py`

- [ ] **Step 1: Write failing model and migration tests**

```python
# cs-agent/tests/test_schema_migrations.py
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect, text

from app.schema_migrations import ensure_conversation_last_message_at


def test_migration_adds_and_backfills_last_message_at():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE conversations (
                id VARCHAR PRIMARY KEY,
                customer_ref VARCHAR NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                conversation_id VARCHAR NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text(
            "INSERT INTO conversations (id, customer_ref, created_at) VALUES "
            "('c1', '138', '2026-06-04 08:00:00')"
        ))
        conn.execute(text(
            "INSERT INTO messages (id, conversation_id, created_at) VALUES "
            "(1, 'c1', '2026-06-04 09:00:00')"
        ))

    ensure_conversation_last_message_at(engine)

    assert "last_message_at" in {c["name"] for c in inspect(engine).get_columns("conversations")}
    with engine.connect() as conn:
        value = conn.execute(text(
            "SELECT last_message_at FROM conversations WHERE id = 'c1'"
        )).scalar_one()
    assert str(value).startswith("2026-06-04 09:00:00")


def test_migration_is_idempotent():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE conversations (
                id VARCHAR PRIMARY KEY,
                customer_ref VARCHAR NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                conversation_id VARCHAR NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))

    ensure_conversation_last_message_at(engine)
    ensure_conversation_last_message_at(engine)
```

- [ ] **Step 2: Run the migration tests and verify failure**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_schema_migrations.py -q
```

Expected: FAIL because `app.schema_migrations` and `Conversation.last_message_at` do not exist.

- [ ] **Step 3: Add the model field and idempotent migration**

```python
# cs-agent/app/models.py
class Conversation(Base):
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

```python
# cs-agent/app/schema_migrations.py
from sqlalchemy import Engine, inspect, text


def ensure_conversation_last_message_at(engine: Engine) -> None:
    inspector = inspect(engine)
    if "conversations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("conversations")}
    with engine.begin() as conn:
        if "last_message_at" not in columns:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN last_message_at TIMESTAMP"))
        conn.execute(text("""
            UPDATE conversations
            SET last_message_at = COALESCE(
                (SELECT MAX(messages.created_at)
                 FROM messages
                 WHERE messages.conversation_id = conversations.id),
                created_at
            )
            WHERE last_message_at IS NULL
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_conversations_last_message_at
            ON conversations (last_message_at)
        """))
```

In `cs-agent/app/main.py`, call `ensure_conversation_last_message_at(get_engine())` immediately after the existing `Base.metadata.create_all(bind=get_engine())` call.

- [ ] **Step 4: Run migration tests**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_schema_migrations.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add cs-agent/app/models.py cs-agent/app/schema_migrations.py cs-agent/app/main.py cs-agent/tests/test_schema_migrations.py
git commit -m "feat: 增加会话活跃时间迁移"
```

### Task 2: Centralize Message Persistence and Activity Updates

**Files:**
- Create: `cs-agent/app/conversation_activity.py`
- Create: `cs-agent/tests/test_conversation_activity.py`
- Modify: `cs-agent/app/agent/service.py`
- Modify: `cs-agent/app/routers/conversation_router.py`
- Modify: `cs-agent/tests/test_conversation_api.py`

- [ ] **Step 1: Write failing activity helper tests**

```python
# cs-agent/tests/test_conversation_activity.py
from datetime import datetime, timedelta, timezone

from app.conversation_activity import add_message
from app.models import Conversation


def test_add_message_updates_last_message_at(db_session):
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    db_session.add(Conversation(id="c1", customer_ref="138", last_message_at=old))
    db_session.commit()

    message = add_message(db_session, "c1", "customer", "你好", {"source": "web"})
    db_session.commit()

    conversation = db_session.get(Conversation, "c1")
    assert message.content == "你好"
    assert message.meta == {"source": "web"}
    assert conversation.last_message_at > old
```

Extend `test_agent_reply_to_human_conversation` in `cs-agent/tests/test_conversation_api.py` to assert `last_message_at` increased after the agent reply.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_conversation_activity.py tests\test_conversation_api.py::test_agent_reply_to_human_conversation -q
```

Expected: FAIL because `add_message` does not exist and agent replies do not update activity.

- [ ] **Step 3: Implement and adopt the helper**

```python
# cs-agent/app/conversation_activity.py
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Conversation, Message


def add_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    meta: dict | None = None,
) -> Message:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError(f"conversation not found: {conversation_id}")
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        meta=meta or {},
    )
    db.add(message)
    conversation.last_message_at = datetime.now(timezone.utc)
    return message
```

Replace the direct `Message` construction in `ConversationService.start_turn`, both `ConversationService.resume_action` branches, and `conversation_router.agent_reply` with `add_message`. Keep existing commit boundaries and response payloads unchanged.

- [ ] **Step 4: Run all affected backend tests**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_conversation_activity.py tests\test_conversation_api.py tests\test_agent_productization.py tests\test_confirm_flow.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add cs-agent/app/conversation_activity.py cs-agent/app/agent/service.py cs-agent/app/routers/conversation_router.py cs-agent/tests/test_conversation_activity.py cs-agent/tests/test_conversation_api.py
git commit -m "refactor: 统一更新会话活跃时间"
```

### Task 3: Add Customer JWT and Phone Plus Recent-Order Verification

**Files:**
- Modify: `cs-agent/app/config.py`
- Modify: `cs-agent/app/auth.py`
- Modify: `cs-agent/app/schemas_api.py`
- Modify: `cs-agent/app/routers/auth_router.py`
- Create: `cs-agent/app/routers/customer_auth_router.py`
- Modify: `cs-agent/app/main.py`
- Create: `cs-agent/tests/test_customer_auth.py`
- Modify: `cs-agent/tests/test_auth.py`

- [ ] **Step 1: Write failing customer-token and verification tests**

```python
# cs-agent/tests/test_customer_auth.py
from datetime import datetime, timezone


def test_verify_customer_with_most_recent_order(client, monkeypatch):
    import app.routers.customer_auth_router as router

    monkeypatch.setattr(router.BusinessClient, "get_customer_by_phone", lambda self, phone: {
        "id": "C1001", "phone": phone, "name": "张三"
    })
    monkeypatch.setattr(router.BusinessClient, "list_orders", lambda self, customer_id: [
        {"id": "OLD", "created_at": "2026-05-01T00:00:00"},
        {"id": "LATEST", "created_at": "2026-06-01T00:00:00"},
    ])

    response = client.post("/customer-auth/verify", json={
        "phone": "13800000001",
        "recent_order_id": "LATEST",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["masked_phone"] == "138****0001"
    assert body["expires_at"] > datetime.now(timezone.utc).isoformat()


def test_verify_customer_rejects_non_recent_order(client, monkeypatch):
    import app.routers.customer_auth_router as router

    monkeypatch.setattr(router.BusinessClient, "get_customer_by_phone", lambda self, phone: {
        "id": "C1001", "phone": phone
    })
    monkeypatch.setattr(router.BusinessClient, "list_orders", lambda self, customer_id: [
        {"id": "OLD", "created_at": "2026-05-01T00:00:00"},
        {"id": "LATEST", "created_at": "2026-06-01T00:00:00"},
    ])

    response = client.post("/customer-auth/verify", json={
        "phone": "13800000001",
        "recent_order_id": "OLD",
    })

    assert response.status_code == 401
    assert response.json()["detail"] == "手机号或最近订单号不匹配"
```

Add to `cs-agent/tests/test_auth.py`:

```python
from datetime import datetime, timedelta, timezone

from app.auth import create_customer_access_token


def test_customer_jwt_roundtrip():
    token, expires_at = create_customer_access_token("13800000001")
    payload = decode_token(token)
    assert payload["role"] == "customer"
    assert payload["customer_ref"] == "13800000001"
    remaining = expires_at - datetime.now(timezone.utc)
    assert timedelta(days=6, hours=23) < remaining <= timedelta(days=7)


def test_customer_token_cannot_access_agent_endpoints(client):
    token, _ = create_customer_access_token("13800000001")
    response = client.get(
        "/pending-actions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_customer_auth.py tests\test_auth.py -q
```

Expected: FAIL because customer token helpers and router do not exist.

- [ ] **Step 3: Implement customer token and verification router**

Add settings:

```python
# cs-agent/app/config.py
customer_jwt_expire_days: int = 7
customer_resume_hours: int = 2
```

Add token helper:

```python
# cs-agent/app/auth.py
def create_customer_access_token(customer_ref: str) -> tuple[str, datetime]:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.customer_jwt_expire_days)
    payload = {
        "sub": customer_ref,
        "role": "customer",
        "customer_ref": customer_ref,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGO), expire
```

Harden `current_user` in `cs-agent/app/routers/auth_router.py` before reading `uid`:

```python
if not payload or payload.get("role") not in {"agent", "admin"} or not payload.get("uid"):
    raise HTTPException(status_code=401, detail="登录已失效")
```

Add schemas:

```python
# cs-agent/app/schemas_api.py
class CustomerVerifyIn(BaseModel):
    phone: str
    recent_order_id: str


class CustomerVerifyOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    masked_phone: str
    expires_at: str
```

Implement `POST /customer-auth/verify` in `customer_auth_router.py`. Sort orders with:

```python
latest = max(orders or [], key=lambda order: (order.get("created_at", ""), order.get("id", "")), default=None)
```

Return the same 401 detail for missing customer, no orders, and mismatched latest order. Register the router in `main.py`.

- [ ] **Step 4: Run customer authentication tests**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_customer_auth.py tests\test_auth.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add cs-agent/app/config.py cs-agent/app/auth.py cs-agent/app/schemas_api.py cs-agent/app/routers/auth_router.py cs-agent/app/routers/customer_auth_router.py cs-agent/app/main.py cs-agent/tests/test_customer_auth.py cs-agent/tests/test_auth.py
git commit -m "feat: 增加客户身份验证"
```

### Task 4: Add Authorized Customer Conversation APIs and Two-Hour Resume Rule

**Files:**
- Create: `cs-agent/app/routers/customer_conversation_router.py`
- Modify: `cs-agent/app/main.py`
- Create: `cs-agent/tests/test_customer_conversation_api.py`

- [ ] **Step 1: Write failing ownership and resume tests**

```python
# cs-agent/tests/test_customer_conversation_api.py
from datetime import datetime, timedelta, timezone

from app.auth import create_customer_access_token
from app.models import Conversation, Message


def _customer_headers(customer_ref="138"):
    token, _ = create_customer_access_token(customer_ref)
    return {"Authorization": f"Bearer {token}"}


def test_recent_conversation_resumes_within_two_hours(client, db_session):
    now = datetime.now(timezone.utc)
    db_session.add(Conversation(
        id="c1", customer_ref="138", summary="查物流",
        last_message_at=now - timedelta(minutes=30),
    ))
    db_session.commit()

    response = client.get("/customer/conversations/recent", headers=_customer_headers())

    assert response.status_code == 200
    assert response.json()["conversation"]["id"] == "c1"
    assert response.json()["should_resume"] is True


def test_recent_conversation_does_not_resume_after_two_hours(client, db_session):
    db_session.add(Conversation(
        id="c1", customer_ref="138",
        last_message_at=datetime.now(timezone.utc) - timedelta(hours=2, seconds=1),
    ))
    db_session.commit()

    response = client.get("/customer/conversations/recent", headers=_customer_headers())

    assert response.status_code == 200
    assert response.json()["should_resume"] is False


def test_customer_cannot_read_another_customers_messages(client, db_session):
    db_session.add(Conversation(id="other", customer_ref="139"))
    db_session.add(Message(conversation_id="other", role="customer", content="私密内容"))
    db_session.commit()

    response = client.get(
        "/customer/conversations/other/messages",
        headers=_customer_headers("138"),
    )

    assert response.status_code == 404
```

Also test history ordering by `last_message_at` descending and reject agent tokens with 401.

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_customer_conversation_api.py -q
```

Expected: FAIL with 404 because customer conversation routes do not exist.

- [ ] **Step 3: Implement customer-only dependency and routes**

```python
# cs-agent/app/routers/customer_conversation_router.py
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth import decode_token
from app.config import settings
from app.db import get_db
from app.models import Conversation, Message

router = APIRouter(prefix="/customer", tags=["customer-conversations"])
_bearer = HTTPBearer(auto_error=False)


def current_customer(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    payload = decode_token(cred.credentials) if cred else None
    if not payload or payload.get("role") != "customer" or not payload.get("customer_ref"):
        raise HTTPException(status_code=401, detail="客户登录已失效")
    return payload["customer_ref"]
```

Use a private serializer shared by list and recent endpoints. For `recent`, compute:

```python
cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.customer_resume_hours)
last_message_at = conversation.last_message_at if conversation else None
if last_message_at and last_message_at.tzinfo is None:
    last_message_at = last_message_at.replace(tzinfo=timezone.utc)
should_resume = bool(last_message_at and last_message_at >= cutoff)
```

Before returning messages, query the conversation by both ID and `customer_ref`; return 404 for missing or foreign conversations. Register the router in `main.py`.

- [ ] **Step 4: Run customer conversation tests**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_customer_conversation_api.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add cs-agent/app/routers/customer_conversation_router.py cs-agent/app/main.py cs-agent/tests/test_customer_conversation_api.py
git commit -m "feat: 增加客户历史会话接口"
```

### Task 5: Enforce Customer Ownership and Personal-Data Access When Sending Chat Messages

**Files:**
- Create: `cs-agent/app/customer_access.py`
- Modify: `cs-agent/app/routers/chat_router.py`
- Modify: `cs-agent/tests/test_chat_api.py`
- Modify: `cs-agent/tests/conftest.py`

- [ ] **Step 1: Write failing authenticated-chat tests**

```python
# cs-agent/tests/test_chat_api.py
from app.auth import create_customer_access_token
from app.models import Conversation


def _headers(customer_ref):
    token, _ = create_customer_access_token(customer_ref)
    return {"Authorization": f"Bearer {token}"}


def test_authenticated_chat_uses_token_customer_ref(client, db_session):
    response = client.post(
        "/chat",
        headers=_headers("138"),
        json={"customer_ref": "forged", "message": "你好"},
    )
    assert response.status_code == 200
    conversation_id = response.text.split('"conversation_id": "')[1].split('"')[0]
    assert db_session.get(Conversation, conversation_id).customer_ref == "138"


def test_authenticated_chat_rejects_foreign_conversation(client, db_session):
    db_session.add(Conversation(id="foreign", customer_ref="139"))
    db_session.commit()

    response = client.post(
        "/chat",
        headers=_headers("138"),
        json={"conversation_id": "foreign", "customer_ref": "139", "message": "你好"},
    )

    assert response.status_code == 404


def test_anonymous_personal_order_query_requires_identity(client):
    response = client.post(
        "/chat",
        json={"customer_ref": "anonymous-web", "message": "查询订单 20260531002"},
    )
    assert response.status_code == 200
    assert '"type": "identity_required"' in response.text


def test_authenticated_customer_cannot_query_foreign_order(client, monkeypatch):
    import app.routers.chat_router as router

    monkeypatch.setattr(router.BusinessClient, "get_customer_by_phone", lambda self, phone: {
        "id": "C1001", "phone": phone
    })
    monkeypatch.setattr(router.BusinessClient, "list_orders", lambda self, customer_id: [
        {"id": "OWN-ORDER", "customer_id": customer_id, "created_at": "2026-06-01T00:00:00"},
    ])

    response = client.post(
        "/chat",
        headers=_headers("138"),
        json={"customer_ref": "138", "message": "查询订单 FOREIGN-ORDER"},
    )

    assert response.status_code == 200
    assert '"type": "access_denied"' in response.text
```

- [ ] **Step 2: Run chat tests and verify failure**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_chat_api.py -q
```

Expected: FAIL because `/chat` trusts `body.customer_ref` and does not enforce identity or order ownership.

- [ ] **Step 3: Add personal-data request classification**

```python
# cs-agent/app/customer_access.py
import re

_ORDER_ID = re.compile(r"\b[A-Z0-9-]{6,}\b", re.IGNORECASE)
_PERSONAL_TERMS = ("我的订单", "查订单", "查询订单", "查物流", "物流进度", "退款进度", "退款状态")


def requested_order_ids(message: str) -> set[str]:
    return {match.upper() for match in _ORDER_ID.findall(message)}


def requires_customer_identity(message: str) -> bool:
    return bool(requested_order_ids(message)) or any(term in message for term in _PERSONAL_TERMS)
```

Keep policy questions such as “退货规则是什么” and “退款多久到账” available without verification.

- [ ] **Step 4: Add optional customer authentication and access guard to `/chat`**

Use `HTTPBearer(auto_error=False)` and decode only customer-role tokens. Rules:

```python
customer_ref = payload["customer_ref"] if valid_customer_payload else body.customer_ref
conversation = db.get(Conversation, conv_id) if body.conversation_id else None
if conversation and valid_customer_payload and conversation.customer_ref != customer_ref:
    raise HTTPException(status_code=404, detail="会话不存在")
if conversation is None:
    conversation = Conversation(
        id=conv_id,
        customer_ref=customer_ref,
        status="ai_handling",
        last_message_at=datetime.now(timezone.utc),
    )
    db.add(conversation)
    db.commit()
```

Before calling `ConversationService.start_turn`:

- If `requires_customer_identity(body.message)` and no valid customer token exists, stream `identity_required` and `done` events without invoking the Agent.
- If an authenticated message contains order IDs, resolve the verified phone to its business customer, load that customer's orders, and stream `access_denied` plus `done` when any requested order ID is not owned by that customer.
- Keep anonymous compatibility for general policy questions.
- Update the `MockService.start_turn` in `tests/conftest.py` to use `add_message`, ensuring test AI replies update activity.

- [ ] **Step 5: Run affected backend test suite**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests\test_chat_api.py tests\test_customer_conversation_api.py tests\test_conversation_activity.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add cs-agent/app/customer_access.py cs-agent/app/routers/chat_router.py cs-agent/tests/test_chat_api.py cs-agent/tests/conftest.py
git commit -m "feat: 校验客户会话所有权"
```

### Task 6: Add Frontend Customer Session Store and Authenticated SSE

**Files:**
- Create: `web/src/stores/customerSession.js`
- Modify: `web/src/api/sse.js`
- Create: `web/tests/customerSession.spec.js`

- [ ] **Step 1: Write failing customer session store tests**

```javascript
// web/tests/customerSession.spec.js
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCustomerSessionStore } from '../src/stores/customerSession'

describe('customerSession store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('清理已过期客户令牌', () => {
    localStorage.setItem('customer_token', 'expired')
    localStorage.setItem('customer_expires_at', '2026-01-01T00:00:00Z')
    const store = useCustomerSessionStore()
    store.restore()
    expect(store.token).toBe('')
  })

  it('验证成功后保存七天客户会话信息', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        access_token: 'token-1',
        masked_phone: '138****0001',
        expires_at: '2099-06-11T00:00:00Z',
      }),
    })))
    const store = useCustomerSessionStore()
    await store.verify('13800000001', '20260531002')
    expect(store.token).toBe('token-1')
    expect(localStorage.getItem('customer_masked_phone')).toBe('138****0001')
  })
})
```

- [ ] **Step 2: Run frontend store tests and verify failure**

Run:

```powershell
cd web
npm run test -- customerSession.spec.js
```

Expected: FAIL because `customerSession` store does not exist.

- [ ] **Step 3: Implement store and token-aware SSE**

```javascript
// web/src/stores/customerSession.js
import { defineStore } from 'pinia'
import { api } from '../api/client'

export const useCustomerSessionStore = defineStore('customerSession', {
  state: () => ({
    token: '',
    maskedPhone: '',
    expiresAt: '',
  }),
  getters: {
    isLoggedIn: (state) => !!state.token && Date.parse(state.expiresAt) > Date.now(),
  },
  actions: {
    restore() {
      this.token = localStorage.getItem('customer_token') || ''
      this.maskedPhone = localStorage.getItem('customer_masked_phone') || ''
      this.expiresAt = localStorage.getItem('customer_expires_at') || ''
      if (!this.isLoggedIn) this.logout()
    },
    async verify(phone, recentOrderId) {
      const data = await api('/customer-auth/verify', {
        method: 'POST',
        body: { phone, recent_order_id: recentOrderId },
      })
      this.token = data.access_token
      this.maskedPhone = data.masked_phone
      this.expiresAt = data.expires_at
      localStorage.setItem('customer_token', this.token)
      localStorage.setItem('customer_masked_phone', this.maskedPhone)
      localStorage.setItem('customer_expires_at', this.expiresAt)
    },
    logout() {
      this.token = ''
      this.maskedPhone = ''
      this.expiresAt = ''
      localStorage.removeItem('customer_token')
      localStorage.removeItem('customer_masked_phone')
      localStorage.removeItem('customer_expires_at')
    },
  },
})
```

Change `chatStream` signature to accept `token`; add `Authorization: Bearer ${token}` only when present. Throw a readable error when `resp.ok` is false before reading the stream.

- [ ] **Step 4: Run frontend store tests**

Run:

```powershell
cd web
npm run test -- customerSession.spec.js
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add web/src/stores/customerSession.js web/src/api/sse.js web/tests/customerSession.spec.js
git commit -m "feat: 增加客户会话状态"
```

### Task 7: Build Customer Verification Dialog and History Drawer

**Files:**
- Create: `web/src/components/CustomerVerifyDialog.vue`
- Create: `web/src/components/CustomerHistoryDrawer.vue`
- Create: `web/tests/CustomerVerifyDialog.spec.js`
- Create: `web/tests/CustomerHistoryDrawer.spec.js`

- [ ] **Step 1: Write failing component tests**

```javascript
// web/tests/CustomerVerifyDialog.spec.js
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CustomerVerifyDialog from '../src/components/CustomerVerifyDialog.vue'

it('提交手机号和最近订单号', async () => {
  const wrapper = mount(CustomerVerifyDialog, { props: { modelValue: true } })
  await wrapper.find('[data-test="customer-phone"]').setValue('13800000001')
  await wrapper.find('[data-test="recent-order-id"]').setValue('20260531002')
  await wrapper.find('[data-test="verify-submit"]').trigger('click')
  expect(wrapper.emitted('verify')[0]).toEqual(['13800000001', '20260531002'])
})
```

```javascript
// web/tests/CustomerHistoryDrawer.spec.js
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CustomerHistoryDrawer from '../src/components/CustomerHistoryDrawer.vue'

it('选择历史咨询', async () => {
  const wrapper = mount(CustomerHistoryDrawer, {
    props: {
      modelValue: true,
      conversations: [{
        id: 'c1', summary: '物流查询', status: 'ai_handling',
        last_message_at: '2026-06-04T10:00:00Z',
      }],
    },
  })
  await wrapper.find('[data-test="history-c1"]').trigger('click')
  expect(wrapper.emitted('select')[0]).toEqual(['c1'])
})
```

- [ ] **Step 2: Run component tests and verify failure**

Run:

```powershell
cd web
npm run test -- CustomerVerifyDialog.spec.js CustomerHistoryDrawer.spec.js
```

Expected: FAIL because both components do not exist.

- [ ] **Step 3: Implement focused components**

`CustomerVerifyDialog.vue` requirements:

- Use `el-dialog`, two labeled inputs, one primary submit action, loading state, and inline error text.
- Emit `verify(phone, recentOrderId)` and `update:modelValue`.
- Do not retain raw phone or order number after successful verification or dialog close.

`CustomerHistoryDrawer.vue` requirements:

- Use `el-drawer`.
- Render summary fallback `新咨询`, localized status, and formatted last-message time.
- Emit `select(conversationId)`, `retry`, and `update:modelValue`.
- Include loading, empty, and failure states.

- [ ] **Step 4: Run component tests**

Run:

```powershell
cd web
npm run test -- CustomerVerifyDialog.spec.js CustomerHistoryDrawer.spec.js
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add web/src/components/CustomerVerifyDialog.vue web/src/components/CustomerHistoryDrawer.vue web/tests/CustomerVerifyDialog.spec.js web/tests/CustomerHistoryDrawer.spec.js
git commit -m "feat: 增加客户验证和历史组件"
```

### Task 8: Rebuild Chat Entry, Resume Flow, and Account Menu

**Files:**
- Modify: `web/src/views/ChatView.vue`
- Modify: `web/tests/ChatView.spec.js`

- [ ] **Step 1: Replace local-cache tests with failing session behavior tests**

Add or replace tests in `web/tests/ChatView.spec.js`:

```javascript
it('无客户令牌时进入全新咨询页', async () => {
  const pinia = createPinia()
  const wrapper = mount(ChatView, { global: { plugins: [pinia] } })
  await flushPromises()
  expect(wrapper.text()).toContain('您好，请问有什么可以帮您？')
  expect(wrapper.text()).not.toContain('服务上下文')
  expect(wrapper.find('[data-test="customer-ref-input"]').exists()).toBe(false)
})

it('最近会话在两小时内时自动续聊', async () => {
  localStorage.setItem('customer_token', 'token-1')
  localStorage.setItem('customer_masked_phone', '138****0001')
  localStorage.setItem('customer_expires_at', '2099-06-11T00:00:00Z')
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ should_resume: true, conversation: { id: 'c1' } }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => [{ role: 'customer', content: '继续查物流', meta: {} }],
    }))

  const wrapper = mount(ChatView)
  await flushPromises()

  expect(wrapper.text()).toContain('继续查物流')
})

it('最近会话超过两小时时展示全新咨询页', async () => {
  localStorage.setItem('customer_token', 'token-1')
  localStorage.setItem('customer_masked_phone', '138****0001')
  localStorage.setItem('customer_expires_at', '2099-06-11T00:00:00Z')
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({ should_resume: false, conversation: { id: 'old' } }),
  })))

  const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } })
  await flushPromises()

  expect(wrapper.text()).toContain('您好，请问有什么可以帮您？')
  expect(fetch).toHaveBeenCalledOnce()
})

it('点击新咨询后清空当前视图但不退出客户账户', async () => {
  localStorage.setItem('customer_token', 'token-1')
  localStorage.setItem('customer_masked_phone', '138****0001')
  localStorage.setItem('customer_expires_at', '2099-06-11T00:00:00Z')
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ should_resume: true, conversation: { id: 'c1' } }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => [{ role: 'customer', content: '旧消息', meta: {} }],
    }))

  const wrapper = mount(ChatView, { global: { plugins: [createPinia()] } })
  await flushPromises()
  await wrapper.find('[data-test="new-consultation"]').trigger('click')

  expect(wrapper.text()).not.toContain('旧消息')
  expect(wrapper.text()).toContain('138****0001')
})
```

Use a real Pinia instance in these tests; do not introduce `@pinia/testing` unless it is already installed.

- [ ] **Step 2: Run ChatView tests and verify failure**

Run:

```powershell
cd web
npm run test -- ChatView.spec.js
```

Expected: FAIL because the current page restores `chat_messages`, exposes customer ref, and has no recent-session flow.

- [ ] **Step 3: Implement the new ChatView behavior**

In `ChatView.vue`:

- Remove `loadCachedMessages`, `persistChat`, `customerRef` input, sync timer, and the right service panel.
- On mount, call `customerSession.restore()`, remove legacy keys `chat_messages`, `chat_conversation_id`, and `chat_customer_ref`, then initialize recent conversation.
- Add functions:

```javascript
async function initializeRecentConversation() {
  messages.value = []
  conversationId.value = ''
  if (!customerSession.isLoggedIn) return
  try {
    const recent = await api('/customer/conversations/recent', { token: customerSession.token })
    if (!recent.should_resume || !recent.conversation) return
    await openConversation(recent.conversation.id)
  } catch (error) {
    if (String(error.message).includes('登录')) customerSession.logout()
  }
}

async function openConversation(id) {
  const rows = await api(`/customer/conversations/${id}/messages`, {
    token: customerSession.token,
  })
  conversationId.value = id
  messages.value = rows.map((message) => ({
    role: message.role,
    content: message.content,
    citations: message.meta?.citations || [],
    agent_trace: message.meta?.agent_trace || [],
  }))
  historyOpen.value = false
}

function startNewConsultation() {
  conversationId.value = ''
  messages.value = []
  input.value = ''
}
```

- Pass `customerSession.token` to `chatStream`.
- Handle `identity_required` by replacing the pending message with a verification prompt and opening `CustomerVerifyDialog`.
- Handle `access_denied` by replacing the pending message with the server-safe denial text.
- Use the verified identity for logged-in requests; use a stable anonymous ref such as `anonymous-web` for unauthenticated general consultation.
- Add account menu actions for verify identity, history, new consultation, switch account, and logout.
- Open verification dialog when an unauthenticated user requests history.
- Keep quick intents, citations, streaming reply animation, and human-confirmation messaging.
- Use a centered single-column chat shell with responsive width and no internal progress sidebar.

- [ ] **Step 4: Run ChatView and full frontend tests**

Run:

```powershell
cd web
npm run test -- ChatView.spec.js
npm run test
npm run build
```

Expected: ChatView tests pass, full Vitest suite passes, and Vite build completes.

- [ ] **Step 5: Commit**

```powershell
git add web/src/views/ChatView.vue web/tests/ChatView.spec.js
git commit -m "feat: 重构客户 Chat 会话入口"
```

### Task 9: Full Verification and Browser Acceptance

**Files:**
- Modify only if verification exposes a defect.

- [ ] **Step 1: Run complete backend unit suite**

Run:

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests -q -m "not integration"
```

Expected: all non-integration tests pass.

- [ ] **Step 2: Run business-system tests**

Run:

```powershell
cd business-system
.venv\Scripts\python.exe -m pytest tests -q
```

Expected: all tests pass.

- [ ] **Step 3: Run complete frontend suite and build**

Run:

```powershell
cd web
npm run test
npm run build
```

Expected: all tests pass and production build succeeds.

- [ ] **Step 4: Start services from this worktree and verify the customer workflow**

Before starting, inspect port owners for `5173`, `8000`, and `8100`; stop and restart any dev server whose command line points at the main repository instead of this worktree.

Verify in the browser:

1. Open `/chat` without a customer token: a clean new consultation page appears.
2. Confirm the customer identifier input and internal progress sidebar are absent.
3. Verify identity with seed data `13800000001` and most recent order `20260531002`.
4. Confirm the account menu displays `138****0001`.
5. Send a message, reload within two hours, and confirm the conversation resumes.
6. Click new consultation and confirm the view clears while the account remains signed in.
7. Open history and confirm the prior conversation can be selected.
8. Change the test conversation's `last_message_at` to more than two hours ago, reload, and confirm a clean new consultation page appears.
9. Expire or remove the customer token and confirm history requests require verification again.
10. Check desktop and mobile widths for non-overlapping header, menu, drawer, messages, and composer.

- [ ] **Step 5: Commit verification fixes only when files changed**

```powershell
git status --short
git add web/src/views/ChatView.vue
git commit -m "fix: 完善客户会话体验验证"
```

Stage the exact changed files shown by `git status --short`; the `web/src/views/ChatView.vue` command is the expected example. Skip this commit when verification requires no code changes.
