import copy
import json
import sys
from pathlib import Path

from app.services.navigation_function_catalog import validate_catalog_payload


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_catalog_v3_data import (  # noqa: E402
    REQUIRED_OFFICIAL_EXAMPLES,
    V3CatalogValidationError,
    V3_FUNCTIONS,
    V3_INTENTS,
    load_base_catalog,
    merge_with_base,
    validate_v3_data,
)
from navigation_catalog_v13_data import CATALOG_V13_DESCRIPTION, CATALOG_V13_VERSION  # noqa: E402
from navigation_catalog_v14_data import (  # noqa: E402
    CATALOG_V14_DESCRIPTION,
    CATALOG_V14_VERSION,
    V14_FUNCTIONS,
    V14_INTENTS,
)
from navigation_catalog_v15_data import (  # noqa: E402
    CATALOG_V15_DESCRIPTION,
    CATALOG_V15_VERSION,
    V15_FUNCTIONS,
    V15_INTENTS,
)


def main() -> None:
    materialized = load_base_catalog()
    v3_function_ids = {str(item["function_id"]) for item in V3_FUNCTIONS}
    v3_intent_ids = {str(item["intent_id"]) for item in V3_INTENTS}
    v14_function_ids = {str(item["function_id"]) for item in V14_FUNCTIONS}
    v14_intent_ids = {str(item["intent_id"]) for item in V14_INTENTS}
    v15_function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    v15_intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}
    # The runtime catalog may already be materialized at v3.  Reconstruct the
    # v2 base so the independent pack is still collision-checked on every run.
    base = copy.deepcopy(materialized)
    base["functions"] = [
        item for item in materialized["functions"]
        if str(item["function_id"]) not in v3_function_ids | v14_function_ids | v15_function_ids
    ]
    base["intents"] = [
        item for item in materialized["intents"]
        if str(item["intent_id"]) not in v3_intent_ids | v14_intent_ids | v15_intent_ids
    ]
    base.pop("official_sources_v14", None)
    base.pop("source_document_v14", None)
    base.pop("official_sources_v15", None)
    base.pop("source_document_v15", None)
    base.pop("semantic_equivalence_v15", None)
    base["catalog_version"] = CATALOG_V13_VERSION
    base["description"] = CATALOG_V13_DESCRIPTION
    base_snapshot = copy.deepcopy(base)
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
    stats = validate_v3_data(base)

    assert stats["functions"] >= 100
    assert stats["intents"] >= 80
    assert stats["domains"] >= 15
    assert stats["aliases"] >= stats["functions"] * 4
    assert stats["goal_patterns"] >= stats["intents"] * 6
    assert stats["goal_rules"] >= stats["intents"] * 4
    assert stats["state_changing"] > 0
    assert stats["high_risk"] > 0

    function_ids = v3_function_ids
    intent_by_terminal = {str(item["terminal_function"]): item for item in V3_INTENTS}
    assert REQUIRED_OFFICIAL_EXAMPLES <= function_ids
    assert REQUIRED_OFFICIAL_EXAMPLES <= set(intent_by_terminal)

    required_domains = {
        "email",
        "calendar",
        "contacts",
        "maps",
        "mobility_delivery",
        "telecom",
        "documents_cloud",
        "education",
        "gaming_parental",
        "government_tax",
        "smart_home",
        "photos_camera",
        "audio",
        "work_collaboration",
        "finance_long_tail",
        "safety",
        "wellbeing_health",
        "android_extended",
    }
    assert required_domains <= {str(item["domain"]) for item in V3_FUNCTIONS}

    for item in V3_FUNCTIONS:
        aliases = item["aliases"]
        assert aliases["ko-KR"] and aliases["en-US"]
        assert item["positive_context"] and item["negative_context"]
        assert item["role_hints"] and item["state_cues"] and item["risk_cues"]
        if item["state_changing"] or item["risk_level"] == "high":
            assert item["automation_policy"] == "never_auto"
            assert item["stop_policy"] in {
                "before_action",
                "before_activation",
                "user_confirmation",
                "user_only",
                "stop_before_action",
            }

    for intent in V3_INTENTS:
        assert len(intent["patterns_by_locale"]["ko-KR"]) >= 3
        assert len(intent["patterns_by_locale"]["en-US"]) >= 3
        assert len(intent["goal_rules"]) >= 4
        assert intent["route"][-1]["function_id"] == intent["terminal_function"]
        assert intent["avoid_functions"]

    merged = merge_with_base(base)
    assert base == base_snapshot, "merge_with_base must not mutate the source catalog"
    assert merged["functions"][:len(base["functions"])] == base["functions"]
    assert merged["intents"][:len(base["intents"])] == base["intents"]
    assert len(merged["functions"]) == len(base["functions"]) + len(V3_FUNCTIONS)
    assert len(merged["intents"]) == len(base["intents"]) + len(V3_INTENTS)
    validate_catalog_payload(merged)

    colliding = {"functions": [{"function_id": next(iter(function_ids))}], "intents": []}
    try:
        validate_v3_data(colliding)
    except V3CatalogValidationError as exc:
        assert "collides with base catalog" in str(exc)
    else:
        raise AssertionError("base ID collisions must fail validation")

    print(
        "navigation catalog v3 data checks ok: "
        f"functions={stats['functions']} intents={stats['intents']} domains={stats['domains']} "
        f"aliases={stats['aliases']} patterns={stats['goal_patterns']} rules={stats['goal_rules']}"
    )


if __name__ == "__main__":
    main()
