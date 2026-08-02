from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.android_control_index import (  # noqa: E402
    AndroidControlIndex,
    SEMANTIC_VECTOR_DIMENSIONS,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill the portable local semantic-vector layer of an AndroidControl index."
    )
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4_000)
    args = parser.parse_args()
    index = AndroidControlIndex(args.index)
    updated = index.backfill_semantic_vectors(batch_size=args.batch_size)
    connection = sqlite3.connect(args.index)
    try:
        records, vectors = connection.execute(
            """
            SELECT COUNT(*), SUM(CASE WHEN length(semantic_vector) > 0 THEN 1 ELSE 0 END)
            FROM android_control_steps
            """
        ).fetchone()
        transitions, terminals, failures = connection.execute(
            """
            SELECT COUNT(*), SUM(terminal),
                   SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END)
            FROM android_control_steps
            """
        ).fetchone()
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        connection.close()
    report = {
        "schema_version": 3,
        "vector_kind": "signed-feature-hash-bilingual-function-cues",
        "dimensions": SEMANTIC_VECTOR_DIMENSIONS,
        "records": int(records),
        "vectors": int(vectors or 0),
        "updated": updated,
        "transition_metadata": int(transitions),
        "terminal_steps": int(terminals or 0),
        "failure_steps": int(failures or 0),
        "integrity": integrity,
        "portable": True,
    }
    if report["records"] != report["vectors"] or integrity != "ok":
        raise SystemExit(json.dumps(report, ensure_ascii=False))
    digest = hashlib.sha256()
    with args.index.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    checksum = digest.hexdigest()
    built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    args.index.with_suffix(args.index.suffix + ".sha256").write_text(
        f"{checksum}  {args.index.resolve()}\n",
        encoding="ascii",
    )
    args.index.with_suffix(args.index.suffix + ".built-at").write_text(
        f"{built_at}\n",
        encoding="ascii",
    )
    report["index_sha256"] = checksum
    report["built_at"] = built_at
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
