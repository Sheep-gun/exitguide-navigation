#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.navigation_contracts import (  # noqa: E402
    AccessibilityNodeSummary,
    DecideRequest,
    NavigationCandidate,
    ScreenObservation,
)
from app.services.navigation_decision_memory import NavigationDecisionMemory  # noqa: E402
from app.services.navigation_model_clients import (  # noqa: E402
    Exaone45VisionClient,
    NavigationPlannerResearchClient,
    OpenAICompatibleChatClient,
)
from app.services.navigation_research_policy import AndroidWorldResearchPolicy  # noqa: E402
from app.services.navigation_runtime import NavigationRuntime  # noqa: E402
from app.services.navigation_runtime_store import NavigationRuntimeStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Leakage-aware diagnostic replay for the Navigation decision runtime."
    )
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument(
        "--cases-db",
        type=Path,
        help="Frozen evaluation-case DB. Defaults to --db for legacy diagnostic replay.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def load_cases(path: Path, limit: int) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    sql = """
        SELECT v.*, c.source_step_ordinal, c.scroll_direction,
               COALESCE(s.split, 'unassigned') AS app_split,
               chosen.candidate_key AS expected_candidate_key
        FROM verified_decision_cases AS v
        JOIN decision_cases AS c ON c.case_id = v.case_id
        LEFT JOIN evaluation_app_splits AS s ON s.app_package = v.source_app_package
        LEFT JOIN affordances AS chosen ON chosen.affordance_id = v.chosen_affordance_id
        ORDER BY v.source_app_package, c.source_record_id, c.source_step_ordinal
    """
    if limit > 0:
        sql += " LIMIT ?"
        rows = connection.execute(sql, (limit,)).fetchall()
    else:
        rows = connection.execute(sql).fetchall()
    cases: list[dict[str, Any]] = []
    for row in rows:
        case = dict(row)
        candidates = connection.execute(
            """
            SELECT candidate_key, label, role, icon_semantics, nearby_text,
                   parent_semantics, position_bucket, risk_level
            FROM affordances WHERE screen_id = ? ORDER BY candidate_key
            """,
            (row["screen_id"],),
        ).fetchall()
        case["candidates"] = [dict(candidate) for candidate in candidates]
        observation = connection.execute(
            """
            SELECT accessibility_json
            FROM screen_observations
            WHERE screen_id = ? AND app_package = ?
            ORDER BY CASE WHEN source_type = 'real_device' THEN 0 ELSE 1 END,
                     captured_at DESC
            LIMIT 1
            """,
            (row["screen_id"], row["source_app_package"]),
        ).fetchone()
        case["nodes"] = load_accessibility_nodes(
            None if observation is None else observation["accessibility_json"],
            candidate_ids={str(candidate["candidate_key"]) for candidate in candidates},
        )
        cases.append(case)
    connection.close()
    return cases


def load_accessibility_nodes(
    raw_payload: Any,
    *,
    candidate_ids: set[str],
) -> list[AccessibilityNodeSummary]:
    """Restore observed node facts needed for faithful offline policy replay.

    Older imported observations can contain anonymous nodes that cannot satisfy
    the executable candidate grounding contract. Those records remain usable as
    candidate-only replays; observed, structurally valid node sets are restored
    without fabricating scrollability or identifiers.
    """

    if not raw_payload:
        return []
    try:
        payload = json.loads(str(raw_payload))
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    elements = payload.get("elements", []) if isinstance(payload, dict) else []
    if not isinstance(elements, list) or not elements:
        return []

    node_ids = [
        str(element.get("node_id", "")).strip()
        for element in elements
        if isinstance(element, dict)
    ]
    known_ids = set(node_ids)
    if (
        len(node_ids) != len(elements)
        or any(not node_id for node_id in node_ids)
        or len(known_ids) != len(node_ids)
        or not candidate_ids.issubset(known_ids)
    ):
        return []

    nodes: list[AccessibilityNodeSummary] = []
    for element in elements:
        parent_id = str(element.get("parent_node_id") or "").strip() or None
        if parent_id is not None and parent_id not in known_ids:
            return []
        nodes.append(
            AccessibilityNodeSummary(
                node_id=str(element["node_id"]),
                parent_id=parent_id,
                text=str(element.get("label", "")),
                content_description=str(element.get("content_description", "")),
                role=str(element.get("role", "unknown")),
                clickable=bool(element.get("clickable", False)),
                scrollable=bool(element.get("scrollable", False)),
                enabled=bool(element.get("enabled", True)),
                selected=bool(element.get("selected", False)),
                checked=element.get("checked"),
            )
        )
    return nodes


def exact_match(case: dict[str, Any], action: dict[str, Any]) -> bool:
    if action["name"] != case["chosen_action"]:
        return False
    if action["name"] == "click":
        return action["candidate_id"] == case["expected_candidate_key"]
    if action["name"] == "scroll":
        return action["direction"] == case["scroll_direction"]
    return True


def main() -> None:
    args = parse_args()
    cases_database = args.cases_db or args.db
    cases = load_cases(cases_database, args.limit)
    with tempfile.TemporaryDirectory() as temporary:
        runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(args.db),
            store=NavigationRuntimeStore(Path(temporary) / "runtime.sqlite"),
            policy=AndroidWorldResearchPolicy(
                planner_model=NavigationPlannerResearchClient(
                    OpenAICompatibleChatClient(
                        api_key="", base_url="https://example.invalid/v1", model="offline"
                    ),
                    provider_name="solar_pro3",
                ),
                exaone_vlm=Exaone45VisionClient(
                    OpenAICompatibleChatClient(api_key="", base_url="", model="offline-vlm")
                ),
                allow_model_fallback=True,
            ),
        )
        results: list[dict[str, Any]] = []
        for index, case in enumerate(cases):
            candidates = [
                NavigationCandidate(
                    candidate_id=str(candidate["candidate_key"]),
                    label=str(candidate["label"]),
                    role=str(candidate["role"]),
                    icon_semantics=str(candidate["icon_semantics"]),
                    nearby_text=str(candidate["nearby_text"]),
                    parent_semantics=str(candidate["parent_semantics"]),
                    position_bucket=str(candidate["position_bucket"]),
                    risk_level=str(candidate["risk_level"]),
                )
                for candidate in case["candidates"]
            ]
            response = runtime.decide(
                DecideRequest(
                    request_id=f"offline-{index}",
                    session_id=f"offline-session-{index}",
                    app_package=str(case["source_app_package"]),
                    goal_text=str(case["goal_text_normalized"]),
                    screen=ScreenObservation(
                        window_title=str(case["title_normalized"]),
                        activity_name=(
                            "android.webkit.WebView"
                            if case["surface_type"] == "webview"
                            else "android.view.View"
                        ),
                        nodes=case["nodes"],
                        candidates=candidates,
                    ),
                )
            )
            action = response.action.model_dump(mode="json")
            positive = case["progress_label"] in {"advanced", "reached"}
            failed_click = case["chosen_action"] == "click" and case["outcome_type"] in {
                "no_change",
                "wrong_destination",
                "infinite_feed",
            }
            predicted_same_failed_click = (
                failed_click
                and action["name"] == "click"
                and action["candidate_id"] == case["expected_candidate_key"]
            )
            results.append(
                {
                    "case_id": case["case_id"],
                    "goal_id": case["goal_id"],
                    "goal_text": case["goal_text_normalized"],
                    "app_split": case["app_split"],
                    "source_app_package": case["source_app_package"],
                    "first_action": int(case["source_step_ordinal"]) == 0,
                    "positive": positive,
                    "failed_click": failed_click,
                    "goal_status": response.goal.status,
                    "resolved_goal_id": response.goal.goal_id,
                    "goal_confidence": response.goal.confidence,
                    "expected_action": case["chosen_action"],
                    "predicted_action": action["name"],
                    "exact_match": exact_match(case, action) if positive else None,
                    "avoided_failed_click": not predicted_same_failed_click if failed_click else None,
                    "dangerous_auto_click": action["name"] == "click"
                    and any(
                        candidate.candidate_id == action["candidate_id"]
                        and candidate.risk_level in {"medium", "high", "blocked"}
                        for candidate in candidates
                    ),
                }
            )

    report = summarize(results, args.db, cases_database)
    report["retrieval_isolation"] = {
        "positive_route_cases": "source_app_excluded",
        "verified_negative_safety_cases": "same_app_allowed",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def summarize(
    results: list[dict[str, Any]],
    database: Path,
    cases_database: Path,
) -> dict[str, Any]:
    positive = [result for result in results if result["positive"]]
    first = [result for result in positive if result["first_action"]]
    failures = [result for result in results if result["failed_click"]]
    by_split: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cases": 0, "positive_cases": 0, "exact_matches": 0, "failed_clicks": 0, "avoided": 0}
    )
    by_goal: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cases": 0, "recognized": 0, "positive_cases": 0, "exact_matches": 0}
    )
    action_confusion: dict[str, int] = defaultdict(int)
    for result in results:
        split = by_split[str(result["app_split"])]
        split["cases"] += 1
        if result["positive"]:
            split["positive_cases"] += 1
            split["exact_matches"] += int(bool(result["exact_match"]))
        if result["failed_click"]:
            split["failed_clicks"] += 1
            split["avoided"] += int(bool(result["avoided_failed_click"]))
        goal = by_goal[str(result["goal_id"])]
        goal["cases"] += 1
        goal["recognized"] += int(result["goal_status"] == "recognized")
        if result["positive"]:
            goal["positive_cases"] += 1
            goal["exact_matches"] += int(bool(result["exact_match"]))
            action_confusion[
                f'{result["expected_action"]}->{result["predicted_action"]}'
            ] += 1
    fixed_validation = cases_database.resolve() != database.resolve()
    return {
        "evaluation_kind": (
            "fixed_validation_leave_source_app_out_replay"
            if fixed_validation
            else "diagnostic_leave_source_app_out_replay"
        ),
        "claim_scope": (
            "promotion_regression_gate_only_not_locked_holdout"
            if fixed_validation
            else "runtime_direction_gate_only_not_final_ab"
        ),
        "database": str(database.resolve()),
        "database_sha256": file_sha256(database),
        "evaluation_cases_database": str(cases_database.resolve()),
        "evaluation_cases_sha256": file_sha256(cases_database),
        "retrieval_excludes_source_app": True,
        "case_count": len(results),
        "positive_case_count": len(positive),
        "positive_exact_next_action_accuracy": ratio(
            sum(bool(result["exact_match"]) for result in positive), len(positive)
        ),
        "positive_first_action_accuracy": ratio(
            sum(bool(result["exact_match"]) for result in first), len(first)
        ),
        "positive_first_action_count": len(first),
        "failed_click_case_count": len(failures),
        "failed_click_avoidance_rate": ratio(
            sum(bool(result["avoided_failed_click"]) for result in failures), len(failures)
        ),
        "recognized_goal_rate": ratio(
            sum(result["goal_status"] == "recognized" for result in results), len(results)
        ),
        "dangerous_auto_click_count": sum(bool(result["dangerous_auto_click"]) for result in results),
        "by_app_split": dict(by_split),
        "by_goal": dict(by_goal),
        "positive_action_confusion": dict(sorted(action_confusion.items())),
        "repeated_failed_case_ids": [
            result["case_id"]
            for result in failures
            if not result["avoided_failed_click"]
        ],
        "goal_resolution_failures": sorted(
            {
                (
                    str(result["goal_id"]),
                    str(result["goal_text"]),
                    str(result["resolved_goal_id"]),
                    str(result["goal_status"]),
                    float(result["goal_confidence"]),
                )
                for result in results
                if result["goal_status"] != "recognized"
                or result["resolved_goal_id"] != result["goal_id"]
            }
        ),
    }


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
