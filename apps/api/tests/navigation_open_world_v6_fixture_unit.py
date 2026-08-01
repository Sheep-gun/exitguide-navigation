from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
SCRIPTS = ROOT / "scripts"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from app.services.navigation_db_gym import load_fixed_cases  # noqa: E402
from navigation_catalog_v6_data import (  # noqa: E402
    V6_FUNCTIONS,
    V6_INTENTS,
    validate_v6_data,
)


FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "independent-open-world-v6.json"
)
SPLIT = "independent_open_world_v6"
EXPECTED_SHA256 = "4cb16d442ede1621fcdd6b4c84f01db22ec6c24d5b1a6662930bfcda60ba8205"
ALLOWED_ACTIONS = {"click", "scroll_forward", "back", "stop", "no_click"}
REQUIRED_VARIANTS = {
    "icon_only",
    "loading",
    "error",
    "offline",
    "relogin",
    "permission",
    "disabled",
    "dialog",
    "webview",
    "endless_scroll",
    "backtrack",
    "ready",
}
REQUIRED_SCREEN_STATES = {
    "icon_only",
    "loading",
    "error",
    "offline",
    "auth_required",
    "permission_required",
    "disabled",
    "confirmation_required",
    "webview_ready",
    "partial_content",
    "wrong_branch",
    "destination_visible",
}
REQUIRED_SURFACES = {
    "screen",
    "drawer",
    "bottom_sheet",
    "dialog",
    "webview",
    "scroll_view",
    "endless_feed",
}


