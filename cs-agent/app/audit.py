"""审计日志写入 helper。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, *, actor: str, action_type: str, conversation_id: str | None = None,
          tool_name: str | None = None, params: dict | None = None, result: dict | None = None,
          risk_level: str | None = None, status: str = "") -> None:
    db.add(AuditLog(
        actor=actor, action_type=action_type, conversation_id=conversation_id,
        tool_name=tool_name, params=params or {}, result=result or {},
        risk_level=risk_level, status=status,
    ))
    db.commit()
