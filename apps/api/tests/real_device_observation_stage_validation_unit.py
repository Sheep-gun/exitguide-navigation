from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
TEST_ROOT = API_ROOT / "tests"
for value in (str(API_ROOT), str(TEST_ROOT)):
    if value not in sys.path:
        sys.path.insert(0, value)

import real_device_goal_task_planner_unit as PLANNER_FIXTURE  # noqa: E402
import real_device_observation_safety_unit as SAFETY_FIXTURE  # noqa: E402
from app.services.real_device_action_safety import evaluate_auto_action_guard  # noqa: E402
from app.services.real_device_goal_task_planner import plan_applicable_goals  # noqa: E402
from app.services.real_device_observation_corpus import (  # noqa: E402
    RealDeviceObservationCorpus,
)
from app.services.real_device_task_metrics import build_task_summary_metric  # noqa: E402


COLLECTOR = SAFETY_FIXTURE.COLLECTOR
VALIDATOR = SAFETY_FIXTURE.VALIDATOR


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _update_json(path: Path, update: Callable[[dict[str, Any]], None]) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    update(value)
    _write_json(path, value)


def _runtime_attestation() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "checked_at": "2026-07-31T00:00:00.000Z",
        "device": {
            "serial": COLLECTOR.EXPECTED_SERIAL,
            "model": "stage-test-device",
            "android_version": "16",
            "locale": "ko-KR",
            "device_type": "physical_android",
            "is_emulator": False,
        },
        "exitguide": {
            "package": COLLECTOR.EXITGUIDE_PACKAGE,
            "installed_for_user_0": True,
            "accessibility_component": COLLECTOR.EXITGUIDE_ACCESSIBILITY_COMPONENT,
            "accessibility_enabled": True,
            "overlay_appop": "allow",
        },
        "api": {
            "health_path": "/health",
            "status": "ok",
            "provider_status_path": "/v1/status",
            "llm_provider": "exaone",
            "provider_ready": True,
        },
    }


def _enrich_planner_source(root: Path) -> tuple[Path, Path, Path]:
    artifact_path, snapshot_path, family_path = PLANNER_FIXTURE._fixture(root)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    app = snapshot["included_apps"][0]
    app.update(
        {
            "launchable_activity": "com.example.service/.MainActivity",
            "decision_reason_code": "eligible_user_app",
            "change_status": "new",
            "observation_status": "unobserved_current_version",
        }
    )
    snapshot.update(
        {
            "canonical_catalog": COLLECTOR.EXPECTED_INVENTORY_CANONICAL,
            "device": {
                "serial": COLLECTOR.EXPECTED_SERIAL,
                "model": "stage-test-device",
                "android_version": "16",
                "locale": "ko-KR",
                "device_type": "physical_android",
                "is_emulator": False,
            },
            "discovered_at": "2026-07-31T00:00:00.000Z",
            "previous_snapshot_id": None,
            "excluded_apps": [],
            "prioritized_apps": [
                {
                    "priority_rank": 1,
                    "package": app["package"],
                    "version_key": app["version_key"],
                    "change_status": app["change_status"],
                    "observation_status": app["observation_status"],
                    "priority_reason": "new package",
                }
            ],
            "summary": {
                "discovered_apps": 1,
                "included_apps": 1,
                "excluded_apps": 0,
            },
        }
    )
    _write_json(snapshot_path, snapshot)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["source_sha256"]["snapshot"] = _sha256(snapshot_path)
    _write_json(artifact_path, artifact)
    # The source marker remains valid: it binds the source manifest and screens,
    # while source_sha256 independently binds this exact inventory snapshot.
    plan_applicable_goals(artifact_path, snapshot_path, family_path)
    return artifact_path, snapshot_path, family_path


