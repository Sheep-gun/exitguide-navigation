import gzip
import json
import sqlite3
import struct
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services import android_control_import, android_control_index
from app.services.android_control_index import AndroidControlIndex, AndroidControlStepRecord, read_normalized_jsonl


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "fixtures" / "android-control" / "normalized-sample.jsonl"


def main() -> None:
    assert_normalized_records_build_searchable_index()
    assert_runtime_search_is_read_only()
    assert_legacy_index_semantic_vectors_are_backfilled()
    assert_korean_goal_retrieves_account_entry_demonstration()
    assert_typed_values_are_not_copied_to_index_targets()
    assert_sensitive_screen_text_is_redacted()
    assert_normalized_export_is_redacted()
    assert_official_tfrecord_streams_without_tensorflow()
    print("AndroidControl retrieval index checks ok")


def assert_runtime_search_is_read_only() -> None:
    with TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "android-control.sqlite"
        index = AndroidControlIndex(path)
        index.build(read_normalized_jsonl(FIXTURE))
        before = path.stat().st_mtime_ns
        evidence = index.search(
            goal_text="구독을 해지하고 싶어",
            candidate_labels=["내 페이지", "구독 관리"],
            limit=3,
        )
        assert evidence
        assert path.stat().st_mtime_ns == before
        assert not path.with_name(path.name + "-wal").exists()
        assert not path.with_name(path.name + "-shm").exists()


def assert_normalized_records_build_searchable_index() -> None:
    records = list(read_normalized_jsonl(FIXTURE))
    assert len(records) == 10
    with TemporaryDirectory() as temporary_directory:
        index = AndroidControlIndex(Path(temporary_directory) / "android-control.sqlite")
        assert index.build(records) == 10
        assert index.count() == 10
        evidence = index.search(goal_text="마케팅 알림을 끄고 싶어", candidate_labels=["설정", "프로필"])
        assert evidence
        assert evidence[0].goal == "Turn off marketing notifications"
        connection = sqlite3.connect(index.database_path)
        try:
            vector_rows, dimensions = connection.execute(
                """
                SELECT COUNT(*), MIN(length(semantic_vector))
                FROM android_control_steps
                """
            ).fetchone()
            first_transition = connection.execute(
                """
                SELECT next_screen_text, success, terminal, risk_level,
                       screen_function, action_function
                FROM android_control_steps
                WHERE episode_id = 'synthetic_ac_subscription_1' AND step_index = 0
                """
            ).fetchone()
            terminal_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM android_control_steps WHERE terminal = 1"
                ).fetchone()[0]
            )
            high_risk_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM android_control_steps WHERE risk_level IN ('high', 'blocked')"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        assert vector_rows == 10
        assert dimensions == android_control_index.SEMANTIC_VECTOR_DIMENSIONS * 4
        assert first_transition is not None
        assert "Purchases and memberships" in first_transition[0]
        assert first_transition[1:3] == (1, 0)
        assert first_transition[4]
        assert first_transition[5]
        assert terminal_count == 3
        assert high_risk_count >= 2


