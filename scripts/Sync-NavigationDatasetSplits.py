from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path


SPLIT_MAP = {
    "collection": "train",
    "validation": "validation",
    "locked_holdout": "test",
}


def load_manifest(path: Path) -> tuple[str, list[dict[str, object]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = str(payload.get("manifest_version", ""))
    entries = payload.get("entries")
    if not version or not isinstance(entries, list):
        raise ValueError("invalid dataset split manifest")
    packages: set[str] = set()
    normalized: list[dict[str, object]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError("manifest entry must be an object")
        app_package = str(raw.get("app_package", ""))
        split = str(raw.get("split", ""))
        if not app_package or split not in SPLIT_MAP or app_package in packages:
            raise ValueError(f"invalid or duplicate manifest entry: {app_package}")
        packages.add(app_package)
        normalized.append(raw)
    return version, normalized


def planned_changes(
    connection: sqlite3.Connection,
    *,
    manifest_version: str,
    entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    connection.row_factory = sqlite3.Row
    changes: list[dict[str, object]] = []
    for entry in entries:
        app_package = str(entry["app_package"])
        target = SPLIT_MAP[str(entry["split"])]
        existing = connection.execute(
            "SELECT split_version,split,reason FROM evaluation_app_splits WHERE app_package=?",
            (app_package,),
        ).fetchall()
        if len(existing) > 1:
            raise ValueError(f"multiple legacy split rows for {app_package}")
        previous = None if not existing else str(existing[0]["split"])
        if previous != target:
            changes.append(
                {
                    "app_package": app_package,
                    "from": previous,
                    "to": target,
                    "manifest_version": manifest_version,
                }
            )
    return changes


def apply_changes(
    connection: sqlite3.Connection,
    *,
    manifest_version: str,
    entries: list[dict[str, object]],
) -> None:
    for entry in entries:
        app_package = str(entry["app_package"])
        target = SPLIT_MAP[str(entry["split"])]
        reason = f"synchronized from {manifest_version}: {entry.get('reason', '')}"
        existing = connection.execute(
            "SELECT split_version FROM evaluation_app_splits WHERE app_package=?",
            (app_package,),
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO evaluation_app_splits VALUES ('app-disjoint-v1',?,?,?)",
                (app_package, target, reason),
            )
        else:
            connection.execute(
                "UPDATE evaluation_app_splits SET split=?,reason=? WHERE app_package=?",
                (target, reason, app_package),
            )
        connection.execute(
            "UPDATE experience_episodes SET split_version='app-disjoint-v1',split=? WHERE source_app_package=?",
            (target, app_package),
        )
    leaking = connection.execute(
        """
        SELECT c.source_app_package,s.split,count(*)
        FROM decision_cases AS c
        JOIN evaluation_app_splits AS s ON s.app_package=c.source_app_package
        WHERE s.split IN ('validation','test')
        GROUP BY c.source_app_package,s.split
        """
    ).fetchall()
    if leaking:
        raise ValueError(f"apps with retrieval evidence remain outside train: {leaking}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize Decision DB app splits")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    version, entries = load_manifest(args.manifest)
    with sqlite3.connect(args.database) as connection:
        changes = planned_changes(connection, manifest_version=version, entries=entries)
    if args.apply:
        if args.backup is None:
            raise ValueError("--backup is required with --apply")
        args.backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.database, args.backup)
        with sqlite3.connect(args.database) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            try:
                apply_changes(connection, manifest_version=version, entries=entries)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    print(
        json.dumps(
            {
                "database": str(args.database),
                "manifest_version": version,
                "applied": args.apply,
                "change_count": len(changes),
                "changes": changes,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
