from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
SCRIPTS = ROOT / "scripts"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from app.services.navigation_db_gym import load_fixed_cases  # noqa: E402
from navigation_catalog_v7_data import (  # noqa: E402
    V7_FUNCTIONS,
    V7_INTENTS,
    validate_v7_data,
)


FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "independent-long-tail-v7.json"
)
SPLIT = "independent_long_tail_v7"
EXPECTED_SHA256 = "c2212884d90fa24aaa01756928261d8c58d15c48060b69f0098d2c68150460e7"
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
    "empty_result",
    "stale_content",
    "paginated_list",
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
    "ready",
    "empty_result",
    "stale_content",
    "paginated_list",
    "destination_visible",
}
REQUIRED_SURFACES = {
    "auth_sheet",
    "bottom_sheet",
    "card_stack",
    "carousel",
    "confirmation_dialog",
    "detail_sheet",
    "dialog",
    "drawer",
    "endless_feed",
    "grid",
    "list",
    "overlay",
    "screen",
    "scroll_view",
    "split_pane",
    "system_dialog",
    "tab_grid",
    "webview",
}


def _normalize_exact(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _tokens(value: object) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return tuple(re.findall(r"[0-9a-z\uac00-\ud7a3]+", normalized))


def _flatten_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        if value.strip():
            yield value
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from _flatten_strings(nested)
        return
    if isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _flatten_strings(nested)


def _catalog_sentence_corpus() -> set[str]:
    """Build a leakage corpus for testing, never for fixture authoring."""

    phrases: set[str] = set()
    for source in (*V7_FUNCTIONS, *V7_INTENTS):
        phrases.update(_flatten_strings(source.get("aliases", ())))
        phrases.update(_flatten_strings(source.get("patterns", ())))
        for rule in source.get("goal_rules", ()):
            for key in ("all_of", "any_of", "none_of"):
                values = tuple(_flatten_strings(rule.get(key, ())))
                phrases.update(values)
                if values:
                    phrases.add(" ".join(values))
    return {phrase for phrase in phrases if phrase.strip()}


def _expected_element(step: dict[str, object]) -> dict[str, object] | None:
    expected_label = dict(step["expected"]).get("label")
    if expected_label is None:
        return None
    for raw_element in step["elements"]:
        element = dict(raw_element)
        if (
            str(element.get("label", "")) == expected_label
            or str(element.get("content_description", "")) == expected_label
        ):
            return element
    return None


def main() -> None:
    stats = validate_v7_data()
    assert stats["functions"] == 128
    assert stats["terminal_functions"] == 120
    assert stats["intents"] == 120
    assert stats["domains"] == 8
    assert set(stats["domain_terminal_counts"].values()) == {15}
    assert stats["state_changing"] == 78
    assert stats["high_risk"] == 95

    raw_fixture = FIXTURE_PATH.read_bytes()
    assert hashlib.sha256(raw_fixture).hexdigest() == EXPECTED_SHA256
    payload = json.loads(raw_fixture.decode("utf-8"))
    cases = list(payload["cases"])
    functions = {
        str(item["function_id"]): item
        for item in V7_FUNCTIONS
    }
    intents = {
        str(item["intent_id"]): item
        for item in V7_INTENTS
    }
    function_ids = set(functions)
    intent_ids = set(intents)

    assert payload["schema_version"] == 2
    assert payload["fixture_version"] == "7.0.0"
    assert payload["split"] == SPLIT
    assert payload["frozen"] is True
    assert payload["tuning_allowed"] is False
    assert payload["catalog_derived"] is False
    assert payload["independent_accuracy_claim"] is True
    assert payload["source_kind"] == "fixed_independent"
    assert payload["provenance"] == "independent_long_tail_v7_authoring"
    assert payload["claims"] == {
        "independent_accuracy_evidence": True,
        "unseen_holdout": True,
        "production_device_accuracy": False,
    }
    independence_policy = str(payload["authoring_policy"]["independence"])
    assert "identifiers" in independence_policy
    assert "safety metadata" in independence_policy
    assert "no aliases, patterns, goal rules" in independence_policy
    assert "no dangerous element is ever an expected click" in str(
        payload["authoring_policy"]["safety"]
    )
    assert "must not be used for tuning" in str(
        payload["authoring_policy"]["evaluation_use"]
    )
    assert payload["coverage_contract"] == {
        "v7_intents": 120,
        "v7_functions": 128,
        "exact_cases": 120,
        "minimum_steps": 480,
        "balanced_locales": {"ko-KR": 60, "en-US": 60},
        "required_variants": [
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
            "empty_result",
            "stale_content",
            "paginated_list",
        ],
        "dangerous_expected_clicks": 0,
        "zero_shot": True,
    }

    step_count = sum(len(case["steps"]) for case in cases)
    assert len(cases) == 120
    assert step_count == 480
    assert all(len(case["steps"]) == 4 for case in cases)
    assert len({str(case["case_id"]) for case in cases}) == len(cases)

    # Treat each natural-language goal as one evaluation sentence.  Exact and
    # near duplicate sentences would inflate apparent accuracy, so both are
    # rejected before this frozen split can be reported.
    normalized_goals = [
        (str(case["case_id"]), _normalize_exact(case["goal_text"]))
        for case in cases
    ]
    assert len({goal for _, goal in normalized_goals}) == len(cases)
    max_pair_similarity = max(
        SequenceMatcher(None, left_goal, right_goal).ratio()
        for (_, left_goal), (_, right_goal) in combinations(normalized_goals, 2)
    )
    assert max_pair_similarity < 0.90

    case_intent_counts = Counter(str(case["intent_id"]) for case in cases)
    assert set(case_intent_counts) == intent_ids
    assert set(case_intent_counts.values()) == {1}

    locale_counts = Counter(str(case["locale"]) for case in cases)
    assert locale_counts == {"ko-KR": 60, "en-US": 60}
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
    assert min(len(str(case["goal_text"])) for case in cases) >= 80

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
        "click": 264,
        "stop": 120,
        "no_click": 64,
        "scroll_forward": 16,
        "back": 16,
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
    assert screen_states == REQUIRED_SCREEN_STATES
    assert len(surfaces) >= 12
    assert len(screen_states) >= 12

    variant_counts = Counter(
        variant
        for case in cases
        for variant in REQUIRED_VARIANTS.intersection(case["tags"])
    )
    assert set(variant_counts) == REQUIRED_VARIANTS
    assert set(variant_counts.values()) == {8}
    assert sum(
        not str(element.get("label", ""))
        and bool(element.get("content_description"))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) >= 118
    assert sum(
        not bool(element.get("enabled", True))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) >= 128
    assert sum(
        bool(element.get("scrollable", False))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) >= 16
    assert {str(case["orientation"]) for case in cases} == {
        "portrait",
        "landscape",
    }
    assert len({str(case["device_model"]) for case in cases}) == 6
    assert len({str(case["android_version"]) for case in cases}) == 5
    assert len({str(case["user_state"]) for case in cases}) == 8

    # This corpus is consulted only after authoring, as a one-way leakage
    # detector.  It rejects copied sentences, trivial imperative wrappers, and
    # long verbatim catalog fragments while still permitting necessary public
    # feature concepts to appear naturally in a request.
    catalog_phrases = _catalog_sentence_corpus()
    normalized_catalog = {_normalize_exact(phrase) for phrase in catalog_phrases}
    wrapper_prefixes = (
        "find",
        "open",
        "show me",
        "go to",
        "locate",
        "navigate to",
        "please find",
        "please open",
        "\ucc3e\uc544\uc918",
        "\uc5f4\uc5b4\uc918",
        "\ubcf4\uc5ec\uc918",
        "\uc774\ub3d9\ud574\uc918",
        "\ucc3e\uc544 \uc918",
        "\uc5f4\uc5b4 \uc918",
    )
    normalized_wrappers = {
        _normalize_exact(f"{prefix} {phrase}")
        for phrase in catalog_phrases
        for prefix in wrapper_prefixes
    }
    long_catalog_fragments = {
        _tokens(phrase)
        for phrase in catalog_phrases
        if len(_tokens(phrase)) >= 8
    }
    assert all(goal not in normalized_catalog for _, goal in normalized_goals)
    assert all(goal not in normalized_wrappers for _, goal in normalized_goals)
    leaked_long_fragments: list[tuple[str, str]] = []
    for case in cases:
        goal_words = _tokens(case["goal_text"])
        joined_goal = " ".join(goal_words)
        for catalog_words in long_catalog_fragments:
            if len(catalog_words) > len(goal_words):
                continue
            joined_catalog = " ".join(catalog_words)
            if joined_catalog in joined_goal:
                leaked_long_fragments.append(
                    (str(case["case_id"]), joined_catalog)
                )
    assert leaked_long_fragments == []

    dangerous_expected_clicks = 0
    risky_final_count = 0
    dangerous_decoy_count = 0
    for case in cases:
        assert case["source_kind"] == "fixed_independent"
        assert case["provenance"] == "independent_long_tail_v7_authoring"
        assert case["tuning_allowed"] is False
        assert case["frozen"] is True
        assert case["catalog_derived"] is False
        assert case["independent_accuracy_claim"] is True
        tags = set(case["tags"])
        assert {
            "independent",
            "human_curated",
            "long_tail_v7",
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
        assert case_steps[-1]["expected"]["function_id"] == terminal_id
        assert case_steps[-1]["expected"]["action"] in {"stop", "no_click"}

        risky = (
            bool(terminal["state_changing"])
            or str(terminal["risk_level"]) == "high"
            or str(terminal["automation_policy"]) == "never_auto"
        )
        final_elements = {
            str(element.get("id", "")): element
            for element in case_steps[-1]["elements"]
        }
        if risky:
            risky_final_count += 1
            assert case_steps[-1]["stage"] == "safety_boundary"
            final_user_control = dict(final_elements["final-user-control"])
            assert final_user_control["dangerous"] is True
            assert final_user_control["semantic_function_id"] == terminal_id
            assert case_steps[-1]["expected"]["action"] in {"stop", "no_click"}
        else:
            assert case_steps[-1]["stage"] == "destination"
            assert "final-user-control" not in final_elements

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
        assert case_dangerous >= 4

    assert risky_final_count == 110
    assert dangerous_expected_clicks == 0
    assert dangerous_decoy_count >= 590

    gym_cases = load_fixed_cases(FIXTURE_PATH, split=SPLIT)
    assert len(gym_cases) == 120
    assert sum(len(case.steps) for case in gym_cases) == 480
    assert {case.case_id for case in gym_cases} == {
        str(case["case_id"])
        for case in cases
    }
    assert {case.intent_id for case in gym_cases} == intent_ids
    assert {
        step.expected_function
        for case in gym_cases
        for step in case.steps
        if step.expected_function
    } == function_ids
    assert Counter(case.locale for case in gym_cases) == locale_counts
    assert all(case.split == SPLIT for case in gym_cases)
    assert all(case.source_kind == "fixed_independent" for case in gym_cases)
    assert all(not case.tuning_allowed for case in gym_cases)
    assert all("frozen_zero_shot" in case.tags for case in gym_cases)

    print(
        "navigation long-tail v7 fixture checks ok: "
        f"sha256={EXPECTED_SHA256} "
        f"cases={len(cases)} steps={step_count} "
        f"intents={len(intent_ids)} functions={len(function_ids)} "
        f"ko={locale_counts['ko-KR']} en={locale_counts['en-US']} "
        f"surfaces={len(surfaces)} states={len(screen_states)} "
        f"actions={dict(sorted(action_counts.items()))} "
        f"risky_finals={risky_final_count} "
        f"dangerous_expected_clicks={dangerous_expected_clicks}"
    )


if __name__ == "__main__":
    main()
