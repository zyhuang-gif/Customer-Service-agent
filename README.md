# Customer-Service-agent

智能售后客服 Agent 工作台。目标不是做一个只会聊天的机器人，而是做一个能查询业务系统、调用工具、遇到高风险动作自动暂停并交给坐席确认的售后处理系统。

当前 `master` 已完成两个后端服务与 Agent 后端深度能力；Vue 前端仍在独立工作线待合并。

## 架构

```text
customer / agent UI
        |
        | HTTP / SSE
        v
cs-agent (FastAPI + LangGraph + retrieval + audit)
        |
        | HTTP tools
        v
business-system (FastAPI business APIs)
        |
        v
Postgres
```

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

## 当前交付缺口

- Vue 前端在独立工作线，尚未合并到 `master`。
- `docker-compose.yml` 目前覆盖 Postgres + 两个后端；前端合并后再加入 web 服务。
- README 演示截图、架构图、完整 API 文档仍待补齐。
- 评测脚本是第一版链路评测，尚未加入 LLM judge 或人工标注分。
