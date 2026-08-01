from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_db_gym import load_fixed_cases  # noqa: E402


FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "independent-specialized-ops-v12.json"
)
AUDIT_PATH = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V12.md"
SOURCE_PATH = ROOT / "scripts" / "navigation_catalog_v12_data.py"
EXPECTED_SEAL = "88fc2a75c95ee584290bce735c0a830be7bf179fce21544acb655430855acd2a"
EXPECTED_SURFACES = {
    "approval_sheet",
    "bottom_navigation",
    "calendar_board",
    "card_carousel",
    "dashboard_grid",
    "detail_panel",
    "filter_drawer",
    "form_sections",
    "map_panel",
    "modal_sheet",
    "navigation_drawer",
    "offline_panel",
    "record_inspector",
    "search_results",
    "settings_list",
    "split_pane",
    "tab_strip",
    "timeline",
    "top_app_bar",
    "work_queue",
}
EXPECTED_STATES = {
    "awaiting_user_confirmation",
    "certification_pending_noted",
    "clinical_hold_noted",
    "destination_verified",
    "empty_state_recovered",
    "filter_applied",
    "legal_hold_noted",
    "loading_complete",
    "offline_recovered",
    "overlay_dismissed",
    "permission_denied_recovered",
    "ready",
    "record_matched",
    "record_selected",
    "regulatory_hold_noted",
    "role_scope_verified",
    "role_selected",
    "safety_hold_noted",
    "scrolled",
    "signed_in",
    "stale_cache_refreshed",
    "unavailable_noted",
    "wrong_branch_recovered",
}
EXPECTED_TRANSITIONS = {
    "full_page_scroll",
    "offline_resume",
    "permission_recovery",
    "record_reselection",
    "role_scoped_gateway",
    "section_gateway",
    "stale_refresh",
    "wrong_branch_backtrack",
}
RECOVERY_KINDS = {
    "disabled_destination",
    "offline_recovery",
    "stale_recovery",
    "unavailable_destination",
}
ROW_PATTERN = re.compile(
    r"(?m)^\| `([^`]+\.[^`]+)` \| `([^`]+)` \| ([SC]) \|"
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _normalized(value: object) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", str(value)).casefold()
        if character.isalnum()
    )


def _character_trigrams(value: str) -> frozenset[str]:
    return frozenset(value[index : index + 3] for index in range(len(value) - 2))


def _near_copy_violation(left: object, right: object) -> tuple[str | None, float]:
    """Detect duplicated fixture prose without consulting any catalog wording."""

    left_normalized = _normalized(left)
    right_normalized = _normalized(right)
    if left_normalized == right_normalized:
        return "exact", 1.0
    if min(len(left_normalized), len(right_normalized)) >= 48 and (
        left_normalized in right_normalized or right_normalized in left_normalized
    ):
        return "wrapped_copy", 1.0

    length_ratio = min(len(left_normalized), len(right_normalized)) / max(
        1, max(len(left_normalized), len(right_normalized))
    )
    if length_ratio < 0.72:
        return None, 0.0
    similarity = SequenceMatcher(
        None,
        left_normalized,
        right_normalized,
        autojunk=False,
    ).ratio()
    if similarity >= 0.96:
        return "high_similarity_copy", similarity

    left_trigrams = _character_trigrams(left_normalized)
    right_trigrams = _character_trigrams(right_normalized)
    overlap = len(left_trigrams & right_trigrams) / max(
        1, min(len(left_trigrams), len(right_trigrams))
    )
    if similarity >= 0.91 and overlap >= 0.96:
        return "distributed_copy", max(similarity, overlap)
    return None, max(similarity, overlap)


def _assert_near_copy_guard_self_tests() -> None:
    source = (
        "The assigned field reviewer opens the amber work bundle, verifies its lifecycle, "
        "and leaves the final control untouched for the user."
    )
    violation, _score = _near_copy_violation(source, source)
    assert violation == "exact"
    violation, _score = _near_copy_violation(
        source,
        f"Independent preface. {source} Independent suffix.",
    )
    assert violation == "wrapped_copy"
    mutation = source[:-2] + "x."
    violation, score = _near_copy_violation(source, mutation)
    assert violation == "high_similarity_copy", score
    violation, _score = _near_copy_violation(
        source,
        "서로 다른 현장 문장은 대상 기록과 안전 경계를 별도의 어휘로 설명합니다.",
    )
    assert violation is None


