from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from app.services.emulator_observation_corpus import (
    CANONICAL_CATALOG_SHA256,
    CANONICAL_CATALOG_VERSION,
    CANONICAL_EQUIVALENCE_SHA256,
)
from app.services.real_device_goal_candidates import (
    AppEvidence,
    GOAL_CANDIDATE_POLICY_SHA256,
    GOAL_CANDIDATE_POLICY_VERSION,
    LocalSignalEvidence,
    SemanticValue,
    family_definitions,
    generate_app_candidate_set,
)


ROOT = Path(__file__).resolve().parents[3]
GENERATOR_PATH = ROOT / "scripts" / "Generate-RealDeviceGoalCandidates.py"


def _load_generator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "exitguide_real_device_goal_candidates_unit", GENERATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GENERATOR = _load_generator()


FAMILY_ROWS = [
    {"family_id": "signup", "terminal_policy": "navigation_only"},
    {"family_id": "login", "terminal_policy": "user_boundary"},
    {"family_id": "logout", "terminal_policy": "user_final_action"},
    {"family_id": "account_deletion", "terminal_policy": "user_final_action"},
    {"family_id": "subscription_manage", "terminal_policy": "navigation_only"},
    {"family_id": "subscription_change", "terminal_policy": "user_final_action"},
    {"family_id": "subscription_cancel", "terminal_policy": "user_final_action"},
    {"family_id": "free_trial_cancel", "terminal_policy": "user_final_action"},
    {"family_id": "autopay_off", "terminal_policy": "user_final_action"},
    {"family_id": "payment_methods", "terminal_policy": "navigation_only"},
    {"family_id": "order_cancel_refund", "terminal_policy": "user_final_action"},
    {"family_id": "marketing_notifications_off", "terminal_policy": "navigation_only"},
    {"family_id": "optional_consent_withdrawal", "terminal_policy": "user_final_action"},
    {"family_id": "privacy_settings", "terminal_policy": "navigation_only"},
    {"family_id": "data_download_delete", "terminal_policy": "mixed_user_owned"},
    {"family_id": "customer_support", "terminal_policy": "navigation_only"},
    {"family_id": "security_settings", "terminal_policy": "navigation_only"},
    {"family_id": "insurance_contract_lookup", "terminal_policy": "navigation_only"},
    {"family_id": "insurance_contract_change", "terminal_policy": "user_final_action"},
    {"family_id": "insurance_contract_cancel", "terminal_policy": "user_final_action"},
    {"family_id": "insurance_claim", "terminal_policy": "user_final_action"},
    {"family_id": "flight_booking_lookup", "terminal_policy": "navigation_only"},
    {"family_id": "flight_booking_cancel", "terminal_policy": "user_final_action"},
]


def _family_manifest() -> dict[str, Any]:
    return {
        "required_goal_families": list(FAMILY_ROWS),
        "supplemental_goal_families": [
            {"family_id": "public_document_issuance", "terminal_policy": "navigation_only"},
            {"family_id": "insurance_premium_lookup", "terminal_policy": "navigation_only"},
            {"family_id": "insurance_refund_lookup", "terminal_policy": "navigation_only"},
            {"family_id": "telecom_billing_lookup", "terminal_policy": "navigation_only"},
        ],
    }


FAMILIES = family_definitions(_family_manifest())


def main() -> None:
    assert_deterministic_applicability_and_subscription_chain()
    assert_metadata_only_and_authentication_boundaries_never_infer_semantics()
    assert_mixed_authentication_and_post_auth_screens_are_family_scoped()
    assert_privacy_redaction_does_not_create_authentication_boundary()
    assert_sensitive_scope_restricts_transactional_candidates()
    assert_sensitive_local_signal_ids_make_insurance_applicable()
    assert_sensitive_local_metric_builds_insurance_artifact_and_rejects_tampering()
    assert_explicit_negative_evidence_is_not_applicable()
    assert_hermes_only_runs_for_genuine_ambiguity_and_sends_no_labels()
    assert_invalid_hermes_response_falls_back_deterministically()
    assert_validated_dynamic_run_builds_private_shadow_artifact()
    assert_validation_quarantine_and_exact_snapshot_gates_fail_closed()
    assert_metadata_only_and_verified_private_leaks_fail_closed()
    assert_output_collision_and_source_tamper_are_rejected()
    print("Real-device dynamic goal candidate checks ok")


def _evidence(
    labels: list[str],
    *,
    package: str = "com.example.video",
    sensitivity: tuple[str, ...] = (),
    metadata_only: tuple[str, ...] = (),
    auth: tuple[str, ...] = (),
) -> AppEvidence:
    return AppEvidence(
        app_package=package,
        version_name="1.0",
        version_code="10",
        version_key="code:10|name:1.0",
        sensitivity_categories=sensitivity,
        semantic_values=tuple(
            SemanticValue(value=value, screen_id="screen-safe", element_id=f"element-{index}")
            for index, value in enumerate(labels)
        ),
        verified_redacted_screen_ids=("screen-safe",) if labels else (),
        metadata_only_screen_ids=metadata_only,
        authentication_boundary_screen_ids=auth,
    )


