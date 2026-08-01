from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
SCRIPTS = ROOT / "scripts"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from app.services.navigation_db_gym import load_fixed_cases  # noqa: E402
from navigation_catalog_v9_data import (  # noqa: E402
    REQUIRED_DOMAINS,
    V9_FUNCTIONS,
    V9_INTENTS,
)


FIXTURE_PATH = (
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-cross-domain-v9.json"
)
EXPECTED_SEAL = "7be8bcbde2d9a7f09370942837b3c299190e2f330eed8a55c6c1b4e52e3814d2"
EXPECTED_SURFACES = {
    "bottom_navigation",
    "navigation_drawer",
    "top_app_bar",
    "dashboard_grid",
    "search_results",
    "modal_sheet",
    "settings_list",
    "split_pane",
    "map_panel",
    "timeline",
    "tab_strip",
    "detail_panel",
}
EXPECTED_STATES = {
    "ready",
    "loading_complete",
    "offline_recovered",
    "overlay_dismissed",
    "empty_state_recovered",
    "permission_denied_recovered",
    "stale_cache_refreshed",
    "keyboard_hidden",
    "filter_applied",
    "signed_in",
    "role_selected",
    "scrolled",
}
EXPECTED_TRANSITIONS = {
    "section_gateway",
    "full_page_scroll",
    "wrong_branch_backtrack",
    "role_scoped_gateway",
}
APP_IDENTITY_FRAGMENTS = {
    "github",
    "meetup",
    "gofundme",
    "chargepoint",
    "myfitnesspal",
    "google translate",
    "samsara",
    "airbnb",
    "envoy",
    "john deere",
}


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _normalized(value: object) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", str(value)).casefold()
        if character.isalnum()
    )


def _words(value: object) -> tuple[str, ...]:
    return tuple(
        re.findall(
            r"[0-9a-z]+|[가-힣]+",
            unicodedata.normalize("NFKC", str(value)).casefold(),
        )
    )


def _protected_wording() -> dict[str, dict[str, tuple[str, str, str, int]]]:
    """Collect v9 runtime wording without consulting any prior sealed fixture."""

    result: dict[str, dict[str, tuple[str, str, str, int]]] = {
        "ko-KR": {},
        "en-US": {},
    }

    def add(locale: str, owner: str, kind: str, phrase: object) -> None:
        normalized = _normalized(phrase)
        if locale in result and normalized:
            result[locale].setdefault(
                normalized,
                (owner, kind, str(phrase), len(_words(phrase))),
            )

    for function in V9_FUNCTIONS:
        for locale, aliases in function["aliases"].items():
            for alias in aliases:
                add(str(locale), str(function["function_id"]), "alias", alias)
    for intent in V9_INTENTS:
        for locale, patterns in intent["patterns_by_locale"].items():
            for pattern in patterns:
                add(str(locale), str(intent["intent_id"]), "pattern", pattern)
        for rule in intent["goal_rules"]:
            locale = str(rule.get("v9_locale", ""))
            for field in ("all_of", "none_of"):
                for phrase in rule.get(field, []):
                    add(locale, str(intent["intent_id"]), f"rule_{field}", phrase)
    return result


