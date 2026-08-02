from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_learning_queue import (  # noqa: E402
    materialize_runtime_learning_queue,
    write_runtime_learning_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build privacy-redacted Navigation Agent runtime feedback artifacts."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    examples = materialize_runtime_learning_queue(args.database)
    manifest = write_runtime_learning_artifacts(examples, args.output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
