from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.universal_navigation_graph import (  # noqa: E402
    UniversalNavigationGraphRepository,
)


REVIEW_CONFIRMATION = "I_REVIEWED_THE_DESTINATION_AND_SAFETY"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert one independently reviewed navigation session into an "
            "app/version-scoped verified candidate. This never formally approves a route."
        )
    )
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--app-version",
        required=True,
        help="Independently checked installed version for a legacy session that omitted it.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / ".artifacts" / "universal-navigation.sqlite",
    )
    parser.add_argument(
        "--confirm-reviewed",
        required=True,
        choices=[REVIEW_CONFIRMATION],
        help="Explicitly confirms independent destination and safety review.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = UniversalNavigationGraphRepository(args.database.resolve())
    app_package, app_version, locale = repository.bind_session_missing_app_version(
        args.session_id,
        args.app_version,
    )
    repository.performance.apply_validation(
        session_id=args.session_id,
        destination_correct=True,
        safe_stop=True,
        unsafe_clicks=0,
        wrong_clicks=0,
        verification_level="human_gold",
    )
    route = repository.rebuild_verified_candidate_from_session(args.session_id)
    print(
        json.dumps(
            {
                "session_id": args.session_id,
                "app_package": app_package,
                "app_version": app_version,
                "locale": locale,
                "route_id": route.route_id,
                "lifecycle_status": route.lifecycle_status,
                "provisional": route.provisional,
                "target_function": route.target_function,
                "start_screen_fingerprint": route.start_screen_fingerprint,
                "destination_screen_fingerprint": route.destination_screen_fingerprint,
                "step_count": len(route.steps),
                "formal_approval_performed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
