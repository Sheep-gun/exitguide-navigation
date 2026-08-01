import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
GYM_ROOT = ROOT / "fixtures" / "navigation" / "db-gym"
SEALED_PATH = GYM_ROOT / "independent-sealed-realistic.v1.json"


def normalized(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def iter_aliases(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_aliases(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_aliases(item)


def main() -> None:
    payload = json.loads(SEALED_PATH.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]

    # Seal, provenance, and review controls.  This test deliberately does not
    # import the goal resolver, candidate matcher, Gym evaluator, or report code.
    assert payload["dataset_version"] == "1.0.0"
    assert payload["split"] == "independent_sealed_realistic"
    assert payload["sealed"] is True
    assert payload["frozen"] is True
    assert payload["tuning_allowed"] is False
    assert payload["catalog_derived"] is False
    assert payload["provenance"] == "human_authored_realistic_synthetic"
    assert "zero-shot" in payload["review_policy"]
    assert "two independent human reviewers" in payload["review_policy"]
    assert "version bump" in payload["review_policy"]
    assert "retire this version" in payload["blind_evaluation_policy"]
    assert payload["safety_expectations"]["risky_or_state_changing_automatic_clicks"] == 0
    assert payload["safety_expectations"]["offline_automatic_retries"] == 0

    canonical_cases = json.dumps(
        cases,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    actual_sha = hashlib.sha256(canonical_cases).hexdigest()
    assert payload["cases_sha256"] == actual_sha
    assert len(actual_sha) == 64

    intents = {str(item["intent_id"]): item for item in catalog["intents"]}
    functions = {str(item["function_id"]): item for item in catalog["functions"]}
    assert len(cases) >= 100
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert len({case["intent_id"] for case in cases}) >= 100
    assert sum(len(case["steps"]) for case in cases) >= 220
    assert all(case["intent_id"] in intents for case in cases)
    assert all(case["source_kind"] == "fixed_independent_sealed" for case in cases)
    assert all({"sealed", "realistic_synthetic", "blind_zero_shot"} <= set(case["tags"]) for case in cases)

    locale_counts = Counter(case["locale"] for case in cases)
    assert set(locale_counts) == {"ko-KR", "en-US"}
    assert locale_counts["ko-KR"] / len(cases) >= 0.40
    assert locale_counts["en-US"] / len(cases) >= 0.40
    assert len({normalized(case["goal_text"]) for case in cases}) == len(cases)

    allowed_actions = {"click", "scroll_forward", "back", "stop", "no_click"}
    risky_auto_clicks = []
    dimensions = Counter()
    all_screen_titles = set()
    all_activity_names = set()
    all_ui_surfaces = set()
    all_screen_states = set()

    for case in cases:
        assert case["goal_text"].strip()
        assert case["app_package"].count(".") >= 1
        assert case["app_version"].strip()
        assert case["device_model"].strip()
        assert case["android_version"] in {"12", "13", "14", "15"}
        assert case["orientation"] in {"portrait", "landscape"}
        assert case["steps"]
        assert case["steps"][-1]["expected"]["action"] in {"stop", "no_click"}
        assert case["steps"][-1]["expected"]["function_id"] == intents[case["intent_id"]]["terminal_function"]

        step_ids = [step["step_id"] for step in case["steps"]]
        assert len(step_ids) == len(set(step_ids))
        for step in case["steps"]:
            all_screen_titles.add(step["screen_title"])
            all_activity_names.add(step["activity_name"])
            all_ui_surfaces.add(step["ui_surface"])
            all_screen_states.add(step["screen_state"])
            assert step["screen_title"].strip()
            assert step["activity_name"].strip()
            assert step["stage"].strip()
            assert step["ui_surface"].strip()
            assert step["screen_state"].strip()
            assert step["elements"]
            element_ids = [element["id"] for element in step["elements"]]
            assert len(element_ids) == len(set(element_ids))

            exp = step["expected"]
            assert exp["action"] in allowed_actions
            assert exp["function_id"] in functions
            function = functions[exp["function_id"]]
            risky = bool(
                function.get("state_changing")
                or function.get("risk_level") == "high"
                or function.get("stop_policy") in {"before_action", "stop_before_action"}
                or function.get("automation_policy") in {"never_auto", "user_confirmation"}
            )
            if risky and exp["action"] == "click":
                risky_auto_clicks.append((case["case_id"], step["step_id"], exp["function_id"]))

            if exp["action"] in {"click", "stop"}:
                assert isinstance(exp.get("label"), str) and exp["label"].strip()
                candidates = [
                    element
                    for element in step["elements"]
                    if exp["label"] in {element.get("label"), element.get("content_description")}
                ]
                assert candidates, (case["case_id"], step["step_id"], exp["label"])
                if exp["action"] == "click":
                    assert any(
                        candidate.get("clickable", True)
                        and candidate.get("enabled", True)
                        and candidate.get("visible", True)
                        and not candidate.get("dangerous", False)
                        for candidate in candidates
                    )
            if exp["action"] == "scroll_forward":
                assert any(element.get("scrollable") is True for element in step["elements"])
                dimensions["scroll"] += 1
            if exp["action"] == "no_click":
                dimensions["no_click"] += 1

            for element in step["elements"]:
                assert element["id"].strip()
                assert element.get("label") or element.get("content_description") or element.get("scrollable")
                if element.get("content_description") and not element.get("label"):
                    dimensions["icon_only"] += 1
                if element.get("dangerous"):
                    dimensions["dangerous"] += 1
                    assert exp["action"] != "click" or exp.get("label") not in {
                        element.get("label"),
                        element.get("content_description"),
                    }
                if element.get("enabled") is False:
                    dimensions["disabled"] += 1
                if element.get("visible") is False:
                    dimensions["invisible"] += 1
                if element.get("selected") is True:
                    dimensions["selected"] += 1
                if element.get("checkable") is True:
                    dimensions["checkable"] += 1
                if element.get("decoy_kind"):
                    dimensions[f"decoy:{element['decoy_kind']}"] += 1

    assert risky_auto_clicks == []
    assert dimensions["scroll"] >= 20
    assert dimensions["icon_only"] >= 20
    assert dimensions["dangerous"] >= 10
    assert dimensions["disabled"] >= 20
    assert dimensions["invisible"] >= 20
    assert dimensions["selected"] >= 20
    assert dimensions["checkable"] >= 20
    assert dimensions["no_click"] >= 2
    assert sum(state == "offline" for case in cases for state in [case["steps"][0]["screen_state"]]) >= 2
    assert sum(step["screen_state"] == "signed_out" for case in cases for step in case["steps"]) >= 10
    assert {"dialog", "confirmation_dialog", "navigation_drawer", "bottom_sheet", "lazy_list"} <= all_ui_surfaces
    assert {"offline", "modal", "signed_out", "target_below_fold", "confirmation_required"} <= all_screen_states
    assert len(all_screen_titles) >= 100
    assert len(all_activity_names) >= 30
    assert dimensions["decoy:advertisement"] >= 20
    assert dimensions["decoy:disabled_duplicate"] >= 20

    # Exact sentence leakage checks only. Common real UI nouns may naturally recur,
    # but no sealed user utterance may be copied verbatim from a catalog trigger or
    # any pre-existing fixture.
    catalog_phrases = set()
    for intent in catalog["intents"]:
        catalog_phrases.update(normalized(value) for value in intent.get("patterns", []))
        catalog_phrases.update(normalized(value) for value in iter_aliases(intent.get("goal_rules", [])))
    for function in catalog["functions"]:
        catalog_phrases.update(normalized(value) for value in iter_aliases(function.get("aliases", {})))

    prior_fixture_goals = set()
    for fixture_path in GYM_ROOT.glob("*.json"):
        if fixture_path == SEALED_PATH:
            continue
        prior = json.loads(fixture_path.read_text(encoding="utf-8"))
        prior_fixture_goals.update(
            normalized(case.get("goal_text", ""))
            for case in prior.get("cases", [])
            if case.get("goal_text")
        )
    sealed_goals = {normalized(case["goal_text"]) for case in cases}
    assert not sealed_goals.intersection(catalog_phrases)
    assert not sealed_goals.intersection(prior_fixture_goals)
    assert not any("기능 목록" in case["goal_text"] or "관련 도움말" in case["goal_text"] for case in cases)

    print(
        "sealed realistic fixture integrity checks ok: "
        f"cases={len(cases)} steps={sum(len(case['steps']) for case in cases)} "
        f"intents={len({case['intent_id'] for case in cases})} "
        f"ko={locale_counts['ko-KR']} en={locale_counts['en-US']} sha={actual_sha}"
    )


if __name__ == "__main__":
    main()
