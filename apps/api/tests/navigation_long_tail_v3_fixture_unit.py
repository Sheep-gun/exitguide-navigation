from __future__ import annotations

import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_catalog_v3_data import V3_FUNCTIONS, V3_INTENTS, validate_v3_data  # noqa: E402

from app.services.navigation_db_gym import load_fixed_cases  # noqa: E402
from app.services.navigation_function_catalog import NavigationFunctionCatalog  # noqa: E402


CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
FIXTURE_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "independent-long-tail-v3.json"
SPLIT = "independent_long_tail_v3"
ALLOWED_ACTIONS = {"click", "scroll_forward", "back", "stop", "no_click"}


def _normalize_exact(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _selected_element(step: dict[str, object]) -> dict[str, object] | None:
    expected = dict(step["expected"])
    expected_label = expected.get("label")
    if expected_label is None:
        return None
    for element in step["elements"]:
        if element.get("label") == expected_label:
            return element
    return None


def main() -> None:
    validate_v3_data()
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = list(payload["cases"])
    functions = {str(item["function_id"]): item for item in V3_FUNCTIONS}
    intents = {str(item["intent_id"]): item for item in V3_INTENTS}
    v3_function_ids = set(functions)
    v3_intent_ids = set(intents)

    assert payload["schema_version"] == 2
    assert payload["fixture_version"] == "3.0.0"
    assert payload["split"] == SPLIT
    assert payload["frozen"] is True
    assert payload["catalog_derived"] is False
    assert payload["provenance"] == "independent_long_tail_authoring"
    assert payload["tuning_allowed"] is True
    assert payload["coverage_contract"] == {
        "v3_intents": 221,
        "v3_functions": 239,
        "minimum_cases": 221,
        "minimum_steps": 500,
        "balanced_locales": ["ko-KR", "en-US"],
    }
    assert "must not be imported" in payload["authoring_policy"]["independence"]

    assert len(V3_INTENTS) == 221
    assert len(V3_FUNCTIONS) == 239
    assert len(cases) == 221
    assert sum(len(case["steps"]) for case in cases) == 663
    assert len({str(case["case_id"]) for case in cases}) == len(cases)
    assert len({str(case["goal_text"]) for case in cases}) == len(cases)
    assert {str(case["intent_id"]) for case in cases} == v3_intent_ids
    assert Counter(str(case["intent_id"]) for case in cases).most_common(1)[0][1] == 1

    locale_counts = Counter(str(case["locale"]) for case in cases)
    assert locale_counts == {"ko-KR": 111, "en-US": 110}
    assert abs(locale_counts["ko-KR"] - locale_counts["en-US"]) <= 1
    assert all(
        any("가" <= character <= "힣" for character in str(case["goal_text"]))
        for case in cases
        if case["locale"] == "ko-KR"
    )
    assert all(
        any("a" <= character.casefold() <= "z" for character in str(case["goal_text"]))
        for case in cases
        if case["locale"] == "en-US"
    )

    covered_functions = {
        str(step["expected"]["function_id"])
        for case in cases
        for step in case["steps"]
        if step["expected"].get("function_id")
    }
    assert covered_functions == v3_function_ids
    assert len(covered_functions) == 239

    all_actions = Counter(
        str(step["expected"]["action"])
        for case in cases
        for step in case["steps"]
    )
    assert set(all_actions) == ALLOWED_ACTIONS
    assert all_actions["scroll_forward"] >= 70
    assert all_actions["back"] >= 70
    assert all_actions["no_click"] >= 170
    assert all_actions["stop"] >= 45

    assert {str(case["orientation"]) for case in cases} == {"portrait", "landscape"}
    assert len({str(case["device_model"]) for case in cases}) == 5
    assert len({str(case["user_state"]) for case in cases}) == 6
    assert {
        str(step["ui_surface"])
        for case in cases
        for step in case["steps"]
    } == {"screen", "drawer", "sheet", "dialog", "scroll_view", "webview"}
    assert len(
        {
            str(step["screen_state"])
            for case in cases
            for step in case["steps"]
        }
    ) >= 9
    assert sum(
        not str(element.get("label", "")) and bool(element.get("content_description"))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) >= 400
    assert sum(
        not bool(element.get("enabled", True))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) >= 500
    assert sum(
        bool(element.get("scrollable", False))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) >= 70

    for case in cases:
        intent_id = str(case["intent_id"])
        intent = intents[intent_id]
        route = [str(step["function_id"]) for step in intent["route"]]
        terminal_function = str(intent["terminal_function"])
        steps = list(case["steps"])
        assert case["source_kind"] == "fixed_independent"
        assert case["provenance"] == "independent_long_tail_authoring"
        assert case["tuning_allowed"] is True
        assert {"independent", "human_curated", "long_tail_v3", "tuning_allowed"} <= set(
            case["tags"]
        )
        assert len(steps) == 3
        assert steps[0]["expected"] == {
            "action": "click",
            "label": steps[0]["elements"][0]["label"],
            "function_id": route[0],
        }
        assert steps[1]["expected"]["action"] in {"click", "scroll_forward", "back"}
        assert steps[1]["expected"]["function_id"] == route[0]
        assert steps[-1]["expected"]["function_id"] == terminal_function

        # Goals are independently phrased conversations, never exact catalog
        # patterns or labels. Necessary domain terms may still occur naturally.
        normalized_goal = _normalize_exact(case["goal_text"])
        exact_catalog_phrases = {
            _normalize_exact(value) for value in intent.get("patterns", []) if str(value).strip()
        }
        terminal = functions[terminal_function]
        exact_catalog_phrases.update(
            _normalize_exact(value)
            for values in terminal["aliases"].values()
            for value in values
            if str(value).strip()
        )
        assert normalized_goal not in exact_catalog_phrases

        risky = (
            bool(terminal["state_changing"])
            or str(terminal["risk_level"]) == "high"
            or str(terminal["automation_policy"]) == "never_auto"
        )
        destination = steps[-1]
        destination_element = next(
            element for element in destination["elements"] if element["id"] == "destination"
        )
        if risky:
            assert destination["expected"]["action"] == "no_click"
            assert destination["expected"]["label"] is None
            assert destination_element["dangerous"] is True
            assert destination["stage"] == "safety_boundary"
        else:
            assert destination["expected"]["action"] == "stop"
            assert destination["expected"]["label"] == destination_element["label"]
            assert destination_element["dangerous"] is False

        for step in steps:
            assert step["expected"]["action"] in ALLOWED_ACTIONS
            if step["expected"]["action"] == "click":
                selected = _selected_element(step)
                assert selected is not None
                assert not bool(selected.get("dangerous", False))
                assert bool(selected.get("enabled", True))
                assert bool(selected.get("visible", True))
                assert bool(selected.get("clickable", True))

    # Exercise the same parser used by NavigationDbGym, not a test-only schema.
    gym_cases = load_fixed_cases(FIXTURE_PATH, split=SPLIT)
    assert len(gym_cases) == len(cases)
    assert sum(len(case.steps) for case in gym_cases) == 663
    assert {case.intent_id for case in gym_cases} == v3_intent_ids
    assert {
        step.expected_function
        for case in gym_cases
        for step in case.steps
        if step.expected_function
    } == v3_function_ids
    assert all(case.source_kind == "fixed_independent" for case in gym_cases)

    # Cross-check the independently authored IDs against the materialized
    # runtime database as well as the authoring module.
    runtime_payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    runtime_intents = {str(item["intent_id"]) for item in runtime_payload["intents"]}
    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "long-tail-v3.sqlite",
            CATALOG_PATH,
        )
        catalog.validate()
        assert v3_intent_ids <= runtime_intents
        assert all(catalog.function(function_id) is not None for function_id in v3_function_ids)
        assert catalog.stats()["function_count"] >= len(v3_function_ids)
        assert catalog.stats()["intent_count"] >= len(v3_intent_ids)

    print(
        "navigation long-tail v3 fixture checks ok: "
        f"cases={len(cases)} steps={sum(len(case['steps']) for case in cases)} "
        f"intents={len(v3_intent_ids)} functions={len(v3_function_ids)} "
        f"ko={locale_counts['ko-KR']} en={locale_counts['en-US']}"
    )


if __name__ == "__main__":
    main()
