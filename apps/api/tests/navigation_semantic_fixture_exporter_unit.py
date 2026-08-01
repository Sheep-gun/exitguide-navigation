from __future__ import annotations

import hashlib
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

from app.services.navigation_semantic_fixture_exporter import (  # noqa: E402
    IndependentDestinationAnnotation,
    SemanticFixtureExportError,
    export_navigation_semantic_fixture,
)


PRIVATE_CANARIES = (
    "private.person@example.com",
    "010-1234-5678",
    "서울특별시 중구 세종대로 110",
    "홍길동님",
    "민감한가게상호",
    "sk_abcdefghijklmnopqrstuvwxyz123456",
    "source-session-secret-41",
    "source-screen-private-account",
    "source-element-settings-private",
    "com.private.delivery",
    "2026-08-01T01:02:03+09:00",
)


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        database_path = root / "source.sqlite"
        output_path = (
            root
            / ".artifacts"
            / "navigation-semantic-fixtures"
            / "candidate.json"
        )
        _create_source_database(database_path)
        before_hash = _sha256(database_path)
        before_stat = database_path.stat()

        result = export_navigation_semantic_fixture(
            database_path,
            session_rowids=(40, 41),
            false_positive_session_rowids=(41,),
            output_path=output_path,
        )

        after_hash = _sha256(database_path)
        after_stat = database_path.stat()
        assert before_hash == after_hash
        assert result.source_sha256_before == before_hash
        assert result.source_sha256_after == after_hash
        assert result.source_hash_unchanged is True
        assert before_stat.st_size == after_stat.st_size
        assert before_stat.st_mtime_ns == after_stat.st_mtime_ns
        assert output_path.is_file()
        assert json.loads(output_path.read_text(encoding="utf-8")) == result.fixture

        fixture = result.fixture
        assert fixture["privacy"]["source_opened_read_only"] is True
        assert fixture["privacy"]["sqlite_query_only"] is True
        assert fixture["privacy"]["accessibility_structure_persisted"] is False
        assert fixture["privacy"]["free_form_labels_persisted"] is False
        assert fixture["privacy"]["source_identifiers_persisted"] is False
        assert fixture["privacy"]["projection_counts"]["sensitive_values_dropped"] >= 5
        assert fixture["privacy"]["projection_counts"]["unknown_values_dropped"] >= 1
        assert fixture["promotion_gate"]["positive_promotion_eligible"] is False
        assert fixture["promotion_gate"]["annotations"] == []
        assert fixture["provenance"]["known_false_positive_count"] == 1
        assert fixture["goal_contract"] == {
            "target_function": "notification.settings",
            "destination_semantic": "notification_preferences",
            "final_action_policy": "user_only",
        }

        sessions = fixture["sessions"]
        assert len(sessions) == 2
        false_positive = [session for session in sessions if session["known_false_positive"]]
        assert len(false_positive) == 1
        assert false_positive[0]["destination_assessment"] == "false_positive_unverified"
        assert false_positive[0]["eligible_as_positive_evidence"] is False
        assert false_positive[0]["stored_verification_claim"] == "runtime_inferred"
        assert all(session["lifecycle"] == "shadow_candidate" for session in sessions)

        semantics = {
            semantic
            for screen in fixture["screens"]
            for semantic in screen["semantics"]
        }
        assert "settings" in semantics
        assert "account_hub" in semantics
        assert any(
            screen["surface"] == "foreign_app_surface"
            for screen in fixture["screens"]
        )
        action_semantics = {
            semantic
            for action in fixture["actions"]
            for semantic in action["semantics"]
        }
        assert "settings" in action_semantics
        assert all(action["action_ref"].startswith("action-") for action in fixture["actions"])
        assert all(
            transition["lifecycle"] == "shadow_candidate"
            for transition in fixture["transitions"]
        )

        serialized = json.dumps(fixture, ensure_ascii=False, sort_keys=True)
        for canary in PRIVATE_CANARIES:
            assert canary not in serialized
        for forbidden_key in (
            '"session_id"',
            '"screen_fingerprint"',
            '"element_key"',
            '"resource_id"',
            '"structure_json"',
            '"device_serial"',
            '"started_at"',
            '"screenshot_path"',
        ):
            assert forbidden_key not in serialized

        _assert_known_false_positive_cannot_be_promoted(database_path, root)
        _assert_independent_annotation_is_required_and_sufficient(database_path, root)
        _assert_output_is_confined_to_ignored_artifacts(database_path, root)
        _assert_cli_is_sanitized(database_path, root)

    print("navigation_semantic_fixture_exporter_unit: ok")


