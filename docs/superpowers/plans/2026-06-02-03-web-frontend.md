# 前端 web（子计划③）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做出客服 Agent 的两个核心前端页面——客户聊天端（SSE 流式对话 + 引用出处展示）和坐席工作台（会话列表 + 对话流 + 待确认动作卡片 + 确认/驳回），让"人在环路"这个最大亮点可视化、可现场演示。并补齐 cs-agent 缺失的只读接口与 CORS。

**Architecture:** 前端 Vite + Vue3 + Element Plus + Pinia + vue-router，只调 cs-agent（不直连 business-system）。先给 cs-agent 补三个只读接口（会话列表、会话消息历史）与 CORS 中间件，再做前端。客户端匿名（按设计：用手机号/会话标识进入）；工作台需登录（JWT Bearer）。看板页留到②b-2 后端完成后做。

**Tech Stack:** 后端补丁：FastAPI（cs-agent，Python 3.13）。前端：Vite 5、Vue 3、Element Plus、Pinia、vue-router、原生 fetch（SSE 用 fetch + ReadableStream 解析）、Vitest + @vue/test-utils。

---

## 前置：已确认的后端接口契约（来自已合并的 cs-agent 代码）

- `POST /auth/login` body `{username, password}` → `{access_token, token_type, role, display_name}`；401 错误。
- `POST /chat` body `{conversation_id?, customer_ref, message}` → **SSE 流**，事件：
  - `{"type":"start","conversation_id":"..."}`
  - `{"type":"response","content":"..."}` 或 `{"type":"awaiting_confirmation","pending_action_id":N,"content":"..."}`
  - `{"type":"done","conversation_id":"..."}`
- `GET /pending-actions`（需 Bearer）→ `[{id, conversation_id, tool_name, params, created_at}]`
- `POST /pending-actions/{id}/review`（需 Bearer）body `{approved: bool}` → `{status, pending_status, message}`（或 `{status:"not_found"|"noop",...}`）
- 端口：cs-agent **8000**、business-system 8100、前端 dev **5173**。

**本计划要补的后端缺口**（Task 1-2）：CORS、`GET /conversations`、`GET /conversations/{id}/messages`。

---

## 文件结构

```
# 后端补丁（cs-agent）
cs-agent/app/main.py                      # 修改：加 CORSMiddleware
cs-agent/app/routers/conversation_router.py  # 新增：会话列表 + 消息历史
cs-agent/tests/test_conversation_api.py   # 新增

# 前端（web/）
web/
├─ index.html
├─ package.json
├─ vite.config.js
├─ vitest.config.js
├─ .env.development            # VITE_API_BASE=http://localhost:8000
├─ src/
│  ├─ main.js                  # 挂载 app + Element Plus + router + pinia
│  ├─ App.vue
│  ├─ router/index.js          # /chat, /agent-desk, /login
│  ├─ stores/auth.js           # Pinia：token、登录态
│  ├─ api/client.js            # fetch 封装（带 token）
│  ├─ api/sse.js               # SSE 解析（fetch + ReadableStream）
│  ├─ views/
│  │  ├─ ChatView.vue          # 客户聊天端
│  │  ├─ LoginView.vue         # 坐席登录
│  │  └─ AgentDeskView.vue     # 坐席工作台
│  └─ components/
│     ├─ MessageBubble.vue     # 消息气泡（含引用展示）
│     ├─ ConversationList.vue  # 工作台左栏会话列表
│     └─ PendingActionCard.vue # 待确认动作卡片（确认/驳回）
└─ tests/
   ├─ MessageBubble.spec.js
   └─ PendingActionCard.spec.js
```

---

## Task 1: cs-agent 加 CORS

**Files:**
- Modify: `cs-agent/app/main.py`
- Test: `cs-agent/tests/test_conversation_api.py`（建文件，先放 CORS 冒烟）

- [ ] **Step 1: 写测试（先失败）**

`cs-agent/tests/test_conversation_api.py`:
```python
def test_cors_headers_present(client):
    # 预检请求应返回 CORS 头
    r = client.options("/health/live", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    })
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_conversation_api.py -v`
Expected: FAIL（无 CORS 头）

