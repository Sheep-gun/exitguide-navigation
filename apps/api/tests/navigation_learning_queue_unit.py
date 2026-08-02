from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from app.services.navigation_learning_queue import (
    materialize_runtime_learning_queue,
    review_runtime_example,
    write_runtime_learning_artifacts,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        database = root / "navigation.sqlite"
        _fixture(database)
        examples = materialize_runtime_learning_queue(database)
        assert len(examples) == 2
        passed = next(row for row in examples if row.recommendation_id == "rec-good")
        failed = next(row for row in examples if row.recommendation_id == "rec-bad")
        assert passed.lifecycle_status == "auto_quality_passed"
        assert passed.review_status == "pending_review"
        assert passed.selected_action["arguments"]["candidate_id"] == "settings"
        assert len(passed.candidates) == 2
        assert failed.lifecycle_status == "runtime"
        assert "action_not_observed_as_performed" in failed.quality_reasons

        review_runtime_example(database, passed.example_id, approved=True, reviewer="tester")
        materialize_runtime_learning_queue(database)
        connection = sqlite3.connect(database)
        try:
            status = connection.execute(
                "SELECT lifecycle_status, review_status FROM navigation_runtime_learning_queue WHERE example_id = ?",
                (passed.example_id,),
            ).fetchone()
        finally:
            connection.close()
        assert status == ("verified_candidate", "approved")

        manifest = write_runtime_learning_artifacts(examples, root / "out")
        assert manifest["never_auto_gold"] is True
        assert manifest["artifacts"]["auto_quality_passed"]["examples"] == 1
        payload = json.loads(
            (root / "out" / "navigation-runtime-auto_quality_passed.jsonl").read_text("utf-8")
        )
        assert payload["provenance"] == "runtime_agent_shadow"
        assert payload["automatic_quality"]["passed"] is True
        assert "human_gold" not in payload["lifecycle_status"]
    print("navigation runtime learning queue checks ok")


def _fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE universal_apps (
              app_key TEXT PRIMARY KEY, app_package TEXT, app_version TEXT, locale TEXT
            );
            CREATE TABLE universal_sessions (
              session_id TEXT PRIMARY KEY, app_key TEXT, goal_text TEXT, status TEXT
            );
            CREATE TABLE universal_screens (
              screen_fingerprint TEXT PRIMARY KEY, activity_name TEXT, title TEXT, structure_json TEXT
            );
            CREATE TABLE universal_actions (
              action_id TEXT PRIMARY KEY, screen_fingerprint TEXT, last_element_id TEXT,
              element_key TEXT, label TEXT, role TEXT, risk_level TEXT, risk_reason TEXT
            );
            CREATE TABLE universal_session_steps (
              recommendation_id TEXT PRIMARY KEY, session_id TEXT, screen_fingerprint TEXT,
              action_id TEXT, target_function TEXT, decision_mode TEXT, confidence REAL,
              performed INTEGER, outcome TEXT, next_screen_fingerprint TEXT, created_at TEXT
            );
            CREATE TABLE navigation_sessions (
              session_id TEXT PRIMARY KEY, destination_correct INTEGER, safe_stop INTEGER,
              unsafe_click_count INTEGER, wrong_click_count INTEGER, verification_level TEXT
            );
            INSERT INTO universal_apps VALUES ('app', 'com.example', '1.0', 'ko-KR');
            INSERT INTO universal_sessions VALUES ('session', 'app', '알림을 끄고 싶어', 'completed');
            INSERT INTO universal_screens VALUES ('screen', 'Settings', '설정', '{"ocr":["설정"]}');
            INSERT INTO universal_actions VALUES
              ('a-settings', 'screen', 'settings', 'key-settings', '설정', 'button', 'low', ''),
              ('a-feed', 'screen', 'feed', 'key-feed', '추천 영상 user@example.com', 'card', 'low', '');
            INSERT INTO universal_session_steps VALUES
              ('rec-good', 'session', 'screen', 'a-settings', 'notification.settings', 'exaone', 0.91,
               1, 'navigated', 'next', '2026-01-01T00:00:00Z'),
              ('rec-bad', 'session', 'screen', 'a-feed', 'notification.settings', 'heuristic', 0.20,
               0, '', '', '2026-01-01T00:00:01Z');
            INSERT INTO navigation_sessions VALUES ('session', 1, 1, 0, 0, 'runtime_inferred');
            """
        )
        connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
