from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import get_settings  # noqa: E402
from app.services.navigation_review import (  # noqa: E402
    NavigationHumanReviewRequest,
    NavigationReviewStore,
)


def _candidate(candidate_id: str, label: str, *, risk: str = "low") -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "label": label,
        "role": "button",
        "nearby_text": f"{label} 주변 문구",
        "risk_level": risk,
        "clickable": True,
        "enabled": True,
    }


def _screen(candidates: list[dict[str, object]], title: str) -> dict[str, object]:
    return {
        "window_title": title,
        "activity_name": "FixtureActivity",
        "app_package": "com.example.app",
        "candidates": candidates,
        "nodes": [
            {
                "node_id": candidate["candidate_id"],
                "text": candidate["label"],
                "content_description": "",
                "clickable": True,
                "scrollable": False,
                "private_input": False,
            }
            for candidate in candidates
        ],
    }


def _build_runtime(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript((ROOT / "db" / "navigation_runtime_v1.sql").read_text(encoding="utf-8"))
    connection.execute(
        """
        INSERT INTO navigation_collection_runs(
            run_id, collection_batch_id, collector_alias, device_instance_id,
            context_json, started_at, last_seen_at
        ) VALUES ('run-1', 'batch-1', 'fixture', 'device-1', '{}', '2026-08-05T00:00:00Z', '2026-08-05T00:00:00Z')
        """
    )
    cases = (
        ("reached", "d-reached", 0, "stop_for_user", "reached", "destination_reached"),
        ("safety", "d-safety", 0, "stop_for_user", "unknown", "unknown"),
        ("routine", "d-routine", 0, "click", "advanced", "navigated"),
    )
    for index, (name, decision_id, step, action, progress, outcome) in enumerate(cases):
        session_id = f"s-{name}"
        status = "reached" if name == "reached" else "stopped"
        connection.execute(
            """
            INSERT INTO navigation_sessions(
                session_id, run_id, request_id, app_package, app_version, locale,
                goal_text_redacted, goal_id, status, created_at, updated_at
            ) VALUES (?, 'run-1', ?, 'com.example.app', '1.0', 'ko-KR', ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                f"request-{name}",
                f"{name} 목표",
                f"goal.{name}",
                status,
                f"2026-08-05T00:0{index}:00Z",
                f"2026-08-05T00:0{index}:00Z",
            ),
        )
        before_candidates = [
            _candidate("candidate-main", "현재 선택", risk="high" if name == "safety" else "low"),
            _candidate("candidate-alt", "더 나은 선택"),
        ]
        candidate_id = "candidate-main" if action == "click" else None
        connection.execute(
            """
            INSERT INTO navigation_decisions(
                decision_id, session_id, step_ordinal, screen_fingerprint,
                screen_payload_json, goal_id, plan_stage, plan_json,
                action_name, candidate_id, confidence, score_margin,
                reflection_on_demand, planner_provider, planner_fallback_used,
                safety_status, safety_reason, destination_match_before,
                evidence_case_ids_json, candidate_values_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'navigate', '{}', ?, ?, ?, 0.2, 0,
                      'fixture', 0, 'allowed', 'fixture', 0.4, '[]', '[]', ?)
            """,
            (
                decision_id,
                session_id,
                step,
                f"before-{name}",
                json.dumps(_screen(before_candidates, f"{name} 전"), ensure_ascii=False),
                f"goal.{name}",
                action,
                candidate_id,
                0.5 if name == "routine" else 0.9,
                f"2026-08-05T00:0{index}:10Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO navigation_screen_snapshots(
                snapshot_id, decision_id, phase, screen_fingerprint,
                window_title_redacted, activity_name_redacted,
                screen_payload_json, captured_at, nodes_total, nodes_captured,
                candidates_total, candidates_captured
            ) VALUES (?, ?, 'before', ?, ?, 'FixtureActivity', ?, ?, 2, 2, 2, 2)
            """,
            (
                f"snapshot-before-{name}",
                decision_id,
                f"before-{name}",
                f"{name} 전",
                json.dumps(_screen(before_candidates, f"{name} 전"), ensure_ascii=False),
                f"2026-08-05T00:0{index}:10Z",
            ),
        )
        for ordinal, candidate in enumerate(before_candidates):
            connection.execute(
                """
                INSERT INTO navigation_screen_candidates(
                    snapshot_id, candidate_id, ordinal, observed_payload_json,
                    final_score, score_source, risk_level, terminal,
                    dangerous_final, forbidden, selected
                ) VALUES (?, ?, ?, ?, ?, 'fixture', ?, ?, ?, 0, ?)
                """,
                (
                    f"snapshot-before-{name}",
                    candidate["candidate_id"],
                    ordinal,
                    json.dumps(candidate, ensure_ascii=False),
                    0.8 - ordinal * 0.2,
                    candidate["risk_level"],
                    int(candidate["risk_level"] == "high"),
                    int(candidate["risk_level"] == "high"),
                    int(candidate["candidate_id"] == candidate_id),
                ),
            )
        if name != "safety":
            observation_id = f"observation-{name}"
            after_screen = _screen([_candidate("candidate-next", "다음 화면")], f"{name} 후")
            connection.execute(
                """
                INSERT INTO navigation_observations(
                    observation_id, decision_id, connectivity_status,
                    next_screen_fingerprint, state_changed, outcome_type,
                    progress_label, destination_match_before,
                    destination_match_after, observed_at
                ) VALUES (?, ?, 'observed', ?, 1, ?, ?, 0.4, 0.8, ?)
                """,
                (
                    observation_id,
                    decision_id,
                    f"after-{name}",
                    outcome,
                    progress,
                    f"2026-08-05T00:0{index}:20Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO navigation_screen_snapshots(
                    snapshot_id, decision_id, observation_id, phase,
                    screen_fingerprint, window_title_redacted,
                    activity_name_redacted, screen_payload_json, captured_at,
                    nodes_total, nodes_captured, candidates_total, candidates_captured
                ) VALUES (?, ?, ?, 'after', ?, ?, 'FixtureActivity', ?, ?, 1, 1, 1, 1)
                """,
                (
                    f"snapshot-after-{name}",
                    decision_id,
                    observation_id,
                    f"after-{name}",
                    f"{name} 후",
                    json.dumps(after_screen, ensure_ascii=False),
                    f"2026-08-05T00:0{index}:20Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO navigation_screen_candidates(
                    snapshot_id, candidate_id, ordinal, observed_payload_json,
                    final_score, score_source, risk_level
                ) VALUES (?, 'candidate-next', 0, ?, 0.7, 'fixture', 'low')
                """,
                (
                    f"snapshot-after-{name}",
                    json.dumps(_candidate("candidate-next", "다음 화면"), ensure_ascii=False),
                ),
            )
            connection.execute(
                """
                INSERT INTO navigation_step_executions(
                    decision_id, observation_id, execution_status,
                    execution_succeeded, observed_signal, reflection_level,
                    completed_at
                ) VALUES (?, ?, 'executed', 1, 'fixture', 'none', ?)
                """,
                (decision_id, observation_id, f"2026-08-05T00:0{index}:20Z"),
            )
    connection.commit()
    connection.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        runtime_path = root / "runtime.sqlite"
        review_path = root / "reviews.sqlite"
        _build_runtime(runtime_path)
        store = NavigationReviewStore(runtime_path, review_path)

        with store._runtime_connect() as source:
            try:
                source.execute("CREATE TABLE forbidden_write(value TEXT)")
                raise AssertionError("Runtime DB accepted a write through the review connection")
            except sqlite3.OperationalError as error:
                assert "readonly" in str(error).lower() or "read-only" in str(error).lower()

        queue = store.list_queue(reviewer="tester", queue="priority", review_status="unreviewed")
        assert [item["decision_id"] for item in queue["items"]] == [
            "d-reached",
            "d-safety",
            "d-routine",
        ]
        assert store.detail("d-reached", reviewer="tester")["decision"]["evidence_complete"] is True
        safety = store.detail("d-safety", reviewer="tester")
        assert safety["decision"]["boundary_candidate_id"] == "candidate-main"
        assert safety["decision"]["evidence_complete"] is False

        source_before = runtime_path.read_bytes()
        saved = store.save_review(
            "d-routine",
            NavigationHumanReviewRequest(
                reviewer="tester",
                action_judgment="wrong",
                progress_judgment="advanced",
                safety_boundary_judgment="false",
                better_candidate_status="selected",
                better_candidate_id="candidate-alt",
                system_success_judgment="not_applicable",
                notes="fixture review",
            ),
        )
        assert saved["source_read_only"] is True
        assert runtime_path.read_bytes() == source_before
        reviewed = store.detail("d-routine", reviewer="tester")["human_review"]
        assert reviewed["better_candidate_id"] == "candidate-alt"
        assert store.status(reviewer="tester")["counts"]["reviewed"] == 1

        os.environ["NAVIGATION_RUNTIME_DB_PATH"] = str(runtime_path)
        os.environ["NAVIGATION_REVIEW_DB_PATH"] = str(review_path)
        get_settings.cache_clear()
        from app import navigation_main  # noqa: E402

        navigation_main.get_navigation_review_store.cache_clear()
        client = TestClient(navigation_main.app)
        assert client.get("/review").status_code == 200
        assert client.get("/v1/navigation/review/status", params={"reviewer": "tester"}).json()[
            "source_read_only"
        ] is True
        response = client.get(
            "/v1/navigation/review/queue",
            params={"reviewer": "tester", "review_status": "reviewed"},
        )
        assert response.status_code == 200
        assert response.json()["items"][0]["decision_id"] == "d-routine"

    print("navigation review unit: PASS")


if __name__ == "__main__":
    main()
