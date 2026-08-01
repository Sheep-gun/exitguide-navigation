from __future__ import annotations

"""Export a privacy-safe semantic fixture from explicit live-session rows."""

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_semantic_fixture_exporter import (  # noqa: E402
    IndependentDestinationAnnotation,
    SemanticFixtureExportError,
    export_navigation_semantic_fixture,
)


DEFAULT_DATABASE = ROOT / ".artifacts" / "universal-navigation.sqlite"
DEFAULT_OUTPUT = (
    ROOT
    / ".artifacts"
    / "navigation-semantic-fixtures"
    / "baemin-notification-settings.shadow-candidate.json"
)


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project selected physical navigation sessions into a strict, "
            "privacy-safe semantic shadow fixture."
        )
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--session-rowid",
        type=_positive_integer,
        action="append",
        required=True,
        help="explicit navigation_sessions.rowid selector; repeat as needed",
    )
    parser.add_argument(
        "--false-positive-session-rowid",
        type=_positive_integer,
        action="append",
        default=[],
        help="selected runtime result known to have reached the wrong surface",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--verified-session-rowid",
        type=_positive_integer,
        help="session independently confirmed at the destination",
    )
    parser.add_argument(
        "--verification-method",
        choices=(
            "human_on_device",
            "independent_device_replay",
            "independent_test_harness",
        ),
    )
    parser.add_argument(
        "--destination-semantic",
        choices=("notification_preferences",),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    annotation_flags = (
        args.verified_session_rowid,
        args.verification_method,
        args.destination_semantic,
    )
    if any(value is not None for value in annotation_flags) and not all(
        value is not None for value in annotation_flags
    ):
        parser.error(
            "independent destination annotation requires rowid, method, and semantic"
        )
    annotations = ()
    if args.verified_session_rowid is not None:
        annotations = (
            IndependentDestinationAnnotation(
                source_session_rowid=args.verified_session_rowid,
                target_function="notification.settings",
                destination_semantic=args.destination_semantic,
                verification_method=args.verification_method,
            ),
        )

    try:
        result = export_navigation_semantic_fixture(
            args.database,
            session_rowids=args.session_rowid,
            output_path=args.output,
            false_positive_session_rowids=args.false_positive_session_rowid,
            independent_destination_annotations=annotations,
        )
    except SemanticFixtureExportError as exc:
        print(
            json.dumps(
                {"schema_version": 1, "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    serialized = json.dumps(result.fixture, ensure_ascii=False, sort_keys=True).encode(
        "utf-8"
    )
    print(
        json.dumps(
            {
                "schema_version": 1,
                "exported": True,
                "source_hash_unchanged": result.source_hash_unchanged,
                "fixture_sha256": hashlib.sha256(serialized).hexdigest(),
                "session_count": len(result.fixture["sessions"]),
                "screen_count": len(result.fixture["screens"]),
                "action_count": len(result.fixture["actions"]),
                "positive_promotion_eligible": result.fixture["promotion_gate"][
                    "positive_promotion_eligible"
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
