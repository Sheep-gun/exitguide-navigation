import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from app.services.navigation_db_gym import load_fixed_cases


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "public-productivity-system.v1.json"
)
SPLIT = "public_productivity_system"
ALLOWED_ACTIONS = {"click", "scroll_forward", "back", "stop", "no_click"}
REQUIRED_OFFICIAL_PATHS = {
    "/calendar/answer/72143",
    "/calendar/answer/6084644",
    "/calendar/answer/37242",
    "/calendar/answer/37135",
    "/maps/answer/144349",
    "/maps/answer/3273406",
    "/maps/answer/6291838",
    "/maps/answer/7280933",
    "/maps/answer/15437054",
    "/maps/answer/9430563",
    "/mail/answer/6576",
    "/mail/answer/6562",
    "/mail/answer/25922",
    "/android/answer/9079661",
    "/android/answer/13530434",
    "/android/answer/12623953",
    "/android/answer/2819582",
    "/android/answer/9319337",
    "/android/answer/12464968",
}


def _normalized(value: object) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", str(value)).strip().casefold().split()
    )


def _selected_element(step: dict[str, object]) -> dict[str, object] | None:
    expected = dict(step["expected"])
    label = expected.get("label")
    if not isinstance(label, str) or not label:
        return None
    for element in step["elements"]:
        if label in {element.get("label"), element.get("content_description")}:
            return element
    return None


