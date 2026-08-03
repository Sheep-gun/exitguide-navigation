from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_decision_memory import normalize_text, stable_id  # noqa: E402


PATCH_VERSION = "navigation-decision-patch-20260803-account-hub-alias-v1"
ALIASES = (
    ("account.hub", "ko", "계정", 0.96, []),
)


def apply_patches(database: Path) -> dict[str, object]:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(database)

    connection = sqlite3.connect(database)
    try:
        integrity_before = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity_before != "ok":
            raise RuntimeError(f"database integrity check failed: {integrity_before}")

        connection.execute("BEGIN IMMEDIATE")
        inserted = 0
        unchanged = 0
        for role_id, locale, alias, confidence, negatives in ALIASES:
            if connection.execute(
                "SELECT 1 FROM affordance_roles WHERE role_id = ?", (role_id,)
            ).fetchone() is None:
                raise RuntimeError(f"missing affordance role: {role_id}")
            normalized = normalize_text(alias)
            existing = connection.execute(
                """
                SELECT confidence, negative_context_json
                FROM affordance_role_aliases
                WHERE role_id = ? AND locale = ? AND normalized_alias = ?
                """,
                (role_id, locale, normalized),
            ).fetchone()
            expected_negatives = json.dumps(negatives, ensure_ascii=False, separators=(",", ":"))
            if existing is not None:
                if float(existing[0]) != confidence or str(existing[1]) != expected_negatives:
                    raise RuntimeError(
                        f"existing alias differs from patch contract: {role_id}/{locale}/{normalized}"
                    )
                unchanged += 1
                continue
            connection.execute(
                """
                INSERT INTO affordance_role_aliases(
                    alias_id, role_id, locale, alias, normalized_alias,
                    confidence, negative_context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stable_id("ara_", role_id, locale, normalized),
                    role_id,
                    locale,
                    alias,
                    normalized,
                    confidence,
                    expected_negatives,
                ),
            )
            inserted += 1
        connection.execute(
            """
            INSERT INTO navigation_db_metadata(key, value) VALUES ('ontology_patch_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (PATCH_VERSION,),
        )
        connection.commit()
        integrity_after = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity_after != "ok":
            raise RuntimeError(f"database integrity check failed after patch: {integrity_after}")
        return {
            "database": str(database),
            "patch_version": PATCH_VERSION,
            "inserted_aliases": inserted,
            "unchanged_aliases": unchanged,
            "integrity_check": integrity_after,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply idempotent, evidence-backed Navigation Decision DB patches"
    )
    parser.add_argument("--database", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    print(json.dumps(apply_patches(parse_args().database), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
