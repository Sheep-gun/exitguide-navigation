from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
VALIDATOR_PATH = ROOT / "scripts" / "Validate-RealDeviceObservationCorpus.py"
COLLECTOR_PATH = ROOT / "scripts" / "Collect-RealDeviceObservations.py"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("exitguide_real_device_validator_test", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


def _load_collector() -> Any:
    spec = importlib.util.spec_from_file_location(
        "exitguide_real_device_collector_safety_test", COLLECTOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COLLECTOR = _load_collector()

from app.services.real_device_observation_corpus import (  # noqa: E402
    GRAPH_DATABASE_FILENAME,
    RealDeviceObservationCorpus,
)


def _all_statuses(*, youtube: str = "installed_observed") -> list[dict[str, str]]:
    return [
        {
            "app_package": package,
            "status": youtube if package == "com.google.android.youtube" else "skipped_missing",
        }
        for _, package in VALIDATOR.EXPECTED_APPS
    ]


def _partial_statuses(*, youtube: str = "installed_observed") -> list[dict[str, str]]:
    return [
        {
            "app_package": package,
            "status": (
                youtube
                if package == "com.google.android.youtube"
                else "skipped_missing"
                if package == "com.ktshow.cs"
                else "installed_not_selected"
            ),
        }
        for _, package in VALIDATOR.EXPECTED_APPS
    ]


def _append_consistent_observation(corpus: RealDeviceObservationCorpus) -> None:
    corpus.append_run(
        {
            "run_observation_id": "real-device-safety",
            "device_id": "physical-device-hash",
            "avd_name": "physical_android",
            "api_base_url": "https://example.invalid",
            "lifecycle_event": "started",
            "resumed_from_sequence": 0,
            "started_at": "2026-07-31T00:00:00Z",
        }
    )
    corpus.append_app(
        {
            "app_observation_id": "youtube-observation",
            "app_package": "com.google.android.youtube",
            "app_name": "YouTube",
            "app_version": "20.30.34",
            "locale": "ko-KR",
            "install_source": "physical_device_inventory",
            "store_url": "",
            "status": "installed_observed",
        }
    )
    for screen_id, title in (("screen-start", "설정"), ("screen-destination", "구독 관리")):
        corpus.append_screen(
            {
                "screen_id": screen_id,
                "app_package": "com.google.android.youtube",
                "app_name": "YouTube",
                "app_version": "20.30.34",
                "locale": "ko-KR",
                "screen_signature": f"signature-{screen_id}",
                "screenshot_path": "",
                "accessibility_tree_path": "",
                "activity_name": ".MainActivity",
                "title_text": title,
                "visible_texts": [title],
                "content_descriptions": [],
                "resource_ids": [],
                "scrollable_regions": [],
                "screen_type": "menu",
                "prerequisites": [],
                "contains_personal_data": False,
                "collected_at": "2026-07-31T00:00:01Z",
            },
            privacy_verified=True,
        )
    corpus.append_element(
        {
            "element_id": "element-next",
            "screen_id": "screen-start",
            "text": "구매 항목 및 멤버십",
            "content_description": "구매 항목 및 멤버십",
            "resource_id": "com.google.android.youtube:id/purchases",
            "class_name": "android.widget.TextView",
            "bounds": [20, 200, 1060, 320],
            "clickable": True,
            "enabled": True,
            "selected": False,
            "inferred_icon_semantics": ["subscription"],
            "semantic_function_id": "subscription.manage",
            "synonyms": ["구독 관리"],
            "expected_outcome": "Open subscription management",
            "risk_level": "low",
            "is_final_action": False,
            "confidence": 0.97,
            "evidence": {"source": "accessibility_metadata"},
        }
    )
    corpus.append_element(
        {
            "element_id": "element-final",
            "screen_id": "screen-destination",
            "text": "구독 취소",
            "content_description": "구독 취소",
            "resource_id": "com.google.android.youtube:id/cancel",
            "class_name": "android.widget.Button",
            "bounds": [20, 800, 1060, 920],
            "clickable": True,
            "enabled": True,
            "selected": False,
            "inferred_icon_semantics": ["cancel"],
            "semantic_function_id": "subscription.cancel",
            "synonyms": ["멤버십 해지"],
            "expected_outcome": "User-owned final cancellation action",
            "risk_level": "critical",
            "is_final_action": True,
            "confidence": 0.99,
            "evidence": {"source": "accessibility_metadata"},
        }
    )
    corpus.append_transition(
        {
            "transition_id": "transition-next",
            "source_screen_id": "screen-start",
            "target_screen_id": "screen-destination",
            "action_type": "click",
            "element_id": "element-next",
            "ui_element_id": "element-next",
            "selected_label": "구매 항목 및 멤버십",
            "auto_action_guard": {
                "policy_version": "egl-real-device-auto-action.v1",
                "evaluation_phase": "pre_execution",
                "action_type": "click",
                "allowed": True,
                "computed_final_or_consequential": False,
                "safe_menu_match": True,
                "reason": "physical_safe_menu_navigation",
            },
            "coordinates": [540, 260],
            "scroll_direction": "",
            "scroll_distance": 0,
            "transition_time_ms": 400,
            "success": True,
            "back_available": True,
            "is_loop": False,
            "error_text": "",
            "auto_executed": True,
            "unsafe_action": False,
            "is_final_action": False,
        }
    )
    corpus.append_goal(
        {
            "goal_id": "goal-cancel-premium",
            "app_package": "com.google.android.youtube",
            "user_goal": "유튜브 프리미엄 구독을 해지하고 싶어",
            "standard_goal_id": "subscription.cancel",
            "terminal_candidate_screen_id": "screen-destination",
            "terminal_candidate_element_id": "element-final",
            "status": "candidate",
        }
    )
    corpus.append_metric(
        {
            "metric_id": "metric-youtube",
            "app_package": "com.google.android.youtube",
            "perception_clickable_recall": 1.0,
            "perception_icon_text_link_accuracy": 1.0,
            "semantic_goal_match_accuracy": 1.0,
            "semantic_disambiguation_accuracy": 1.0,
            "destination_found_success": True,
            "wrong_terminal_destination": False,
            "exploration_time_ms": 1200,
            "click_count": 1,
            "scroll_count": 0,
            "back_count": 0,
            "repeat_screen_visit_count": 0,
            "user_intervention_count": 0,
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
            "graph_reuse_rate": 0.0,
        }
    )


def _add_shadow_route(corpus: RealDeviceObservationCorpus) -> None:
    graph_path = corpus.graph_database_path
    connection = sqlite3.connect(graph_path)
    try:
        connection.execute(
            """
            INSERT INTO universal_apps (
              app_key, app_package, app_version, locale, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "com.google.android.youtube|20.30.34|ko-KR",
                "com.google.android.youtube",
                "20.30.34",
                "ko-KR",
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO universal_routes (
              route_id, app_key, goal_key, target_function,
              start_screen_fingerprint, destination_screen_fingerprint,
              steps_json, confidence, provisional, status,
              success_count, failure_count, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "route-youtube-cancel",
                "com.google.android.youtube|20.30.34|ko-KR",
                "goal-key",
                "subscription.cancel",
                "signature-screen-start",
                "signature-screen-destination",
                "[]",
                0.9,
                1,
                "shadow",
                1,
                0,
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    corpus.refresh_after_graph_write()


def _add_partial_graph_evidence(corpus: RealDeviceObservationCorpus) -> None:
    connection = sqlite3.connect(corpus.graph_database_path)
    try:
        app_key = "com.google.android.youtube|20.30.34|ko-KR"
        connection.execute(
            """
            INSERT INTO universal_apps (
              app_key, app_package, app_version, locale, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                app_key,
                "com.google.android.youtube",
                "20.30.34",
                "ko-KR",
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO universal_screens (
              screen_fingerprint, app_key, activity_name, title, structure_json,
              first_seen_at, last_seen_at, seen_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "graph-screen-youtube",
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
            """
            INSERT INTO universal_actions (
              action_id, screen_fingerprint, element_key, last_element_id,
              label, role, risk_level, risk_reason,
              first_seen_at, last_seen_at, seen_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "graph-action-youtube-settings",
                "graph-screen-youtube",
                "settings-key",
                "element-next",
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
    corpus.refresh_after_graph_write()


def _create_run(root: Path, *, completed: bool = False) -> Path:
    run_dir = root / "real-device-safety"
    corpus = RealDeviceObservationCorpus(run_dir, run_id="real-device-safety")
    _append_consistent_observation(corpus)
    corpus.update_control_metadata(
        status="completed" if completed else "incomplete",
        app_statuses=_all_statuses(),
        collection_mode="safe_explore" if completed else "capture_only",
    )
    if completed:
        _add_shadow_route(corpus)
        corpus.update_control_metadata(
            status="completed",
            app_statuses=_all_statuses(),
            collection_mode="safe_explore",
        )
    return run_dir


def _create_partial_run(root: Path) -> Path:
    run_dir = root / "real-device-partial"
    corpus = RealDeviceObservationCorpus(run_dir, run_id="real-device-safety")
    _append_consistent_observation(corpus)
    inventory = sorted(VALIDATOR.EXPECTED_PACKAGES)
    corpus.update_control_metadata(
        status="incomplete",
        app_statuses=_partial_statuses(),
        collection_mode="capture_only",
        validation_profile="partial_research",
        selected_packages=["com.google.android.youtube"],
        inventory_packages=inventory,
    )
    _add_partial_graph_evidence(corpus)
    corpus.update_control_metadata(
        status="incomplete",
        app_statuses=_partial_statuses(),
        collection_mode="capture_only",
        validation_profile="partial_research",
        selected_packages=["com.google.android.youtube"],
        inventory_packages=inventory,
    )
    return run_dir


def _dynamic_snapshot_document(*, selected_sensitive: bool = False) -> dict[str, Any]:
    included = [
        {
            "package": "com.example.updated",
            "launchable_activity": "com.example.updated/.MainActivity",
            "version_name": "2.0",
            "version_code": "20",
            "version_key": "code:20|name:2.0",
            "included": True,
            "decision_reason_code": "eligible_user_app",
            "sensitivity_categories": [],
            "sensitivity_handling": "standard_metadata_only",
            "change_status": "updated",
            "observation_status": "unobserved_current_version",
        },
        {
            "package": "com.netflix.mediaclient",
            "launchable_activity": "com.netflix.mediaclient/.ui.launch.UIWebViewActivity",
            "version_name": "9.76.0",
            "version_code": "64304",
            "version_key": "code:64304|name:9.76.0",
            "included": True,
            "decision_reason_code": "eligible_user_app",
            "sensitivity_categories": (
                ["personal_content"] if selected_sensitive else []
            ),
            "sensitivity_handling": (
                "heightened_metadata_only"
                if selected_sensitive
                else "standard_metadata_only"
            ),
            "change_status": "new",
            "observation_status": "unobserved_current_version",
        },
    ]
    excluded = [
        {
            "package": "com.example.excluded",
            "launchable_activity": None,
            "version_name": "1.0",
            "version_code": "1",
            "version_key": "code:1|name:1.0",
            "included": False,
            "decision_reason_code": "non_launchable",
            "sensitivity_categories": [],
            "sensitivity_handling": "standard_metadata_only",
            "change_status": "unchanged",
            "observation_status": "unobserved_current_version",
        }
    ]
    prioritized = [
        {
            "priority_rank": 1,
            "package": "com.netflix.mediaclient",
            "version_key": "code:64304|name:9.76.0",
            "change_status": "new",
            "observation_status": "unobserved_current_version",
            "priority_reason": "new package",
        },
        {
            "priority_rank": 2,
            "package": "com.example.updated",
            "version_key": "code:20|name:2.0",
            "change_status": "updated",
            "observation_status": "unobserved_current_version",
            "priority_reason": "updated package",
        },
    ]
    return {
        "schema_version": 1,
        "snapshot_id": "20260731T000000000Z-dynamic-test",
        "provenance": COLLECTOR.PROVENANCE,
        "dataset_role": COLLECTOR.DATASET_ROLE,
        "review_status": COLLECTOR.REVIEW_STATUS,
        "route_lifecycle": COLLECTOR.ROUTE_LIFECYCLE,
        "canonical_catalog_mutation": False,
        "canonical_catalog": COLLECTOR.EXPECTED_INVENTORY_CANONICAL,
        "device": {
            "serial": COLLECTOR.EXPECTED_SERIAL,
            "device_type": "physical_android",
            "is_emulator": False,
            "model": "test-device",
            "android_version": "16",
            "locale": "ko-KR",
        },
        "discovered_at": "2026-07-31T00:00:00.000Z",
        "included_apps": included,
        "excluded_apps": excluded,
        "prioritized_apps": prioritized,
        "summary": {
            "discovered_apps": 3,
            "included_apps": len(included),
            "excluded_apps": len(excluded),
        },
    }


def _add_dynamic_graph_evidence(
    corpus: RealDeviceObservationCorpus,
    *,
    package: str,
    version_name: str,
) -> None:
    connection = sqlite3.connect(corpus.graph_database_path)
    try:
        app_key = f"{package}|{version_name}|ko-KR"
        connection.execute(
            """
            INSERT INTO universal_apps (
              app_key, app_package, app_version, locale, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                app_key,
                package,
                version_name,
                "ko-KR",
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO universal_screens (
              screen_fingerprint, app_key, activity_name, title, structure_json,
              first_seen_at, last_seen_at, seen_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dynamic-screen-netflix",
                app_key,
                ".MainActivity",
                "",
                "{}",
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:00Z",
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO universal_actions (
              action_id, screen_fingerprint, element_key, last_element_id,
              label, role, risk_level, risk_reason,
              first_seen_at, last_seen_at, seen_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "dynamic-action-netflix",
                "dynamic-screen-netflix",
                "menu-entry-key",
                "dynamic-element-entry",
                "",
                "button",
                "low",
                "metadata-only menu exploration",
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:00Z",
                1,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    corpus.refresh_after_graph_write()


def _create_dynamic_inventory_run(
    root: Path,
    *,
    app_version_override: str | None = None,
    observe_excluded: bool = False,
    selected_sensitive: bool = False,
    sensitive_api_transfer_count: int = 0,
    sensitive_evidence_violation: bool = False,
    sensitive_policy_event: str = "dynamic_sensitive_metadata_only_capture",
    sensitive_human_text_persisted: bool = False,
    sensitive_goal_id_override: str | None = None,
    sensitive_selected_label: str | None = None,
) -> tuple[Path, Path]:
    snapshot_path = root / "device-inventory" / "inventory-dynamic-test.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            _dynamic_snapshot_document(selected_sensitive=selected_sensitive),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    snapshot = COLLECTOR.load_dynamic_inventory_snapshot(snapshot_path)
    tasks = COLLECTOR.dynamic_inventory_tasks(
        snapshot, only_packages=["com.netflix.mediaclient"]
    )
    assert len(tasks) == 1
    task = tasks[0]
    run_id = "dynamic-inventory-test"
    inventory_packages = sorted(
        str(item["package"]) for item in snapshot["included_apps"]
    )
    metadata = COLLECTOR.dynamic_inventory_manifest_metadata(
        snapshot,
        observation_root=root,
        run_id=run_id,
        selected_packages=[task.app_package],
    )
    metadata["selected_tasks"] = [
        {
            "app_package": task.app_package,
            "app_name": task.app_name,
            "category": task.category,
            "goal_text": task.goal_text,
            "sensitivity_categories": list(task.sensitivity_categories),
            "sensitivity_handling": task.sensitivity_handling,
            "version_name": task.version_name,
            "version_code": task.version_code,
            "version_key": task.version_key,
            "change_status": task.change_status,
            "observation_status": task.observation_status,
            "priority_rank": task.priority_rank,
            "priority_reason": task.priority_reason,
            "task_id": task.task_id,
        }
    ]
    metadata["exploration_stage"] = COLLECTOR.EXPLORATION_STAGE_INITIAL_CAPTURE
    metadata["goal_candidate_plan"] = None
    candidate = next(
        item
        for item in metadata["version_candidates"]
        if item["app_package"] == task.app_package
    )
    runtime_attestation = {
        "schema_version": 1,
        "checked_at": "2026-07-31T00:00:00.000Z",
        "device": {
            "serial": COLLECTOR.EXPECTED_SERIAL,
            "model": "test-device",
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
    run_dir = root / run_id
    corpus = RealDeviceObservationCorpus(run_dir, run_id=run_id)
    statuses = [
        {
            "app_package": package,
            "status": (
                "installed_observed"
                if package == task.app_package
                else "installed_not_selected"
            ),
        }
        for package in inventory_packages
    ]
    corpus.update_control_metadata(
        status="incomplete",
        app_statuses=statuses,
        device_serial=COLLECTOR.EXPECTED_SERIAL,
        collection_mode="capture_only",
        validation_profile=COLLECTOR.DYNAMIC_INVENTORY_PROFILE,
        selected_packages=[task.app_package],
        inventory_packages=inventory_packages,
        inventory_snapshot=metadata,
        runtime_attestation=runtime_attestation,
    )
    corpus.append_run(
        {
            "run_observation_id": run_id,
            "device_id": "physical-device-hash",
            "avd_name": "physical_android",
            "lifecycle_event": "started",
            "started_at": "2026-07-31T00:00:00Z",
        }
    )
    captured_version = app_version_override or str(task.version_name)
    corpus.append_app(
        {
            "app_observation_id": "dynamic-netflix-app",
            "app_package": task.app_package,
            "app_name": task.app_name,
            "app_version": captured_version,
            "version_name": captured_version,
            "version_code": task.version_code,
            "version_candidate_id": candidate["candidate_id"],
            "locale": "ko-KR",
            "status": "installed_observed",
        }
    )
    corpus.append_screen(
        {
            "screen_id": "dynamic-screen",
            "app_package": task.app_package,
            "app_name": task.app_name,
            "app_version": captured_version,
            "locale": "ko-KR",
            "screen_signature": "dynamic-screen-signature",
            "activity_name": ".MainActivity",
            "screen_type": "menu",
            "contains_personal_data": False,
            "collected_at": "2026-07-31T00:00:01Z",
        },
        privacy_verified=sensitive_evidence_violation,
    )
    corpus.append_element(
        {
            "element_id": "dynamic-element-entry",
            "screen_id": "dynamic-screen",
            "role": "button",
            "bounds": [0, 0, 100, 100],
            "clickable": True,
            "enabled": True,
            "risk_level": "low",
            "is_final_action": False,
            "evidence": {"source": "accessibility_metadata"},
        },
        privacy_verified=sensitive_evidence_violation,
    )
    goal_id = "goal_" + COLLECTOR.stable_hash(
        {"package": task.app_package, "goal": task.goal_text}, 20
    )
    corpus.append_goal(
        {
            "goal_id": goal_id,
            "app_package": task.app_package,
            "goal_text": COLLECTOR.NEUTRAL_INVENTORY_GOAL,
            "status": "candidate",
        }
    )
    corpus.append_metric(
        {
            "metric_id": "dynamic-safety-metric",
            "app_package": task.app_package,
            "metric_dimension": (
                "sensitive_local_policy" if selected_sensitive else "policy"
            ),
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
            **(
                {
                    "goal_id": sensitive_goal_id_override or goal_id,
                    "goal_candidate_id": None,
                    "goal_family_id": None,
                    "policy_event": sensitive_policy_event,
                    "external_api_transfer_count": sensitive_api_transfer_count,
                    "sensitivity_categories": list(task.sensitivity_categories),
                    "fallback_mode": "deterministic_local_transient_accessibility",
                    "boundary_kind": None,
                    "local_decision": None,
                    "human_text_persisted": sensitive_human_text_persisted,
                    **(
                        {"selected_label": sensitive_selected_label}
                        if sensitive_selected_label is not None
                        else {}
                    ),
                }
                if selected_sensitive
                else {}
            ),
        }
    )
    if observe_excluded:
        corpus.append_app(
            {
                "app_observation_id": "dynamic-excluded-app",
                "app_package": "com.example.excluded",
                "app_name": "Excluded",
                "app_version": "1.0",
                "locale": "ko-KR",
                "status": "installed_observed",
            }
        )
    _add_dynamic_graph_evidence(
        corpus, package=task.app_package, version_name=captured_version
    )
    corpus.update_control_metadata(
        status="incomplete",
        app_statuses=statuses,
        device_serial=COLLECTOR.EXPECTED_SERIAL,
        collection_mode="capture_only",
        validation_profile=COLLECTOR.DYNAMIC_INVENTORY_PROFILE,
        selected_packages=[task.app_package],
        inventory_packages=inventory_packages,
        inventory_snapshot=metadata,
        runtime_attestation=runtime_attestation,
    )
    connection = sqlite3.connect(corpus.database_path)
    try:
        screen_payloads = [
            str(row[0])
            for row in connection.execute(
                "SELECT payload_json FROM screens ORDER BY event_sequence"
            )
        ]
    finally:
        connection.close()
    (run_dir / "screens.jsonl").write_text(
        "".join(f"{payload}\n" for payload in screen_payloads),
        encoding="utf-8",
    )
    return run_dir, snapshot_path


def _validate(run_dir: Path) -> dict[str, Any]:
    return VALIDATOR.validate_corpus(
        run_dir,
        repo_root=ROOT,
        observation_root=run_dir.parent,
    )


def _codes(report: dict[str, Any]) -> set[str]:
    return {str(item["code"]) for item in report["errors"]}


def _reject(mutation: Callable[[Path], None], code: str, *, completed: bool = True) -> None:
    with TemporaryDirectory(prefix="exitguide-real-device-negative-") as temporary_directory:
        run_dir = _create_run(Path(temporary_directory), completed=completed)
        mutation(run_dir)
        report = _validate(run_dir)
        assert report["ok"] is False, report
        assert code in _codes(report), report


def _update_json(path: Path, update: Callable[[dict[str, Any]], None]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    update(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_exact_physical_app_manifest_contract() -> None:
    errors: list[dict[str, str]] = []
    checks: dict[str, Any] = {}
    payload = VALIDATOR._validate_app_manifest(VALIDATOR.DEFAULT_MANIFEST, errors, checks)
    assert errors == [], errors
    assert len(payload["apps"]) == 14
    assert {(item["app_name"], item["app_package"]) for item in payload["apps"]} == set(VALIDATOR.EXPECTED_APPS)


def assert_capture_only_and_completed_profiles_pass_separately() -> None:
    with TemporaryDirectory(prefix="exitguide-real-device-positive-") as temporary_directory:
        capture = _create_run(Path(temporary_directory) / "capture", completed=False)
        capture_report = _validate(capture)
        assert capture_report["ok"] is True, capture_report
        assert capture_report["checks"]["run_profile"]["capture_only"] is True
        assert capture_report["checks"]["auto_action_guard_transition_count"] == 1
        assert capture_report["checks"]["auto_action_guard_attested_count"] == 1
        assert capture_report["checks"]["recomputed_unsafe_auto_click_count"] == 0
        assert capture_report["checks"]["recomputed_final_action_auto_click_count"] == 0

        completed = _create_run(Path(temporary_directory) / "completed", completed=True)
        completed_report = _validate(completed)
        assert completed_report["ok"] is True, completed_report
        assert completed_report["checks"]["run_profile"]["completed"] is True


def assert_partial_research_is_explicit_deep_and_privacy_preserving() -> None:
    with TemporaryDirectory(prefix="exitguide-real-device-partial-") as temporary_directory:
        run_dir = _create_partial_run(Path(temporary_directory))
        report = _validate(run_dir)
        assert report["ok"] is True, report
        run_profile = report["checks"]["run_profile"]
        assert run_profile["cohort_profile"] == "partial_research"
        assert run_profile["selected_packages"] == ["com.google.android.youtube"]
        assert len(run_profile["inventory_packages"]) == 14
        assert run_profile["not_selected_packages"]
        assert report["checks"]["partial_graph_evidence"]["com.google.android.youtube"] == {
            "screens": 1,
            "actions": 1,
        }

        (run_dir / "partial-leak.json").write_text(
            '{"title_text":"partial.person@example.com"}', encoding="utf-8"
        )
        leaked = _validate(run_dir)
        assert leaked["ok"] is False, leaked
        assert "sensitive_data_detected" in _codes(leaked), leaked


def assert_partial_research_rejects_missing_selected_evidence_and_full_bypass() -> None:
    with TemporaryDirectory(prefix="exitguide-real-device-partial-negative-") as temporary_directory:
        run_dir = _create_partial_run(Path(temporary_directory))
        missing_statuses = _partial_statuses(youtube="skipped_missing")
        _update_json(
            run_dir / "manifest.json",
            lambda value: value.__setitem__("app_statuses", missing_statuses),
        )
        _update_json(
            run_dir / "checkpoint.json",
            lambda value: value.__setitem__("app_statuses", missing_statuses),
        )
        report = _validate(run_dir)
        assert report["ok"] is False, report
        assert "selected_package_missing_evidence" in _codes(report), report

    def mutate_full_status(run_dir: Path) -> None:
        statuses = _all_statuses()
        statuses[1]["status"] = "installed_not_selected"
        _update_json(run_dir / "manifest.json", lambda value: value.__setitem__("app_statuses", statuses))
        _update_json(run_dir / "checkpoint.json", lambda value: value.__setitem__("app_statuses", statuses))

    _reject(mutate_full_status, "full_cohort_partial_status_forbidden", completed=False)


def assert_dynamic_inventory_is_exact_tamper_evident_and_version_bound() -> None:
    with TemporaryDirectory(prefix="exitguide-real-device-dynamic-positive-") as temporary_directory:
        run_dir, snapshot_path = _create_dynamic_inventory_run(Path(temporary_directory))
        report = _validate(run_dir)
        assert report["ok"] is True, report
        json.dumps(report, ensure_ascii=False, sort_keys=True)
        profile = report["checks"]["run_profile"]
        assert profile["cohort_profile"] == "dynamic_inventory"
        assert profile["selected_packages"] == ["com.netflix.mediaclient"]
        assert profile["inventory_packages"] == [
            "com.example.updated",
            "com.netflix.mediaclient",
        ]
        assert "com.ktshow.cs" not in profile["inventory_packages"]
        assert profile["not_selected_packages"] == ["com.example.updated"]
        assert report["checks"]["dynamic_inventory"] == {
            "snapshot_id": "20260731T000000000Z-dynamic-test",
            "included_count": 2,
            "excluded_count": 1,
            "selected_count": 1,
        }
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["safety"]["unsafe_auto_click_count"] == 0
        assert manifest["safety"]["final_action_auto_click_count"] == 0

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = VALIDATOR.main(
                [
                    "--run-dir",
                    str(run_dir),
                    "--observation-root",
                    str(run_dir.parent),
                    "--compact",
                ]
            )
        cli_report = json.loads(stdout.getvalue())
        assert exit_code == 0 and cli_report["ok"] is True, cli_report
        attestation_path = run_dir / VALIDATOR.VALIDATION_ATTESTATION_FILENAME
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        assert attestation["status"] == "passed"
        assert attestation["validator"] == "Validate-RealDeviceObservationCorpus.py"
        assert attestation["device_serial"] == COLLECTOR.EXPECTED_SERIAL
        assert attestation["is_emulator"] is False
        assert attestation["manifest_sha256"]
        assert attestation["screens_sha256"]
        assert set(attestation["core_artifact_sha256"]) == set(
            VALIDATOR.VALIDATION_CORE_ARTIFACTS
        )
        for filename, digest in attestation["core_artifact_sha256"].items():
            assert digest == VALIDATOR._sha256(run_dir / filename)
        assert (
            attestation["manifest_sha256"]
            == attestation["core_artifact_sha256"]["manifest.json"]
        )
        assert (
            attestation["screens_sha256"]
            == attestation["core_artifact_sha256"]["screens.jsonl"]
        )

        snapshot_path.write_text(
            snapshot_path.read_text(encoding="utf-8") + " ", encoding="utf-8"
        )
        tampered = _validate(run_dir)
        assert tampered["ok"] is False, tampered
        assert "inventory_snapshot_sha256_mismatch" in _codes(tampered)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = VALIDATOR.main(
                [
                    "--run-dir",
                    str(run_dir),
                    "--observation-root",
                    str(run_dir.parent),
                    "--compact",
                ]
            )
        json.loads(stdout.getvalue())
        assert exit_code == 1
        assert not attestation_path.exists()

    with TemporaryDirectory(prefix="exitguide-real-device-dynamic-version-") as temporary_directory:
        run_dir, _ = _create_dynamic_inventory_run(
            Path(temporary_directory), app_version_override="9.75.0"
        )
        report = _validate(run_dir)
        assert report["ok"] is False, report
        assert "dynamic_inventory_version_mismatch" in _codes(report), report

    with TemporaryDirectory(prefix="exitguide-real-device-dynamic-excluded-") as temporary_directory:
        run_dir, _ = _create_dynamic_inventory_run(
            Path(temporary_directory), observe_excluded=True
        )
        report = _validate(run_dir)
        assert report["ok"] is False, report
        assert "excluded_inventory_package_observed" in _codes(report), report

    with TemporaryDirectory(prefix="exitguide-real-device-dynamic-status-") as temporary_directory:
        run_dir, _ = _create_dynamic_inventory_run(Path(temporary_directory))
        for filename in ("manifest.json", "checkpoint.json"):
            _update_json(
                run_dir / filename,
                lambda value: value.__setitem__(
                    "app_statuses",
                    [
                        {
                            "app_package": "com.example.updated",
                            "status": "skipped_missing",
                        },
                        {
                            "app_package": "com.netflix.mediaclient",
                            "status": "installed_observed",
                        },
                    ],
                ),
            )
        report = _validate(run_dir)
        assert report["ok"] is False, report
        assert "unselected_package_status_invalid" in _codes(report), report

    with TemporaryDirectory(prefix="exitguide-real-device-dynamic-runtime-") as temporary_directory:
        run_dir, _ = _create_dynamic_inventory_run(Path(temporary_directory))
        for filename in ("manifest.json", "checkpoint.json"):
            _update_json(
                run_dir / filename,
                lambda value: value["runtime_attestation"]["api"].update(
                    {"llm_provider": "mock", "provider_ready": True}
                ),
            )
        report = _validate(run_dir)
        assert report["ok"] is False, report
        assert "runtime_attestation_invalid" in _codes(report), report

    with TemporaryDirectory(prefix="exitguide-real-device-dynamic-sensitive-") as temporary_directory:
        run_dir, _ = _create_dynamic_inventory_run(
            Path(temporary_directory), selected_sensitive=True
        )
        report = _validate(run_dir)
        assert report["ok"] is True, report
        assert report["checks"]["dynamic_sensitive_policy"][
            "com.netflix.mediaclient"
        ]["external_api_transfer_count_zero"] is True

    with TemporaryDirectory(prefix="exitguide-real-device-dynamic-sensitive-api-") as temporary_directory:
        run_dir, _ = _create_dynamic_inventory_run(
            Path(temporary_directory),
            selected_sensitive=True,
            sensitive_api_transfer_count=1,
        )
        report = _validate(run_dir)
        assert report["ok"] is False, report
        assert "dynamic_sensitive_api_transfer_nonzero" in _codes(report), report

    with TemporaryDirectory(prefix="exitguide-real-device-dynamic-sensitive-evidence-") as temporary_directory:
        run_dir, _ = _create_dynamic_inventory_run(
            Path(temporary_directory),
            selected_sensitive=True,
            sensitive_evidence_violation=True,
        )
        report = _validate(run_dir)
        assert report["ok"] is False, report
        assert "dynamic_sensitive_evidence_policy_violation" in _codes(report), report

    for label, kwargs in (
        (
            "legacy-event",
            {"sensitive_policy_event": "dynamic_sensitive_metadata_only"},
        ),
        ("goal-lineage", {"sensitive_goal_id_override": "goal_wrong"}),
        ("human-attestation", {"sensitive_human_text_persisted": True}),
        ("human-field", {"sensitive_selected_label": "설정"}),
    ):
        with TemporaryDirectory(
            prefix=f"exitguide-real-device-dynamic-sensitive-{label}-"
        ) as temporary_directory:
            run_dir, _ = _create_dynamic_inventory_run(
                Path(temporary_directory),
                selected_sensitive=True,
                **kwargs,
            )
            report = _validate(run_dir)
            assert report["ok"] is False, report
            assert "sensitive_local_metric_invalid" in _codes(report), report


def assert_unreviewed_gold_and_catalog_promotion_are_rejected() -> None:
    _reject(
        lambda run: _update_json(run / "manifest.json", lambda value: value.__setitem__("review_status", "approved_gold")),
        "unreviewed_gold_forbidden",
    )
    _reject(
        lambda run: _update_json(run / "manifest.json", lambda value: value.__setitem__("proposed_catalog_version", "V16")),
        "v16_v20_promotion_forbidden",
    )


def assert_skipped_missing_apps_cannot_have_observation_rows() -> None:
    def mutate(run_dir: Path) -> None:
        statuses = _all_statuses(youtube="skipped_missing")
        _update_json(run_dir / "manifest.json", lambda value: value.__setitem__("app_statuses", statuses))
        _update_json(run_dir / "checkpoint.json", lambda value: value.__setitem__("app_statuses", statuses))

    _reject(mutate, "uninstalled_app_observed")


def assert_raw_artifacts_pii_and_secrets_fail_closed() -> None:
    _reject(
        lambda run: (run / "raw-original-screen.png").write_bytes(b"raw screenshot"),
        "raw_artifact_forbidden",
    )
    _reject(
        lambda run: (run / "leak.json").write_text('{"title_text":"person@example.com"}', encoding="utf-8"),
        "sensitive_data_detected",
    )
    _reject(
        lambda run: (run / "secret.json").write_text('{"authorization":"Bearer abcdefghijklmnopqrstuvwxyz"}', encoding="utf-8"),
        "sensitive_data_detected",
    )


def assert_shared_privacy_classifier_covers_formats_without_structural_id_false_positive() -> None:
    with TemporaryDirectory(prefix="exitguide-real-device-privacy-formats-") as temporary_directory:
        run_dir = Path(temporary_directory)
        opaque_id = "task_a3645d76d16f6d51-000-a05f5051:node_01012345678"
        generated_ids = {
            "ui_element_id": "01012345678",
            "parent_id": "9001011234567",
            "event_id": "4111111111111111",
            "record_id": "01098765432",
            "last_element_id": "8001012345678",
        }
        (run_dir / "structural.json").write_text(
            json.dumps({"element_id": opaque_id, **generated_ids}),
            encoding="utf-8",
        )
        (run_dir / "structural.xml").write_text(
            f'<node resource-id="com.example:id/{opaque_id}" bounds="[0,0][10,10]" />',
            encoding="utf-8",
        )
        database = run_dir / "corpus.sqlite"
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE sample (element_id TEXT, title_text TEXT, payload_json TEXT)")
            connection.execute(
                "INSERT INTO sample(element_id, title_text, payload_json) VALUES (?, ?, ?)",
                (opaque_id, "설정", json.dumps({"screen_id": opaque_id})),
            )
            connection.execute(
                "CREATE TABLE generated_ids (ui_element_id TEXT, parent_id TEXT, "
                "event_id TEXT, record_id TEXT, last_element_id TEXT)"
            )
            connection.execute(
                "INSERT INTO generated_ids VALUES (?, ?, ?, ?, ?)",
                tuple(generated_ids.values()),
            )
            connection.commit()
            errors: list[dict[str, str]] = []
            checks: dict[str, Any] = {}
            VALIDATOR._validate_shared_privacy_classifier(run_dir, connection, errors, checks)
            assert errors == [], errors
            assert checks["sensitive_data_findings"] == 0

            (run_dir / "accessibility.xml").write_text(
                '<node content-desc="프로필 @sample_user" state-description="배송 주소를 확인하세요" />',
                encoding="utf-8",
            )
            (run_dir / "elements.jsonl").write_text(
                json.dumps({"content_description": "인증번호를 입력하세요"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            connection.execute(
                "INSERT INTO sample(element_id, title_text, payload_json) VALUES (?, ?, ?)",
                (
                    "safe-2",
                    "보험 계약번호 TEST-123",
                    json.dumps({"text": "계좌 잔액 12,345원"}, ensure_ascii=False),
                ),
            )
            connection.commit()
            errors = []
            checks = {}
            VALIDATOR._validate_shared_privacy_classifier(run_dir, connection, errors, checks)
        finally:
            connection.close()

        categories = set(checks["sensitive_data_categories"])
        assert {
            "account_handle",
            "location_or_address_context",
            "authentication_data",
            "insurance_data",
            "financial_balance",
        } <= categories, checks
        assert errors and all(item["code"] == "sensitive_data_detected" for item in errors)
        rendered = json.dumps(errors, ensure_ascii=False)
        for source_value in (
            "@sample_user",
            "배송 주소를 확인하세요",
            "인증번호를 입력하세요",
            "보험 계약번호 TEST-123",
            "계좌 잔액 12,345원",
        ):
            assert source_value not in rendered


def assert_unsafe_final_click_and_metrics_fail_closed() -> None:
    def mutate(run_dir: Path) -> None:
        connection = sqlite3.connect(run_dir / "corpus.sqlite")
        try:
            connection.execute("DROP TRIGGER transitions_append_only_update")
            connection.execute("UPDATE transitions SET is_final_action=1 WHERE transition_id='transition-next'")
            connection.commit()
        finally:
            connection.close()

    _reject(mutate, "final_action_auto_click")


def assert_missing_or_tampered_pre_execution_guard_fails_closed() -> None:
    def mutate(run_dir: Path) -> None:
        connection = sqlite3.connect(run_dir / "corpus.sqlite")
        try:
            row = connection.execute(
                "SELECT payload_json FROM transitions WHERE transition_id='transition-next'"
            ).fetchone()
            payload = json.loads(str(row[0]))
            payload.pop("auto_action_guard", None)
            connection.execute("DROP TRIGGER transitions_append_only_update")
            connection.execute(
                "UPDATE transitions SET payload_json=? WHERE transition_id='transition-next'",
                (json.dumps(payload, ensure_ascii=False, sort_keys=True),),
            )
            connection.commit()
        finally:
            connection.close()

    _reject(mutate, "auto_action_guard_missing_or_inconsistent")


def assert_misclassified_terminal_source_element_fails_closed() -> None:
    def mutate(run_dir: Path) -> None:
        connection = sqlite3.connect(run_dir / "corpus.sqlite")
        try:
            row = connection.execute(
                "SELECT payload_json FROM elements WHERE element_id='element-next'"
            ).fetchone()
            payload = json.loads(str(row[0]))
            payload["label"] = "Delete account"
            payload["text"] = "Delete account"
            payload["content_description"] = "Delete account"
            connection.execute("DROP TRIGGER elements_append_only_update")
            connection.execute(
                "UPDATE elements SET payload_json=? WHERE element_id='element-next'",
                (json.dumps(payload, ensure_ascii=False, sort_keys=True),),
            )
            connection.commit()
        finally:
            connection.close()

    _reject(mutate, "final_action_auto_click_recomputed")


def assert_resume_sequence_hash_and_jsonl_divergence_fail_closed() -> None:
    def mutate(run_dir: Path) -> None:
        path = run_dir / "observations.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    _reject(mutate, "observation_log_divergence")


def assert_graph_must_remain_shadow_candidate() -> None:
    def mutate(run_dir: Path) -> None:
        connection = sqlite3.connect(run_dir / GRAPH_DATABASE_FILENAME)
        try:
            connection.execute("DROP TRIGGER real_device_routes_shadow_update")
            connection.execute("UPDATE universal_routes SET status='approved', provisional=0")
            connection.commit()
        finally:
            connection.close()

    _reject(mutate, "graph_route_not_candidate")


def assert_completed_validation_requires_graph_and_transition_evidence() -> None:
    def mutate(run_dir: Path) -> None:
        (run_dir / GRAPH_DATABASE_FILENAME).unlink()

    _reject(mutate, "graph_candidate_missing")


def main() -> None:
    assert_exact_physical_app_manifest_contract()
    assert_capture_only_and_completed_profiles_pass_separately()
    assert_partial_research_is_explicit_deep_and_privacy_preserving()
    assert_partial_research_rejects_missing_selected_evidence_and_full_bypass()
    assert_dynamic_inventory_is_exact_tamper_evident_and_version_bound()
    assert_unreviewed_gold_and_catalog_promotion_are_rejected()
    assert_skipped_missing_apps_cannot_have_observation_rows()
    assert_raw_artifacts_pii_and_secrets_fail_closed()
    assert_shared_privacy_classifier_covers_formats_without_structural_id_false_positive()
    assert_unsafe_final_click_and_metrics_fail_closed()
    assert_missing_or_tampered_pre_execution_guard_fails_closed()
    assert_misclassified_terminal_source_element_fails_closed()
    assert_resume_sequence_hash_and_jsonl_divergence_fail_closed()
    assert_graph_must_remain_shadow_candidate()
    assert_completed_validation_requires_graph_and_transition_evidence()
    print("Real-device observation validator safety checks ok")


if __name__ == "__main__":
    main()
