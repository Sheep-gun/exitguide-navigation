#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix)
    if content_type is None:
        raise ValueError("screenshot must be png, jpeg, or webp")
    return f"data:{content_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _screen() -> dict[str, object]:
    return {
        "window_title": "Account",
        "activity_name": "android.view.View",
        "navigation_depth": 0,
        "candidates": [
            {
                "candidate_id": "profile",
                "label": "Profile",
                "role": "button",
                "risk_level": "low",
                "icon_semantics": "person",
                "nearby_text": "Account and personal settings",
                "parent_semantics": "Account",
                "position_bucket": "middle",
            },
            {
                "candidate_id": "settings",
                "label": "Settings",
                "role": "button",
                "risk_level": "low",
                "icon_semantics": "gear",
                "nearby_text": "Notifications and privacy",
                "parent_semantics": "Account",
                "position_bucket": "middle",
            },
            {
                "candidate_id": "membership",
                "label": "Membership",
                "role": "button",
                "risk_level": "low",
                "icon_semantics": "card",
                "nearby_text": "Plan and billing",
                "parent_semantics": "Account",
                "position_bucket": "bottom",
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one live Navigation API decision and observation.")
    parser.add_argument("--decision-db", type=Path, required=True)
    parser.add_argument("--runtime-db", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--goal", default="회원 탈퇴 메뉴를 찾고 싶어")
    parser.add_argument("--expected-candidate", default="")
    args = parser.parse_args()

    os.environ["NAVIGATION_DECISION_DB_PATH"] = str(args.decision_db.resolve())
    os.environ["NAVIGATION_RUNTIME_DB_PATH"] = str(args.runtime_db.resolve())

    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app import navigation_main

    get_settings.cache_clear()
    navigation_main.get_navigation_runtime.cache_clear()
    result: dict[str, object] = {
        "status_ready": False,
        "research_models_ready": False,
        "decide_success": False,
        "observe_success": False,
        "candidate_id_constraint_preserved": False,
        "dangerous_action_executed": False,
    }
    try:
        with TestClient(navigation_main.app) as client:
            status = client.get("/v1/navigation/status")
            status_payload = status.json()
            result["status_ready"] = status.status_code == 200 and status_payload.get("ready") is True
            result["research_models_ready"] = status_payload.get("research_models_ready") is True

            screenshot = _data_url(args.screenshot.resolve())
            screen = _screen()
            started = time.perf_counter()
            decision_response = client.post(
                "/v1/navigation/decide",
                json={
                    "request_id": str(uuid.uuid4()),
                    "app_package": "privacy.safe.synthetic.app",
                    "locale": "ko-KR",
                    "goal_text": args.goal,
                    "step_ordinal": 0,
                    "screenshot_data_url": screenshot,
                    "screen": screen,
                },
                timeout=240,
            )
            result["decide_latency_ms"] = round((time.perf_counter() - started) * 1000)
            if decision_response.status_code != 200:
                result["decide_http_status"] = decision_response.status_code
                print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
                return 1

            decision = decision_response.json()
            action = decision["action"]
            allowed_ids = {item["candidate_id"] for item in screen["candidates"]}
            result.update(
                {
                    "decide_success": True,
                    "action_name": action["name"],
                    "candidate_id_constraint_preserved": action["name"] != "click"
                    or action.get("candidate_id") in allowed_ids,
                    "expected_candidate_matched": not args.expected_candidate
                    or (
                        action["name"] == "click"
                        and action.get("candidate_id") == args.expected_candidate
                    ),
                    "dangerous_action_executed": action["name"] not in {
                        "click",
                        "scroll",
                        "back",
                        "wait_and_observe",
                        "stop_for_user",
                    },
                    "perception_provider": decision["perception_provider"],
                    "planner_provider": decision["planner_provider"],
                    "verifier_provider": decision["verifier_provider"],
                    "safety_status": decision["safety_status"],
                }
            )

            started = time.perf_counter()
            observation_response = client.post(
                "/v1/navigation/observe",
                json={
                    "request_id": str(uuid.uuid4()),
                    "decision_id": decision["decision_id"],
                    "connectivity_status": "observed",
                    "observed_signal": "none",
                    "execution_succeeded": True,
                    "before_screenshot_data_url": screenshot,
                    "after_screenshot_data_url": screenshot,
                    "next_screen": screen,
                },
                timeout=120,
            )
            result["observe_latency_ms"] = round((time.perf_counter() - started) * 1000)
            if observation_response.status_code == 200:
                observation = observation_response.json()
                result.update(
                    {
                        "observe_success": True,
                        "outcome_type": observation["outcome_type"],
                        "reflection_level": observation["reflection_level"],
                        "transport_failure_conflated": observation["connectivity_status"] != "observed",
                    }
                )
            else:
                result["observe_http_status"] = observation_response.status_code
    except Exception as error:  # never emit model response bodies or credentials
        result["error_type"] = type(error).__name__
    finally:
        navigation_main.get_navigation_runtime.cache_clear()
        get_settings.cache_clear()

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    passed = (
        result["status_ready"]
        and result["research_models_ready"]
        and result["decide_success"]
        and result["observe_success"]
        and result["candidate_id_constraint_preserved"]
        and result.get("expected_candidate_matched", False)
        and not result["dangerous_action_executed"]
        and not result.get("transport_failure_conflated", True)
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
