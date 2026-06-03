import tempfile
import unittest
from pathlib import Path

from run_eval import build_markdown_report, build_metrics, evaluate_case, parse_sse, write_markdown_report


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
                "expected_high_risk": True,
                "actual_awaiting_confirmation": True,
                "expected_knowledge_hit": True,
            },
            {
                "passed": False,
                "intent_correct": True,
                "tool_call_correct": False,
                "actual_ai_resolution": False,
                "actual_handoff": True,
                "actual_knowledge_hit": False,
                "high_risk_misexecuted": True,
                "expected_high_risk": True,
                "actual_awaiting_confirmation": False,
                "expected_knowledge_hit": False,
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
        self.assertEqual(metrics["high_risk_block_rate"], 0.5)
        self.assertEqual(metrics["knowledge_gap_accuracy"], 1.0)

    def test_evaluate_case_reads_tools_from_agent_trace(self):
        case = {
            "id": "faq",
            "expect": {
                "event_types": ["start", "response", "done"],
                "tools": ["search_knowledge"],
                "knowledge_hit": True,
            },
        }
        events = [
            {"type": "start"},
            {
                "type": "response",
                "content": "根据退款政策回答。",
                "agent_trace": [
                    {"agent": "CoordinatorAgent", "action": "route"},
                    {"agent": "KnowledgeAgent", "action": "search_knowledge"},
                    {"agent": "CoordinatorAgent", "action": "respond"},
                ],
                "citations": [{"title": "退款政策", "source": "refund.md"}],
            },
            {"type": "done"},
        ]

        result = evaluate_case(case, events)

        self.assertTrue(result["passed"])
        self.assertEqual(result["observed_tools"], ["search_knowledge"])

    def test_markdown_report_contains_summary_and_failed_cases(self):
        report = {
            "passed": 1,
            "total": 2,
            "metrics": {
                "case_pass_rate": 0.5,
                "tool_call_accuracy": 0.5,
                "high_risk_block_rate": 1.0,
                "knowledge_gap_accuracy": 1.0,
            },
            "results": [
                {"id": "ok", "passed": True, "missing_event_types": [], "expected_tools": [], "observed_tools": []},
                {
                    "id": "bad",
                    "passed": False,
                    "missing_event_types": ["done"],
                    "expected_tools": ["search_knowledge"],
                    "observed_tools": [],
                    "error": "timeout",
                },
            ],
        }

        md = build_markdown_report(report)

        self.assertIn("# Customer Service Agent Eval Report", md)
        self.assertIn("Passed: 1 / 2", md)
        self.assertIn("bad", md)
        self.assertIn("timeout", md)

    def test_write_markdown_report_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "docs" / "verification" / "latest-eval-report.md"
            write_markdown_report({"passed": 0, "total": 0, "metrics": {}, "results": []}, target)

            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
