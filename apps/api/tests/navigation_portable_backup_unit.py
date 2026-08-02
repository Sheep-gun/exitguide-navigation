from __future__ import annotations

import sqlite3
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_portable_backup import (
    ARCHIVE_ROOT,
    create_portable_backup,
    restore_portable_backup,
    verify_portable_backup,
)


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        base = Path(temporary_directory)
        root = base / "source"
        database = root / "data" / "universal-navigation.sqlite"
        index = root / ".artifacts" / "android-control" / "navigation-examples.sqlite"
        database.parent.mkdir(parents=True)
        index.parent.mkdir(parents=True)
        _database(database, "navigation")
        _database(index, "android-control")
        index_connection = sqlite3.connect(index)
        try:
            index_connection.execute(
                "INSERT INTO sample(value) VALUES (?)",
                ("https://example.test/risk-evaluation-and-mitigation-strategies-rems",),
            )
            index_connection.execute(
                "INSERT INTO sample(value) VALUES (?)",
                ("https://example.test/click?gclid=abc_sk-abcdefghijklmnopqrstuvwxyz012345%2",),
            )
            index_connection.commit()
        finally:
            index_connection.close()
        external_artifacts = base / "server-artifacts"
        training = external_artifacts / "navigation-training"
        training.mkdir(parents=True)
        (training / "sft.jsonl").write_text('{"safe":true}\n', encoding="utf-8")
        raw = training / "raw"
        raw.mkdir()
        (raw / "screen.png").write_bytes(b"raw-private-image")
        (root / ".env").write_text("EXAONE_API_KEY=flp_secret_should_not_leave\n", encoding="utf-8")
        (root / ".env.example").write_text("EXAONE_API_KEY=\n", encoding="utf-8")

        archive = base / "portable.tar.gz"
        created = create_portable_backup(
            root=root,
            output=archive,
            database_path=database,
            android_control_index=index,
            artifacts_root=external_artifacts,
            source_commit="test-commit",
        )
        assert created["source_commit"] == "test-commit"
        verified = verify_portable_backup(archive)
        assert verified["file_count"] >= 4
        with tarfile.open(archive, "r:gz") as handle:
            names = {member.name for member in handle.getmembers()}
        assert f"{ARCHIVE_ROOT}/manifest.json" in names
        assert not any(name.endswith("/.env") for name in names)
        assert not any("/raw/" in name for name in names)
        assert f"{ARCHIVE_ROOT}/artifacts/navigation-training/sft.jsonl" in names

        restored_root = base / "restored"
        restored = restore_portable_backup(
            archive_path=archive,
            destination=restored_root,
        )
        assert "data\\universal-navigation.sqlite" in restored["restored"] or "data/universal-navigation.sqlite" in restored["restored"]
        assert _value(restored_root / "data" / "universal-navigation.sqlite") == "navigation"
        assert _value(
            restored_root / ".artifacts" / "android-control" / "navigation-examples.sqlite"
        ) == "android-control"
        assert not (restored_root / ".env").exists()

        leaked = external_artifacts / "models" / "token.txt"
        leaked.parent.mkdir(parents=True)
        # Credentials must still be detected in artifacts larger than the old
        # 2 MB in-memory scan shortcut.
        leaked.write_bytes(
            b"x" * 2_100_000
            + b"\nEXAONE_API_KEY=flp_abcdefghijklmnopqrstuvwxyz012345\n"
        )
        try:
            create_portable_backup(
                root=root,
                output=base / "unsafe.tar.gz",
                database_path=database,
                android_control_index=index,
                artifacts_root=external_artifacts,
            )
        except ValueError as exc:
            assert "possible credential" in str(exc)
        else:
            raise AssertionError("portable backup must reject embedded credentials")
    print("portable backup checks ok")


def _database(path: Path, value: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE sample(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample(value) VALUES (?)", (value,))
        connection.commit()
    finally:
        connection.close()


def _value(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return str(connection.execute("SELECT value FROM sample").fetchone()[0])
    finally:
        connection.close()


if __name__ == "__main__":
    main()