- [ ] **Step 3: 加 CORS 中间件**

修改 `cs-agent/app/main.py`，在 `app = FastAPI(...)` 之后、`include_router` 之前加：
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_conversation_api.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```
git add cs-agent/app/main.py cs-agent/tests/test_conversation_api.py
git commit -m "feat: cs-agent 加 CORS 中间件（前端跨域）"
```
（commit 末尾统一加 `Co-Authored-By: Claude <noreply@anthropic.com>`，后续不再重复。）

---

## Task 2: cs-agent 会话列表 + 消息历史接口

**Files:**
- Create: `cs-agent/app/routers/conversation_router.py`
- Modify: `cs-agent/app/main.py`（挂载）
- Test: `cs-agent/tests/test_conversation_api.py`（追加）

工作台要展示会话列表和某会话的消息流。两个只读接口，需登录（Bearer）。

- [ ] **Step 1: 追加测试（先失败）**

在 `cs-agent/tests/test_conversation_api.py` 追加：
```python
from app.auth import hash_password
from app.models import Conversation, Message, User


def _login(client, db_session):
    db_session.add(User(username="a1", password_hash=hash_password("pw"), role="agent", display_name="一号"))
    db_session.commit()
    token = client.post("/auth/login", json={"username": "a1", "password": "pw"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_list_conversations(client, db_session):
    h = _login(client, db_session)
    db_session.add(Conversation(id="c1", customer_ref="138", status="ai_handling"))
    db_session.add(Conversation(id="c2", customer_ref="139", status="awaiting_confirmation"))
    db_session.commit()
    r = client.get("/conversations", headers=h)
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert "c1" in ids and "c2" in ids


def test_list_conversations_filter_status(client, db_session):
    h = _login(client, db_session)
    db_session.add(Conversation(id="c1", customer_ref="138", status="ai_handling"))
    db_session.add(Conversation(id="c2", customer_ref="139", status="awaiting_confirmation"))
    db_session.commit()
    r = client.get("/conversations", params={"status": "awaiting_confirmation"}, headers=h)
    assert r.status_code == 200
    assert [c["id"] for c in r.json()] == ["c2"]


def test_get_conversation_messages(client, db_session):
    h = _login(client, db_session)
    db_session.add(Conversation(id="c1", customer_ref="138", status="ai_handling"))
    db_session.add(Message(conversation_id="c1", role="customer", content="你好"))
    db_session.add(Message(conversation_id="c1", role="ai", content="您好，有什么可以帮您"))
    db_session.commit()
    r = client.get("/conversations/c1/messages", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["role"] == "customer"
    assert body[1]["content"] == "您好，有什么可以帮您"


def test_conversations_require_auth(client):
    assert client.get("/conversations").status_code == 401
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_conversation_api.py -v`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 写会话路由**

`cs-agent/app/routers/conversation_router.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Conversation, Message
from app.routers.auth_router import current_user

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
def list_conversations(status: str | None = Query(None), db: Session = Depends(get_db), user=Depends(current_user)):
    q = db.query(Conversation)
    if status:
        q = q.filter(Conversation.status == status)
    rows = q.order_by(Conversation.created_at.desc()).all()
    return [{"id": c.id, "customer_ref": c.customer_ref, "status": c.status,
             "assigned_agent_id": c.assigned_agent_id, "summary": c.summary,
             "created_at": c.created_at.isoformat()} for c in rows]


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = db.query(Message).filter_by(conversation_id=conversation_id).order_by(Message.created_at, Message.id).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "meta": m.meta,
             "created_at": m.created_at.isoformat()} for m in rows]
```

- [ ] **Step 4: 挂载到 main**

