from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_catalog_v7_data import (  # noqa: E402
    CATALOG_V7_DESCRIPTION,
    CATALOG_V7_VERSION,
    OFFICIAL_SOURCES,
    REQUIRED_DOMAINS,
    REQUIRED_FUNCTIONS,
    V7CatalogValidationError,
    V7_FUNCTIONS,
    V7_INTENTS,
    load_base_catalog,
    merge_with_base,
    validate_v7_data,
)
from navigation_catalog_v6_data import CATALOG_V6_DESCRIPTION, CATALOG_V6_VERSION  # noqa: E402
from navigation_catalog_v8_data import (  # noqa: E402
    V8_FUNCTIONS,
    V8_INTENTS,
    merge_with_base as merge_v8_with_base,
)
from navigation_catalog_v9_data import (  # noqa: E402
    V9_FUNCTIONS,
    V9_INTENTS,
    merge_with_base as merge_v9_with_base,
)
from navigation_catalog_v10_data import (  # noqa: E402
    V10_FUNCTIONS,
    V10_INTENTS,
    merge_with_base as merge_v10_with_base,
)
from navigation_catalog_v11_data import (  # noqa: E402
    V11_FUNCTIONS,
    V11_INTENTS,
    merge_with_base as merge_v11_with_base,
)
from navigation_catalog_v12_data import (  # noqa: E402
    V12_FUNCTIONS,
    V12_INTENTS,
    merge_with_base as merge_v12_with_base,
)
from navigation_catalog_v13_data import (  # noqa: E402
    V13_FUNCTIONS,
    V13_INTENTS,
    merge_with_base as merge_v13_with_base,
)
from navigation_catalog_v14_data import (  # noqa: E402
    CATALOG_V14_DESCRIPTION,
    CATALOG_V14_VERSION,
    V14_FUNCTIONS,
    V14_INTENTS,
    merge_with_base as merge_v14_with_base,
)
from navigation_catalog_v15_data import (  # noqa: E402
    CATALOG_V15_DESCRIPTION,
    CATALOG_V15_VERSION,
    V15_FUNCTIONS,
    V15_INTENTS,
    merge_with_base as merge_v15_with_base,
)
from navigation_alias_context_overrides import (  # noqa: E402
    apply_alias_context_overrides,
    strip_alias_context_overrides,
)
from app.services.navigation_catalog_quality import audit_navigation_catalog  # noqa: E402
from app.services.navigation_function_catalog import (  # noqa: E402
    NavigationFunctionCatalog,
    validate_catalog_payload,
)


