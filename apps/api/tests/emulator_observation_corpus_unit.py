import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.emulator_observation_corpus import (
    CANONICAL_CATALOG_SHA256,
    CANONICAL_CATALOG_VERSION,
    CANONICAL_EQUIVALENCE_SHA256,
    CHECKPOINT_FILENAME,
    DATABASE_FILENAME,
    JSONL_FILENAME,
    MANIFEST_FILENAME,
    PROVENANCE,
    RECORD_TABLES,
    ROUTE_LIFECYCLE,
    CorpusIntegrityError,
    EmulatorObservationCorpus,
    canonical_sha256,
)


def main() -> None:
    assert_all_required_tables_and_fields_are_append_only()
    assert_unverified_screen_falls_back_to_metadata_only()
    assert_verified_evidence_is_hashed_and_scoped_to_run()
    assert_checkpoint_resume_and_jsonl_repair_are_deterministic()
    assert_fixed_provenance_and_v15_baseline_fail_closed()
    print("Emulator observation corpus checks ok")


def assert_all_required_tables_and_fields_are_append_only() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory) / "run"
        corpus = EmulatorObservationCorpus(root, run_id="run-complete")
        evidence = root / "evidence"
        evidence.mkdir()
        screenshot = evidence / "screen.png"
        tree = evidence / "screen.xml"
        screenshot.write_bytes(b"redacted-png-evidence")
        tree.write_text("<hierarchy redacted='true'/>", encoding="utf-8")

        records = [
            corpus.append_run(
                {
                    "device_id": "emulator-5554",
                    "avd_name": "EGL_Universal_Play_API36",
                    "api_base_url": "http://10.0.2.2:8010",
                    "lifecycle_event": "started",
                    "started_at": "2026-07-31T00:00:00Z",
                }
            ),
            corpus.append_app(
                {
                    "app_observation_id": "app-youtube-v1",
                    "app_package": "com.google.android.youtube",
                    "app_name": "YouTube",
                    "app_version": "20.1",
                    "locale": "ko-KR",
                    "install_source": "google_play",
                }
            ),
            corpus.append_screen(
                {
                    "screen_id": "screen-settings",
                    "app_package": "com.google.android.youtube",
                    "app_name": "YouTube",
                    "app_version": "20.1",
                    "locale": "ko-KR",
                    "screen_signature": "sha256:screen-settings",
                    "screenshot_path": screenshot,
                    "accessibility_tree_path": tree,
                    "activity_name": ".SettingsActivity",
                    "title_text": "설정",
                    "visible_texts": ["설정", "구매 항목 및 멤버십"],
                    "content_descriptions": ["뒤로 가기"],
                    "resource_ids": ["youtube:id/purchases"],
                    "scrollable_regions": [[0, 200, 1080, 2200]],
                    "screen_type": "menu",
                    "login_state": "authenticated",
                    "prerequisite": "signed_in",
                    "contains_personal_data": False,
                    "collected_at": "2026-07-31T00:00:01Z",
                },
                privacy_verified=True,
            ),
            corpus.append_element(
                {
                    "element_id": "element-memberships",
                    "screen_id": "screen-settings",
                    "text": "구매 항목 및 멤버십",
                    "content_description": "",
                    "resource_id": "youtube:id/purchases",
                    "class_name": "android.widget.TextView",
                    "bounds": [32, 420, 1048, 548],
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "semantic_function_id": "subscription.manage",
                    "synonyms": ["구독 관리", "멤버십 관리"],
                    "expected_result": "membership menu",
                    "risk_level": "low",
                    "is_final_action": False,
                    "confidence": 0.98,
                    "evidence": {"source": "accessibility"},
                }
            ),
            corpus.append_transition(
                {
                    "transition_id": "transition-settings-membership",
                    "source_screen_id": "screen-settings",
                    "target_screen_id": "screen-membership",
                    "element_id": "element-memberships",
                    "action_type": "click",
                    "action_coordinates": [540, 484],
                    "transition_time_ms": 620,
                    "success": True,
                    "can_go_back": True,
                    "repeated_or_loop": False,
                    "auto_executed": True,
                    "is_final_action": False,
                    "unsafe_action": False,
                }
            ),
            corpus.append_goal(
                {
                    "goal_id": "goal-cancel-premium",
                    "app_package": "com.google.android.youtube",
                    "goal_text": "유튜브 프리미엄 구독을 해지하고 싶어",
                    "canonical_goal_id": "subscription.cancel",
                    "semantic_function_id": "subscription.cancel",
                    "terminal_candidate_screen_id": "screen-cancel-confirmation",
                    "terminal_candidate_element_id": "element-final-cancel",
                    "terminal_confidence": 0.94,
                    "status": "candidate_found",
                    "expected_terminal": "cancel confirmation boundary",
                    "evidence": ["screen-settings", "screen-membership"],
                }
            ),
            corpus.append_failure(
                {
                    "failure_id": "failure-decoy-login",
                    "app_package": "com.google.android.youtube",
                    "goal_id": "goal-cancel-premium",
                    "source_screen_id": "screen-settings",
                    "selected_candidate": "로그인",
                    "correct_candidate": "구매 항목 및 멤버십",
                    "failure_reason": "semantic decoy",
                    "missing_synonym_or_rule": "membership alias",
                    "policy_correction": "penalize auth action for cancellation goal",
                    "retry_result": "success",
                }
            ),
            corpus.append_metric(
                {
                    "metric_id": "metric-policy-youtube",
                    "app_package": "com.google.android.youtube",
                    "goal_id": "goal-cancel-premium",
                    "metric_dimension": "policy",
                    "destination_found_success": True,
                    "wrong_terminal_destination": False,
                    "exploration_time_ms": 8400,
                    "click_count": 4,
                    "scroll_count": 1,
                    "back_count": 0,
                    "repeat_screen_visit_count": 0,
                    "user_intervention_count": 0,
                    "unsafe_auto_click_count": 0,
                    "final_action_auto_click_count": 0,
                    "graph_reuse_rate": 0.75,
                    "perception_clickable_recall": 0.99,
                    "perception_icon_text_link_accuracy": 0.97,
                    "semantic_goal_match_accuracy": 0.96,
                    "semantic_disambiguation_accuracy": 0.95,
                }
            ),
            corpus.append_annotation(
                {
                    "annotation_id": "annotation-terminal",
                    "entity_type": "element",
                    "entity_id": "element-final-cancel",
                    "label": "final_consequential_action",
                    "value": True,
                    "confidence": 1.0,
                    "reviewer": "rule_engine",
                    "status": "shadow",
                }
            ),
        ]
        assert [record.sequence for record in records] == list(range(1, 10))
        assert corpus.counts() == {table: 1 for table in RECORD_TABLES}

        connection = sqlite3.connect(root / DATABASE_FILENAME)
        try:
            table_names = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert set(RECORD_TABLES) <= table_names
            run = connection.execute(
                "SELECT run_id, provenance, route_lifecycle, started_at FROM runs"
            ).fetchone()
            assert run == (
                "run-complete",
                PROVENANCE,
                ROUTE_LIFECYCLE,
                "2026-07-31T00:00:00Z",
            )
            metric = connection.execute(
                """
                SELECT destination_found_success, wrong_terminal_destination,
                       unsafe_auto_click_count, final_action_auto_click_count,
                       graph_reuse_rate, perception_clickable_recall,
                       perception_icon_text_link_accuracy,
                       semantic_goal_match_accuracy,
                       semantic_disambiguation_accuracy
                FROM metrics
                """
            ).fetchone()
            assert metric == (1, 0, 0, 0, 0.75, 0.99, 0.97, 0.96, 0.95)
            transition = connection.execute(
                """
                SELECT auto_executed, is_final_action, unsafe_action,
                       coordinates_json, back_available, is_loop
                FROM transitions
                """
            ).fetchone()
            assert transition == (1, 0, 0, "[540,484]", 1, 0)
            try:
                connection.execute("UPDATE metrics SET click_count = 99")
            except sqlite3.IntegrityError as exc:
                assert "append-only" in str(exc)
            else:
                raise AssertionError("append-only UPDATE trigger did not fire")
        finally:
            connection.close()

        events = _read_events(root / JSONL_FILENAME)
        assert len(events) == 9
        for event in events:
            claimed_event_sha = event.pop("event_sha256")
            assert claimed_event_sha == canonical_sha256(event)
            assert event["content_sha256"] == canonical_sha256(event["payload"])
            assert event["provenance"] == PROVENANCE
            assert event["route_lifecycle"] == ROUTE_LIFECYCLE
            assert event["canonical_catalog_version"] == CANONICAL_CATALOG_VERSION
            assert event["canonical_catalog_sha256"] == CANONICAL_CATALOG_SHA256
            assert event["canonical_equivalence_sha256"] == CANONICAL_EQUIVALENCE_SHA256
        assert corpus.verify_integrity()["ok"] is True
        manifest = json.loads((root / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        assert manifest["canonical_catalog"] == {
            "version": CANONICAL_CATALOG_VERSION,
            "sha256": CANONICAL_CATALOG_SHA256,
            "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "domain_count": 179,
            "function_count": 2866,
            "terminal_function_count": 2660,
            "intent_count": 2660,
        }
        assert manifest["safety"] == {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }


def assert_unverified_screen_falls_back_to_metadata_only() -> None:
    private_email = "private.person@example.com"
    private_phone = "010-1234-5678"
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory) / "run"
        corpus = EmulatorObservationCorpus(root, run_id="run-private")
        screen = corpus.append_screen(
            {
                "screen_id": "private-screen",
                "app_package": "com.example.private",
                "screen_signature": "structural-hash-only",
                "screenshot_path": "raw/private.png",
                "accessibility_tree_path": "raw/private.xml",
                "title_text": private_email,
                "visible_texts": [private_email, private_phone],
                "content_descriptions": [private_email],
                "activity_name": ".AccountActivity",
                "screen_type": "account",
                "contains_personal_data": True,
            },
            privacy_verified=False,
        )
        assert screen.payload["evidence_mode"] == "metadata_only"
        assert screen.payload["privacy_verified"] is False
        assert screen.payload["visible_text_count"] == 2
        assert "screenshot_path" not in screen.payload
        assert "accessibility_tree_path" not in screen.payload
        assert "visible_texts" not in screen.payload
        assert "title_text" not in screen.payload

        element = corpus.append_element(
            {
                "element_id": "private-element",
                "screen_id": "private-screen",
                "text": private_email,
                "content_description": private_phone,
                "bounds": [10, 10, 100, 100],
                "clickable": True,
            }
        )
        assert element.payload["evidence_mode"] == "metadata_only"
        assert "text" not in element.payload
        assert "content_description" not in element.payload

        raw_corpus = (root / JSONL_FILENAME).read_text(encoding="utf-8")
        assert private_email not in raw_corpus
        assert private_phone not in raw_corpus
        connection = sqlite3.connect(root / DATABASE_FILENAME)
        try:
            row = connection.execute(
                """
                SELECT screenshot_path, accessibility_tree_path, title_text,
                       evidence_mode, privacy_verified
                FROM screens WHERE screen_id='private-screen'
                """
            ).fetchone()
            assert row == (None, None, None, "metadata_only", 0)
        finally:
            connection.close()
        assert corpus.verify_integrity()["ok"] is True


def assert_verified_evidence_is_hashed_and_scoped_to_run() -> None:
    with TemporaryDirectory() as temporary_directory:
        parent = Path(temporary_directory)
        root = parent / "run"
        corpus = EmulatorObservationCorpus(root, run_id="run-evidence")
        evidence = root / "apps" / "example" / "screens"
        evidence.mkdir(parents=True)
        screenshot = evidence / "home.redacted.png"
        tree = evidence / "home.redacted.xml"
        screenshot.write_bytes(b"privacy-reviewed-redacted-image")
        tree.write_bytes(b"<hierarchy privacy-reviewed='true'/>")

        record = corpus.append_screen(
            {
                "screen_id": "verified-screen",
                "app_package": "com.example",
                "screenshot_path": screenshot,
                "accessibility_tree_path": tree,
                "title_text": "설정",
            },
            privacy_verified=True,
        )
        assert record.payload["screenshot_path"] == "apps/example/screens/home.redacted.png"
        assert record.payload["accessibility_tree_path"] == "apps/example/screens/home.redacted.xml"
        assert record.payload["screenshot_sha256"] == hashlib.sha256(screenshot.read_bytes()).hexdigest()
        assert record.payload["accessibility_tree_sha256"] == hashlib.sha256(tree.read_bytes()).hexdigest()
        assert record.payload["evidence_mode"] == "verified_evidence"

        external = parent / "unreviewed.png"
        external.write_bytes(b"not-in-corpus")
        try:
            corpus.append_screen(
                {
                    "screen_id": "external-screen",
                    "app_package": "com.example",
                    "screenshot_path": external,
                },
                privacy_verified=True,
            )
        except CorpusIntegrityError as exc:
            assert "inside the run corpus directory" in str(exc)
        else:
            raise AssertionError("external evidence path was accepted")


def assert_checkpoint_resume_and_jsonl_repair_are_deterministic() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory) / "run"
        corpus = EmulatorObservationCorpus(root, run_id="run-resume")
        payload = {
            "app_observation_id": "app-resume",
            "app_package": "com.example.resume",
            "app_name": "Resume",
            "app_version": "1",
            "locale": "ko-KR",
        }
        first = corpus.append_app(payload)
        corpus.save_checkpoint(
            {"app_index": 2, "goal_index": 4, "frontier": ["screen-a", "screen-b"]}
        )
        assert first.appended is True
        assert not list(root.glob(".*.tmp"))
        assert {DATABASE_FILENAME, JSONL_FILENAME, MANIFEST_FILENAME, CHECKPOINT_FILENAME} <= {
            path.name for path in root.iterdir()
        }

        # Model a crash after SQLite commit but before the JSONL mirror append.
        (root / JSONL_FILENAME).write_text("", encoding="utf-8")
        resumed = EmulatorObservationCorpus(root, run_id="run-resume", resume=True)
        assert resumed.resume_state == {
            "app_index": 2,
            "goal_index": 4,
            "frontier": ["screen-a", "screen-b"],
        }
        assert len(_read_events(root / JSONL_FILENAME)) == 1
        retry = resumed.append_app(payload)
        assert retry.appended is False
        assert retry.sequence == first.sequence
        second = resumed.append_annotation(
            {
                "annotation_id": "resume-note",
                "entity_type": "run",
                "entity_id": "run-resume",
                "label": "resumed",
                "value": True,
            }
        )
        assert second.sequence == 2
        assert resumed.verify_integrity()["ok"] is True

        try:
            resumed.append_app(dict(payload, app_name="Changed"))
        except CorpusIntegrityError as exc:
            assert "conflicting append" in str(exc)
        else:
            raise AssertionError("conflicting idempotent retry was accepted")

        try:
            EmulatorObservationCorpus(root, run_id="different-run", resume=True)
        except CorpusIntegrityError as exc:
            assert "SQLite metadata mismatch for run_id" in str(exc)
        else:
            raise AssertionError("run identity mismatch was accepted")


