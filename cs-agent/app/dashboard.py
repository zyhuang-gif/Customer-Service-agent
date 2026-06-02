"""Dashboard aggregation over agent schema tables."""
from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from app.models import AuditLog, Conversation, PendingAction


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def build_dashboard_summary(db: Session) -> dict:
    conversations = db.query(Conversation).all()
    total = len(conversations)
    status_counts = Counter(c.status for c in conversations)
    handoff_count = db.query(AuditLog).filter_by(action_type="handoff").count()
    pending_count = db.query(PendingAction).filter_by(status="pending").count()

    knowledge_logs = (
        db.query(AuditLog)
        .filter_by(action_type="tool_call", tool_name="search_knowledge")
        .all()
    )
    knowledge_hits = sum(1 for log in knowledge_logs if log.status == "hit")
    gap_logs = db.query(AuditLog).filter_by(action_type="knowledge_gap").all()
    gap_counts = Counter((log.params or {}).get("query", "") for log in gap_logs)
    knowledge_gaps = [
        {"query": query, "count": count}
        for query, count in gap_counts.most_common()
        if query
    ]

    return {
        "conversation_total": total,
        "status_counts": dict(status_counts),
        "pending_actions": pending_count,
        "ai_resolution_rate": _rate(status_counts.get("resolved", 0) + status_counts.get("closed", 0), total),
        "handoff_rate": _rate(handoff_count, total),
        "knowledge_hit_rate": _rate(knowledge_hits, len(knowledge_logs)),
        "knowledge_gaps": knowledge_gaps,
    }
