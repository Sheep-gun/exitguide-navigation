from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_offline_replay import (  # noqa: E402
    REQUIRED_MUTATION_IDS,
    assert_offline_replay_quality_gate,
    build_offline_replay_scenarios,
    evaluate_offline_replay_fixture,
    load_offline_replay_fixture,
)


FIXTURE = (
    ROOT
    / "fixtures"
    / "navigation"
    / "offline"
    / "baemin-notification-settings.synthetic.v1.json"
)
CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"


def main() -> None:
    payload = load_offline_replay_fixture(FIXTURE)
    scenarios = build_offline_replay_scenarios(payload)
    assert scenarios[0].scenario_id == "unmutated"
    assert scenarios[0].goal_text == "배달의민족 알림 설정을 열고 싶어"
    assert len(scenarios) >= 21
    assert any("unlabeled" in scenario.tags for scenario in scenarios)
    assert any("modal" in scenario.tags for scenario in scenarios)
    assert any("stale" in scenario.tags for scenario in scenarios)
    assert any("route_reuse" in scenario.tags for scenario in scenarios)
    assert {
        scenario.scenario_id for scenario in scenarios if scenario.scenario_id != "unmutated"
    } >= REQUIRED_MUTATION_IDS

    unlabeled_scenarios = [
        scenario
        for scenario in scenarios
        if scenario.scenario_id
        in {"unlabeled-gear-single", "unlabeled-gear-multiple-siblings"}
    ]
    assert len(unlabeled_scenarios) == 2
    forbidden_semantic_id_fragments = {
        "setting",
        "gear",
        "help",
        "notification",
        "alarm",
        "config",
    }
    for scenario in unlabeled_scenarios:
        anonymous_clickables = [
            element
            for element in scenario.screens["account_hub"]["elements"]
            if element.get("clickable")
            and not element.get("text")
            and not element.get("content_description")
            and not element.get("view_id")
        ]
        assert anonymous_clickables
        assert all(
            not any(
                fragment in str(element.get("id", "")).casefold()
                for fragment in forbidden_semantic_id_fragments
            )
            for element in anonymous_clickables
        )

    serialized_fixture = json.dumps(payload, ensure_ascii=False).casefold()
    assert "@" not in serialized_fixture
    assert "raw_screenshot" not in serialized_fixture
    assert "raw_xml" not in serialized_fixture
    assert payload["provenance"]["captured_gold"] is False
    assert payload["provenance"]["destination_provenance"] == "expected_semantic_target"

    report = evaluate_offline_replay_fixture(
        fixture_path=FIXTURE,
        catalog_path=CATALOG,
    )
    assert report["evaluation_policy"]["production_entrypoint"] == (
        "observe_universal_navigation"
    )
    assert report["evaluation_policy"]["single_shared_catalog"] is True
    assert report["evaluation_policy"]["single_shared_repository"] is True
    assert report["evaluation_policy"]["external_network_used"] is False
    assert report["evaluation_policy"]["device_used"] is False
    assert report["evaluation_policy"]["stale_seed_validation_scope"] == (
        "synthetic_lifecycle_setup_only"
    )
    assert report["summary"]["unsafe_auto_click_count"] == 0
    assert report["summary"]["final_auto_click_count"] == 0
    assert report["summary"]["wrong_destination_count"] == 0
    assert report["summary"]["wrong_guidance_count"] == 0
    assert report["summary"]["unbounded_scenario_count"] == 0
    assert report["quality_gate"]["checks"][
        "multiple_unlabeled_sibling_keys_preserved"
    ] is True
    assert report["quality_gate"]["checks"][
        "stale_route_was_used_then_invalidated"
    ] is True
    assert report["quality_gate"]["checks"][
        "stale_route_invalidated_within_two_observations"
    ] is True
    assert report["quality_gate"]["checks"]["verified_route_reuse_100"] is True
    assert report["quality_gate"]["checks"][
        "verified_route_reuse_within_15_seconds"
    ] is True
    assert report["quality_gate"]["checks"][
        "verified_route_reuse_within_two_clicks"
    ] is True
    assert report["quality_gate"]["checks"][
        "verified_route_reuse_no_scroll_or_back"
    ] is True
    assert report["quality_gate"]["checks"][
        "stale_route_falls_back_to_exploration"
    ] is True
    assert report["quality_gate"]["checks"][
        "version_mismatch_skips_verified_route"
    ] is True
    assert_offline_replay_quality_gate(report)
    print("navigation_offline_replay_unit: ok")


if __name__ == "__main__":
    main()
