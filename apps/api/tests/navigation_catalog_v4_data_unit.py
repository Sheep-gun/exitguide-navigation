import copy
import json
import sys
import tempfile
from pathlib import Path

from app.services.navigation_function_catalog import validate_catalog_payload
from app.services.navigation_catalog_quality import audit_navigation_catalog, normalize_catalog_text


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_catalog_v4_data import (  # noqa: E402
    OFFICIAL_SOURCES,
    REQUIRED_DOMAINS,
    REQUIRED_FUNCTIONS,
    V4CatalogValidationError,
    V4_FUNCTIONS,
    V4_INTENTS,
    load_base_catalog,
    merge_with_base,
    validate_v4_data,
)
from navigation_alias_context_overrides import (  # noqa: E402
    apply_alias_context_overrides,
    strip_alias_context_overrides,
)
from navigation_catalog_v5_data import (  # noqa: E402
    V5_FUNCTIONS,
    V5_INTENTS,
    merge_with_base as merge_v5_with_base,
)
from navigation_catalog_v6_data import (  # noqa: E402
    V6_FUNCTIONS,
    V6_INTENTS,
    merge_with_base as merge_v6_with_base,
)
from navigation_catalog_v7_data import (  # noqa: E402
    V7_FUNCTIONS,
    V7_INTENTS,
    merge_with_base as merge_v7_with_base,
)
from navigation_catalog_v8_data import (  # noqa: E402
    CATALOG_V8_DESCRIPTION,
    CATALOG_V8_VERSION,
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


def main() -> None:
    materialized = strip_alias_context_overrides(load_base_catalog())
    v4_function_ids = {str(item["function_id"]) for item in V4_FUNCTIONS}
    v4_intent_ids = {str(item["intent_id"]) for item in V4_INTENTS}
    v9_function_ids = {str(item["function_id"]) for item in V9_FUNCTIONS}
    v9_intent_ids = {str(item["intent_id"]) for item in V9_INTENTS}
    v10_function_ids = {str(item["function_id"]) for item in V10_FUNCTIONS}
    v10_intent_ids = {str(item["intent_id"]) for item in V10_INTENTS}
    v11_function_ids = {str(item["function_id"]) for item in V11_FUNCTIONS}
    v11_intent_ids = {str(item["intent_id"]) for item in V11_INTENTS}
    v12_function_ids = {str(item["function_id"]) for item in V12_FUNCTIONS}
    v12_intent_ids = {str(item["intent_id"]) for item in V12_INTENTS}
    v13_function_ids = {str(item["function_id"]) for item in V13_FUNCTIONS}
    v13_intent_ids = {str(item["intent_id"]) for item in V13_INTENTS}
    v14_function_ids = {str(item["function_id"]) for item in V14_FUNCTIONS}
    v14_intent_ids = {str(item["intent_id"]) for item in V14_INTENTS}
    v15_function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    v15_intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}

    # Remain useful after a later materializer lands v4: reconstruct the v3
    # base and exercise the exact same collision/merge path every run.
    base = copy.deepcopy(materialized)
    base["functions"] = [
        item
        for item in materialized["functions"]
        if str(item["function_id"])
        not in v4_function_ids | v9_function_ids | v10_function_ids | v11_function_ids | v12_function_ids | v13_function_ids | v14_function_ids | v15_function_ids
    ]
    base["intents"] = [
        item
        for item in materialized["intents"]
        if str(item["intent_id"])
        not in v4_intent_ids | v9_intent_ids | v10_intent_ids | v11_intent_ids | v12_intent_ids | v13_intent_ids | v14_intent_ids | v15_intent_ids
    ]
    base.pop("official_sources_v4", None)
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
    base["catalog_version"] = CATALOG_V8_VERSION
    base["description"] = CATALOG_V8_DESCRIPTION
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
    stats = validate_v4_data(base)

    assert stats["functions"] == 179
    assert stats["intents"] == 163
    assert stats["domains"] == 16
    assert stats["official_sources"] == 43
    assert stats["sourced_functions"] >= 140
    assert stats["aliases"] >= len(V4_FUNCTIONS) * 8
    assert stats["goal_patterns"] >= len(V4_INTENTS) * 10
    assert stats["goal_rules"] >= len(V4_INTENTS) * 8
    assert stats["state_changing"] > 90
    assert stats["high_risk"] > 75
    assert stats["materialized"] is False

    assert REQUIRED_DOMAINS == {str(item["domain"]) for item in V4_FUNCTIONS}
    assert REQUIRED_FUNCTIONS <= v4_function_ids
    terminal_ids = {str(item["function_id"]) for item in V4_FUNCTIONS if item["terminal"]}
    assert terminal_ids == {str(item["terminal_function"]) for item in V4_INTENTS}

    required_source_urls = {
        "https://support.google.com/chrome/answer/2391819",
        "https://support.google.com/chrome/answer/165139",
        "https://support.google.com/messages/answer/7028817",
        "https://support.google.com/messages/answer/9061432",
        "https://support.google.com/messages/answer/7611075",
        "https://support.google.com/googleplay/answer/6294544",
        "https://support.google.com/googleplay/answer/9281767",
        "https://support.google.com/googleplay/answer/7018481",
        "https://support.google.com/android/answer/9319337",
        "https://support.google.com/android/answer/12464968",
        "https://support.google.com/android/answer/2819582",
    }
    assert required_source_urls <= {str(source["url"]) for source in OFFICIAL_SOURCES.values()}
    assert all(source["verified_status"] == 200 for source in OFFICIAL_SOURCES.values())
    assert all(source["verified_on"] == "2026-07-30" for source in OFFICIAL_SOURCES.values())

    never_auto_stops = {
        "before_action", "before_activation", "user_confirmation", "user_only", "stop_before_action"
    }
    known_sources = set(OFFICIAL_SOURCES)
    for item in V4_FUNCTIONS:
        aliases = item["aliases"]
        assert len(aliases["ko-KR"]) >= 4
        assert len(aliases["en-US"]) >= 4
        assert item["positive_context"] and item["negative_context"]
        assert item["role_hints"] and item["state_cues"] and item["risk_cues"]
        assert item["scope"] and item["node_kind"] and item["stop_policy"]
        assert set(item["source_refs"]) <= known_sources
        assert item["evidence_level"] == ("official" if item["source_refs"] else "ontology_design")
        if item["state_changing"] or item["risk_level"] == "high":
            assert item["automation_policy"] == "never_auto"
            assert item["stop_policy"] in never_auto_stops
        assert not ({"x", "y", "bounds", "coordinates"} & set(item))

    for intent in V4_INTENTS:
        assert len(intent["patterns_by_locale"]["ko-KR"]) >= 3
        assert len(intent["patterns_by_locale"]["en-US"]) >= 3
        assert len(intent["goal_rules"]) >= 8
        assert intent["route"][-1]["function_id"] == intent["terminal_function"]
        assert intent["avoid_functions"]

    # Exact patterns must have one semantic owner across the entire pre-v4
    # catalog and the new pack.  Short UI aliases may overlap because context
    # disambiguates candidates; goal patterns may not.
    pattern_owners: dict[str, set[str]] = {}
    for intent in [*base["intents"], *V4_INTENTS]:
        intent_id = str(intent["intent_id"])
        for pattern in intent.get("patterns", []):
            normalized = normalize_catalog_text(str(pattern))
            if normalized:
                pattern_owners.setdefault(normalized, set()).add(intent_id)
    collisions = {
        normalized: owners for normalized, owners in pattern_owners.items() if len(owners) > 1
    }
    assert collisions == {}, f"exact normalized goal-pattern collisions: {collisions}"

    merged = merge_with_base(base)
    assert base == base_snapshot, "merge_with_base must not mutate the v3 source catalog"
    assert merged["functions"][:len(base["functions"])] == base["functions"]
    assert merged["intents"][:len(base["intents"])] == base["intents"]
    assert len(merged["functions"]) == len(base["functions"]) + len(V4_FUNCTIONS)
    assert len(merged["intents"]) == len(base["intents"]) + len(V4_INTENTS)
    assert merged["catalog_version"] == "4.0.0"
    assert merged["official_sources_v4"] == OFFICIAL_SOURCES
    validate_catalog_payload(merged)

    policy_path = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
    with tempfile.TemporaryDirectory(prefix="exitguide-v4-audit-") as temp_dir:
        catalog_path = Path(temp_dir) / "catalog.json"
        quality_function_ids = {
            str(item["function_id"])
            for generation in (
                V4_FUNCTIONS, V5_FUNCTIONS, V6_FUNCTIONS, V7_FUNCTIONS,
                V8_FUNCTIONS, V9_FUNCTIONS, V10_FUNCTIONS, V11_FUNCTIONS,
                V12_FUNCTIONS, V13_FUNCTIONS, V14_FUNCTIONS, V15_FUNCTIONS,
            )
            for item in generation
        }
        quality_intent_ids = {
            str(item["intent_id"])
            for generation in (
                V4_INTENTS, V5_INTENTS, V6_INTENTS, V7_INTENTS,
                V8_INTENTS, V9_INTENTS, V10_INTENTS, V11_INTENTS,
                V12_INTENTS, V13_INTENTS, V14_INTENTS, V15_INTENTS,
            )
            for item in generation
        }
        quality_payload = copy.deepcopy(materialized)
        quality_payload["functions"] = [
            item for item in materialized["functions"]
            if str(item["function_id"]) not in quality_function_ids
        ]
        quality_payload["intents"] = [
            item for item in materialized["intents"]
            if str(item["intent_id"]) not in quality_intent_ids
        ]
        for version in range(4, 16):
            quality_payload.pop(f"official_sources_v{version}", None)
            quality_payload.pop(f"source_document_v{version}", None)
        quality_payload.pop("semantic_equivalence_v15", None)
        quality_payload["catalog_version"] = "3.0.0"
        quality_payload["description"] = (
            "ExitGuide cross-app function ontology v3: general application menus, Android system settings, "
            "state-aware destinations, user-confirmed high-risk actions, and long-tail communication, mobility, "
            "telecom, productivity, public-service, IoT, media, work, finance, safety, and health functions."
        )
        for merge_generation in (
            merge_with_base,
            merge_v5_with_base,
            merge_v6_with_base,
            merge_v7_with_base,
            merge_v8_with_base,
            merge_v9_with_base,
            merge_v10_with_base,
            merge_v11_with_base,
            merge_v12_with_base,
            merge_v13_with_base,
            merge_v14_with_base,
            merge_v15_with_base,
        ):
            quality_payload = merge_generation(quality_payload)
        quality_payload = apply_alias_context_overrides(
            strip_alias_context_overrides(quality_payload)
        )
        catalog_path.write_text(json.dumps(quality_payload, ensure_ascii=False), encoding="utf-8")
        quality = audit_navigation_catalog(catalog_path, policy_path)
    assert quality["goal_pattern_collisions"] == []
    assert quality["severity_counts"] == {}, quality
    assert quality["quality_score"] == 100.0

    merged_snapshot = copy.deepcopy(merged)
    merged_again = merge_with_base(merged)
    assert merged == merged_snapshot, "idempotent merge must not mutate an already merged catalog"
    assert merged_again == merged, "merging identical v4 twice must not duplicate data"
    assert validate_v4_data(merged)["materialized"] is True

    partial_collision = copy.deepcopy(base)
    partial_collision["functions"].append(copy.deepcopy(V4_FUNCTIONS[0]))
    try:
        validate_v4_data(partial_collision)
    except V4CatalogValidationError as exc:
        assert "partial v4 ID collision" in str(exc)
    else:
        raise AssertionError("partial v4 function collision must fail")

    changed_collision = copy.deepcopy(merged)
    for item in changed_collision["functions"]:
        if item["function_id"] == V4_FUNCTIONS[0]["function_id"]:
            item["description"] = "conflicting definition"
            break
    try:
        merge_with_base(changed_collision)
    except V4CatalogValidationError as exc:
        assert "collides with different base definition" in str(exc)
    else:
        raise AssertionError("different definition under a v4 ID must fail")

    print(
        "navigation catalog v4 data checks ok: "
        f"functions={stats['functions']} intents={stats['intents']} domains={stats['domains']} "
        f"sources={stats['official_sources']} sourced={stats['sourced_functions']} "
        f"aliases={stats['aliases']} patterns={stats['goal_patterns']} rules={stats['goal_rules']}"
    )


if __name__ == "__main__":
    main()
