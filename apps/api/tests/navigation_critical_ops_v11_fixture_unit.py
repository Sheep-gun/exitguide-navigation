from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
SCRIPTS = ROOT / "scripts"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from app.services.navigation_db_gym import load_fixed_cases  # noqa: E402
from navigation_catalog_v11_data import (  # noqa: E402
    REQUIRED_DOMAINS,
    V11_FUNCTIONS,
    V11_INTENTS,
)


FIXTURE_PATH = (
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-critical-ops-v11.json"
)
AUDIT_PATH = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V11.md"
EXPECTED_SEAL = "4cd377b191b19ac23cbf35e0939531f0437bf1147fd260184bd50161d0b97efe"
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
    "work_queue",
    "form_sections",
    "offline_panel",
    "approval_sheet",
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
    "record_selected",
    "scrolled",
    "wrong_branch_recovered",
    "unavailable_noted",
    "disabled_noted",
    "awaiting_user_confirmation",
}
EXPECTED_TRANSITIONS = {
    "section_gateway",
    "full_page_scroll",
    "wrong_branch_backtrack",
    "role_scoped_gateway",
}
PROHIBITED_FRAGMENTS = {
    "oracle",
    "servicenow",
    "guidewire",
    "xactimate",
    "arcgis",
    "fema",
    "esri",
    "firebase",
    "androidx",
    "com.",
    "org.",
    "net.",
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


@lru_cache(maxsize=40_000)
def _character_trigrams(value: str) -> frozenset[str]:
    return frozenset(value[index : index + 3] for index in range(len(value) - 2))


def _protected_wording() -> dict[str, dict[str, tuple[str, str, str, int]]]:
    """Load v11 runtime phrases solely for leakage detection, never for authoring."""

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

    for function in V11_FUNCTIONS:
        for locale, aliases in function["aliases"].items():
            for alias in aliases:
                add(str(locale), str(function["function_id"]), "alias", alias)
    for intent in V11_INTENTS:
        for locale, patterns in intent["patterns_by_locale"].items():
            for pattern in patterns:
                add(str(locale), str(intent["intent_id"]), "pattern", pattern)
        for rule in intent["goal_rules"]:
            locale = str(rule.get("v11_locale", rule.get("locale", "")))
            for field in ("all_of", "none_of"):
                for phrase in rule.get(field, []):
                    add(locale, str(intent["intent_id"]), f"rule_{field}", phrase)
    return result


def _audit_contract() -> dict[str, tuple[str, str]]:
    """Read only IDs and S/C class from the v11 coverage audit."""

    rows: dict[str, tuple[str, str]] = {}
    pattern = re.compile(
        r"\| `([^`]+\.[^`]+)` \| `([^`]+)` \| ([SC]) \|"
    )
    for function_id, intent_id, safety_class in pattern.findall(
        AUDIT_PATH.read_text(encoding="utf-8")
    ):
        assert intent_id not in rows
        rows[intent_id] = (function_id, safety_class)
    assert len(rows) == 230
    assert Counter(value[1] for value in rows.values()) == {"S": 74, "C": 156}
    return rows


def _source_violation(
    goal_normalized: str,
    protected_normalized: str,
    *,
    protected_word_count: int,
) -> tuple[str | None, float, float]:
    if goal_normalized == protected_normalized:
        return "exact", 1.0, 1.0
    if protected_word_count >= 2 and len(protected_normalized) >= 10:
        if protected_normalized in goal_normalized:
            return "wrapped_runtime_phrase", 1.0, 1.0
        if goal_normalized in protected_normalized:
            return "runtime_phrase_wraps_goal", 1.0, 1.0

    trigram_coverage = 0.0
    if protected_word_count >= 2 and len(protected_normalized) >= 18:
        protected_trigrams = _character_trigrams(protected_normalized)
        global_trigram_coverage = len(
            protected_trigrams.intersection(_character_trigrams(goal_normalized))
        ) / max(1, len(protected_trigrams))
        if global_trigram_coverage >= 0.84:
            window_length = len(protected_normalized) + 6
            trigram_coverage = max(
                (
                    len(
                        protected_trigrams.intersection(
                            _character_trigrams(
                                goal_normalized[start : start + window_length]
                            )
                        )
                    )
                    / max(1, len(protected_trigrams))
                )
                for start in range(max(1, len(goal_normalized) - window_length + 1))
            )
            if trigram_coverage >= 0.84:
                return "character_ngram_near_copy", trigram_coverage, trigram_coverage

    length_upper_bound = (
        2 * min(len(goal_normalized), len(protected_normalized))
        / (len(goal_normalized) + len(protected_normalized))
    )
    if length_upper_bound < 0.62:
        return None, trigram_coverage, trigram_coverage

    matcher = SequenceMatcher(
        None,
        goal_normalized,
        protected_normalized,
        autojunk=False,
    )
    similarity = matcher.ratio()
    matched = sum(block.size for block in matcher.get_matching_blocks())
    protected_coverage = matched / max(1, len(protected_normalized))
    if similarity >= 0.82:
        return "near_copy", similarity, protected_coverage
    if (
        protected_word_count >= 3
        and len(protected_normalized) >= 16
        and similarity >= 0.62
        and protected_coverage >= 0.94
    ):
        return "distributed_runtime_copy", similarity, protected_coverage
    return None, max(similarity, trigram_coverage), protected_coverage


def _assert_goal_is_independent(
    *,
    case_id: str,
    locale: str,
    goal_text: str,
    protected: dict[str, dict[str, tuple[str, str, str, int]]],
) -> float:
    goal_normalized = _normalized(goal_text)
    assert len(goal_normalized) >= 70, (case_id, "goal too short")
    maximum_similarity = 0.0
    maximum_source: tuple[str, str, str] | None = None
    for protected_normalized, (owner, kind, phrase, word_count) in protected[locale].items():
        violation, similarity, coverage = _source_violation(
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
            coverage,
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
        (locale, normalized, owner, kind, phrase, count)
        for locale in ("ko-KR", "en-US")
        for normalized, (owner, kind, phrase, count) in protected[locale].items()
    ]
    assert entries
    chosen: dict[str, tuple[str, str, str, str, int]] = {}
    for wanted in ("alias", "pattern", "rule_all_of", "rule_none_of"):
        candidates = [entry for entry in entries if entry[3] == wanted and entry[5] >= 2]
        assert candidates, wanted
        locale, normalized, _owner, kind, phrase, count = max(
            candidates,
            key=lambda entry: len(entry[1]),
        )
        chosen[wanted] = (locale, normalized, kind, phrase, count)

    for _locale, normalized, kind, _phrase, count in chosen.values():
        violation, _similarity, _coverage = _source_violation(
            normalized,
            normalized,
            protected_word_count=count,
        )
        assert violation == "exact", kind

    _locale, pattern, _kind, _phrase, pattern_count = chosen["pattern"]
    wrapped = _normalized(f"independent preface {pattern} independent suffix")
    violation, _similarity, _coverage = _source_violation(
        wrapped,
        pattern,
        protected_word_count=pattern_count,
    )
    assert violation == "wrapped_runtime_phrase"

    _locale, rule, _kind, _phrase, rule_count = chosen["rule_all_of"]
    replacement = "x" if not rule.endswith("x") else "y"
    near_copy = rule[:-1] + replacement
    violation, similarity, _coverage = _source_violation(
        near_copy,
        rule,
        protected_word_count=rule_count,
    )
    assert violation == "near_copy", (violation, similarity)

    distributed_source = "independentoperationalboundarywording"
    distributed_goal = (
        "independent"
        + ("x" * 10)
        + "operational"
        + ("y" * 10)
        + "boundarywording"
    )
    violation, _similarity, coverage = _source_violation(
        distributed_goal,
        distributed_source,
        protected_word_count=3,
    )
    assert violation in {
        "distributed_runtime_copy",
        "character_ngram_near_copy",
    }, (violation, coverage)

    embedded_source = "protectedoperationalboundaryphrase"
    embedded_mutation = _normalized(
        "unrelated independent preface "
        "protectedoperationalboundaryphraze "
        "unrelated independent suffix with more wording"
    )
    violation, _similarity, coverage = _source_violation(
        embedded_mutation,
        embedded_source,
        protected_word_count=3,
    )
    assert violation == "character_ngram_near_copy", (violation, coverage)

    one_word = next(
        normalized
        for _locale, normalized, _owner, _kind, _phrase, count in entries
        if count == 1 and len(normalized) >= 5
    )
    independent_sentence = _normalized(
        f"A separately authored operational sentence can share one vocabulary item {one_word} "
        "without copying a protected multiword construction"
    )
    violation, _similarity, _coverage = _source_violation(
        independent_sentence,
        one_word,
        protected_word_count=1,
    )
    assert violation is None


def main() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["fixture_id"] == "independent-critical-ops-v11"
    assert payload["schema_version"] == "1.0"
    assert payload["catalog_target"] == "11.0.0"
    assert payload["split"] == "independent_critical_ops_v11"
    assert payload["source_kind"] == "fixed_independent"
    assert payload["tuning_allowed"] is False
    assert payload["frozen"] is True
    assert payload["catalog_derived"] is False
    assert payload["independent_accuracy_claim"] is True
    assert payload["created_on"] == "2026-07-30"

    assert payload["independence"] == {
        "authoring_basis": (
            "independently worded critical-work outcomes based only on v11 IDs, domain scope, "
            "and S/C safety class"
        ),
        "prohibited_inputs": [
            "v11 aliases",
            "v11 goal patterns",
            "v11 goal-rule wording",
            "catalog descriptions",
            "other independent fixture labels or failures",
        ],
        "label_access_policy": (
            "frozen non-tuning holdout; resolver failures must not be inspected for catalog edits"
        ),
        "ui_policy": (
            "synthetic brand-free and package-free Android-like surfaces with no coordinates or "
            "real-world identifiers; destination labels exist only as visible choices"
        ),
    }

    coverage = payload["coverage_contract"]
    assert coverage == {
        "exact_cases": 230,
        "exact_steps": 920,
        "exact_intents": 230,
        "exact_functions": 242,
        "exact_cases_per_intent": 1,
        "exact_cases_per_locale": {"ko-KR": 115, "en-US": 115},
        "exact_safety_classes": {"S": 74, "C": 156},
        "exact_steps_per_case": 4,
        "required_domains": sorted(REQUIRED_DOMAINS),
        "minimum_ui_surfaces": 12,
        "minimum_screen_states": 14,
        "required_transition_variants": sorted(EXPECTED_TRANSITIONS),
        "minimum_recovery_probes": 920,
        "minimum_wrong_role_or_record_probes": 460,
        "minimum_homonym_decoys": 230,
    }
    assert payload["safety_contract"] == {
        "dangerous_expected_clicks": 0,
        "terminal_automation_policy": "never_auto",
        "terminal_stop_policy": "before_action",
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

    functions = {str(item["function_id"]): item for item in V11_FUNCTIONS}
    intents = {str(item["intent_id"]): item for item in V11_INTENTS}
    terminal_to_intent = {
        str(item["terminal_function"]): str(item["intent_id"])
        for item in V11_INTENTS
    }
    terminal_ids = set(terminal_to_intent)
    hub_ids = {
        str(item["function_id"])
        for item in V11_FUNCTIONS
        if not bool(item["terminal"])
    }
    assert len(functions) == 242
    assert len(intents) == 230
    assert len(terminal_ids) == 230
    assert len(hub_ids) == 12
    assert {str(functions[item]["domain"]) for item in terminal_ids} == set(REQUIRED_DOMAINS)
    assert all(functions[item]["risk_level"] == "high" for item in terminal_ids)
    assert all(functions[item]["automation_policy"] == "never_auto" for item in terminal_ids)
    assert all(functions[item]["stop_policy"] == "before_action" for item in terminal_ids)

    protected = _protected_wording()
    assert len(protected["ko-KR"]) >= 4_500
    assert len(protected["en-US"]) >= 4_500
    assert {
        kind
        for locale_entries in protected.values()
        for _owner, kind, _phrase, _count in locale_entries.values()
    } >= {"alias", "pattern", "rule_all_of", "rule_none_of"}
    _assert_copy_guard_self_tests(protected)

    cases = list(payload["cases"])
    audit_contract = _audit_contract()
    assert len(cases) == 230
    assert len({str(case["case_id"]) for case in cases}) == 230
    assert len({str(case["goal_text"]) for case in cases}) == 230
    assert all(len(case["steps"]) == 4 for case in cases)
    assert sum(len(case["steps"]) for case in cases) == 920

    intent_counts = Counter(str(case["intent_id"]) for case in cases)
    locale_counts = Counter(str(case["locale"]) for case in cases)
    safety_counts = Counter(str(case["safety_class"]) for case in cases)
    assert intent_counts == Counter({intent_id: 1 for intent_id in intents})
    assert locale_counts == {"ko-KR": 115, "en-US": 115}
    assert safety_counts == {"S": 74, "C": 156}

    maximum_similarity = 0.0
    expected_functions: set[str] = set()
    surfaces: set[str] = set()
    states: set[str] = set()
    transitions: set[str] = set()
    recovery_kinds: Counter[str] = Counter()
    wrong_role_or_record = 0
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
        assert intent_id in audit_contract
        assert case["split"] == payload["split"]
        assert case["source_kind"] == "fixed_independent"
        assert case["tuning_allowed"] is False
        assert case["app_package"] == ""
        assert case["app_version"] == "synthetic"
        assert {
            "fixed_independent",
            "non_tuning",
            "user_owned_final_action",
            "role_inversion",
            "wrong_record",
            "homonym_decoy",
            "recovery_probe",
        } <= set(case["tags"])
        assert len(EXPECTED_TRANSITIONS.intersection(case["tags"])) == 1
        assert not any(fragment in goal_text.casefold() for fragment in PROHIBITED_FRAGMENTS)
        assert not re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", goal_text.casefold())
        assert not re.search(r"\b(?:\+?\d[\d -]{8,}\d)\b", goal_text)
        assert not re.search(r"\b(?:[A-Fa-f0-9]{8,}|\d{6,})\b", goal_text)
        visible_text = "\n".join(
            [goal_text]
            + [str(step["screen_title"]) for step in case["steps"]]
            + [
                str(element.get("label", ""))
                for step in case["steps"]
                for element in step["elements"]
            ]
        )
        assert not any(
            fragment in visible_text.casefold() for fragment in PROHIBITED_FRAGMENTS
        )
        assert not re.search(
            r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}\b",
            visible_text.casefold(),
        )
        assert not re.search(r"\b[xy]\s*[:=]\s*-?\d+\b", visible_text.casefold())
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
        assert audit_contract[intent_id] == (terminal_id, str(case["safety_class"]))
        domain = str(functions[terminal_id]["domain"])
        hub_id = f"{domain}.hub"
        assert [str(step["expected"]["function_id"]) for step in steps] == [
            hub_id,
            hub_id,
            terminal_id,
            terminal_id,
        ]
        assert [step["stage"] for step in steps] == [
            "gateway",
            "recovery",
            "destination_candidate",
            "safety_boundary",
        ]
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
            expected_functions.add(str(expected["function_id"]))
            surfaces.add(str(step["ui_surface"]))
            states.add(str(step["screen_state"]))
            assert step["activity_name"] == "SyntheticSurface"
            for element in step["elements"]:
                assert "bounds" not in element
                assert "view_id" not in element
                assert "resource_id" not in element
                assert "package" not in element
                decoy_kind = str(element.get("decoy_kind", ""))
                recovery_kinds[decoy_kind] += int(
                    decoy_kind
                    in {
                        "disabled_destination",
                        "unavailable_destination",
                        "offline_recovery",
                        "stale_recovery",
                    }
                )
                wrong_role_or_record += int(
                    decoy_kind in {"role_inversion_wrong_role", "wrong_record_decoy"}
                )
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

        transitions.update(EXPECTED_TRANSITIONS.intersection(case["tags"]))

    assert expected_functions == set(functions)
    assert len(surfaces) >= 12
    assert surfaces == EXPECTED_SURFACES
    assert len(states) >= 14
    assert states == EXPECTED_STATES
    assert transitions == EXPECTED_TRANSITIONS
    assert sum(recovery_kinds.values()) >= 920
    assert all(recovery_kinds[kind] >= 230 for kind in (
        "disabled_destination",
        "unavailable_destination",
        "offline_recovery",
        "stale_recovery",
    ))
    assert wrong_role_or_record >= 460
    assert homonym_decoys >= 230
    assert dangerous_final_actions == 230
    assert dangerous_expected_clicks == 0
    assert action_counts == {
        "click": 575,
        "scroll_forward": 58,
        "back": 57,
        "stop": 115,
        "no_click": 115,
    }

    gym_cases = load_fixed_cases(FIXTURE_PATH, split=str(payload["split"]))
    assert len(gym_cases) == 230
    assert sum(len(case.steps) for case in gym_cases) == 920
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
        "navigation critical operations v11 independent fixture checks ok: "
        f"cases={len(cases)} steps={sum(len(case['steps']) for case in cases)} "
        f"intents={len(intent_counts)} functions={len(expected_functions)} "
        f"locales={dict(sorted(locale_counts.items()))} "
        f"safety_classes={dict(sorted(safety_counts.items()))} "
        f"surfaces={len(surfaces)} states={len(states)} transitions={len(transitions)} "
        f"recovery_probes={sum(recovery_kinds.values())} "
        f"wrong_role_or_record={wrong_role_or_record} homonym_decoys={homonym_decoys} "
        f"dangerous_expected_clicks={dangerous_expected_clicks} "
        f"max_runtime_wording_similarity={maximum_similarity:.6f} "
        f"sha256={actual_seal}"
    )


if __name__ == "__main__":
    main()