def _audit_contract() -> dict[str, tuple[str, str]]:
    """Consume only function ID, intent ID, and S/C from the v12 audit table."""

    rows: dict[str, tuple[str, str]] = {}
    for function_id, intent_id, safety_class in ROW_PATTERN.findall(
        AUDIT_PATH.read_text(encoding="utf-8")
    ):
        assert intent_id not in rows
        rows[intent_id] = (function_id, safety_class)
    assert len(rows) == 240
    assert len({value[0] for value in rows.values()}) == 240
    assert Counter(value[1] for value in rows.values()) == {"S": 78, "C": 162}
    return rows


def _contract_digest(contract: dict[str, tuple[str, str]]) -> str:
    rows = sorted(
        f"{function_id}\t{intent_id}\t{safety_class}"
        for intent_id, (function_id, safety_class) in contract.items()
    )
    return hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()


def _load_source_contract() -> ModuleType | None:
    if not SOURCE_PATH.is_file():
        return None
    module_name = "_navigation_catalog_v12_contract_only"
    spec = importlib.util.spec_from_file_location(
        module_name,
        SOURCE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # ``dataclasses`` resolves postponed annotations through ``sys.modules``
    # while the module body is executing.  Register the isolated contract
    # module first, just like Python's regular import machinery does.
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
    return module


def _validate_source_ids(
    source: ModuleType,
    *,
    audit_contract: dict[str, tuple[str, str]],
    required_domains: set[str],
) -> None:
    """Validate source IDs and fixed terminal policy; never inspect source wording fields."""

    functions = {
        str(item["function_id"]): item for item in getattr(source, "V12_FUNCTIONS")
    }
    intents = {
        str(item["intent_id"]): item for item in getattr(source, "V12_INTENTS")
    }
    terminal_to_intent = {
        str(item["terminal_function"]): str(item["intent_id"])
        for item in getattr(source, "V12_INTENTS")
    }
    terminal_ids = {value[0] for value in audit_contract.values()}
    hub_ids = {f"{domain}.hub" for domain in required_domains}
    assert set(functions) == terminal_ids | hub_ids
    assert set(intents) == set(audit_contract)
    assert terminal_to_intent == {
        function_id: intent_id
        for intent_id, (function_id, _safety_class) in audit_contract.items()
    }
    assert set(getattr(source, "REQUIRED_DOMAINS")) == required_domains
    assert all(bool(functions[item]["terminal"]) for item in terminal_ids)
    assert all(not bool(functions[item]["terminal"]) for item in hub_ids)
    assert all(str(functions[item]["domain"]) in required_domains for item in terminal_ids)
    assert all(functions[item]["risk_level"] == "high" for item in terminal_ids)
    assert all(functions[item]["automation_policy"] == "never_auto" for item in terminal_ids)
    assert all(functions[item]["stop_policy"] == "before_action" for item in terminal_ids)


def main(*, fixture_only: bool = False) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["fixture_id"] == "independent-specialized-ops-v12"
    assert payload["schema_version"] == "1.0"
    assert payload["catalog_target"] == "12.0.0"
    assert payload["split"] == "independent_specialized_ops_v12"
    assert payload["source_kind"] == "fixed_independent"
    assert payload["tuning_allowed"] is False
    assert payload["frozen"] is True
    assert payload["catalog_derived"] is False
    assert payload["independent_accuracy_claim"] is True
    assert payload["created_on"] == "2026-07-30"

    audit_contract = _audit_contract()
    terminal_ids = {value[0] for value in audit_contract.values()}
    required_domains = {item.split(".", 1)[0] for item in terminal_ids}
    hub_ids = {f"{domain}.hub" for domain in required_domains}
    expected_functions = terminal_ids | hub_ids
    assert len(required_domains) == 12
    assert len(terminal_ids) == 240
    assert len(expected_functions) == 252

    assert payload["independence"] == {
        "authoring_basis": (
            "independently written operational outcomes using only v12 function IDs, "
            "intent IDs, and S/C classes"
        ),
        "prohibited_inputs": [
            "v12 catalog aliases",
            "v12 catalog goal patterns",
            "v12 catalog goal-rule wording",
            "catalog descriptions",
            "materializer output",
            "resolver results or fixture failures",
        ],
        "label_access_policy": (
            "frozen non-tuning holdout; outcomes and misses are not inputs to catalog tuning"
        ),
        "ui_policy": (
            "synthetic brand-free and package-free surfaces without coordinates, resource "
            "identifiers, or real-person data"
        ),
        "near_copy_policy": (
            "same-locale goals are pairwise checked after Unicode normalization; exact, "
            "wrapped, and high-similarity copies are rejected"
        ),
        "id_class_contract_sha256": _contract_digest(audit_contract),
    }
    assert payload["coverage_contract"] == {
        "exact_cases": 240,
        "exact_steps": 960,
        "exact_intents": 240,
        "exact_functions": 252,
        "exact_cases_per_intent": 1,
        "exact_cases_per_locale": {"ko-KR": 120, "en-US": 120},
        "exact_safety_classes": {"S": 78, "C": 162},
        "exact_steps_per_case": 4,
        "required_domains": sorted(required_domains),
        "minimum_ui_surfaces": 20,
        "minimum_screen_states": 20,
        "required_transition_variants": sorted(EXPECTED_TRANSITIONS),
        "minimum_recovery_probes": 960,
        "minimum_wrong_role_or_record_probes": 960,
        "minimum_homonym_decoys": 480,
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

    cases = list(payload["cases"])
    assert len(cases) == 240
    assert len({str(case["case_id"]) for case in cases}) == 240
    assert len({str(case["goal_text"]) for case in cases}) == 240
    assert all(len(case["steps"]) == 4 for case in cases)
    assert sum(len(case["steps"]) for case in cases) == 960
    assert Counter(str(case["intent_id"]) for case in cases) == Counter(
        {intent_id: 1 for intent_id in audit_contract}
    )
    assert Counter(str(case["locale"]) for case in cases) == {
        "ko-KR": 120,
        "en-US": 120,
    }
    assert Counter(str(case["safety_class"]) for case in cases) == {
        "S": 78,
        "C": 162,
    }
    assert Counter(
        str(case["steps"][-1]["expected"]["function_id"]).split(".", 1)[0]
        for case in cases
    ) == Counter({domain: 20 for domain in required_domains})

    _assert_near_copy_guard_self_tests()
    maximum_goal_similarity = 0.0
    for index, left in enumerate(cases):
        for right in cases[index + 1 :]:
            if left["locale"] != right["locale"]:
                continue
            violation, score = _near_copy_violation(
                left["goal_text"],
                right["goal_text"],
            )
            maximum_goal_similarity = max(maximum_goal_similarity, score)
            assert violation is None, (
                left["case_id"],
                right["case_id"],
                violation,
                score,
            )

    found_functions: set[str] = set()
    found_surfaces: set[str] = set()
    found_states: set[str] = set()
    found_transitions: set[str] = set()
    recovery_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    wrong_role_or_record = 0
    homonym_decoys = 0
    dangerous_final_actions = 0
    dangerous_expected_clicks = 0

    for case in cases:
        case_id = str(case["case_id"])
        locale = str(case["locale"])
        intent_id = str(case["intent_id"])
        goal_text = str(case["goal_text"])
        assert locale in {"ko-KR", "en-US"}
        assert case["split"] == payload["split"]
        assert case["source_kind"] == "fixed_independent"
        assert case["tuning_allowed"] is False
        assert case["app_package"] == ""
        assert case["app_version"] == "synthetic"
        assert case["user_state"] == "role_asset_state_verified"
        assert {
            "fixed_independent",
            "non_tuning",
            "catalog_blind_authored",
            "user_owned_final_action",
            "role_asset_state_evidence",
            "role_inversion",
            "wrong_record",
            "homonym_decoy",
            "recovery_probe",
        } <= set(case["tags"])
        transitions = EXPECTED_TRANSITIONS.intersection(case["tags"])
        assert len(transitions) == 1
        found_transitions.update(transitions)
        assert len(_normalized(goal_text)) >= 150
        assert "_" not in goal_text
        assert not re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", goal_text.casefold())
        assert not re.search(r"\b(?:\+?\d[\d -]{8,}\d)\b", goal_text)
        assert not re.search(r"\b(?:[A-Fa-f0-9]{8,}|\d{6,})\b", goal_text)
        assert ("역할" in goal_text and "생명주기" in goal_text) if locale == "ko-KR" else (
            "role" in goal_text.casefold() and "lifecycle" in goal_text.casefold()
        )

        function_id, safety_class = audit_contract[intent_id]
        assert case["safety_class"] == safety_class
        domain, terminal_key = function_id.split(".", 1)
        assert intent_id == f"v12_{domain}_{terminal_key}"
        steps = list(case["steps"])
        assert str(steps[2]["expected"]["label"]).casefold() in goal_text.casefold()
        assert [str(step["expected"]["function_id"]) for step in steps] == [
            f"{domain}.hub",
            f"{domain}.hub",
            function_id,
            function_id,
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

        case_decoys: Counter[str] = Counter()
        for step in steps:
            expected = step["expected"]
            action = str(expected["action"])
            action_counts[action] += 1
            found_functions.add(str(expected["function_id"]))
            found_surfaces.add(str(step["ui_surface"]))
            found_states.add(str(step["screen_state"]))
            assert step["activity_name"] == "SyntheticSurface"
            for item in step["elements"]:
                assert "bounds" not in item
                assert "view_id" not in item
                assert "resource_id" not in item
                assert "package" not in item
                decoy_kind = str(item.get("decoy_kind", ""))
                case_decoys[decoy_kind] += 1
                if decoy_kind in RECOVERY_KINDS:
                    recovery_counts[decoy_kind] += 1
                wrong_role_or_record += int(
                    decoy_kind in {"role_inversion_wrong_role", "wrong_record_decoy"}
                )
                homonym_decoys += int(decoy_kind == "homonym_decoy")
                dangerous_final_actions += int(
                    bool(item.get("dangerous", False))
                    and decoy_kind == "user_owned_final_action"
                )
            if action == "click":
                matches = [
                    item
                    for item in step["elements"]
                    if item.get("label") == expected["label"]
                    and bool(item.get("clickable", True))
                    and bool(item.get("enabled", True))
                    and bool(item.get("visible", True))
                ]
                assert matches, (case_id, step["step_id"], expected)
                dangerous_expected_clicks += sum(
                    int(bool(item.get("dangerous", False))) for item in matches
                )
            else:
                assert expected["label"] is None
        assert all(case_decoys[kind] >= 1 for kind in RECOVERY_KINDS)
        assert case_decoys["role_inversion_wrong_role"] >= 3
        assert case_decoys["wrong_record_decoy"] >= 4
        assert case_decoys["homonym_decoy"] >= 2
        assert case_decoys["user_owned_final_action"] == 1

    assert found_functions == expected_functions
    assert found_surfaces == EXPECTED_SURFACES
    assert found_states == EXPECTED_STATES
    assert found_transitions == EXPECTED_TRANSITIONS
    assert sum(recovery_counts.values()) == 2_160
    assert recovery_counts == {
        "disabled_destination": 720,
        "unavailable_destination": 480,
        "offline_recovery": 480,
        "stale_recovery": 480,
    }
    assert wrong_role_or_record == 1_680
    assert homonym_decoys == 480
    assert dangerous_final_actions == 240
    assert dangerous_expected_clicks == 0
    assert action_counts == {
        "click": 600,
        "scroll_forward": 60,
        "back": 60,
        "stop": 120,
        "no_click": 120,
    }

    gym_cases = load_fixed_cases(FIXTURE_PATH, split=str(payload["split"]))
    assert len(gym_cases) == 240
    assert sum(len(case.steps) for case in gym_cases) == 960
    assert all(case.source_kind == "fixed_independent" for case in gym_cases)
    assert all(case.tuning_allowed is False for case in gym_cases)
    assert {
        step.expected_function for case in gym_cases for step in case.steps
    } == expected_functions
    assert not any(
        element.dangerous
        and step.expected_action == "click"
        and element.label == step.expected_label
        for case in gym_cases
        for step in case.steps
        for element in step.elements
    )

    source_checked = False
    if not fixture_only:
        source = _load_source_contract()
        if source is not None:
            _validate_source_ids(
                source,
                audit_contract=audit_contract,
                required_domains=required_domains,
            )
            source_checked = True

    print(
        "navigation specialized operations v12 independent fixture checks ok: "
        f"cases={len(cases)} steps={sum(len(case['steps']) for case in cases)} "
        f"intents={len(audit_contract)} functions={len(found_functions)} "
        f"locales={dict(sorted(Counter(str(case['locale']) for case in cases).items()))} "
        f"safety_classes={dict(sorted(Counter(str(case['safety_class']) for case in cases).items()))} "
        f"surfaces={len(found_surfaces)} states={len(found_states)} "
        f"transitions={len(found_transitions)} recovery_probes={sum(recovery_counts.values())} "
        f"wrong_role_or_record={wrong_role_or_record} homonym_decoys={homonym_decoys} "
        f"dangerous_expected_clicks={dangerous_expected_clicks} "
        f"max_pairwise_goal_similarity={maximum_goal_similarity:.6f} "
        f"source_contract_checked={source_checked} sha256={actual_seal}"
    )


if __name__ == "__main__":
    main(fixture_only="--fixture-only" in sys.argv[1:])
