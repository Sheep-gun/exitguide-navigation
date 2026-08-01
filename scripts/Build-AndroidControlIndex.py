from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.android_control_import import iter_official_tfrecords  # noqa: E402
from app.services.android_control_index import (  # noqa: E402
    AndroidControlIndex,
    read_normalized_jsonl,
    write_normalized_jsonl,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a compact ExitGuide retrieval index from AndroidControl demonstrations."
    )
    parser.add_argument("--input", nargs="+", required=True, help="JSONL file(s), TFRecord shard(s), or directories")
    parser.add_argument(
        "--format",
        choices=("normalized-jsonl", "official-tfrecord"),
        default="normalized-jsonl",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / ".artifacts" / "android-control" / "navigation-examples.sqlite"),
    )
    parser.add_argument("--normalized-output", default="")
    parser.add_argument("--source-split", default="")
    parser.add_argument("--episode-limit", type=int, default=None)
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args()

    paths = _expand_paths(args.input, args.format)
    if args.format == "official-tfrecord":
        records = iter_official_tfrecords(
            paths,
            source_split=args.source_split,
            episode_limit=args.episode_limit,
        )
    else:
        records = itertools.chain.from_iterable(read_normalized_jsonl(path) for path in paths)

    if args.normalized_output:
        normalized_path = Path(args.normalized_output)
        normalized_count = write_normalized_jsonl(records, normalized_path)
        print(f"normalized AndroidControl records: {normalized_count} -> {normalized_path}")
        records = read_normalized_jsonl(normalized_path)

    index = AndroidControlIndex(args.output)
    count = index.build(records, replace=not args.append)
    print(f"AndroidControl retrieval index: {count} records -> {index.database_path}")


def _expand_paths(raw_paths: list[str], format_name: str) -> list[Path]:
    paths: list[Path] = []
    pattern = "android_control-*" if format_name == "official-tfrecord" else "*.jsonl"
    for raw_path in raw_paths:
        path = Path(raw_path).expanduser()
        if path.is_dir():
            paths.extend(sorted(candidate for candidate in path.glob(pattern) if candidate.is_file()))
        elif path.is_file():
            paths.append(path)
        else:
            raise SystemExit(f"AndroidControl input does not exist: {path}")
    if not paths:
        raise SystemExit("No AndroidControl input files matched")
    return paths


if __name__ == "__main__":
    main()
