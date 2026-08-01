from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_session_report import (  # noqa: E402
    NavigationSessionReportError,
    build_navigation_session_report,
    capture_navigation_session_baseline,
)


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "navigation report.sqlite"
        _create_fixture(database_path)
        assert capture_navigation_session_baseline(database_path) == 2

        before = database_path.stat()
        report = build_navigation_session_report(
            database_path,
            baseline_rowid=1,
            app_package="com.example.target",
            session_id="physical-secret-session-id",
        )
        after = database_path.stat()

        assert before.st_size == after.st_size
        assert before.st_mtime_ns == after.st_mtime_ns
        assert report["selection"]["selected_navigation_session_rowid"] == 2
        assert report["selection"]["session_ref"].startswith("session_")
        assert report["outcome"] == {
            "status": "completed",
            "success": True,
            "destination_reached": True,
            "destination_correct": True,
            "destination_verification_level": "human_gold",
            "destination_independently_verified": True,
            "safe_stop": False,
            "session_safety_passed": False,
            "failure_or_stop_reason": None,
        }
        assert report["timing_ms"]["total"] == 8000.0
        assert report["timing_ms"]["controllable"] == 5000.0
        assert report["actions"] == {
            "stage_count": 5,
            "click_count": 1,
            "scroll_count": 2,
            "back_count": 1,
            "revisit_count": 2,
            "recovery_count": 1,
            "wrong_guidance_count": 2,
            "unsafe_action_count": 0,
        }
        assert report["graph_usage"]["existing_approved_route_reused"] is True
        assert report["graph_usage"]["function_graph_exploration_used"] is True
        assert report["graph_usage"]["deterministic_fallback_used"] is True
        assert report["graph_usage"]["mixed_existing_graph_and_dynamic_fallback"] is True
        assert report["repeat_no_change_proxies"] == {
            "repeated_screen_stage_count": 2,
            "consecutive_no_change_proxy_count": 2,
            "recorded_no_change_transition_count": 1,
            "recorded_failed_transition_count": 0,
            "scroll_no_change_proxy_count": 1,
            "longest_consecutive_scroll_run": 2,
            "repeat_or_no_change_detected": True,
            "possible_infinite_scroll": False,
        }
        assert report["candidate_route"] == {
            "new_route_count": 1,
            "new_shadow_candidate_appeared": True,
            "new_shadow_candidate_count": 1,
            "unexpected_non_candidate_route_count": 0,
            "session_route_is_new_shadow_candidate": True,
            "candidate_only_not_auto_promoted": True,
        }

        serialized = json.dumps(report, ensure_ascii=False)
        assert "physical-secret-session-id" not in serialized
        assert "private-goal@example.com" not in serialized
        assert "private button label" not in serialized
        assert "us_private" not in serialized

        connection = sqlite3.connect(database_path)
        connection.execute(
            "INSERT INTO universal_routes VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "ugr_unexpected_promotion",
                "app_target",
                "goal_hash",
                "subscription.manage",
                "approved",
                0,
                "2026-07-31T01:00:08.000+00:00",
            ),
        )
        connection.commit()
        connection.close()
        lifecycle_report = build_navigation_session_report(
            database_path,
            baseline_rowid=1,
            app_package="com.example.target",
            session_id="physical-secret-session-id",
        )
        assert lifecycle_report["candidate_route"]["new_route_count"] == 2
        assert (
            lifecycle_report["candidate_route"]["unexpected_non_candidate_route_count"]
            == 1
        )
        assert lifecycle_report["candidate_route"]["candidate_only_not_auto_promoted"] is False

        try:
            build_navigation_session_report(
                database_path,
                baseline_rowid=0,
                app_package="com.example.target",
            )
        except NavigationSessionReportError as exc:
            assert "Multiple matching sessions" in str(exc)
        else:
            raise AssertionError("ambiguous session selection should fail closed")

        _insert_second_post_baseline_session(database_path)
        try:
            build_navigation_session_report(
                database_path,
                baseline_rowid=1,
                app_package="com.example.target",
            )
        except NavigationSessionReportError as exc:
            assert "Multiple matching sessions" in str(exc)
        else:
            raise AssertionError("multiple post-baseline sessions should require session id")

        selected = build_navigation_session_report(
            database_path,
            baseline_rowid=1,
            app_package="com.example.target",
            session_id="second-physical-session",
        )
        assert selected["outcome"]["status"] == "failed"
        assert selected["outcome"]["failure_or_stop_reason"] == "exploration_stopped"

        command = [
            sys.executable,
            str(ROOT / "scripts" / "Report-EgNavigationSession.py"),
            "--database",
            str(database_path),
            "--baseline-rowid",
            "1",
            "--app-package",
            "com.example.target",
            "--session-id",
            "physical-secret-session-id",
            "--compact",
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        cli_report = json.loads(completed.stdout)
        assert cli_report["outcome"]["success"] is True
        assert "private-goal@example.com" not in completed.stdout

    assert_verified_progressing_scroll_run_is_not_infinite()

    print("navigation session report unit: pass")


def assert_verified_progressing_scroll_run_is_not_infinite() -> None:
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "scroll evidence.sqlite"
        _create_fixture(database_path)
        cases = {
            "finite-progressing-scrolls": (
                "human_gold",
                [
                    "us_scroll_a",
                    "us_scroll_b",
                    "us_scroll_c",
                    "us_scroll_d",
                    "us_verified_destination",
                ],
            ),
            "repeated-no-change-scrolls": (
                "human_gold",
                [
                    "us_stuck",
                    "us_stuck",
                    "us_stuck",
                    "us_stuck",
                    "us_verified_destination",
                ],
            ),
            "unverified-progressing-scrolls": (
                "runtime_inferred",
                [
                    "us_scroll_a",
                    "us_scroll_b",
                    "us_scroll_c",
                    "us_scroll_d",
                    "us_unverified_destination",
                ],
            ),
        }
        with sqlite3.connect(database_path) as connection:
            for session_id, (verification_level, fingerprints) in cases.items():
                _insert_session(
                    connection,
                    session_id=session_id,
                    status="completed",
                    failure_type="",
                    destination_correct=1,
                    safe_stop=1,
                    verification_level=verification_level,
                    destination_confirmed_at="2026-07-31T01:00:08.000+00:00",
                    counts=(0, 4, 0, 0, 0, 0, 0),
                )
                connection.executemany(
                    "INSERT INTO navigation_stage_timings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            session_id,
                            ordinal,
                            fingerprint,
                            "function_graph_exploration",
                            "destination_reached" if ordinal == 4 else "exploring",
                            "stop" if ordinal == 4 else "scroll_forward",
                            10.0,
                            0.0,
                            10.0,
                        )
                        for ordinal, fingerprint in enumerate(fingerprints)
                    ],
                )
        connection.close()

        finite_report = build_navigation_session_report(
            database_path,
            baseline_rowid=0,
            app_package="com.example.target",
            session_id="finite-progressing-scrolls",
        )
        finite = finite_report["repeat_no_change_proxies"]
        assert finite["longest_consecutive_scroll_run"] == 4
        assert finite["scroll_no_change_proxy_count"] == 0
        assert finite["possible_infinite_scroll"] is False
        assert finite_report["outcome"]["session_safety_passed"] is True

        repeated = build_navigation_session_report(
            database_path,
            baseline_rowid=0,
            app_package="com.example.target",
            session_id="repeated-no-change-scrolls",
        )["repeat_no_change_proxies"]
        assert repeated["scroll_no_change_proxy_count"] == 3
        assert repeated["possible_infinite_scroll"] is True

        unverified = build_navigation_session_report(
            database_path,
            baseline_rowid=0,
            app_package="com.example.target",
            session_id="unverified-progressing-scrolls",
        )["repeat_no_change_proxies"]
        assert unverified["scroll_no_change_proxy_count"] == 0
        assert unverified["possible_infinite_scroll"] is True


