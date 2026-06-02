from app.insights import analyze_sentiment, build_handoff_summary
from app.models import Message


def test_analyze_sentiment_flags_angry_customer():
    meta = analyze_sentiment("你们太离谱了，我要投诉，马上转人工")
    assert meta["sentiment"] == "angry"
    assert meta["risk"] == "high"
    assert meta["handoff_requested"] is True


def test_analyze_sentiment_keeps_neutral_message_low_risk():
    meta = analyze_sentiment("你好，帮我查一下订单")
    assert meta["sentiment"] == "neutral"
    assert meta["risk"] == "low"
    assert meta["handoff_requested"] is False


def test_build_handoff_summary_uses_recent_messages_and_sentiment():
    messages = [
        Message(role="customer", content="我的退款还没到"),
        Message(role="ai", content="我查一下退款状态"),
        Message(role="customer", content="我要投诉"),
    ]
    summary = build_handoff_summary(messages, {"sentiment": "angry", "risk": "high"})
    assert "客户问题：我要投诉" in summary
    assert "已查信息：我查一下退款状态" in summary
    assert "客户情绪：angry / high" in summary
