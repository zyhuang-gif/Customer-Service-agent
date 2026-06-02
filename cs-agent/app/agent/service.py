"""对话服务层：串起 LangGraph 图、agent schema 业务表、业务系统执行。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command
from sqlalchemy.orm import Session

from app.audit import audit
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

    def start_turn(self, conversation_id: str, user_text: str) -> dict[str, Any]:
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
            resume_payload = {"approved": False}
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
