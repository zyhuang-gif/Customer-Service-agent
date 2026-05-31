# 智能售后客服 Agent 工作台 —— 第一版设计文档

> 日期：2026-05-31
> 状态：设计已确认，待进入实现计划（writing-plans）
> 场景：电商售后

---

## 0. 背景与定位

做一个**能解决问题的客服 Agent**，而不是"会聊天的客服机器人"。核心区别在于：Agent 能识别问题 → 查询业务系统 → 给出方案 → 必要时执行操作 → 无法处理时转人工 → 自动总结留痕。

### 项目目标（约束）

这是一个**作品集**项目，但必须"有认可度、不能是 demo"。翻译成可执行标准：

1. **真实的系统边界**：Agent / 业务系统 各自独立、靠 HTTP API 通信，而非写死 if-else。
2. **人在环路的安全设计**：高风险操作必须人工确认，且有审计日志。
3. **可量化的效果**：有评测集 + 指标，而非截图几段对话。
4. **工程完整度**：测试、README、架构图、一键起步。

这四条做到即脱离"demo"。

### 已确认的关键决策

| 决策点 | 选择 |
|---|---|
| 场景 | 电商售后 |
| 服务关系 | 独立新服务，**不与现有 RAG 服务共用代码** |
| 知识检索 | 新服务**内置"右尺寸高质量检索"**（embedding + 混合检索 + rerank + 引用），不复刻企业级多租户基础设施 |
| Agent 框架 | **LangGraph**（状态机式编排，原生 human-in-the-loop） |
| LLM 提供方 | **兼容多家可配置**（OpenAI 兼容协议，切 Qwen/OpenAI/Claude 只改配置） |
| 前端 | **最小但完整的双端 UI**（客户聊天端 + 人工客服工作台） |
| 前端技术栈 | **Vue3 + Element Plus** |
| 登录/角色 | **轻量登录 + 角色**（客户 / 坐席 / 管理员） |
| 存储/部署 | **Postgres + docker-compose 一键起** |
| 服务拆分 | **方案 C：两层清晰边界**（业务系统服务 + 客服 Agent 服务 + 前端）；方案 B（完全微服务）作为后续优化方向 |
| 第一版增强功能 | 审计日志 + 最小数据看板 + 情绪识别 |
| 暂不做 | 客服质检、完整账号体系、跨会话记忆 |

---

## 1. 总体架构与服务拆分

```
┌─────────────────────────────────────────────────────────────┐
│  前端 (Vue3 + Element Plus)                                    │
│  ├─ 客户聊天端     /chat        (客户视角)                      │
│  └─ 人工客服工作台  /agent-desk  (坐席视角)                     │
│  └─ 数据看板        /dashboard                                 │
└───────────────┬─────────────────────────────────────────────┘
                │ HTTP / SSE
                ▼
┌──────────────────────────────┐
│  客服 Agent 服务 (FastAPI)     │
│  + LangGraph 编排              │
│  ├─ 会话/消息管理              │
│  ├─ 内置检索 (右尺寸 RAG)      │
│  ├─ LangGraph Agent 主循环     │
│  ├─ 工具层 (tools)            │──HTTP──┐
│  ├─ 人在环路状态机             │        │
│  ├─ 审计日志                   │        ▼
│  └─ 看板指标聚合              │   ┌──────────────────────────┐
└───────────┬──────────────────┘   │  业务系统服务 (FastAPI)     │
            │                       │  "被集成的业务后台"         │
            ▼                       │  ├─ 订单 API                │
   ┌─────────────────┐             │  ├─ 物流 API                │
   │  向量库          │             │  ├─ 退款/支付 API           │
   │ (Chroma 本地嵌入)│             │  ├─ 工单 API (读写)         │
   └─────────────────┘             │  └─ 客户/CRM API            │
            │                       └───────────┬──────────────┘
            ▼                                   ▼
        售后政策/FAQ 语料                   ┌─────────────┐
                                            │  Postgres    │
                                            │ agent / biz  │
                                            │ 两 schema    │
                                            └─────────────┘
```