def assert_legacy_index_semantic_vectors_are_backfilled() -> None:
    with TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "android-control-v1.sqlite"
        connection = sqlite3.connect(path)
        try:
            connection.executescript(
                """
                CREATE TABLE android_control_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE android_control_steps (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  episode_id TEXT NOT NULL,
                  goal TEXT NOT NULL,
                  step_index INTEGER NOT NULL,
                  step_instruction TEXT NOT NULL,
                  action_type TEXT NOT NULL,
                  target_text TEXT NOT NULL,
                  screen_text TEXT NOT NULL,
                  app_name TEXT NOT NULL DEFAULT '',
                  source_split TEXT NOT NULL DEFAULT '',
                  search_text TEXT NOT NULL,
                  UNIQUE(episode_id, step_index)
                );
                CREATE VIRTUAL TABLE android_control_steps_fts USING fts5(search_text);
                """
            )
            search_text = "cancel subscription settings membership"
            cursor = connection.execute(
                """
                INSERT INTO android_control_steps (
                  episode_id, goal, step_index, step_instruction, action_type,
                  target_text, screen_text, app_name, source_split, search_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-episode",
                    "Cancel a subscription",
                    0,
                    "Open settings",
                    "click",
                    "Settings",
                    "Account Settings",
                    "synthetic",
                    "test",
                    search_text,
                ),
            )
            connection.execute(
                "INSERT INTO android_control_steps_fts(rowid, search_text) VALUES (?, ?)",
                (cursor.lastrowid, search_text),
            )
            connection.commit()
        finally:
            connection.close()

        index = AndroidControlIndex(path)
        assert index.backfill_semantic_vectors(batch_size=1) == 1
        assert index.backfill_semantic_vectors(batch_size=1) == 0
        connection = sqlite3.connect(path)
        try:
            vector_length = int(
                connection.execute("SELECT length(semantic_vector) FROM android_control_steps").fetchone()[0]
            )
            schema_version = connection.execute(
                "SELECT value FROM android_control_metadata WHERE key = 'schema_version'"
            ).fetchone()
        finally:
            connection.close()
        assert vector_length == android_control_index.SEMANTIC_VECTOR_DIMENSIONS * 4
        assert schema_version == ("3",)


def assert_korean_goal_retrieves_account_entry_demonstration() -> None:
    with TemporaryDirectory() as temporary_directory:
        index = AndroidControlIndex(Path(temporary_directory) / "android-control.sqlite")
        index.build(read_normalized_jsonl(FIXTURE))
        evidence = index.search(
            goal_text="유튜브 프리미엄 구독을 해지하고 싶어",
            candidate_labels=["홈", "Shorts", "구독", "내 페이지"],
            screen_text="YouTube 홈",
            limit=5,
        )
        assert evidence
        assert any(item.target_text == "Profile" for item in evidence)
        assert all(item.goal == "Cancel a premium membership" for item in evidence[:3])
        assert all(item.next_screen_text for item in evidence if not item.terminal)
        payload = evidence[0].prompt_payload()
        assert payload["success"] is True
        assert payload["risk_level"] in {"low", "medium", "high", "blocked"}
        assert "expected_next_screen" in payload
        assert "target_present_on_current_screen" in payload
        assert 0.0 <= float(payload["current_candidate_alignment"]) <= 1.0


def assert_typed_values_are_not_copied_to_index_targets() -> None:
    action = json.loads('{"action_type":"input_text","text":"private@example.com"}')
    target = android_control_import._target_text(action, [], width=1080, height=2400)
    assert target == "text input"
    assert "private@example.com" not in target


def assert_sensitive_screen_text_is_redacted() -> None:
    with TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "android-control.sqlite"
        index = AndroidControlIndex(path)
        index.build(
            [
                AndroidControlStepRecord(
                    episode_id="private-test",
                    goal="Open account settings",
                    step_index=0,
                    step_instruction="Tap the profile",
                    action_type="click",
                    target_text="yang@example.com",
                    screen_text="Account 010-1234-5678",
                )
            ]
        )
        connection = sqlite3.connect(path)
        try:
            row = connection.execute(
                "SELECT target_text, screen_text FROM android_control_steps"
            ).fetchone()
        finally:
            connection.close()
        assert row == ("[email]", "Account [phone]")


def assert_normalized_export_is_redacted() -> None:
    with TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "normalized.jsonl"
        android_control_index.write_normalized_jsonl(
            [
                AndroidControlStepRecord(
                    episode_id="private-export",
                    goal="Open account for private@example.com",
                    step_index=0,
                    step_instruction="Tap 010-1234-5678",
                    action_type="click",
                    target_text="private@example.com",
                    screen_text="Contact 010-1234-5678",
                )
            ],
            path,
        )
        exported = path.read_text(encoding="utf-8")
        assert "private@example.com" not in exported
        assert "010-1234-5678" not in exported
        assert "[email]" in exported and "[phone]" in exported


def assert_official_tfrecord_streams_without_tensorflow() -> None:
    forest = _message(
        1,
        _message(
            11,
            _message(
                1,
                b"".join(
                    (
                        _varint_field(1, 1),
                        _message(
                            2,
                            b"".join(
                                (
                                    _varint_field(1, 0),
                                    _varint_field(2, 0),
                                    _varint_field(3, 1080),
                                    _varint_field(4, 2400),
                                )
                            ),
                        ),
                        _message(3, b"android.widget.Button"),
                        _message(6, b"com.synthetic.video"),
                        _message(7, b"Profile"),
                        _varint_field(14, 1),
                        _varint_field(16, 1),
                        _varint_field(23, 1),
                    )
                ),
            ),
        ),
    )
    example = _tf_example(
        {
            "episode_id": _int_feature([42]),
            "goal": _bytes_feature([b"Cancel a premium membership"]),
            "accessibility_trees": _bytes_feature([forest]),
            "screenshot_widths": _int_feature([1080]),
            "screenshot_heights": _int_feature([2400]),
            "actions": _bytes_feature([b'{"action_type":"click","x":0.5,"y":0.5}']),
            "step_instructions": _bytes_feature([b"Tap the profile button"]),
            # The decoder deliberately ignores this potentially large field.
            "screenshots": _bytes_feature([b"not-a-real-png"]),
        }
    )
    with TemporaryDirectory() as temporary_directory:
        tfrecord_path = Path(temporary_directory) / "android_control-00000-of-00020"
        with gzip.open(tfrecord_path, "wb") as handle:
            handle.write(struct.pack("<Q", len(example)))
            handle.write(b"\0" * 4)
            handle.write(example)
            handle.write(b"\0" * 4)
        records = list(
            android_control_import.iter_official_tfrecords(
                [tfrecord_path],
                source_split="synthetic",
                episode_limit=1,
            )
        )
    assert len(records) == 1
    assert records[0].episode_id == "42"
    assert records[0].target_text == "Profile"
    assert records[0].screen_text == "Profile"
    assert records[0].app_name == "com.synthetic.video"
    assert records[0].source_split == "synthetic"


def _tf_example(features: dict[str, bytes]) -> bytes:
    entries = b"".join(
        _message(1, _message(1, key.encode("utf-8")) + _message(2, feature))
        for key, feature in features.items()
    )
    return _message(1, entries)


def _bytes_feature(values: list[bytes]) -> bytes:
    return _message(1, b"".join(_message(1, value) for value in values))


def _int_feature(values: list[int]) -> bytes:
    packed = b"".join(_varint(value) for value in values)
    return _message(3, _message(1, packed))


def _message(field: int, value: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(value)) + value


def _varint_field(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while True:
        current = value & 0x7F
        value >>= 7
        if value:
            encoded.append(current | 0x80)
        else:
            encoded.append(current)
            return bytes(encoded)


if __name__ == "__main__":
    main()
