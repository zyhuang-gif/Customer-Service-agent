# cs-agent Backend Depth ②b-2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 ②b-1 留下的后端深度：情绪识别、转人工摘要、知识缺口统计、最小看板聚合 API。

**Architecture:** 不新增业务表，复用 `messages.meta` 写情绪，复用 `conversations.status/summary` 表示转人工，复用 `audit_logs` 记录 handoff 与 knowledge_gap，再由 dashboard service 实时聚合。`transfer_to_human` 作为控制类工具进入 tool schema，但真正状态变更统一在 `ConversationService` 中落库，避免 graph 节点直接碰 DB。

**Tech Stack:** FastAPI、SQLAlchemy、LangGraph、pytest。

---

## Task 1: 情绪与摘要纯函数

**Files:**
- Create: `cs-agent/app/insights.py`
- Create: `cs-agent/tests/test_insights.py`

- [ ] Write failing tests for sentiment and handoff summary.
- [ ] Implement keyword-based sentiment analysis and deterministic summary formatting.
- [ ] Run `pytest tests/test_insights.py -q`.

## Task 2: 对话服务落情绪、转人工、知识缺口

**Files:**
- Modify: `cs-agent/app/agent/tools_bind.py`
- Modify: `cs-agent/app/tools/risk.py`
- Modify: `cs-agent/app/tools/registry.py`
- Modify: `cs-agent/app/agent/service.py`
- Create: `cs-agent/tests/test_backend_depth_service.py`

- [ ] Write failing service tests for customer message sentiment meta, explicit handoff, transfer tool handoff, and empty knowledge retrieval audit.
- [ ] Add `transfer_to_human` tool schema and registry handler.
- [ ] Update `ConversationService.start_turn()` to persist sentiment meta, set `human_handling` with summary when handoff is requested, and audit `knowledge_gap` when `search_knowledge` returns uncovered.
- [ ] Run `pytest tests/test_backend_depth_service.py -q`.

## Task 3: 看板聚合与 API

**Files:**
- Create: `cs-agent/app/dashboard.py`
- Create: `cs-agent/app/routers/dashboard_router.py`
- Modify: `cs-agent/app/routers/__init__.py`
- Modify: `cs-agent/app/main.py`
- Modify: `cs-agent/app/schemas_api.py`
- Create: `cs-agent/tests/test_dashboard_api.py`

- [ ] Write failing tests for dashboard metric aggregation and auth-protected API.
- [ ] Implement dashboard aggregation from `conversations`, `pending_actions`, and `audit_logs`.
- [ ] Add `GET /dashboard/summary` protected by `current_user`.
- [ ] Run `pytest tests/test_dashboard_api.py -q`.

## Task 4: Regression

**Files:**
- All touched files.

- [ ] Run focused backend depth tests.
- [ ] Run full cs-agent non-integration tests.
- [ ] Commit with message `feat: cs-agent 补齐②b-2后端深度能力`.
