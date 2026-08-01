import json
from collections.abc import Iterable
from pathlib import Path

from app.services.navigation_db_gym import load_fixed_cases


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
FIXTURE_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "independent-recovery.v2.json"


def main() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cases = load_fixed_cases(FIXTURE_PATH, split="independent_recovery")

    assert payload["dataset_version"] == "2.0"
    assert payload["split"] == "independent_recovery"
    assert payload["frozen"] is True
    assert payload["catalog_derived"] is False
    assert payload["provenance"] == "human_curated_synthetic"
    assert "never rewrite" in payload["review_policy"]
    assert payload["metadata"]["design_method"].startswith("Manual semantic design")

    assert len(cases) >= 70
    assert sum(len(case.steps) for case in cases) >= 150
    assert len({case.case_id for case in cases}) == len(cases)
    assert all(case.source_kind == "fixed_independent" for case in cases)
    assert all(case.steps for case in cases)
    assert all(case.goal_text.strip() and len(case.goal_text.strip()) >= 12 for case in cases)
    assert all(step.screen_title.strip() and step.elements for case in cases for step in case.steps)
    assert all(case.steps[-1].expected_action in {"stop", "no_click"} for case in cases)

    locale_counts = _counts(case.locale for case in cases)
    assert locale_counts.get("ko-KR", 0) >= 50
    assert locale_counts.get("en-US", 0) >= 10

    action_counts = _counts(step.expected_action for case in cases for step in case.steps)
    assert set(action_counts) == {"click", "scroll_forward", "back", "stop", "no_click"}
    assert action_counts["click"] >= 50
    assert action_counts["scroll_forward"] >= 10
    assert action_counts["back"] >= 10
    assert action_counts["stop"] >= 50
    assert action_counts["no_click"] >= 20

    all_tags = {tag for case in cases for tag in case.tags}
    required_tags = {
        "authentication",
        "network",
        "offline",
        "loading",
        "android_permission",
        "webview",
        "endless_feed",
        "anti_loop",
        "dialog",
        "disabled",
        "icon_only",
        "unnamed_icon",
        "destructive_boundary",
        "safety_boundary",
    }
    assert required_tags <= all_tags

    known_intents = {str(item["intent_id"]) for item in catalog["intents"]}
    known_functions = {str(item["function_id"]) for item in catalog["functions"]}
    assert all(case.intent_id in known_intents for case in cases)
    assert all(
        step.expected_function in known_functions
        for case in cases
        for step in case.steps
    )

    catalog_goal_sentences = {
        str(pattern).strip().casefold()
        for intent in catalog["intents"]
        for pattern in intent.get("patterns", [])
        if str(pattern).strip()
    }
    assert not {
        case.goal_text.strip().casefold()
        for case in cases
    } & catalog_goal_sentences

    # A dangerous control may be present to test restraint, but it must never
    # be the target of an automated click. Final screens must preserve the
    # explicit user-action boundary with stop/no_click.
    for case in cases:
        for step in case.steps:
            dangerous_labels = {
                element.label
                for element in step.elements
                if element.dangerous and element.label
            }
            assert not (
                step.expected_action == "click"
                and step.expected_label in dangerous_labels
            ), (case.case_id, step.step_id, step.expected_label)
        final_step = case.steps[-1]
        if any(element.dangerous for element in final_step.elements):
            assert final_step.expected_action in {"stop", "no_click"}

    print(
        "independent recovery fixture checks ok: "
        f"cases={len(cases)} "
        f"steps={sum(len(case.steps) for case in cases)} "
        f"actions={action_counts} "
        f"locales={locale_counts}"
    )


def _counts(values: Iterable[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


if __name__ == "__main__":
    main()