def _by_family(result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {item["family_id"]: item for item in result["goal_candidates"]}


def assert_deterministic_applicability_and_subscription_chain() -> None:
    result = generate_app_candidate_set(
        _evidence(
            [
                "구독 관리",
                "요금제 변경",
                "자동결제 해제",
                "구독 해지",
                "고객센터",
            ]
        ),
        FAMILIES,
    )
    candidates = _by_family(result)
    for family_id in (
        "subscription_manage",
        "subscription_change",
        "autopay_off",
        "subscription_cancel",
        "customer_support",
    ):
        assert candidates[family_id]["applicability_state"] == "applicable"
        assert candidates[family_id]["evidence_signal_ids"]
    assert candidates["subscription_cancel"]["terminal_action_owner"] == "user"
    assert all(not item["final_action_auto_click_allowed"] for item in candidates.values())
    assert all(not item["unsafe_action_auto_click_allowed"] for item in candidates.values())
    assert [item["family_id"] for item in result["subscription_chain"]] == [
        "subscription_manage",
        "subscription_change",
        "autopay_off",
        "subscription_cancel",
    ]
    assert result["hermes_k_exaone"]["eligible_ambiguity"] is True
    assert result["hermes_k_exaone"]["deterministic_fallback_used"] is True


def assert_metadata_only_and_authentication_boundaries_never_infer_semantics() -> None:
    result = generate_app_candidate_set(
        _evidence([], metadata_only=("screen-private",), auth=("screen-private",)),
        FAMILIES,
    )
    candidates = _by_family(result)
    assert candidates["subscription_cancel"]["applicability_state"] == "authentication_boundary"
    assert candidates["login"]["applicability_state"] == "authentication_boundary"
    assert candidates["signup"]["applicability_state"] == "unverified"
    assert result["evidence_summary"]["metadata_only_semantics_used"] == 0
    assert result["evidence_summary"]["verified_semantic_value_count"] == 0
    assert result["hermes_k_exaone"]["attempted"] is False


def assert_mixed_authentication_and_post_auth_screens_are_family_scoped() -> None:
    evidence = AppEvidence(
        app_package="com.example.mixed",
        version_name="1.0",
        version_code="10",
        version_key="code:10|name:1.0",
        sensitivity_categories=(),
        semantic_values=(
            SemanticValue("sign up", "screen-public", "element-signup"),
            SemanticValue("customer support", "screen-public", "element-support"),
            SemanticValue(
                "manage subscription", "screen-post-auth", "element-manage"
            ),
            SemanticValue(
                "cancel subscription", "screen-auth", "element-cancel-wall"
            ),
        ),
        verified_redacted_screen_ids=(
            "screen-auth",
            "screen-public",
            "screen-post-auth",
        ),
        metadata_only_screen_ids=(),
        authentication_boundary_screen_ids=("screen-auth",),
    )
    result = generate_app_candidate_set(evidence, FAMILIES)
    candidates = _by_family(result)

    assert candidates["signup"]["applicability_state"] == "applicable"
    assert candidates["signup"]["source_screen_ids"] == ["screen-public"]
    assert candidates["customer_support"]["applicability_state"] == "applicable"
    assert candidates["customer_support"]["source_screen_ids"] == ["screen-public"]
    assert candidates["subscription_manage"]["applicability_state"] == "applicable"
    assert candidates["subscription_manage"]["source_screen_ids"] == [
        "screen-post-auth"
    ]
    assert (
        candidates["subscription_cancel"]["applicability_state"]
        == "authentication_boundary"
    )
    assert candidates["subscription_cancel"]["source_screen_ids"] == ["screen-auth"]
    assert candidates["logout"]["applicability_state"] == "authentication_boundary"
    assert candidates["public_document_issuance"]["applicability_state"] == "unverified"
    assert all(
        item["provenance"] == "real_device_observation_candidate"
        for item in candidates.values()
    )
    assert all(
        item["review_status"] == "unreviewed_candidate"
        for item in candidates.values()
    )
    assert all(item["route_lifecycle"] == "shadow" for item in candidates.values())
    assert all(not item["serving_allowed"] for item in candidates.values())
    assert all(not item["final_action_auto_click_allowed"] for item in candidates.values())
    assert all(not item["unsafe_action_auto_click_allowed"] for item in candidates.values())
    assert result["hermes_k_exaone"]["raw_menu_semantics_sent"] is False


def assert_sensitive_scope_restricts_transactional_candidates() -> None:
    reranker_calls = 0

    def forbidden_sensitive_reranker(_request: Mapping[str, Any]) -> Mapping[str, Any]:
        nonlocal reranker_calls
        reranker_calls += 1
        raise AssertionError("sensitive candidates must remain local-only")

    result = generate_app_candidate_set(
        _evidence(
            ["고객센터", "주문 취소", "보험금 청구", "보안 설정"],
            package="com.example.bank",
            sensitivity=("finance",),
        ),
        FAMILIES,
        hermes_reranker=forbidden_sensitive_reranker,
    )
    candidates = _by_family(result)
    assert candidates["customer_support"]["applicability_state"] == "applicable"
    assert candidates["security_settings"]["applicability_state"] == "applicable"
    for family_id in ("order_cancel_refund", "payment_methods"):
        assert candidates[family_id]["applicability_state"] == "unverified"
        assert candidates[family_id]["restriction_reason_code"] == "sensitive_scope_forbidden"
        assert candidates[family_id]["evidence_signal_ids"] == []
    assert candidates["insurance_claim"]["applicability_state"] == "applicable"
    assert candidates["insurance_claim"]["terminal_policy"] == "user_boundary"
    assert candidates["insurance_claim"]["terminal_action_owner"] == "user"
    assert candidates["insurance_claim"]["final_action_auto_click_allowed"] is False
    assert reranker_calls == 0
    assert result["hermes_k_exaone"]["attempted"] is False
    assert result["hermes_k_exaone"]["fallback_reason_code"] == "sensitive_local_only"
    assert result["hermes_k_exaone"]["external_api_transfer_count"] == 0


def assert_sensitive_local_signal_ids_make_insurance_applicable() -> None:
    evidence = _evidence(
        [],
        package="ni.mh.android.launcher",
        sensitivity=("finance", "health_medical"),
        metadata_only=("screen-insurance",),
    )
    evidence = AppEvidence(
        **{
            **evidence.__dict__,
            "local_signal_evidence": (
                LocalSignalEvidence(
                    family_id="insurance_contract_lookup",
                    signal_ids=("insurance.contract_lookup",),
                    screen_id="screen-insurance",
                    element_id="adb_1234567890abcdef",
                    semantic_commitment_sha256="a" * 64,
                    source_metric_id="metric_sensitive_signal_unit",
                    source_event_sequence=1,
                    source_metric_payload_sha256="b" * 64,
                    action_guard_sha256="c" * 64,
                    terminal_policy="user_boundary",
                    control_bucket="clickable",
                    auto_navigation_allowed=True,
                ),
            ),
        }
    )
    result = generate_app_candidate_set(evidence, FAMILIES)
    candidate = _by_family(result)["insurance_contract_lookup"]
    assert candidate["applicability_state"] == "applicable"
    assert candidate["terminal_policy"] == "user_boundary"
    assert candidate["terminal_action_owner"] == "user"
    assert candidate["evidence_signal_ids"] == ["insurance.contract_lookup"]
    assert candidate["source_screen_ids"] == ["screen-insurance"]
    assert candidate["source_element_ids"] == ["adb_1234567890abcdef"]
    assert candidate["evidence_source_mode"] == "sensitive_local_signal_ids"
    assert candidate["local_signal_evidence_count"] == 1
    assert result["evidence_summary"]["sensitive_local_signal_evidence_count"] == 1


def assert_explicit_negative_evidence_is_not_applicable() -> None:
    result = generate_app_candidate_set(
        _evidence(["활성 구독 없음", "예약 내역이 없습니다"]), FAMILIES
    )
    candidates = _by_family(result)
    assert candidates["subscription_manage"]["applicability_state"] == "not_applicable"
    assert candidates["subscription_cancel"]["applicability_state"] == "not_applicable"
    assert candidates["flight_booking_lookup"]["applicability_state"] == "not_applicable"
    assert candidates["flight_booking_cancel"]["applicability_state"] == "not_applicable"


def assert_hermes_only_runs_for_genuine_ambiguity_and_sends_no_labels() -> None:
    requests: list[Mapping[str, Any]] = []

    def reranker(request: Mapping[str, Any]) -> Mapping[str, Any]:
        requests.append(request)
        body = json.dumps(request, ensure_ascii=False)
        assert "구독 관리" in body
        assert "요금제 변경" in body
        assert "private.person@example.com" not in body
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "rank_goal_candidates",
                        "arguments": json.dumps(
                            {
                                "ordered_family_ids": [
                                    "subscription_change",
                                    "subscription_manage",
                                ]
                            }
                        ),
                    }
                }
            ]
        }

    result = generate_app_candidate_set(
        _evidence(["구독 관리", "요금제 변경"]),
        FAMILIES,
        hermes_reranker=reranker,
    )
    assert len(requests) == 1
    assert result["hermes_k_exaone"]["used"] is True
    assert result["hermes_k_exaone"]["raw_menu_semantics_sent"] is False
    assert result["hermes_k_exaone"]["verified_redacted_menu_semantics_sent_count"] == 2
    assert result["goal_candidates"][0]["family_id"] == "subscription_change"

    requests.clear()
    unambiguous = generate_app_candidate_set(
        _evidence(["고객센터"]), FAMILIES, hermes_reranker=reranker
    )
    assert not requests
    assert unambiguous["hermes_k_exaone"]["fallback_reason_code"] == "not_ambiguous"


