from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_portable_backup import create_portable_backup  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a credential-free, checksum-verified portable ExitGuide Navigation backup."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--android-control-index", type=Path)
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        help="Optional external .artifacts directory (useful for immutable server releases).",
    )
    parser.add_argument("--source-commit", default="")
    args = parser.parse_args()
    report = create_portable_backup(
        root=args.root,
        output=args.output,
        database_path=args.database,
        android_control_index=args.android_control_index,
        artifacts_root=args.artifacts_root,
        source_commit=args.source_commit,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