def _assert_goal_is_independent(
    *,
    case_id: str,
    locale: str,
    goal_text: str,
    protected: dict[str, dict[str, tuple[str, str, str, int]]],
) -> float:
    """Reject copied labels, wrappers, and high-similarity rewrites.

    Single domain terms may overlap because a semantic holdout still has to say
    what the user means.  Copy detection applies to every exact phrase and to
    multi-token runtime phrases.  The 0.84 character-similarity ceiling is much
    stricter than the observed fixture maximum and catches near-copy edits.
    """

    goal_normalized = _normalized(goal_text)
    assert len(goal_normalized) >= 36, (case_id, "goal too short")
    maximum_similarity = 0.0
    maximum_source: tuple[str, str, str] | None = None
    for protected_normalized, (owner, kind, phrase, word_count) in protected[locale].items():
        assert goal_normalized != protected_normalized, (
            case_id,
            "exact runtime wording",
            owner,
            kind,
            phrase,
        )
        if word_count >= 2 and len(protected_normalized) >= 12:
            assert protected_normalized not in goal_normalized, (
                case_id,
                "runtime phrase wrapped by holdout goal",
                owner,
                kind,
                phrase,
            )
            assert goal_normalized not in protected_normalized, (
                case_id,
                "holdout goal wrapped by runtime phrase",
                owner,
                kind,
                phrase,
            )

        # Avoid expensive edit-distance work when the length ratio proves that
        # the pair cannot reach the near-copy threshold.
        length_upper_bound = (
            2 * min(len(goal_normalized), len(protected_normalized))
            / (len(goal_normalized) + len(protected_normalized))
        )
        if length_upper_bound < 0.84:
            continue
        similarity = SequenceMatcher(
            None,
            goal_normalized,
            protected_normalized,
            autojunk=False,
        ).ratio()
        if similarity > maximum_similarity:
            maximum_similarity = similarity
            maximum_source = (owner, kind, phrase)
    assert maximum_similarity < 0.84, (
        case_id,
        "near-copy runtime wording",
        maximum_similarity,
        maximum_source,
    )
    return maximum_similarity