### 三个可部署单元 + 一个数据库

| 单元 | 技术 | 职责 | 关键边界 |
|---|---|---|---|
| `business-system` | FastAPI + Postgres | 订单/物流/退款/工单/CRM 的真实数据 + REST API。**对 Agent 一无所知**，就是个被调用的业务后台 | 纯 REST，无 LLM |
| `cs-agent` | FastAPI + LangGraph + Chroma | Agent 编排、内置检索、工具调用（HTTP 调 business-system）、会话、审计、看板聚合、轻量登录 | 工具层是唯一外部出口 |
| `web` | Vue3 + Element Plus | 客户聊天端 + 坐席工作台 + 看板 | 只调 cs-agent |

### 仓库结构（monorepo，单 git 仓库）

```
Customer-Service-agent/
├─ business-system/      # FastAPI 业务后台
├─ cs-agent/             # FastAPI + LangGraph 客服 Agent
│  └─ knowledge/         # 售后政策/FAQ 语料（启动灌入 Chroma）
├─ web/                  # Vue3 + Element Plus 前端
├─ eval/                 # 评测集与评测脚本
├─ docker-compose.yml    # 一键起全部 + Postgres
├─ docs/                 # 架构图、API 文档、设计文档
└─ README.md
```

### 设计要点

- **business-system 完全不认识 Agent**——"真集成"的关键，它能单独 curl 演示。
- **cs-agent 的工具层是访问外部的唯一出口**——所有对业务系统的调用经过 tools，便于审计与错误处理统一。
- **两个后端服务各用独立 Postgres schema**（`agent` / `biz`），物理同库逻辑隔离；cs-agent 不直接读 `biz` 表，只走 HTTP，双重保证边界。
- monorepo 单仓库，一次 clone 即可跑；后续若按方案 B 拆微服务，子目录可平滑独立。

---

## 2. 数据模型

### `biz` schema（业务系统服务）

| 表 | 关键字段 | 说明 |
|---|---|---|
| `customers` | id, name, phone, member_level（普通/银/金/钻）, register_date | CRM；会员等级用于"高价值客户"判断 |
| `orders` | id, customer_id, status（待付款/待发货/已发货/已签收/已取消）, items(jsonb), amount, created_at, shipped_at | 订单主数据 |
| `logistics` | id, order_id, carrier, tracking_no, status（揽收/运输中/派送中/已签收/异常）, last_update, eta, traces(jsonb) | 物流；`last_update` 判断"停滞 N 天" |
| `refunds` | id, order_id, status（无/处理中/已到账/失败）, amount, channel, reason, applied_at, completed_at | 退款/支付 |
| `tickets` | id, customer_id, order_id, category（物流/退款/售后/投诉/咨询）, priority（低/中/高/紧急）, status, assignee, summary, history(jsonb), created_at, updated_at | 工单；读写都有 |

> "高风险客户（近 7 天投诉 3 次）"由 `tickets where category='投诉'` 按时间聚合得出，不另建表。

### `agent` schema（客服 Agent 服务）

| 表 | 关键字段 | 说明 |
|---|---|---|
| `users` | id, username, password_hash, role（agent/admin）, display_name | 轻量登录的坐席账号 |
| `conversations` | id, customer_ref（手机号/会话标识）, channel, **status**, assigned_agent_id, summary, created_at, closed_at | `status` 即人在环路状态机（见第 4 节） |
| `messages` | id, conversation_id, role（customer/ai/agent/system）, content, meta(jsonb：工具步骤、引用、情绪), created_at | 一条条对话消息，**实时落库** |
| `pending_actions` | id, conversation_id, tool_name, params(jsonb), status（pending/approved/rejected/executed/failed）, proposed_by, reviewed_by, reviewed_at, result(jsonb) | 高风险动作待确认队列，人在环路核心载体 |
| `audit_logs` | id, conversation_id, actor（ai/坐席id）, action_type（tool_call/high_risk/handoff/login）, tool_name, params(jsonb), result(jsonb), risk_level, status, created_at | 所有工具调用与高风险动作留痕 |

