#!/usr/bin/env python3
"""Replay one frozen screen set against a live Navigation API endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-db", required=True, type=Path)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--request-prefix", required=True)
    parser.add_argument("--decision-db-sha256", required=True)
    parser.add_argument("--public-prior-enabled", action="store_true")
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_match(case: sqlite3.Row, action: dict[str, Any]) -> bool:
    if action.get("name") != case["expected_action"]:
        return False
    if case["expected_action"] == "click":
        return action.get("candidate_id") == case["expected_candidate_id"]
    if case["expected_action"] == "scroll":
        return action.get("direction") == case["expected_direction"]
    return True


def main() -> None:
    args = parse_args()
    connection = sqlite3.connect(f"file:{args.cases_db.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    cases = connection.execute(
        "SELECT * FROM frozen_validation_cases ORDER BY rowid"
    ).fetchall()
    if not cases:
        raise ValueError("frozen case database is empty")
    results: list[dict[str, Any]] = []
    dangerous_auto_click_count = 0
    endpoint = args.endpoint.rstrip("/") + "/v1/navigation/decide"
    for ordinal, case in enumerate(cases):
        screen = json.loads(case["screen_payload_json"])
        request_id = f"{args.request_prefix}-{ordinal}-{case['case_id']}"
        request_payload = {
            "request_id": request_id,
            "app_package": case["app_package"],
            "app_version": case["app_version"],
            "locale": "ko-KR",
            "goal_text": case["goal_text"],
            "step_ordinal": 0,
            "visual_reasoning_required": False,
            "screen": screen,
        }
        encoded = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        started = time.perf_counter()
        with urllib.request.urlopen(
            urllib.request.Request(
                endpoint,
                data=encoded,
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=90,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        action = result["action"]
        candidate = next(
            (
                item
                for item in screen.get("candidates", [])
                if str(item.get("candidate_id") or item.get("element_id") or "")
                == str(action.get("candidate_id") or "")
            ),
            None,
        )
        dangerous = bool(
            action.get("name") == "click"
            and candidate is not None
            and (
                candidate.get("risk_level") in {"medium", "high", "blocked"}
                or candidate.get("dangerous_final") is True
            )
        )
        dangerous_auto_click_count += int(dangerous)
        evidence = [str(value) for value in result.get("evidence_case_ids", [])]
        results.append(
            {
                "case_id": case["case_id"],
                "request_id": request_id,
                "session_id": result["session_id"],
                "decision_id": result["decision_id"],
                "goal_id": result["goal"]["goal_id"],
                "goal_status": result["goal"]["status"],
                "expected_action": case["expected_action"],
                "expected_candidate_id": case["expected_candidate_id"],
                "expected_direction": case["expected_direction"],
                "predicted_action": action["name"],
                "predicted_candidate_id": action.get("candidate_id"),
                "predicted_direction": action.get("direction"),
                "planner_provider": result["planner_provider"],
                "exact_match": exact_match(case, action),
                "first_action": bool(case["first_action"]),
                "visual_reobserve_required": bool(result.get("visual_reobserve_required")),
                "public_evidence_count": sum(value.startswith("public:") for value in evidence),
                "dangerous_auto_click": dangerous,
                "latency_ms": latency_ms,
            }
        )
    connection.close()
    first = [item for item in results if item["first_action"]]
    report = {
        "evaluation_kind": "frozen_validation_navigation_api_replay",
        "claim_scope": "TVING validation only; not locked holdout and not promotion evidence",
        "case_count": len(results),
        "positive_case_count": len(results),
        "evaluation_cases_database": str(args.cases_db.resolve()),
        "evaluation_cases_sha256": file_sha256(args.cases_db),
        "database_sha256": args.decision_db_sha256,
        "public_prior": {
            "enabled": args.public_prior_enabled,
            "mode": "planner_advisory_only",
            "runtime_execution_allowed": False,
            "canonical_promotion_allowed": False,
        },
        "positive_exact_next_action_accuracy": round(
            sum(item["exact_match"] for item in results) / len(results), 4
        ),
        "positive_first_action_accuracy": round(
            sum(item["exact_match"] for item in first) / len(first), 4
        ),
        "positive_first_action_count": len(first),
        "recognized_goal_rate": round(
            sum(item["goal_status"] == "recognized" for item in results) / len(results), 4
        ),
        "dangerous_auto_click_count": dangerous_auto_click_count,
        "mean_latency_ms": round(
            sum(item["latency_ms"] for item in results) / len(results), 1
        ),
        "predictions": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
