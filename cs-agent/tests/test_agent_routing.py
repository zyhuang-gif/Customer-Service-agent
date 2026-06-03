from app.agent.routing import route_customer_message


def test_routes_refund_status_with_knowledge_and_action():
    decision = route_customer_message("我的退款怎么还没到账？订单号是 20260531003")

    assert decision["task_type"] == "refund_status_query"
    assert decision["need_knowledge"] is True
    assert decision["need_action"] is True
    assert decision["action_type"] == "get_refund_status"
    assert decision["risk_level"] == "normal"
    assert "退款" in decision["reason"]


def test_routes_complaint_to_handoff_high_risk():
    decision = route_customer_message("我要投诉，马上转人工")

    assert decision["task_type"] == "complaint"
    assert decision["need_human_handoff"] is True
    assert decision["risk_level"] == "high"


def test_routes_plain_policy_question_to_faq():
    decision = route_customer_message("七天无理由退货规则是什么？")

    assert decision["task_type"] == "faq_qa"
    assert decision["need_knowledge"] is True
    assert decision["need_action"] is False