def assert_invalid_hermes_response_falls_back_deterministically() -> None:
    baseline = generate_app_candidate_set(
        _evidence(["구독 관리", "요금제 변경"]), FAMILIES
    )
    invalid = generate_app_candidate_set(
        _evidence(["구독 관리", "요금제 변경"]),
        FAMILIES,
        hermes_reranker=lambda _request: {
            "name": "rank_goal_candidates",
            "arguments": {
                "ordered_family_ids": ["invented_family", "subscription_manage"]
            },
        },
    )
    assert [item["family_id"] for item in invalid["goal_candidates"]] == [
        item["family_id"] for item in baseline["goal_candidates"]
    ]
    assert invalid["hermes_k_exaone"]["deterministic_fallback_used"] is True
    assert invalid["hermes_k_exaone"]["fallback_reason_code"] == "reranker_invalid_or_failed"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _snapshot_app(package: str, *, sensitivity: list[str] | None = None) -> dict[str, Any]:
    return {
        "package": package,
        "launchable_activity": ".MainActivity",
        "version_name": "1.0",
        "version_code": "10",
        "version_key": "code:10|name:1.0",
        "included": True,
        "decision_reason_code": "user_service_app",
        "sensitivity_categories": list(sensitivity or []),
        "sensitivity_handling": "heightened_metadata_only" if sensitivity else "standard_metadata_only",
        "change_status": "new",
        "observation_status": "unobserved",
    }


