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
    assert_korean_goal_retrieves_account_entry_demonstration()
    assert_typed_values_are_not_copied_to_index_targets()
    assert_sensitive_screen_text_is_redacted()
    assert_normalized_export_is_redacted()
    assert_official_tfrecord_streams_without_tensorflow()
    print("AndroidControl retrieval index checks ok")


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
