import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.agent.deps import build_service
from app.auth import decode_token
from app.customer_access import (
    CustomerAccessValidationError,
    classify_customer_request,
    customer_owns_orders,
)
from app.db import get_db
from app.errors import BusinessUnavailable
from app.models import Conversation
from app.schemas_api import ChatIn

router = APIRouter(tags=["chat"])
_bearer = HTTPBearer(auto_error=False)
_AUTH_ERROR = "客户登录已失效"


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def optional_customer(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str | None:
    if "authorization" not in request.headers:
        return None
    payload = decode_token(cred.credentials) if cred else None
    customer_ref = payload.get("customer_ref") if payload else None
    if not payload or payload.get("role") != "customer" or not customer_ref:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)
    return customer_ref


def _short_stream(event_type: str, content: str, conversation_id: str):
    def gen():
        yield _sse({"type": event_type, "content": content})
        yield _sse({"type": "done", "conversation_id": conversation_id})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/chat")
def chat(
    body: ChatIn,
    db: Session = Depends(get_db),
    customer_ref: str | None = Depends(optional_customer),
):
    conv_id = body.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    conversation = db.get(Conversation, conv_id)
    if body.conversation_id and (
        not customer_ref or not conversation or conversation.customer_ref != customer_ref
    ):
        raise HTTPException(status_code=404, detail="会话不存在")

    request_access = classify_customer_request(body.message)
    if request_access.is_personal and not customer_ref:
        return _short_stream(
            "identity_required",
            "为保护您的个人信息，请先登录后再查询。",
            conv_id,
        )
    if customer_ref and request_access.order_ids:
        try:
            owns_orders = customer_owns_orders(customer_ref, request_access.order_ids)
        except (BusinessUnavailable, CustomerAccessValidationError):
            return _short_stream(
                "service_unavailable",
                "查询服务暂时不可用，请稍后再试。",
                conv_id,
            )
        if not owns_orders:
            return _short_stream(
                "access_denied",
                "无法验证相关信息归属于当前账号。",
                conv_id,
            )

    effective_customer_ref = customer_ref or body.customer_ref
    if not conversation:
        db.add(
            Conversation(
                id=conv_id,
                customer_ref=effective_customer_ref,
                status="ai_handling",
            )
        )
        db.commit()

    def gen():
        yield _sse({"type": "start", "conversation_id": conv_id})
        svc = build_service(db)
        out = svc.start_turn(
            conv_id,
            body.message,
            verified_customer_id=customer_ref,
        )
        if out["status"] == "awaiting_confirmation":
            yield _sse({"type": "awaiting_confirmation", "pending_action_id": out["pending_action_id"],
                        "content": out["message"], "citations": out.get("citations", []),
                        "agent_trace": out.get("agent_trace", [])})
        else:
            yield _sse({"type": "response", "content": out["message"],
                        "citations": out.get("citations", []),
                        "agent_trace": out.get("agent_trace", [])})
        yield _sse({"type": "done", "conversation_id": conv_id})

    return StreamingResponse(gen(), media_type="text/event-stream")
