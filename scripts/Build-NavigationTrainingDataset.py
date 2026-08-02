#!/usr/bin/env python3
"""Materialize reviewed Navigation decisions and export SFT/preference JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_training_examples import (  # noqa: E402
    materialize_human_gold_examples,
    write_training_artifacts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--split-override",
        action="append",
        default=[],
        metavar="PACKAGE=SPLIT",
        help="Keep all examples from PACKAGE in train, validation, or test.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    overrides: dict[str, str] = {}
    for value in args.split_override:
        package, separator, split = value.partition("=")
        if not separator or not package.strip() or not split.strip():
            raise SystemExit(f"invalid --split-override: {value}")
        overrides[package.strip()] = split.strip()
    examples = materialize_human_gold_examples(
        args.database.resolve(),
        split_overrides=overrides,
    )
    manifest = write_training_artifacts(examples, args.output.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