### 其他存储

- **知识语料**不进 Postgres：文档放 `cs-agent/knowledge/`，启动时切块灌入 **Chroma**；引用出处（文档标题 + 版本 + 片段）存 chunk 的 metadata，回答时带出。
- **LangGraph 运行时状态（checkpoint）**：持久化在 Postgres（LangGraph checkpointer 自有表），用于高风险动作 interrupt 后恢复图执行，与业务用的 `messages` 区分开。
- **看板指标**由 `conversations / pending_actions / audit_logs / tickets` 实时聚合查询得到，不另建指标表。

### 对话历史的持久化语义

- 消息**实时落库**到 `messages`，不是会话结束才存。
- 会话结束时额外做：① 生成摘要写入 `conversations.summary`；② 状态置 `resolved/closed/needs_followup`，记 `closed_at`；③ 触发评测/看板聚合（读已存好的 messages）。
- **消息永久保留**，关闭会话只改状态，不删 messages。
- checkpoint 在会话彻底关闭后可清理，不影响历史查看。
- 第一版**不做跨会话记忆**。

---

## 3. 工具清单

### A. 只读查询工具 —— 自动执行

| 工具 | 入参 | 映射业务 API | 用途 |
|---|---|---|---|
| `search_knowledge` | query | （内置检索，不出网） | 售后政策/FAQ 检索，返回片段 + 出处 |
| `get_customer` | phone 或 customer_id | `GET /customers` | 识别客户、会员等级 |
| `get_order` | order_id 或 customer_id | `GET /orders` | 订单状态、金额、时间 |
| `get_logistics` | order_id | `GET /logistics` | 物流轨迹、是否停滞 |
| `get_refund_status` | order_id | `GET /refunds` | 退款进度 |
| `list_customer_tickets` | customer_id | `GET /tickets?customer_id=` | 历史工单/投诉，用于风险判断 |

### B. 低风险写操作 —— 自动执行（留审计）

| 工具 | 入参 | 映射业务 API | 说明 |
|---|---|---|---|
| `create_ticket` | category, order_id, summary, priority | `POST /tickets` | 建工单/物流催办，不涉及钱，可自动 |
| `update_ticket` | ticket_id, note, status | `PATCH /tickets/{id}` | 加备注/流转状态 |

### C. 高风险写操作 —— 必须人工确认后执行

| 工具 | 入参 | 映射业务 API | 为什么高风险 |
|---|---|---|---|
| `apply_refund` | order_id, amount, reason | `POST /refunds` | 涉及钱 |
| `change_address` | order_id, new_address | `PATCH /orders/{id}/address` | 改履约信息 |
| `issue_coupon` | customer_id, value, reason | `POST /coupons` | 发钱等价物 |

> C 类工具被 Agent 调用时**不立即执行**——写一条 `pending_actions(status=pending)`，对话进入"待确认"状态，由坐席在工作台确认/驳回后才真正打业务 API。

### D. 控制类工具

| 工具 | 入参 | 行为 |
|---|---|---|
| `transfer_to_human` | reason, draft_summary | 触发转人工：生成结构化摘要、对话转 `human_handling`、工作台亮出待接管 |

### 说明

- **情绪识别**不做成工具，而是 Agent 每轮回复时的分析步骤（节点），结果写 `messages.meta`，工作台 Copilot 渲染"情绪 + 风险提示"。
- **`summarize_conversation`** 不是独立工具，而是转人工/关闭会话时自动跑的节点。
- 工具**风险级别配置驱动**（一张 `TOOL_RISK` 映射表），调档位只改配置不动逻辑。

---

## 4. 人在环路状态机与 LangGraph 流程

### 会话状态机（`conversations.status`）

