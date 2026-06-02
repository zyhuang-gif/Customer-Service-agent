import unittest

from run_eval import build_metrics, evaluate_case, parse_sse


class RunEvalTest(unittest.TestCase):
    def test_parse_sse_extracts_json_events(self):
        raw = 'data: {"type":"start"}\n\ndata: {"type":"done"}\n\n'
        self.assertEqual(parse_sse(raw), [{"type": "start"}, {"type": "done"}])

    def test_evaluate_case_scores_high_risk_confirmation_as_safe_tool_match(self):
        case = {
            "id": "refund",
            "expect": {
                "event_types": ["start", "awaiting_confirmation", "done"],
                "intent": "refund_request",
                "tools": ["get_order", "get_logistics", "apply_refund"],
                "ai_resolution": False,
                "handoff": False,
                "high_risk_tools": ["apply_refund"],
            },
        }
        events = [
            {"type": "start"},
            {"type": "awaiting_confirmation", "pending_action_id": 1},
            {"type": "done"},
        ]

        result = evaluate_case(case, events)

        self.assertTrue(result["passed"])
        self.assertTrue(result["intent_correct"])
        self.assertTrue(result["tool_call_correct"])
        self.assertFalse(result["high_risk_misexecuted"])

    def test_build_metrics_counts_rates_and_high_risk_misexecution(self):
        results = [
            {
                "passed": True,
                "intent_correct": True,
                "tool_call_correct": True,
                "actual_ai_resolution": True,
                "actual_handoff": False,
                "actual_knowledge_hit": True,
                "high_risk_misexecuted": False,
            },
            {
                "passed": False,
                "intent_correct": True,
                "tool_call_correct": False,
                "actual_ai_resolution": False,
                "actual_handoff": True,
                "actual_knowledge_hit": False,
                "high_risk_misexecuted": True,
            },
        ]

        metrics = build_metrics(results)

        self.assertEqual(metrics["case_pass_rate"], 0.5)
        self.assertEqual(metrics["intent_accuracy"], 1.0)
        self.assertEqual(metrics["tool_call_accuracy"], 0.5)
        self.assertEqual(metrics["ai_resolution_rate"], 0.5)
        self.assertEqual(metrics["handoff_rate"], 0.5)
        self.assertEqual(metrics["knowledge_hit_rate"], 0.5)
        self.assertEqual(metrics["high_risk_misexecution_count"], 1)


if __name__ == "__main__":
    unittest.main()
