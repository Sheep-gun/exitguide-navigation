from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = 1
ARCHIVE_ROOT = "exitguide-navigation-portable"
DEFAULT_ARTIFACT_NAMES = (
    "navigation-training",
    "training-v2",
    "navigation-learning",
    "agent-only",
    "navigation-evaluation",
    "models",
    "navigation-vlm",
    "apk",
)
SOURCE_ALLOWLIST = (
    ".env.example",
    "apps/api/app",
    "apps/api/requirements.txt",
    "apps/mobile/app.json",
    "apps/mobile/eas.json",
    "apps/mobile/package.json",
    "apps/mobile/package-lock.json",
    "apps/mobile/plugins",
    "apps/mobile/src",
    "apps/mobile/assets",
    "contracts",
    "deploy",
    "fixtures/android-control",
    "fixtures/navigation",
    "scripts",
    "docs/ANDROID_CONTROL.md",
    "docs/CURRENT_PROJECT_STATUS.md",
    "docs/K_EXAONE_CAPABILITY_AUDIT.md",
    "docs/NAVIGATION_AGENT_EVALUATION.md",
    "docs/NAVIGATION_AGENT_LEARNING_ARCHITECTURE.md",
    "docs/UNIVERSAL_NAVIGATION_AGENT.md",
)
FORBIDDEN_BASENAMES = frozenset({".env", "runtime.env", "credentials.json"})
FORBIDDEN_PARTS = frozenset(
    {
        "raw",
        "screenshots",
        "images",
        "model-weights",
        "venv",
        ".venv",
        ".git",
        "__pycache__",
        "node_modules",
        "build",
    }
)
SECRET_PATTERNS = (
    # Token boundaries matter for corpus/index files: ordinary words such as
    # ``risk-evaluation`` contain the byte sequence ``sk-`` but are not API
    # keys. A real credential may follow ``=``, quotes or whitespace, all of
    # which still satisfy this negative alphanumeric boundary.
    re.compile(rb"(?<![a-z0-9])flp_[a-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(rb"(?<![a-z0-9])sk-[a-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(rb"\bbearer\s+[a-z0-9._~-]{24,}", re.IGNORECASE),
)


def create_portable_backup(
    *,
    root: str | Path,
    output: str | Path,
    database_path: str | Path | None = None,
    android_control_index: str | Path | None = None,
    artifacts_root: str | Path | None = None,
    artifact_names: Iterable[str] = DEFAULT_ARTIFACT_NAMES,
    source_commit: str = "",
) -> dict[str, object]:
    root_path = Path(root).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    database = _resolve_input(
        root_path,
        database_path or root_path / "data" / "universal-navigation.sqlite",
    )
    android_index = _resolve_input(
        root_path,
        android_control_index
        or root_path / ".artifacts" / "android-control" / "navigation-examples.sqlite",
    )
    artifact_source_root = _resolve_input(
        root_path,
        artifacts_root or root_path / ".artifacts",
    )
    if not database.is_file():
        raise FileNotFoundError(f"navigation database not found: {database}")

    with tempfile.TemporaryDirectory(
        prefix=".exitguide-portable-",
        dir=output_path.parent,
    ) as temporary_directory:
        staging = Path(temporary_directory) / ARCHIVE_ROOT
        staging.mkdir(parents=True)
        snapshot = staging / "data" / "universal-navigation.sqlite"
        snapshot.parent.mkdir(parents=True)
        _snapshot_sqlite(database, snapshot)

        if android_index.is_file():
            target = staging / "indices" / "android-control.sqlite"
            target.parent.mkdir(parents=True)
            shutil.copy2(android_index, target)

        for name in artifact_names:
            safe_name = _safe_artifact_name(name)
            source = artifact_source_root / safe_name
            if source.exists():
                _copy_filtered(source, staging / "artifacts" / safe_name)

        for relative in SOURCE_ALLOWLIST:
            source = root_path / relative
            if not source.exists():
                continue
            target = staging / "source" / relative
            if source.is_dir():
                _copy_filtered(source, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

        commit = source_commit.strip() or _git_commit(root_path)
        manifest = _build_manifest(
            staging,
            source_commit=commit,
            source_database=str(database),
            android_control_included=android_index.is_file(),
        )
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        verify_staging(staging)

        temporary_archive = output_path.with_name(f".{output_path.name}.building")
        temporary_archive.unlink(missing_ok=True)
        try:
            with tarfile.open(temporary_archive, "w:gz") as archive:
                archive.add(staging, arcname=ARCHIVE_ROOT, recursive=True)
            os.replace(temporary_archive, output_path)
        finally:
            temporary_archive.unlink(missing_ok=True)

    archive_sha256 = _sha256(output_path)
    checksum_path = output_path.with_suffix(output_path.suffix + ".sha256")
    checksum_path.write_text(
        f"{archive_sha256}  {output_path.name}\n",
        encoding="ascii",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "archive": str(output_path),
        "archive_sha256": archive_sha256,
        "archive_bytes": output_path.stat().st_size,
        "database_snapshot": True,
        "android_control_included": android_index.is_file(),
        "source_commit": commit,
    }


def verify_portable_backup(archive_path: str | Path) -> dict[str, object]:
    path = Path(archive_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    with tempfile.TemporaryDirectory(prefix="exitguide-portable-verify-") as temporary_directory:
        root = Path(temporary_directory)
        _safe_extract(path, root)
        staging = root / ARCHIVE_ROOT
        manifest = verify_staging(staging)
    return {
        "schema_version": SCHEMA_VERSION,
        "archive": str(path),
        "archive_sha256": _sha256(path),
        "archive_bytes": path.stat().st_size,
        "file_count": len(manifest["files"]),
        "source_commit": manifest.get("source_commit", ""),
    }


def restore_portable_backup(
    *,
    archive_path: str | Path,
    destination: str | Path,
    force: bool = False,
) -> dict[str, object]:
    archive = Path(archive_path).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    destination_path.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".exitguide-portable-restore-",
        dir=destination_path.parent,
    ) as temporary_directory:
        extracted = Path(temporary_directory)
        _safe_extract(archive, extracted)
        staging = extracted / ARCHIVE_ROOT
        manifest = verify_staging(staging)
        mappings = (
            (staging / "data" / "universal-navigation.sqlite", destination_path / "data" / "universal-navigation.sqlite"),
            (staging / "artifacts", destination_path / ".artifacts"),
            (staging / "indices" / "android-control.sqlite", destination_path / ".artifacts" / "android-control" / "navigation-examples.sqlite"),
            (staging / "source", destination_path / "portable-source"),
        )
        restored: list[str] = []
        for source, target in mappings:
            if not source.exists():
                continue
            if target.exists() and not force:
                raise FileExistsError(f"restore target already exists: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                temporary_target = target.with_name(f".{target.name}.restoring")
                shutil.copy2(source, temporary_target)
                os.replace(temporary_target, target)
            restored.append(str(target.relative_to(destination_path)))
    return {
        "schema_version": SCHEMA_VERSION,
        "archive": str(archive),
        "destination": str(destination_path),
        "restored": restored,
        "source_commit": manifest.get("source_commit", ""),
    }


def verify_staging(staging: Path) -> dict[str, object]:
    manifest_path = staging / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("portable backup manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("unsupported portable backup schema")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("portable backup manifest has no files")
    expected_paths: set[str] = set()
    for row in files:
        if not isinstance(row, dict):
            raise ValueError("invalid portable backup file manifest row")
        relative = _safe_relative(str(row.get("path", "")))
        expected_paths.add(relative.as_posix())
        path = staging / relative
        if not path.is_file():
            raise ValueError(f"portable backup file is missing: {relative}")
        if path.stat().st_size != int(row.get("bytes", -1)):
            raise ValueError(f"portable backup size mismatch: {relative}")
        if _sha256(path) != str(row.get("sha256", "")):
            raise ValueError(f"portable backup checksum mismatch: {relative}")
        _assert_safe_archive_file(path, relative)
    actual_paths = {
        path.relative_to(staging).as_posix()
        for path in staging.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_paths != expected_paths:
        raise ValueError("portable backup contains unmanifested or missing files")
    return manifest


def _snapshot_sqlite(source: Path, target: Path) -> None:
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30.0)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.backup(target_connection, pages=4096)
        integrity = str(target_connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise ValueError(f"navigation database snapshot failed integrity check: {integrity}")
    finally:
        target_connection.close()
        source_connection.close()


def _build_manifest(
    staging: Path,
    *,
    source_commit: str,
    source_database: str,
    android_control_included: bool,
) -> dict[str, object]:
    files = []
    for path in sorted(item for item in staging.rglob("*") if item.is_file()):
        relative = path.relative_to(staging)
        _assert_safe_archive_file(path, relative)
        files.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_commit": source_commit,
        "source_database": source_database,
        "android_control_included": android_control_included,
        "excludes": [
            "credentials and .env files",
            "AndroidControl raw shards",
            "raw screenshots and images",
            "model weights and virtual environments",
        ],
        "files": files,
    }


def _safe_extract(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            relative = _safe_relative(member.name)
            if not relative.parts or relative.parts[0] != ARCHIVE_ROOT:
                raise ValueError("portable archive has an unexpected root")
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError("portable archive may not contain links or devices")
            target = (destination / relative).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise ValueError("portable archive path traversal detected")
        # Every path and member type is validated above, which also keeps this
        # compatible with the Python 3.10 runtime on the temporary GPU host.
        archive.extractall(destination, members=members)


def _copy_filtered(source: Path, target: Path) -> None:
    if source.is_file():
        relative = Path(source.name)
        _assert_safe_source_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        try:
            _assert_safe_source_path(relative)
        except ValueError:
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def _assert_safe_source_path(relative: Path) -> None:
    lowered = {part.casefold() for part in relative.parts}
    if relative.name.casefold() in FORBIDDEN_BASENAMES or lowered & FORBIDDEN_PARTS:
        raise ValueError(f"forbidden portable backup source path: {relative}")


def _assert_safe_archive_file(path: Path, relative: Path) -> None:
    _assert_safe_source_path(relative)
    if _contains_secret(path):
        raise ValueError(f"possible credential in portable backup: {relative}")


def _contains_secret(path: Path) -> bool:
    """Scan small and multi-gigabyte artifacts without loading them in RAM."""

    overlap = 256
    tail = b""
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sample = (tail + chunk).lower()
            if any(pattern.search(sample) for pattern in SECRET_PATTERNS):
                return True
            tail = sample[-overlap:]
    return False


def _safe_relative(value: str) -> Path:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or not value or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe portable backup path: {value!r}")
    return path


def _safe_artifact_name(value: str) -> str:
    if not value or Path(value).name != value or value.startswith("."):
        raise ValueError(f"unsafe artifact name: {value!r}")
    return value


def _resolve_input(root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
