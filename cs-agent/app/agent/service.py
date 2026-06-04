"""对话服务层：串起 LangGraph 图、agent schema 业务表、业务系统执行。"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.audit import audit
from app.agent.routing import route_customer_message
from app.conversation_activity import add_message
from app.insights import analyze_sentiment, build_handoff_summary
from app.models import Conversation, Message, PendingAction

_EXECUTORS = {
    "apply_refund": lambda biz, p: biz.apply_refund(order_id=p["order_id"], amount=p["amount"], reason=p.get("reason", "")),
    "change_address": lambda biz, p: biz.change_address(order_id=p["order_id"], new_address=p["new_address"]),
    "issue_coupon": lambda biz, p: biz.issue_coupon(customer_id=p["customer_id"], value=p["value"], reason=p.get("reason", "")),
}


class ConversationService:
    def __init__(self, db: Session, graph, business, registry=None):
        self.db = db
        self.graph = graph
        self.business = business
        self.registry = registry

    def _config(self, conversation_id: str) -> dict:
        return {"configurable": {"thread_id": conversation_id}}

    def _recent_messages(self, conversation_id: str) -> list[Message]:
        return (
            self.db.query(Message)
            .filter_by(conversation_id=conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )

    def _approved_message(self, pa: PendingAction, status: str) -> str:
        if status == "failed":
            return f"坐席已确认执行{pa.tool_name}，但业务系统执行失败，请稍后由人工继续处理。"

        if pa.tool_name == "apply_refund":
            refund_id = (pa.result or {}).get("id") or (pa.result or {}).get("refund_id") or ""
            refund_status = (pa.result or {}).get("status") or "已提交"
            suffix = f"业务系统已创建退款单 {refund_id}，当前状态：{refund_status}。" if refund_id else f"退款申请已提交，当前状态：{refund_status}。"
            return f"坐席已确认执行退款申请，{suffix}"
        if pa.tool_name == "change_address":
            return "坐席已确认执行改地址申请，业务系统已更新收货地址。"
        if pa.tool_name == "issue_coupon":
            coupon_id = (pa.result or {}).get("id") or (pa.result or {}).get("coupon_id") or ""
            suffix = f"业务系统已发放优惠券 {coupon_id}。" if coupon_id else "业务系统已发放优惠券。"
            return f"坐席已确认执行发券申请，{suffix}"
        return "坐席已确认执行该操作，业务系统已处理完成。"

    def _pending_high_risk(
        self,
        conversation_id: str,
        tool_name: str,
        params: dict[str, Any],
        customer_ref: str | None = None,
    ) -> dict[str, Any]:
        pa = PendingAction(
            conversation_id=conversation_id, tool_name=tool_name,
            params=params, status="pending", proposed_by="ai", customer_ref=customer_ref,
        )
        self.db.add(pa)
        conv = self.db.get(Conversation, conversation_id)
        conv.status = "awaiting_confirmation"
        self.db.commit()
        audit(self.db, actor="ai", action_type="high_risk", conversation_id=conversation_id,
              tool_name=tool_name, params=params, risk_level="high_write", status="pending")
        return {"status": "awaiting_confirmation", "pending_action_id": pa.id,
                "message": "该操作涉及资金/履约，已提交人工确认。"}

    def _explicit_high_risk_request(self, user_text: str) -> tuple[str, dict[str, Any]] | None:
        order_match = re.search(r"(?:订单号?|订单编号)?\s*([A-Z0-9]{6,})", user_text, re.IGNORECASE)
        amount_match = re.search(r"(?:退款金额|金额|退款)?\s*([0-9]+(?:\.[0-9]+)?)\s*元", user_text)

        if any(word in user_text for word in ("申请退款", "我要退款", "要求退款", "提交退款", "退钱")):
            if any(word in user_text for word in ("退款进度", "退款状态", "查询退款")):
                return None
            if order_match and amount_match:
                return "apply_refund", {
                    "order_id": order_match.group(1),
                    "amount": float(amount_match.group(1)),
                    "reason": "用户明确申请退款",
                }

        if any(word in user_text for word in ("改地址", "修改地址", "更换地址")):
            if order_match:
                address_match = re.search(r"(?:改到|改成|修改为|新地址[:：]?)\s*(.+)$", user_text)
                if address_match:
                    return "change_address", {
                        "order_id": order_match.group(1),
                        "new_address": address_match.group(1).strip(" 。"),
                    }

        if any(word in user_text for word in ("发券", "补偿券", "优惠券")):
            customer_match = re.search(r"(?:客户|用户|会员)\s*([A-Z0-9]{3,})", user_text, re.IGNORECASE)
            value_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*元", user_text)
            if customer_match and value_match:
                return "issue_coupon", {
                    "customer_id": customer_match.group(1),
                    "value": float(value_match.group(1)),
                    "reason": "用户明确要求发券",
                }

        return None

    def _handoff(self, conversation_id: str, summary: str, reason: str, actor: str = "ai") -> dict[str, Any]:
        conv = self.db.get(Conversation, conversation_id)
        conv.status = "human_handling"
        conv.summary = summary
        self.db.commit()
        audit(
            self.db,
            actor=actor,
            action_type="handoff",
            conversation_id=conversation_id,
            params={"reason": reason},
            result={"summary": summary},
            status="human_handling",
        )
        return {"status": "human_handling", "message": "已为您转接人工客服。", "summary": summary}

    def _decode_tool_payload(self, message) -> dict[str, Any] | None:
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            return None
        try:
            payload = ast.literal_eval(content)
        except (ValueError, SyntaxError):
            return None
        return payload if isinstance(payload, dict) else None

    def _coordinator_trace(self, decision: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent": "CoordinatorAgent",
            "action": "route",
            "summary": decision["reason"],
            "input": {"task_type": decision["task_type"]},
            "output": decision,
            "status": "success",
        }

    def _final_trace(self) -> dict[str, Any]:
        return {
            "agent": "CoordinatorAgent",
            "action": "respond",
            "summary": "汇总知识检索和业务工具结果，生成最终客服回复。",
            "input": {},
            "output": {},
            "status": "success",
        }

    def _tool_trace(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "search_knowledge":
            return {
                "agent": "KnowledgeAgent",
                "action": tool_name,
                "summary": "检索客服知识库，返回政策依据和引用来源。" if payload.get("covered") else "检索客服知识库，未找到明确依据。",
                "input": {"query": payload.get("query", "")},
                "output": {"covered": bool(payload.get("covered")), "hits": len(payload.get("hits") or [])},
                "status": "success" if payload.get("covered") else "miss",
            }
        return {
            "agent": "ActionAgent",
            "action": tool_name,
            "summary": f"调用业务工具 {tool_name} 获取或处理业务数据。",
            "input": {},
            "output": payload,
            "status": "success" if not payload.get("error") else "failed",
        }

    def _collect_tool_metadata(self, conversation_id: str, messages: list) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
        citations: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        handoff: dict[str, Any] | None = None
        for msg in messages:
            tool_name = getattr(msg, "name", None)
            payload = self._decode_tool_payload(msg)
            if not tool_name or not payload:
                continue
            trace.append(self._tool_trace(tool_name, payload))
            if tool_name == "search_knowledge":
                citations.extend([
                    {
                        "title": hit.get("title", ""),
                        "source": hit.get("source", ""),
                        "text": hit.get("text", ""),
                        "score": hit.get("score"),
                    }
                    for hit in payload.get("hits", [])
                ])
            if tool_name == "transfer_to_human" and payload.get("handoff") is True:
                summary = payload.get("draft_summary") or build_handoff_summary(
                    self._recent_messages(conversation_id), {}
                )
                handoff = self._handoff(
                    conversation_id,
                    summary=summary,
                    reason=payload.get("reason", "transfer_to_human"),
                )
        return citations, trace, handoff

    def _record_tool_insights(self, conversation_id: str, messages: list) -> dict[str, Any] | None:
        for msg in messages:
            tool_name = getattr(msg, "name", None)
            payload = self._decode_tool_payload(msg)
            if not payload:
                continue
            if tool_name == "search_knowledge":
                query = payload.get("query") or payload.get("request") or ""
                covered = bool(payload.get("covered"))
                audit(
                    self.db,
                    actor="ai",
                    action_type="tool_call",
                    conversation_id=conversation_id,
                    tool_name="search_knowledge",
                    params={"query": query},
                    result=payload,
                    status="hit" if covered else "miss",
                )
                if not covered:
                    audit(
                        self.db,
                        actor="ai",
                        action_type="knowledge_gap",
                        conversation_id=conversation_id,
                        tool_name="search_knowledge",
                        params={"query": query},
                        result=payload,
                        status="uncovered",
                    )
            if tool_name == "transfer_to_human" and payload.get("handoff") is True:
                summary = payload.get("draft_summary") or build_handoff_summary(
                    self._recent_messages(conversation_id), {}
                )
                return self._handoff(
                    conversation_id,
                    summary=summary,
                    reason=payload.get("reason", "transfer_to_human"),
                )
        return None

    def start_turn(
        self,
        conversation_id: str,
        user_text: str,
        *,
        verified_customer_id: str | None = None,
    ) -> dict[str, Any]:
        sentiment_meta = analyze_sentiment(user_text)
        decision = route_customer_message(user_text)
        add_message(
            self.db,
            conversation_id,
            "customer",
            user_text,
            {**sentiment_meta, "coordinator_decision": decision},
        )
        self.db.commit()

        if sentiment_meta["handoff_requested"]:
            summary = build_handoff_summary(self._recent_messages(conversation_id), sentiment_meta)
            out = self._handoff(conversation_id, summary=summary, reason="customer_requested_handoff")
            out["agent_trace"] = [self._coordinator_trace(decision)]
            out["citations"] = []
            return out

        high_risk_request = self._explicit_high_risk_request(user_text)
        if high_risk_request:
            tool_name, params = high_risk_request
            if self.registry:
                denied = self.registry.authorize_customer_call(
                    tool_name,
                    params,
                    customer_ref=verified_customer_id,
                )
                if denied:
                    return {
                        "status": "access_denied",
                        "message": denied["message"],
                        "agent_trace": [self._coordinator_trace(decision)],
                        "citations": [],
                    }
            out = self._pending_high_risk(
                conversation_id, tool_name, params, customer_ref=verified_customer_id
            )
            out["agent_trace"] = [
                self._coordinator_trace(decision),
                {
                    "agent": "ActionAgent",
                    "action": tool_name,
                    "summary": f"识别到高风险业务动作 {tool_name}，已提交人工确认。",
                    "input": params,
                    "output": {"pending_action_id": out["pending_action_id"]},
                    "status": "pending",
                },
            ]
            out["citations"] = []
            return out

        state = {"messages": [{"role": "user", "content": user_text}],
                 "conversation_id": conversation_id, "customer_ref": verified_customer_id,
                 "intent": decision["task_type"],
                 "coordinator_decision": decision}
        result = self.graph.invoke(state, config=self._config(conversation_id))

        if "__interrupt__" in result:
            intr = result["__interrupt__"][0].value
            out = self._pending_high_risk(
                conversation_id,
                intr["tool_name"],
                intr["params"],
                customer_ref=verified_customer_id,
            )
            out["agent_trace"] = [self._coordinator_trace(decision)]
            out["citations"] = []
            return out

        tool_outcome = self._record_tool_insights(conversation_id, result["messages"])
        if tool_outcome:
            tool_outcome.setdefault("agent_trace", [self._coordinator_trace(decision)])
            tool_outcome.setdefault("citations", [])
            return tool_outcome
        citations, tool_trace, handoff = self._collect_tool_metadata(conversation_id, result["messages"])
        if handoff:
            handoff["agent_trace"] = [self._coordinator_trace(decision), *tool_trace]
            handoff["citations"] = citations
            return handoff

        last = result["messages"][-1]
        ai_text = getattr(last, "content", "")
        agent_trace = [self._coordinator_trace(decision), *tool_trace, self._final_trace()]
        meta = {
            "coordinator_decision": decision,
            "citations": citations,
            "agent_trace": agent_trace,
        }
        add_message(self.db, conversation_id, "ai", ai_text, meta)
        self.db.commit()
        return {
            "status": "ai_handling",
            "message": ai_text,
            "citations": citations,
            "agent_trace": agent_trace,
            "coordinator_decision": decision,
        }

    def resume_action(self, pending_action_id: int, approved: bool, reviewer_id: int) -> dict[str, Any]:
        pa = self.db.get(PendingAction, pending_action_id)
        if pa is None:
            return {"status": "not_found", "message": "待确认动作不存在"}
        # 幂等守护：非 pending 状态直接返回，防止重复退款/发券
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
            ai_text = "坐席已驳回该操作申请，未执行退款、改地址或发券。建议先为您转人工继续处理，或改为创建普通工单跟进。"
            add_message(self.db, pa.conversation_id, "ai", ai_text)
            conv.status = "ai_handling"
            self.db.commit()
            return {"status": conv.status, "pending_status": pa.status, "message": ai_text}
        else:
            denied = (
                self.registry.authorize_customer_call(
                    pa.tool_name,
                    pa.params,
                    customer_ref=pa.customer_ref,
                )
                if self.registry
                else None
            )
            if denied:
                pa.status = "failed"
                pa.result = denied
                status = "failed"
            else:
                executor = _EXECUTORS[pa.tool_name]
                try:
                    result = executor(self.business, pa.params)
                    pa.status = "executed"
                    pa.result = result or {}
                    status = "executed"
                except Exception as exc:  # noqa: BLE001
                    pa.status = "failed"
                    pa.result = {"error": str(exc)}
                    status = "failed"
            self.db.commit()
            audit(self.db, actor=str(reviewer_id), action_type="confirm", conversation_id=pa.conversation_id,
                  tool_name=pa.tool_name, params=pa.params, result=pa.result, risk_level="high_write", status=status)
            ai_text = self._approved_message(pa, status)
        add_message(self.db, pa.conversation_id, "ai", ai_text)
        conv.status = "ai_handling"
        self.db.commit()
        return {"status": conv.status, "pending_status": pa.status, "message": ai_text}
