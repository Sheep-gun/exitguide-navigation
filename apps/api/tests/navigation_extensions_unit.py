from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.services.navigation_extensions import (
    ExtensionMode,
    LogicPolicyVerifier,
    NavigationEvaluationStore,
    NavigationExtensionRuntime,
    PolicyVerdict,
    ProcedureCatalog,
    build_procedure_catalog,
)
from app.services.navigation_extensions.predicates import evaluate_predicate
from app.services.navigation_extensions.n100_adapter import merge_procedure_hint


ROOT = Path(__file__).resolve().parents[3]
SEED_PATH = ROOT / "fixtures" / "navigation-extensions" / "procedures.v1.json"
POLICY_PATH = ROOT / "contracts" / "navigation-safety-rules.v1.json"


def _facts(**screen: object) -> dict[str, object]:
    return {
        "screen": {
            "trusted": True,
            "account_hub_reached": False,
            "membership_hub_reached": False,
            "terminal_boundary_reached": False,
            **screen,
        }
    }


def _policy_facts(*, terminal: bool = False, confirmation: bool = False) -> dict[str, object]:
    return {
        "screen": {"trusted": True},
        "candidate": {
            "observed": True,
            "clickable": True,
            "enabled": True,
            "forbidden": False,
            "risk_level": "high" if terminal else "low",
            "terminal": terminal,
            "state_changing": terminal,
        },
        "goal_candidate_operation_match": True,
        "terms": {"required": False, "status": "not_applicable", "blocked": False},
        "confirmation": {"valid": confirmation},
    }


def assert_predicates_are_data_only() -> None:
    facts = {"screen": {"trusted": True, "roles": ["account.hub"]}}
    assert evaluate_predicate({"equals": {"fact": "screen.trusted", "value": True}}, facts)
    assert evaluate_predicate(
        {
            "all": [
                {"exists": {"fact": "screen.roles"}},
                {"not": {"equals": {"fact": "screen.trusted", "value": False}}},
            ]
        },
        facts,
    )


def assert_procedure_chain_runs_in_shadow(root: Path) -> None:
    catalog_path = root / "procedures.sqlite"
    build_procedure_catalog(SEED_PATH, catalog_path)
    catalog = ProcedureCatalog(catalog_path)
    assert catalog.metadata()["generation_id"] == "navigation-procedure-seed-20260804"
    assert len(catalog.all(statuses=("draft",))) == 4
    assert catalog.all(statuses=("validated",)) == ()
    assert catalog.all(statuses=("active",)) == ()

    runtime = NavigationExtensionRuntime.from_paths(
        mode=ExtensionMode.SHADOW,
        procedure_catalog_path=catalog_path,
        policy_path=POLICY_PATH,
        extension_db_path=root / "extension.sqlite",
    )
    session_id = "session-procedure"
    first = runtime.prepare_decision(
        session_id=session_id,
        goal_id="membership.cancel",
        app_package="example.app",
        facts=_facts(),
        parameters={"operation": "cancel"},
    )
    assert first is not None
    assert first.procedure_id == "account_hub.open.v1"
    assert first.preferred_role_id == "account.hub"
    assert first.enforced is False
    assert first.fast_path_eligible is False
    assert first.fast_path_reason == "procedure_not_active"

    observed_first = runtime.observe_procedure(
        session_id=session_id,
        decision_id="decision-1",
        observation_id="observation-1",
        facts=_facts(account_hub_reached=True),
    )
    assert observed_first is not None and observed_first.procedure_completed

    second = runtime.prepare_decision(
        session_id=session_id,
        goal_id="membership.cancel",
        app_package="example.app",
        facts=_facts(account_hub_reached=True),
        parameters={"operation": "cancel"},
    )
    assert second is not None
    assert second.procedure_id == "membership_management.open.v1"
    assert second.preferred_role_id == "membership.hub"
    runtime.observe_procedure(
        session_id=session_id,
        decision_id="decision-2",
        observation_id="observation-2",
        facts=_facts(account_hub_reached=True, membership_hub_reached=True),
    )

    third = runtime.prepare_decision(
        session_id=session_id,
        goal_id="membership.cancel",
        app_package="example.app",
        facts=_facts(account_hub_reached=True, membership_hub_reached=True),
        parameters={"operation": "cancel"},
    )
    assert third is not None
    assert third.procedure_id == "membership_operation.reach.v1"
    assert third.preferred_role_id == "membership.cancel.entry"


