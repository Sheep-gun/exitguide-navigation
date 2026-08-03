from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROMOTER = load_script(
    "navigation_promoter",
    ROOT / "scripts" / "Promote-NavigationRuntimeExperiences.py",
)
MIGRATOR = load_script(
    "navigation_decision_migrator",
    ROOT / "scripts" / "Migrate-NavigationDecisionDb.py",
)


def screen_payload(*, title: str, candidate_id: str, label: str) -> dict:
    return {
        "app_package": "com.example.membership",
        "window_title": title,
        "activity_name": "ExampleActivity",
        "navigation_depth": 1,
        "nodes": [
            {
                "node_id": candidate_id,
                "parent_id": None,
                "child_ids": [],
                "text": label,
                "content_description": "",
                "view_id": "example:id/account",
                "role": "button",
                "position_bucket": "top",
                "clickable": True,
                "enabled": True,
                "visible": True,
                "scrollable": False,
                "checkable": False,
                "selected": False,
                "checked": None,
                "private_input": False,
            }
        ],
        "candidates": [
            {
                "candidate_id": candidate_id,
                "label": label,
                "role": "button",
                "risk_level": "low",
                "icon_semantics": "profile",
                "nearby_text": "membership settings",
                "parent_semantics": "account hub",
                "child_semantics": "",
                "visual_role": "",
                "visual_region": "top",
                "visual_relevance": None,
                "position_bucket": "top",
                "clickable": True,
                "enabled": True,
                "selected": False,
                "checked": None,
            }
        ],
    }