def _create_fixture(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE app_version_signatures (
          version_signature TEXT PRIMARY KEY, app_key TEXT NOT NULL,
          app_package TEXT NOT NULL, app_version TEXT NOT NULL, locale TEXT NOT NULL
        );
        CREATE TABLE navigation_sessions (
          session_id TEXT PRIMARY KEY, app_key TEXT NOT NULL,
          version_signature TEXT NOT NULL, goal_key TEXT NOT NULL,
          target_function TEXT NOT NULL, measurement_source TEXT NOT NULL,
          status TEXT NOT NULL, start_screen_fingerprint TEXT NOT NULL,
          destination_screen_fingerprint TEXT NOT NULL, route_id TEXT NOT NULL,
          route_reused INTEGER NOT NULL, destination_correct INTEGER NOT NULL,
          safe_stop INTEGER NOT NULL, unsafe_click_count INTEGER NOT NULL,
          wrong_click_count INTEGER NOT NULL, wrong_guidance_count INTEGER NOT NULL,
          click_count INTEGER NOT NULL,
          scroll_count INTEGER NOT NULL, back_count INTEGER NOT NULL,
          revisit_count INTEGER NOT NULL, recovery_count INTEGER NOT NULL,
          failure_type TEXT NOT NULL, verification_level TEXT NOT NULL,
          started_at TEXT NOT NULL, destination_confirmed_at TEXT NOT NULL,
          time_to_destination_ms REAL, controllable_time_ms REAL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE navigation_stage_timings (
          session_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
          screen_fingerprint TEXT NOT NULL, decision_mode TEXT NOT NULL,
          phase TEXT NOT NULL, automation_action TEXT NOT NULL,
          server_total_ms REAL NOT NULL, external_wait_ms REAL NOT NULL,
          stage_total_ms REAL NOT NULL,
          PRIMARY KEY(session_id, ordinal)
        );
        CREATE TABLE universal_apps (
          app_key TEXT PRIMARY KEY, app_package TEXT NOT NULL,
          app_version TEXT NOT NULL, locale TEXT NOT NULL
        );
        CREATE TABLE universal_routes (
          route_id TEXT PRIMARY KEY, app_key TEXT NOT NULL, goal_key TEXT NOT NULL,
          target_function TEXT NOT NULL, status TEXT NOT NULL,
          provisional INTEGER NOT NULL, first_seen_at TEXT NOT NULL
        );
        CREATE TABLE universal_session_steps (
          recommendation_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
          outcome TEXT NOT NULL, private_label TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO app_version_signatures VALUES (?, ?, ?, ?, ?)",
        ("avs_target", "app_target", "com.example.target", "2.4.1", "ko-KR"),
    )
    connection.execute(
        "INSERT INTO universal_apps VALUES (?, ?, ?, ?)",
        ("app_target", "com.example.target", "2.4.1", "ko-KR"),
    )
    _insert_session(
        connection,
        session_id="old-physical-session",
        status="failed",
        failure_type="exploration_stopped",
    )
    _insert_session(
        connection,
        session_id="physical-secret-session-id",
        status="completed",
        failure_type="",
        route_id="ugr_new_shadow",
        route_reused=1,
        destination_correct=1,
        verification_level="human_gold",
        destination_confirmed_at="2026-07-31T01:00:08.000+00:00",
        total_ms=8000.0,
        controllable_ms=5000.0,
        counts=(1, 2, 1, 2, 1, 1, 0),
        wrong_guidance_count=2,
    )
    stages = [
        (0, "us_private_a", "function_graph_exploration", "exploring", "click"),
        (1, "us_private_a", "function_graph_exploration", "exploring", "scroll_forward"),
        (2, "us_private_b", "deterministic_fallback", "exploring", "scroll_forward"),
        (3, "us_private_b", "route_cache", "guiding", "back"),
        (4, "us_private_c", "route_cache", "destination_reached", "stop"),
    ]
    for ordinal, fingerprint, mode, phase, action in stages:
        connection.execute(
            "INSERT INTO navigation_stage_timings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "physical-secret-session-id",
                ordinal,
                fingerprint,
                mode,
                phase,
                action,
                100.0,
                50.0,
                1000.0,
            ),
        )
    connection.execute(
        "INSERT INTO universal_routes VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "ugr_new_shadow",
            "app_target",
            "goal_hash",
            "subscription.manage",
            "shadow",
            1,
            "2026-07-31T01:00:07.000+00:00",
        ),
    )
    connection.executemany(
        "INSERT INTO universal_session_steps VALUES (?, ?, ?, ?)",
        [
            ("r1", "physical-secret-session-id", "navigated", "private button label"),
            ("r2", "physical-secret-session-id", "no_change", "private button label"),
        ],
    )
    connection.commit()
    connection.close()


