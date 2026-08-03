from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.navigation_contracts import DecideRequest, ScreenObservation  # noqa: E402
from app.navigation_main import get_navigation_runtime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay one recorded screen into an isolated runtime safety gate."
    )
    parser.add_argument("--source-runtime-db", type=Path, required=True)
    parser.add_argument("--source-decision-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--goal-text", default="멤버십 해지 메뉴를 찾아줘")
    parser.add_argument("--expected-action", default="stop_for_user")
    args = parser.parse_args()

    source_uri = f"file:{args.source_runtime_db.expanduser().resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as connection:
        row = connection.execute(
            """
            SELECT d.screen_payload_json, s.app_package, s.locale, s.app_version
            FROM navigation_decisions AS d
            JOIN navigation_sessions AS s USING(session_id)
            WHERE d.decision_id = ?
            """,
            (args.source_decision_id,),
        ).fetchone()
    if row is None:
        raise SystemExit(f"decision not found: {args.source_decision_id}")

    screen_payload, app_package, locale, app_version = row
    screen = ScreenObservation.model_validate(json.loads(screen_payload))
    response = get_navigation_runtime().decide(
        DecideRequest(
            request_id=args.request_id,
            app_package=app_package,
            locale=locale,
            app_version=app_version,
            goal_text=args.goal_text,
            screen=screen,
        )
    )
    result = {
        "source_decision_id": args.source_decision_id,
        "action": response.action.name,
        "candidate_id": response.action.candidate_id,
        "planner_provider": response.planner_provider,
        "safety_status": response.safety_status,
        "safety_reason": response.safety_reason,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if response.action.name != args.expected_action:
        raise SystemExit(
            f"expected {args.expected_action}, received {response.action.name}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
