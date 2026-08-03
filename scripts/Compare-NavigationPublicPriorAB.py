from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


METRICS = (
    "positive_exact_next_action_accuracy",
    "positive_first_action_accuracy",
    "failed_click_avoidance_rate",
    "recognized_goal_rate",
)


def _delta(before: Any, after: Any) -> float | None:
    if before is None or after is None:
        return None
    return round(float(after) - float(before), 4)


def compare(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if baseline.get("evaluation_cases_sha256") != candidate.get("evaluation_cases_sha256"):
        raise ValueError("A and B must use the same frozen evaluation-case database")
    if baseline.get("database_sha256") != candidate.get("database_sha256"):
        raise ValueError("A and B must use the same Decision DB")
    if baseline.get("case_count", 0) <= 0:
        raise ValueError("A/B comparison requires at least one frozen evaluation case")
    if baseline.get("public_prior", {}).get("enabled") is not False:
        raise ValueError("A must have public prior disabled")
    if candidate.get("public_prior", {}).get("enabled") is not True:
        raise ValueError("B must have public prior enabled")

    deltas = {metric: _delta(baseline.get(metric), candidate.get(metric)) for metric in METRICS}
    safety_regressed = int(candidate.get("dangerous_auto_click_count", 0)) > int(
        baseline.get("dangerous_auto_click_count", 0)
    )
    accuracy_regressed = any(
        deltas[metric] is not None and deltas[metric] < 0
        for metric in (
            "positive_exact_next_action_accuracy",
            "positive_first_action_accuracy",
            "failed_click_avoidance_rate",
        )
    )
    improvement = any(value is not None and value > 0 for value in deltas.values())
    passed = not safety_regressed and not accuracy_regressed and improvement
    return {
        "evaluation_kind": "frozen_validation_public_prior_ab",
        "case_count": baseline["case_count"],
        "evaluation_cases_sha256": baseline["evaluation_cases_sha256"],
        "decision_db_sha256": baseline["database_sha256"],
        "metric_deltas_b_minus_a": deltas,
        "dangerous_auto_click_count": {
            "a": baseline.get("dangerous_auto_click_count", 0),
            "b": candidate.get("dangerous_auto_click_count", 0),
        },
        "passed": passed,
        "conclusion": (
            "public_prior_improved_without_regression"
            if passed
            else "no_proven_improvement_do_not_expand_or_activate"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare public-prior OFF/ON reports on one frozen validation set."
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = compare(
        json.loads(arguments.baseline.read_text(encoding="utf-8")),
        json.loads(arguments.candidate.read_text(encoding="utf-8")),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
