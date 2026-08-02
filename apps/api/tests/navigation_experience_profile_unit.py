from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_V1 = ROOT / "db" / "navigation_decision_v1.sql"
MIGRATOR = ROOT / "scripts" / "Migrate-NavigationExperienceProfile.py"
VALIDATOR = ROOT / "scripts" / "Validate-NavigationExperienceProfile.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_v1(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA_V1.read_text(encoding="utf-8"))
    connection.executemany(
        "INSERT INTO navigation_db_metadata(key,value) VALUES (?,?)",
        (("schema_version", "1"), ("source_sha256", "a" * 64)),
    )
    connection.execute(
        "INSERT INTO goals VALUES (?,?,?,?,?,?,?)",
        ("account.delete", "account", "delete", "회원탈퇴 화면", "high", "stop_for_user", 1),
    )
    connection.execute(
        "INSERT INTO goal_phrases VALUES (?,?,?,?,?,?,?,?)",
        ("phrase-1", "account.delete", "ko-KR", "회원탈퇴", "회원탈퇴", "canonical", "human_gold", 1.0),
    )
    connection.execute(
        "INSERT INTO destination_signatures VALUES (?,?,?,?,?,?,?,?,?)",
        ("dest-1", "account.delete", "탈퇴 확인", '["회원탈퇴"]', "[]", "[]", '["탈퇴하기"]', 0.7, 1),
    )
    connection.execute(
        "INSERT INTO affordance_roles VALUES (?,?,?,?)",
        ("account_management", "계정 관리", "medium", 0),
    )
    connection.execute(
        "INSERT INTO semantic_screens VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "screen-1", "fingerprint-1", "설정", '["settings"]', 1, "logged_in", "native",
            '["설정","계정"]', "source-hash", "2026-08-01T00:00:00+00:00",
            "2026-08-01T00:00:00+00:00",
        ),
    )
    accessibility = json.dumps(
        {
            "window_title": "설정",
            "activity_semantics": "native",
            "elements": [
                {
                    "node_id": "node-1", "parent_node_id": "", "label": "계정 관리",
                    "role": "button", "clickable": True, "scrollable": False,
                }
            ],
        },
        ensure_ascii=False,
    )
    connection.execute(
        "INSERT INTO screen_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "obs-1", "screen-1", "com.example.safe", "1.0", "ko-KR",
            accessibility, '{"labels":[]}', "{}", "human_gold",
            "2026-08-01T00:00:00+00:00",
        ),
    )
    connection.execute(
        "INSERT INTO affordances VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "aff-1", "screen-1", "candidate-1", "계정 관리", "계정 관리", "",
            "account_management", "설정", "", "middle", "medium", 0,
            '["account_management"]', "node-1",
        ),
    )
    connection.execute(
        "INSERT INTO decision_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "case-1", "account.delete", "screen-1", "회원탈퇴", "{}", "click", "aff-1",
            None, "dest-1", "com.example.safe", "gold-1", 0, "human_gold", 0.98,
            "2026-08-01T00:00:00+00:00",
        ),
    )
    connection.execute(
        "INSERT INTO transition_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "outcome-1", "case-1", "screen-1", "destination_reached", "observed", 1,
            0.2, 0.9, 0.8, 0.1, "signature-v1", "reached", "", "",
            "2026-08-01T00:00:01+00:00",
        ),
    )
    connection.execute(
        "INSERT INTO evidence_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "evidence-1", "decision_case", "case-1", "human_gold", "gold-1", 1,
            0.98, "com.example.safe", "1.0", "ko-KR", "2026-08-01T00:00:01+00:00",
        ),
    )
    connection.execute(
        "INSERT INTO evaluation_app_splits VALUES (?,?,?,?)",
        ("app-disjoint-v1", "com.example.safe", "train", "unit fixture"),
    )
    connection.commit()
    connection.close()


def run() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "source-v1.sqlite"
        target = root / "target-v2.sqlite"
        migration_report = root / "migration.json"
        validation_report = root / "validation.json"
        build_v1(source)
        source_hash = sha256(source)
        subprocess.run(
            [
                sys.executable, str(MIGRATOR), "--source", str(source), "--target", str(target),
                "--report", str(migration_report),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert sha256(source) == source_hash
        subprocess.run(
            [
                sys.executable, str(VALIDATOR), "--database", str(target),
                "--expected-source-sha256", source_hash, "--expected-human-gold-records", "1",
                "--output", str(validation_report),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        validation = json.loads(validation_report.read_text(encoding="utf-8"))
        assert validation["passed"] is True
        assert validation["counts"]["experience_episodes"] == 1
        assert validation["counts"]["experience_steps"] == 1
        assert validation["counts"]["evidence_provenance"] == 1
        connection = sqlite3.connect(target)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM rlds_experience_steps_v1"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM skos_goal_concepts_v1"
        ).fetchone()[0] == 1
        connection.close()

        overwrite = subprocess.run(
            [
                sys.executable, str(MIGRATOR), "--source", str(source), "--target", str(target),
                "--report", str(migration_report),
            ],
            capture_output=True,
            text=True,
        )
        assert overwrite.returncode != 0
        assert "refusing to overwrite existing target" in (overwrite.stderr + overwrite.stdout)


if __name__ == "__main__":
    run()
    print("navigation_experience_profile_unit: ok")