def _all_keys(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_keys(item)


def main() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    sources = payload["sources"]

    assert payload["dataset_version"] == "1.0.0"
    assert payload["split"] == SPLIT
    assert payload["frozen"] is True
    assert payload["catalog_derived"] is False
    assert payload["tuning_allowed"] is True
    assert payload["provenance"] == "official_primary_documentation"
    assert payload["retrieved_at"] == "2026-07-30"
    assert "primary publisher documentation only" in payload["review_policy"]
    assert "Never convert documented order into guessed coordinates" in payload["review_policy"]
    assert payload["safety_expectations"]["unsafe_automatic_clicks"] == 0
    assert payload["safety_expectations"]["coordinate_claims"] == 0
    assert payload["safety_expectations"]["user_owns_final_activation"] is True

    # Every provenance record is complete, primary, version-reviewable, and used.
    source_ids = [str(source["source_id"]) for source in sources]
    assert len(source_ids) == len(set(source_ids))
    assert len(sources) >= 29
    for source in sources:
        assert set(source) == {
            "source_id",
            "publisher",
            "title",
            "url",
            "platform",
            "retrieved_at",
            "review_policy",
        }
        assert source["publisher"] == "Google"
        parsed = urlparse(str(source["url"]))
        assert parsed.scheme == "https"
        assert parsed.hostname == "support.google.com"
        assert re.fullmatch(r"/(calendar|maps|mail|android)/answer/\d+", parsed.path)
        assert source["title"].strip()
        assert source["platform"].strip()
        assert source["retrieved_at"] == "2026-07-30"
        assert "Recheck" in source["review_policy"] or "recheck" in source["review_policy"]

    registered_paths = {urlparse(str(source["url"])).path for source in sources}
    assert REQUIRED_OFFICIAL_PATHS <= registered_paths
    used_source_ids = {str(case["source_id"]) for case in cases}
    assert used_source_ids == set(source_ids)

    # Independent breadth: all goals and cases are unique, bilingual, and cover
    # significantly more intents than the minimum gate.
    assert len(cases) == 55
    assert sum(len(case["steps"]) for case in cases) == 176
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert len({_normalized(case["goal_text"]) for case in cases}) == len(cases)
    assert len({case["intent_id"] for case in cases}) == 55
    locale_counts = Counter(str(case["locale"]) for case in cases)
    assert locale_counts == {"ko-KR": 28, "en-US": 27}
    assert all(len(str(case["goal_text"]).strip()) >= 20 for case in cases)

    intents = {str(item["intent_id"]): item for item in catalog["intents"]}
    functions = {str(item["function_id"]): item for item in catalog["functions"]}
    catalog_exact_phrases = {
        _normalized(pattern)
        for intent in catalog["intents"]
        for pattern in intent.get("patterns", [])
        if str(pattern).strip()
    }
    assert not {
        _normalized(case["goal_text"]) for case in cases
    }.intersection(catalog_exact_phrases)

    action_counts: Counter[str] = Counter()
    surface_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    dimension_counts: Counter[str] = Counter()
    unsafe_clicks: list[tuple[str, str, str]] = []

    for case in cases:
        assert case["source_id"] in used_source_ids
        assert case["source_kind"] == "fixed_independent"
        assert case["intent_id"] in intents
        assert case["app_package"].count(".") >= 1
        assert case["app_version"] == "documented-2026-07"
        assert case["orientation"] in {"portrait", "landscape"}
        assert case["android_version"] in {"9", "12", "13", "14", "15"}
        assert {
            "official_help",
            "primary_source",
            "productivity_system",
            "coordinate_free",
        } <= set(case["tags"])
        assert case["steps"]
        assert case["steps"][-1]["expected"]["action"] in {"stop", "no_click"}
        assert (
            case["steps"][-1]["expected"]["function_id"]
            == intents[case["intent_id"]]["terminal_function"]
        )
        step_ids = [str(step["step_id"]) for step in case["steps"]]
        assert len(step_ids) == len(set(step_ids))

        for step in case["steps"]:
            assert step["screen_title"].strip()
            assert step["activity_name"].strip()
            assert step["stage"].strip()
            assert step["ui_surface"].strip()
            assert step["screen_state"].strip()
            assert step["elements"]
            action = str(step["expected"]["action"])
            function_id = str(step["expected"]["function_id"])
            assert action in ALLOWED_ACTIONS
            assert function_id in functions
            action_counts[action] += 1
            surface_counts[str(step["ui_surface"])] += 1
            state_counts[str(step["screen_state"])] += 1

            element_ids = [str(element["id"]) for element in step["elements"]]
            assert len(element_ids) == len(set(element_ids))
            for element in step["elements"]:
                assert str(element["id"]).strip()
                assert (
                    element.get("label")
                    or element.get("content_description")
                    or element.get("scrollable")
                )
                if element.get("content_description") and not element.get("label"):
                    dimension_counts["icon_only"] += 1
                if element.get("dangerous"):
                    dimension_counts["dangerous"] += 1
                if element.get("enabled") is False:
                    dimension_counts["disabled"] += 1
                if element.get("scrollable"):
                    dimension_counts["scrollable"] += 1
                if element.get("checkable"):
                    dimension_counts["checkable"] += 1
                if element.get("decoy_kind"):
                    dimension_counts["decoy"] += 1

            if action in {"click", "stop"}:
                selected = _selected_element(step)
                assert selected is not None, (case["case_id"], step["step_id"])
                if action == "click":
                    assert selected.get("clickable", True) is True
                    assert selected.get("enabled", True) is True
                    assert selected.get("visible", True) is True
                    assert selected.get("dangerous", False) is False
            if action == "scroll_forward":
                assert any(element.get("scrollable") for element in step["elements"])
            if action == "no_click":
                assert step["expected"].get("label") is None

            function = functions[function_id]
            risky = bool(
                function.get("state_changing")
                or function.get("risk_level") == "high"
                or function.get("automation_policy") == "never_auto"
                or function.get("stop_policy") in {"before_action", "stop_before_action"}
            )
            if action == "click" and risky:
                unsafe_clicks.append((case["case_id"], step["step_id"], function_id))

        terminal = functions[intents[case["intent_id"]]["terminal_function"]]
        terminal_is_risky = bool(
            terminal.get("state_changing")
            or terminal.get("risk_level") == "high"
            or terminal.get("automation_policy") == "never_auto"
            or terminal.get("stop_policy") in {"before_action", "stop_before_action"}
        )
        if terminal_is_risky:
            assert case["steps"][-1]["expected"]["action"] in {"stop", "no_click"}

    assert unsafe_clicks == []
    assert action_counts == {
        "click": 111,
        "no_click": 29,
        "stop": 28,
        "scroll_forward": 6,
        "back": 2,
    }
    assert {
        "screen",
        "scroll_view",
        "navigation_drawer",
        "sheet",
        "webview",
        "bottom_sheet",
        "dialog",
    } == set(surface_counts)
    assert {
        "ready",
        "confirmation_required",
        "target_below_fold",
        "sensitive_data",
        "unsupported_on_platform",
        "offline",
        "signed_out",
        "permission",
        "loading",
    } == set(state_counts)
    assert dimension_counts["icon_only"] >= 60
    assert dimension_counts["dangerous"] >= 85
    assert dimension_counts["disabled"] >= 5
    assert dimension_counts["scrollable"] >= 20
    assert dimension_counts["checkable"] >= 25
    assert dimension_counts["decoy"] >= 30

    # This fixture is semantic and coordinate-free by contract.
    forbidden_coordinate_keys = {
        "x",
        "y",
        "bounds",
        "coordinates",
        "tap_x",
        "tap_y",
        "screen_width",
        "screen_height",
    }
    assert not forbidden_coordinate_keys.intersection(_all_keys(cases))

    # Exercise the production DB Gym fixed-case parser without evaluating the
    # goals or candidate ranker; this keeps the authored baseline independent.
    loaded = load_fixed_cases(FIXTURE_PATH, split=SPLIT)
    assert len(loaded) == 55
    assert sum(len(case.steps) for case in loaded) == 176
    assert {case.intent_id for case in loaded} == {
        str(case["intent_id"]) for case in cases
    }
    assert all(case.split == SPLIT for case in loaded)
    assert all(case.source_kind == "fixed_independent" for case in loaded)
    assert all(
        step.expected_action in ALLOWED_ACTIONS
        for case in loaded
        for step in case.steps
    )

    print(
        "public productivity/system fixture checks ok: "
        f"cases={len(cases)} steps={sum(len(case['steps']) for case in cases)} "
        f"intents={len({case['intent_id'] for case in cases})} "
        f"sources={len(sources)} actions={dict(action_counts)} "
        f"locales={dict(locale_counts)} unsafe_clicks={len(unsafe_clicks)}"
    )


if __name__ == "__main__":
    main()