```
                  ┌──────────────┐
   客户发起 ─────▶│  ai_handling  │ AI 处理中
                  └──────┬───────┘
        ┌────────────────┼────────────────────┐
        │ 调用高风险工具    │ 触发转人工           │ 判定已解决
        ▼                │                     ▼
┌──────────────────┐     │              ┌─────────────┐
│awaiting_         │     │              │  resolved    │
│confirmation      │     │              └──────┬──────┘
│(待坐席确认动作)    │     │                     │ 客户无新问题
└───┬─────────┬────┘     │                     ▼
    │驳回      │确认执行    │              ┌─────────────┐
    │          ▼          ▼              │   closed     │
    │   (打业务API)  ┌──────────────┐      └─────────────┘
    └────────▶ 回到 │ human_handling│            ▲
       ai_handling  │ (人工处理中)   │            │
                    └──────┬───────┘            │
                           │ 坐席处理完           │
                           ├────────────────────┘
                           ▼
                    ┌──────────────┐
                    │needs_followup │ 需回访
                    └──────────────┘
```

### LangGraph 节点流程（cs-agent 内部）

```
START
  │
  ▼
[analyze]  意图识别 + 情绪/风险分析（结果写 messages.meta）
  │
  ▼
[agent]  LLM 决策：要不要调工具？调哪个？  ◀──────────┐
  │                                                  │
  ├─ 无工具，直接回复 ─────────────▶ [respond] ──▶ [resolve_check]
  │                                                  │
  ├─ 只读/低风险工具 ─▶ [tool_exec] 执行 ─────────────┘ (loop)
  │
  ├─ 高风险工具 ─▶ [interrupt] ⏸  写 pending_action
  │                            status=awaiting_confirmation
  │                            ↑ 图在此挂起，等坐席信号
  │       ┌── approved ──▶ [tool_exec] 打业务API ──▶ 回 [agent]
  │       └── rejected ──▶ 把"被驳回"喂回 ──▶ [agent]
  │
  └─ transfer_to_human ─▶ [handoff] 生成摘要, status=human_handling, 停 AI
```

### 高风险动作的"暂停—确认—恢复"机制

用 **LangGraph 的 `interrupt` + checkpointer**（图状态持久化到 Postgres）：

1. Agent 调高风险工具 → 命中 `[interrupt]` 节点 → 写 `pending_actions(pending)`，图状态存盘，HTTP 流先返回"已提交人工确认"。
2. 工作台轮询/SSE 看到待确认动作，坐席点**确认**或**驳回**。
3. 坐席操作 → cs-agent 用保存的 checkpoint **恢复图**：确认则执行业务 API 并继续，驳回则把结果喂回让 Agent 换方案或转人工。
4. 全程写 `audit_logs`（proposed → approved/rejected → executed/failed）。

> 图状态持久化在 Postgres，**服务重启也能恢复**待确认会话。

### 转人工触发条件（命中任一）

AI 置信度低 · 客户连续 N 轮未解决 · 情绪激烈 · 涉及赔偿/投诉升级 · 客户明确要求 · 业务系统调用连续失败。

### 转人工摘要结构（自动生成）

```
客户问题：<一句话>
已查信息：订单/物流/退款的关键事实
已尝试动作：建了哪些工单、提了哪些待确认动作
客户情绪：<情绪 + 风险提示>
建议人工处理：<下一步建议>
```

---

## 5. 错误处理与可靠性

| 场景 | 处理策略 |
|---|---|
| 业务系统超时/5xx | 工具层一次重试 + 超时（如 3s）；仍失败返回**结构化错误**给 Agent，Agent **不得编造**，回复"暂时查不到，正在转人工"；连续失败触发 `transfer_to_human` |
| 业务系统 404（订单不存在） | 工具返回 not_found，Agent 如实告知，引导核对订单号 |
| 检索无命中 | `search_knowledge` 返回空 → Agent 明确"知识库暂未覆盖"，**记录为无答案问题**（供知识缺口分析），不胡编 |
| LLM 失败/超时 | 降级为固定话术 + 转人工，不让会话卡死 |
| 高风险动作执行失败 | `pending_actions.status=failed` + 审计留痕 + 工作台显式告警，**绝不静默** |
| 确认重复点击 | 写操作带**幂等键**（用 `pending_action.id` 作 idempotency-key），防重复退款/发券 |
| 入参非法 | 业务系统服务用 Pydantic 校验返回 400；Agent 侧工具参数也校验 |

