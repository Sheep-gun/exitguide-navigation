from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_portable_backup import (  # noqa: E402
    restore_portable_backup,
    verify_portable_backup,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify or restore an ExitGuide Navigation portable backup."
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.destination is None:
        report = verify_portable_backup(args.archive)
    else:
        report = restore_portable_backup(
            archive_path=args.archive,
            destination=args.destination,
            force=args.force,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
