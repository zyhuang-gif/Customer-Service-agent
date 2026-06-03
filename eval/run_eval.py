from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import request


def parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line.removeprefix("data:").strip()
            if not payload:
                continue
            events.append(json.loads(payload))
    return events


def post_json(url: str, body: dict, timeout: float) -> str:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def expectation(case: dict) -> dict:
    expect = dict(case.get("expect") or {})
    if "event_types" not in expect and "expect_event_types" in case:
        expect["event_types"] = case["expect_event_types"]
    return expect


def event_types(events: list[dict]) -> list[str | None]:
    return [event.get("type") for event in events]


def event_text(events: list[dict]) -> str:
    parts = []
    for event in events:
        for key in ("content", "message", "text"):
            if event.get(key):
                parts.append(str(event[key]))
    return "\n".join(parts)


def extract_tools(events: list[dict]) -> list[str]:
    tools: list[str] = []
    for event in events:
        if event.get("tool_name"):
            tools.append(event["tool_name"])
        trace = event.get("agent_trace")
        if isinstance(trace, list):
            for step in trace:
                if not isinstance(step, dict):
                    continue
                action = step.get("action")
                if action and action not in ("route", "respond"):
                    tools.append(action)
        for key in ("tool_calls", "tools", "steps"):
            value = event.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, str):
                    tools.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("tool_name")
                    if name:
                        tools.append(name)
    return tools


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def actual_outcome(events: list[dict]) -> dict:
    seen = event_types(events)
    text = event_text(events)
    awaiting = "awaiting_confirmation" in seen
    handoff = (
        "handoff" in seen
        or "human_handling" in seen
        or "转接人工" in text
        or "人工客服" in text
    )
    return {
        "event_types": seen,
        "tools": _dedupe(extract_tools(events)),
        "ai_resolution": "response" in seen and not awaiting and not handoff,
        "handoff": handoff,
        "knowledge_hit": any(
            event.get("citations") or event.get("references") or event.get("knowledge_hit")
            for event in events
        ) or any(marker in text for marker in ("政策", "知识库", "售后规则", "根据")),
        "awaiting_confirmation": awaiting,
    }


