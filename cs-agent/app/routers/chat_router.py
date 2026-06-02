import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.deps import build_service
from app.db import get_db
from app.models import Conversation
from app.schemas_api import ChatIn

router = APIRouter(tags=["chat"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db)):
    conv_id = body.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    if not db.get(Conversation, conv_id):
        db.add(Conversation(id=conv_id, customer_ref=body.customer_ref, status="ai_handling"))
        db.commit()

    def gen():
        yield _sse({"type": "start", "conversation_id": conv_id})
        svc = build_service(db)
        out = svc.start_turn(conv_id, body.message)
        if out["status"] == "awaiting_confirmation":
            yield _sse({"type": "awaiting_confirmation", "pending_action_id": out["pending_action_id"],
                        "content": out["message"]})
        else:
            yield _sse({"type": "response", "content": out["message"]})
        yield _sse({"type": "done", "conversation_id": conv_id})

    return StreamingResponse(gen(), media_type="text/event-stream")