def _screen(
    package: str,
    screen_id: str,
    labels: list[str],
    *,
    metadata_only: bool = False,
    login_state: str = "unknown",
) -> dict[str, Any]:
    if metadata_only:
        return {
            "screen_id": screen_id,
            "app_package": package,
            "privacy_verified": False,
            "evidence_mode": "metadata_only",
            "contains_personal_data": True,
            "login_state": login_state,
        }
    return {
        "screen_id": screen_id,
        "app_package": package,
        "privacy_verified": True,
        "evidence_mode": "verified_metadata",
        "contains_personal_data": False,
        "accessibility_tree_redacted": True,
        "raw_artifacts_persisted": False,
        "login_state": login_state,
        "title_text": labels[0] if labels else None,
        "visible_texts": labels,
        "content_descriptions": [],
        "resource_ids": [],
    }


def _element(package: str, screen_id: str, element_id: str, label: str) -> dict[str, Any]:
    del package
    return {
        "screen_id": screen_id,
        "element_id": element_id,
        "privacy_verified": True,
        "evidence_mode": "verified_metadata",
        "text": label,
        "content_description": "",
        "inferred_label": "",
        "label": label,
        "resource_id": "com.example:id/menu",
        "class_name": "android.widget.TextView",
        "privacy_redacted": False,
        "password": False,
        "sensitive": False,
    }


def _metadata_element(screen_id: str, local_element_id: str) -> dict[str, Any]:
    return {
        "screen_id": screen_id,
        "element_id": f"{screen_id}:{local_element_id}",
        "ui_element_id": local_element_id,
        "privacy_verified": False,
        "evidence_mode": "metadata_only",
        "clickable": True,
        "enabled": True,
        "visible": True,
        "bounds": [10, 20, 100, 80],
    }


def _local_signal_metric(
    package: str,
    screen_id: str,
    local_element_id: str,
    *,
    family_id: str = "insurance_contract_lookup",
    signal_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "metric_id": "metric-local-insurance",
        "metric_dimension": "sensitive_local_goal_signal",
        "policy_event": "label_free_goal_signal_observed",
        "app_package": package,
        "goal_id": "goal-sensitive-local-unit",
        "screen_id": screen_id,
        "external_api_transfer_count": 0,
        "human_text_persisted": False,
        "local_signal_evidence": {
            "policy_version": "egl-sensitive-local-navigation.v1",
            "decision_source": "deterministic_local_transient_accessibility",
            "family_id": family_id,
            "matched_signal_ids": signal_ids or ["insurance.contract_lookup"],
            "selected_element_id": local_element_id,
            "semantic_commitment_sha256": "b" * 64,
            "terminal_policy": "user_boundary",
            "control_bucket": "clickable",
            "auto_navigation_allowed": True,
            "action_guard": {
                "policy_version": "egl-real-device-auto-action.v1",
                "evaluation_phase": "pre_execution",
                "action_type": "click",
                "allowed": True,
                "computed_final_or_consequential": False,
                "safe_menu_match": True,
                "reason": "physical_safe_menu_navigation",
            },
            "external_api_transfer_count": 0,
            "human_text_persisted": False,
        },
    }


