from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADAPTER_PATH = ROOT / "scripts" / "Export-NavigationInteractionEpisodes.py"
CONTRACTS_ROOT = ROOT / "db" / "contracts" / "shared_app_knowledge_v0_9_1"


def load_adapter():
    spec = importlib.util.spec_from_file_location("navigation_interaction_adapter", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def build_legacy_source(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE navigation_training_examples(
            example_id TEXT PRIMARY KEY,provenance TEXT NOT NULL,candidates_json TEXT NOT NULL
        );
        CREATE TABLE universal_exploration_attempts(
            attempt_id TEXT PRIMARY KEY,screen_fingerprint TEXT NOT NULL
        );
        CREATE TABLE universal_actions(
            action_id TEXT PRIMARY KEY,screen_fingerprint TEXT NOT NULL,element_key TEXT NOT NULL,
            label TEXT NOT NULL,role TEXT NOT NULL,risk_level TEXT NOT NULL,risk_reason TEXT
        );
        """
    )
    candidates = json.dumps(
        [
            {"element_id": "element-1", "element_key": "key-1", "label": "계정 관리", "role": "button"},
            {"element_id": "element-2", "element_key": "key-2", "label": "회원가입", "role": "button"},
        ],
        ensure_ascii=False,
    )
    connection.executemany(
        "INSERT INTO navigation_training_examples VALUES (?,?,?)",
        (
            ("example-1", "real_device_human_gold", candidates),
            ("example-2", "real_device_human_gold", "[]"),
        ),
    )
    connection.execute(
        "INSERT INTO universal_exploration_attempts VALUES (?,?)",
        ("attempt-1", "legacy-screen-1"),
    )
    connection.executemany(
        "INSERT INTO universal_actions VALUES (?,?,?,?,?,?,?)",
        (
            ("action-1", "legacy-screen-1", "key-1", "계정 관리", "button", "low", ""),
            ("action-2", "legacy-screen-1", "key-2", "회원가입", "button", "low", ""),
        ),
    )
    connection.commit()
    connection.close()


def build_source(path: Path, legacy_hash: str) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA user_version=2;
        CREATE TABLE navigation_db_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE semantic_screens(screen_id TEXT PRIMARY KEY,semantic_fingerprint TEXT NOT NULL);
        CREATE TABLE screen_observations(
            observation_id TEXT PRIMARY KEY,screen_id TEXT NOT NULL,app_package TEXT NOT NULL,
            app_version TEXT NOT NULL,locale TEXT NOT NULL,accessibility_json TEXT NOT NULL,
            ocr_json TEXT NOT NULL,vlm_json TEXT NOT NULL,source_type TEXT NOT NULL,captured_at TEXT NOT NULL
        );
        CREATE TABLE affordances(
            affordance_id TEXT PRIMARY KEY,screen_id TEXT NOT NULL,candidate_key TEXT NOT NULL,
            label TEXT NOT NULL,normalized_label TEXT NOT NULL,icon_semantics TEXT NOT NULL,
            role TEXT NOT NULL,parent_semantics TEXT NOT NULL,nearby_text TEXT NOT NULL,
            position_bucket TEXT NOT NULL,risk_level TEXT NOT NULL,dangerous_final INTEGER NOT NULL,
            function_roles_json TEXT NOT NULL,source_element_key TEXT NOT NULL
        );
        CREATE TABLE decision_cases(
            case_id TEXT PRIMARY KEY,goal_id TEXT NOT NULL,screen_id TEXT NOT NULL,
            goal_text_normalized TEXT NOT NULL,goal_conditions_json TEXT NOT NULL,
            chosen_action TEXT NOT NULL,chosen_affordance_id TEXT,scroll_direction TEXT,
            expected_destination_signature_id TEXT,source_app_package TEXT NOT NULL,
            source_record_id TEXT NOT NULL,source_step_ordinal INTEGER NOT NULL,
            source_type TEXT NOT NULL,evidence_weight REAL NOT NULL,observed_at TEXT NOT NULL
        );
        CREATE TABLE transition_outcomes(
            outcome_id TEXT PRIMARY KEY,case_id TEXT NOT NULL,next_screen_id TEXT,
            outcome_type TEXT NOT NULL,connectivity_status TEXT NOT NULL,state_changed INTEGER,
            destination_match_before REAL,destination_match_after REAL,distance_before REAL,
            distance_after REAL,distance_method TEXT,progress_label TEXT,failure_class TEXT,
            external_target TEXT,observed_at TEXT NOT NULL
        );
        CREATE TABLE evidence_records(
            evidence_id TEXT PRIMARY KEY,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,
            source_ref TEXT NOT NULL,confidence REAL NOT NULL,verification_count INTEGER NOT NULL
        );
        CREATE TABLE experience_episodes(
            episode_id TEXT PRIMARY KEY,goal_id TEXT NOT NULL,source_type TEXT NOT NULL,
            source_record_id TEXT NOT NULL,source_app_package TEXT NOT NULL,app_version TEXT NOT NULL,
            language_tag TEXT NOT NULL,split_version TEXT NOT NULL,split TEXT NOT NULL,
            started_at TEXT NOT NULL,ended_at TEXT NOT NULL,end_reason TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );
        CREATE TABLE experience_steps(
            case_id TEXT PRIMARY KEY,episode_id TEXT NOT NULL,step_index INTEGER NOT NULL,
            is_first INTEGER NOT NULL,is_last INTEGER NOT NULL,is_terminal INTEGER NOT NULL,
            reward REAL,discount REAL,reward_semantics TEXT,step_metadata_json TEXT
        );
        """
    )
    connection.executemany(
        "INSERT INTO navigation_db_metadata VALUES (?,?)",
        (
            ("database_kind", "navigation_decision_memory"),
            ("schema_version", "2"),
            ("standards_profile", "exitguide.navigation-experience.v1"),
            ("standards_profile_version", "1.0.0"),
            ("upstream_legacy_source_sha256", legacy_hash),
        ),
    )
    connection.executemany(
        "INSERT INTO semantic_screens VALUES (?,?)",
        (("screen-1", "fingerprint-1"), ("screen-2", "fingerprint-2")),
    )
    observation_payload = json.dumps(
        {
            "window_title": "설정",
            "elements": [
                {
                    "node_id": "node-1",
                    "parent_node_id": "",
                    "label": "계정 관리",
                    "role": "button",
                    "clickable": True,
                    "scrollable": False,
                }
            ],
        },
        ensure_ascii=False,
    )
    connection.executemany(
        "INSERT INTO screen_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            ("obs-1", "screen-1", "com.example", "1.0", "ko-KR", observation_payload, "{}", "{}", "human_gold", "2026-08-01T00:00:00+00:00"),
            ("obs-2", "screen-2", "com.example", "1.0", "ko-KR", observation_payload, "{}", "{}", "human_gold", "2026-08-01T00:00:01+00:00"),
        ),
    )
    connection.executemany(
        "INSERT INTO affordances VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ("aff-1", "screen-1", "candidate-1", "계정 관리", "계정 관리", "", "button", "", "", "middle", "low", 0, '["account.hub"]', source_key("key-1")),
            ("aff-2", "screen-1", "candidate-2", "회원가입", "회원가입", "", "button", "", "", "middle", "low", 0, '["auth.signup.entry"]', source_key("key-2")),
        ),
    )
    connection.executemany(
        "INSERT INTO decision_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ("case-1", "account.delete", "screen-1", "회원탈퇴", "{}", "click", "aff-1", None, "dest-delete", "com.example", "gold-1", 4, "human_gold", 0.98, "2026-08-01T00:00:00+00:00"),
            ("case-2", "account.delete", "screen-2", "회원탈퇴", "{}", "stop_for_user", None, None, "dest-delete", "com.example", "gold-1", 8, "human_gold", 0.98, "2026-08-01T00:00:01+00:00"),
            ("case-3", "account.signup", "screen-1", "회원가입", "{}", "click", "aff-2", None, "dest-signup", "com.example", "device-1", 0, "real_device", 0.9, "2026-08-01T00:00:02+00:00"),
        ),
    )
    connection.executemany(
        "INSERT INTO evidence_records VALUES (?,?,?,?,?,?)",
        (
            ("evidence-1", "decision_case", "case-1", "example-1", 0.98, 1),
            ("evidence-2", "decision_case", "case-2", "example-2", 0.98, 1),
            ("evidence-3", "decision_case", "case-3", "attempt-1", 0.9, 1),
        ),
    )
    connection.executemany(
        "INSERT INTO transition_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ("out-1", "case-1", "screen-2", "navigated", "observed", 1, 0.2, 0.7, 0.8, 0.3, "signature-v1", "advanced", "", "", "2026-08-01T00:00:01+00:00"),
            ("out-2", "case-2", None, "destination_reached", "observed", 0, 0.7, 1.0, 0.3, 0.0, "signature-v1", "reached", "", "", "2026-08-01T00:00:02+00:00"),
            ("out-3", "case-3", None, "unknown", "transport_error", 0, 0.1, None, 0.9, None, "signature-v1", "unknown", "transport", "", "2026-08-01T00:00:03+00:00"),
        ),
    )
    connection.executemany(
        "INSERT INTO experience_episodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ("episode-1", "account.delete", "human_gold", "gold-1", "com.example", "1.0", "ko-KR", "app-disjoint-v1", "train", "2026-08-01T00:00:00+00:00", "2026-08-01T00:00:02+00:00", "user_handoff", "{}"),
            ("episode-2", "account.signup", "real_device", "device-1", "com.example", "1.0", "ko-KR", "app-disjoint-v1", "validation", "2026-08-01T00:00:02+00:00", "2026-08-01T00:00:03+00:00", "truncated", "{}"),
        ),
    )
    connection.executemany(
        "INSERT INTO experience_steps VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            ("case-1", "episode-1", 4, 1, 0, 0, 0.5, 1.0, "exitguide_progress_v1", "{}"),
            ("case-2", "episode-1", 8, 0, 1, 0, 1.0, 1.0, "exitguide_progress_v1", "{}"),
            ("case-3", "episode-2", 0, 1, 1, 0, None, 1.0, "exitguide_progress_v1", "{}"),
        ),
    )
    connection.commit()
    connection.close()


