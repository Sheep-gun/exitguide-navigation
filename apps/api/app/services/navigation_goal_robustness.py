from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.services.navigation_function_catalog import NavigationFunctionCatalog


KOREAN_PATTERN = re.compile(r"[가-힣]")


def evaluate_goal_robustness(
    catalog_path: Path,
    *,
    mode: str = "fast",
) -> dict[str, Any]:
    source = json.loads(catalog_path.read_text(encoding="utf-8"))
    if mode not in {"fast", "full"}:
        raise ValueError("mode must be fast or full")
    failures: list[dict[str, object]] = []
    per_intent: dict[str, dict[str, int]] = {}
    total = 0
    correct = 0
    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "goal-robustness.sqlite",
            catalog_path,
        )
        for intent_source in source.get("intents", []):
            intent_id = str(intent_source["intent_id"])
            patterns = [str(value) for value in intent_source.get("patterns", [])]
            selected_patterns = patterns if mode == "full" else _fast_pattern_sample(patterns)
            intent_total = 0
            intent_correct = 0
            for pattern in selected_patterns:
                for transform_id, query in metamorphic_goal_variants(pattern, mode=mode):
                    total += 1
                    intent_total += 1
                    plan = catalog.plan_goal(query)
                    if plan.intent == intent_id:
                        correct += 1
                        intent_correct += 1
                        continue
                    failures.append(
                        {
                            "intent_id": intent_id,
                            "source_pattern": pattern,
                            "transform_id": transform_id,
                            "query": query,
                            "actual_intent": plan.intent,
                            "actual_terminal_function": plan.terminal_function,
                            "confidence": plan.confidence,
                        }
                    )
            per_intent[intent_id] = {
                "total": intent_total,
                "correct": intent_correct,
                "failure_count": intent_total - intent_correct,
            }

    confusion = Counter((str(item["intent_id"]), str(item["actual_intent"])) for item in failures)
    return {
        "schema_version": 1,
        "mode": mode,
        "catalog_version": str(source.get("catalog_version", "")),
        "catalog_derived": True,
        "independent_accuracy_claim": False,
        "description": (
            "Metamorphic stability check derived from reviewed goal patterns. "
            "It measures robustness to wrappers and formatting, not independent real-app accuracy."
        ),
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 6) if total else 0.0,
        "intent_count": len(per_intent),
        "perfect_intent_count": sum(1 for item in per_intent.values() if item["failure_count"] == 0),
        "per_intent": per_intent,
        "confusions": [
            {"expected_intent": expected, "actual_intent": actual, "count": count}
            for (expected, actual), count in confusion.most_common()
        ],
        "failures": failures,
    }


def metamorphic_goal_variants(pattern: str, *, mode: str) -> list[tuple[str, str]]:
    korean = bool(KOREAN_PATTERN.search(pattern))
    if korean:
        variants = [
            ("app_prefix", f"유튜브에서 {pattern}"),
            ("polite_suffix", f"{pattern} 메뉴 찾아줘"),
        ]
        if mode == "full":
            variants.append(("desire_suffix", f"{pattern} 하고 싶어"))
            variants.append(("punctuation", f"  {pattern}...  "))
        return variants
    variants = [
        ("polite_prefix", f"please {pattern}"),
        ("desire_prefix", f"I want to {pattern}"),
    ]
    if mode == "full":
        variants.append(("menu_suffix", f"{pattern} menu"))
        variants.append(("case_and_punctuation", f"  {pattern.upper()}...  "))
    return variants


def _fast_pattern_sample(patterns: list[str]) -> list[str]:
    if len(patterns) <= 2:
        return patterns
    korean = next((value for value in patterns if KOREAN_PATTERN.search(value)), patterns[0])
    english = next((value for value in patterns if not KOREAN_PATTERN.search(value)), patterns[-1])
    return list(dict.fromkeys((korean, english)))
