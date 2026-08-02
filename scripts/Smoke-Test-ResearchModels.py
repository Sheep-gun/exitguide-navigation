#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import Settings  # noqa: E402
from app.navigation_contracts import NavigationCandidate, ScreenObservation  # noqa: E402
from app.services.navigation_model_clients import (  # noqa: E402
    Exaone45VisionClient,
    NavigationPlannerResearchClient,
    OpenAICompatibleChatClient,
)


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


def _clients(settings: Settings) -> tuple[NavigationPlannerResearchClient, Exaone45VisionClient]:
    planner_model = NavigationPlannerResearchClient(
        OpenAICompatibleChatClient(
            api_key=settings.navigation_planner_api_key,
            base_url=settings.navigation_planner_base_url,
            model=settings.navigation_planner_model,
            timeout_seconds=settings.navigation_planner_timeout_seconds,
        ),
        provider_name=settings.navigation_planner_provider,
    )
    exaone_vlm = Exaone45VisionClient(
        OpenAICompatibleChatClient(
            api_key=settings.exaone_vlm_api_key,
            base_url=settings.exaone_vlm_base_url,
            model=settings.exaone_vlm_model,
            team=settings.exaone_vlm_team,
            timeout_seconds=settings.exaone_vlm_timeout_seconds,
            chat_template_kwargs={"enable_thinking": False},
        )
    )
    return planner_model, exaone_vlm


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a privacy-safe live smoke against Solar Pro 3 and EXAONE 4.5."
    )
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()

    settings = Settings()
    planner_model, exaone_vlm = _clients(settings)
    result: dict[str, object] = {
        "planner_model_provider": planner_model.name,
        "planner_model_configured": planner_model.configured,
        "exaone_4_5_configured": exaone_vlm.configured,
        "planner_model_success": False,
        "exaone_4_5_success": False,
    }

    screen = ScreenObservation(
        window_title="Account",
        activity_name="android.view.View",
        navigation_depth=0,
        candidates=[
            NavigationCandidate(
                candidate_id="profile",
                label="Profile",
                role="button",
                nearby_text="Account and personal settings",
                position_bucket="middle",
            ),
            NavigationCandidate(
                candidate_id="settings",
                label="Settings",
                role="button",
                nearby_text="Notifications and privacy",
                position_bucket="middle",
            ),
            NavigationCandidate(
                candidate_id="membership",
                label="Membership",
                role="button",
                nearby_text="Plan and billing",
                position_bucket="bottom",
            ),
        ],
    )

    try:
        started = time.perf_counter()
        perception = exaone_vlm.perceive(
            goal_text="멤버십 관리 화면을 찾고 싶어",
            screen=screen,
            screenshot_data_url=_data_url(args.screenshot.resolve()),
        )
        output_ids = {candidate.candidate_id for candidate in perception.screen.candidates}
        expected_ids = {candidate.candidate_id for candidate in screen.candidates}
        result.update(
            {
                "exaone_4_5_success": perception.provider == "exaone_4_5"
                and output_ids == expected_ids,
                "exaone_4_5_candidate_ids_preserved": output_ids == expected_ids,
                "exaone_4_5_latency_ms": round((time.perf_counter() - started) * 1000),
            }
        )
    except Exception as error:  # smoke output deliberately excludes response bodies
        result["exaone_4_5_error_type"] = type(error).__name__

    try:
        started = time.perf_counter()
        plan = planner_model.plan(
            goal={
                "goal_id": "subscription.manage",
                "canonical_name": "멤버십 관리",
                "normalized_conditions": [],
            },
            screen=screen.model_dump(mode="json"),
            destination_signatures=[
                {
                    "signature_id": "membership_management",
                    "required_semantics": ["membership", "plan", "billing"],
                }
            ],
            decision_evidence=[],
            recent_history=[],
            target_roles=["membership_hub", "account_hub"],
        )
        verification = planner_model.verify_action(
            goal={"goal_id": "subscription.manage", "canonical_name": "멤버십 관리"},
            subgoal=plan.immediate_subgoal,
            expected_outcome=plan.expected_outcome,
            screen=screen.model_dump(mode="json"),
            recent_history=[],
            action={
                "name": "click",
                "candidate_id": "membership",
                "candidate": screen.candidates[2].model_dump(mode="json"),
            },
            memory_prior=0.75,
            decision_evidence=[],
        )
        result.update(
            {
                "planner_model_success": bool(plan.immediate_subgoal)
                and 0.0 <= verification.helpful_probability <= 1.0,
                "planner_model_stage": plan.stage,
                "planner_model_verifier_bounded": 0.0
                <= verification.helpful_probability
                <= 1.0,
                "planner_model_latency_ms": round((time.perf_counter() - started) * 1000),
            }
        )
    except Exception as error:  # smoke output deliberately excludes response bodies
        result["planner_model_error_type"] = type(error).__name__

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["planner_model_success"] and result["exaone_4_5_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
