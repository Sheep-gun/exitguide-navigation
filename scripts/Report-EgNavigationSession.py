from __future__ import annotations

"""Emit a sanitized, read-only report for one physical EG navigation run."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_session_report import (  # noqa: E402
    NavigationSessionReportError,
    build_navigation_session_report,
    capture_navigation_session_baseline,
)


DEFAULT_DATABASE = ROOT / ".artifacts" / "universal-navigation.sqlite"


def _non_negative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read one post-baseline physical EG session without exposing raw UI data."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="navigation SQLite path (opened with mode=ro)",
    )
    parser.add_argument(
        "--capture-baseline",
        action="store_true",
        help="print the current navigation_sessions rowid before starting a test",
    )
    parser.add_argument("--baseline-rowid", type=_non_negative_integer)
    parser.add_argument("--app-package")
    parser.add_argument("--session-id")
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit one-line JSON instead of indented JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.capture_baseline:
            if args.baseline_rowid is not None or args.app_package or args.session_id:
                parser.error(
                    "--capture-baseline cannot be combined with session selection arguments"
                )
            payload: dict[str, object] = {
                "report_version": 1,
                "baseline_navigation_session_rowid": capture_navigation_session_baseline(
                    args.database
                ),
            }
        else:
            if args.baseline_rowid is None or not args.app_package:
                parser.error(
                    "--baseline-rowid and --app-package are required for a session report"
                )
            payload = build_navigation_session_report(
                args.database,
                baseline_rowid=args.baseline_rowid,
                app_package=args.app_package,
                session_id=args.session_id,
            )
    except NavigationSessionReportError as exc:
        print(
            json.dumps(
                {"report_version": 1, "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