def assert_enforce_requires_promoted_procedures(root: Path) -> None:
    packet = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    active_packet = root / "active-procedures.json"
    for procedure in packet["procedures"]:
        procedure["status"] = "active"
    active_packet.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    active_catalog = root / "active-procedures.sqlite"
    build_procedure_catalog(active_packet, active_catalog)

    inactive_runtime = NavigationExtensionRuntime.from_paths(
        mode=ExtensionMode.ENFORCE,
        procedure_catalog_path=root / "procedures.sqlite",
        policy_path=POLICY_PATH,
        extension_db_path=root / "inactive-extension.sqlite",
    )
    assert (
        inactive_runtime.prepare_decision(
            session_id="inactive-session",
            goal_id="membership.cancel",
            app_package="example.app",
            facts=_facts(),
            parameters={"operation": "cancel"},
        )
        is None
    )

    active_runtime = NavigationExtensionRuntime.from_paths(
        mode=ExtensionMode.ENFORCE,
        procedure_catalog_path=active_catalog,
        policy_path=POLICY_PATH,
        extension_db_path=root / "active-extension.sqlite",
    )
    hint = active_runtime.prepare_decision(
        session_id="active-session",
        goal_id="membership.cancel",
        app_package="example.app",
        facts=_facts(),
        parameters={"operation": "cancel"},
    )
    assert hint is not None and hint.enforced
    assert hint.fast_path_eligible is False
    assert hint.fast_path_reason == "hint_only"


def assert_fast_path_needs_exact_validated_scope(root: Path) -> None:
    packet = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    procedure = packet["procedures"][0]
    packet["procedures"] = [procedure]
    procedure.update(
        {
            "procedure_id": "example.account_hub.fast.v1",
            "status": "active",
            "app_package": "example.app",
            "compatible_app_versions": ["1.2.*"],
            "locales": ["ko-KR"],
            "execution_mode": "deterministic_fast_path",
            "validation_count": 3,
            "fast_path_min_validation_count": 3,
        }
    )
    packet_path = root / "fast-procedures.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    catalog_path = root / "fast-procedures.sqlite"
    build_procedure_catalog(packet_path, catalog_path)
    runtime = NavigationExtensionRuntime.from_paths(
        mode=ExtensionMode.ENFORCE,
        procedure_catalog_path=catalog_path,
        policy_path=POLICY_PATH,
        extension_db_path=root / "fast-extension.sqlite",
    )
    hint = runtime.prepare_decision(
        session_id="fast-session",
        goal_id="membership.cancel",
        app_package="example.app",
        app_version="1.2.9",
        locale="ko-KR",
        facts=_facts(),
        parameters={"operation": "cancel"},
    )
    assert hint is not None
    assert hint.fast_path_eligible is True
    assert hint.fast_path_reason == "validated_exact_scope"
    merged = merge_procedure_hint(
        {"target_roles": ["navigation.menu"], "immediate_subgoal": "fallback"},
        hint,
    )
    assert merged["target_roles"][:2] == ["account.hub", "navigation.menu"]

    assert (
        runtime.prepare_decision(
            session_id="wrong-version-session",
            goal_id="membership.cancel",
            app_package="example.app",
            app_version="2.0.0",
            locale="ko-KR",
            facts=_facts(),
            parameters={"operation": "cancel"},
        )
        is None
    )
    assert (
        runtime.prepare_decision(
            session_id="wrong-locale-session",
            goal_id="membership.cancel",
            app_package="example.app",
            app_version="1.2.9",
            locale="en-US",
            facts=_facts(),
            parameters={"operation": "cancel"},
        )
        is None
    )

    procedure["validation_count"] = 2
    insufficient_path = root / "insufficient-procedures.json"
    insufficient_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    insufficient_catalog = root / "insufficient-procedures.sqlite"
    build_procedure_catalog(insufficient_path, insufficient_catalog)
    insufficient_runtime = NavigationExtensionRuntime.from_paths(
        mode=ExtensionMode.ENFORCE,
        procedure_catalog_path=insufficient_catalog,
        policy_path=POLICY_PATH,
        extension_db_path=root / "insufficient-extension.sqlite",
    )
    insufficient = insufficient_runtime.prepare_decision(
        session_id="insufficient-session",
        goal_id="membership.cancel",
        app_package="example.app",
        app_version="1.2.9",
        locale="ko-KR",
        facts=_facts(),
        parameters={"operation": "cancel"},
    )
    assert insufficient is not None
    assert insufficient.fast_path_eligible is False
    assert insufficient.fast_path_reason == "insufficient_validations"
    unchanged_roles = merge_procedure_hint(
        {"target_roles": ["navigation.menu"], "immediate_subgoal": "fallback"},
        insufficient,
    )
    assert unchanged_roles["target_roles"] == ["navigation.menu"]


