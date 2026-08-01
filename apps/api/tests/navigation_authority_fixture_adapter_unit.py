from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_db_gym import load_fixed_cases  # noqa: E402
from app.services.navigation_independent_coverage import audit_independent_coverage  # noqa: E402


SOURCE_PATH = ROOT / "fixtures/navigation/db-gym/independent-authority-systems-v15.json"
CATALOG_PATH = ROOT / "fixtures/navigation/function-catalog.v1.json"
ADAPTER_PATH = ROOT / "scripts/Normalize-NavigationAuthorityFixture.py"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("navigation_authority_fixture_adapter", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expect_failure(action, fragment: str) -> None:
    try:
        action()
    except ValueError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"invalid authority projection accepted; expected {fragment!r}")


def main() -> None:
    adapter = _load_adapter()
    source = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    source_snapshot = copy.deepcopy(source)
    catalog_snapshot = copy.deepcopy(catalog)

    stateful = adapter.normalize_stateful_fixture(source=source, catalog=catalog)
    goals = adapter.normalize_goal_fixture(source=source, catalog=catalog)
    assert source == source_snapshot
    assert catalog == catalog_snapshot
    assert stateful["split"] == goals["split"] == "independent_authority_systems_v15"
    assert stateful["frozen"] is goals["frozen"] is True
    assert stateful["catalog_derived"] is goals["catalog_derived"] is False
    assert stateful["tuning_allowed"] is goals["tuning_allowed"] is False
    assert stateful["source_fixture_sha256"] == source["canonical_json_sha256"]
    assert goals["source_fixture_sha256"] == source["canonical_json_sha256"]
    assert stateful["projection_contract"] == {
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
    assert goals["projection_contract"] == {
        "source_case_count": 960,
        "routable_case_count": 840,
        "excluded_abstention_count": 120,
    }

    raw_by_id = {str(case["case_id"]): case for case in source["cases"]}
    projected_by_id = {str(case["case_id"]): case for case in stateful["cases"]}
    goal_by_id = {str(case["case_id"]): case for case in goals["cases"]}
    assert set(projected_by_id) == set(raw_by_id)
    assert len(projected_by_id) == 960
    assert len(goal_by_id) == 840
    assert Counter(
        case["steps"][0]["expected"]["action"] for case in stateful["cases"]
    ) == {"stop": 840, "no_click": 120}
    assert Counter(case["independent_expected"]["decision"] for case in stateful["cases"]) == {
        "route": 600,
        "retain_prior": 240,
        "abstain": 120,
    }

    for case_id, projected in projected_by_id.items():
        raw = raw_by_id[case_id]
        raw_expected = raw["expected"]
        expected = projected["steps"][0]["expected"]
        assert projected["goal_text"] == raw["goal"]
        assert projected["independent_expected"] == raw_expected
        assert projected["independent_surface"] == raw["surface"]
        assert expected["dangerous_clicks"] == 0
        assert expected["automated_final_presses"] == 0
        assert expected["terminal_press_owner"] == "user"
        assert projected["steps"][0]["screen_state"] == "ready"
        assert all(not bool(element.get("dangerous", False)) for element in projected["steps"][0]["elements"])
        if raw_expected["decision"] == "abstain":
            assert projected["intent_id"] == "__abstain__"
            assert expected["action"] == "no_click"
            assert expected["function_id"] == f"{raw_expected['safe_fallback_domain']}.hub"
            assert projected["user_state"].startswith("underspecified:")
            assert case_id not in goal_by_id
        else:
            assert expected["action"] == "stop"
            assert expected["function_id"] == raw_expected["function_id"]
            assert projected["intent_id"] != "__abstain__"
            assert goal_by_id[case_id]["goal_text"] == raw["goal"]
            assert goal_by_id[case_id]["independent_expected"] == raw_expected

    with TemporaryDirectory(prefix="egl-v15-adapter-") as temporary_directory:
        stateful_path = Path(temporary_directory) / "stateful.json"
        stateful_path.write_text(json.dumps(stateful, ensure_ascii=False), encoding="utf-8")
        loaded = load_fixed_cases(stateful_path, split=stateful["split"])
        assert len(loaded) == 960
        assert Counter(step.expected_action for case in loaded for step in case.steps) == {
            "stop": 840,
            "no_click": 120,
        }
        report = audit_independent_coverage(
            catalog_path=CATALOG_PATH,
            fixture_paths=[stateful_path],
        )
        split_errors = [
            item
            for item in report["errors"]
            if item["split"] == "independent_authority_systems_v15"
            and item["kind"] in {"unknown_intent", "unknown_function", "unguarded_state_change_click"}
        ]
        assert split_errors == []

    tampered = copy.deepcopy(source)
    tampered["cases"][0]["goal"] += " tampered"
    _expect_failure(
        lambda: adapter.normalize_stateful_fixture(source=tampered, catalog=catalog),
        "canonical seal differs",
    )
    wrong_catalog = copy.deepcopy(catalog)
    wrong_catalog["catalog_version"] = "14.0.0"
    _expect_failure(
        lambda: adapter.normalize_stateful_fixture(source=source, catalog=wrong_catalog),
        "exact materialized V15",
    )
    print(
        "navigation authority fixture adapter checks ok: "
        "cases=960 steps=960 stop=840 no_click=120 routable_goals=840 "
        "dangerous_clicks=0 automated_final_presses=0 sealed=true"
    )


if __name__ == "__main__":
    main()