修改 `cs-agent/app/main.py`：import 改为 `from app.routers import auth_router, chat_router, confirm_router, conversation_router`，并加 `app.include_router(conversation_router.router)`。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests/test_conversation_api.py -v`
Expected: PASS（CORS 1 + 会话 4 = 5）

- [ ] **Step 6: 全量回归 + 提交**

Run: `cd cs-agent && .venv\Scripts\python.exe -m pytest tests -q -m "not integration"`
Expected: 全过（②b-1 的 54 + 本次 5 = 59）

```
git add cs-agent/app/routers/conversation_router.py cs-agent/app/main.py cs-agent/tests/test_conversation_api.py
git commit -m "feat: cs-agent 会话列表与消息历史只读接口"
```

---

## Task 3: 前端脚手架（Vite + Vue3 + Element Plus）

**Files:**
- Create: `web/package.json`、`web/vite.config.js`、`web/vitest.config.js`、`web/index.html`、`web/.env.development`
- Create: `web/src/main.js`、`web/src/App.vue`

- [ ] **Step 1: 写 package.json**

`web/package.json`:
```json
{
  "name": "cs-agent-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "vue": "^3.5.13",
    "vue-router": "^4.5.0",
    "pinia": "^2.3.0",
    "element-plus": "^2.9.1",
    "@element-plus/icons-vue": "^2.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.2.1",
    "vite": "^6.0.5",
    "vitest": "^2.1.8",
    "@vue/test-utils": "^2.4.6",
    "jsdom": "^25.0.1"
  }
}
```

- [ ] **Step 2: 写配置文件**

`web/vite.config.js`:
```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173 },
})
```

`web/vitest.config.js`:
```javascript
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: { environment: 'jsdom', globals: true },
})
```

`web/index.html`:
```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>智能售后客服 Agent 工作台</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

`web/.env.development`:
```
VITE_API_BASE=http://localhost:8000
```

- [ ] **Step 3: 写入口与根组件**

`web/src/main.js`:
```javascript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
```

`web/src/App.vue`:
```vue
<template>
  <router-view />
</template>
```

- [ ] **Step 4: 安装依赖并验证构建**

Run（Windows PowerShell）:
```
cd web
npm install
```
Expected: 安装成功。
> 注：router/index.js、stores、views 在后续任务创建；本任务先把脚手架装起来。为让 `npm install` 后不因缺文件报错，本任务**不运行 dev/build**，只验证 `npm install` 成功。下个任务补 router 后再验证启动。

- [ ] **Step 5: 提交**

```
git add web/package.json web/vite.config.js web/vitest.config.js web/index.html web/.env.development web/src/main.js web/src/App.vue
git commit -m "chore: web 前端脚手架（Vite+Vue3+Element Plus）"
```

---

## Task 4: 路由 + API 客户端 + auth store

**Files:**
- Create: `web/src/router/index.js`
- Create: `web/src/api/client.js`
- Create: `web/src/api/sse.js`
- Create: `web/src/stores/auth.js`

- [ ] **Step 1: 写 API 客户端**

`web/src/api/client.js`:
```javascript
const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export function apiUrl(path) {
  return `${BASE}${path}`
}

export async function api(path, { method = 'GET', body, token } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(apiUrl(path), {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail.detail || `请求失败 ${resp.status}`)
  }
  return resp.json()
}
```

- [ ] **Step 2: 写 SSE 解析**

`web/src/api/sse.js`:
```javascript
import { apiUrl } from './client'

/**
 * 发起 SSE 对话。onEvent 收到每个解析后的事件对象。
 * 用 fetch + ReadableStream 解析 text/event-stream。
 */
export async function chatStream({ conversationId, customerRef, message }, onEvent) {
  const resp = await fetch(apiUrl('/chat'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId || null,
      customer_ref: customerRef,
      message,
    }),
  })
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop()
    for (const part of parts) {
      const line = part.trim()
      if (line.startsWith('data:')) {
        const json = line.slice(5).trim()
        try {
          onEvent(JSON.parse(json))
        } catch {
          /* 忽略解析失败的分片 */
        }
      }
    }
  }
}
```

- [ ] **Step 3: 写 auth store**