def assert_verifier_and_confirmation_are_separate(root: Path) -> None:
    verifier = LogicPolicyVerifier(POLICY_PATH)
    safe = verifier.verify(
        proposed_action={"name": "click", "candidate_id": "safe"},
        facts=_policy_facts(),
    )
    assert safe.verdict == PolicyVerdict.ALLOW
    terminal = verifier.verify(
        proposed_action={"name": "click", "candidate_id": "delete"},
        facts=_policy_facts(terminal=True),
    )
    assert terminal.verdict == PolicyVerdict.REQUIRE_CONFIRMATION
    assert terminal.final_action == {"name": "stop_for_user"}

    runtime = NavigationExtensionRuntime.from_paths(
        mode=ExtensionMode.ENFORCE,
        procedure_catalog_path=root / "active-procedures.sqlite",
        policy_path=POLICY_PATH,
        extension_db_path=root / "verifier-extension.sqlite",
    )
    action = {"name": "click", "candidate_id": "delete"}
    blocked_action, blocked = runtime.verify_action(
        session_id="safety-session",
        decision_id="safety-decision-1",
        proposed_action=action,
        facts=_policy_facts(terminal=True),
    )
    assert blocked is not None
    assert blocked.verdict == PolicyVerdict.REQUIRE_CONFIRMATION
    assert blocked.confirmation_id is not None
    assert blocked_action == {"name": "stop_for_user"}

    runtime.store.confirm_challenge(
        blocked.confirmation_id,
        source="native_ui",
        session_id="safety-session",
        action=action,
    )
    assert runtime.store.summary()["user"]["confirmations"] == 1
    allowed_action, allowed = runtime.verify_action(
        session_id="safety-session",
        decision_id="safety-decision-2",
        proposed_action=action,
        facts=_policy_facts(terminal=True),
        confirmation_id=blocked.confirmation_id,
    )
    assert allowed is not None and allowed.verdict == PolicyVerdict.ALLOW
    assert allowed_action == action
    replay_action, replay = runtime.verify_action(
        session_id="safety-session",
        decision_id="safety-decision-3",
        proposed_action=action,
        facts=_policy_facts(terminal=True),
        confirmation_id=blocked.confirmation_id,
    )
    assert replay is not None and replay.verdict == PolicyVerdict.REQUIRE_CONFIRMATION
    assert replay_action == {"name": "stop_for_user"}


def assert_enforce_never_weakens_grounding_gate(root: Path) -> None:
    runtime = NavigationExtensionRuntime.from_paths(
        mode=ExtensionMode.ENFORCE,
        procedure_catalog_path=root / "active-procedures.sqlite",
        policy_path=POLICY_PATH,
        extension_db_path=root / "monotonic-extension.sqlite",
    )
    proposed = {"name": "click", "candidate_id": "ordinary"}

    waited_action, waited = runtime.verify_action(
        session_id="grounding-wait-session",
        decision_id="grounding-wait-decision",
        proposed_action=proposed,
        grounded_action={"name": "wait_and_observe"},
        facts=_policy_facts(),
    )
    assert waited is not None and waited.verdict == PolicyVerdict.ALLOW
    assert waited_action == {"name": "wait_and_observe"}
    assert waited.final_action == waited_action

    stopped_action, stopped = runtime.verify_action(
        session_id="grounding-stop-session",
        decision_id="grounding-stop-decision",
        proposed_action=proposed,
        grounded_action={"name": "stop_for_user"},
        facts=_policy_facts(),
    )
    assert stopped is not None and stopped.verdict == PolicyVerdict.ALLOW
    assert stopped_action == {"name": "stop_for_user"}
    assert stopped.final_action == stopped_action

    blocked_action, blocked = runtime.verify_action(
        session_id="policy-block-session",
        decision_id="policy-block-decision",
        proposed_action=proposed,
        grounded_action={"name": "wait_and_observe"},
        facts={
            **_policy_facts(),
            "candidate": {
                **_policy_facts()["candidate"],
                "forbidden": True,
            },
        },
    )
    assert blocked is not None and blocked.verdict == PolicyVerdict.BLOCK
    assert blocked_action == {"name": "stop_for_user"}
    assert blocked.final_action == blocked_action