def _append_directed_evidence(
    corpus: RealDeviceObservationCorpus,
    task: Any,
    *,
    version_candidate_id: str,
) -> None:
    corpus.append_run(
        {
            "run_observation_id": "directed-stage-run",
            "device_id": "physical-device-hash",
            "avd_name": "physical_android",
            "lifecycle_event": "started",
            "started_at": "2026-07-31T00:00:00Z",
        }
    )
    corpus.append_app(
        {
            "app_observation_id": "directed-app",
            "app_package": task.app_package,
            "app_name": task.app_name,
            "app_version": task.version_name,
            "version_name": task.version_name,
            "version_code": task.version_code,
            "version_candidate_id": version_candidate_id,
            "locale": "ko-KR",
            "status": "installed_observed",
        }
    )
    for screen_id, signature in (
        ("directed-screen-start", "directed-signature-start"),
        ("directed-screen-destination", "directed-signature-destination"),
    ):
        corpus.append_screen(
            {
                "screen_id": screen_id,
                "app_package": task.app_package,
                "app_name": task.app_name,
                "app_version": task.version_name,
                "locale": "ko-KR",
                "screen_signature": signature,
                "activity_name": ".MainActivity",
                "title_text": "Settings",
                "visible_texts": ["Settings"],
                "screen_type": "menu",
                "contains_personal_data": False,
                "collected_at": "2026-07-31T00:00:01Z",
            },
            privacy_verified=True,
        )
    corpus.append_element(
        {
            "element_id": "directed-element",
            "screen_id": "directed-screen-start",
            "text": "Settings",
            "content_description": "Settings",
            "resource_id": "com.example.service:id/settings",
            "class_name": "android.widget.TextView",
            "bounds": [0, 0, 100, 100],
            "clickable": True,
            "enabled": True,
            "risk_level": "low",
            "is_final_action": False,
            "evidence": {"source": "accessibility_metadata"},
        },
        privacy_verified=True,
    )
    guard = evaluate_auto_action_guard(
        "click",
        selected_label="Settings",
        element_labels=("Settings", "Settings"),
        resource_id="com.example.service:id/settings",
    )
    assert guard.allowed and not guard.computed_final_or_consequential
    corpus.append_transition(
        {
            "transition_id": "directed-transition",
            "source_screen_id": "directed-screen-start",
            "target_screen_id": "directed-screen-destination",
            "action_type": "click",
            "element_id": "directed-element",
            "ui_element_id": "directed-element",
            "selected_label": "Settings",
            "auto_action_guard": guard.evidence(),
            "outcome": "navigated",
            "success": True,
            "auto_executed": True,
            "unsafe_action": False,
            "is_final_action": False,
            "coordinates": [50, 50],
            "transition_time_ms": 100,
            "back_available": True,
            "is_loop": False,
        }
    )
    goal_id = "goal_" + COLLECTOR.stable_hash(
        {
            "package": task.app_package,
            "goal": task.goal_text,
            "candidate_id": task.candidate_id,
        },
        20,
    )
    corpus.append_goal(
        {
            "goal_id": goal_id,
            "app_package": task.app_package,
            "goal_text": task.goal_text,
            "status": "unreviewed_candidate",
            "terminal_confidence": 0.0,
            "evidence": {
                "source": COLLECTOR.PROVENANCE,
                "task_id": task.task_id,
                "sensitivity_categories": list(task.sensitivity_categories),
                "sensitivity_handling": task.sensitivity_handling or None,
                "version_key": task.version_key,
                "candidate_id": task.candidate_id,
                "family_id": task.family_id,
                "terminal_policy": task.terminal_policy,
                "source_run_id": task.source_run_id,
                "source_inventory_snapshot_id": task.source_inventory_snapshot_id,
                "confidence": task.confidence,
                "candidate_rank": task.candidate_rank,
                "source_artifact_sha256": task.source_artifact_sha256,
            },
        }
    )
    corpus.append_metric(
        {
            "metric_id": "directed-destination-policy",
            "metric_dimension": "policy",
            "app_package": task.app_package,
            "goal_id": goal_id,
            "phase": "destination_reached",
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }
    )
    summary = build_task_summary_metric(
        task_id=task.task_id,
        app_package=task.app_package,
        goal_id=goal_id,
        terminal_status="destination_reached",
        state={
            "action_count": 1,
            "scroll_count": 0,
            "back_count": 0,
            "elapsed_seconds": 1.0,
            "screen_visits": {"directed-signature-start": 1},
        },
        attempt_number=1,
        goal_candidate_id=task.candidate_id,
        goal_family_id=task.family_id,
        terminal_policy=task.terminal_policy,
    )
    summary.update(
        {
            "metric_id": "directed-task-summary",
            "source_goal_run_id": task.source_run_id,
            "source_inventory_snapshot_id": task.source_inventory_snapshot_id,
            "source_goal_artifact_sha256": task.source_artifact_sha256,
        }
    )
    corpus.append_metric(summary)

    connection = sqlite3.connect(corpus.graph_database_path)
    try:
        app_key = hashlib.sha256(
            f"{task.app_package}|{task.version_name}|ko-kr".encode("utf-8")
        ).hexdigest()[:20]
        connection.execute(
            "INSERT INTO universal_apps VALUES (?,?,?,?,?,?)",
            (
                app_key,
                task.app_package,
                task.version_name,
                "ko-KR",
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO universal_screens VALUES (?,?,?,?,?,?,?,?)",
            (
                "directed-graph-start",
                app_key,
                ".MainActivity",
                "Settings",
                "{}",
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:00Z",
                1,
            ),
        )
        connection.execute(
            "INSERT INTO universal_actions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "directed-graph-action",
                "directed-graph-start",
                "settings-key",
                "directed-element",
                "Settings",
                "button",
                "low",
                "menu navigation",
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:00Z",
                1,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    corpus.graph_repository.save_route(
        app_package=task.app_package,
        app_version=str(task.version_name),
        locale="ko-KR",
        goal_text=task.goal_text,
        target_function=task.family_id,
        start_screen_fingerprint="directed-graph-start",
        destination_screen_fingerprint="directed-graph-start",
        steps=[],
        confidence=float(task.confidence),
        provisional=True,
    )
    corpus.refresh_after_graph_write()


def _create_directed_run(root: Path) -> Path:
    source_root = root / "source"
    source_root.mkdir()
    artifact_path, snapshot_path, family_path = _enrich_planner_source(source_root)
    snapshot = COLLECTOR.load_dynamic_inventory_snapshot(snapshot_path)
    plan = plan_applicable_goals(artifact_path, snapshot_path, family_path)
    tasks = COLLECTOR.dynamic_goal_tasks(snapshot, plan)
    assert len(tasks) == 1
    task = tasks[0]
    run_id = "directed-stage-run"
    metadata = COLLECTOR.dynamic_inventory_manifest_metadata(
        snapshot,
        observation_root=root,
        run_id=run_id,
        selected_packages=[task.app_package],
    )
    metadata["selected_tasks"] = [asdict(task) | {"task_id": task.task_id}]
    metadata["exploration_stage"] = COLLECTOR.EXPLORATION_STAGE_GOAL_DIRECTED
    goal_plan = COLLECTOR.dynamic_goal_plan_manifest_metadata(
        plan,
        artifact_path=artifact_path,
        family_manifest_path=family_path,
        observation_root=root,
        tasks=tasks,
    )
    metadata["goal_candidate_plan"] = goal_plan
    run_dir = root / run_id
    corpus = RealDeviceObservationCorpus(run_dir, run_id=run_id)
    corpus.update_control_metadata(
        status="incomplete",
        app_statuses=[
            {"app_package": task.app_package, "status": "installed_observed"}
        ],
        device_serial=COLLECTOR.EXPECTED_SERIAL,
        collection_mode="safe_explore",
        validation_profile="dynamic_inventory",
        selected_packages=[task.app_package],
        inventory_packages=[task.app_package],
        inventory_snapshot=metadata,
        runtime_attestation=_runtime_attestation(),
        exploration_stage=COLLECTOR.EXPLORATION_STAGE_GOAL_DIRECTED,
        goal_candidate_plan=goal_plan,
    )
    version_candidate = metadata["version_candidates"][0]
    _append_directed_evidence(
        corpus, task, version_candidate_id=version_candidate["candidate_id"]
    )
    corpus.update_control_metadata(
        status="completed",
        app_statuses=[
            {"app_package": task.app_package, "status": "installed_observed"}
        ],
    )
    corpus.save_checkpoint(
        {
            "run_status": "completed",
            "completed_task_ids": [task.task_id],
            "current_task_id": None,
            "current_task": None,
            "task_attempt_numbers": {task.task_id: 1},
            "task_status": "destination_reached",
            "statuses": {task.task_id: "destination_reached"},
            "pending_action": None,
        }
    )
    with sqlite3.connect(corpus.database_path) as connection:
        screens = [
            str(row[0])
            for row in connection.execute(
                "SELECT payload_json FROM screens ORDER BY event_sequence"
            )
        ]
    (run_dir / "screens.jsonl").write_text(
        "".join(f"{row}\n" for row in screens), encoding="utf-8"
    )
    return run_dir


def _create_discovery_run(root: Path) -> Path:
    run_dir, _ = SAFETY_FIXTURE._create_dynamic_inventory_run(root)
    corpus = RealDeviceObservationCorpus(
        run_dir, run_id="dynamic-inventory-test", resume=True
    )
    manifest = json.loads(corpus.manifest_path.read_text(encoding="utf-8"))
    metadata = deepcopy(manifest["inventory_snapshot"])
    metadata["exploration_stage"] = COLLECTOR.EXPLORATION_STAGE_NEUTRAL_DISCOVERY
    metadata["goal_candidate_plan"] = None
    corpus.update_control_metadata(
        status="incomplete",
        app_statuses=manifest["app_statuses"],
        collection_mode="safe_explore",
        validation_profile="dynamic_inventory",
        selected_packages=manifest["selected_packages"],
        inventory_packages=manifest["inventory_packages"],
        inventory_snapshot=metadata,
        runtime_attestation=manifest["runtime_attestation"],
        exploration_stage=COLLECTOR.EXPLORATION_STAGE_NEUTRAL_DISCOVERY,
    )
    task = metadata["selected_tasks"][0]
    goal_id = "goal_" + COLLECTOR.stable_hash(
        {"package": task["app_package"], "goal": task["goal_text"]}, 20
    )
    corpus.append_metric(
        {
            "metric_id": "discovery-coverage",
            "metric_dimension": "neutral_discovery_coverage",
            "app_package": task["app_package"],
            "goal_id": goal_id,
            "coverage_outcome": "discovery_frontier_exhausted",
            "coverage_reason": "no_safe_action",
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }
    )
    interrupted = build_task_summary_metric(
        task_id=task["task_id"],
        app_package=task["app_package"],
        goal_id=goal_id,
        terminal_status="stopped:server_none",
        state={
            "action_count": 0,
            "scroll_count": 0,
            "back_count": 0,
            "elapsed_seconds": 0.5,
            "screen_visits": {"dynamic-screen-signature": 1},
        },
        attempt_number=1,
    )
    interrupted["metric_id"] = "discovery-task-summary-interrupted"
    interrupted["source_goal_run_id"] = None
    interrupted["source_inventory_snapshot_id"] = None
    interrupted["source_goal_artifact_sha256"] = None
    corpus.append_metric(interrupted)
    summary = build_task_summary_metric(
        task_id=task["task_id"],
        app_package=task["app_package"],
        goal_id=goal_id,
        terminal_status="discovery_frontier_exhausted",
        state={
            "action_count": 0,
            "scroll_count": 0,
            "back_count": 0,
            "elapsed_seconds": 1.0,
            "screen_visits": {"dynamic-screen-signature": 1},
        },
        attempt_number=4,
    )
    summary["metric_id"] = "discovery-task-summary"
    summary["source_goal_run_id"] = None
    summary["source_inventory_snapshot_id"] = None
    summary["source_goal_artifact_sha256"] = None
    corpus.append_metric(summary)
    corpus.update_control_metadata(
        status="completed", app_statuses=manifest["app_statuses"]
    )
    corpus.save_checkpoint(
        {
            "run_status": "completed",
            "completed_task_ids": [task["task_id"]],
            "current_task_id": None,
            "current_task": None,
            "task_attempt_numbers": {task["task_id"]: 4},
            "task_status": "discovery_frontier_exhausted",
            "statuses": {task["task_id"]: "discovery_frontier_exhausted"},
            "pending_action": None,
        }
    )
    return run_dir


def _validate(run_dir: Path) -> dict[str, Any]:
    return VALIDATOR.validate_corpus(
        run_dir, repo_root=ROOT, observation_root=run_dir.parent
    )


def _codes(report: Mapping[str, Any]) -> set[str]:
    return {str(item["code"]) for item in report["errors"]}


def test_valid_discovery_and_directed_stages() -> None:
    with TemporaryDirectory(prefix="exitguide-stage-positive-") as temporary:
        root = Path(temporary)
        discovery = _create_discovery_run(root / "discovery")
        discovery_report = _validate(discovery)
        assert discovery_report["ok"] is True, discovery_report
        assert discovery_report["checks"]["neutral_discovery_completion"][
            "successful_route_coverage"
        ] is False

        directed_root = root / "directed"
        directed_root.mkdir()
        directed = _create_directed_run(directed_root)
        directed_report = _validate(directed)
        assert directed_report["ok"] is True, directed_report
        assert directed_report["checks"]["directed_graph_route_evidence"][
            "complete"
        ] is True


def test_stage_spoof_hash_mixing_budget_attempt_and_pending_fail_closed() -> None:
    with TemporaryDirectory(prefix="exitguide-stage-negative-") as temporary:
        root = Path(temporary)

        discovery = _create_discovery_run(root / "stage-spoof")
        _update_json(
            discovery / "manifest.json",
            lambda value: value.__setitem__(
                "exploration_stage", COLLECTOR.EXPLORATION_STAGE_GOAL_DIRECTED
            ),
        )
        report = _validate(discovery)
        assert {
            "inventory_exploration_stage_mismatch",
            "checkpoint_selection_mismatch",
        } & _codes(report), report

        discovery = _create_discovery_run(root / "neutral-mixing")
        for filename in ("manifest.json", "checkpoint.json"):
            _update_json(
                discovery / filename,
                lambda value: value["inventory_snapshot"]["selected_tasks"][0].update(
                    {"candidate_id": "goal_spoof"}
                ),
            )
        report = _validate(discovery)
        assert "inventory_selected_tasks_invalid" in _codes(report), report

        discovery = _create_discovery_run(root / "attempt-spoof")
        _update_json(
            discovery / "checkpoint.json",
            lambda value: value["state"]["task_attempt_numbers"].update(
                {next(iter(value["state"]["task_attempt_numbers"])): 0}
            ),
        )
        report = _validate(discovery)
        assert "checkpoint_task_attempt_lineage_invalid" in _codes(report), report

        discovery = _create_discovery_run(root / "pending-spoof")
        _update_json(
            discovery / "checkpoint.json",
            lambda value: value["state"].update(
                {
                    "current_task_id": value["state"]["completed_task_ids"][0],
                    "current_task": value["inventory_snapshot"]["selected_tasks"][0],
                    "pending_action": {"action_type": "click"},
                }
            ),
        )
        report = _validate(discovery)
        assert "checkpoint_pending_action_invalid" in _codes(report), report

        directed_root = root / "hash-spoof"
        directed_root.mkdir()
        directed = _create_directed_run(directed_root)
        for filename in ("manifest.json", "checkpoint.json"):
            _update_json(
                directed / filename,
                lambda value: value["goal_candidate_plan"]["artifact"].update(
                    {"sha256": "0" * 64}
                ),
            )
        report = _validate(directed)
        assert {
            "goal_candidate_plan_control_mismatch",
            "goal_candidate_plan_source_invalid",
        } & _codes(report), report

        directed_root = root / "budget-misuse"
        directed_root.mkdir()
        directed = _create_directed_run(directed_root)
        with sqlite3.connect(directed / "corpus.sqlite") as connection:
            task_id = json.loads(
                connection.execute(
                    "SELECT payload_json FROM metrics WHERE metric_dimension='task_summary'"
                ).fetchone()[0]
            )["task_id"]
        # The append-only store is rebuilt by the fixture only; mutate the
        # mirrored task-summary payload and its event hashes is intentionally
        # unnecessary here because the semantic stage error is independently
        # reported before integrity errors.
        connection = sqlite3.connect(directed / "corpus.sqlite")
        try:
            connection.execute("DROP TRIGGER metrics_append_only_update")
            payload = json.loads(
                connection.execute(
                    "SELECT payload_json FROM metrics WHERE metric_dimension='task_summary'"
                ).fetchone()[0]
            )
            payload["terminal_status"] = "discovery_budget_complete"
            payload["completion_class"] = "discovery_budget_complete"
            payload["candidate_destination_found"] = False
            connection.execute(
                "UPDATE metrics SET payload_json=? WHERE metric_dimension='task_summary'",
                (json.dumps(payload, ensure_ascii=False, sort_keys=True),),
            )
            connection.commit()
        finally:
            connection.close()
        report = _validate(directed)
        assert "discovery_terminal_stage_misuse" in _codes(report), (task_id, report)


def main() -> None:
    test_valid_discovery_and_directed_stages()
    test_stage_spoof_hash_mixing_budget_attempt_and_pending_fail_closed()
    print("Real-device staged observation validation checks ok")


if __name__ == "__main__":
    main()
