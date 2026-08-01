from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from app.services.navigation_function_catalog import NavigationFunctionCatalog


def evaluate_independent_goals(
    *,
    catalog_path: Path,
    fixture_paths: Iterable[Path],
) -> dict[str, Any]:
    """Measure intent resolution on independently authored user goals only."""

    fixtures: list[tuple[Path, dict[str, Any]]] = []
    for path in fixture_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("catalog_derived") is not False:
            raise ValueError(f"Goal fixture is not marked independent: {path}")
        fixtures.append((path, payload))

    total = 0
    correct = 0
    generic = 0
    confidence_sum = 0.0
    failures: list[dict[str, object]] = []
    split_counts: dict[str, Counter[str]] = defaultdict(Counter)
    intent_counts: dict[str, Counter[str]] = defaultdict(Counter)
    confusions: Counter[tuple[str, str]] = Counter()
    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "independent-goals.sqlite",
            catalog_path,
        )
        for path, payload in fixtures:
            split = str(payload.get("split", path.stem))
            for case in payload.get("cases", []):
                total += 1
                split_counts[split]["total"] += 1
                expected = str(case.get("intent_id", ""))
                intent_counts[expected]["total"] += 1
                goal_text = str(case.get("goal_text", ""))
                plan = catalog.plan_goal(goal_text)
                confidence_sum += plan.confidence
                is_correct = plan.intent == expected
                if is_correct:
                    correct += 1
                    split_counts[split]["correct"] += 1
                    intent_counts[expected]["correct"] += 1
                    continue
                generic += int(plan.intent == "generic_navigation")
                confusions[(expected, plan.intent)] += 1
                failures.append(
                    {
                        "split": split,
                        "case_id": str(case.get("case_id", "")),
                        "locale": str(case.get("locale", "")),
                        "goal_text": goal_text,
                        "expected_intent": expected,
                        "actual_intent": plan.intent,
                        "expected_terminal_function": _expected_terminal(case),
                        "actual_terminal_function": plan.terminal_function,
                        "confidence": plan.confidence,
                    }
                )

    return {
        "schema_version": 1,
        "catalog_derived": False,
        "independent_source_accuracy_claim": True,
        "unseen_holdout_accuracy_claim": False,
        "evaluation_scope": (
            "Independently authored source wording used as a regression suite. "
            "Because failures may be used to improve the catalog, this is not an untouched zero-shot holdout claim."
        ),
        "fixture_count": len(fixtures),
        "total": total,
        "correct": correct,
        "accuracy": _ratio(correct, total),
        "generic_count": generic,
        "generic_rate": _ratio(generic, total),
        "mean_confidence": round(confidence_sum / total, 6) if total else 0.0,
        "split_results": {
            split: {
                "total": counts["total"],
                "correct": counts["correct"],
                "accuracy": _ratio(counts["correct"], counts["total"]),
            }
            for split, counts in sorted(split_counts.items())
        },
        "intent_results": {
            intent: {
                "total": counts["total"],
                "correct": counts["correct"],
                "accuracy": _ratio(counts["correct"], counts["total"]),
            }
            for intent, counts in sorted(intent_counts.items())
        },
        "confusions": [
            {"expected_intent": expected, "actual_intent": actual, "count": count}
            for (expected, actual), count in confusions.most_common()
        ],
        "failures": failures,
    }


def _expected_terminal(case: dict[str, Any]) -> str:
    steps = list(case.get("steps", []))
    if not steps:
        return ""
    return str(dict(steps[-1].get("expected", {})).get("function_id", ""))


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
