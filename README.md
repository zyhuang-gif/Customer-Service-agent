# Customer-Service-agent

智能售后客服 Agent 工作台。目标不是做一个只会聊天的机器人，而是做一个能查询业务系统、调用工具、遇到高风险动作自动暂停并交给坐席确认的售后处理系统。

当前 `master` 已完成两个后端服务、Agent 后端深度能力，以及 Vue 前端（客户聊天端 + 坐席工作台），`docker-compose up` 可一键起全栈。

## 架构

```mermaid
flowchart LR
  customer["客户浏览器 /chat"]
  agent["坐席工作台 /agent-desk"]
  dashboard["运营看板 /dashboard"]

  subgraph web["web: Vue3 + Element Plus"]
    customer
    agent
    dashboard
  end

  subgraph cs["cs-agent: FastAPI + LangGraph"]
    chat["/chat SSE"]
    auth["/auth/login"]
    confirm["/pending-actions"]
    summary["/dashboard/summary"]
    graph["LangGraph agent loop"]
    risk["risk gate: high-risk interrupt"]
    retrieval["retrieval: Chroma + DashScope rerank"]
    audit["audit + conversations + messages"]
  end

  subgraph biz["business-system: FastAPI"]
    orders["orders / logistics / customers"]
    tickets["tickets"]
    refunds["refunds"]
    coupons["coupons"]
  end

  subgraph pg["Postgres cs database"]
    agent_schema["agent data: conversations, messages, pending_actions, audit_logs, checkpoints"]
    biz_schema["biz data: orders, logistics, customers, tickets, refunds, coupons"]
  end

  chroma["chroma_data volume"]
  dashscope["DashScope chat / embedding / rerank"]

  customer -->|"HTTP + SSE"| chat
  agent -->|"Bearer token"| auth
  agent -->|"list / approve / reject"| confirm
  dashboard -->|"Bearer token"| summary

  chat --> graph
  graph --> retrieval
  graph --> risk
  risk -->|"pending high-risk action"| confirm
  confirm -->|"approved only"| refunds
  graph -->|"HTTP tools only"| orders
  graph --> tickets
  graph --> coupons
  summary --> audit

  retrieval --> chroma
  retrieval --> dashscope
  graph --> dashscope

  audit --> agent_schema
  confirm --> agent_schema
  graph --> agent_schema
  orders --> biz_schema
  tickets --> biz_schema
  refunds --> biz_schema
  coupons --> biz_schema
```

可单独查看的 Mermaid 源文件：`docs/images/customer-service-agent-architecture.mmd`。

## 服务

| 路径 | 端口 | 说明 |
| --- | --- | --- |
| `business-system/` | `8100` | 订单、物流、退款、工单、客户、优惠券等业务后台 API |
| `cs-agent/` | `8000` | Agent 对话、SSE、人在环路确认、审计、情绪/看板聚合 |
| `eval/` | - | 评测用例与轻量运行脚本 |

## 已有能力

- 独立业务系统：Agent 只能通过 HTTP 工具调用业务后台，不直读业务表。
- 只读工具：客户、订单、物流、退款、历史工单、知识库检索。
- 写工具分级：低风险工单可自动执行，高风险退款、改地址、发券进入人工确认。
- 人在环路：高风险动作写入 `pending_actions`，坐席确认或驳回后恢复执行。
- 审计留痕：工具调用、高风险动作、转人工、知识缺口都会写入审计日志。
- 后端深度：情绪识别、转人工摘要、知识缺口统计、最小看板 API。

## 本地运行

### 方式一：docker-compose 后端一键起

先复制环境变量样例，并把真实 DashScope key 写入 `cs-agent/.env`：

```powershell
Copy-Item business-system\.env.example business-system\.env
Copy-Item cs-agent\.env.example cs-agent\.env
```

启动 Postgres、业务系统和 Agent：

```powershell
docker compose up --build
```

服务启动后：

- `business-system`: http://localhost:8100/health/live
- `cs-agent`: http://localhost:8000/health/live
- 坐席账号：`agent / agent123`，管理员账号：`admin / admin123`

### 方式二：本地 Python

```powershell
cd business-system
.venv\Scripts\python.exe -m app.seed
.venv\Scripts\uvicorn.exe app.main:app --port 8100
```

```powershell
cd cs-agent
.venv\Scripts\python.exe -m app.seed_agent
.venv\Scripts\uvicorn.exe app.main:app --port 8000
```

## 常用 API

### 登录

```powershell
curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d "{\"username\":\"agent\",\"password\":\"agent123\"}"
```

### 客户对话 SSE

```powershell
curl -N -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  -d "{\"customer_ref\":\"13800000001\",\"message\":\"订单 20260531002 物流停了，我要退款 499 元\"}"
```

### 待确认动作

```powershell
curl http://localhost:8000/pending-actions `
  -H "Authorization: Bearer <token>"
```

### 看板汇总

```powershell
curl http://localhost:8000/dashboard/summary `
  -H "Authorization: Bearer <token>"
```

## 测试

```powershell
cd business-system
.venv\Scripts\python.exe -m pytest tests -q
```

```powershell
cd cs-agent
.venv\Scripts\python.exe -m pytest tests -q -m "not integration"
```

## 评测

`eval/cases.json` 放售后剧情用例，`eval/run_eval.py` 会调用 `/chat` 并检查 SSE 事件类型。

```powershell
python eval\run_eval.py --base-url http://localhost:8000
```

这个脚本是轻量冒烟评测，适合验证真实服务链路是否还能跑通；更细的答案质量评分可以在此基础上扩展。

## 前端（web）

Vite + Vue3 + Element Plus，两个核心页面：

- **客户聊天端** `/chat`：SSE 流式对话，AI 回复带知识库引用出处。
- **坐席工作台** `/agent-desk`（需登录，演示账号 `agent/agent123`）：三栏布局——会话列表 / 对话流 / 待确认动作卡片，坐席可对高风险动作（退款、改地址、发券）确认或驳回。

本地开发：`cd web && npm install && npm run dev`（5173）；组件单测 `npm run test`。
容器部署：已纳入 `docker-compose.yml`（web 服务映射 `5173:80`）。

> 端到端联调验证（真实 Postgres + qwen3-max 跑通人在环路）见 `docs/verification/2026-06-02-e2e-human-in-the-loop.md`。

## 当前交付缺口

- 完整 API 文档仍待补齐。
- 演示截图可按最终演示环境补充。
- 评测脚本已扩展剧情用例与指标报告，尚未加入 LLM judge 或人工标注分。