def _assert_known_false_positive_cannot_be_promoted(
    database_path: Path,
    root: Path,
) -> None:
    try:
        export_navigation_semantic_fixture(
            database_path,
            session_rowids=(41,),
            output_path=(
                root
                / ".artifacts"
                / "navigation-semantic-fixtures"
                / "must-not-exist.json"
            ),
            independent_destination_annotations=(
                IndependentDestinationAnnotation(
                    source_session_rowid=41,
                    target_function="notification.settings",
                    destination_semantic="notification_preferences",
                    verification_method="human_on_device",
                ),
            ),
        )
    except SemanticFixtureExportError as exc:
        assert "false-positive" in str(exc)
    else:
        raise AssertionError("known false-positive session was promoted")


def _assert_independent_annotation_is_required_and_sufficient(
    database_path: Path,
    root: Path,
) -> None:
    unannotated = export_navigation_semantic_fixture(
        database_path,
        session_rowids=(42,),
        output_path=(
            root
            / ".artifacts"
            / "navigation-semantic-fixtures"
            / "unannotated.json"
        ),
    )
    assert unannotated.fixture["promotion_gate"]["positive_promotion_eligible"] is False
    assert (
        unannotated.fixture["sessions"][0]["destination_assessment"]
        == "runtime_claim_unverified"
    )

    annotated = export_navigation_semantic_fixture(
        database_path,
        session_rowids=(42,),
        output_path=(
            root
            / ".artifacts"
            / "navigation-semantic-fixtures"
            / "annotated.json"
        ),
        independent_destination_annotations=(
            IndependentDestinationAnnotation(
                source_session_rowid=42,
                target_function="notification.settings",
                destination_semantic="notification_preferences",
                verification_method="independent_device_replay",
            ),
        ),
    )
    assert annotated.fixture["promotion_gate"]["positive_promotion_eligible"] is True
    assert annotated.fixture["sessions"][0]["eligible_as_positive_evidence"] is True
    assert (
        annotated.fixture["sessions"][0]["destination_assessment"]
        == "independently_verified"
    )


def _assert_output_is_confined_to_ignored_artifacts(
    database_path: Path,
    root: Path,
) -> None:
    try:
        export_navigation_semantic_fixture(
            database_path,
            session_rowids=(40,),
            output_path=root / "repository-fixtures" / "unsafe.json",
        )
    except SemanticFixtureExportError as exc:
        assert "ignored artifact directory" in str(exc)
    else:
        raise AssertionError("export escaped the ignored artifact directory")


def _assert_cli_is_sanitized(database_path: Path, root: Path) -> None:
    output_path = (
        root
        / ".artifacts"
        / "navigation-semantic-fixtures"
        / "cli-candidate.json"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "Export-NavigationSemanticFixture.py"),
            "--database",
            str(database_path),
            "--session-rowid",
            "40",
            "--session-rowid",
            "41",
            "--false-positive-session-rowid",
            "41",
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["exported"] is True
    assert summary["source_hash_unchanged"] is True
    assert summary["positive_promotion_eligible"] is False
    combined_output = completed.stdout + completed.stderr
    for canary in PRIVATE_CANARIES:
        assert canary not in combined_output