def run() -> None:
    adapter = load_adapter()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        legacy_source = root / "legacy.sqlite"
        source = root / "source.sqlite"
        output = root / "episodes.jsonl"
        report_path = root / "report.json"
        build_legacy_source(legacy_source)
        legacy_hash = sha256(legacy_source)
        build_source(source, legacy_hash)
        source_hash = sha256(source)
        report = adapter.export(
            source,
            CONTRACTS_ROOT,
            output,
            report_path,
            legacy_source=legacy_source,
            require_complete_candidates=True,
        )
        assert sha256(source) == source_hash
        assert sha256(legacy_source) == legacy_hash
        assert report["validation"]["passed"] is True
        assert report["output"]["episodes"] == 2
        assert report["output"]["steps"] == 3
        assert report["output"]["candidate_set_status"] == {
            "unavailable": 0,
            "partial": 0,
            "complete": 3,
        }
        assert report["output"]["promotion_validation_eligible_steps"] == 3
        assert report["output"]["automatically_promoted_steps"] == 0
        episodes = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
        delete_episode = next(row for row in episodes if row["context"]["goal_id"] == "delete_account")
        assert delete_episode["outcome"] == "user_stopped"
        assert [step["ordinal"] for step in delete_episode["steps"]] == [0, 1]
        first_step = delete_episode["steps"][0]
        assert first_step["selected_action"]["candidate_id"] == "candidate-1"
        assert first_step["candidate_set_status"] == "complete"
        assert {candidate["candidate_id"] for candidate in first_step["candidates"]} == {
            "candidate-1",
            "candidate-2",
        }
        assert [
            candidate["candidate_id"]
            for candidate in first_step["candidates"]
            if candidate["selected"]
        ] == ["candidate-1"]
        transport_episode = next(row for row in episodes if row["context"]["goal_id"] == "create_account")
        transport_step = transport_episode["steps"][0]
        assert transport_step["execution"]["status"] == "transport_error"
        assert transport_step["execution"]["outcome_type"] == "unknown"
        assert transport_step["after"] is None
        try:
            adapter.export(
                source,
                CONTRACTS_ROOT,
                output,
                report_path,
                legacy_source=legacy_source,
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("adapter must refuse to overwrite generated artifacts by default")


if __name__ == "__main__":
    run()
    print("navigation_interaction_adapter_unit: ok")
