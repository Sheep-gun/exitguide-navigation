import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_graph_merge import (
    NavigationGraphMergeError,
    merge_validated_navigation_graph,
)
from app.services.navigation_performance import StageMeasurement
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


def main() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        root = Path(temporary_directory)
        source_path = root / "candidate.sqlite"
        destination_path = root / "canonical.sqlite"
        validation_path = root / "VALIDATED.json"
        source = UniversalNavigationGraphRepository(source_path)
        _seed_observation_graph(source_path)
        _seed_routes(source)
        _write_validation(validation_path, source_path)

        first = merge_validated_navigation_graph(
            candidate_database=source_path,
            validation_artifact=validation_path,
            destination_database=destination_path,
        )
        assert first.status == "passed"
        assert first.already_imported is False
        assert first.inserted_counts["universal_apps"] == 1
        assert first.inserted_counts["universal_screens"] == 2
        assert first.inserted_counts["universal_actions"] == 1
        assert first.inserted_counts["universal_transitions"] == 1
        assert first.inserted_counts["universal_routes"] == 1
        assert first.inserted_counts["route_performance"] == 1
        assert first.skipped_counts["unverified_routes"] == 1
        assert Path(first.backup_path).is_file()

        with sqlite3.connect(destination_path) as connection:
            lifecycle = dict(
                connection.execute(
                    "SELECT status, COUNT(*) FROM universal_routes GROUP BY status"
                ).fetchall()
            )
            assert lifecycle == {"verified_candidate": 1}
            assert connection.execute(
                "SELECT COUNT(*) FROM navigation_graph_imports"
            ).fetchone()[0] == 1

        second = merge_validated_navigation_graph(
            candidate_database=source_path,
            validation_artifact=validation_path,
            destination_database=destination_path,
        )
        assert second.already_imported is True
        assert not any(second.inserted_counts.values())

        broken_validation = root / "BROKEN.json"
        payload = json.loads(validation_path.read_text(encoding="utf-8"))
        payload["core_artifact_sha256"]["graph-candidate.sqlite"] = "0" * 64
        broken_validation.write_text(json.dumps(payload), encoding="utf-8")
        try:
            merge_validated_navigation_graph(
                candidate_database=source_path,
                validation_artifact=broken_validation,
                destination_database=root / "must-not-exist.sqlite",
            )
        except NavigationGraphMergeError:
            pass
        else:
            raise AssertionError("a mismatched validation hash must fail closed")
        assert not (root / "must-not-exist.sqlite").exists()
    print("navigation graph merge checks ok")


def _seed_observation_graph(database_path: Path) -> None:
    repository = UniversalNavigationGraphRepository(database_path)
    repository.ensure_app_scope("com.example.real", "1.2.3", "ko-KR")
    app_key = hashlib.sha256(
        "com.example.real|1.2.3|ko-kr".encode("utf-8")
    ).hexdigest()[:20]
    now = "2026-08-01T00:00:00+00:00"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO universal_screens VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("us_start", app_key, "MainActivity", "홈", "[]", now, now, 1),
        )
        connection.execute(
            "INSERT INTO universal_screens VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("us_end", app_key, "SettingsActivity", "설정", "[]", now, now, 1),
        )
        connection.execute(
            "INSERT INTO universal_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ua_settings",
                "us_start",
                "ue_settings",
                "settings",
                "설정",
                "button",
                "low",
                None,
                now,
                now,
                1,
            ),
        )
        connection.execute(
            "INSERT INTO universal_transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ut_settings",
                "us_start",
                "ua_settings",
                "us_end",
                1,
                0,
                now,
                now,
            ),
        )
        connection.commit()


def _seed_routes(repository: UniversalNavigationGraphRepository) -> None:
    safe_steps = [
        {
            "ordinal": 0,
            "kind": "click",
            "from_screen_fingerprint": "us_start",
            "element_key": "ue_settings",
            "label": "설정",
            "function_ids": ["settings.root"],
            "role": "button",
            "risk_level": "low",
            "expected_to_screen_fingerprint": "us_end",
            "terminal": False,
            "confidence": 1.0,
        },
        {
            "ordinal": 1,
            "kind": "stop",
            "from_screen_fingerprint": "us_end",
            "element_key": "ue_terminal",
            "label": "알림 설정",
            "function_ids": ["notification.settings"],
            "role": "button",
            "risk_level": "medium",
            "expected_to_screen_fingerprint": "us_end",
            "terminal": True,
            "confidence": 1.0,
        },
    ]
    verified = repository.save_route(
        app_package="com.example.real",
        app_version="1.2.3",
        locale="ko-KR",
        goal_text="알림 설정 열기",
        target_function="notification.settings",
        start_screen_fingerprint="us_start",
        destination_screen_fingerprint="us_end",
        steps=safe_steps,
        confidence=1.0,
        provisional=True,
    )
    session_id = "trusted-real-device-session"
    repository.performance.record_stage(
        session_id=session_id,
        app_package="com.example.real",
        app_version="1.2.3",
        locale="ko-KR",
        goal_key=verified.goal_key,
        target_function="notification.settings",
        start_screen_fingerprint="us_start",
        current_screen_fingerprint="us_end",
        destination_screen_fingerprint="us_end",
        decision_mode="function_graph_exploration",
        phase="destination_reached",
        action="stop",
        safe_to_execute=False,
        selected_risk_level="medium",
        selected_element_key="ue_terminal",
        route_id=verified.route_id,
        failure_type="",
        measurement=StageMeasurement(
            measurement_source="real_device",
            server_total_ms=50.0,
            exploration_elapsed_ms=5000.0,
        ),
    )
    repository.performance.apply_validation(
        session_id=session_id,
        destination_correct=True,
        safe_stop=True,
        unsafe_clicks=0,
        wrong_clicks=0,
        verification_level="human_gold",
    )
    repository.verify_route_candidate(verified.route_id)

    repository.save_route(
        app_package="com.example.real",
        app_version="1.2.3",
        locale="ko-KR",
        goal_text="설정 열기",
        target_function="settings.root",
        start_screen_fingerprint="us_start",
        destination_screen_fingerprint="us_end",
        steps=safe_steps,
        confidence=0.7,
        provisional=True,
    )


def _write_validation(path: Path, database_path: Path) -> None:
    digest = hashlib.sha256(database_path.read_bytes()).hexdigest()
    path.write_text(
        json.dumps(
            {
                "status": "passed",
                "validator": "Validate-RealDeviceObservationCorpus.py",
                "provenance": "real_device_observation_candidate",
                "run_id": "merge-unit-real-device-run",
                "core_artifact_sha256": {"graph-candidate.sqlite": digest},
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