def _serialized(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def main() -> None:
    base = strip_alias_context_overrides(load_base_catalog())
    v8_function_ids = {
        str(item["function_id"])
        for item in (*V8_FUNCTIONS, *V9_FUNCTIONS, *V10_FUNCTIONS, *V11_FUNCTIONS, *V12_FUNCTIONS, *V13_FUNCTIONS, *V14_FUNCTIONS, *V15_FUNCTIONS)
    }
    v8_intent_ids = {
        str(item["intent_id"])
        for item in (*V8_INTENTS, *V9_INTENTS, *V10_INTENTS, *V11_INTENTS, *V12_INTENTS, *V13_INTENTS, *V14_INTENTS, *V15_INTENTS)
    }
    base["functions"] = [
        item for item in base["functions"] if str(item["function_id"]) not in v8_function_ids
    ]
    base["intents"] = [
        item for item in base["intents"] if str(item["intent_id"]) not in v8_intent_ids
    ]
    base.pop("official_sources_v8", None)
    base.pop("official_sources_v9", None)
    base.pop("official_sources_v10", None)
    base.pop("official_sources_v11", None)
    base.pop("official_sources_v12", None)
    base.pop("source_document_v12", None)
    base.pop("official_sources_v13", None)
    base.pop("source_document_v13", None)
    base.pop("official_sources_v14", None)
    base.pop("source_document_v14", None)
    base.pop("official_sources_v15", None)
    base.pop("source_document_v15", None)
    base.pop("semantic_equivalence_v15", None)
    base["catalog_version"] = CATALOG_V6_VERSION
    base["description"] = CATALOG_V6_DESCRIPTION
    before = copy.deepcopy(base)
    v14_function_ids = {str(item["function_id"]) for item in V14_FUNCTIONS}
    v14_intent_ids = {str(item["intent_id"]) for item in V14_INTENTS}
    v15_function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    v15_intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}
    assert not v14_function_ids.intersection(str(item["function_id"]) for item in base["functions"])
    assert not v14_intent_ids.intersection(str(item["intent_id"]) for item in base["intents"])
    assert "official_sources_v14" not in base and "source_document_v14" not in base
    assert base["catalog_version"] != CATALOG_V14_VERSION
    assert base["description"] != CATALOG_V14_DESCRIPTION
    assert not v15_function_ids.intersection(str(item["function_id"]) for item in base["functions"])
    assert not v15_intent_ids.intersection(str(item["intent_id"]) for item in base["intents"])
    assert not {"official_sources_v15", "source_document_v15", "semantic_equivalence_v15"} & set(base)
    assert base["catalog_version"] != CATALOG_V15_VERSION
    assert base["description"] != CATALOG_V15_DESCRIPTION
    stats = validate_v7_data(base)
    assert stats == {
        "functions": 128,
        "terminal_functions": 120,
        "intents": 120,
        "domains": 8,
        "domain_terminal_counts": {
            "beauty_wellness_booking": 15,
            "childcare_family_portal": 15,
            "creator_monetization": 15,
            "crypto_assets": 15,
            "dating_discovery": 15,
            "digital_library": 15,
            "esign_notary": 15,
            "sports_team": 15,
        },
        "official_sources": 46,
        "aliases": 2320,
        "goal_patterns": 3120,
        "goal_rules": 4696,
        "compositional_goal_rules": 1822,
        "state_changing": 78,
        "high_risk": 95,
        "materialized": False,
    }
    assert base == before, "validation mutated the catalog"
    assert REQUIRED_DOMAINS == {
        "dating_discovery",
        "digital_library",
        "beauty_wellness_booking",
        "childcare_family_portal",
        "esign_notary",
        "creator_monetization",
        "crypto_assets",
        "sports_team",
    }
    function_ids = {str(item["function_id"]) for item in V7_FUNCTIONS}
    terminal_ids = {str(item["function_id"]) for item in V7_FUNCTIONS if item["terminal"]}
    assert REQUIRED_FUNCTIONS <= function_ids
    assert {str(item["terminal_function"]) for item in V7_INTENTS} == terminal_ids
    assert all(str(item["intent_id"]).startswith("v7_") for item in V7_INTENTS)
    assert all(
        str(rule["rule_kind"]).startswith("v7_")
        and "v7_discriminative_keys" in rule
        and "v6_discriminative_keys" not in rule
        for intent in V7_INTENTS
        for rule in intent["goal_rules"]
    )
    assert all(
        "v7_long_tail" in item["legacy_tags"] and "v6_open_world" not in item["legacy_tags"]
        for item in V7_FUNCTIONS
    )
    for item in V7_FUNCTIONS:
        assert len(item["aliases"]["ko-KR"]) >= 8
        assert len(item["aliases"]["en-US"]) >= 8
        assert len(item["positive_context"]) >= 6
        assert len(item["negative_context"]) >= 4
        assert item["source_refs"]
        assert set(item["source_refs"]) <= set(OFFICIAL_SOURCES)
        if item["state_changing"] or item["risk_level"] == "high":
            assert item["automation_policy"] == "never_auto"
            assert item["stop_policy"] == "before_action"
            boundary = " ".join(item["risk_cues"]["user_boundary"])
            assert "사용자" in boundary and "user" in boundary.casefold()
    for item in V7_INTENTS:
        assert len(item["patterns_by_locale"]["ko-KR"]) >= 10
        assert len(item["patterns_by_locale"]["en-US"]) >= 10
        assert len(item["goal_rules"]) >= 24
        assert len(item["route"]) == 2
        assert item["route"][-1]["function_id"] == item["terminal_function"]

    merged = merge_with_base(base)
    assert base == before, "merge mutated the caller"
    assert merged["functions"][:len(base["functions"])] == base["functions"]
    assert merged["intents"][:len(base["intents"])] == base["intents"]
    assert merged["catalog_version"] == CATALOG_V7_VERSION
    assert merged["description"] == CATALOG_V7_DESCRIPTION
    assert merged["official_sources_v7"] == OFFICIAL_SOURCES
    assert len(merged["functions"]) == len(base["functions"]) + len(V7_FUNCTIONS)
    assert len(merged["intents"]) == len(base["intents"]) + len(V7_INTENTS)
    validate_catalog_payload(merged)
    materialized_stats = validate_v7_data(merged)
    assert materialized_stats["materialized"] is True
    assert merge_with_base(merged) == merged
    digest_one = hashlib.sha256(_serialized(merge_with_base(base))).hexdigest()
    digest_two = hashlib.sha256(_serialized(merge_with_base(copy.deepcopy(base)))).hexdigest()
    assert digest_one == digest_two

    policy_path = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
    with tempfile.TemporaryDirectory(prefix="exitguide-v7-trial-") as temp_dir:
        temp = Path(temp_dir)
        merged_path = temp / "v7-trial.json"
        merged_path.write_text(
            json.dumps(
                apply_alias_context_overrides(
                    strip_alias_context_overrides(
                        merge_v15_with_base(
                            merge_v14_with_base(
                                merge_v13_with_base(
                                    merge_v12_with_base(
                                        merge_v11_with_base(
                                            merge_v10_with_base(
                                                merge_v9_with_base(merge_v8_with_base(merged))
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        quality = audit_navigation_catalog(merged_path, policy_path)
        assert quality["quality_score"] == 100.0
        assert quality["severity_counts"] == {}
        assert quality["goal_pattern_collisions"] == []
        catalog = NavigationFunctionCatalog(temp / "v7.sqlite", merged_path)
        for intent in V7_INTENTS:
            for locale in ("ko-KR", "en-US"):
                goal = str(intent["patterns_by_locale"][locale][0])
                plan = catalog.plan_goal(goal)
                assert plan.terminal_function == intent["terminal_function"], (
                    goal,
                    plan.terminal_function,
                    intent["terminal_function"],
                )

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V7_FUNCTIONS[0]))
    try:
        validate_v7_data(partial)
    except V7CatalogValidationError as error:
        assert "partial v7" in str(error)
    else:
        raise AssertionError("partial materialization was accepted")

    changed = copy.deepcopy(merged)
    changed["official_sources_v7"] = {}
    try:
        validate_v7_data(changed)
    except V7CatalogValidationError as error:
        assert "official evidence" in str(error)
    else:
        raise AssertionError("changed evidence registry was accepted")

    print(
        "navigation catalog v7 data checks ok: "
        f"functions={stats['functions']} intents={stats['intents']} domains={stats['domains']} "
        f"sources={stats['official_sources']} aliases={stats['aliases']} "
        f"patterns={stats['goal_patterns']} rules={stats['goal_rules']} sha256={digest_one}"
    )


if __name__ == "__main__":
    main()
