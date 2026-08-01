import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.real_device_observation_corpus import RealDeviceObservationCorpus


ROOT = Path(__file__).resolve().parents[3]
BUILDER_PATH = ROOT / "scripts" / "Build-RealDeviceFunctionGraphArtifacts.py"
APP_MANIFEST_PATH = ROOT / "fixtures" / "navigation" / "real-device-observation-apps.v1.json"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "exitguide_real_device_function_graph_builder_unit", BUILDER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load_builder()


def main() -> None:
    assert_rates_require_explicit_attempt_counts()
    assert_latest_task_summary_prevents_cumulative_metric_double_counting()
    assert_hash_fields_are_format_checked_without_pii_false_positives()
    assert_validated_physical_run_builds_all_privacy_safe_artifacts()
    assert_existing_artifacts_require_explicit_overwrite()
    assert_sensitive_source_fails_without_partial_publication()
    assert_quarantine_marker_rejects_builder_input_with_reason_codes_only()
    assert_publication_failure_restores_existing_artifact_set()
    assert_unvalidated_or_incomplete_sources_fail_closed()
    print("Real-device function graph artifact checks ok")


def assert_hash_fields_are_format_checked_without_pii_false_positives() -> None:
    # A real SHA-256 can accidentally contain a Korean phone-number-shaped
    # digit run.  It remains safe structural evidence after exact validation.
    digest = "a01012345678b" + ("c" * 51)
    assert len(digest) == 64
    BUILDER._assert_privacy_safe(
        {
            "source_database_sha256": {"corpus.sqlite": digest},
            "semantic_commitment_sha256": digest,
        },
        location="hash-unit.json",
    )

    for payload in (
        {"semantic_commitment_sha256": "not-a-digest"},
        {"source_database_sha256": {"corpus.sqlite": "api_key=secret-value"}},
    ):
        try:
            BUILDER._assert_privacy_safe(payload, location="hash-unit.json")
        except BUILDER.ArtifactBuildError as error:
            assert "hash" in str(error) or "sha256" in str(error)
        else:
            raise AssertionError("malformed digest evidence was accepted")


def assert_rates_require_explicit_attempt_counts() -> None:
    legacy_only = BUILDER._performance_summary(
        [{"destination_found_success": 1, "wrong_terminal_destination": 0}],
        [],
    )
    assert legacy_only["success_rate"] is None
    assert legacy_only["false_positive_rate"] is None
    assert legacy_only["success_rate_basis"]["availability"] == "unavailable"
    assert legacy_only["success_rate_basis"]["unavailable_reason"] == (
        "explicit_attempt_count_missing"
    )


def assert_latest_task_summary_prevents_cumulative_metric_double_counting() -> None:
    rows = [
        {
            "metric_dimension": "policy",
            "task_id": "task_a",
            "click_count": 1,
            "scroll_count": 0,
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        },
        {
            "metric_dimension": "policy",
            "task_id": "task_a",
            "click_count": 2,
            "scroll_count": 1,
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        },
        {
            "metric_dimension": "task_summary",
            "task_id": "task_a",
            "attempt_number": 1,
            "attempt_count": 1,
            "success_count": 0,
            "false_positive_count": 0,
            "click_count": 2,
            "scroll_count": 1,
            "exploration_time_ms": 8000,
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        },
        {
            "metric_dimension": "task_summary",
            "task_id": "task_a",
            "attempt_number": 2,
            "attempt_count": 1,
            "success_count": 1,
            "false_positive_count": 0,
            "click_count": 3,
            "scroll_count": 1,
            "exploration_time_ms": 7000,
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        },
    ]
    summary = BUILDER._performance_summary(rows, [])
    assert summary["metric_row_policy"] == "latest_task_summary_per_task"
    assert summary["raw_metric_event_count"] == 4
    assert summary["measurement_count"] == 1
    assert summary["click_count"]["total"] == 3.0
    assert summary["scroll_count"]["total"] == 1.0
    assert summary["success_rate"] == 1.0
    assert summary["false_positive_rate"] == 0.0


