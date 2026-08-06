from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "Prepare-NavigationRuntimeGeneration.py"
SPEC = importlib.util.spec_from_file_location("runtime_generation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def run() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        output = root / "generation-test"
        payload = MODULE.prepare_generation(
            argparse.Namespace(
                output_dir=output,
                generation_id="generation-test",
                base_snapshot="training_snapshot_test",
                plan=ROOT / "db" / "navigation_account_state_recollection_v1.json",
                source_code_commit="a" * 40,
                server_release_id="test-release",
            )
        )
        assert payload["status"] == "prepared"
        assert payload["policy"]["activation_status"] == "not_activated"
        assert payload["policy"]["runtime_and_review_separate"] is True
        assert payload["runtime"]["user_version"] == 5
        assert payload["review"]["user_version"] == 2
        assert payload["runtime"]["quick_check"] == "ok"
        assert payload["review"]["quick_check"] == "ok"
        assert payload["runtime"]["path"] != payload["review"]["path"]
        environment = (output / "navigation-runtime-generation.env").read_text(
            encoding="utf-8"
        )
        assert f"NAVIGATION_RUNTIME_DB_PATH={output / 'navigation-runtime-v1.sqlite'}" in environment
        assert f"NAVIGATION_REVIEW_DB_PATH={output / 'navigation-human-review-v1.sqlite'}" in environment
        with closing(sqlite3.connect(output / "navigation-runtime-v1.sqlite")) as connection:
            assert connection.execute("SELECT count(*) FROM navigation_sessions").fetchone()[0] == 0
        with closing(sqlite3.connect(output / "navigation-human-review-v1.sqlite")) as connection:
            assert connection.execute("SELECT count(*) FROM navigation_human_reviews").fetchone()[0] == 0
        second = MODULE.prepare_generation(
            argparse.Namespace(
                output_dir=output,
                generation_id="generation-test",
                base_snapshot="training_snapshot_test",
                plan=ROOT / "db" / "navigation_account_state_recollection_v1.json",
                source_code_commit="a" * 40,
                server_release_id="test-release",
            )
        )
        assert second["generation_id"] == payload["generation_id"]


if __name__ == "__main__":
    run()
    print("navigation_runtime_generation_unit: ok")