def _insert_second_post_baseline_session(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    _insert_session(
        connection,
        session_id="second-physical-session",
        status="failed",
        failure_type="exploration_stopped",
    )
    connection.commit()
    connection.close()


def _insert_session(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    status: str,
    failure_type: str,
    route_id: str = "",
    route_reused: int = 0,
    destination_correct: int = 0,
    safe_stop: int = 0,
    verification_level: str = "runtime_inferred",
    destination_confirmed_at: str = "",
    total_ms: float | None = None,
    controllable_ms: float | None = None,
    counts: tuple[int, int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0, 0),
    wrong_guidance_count: int | None = None,
) -> None:
    click, scroll, back, revisit, recovery, wrong, unsafe = counts
    wrong_guidance = wrong if wrong_guidance_count is None else wrong_guidance_count
    connection.execute(
        """
        INSERT INTO navigation_sessions (
          session_id, app_key, version_signature, goal_key, target_function,
          measurement_source, status, start_screen_fingerprint,
          destination_screen_fingerprint, route_id, route_reused,
          destination_correct, safe_stop, unsafe_click_count, wrong_click_count,
          wrong_guidance_count, click_count, scroll_count, back_count,
          revisit_count, recovery_count, failure_type, verification_level,
          started_at, destination_confirmed_at, time_to_destination_ms,
          controllable_time_ms, created_at, updated_at
        ) VALUES (
          ?, 'app_target', 'avs_target', 'goal_hash', 'subscription.manage',
          'real_device', ?, 'us_private_start', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
          ?, ?, ?, '2026-07-31T01:00:00.000+00:00', ?, ?, ?,
          '2026-07-31T01:00:00.000+00:00', '2026-07-31T01:00:09.000+00:00'
        )
        """,
        (
            session_id,
            status,
            "us_private_destination" if destination_correct else "",
            route_id,
            route_reused,
            destination_correct,
            safe_stop,
            unsafe,
            wrong,
            wrong_guidance,
            click,
            scroll,
            back,
            revisit,
            recovery,
            failure_type,
            verification_level,
            destination_confirmed_at,
            total_ms,
            controllable_ms,
        ),
    )


if __name__ == "__main__":
    main()
