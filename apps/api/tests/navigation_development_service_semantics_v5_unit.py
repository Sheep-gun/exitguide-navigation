from __future__ import annotations

import copy
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_catalog_v5_data import (  # noqa: E402
    OFFICIAL_SOURCES,
    V5_FUNCTIONS,
    V5_INTENTS,
    V5_PURPOSE_CONCEPTS,
    merge_with_base,
)
from navigation_catalog_v6_data import V6_FUNCTIONS, V6_INTENTS  # noqa: E402
from navigation_catalog_v7_data import V7_FUNCTIONS, V7_INTENTS  # noqa: E402
from navigation_catalog_v8_data import V8_FUNCTIONS, V8_INTENTS, merge_with_base as merge_v8_with_base  # noqa: E402
from navigation_catalog_v9_data import V9_FUNCTIONS, V9_INTENTS  # noqa: E402
from navigation_catalog_v10_data import V10_FUNCTIONS, V10_INTENTS  # noqa: E402
from navigation_catalog_v11_data import V11_FUNCTIONS, V11_INTENTS  # noqa: E402
from navigation_alias_context_overrides import strip_alias_context_overrides  # noqa: E402

from app.services.navigation_function_catalog import NavigationFunctionCatalog  # noqa: E402


CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-service-semantics-v5.json"
)
SPLIT = "development_service_semantics_v5"
LOCALES = {"ko-KR", "en-US"}