def assert_evaluation_metrics_are_distinct(root: Path) -> None:
    store = NavigationEvaluationStore(root / "metrics.sqlite")
    attempt_0 = store.start_attempt(
        task_run_id="run-a",
        task_case_id="case-a",
        session_id="session-a0",
        attempt_index=0,
        memory_profile="off",
        procedure_profile="off",
        verifier_profile="base",
        app_package="example.app",
        app_version="1",
        goal_id="membership.cancel",
    )
    store.finish_attempt(
        attempt_0,
        success=False,
        outcome="wrong_destination",
        within_attempt_recoveries=1,
        total_actions=4,
        llm_calls=1,
    )
    attempt_1 = store.start_attempt(
        task_run_id="run-a",
        task_case_id="case-a",
        session_id="session-a1",
        attempt_index=1,
        memory_profile="canonical",
        procedure_profile="procedure-v1",
        verifier_profile="logic-v1",
        app_package="example.app",
        app_version="1",
        goal_id="membership.cancel",
    )
    store.finish_attempt(
        attempt_1,
        success=True,
        outcome="reached",
        within_attempt_recoveries=0,
        total_actions=3,
        llm_calls=0,
    )
    attempt_b = store.start_attempt(
        task_run_id="run-b",
        task_case_id="case-b",
        session_id="session-b0",
        attempt_index=0,
        memory_profile="canonical",
        procedure_profile="procedure-v1",
        verifier_profile="logic-v1",
        app_package="other.app",
        app_version="2",
        goal_id="account.delete",
    )
    store.finish_attempt(
        attempt_b,
        success=True,
        outcome="reached",
        within_attempt_recoveries=0,
        total_actions=2,
        llm_calls=0,
    )
    retrieval_ids = store.record_memory_retrievals(
        session_id="session-a0",
        decision_id="decision-a",
        task_run_id="run-a",
        rows=[
            {
                "evidence_id": "memory-bad",
                "source_type": "canonical",
                "used": True,
            },
            {
                "evidence_id": "memory-good",
                "source_type": "canonical",
                "applicable": True,
                "used": False,
            },
        ],
    )
    store.label_memory_retrieval(
        retrieval_ids[0],
        applicable=False,
        changed_action=True,
        outcome_effect="harmed",
        stale=False,
    )
    store.record_user_intervention(
        session_id="session-a0", kind="correction", reason_code="wrong_candidate"
    )
    store.record_user_intervention(
        session_id="session-a1", kind="confirmation", reason_code="terminal_action"
    )
    summary = store.summary()
    assert summary["first_attempt"] == {"total": 2, "success": 1, "rate": 0.5}
    assert summary["within_one_retry"] == {"total": 2, "success": 2, "rate": 1.0}
    assert summary["memory"]["false_recall_rate"] == 0.5
    assert summary["memory"]["harmful_recall_count"] == 1
    assert summary["user"] == {"corrections": 1, "confirmations": 1}


def main() -> None:
    assert_predicates_are_data_only()
    with tempfile.TemporaryDirectory(prefix="exitguide-navigation-extension-") as raw:
        root = Path(raw)
        assert_procedure_chain_runs_in_shadow(root)
        assert_enforce_requires_promoted_procedures(root)
        assert_fast_path_needs_exact_validated_scope(root)
        assert_verifier_and_confirmation_are_separate(root)
        assert_enforce_never_weakens_grounding_gate(root)
        assert_evaluation_metrics_are_distinct(root)
    print("navigation extension unit checks passed")


if __name__ == "__main__":
    main()
