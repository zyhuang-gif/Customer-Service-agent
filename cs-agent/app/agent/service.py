"""对话服务层：串起 LangGraph 图、agent schema 业务表、业务系统执行。"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command
from sqlalchemy.orm import Session

from app.audit import audit
from app.insights import analyze_sentiment, build_handoff_summary
from app.models import Conversation, Message, PendingAction

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

    def _recent_messages(self, conversation_id: str) -> list[Message]:
        return (
            self.db.query(Message)
            .filter_by(conversation_id=conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .all()
        )

    def _pending_high_risk(self, conversation_id: str, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        pa = PendingAction(
            conversation_id=conversation_id, tool_name=tool_name,
            params=params, status="pending", proposed_by="ai",
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

    def start_turn(self, conversation_id: str, user_text: str) -> dict[str, Any]:
        sentiment_meta = analyze_sentiment(user_text)
        self.db.add(Message(conversation_id=conversation_id, role="customer", content=user_text, meta=sentiment_meta))
        self.db.commit()

        if sentiment_meta["handoff_requested"]:
            summary = build_handoff_summary(self._recent_messages(conversation_id), sentiment_meta)
            return self._handoff(conversation_id, summary=summary, reason="customer_requested_handoff")

        high_risk_request = self._explicit_high_risk_request(user_text)
        if high_risk_request:
            tool_name, params = high_risk_request
            return self._pending_high_risk(conversation_id, tool_name, params)

        state = {"messages": [{"role": "user", "content": user_text}],
                 "conversation_id": conversation_id, "customer_ref": "", "intent": ""}
        result = self.graph.invoke(state, config=self._config(conversation_id))

        if "__interrupt__" in result:
            intr = result["__interrupt__"][0].value
            return self._pending_high_risk(conversation_id, intr["tool_name"], intr["params"])

        tool_outcome = self._record_tool_insights(conversation_id, result["messages"])
        if tool_outcome:
            return tool_outcome

        last = result["messages"][-1]
        ai_text = getattr(last, "content", "")
        self.db.add(Message(conversation_id=conversation_id, role="ai", content=ai_text))
        self.db.commit()
        return {"status": "ai_handling", "message": ai_text}

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
            self.db.add(Message(conversation_id=pa.conversation_id, role="ai", content=ai_text))
            conv.status = "ai_handling"
            self.db.commit()
            return {"status": conv.status, "pending_status": pa.status, "message": ai_text}
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
            resume_payload = {"approved": True, "result": pa.result}

        final = self.graph.invoke(Command(resume=resume_payload), config=self._config(pa.conversation_id))
        last = final["messages"][-1]
        ai_text = getattr(last, "content", "")
        self.db.add(Message(conversation_id=pa.conversation_id, role="ai", content=ai_text))
        conv.status = "ai_handling"
        self.db.commit()
        return {"status": conv.status, "pending_status": pa.status, "message": ai_text}