def main() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["fixture_id"] == "independent-cross-domain-v9"
    assert payload["schema_version"] == "1.0"
    assert payload["catalog_target"] == "9.0.0"
    assert payload["split"] == "independent_cross_domain_v9"
    assert payload["source_kind"] == "fixed_independent"
    assert payload["tuning_allowed"] is False
    assert payload["frozen"] is True
    assert payload["catalog_derived"] is False
    assert payload["independent_accuracy_claim"] is True
    assert payload["created_on"] == "2026-07-30"

    independence = payload["independence"]
    assert independence == {
        "authoring_basis": "real-world outcome scenarios written independently from runtime wording",
        "prohibited_inputs": [
            "v9 aliases",
            "v9 goal patterns",
            "v9 goal-rule wording",
            "prior sealed fixtures",
        ],
        "label_access_policy": (
            "frozen non-tuning holdout; failures may be measured but not inspected for catalog edits"
        ),
        "ui_policy": (
            "synthetic app-agnostic surfaces; canonical labels appear only as UI choices, "
            "never as goal labels"
        ),
    }
    assert "prior sealed fixtures" in independence["prohibited_inputs"]

    coverage = payload["coverage_contract"]
    assert coverage == {
        "exact_cases": 368,
        "exact_steps": 1472,
        "exact_intents": 184,
        "exact_functions": 194,
        "exact_cases_per_intent": 2,
        "exact_cases_per_locale": {"ko-KR": 184, "en-US": 184},
        "minimum_steps_per_case": 4,
        "required_domains": sorted(REQUIRED_DOMAINS),
        "required_surfaces": [
            "bottom_navigation",
            "navigation_drawer",
            "top_app_bar",
            "dashboard_grid",
            "search_results",
            "modal_sheet",
            "settings_list",
            "split_pane",
            "map_panel",
            "timeline",
            "tab_strip",
            "detail_panel",
        ],
        "required_states": [
            "ready",
            "loading_complete",
            "offline_recovered",
            "overlay_dismissed",
            "empty_state_recovered",
            "permission_denied_recovered",
            "stale_cache_refreshed",
            "keyboard_hidden",
            "filter_applied",
            "signed_in",
            "role_selected",
            "scrolled",
        ],
        "required_transition_variants": [
            "section_gateway",
            "full_page_scroll",
            "wrong_branch_backtrack",
            "role_scoped_gateway",
        ],
    }
    assert payload["safety_contract"] == {
        "dangerous_expected_clicks": 0,
        "consequential_final_actions": ["stop", "no_click"],
        "final_press_owner": "user",
    }

    unsealed = copy.deepcopy(payload)
    seal = unsealed.pop("seal")
    assert seal == {
        "algorithm": "sha256",
        "scope": "entire_fixture_except_seal_canonical_json",
        "value": EXPECTED_SEAL,
    }
    actual_seal = hashlib.sha256(_canonical(unsealed)).hexdigest()
    assert actual_seal == EXPECTED_SEAL

    functions = {str(item["function_id"]): item for item in V9_FUNCTIONS}
    intents = {str(item["intent_id"]): item for item in V9_INTENTS}
    terminal_to_intent = {
        str(item["terminal_function"]): str(item["intent_id"])
        for item in V9_INTENTS
    }
    terminal_ids = set(terminal_to_intent)
    hub_ids = {str(item["function_id"]) for item in V9_FUNCTIONS if not item["terminal"]}
    assert len(functions) == 194
    assert len(intents) == 184
    assert len(terminal_ids) == 184
    assert len(hub_ids) == 10

    cases = list(payload["cases"])
    assert len(cases) == 368
    assert len({str(case["case_id"]) for case in cases}) == 368
    assert len({str(case["goal_text"]) for case in cases}) == 368
    assert all(len(case["steps"]) == 4 for case in cases)
    assert sum(len(case["steps"]) for case in cases) == 1472

    intent_counts = Counter(str(case["intent_id"]) for case in cases)
    locale_counts = Counter(str(case["locale"]) for case in cases)
    assert set(intent_counts) == set(intents)
    assert set(intent_counts.values()) == {2}
    assert locale_counts == {"ko-KR": 184, "en-US": 184}
    for intent_id in intents:
        assert {
            str(case["locale"])
            for case in cases
            if str(case["intent_id"]) == intent_id
        } == {"ko-KR", "en-US"}

    protected = _protected_wording()
    assert len(protected["ko-KR"]) >= 4_100
    assert len(protected["en-US"]) >= 4_250
    maximum_similarity = 0.0
    all_expected_functions: set[str] = set()
    all_surfaces: set[str] = set()
    all_states: set[str] = set()
    all_transition_tags: set[str] = set()
    all_user_states: set[str] = set()
    all_devices: set[str] = set()
    all_android_versions: set[str] = set()
    all_orientations: set[str] = set()
    all_packages: set[str] = set()
    dangerous_expected_clicks = 0
    dangerous_decoys = 0
    consequential_final_count = 0
    action_counts: Counter[str] = Counter()

    for case in cases:
        case_id = str(case["case_id"])
        locale = str(case["locale"])
        intent_id = str(case["intent_id"])
        goal_text = str(case["goal_text"])
        assert locale in {"ko-KR", "en-US"}
        assert intent_id in intents
        assert case["split"] == payload["split"]
        assert case["source_kind"] == "fixed_independent"
        assert case["tuning_allowed"] is False
        assert "fixed_independent" in case["tags"]
        assert "non_tuning" in case["tags"]
        assert "user_owned_final_action" in case["tags"]
        assert not any(fragment in goal_text.casefold() for fragment in APP_IDENTITY_FRAGMENTS)
        maximum_similarity = max(
            maximum_similarity,
            _assert_goal_is_independent(
                case_id=case_id,
                locale=locale,
                goal_text=goal_text,
                protected=protected,
            ),
        )

        steps = list(case["steps"])
        terminal_id = str(steps[-1]["expected"]["function_id"])
        assert terminal_id in terminal_ids
        assert terminal_to_intent[terminal_id] == intent_id
        domain = str(functions[terminal_id]["domain"])
        hub_id = f"{domain}.hub"
        assert [
            str(step["expected"]["function_id"]) for step in steps
        ] == [hub_id, hub_id, terminal_id, terminal_id]
        assert [str(step["stage"]) for step in steps[:3]] in (
            ["gateway", "gateway", "destination_candidate"],
            ["gateway", "recovery", "destination_candidate"],
        )
        assert steps[0]["expected"]["action"] == "click"
        assert steps[1]["expected"]["action"] in {"click", "scroll_forward", "back"}
        assert steps[2]["expected"]["action"] == "click"
        assert steps[-1]["expected"]["action"] in {"stop", "no_click"}
        assert steps[-1]["expected"]["label"] is None

        terminal = functions[terminal_id]
        consequential = bool(terminal["state_changing"]) or terminal["risk_level"] == "high"
        if consequential:
            consequential_final_count += 1
            assert steps[-1]["stage"] == "safety_boundary"
            assert steps[-1]["screen_state"] == "awaiting_user_confirmation"
            assert any(
                bool(element.get("dangerous", False))
                and element.get("decoy_kind") == "user_owned_final_action"
                for element in steps[-1]["elements"]
            )
        else:
            assert steps[-1]["stage"] == "destination"
            assert steps[-1]["screen_state"] == "destination_reached"

        for step in steps:
            expected = step["expected"]
            action = str(expected["action"])
            action_counts[action] += 1
            all_expected_functions.add(str(expected["function_id"]))
            all_surfaces.add(str(step["ui_surface"]))
            all_states.add(str(step["screen_state"]))
            for element in step["elements"]:
                dangerous_decoys += int(bool(element.get("dangerous", False)))
            if action == "click":
                matches = [
                    element
                    for element in step["elements"]
                    if element.get("label") == expected["label"]
                    and bool(element.get("clickable", True))
                    and bool(element.get("enabled", True))
                    and bool(element.get("visible", True))
                ]
                assert matches, (case_id, step["step_id"], expected)
                dangerous_expected_clicks += sum(
                    int(bool(element.get("dangerous", False))) for element in matches
                )
            else:
                assert expected["label"] is None

        all_transition_tags.update(EXPECTED_TRANSITIONS.intersection(case["tags"]))
        all_user_states.add(str(case["user_state"]))
        all_devices.add(str(case["device_model"]))
        all_android_versions.add(str(case["android_version"]))
        all_orientations.add(str(case["orientation"]))
        all_packages.add(str(case["app_package"]))

    assert all_expected_functions == set(functions)
    assert all_surfaces == EXPECTED_SURFACES
    assert EXPECTED_STATES <= all_states
    assert all_transition_tags == EXPECTED_TRANSITIONS
    assert len(all_user_states) == 10
    assert all_devices == {"compact-phone", "large-phone", "foldable-inner", "tablet-compact"}
    assert all_android_versions == {"12", "13", "14", "15", "16"}
    assert all_orientations == {"portrait", "landscape"}
    assert len(all_packages) == 10
    assert dangerous_expected_clicks == 0
    assert dangerous_decoys > 700
    assert consequential_final_count == 338
    assert action_counts == {
        "click": 920,
        "scroll_forward": 92,
        "back": 92,
        "stop": 184,
        "no_click": 184,
    }

    gym_cases = load_fixed_cases(FIXTURE_PATH, split=str(payload["split"]))
    assert len(gym_cases) == 368
    assert sum(len(case.steps) for case in gym_cases) == 1472
    assert all(case.source_kind == "fixed_independent" for case in gym_cases)
    assert all(case.tuning_allowed is False for case in gym_cases)
    assert {
        step.expected_function for case in gym_cases for step in case.steps
    } == set(functions)
    assert not any(
        element.dangerous and step.expected_action == "click" and element.label == step.expected_label
        for case in gym_cases
        for step in case.steps
        for element in step.elements
    )

    print(
        "navigation cross-domain v9 independent fixture checks ok: "
        f"cases={len(cases)} steps={sum(len(case['steps']) for case in cases)} "
        f"intents={len(intent_counts)} functions={len(all_expected_functions)} "
        f"locales={dict(sorted(locale_counts.items()))} surfaces={len(all_surfaces)} "
        f"states={len(all_states)} transitions={len(all_transition_tags)} "
        f"consequential_finals={consequential_final_count} "
        f"dangerous_expected_clicks={dangerous_expected_clicks} "
        f"max_runtime_wording_similarity={maximum_similarity:.6f} "
        f"sha256={actual_seal}"
    )


if __name__ == "__main__":
    main()