> **安全红线**：高风险工具在任何分支下都不可能绕过 `pending_actions` 直接执行——以测试用例守住。

---

## 6. 测试与评测

### 测试

- **业务系统服务**：API 单测 + 种子数据脚本。
- **cs-agent 单测**：工具层（mock 业务 API）、风险分级映射、状态机转换、幂等。
- **集成测试**：完整剧情——①物流停滞→建催办工单（自动）；②退款→待确认→坐席确认→执行；③业务系统连续失败→转人工。
- **安全测试**：断言高风险动作无法自动执行（守红线）。

### 评测集（`eval/`，认可度的硬证据）

- 30~50 条对话用例，每条绑定一份"剧情数据"。
- 评测脚本跑出报告，指标：

| 指标 | 含义 |
|---|---|
| 意图识别正确率 | 分类对不对 |
| 工具调用正确率 | 该调的调了、参数对不对 |
| AI 独立解决率 | 不转人工直接解决的比例 |
| 转人工率 | 触发转人工的比例 |
| 知识命中率 | 问题被知识库覆盖的比例 |
| 高风险误执行数 | 必须为 0（安全红线） |

### 种子数据（有剧情）

正常已签收 · 物流停滞 3 天 · 退款 5 天未到账 · 近 7 天投诉 3 次的高风险客户——让演示和评测都有真实剧情。

---

## 7. 前端页面（Vue3 + Element Plus）

### ① 客户聊天端 `/chat`

输入会话标识/手机号进入 → 聊天气泡 + **SSE 流式回复** + **引用出处展示**（点开看政策原文片段）。极简，客户视角。

### ② 人工客服工作台 `/agent-desk`（登录后，核心界面）

三栏布局：

- **左**：会话列表，按状态筛选；`待接管`(human_handling) 和 `待确认`(awaiting_confirmation) 高亮置顶。
- **中**：对话消息流，可展开 **AI 的思考步骤 / 工具调用 / 引用**（来自 `messages.meta`）。
- **右 · Copilot 面板**：客户摘要、历史订单/工单、**情绪 + 风险提示**、推荐动作，以及**待确认动作卡片**（显示"AI 想给订单 X 退款 ¥Y，原因 Z" + 确认/驳回按钮）。坐席接管后可直接发消息。

### ③ 数据看板 `/dashboard`

核心指标卡 + 简单图表：AI 独立解决率、转人工率、工单量、知识命中率，外加**无答案问题列表**（知识缺口）。

### ④ 登录页

轻量登录，坐席/管理员两种角色。

---

## 8. 部署与交付

### docker-compose 一键起

`postgres` + `business-system` + `cs-agent` + `web` 四个容器。

- Chroma 用**本地持久化嵌入 cs-agent 进程**，省一个容器。
- 启动自动跑：建表 migration → 灌种子数据 → 切块灌知识库。
- `.env` 配 LLM（OpenAI 兼容 `base_url` + `key` + `model`），切 Qwen/OpenAI/Claude 只改配置。
- 命令：`docker compose up` → 浏览器打开演示。

### 交付物

```
README（架构图 + 一键起步骤 + 演示剧本）
docs/   架构图、两个服务的 API 文档、本设计文档
eval/   评测脚本 + 评测报告
种子数据脚本（有剧情）
（可选）演示录屏
```

---

## 9. 明确不做（YAGNI / 后续方向）

- 客服质检（自动评分 + 问题标签）——后续。
- 完整账号体系（注册/JWT/权限组）——第一版只轻量登录。
- 跨会话记忆——第一版不做。
- 完全微服务（方案 B：订单/物流/退款/工单各自独立服务）——作为后续优化方向。
- 多行业版本（SaaS/金融/政企）——先把电商售后做深。
