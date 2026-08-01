from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = ROOT / "scripts" / "Validate-EmulatorObservationCorpus.py"
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "exitguide_emulator_observation_validator",
        VALIDATOR_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()

from app.services.emulator_observation_corpus import EmulatorObservationCorpus  # noqa: E402


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": "safety-unit-run",
        "provenance": "emulator_observation",
        "route_lifecycle": "shadow",
        "canonical_catalog_mutation": False,
        "canonical_catalog": {
            "version": VALIDATOR.EXPECTED_CATALOG_VERSION,
            "sha256": VALIDATOR.EXPECTED_CATALOG_SHA256,
            "equivalence_sha256": VALIDATOR.EXPECTED_EQUIVALENCE_SHA256,
            "domain_count": VALIDATOR.EXPECTED_DOMAIN_COUNT,
            "function_count": VALIDATOR.EXPECTED_FUNCTION_COUNT,
            "terminal_function_count": VALIDATOR.EXPECTED_TERMINAL_FUNCTION_COUNT,
            "intent_count": VALIDATOR.EXPECTED_INTENT_COUNT,
        },
        "safety": {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        },
    }


def _create_corpus_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;

            CREATE TABLE apps (
              app_package TEXT PRIMARY KEY,
              app_name TEXT NOT NULL,
              app_version TEXT NOT NULL,
              locale TEXT NOT NULL
            );

            CREATE TABLE runs (
              run_id TEXT PRIMARY KEY,
              provenance TEXT NOT NULL,
              route_lifecycle TEXT NOT NULL,
              started_at TEXT NOT NULL
            );

            CREATE TABLE screens (
              screen_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              app_package TEXT NOT NULL,
              app_name TEXT NOT NULL,
              app_version TEXT NOT NULL,
              locale TEXT NOT NULL,
              screen_signature TEXT NOT NULL,
              screenshot_path TEXT NOT NULL,
              accessibility_tree_path TEXT NOT NULL,
              activity_name TEXT NOT NULL,
              title_text TEXT NOT NULL,
              visible_texts_json TEXT NOT NULL,
              content_descriptions_json TEXT NOT NULL,
              resource_ids_json TEXT NOT NULL,
              scrollable_regions_json TEXT NOT NULL,
              screen_type TEXT NOT NULL,
              prerequisites_json TEXT NOT NULL,
              contains_personal_data INTEGER NOT NULL,
              privacy_status TEXT NOT NULL,
              screenshot_redacted INTEGER NOT NULL,
              collected_at TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id),
              FOREIGN KEY(app_package) REFERENCES apps(app_package)
            );

            CREATE TABLE elements (
              element_id TEXT PRIMARY KEY,
              screen_id TEXT NOT NULL,
              text TEXT NOT NULL,
              content_description TEXT NOT NULL,
              resource_id TEXT NOT NULL,
              class_name TEXT NOT NULL,
              bounds_json TEXT NOT NULL,
              clickable INTEGER NOT NULL,
              enabled INTEGER NOT NULL,
              selected INTEGER NOT NULL,
              inferred_icon_semantics_json TEXT NOT NULL,
              semantic_function_id TEXT NOT NULL,
              synonyms_json TEXT NOT NULL,
              expected_outcome TEXT NOT NULL,
              risk_level TEXT NOT NULL,
              is_final_action INTEGER NOT NULL,
              confidence REAL NOT NULL,
              evidence_json TEXT NOT NULL,
              FOREIGN KEY(screen_id) REFERENCES screens(screen_id)
            );

            CREATE TABLE transitions (
              transition_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              source_screen_id TEXT NOT NULL,
              target_screen_id TEXT,
              action_type TEXT NOT NULL,
              element_id TEXT,
              coordinates_json TEXT NOT NULL,
              scroll_direction TEXT NOT NULL,
              scroll_distance INTEGER NOT NULL,
              transition_ms INTEGER NOT NULL,
              success INTEGER NOT NULL,
              back_available INTEGER NOT NULL,
              is_loop INTEGER NOT NULL,
              error_text TEXT NOT NULL,
              auto_executed INTEGER NOT NULL,
              unsafe_action INTEGER NOT NULL,
              is_final_action INTEGER NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id),
              FOREIGN KEY(source_screen_id) REFERENCES screens(screen_id),
              FOREIGN KEY(target_screen_id) REFERENCES screens(screen_id),
              FOREIGN KEY(element_id) REFERENCES elements(element_id)
            );

            CREATE TABLE goals (
              goal_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              app_package TEXT NOT NULL,
              user_goal TEXT NOT NULL,
              standard_goal_id TEXT NOT NULL,
              terminal_candidate_screen_id TEXT,
              terminal_candidate_element_id TEXT,
              status TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id),
              FOREIGN KEY(app_package) REFERENCES apps(app_package),
              FOREIGN KEY(terminal_candidate_screen_id) REFERENCES screens(screen_id),
              FOREIGN KEY(terminal_candidate_element_id) REFERENCES elements(element_id)
            );

            CREATE TABLE failures (
              failure_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              app_package TEXT NOT NULL,
              user_goal TEXT NOT NULL,
              screen_id TEXT,
              selected_candidate TEXT NOT NULL,
              correct_candidate TEXT NOT NULL,
              failure_reason TEXT NOT NULL,
              required_synonym_or_label TEXT NOT NULL,
              policy_change TEXT NOT NULL,
              retest_result TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id),
              FOREIGN KEY(app_package) REFERENCES apps(app_package),
              FOREIGN KEY(screen_id) REFERENCES screens(screen_id)
            );

            CREATE TABLE metrics (
              metric_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              app_package TEXT NOT NULL,
              perception_clickable_recall REAL NOT NULL,
              perception_icon_text_link_accuracy REAL NOT NULL,
              semantic_goal_match_accuracy REAL NOT NULL,
              semantic_disambiguation_accuracy REAL NOT NULL,
              destination_found_success INTEGER NOT NULL,
              wrong_terminal_destination INTEGER NOT NULL,
              exploration_time_ms INTEGER NOT NULL,
              click_count INTEGER NOT NULL,
              scroll_count INTEGER NOT NULL,
              back_count INTEGER NOT NULL,
              repeat_screen_visit_count INTEGER NOT NULL,
              user_intervention_count INTEGER NOT NULL,
              unsafe_auto_click_count INTEGER NOT NULL,
              final_action_auto_click_count INTEGER NOT NULL,
              graph_reuse_rate REAL NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id),
              FOREIGN KEY(app_package) REFERENCES apps(app_package)
            );

            CREATE TABLE annotations (
              annotation_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              entity_type TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              annotation_json TEXT NOT NULL,
              FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            """
        )
        connection.execute(
            "INSERT INTO apps VALUES (?,?,?,?)",
            ("example.safe", "Example Safe App", "1.2.3", "ko-KR"),
        )
        connection.execute(
            "INSERT INTO runs VALUES (?,?,?,?)",
            ("safety-unit-run", "emulator_observation", "shadow", "2026-07-31T00:00:00+09:00"),
        )
        screens = (
            (
                "screen-one",
                "safety-unit-run",
                "example.safe",
                "Example Safe App",
                "1.2.3",
                "ko-KR",
                "signature-one",
                "apps/example.safe/screens/screen-one.png",
                "apps/example.safe/screens/screen-one.xml",
                "example.safe.HomeActivity",
                "Settings",
                '["Settings", "Account"]',
                '["Open account settings"]',
                '["example.safe:id/account"]',
                "[]",
                "menu",
                "[]",
                0,
                "clear",
                0,
                "2026-07-31T00:00:01+09:00",
            ),
            (
                "screen-two",
                "safety-unit-run",
                "example.safe",
                "Example Safe App",
                "1.2.3",
                "ko-KR",
                "signature-two",
                "apps/example.safe/screens/screen-two.png",
                "apps/example.safe/screens/screen-two.xml",
                "example.safe.AccountActivity",
                "Account",
                '["Account", "Delete account"]',
                '["Delete account"]',
                '["example.safe:id/delete"]',
                "[]",
                "terminal_boundary",
                '["authenticated"]',
                0,
                "clear",
                0,
                "2026-07-31T00:00:02+09:00",
            ),
        )
        connection.executemany(
            "INSERT INTO screens VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            screens,
        )
        connection.executemany(
            "INSERT INTO elements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    "element-account",
                    "screen-one",
                    "Account",
                    "Open account settings",
                    "example.safe:id/account",
                    "android.widget.Button",
                    "[20,200][500,320]",
                    1,
                    1,
                    0,
                    '["account"]',
                    "account.settings",
                    '["My account"]',
                    "Open account settings",
                    "low",
                    0,
                    0.98,
                    '["accessibility_text"]',
                ),
                (
                    "element-delete",
                    "screen-two",
                    "Delete account",
                    "Delete account",
                    "example.safe:id/delete",
                    "android.widget.Button",
                    "[20,800][500,920]",
                    1,
                    1,
                    0,
                    '["delete"]',
                    "account.delete",
                    '["Close account"]',
                    "Permanently delete account",
                    "critical",
                    1,
                    0.99,
                    '["accessibility_text", "visual_confirmation"]',
                ),
            ),
        )
        connection.execute(
            "INSERT INTO transitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "transition-one",
                "safety-unit-run",
                "screen-one",
                "screen-two",
                "click",
                "element-account",
                "[260,260]",
                "",
                0,
                180,
                1,
                1,
                0,
                "",
                1,
                0,
                0,
            ),
        )
        connection.execute(
            "INSERT INTO goals VALUES (?,?,?,?,?,?,?,?)",
            (
                "goal-one",
                "safety-unit-run",
                "example.safe",
                "Delete my account",
                "account.delete",
                "screen-two",
                "element-delete",
                "destination_found_user_action_required",
            ),
        )
        connection.execute(
            "INSERT INTO failures VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "failure-one",
                "safety-unit-run",
                "example.safe",
                "Turn off marketing",
                "screen-one",
                "Account",
                "Notifications",
                "candidate not visible",
                "marketing preferences",
                "prefer notification settings",
                "pending",
            ),
        )
        connection.execute(
            "INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "metric-one",
                "safety-unit-run",
                "example.safe",
                1.0,
                1.0,
                1.0,
                1.0,
                1,
                0,
                180,
                1,
                0,
                0,
                0,
                0,
                0,
                0,
                1.0,
            ),
        )
        connection.execute(
            "INSERT INTO annotations VALUES (?,?,?,?,?)",
            (
                "annotation-one",
                "safety-unit-run",
                "screen",
                "4111111111111111",
                '{"boundary":"user_owned_final_press"}',
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _create_graph_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE universal_routes (route_id TEXT PRIMARY KEY, status TEXT NOT NULL, provisional INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO universal_routes VALUES (?,?,?)",
            ("route-one", "shadow", 1),
        )
        connection.commit()
    finally:
        connection.close()


def _create_run(root: Path) -> Path:
    run_dir = root / "safety-unit-run"
    evidence_dir = run_dir / "apps" / "example.safe" / "screens"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "screen-one.png").write_bytes(b"safe-redacted-image-one")
    (evidence_dir / "screen-two.png").write_bytes(b"safe-redacted-image-two")
    (evidence_dir / "screen-one.xml").write_text(
        '<hierarchy><node text="Settings" content-desc="Open account settings" '
        'resource-id="4111111111111111" bounds="[01012345678,9001011234567]"/></hierarchy>',
        encoding="utf-8",
    )
    (evidence_dir / "screen-two.xml").write_text(
        '<hierarchy><node text="Delete account" content-desc="Delete account"/></hierarchy>',
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(_manifest(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "safety-unit-run",
                "provenance": "emulator_observation",
                "route_lifecycle": "shadow",
                "canonical_catalog_version": VALIDATOR.EXPECTED_CATALOG_VERSION,
                "canonical_catalog_sha256": VALIDATOR.EXPECTED_CATALOG_SHA256,
                "canonical_equivalence_sha256": VALIDATOR.EXPECTED_EQUIVALENCE_SHA256,
                "canonical_mutation_allowed": False,
                "complete": True,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    jsonl_payloads = {
        "observations.jsonl": {
            "screen_id": "screen-one",
            "title": "Settings",
            "provenance": "emulator_observation",
            "route_lifecycle": "shadow",
            "canonical_catalog_version": VALIDATOR.EXPECTED_CATALOG_VERSION,
            "canonical_catalog_sha256": VALIDATOR.EXPECTED_CATALOG_SHA256,
            "canonical_equivalence_sha256": VALIDATOR.EXPECTED_EQUIVALENCE_SHA256,
            "record_id": "01012345678",
            "event_id": "4111111111111111",
            "content_sha256": "9001011234567",
            "coordinates": [4111111111111111, 1012345678],
        },
        "elements.jsonl": {"element_id": "element-account", "text": "Account"},
        "transitions.jsonl": {
            "transition_id": "transition-one",
            "auto_executed": True,
            "unsafe_action": False,
            "is_final_action": False,
        },
        "failures.jsonl": {"failure_id": "failure-one", "failure_reason": "candidate not visible"},
        "metrics.jsonl": {
            "metric_id": "metric-one",
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        },
    }
    for name, payload in jsonl_payloads.items():
        (run_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    _create_corpus_database(run_dir / "corpus.sqlite")
    _create_graph_database(run_dir / "graph-candidate.sqlite")
    return run_dir


def _validate(run_dir: Path) -> dict[str, Any]:
    return VALIDATOR.validate_corpus(run_dir, repo_root=ROOT)


def _error_codes(report: dict[str, Any]) -> set[str]:
    return {str(item["code"]) for item in report["errors"]}


def _assert_rejected(
    mutation: Callable[[Path], None],
    expected_code: str,
) -> None:
    with TemporaryDirectory(prefix="exitguide-emulator-safety-negative-") as temporary_directory:
        run_dir = _create_run(Path(temporary_directory))
        mutation(run_dir)
        report = _validate(run_dir)
        assert report["ok"] is False, report
        assert expected_code in _error_codes(report), report


def _update_manifest(run_dir: Path, update: Callable[[dict[str, Any]], None]) -> None:
    path = run_dir / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    update(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _execute(run_dir: Path, database: str, statement: str) -> None:
    connection = sqlite3.connect(run_dir / database)
    try:
        connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def assert_valid_corpus_passes_all_governance_and_safety_gates() -> None:
    with TemporaryDirectory(prefix="exitguide-emulator-safety-positive-") as temporary_directory:
        run_dir = _create_run(Path(temporary_directory))
        report = _validate(run_dir)
        assert report["ok"] is True, report
        assert report["error_count"] == 0
        assert report["checks"]["canonical_catalog"] == {
            "version": "15.0.0",
            "domains": 179,
            "functions": 2866,
            "terminal_functions": 2660,
            "intents": 2660,
        }
        assert report["checks"]["canonical_catalog_sha256"] == VALIDATOR.EXPECTED_CATALOG_SHA256
        assert report["checks"]["equivalence_sha256"] == VALIDATOR.EXPECTED_EQUIVALENCE_SHA256
        assert report["checks"]["v22_artifacts"] == []
        assert report["checks"]["v21_implementation_artifacts"] == []
        assert report["checks"]["metric_dimensions"] == ["perception", "policy", "semantics"]
        assert report["checks"]["unsafe_auto_transition_count"] == 0
        assert report["checks"]["final_action_auto_transition_count"] == 0


def assert_authoritative_store_schema_and_manifest_match_validator_contract() -> None:
    with TemporaryDirectory(prefix="exitguide-emulator-store-contract-") as temporary_directory:
        run_dir = Path(temporary_directory) / "store-contract"
        EmulatorObservationCorpus(run_dir, run_id="store-contract")
        manifest_errors: list[dict[str, str]] = []
        manifest_checks: dict[str, Any] = {}
        manifest = VALIDATOR._validate_manifest(
            run_dir / "manifest.json",
            manifest_errors,
            manifest_checks,
        )
        assert manifest_errors == [], manifest_errors
        assert manifest["provenance"] == "emulator_observation"
        assert manifest["route_lifecycle"] == "shadow"

        connection = sqlite3.connect(run_dir / "corpus.sqlite")
        try:
            schema_errors: list[dict[str, str]] = []
            schema_checks: dict[str, Any] = {}
            columns = VALIDATOR._validate_schema(
                connection,
                schema_errors,
                schema_checks,
                run_dir / "corpus.sqlite",
            )
        finally:
            connection.close()
        assert schema_errors == [], schema_errors
        assert set(VALIDATOR.REQUIRED_TABLES) <= set(columns)


def assert_invalid_provenance_is_rejected() -> None:
    def mutate(run_dir: Path) -> None:
        _update_manifest(run_dir, lambda payload: payload.__setitem__("provenance", "real_device_gold"))
        _execute(run_dir, "corpus.sqlite", "UPDATE runs SET provenance='real_device_gold'")

    _assert_rejected(mutate, "invalid_provenance")


def assert_non_shadow_route_is_rejected() -> None:
    def mutate(run_dir: Path) -> None:
        _execute(run_dir, "graph-candidate.sqlite", "UPDATE universal_routes SET status='approved'")

    _assert_rejected(mutate, "route_not_shadow")


def assert_broken_reference_is_rejected() -> None:
    def mutate(run_dir: Path) -> None:
        _execute(run_dir, "corpus.sqlite", "PRAGMA foreign_keys=OFF")
        _execute(run_dir, "corpus.sqlite", "UPDATE elements SET screen_id='missing-screen' WHERE element_id='element-account'")

    _assert_rejected(mutate, "referential_integrity")


def assert_real_pii_in_human_json_and_xml_is_rejected_without_echoing_values() -> None:
    with TemporaryDirectory(prefix="exitguide-emulator-real-pii-") as temporary_directory:
        run_dir = _create_run(Path(temporary_directory))
        with (run_dir / "observations.jsonl").open("a", encoding="utf-8") as destination:
            destination.write(
                json.dumps(
                    {
                        "visible_texts": [
                            "person@example.com",
                            "010-1234-5678",
                            "900101-1234567",
                            "4111 1111 1111 1111",
                        ],
                        "api_key": "sk_AAAAAAAAAAAAAAAAAAAAAAAA",
                    }
                )
                + "\n"
            )
        tree_path = run_dir / "apps" / "example.safe" / "screens" / "screen-one.xml"
        tree_path.write_text(
            '<hierarchy><node content-desc="010-9876-5432" resource-id="9001011234567"/></hierarchy>',
            encoding="utf-8",
        )
        report = _validate(run_dir)
        assert report["ok"] is False, report
        findings = [item for item in report["errors"] if item["code"] == "sensitive_data_detected"]
        assert findings
        labels = " ".join(item["message"] for item in findings)
        assert "email" in labels
        assert "phone" in labels
        assert "korean_resident_id" in labels
        assert "payment_card" in labels
        assert "api_key" in labels
        assert "generic_secret_key" in labels
        assert all("person@example.com" not in item["message"] for item in findings)


def assert_capture_only_run_accepts_empty_graph_and_run_summary() -> None:
    with TemporaryDirectory(prefix="exitguide-emulator-capture-only-") as temporary_directory:
        run_dir = _create_run(Path(temporary_directory))

        def update(payload: dict[str, Any]) -> None:
            payload["run_mode"] = "capture_only"
            payload["status"] = "captured"
            payload["screenshot_policy"] = "none"

        _update_manifest(run_dir, update)
        _execute(run_dir, "corpus.sqlite", "DELETE FROM transitions")
        _execute(run_dir, "corpus.sqlite", "UPDATE screens SET screenshot_path='' WHERE 1=1")
        _execute(run_dir, "corpus.sqlite", "ALTER TABLE metrics ADD COLUMN metric_dimension TEXT")
        _execute(run_dir, "corpus.sqlite", "UPDATE metrics SET metric_dimension='run_summary'")
        (run_dir / "transitions.jsonl").unlink()
        (run_dir / "failures.jsonl").unlink()
        (run_dir / "graph-candidate.sqlite").unlink()

        report = _validate(run_dir)
        assert report["ok"] is True, report
        assert report["checks"]["run_profile"]["capture_only"] is True
        assert report["checks"]["graph_candidate_present"] is False
        assert report["checks"]["corpus_row_counts"]["transitions"] == 0
        assert report["checks"]["metric_dimensions"] == ["perception", "policy", "semantics"]


def assert_completed_exploration_still_requires_transitions_and_graph() -> None:
    def mutate(run_dir: Path) -> None:
        _execute(run_dir, "corpus.sqlite", "DELETE FROM transitions")
        (run_dir / "transitions.jsonl").unlink()
        (run_dir / "graph-candidate.sqlite").unlink()

    _assert_rejected(mutate, "missing_run_files")

    def empty_graph(run_dir: Path) -> None:
        _execute(run_dir, "graph-candidate.sqlite", "DELETE FROM universal_routes")

    _assert_rejected(empty_graph, "graph_routes_empty")


def assert_unsafe_and_final_automatic_clicks_are_rejected() -> None:
    def unsafe(run_dir: Path) -> None:
        _execute(run_dir, "corpus.sqlite", "UPDATE transitions SET unsafe_action=1")

    def final(run_dir: Path) -> None:
        _execute(run_dir, "corpus.sqlite", "UPDATE transitions SET is_final_action=1")

    _assert_rejected(unsafe, "unsafe_auto_click")
    _assert_rejected(final, "final_action_auto_click")


def assert_missing_metric_dimension_is_rejected() -> None:
    def mutate(run_dir: Path) -> None:
        _execute(
            run_dir,
            "corpus.sqlite",
            "ALTER TABLE metrics RENAME COLUMN semantic_goal_match_accuracy TO ungoverned_semantic_score",
        )

    _assert_rejected(mutate, "missing_metric_fields")


def assert_manifest_cannot_claim_canonical_mutation_or_drift() -> None:
    def mutate(run_dir: Path) -> None:
        def update(payload: dict[str, Any]) -> None:
            payload["canonical_catalog_mutation"] = True
            payload["canonical_catalog"]["sha256"] = "0" * 64

        _update_manifest(run_dir, update)

    with TemporaryDirectory(prefix="exitguide-emulator-safety-canonical-") as temporary_directory:
        run_dir = _create_run(Path(temporary_directory))
        mutate(run_dir)
        report = _validate(run_dir)
        assert report["ok"] is False
        assert {"canonical_mutation_enabled", "manifest_canonical_mismatch"}.issubset(_error_codes(report))


def main() -> None:
    assert_valid_corpus_passes_all_governance_and_safety_gates()
    assert_authoritative_store_schema_and_manifest_match_validator_contract()
    assert_invalid_provenance_is_rejected()
    assert_non_shadow_route_is_rejected()
    assert_broken_reference_is_rejected()
    assert_real_pii_in_human_json_and_xml_is_rejected_without_echoing_values()
    assert_capture_only_run_accepts_empty_graph_and_run_summary()
    assert_completed_exploration_still_requires_transitions_and_graph()
    assert_unsafe_and_final_automatic_clicks_are_rejected()
    assert_missing_metric_dimension_is_rejected()
    assert_manifest_cannot_claim_canonical_mutation_or_drift()
    print("emulator observation corpus safety checks ok")


if __name__ == "__main__":
    main()