def _normalized_words(value: object) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return tuple(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


def _normalized_exact(value: object) -> str:
    return "".join(_normalized_words(value))


def _contains_complete_phrase(goal: object, phrase: object) -> bool:
    goal_words = _normalized_words(goal)
    phrase_words = _normalized_words(phrase)
    if not phrase_words or len(phrase_words) > len(goal_words):
        return False
    width = len(phrase_words)
    return any(goal_words[index : index + width] == phrase_words for index in range(len(goal_words) - width + 1))


def _jaccard(left: object, right: object) -> float:
    left_words = set(_normalized_words(left))
    right_words = set(_normalized_words(right))
    if not left_words or not right_words:
        return 0.0
    return len(left_words.intersection(right_words)) / len(left_words.union(right_words))


def main() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = list(payload["cases"])
    functions = {
        str(item["function_id"]): item
        for item in V5_FUNCTIONS
        if bool(item["terminal"])
    }
    intents = {str(item["intent_id"]): item for item in V5_INTENTS}
    all_v5_aliases = {
        str(alias)
        for function in V5_FUNCTIONS
        for values in function["aliases"].values()
        for alias in values
        if str(alias).strip()
    }
    all_v5_patterns = {
        str(pattern)
        for intent in V5_INTENTS
        for pattern in intent.get("patterns", [])
        if str(pattern).strip()
    }

    assert payload["schema_version"] == 2
    assert payload["fixture_version"] == "5.0.0-development.1"
    assert payload["split"] == SPLIT
    assert payload["frozen"] is False
    assert payload["catalog_derived"] is False
    assert payload["tuning_allowed"] is True
    assert payload["source_kind"] == "semantic_development"
    assert payload["claims"] == {
        "independent_accuracy_evidence": False,
        "unseen_holdout": False,
        "production_device_accuracy": False,
    }
    assert "not independent accuracy evidence" in payload["description"]
    assert "never be reported as independent accuracy" in payload["authoring_policy"]["evaluation_use"]
    assert payload["coverage_contract"] == {
        "v5_intents": 136,
        "v5_terminal_functions": 136,
        "cases_per_intent": 2,
        "minimum_cases": 272,
        "locales_per_intent": ["ko-KR", "en-US"],
        "ui_steps": 0,
    }
    assert set(payload["official_sources"]) == set(OFFICIAL_SOURCES)

    assert len(functions) == 136
    assert len(intents) == 136
    assert len(cases) == 272
    assert len({str(case["case_id"]) for case in cases}) == 272
    assert len({_normalized_exact(case["goal_text"]) for case in cases}) == 272

    intent_counts = Counter(str(case["intent_id"]) for case in cases)
    locale_counts = Counter(str(case["locale"]) for case in cases)
    locales_by_intent: dict[str, set[str]] = defaultdict(set)
    strategies_by_intent: dict[str, set[str]] = defaultdict(set)
    goals_by_locale: dict[str, list[str]] = defaultdict(list)

    assert set(intent_counts) == set(intents)
    assert set(intent_counts.values()) == {2}
    assert locale_counts == {"ko-KR": 136, "en-US": 136}

    for case in cases:
        case_id = str(case["case_id"])
        intent_id = str(case["intent_id"])
        locale = str(case["locale"])
        goal = str(case["goal_text"])
        expected_function_id = str(case["expected_function_id"])
        intent = intents[intent_id]
        terminal = functions[expected_function_id]

        assert locale in LOCALES
        assert expected_function_id == str(intent["terminal_function"])
        assert case["source_kind"] == "semantic_development"
        assert case["tuning_allowed"] is True
        assert case["steps"] == []
        assert set(case["source_refs"]) == set(terminal["source_refs"])
        assert set(case["source_refs"]) <= set(OFFICIAL_SOURCES)
        assert {
            "semantic_development",
            "tuning_allowed",
            "purpose_consequence",
            "coordinate_free",
            "not_accuracy_evidence",
        } <= set(case["tags"])
        assert "independent" not in set(case["tags"])

        locales_by_intent[intent_id].add(locale)
        strategies_by_intent[intent_id].add(str(case["semantic_strategy"]))
        goals_by_locale[locale].append(goal)

        if locale == "ko-KR":
            assert case_id.endswith("_ko")
            assert len(goal) >= 70
            assert any("가" <= character <= "힣" for character in goal)
            assert any(marker in goal for marker in ("싶어", "위해", "때문", "도록", "전에", "뒤", "다음"))
            assert goal.count(".") >= 1
        else:
            assert case_id.endswith("_en")
            assert len(goal) >= 135
            assert re.search(r"[a-z]", goal, flags=re.IGNORECASE)
            assert sum(
                marker in f" {goal.casefold()} "
                for marker in (
                    " need ",
                    " want ",
                    " because ",
                    " before ",
                    " after ",
                    " without ",
                    " while ",
                    " so ",
                    " until ",
                )
            ) >= 1
            assert goal.count(".") >= 2

        # This pack tests consequence-level language.  A complete reviewed UI
        # alias or goal pattern from anywhere in v5 would turn it back into
        # label memorization or introduce an accidental cross-intent shortcut.
        copied_aliases = sorted(alias for alias in all_v5_aliases if _contains_complete_phrase(goal, alias))
        copied_patterns = sorted(pattern for pattern in all_v5_patterns if _contains_complete_phrase(goal, pattern))
        assert not copied_aliases, (case_id, copied_aliases)
        assert not copied_patterns, (case_id, copied_patterns)
        assert _normalized_exact(goal) not in {
            _normalized_exact(value) for value in all_v5_aliases | all_v5_patterns
        }
        purpose_rules = V5_PURPOSE_CONCEPTS[expected_function_id][locale]
        assert any(
            all(_normalized_exact(term) in _normalized_exact(goal) for term in terms)
            for terms in purpose_rules
        )
        for terms in purpose_rules:
            assert 2 <= len(terms) <= 4
            assert all("." not in term and "\n" not in term for term in terms)
            assert _normalized_exact(goal) not in {
                _normalized_exact(term) for term in terms
            }
            assert _normalized_exact(goal) != _normalized_exact(" ".join(terms))
        assert not re.match(
            r"^\s*(find|open|show me|go to|locate|navigate to|찾아|열어|보여|이동)",
            goal,
            flags=re.IGNORECASE,
        )

    assert all(locales == LOCALES for locales in locales_by_intent.values())
    assert all(
        strategies == {
            "consequence_and_user_boundary",
            "scenario_constraint_and_review_boundary",
        }
        for strategies in strategies_by_intent.values()
    )

    # Repeated safety framing is intentional, but no two probes should be near
    # duplicates once their scenario and consequence vocabulary are included.
    for locale, goals in goals_by_locale.items():
        maximum_similarity = max(
            _jaccard(left, right)
            for index, left in enumerate(goals)
            for right in goals[index + 1 :]
        )
        assert maximum_similarity < 0.78, (locale, maximum_similarity)

    # Materialize the source ontology over the pre-v5 prefix.  This makes the
    # development gate exercise the reviewed source definition even before a
    # maintainer promotes it into the canonical generated JSON.
    materialized = strip_alias_context_overrides(
        json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    )
    v5_function_ids = {str(item["function_id"]) for item in V5_FUNCTIONS}
    v5_intent_ids = {str(item["intent_id"]) for item in V5_INTENTS}
    later_function_ids = {
        str(item["function_id"])
        for item in (
            *V6_FUNCTIONS,
            *V7_FUNCTIONS,
            *V8_FUNCTIONS,
            *V9_FUNCTIONS,
            *V10_FUNCTIONS,
            *V11_FUNCTIONS,
        )
    }
    later_intent_ids = {
        str(item["intent_id"])
        for item in (
            *V6_INTENTS,
            *V7_INTENTS,
            *V8_INTENTS,
            *V9_INTENTS,
            *V10_INTENTS,
            *V11_INTENTS,
        )
    }
    base = copy.deepcopy(materialized)
    base["functions"] = [
        item for item in materialized["functions"]
        if str(item["function_id"]) not in v5_function_ids | later_function_ids
    ]
    base["intents"] = [
        item for item in materialized["intents"]
        if str(item["intent_id"]) not in v5_intent_ids | later_intent_ids
    ]
    base.pop("official_sources_v5", None)
    base.pop("official_sources_v6", None)
    base.pop("official_sources_v7", None)
    base.pop("official_sources_v8", None)
    base.pop("official_sources_v9", None)
    base.pop("official_sources_v10", None)
    base.pop("official_sources_v11", None)
    base["catalog_version"] = "4.0.0"
    merged = merge_with_base(base)

    # Development accuracy is a tuning gate, never holdout or independent
    # evidence.  Every successful match must come from compact ontology atoms,
    # not a copied authored sentence.
    correct = Counter()
    generic = Counter()
    with TemporaryDirectory() as temporary_directory:
        generated_catalog = Path(temporary_directory) / "v5-catalog.json"
        generated_catalog.write_text(
            json.dumps(merged, ensure_ascii=False),
            encoding="utf-8",
        )
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "v5-semantic-development.sqlite",
            generated_catalog,
        )
        catalog.validate()
        for case in cases:
            locale = str(case["locale"])
            plan = catalog.plan_goal(str(case["goal_text"]))
            assert plan.intent
            correct[locale] += int(plan.intent == str(case["intent_id"]))
            generic[locale] += int(plan.intent == "generic_navigation")

    total_correct = sum(correct.values())
    total_generic = sum(generic.values())
    assert total_correct / len(cases) >= 0.90
    assert correct["ko-KR"] / 136 >= 0.90
    assert correct["en-US"] / 136 >= 0.90
    assert total_generic == 0
    print(
        "navigation v5 semantic-development checks ok: "
        f"cases={len(cases)} intents={len(intents)} ko={locale_counts['ko-KR']} en={locale_counts['en-US']} "
        f"development={total_correct}/{len(cases)} ({total_correct / len(cases):.2%}) "
        f"ko={correct['ko-KR']}/136 en={correct['en-US']}/136 "
        f"generic={total_generic}/{len(cases)}"
    )


if __name__ == "__main__":
    main()
