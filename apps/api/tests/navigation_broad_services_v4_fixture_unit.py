from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_catalog_v4_data import (  # noqa: E402
    V4_FUNCTIONS,
    V4_INTENTS,
    merge_with_base,
    validate_v4_data,
)
from navigation_catalog_v5_data import V5_FUNCTIONS, V5_INTENTS  # noqa: E402

from app.services.navigation_db_gym import load_fixed_cases  # noqa: E402
from app.services.navigation_function_catalog import NavigationFunctionCatalog  # noqa: E402


CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "independent-broad-services-v4.json"
)
SPLIT = "independent_broad_services_v4"
ALLOWED_ACTIONS = {"click", "scroll_forward", "back", "stop", "no_click"}
REQUIRED_SURFACES = {
    "screen",
    "drawer",
    "bottom_sheet",
    "dialog",
    "webview",
    "scroll_view",
}
REQUIRED_RECOVERY_STATES = {
    "partial_content",
    "wrong_branch",
    "offline",
    "permission_required",
    "auth_required",
    "loading",
    "error",
}


def _normalize_exact(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _tokens(value: object) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"[0-9A-Za-z가-힣]+", unicodedata.normalize("NFKC", str(value)))
        if token
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / len(left.union(right))


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
    stats = validate_v4_data()
    assert stats["functions"] == 179
    assert stats["intents"] == 163

    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = list(payload["cases"])
    functions = {str(item["function_id"]): item for item in V4_FUNCTIONS}
    intents = {str(item["intent_id"]): item for item in V4_INTENTS}
    function_ids = set(functions)
    intent_ids = set(intents)

    assert payload["schema_version"] == 2
    assert payload["fixture_version"] == "4.0.0"
    assert payload["split"] == SPLIT
    assert payload["frozen"] is True
    assert payload["catalog_derived"] is False
    assert payload["provenance"] == "independent_broad_services_authoring"
    assert payload["tuning_allowed"] is True
    assert payload["coverage_contract"] == {
        "v4_intents": 163,
        "v4_functions": 179,
        "minimum_cases": 163,
        "minimum_steps": 520,
        "balanced_locales": ["ko-KR", "en-US"],
    }
    assert "must not be copied" in payload["authoring_policy"]["independence"]
    assert "final activation" in payload["authoring_policy"]["safety"]

    step_count = sum(len(case["steps"]) for case in cases)
    assert len(cases) == 163
    assert step_count == 652
    assert len({str(case["case_id"]) for case in cases}) == len(cases)
    assert len({_normalize_exact(case["goal_text"]) for case in cases}) == len(cases)
    assert {str(case["intent_id"]) for case in cases} == intent_ids
    assert Counter(str(case["intent_id"]) for case in cases).most_common(1)[0][1] == 1

    locale_counts = Counter(str(case["locale"]) for case in cases)
    assert locale_counts == {"ko-KR": 82, "en-US": 81}
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
    assert covered_functions == function_ids

    action_counts = Counter(
        str(step["expected"]["action"])
        for case in cases
        for step in case["steps"]
    )
    assert set(action_counts) == ALLOWED_ACTIONS
    assert action_counts["scroll_forward"] >= 20
    assert action_counts["back"] >= 40
    assert action_counts["stop"] >= 20
    assert action_counts["no_click"] >= 100

    surfaces = {
        str(step["ui_surface"])
        for case in cases
        for step in case["steps"]
    }
    states = {
        str(step["screen_state"])
        for case in cases
        for step in case["steps"]
    }
    assert REQUIRED_SURFACES <= surfaces
    assert REQUIRED_RECOVERY_STATES <= states
    assert {"confirmation_required", "sensitive_confirmation", "destination_visible"} <= states
    assert {str(case["orientation"]) for case in cases} == {"portrait", "landscape"}
    assert len({str(case["device_model"]) for case in cases}) == 6
    assert len({str(case["android_version"]) for case in cases}) == 5
    assert len({str(case["user_state"]) for case in cases}) == 8
    assert len(
        {
            str(step["activity_name"])
            for case in cases
            for step in case["steps"]
        }
    ) >= 10

    all_elements = [
        element
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ]
    assert sum(
        not str(element.get("label", "")) and bool(element.get("content_description"))
        for element in all_elements
    ) >= 500
    assert sum(not bool(element.get("enabled", True)) for element in all_elements) >= 600
    assert sum(not bool(element.get("visible", True)) for element in all_elements) >= 450
    assert sum(bool(element.get("checkable", False)) for element in all_elements) >= 450
    assert sum(bool(element.get("selected", False)) for element in all_elements) >= 450
    assert sum(bool(element.get("scrollable", False)) for element in all_elements) >= 20
    assert sum(element.get("decoy_kind") == "same_domain_collision" for element in all_elements) == 326

    dangerous_expected_clicks = 0
    for case in cases:
        assert case["source_kind"] == "fixed_independent"
        assert case["provenance"] == "independent_broad_services_authoring"
        assert case["tuning_allowed"] is True
        assert {
            "independent",
            "human_curated",
            "broad_services_v4",
            "tuning_allowed",
        } <= set(case["tags"])

        intent_id = str(case["intent_id"])
        intent = intents[intent_id]
        route = [str(step["function_id"]) for step in intent["route"]]
        terminal_id = str(intent["terminal_function"])
        terminal = functions[terminal_id]
        case_steps = list(case["steps"])
        assert len(route) == 2
        assert len(case_steps) == 4
        assert [
            str(step["expected"]["function_id"]) for step in case_steps
        ] == [route[0], route[0], terminal_id, terminal_id]
        assert case_steps[0]["expected"]["action"] == "click"
        assert case_steps[1]["expected"]["action"] in {
            "click",
            "scroll_forward",
            "back",
        }
        assert case_steps[2]["expected"]["action"] == "click"

        # The route menu deliberately contains two plausible choices from the
        # same domain, not arbitrary cross-domain noise.
        route_decoys = [
            element
            for element in case_steps[2]["elements"]
            if element.get("decoy_kind") == "same_domain_collision"
        ]
        assert len(route_decoys) == 2
        assert all(
            str(element["semantic_function_id"]) in function_ids
            and functions[str(element["semantic_function_id"])]["domain"] == terminal["domain"]
            and str(element["semantic_function_id"]) != terminal_id
            for element in route_decoys
        )

        # Goals must be real contextual requests rather than catalog labels,
        # descriptions, exact patterns, or trivial find/open wrappers.
        goal = str(case["goal_text"])
        normalized_goal = _normalize_exact(goal)
        assert len(goal) >= 80
        assert not re.match(
            r"^\s*(find|open|show me|go to|locate|navigate to)\b",
            goal,
            flags=re.IGNORECASE,
        )
        assert not re.match(r"^\s*(찾아|열어|보여|이동)", goal)
        if case["locale"] == "ko-KR":
            assert any(marker in goal for marker in ("하려", "해서", "필요", "싶", "해야", "때문"))
        else:
            assert any(marker in goal.casefold() for marker in (" need ", " want ", " so ", " preparing "))

        phrases = {
            str(value)
            for value in intent.get("patterns", [])
            if str(value).strip()
        }
        phrases.update(
            str(value)
            for values in terminal["aliases"].values()
            for value in values
            if str(value).strip()
        )
        phrases.update(
            {
                str(terminal["name_ko"]),
                str(terminal["name_en"]),
                str(terminal["description"]),
            }
        )
        normalized_phrases = {_normalize_exact(phrase) for phrase in phrases}
        assert normalized_goal not in normalized_phrases
        wrappers = {
            _normalize_exact(f"{prefix} {phrase}")
            for phrase in phrases
            for prefix in (
                "find",
                "open",
                "show me",
                "go to",
                "찾아줘",
                "열어줘",
                "보여줘",
                "이동해줘",
            )
        }
        assert normalized_goal not in wrappers
        goal_tokens = _tokens(goal)
        assert max((_jaccard(goal_tokens, _tokens(phrase)) for phrase in phrases), default=0.0) < 0.60

        destination = case_steps[-1]
        destination_element = next(
            element for element in destination["elements"] if element["id"] == "destination"
        )
        risky = (
            bool(terminal["state_changing"])
            or str(terminal["risk_level"]) == "high"
            or str(terminal["automation_policy"]) == "never_auto"
        )
        if risky:
            assert destination["stage"] == "safety_boundary"
            assert destination["expected"] == {
                "action": "no_click",
                "label": None,
                "function_id": terminal_id,
            }
            assert destination_element["dangerous"] is True
        else:
            assert destination["stage"] == "destination"
            assert destination["expected"]["action"] == "stop"
            assert destination["expected"]["label"] == destination_element["label"]
            assert destination_element["dangerous"] is False

        for step in case_steps:
            expected = dict(step["expected"])
            assert expected["action"] in ALLOWED_ACTIONS
            if expected["action"] == "click":
                selected = _selected_element(step)
                assert selected is not None
                dangerous_expected_clicks += int(bool(selected.get("dangerous", False)))
                assert not bool(selected.get("dangerous", False))
                assert bool(selected.get("enabled", True))
                assert bool(selected.get("visible", True))
                assert bool(selected.get("clickable", True))
    assert dangerous_expected_clicks == 0

    # Exercise the production fixture loader instead of accepting a test-only
    # JSON shape.
    gym_cases = load_fixed_cases(FIXTURE_PATH, split=SPLIT)
    assert len(gym_cases) == 163
    assert sum(len(case.steps) for case in gym_cases) == 652
    assert {case.intent_id for case in gym_cases} == intent_ids
    assert {
        step.expected_function
        for case in gym_cases
        for step in case.steps
        if step.expected_function
    } == function_ids
    assert all(case.source_kind == "fixed_independent" for case in gym_cases)

    # The frozen IDs must match both the v4 authoring module and the currently
    # materialized runtime catalog.  The materializer intentionally removes
    # v4 goal patterns and one-term rules that collide with a pre-v4 cue, so
    # compare runtime intents with the deterministic merge result rather than
    # the unfiltered authoring tuple.
    runtime_payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    runtime_functions = {
        str(item["function_id"]): item for item in runtime_payload["functions"]
    }
    runtime_intents = {
        str(item["intent_id"]): item for item in runtime_payload["intents"]
    }
    assert function_ids <= set(runtime_functions)
    assert intent_ids <= set(runtime_intents)
    assert all(runtime_functions[function_id] == functions[function_id] for function_id in function_ids)
    pre_v4_payload = dict(runtime_payload)
    later_function_ids = {str(item["function_id"]) for item in V5_FUNCTIONS}
    later_intent_ids = {str(item["intent_id"]) for item in V5_INTENTS}
    pre_v4_payload["functions"] = [
        item
        for item in runtime_payload["functions"]
        if str(item["function_id"]) not in function_ids | later_function_ids
    ]
    pre_v4_payload["intents"] = [
        item
        for item in runtime_payload["intents"]
        if str(item["intent_id"]) not in intent_ids | later_intent_ids
    ]
    pre_v4_payload.pop("official_sources_v4", None)
    pre_v4_payload.pop("official_sources_v5", None)
    expected_materialized = merge_with_base(pre_v4_payload)
    expected_intents = {
        str(item["intent_id"]): item for item in expected_materialized["intents"]
    }
    assert all(
        runtime_intents[intent_id] == expected_intents[intent_id]
        for intent_id in intent_ids
    )

    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "broad-services-v4.sqlite",
            CATALOG_PATH,
        )
        catalog.validate()
        assert all(catalog.function(function_id) is not None for function_id in function_ids)
        assert catalog.stats()["function_count"] >= 179
        assert catalog.stats()["intent_count"] >= 163

    print(
        "navigation broad-services v4 fixture checks ok: "
        f"cases={len(cases)} steps={step_count} "
        f"intents={len(intent_ids)} functions={len(function_ids)} "
        f"ko={locale_counts['ko-KR']} en={locale_counts['en-US']} "
        f"actions={dict(sorted(action_counts.items()))}"
    )


if __name__ == "__main__":
    main()