`web/src/stores/auth.js`:
```javascript
import { defineStore } from 'pinia'
import { api } from '../api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('cs_token') || '',
    role: localStorage.getItem('cs_role') || '',
    displayName: localStorage.getItem('cs_name') || '',
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
  },
  actions: {
    async login(username, password) {
      const data = await api('/auth/login', { method: 'POST', body: { username, password } })
      this.token = data.access_token
      this.role = data.role
      this.displayName = data.display_name
      localStorage.setItem('cs_token', this.token)
      localStorage.setItem('cs_role', this.role)
      localStorage.setItem('cs_name', this.displayName)
    },
    logout() {
      this.token = ''
      this.role = ''
      this.displayName = ''
      localStorage.removeItem('cs_token')
      localStorage.removeItem('cs_role')
      localStorage.removeItem('cs_name')
    },
  },
})
```

- [ ] **Step 4: 写路由（工作台需登录守卫）**

`web/src/router/index.js`:
```javascript
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', component: () => import('../views/ChatView.vue') },
  { path: '/login', component: () => import('../views/LoginView.vue') },
  { path: '/agent-desk', component: () => import('../views/AgentDeskView.vue'), meta: { requiresAuth: true } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  if (to.meta.requiresAuth) {
    const auth = useAuthStore()
    if (!auth.isLoggedIn) return '/login'
  }
  return true
})

export default router
```

- [ ] **Step 5: 验证 dev 启动（router 已就绪，但 views 还没建——用占位）**

先建占位 view 避免动态 import 失败（下个任务覆盖为真实内容）：
`web/src/views/ChatView.vue`、`web/src/views/LoginView.vue`、`web/src/views/AgentDeskView.vue` 各写：
```vue
<template><div>占位</div></template>
```
Run: `cd web && npm run dev`（启动后 Ctrl+C 即可，只验证编译无错）。
Expected: Vite 启动，无编译错误，监听 5173。

- [ ] **Step 6: 提交**

```
git add web/src/router web/src/api web/src/stores web/src/views
git commit -m "feat: web 路由、API 客户端、SSE 解析与 auth store"
```

---

## Task 5: 消息气泡组件（含引用展示）+ 单测

**Files:**
- Create: `web/src/components/MessageBubble.vue`
- Test: `web/tests/MessageBubble.spec.js`

- [ ] **Step 1: 写组件单测（先失败）**

`web/tests/MessageBubble.spec.js`:
```javascript
import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import MessageBubble from '../src/components/MessageBubble.vue'

describe('MessageBubble', () => {
  it('渲染客户消息内容', () => {
    const w = mount(MessageBubble, { props: { role: 'customer', content: '我的订单到哪了' } })
    expect(w.text()).toContain('我的订单到哪了')
  })

  it('AI 消息带引用出处时展示来源', () => {
    const w = mount(MessageBubble, {
      props: {
        role: 'ai',
        content: '物流停滞可申请催办',
        citations: [{ title: '物流催办政策', source: 'aftersale_policy.md' }],
      },
    })
    expect(w.text()).toContain('物流催办政策')
  })

  it('不同角色应用不同样式类', () => {
    const w = mount(MessageBubble, { props: { role: 'customer', content: 'x' } })
    expect(w.find('.bubble-customer').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd web && npm run test`
Expected: FAIL（组件不存在）

- [ ] **Step 3: 写组件**

`web/src/components/MessageBubble.vue`:
```vue
<script setup>
defineProps({
  role: { type: String, required: true }, // customer / ai / agent / system
  content: { type: String, default: '' },
  citations: { type: Array, default: () => [] },
})
</script>

<template>
  <div class="bubble-row" :class="`row-${role}`">
    <div class="bubble" :class="`bubble-${role}`">
      <div class="bubble-content">{{ content }}</div>
      <div v-if="citations.length" class="citations">
        <span class="citation-label">引用：</span>
        <el-tag v-for="(c, i) in citations" :key="i" size="small" type="info" class="citation-tag">
          {{ c.title }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bubble-row { display: flex; margin: 8px 0; }
.row-customer { justify-content: flex-end; }
.row-ai, .row-agent, .row-system { justify-content: flex-start; }
.bubble { max-width: 70%; padding: 10px 14px; border-radius: 10px; line-height: 1.5; }
.bubble-customer { background: #409eff; color: #fff; }
.bubble-ai { background: #f4f4f5; color: #303133; }
.bubble-agent { background: #e1f3d8; color: #303133; }
.bubble-system { background: #fdf6ec; color: #909399; font-size: 13px; }
.citations { margin-top: 6px; }
.citation-label { font-size: 12px; color: #909399; }
.citation-tag { margin-right: 4px; }
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd web && npm run test`
Expected: 3 个 PASS

