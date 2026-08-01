import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.emulator_observation_corpus import (
    CANONICAL_CATALOG_SHA256,
    CANONICAL_CATALOG_VERSION,
    CANONICAL_EQUIVALENCE_SHA256,
    RECORD_TABLES,
)
from app.services.real_device_observation_corpus import (
    DATASET_ROLE,
    GRAPH_DATABASE_FILENAME,
    PROVENANCE,
    REVIEW_LIFECYCLE,
    REVIEW_STATUS,
    ROUTE_LIFECYCLE,
    RUN_MODE,
    CorpusIntegrityError,
    RealDeviceObservationCorpus,
)


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = ROOT / "scripts" / "Validate-RealDeviceObservationCorpus.py"
APP_MANIFEST_PATH = ROOT / "fixtures" / "navigation" / "real-device-observation-apps.v1.json"


def main() -> None:
    assert_physical_candidate_layout_and_manifest_contract()
    assert_all_record_types_are_append_only_and_resumable()
    assert_dynamic_inventory_control_metadata_is_exact_and_resumable()
    assert_unredacted_physical_evidence_falls_back_to_metadata_only()
    assert_gold_catalog_promotion_and_automatic_final_actions_fail_closed()
    assert_graph_candidate_cannot_leave_shadow_lifecycle()
    assert_shared_physical_validator_accepts_resumable_candidate_store()
    print("Real-device observation corpus checks ok")