def assert_fixed_provenance_and_v15_baseline_fail_closed() -> None:
    with TemporaryDirectory() as temporary_directory:
        corpus = EmulatorObservationCorpus(Path(temporary_directory) / "run", run_id="run-pins")
        invalid_records = [
            {"provenance": "real_device_gold", "app_package": "com.example"},
            {"route_lifecycle": "approved", "app_package": "com.example"},
            {"canonical_catalog_version": "16.0.0", "app_package": "com.example"},
            {"canonical_catalog_sha256": "0" * 64, "app_package": "com.example"},
            {"canonical_mutation_allowed": True, "app_package": "com.example"},
        ]
        for index, payload in enumerate(invalid_records):
            try:
                corpus.append_app(payload, record_id=f"invalid-{index}")
            except CorpusIntegrityError as exc:
                assert "cannot override fixed" in str(exc)
            else:
                raise AssertionError(f"fixed corpus policy override was accepted: {payload}")
        assert corpus.counts()["apps"] == 0
        for record_type, payload in (
            (
                "transitions",
                {
                    "transition_id": "unsafe-transition",
                    "auto_executed": True,
                    "is_final_action": True,
                    "unsafe_action": False,
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
        ):
            try:
                corpus.append(record_type, payload)
            except CorpusIntegrityError:
                pass
            else:
                raise AssertionError(f"unsafe record was accepted: {record_type}")


def _read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


if __name__ == "__main__":
    main()