- [ ] **Step 5: 提交**

```
git add web/src/components/MessageBubble.vue web/tests/MessageBubble.spec.js
git commit -m "feat: web 消息气泡组件（含引用展示）"
```

---

## Task 6: 客户聊天端 ChatView

**Files:**
- Modify: `web/src/views/ChatView.vue`（替换占位）

- [ ] **Step 1: 写 ChatView**

`web/src/views/ChatView.vue`:
```vue
<script setup>
import { ref } from 'vue'
import { chatStream } from '../api/sse'
import MessageBubble from '../components/MessageBubble.vue'

const customerRef = ref('13800000001')
const conversationId = ref('')
const input = ref('')
const messages = ref([])
const sending = ref(false)

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  messages.value.push({ role: 'customer', content: text })
  input.value = ''
  sending.value = true
  let aiContent = ''
  let aiIndex = -1
  try {
    await chatStream(
      { conversationId: conversationId.value, customerRef: customerRef.value, message: text },
      (ev) => {
        if (ev.type === 'start') {
          conversationId.value = ev.conversation_id
        } else if (ev.type === 'response') {
          aiContent = ev.content
          if (aiIndex === -1) {
            messages.value.push({ role: 'ai', content: aiContent })
            aiIndex = messages.value.length - 1
          } else {
            messages.value[aiIndex].content = aiContent
          }
        } else if (ev.type === 'awaiting_confirmation') {
          messages.value.push({ role: 'system', content: ev.content || '该操作已提交人工确认，请稍候。' })
        }
      },
    )
  } catch (e) {
    messages.value.push({ role: 'system', content: '网络错误，请重试。' })
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="chat-page">
    <div class="chat-header">
      <span>智能售后客服</span>
      <el-input v-model="customerRef" size="small" style="width: 160px" placeholder="手机号/标识" />
    </div>
    <div class="chat-body">
      <MessageBubble
        v-for="(m, i) in messages"
        :key="i"
        :role="m.role"
        :content="m.content"
        :citations="m.citations || []"
      />
      <div v-if="!messages.length" class="empty">您好，请问有什么可以帮您？</div>
    </div>
    <div class="chat-input">
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        placeholder="输入您的问题，回车发送"
        @keydown.enter.prevent="send"
      />
      <el-button type="primary" :loading="sending" @click="send">发送</el-button>
    </div>
  </div>
</template>

<style scoped>
.chat-page { display: flex; flex-direction: column; height: 100vh; max-width: 720px; margin: 0 auto; }
.chat-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #ebeef5; font-weight: 600; }
.chat-body { flex: 1; overflow-y: auto; padding: 16px; }
.empty { color: #909399; text-align: center; margin-top: 40px; }
.chat-input { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #ebeef5; }
</style>
```

- [ ] **Step 2: 手动验证（需后端在跑）**

前置：cs-agent 在 8000 跑（连真 Postgres + 有 DASHSCOPE key）、business-system 在 8100 跑、已灌种子。
Run: `cd web && npm run dev`，浏览器开 `http://localhost:5173/chat`，输入"订单 20260531002 到哪了"，应看到 AI 流式回复。
> 若后端未就绪，本步骤记录为"待 docker-compose 阶段（子计划④）统一联调"，不阻塞提交（ChatView 逻辑已完成，SSE 解析有 sse.js 保证）。

- [ ] **Step 3: 提交**

```
git add web/src/views/ChatView.vue
git commit -m "feat: web 客户聊天端（SSE 流式对话）"
```

---

## Task 7: 待确认动作卡片组件 + 单测

