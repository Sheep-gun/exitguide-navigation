import os
from typing import Any

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8010"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def get_json(client: httpx.Client, path: str) -> Any:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def post_json(client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=payload)
    response.raise_for_status()
    return response.json()


def main() -> None:
    base_url = os.environ.get("EXITGUIDE_TEST_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        health = get_json(client, "/health")
        expect(health["status"] == "ok", "health endpoint should return ok")

        readiness = get_json(client, "/v1/readiness")
        expect(readiness["status"] == "ready", "readiness should be ready")
        expect(all(check["passed"] for check in readiness["checks"]), "all readiness checks should pass")

        providers = get_json(client, "/v1/providers")
        provider_ids = {provider["id"] for provider in providers}
        expect({"server", "google", "gpt", "exaone"}.issubset(provider_ids), "provider catalog should include server, google, gpt, and exaone")

        quality = get_json(client, "/v1/demo-quality")
        expect(quality["status"] == "pass", "demo quality should pass")
        expect(quality["summary"]["scenarios_passed"] == 10, "ten demo scenarios should pass")
        expect(quality["summary"]["flows_passed"] == 4, "four demo flows should pass")
        expect(quality["summary"]["synthetic_passed"] == 15, "fifteen synthetic screens should pass")

        scenarios = get_json(client, "/v1/demo-scenarios")
        expect(len(scenarios) == 10, "demo scenario catalog should contain ten scenarios")

        synthetic_catalog = get_json(client, "/v1/synthetic-screens")
        screens = synthetic_catalog["screens"]
        expect(synthetic_catalog["screen_count"] == 15, "synthetic catalog screen_count should be fifteen")
        expect(len(screens) == 15, "synthetic catalog should return fifteen screen entries")

        demo = post_json(
            client,
            "/v1/analyze/demo",
            {"goal_id": "buy_without_addons", "scenario_id": "checkout_addons"},
        )
        expect(demo["analysis_id"].startswith("an_"), "demo analysis should return a stable analysis id")
        expect(demo["analysis_mode"] == "demo", "demo analysis should report demo mode")
        expect(demo["overall_risk"] == "high", "checkout add-on demo should be high risk")
        expect(demo["risk_counts"]["high"] >= 1, "checkout add-on demo should contain high-risk signals")

        custom_goal_demo = post_json(
            client,
            "/v1/analyze/demo",
            {"goal_text": "추가 결제 없이 가입하고 싶어요", "scenario_id": "checkout_addons"},
        )
        expect(custom_goal_demo["goal_id"] == "custom_goal", "custom goal text should be accepted")
        expect(custom_goal_demo["overall_risk"] == "high", "custom checkout goal should still catch add-ons")

        prompt = post_json(
            client,
            "/v1/prompt/demo",
            {"goal_id": "buy_without_addons", "scenario_id": "checkout_addons"},
        )
        expect("output_schema" in prompt["user_prompt"], "prompt preview should include output schema")

        flow = post_json(
            client,
            "/v1/analyze/flow",
            {"goal_id": "buy_without_addons", "scenario_ids": ["checkout_addons", "checkout_clean"]},
        )
        expect(flow["flow_id"].startswith("fl_"), "flow analysis should return a stable flow id")
        expect(flow["screen_count"] == 2, "flow analysis should include two screens")
        expect(flow["highest_risk_screen_number"] == 1, "highest risk screen should be the first screen")
        expect(flow["risk_path"] == ["high", "low"], "checkout flow risk path should be high then low")

        upload_fixture = next(screen for screen in screens if screen["filename"] == "checkout-preselected-addon.png")
        upload_response = client.post(
            "/v1/analyze",
            data={"goal_id": upload_fixture["recommended_goal_id"]},
            files={"screenshot": (upload_fixture["filename"], b"fake", "image/png")},
        )
        upload_response.raise_for_status()
        upload = upload_response.json()
        expect(upload["analysis_id"].startswith("an_"), "upload analysis should return a stable analysis id")
        expect(upload["analysis_mode"] == "upload", "upload analysis should report upload mode")
        expect(upload["overall_risk"] == upload_fixture["risk_fixture"], "upload risk should match fixture")

    print("live test environment checks ok")


if __name__ == "__main__":
    main()