def assert_physical_candidate_layout_and_manifest_contract() -> None:
    with TemporaryDirectory() as temporary_directory:
        run_dir = Path(temporary_directory) / "physical-run"
        corpus = RealDeviceObservationCorpus(run_dir, run_id="physical-layout")
        expected_files = {
            "corpus.sqlite",
            "graph-candidate.sqlite",
            "observations.jsonl",
            "manifest.json",
            "checkpoint.json",
        }
        assert expected_files <= {path.name for path in run_dir.iterdir()}
        manifest = _load_json(run_dir / "manifest.json")
        assert manifest["provenance"] == PROVENANCE
        assert manifest["dataset_role"] == DATASET_ROLE
        assert manifest["review_status"] == REVIEW_STATUS
        assert manifest["review_lifecycle"] == REVIEW_LIFECYCLE
        assert manifest["route_lifecycle"] == ROUTE_LIFECYCLE
        assert manifest["run_mode"] == RUN_MODE
        assert manifest["status"] == "collecting"
        assert manifest["device_type"] == "physical_android"
        assert manifest["is_emulator"] is False
        assert manifest["raw_artifacts_persisted"] is False
        assert manifest["git_eligible"] is False
        assert manifest["app_statuses"] == []
        assert manifest["canonical_catalog"] == {
            "version": CANONICAL_CATALOG_VERSION,
            "sha256": CANONICAL_CATALOG_SHA256,
            "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "domain_count": 179,
            "function_count": 2866,
            "terminal_function_count": 2660,
            "intent_count": 2660,
        }
        assert manifest["version_policy"] == {
            "canonical": "V15_frozen",
            "v16_v20_promotion": "forbidden",
            "v21": "research_only_noncanonical",
            "v22_plus": "forbidden",
        }
        assert manifest["safety"] == {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }

        connection = sqlite3.connect(run_dir / "corpus.sqlite")
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert set(RECORD_TABLES) | {"event_log"} <= tables
            event_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(event_log)")
            }
            assert {
                "sequence",
                "event_id",
                "record_type",
                "record_id",
                "run_id",
                "provenance",
                "dataset_role",
                "review_status",
                "review_lifecycle",
                "route_lifecycle",
                "content_sha256",
                "event_sha256",
            } <= event_columns
        finally:
            connection.close()

        graph = sqlite3.connect(run_dir / GRAPH_DATABASE_FILENAME)
        try:
            graph_tables = {
                row[0]
                for row in graph.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert {"universal_routes", "real_device_candidate_metadata"} <= graph_tables
            metadata = dict(graph.execute("SELECT key, value FROM real_device_candidate_metadata"))
            assert metadata["provenance"] == PROVENANCE
            assert metadata["review_status"] == REVIEW_STATUS
            assert metadata["review_lifecycle"] == REVIEW_LIFECYCLE
            assert metadata["route_lifecycle"] == ROUTE_LIFECYCLE
        finally:
            graph.close()
        assert corpus.verify_integrity()["ok"] is True


def assert_all_record_types_are_append_only_and_resumable() -> None:
    with TemporaryDirectory() as temporary_directory:
        run_dir = Path(temporary_directory) / "physical-run"
        corpus = RealDeviceObservationCorpus(run_dir, run_id="physical-records")
        evidence_dir = run_dir / "apps" / "com.example" / "screens"
        evidence_dir.mkdir(parents=True)
        screenshot = evidence_dir / "settings.redacted.png"
        tree = evidence_dir / "settings.redacted.xml"
        screenshot.write_bytes(b"redacted-device-screenshot")
        tree.write_text("<hierarchy redacted='true'/>", encoding="utf-8")

        records = [
            corpus.append_run(
                {
                    "device_id": "R3CT-device-hash",
                    "avd_name": "physical_android",
                    "api_base_url": "https://example.invalid",
                    "lifecycle_event": "started",
                    "started_at": "2026-07-31T00:00:00Z",
                }
            ),
            corpus.append_app(
                {
                    "app_observation_id": "app-example-v1",
                    "app_package": "com.example",
                    "app_name": "Example",
                    "app_version": "1.0",
                    "locale": "ko-KR",
                    "status": "installed_observed",
                }
            ),
            corpus.append_screen(
                {
                    "screen_id": "screen-settings",
                    "app_package": "com.example",
                    "app_name": "Example",
                    "app_version": "1.0",
                    "locale": "ko-KR",
                    "screen_signature": "screen-signature",
                    "screenshot_path": screenshot,
                    "accessibility_tree_path": tree,
                    "screenshot_redacted": True,
                    "accessibility_tree_redacted": True,
                    "activity_name": ".SettingsActivity",
                    "title_text": "설정",
                    "visible_texts": ["설정", "계정"],
                    "content_descriptions": ["뒤로"],
                    "resource_ids": ["com.example:id/account"],
                    "scrollable_regions": [],
                    "screen_type": "menu",
                    "prerequisites": ["app_open"],
                    "contains_personal_data": False,
                    "collected_at": "2026-07-31T00:00:01Z",
                },
                privacy_verified=True,
            ),
            corpus.append_element(
                {
                    "element_id": "element-account",
                    "screen_id": "screen-settings",
                    "text": "계정",
                    "content_description": "계정 설정",
                    "resource_id": "com.example:id/account",
                    "class_name": "android.widget.TextView",
                    "bounds": [20, 300, 1060, 440],
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "inferred_icon_semantics": ["account", "profile"],
                    "semantic_function_id": "account.settings",
                    "synonyms": ["내 계정", "프로필"],
                    "expected_outcome": "account settings menu",
                    "risk_level": "low",
                    "is_final_action": False,
                    "confidence": 0.97,
                    "evidence": {"source": "accessibility"},
                }
            ),
            corpus.append_transition(
                {
                    "transition_id": "transition-account",
                    "source_screen_id": "screen-settings",
                    "target_screen_id": "screen-account",
                    "action_type": "click",
                    "element_id": "element-account",
                    "ui_element_id": "element-account",
                    "selected_label": "계정 설정",
                    "auto_action_guard": {
                        "policy_version": "egl-real-device-auto-action.v1",
                        "evaluation_phase": "pre_execution",
                        "action_type": "click",
                        "allowed": True,
                        "computed_final_or_consequential": False,
                        "safe_menu_match": True,
                        "reason": "physical_safe_menu_navigation",
                    },
                    "coordinates": [540, 370],
                    "scroll_direction": None,
                    "scroll_distance": 0,
                    "transition_time_ms": 500,
                    "success": True,
                    "back_available": True,
                    "is_loop": False,
                    "error_text": None,
                    "auto_executed": True,
                    "unsafe_action": False,
                    "is_final_action": False,
                }
            ),
            corpus.append_goal(
                {
                    "goal_id": "goal-account-delete",
                    "app_package": "com.example",
                    "goal_text": "계정을 삭제하고 싶어",
                    "standard_goal_id": "account.delete",
                    "terminal_candidate_screen_id": "screen-delete-boundary",
                    "terminal_candidate_element_id": "element-final-delete",
                    "status": "candidate",
                }
            ),
            corpus.append_failure(
                {
                    "failure_id": "failure-decoy",
                    "app_package": "com.example",
                    "goal_id": "goal-account-delete",
                    "user_goal": "계정을 삭제하고 싶어",
                    "screen_id": "screen-settings",
                    "selected_candidate": "로그아웃",
                    "correct_candidate": "계정 삭제",
                    "failure_reason": "similar account action",
                    "required_synonym_or_label": "회원 탈퇴",
                    "policy_change": "separate logout from deletion",
                    "retest_result": "success",
                }
            ),
            corpus.append_metric(
                {
                    "metric_id": "metric-example",
                    "app_package": "com.example",
                    "goal_id": "goal-account-delete",
                    "metric_dimension": "policy",
                    "perception_clickable_recall": 0.98,
                    "perception_icon_text_link_accuracy": 0.96,
                    "semantic_goal_match_accuracy": 0.95,
                    "semantic_disambiguation_accuracy": 0.93,
                    "destination_found_success": True,
                    "wrong_terminal_destination": False,
                    "exploration_time_ms": 5000,
                    "click_count": 3,
                    "scroll_count": 1,
                    "back_count": 0,
                    "repeat_screen_visit_count": 0,
                    "user_intervention_count": 0,
                    "unsafe_auto_click_count": 0,
                    "final_action_auto_click_count": 0,
                    "graph_reuse_rate": 0.5,
                }
            ),
            corpus.append_annotation(
                {
                    "annotation_id": "annotation-review",
                    "entity_type": "screen",
                    "entity_id": "screen-settings",
                    "label": "candidate_only",
                    "value": True,
                    "reviewer": "rule_engine",
                    "status": "candidate",
                }
            ),
        ]
        assert [record.sequence for record in records] == list(range(1, 10))
        assert corpus.counts() == {table: 1 for table in RECORD_TABLES}
        screen = records[2].payload
        assert screen["evidence_mode"] == "verified_redacted"
        assert screen["evidence_retention"] == "redacted_derivative_only"
        assert screen["raw_artifacts_persisted"] is False
        assert screen["screenshot_path"].endswith("settings.redacted.png")

        corpus.update_control_metadata(
            status="incomplete",
            device_type="physical_android",
            is_emulator=False,
            device_serial="physical-test-device",
            app_statuses=[
                {"app_package": "com.example", "status": "installed_observed"},
                {"app_package": "com.missing", "status": "skipped_missing"},
            ],
        )
        corpus.save_checkpoint({"task_index": 3, "screen_frontier": ["screen-account"]})
        manifest = _load_json(run_dir / "manifest.json")
        checkpoint = _load_json(run_dir / "checkpoint.json")
        events = [
            json.loads(line)
            for line in (run_dir / "observations.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert checkpoint["last_sequence"] == events[-1]["sequence"]
        assert checkpoint["last_event_id"] == events[-1]["event_id"]
        assert manifest["status"] == "incomplete"
        assert manifest["device_serial"] == "physical-test-device"
        assert manifest["serial"] == "physical-test-device"
        assert manifest["app_statuses"] == [
            {"app_package": "com.example", "status": "installed_observed"},
            {"app_package": "com.missing", "status": "skipped_missing"},
        ]

        resumed = RealDeviceObservationCorpus(run_dir, run_id="physical-records", resume=True)
        assert resumed.resume_state == {
            "task_index": 3,
            "screen_frontier": ["screen-account"],
        }
        resumed_manifest = _load_json(run_dir / "manifest.json")
        assert resumed_manifest["status"] == "incomplete"
        assert resumed_manifest["device_serial"] == "physical-test-device"
        assert resumed_manifest["app_statuses"] == manifest["app_statuses"]
        retry = resumed.append_app(
            {
                "app_observation_id": "app-example-v1",
                "app_package": "com.example",
                "app_name": "Example",
                "app_version": "1.0",
                "locale": "ko-KR",
                "status": "installed_observed",
            }
        )
        assert retry.appended is False
        assert resumed.verify_integrity()["ok"] is True

        connection = sqlite3.connect(run_dir / "corpus.sqlite")
        try:
            try:
                connection.execute("UPDATE goals SET status='gold'")
            except sqlite3.IntegrityError as exc:
                assert "append-only" in str(exc)
            else:
                raise AssertionError("physical corpus UPDATE was not blocked")
        finally:
            connection.close()


def assert_dynamic_inventory_control_metadata_is_exact_and_resumable() -> None:
    with TemporaryDirectory() as temporary_directory:
        run_dir = Path(temporary_directory) / "dynamic-run"
        corpus = RealDeviceObservationCorpus(run_dir, run_id="dynamic-control")
        included_inventory = [
            {"package": "com.example.alpha", "version_key": "code:10|name:1.0"},
            {"package": "com.example.beta", "version_key": "code:20|name:2.0"},
        ]
        snapshot_metadata = {
            "snapshot_id": "20260731T000000000Z-testfixture",
            "path": "device-inventory/inventory.json",
            "path_scope": "observation_root_relative",
            "explicit_safe_file": False,
            "sha256": "a" * 64,
            "included_inventory": included_inventory,
            "selected_packages": ["com.example.alpha"],
            "exploration_stage": "initial_capture",
            "goal_candidate_plan": None,
            "selected_tasks": [
                {
                    "task_id": "task-alpha",
                    "app_package": "com.example.alpha",
                    "goal_text": "앱 기능 메뉴 및 설정 진입점 조사",
                }
            ],
        }
        statuses = [
            {"app_package": "com.example.alpha", "status": "installed_observed"},
            {"app_package": "com.example.beta", "status": "installed_not_selected"},
        ]
        runtime_attestation = {
            "schema_version": 1,
            "checked_at": "2026-07-31T00:00:00.000Z",
            "device": {
                "serial": "physical-dynamic-test",
                "model": "test-model",
                "android_version": "16",
                "locale": "ko-KR",
                "device_type": "physical_android",
                "is_emulator": False,
            },
            "exitguide": {
                "package": "com.exitguide.ai",
                "installed_for_user_0": True,
                "accessibility_component": "com.exitguide.ai/com.exitguide.ai.overlay.ExitGuideAccessibilityService",
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
        corpus.update_control_metadata(
            status="incomplete",
            app_statuses=statuses,
            device_serial="physical-dynamic-test",
            collection_mode="capture_only",
            validation_profile="dynamic_inventory",
            selected_packages=["com.example.alpha"],
            inventory_packages=["com.example.beta", "com.example.alpha"],
            inventory_snapshot=snapshot_metadata,
            runtime_attestation=runtime_attestation,
        )
        corpus.save_checkpoint({"current_task_id": "task-alpha", "action_count": 2})

        manifest = _load_json(run_dir / "manifest.json")
        checkpoint = _load_json(run_dir / "checkpoint.json")
        assert manifest["validation_profile"] == "dynamic_inventory"
        assert manifest["selected_packages"] == ["com.example.alpha"]
        assert manifest["inventory_packages"] == ["com.example.alpha", "com.example.beta"]
        assert manifest["inventory_snapshot"] == snapshot_metadata
        assert manifest["runtime_attestation"] == runtime_attestation
        assert manifest["app_statuses"] == statuses
        assert checkpoint["inventory_snapshot"] == snapshot_metadata
        assert checkpoint["runtime_attestation"] == runtime_attestation

        resumed = RealDeviceObservationCorpus(
            run_dir, run_id="dynamic-control", resume=True
        )
        assert resumed.resume_state["current_task_id"] == "task-alpha"
        resumed_manifest = _load_json(run_dir / "manifest.json")
        assert resumed_manifest["inventory_snapshot"] == snapshot_metadata
        assert resumed_manifest["runtime_attestation"] == runtime_attestation
        assert resumed_manifest["selected_packages"] == ["com.example.alpha"]

        missing_snapshot = RealDeviceObservationCorpus(
            Path(temporary_directory) / "invalid-dynamic", run_id="invalid-dynamic"
        )
        try:
            missing_snapshot.update_control_metadata(
                validation_profile="dynamic_inventory",
                selected_packages=["com.example.alpha"],
                inventory_packages=["com.example.alpha"],
            )
        except CorpusIntegrityError as error:
            assert "inventory snapshot metadata" in str(error)
        else:
            raise AssertionError("dynamic_inventory accepted missing snapshot metadata")


def assert_unredacted_physical_evidence_falls_back_to_metadata_only() -> None:
    private_value = "private.person@example.com"
    with TemporaryDirectory() as temporary_directory:
        run_dir = Path(temporary_directory) / "physical-run"
        corpus = RealDeviceObservationCorpus(run_dir, run_id="physical-private")
        evidence_dir = run_dir / "runtime"
        evidence_dir.mkdir()
        raw_screenshot = evidence_dir / "raw.png"
        raw_tree = evidence_dir / "raw.xml"
        raw_screenshot.write_bytes(b"raw-private-image")
        raw_tree.write_text(f"<node text='{private_value}'/>", encoding="utf-8")
        record = corpus.append_screen(
            {
                "screen_id": "private-screen",
                "app_package": "com.example.private",
                "screen_signature": "private-structure-hash",
                "screenshot_path": raw_screenshot,
                "accessibility_tree_path": raw_tree,
                "title_text": private_value,
                "visible_texts": [private_value],
                "content_descriptions": [private_value],
                "contains_personal_data": True,
                # No redacted-derivative attestations on purpose.
            },
            privacy_verified=True,
        )
        assert record.payload["evidence_mode"] == "metadata_only"
        assert record.payload["privacy_fallback_reason"] == "redacted_derivative_not_attested"
        assert record.payload["raw_artifacts_persisted"] is False
        assert "screenshot_path" not in record.payload
        assert "accessibility_tree_path" not in record.payload
        assert "visible_texts" not in record.payload
        element = corpus.append_element(
            {
                "element_id": "private-element",
                "screen_id": "private-screen",
                "label": private_value,
                "inferred_label": private_value,
                "text": private_value,
                "content_description": private_value,
                "resource_id": private_value,
                "role": "button",
            },
            privacy_verified=False,
        )
        for private_key in (
            "label",
            "inferred_label",
            "text",
            "content_description",
            "resource_id",
        ):
            assert private_key not in element.payload
        assert private_value not in (run_dir / "observations.jsonl").read_text(encoding="utf-8")
        manifest = _load_json(run_dir / "manifest.json")
        assert manifest["raw_artifacts_persisted"] is False
        assert manifest["git_eligible"] is False
        assert corpus.verify_integrity()["ok"] is True


def assert_gold_catalog_promotion_and_automatic_final_actions_fail_closed() -> None:
    with TemporaryDirectory() as temporary_directory:
        corpus = RealDeviceObservationCorpus(
            Path(temporary_directory) / "physical-run", run_id="physical-policy"
        )
        rejected_payloads = [
            {"provenance": "real_device_gold", "app_package": "com.example"},
            {"measurement_source": "human_gold", "app_package": "com.example"},
            {"review_status": "approved", "app_package": "com.example"},
            {"canonical_catalog_version": "16.0.0", "app_package": "com.example"},
            {"proposed_catalog_version": "V16", "app_package": "com.example"},
            {"proposed_catalog_version": "V20", "app_package": "com.example"},
            {"proposed_catalog_version": "V21", "app_package": "com.example"},
            {"proposed_catalog_version": "V22", "app_package": "com.example"},
            {"canonical_mutation_allowed": True, "app_package": "com.example"},
        ]
        for index, payload in enumerate(rejected_payloads):
            try:
                corpus.append_app(payload, record_id=f"rejected-{index}")
            except CorpusIntegrityError:
                pass
            else:
                raise AssertionError(f"governance override accepted: {payload}")

        for record_type, payload in (
            (
                "transitions",
                {
                    "transition_id": "final-auto",
                    "auto_executed": True,
                    "is_final_action": True,
                    "unsafe_action": False,
                },
            ),
            (
                "transitions",
                {
                    "transition_id": "unsafe-auto",
                    "auto_executed": True,
                    "is_final_action": False,
                    "unsafe_action": True,
                },
            ),
            (
                "metrics",
                {
                    "metric_id": "unsafe-metric",
                    "unsafe_auto_click_count": 1,
                    "final_action_auto_click_count": 0,
                },
            ),
            (
                "metrics",
                {
                    "metric_id": "final-metric",
                    "unsafe_auto_click_count": 0,
                    "final_action_auto_click_count": 1,
                },
            ),
        ):
            try:
                corpus.append(record_type, payload)
            except CorpusIntegrityError:
                pass
            else:
                raise AssertionError(f"unsafe candidate record accepted: {record_type}")
        assert corpus.counts() == {table: 0 for table in RECORD_TABLES}
        try:
            corpus.update_control_metadata(
                device_type="physical_android",
                is_emulator=False,
                device_serial="emulator-5554",
            )
        except CorpusIntegrityError as exc:
            assert "emulator serial" in str(exc)
        else:
            raise AssertionError("emulator serial was accepted for physical corpus")


def assert_graph_candidate_cannot_leave_shadow_lifecycle() -> None:
    with TemporaryDirectory() as temporary_directory:
        run_dir = Path(temporary_directory) / "physical-run"
        corpus = RealDeviceObservationCorpus(run_dir, run_id="physical-graph")
        connection = sqlite3.connect(run_dir / GRAPH_DATABASE_FILENAME)
        route_values = (
            "route-test",
            "app-test",
            "goal-test",
            "account.delete",
            "screen-start",
            "screen-terminal",
            "[]",
            0.8,
            1,
            "approved",
            0,
            0,
            "2026-07-31T00:00:00Z",
            "2026-07-31T00:00:00Z",
        )
        try:
            try:
                connection.execute(
                    """
                    INSERT INTO universal_routes (
                      route_id, app_key, goal_key, target_function,
                      start_screen_fingerprint, destination_screen_fingerprint,
                      steps_json, confidence, provisional, status,
                      success_count, failure_count, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    route_values,
                )
            except sqlite3.IntegrityError as exc:
                assert "must remain shadow" in str(exc)
            else:
                raise AssertionError("approved physical graph route was accepted")
        finally:
            connection.close()
        corpus.refresh_after_graph_write()
        assert corpus.verify_integrity()["ok"] is True


def assert_shared_physical_validator_accepts_resumable_candidate_store() -> None:
    spec = importlib.util.spec_from_file_location("exitguide_real_device_validator_unit", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    validator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = validator
    spec.loader.exec_module(validator)
    app_manifest = _load_json(APP_MANIFEST_PATH)
    statuses = [
        {"app_package": str(app["app_package"]), "status": "skipped_missing"}
        for app in app_manifest["apps"]
    ]
    with TemporaryDirectory() as temporary_directory:
        run_dir = Path(temporary_directory) / "physical-run"
        corpus = RealDeviceObservationCorpus(run_dir, run_id="physical-validator")
        corpus.append_run(
            {
                "device_id": "physical-device-hash",
                "avd_name": "physical_android",
                "lifecycle_event": "started",
                "started_at": "2026-07-31T00:00:00Z",
            }
        )
        corpus.update_control_metadata(status="incomplete", app_statuses=statuses)
        report = validator.validate_corpus(
            run_dir,
            repo_root=ROOT,
            app_manifest_path=APP_MANIFEST_PATH,
        )
        assert report["ok"] is True, report["errors"]


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


if __name__ == "__main__":
    main()
