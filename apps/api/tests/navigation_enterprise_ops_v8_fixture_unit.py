from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
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
from navigation_catalog_v8_data import (  # noqa: E402
    V8_FUNCTIONS,
    V8_INTENTS,
    validate_v8_data,
)


FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "independent-enterprise-ops-v8.json"
)
SPLIT = "independent_enterprise_ops_v8"
EXPECTED_SHA256 = "1ea2d3f769fb6084b829d40c8ec375f4abbdca7b3ed319cd637585f4911749ac"
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
    "split_pane",
    "confirmation",
    "carousel",
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
REQUIRED_SCREEN_STATES = {
    "auth_required",
    "confirmation_required",
    "destination_visible",
    "disabled",
    "empty_result",
    "error",
    "icon_only",
    "loading",
    "offline",
    "paginated_list",
    "partial_content",
    "permission_required",
    "ready",
    "stale_content",
    "webview_ready",
    "wrong_branch",
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
    """One-way post-authoring leakage corpus; never used to write the split."""

    phrases: set[str] = set()
    for source in (*V8_FUNCTIONS, *V8_INTENTS):
        phrases.update(_flatten_strings(source.get("aliases", ())))
        phrases.update(_flatten_strings(source.get("patterns", ())))
        for rule in source.get("goal_rules", ()):
            for key in ("all_of", "any_of", "none_of"):
                values = tuple(_flatten_strings(rule.get(key, ())))
                phrases.update(values)
                if values:
                    phrases.add(" ".join(values))
    return {phrase.strip() for phrase in phrases if phrase.strip()}


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
    stats = validate_v8_data()
    assert stats["functions"] == 146
    assert stats["terminal_functions"] == 138
    assert stats["intents"] == 138
    assert stats["domains"] == 8
    assert stats["state_changing"] == 82
    assert stats["high_risk"] == 126

    raw_fixture = FIXTURE_PATH.read_bytes()
    assert hashlib.sha256(raw_fixture).hexdigest() == EXPECTED_SHA256
    payload = json.loads(raw_fixture.decode("utf-8"))
    cases = list(payload["cases"])
    functions = {str(item["function_id"]): item for item in V8_FUNCTIONS}
    intents = {str(item["intent_id"]): item for item in V8_INTENTS}
    function_ids = set(functions)
    intent_ids = set(intents)

    assert payload["schema_version"] == 2
    assert payload["fixture_version"] == "8.0.0"
    assert payload["split"] == SPLIT
    assert payload["frozen"] is True
    assert payload["tuning_allowed"] is False
    assert payload["catalog_derived"] is False
    assert payload["source_kind"] == "fixed_independent"
    assert payload["independent_accuracy_claim"] is True
    assert payload["provenance"] == "independent_enterprise_ops_v8_authoring"
    assert payload["claims"] == {
        "independent_accuracy_evidence": True,
        "unseen_holdout": True,
        "production_device_accuracy": False,
    }
    independence = str(payload["authoring_policy"]["independence"])
    assert "identifiers, terminal routes, and safety metadata only" in independence
    assert "aliases, patterns, goal rules" in independence
    assert "prior sealed fixtures" in independence
    assert "no dangerous element is ever an expected click" in str(
        payload["authoring_policy"]["safety"]
    )
    assert "must not be used for tuning" in str(
        payload["authoring_policy"]["evaluation_use"]
    )
    assert payload["coverage_contract"] == {
        "v8_intents": 138,
        "v8_functions": 146,
        "exact_cases": 276,
        "exact_steps": 1104,
        "locale_cases_each": 138,
        "minimum_steps_per_case": 4,
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
            "split_pane",
            "confirmation",
            "carousel",
        ],
        "dangerous_expected_clicks": 0,
        "zero_shot": True,
    }

    step_count = sum(len(case["steps"]) for case in cases)
    assert len(cases) == 276
    assert step_count == 1104
    assert all(len(case["steps"]) == 4 for case in cases)
    assert len({str(case["case_id"]) for case in cases}) == 276

    normalized_goals = [
        (str(case["case_id"]), _normalize_exact(case["goal_text"]))
        for case in cases
    ]
    assert len({goal for _, goal in normalized_goals}) == 276
    max_pair_similarity = max(
        SequenceMatcher(None, left_goal, right_goal).ratio()
        for (_, left_goal), (_, right_goal) in combinations(normalized_goals, 2)
    )
    assert max_pair_similarity < 0.92

    cases_by_intent: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for case in cases:
        cases_by_intent[str(case["intent_id"])].append(case)
    assert set(cases_by_intent) == intent_ids
    assert all(len(items) == 2 for items in cases_by_intent.values())
    assert all(
        {str(item["locale"]) for item in items} == {"ko-KR", "en-US"}
        for items in cases_by_intent.values()
    )
    locale_counts = Counter(str(case["locale"]) for case in cases)
    assert locale_counts == {"ko-KR": 138, "en-US": 138}
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
    assert min(len(str(case["goal_text"])) for case in cases) >= 220

    covered_functions = {
        str(step["expected"]["function_id"])
        for case in cases
        for step in case["steps"]
        if step["expected"].get("function_id")
    }
    assert covered_functions == function_ids
    assert {function_id for function_id in covered_functions if function_id.endswith(".hub")} == {
        function_id for function_id in function_ids if function_id.endswith(".hub")
    }

    action_counts = Counter(
        str(step["expected"]["action"])
        for case in cases
        for step in case["steps"]
    )
    assert action_counts == {
        "click": 643,
        "no_click": 217,
        "stop": 184,
        "scroll_forward": 45,
        "back": 15,
    }
    assert set(action_counts) == ALLOWED_ACTIONS

    surfaces = {str(step["ui_surface"]) for case in cases for step in case["steps"]}
    screen_states = {
        str(step["screen_state"])
        for case in cases
        for step in case["steps"]
    }
    assert surfaces == REQUIRED_SURFACES
    assert screen_states == REQUIRED_SCREEN_STATES
    variant_counts = Counter(
        variant
        for case in cases
        for variant in REQUIRED_VARIANTS.intersection(case["tags"])
    )
    assert set(variant_counts) == REQUIRED_VARIANTS
    assert min(variant_counts.values()) == 15
    assert max(variant_counts.values()) == 16
    assert sum(variant_counts.values()) == 276
    assert sum(
        not str(element.get("label", ""))
        and bool(element.get("content_description"))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) == 16
    assert sum(
        not bool(element.get("enabled", True))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) == 1104
    assert sum(
        bool(element.get("scrollable", False))
        for case in cases
        for step in case["steps"]
        for element in step["elements"]
    ) == 45
    assert {str(case["orientation"]) for case in cases} == {"portrait", "landscape"}
    assert len({str(case["device_model"]) for case in cases}) == 6
    assert len({str(case["android_version"]) for case in cases}) == 5
    assert len({str(case["user_state"]) for case in cases}) == 8

    # Check goals against the v8 authoring corpus only after the split is frozen.
    # Necessary feature nouns can occur, but copied sentences, trivial wrappers,
    # long verbatim fragments, and high-overlap paraphrases are rejected.
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
        "찾아줘",
        "열어줘",
        "보여줘",
        "이동해줘",
        "찾아 줘",
        "열어 줘",
    )
    normalized_wrappers = {
        _normalize_exact(f"{prefix} {phrase}")
        for phrase in catalog_phrases
        for prefix in wrapper_prefixes
    }
    assert all(goal not in normalized_catalog for _, goal in normalized_goals)
    assert all(goal not in normalized_wrappers for _, goal in normalized_goals)

    catalog_token_sequences = {
        _tokens(phrase)
        for phrase in catalog_phrases
        if len(_tokens(phrase)) >= 7
    }
    leaked_fragments: list[tuple[str, str]] = []
    for case in cases:
        joined_goal = " ".join(_tokens(case["goal_text"]))
        for phrase_tokens in catalog_token_sequences:
            joined_phrase = " ".join(phrase_tokens)
            if joined_phrase and joined_phrase in joined_goal:
                leaked_fragments.append((str(case["case_id"]), joined_phrase))
    assert leaked_fragments == []

    normalized_nontrivial_phrases = {
        _normalize_exact(phrase)
        for phrase in catalog_phrases
        if len(_normalize_exact(phrase)) >= 24
    }
    near_copy_hits: list[tuple[str, str, float]] = []
    for case_id, goal in normalized_goals:
        for phrase in normalized_nontrivial_phrases:
            length_ratio = len(phrase) / len(goal)
            if not 0.45 <= length_ratio <= 1.8:
                continue
            similarity = SequenceMatcher(None, goal, phrase).ratio()
            if similarity >= 0.80:
                near_copy_hits.append((case_id, phrase, similarity))
    assert near_copy_hits == []

    dangerous_expected_clicks = 0
    dangerous_element_count = 0
    risky_final_count = 0
    safe_final_count = 0
    for case in cases:
        assert case["source_kind"] == "fixed_independent"
        assert case["provenance"] == "independent_enterprise_ops_v8_authoring"
        assert case["tuning_allowed"] is False
        assert case["frozen"] is True
        assert case["catalog_derived"] is False
        assert case["independent_accuracy_claim"] is True
        assert {
            "independent",
            "human_curated",
            "enterprise_ops_v8",
            "frozen_zero_shot",
            "risk_decoy",
        } <= set(case["tags"])
        assert len(REQUIRED_VARIANTS.intersection(case["tags"])) == 1

        intent = intents[str(case["intent_id"])]
        route = [str(item["function_id"]) for item in intent["route"]]
        terminal_id = str(intent["terminal_function"])
        terminal = functions[terminal_id]
        steps = list(case["steps"])
        assert len(route) == 2
        assert route[-1] == terminal_id
        assert {str(step["expected"]["function_id"]) for step in steps} == set(route)
        assert steps[-1]["expected"]["function_id"] == terminal_id
        assert steps[-1]["expected"]["action"] in {"stop", "no_click"}

        risky = (
            bool(terminal["state_changing"])
            or str(terminal["risk_level"]) == "high"
            or str(terminal["automation_policy"]) == "never_auto"
        )
        final_elements = {
            str(element.get("id", "")): element
            for element in steps[-1]["elements"]
        }
        if risky:
            risky_final_count += 1
            assert steps[-1]["stage"] == "safety_boundary"
            user_control = dict(final_elements["final-user-control"])
            assert user_control["dangerous"] is True
            assert user_control["semantic_function_id"] == terminal_id
        else:
            safe_final_count += 1
            assert steps[-1]["stage"] == "destination"
            assert "final-user-control" not in final_elements

        case_dangerous = 0
        for step in steps:
            expected = dict(step["expected"])
            assert expected["action"] in ALLOWED_ACTIONS
            dangerous = [
                element
                for element in step["elements"]
                if bool(element.get("dangerous", False))
            ]
            case_dangerous += len(dangerous)
            dangerous_element_count += len(dangerous)
            if expected["action"] == "click":
                selected = _expected_element(step)
                assert selected is not None
                dangerous_expected_clicks += int(bool(selected.get("dangerous", False)))
                assert not bool(selected.get("dangerous", False))
                assert bool(selected.get("enabled", True))
                assert bool(selected.get("visible", True))
                assert bool(selected.get("clickable", True))
            elif expected["action"] in {"scroll_forward", "back", "no_click"}:
                assert expected["label"] is None
        assert case_dangerous >= 4

    assert risky_final_count == 274
    assert safe_final_count == 2
    assert dangerous_expected_clicks == 0
    assert dangerous_element_count == 1378

    gym_cases = load_fixed_cases(FIXTURE_PATH, split=SPLIT)
    assert len(gym_cases) == 276
    assert sum(len(case.steps) for case in gym_cases) == 1104
    assert {case.case_id for case in gym_cases} == {
        str(case["case_id"]) for case in cases
    }
    assert Counter(case.intent_id for case in gym_cases) == Counter(
        {intent_id: 2 for intent_id in intent_ids}
    )
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
        "navigation enterprise ops v8 fixture checks ok: "
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
