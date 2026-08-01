import importlib.util
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_independent_coverage import audit_independent_coverage


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
GYM_ROOT = ROOT / "fixtures" / "navigation" / "db-gym"


def _load_authority_adapter():
    adapter_path = ROOT / "scripts" / "Normalize-NavigationAuthorityFixture.py"
    spec = importlib.util.spec_from_file_location(
        "navigation_authority_fixture_adapter", adapter_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load authority fixture adapter: {adapter_path}")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter


def _normalized_v14_payload(
    *,
    fixture: dict[str, object],
    catalog: dict[str, object],
) -> dict[str, object]:
    terminal_intents = {
        str(item["terminal_function"]): str(item["intent_id"])
        for item in catalog["intents"]
    }
    surfaces = ("screen", "dialog", "drawer", "bottom_sheet", "webview", "scroll_view", "endless_feed", "system_dialog")
    states = ("ready", "loading", "offline", "error", "relogin_required", "permission_rationale", "stale_cache", "transient_error", "recovered", "confirmation_required", "repeated_content")
    cases = []
    for index, case in enumerate(fixture["cases"]):
        route_id = str(case["expected"]["route_id"])
        hub_case = route_id.endswith(".hub")
        cases.append(
            {
                "case_id": str(case["case_id"]),
                "intent_id": "__abstain__" if hub_case else terminal_intents[route_id],
                "goal_text": str(case["goal"]),
                "locale": "ko-KR" if case.get("locale") == "ko" else "en-US",
                "tuning_allowed": False,
                "steps": [
                    {
                        "ui_surface": surfaces[index % len(surfaces)],
                        "screen_state": states[index % len(states)],
                        "elements": [
                            {
                                "label": str(case["ui"]["decoys"][0]),
                                "enabled": index % 7 != 0,
                                "visible": index % 11 != 0,
                                "selected": index % 13 == 0,
                                "checkable": index % 17 == 0,
                                "scrollable": index % 19 == 0,
                                "dangerous": index % 5 == 0,
                            },
                            {
                                "label": "",
                                "content_description": str(case["ui"]["decoys"][1]),
                            },
                        ],
                        "expected": {
                            "action": "no_click" if hub_case else "stop",
                            "function_id": route_id,
                        },
                    }
                ],
            }
        )
    return {
        "split": "independent_institutional_systems_v14",
        "frozen": True,
        "catalog_derived": False,
        "tuning_allowed": False,
        "cases": cases,
    }


def main() -> None:
    fixture_paths = [
        GYM_ROOT / "public-web.v1.json",
        GYM_ROOT / "public-insurance.v1.json",
        GYM_ROOT / "public-productivity-system.v1.json",
        GYM_ROOT / "independent-core.v2.json",
        GYM_ROOT / "alias-collision-adversarial.v2.json",
        GYM_ROOT / "independent-coverage.v2.json",
        GYM_ROOT / "independent-recovery.v2.json",
        GYM_ROOT / "independent-long-tail-v3.json",
        GYM_ROOT / "independent-broad-services-v4.json",
        GYM_ROOT / "independent-service-gaps-v5.json",
        GYM_ROOT / "independent-open-world-v6.json",
        GYM_ROOT / "independent-long-tail-v7.json",
        GYM_ROOT / "independent-enterprise-ops-v8.json",
        GYM_ROOT / "independent-cross-domain-v9.json",
        GYM_ROOT / "independent-operational-v10.json",
        GYM_ROOT / "independent-critical-ops-v11.json",
        GYM_ROOT / "independent-specialized-ops-v12.json",
        GYM_ROOT / "independent-regulated-systems-v13.json",
    ]
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert catalog["catalog_version"] == "15.0.0"
    assert len(catalog["intents"]) == 2660
    assert len(catalog["functions"]) == 2866
    v14_fixture = json.loads(
        (GYM_ROOT / "independent-institutional-systems-v14.json").read_text(
            encoding="utf-8"
        )
    )
    v15_fixture = json.loads(
        (GYM_ROOT / "independent-authority-systems-v15.json").read_text(
            encoding="utf-8"
        )
    )
    authority_adapter = _load_authority_adapter()
    normalized_v15 = authority_adapter.normalize_stateful_fixture(
        source=v15_fixture,
        catalog=catalog,
    )
    normalized_v15_cases = list(normalized_v15["cases"])
    assert normalized_v15["split"] == "independent_authority_systems_v15"
    assert normalized_v15["projection_contract"] == {
        "case_count": 960,
        "step_count": 960,
        "stop_count": 840,
        "no_click_count": 120,
        "zero_dangerous_clicks": 960,
        "zero_automated_final_presses": 960,
        "disposition_counts": {"route": 600, "retain_prior": 240, "abstain": 120},
        "source_stop_policy_counts": {"before_action": 600, "navigation_only": 360},
        "terminal_press_owner_user_count": 960,
    }
    assert len(normalized_v15_cases) == 960
    assert sum(len(case["steps"]) for case in normalized_v15_cases) == 960
    assert Counter(
        step["expected"]["action"]
        for case in normalized_v15_cases
        for step in case["steps"]
    ) == {"stop": 840, "no_click": 120}
    assert all(
        (case["intent_id"] == "__abstain__")
        == (case["steps"][0]["expected"]["action"] == "no_click")
        for case in normalized_v15_cases
    )
    assert all(
        step["expected"]["dangerous_clicks"] == 0
        and step["expected"]["automated_final_presses"] == 0
        and step["expected"]["terminal_press_owner"] == "user"
        for case in normalized_v15_cases
        for step in case["steps"]
    )
    normalized_v15_goals = authority_adapter.normalize_goal_fixture(
        source=v15_fixture,
        catalog=catalog,
    )
    assert normalized_v15_goals["projection_contract"] == {
        "source_case_count": 960,
        "routable_case_count": 840,
        "excluded_abstention_count": 120,
    }
    assert len(normalized_v15_goals["cases"]) == 840
    assert 3565 + len(normalized_v15_goals["cases"]) == 4405
    with TemporaryDirectory() as normalized_directory:
        normalized_v14_path = (
            Path(normalized_directory) / "independent-institutional-systems-v14.json"
        )
        normalized_v14_path.write_text(
            json.dumps(
                _normalized_v14_payload(fixture=v14_fixture, catalog=catalog),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        normalized_v15_path = (
            Path(normalized_directory) / "independent-authority-systems-v15.json"
        )
        normalized_v15_path.write_text(
            json.dumps(normalized_v15, ensure_ascii=False),
            encoding="utf-8",
        )
        report = audit_independent_coverage(
            catalog_path=CATALOG_PATH,
            fixture_paths=[*fixture_paths, normalized_v14_path, normalized_v15_path],
        )
    assert report["status"] == "pass", report["errors"][:5]
    assert report["intent_coverage"] == 1.0
    assert report["function_coverage"] == 1.0
    assert report["case_count"] == 4645
    assert report["step_count"] == 12007
    assert report["intent_covered"] == 2660
    assert report["function_covered"] == 2866
    fixture_counts = {
        item["split"]: item["case_count"] for item in report["fixtures"]
    }
    assert fixture_counts["independent_institutional_systems_v14"] == 960
    assert fixture_counts["independent_authority_systems_v15"] == 960
    assert report["action_counts"]["click"] > 0
    assert report["action_counts"]["stop"] > 0
    assert report["action_counts"]["no_click"] > 0
    assert {"ko-KR", "en-US"} <= set(report["locale_counts"])
    assert {"screen", "dialog", "drawer", "bottom_sheet", "webview", "scroll_view", "endless_feed", "system_dialog"} <= set(report["ui_surface_counts"])
    assert {"ready", "loading", "offline", "error", "relogin_required", "permission_rationale", "stale_cache", "transient_error", "recovered", "confirmation_required", "repeated_content"} <= set(report["screen_state_counts"])
    assert {"disabled", "invisible", "selected", "checkable", "scrollable", "icon_only", "dangerous"} <= set(report["element_state_counts"])

    with TemporaryDirectory() as temporary_directory:
        broken_path = Path(temporary_directory) / "broken-independent.json"
        broken_path.write_text(
            json.dumps(
                {
                    "split": "broken",
                    "frozen": True,
                    "catalog_derived": False,
                    "cases": [
                        {
                            "case_id": "broken-case",
                            "intent_id": "not.a.real.intent",
                            "goal_text": "broken",
                            "steps": [
                                {
                                    "expected": {
                                        "action": "click",
                                        "function_id": "not.a.real.function",
                                    }
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        broken = audit_independent_coverage(
            catalog_path=CATALOG_PATH,
            fixture_paths=[broken_path],
        )
        assert broken["status"] == "fail"
        assert {item["kind"] for item in broken["errors"]} >= {
            "unknown_intent",
            "unknown_function",
        }
        invalid_abstention_path = Path(temporary_directory) / "invalid-abstention.json"
        terminal_function = next(
            item["function_id"] for item in catalog["functions"] if item["terminal"]
        )
        invalid_abstention_path.write_text(
            json.dumps(
                {
                    "split": "invalid_abstention",
                    "frozen": True,
                    "catalog_derived": False,
                    "cases": [
                        {
                            "case_id": "invalid-abstention-terminal",
                            "intent_id": "__abstain__",
                            "goal_text": "insufficient context",
                            "locale": "en-US",
                            "steps": [
                                {
                                    "expected": {
                                        "action": "no_click",
                                        "function_id": terminal_function,
                                    }
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        invalid_abstention = audit_independent_coverage(
            catalog_path=CATALOG_PATH,
            fixture_paths=[invalid_abstention_path],
        )
        assert "unknown_intent" in {
            item["kind"] for item in invalid_abstention["errors"]
        }
    print(
        "navigation independent coverage checks ok: "
        f"cases={report['case_count']} steps={report['step_count']} "
        f"intents={report['intent_covered']} functions={report['function_covered']}"
    )


if __name__ == "__main__":
    main()