**Files:**
- Create: `web/src/components/PendingActionCard.vue`
- Test: `web/tests/PendingActionCard.spec.js`

- [ ] **Step 1: 写单测（先失败）**

`web/tests/PendingActionCard.spec.js`:
```javascript
import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import PendingActionCard from '../src/components/PendingActionCard.vue'

const action = {
  id: 1,
  conversation_id: 'c1',
  tool_name: 'apply_refund',
  params: { order_id: 'O1', amount: 499, reason: '物流停滞' },
  created_at: '2026-06-02T00:00:00',
}

describe('PendingActionCard', () => {
  it('展示工具名与关键参数', () => {
    const w = mount(PendingActionCard, { props: { action } })
    expect(w.text()).toContain('apply_refund')
    expect(w.text()).toContain('O1')
    expect(w.text()).toContain('499')
  })

  it('点确认触发 review 事件且 approved=true', async () => {
    const w = mount(PendingActionCard, { props: { action } })
    await w.find('.btn-approve').trigger('click')
    expect(w.emitted('review')).toBeTruthy()
    expect(w.emitted('review')[0]).toEqual([{ id: 1, approved: true }])
  })

  it('点驳回触发 review 事件且 approved=false', async () => {
    const w = mount(PendingActionCard, { props: { action } })
    await w.find('.btn-reject').trigger('click')
    expect(w.emitted('review')[0]).toEqual([{ id: 1, approved: false }])
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd web && npm run test`
Expected: FAIL

- [ ] **Step 3: 写组件**

`web/src/components/PendingActionCard.vue`:
```vue
<script setup>
const props = defineProps({
  action: { type: Object, required: true },
})
const emit = defineEmits(['review'])

const RISK_LABEL = {
  apply_refund: '发起退款',
  change_address: '修改收货地址',
  issue_coupon: '发放优惠券',
}
</script>

<template>
  <el-card class="pending-card" shadow="hover">
    <div class="pending-title">
      <el-tag type="danger" size="small">待确认</el-tag>
      <span class="tool">{{ RISK_LABEL[action.tool_name] || action.tool_name }}（{{ action.tool_name }}）</span>
    </div>
    <div class="params">
      <div v-for="(v, k) in action.params" :key="k" class="param-row">
        <span class="param-key">{{ k }}：</span><span class="param-val">{{ v }}</span>
      </div>
    </div>
    <div class="actions">
      <el-button class="btn-approve" type="success" size="small" @click="emit('review', { id: action.id, approved: true })">
        确认执行
      </el-button>
      <el-button class="btn-reject" type="info" size="small" @click="emit('review', { id: action.id, approved: false })">
        驳回
      </el-button>
    </div>
  </el-card>
</template>

<style scoped>
.pending-card { margin-bottom: 12px; border-left: 3px solid #f56c6c; }
.pending-title { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.tool { font-weight: 600; }
.params { background: #fafafa; padding: 8px; border-radius: 4px; font-size: 13px; }
.param-key { color: #909399; }
.actions { margin-top: 10px; display: flex; gap: 8px; }
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd web && npm run test`
Expected: MessageBubble 3 + PendingActionCard 3 = 6 PASS

- [ ] **Step 5: 提交**

```
git add web/src/components/PendingActionCard.vue web/tests/PendingActionCard.spec.js
git commit -m "feat: web 待确认动作卡片组件"
```

---

## Task 8: 坐席登录 LoginView

**Files:**
- Modify: `web/src/views/LoginView.vue`（替换占位）

- [ ] **Step 1: 写 LoginView**

`web/src/views/LoginView.vue`:
```vue
<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const username = ref('agent')
const password = ref('agent123')
const loading = ref(false)
const auth = useAuthStore()
const router = useRouter()

async function doLogin() {
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    ElMessage.success('登录成功')
    router.push('/agent-desk')
  } catch (e) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2>坐席登录</h2>
      <el-form @submit.prevent="doLogin">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="doLogin">登录</el-button>
      </el-form>
      <p class="hint">演示账号：agent / agent123</p>
    </el-card>
  </div>
</template>

<style scoped>
.login-page { display: flex; justify-content: center; align-items: center; height: 100vh; background: #f5f7fa; }
.login-card { width: 360px; }
.hint { color: #909399; font-size: 13px; margin-top: 12px; text-align: center; }
</style>
```

