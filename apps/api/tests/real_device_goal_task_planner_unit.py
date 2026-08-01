from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.services.emulator_observation_corpus import (
    CANONICAL_CATALOG_SHA256,
    CANONICAL_CATALOG_VERSION,
    CANONICAL_EQUIVALENCE_SHA256,
)
from app.services.real_device_goal_task_planner import (
    GoalTaskPlanningError,
    plan_applicable_goals,
)
from app.services.real_device_goal_candidates import (
    GOAL_CANDIDATE_POLICY_SHA256,
    GOAL_CANDIDATE_POLICY_VERSION,
)


PROVENANCE = "real_device_observation_candidate"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _fixture(
    root: Path,
    *,
    state: str = "applicable",
    family_id: str = "subscription_manage",
    terminal_policy: str = "navigation_only",
    manifest_terminal_policy: str | None = None,
    sensitivity_categories: list[str] | None = None,
) -> tuple[Path, Path, Path]:
    run = root / "run-one"
    run.mkdir()
    snapshot_path = root / "inventory.json"
    family_path = root / "families.json"
    categories = list(sensitivity_categories or [])
    snapshot_id = "snapshot-one"
    version_key = "code:7|name:1.2.3"
    snapshot = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "provenance": PROVENANCE,
        "dataset_role": PROVENANCE,
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
            "is_emulator": False,
            "device_type": "physical_android",
        },
        "included_apps": [
            {
                "package": "com.example.service",
                "included": True,
                "version_name": "1.2.3",
                "version_code": "7",
                "version_key": version_key,
                "sensitivity_categories": categories,
                "sensitivity_handling": (
                    "heightened_metadata_only" if categories else "standard_metadata_only"
                ),
            }
        ],
    }
    _write_json(snapshot_path, snapshot)
    labels = {
        "subscription_manage": "구독 관리",
        "payment_methods": "결제수단 관리",
        "insurance_contract_lookup": "보험 계약 조회",
    }
    _write_json(
        family_path,
        {
            "required_goal_families": [
                {
                    "family_id": family_id,
                    "label_ko": labels[family_id],
                    "terminal_policy": manifest_terminal_policy or terminal_policy,
                }
            ],
            "supplemental_goal_families": [],
        },
    )
    manifest = {
        "run_id": "run-one",
        "selected_packages": ["com.example.service"],
        "status": "completed",
        "validation_profile": "dynamic_inventory",
        "collection_mode": "capture_only",
        "provenance": PROVENANCE,
        "dataset_role": PROVENANCE,
        "review_status": "unreviewed_candidate",
        "route_lifecycle": "shadow",
        "canonical_mutation_allowed": False,
        "is_emulator": False,
        "device_serial": "R3CY204GDVE",
        "safety": {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        },
    }
    _write_json(run / "manifest.json", manifest)
    _write_json(run / "checkpoint.json", {"run_id": "run-one"})
    sensitive_refs: list[dict[str, Any]] = []
    if categories:
        screen_id = "screen-sensitive-one"
        local_element_id = "adb_1234567890abcdef"
        connection = sqlite3.connect(run / "corpus.sqlite")
        try:
            for table in ("screens", "elements", "metrics"):
                connection.execute(
                    f"CREATE TABLE {table} (event_sequence INTEGER PRIMARY KEY, payload_json TEXT NOT NULL)"
                )
            screen = {
                "screen_id": screen_id,
                "app_package": "com.example.service",
                "privacy_verified": False,
                "evidence_mode": "metadata_only",
                "contains_personal_data": True,
                "login_state": "unknown",
            }
            connection.execute(
                "INSERT INTO screens VALUES (?, ?)",
                (1, json.dumps(screen, ensure_ascii=False)),
            )
            if family_id == "insurance_contract_lookup":
                element = {
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
                guard = {
                    "policy_version": "egl-real-device-auto-action.v1",
                    "evaluation_phase": "pre_execution",
                    "action_type": "click",
                    "allowed": True,
                    "computed_final_or_consequential": False,
                    "safe_menu_match": True,
                    "reason": "physical_safe_menu_navigation",
                }
                local_evidence = {
                    "policy_version": "egl-sensitive-local-navigation.v1",
                    "decision_source": "deterministic_local_transient_accessibility",
                    "family_id": family_id,
                    "matched_signal_ids": ["insurance.contract_lookup"],
                    "selected_element_id": local_element_id,
                    "semantic_commitment_sha256": "b" * 64,
                    "terminal_policy": "user_boundary",
                    "control_bucket": "clickable",
                    "auto_navigation_allowed": True,
                    "action_guard": guard,
                    "external_api_transfer_count": 0,
                    "human_text_persisted": False,
                }
                metric = {
                    "metric_id": "metric-sensitive-one",
                    "metric_dimension": "sensitive_local_goal_signal",
                    "policy_event": "label_free_goal_signal_observed",
                    "app_package": "com.example.service",
                    "goal_id": "goal-sensitive-one",
                    "screen_id": screen_id,
                    "local_signal_evidence": local_evidence,
                    "external_api_transfer_count": 0,
                    "human_text_persisted": False,
                }
                connection.execute(
                    "INSERT INTO elements VALUES (?, ?)",
                    (1, json.dumps(element, ensure_ascii=False)),
                )
                connection.execute(
                    "INSERT INTO metrics VALUES (?, ?)",
                    (1, json.dumps(metric, ensure_ascii=False)),
                )
                sensitive_refs.append(
                    {
                        "source_metric_id": metric["metric_id"],
                        "source_event_sequence": 1,
                        "source_metric_payload_sha256": _canonical_sha256(metric),
                        "source_screen_id": screen_id,
                        "source_element_id": local_element_id,
                        "policy_version": "egl-sensitive-local-navigation.v1",
                        "family_id": family_id,
                        "signal_ids": ["insurance.contract_lookup"],
                        "semantic_commitment_sha256": "b" * 64,
                        "action_guard_sha256": _canonical_sha256(guard),
                        "terminal_policy": "user_boundary",
                        "control_bucket": "clickable",
                        "auto_navigation_allowed": True,
                    }
                )
            connection.commit()
        finally:
            connection.close()
    else:
        (run / "corpus.sqlite").write_bytes(b"candidate-corpus")
    (run / "graph-candidate.sqlite").write_bytes(b"candidate-graph")
    (run / "observations.jsonl").write_text("{}\n", encoding="utf-8")
    (run / "screens.jsonl").write_text("{}\n", encoding="utf-8")
    core_hashes = {
        filename: _sha256(run / filename)
        for filename in (
            "manifest.json",
            "checkpoint.json",
            "corpus.sqlite",
            "graph-candidate.sqlite",
            "observations.jsonl",
            "screens.jsonl",
        )
    }
    _write_json(
        run / "VALIDATED.json",
        {
            "schema_version": 1,
            "status": "passed",
            "run_id": "run-one",
            "provenance": PROVENANCE,
            "device_serial": "R3CY204GDVE",
            "is_emulator": False,
            "manifest_sha256": core_hashes["manifest.json"],
            "screens_sha256": core_hashes["screens.jsonl"],
            "core_artifact_sha256": core_hashes,
        },
    )
    sensitive_attestation = (
        {
            "schema_version": 1,
            "policy_version": "egl-sensitive-local-navigation.v1",
            "source_event_count": len(sensitive_refs),
            "ordered_event_refs": [
                {
                    "source_metric_id": value["source_metric_id"],
                    "source_event_sequence": value["source_event_sequence"],
                    "source_metric_payload_sha256": value[
                        "source_metric_payload_sha256"
                    ],
                }
                for value in sensitive_refs
            ],
            "evidence_root_sha256": _canonical_sha256(sensitive_refs),
            "external_api_transfer_count": 0,
            "human_text_persisted": False,
        }
        if categories
        else None
    )
    candidate_id = (
        "goal_"
        + _canonical_sha256(
            {
                "package": "com.example.service",
                "version_key": version_key,
                "family_id": family_id,
            }
        )[:24]
        if categories
        else "goal_candidate_one"
    )
    artifact = {
        "schema_version": 1,
        "artifact_type": "dynamic_real_device_goal_candidates",
        "source_run_id": "run-one",
        "source_inventory_snapshot_id": snapshot_id,
        "source_sha256": {
            "manifest": _sha256(run / "manifest.json"),
            "checkpoint": _sha256(run / "checkpoint.json"),
            "corpus": _sha256(run / "corpus.sqlite"),
            "graph": _sha256(run / "graph-candidate.sqlite"),
            "snapshot": _sha256(snapshot_path),
            "family_manifest": _sha256(family_path),
        },
        "provenance": PROVENANCE,
        "dataset_role": PROVENANCE,
        "review_status": "unreviewed_candidate",
        "route_lifecycle": "shadow",
        "serving_allowed": False,
        "human_review_required": True,
        "goal_candidate_policy": {
            "version": GOAL_CANDIDATE_POLICY_VERSION,
            "sha256": GOAL_CANDIDATE_POLICY_SHA256,
        },
        "canonical_catalog": {
            "version": CANONICAL_CATALOG_VERSION,
            "sha256": CANONICAL_CATALOG_SHA256,
            "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "mutation_allowed": False,
        },
        "version_policy": {
            "canonical": "V15_frozen",
            "v16_v20_promotion": "forbidden",
            "v21": "research_only_noncanonical",
            "v22_plus": "forbidden",
        },
        "safety": {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
            "terminal_actions_owned_by_user": True,
        },
        "evidence_policy": {
            "goal_candidate_policy_version": GOAL_CANDIDATE_POLICY_VERSION,
            "goal_candidate_policy_sha256": GOAL_CANDIDATE_POLICY_SHA256,
            "semantic_source": "verified_redacted_accessibility_or_validated_label_free_local_signal_ids",
            "metadata_only_semantics_used": 0,
            "sensitive_local_policy_version": "egl-sensitive-local-navigation.v1",
            "raw_xml_read": False,
            "raw_screenshot_read": False,
        },
        "counts": {
            "inventory_app_count": 1,
            "selected_app_count": 1,
            "candidate_count": 1,
            "applicability_states": {state: 1},
        },
        "apps": [
            {
                "app_package": "com.example.service",
                "version_name": "1.2.3",
                "version_code": "7",
                "version_key": version_key,
                "sensitivity_categories": categories,
                "sensitive_scope_policy_applied": bool(categories),
                "sensitive_evidence_attestation": sensitive_attestation,
                "hermes_k_exaone": (
                    {
                        "attempted": False,
                        "used": False,
                        "external_api_transfer_count": 0,
                        "raw_menu_semantics_sent": False,
                        "request_semantics": "none_sensitive_local_only",
                    }
                    if categories
                    else {}
                ),
                "provenance": PROVENANCE,
                "review_status": "unreviewed_candidate",
                "route_lifecycle": "shadow",
                "serving_allowed": False,
                "human_review_required": True,
                "goal_candidate_policy": {
                    "version": GOAL_CANDIDATE_POLICY_VERSION,
                    "sha256": GOAL_CANDIDATE_POLICY_SHA256,
                },
                "goal_candidates": [
                    {
                        "candidate_id": candidate_id,
                        "family_id": family_id,
                        "applicability_state": state,
                        "terminal_policy": terminal_policy,
                        "rank": 1,
                        "confidence": (
                            1.0
                            if sensitive_refs
                            else 0.91
                            if state == "applicable"
                            else 0.0
                        ),
                        "terminal_action_owner": (
                            "user"
                            if terminal_policy
                            in {"user_boundary", "user_final_action", "mixed_user_owned"}
                            else "navigation_only"
                        ),
                        "evidence_signal_ids": (
                            ["insurance.contract_lookup"]
                            if sensitive_refs
                            else []
                        ),
                        "source_screen_ids": (
                            ["screen-sensitive-one"] if sensitive_refs else []
                        ),
                        "source_element_ids": (
                            ["adb_1234567890abcdef"] if sensitive_refs else []
                        ),
                        "local_signal_evidence_count": len(sensitive_refs),
                        "sensitive_evidence_refs": sensitive_refs,
                        "evidence_source_mode": (
                            "sensitive_local_signal_ids" if sensitive_refs else "none"
                        ),
                        "restriction_reason_code": (
                            "sensitive_scope_forbidden"
                            if categories and family_id not in {
                                "subscription_manage",
                                "insurance_contract_lookup",
                            }
                            else None
                        ),
                        "final_action_auto_click_allowed": False,
                        "unsafe_action_auto_click_allowed": False,
                        "human_review_required": True,
                        "provenance": PROVENANCE,
                        "review_status": "unreviewed_candidate",
                        "route_lifecycle": "shadow",
                        "serving_allowed": False,
                    }
                ],
            }
        ],
    }
    artifact_path = run / "goal-candidates.json"
    _write_json(artifact_path, artifact)
    return artifact_path, snapshot_path, family_path


def _expect_error(code: str, action: Any) -> None:
    try:
        action()
    except GoalTaskPlanningError as error:
        assert str(error) == code, (str(error), code)
    else:
        raise AssertionError(f"expected {code}")


def _mutate_sensitive_metric_and_rebind_source(
    artifact_path: Path, mutate: Any, *, event_sequence: int | None = None
) -> None:
    corpus = artifact_path.parent / "corpus.sqlite"
    connection = sqlite3.connect(corpus)
    try:
        sequence, raw = connection.execute(
            "SELECT event_sequence, payload_json FROM metrics ORDER BY event_sequence LIMIT 1"
        ).fetchone()
        payload = json.loads(raw)
        mutate(payload)
        replacement_sequence = event_sequence if event_sequence is not None else sequence
        connection.execute("DELETE FROM metrics")
        connection.execute(
            "INSERT INTO metrics VALUES (?, ?)",
            (replacement_sequence, json.dumps(payload, ensure_ascii=False)),
        )
        connection.commit()
    finally:
        connection.close()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["source_sha256"]["corpus"] = _sha256(corpus)
    _write_json(artifact_path, artifact)
    marker_path = artifact_path.parent / "VALIDATED.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["core_artifact_sha256"]["corpus.sqlite"] = _sha256(corpus)
    _write_json(marker_path, marker)


def main() -> None:
    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(Path(temporary))
        plan = plan_applicable_goals(artifact, snapshot, families)
        assert plan.source_run_id == "run-one"
        assert plan.state_counts == {"applicable": 1}
        assert len(plan.applicable) == 1
        goal = plan.applicable[0]
        assert goal.goal_text == "구독 관리"
        assert goal.family_id == "subscription_manage"
        assert goal.terminal_policy == "navigation_only"
        assert goal.version_key == "code:7|name:1.2.3"

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(Path(temporary))
        document = json.loads(artifact.read_text(encoding="utf-8"))
        document.pop("goal_candidate_policy")
        _write_json(artifact, document)
        _expect_error(
            "goal_artifact_governance_invalid",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(Path(temporary))
        document = json.loads(artifact.read_text(encoding="utf-8"))
        document["evidence_policy"]["goal_candidate_policy_sha256"] = "f" * 64
        _write_json(artifact, document)
        _expect_error(
            "goal_artifact_policy_stale",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    # A capture may intentionally select only one app from a larger exact
    # inventory snapshot. Planning is bound to manifest.selected_packages,
    # not forced to fabricate candidate rows for every unselected app.
    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(Path(temporary))
        snapshot_document = json.loads(snapshot.read_text(encoding="utf-8"))
        snapshot_document["included_apps"].append(
            {
                "package": "com.example.unselected",
                "included": True,
                "version_name": "9.0",
                "version_code": "9",
                "version_key": "code:9|name:9.0",
                "sensitivity_categories": [],
                "sensitivity_handling": "standard_metadata_only",
            }
        )
        _write_json(snapshot, snapshot_document)
        artifact_document = json.loads(artifact.read_text(encoding="utf-8"))
        artifact_document["source_sha256"]["snapshot"] = _sha256(snapshot)
        artifact_document["counts"]["inventory_app_count"] = 2
        _write_json(artifact, artifact_document)
        plan = plan_applicable_goals(artifact, snapshot, families)
        assert [goal.app_package for goal in plan.applicable] == [
            "com.example.service"
        ]

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(Path(temporary))
        (artifact.parent / "corpus.sqlite").write_bytes(b"tampered")
        _expect_error(
            "source_hash_mismatch:corpus",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(Path(temporary))
        (artifact.parent / "observations.jsonl").write_text(
            '{"post_validation":"tamper"}\n', encoding="utf-8"
        )
        _expect_error(
            "validated_marker_mismatch",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(Path(temporary))
        document = json.loads(artifact.read_text(encoding="utf-8"))
        document["apps"][0]["goal_candidates"][0][
            "final_action_auto_click_allowed"
        ] = True
        _write_json(artifact, document)
        _expect_error(
            "goal_candidate_safety_or_governance_invalid",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(Path(temporary), state="unverified")
        _expect_error(
            "no_applicable_goal_candidates",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(
            Path(temporary),
            family_id="payment_methods",
            terminal_policy="navigation_only",
            sensitivity_categories=["finance"],
        )
        _expect_error(
            "sensitive_candidate_replay_mismatch",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(
            Path(temporary),
            family_id="insurance_contract_lookup",
            terminal_policy="user_boundary",
            manifest_terminal_policy="navigation_only",
            sensitivity_categories=["finance", "health_medical"],
        )
        plan = plan_applicable_goals(artifact, snapshot, families)
        assert len(plan.applicable) == 1
        goal = plan.applicable[0]
        assert goal.family_id == "insurance_contract_lookup"
        assert goal.terminal_policy == "user_boundary"
        assert goal.sensitivity_categories == ("finance", "health_medical")

    # The planner must not trust the generated JSON. It independently replays
    # the hashed source corpus and exact-compares every sensitive fact.
    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(
            Path(temporary),
            family_id="insurance_contract_lookup",
            terminal_policy="user_boundary",
            manifest_terminal_policy="navigation_only",
            sensitivity_categories=["finance", "health_medical"],
        )
        document = json.loads(artifact.read_text(encoding="utf-8"))
        document["apps"][0]["goal_candidates"][0]["applicability_state"] = "unverified"
        document["counts"]["applicability_states"] = {"unverified": 1}
        _write_json(artifact, document)
        _expect_error(
            "sensitive_candidate_replay_mismatch",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(
            Path(temporary),
            family_id="insurance_contract_lookup",
            terminal_policy="user_boundary",
            manifest_terminal_policy="navigation_only",
            sensitivity_categories=["finance", "health_medical"],
        )
        document = json.loads(artifact.read_text(encoding="utf-8"))
        document["apps"][0]["sensitive_evidence_attestation"][
            "evidence_root_sha256"
        ] = "0" * 64
        _write_json(artifact, document)
        _expect_error(
            "sensitive_evidence_attestation_mismatch",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    for name, mutate, sequence, expected in (
        (
            "neutralized_event",
            lambda metric: metric.__setitem__(
                "metric_dimension", "sensitive_local_policy"
            ),
            None,
            "sensitive_evidence_attestation_mismatch",
        ),
        (
            "signal",
            lambda metric: metric["local_signal_evidence"].__setitem__(
                "matched_signal_ids", ["insurance.claim"]
            ),
            None,
            "sensitive_replay_signal_allowlist_invalid",
        ),
        (
            "commitment",
            lambda metric: metric["local_signal_evidence"].__setitem__(
                "semantic_commitment_sha256", "c" * 64
            ),
            None,
            "sensitive_evidence_attestation_mismatch",
        ),
        (
            "event_sequence",
            lambda _metric: None,
            9,
            "sensitive_evidence_attestation_mismatch",
        ),
        (
            "raw_field",
            lambda metric: metric.__setitem__("raw_accessibility_label", "forbidden"),
            None,
            "sensitive_replay_metric_invalid",
        ),
    ):
        with TemporaryDirectory(prefix=f"planner-sensitive-{name}-") as temporary:
            artifact, snapshot, families = _fixture(
                Path(temporary),
                family_id="insurance_contract_lookup",
                terminal_policy="user_boundary",
                manifest_terminal_policy="navigation_only",
                sensitivity_categories=["finance", "health_medical"],
            )
            _mutate_sensitive_metric_and_rebind_source(
                artifact, mutate, event_sequence=sequence
            )
            _expect_error(
                expected,
                lambda: plan_applicable_goals(artifact, snapshot, families),
            )

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(
            Path(temporary),
            family_id="insurance_contract_lookup",
            terminal_policy="user_boundary",
            manifest_terminal_policy="navigation_only",
            sensitivity_categories=["finance", "health_medical"],
        )
        document = json.loads(artifact.read_text(encoding="utf-8"))
        document["apps"][0]["goal_candidates"][0]["sensitive_evidence_refs"][0][
            "source_metric_payload_sha256"
        ] = "f" * 64
        _write_json(artifact, document)
        _expect_error(
            "sensitive_candidate_replay_mismatch",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    with TemporaryDirectory() as temporary:
        artifact, snapshot, families = _fixture(Path(temporary))
        document = json.loads(artifact.read_text(encoding="utf-8"))
        document["counts"]["candidate_count"] = 99
        _write_json(artifact, document)
        _expect_error(
            "goal_artifact_counts_mismatch",
            lambda: plan_applicable_goals(artifact, snapshot, families),
        )

    print("Real-device goal task planner checks ok")


if __name__ == "__main__":
    main()