def _create_source_database(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE navigation_sessions (
          session_id TEXT PRIMARY KEY,
          app_key TEXT NOT NULL,
          goal_key TEXT NOT NULL,
          target_function TEXT NOT NULL,
          measurement_source TEXT NOT NULL,
          status TEXT NOT NULL,
          start_screen_fingerprint TEXT NOT NULL,
          destination_screen_fingerprint TEXT NOT NULL,
          destination_correct INTEGER NOT NULL,
          unsafe_click_count INTEGER NOT NULL,
          wrong_click_count INTEGER NOT NULL,
          click_count INTEGER NOT NULL,
          scroll_count INTEGER NOT NULL,
          back_count INTEGER NOT NULL,
          revisit_count INTEGER NOT NULL,
          verification_level TEXT NOT NULL,
          started_at TEXT NOT NULL
        );
        CREATE TABLE navigation_stage_timings (
          session_id TEXT NOT NULL,
          ordinal INTEGER NOT NULL,
          screen_fingerprint TEXT NOT NULL,
          decision_mode TEXT NOT NULL,
          phase TEXT NOT NULL,
          automation_action TEXT NOT NULL,
          selected_element_key TEXT NOT NULL,
          PRIMARY KEY(session_id, ordinal)
        );
        CREATE TABLE universal_screens (
          screen_fingerprint TEXT PRIMARY KEY,
          app_key TEXT NOT NULL,
          activity_name TEXT NOT NULL,
          title TEXT NOT NULL,
          structure_json TEXT NOT NULL
        );
        CREATE TABLE universal_actions (
          action_id TEXT PRIMARY KEY,
          screen_fingerprint TEXT NOT NULL,
          element_key TEXT NOT NULL,
          last_element_id TEXT NOT NULL,
          label TEXT NOT NULL,
          role TEXT NOT NULL,
          risk_level TEXT NOT NULL,
          seen_count INTEGER NOT NULL
        );
        CREATE TABLE universal_transitions (
          transition_id TEXT PRIMARY KEY,
          from_screen_fingerprint TEXT NOT NULL,
          action_id TEXT NOT NULL,
          to_screen_fingerprint TEXT NOT NULL,
          success_count INTEGER NOT NULL,
          failure_count INTEGER NOT NULL
        );
        CREATE TABLE universal_exploration_attempts (
          attempt_id TEXT PRIMARY KEY,
          action_id TEXT NOT NULL,
          command TEXT NOT NULL,
          outcome TEXT NOT NULL,
          attempt_count INTEGER NOT NULL
        );
        """
    )
    app_key = "private-app-internal-key"
    sessions = (
        (
            40,
            "source-session-secret-40",
            "failed",
            "source-screen-private-account",
            0,
        ),
        (
            41,
            "source-session-secret-41",
            "completed",
            "source-screen-exitguide-false-destination",
            1,
        ),
        (
            42,
            "source-session-secret-42",
            "completed",
            "source-screen-notification-candidate",
            1,
        ),
    )
    for rowid, session_id, status, destination, destination_correct in sessions:
        connection.execute(
            """
            INSERT INTO navigation_sessions (
              rowid, session_id, app_key, goal_key, target_function,
              measurement_source, status, start_screen_fingerprint,
              destination_screen_fingerprint, destination_correct,
              unsafe_click_count, wrong_click_count, click_count, scroll_count,
              back_count, revisit_count, verification_level, started_at
            ) VALUES (?, ?, ?, 'private-goal-key', 'notification.settings',
                      'real_device', ?, 'source-screen-private-home', ?, ?,
                      0, 0, 2, 1, 1, 1, 'runtime_inferred',
                      '2026-08-01T01:02:03+09:00')
            """,
            (rowid, session_id, app_key, status, destination, destination_correct),
        )

    _insert_screen(
        connection,
        "source-screen-private-home",
        app_key,
        "com.private.delivery.HomeActivity",
        "민감한가게상호",
        [
            _node("마이배민", "com.private.delivery:id/my_page", "Button", True),
            _node("홍길동님", "com.private.delivery:id/member", "TextView", False),
            _node("private.person@example.com", "private-email", "TextView", False),
            _node("010-1234-5678", "private-phone", "TextView", False),
            _node("서울특별시 중구 세종대로 110", "private-address", "TextView", False),
            _node(
                "sk_abcdefghijklmnopqrstuvwxyz123456",
                "private-secret",
                "TextView",
                False,
            ),
        ],
    )
    _insert_screen(
        connection,
        "source-screen-private-account",
        app_key,
        "com.private.delivery.AccountActivity",
        "마이배민",
        [
            _node("환경설정", "com.private.delivery:id/settings_gear", "ImageButton", True),
            _node("배민의 음식주문 경험, 어떠셨나요?", "survey-card", "Button", True),
            _node("고객센터", "support", "Button", True),
        ],
    )
    _insert_screen(
        connection,
        "source-screen-notification-candidate",
        app_key,
        "com.private.delivery.NotificationSettingsActivity",
        "알림 설정",
        [
            _node("알림 설정", "notification_settings", "TextView", False),
            _node("마케팅 알림", "marketing_switch", "Switch", True),
        ],
    )
    _insert_screen(
        connection,
        "source-screen-exitguide-false-destination",
        "foreign-exitguide-app-key",
        "com.exitguide.ai.MainActivity",
        "ExitGuide AI",
        [
            _node("통합 목적", "goal-input", "EditText", False),
            _node("탐색 시작", "start-button", "Button", True),
        ],
    )

    actions = (
        (
            "source-action-my-private",
            "source-screen-private-home",
            "source-element-my-private",
            "my_page",
            "마이배민",
            "Button",
        ),
        (
            "source-action-settings-private",
            "source-screen-private-account",
            "source-element-settings-private",
            "settings_gear",
            "환경설정",
            "ImageButton",
        ),
        (
            "source-action-sensitive-private",
            "source-screen-private-account",
            "source-element-private-contact",
            "private-contact",
            "private.person@example.com",
            "Button",
        ),
        (
            "source-action-notification-private",
            "source-screen-notification-candidate",
            "source-element-notification-private",
            "notification_settings",
            "알림 설정",
            "Switch",
        ),
        (
            "source-action-eg-private",
            "source-screen-exitguide-false-destination",
            "source-element-eg-private",
            "start-button",
            "탐색 시작",
            "Button",
        ),
    )
    for action in actions:
        connection.execute(
            "INSERT INTO universal_actions VALUES (?, ?, ?, ?, ?, ?, 'low', 2)",
            action,
        )

    connection.executemany(
        "INSERT INTO universal_transitions VALUES (?, ?, ?, ?, ?, ?)",
        (
            (
                "source-transition-private-1",
                "source-screen-private-home",
                "source-action-my-private",
                "source-screen-private-account",
                2,
                0,
            ),
            (
                "source-transition-private-2",
                "source-screen-private-account",
                "source-action-settings-private",
                "source-screen-notification-candidate",
                1,
                1,
            ),
        ),
    )
    connection.execute(
        "INSERT INTO universal_exploration_attempts VALUES (?, ?, ?, ?, ?)",
        (
            "source-attempt-private",
            "source-action-settings-private",
            "click",
            "success",
            3,
        ),
    )

    stage_paths = {
        "source-session-secret-40": (
            (1, "source-screen-private-home", "source-element-my-private"),
            (2, "source-screen-private-account", "source-element-settings-private"),
        ),
        "source-session-secret-41": (
            (1, "source-screen-private-home", "source-element-my-private"),
            (2, "source-screen-private-account", "source-element-settings-private"),
            (3, "source-screen-exitguide-false-destination", "source-element-eg-private"),
        ),
        "source-session-secret-42": (
            (1, "source-screen-private-home", "source-element-my-private"),
            (2, "source-screen-private-account", "source-element-settings-private"),
            (3, "source-screen-notification-candidate", ""),
        ),
    }
    for session_id, stages in stage_paths.items():
        for ordinal, screen, selected_element in stages:
            connection.execute(
                """
                INSERT INTO navigation_stage_timings VALUES (
                  ?, ?, ?, 'function_graph_exploration', 'explore', 'click', ?
                )
                """,
                (session_id, ordinal, screen, selected_element),
            )
    connection.commit()
    connection.close()


def _node(
    label: str,
    view_id: str,
    role: str,
    clickable: bool,
) -> dict[str, object]:
    return {
        "parent_id": "source-parent-private",
        "view_id": view_id,
        "role": role,
        "clickable": clickable,
        "scrollable": False,
        "label": label,
    }


def _insert_screen(
    connection: sqlite3.Connection,
    fingerprint: str,
    app_key: str,
    activity_name: str,
    title: str,
    nodes: list[dict[str, object]],
) -> None:
    connection.execute(
        "INSERT INTO universal_screens VALUES (?, ?, ?, ?, ?)",
        (
            fingerprint,
            app_key,
            activity_name,
            title,
            json.dumps(nodes, ensure_ascii=False),
        ),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