- [ ] **Step 2: 提交**

```
git add web/src/views/LoginView.vue
git commit -m "feat: web 坐席登录页"
```

---

## Task 9: 坐席工作台 AgentDeskView（三栏：会话列表/对话流/待确认）

**Files:**
- Create: `web/src/components/ConversationList.vue`
- Modify: `web/src/views/AgentDeskView.vue`（替换占位）

- [ ] **Step 1: 写会话列表组件**

`web/src/components/ConversationList.vue`:
```vue
<script setup>
defineProps({
  conversations: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
})
defineEmits(['select'])

const STATUS_TAG = {
  ai_handling: { text: 'AI处理中', type: 'primary' },
  awaiting_confirmation: { text: '待确认', type: 'danger' },
  human_handling: { text: '人工处理', type: 'warning' },
  resolved: { text: '已解决', type: 'success' },
  closed: { text: '已关闭', type: 'info' },
}
</script>

<template>
  <div class="conv-list">
    <div
      v-for="c in conversations"
      :key="c.id"
      class="conv-item"
      :class="{ active: c.id === activeId }"
      @click="$emit('select', c.id)"
    >
      <div class="conv-top">
        <span class="conv-ref">{{ c.customer_ref }}</span>
        <el-tag :type="(STATUS_TAG[c.status] || {}).type || 'info'" size="small">
          {{ (STATUS_TAG[c.status] || {}).text || c.status }}
        </el-tag>
      </div>
      <div class="conv-id">{{ c.id }}</div>
    </div>
    <div v-if="!conversations.length" class="empty">暂无会话</div>
  </div>
</template>

<style scoped>
.conv-list { height: 100%; overflow-y: auto; }
.conv-item { padding: 10px 12px; border-bottom: 1px solid #ebeef5; cursor: pointer; }
.conv-item:hover { background: #f5f7fa; }
.conv-item.active { background: #ecf5ff; }
.conv-top { display: flex; justify-content: space-between; align-items: center; }
.conv-ref { font-weight: 600; }
.conv-id { font-size: 12px; color: #909399; margin-top: 2px; }
.empty { color: #909399; text-align: center; padding: 20px; }
</style>
```

- [ ] **Step 2: 写工作台**

`web/src/views/AgentDeskView.vue`:
```vue
<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'
import ConversationList from '../components/ConversationList.vue'
import MessageBubble from '../components/MessageBubble.vue'
import PendingActionCard from '../components/PendingActionCard.vue'

const auth = useAuthStore()
const conversations = ref([])
const activeId = ref('')
const messages = ref([])
const pendingActions = ref([])

async function loadConversations() {
  conversations.value = await api('/conversations', { token: auth.token })
}

async function loadPending() {
  pendingActions.value = await api('/pending-actions', { token: auth.token })
}

async function selectConversation(id) {
  activeId.value = id
  messages.value = await api(`/conversations/${id}/messages`, { token: auth.token })
}

async function onReview({ id, approved }) {
  try {
    const res = await api(`/pending-actions/${id}/review`, {
      method: 'POST', body: { approved }, token: auth.token,
    })
    ElMessage.success(approved ? '已确认执行' : '已驳回')
    await loadPending()
    if (activeId.value) await selectConversation(activeId.value)
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  }
}

onMounted(() => {
  loadConversations()
  loadPending()
})
</script>

<template>
  <div class="desk">
    <div class="col col-left">
      <div class="col-title">会话列表</div>
      <ConversationList :conversations="conversations" :active-id="activeId" @select="selectConversation" />
    </div>
    <div class="col col-mid">
      <div class="col-title">对话内容</div>
      <div class="msg-area">
        <MessageBubble v-for="m in messages" :key="m.id" :role="m.role" :content="m.content"
                       :citations="(m.meta && m.meta.citations) || []" />
        <div v-if="!messages.length" class="empty">选择左侧会话查看对话</div>
      </div>
    </div>
    <div class="col col-right">
      <div class="col-title">
        待确认动作
        <el-badge :value="pendingActions.length" :hidden="!pendingActions.length" />
      </div>
      <div class="pending-area">
        <PendingActionCard v-for="a in pendingActions" :key="a.id" :action="a" @review="onReview" />
        <div v-if="!pendingActions.length" class="empty">暂无待确认动作</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.desk { display: flex; height: 100vh; }
.col { display: flex; flex-direction: column; border-right: 1px solid #ebeef5; }
.col-left { width: 280px; }
.col-mid { flex: 1; }
.col-right { width: 360px; border-right: none; }
.col-title { padding: 12px 16px; font-weight: 600; border-bottom: 1px solid #ebeef5; }
.msg-area, .pending-area { flex: 1; overflow-y: auto; padding: 16px; }
.empty { color: #909399; text-align: center; margin-top: 40px; }
</style>
```

