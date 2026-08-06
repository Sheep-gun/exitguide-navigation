from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any


def read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def candidate_inventory(
    runtime: sqlite3.Connection,
    decision_id: str,
) -> list[str]:
    decision = runtime.execute(
        "SELECT 1 FROM navigation_decisions WHERE decision_id=?",
        (decision_id,),
    ).fetchone()
    if decision is None:
        raise ValueError(f"review manifest references an absent decision: {decision_id}")
    rows = runtime.execute(
        """
        SELECT sc.candidate_id
        FROM navigation_screen_snapshots AS ss
        JOIN navigation_screen_candidates AS sc ON sc.snapshot_id=ss.snapshot_id
        WHERE ss.decision_id=? AND ss.phase='before'
        ORDER BY sc.ordinal
        """,
        (decision_id,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def apply_manifest(args: argparse.Namespace) -> dict[str, Any]:
    api_root = args.api_root.resolve()
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))
    from app.services.navigation_review import (  # noqa: PLC0415
        CandidateTrainingLabelRequest,
        NavigationCandidateLabelsRequest,
        NavigationHumanReviewRequest,
        NavigationReviewStore,
    )

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    reviewer = str(payload["reviewer"])
    label_source = str(payload.get("label_source") or "codex")
    review_status = str(payload.get("review_status") or "verified")
    records = list(payload.get("decisions", []))
    if not records:
        raise ValueError("review manifest has no decisions")
    store = NavigationReviewStore(args.runtime_db, args.review_db)
    reviewed = 0
    labeled = 0
    with closing(read_only(args.runtime_db)) as runtime:
        for record in records:
            decision_id = str(record["decision_id"])
            inventory = candidate_inventory(runtime, decision_id)
            overrides = dict(record.get("candidate_overrides", {}))
            unknown = sorted(set(overrides) - set(inventory))
            if unknown:
                raise ValueError(
                    f"candidate overrides are absent from {decision_id}: {unknown}"
                )
            default = record.get("default_candidate_label")
            if inventory and not isinstance(default, dict):
                raise ValueError(
                    f"candidate-bearing decision lacks default label: {decision_id}"
                )
            human_payload = {"reviewer": reviewer, **dict(record["human_review"])}
            store.save_review(
                decision_id,
                NavigationHumanReviewRequest.model_validate(human_payload),
            )
            reviewed += 1
            if inventory:
                labels = []
                for candidate_id in inventory:
                    item = {**default, **dict(overrides.get(candidate_id, {}))}
                    labels.append(
                        CandidateTrainingLabelRequest.model_validate(
                            {"candidate_id": candidate_id, **item}
                        )
                    )
                store.save_candidate_labels(
                    decision_id,
                    NavigationCandidateLabelsRequest(
                        reviewer=reviewer,
                        label_source=label_source,
                        review_status=review_status,
                        labels=labels,
                    ),
                )
                labeled += len(labels)
    return {
        "schema_version": "navigation-review-manifest-application.v1",
        "runtime_db": str(args.runtime_db.resolve()),
        "review_db": str(args.review_db.resolve()),
        "manifest": str(args.input.resolve()),
        "reviewer": reviewer,
        "reviewed_decisions": reviewed,
        "candidate_labels": labeled,
        "runtime_source_read_only": True,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Apply a Codex-reviewed manifest while keeping Runtime DB read-only"
    )
    result.add_argument("--runtime-db", type=Path, required=True)
    result.add_argument("--review-db", type=Path, required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument(
        "--api-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "apps" / "api",
    )
    return result


if __name__ == "__main__":
    print(
        json.dumps(
            apply_manifest(parser().parse_args()),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