def insert_runtime_session(
    connection: sqlite3.Connection,
    ordinal: int,
    *,
    status: str = "reached",
) -> str:
    session_id = f"session-{ordinal}"
    decision_id = f"decision-{ordinal}"
    observation_id = f"observation-{ordinal}"
    before_snapshot_id = f"snapshot-before-{ordinal}"
    after_snapshot_id = f"snapshot-after-{ordinal}"
    candidate_id = f"candidate-account-{ordinal}"
    before = screen_payload(
        title="Home",
        candidate_id=candidate_id,
        label="My account",
    )
    after = screen_payload(
        title="Account hub",
        candidate_id=f"candidate-membership-{ordinal}",
        label="Membership",
    )
    started = f"2026-08-04T00:0{ordinal}:00+00:00"
    finished = f"2026-08-04T00:0{ordinal}:02+00:00"
    connection.execute(
        """
        INSERT INTO navigation_sessions(
            session_id,request_id,app_package,app_version,locale,
            goal_text_redacted,goal_id,status,created_at,updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            f"request-{ordinal}",
            "com.example.membership",
            "1.0.0",
            "ko-KR",
            "멤버십 해지",
            "membership.cancel",
            status,
            started,
            finished,
        ),
    )
    connection.execute(
        """
        INSERT INTO navigation_decisions(
            decision_id,session_id,step_ordinal,screen_fingerprint,
            screen_payload_json,goal_id,plan_stage,plan_json,action_name,
            candidate_id,scroll_direction,confidence,score_margin,
            reflection_on_demand,planner_provider,planner_fallback_used,
            safety_status,safety_reason,destination_match_before,
            evidence_case_ids_json,candidate_values_json,created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            decision_id,
            session_id,
            0,
            f"home-fingerprint-{ordinal}",
            json.dumps(before, ensure_ascii=False),
            "membership.cancel",
            "hub_discovery",
            "{}",
            "click",
            candidate_id,
            None,
            0.91,
            0.42,
            0,
            "solar_pro4",
            0,
            "allowed",
            "safe navigation",
            0.1,
            "[]",
            "[]",
            started,
        ),
    )
    connection.execute(
        """
        INSERT INTO navigation_observations(
            observation_id,decision_id,connectivity_status,next_screen_fingerprint,
            state_changed,outcome_type,progress_label,destination_match_before,
            destination_match_after,failure_class,observed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            observation_id,
            decision_id,
            "observed",
            f"account-fingerprint-{ordinal}",
            1,
            "navigated",
            "advanced",
            0.1,
            0.5,
            "",
            finished,
        ),
    )
    connection.execute(
        """
        INSERT INTO navigation_screen_snapshots(
            snapshot_id,decision_id,observation_id,phase,screen_fingerprint,
            window_title_redacted,activity_name_redacted,navigation_depth,
            candidate_set_status,screen_payload_json,captured_at
        ) VALUES (?,?,NULL,'before',?,?,?,?,?,?,?)
        """,
        (
            before_snapshot_id,
            decision_id,
            f"home-fingerprint-{ordinal}",
            "Home",
            "ExampleActivity",
            1,
            "complete",
            json.dumps(before, ensure_ascii=False),
            started,
        ),
    )
    connection.execute(
        """
        INSERT INTO navigation_screen_snapshots(
            snapshot_id,decision_id,observation_id,phase,screen_fingerprint,
            window_title_redacted,activity_name_redacted,navigation_depth,
            candidate_set_status,screen_payload_json,captured_at
        ) VALUES (?,?,?,'after',?,?,?,?,?,?,?)
        """,
        (
            after_snapshot_id,
            decision_id,
            observation_id,
            f"account-fingerprint-{ordinal}",
            "Account hub",
            "ExampleActivity",
            2,
            "complete",
            json.dumps(after, ensure_ascii=False),
            finished,
        ),
    )
    observed_candidate = before["candidates"][0]
    connection.execute(
        """
        INSERT INTO navigation_screen_candidates(
            snapshot_id,candidate_id,ordinal,observed_payload_json,memory_score,
            verifier_score,final_score,score_source,risk_level,terminal,
            dangerous_final,forbidden,selected
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            before_snapshot_id,
            candidate_id,
            0,
            json.dumps(observed_candidate, ensure_ascii=False),
            0.8,
            0.9,
            0.91,
            "planner_model_verifier",
            "low",
            0,
            0,
            0,
            1,
        ),
    )
    connection.execute(
        """
        INSERT INTO navigation_step_executions(
            decision_id,observation_id,execution_status,execution_succeeded,
            observed_signal,recovery_action,candidate_forbidden,
            reflection_level,reflection_reason,completed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            decision_id,
            observation_id,
            "executed",
            1,
            "screen_changed",
            None,
            0,
            "none",
            "",
            finished,
        ),
    )
    return session_id


def build_runtime(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    connection.executescript(
        (ROOT / "db" / "navigation_runtime_v1.sql").read_text(encoding="utf-8")
    )
    sessions = [insert_runtime_session(connection, index) for index in (1, 2)]
    sessions.append(insert_runtime_session(connection, 3, status="stopped"))
    connection.commit()
    connection.close()
    return sessions


def build_decision(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        (ROOT / "db" / "navigation_decision_v1.sql").read_text(encoding="utf-8")
    )
    connection.executescript(
        (ROOT / "db" / "navigation_experience_profile_v1.sqlite.sql").read_text(
            encoding="utf-8"
        )
    )
    MIGRATOR.seed_database(connection, "a" * 64)
    connection.execute(
        "INSERT OR IGNORE INTO provenance_agents VALUES (?,?,?,?)",
        (
            "agent.real-device-recorder",
            "https://exitguide.ai/provenance/agents/real-device-recorder",
            "software",
            "ExitGuide real-device recorder",
        ),
    )
    connection.commit()
    connection.close()


def status_report(split: str, accuracy: float = 1.0) -> dict:
    return {
        "case_count": 3,
        "evaluation_cases_sha256": "b" * 64,
        "by_app_split": {split: {"cases": 3}},
        "positive_exact_next_action_accuracy": accuracy,
        "positive_first_action_accuracy": accuracy,
        "failed_click_avoidance_rate": accuracy,
        "recognized_goal_rate": accuracy,
        "dangerous_auto_click_count": 0,
    }


def run() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runtime = root / "runtime.sqlite"
        base = root / "decision.sqlite"
        episodes_path = root / "episodes.jsonl"
        candidates_path = root / "candidates.jsonl"
        accepted_path = root / "accepted.jsonl"
        generations = root / "generations"
        staging = root / "staging.sqlite"
        projection_report = root / "projection.json"
        sessions = build_runtime(runtime)
        build_decision(base)

        PROMOTER.command_export_episode(
            argparse.Namespace(runtime_db=runtime, session=sessions, output=episodes_path)
        )
        episodes = PROMOTER.load_interaction_episodes(episodes_path)
        assert len(episodes) == 3
        assert [episode["status"] for episode in episodes] == [
            "completed",
            "completed",
            "aborted",
        ]
        assert all(episode["context"]["goal_id"] == "cancel_membership" for episode in episodes)
        assert all(
            episode["context"]["device_context"]["navigation_goal_id"]
            == "membership.cancel"
            for episode in episodes
        )

        PROMOTER.command_generate(
            argparse.Namespace(
                contract=PROMOTER.SHARED_CONTRACTS / "knowledge-promotion.v1.json",
                episodes=episodes_path,
                runtime_db=None,
                session=None,
                allow_legacy_runtime_input=False,
                output=candidates_path,
            )
        )
        candidates = PROMOTER.read_jsonl(candidates_path)
        assert len(candidates) == 1
        assert candidates[0]["status"] == "ready_for_validation"
        assert candidates[0]["support_count"] == 2
        assert {
            source["episode_id"] for source in candidates[0]["sources"]
        } == {"session-1", "session-2"}

        PROMOTER.command_accept(
            argparse.Namespace(
                contract=PROMOTER.SHARED_CONTRACTS / "knowledge-promotion.v1.json",
                episodes=episodes_path,
                runtime_db=None,
                allow_legacy_runtime_input=False,
                input=candidates_path,
                output=accepted_path,
            )
        )
        accepted = PROMOTER.read_jsonl(accepted_path)
        assert accepted[0]["status"] == "accepted"
        assert accepted[0]["validation_runs"][-1]["metrics"]["validation_scope"] == "source_consistency_only"

        PROMOTER.command_build_generation(
            argparse.Namespace(
                contract=PROMOTER.SHARED_CONTRACTS / "knowledge-promotion.v1.json",
                episodes=episodes_path,
                input=accepted_path,
                base_decision_db=base,
                output_root=generations,
                parent_generation_id=None,
            )
        )
        generation_dir = next(path for path in generations.iterdir() if path.is_dir())
        manifest = PROMOTER.verify_generation(generation_dir)
        assert manifest["policy"]["runtime_direct_apply_allowed"] is False
        packet = json.loads(
            (generation_dir / manifest["app_knowledge_packets"][0]["path"]).read_text(
                encoding="utf-8"
            )
        )
        assert packet["transitions"]
        assert packet["procedures"] == []

        PROMOTER.command_project(
            argparse.Namespace(
                generation_dir=generation_dir,
                output=staging,
                report=projection_report,
                overwrite_staging=False,
            )
        )
        projection = json.loads(projection_report.read_text(encoding="utf-8"))
        assert projection["runtime_db_accessed"] is False
        assert projection["decision_cases_after"] == projection["decision_cases_before"] + 2

        passed, failures = PROMOTER.compare_regression_reports(
            status_report("validation"), status_report("validation")
        )
        assert passed is True and failures == []
        passed, failures = PROMOTER.compare_regression_reports(
            status_report("validation"), status_report("validation", 0.5)
        )
        assert passed is False and failures
        try:
            PROMOTER.compare_regression_reports(
                status_report("locked_holdout"), status_report("locked_holdout")
            )
        except ValueError as error:
            assert "validation apps" in str(error)
        else:
            raise AssertionError("locked holdout must never pass the tuning gate")

        operating = root / "operating.sqlite"
        backup = root / "pre-activation.sqlite"
        active_pointer = root / "active.json"
        activation_receipt = root / "activation.json"
        rollback_receipt = root / "rollback.json"
        regression_report = root / "regression.json"
        PROMOTER.write_json(
            regression_report,
            {
                "kind": "fixed_validation_regression_replay",
                "generation_id": manifest["generation_id"],
                "status": "passed",
                "locked_holdout_used": False,
                "evaluation_cases_sha256": "b" * 64,
                "baseline": status_report("validation"),
                "staging": {
                    **status_report("validation"),
                    "database_sha256": PROMOTER.file_sha256(staging),
                    "evaluation_kind": "fixed_validation_leave_source_app_out_replay",
                },
            },
        )
        operating.write_bytes(base.read_bytes())
        original_hash = PROMOTER.file_sha256(operating)
        PROMOTER.command_activate(
            argparse.Namespace(
                generation_dir=generation_dir,
                regression_report=regression_report,
                projection_report=projection_report,
                staging_db=staging,
                operating_db=operating,
                backup=backup,
                active_pointer=active_pointer,
                receipt=activation_receipt,
            )
        )
        assert PROMOTER.file_sha256(operating) == PROMOTER.file_sha256(staging)
        PROMOTER.command_rollback(
            argparse.Namespace(
                activation_receipt=activation_receipt,
                active_pointer=active_pointer,
                receipt=rollback_receipt,
            )
        )
        assert PROMOTER.file_sha256(operating) == original_hash


if __name__ == "__main__":
    run()
    print("navigation_promotion_pipeline_unit: ok")