- [ ] **Step 3: 跑组件单测确认未破坏**

Run: `cd web && npm run test`
Expected: 6 PASS（MessageBubble 3 + PendingActionCard 3）

- [ ] **Step 4: 提交**

```
git add web/src/components/ConversationList.vue web/src/views/AgentDeskView.vue
git commit -m "feat: web 坐席工作台（会话列表/对话流/待确认确认驳回）"
```

---

## Task 10: 端到端联调验证（手动）

需要全后端在跑。本任务不写代码，验证整条人在环路在浏览器里跑通。

- [ ] **Step 1: 起后端**

```
# 终端1：business-system（需本地 Postgres）
cd business-system && .venv\Scripts\python.exe -m app.seed
.venv\Scripts\uvicorn.exe app.main:app --port 8100
# 终端2：cs-agent（连同一 Postgres + .env 有 key）
cd cs-agent && .venv\Scripts\python.exe -m app.seed_agent
.venv\Scripts\uvicorn.exe app.main:app --port 8000
# 终端3：前端
cd web && npm run dev
```

- [ ] **Step 2: 走一遍剧情**

1. 开 `http://localhost:5173/chat`，发"订单 20260531002 物流停了，我要退款 499"。
2. 应看到 AI 流式回复，且出现"已提交人工确认"系统提示。
3. 开 `http://localhost:5173/login`，用 agent/agent123 登录 → 工作台。
4. 右栏应出现"待确认动作"卡片（apply_refund，order_id=20260531002，amount=499）。
5. 点"确认执行" → 提示成功，卡片消失。
6. 左栏点该会话 → 中栏看到完整对话流。

> 若本机后端联调环境未完全就绪，记录为"留子计划④ docker-compose 一键起后统一验证"。前端组件单测（6 个）+ 后端接口测试（59 个）已保证各单元正确。

- [ ] **Step 3: 全量回归确认**

```
cd cs-agent && .venv\Scripts\python.exe -m pytest tests -q -m "not integration"   # 59 passed
cd web && npm run test                                                              # 6 passed
```

- [ ] **Step 4: README 截图位（可选）**

如联调成功，截图客户端对话 + 工作台确认两张图，留作 README/演示用（放 `docs/images/`）。

---

## 完成标准（子计划③）

- [ ] cs-agent 补：CORS + `GET /conversations` + `GET /conversations/{id}/messages`，测试通过（59 passed）。
- [ ] 前端两个核心页：客户聊天端（SSE 流式 + 引用展示）、坐席工作台（会话列表 + 对话流 + 待确认卡片 + 确认/驳回）。
- [ ] 坐席登录（JWT）+ 路由守卫。
- [ ] 前端组件单测 6 个通过（Vitest）。
- [ ] 能在浏览器演示"人在环路"完整剧情（联调或留④）。

> 下一步：子计划②b-2（转人工摘要 + 情绪 + 看板聚合）补全后端深度；子计划④（评测 + docker-compose 一键起）做最终集成与交付。看板前端页等②b-2 后端完成后补。