def assert_validated_physical_run_builds_all_privacy_safe_artifacts() -> None:
    with TemporaryDirectory(prefix="exitguide-real-artifacts-") as temporary_directory:
        run_dir = Path(temporary_directory) / "run"
        _create_completed_run(run_dir)
        source_before = {
            name: BUILDER._sha256_file(run_dir / name)
            for name in ("corpus.sqlite", "graph-candidate.sqlite")
        }
        result = BUILDER.build_artifacts(
            run_dir,
            repo_root=ROOT,
            app_manifest_path=APP_MANIFEST_PATH,
        )
        assert result["ok"] is True
        assert result["source_sha256"] == source_before
        assert result["counts"]["apps"] == 1
        expected = {
            "common-menu-synonyms.json",
            "destination-candidates.jsonl",
            "manual-validation.json",
            "navigation-report.json",
        }
        assert expected <= {path.name for path in run_dir.iterdir()}
        assert {
            name: BUILDER._sha256_file(run_dir / name)
            for name in ("corpus.sqlite", "graph-candidate.sqlite")
        } == source_before

        synonyms = _load_json(run_dir / "common-menu-synonyms.json")
        assert synonyms["provenance"] == "real_device_observation_candidate"
        assert synonyms["route_lifecycle"] == "shadow"
        assert synonyms["canonical_mutation_allowed"] is False
        assert synonyms["metadata_only_elements_excluded"] == 1
        mapped = {entry["semantic_function_id"]: entry for entry in synonyms["entries"]}
        assert "subscription.manage" in mapped
        assert "subscription.cancel.confirm" in mapped
        assert mapped["subscription.manage"]["lifecycle"] == "candidate"
        assert mapped["subscription.manage"]["human_review_required"] is True
        assert any(
            observed["label"] == "구독 관리"
            for observed in mapped["subscription.manage"]["observed_labels"]
        )

        destinations = [
            json.loads(line)
            for line in (run_dir / "destination-candidates.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        assert len(destinations) == 1
        destination = destinations[0]
        assert destination["semantic_function_id"] == "subscription.cancel.confirm"
        assert destination["terminal_label"] == "구독 해지"
        assert destination["is_final_action"] is True
        assert destination["manual_confirmation_required"] is True
        assert destination["serving_allowed"] is False
        assert destination["shadow_routes"][0]["status"] == "shadow"
        assert destination["shadow_routes"][0]["step_count"] == 2

        report = _load_json(run_dir / "navigation-report.json")
        assert report["source_validation"]["ok"] is True
        assert report["overall"]["counts"] == {
            "apps": 1,
            "screens": 3,
            "elements": 3,
            "transitions": 1,
            "goals": 1,
            "failures": 1,
            "destination_candidates": 1,
            "shadow_routes": 1,
            "metadata_only_elements_excluded_from_semantics": 1,
        }
        performance = report["overall"]["performance"]
        assert performance["success_rate"] == 1.0
        assert performance["success_rate_basis"]["attempt_count"] == 1
        assert performance["success_rate_basis"]["numerator_count"] == 1
        assert performance["false_positive_rate"] is None
        assert performance["exploration_time_ms"] == {
            "sample_count": 1,
            "median": 10000.0,
            "p95": 10000.0,
        }
        assert performance["click_count"]["total"] == 3.0
        assert performance["scroll_count"]["total"] == 2.0
        assert performance["back_count"]["total"] == 1.0
        assert performance["repeat_screen_visit_count"]["total"] == 1.0
        assert performance["user_intervention_count"]["total"] == 0.0
        assert performance["decision_modes"] == [{"value": "graph_best_first", "count": 1}]
        assert performance["fallback_modes"] == [{"value": "semantic_exact", "count": 1}]
        assert performance["unsafe_auto_click_count"] == 0
        assert performance["final_action_auto_click_count"] == 0

        manual = _load_json(run_dir / "manual-validation.json")
        assert manual["canonical_promotion"]["recommendation"] == (
            "not_recommended_until_human_review"
        )
        assert manual["canonical_promotion"]["canonical_write_allowed"] is False
        review_types = {item["review_type"] for item in manual["review_items"]}
        assert {
            "destination_candidate",
            "recorded_failure",
            "semantic_label_metadata_only",
        } <= review_types

        combined = "\n".join(
            (run_dir / name).read_text(encoding="utf-8") for name in expected
        )
        assert "private.person@example.com" not in combined
        assert "screenshot_path" not in combined
        assert "accessibility_tree_path" not in combined
        assert "goal_text" not in combined
        assert "구독을 해지하고 싶어" not in combined


def assert_existing_artifacts_require_explicit_overwrite() -> None:
    with TemporaryDirectory(prefix="exitguide-real-artifacts-collision-") as temporary_directory:
        run_dir = Path(temporary_directory) / "run"
        _create_completed_run(run_dir)
        BUILDER.build_artifacts(
            run_dir,
            repo_root=ROOT,
            app_manifest_path=APP_MANIFEST_PATH,
        )
        try:
            BUILDER.build_artifacts(
                run_dir,
                repo_root=ROOT,
                app_manifest_path=APP_MANIFEST_PATH,
            )
        except BUILDER.ArtifactBuildError as exc:
            assert "without --force" in str(exc)
        else:
            raise AssertionError("existing artifacts were silently replaced")
        rebuilt = BUILDER.build_artifacts(
            run_dir,
            repo_root=ROOT,
            app_manifest_path=APP_MANIFEST_PATH,
            overwrite=True,
        )
        assert rebuilt["ok"] is True


def assert_sensitive_source_fails_without_partial_publication() -> None:
    with TemporaryDirectory(prefix="exitguide-real-artifacts-sensitive-") as temporary_directory:
        run_dir = Path(temporary_directory) / "run"
        _create_completed_run(run_dir, verified_sensitive=True)
        existing = run_dir / "common-menu-synonyms.json"
        existing_payload = '{"existing_review_artifact":true}\n'
        existing.write_text(existing_payload, encoding="utf-8")
        original_validate_run = BUILDER._validate_run
        BUILDER._validate_run = lambda *_args, **_kwargs: {
            "ok": True,
            "validator": "synthetic_privacy_preflight_unit",
            "error_count": 0,
        }
        try:
            try:
                BUILDER.build_artifacts(
                    run_dir,
                    repo_root=ROOT,
                    app_manifest_path=APP_MANIFEST_PATH,
                    overwrite=True,
                )
            except BUILDER.ArtifactBuildError as exc:
                message = str(exc)
                assert "source corpus rejected by privacy preflight" in message
                assert "social_handle at $.elements" in message
                assert "synthetic_test_account" not in message
            else:
                raise AssertionError("privacy-sensitive source was accepted")
        finally:
            BUILDER._validate_run = original_validate_run
        assert existing.read_text(encoding="utf-8") == existing_payload
        assert not any(
            (run_dir / name).exists()
            for name in BUILDER.OUTPUT_FILENAMES
            if name != existing.name
        )
        assert not list(run_dir.glob(".function-graph-artifacts.*.staging"))
        assert not list(run_dir.glob(".function-graph-artifacts.*.backup"))


def assert_quarantine_marker_rejects_builder_input_with_reason_codes_only() -> None:
    with TemporaryDirectory(prefix="exitguide-real-artifacts-quarantine-") as temporary_directory:
        run_dir = Path(temporary_directory) / "run"
        _create_completed_run(run_dir)
        marker_path = run_dir / "QUARANTINED.json"
        cases = (
            (
                {"status": "quarantined", "builder_input_allowed": True},
                "source eligibility rejected: source_run_quarantined",
            ),
            (
                {"status": "review_pending", "builder_input_allowed": False},
                "source eligibility rejected: builder_input_disallowed",
            ),
        )
        for fields, expected_message in cases:
            marker = {
                **fields,
                "reason_codes": ["marker-private-sentinel@example.invalid"],
                "disposition": "marker-private-sentinel@example.invalid",
            }
            marker_path.write_text(
                json.dumps(marker, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            source_hashes = {
                name: BUILDER._sha256_file(run_dir / name)
                for name in ("corpus.sqlite", "graph-candidate.sqlite", "QUARANTINED.json")
            }
            try:
                BUILDER.build_artifacts(
                    run_dir,
                    repo_root=ROOT,
                    app_manifest_path=APP_MANIFEST_PATH,
                )
            except BUILDER.ArtifactBuildError as exc:
                message = str(exc)
                assert message == expected_message
                assert "marker-private-sentinel" not in message
                assert "reason_codes" not in message
                assert "disposition" not in message
            else:
                raise AssertionError("quarantined builder input was accepted")
            assert source_hashes == {
                name: BUILDER._sha256_file(run_dir / name)
                for name in ("corpus.sqlite", "graph-candidate.sqlite", "QUARANTINED.json")
            }
            assert not any(
                (run_dir / name).exists() for name in BUILDER.OUTPUT_FILENAMES
            )


def assert_publication_failure_restores_existing_artifact_set() -> None:
    with TemporaryDirectory(prefix="exitguide-real-artifacts-rollback-") as temporary_directory:
        run_dir = Path(temporary_directory) / "run"
        _create_completed_run(run_dir)
        existing = run_dir / "common-menu-synonyms.json"
        existing_payload = '{"existing_review_artifact":true}\n'
        existing.write_text(existing_payload, encoding="utf-8")
        original_replace = BUILDER.os.replace
        failure_injected = False

        def fail_during_second_publish(source, destination):
            nonlocal failure_injected
            source_path = Path(source)
            destination_path = Path(destination)
            if (
                not failure_injected
                and source_path.parent.name.endswith(".staging")
                and destination_path.parent == run_dir
                and destination_path.name == "destination-candidates.jsonl"
            ):
                failure_injected = True
                raise OSError("synthetic publication failure")
            return original_replace(source, destination)

        BUILDER.os.replace = fail_during_second_publish
        try:
            try:
                BUILDER.build_artifacts(
                    run_dir,
                    repo_root=ROOT,
                    app_manifest_path=APP_MANIFEST_PATH,
                    overwrite=True,
                )
            except OSError as exc:
                assert "synthetic publication failure" in str(exc)
            else:
                raise AssertionError("synthetic publication failure did not interrupt publish")
        finally:
            BUILDER.os.replace = original_replace
        assert failure_injected is True
        assert existing.read_text(encoding="utf-8") == existing_payload
        assert not any(
            (run_dir / name).exists()
            for name in BUILDER.OUTPUT_FILENAMES
            if name != existing.name
        )
        assert not list(run_dir.glob(".function-graph-artifacts.*.staging"))
        assert not list(run_dir.glob(".function-graph-artifacts.*.backup"))


def assert_unvalidated_or_incomplete_sources_fail_closed() -> None:
    with TemporaryDirectory(prefix="exitguide-real-artifacts-invalid-") as temporary_directory:
        run_dir = Path(temporary_directory) / "missing"
        run_dir.mkdir()
        try:
            BUILDER.build_artifacts(
                run_dir,
                repo_root=ROOT,
                app_manifest_path=APP_MANIFEST_PATH,
            )
        except BUILDER.ArtifactBuildError as exc:
            assert "required validated source is missing" in str(exc)
        else:
            raise AssertionError("missing source databases were accepted")


def _create_completed_run(run_dir: Path, *, verified_sensitive: bool = False) -> None:
    corpus = RealDeviceObservationCorpus(run_dir, run_id="physical-artifact-unit")
    evidence_dir = run_dir / "apps" / "com.google.android.youtube" / "screens"
    evidence_dir.mkdir(parents=True)

    def evidence(name: str) -> tuple[Path, Path]:
        image = evidence_dir / f"{name}.redacted.png"
        tree = evidence_dir / f"{name}.redacted.xml"
        image.write_bytes(f"redacted-{name}-image".encode("utf-8"))
        tree.write_text(f"<hierarchy redacted='true' id='{name}'/>", encoding="utf-8")
        return image, tree

    settings_image, settings_tree = evidence("settings")
    terminal_image, terminal_tree = evidence("terminal")
    corpus.append_run(
        {
            "device_id": "physical-test-device",
            "avd_name": "physical_android",
            "lifecycle_event": "started",
            "started_at": "2026-07-31T00:00:00Z",
        }
    )
    corpus.append_app(
        {
            "app_observation_id": "youtube-observation",
            "app_package": "com.google.android.youtube",
            "app_name": "YouTube",
            "app_version": "20.1",
            "locale": "ko-KR",
            "status": "installed_observed",
        }
    )
    corpus.append_screen(
        {
            "screen_id": "screen-settings",
            "app_package": "com.google.android.youtube",
            "app_name": "YouTube",
            "app_version": "20.1",
            "locale": "ko-KR",
            "screen_signature": "screen-settings",
            "screenshot_path": settings_image,
            "accessibility_tree_path": settings_tree,
            "screenshot_redacted": True,
            "accessibility_tree_redacted": True,
            "activity_name": ".SettingsActivity",
            "title_text": "설정",
            "visible_texts": ["구독 관리"],
            "content_descriptions": [],
            "resource_ids": ["youtube:id/subscriptions"],
            "scrollable_regions": [],
            "screen_type": "menu",
            "prerequisites": ["signed_in"],
            "contains_personal_data": False,
            "collected_at": "2026-07-31T00:00:01Z",
        },
        privacy_verified=True,
    )
    corpus.append_screen(
        {
            "screen_id": "screen-terminal",
            "app_package": "com.google.android.youtube",
            "app_name": "YouTube",
            "app_version": "20.1",
            "locale": "ko-KR",
            "screen_signature": "screen-terminal",
            "screenshot_path": terminal_image,
            "accessibility_tree_path": terminal_tree,
            "screenshot_redacted": True,
            "accessibility_tree_redacted": True,
            "activity_name": ".MembershipActivity",
            "title_text": "구독 관리",
            "visible_texts": ["구독 해지"],
            "content_descriptions": [],
            "resource_ids": ["youtube:id/cancel"],
            "scrollable_regions": [],
            "screen_type": "terminal_boundary",
            "prerequisites": ["subscription_active"],
            "contains_personal_data": False,
            "collected_at": "2026-07-31T00:00:02Z",
        },
        privacy_verified=True,
    )
    corpus.append_screen(
        {
            "screen_id": "screen-private",
            "app_package": "com.google.android.youtube",
            "app_name": "YouTube",
            "app_version": "20.1",
            "locale": "ko-KR",
            "screen_signature": "screen-private-structural",
            "title_text": "private.person@example.com",
            "visible_texts": ["private.person@example.com"],
            "content_descriptions": ["private.person@example.com"],
            "screen_type": "account",
            "contains_personal_data": True,
            "collected_at": "2026-07-31T00:00:03Z",
        },
        privacy_verified=False,
    )
    corpus.append_element(
        {
            "element_id": "element-subscription-manage",
            "screen_id": "screen-settings",
            "text": "@synthetic_test_account" if verified_sensitive else "구독 관리",
            "content_description": "멤버십 관리",
            "resource_id": "youtube:id/subscriptions",
            "class_name": "android.widget.TextView",
            "bounds": [10, 300, 1070, 450],
            "clickable": True,
            "enabled": True,
            "selected": False,
            "inferred_icon_semantics": ["membership"],
            "semantic_function_id": "subscription.manage",
            "synonyms": ["내 구독"],
            "expected_outcome": "subscription menu",
            "risk_level": "low",
            "is_final_action": False,
            "confidence": 0.98,
            "evidence": {"source": "accessibility"},
        }
    )
    corpus.append_element(
        {
            "element_id": "element-cancel-final",
            "screen_id": "screen-terminal",
            "text": "구독 해지",
            "content_description": "멤버십 종료",
            "resource_id": "youtube:id/cancel",
            "class_name": "android.widget.Button",
            "bounds": [10, 1800, 1070, 1950],
            "clickable": True,
            "enabled": True,
            "selected": False,
            "inferred_icon_semantics": [],
            "semantic_function_id": "subscription.cancel.confirm",
            "synonyms": ["구독 취소"],
            "expected_outcome": "final cancellation action",
            "risk_level": "high",
            "is_final_action": True,
            "confidence": 0.96,
            "evidence": {"source": "accessibility"},
        }
    )
    corpus.append_element(
        {
            "element_id": "element-private",
            "screen_id": "screen-private",
            "text": "private.person@example.com",
            "content_description": "private.person@example.com",
            "resource_id": "youtube:id/private",
            "class_name": "android.widget.TextView",
            "bounds": [10, 10, 100, 100],
            "clickable": True,
            "enabled": True,
            "selected": False,
            "semantic_function_id": "account.entry",
            "synonyms": ["private.person@example.com"],
            "risk_level": "low",
            "is_final_action": False,
            "confidence": 0.9,
        }
    )
    corpus.append_transition(
        {
            "transition_id": "transition-settings-terminal",
            "source_screen_id": "screen-settings",
            "target_screen_id": "screen-terminal",
            "action_type": "click",
            "element_id": "element-subscription-manage",
            "ui_element_id": "element-subscription-manage",
            "selected_label": "멤버십 관리",
            "auto_action_guard": {
                "policy_version": "egl-real-device-auto-action.v1",
                "evaluation_phase": "pre_execution",
                "action_type": "click",
                "allowed": True,
                "computed_final_or_consequential": False,
                "safe_menu_match": True,
                "reason": "physical_safe_menu_navigation",
            },
            "coordinates": [540, 375],
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
    )
    corpus.append_goal(
        {
            "goal_id": "goal-cancel-subscription",
            "app_package": "com.google.android.youtube",
            "goal_text": "구독을 해지하고 싶어",
            "standard_goal_id": "subscription.cancel.confirm",
            "semantic_function_id": "subscription.cancel.confirm",
            "terminal_candidate_screen_id": "screen-terminal",
            "terminal_candidate_element_id": "element-cancel-final",
            "terminal_confidence": 0.95,
            "status": "candidate_found",
        }
    )
    corpus.append_failure(
        {
            "failure_id": "failure-wrong-membership-menu",
            "app_package": "com.google.android.youtube",
            "goal_id": "goal-cancel-subscription",
            "user_goal": "구독을 해지하고 싶어",
            "screen_id": "screen-settings",
            "selected_candidate": "구독 피드",
            "correct_candidate": "구독 관리",
            "failure_reason": "content feed confused with billing membership",
            "required_synonym_or_label": "membership management",
            "policy_change": "penalize content-feed candidates for cancellation goals",
            "retest_result": "success",
        }
    )
    corpus.append_metric(
        {
            "metric_id": "metric-youtube-cancel",
            "app_package": "com.google.android.youtube",
            "goal_id": "goal-cancel-subscription",
            "metric_dimension": "policy",
            "perception_clickable_recall": 1.0,
            "perception_icon_text_link_accuracy": 1.0,
            "semantic_goal_match_accuracy": 1.0,
            "semantic_disambiguation_accuracy": 1.0,
            "attempt_count": 1,
            "success_count": 1,
            "destination_found_success": True,
            "wrong_terminal_destination": None,
            "exploration_time_ms": 10000,
            "click_count": 3,
            "scroll_count": 2,
            "back_count": 1,
            "repeat_screen_visit_count": 1,
            "user_intervention_count": 0,
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
            "graph_reuse_rate": 0.5,
            "decision_mode": "graph_best_first",
            "fallback_mode": "semantic_exact",
        }
    )
    corpus.append_annotation(
        {
            "annotation_id": "annotation-final-boundary",
            "entity_type": "element",
            "entity_id": "element-cancel-final",
            "label": "final_action_boundary",
            "value": True,
            "reviewer": "rule_engine",
            "status": "candidate",
        }
    )

    graph = sqlite3.connect(run_dir / "graph-candidate.sqlite")
    try:
        graph.execute("PRAGMA foreign_keys=ON")
        graph.execute(
            """
            INSERT INTO universal_apps (
              app_key, app_package, app_version, locale, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "app-youtube",
                "com.google.android.youtube",
                "20.1",
                "ko-KR",
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:03Z",
            ),
        )
        for screen_id, title in (
            ("screen-settings", "settings"),
            ("screen-terminal", "terminal boundary"),
        ):
            graph.execute(
                """
                INSERT INTO universal_screens (
                  screen_fingerprint, app_key, activity_name, title, structure_json,
                  first_seen_at, last_seen_at, seen_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    screen_id,
                    "app-youtube",
                    ".SafeActivity",
                    title,
                    "{}",
                    "2026-07-31T00:00:00Z",
                    "2026-07-31T00:00:03Z",
                    1,
                ),
            )
        graph.execute(
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
                "app-youtube",
                "goal-hash",
                "subscription.cancel.confirm",
                "screen-settings",
                "screen-terminal",
                '[{"screen":"settings"},{"screen":"terminal"}]',
                0.9,
                1,
                "shadow",
                1,
                0,
                "2026-07-31T00:00:00Z",
                "2026-07-31T00:00:03Z",
            ),
        )
        graph.commit()
    finally:
        graph.close()
    corpus.refresh_after_graph_write()

    app_manifest = _load_json(APP_MANIFEST_PATH)
    statuses = [
        {
            "app_package": str(app["app_package"]),
            "status": (
                "installed_observed"
                if app["app_package"] == "com.google.android.youtube"
                else "skipped_missing"
            ),
        }
        for app in app_manifest["apps"]
    ]
    corpus.update_control_metadata(
        status="completed",
        app_statuses=statuses,
        device_type="physical_android",
        is_emulator=False,
        device_serial="physical-test-device",
        collection_mode="safe_explore",
    )


def _load_json(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


if __name__ == "__main__":
    main()
