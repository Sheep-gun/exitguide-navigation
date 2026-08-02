from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_training_examples import (
    materialize_human_gold_examples,
    read_materialized_examples,
    write_training_artifacts,
)


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        database = root / "navigation.sqlite"
        _fixture_database(database)

        examples = materialize_human_gold_examples(database)
        assert len(examples) == 6
        assert {example.split for example in examples} == {"train", "validation", "test"}
        app_splits: dict[str, set[str]] = {}
        for example in examples:
            app_splits.setdefault(example.app_package, set()).add(example.split)
        assert all(len(splits) == 1 for splits in app_splits.values())

        action_examples = [
            example for example in examples if example.correct_action["name"] == "click_element"
        ]
        destination_examples = [
            example for example in examples if example.correct_action["name"] == "mark_destination"
        ]
        assert len(action_examples) == 3
        assert len(destination_examples) == 3
        assert all(example.correct_candidate is not None for example in action_examples)
        assert all(len(example.incorrect_candidates) == 1 for example in action_examples)
        assert all(example.history for example in destination_examples)
        assert all(
            step.get("selected_label")
            for example in destination_examples
            for step in example.history
        )

        manifest = write_training_artifacts(examples, root / "training")
        assert manifest["gold_is_evidence_not_macro"] is True
        assert manifest["total_sft_examples"] == 6
        combined = "".join(
            path.read_text(encoding="utf-8")
            for path in (root / "training").glob("*.jsonl")
        )
        assert "person@example.com" not in combined
        assert "010-1234-5678" not in combined
        assert "token=abcdefghijklmnop" not in combined
        assert "[email]" in combined
        assert "[phone]" in combined

        materialize_human_gold_examples(database)
        stored = list(read_materialized_examples(database))
        assert len(stored) == 6
        connection = sqlite3.connect(database)
        count = connection.execute("SELECT COUNT(*) FROM navigation_training_examples").fetchone()[0]
        metadata = dict(connection.execute("SELECT key, value FROM navigation_training_metadata"))
        connection.close()
        assert count == 6
        assert metadata["schema_version"] == "2"
        assert metadata["human_gold_example_count"] == "6"
    print("navigation training example checks ok")


def _fixture_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE navigation_gold_recordings (
          recording_id TEXT PRIMARY KEY,
          app_package TEXT NOT NULL,
          app_version TEXT NOT NULL,
          locale TEXT NOT NULL,
          goal_text TEXT NOT NULL,
          target_function TEXT NOT NULL,
          status TEXT NOT NULL,
          destination_screen_fingerprint TEXT,
          reviewer TEXT
        );
        CREATE TABLE navigation_gold_steps (
          step_id TEXT PRIMARY KEY,
          recording_id TEXT NOT NULL,
          ordinal INTEGER NOT NULL,
          screen_fingerprint TEXT NOT NULL,
          screen_context_json TEXT NOT NULL,
          candidates_json TEXT NOT NULL,
          selected_element_id TEXT,
          selected_element_key TEXT,
          selected_label TEXT,
          selected_action TEXT,
          selected_risk_level TEXT,
          outcome TEXT,
          next_screen_fingerprint TEXT
        );
        """
    )
    candidates = json.dumps(
        [
            {
                "element_id": "settings",
                "element_key": "stable-settings",
                "label": "설정 person@example.com",
                "role": "button",
                "risk_level": "low",
            },
            {
                "element_id": "promotion",
                "element_key": "stable-promotion",
                "label": "광고 010-1234-5678 token=abcdefghijklmnop",
                "role": "button",
                "risk_level": "low",
            },
        ],
        ensure_ascii=False,
    )
    for index, package in enumerate(("com.example.alpha", "com.example.beta", "com.example.gamma")):
        recording_id = f"recording-{index}"
        start = f"screen-{index}-start"
        destination = f"screen-{index}-destination"
        connection.execute(
            "INSERT INTO navigation_gold_recordings VALUES (?, ?, '1.0', 'ko-KR', ?, 'notification.settings', 'human_gold', ?, 'tester')",
            (recording_id, package, f"{package} 알림 설정", destination),
        )
        connection.execute(
            """INSERT INTO navigation_gold_steps VALUES (
                 ?, ?, 0, ?, ?, ?, 'settings', 'stable-settings', '설정',
                 'click', 'low', 'navigated', ?
               )""",
            (
                f"step-{index}-0",
                recording_id,
                start,
                json.dumps({"title": "계정", "private": "person@example.com"}, ensure_ascii=False),
                candidates,
                destination,
            ),
        )
        connection.execute(
            """INSERT INTO navigation_gold_steps VALUES (
                 ?, ?, 1, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL
               )""",
            (
                f"step-{index}-1",
                recording_id,
                destination,
                json.dumps({"title": "알림 설정"}, ensure_ascii=False),
                candidates,
            ),
        )
    connection.commit()
    connection.close()


if __name__ == "__main__":
    main()
