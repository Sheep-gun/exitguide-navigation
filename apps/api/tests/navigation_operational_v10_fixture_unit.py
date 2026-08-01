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
from navigation_catalog_v10_data import (  # noqa: E402
    REQUIRED_DOMAINS,
    V10_FUNCTIONS,
    V10_INTENTS,
)


FIXTURE_PATH = (
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-operational-v10.json"
)
EXPECTED_SEAL = "87742e2f3613b9e31e962de25a0ae1a64e89051de0cdac4946b94ca5e83fa849"
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
PROHIBITED_BRAND_FRAGMENTS = {
    "doorloop",
    "propertyware",
    "odoo",
    "maximo",
    "ibm",
    "benchling",
    "google classroom",
    "clio",
    "toast",
    "circlecare",
    "tesla",
    "enphase",
    "familysearch",
    "sap ariba",
    "oracle",
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
    """Read only v10 runtime language; never consult another holdout fixture."""

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

    for function in V10_FUNCTIONS:
        for locale, aliases in function["aliases"].items():
            for alias in aliases:
                add(str(locale), str(function["function_id"]), "alias", alias)
    for intent in V10_INTENTS:
        for locale, patterns in intent["patterns_by_locale"].items():
            for pattern in patterns:
                add(str(locale), str(intent["intent_id"]), "pattern", pattern)
        for rule in intent["goal_rules"]:
            locale = str(rule.get("v10_locale", ""))
            for field in ("all_of", "none_of"):
                for phrase in rule.get(field, []):
                    add(locale, str(intent["intent_id"]), f"rule_{field}", phrase)
    return result


def _source_violation(
    goal_normalized: str,
    protected_normalized: str,
    *,
    protected_word_count: int,
) -> tuple[str | None, float]:
    if goal_normalized == protected_normalized:
        return "exact", 1.0
    if protected_word_count >= 2 and len(protected_normalized) >= 12:
        if protected_normalized in goal_normalized:
            return "wrapped_runtime_phrase", 1.0
        if goal_normalized in protected_normalized:
            return "runtime_phrase_wraps_goal", 1.0

    length_upper_bound = (
        2 * min(len(goal_normalized), len(protected_normalized))
        / (len(goal_normalized) + len(protected_normalized))
    )
    if length_upper_bound < 0.84:
        return None, 0.0
    similarity = SequenceMatcher(
        None,
        goal_normalized,
        protected_normalized,
        autojunk=False,
    ).ratio()
    if similarity >= 0.84:
        return "near_copy", similarity
    return None, similarity


def _assert_goal_is_independent(
    *,
    case_id: str,
    locale: str,
    goal_text: str,
    protected: dict[str, dict[str, tuple[str, str, str, int]]],
) -> float:
    goal_normalized = _normalized(goal_text)
    assert len(goal_normalized) >= 48, (case_id, "goal too short")
    maximum_similarity = 0.0
    maximum_source: tuple[str, str, str] | None = None
    for protected_normalized, (owner, kind, phrase, word_count) in protected[locale].items():
        violation, similarity = _source_violation(
            goal_normalized,
            protected_normalized,
            protected_word_count=word_count,
        )
        if similarity > maximum_similarity:
            maximum_similarity = similarity
            maximum_source = (owner, kind, phrase)
        assert violation is None, (
            case_id,
            violation,
            owner,
            kind,
            phrase,
            similarity,
        )
    assert maximum_similarity < 0.84, (
        case_id,
        "near-copy runtime wording",
        maximum_similarity,
        maximum_source,
    )
    return maximum_similarity


def _assert_copy_guard_self_tests(
    protected: dict[str, dict[str, tuple[str, str, str, int]]]
) -> None:
    entries = [
        (normalized, owner, kind, phrase, count)
        for locale in ("ko-KR", "en-US")
        for normalized, (owner, kind, phrase, count) in protected[locale].items()
    ]
    by_kind: dict[str, tuple[str, str, str, int]] = {}
    for wanted in ("alias", "pattern", "rule_all_of", "rule_none_of"):
        candidates = [entry for entry in entries if entry[2] == wanted and entry[4] >= 2]
        assert candidates, wanted
        normalized, _owner, kind, phrase, count = max(
            candidates,
            key=lambda entry: len(entry[0]),
        )
        by_kind[wanted] = (normalized, kind, phrase, count)

    for normalized, kind, _phrase, count in by_kind.values():
        violation, _ = _source_violation(
            normalized,
            normalized,
            protected_word_count=count,
        )
        assert violation == "exact", kind

    pattern_normalized, _kind, _phrase, pattern_count = by_kind["pattern"]
    wrapped = _normalized(f"Please inspect {pattern_normalized} but stop before acting")
    violation, _ = _source_violation(
        wrapped,
        pattern_normalized,
        protected_word_count=pattern_count,
    )
    assert violation == "wrapped_runtime_phrase"

    rule_normalized, _kind, _phrase, rule_count = by_kind["rule_all_of"]
    replacement = "x" if not rule_normalized.endswith("x") else "y"
    near_copy = rule_normalized[:-1] + replacement
    violation, similarity = _source_violation(
        near_copy,
        rule_normalized,
        protected_word_count=rule_count,
    )
    assert violation == "near_copy", (violation, similarity)

    one_word_candidates = [entry for entry in entries if entry[4] == 1 and len(entry[0]) >= 5]
    assert one_word_candidates
    single_normalized, _owner, _kind, _phrase, single_count = one_word_candidates[0]
    independent_sentence = _normalized(
        f"This scenario uses {single_normalized} as one necessary semantic word "
        "inside a separately authored operational outcome with a review boundary"
    )
    violation, _ = _source_violation(
        independent_sentence,
        single_normalized,
        protected_word_count=single_count,
    )
    assert violation is None


def main() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["fixture_id"] == "independent-operational-v10"
    assert payload["schema_version"] == "1.0"
    assert payload["catalog_target"] == "10.0.0"
    assert payload["split"] == "independent_operational_v10"
    assert payload["source_kind"] == "fixed_independent"
    assert payload["tuning_allowed"] is False
    assert payload["frozen"] is True
    assert payload["catalog_derived"] is False
    assert payload["independent_accuracy_claim"] is True
    assert payload["created_on"] == "2026-07-30"

    assert payload["independence"] == {
        "authoring_basis": (
            "operational outcome scenarios independently paraphrased from the v10 domain contract"
        ),
        "prohibited_inputs": [
            "v10 aliases",
            "v10 goal patterns",
            "v10 goal-rule wording",
            "prior sealed fixtures",
        ],
        "label_access_policy": (
            "frozen non-tuning holdout; failures may be measured but not inspected for catalog edits"
        ),
        "ui_policy": (
            "synthetic app-agnostic Android surfaces; canonical destination wording is allowed "
            "only as a visible UI choice"
        ),
    }

    coverage = payload["coverage_contract"]
    assert coverage == {
        "exact_cases": 218,
        "exact_steps": 872,
        "exact_intents": 218,
        "exact_functions": 230,
        "exact_cases_per_intent": 1,
        "exact_cases_per_locale": {"ko-KR": 109, "en-US": 109},
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
        "minimum_recovery_probes": 436,
    }
    assert payload["safety_contract"] == {
        "dangerous_expected_clicks": 0,
        "terminal_risk_level": "high",
        "terminal_automation_policy": "never_auto",
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

    functions = {str(item["function_id"]): item for item in V10_FUNCTIONS}
    intents = {str(item["intent_id"]): item for item in V10_INTENTS}
    terminal_to_intent = {
        str(item["terminal_function"]): str(item["intent_id"])
        for item in V10_INTENTS
    }
    terminal_ids = set(terminal_to_intent)
    hub_ids = {str(item["function_id"]) for item in V10_FUNCTIONS if not item["terminal"]}
    assert len(functions) == 230
    assert len(intents) == 218
    assert len(terminal_ids) == 218
    assert len(hub_ids) == 12
    assert all(functions[function_id]["risk_level"] == "high" for function_id in terminal_ids)
    assert all(
        functions[function_id]["automation_policy"] == "never_auto"
        for function_id in terminal_ids
    )
    assert all(
        functions[function_id]["stop_policy"] == "before_action"
        for function_id in terminal_ids
    )

    protected = _protected_wording()
    assert len(protected["ko-KR"]) >= 4_800
    assert len(protected["en-US"]) >= 4_800
    _assert_copy_guard_self_tests(protected)

    cases = list(payload["cases"])
    assert len(cases) == 218
    assert len({str(case["case_id"]) for case in cases}) == 218
    assert len({str(case["goal_text"]) for case in cases}) == 218
    assert all(len(case["steps"]) == 4 for case in cases)
    assert sum(len(case["steps"]) for case in cases) == 872

    intent_counts = Counter(str(case["intent_id"]) for case in cases)
    locale_counts = Counter(str(case["locale"]) for case in cases)
    assert intent_counts == Counter({intent_id: 1 for intent_id in intents})
    assert locale_counts == {"ko-KR": 109, "en-US": 109}

    maximum_similarity = 0.0
    all_expected_functions: set[str] = set()
    all_surfaces: set[str] = set()
    all_states: set[str] = set()
    all_transitions: set[str] = set()
    all_user_states: set[str] = set()
    all_devices: set[str] = set()
    all_android_versions: set[str] = set()
    all_orientations: set[str] = set()
    all_packages: set[str] = set()
    recovery_probes = 0
    role_inversion_probes = 0
    homonym_decoys = 0
    dangerous_expected_clicks = 0
    dangerous_final_actions = 0
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
        assert {
            "fixed_independent",
            "non_tuning",
            "user_owned_final_action",
            "role_inversion",
            "homonym_decoy",
            "recovery_probe",
        } <= set(case["tags"])
        assert not any(fragment in goal_text.casefold() for fragment in PROHIBITED_BRAND_FRAGMENTS)
        assert not re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", goal_text.casefold())
        assert not re.search(r"\b(?:\+?\d[\d -]{8,}\d)\b", goal_text)
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
        assert [str(step["expected"]["function_id"]) for step in steps] == [
            hub_id,
            hub_id,
            terminal_id,
            terminal_id,
        ]
        assert steps[0]["stage"] == "gateway"
        assert steps[1]["stage"] in {"gateway", "recovery"}
        assert steps[2]["stage"] == "destination_candidate"
        assert steps[3]["stage"] == "safety_boundary"
        assert steps[0]["expected"]["action"] == "click"
        assert steps[1]["expected"]["action"] in {"click", "scroll_forward", "back"}
        assert steps[2]["expected"]["action"] == "click"
        assert steps[3]["expected"]["action"] in {"stop", "no_click"}
        assert steps[3]["expected"]["label"] is None
        assert steps[3]["screen_state"] == "awaiting_user_confirmation"
        assert any(
            bool(element.get("dangerous", False))
            and element.get("decoy_kind") == "user_owned_final_action"
            for element in steps[3]["elements"]
        )

        for step in steps:
            expected = step["expected"]
            action = str(expected["action"])
            action_counts[action] += 1
            all_expected_functions.add(str(expected["function_id"]))
            all_surfaces.add(str(step["ui_surface"]))
            all_states.add(str(step["screen_state"]))
            for element in step["elements"]:
                decoy_kind = str(element.get("decoy_kind", ""))
                recovery_probes += int(decoy_kind in {
                    "permission_denied_recovery",
                    "stale_or_offline_recovery",
                })
                role_inversion_probes += int(decoy_kind.startswith("role_inversion"))
                homonym_decoys += int(decoy_kind == "homonym_decoy")
                dangerous_final_actions += int(
                    bool(element.get("dangerous", False))
                    and decoy_kind == "user_owned_final_action"
                )
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

        all_transitions.update(EXPECTED_TRANSITIONS.intersection(case["tags"]))
        all_user_states.add(str(case["user_state"]))
        all_devices.add(str(case["device_model"]))
        all_android_versions.add(str(case["android_version"]))
        all_orientations.add(str(case["orientation"]))
        all_packages.add(str(case["app_package"]))

    assert all_expected_functions == set(functions)
    assert all_surfaces == EXPECTED_SURFACES
    assert EXPECTED_STATES <= all_states
    assert all_transitions == EXPECTED_TRANSITIONS
    assert len(all_user_states) == 12
    assert all_devices == {"compact-phone", "large-phone", "foldable-inner", "tablet-compact"}
    assert all_android_versions == {"12", "13", "14", "15", "16"}
    assert all_orientations == {"portrait", "landscape"}
    assert len(all_packages) == 12
    assert recovery_probes >= 436
    assert role_inversion_probes >= 436
    assert homonym_decoys == 218
    assert dangerous_final_actions == 218
    assert dangerous_expected_clicks == 0
    assert action_counts == {
        "click": 545,
        "scroll_forward": 55,
        "back": 54,
        "stop": 109,
        "no_click": 109,
    }

    gym_cases = load_fixed_cases(FIXTURE_PATH, split=str(payload["split"]))
    assert len(gym_cases) == 218
    assert sum(len(case.steps) for case in gym_cases) == 872
    assert all(case.source_kind == "fixed_independent" for case in gym_cases)
    assert all(case.tuning_allowed is False for case in gym_cases)
    assert {
        step.expected_function for case in gym_cases for step in case.steps
    } == set(functions)
    assert not any(
        element.dangerous
        and step.expected_action == "click"
        and element.label == step.expected_label
        for case in gym_cases
        for step in case.steps
        for element in step.elements
    )

    print(
        "navigation operational v10 independent fixture checks ok: "
        f"cases={len(cases)} steps={sum(len(case['steps']) for case in cases)} "
        f"intents={len(intent_counts)} functions={len(all_expected_functions)} "
        f"locales={dict(sorted(locale_counts.items()))} surfaces={len(all_surfaces)} "
        f"states={len(all_states)} transitions={len(all_transitions)} "
        f"recovery_probes={recovery_probes} role_inversions={role_inversion_probes} "
        f"homonym_decoys={homonym_decoys} dangerous_expected_clicks={dangerous_expected_clicks} "
        f"max_runtime_wording_similarity={maximum_similarity:.6f} "
        f"sha256={actual_seal}"
    )


if __name__ == "__main__":
    main()
