from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.universal_navigation_graph import UniversalNavigationGraphRepository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the compact app/function route serving index and optimize SQLite "
            "without deleting raw navigation evidence."
        )
    )
    parser.add_argument("database", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create a SQLite backup, rebuild the serving index, and compact the database.",
    )
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file():
        raise SystemExit(f"Navigation database does not exist: {database}")

    before = _inventory(database)
    if not args.apply:
        print(json.dumps({"mode": "dry_run", "database": str(database), "before": before}, indent=2))
        return

    backup = database.with_name(
        f"{database.stem}.before-serving-optimize-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}{database.suffix}"
    )
    _backup(database, backup)
    repository = UniversalNavigationGraphRepository(database)
    index_result = repository.rebuild_app_function_route_index()
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA optimize")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    with sqlite3.connect(database) as connection:
        connection.execute("VACUUM")
    print(
        json.dumps(
            {
                "mode": "applied",
                "database": str(database),
                "backup": str(backup),
                "before": before,
                "index": index_result,
                "after": _inventory(database),
                "policy": (
                    "Raw screens, transitions, failures, and shadow routes were retained as "
                    "learning evidence; only verified_candidate and approved routes are serving."
                ),
            },
            indent=2,
        )
    )


def _inventory(database: Path) -> dict[str, object]:
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        route_statuses: dict[str, int] = {}
        if "universal_routes" in tables:
            route_statuses = {
                str(status): int(count)
                for status, count in connection.execute(
                    "SELECT status, COUNT(*) FROM universal_routes GROUP BY status"
                ).fetchall()
            }
        serving_functions = 0
        if "universal_app_function_routes" in tables:
            serving_functions = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM (
                      SELECT app_key, target_function
                      FROM universal_app_function_routes
                      WHERE is_serving = 1
                      GROUP BY app_key, target_function
                    )
                    """
                ).fetchone()[0]
            )
    return {
        "bytes": database.stat().st_size,
        "route_statuses": route_statuses,
        "serving_app_functions": serving_functions,
    }


def _backup(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)


if __name__ == "__main__":
    main()
