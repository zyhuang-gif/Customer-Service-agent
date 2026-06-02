"""Lightweight conversation insights for first-version backend depth."""
from __future__ import annotations

from collections.abc import Sequence


ANGRY_WORDS = ("投诉", "离谱", "生气", "愤怒", "差评", "赔偿", "没人管")
NEGATIVE_WORDS = ("着急", "不满", "失败", "没到账", "太慢", "异常")
HANDOFF_WORDS = ("转人工", "人工", "客服", "投诉")


def analyze_sentiment(text: str) -> dict:
    content = text or ""
    angry = any(word in content for word in ANGRY_WORDS)
    negative = angry or any(word in content for word in NEGATIVE_WORDS)
    handoff_requested = any(word in content for word in HANDOFF_WORDS)
    if angry:
        sentiment = "angry"
        risk = "high"
    elif negative:
        sentiment = "negative"
        risk = "medium"
    else:
        sentiment = "neutral"
        risk = "low"
    return {
        "sentiment": sentiment,
        "risk": risk,
        "handoff_requested": handoff_requested,
    }


def build_handoff_summary(messages: Sequence, sentiment_meta: dict | None = None) -> str:
    sentiment_meta = sentiment_meta or {}
    customer_texts = [m.content for m in messages if getattr(m, "role", "") == "customer" and m.content]
    ai_texts = [m.content for m in messages if getattr(m, "role", "") == "ai" and m.content]
    issue = customer_texts[-1] if customer_texts else "客户请求人工协助"
    checked = ai_texts[-1] if ai_texts else "暂无，需人工继续核实"
    sentiment = sentiment_meta.get("sentiment", "neutral")
    risk = sentiment_meta.get("risk", "low")
    return "\n".join([
        f"客户问题：{issue}",
        f"已查信息：{checked}",
        "已尝试动作：AI 已记录当前会话并请求人工接管",
        f"客户情绪：{sentiment} / {risk}",
        "建议人工处理：优先安抚客户，核对订单/退款/物流事实后给出明确下一步。",
    ])
