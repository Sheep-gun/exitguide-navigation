#!/usr/bin/env python3
"""Explicitly promote or reject one completed real-device demonstration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.universal_navigation_graph import UniversalNavigationGraphRepository  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--recording-id", required=True)
    parser.add_argument("--decision", choices=("human_gold", "rejected"), required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--confirm",
        required=True,
        help="Must be I_REVIEWED_THE_DESTINATION to prevent accidental promotion.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.confirm != "I_REVIEWED_THE_DESTINATION":
        raise SystemExit("Refusing review: pass --confirm I_REVIEWED_THE_DESTINATION")
    repository = UniversalNavigationGraphRepository(args.database.resolve())
    result = repository.review_gold_recording(
        args.recording_id,
        decision=args.decision,
        reviewer=args.reviewer,
        notes=args.notes or None,
    )
    print(
        f"{result['recording_id']} -> {result['status']} "
        f"steps={result['step_count']} selected={result['selected_step_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