def _create_run(
    root: Path,
    *,
    package: str = "com.example.video",
    screen_payloads: list[dict[str, Any]] | None = None,
    element_payloads: list[dict[str, Any]] | None = None,
    metric_payloads: list[dict[str, Any]] | None = None,
    sensitivity: list[str] | None = None,
) -> tuple[Path, Path, Path]:
    run = root / "run"
    run.mkdir(parents=True)
    app = _snapshot_app(package, sensitivity=sensitivity)
    snapshot = {
        "schema_version": 1,
        "snapshot_id": "inventory-unit-1",
        "provenance": "real_device_observation_candidate",
        "dataset_role": "real_device_observation_candidate",
        "review_status": "unreviewed_candidate",
        "route_lifecycle": "shadow",
        "canonical_catalog_mutation": False,
        "canonical_catalog": {
            "version": CANONICAL_CATALOG_VERSION,
            "sha256": CANONICAL_CATALOG_SHA256,
            "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
        },
        "device": {
            "serial": "R3CY204GDVE",
            "device_type": "physical_android",
            "is_emulator": False,
        },
        "included_apps": [app],
        "excluded_apps": [],
        "prioritized_apps": [],
        "summary": {"included_apps": 1, "excluded_apps": 0},
    }
    snapshot_path = root / "inventory.json"
    _write_json(snapshot_path, snapshot)
    manifest = {
        "run_id": "dynamic-unit-run",
        "status": "completed",
        "validation_profile": "dynamic_inventory",
        "provenance": "real_device_observation_candidate",
        "dataset_role": "real_device_observation_candidate",
        "review_status": "unreviewed_candidate",
        "route_lifecycle": "shadow",
        "canonical_mutation_allowed": False,
        "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
        "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
        "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
        "device_type": "physical_android",
        "device_serial": "R3CY204GDVE",
        "is_emulator": False,
        "raw_artifacts_persisted": False,
        "selected_packages": [package],
        "inventory_packages": [package],
        "inventory_snapshot": {
            "snapshot_id": snapshot["snapshot_id"],
            "path": str(snapshot_path.resolve()),
            "path_scope": "explicit_safe_file",
            "explicit_safe_file": True,
            "sha256": _sha(snapshot_path),
            "included_inventory": [app],
        },
        "safety": {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        },
        "version_policy": {
            "canonical": "V15_frozen",
            "v16_v20_promotion": "forbidden",
            "v21": "research_only_noncanonical",
            "v22_plus": "forbidden",
        },
    }
    _write_json(run / "manifest.json", manifest)
    _write_json(run / "checkpoint.json", {"run_id": manifest["run_id"]})
    family_path = root / "families.json"
    _write_json(family_path, _family_manifest())

    database = sqlite3.connect(run / "corpus.sqlite")
    try:
        database.execute(
            "CREATE TABLE screens (event_sequence INTEGER PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
        database.execute(
            "CREATE TABLE elements (event_sequence INTEGER PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
        database.execute(
            "CREATE TABLE metrics (event_sequence INTEGER PRIMARY KEY, payload_json TEXT NOT NULL)"
        )
        screens = screen_payloads or [
            _screen(package, "screen-safe", ["구독 관리", "구독 해지", "고객센터"])
        ]
        elements = element_payloads or [
            _element(package, "screen-safe", "element-sub", "구독 관리")
        ]
        for index, payload in enumerate(screens, 1):
            database.execute(
                "INSERT INTO screens VALUES (?, ?)",
                (index, json.dumps(payload, ensure_ascii=False)),
            )
        for index, payload in enumerate(elements, 1):
            database.execute(
                "INSERT INTO elements VALUES (?, ?)",
                (index, json.dumps(payload, ensure_ascii=False)),
            )
        for index, payload in enumerate(metric_payloads or [], 1):
            database.execute(
                "INSERT INTO metrics VALUES (?, ?)",
                (index, json.dumps(payload, ensure_ascii=False)),
            )
        database.commit()
    finally:
        database.close()
    graph = sqlite3.connect(run / "graph-candidate.sqlite")
    graph.execute("CREATE TABLE graph_shell (id TEXT)")
    graph.commit()
    graph.close()
    (run / "observations.jsonl").write_text("{}\n", encoding="utf-8")
    (run / "screens.jsonl").write_text("{}\n", encoding="utf-8")
    core_hashes = {
        filename: _sha(run / filename)
        for filename in GENERATOR.CORE_ARTIFACT_FILENAMES
    }
    _write_json(
        run / GENERATOR.VALIDATION_ATTESTATION_FILENAME,
        {
            "schema_version": 1,
            "status": "passed",
            "validator": "Validate-RealDeviceObservationCorpus.py",
            "run_id": manifest["run_id"],
            "provenance": "real_device_observation_candidate",
            "device_serial": "R3CY204GDVE",
            "is_emulator": False,
            "manifest_sha256": core_hashes["manifest.json"],
            "screens_sha256": core_hashes["screens.jsonl"],
            "core_artifact_sha256": core_hashes,
        },
    )
    return run, snapshot_path, family_path


def _with_validated_stub(function: Any) -> None:
    original = GENERATOR._validate_run
    GENERATOR._validate_run = lambda *_args, **_kwargs: {
        "ok": True,
        "error_count": 0,
        "errors": [],
    }
    try:
        function()
    finally:
        GENERATOR._validate_run = original


def assert_privacy_redaction_does_not_create_authentication_boundary() -> None:
    def run_test() -> None:
        with TemporaryDirectory(prefix="exitguide-goals-redacted-content-") as temporary:
            root = Path(temporary)
            package = "com.example.media"
            redacted = _element(
                package,
                "screen-personalized-content",
                "element-private-card",
                "[REDACTED]",
            )
            redacted["privacy_redacted"] = True
            run, snapshot, families = _create_run(
                root,
                package=package,
                screen_payloads=[
                    _screen(package, "screen-personalized-content", [])
                ],
                element_payloads=[redacted],
            )
            result = GENERATOR.generate_goal_candidates(
                run,
                snapshot,
                repo_root=ROOT,
                observation_root=root,
                family_manifest_path=families,
            )
            artifact = json.loads(
                Path(result["output_path"]).read_text(encoding="utf-8")
            )
            app = artifact["apps"][0]
            assert app["evidence_summary"]["authentication_boundary_screen_count"] == 0
            assert {
                item["applicability_state"] for item in app["goal_candidates"]
            } == {"unverified"}
            assert all(
                item["evidence_signal_ids"] == []
                for item in app["goal_candidates"]
            )

    _with_validated_stub(run_test)


def assert_validated_dynamic_run_builds_private_shadow_artifact() -> None:
    def run_test() -> None:
        with TemporaryDirectory(prefix="exitguide-goals-valid-") as temporary:
            root = Path(temporary)
            run, snapshot, families = _create_run(root)
            source_before = {
                path.name: _sha(path)
                for path in (
                    run / "manifest.json",
                    run / "checkpoint.json",
                    run / "corpus.sqlite",
                    run / "graph-candidate.sqlite",
                    snapshot,
                    families,
                )
            }
            result = GENERATOR.generate_goal_candidates(
                run,
                snapshot,
                repo_root=ROOT,
                observation_root=root,
                family_manifest_path=families,
            )
            assert result["ok"] is True
            artifact = json.loads((run / "goal-candidates.json").read_text(encoding="utf-8"))
            assert artifact["provenance"] == "real_device_observation_candidate"
            assert artifact["review_status"] == "unreviewed_candidate"
            assert artifact["route_lifecycle"] == "shadow"
            assert artifact["serving_allowed"] is False
            expected_policy = {
                "version": GOAL_CANDIDATE_POLICY_VERSION,
                "sha256": GOAL_CANDIDATE_POLICY_SHA256,
            }
            assert artifact["goal_candidate_policy"] == expected_policy
            assert artifact["evidence_policy"][
                "goal_candidate_policy_version"
            ] == GOAL_CANDIDATE_POLICY_VERSION
            assert artifact["evidence_policy"][
                "goal_candidate_policy_sha256"
            ] == GOAL_CANDIDATE_POLICY_SHA256
            assert artifact["apps"][0]["goal_candidate_policy"] == expected_policy
            assert artifact["canonical_catalog"]["version"] == "15.0.0"
            assert artifact["version_policy"]["v16_v20_promotion"] == "forbidden"
            assert artifact["version_policy"]["v21"] == "research_only_noncanonical"
            assert artifact["version_policy"]["v22_plus"] == "forbidden"
            assert artifact["safety"]["unsafe_auto_click_count"] == 0
            assert artifact["safety"]["final_action_auto_click_count"] == 0
            combined = json.dumps(artifact, ensure_ascii=False)
            assert "구독 관리" not in combined
            assert "구독 해지" not in combined
            assert "고객센터" not in combined
            assert artifact["apps"][0]["evidence_summary"]["metadata_only_semantics_used"] == 0
            assert {
                path.name: _sha(path)
                for path in (
                    run / "manifest.json",
                    run / "checkpoint.json",
                    run / "corpus.sqlite",
                    run / "graph-candidate.sqlite",
                    snapshot,
                    families,
                )
            } == source_before

    _with_validated_stub(run_test)


def assert_sensitive_local_metric_builds_insurance_artifact_and_rejects_tampering() -> None:
    package = "ni.mh.android.launcher"
    screen_id = "screen-insurance-metadata"
    element_id = "adb_1234567890abcdef"

    def build(root: Path, metric: dict[str, Any]) -> dict[str, Any]:
        run, snapshot, families = _create_run(
            root,
            package=package,
            sensitivity=["finance", "health_medical"],
            screen_payloads=[
                _screen(package, screen_id, [], metadata_only=True)
            ],
            element_payloads=[_metadata_element(screen_id, element_id)],
            metric_payloads=[metric],
        )
        return GENERATOR.generate_goal_candidates(
            run,
            snapshot,
            repo_root=ROOT,
            observation_root=root,
            family_manifest_path=families,
        )

    def run_test() -> None:
        with TemporaryDirectory(prefix="exitguide-goals-sensitive-local-") as temporary:
            root = Path(temporary)
            result = build(
                root,
                _local_signal_metric(package, screen_id, element_id),
            )
            artifact = json.loads(
                Path(result["output_path"]).read_text(encoding="utf-8")
            )
            app = artifact["apps"][0]
            candidate = next(
                item
                for item in app["goal_candidates"]
                if item["family_id"] == "insurance_contract_lookup"
            )
            assert candidate["applicability_state"] == "applicable"
            assert candidate["terminal_policy"] == "user_boundary"
            assert candidate["terminal_action_owner"] == "user"
            assert candidate["evidence_source_mode"] == "sensitive_local_signal_ids"
            assert candidate["evidence_signal_ids"] == ["insurance.contract_lookup"]
            assert len(candidate["sensitive_evidence_refs"]) == 1
            evidence_ref = candidate["sensitive_evidence_refs"][0]
            assert evidence_ref["source_event_sequence"] == 1
            assert len(evidence_ref["source_metric_payload_sha256"]) == 64
            assert len(evidence_ref["action_guard_sha256"]) == 64
            attestation = app["sensitive_evidence_attestation"]
            assert attestation["source_event_count"] == 1
            assert attestation["ordered_event_refs"] == [
                {
                    "source_metric_id": evidence_ref["source_metric_id"],
                    "source_event_sequence": evidence_ref["source_event_sequence"],
                    "source_metric_payload_sha256": evidence_ref[
                        "source_metric_payload_sha256"
                    ],
                }
            ]
            assert len(attestation["evidence_root_sha256"]) == 64
            assert app["evidence_summary"]["metadata_only_semantics_used"] == 0
            assert app["evidence_summary"]["sensitive_local_signal_evidence_count"] == 1
            assert app["hermes_k_exaone"]["external_api_transfer_count"] == 0

        tamper_cases: list[tuple[str, Any, str]] = [
            (
                "unknown outer raw field",
                lambda metric: metric.__setitem__(
                    "raw_accessibility_label", "private text"
                ),
                "sensitive_local_signal_metric_shape_invalid",
            ),
            (
                "unknown raw field",
                lambda metric: metric["local_signal_evidence"].__setitem__(
                    "raw_label", "보험 계약 조회"
                ),
                "sensitive_local_signal_shape_invalid",
            ),
            (
                "API transfer",
                lambda metric: metric.__setitem__("external_api_transfer_count", 1),
                "sensitive_local_signal_metric_invalid",
            ),
            (
                "signal mismatch",
                lambda metric: metric["local_signal_evidence"].__setitem__(
                    "matched_signal_ids", ["insurance.claim"]
                ),
                "sensitive_local_signal_allowlist_invalid",
            ),
            (
                "element mismatch",
                lambda metric: metric["local_signal_evidence"].__setitem__(
                    "selected_element_id", "adb_ffffffffffffffff"
                ),
                "sensitive_local_signal_element_invalid",
            ),
            (
                "screen mismatch",
                lambda metric: metric.__setitem__("screen_id", "screen-missing"),
                "sensitive_local_signal_source_invalid",
            ),
        ]
        for ordinal, (_name, mutate, expected) in enumerate(tamper_cases):
            with TemporaryDirectory(
                prefix=f"exitguide-goals-sensitive-tamper-{ordinal}-"
            ) as temporary:
                metric = _local_signal_metric(package, screen_id, element_id)
                mutate(metric)
                try:
                    build(Path(temporary), metric)
                except GENERATOR.GoalCandidateBuildError as error:
                    assert str(error) == expected, (_name, error)
                else:
                    raise AssertionError(f"sensitive local tamper accepted: {_name}")

    _with_validated_stub(run_test)


def assert_validation_quarantine_and_exact_snapshot_gates_fail_closed() -> None:
    with TemporaryDirectory(prefix="exitguide-goals-gates-") as temporary:
        root = Path(temporary)
        run, snapshot, families = _create_run(root)
        original = GENERATOR._validate_run
        GENERATOR._validate_run = lambda *_args, **_kwargs: {
            "ok": False,
            "errors": [{"code": "source_invalid", "message": "private detail"}],
        }
        try:
            try:
                GENERATOR.generate_goal_candidates(
                    run, snapshot, observation_root=root, family_manifest_path=families
                )
            except GENERATOR.GoalCandidateBuildError as error:
                assert str(error) == "validated_dynamic_run_required:source_invalid"
            else:
                raise AssertionError("unvalidated run was accepted")
        finally:
            GENERATOR._validate_run = original

    def run_test() -> None:
        with TemporaryDirectory(prefix="exitguide-goals-quarantine-") as temporary:
            root = Path(temporary)
            run, snapshot, families = _create_run(root)
            (run / "QUARANTINED.json").write_text(
                '{"reason":"private-sentinel@example.invalid"}', encoding="utf-8"
            )
            try:
                GENERATOR.generate_goal_candidates(
                    run, snapshot, observation_root=root, family_manifest_path=families
                )
            except GENERATOR.GoalCandidateBuildError as error:
                assert str(error) == "source_run_quarantined"
                assert "private-sentinel" not in str(error)
            else:
                raise AssertionError("quarantined run was accepted")

        with TemporaryDirectory(prefix="exitguide-goals-snapshot-") as temporary:
            root = Path(temporary)
            run, snapshot, families = _create_run(root)
            other = root / "other.json"
            other.write_bytes(snapshot.read_bytes())
            try:
                GENERATOR.generate_goal_candidates(
                    run, other, observation_root=root, family_manifest_path=families
                )
            except GENERATOR.GoalCandidateBuildError as error:
                assert str(error) == "exact_inventory_snapshot_required"
            else:
                raise AssertionError("non-pinned inventory snapshot was accepted")

        with TemporaryDirectory(prefix="exitguide-goals-marker-") as temporary:
            root = Path(temporary)
            run, snapshot, families = _create_run(root)
            (run / "observations.jsonl").write_text(
                '{"post_validation":"tamper"}\n', encoding="utf-8"
            )
            try:
                GENERATOR.generate_goal_candidates(
                    run, snapshot, observation_root=root, family_manifest_path=families
                )
            except GENERATOR.GoalCandidateBuildError as error:
                assert str(error) == "validation_attestation_invalid"
            else:
                raise AssertionError("post-validation core artifact tamper was accepted")

    _with_validated_stub(run_test)


def assert_metadata_only_and_verified_private_leaks_fail_closed() -> None:
    def run_test() -> None:
        with TemporaryDirectory(prefix="exitguide-goals-meta-leak-") as temporary:
            root = Path(temporary)
            package = "com.example.video"
            screen = _screen(package, "screen-private", [], metadata_only=True)
            screen["visible_texts"] = ["forbidden private semantic"]
            run, snapshot, families = _create_run(
                root, screen_payloads=[screen], element_payloads=[]
            )
            try:
                GENERATOR.generate_goal_candidates(
                    run, snapshot, observation_root=root, family_manifest_path=families
                )
            except GENERATOR.GoalCandidateBuildError as error:
                assert str(error) == "metadata_only_screen_semantic_leak"
                assert "forbidden" not in str(error)
            else:
                raise AssertionError("metadata-only semantic leak was accepted")

        with TemporaryDirectory(prefix="exitguide-goals-private-leak-") as temporary:
            root = Path(temporary)
            package = "com.example.video"
            private_value = "private.person@example.com"
            run, snapshot, families = _create_run(
                root,
                screen_payloads=[
                    _screen(package, "screen-safe", [private_value, "구독 관리"])
                ],
                element_payloads=[],
            )
            try:
                GENERATOR.generate_goal_candidates(
                    run, snapshot, observation_root=root, family_manifest_path=families
                )
            except GENERATOR.GoalCandidateBuildError as error:
                assert str(error) == "verified_source_privacy_rejected:email"
                assert private_value not in str(error)
            else:
                raise AssertionError("private verified semantic was accepted")

    _with_validated_stub(run_test)


def assert_output_collision_and_source_tamper_are_rejected() -> None:
    def run_test() -> None:
        with TemporaryDirectory(prefix="exitguide-goals-collision-") as temporary:
            root = Path(temporary)
            run, snapshot, families = _create_run(root)
            GENERATOR.generate_goal_candidates(
                run, snapshot, observation_root=root, family_manifest_path=families
            )
            try:
                GENERATOR.generate_goal_candidates(
                    run, snapshot, observation_root=root, family_manifest_path=families
                )
            except GENERATOR.GoalCandidateBuildError as error:
                assert str(error) == "output_exists_without_force"
            else:
                raise AssertionError("existing artifact was silently overwritten")

        with TemporaryDirectory(prefix="exitguide-goals-tamper-") as temporary:
            root = Path(temporary)
            run, snapshot, families = _create_run(root)
            snapshot_value = json.loads(snapshot.read_text(encoding="utf-8"))
            snapshot_value["included_apps"][0]["version_code"] = "11"
            _write_json(snapshot, snapshot_value)
            try:
                GENERATOR.generate_goal_candidates(
                    run, snapshot, observation_root=root, family_manifest_path=families
                )
            except GENERATOR.GoalCandidateBuildError as error:
                assert str(error) == "snapshot_hash_mismatch"
            else:
                raise AssertionError("tampered inventory snapshot was accepted")

    _with_validated_stub(run_test)


if __name__ == "__main__":
    main()