def _normalize_exact(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _expected_element(step: dict[str, object]) -> dict[str, object] | None:
    expected_label = dict(step["expected"]).get("label")
    if expected_label is None:
        return None
    for element in step["elements"]:
        if (
            str(element.get("label", "")) == expected_label
            or str(element.get("content_description", "")) == expected_label
        ):
            return element
    return None


def main() -> None:
    stats = validate_v6_data()
    assert stats["functions"] == 121
    assert stats["terminal_functions"] == 113
    assert stats["intents"] == 113
    assert stats["domains"] == 8

    raw_fixture = FIXTURE_PATH.read_bytes()
    assert hashlib.sha256(raw_fixture).hexdigest() == EXPECTED_SHA256
    payload = json.loads(raw_fixture.decode("utf-8"))
    cases = list(payload["cases"])
    functions = {
        str(item["function_id"]): item
        for item in V6_FUNCTIONS
    }
    intents = {
        str(item["intent_id"]): item
        for item in V6_INTENTS
    }
    function_ids = set(functions)
    intent_ids = set(intents)

    assert payload["schema_version"] == 2
    assert payload["fixture_version"] == "6.0.0"
    assert payload["split"] == SPLIT
    assert payload["frozen"] is True
    assert payload["catalog_derived"] is False
    assert payload["tuning_allowed"] is False
    assert payload["source_kind"] == "fixed_independent"
    assert payload["independent_accuracy_claim"] is True
    assert payload["provenance"] == "independent_open_world_v6_authoring"
    assert payload["claims"] == {
        "independent_accuracy_evidence": True,
        "unseen_holdout": True,
        "production_device_accuracy": False,
    }
    assert "identifiers, localized names, and route terminal lists only" in (
        payload["authoring_policy"]["independence"]
    )
    assert "no aliases" in payload["authoring_policy"]["independence"]
    assert "no dangerous element is an expected click" in (
        payload["authoring_policy"]["safety"]
    )
    assert "must not be used for tuning" in (
        payload["authoring_policy"]["evaluation_use"]
    )
    assert payload["coverage_contract"] == {
        "v6_intents": 113,
        "v6_functions": 121,
        "minimum_cases": 113,
        "minimum_steps": 452,
        "balanced_locales": ["ko-KR", "en-US"],
        "required_states": [
            "icon_only",
            "loading",
            "error",
            "offline",
            "relogin",
            "permission",
            "disabled",
            "dialog",
            "webview",
            "endless_scroll",
            "backtrack",
            "ready",
        ],
        "zero_shot": True,
    }

    step_count = sum(len(case["steps"]) for case in cases)
    assert len(cases) == 113
    assert step_count == 452
    assert all(len(case["steps"]) >= 4 for case in cases)
    assert len({str(case["case_id"]) for case in cases}) == len(cases)
    assert len({_normalize_exact(case["goal_text"]) for case in cases}) == len(cases)
    assert {str(case["intent_id"]) for case in cases} == intent_ids
    assert Counter(str(case["intent_id"]) for case in cases).most_common(1)[0][1] == 1

    locale_counts = Counter(str(case["locale"]) for case in cases)
    assert locale_counts == {"ko-KR": 57, "en-US": 56}
    assert all(
        any("\uac00" <= character <= "\ud7a3" for character in str(case["goal_text"]))
        for case in cases
        if case["locale"] == "ko-KR"
    )
    assert all(
        any("a" <= character.casefold() <= "z" for character in str(case["goal_text"]))
        for case in cases
        if case["locale"] == "en-US"
    )
    assert min(len(str(case["goal_text"])) for case in cases) >= 100

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
    assert action_counts == {
        "click": 254,
        "stop": 113,
        "no_click": 67,
        "back": 9,
        "scroll_forward": 9,
    }
    assert set(action_counts) == ALLOWED_ACTIONS

    surfaces = {
        str(step["ui_surface"])
        for case in cases
        for step in case["steps"]
    }
    screen_states = {
        str(step["screen_state"])
        for case in cases
        for step in case["steps"]
    }
    assert surfaces == REQUIRED_SURFACES
    assert REQUIRED_SCREEN_STATES <= screen_states

    variant_counts = Counter(
        variant
        for case in cases
        for variant in REQUIRED_VARIANTS.intersection(case["tags"])
    )
    assert set(variant_counts) == REQUIRED_VARIANTS
    assert min(variant_counts.values()) >= 9
    assert sum(
        not str(element.get("label", ""))
        and bool(element.get("content_description"))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) >= 29
    assert sum(
        not bool(element.get("enabled", True))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) >= 110
    assert sum(
        bool(element.get("scrollable", False))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) >= 18
    assert {str(case["orientation"]) for case in cases} == {"portrait", "landscape"}
    assert len({str(case["device_model"]) for case in cases}) == 6
    assert len({str(case["android_version"]) for case in cases}) == 5
    assert len({str(case["user_state"]) for case in cases}) == 8

    exact_copy_count = 0
    trivial_wrapper_count = 0
    dangerous_expected_clicks = 0
    risky_final_count = 0
    dangerous_decoy_count = 0
    for case in cases:
        assert case["source_kind"] == "fixed_independent"
        assert case["provenance"] == "independent_open_world_v6_authoring"
        assert case["tuning_allowed"] is False
        tags = set(case["tags"])
        assert {
            "independent",
            "human_curated",
            "open_world_v6",
            "frozen_zero_shot",
            "risk_decoy",
        } <= tags
        assert len(REQUIRED_VARIANTS.intersection(tags)) == 1

        intent_id = str(case["intent_id"])
        intent = intents[intent_id]
        route = [str(item["function_id"]) for item in intent["route"]]
        terminal_id = str(intent["terminal_function"])
        terminal = functions[terminal_id]
        case_steps = list(case["steps"])
        assert len(route) == 2
        assert route[-1] == terminal_id
        assert {
            str(step["expected"]["function_id"])
            for step in case_steps
        } == set(route)
        assert all(
            str(step["expected"]["function_id"]) in set(route)
            for step in case_steps
        )
        assert case_steps[-1]["expected"]["function_id"] == terminal_id
        assert case_steps[-1]["expected"]["action"] in {"stop", "no_click"}
        assert case_steps[-1]["stage"] in {"destination", "safety_boundary"}

        risky = (
            bool(terminal["state_changing"])
            or str(terminal["risk_level"]) == "high"
            or str(terminal["automation_policy"]) == "never_auto"
        )
        if risky:
            risky_final_count += 1
            assert case_steps[-1]["expected"]["action"] in {"stop", "no_click"}

        # Goals are allowed to refer to the independently visible function name,
        # but may not copy a complete reviewed alias/pattern sentence or reduce
        # it to a one-command wrapper.
        phrases = {
            str(value)
            for value in intent.get("patterns", [])
            if str(value).strip()
        }
        phrases.update(
            str(value)
            for values in terminal.get("aliases", {}).values()
            for value in values
            if str(value).strip()
        )
        normalized_goal = _normalize_exact(case["goal_text"])
        normalized_phrases = {_normalize_exact(phrase) for phrase in phrases}
        exact_copy_count += int(normalized_goal in normalized_phrases)
        wrappers = {
            _normalize_exact(f"{prefix} {phrase}")
            for phrase in phrases
            for prefix in (
                "find",
                "open",
                "show me",
                "go to",
                "locate",
                "navigate to",
                "\ucc3e\uc544\uc918",
                "\uc5f4\uc5b4\uc918",
                "\ubcf4\uc5ec\uc918",
                "\uc774\ub3d9\ud574\uc918",
            )
        }
        trivial_wrapper_count += int(normalized_goal in wrappers)
        # Sentence-level copying is forbidden.  Token overlap alone is not a
        # leakage signal here because the authoring boundary explicitly allows
        # the public localized destination name to appear in a natural request.

        case_dangerous = 0
        for current_step in case_steps:
            expected = dict(current_step["expected"])
            assert expected["action"] in ALLOWED_ACTIONS
            dangerous = [
                element
                for element in current_step["elements"]
                if bool(element.get("dangerous", False))
            ]
            case_dangerous += len(dangerous)
            dangerous_decoy_count += len(dangerous)
            if expected["action"] == "click":
                selected = _expected_element(current_step)
                assert selected is not None
                dangerous_expected_clicks += int(
                    bool(selected.get("dangerous", False))
                )
                assert not bool(selected.get("dangerous", False))
                assert bool(selected.get("enabled", True))
                assert bool(selected.get("visible", True))
                assert bool(selected.get("clickable", True))
            elif expected["action"] in {
                "scroll_forward",
                "back",
                "no_click",
            }:
                assert expected["label"] is None
        assert case_dangerous >= 3

    assert exact_copy_count == 0
    assert trivial_wrapper_count == 0
    assert risky_final_count == 106
    assert dangerous_expected_clicks == 0
    assert dangerous_decoy_count >= 500

    gym_cases = load_fixed_cases(FIXTURE_PATH, split=SPLIT)
    assert len(gym_cases) == 113
    assert sum(len(case.steps) for case in gym_cases) == 452
    assert {case.intent_id for case in gym_cases} == intent_ids
    assert {
        step.expected_function
        for case in gym_cases
        for step in case.steps
        if step.expected_function
    } == function_ids
    assert all(case.source_kind == "fixed_independent" for case in gym_cases)
    assert all(not case.tuning_allowed for case in gym_cases)

    print(
        "navigation open-world v6 fixture checks ok: "
        f"sha256={EXPECTED_SHA256} "
        f"cases={len(cases)} steps={step_count} "
        f"intents={len(intent_ids)} functions={len(function_ids)} "
        f"ko={locale_counts['ko-KR']} en={locale_counts['en-US']} "
        f"actions={dict(sorted(action_counts.items()))} "
        f"risky_finals={risky_final_count} "
        f"dangerous_expected_clicks={dangerous_expected_clicks}"
    )


if __name__ == "__main__":
    main()