def evaluate_case(case: dict, events: list[dict]) -> dict:
    expect = expectation(case)
    actual = actual_outcome(events)
    expected_events = expect.get("event_types", [])
    missing = [item for item in expected_events if item not in actual["event_types"]]
    expected_tools = expect.get("tools", [])
    high_risk_tools = expect.get("high_risk_tools", [])

    observed_tools = set(actual["tools"])
    if expected_tools and observed_tools:
        tool_call_correct = all(tool in observed_tools for tool in expected_tools)
    elif high_risk_tools:
        tool_call_correct = actual["awaiting_confirmation"]
    elif "transfer_to_human" in expected_tools:
        tool_call_correct = actual["handoff"]
    elif "search_knowledge" in expected_tools and "knowledge_hit" in expect:
        tool_call_correct = actual["knowledge_hit"] == expect["knowledge_hit"]
    else:
        tool_call_correct = True

    high_risk_misexecuted = bool(high_risk_tools) and not actual["awaiting_confirmation"]
    intent_correct = not missing and not high_risk_misexecuted

    checks = [
        not missing,
        intent_correct,
        tool_call_correct,
        not high_risk_misexecuted,
    ]
    for key in ("ai_resolution", "handoff", "knowledge_hit"):
        if key in expect:
            checks.append(actual[key] == expect[key])

    return {
        "id": case["id"],
        "passed": all(checks),
        "intent": expect.get("intent", ""),
        "intent_correct": intent_correct,
        "tool_call_correct": tool_call_correct,
        "expected_tools": expected_tools,
        "observed_tools": actual["tools"],
        "seen_event_types": actual["event_types"],
        "missing_event_types": missing,
        "actual_ai_resolution": actual["ai_resolution"],
        "actual_handoff": actual["handoff"],
        "actual_knowledge_hit": actual["knowledge_hit"],
        "high_risk_misexecuted": high_risk_misexecuted,
        "actual_awaiting_confirmation": actual["awaiting_confirmation"],
        "expected_high_risk": bool(high_risk_tools),
        "expected_knowledge_hit": expect.get("knowledge_hit"),
    }


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def build_metrics(results: list[dict]) -> dict:
    total = len(results)
    high_risk_results = [r for r in results if r.get("expected_high_risk")]
    knowledge_gap_results = [r for r in results if r.get("expected_knowledge_hit") is False]
    return {
        "case_pass_rate": _rate(sum(1 for r in results if r["passed"]), total),
        "intent_accuracy": _rate(sum(1 for r in results if r["intent_correct"]), total),
        "tool_call_accuracy": _rate(sum(1 for r in results if r["tool_call_correct"]), total),
        "ai_resolution_rate": _rate(sum(1 for r in results if r["actual_ai_resolution"]), total),
        "handoff_rate": _rate(sum(1 for r in results if r["actual_handoff"]), total),
        "knowledge_hit_rate": _rate(sum(1 for r in results if r["actual_knowledge_hit"]), total),
        "high_risk_misexecution_count": sum(1 for r in results if r["high_risk_misexecuted"]),
        "high_risk_block_rate": _rate(
            sum(1 for r in high_risk_results if r.get("actual_awaiting_confirmation")),
            len(high_risk_results),
        ),
        "knowledge_gap_accuracy": _rate(
            sum(1 for r in knowledge_gap_results if not r.get("actual_knowledge_hit")),
            len(knowledge_gap_results),
        ),
    }


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_markdown_report(report: dict) -> str:
    metrics = report.get("metrics", {})
    lines = [
        "# Customer Service Agent Eval Report",
        "",
        f"Passed: {report.get('passed', 0)} / {report.get('total', 0)}",
        "",
        "## Metrics",
        "",
    ]
    for key, value in metrics.items():
        display = _percent(value) if isinstance(value, float) else str(value)
        lines.append(f"- `{key}`: {display}")

    failed = [r for r in report.get("results", []) if not r.get("passed")]
    lines.extend(["", "## Failed Cases", ""])
    if not failed:
        lines.append("All cases passed.")
    for result in failed:
        lines.append(f"### {result.get('id', '')}")
        if result.get("error"):
            lines.append(f"- Error: {result['error']}")
        missing = result.get("missing_event_types") or []
        if missing:
            lines.append(f"- Missing events: {', '.join(missing)}")
        expected = result.get("expected_tools") or []
        observed = result.get("observed_tools") or []
        if expected or observed:
            lines.append(f"- Expected tools: {', '.join(expected) if expected else '-'}")
            lines.append(f"- Observed tools: {', '.join(observed) if observed else '-'}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(report: dict, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_markdown_report(report), encoding="utf-8")


def run_case(base_url: str, case: dict, timeout: float) -> dict:
    body = {
        "customer_ref": case["customer_ref"],
        "message": case["message"],
    }
    raw = post_json(f"{base_url.rstrip('/')}/chat", body, timeout)
    events = parse_sse(raw)
    return evaluate_case(case, events)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight cs-agent SSE eval cases.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("cases.json")))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--report-md",
        default="",
        help="Optional path to write a Markdown eval report, e.g. docs/verification/latest-eval-report.md",
    )
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    results = []
    for case in cases:
        try:
            results.append(run_case(args.base_url, case, args.timeout))
        except Exception as exc:
            results.append({
                "id": case["id"],
                "passed": False,
                "intent": expectation(case).get("intent", ""),
                "intent_correct": False,
                "tool_call_correct": False,
                "expected_tools": expectation(case).get("tools", []),
                "observed_tools": [],
                "seen_event_types": [],
                "missing_event_types": expectation(case).get("event_types", []),
                "actual_ai_resolution": False,
                "actual_handoff": False,
                "actual_knowledge_hit": False,
                "high_risk_misexecuted": False,
                "error": str(exc),
            })

    passed = sum(1 for result in results if result["passed"])
    report = {
        "passed": passed,
        "total": len(results),
        "metrics": build_metrics(results),
        "results": results,
    }
    if args.report_md:
        write_markdown_report(report, args.report_md)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
