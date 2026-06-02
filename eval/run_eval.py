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


def run_case(base_url: str, case: dict, timeout: float) -> dict:
    body = {
        "customer_ref": case["customer_ref"],
        "message": case["message"],
    }
    raw = post_json(f"{base_url.rstrip('/')}/chat", body, timeout)
    events = parse_sse(raw)
    seen = [event.get("type") for event in events]
    missing = [event for event in case["expect_event_types"] if event not in seen]
    return {
        "id": case["id"],
        "passed": not missing,
        "seen_event_types": seen,
        "missing_event_types": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight cs-agent SSE eval cases.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("cases.json")))
    parser.add_argument("--timeout", type=float, default=180.0)
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
                "seen_event_types": [],
                "missing_event_types": case["expect_event_types"],
                "error": str(exc),
            })

    passed = sum(1 for result in results if result["passed"])
    print(json.dumps({"passed": passed, "total": len(results), "results": results}, ensure_ascii=False, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
