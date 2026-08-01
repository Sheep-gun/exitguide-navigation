import copy
import json
import sys
import tempfile
from pathlib import Path

from app.services.navigation_catalog_quality import audit_navigation_catalog
from app.services.navigation_function_catalog import NavigationFunctionCatalog, validate_catalog_payload
from app.services.navigation_goal_generalization import evaluate_independent_goals


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_catalog_v5_data import (  # noqa: E402
    COLLECTED_ON,
    EXCLUDED_AS_ALREADY_COVERED,
    OFFICIAL_SOURCES,
    REQUIRED_DOMAINS,
    REQUIRED_FUNCTIONS,
    V5CatalogValidationError,
    V5_COMPOSITIONAL_DOMAIN_REQUIRED_TOKENS,
    V5_DOMAIN_REQUIRED_ALIASES,
    V5_ALIAS_OWNERS,
    V5_FUNCTIONS,
    V5_INTENTS,
    V5_PURPOSE_CONCEPTS,
    V5_TOKEN_OWNERS,
    _base_compositional_token_owners,
    _base_goal_inventory,
    _goal_cue_key,
    _materialized_v5_intents,
    _rule_signature,
    _runtime_goal_key,
    build_v5_compositional_probes,
    build_v5_purpose_probes,
    build_v5_source_paraphrase_probes,
    load_base_catalog,
    merge_with_base,
    validate_v5_data,
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


def main() -> None:
    materialized = strip_alias_context_overrides(load_base_catalog())
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
            *V12_FUNCTIONS,
            *V13_FUNCTIONS,
            *V14_FUNCTIONS,
            *V15_FUNCTIONS,
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
            *V12_INTENTS,
            *V13_INTENTS,
            *V14_INTENTS,
            *V15_INTENTS,
        )
    }
    # Remain useful after v5 is promoted into the canonical catalog: rebuild
    # the v4 input and exercise the same non-mutating merge path on every run.
    base = copy.deepcopy(materialized)
    base["functions"] = [
        item
        for item in materialized["functions"]
        if str(item["function_id"]) not in v5_function_ids | later_function_ids
    ]
    base["intents"] = [
        item
        for item in materialized["intents"]
        if str(item["intent_id"]) not in v5_intent_ids | later_intent_ids
    ]
    base.pop("official_sources_v5", None)
    base.pop("official_sources_v6", None)
    base.pop("official_sources_v7", None)
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
    base["catalog_version"] = "4.0.0"
    base["description"] = (
        "ExitGuide cross-app function ontology v3: general application menus, Android system settings, "
        "state-aware destinations, user-confirmed high-risk actions, and long-tail communication, mobility, "
        "telecom, productivity, public-service, IoT, media, work, finance, safety, and health functions. "
        "Broad-services v4 adds browser, messaging, store, Android safety, local-service, commerce, health, "
        "jobs, property, and utility functions."
    )
    base_snapshot = copy.deepcopy(base)
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
    stats = validate_v5_data(base)

    assert stats == {
        "functions": 147,
        "terminal_functions": 136,
        "intents": 136,
        "domains": 11,
        "official_sources": 68,
        "aliases": 2353,
        "goal_patterns": 4331,
        "raw_goal_patterns": 4346,
        "materialized_goal_patterns": 4331,
        "goal_rules": 13556,
        "raw_goal_rules": 13822,
        "materialized_goal_rules": 13556,
        "raw_compositional_rules": 2432,
        "materialized_compositional_rules": 2256,
        "compositional_probes": 805,
        "raw_purpose_rules": 272,
        "materialized_purpose_rules": 271,
        "purpose_probes": 271,
        "raw_source_paraphrase_rules": 1632,
        "materialized_source_paraphrase_rules": 1619,
        "source_paraphrase_probes": 544,
        "state_changing": 82,
        "high_risk": 89,
        "materialized": False,
    }
    assert len(REQUIRED_DOMAINS) == 11
    assert len(REQUIRED_FUNCTIONS) >= 16
    assert REQUIRED_FUNCTIONS <= {str(item["function_id"]) for item in V5_FUNCTIONS}
    assert V5_DOMAIN_REQUIRED_ALIASES == {"notifyme", "referencerange"}
    assert V5_COMPOSITIONAL_DOMAIN_REQUIRED_TOKENS == {"auto"}

    # The expansion is gap-driven rather than count-driven: common concepts
    # already owned by v1-v4 are explicitly excluded instead of duplicated.
    base_function_ids = {str(item["function_id"]) for item in base["functions"]}
    excluded_existing_ids = {
        value.strip()
        for owners in EXCLUDED_AS_ALREADY_COVERED.values()
        for value in owners.split("/")
    }
    assert excluded_existing_ids <= base_function_ids
    assert not (base_function_ids & {str(item["function_id"]) for item in V5_FUNCTIONS})

    official_hosts = {
        "help.doordash.com", "www.opentable.com", "www.airbnb.com",
        "support.google.com", "help.ticketmaster.com", "help.uber.com",
        "www.bankofamerica.com", "info.bankofamerica.com", "www.chase.com",
        "www.login.gov", "travel.state.gov", "egov.uscis.gov", "my.uscis.gov", "www.uscis.gov",
        "www.nhs.uk", "www.va.gov", "slack.com", "www.ups.com",
    }
    from urllib.parse import urlparse

    assert {urlparse(str(source["url"])).netloc for source in OFFICIAL_SOURCES.values()} <= official_hosts
    assert all(source["collected_on"] == COLLECTED_ON for source in OFFICIAL_SOURCES.values())
    assert all(source["evidence_level"] == "official_primary" for source in OFFICIAL_SOURCES.values())
    assert all(source["verified_status"] == 200 for source in OFFICIAL_SOURCES.values())
    assert all(str(source["verification_method"]).strip() for source in OFFICIAL_SOURCES.values())

    known_sources = set(OFFICIAL_SOURCES)
    terminal_ids = {str(item["function_id"]) for item in V5_FUNCTIONS if item["terminal"]}
    assert terminal_ids == {str(item["terminal_function"]) for item in V5_INTENTS}
    assert set(V5_PURPOSE_CONCEPTS) == terminal_ids
    for function_id, by_locale in V5_PURPOSE_CONCEPTS.items():
        assert set(by_locale) == {"ko-KR", "en-US"}
        for locale, rules in by_locale.items():
            assert len(rules) >= 1
            for terms in rules:
                assert 2 <= len(terms) <= 4
                assert len(set(terms)) == len(terms)
                assert all(1 <= len(term.strip()) <= 48 for term in terms)
                assert all("." not in term and "\n" not in term for term in terms)
    used_sources: set[str] = set()
    for function in V5_FUNCTIONS:
        assert function["source_refs"]
        assert set(function["source_refs"]) <= known_sources
        used_sources.update(function["source_refs"])
        assert len(function["aliases"]["ko-KR"]) >= 6
        assert len(function["aliases"]["en-US"]) >= 6
        assert function["positive_context"] and function["negative_context"]
        assert function["role_hints"] and function["state_cues"] and function["risk_cues"]
        if function["state_changing"] or function["risk_level"] == "high":
            assert function["automation_policy"] == "never_auto"
            assert function["stop_policy"] == "before_action"
    assert used_sources == known_sources, "official evidence registry must not contain orphan sources"

    direct_evidence = {
        "food_order.substitution_preferences": "doordash_substitutions",
        "food_order.schedule": "doordash_schedule",
        "ride_hailing.saved_places": "uber_saved_places",
        "ride_hailing.accessible_vehicle": "uber_accessible_vehicle",
        "ride_hailing.rider_pin": "uber_verify_ride",
        "retail_banking.card_pin": "boa_debit_card_faq",
        "retail_banking.direct_deposit": "boa_direct_deposit",
        "government_digital.identity_verify": "login_gov_identity",
        "government_digital.passport_apply": "passport_apply",
        "government_digital.form_filing": "uscis_file_online",
        "government_digital.fee_calculator": "uscis_fee_calculator",
        "healthcare_provider.proxy_access": "nhs_family_access",
        "healthcare_provider.pharmacy_nomination": "nhs_pharmacy",
        "healthcare_provider.fit_note": "nhs_fit_note",
        "healthcare_provider.organ_donation": "nhs_organ_donation",
    }
    by_function_id = {str(item["function_id"]): item for item in V5_FUNCTIONS}
    for function_id, source_id in direct_evidence.items():
        assert source_id in by_function_id[function_id]["source_refs"]

    for intent in V5_INTENTS:
        assert len(intent["patterns_by_locale"]["ko-KR"]) >= 8
        assert len(intent["patterns_by_locale"]["en-US"]) >= 8
        assert len(intent["goal_rules"]) >= 12
        assert intent["route"][-1]["function_id"] == intent["terminal_function"]
        terminal = next(
            item for item in V5_FUNCTIONS if item["function_id"] == intent["terminal_function"]
        )
        if terminal["state_changing"] or terminal["risk_level"] == "high":
            assert intent["desired_state"] == "user_confirmation_required"
            assert intent["terminal_condition"]["stop_policy"] == "stop_before_action"

    merged = merge_with_base(base)
    assert base == base_snapshot, "v5 merge must not mutate its v4 input"
    assert merged["functions"][:len(base["functions"])] == base["functions"]
    assert merged["intents"][:len(base["intents"])] == base["intents"]
    assert len(merged["functions"]) == len(base["functions"]) + len(V5_FUNCTIONS)
    assert len(merged["intents"]) == len(base["intents"]) + len(V5_INTENTS)
    assert merged["catalog_version"] == "5.0.0"
    assert merged["official_sources_v5"] == OFFICIAL_SOURCES
    validate_catalog_payload(merged)

    # The production payload is derived only from raw ontology vocabulary and
    # the reconstructed pre-v5 catalog.  It must be byte-for-byte equivalent
    # to the deterministic filtered intent set.
    expected_intents = _materialized_v5_intents(base)
    expected_by_id = {str(item["intent_id"]): item for item in expected_intents}
    merged_v5_intents = {
        str(item["intent_id"]): item
        for item in merged["intents"]
        if str(item["intent_id"]) in v5_intent_ids
    }
    assert merged_v5_intents == expected_by_id
    assert sum(len(item["goal_rules"]) for item in V5_INTENTS) == stats["raw_goal_rules"]
    assert sum(len(item["goal_rules"]) for item in expected_intents) == stats["materialized_goal_rules"]
    assert stats["materialized_goal_rules"] < stats["raw_goal_rules"]
    assert sum(len(item["patterns"]) for item in V5_INTENTS) == stats["raw_goal_patterns"]
    assert sum(len(item["patterns"]) for item in expected_intents) == stats["materialized_goal_patterns"]
    assert stats["materialized_goal_patterns"] < stats["raw_goal_patterns"]

    base_cues, base_pattern_keys, base_rule_signatures = _base_goal_inventory(base)
    base_token_owners = _base_compositional_token_owners(base)
    materialized_pattern_owners: dict[str, set[str]] = {}
    materialized_rule_owners: dict[tuple[str, ...], set[str]] = {}
    terminal_rule_kinds: dict[str, set[tuple[str, str]]] = {}
    for intent in expected_intents:
        intent_id = str(intent["intent_id"])
        terminal = str(intent["terminal_function"])
        for pattern in intent["patterns"]:
            key = _runtime_goal_key(pattern)
            assert key not in base_pattern_keys
            cue = _goal_cue_key(pattern)
            assert not (len(V5_ALIAS_OWNERS.get(cue, ())) == 1 and cue in base_cues)
            materialized_pattern_owners.setdefault(key, set()).add(intent_id)
        for rule in intent["goal_rules"]:
            signature = _rule_signature(rule)
            assert signature and signature not in base_rule_signatures
            materialized_rule_owners.setdefault(signature, set()).add(intent_id)
            kind = str(rule["rule_kind"])
            locale = str(rule["v5_locale"])
            alias_key = str(rule["v5_alias_key"])
            terminal_rule_kinds.setdefault(terminal, set()).add((locale, kind))
            if kind in {"v5_distinctive_alias", "v5_request_framing"}:
                assert len(V5_ALIAS_OWNERS[alias_key]) == 1
                assert alias_key not in base_cues
            if (
                kind.startswith("v5_compositional_")
                or kind in {
                    "v5_consequence_context",
                    "v5_purpose_consequence",
                    "v5_source_paraphrase",
                }
            ):
                discriminative = tuple(dict.fromkeys(rule["v5_discriminative_keys"]))
                negative_context_keys = list(rule["v5_negative_context_keys"])
                assert negative_context_keys == sorted(set(negative_context_keys))
                assert len(discriminative) >= 2
                assert len(rule["all_of"]) >= 2
                assert all(key in V5_TOKEN_OWNERS for key in discriminative)
                assert not set(discriminative).intersection(negative_context_keys)
                prior_owners: set[str] | None = None
                for key in discriminative:
                    owners = set(base_token_owners.get(str(key), ()))
                    prior_owners = owners if prior_owners is None else prior_owners & owners
                assert not prior_owners
                if kind in {
                    "v5_compositional_alias",
                    "v5_consequence_context",
                    "v5_purpose_consequence",
                }:
                    assert rule["v5_unqualified"] is True
                if kind == "v5_consequence_context":
                    assert len(rule["v5_positive_context_keys"]) >= 1
                if kind == "v5_purpose_consequence":
                    assert rule["v5_semantic_source"] == "reviewed_purpose_consequence_ontology"
                    assert 2 <= len(rule["all_of"]) <= 4
                if kind == "v5_source_paraphrase":
                    assert rule["v5_semantic_source"] == (
                        "official_source_registry_and_reviewed_function_metadata"
                    )
                    if rule["v5_unqualified"] is False:
                        assert rule["v5_domain_key"]
    assert all(len(owners) == 1 for owners in materialized_pattern_owners.values())
    assert all(len(owners) == 1 for owners in materialized_rule_owners.values())
    for terminal in terminal_ids:
        for locale in ("ko-KR", "en-US"):
            assert (locale, "v5_distinctive_alias") in terminal_rule_kinds[terminal]
            assert (locale, "v5_request_framing") in terminal_rule_kinds[terminal]

    compositional_probes = build_v5_compositional_probes(base)
    assert len(compositional_probes) == stats["compositional_probes"] == 805
    assert {str(item["terminal_function"]) for item in compositional_probes} == terminal_ids
    assert all(item["dropped_source_terms"] > 0 for item in compositional_probes)
    assert all(item["reordered"] is True for item in compositional_probes)
    assert sum(bool(item["uses_positive_context"]) for item in compositional_probes) == 270
    for locale in ("ko-KR", "en-US"):
        assert {
            str(item["terminal_function"])
            for item in compositional_probes
            if item["locale"] == locale
        } == terminal_ids

    purpose_probes = build_v5_purpose_probes(base)
    assert len(purpose_probes) == stats["purpose_probes"] == 271
    assert all(item["reordered"] is True for item in purpose_probes)
    assert all(
        item["semantic_source"] == "reviewed_purpose_consequence_ontology"
        for item in purpose_probes
    )
    assert {str(item["terminal_function"]) for item in purpose_probes} == terminal_ids

    source_paraphrase_probes = build_v5_source_paraphrase_probes(base)
    assert len(source_paraphrase_probes) == stats["source_paraphrase_probes"] == 544
    assert all(item["reordered"] is True for item in source_paraphrase_probes)
    assert all(
        item["semantic_source"]
        == "official_source_registry_and_reviewed_function_metadata"
        for item in source_paraphrase_probes
    )
    source_probe_counts: dict[tuple[str, str], int] = {}
    for probe in source_paraphrase_probes:
        key = (str(probe["terminal_function"]), str(probe["locale"]))
        source_probe_counts[key] = source_probe_counts.get(key, 0) + 1
    assert set(source_probe_counts) == {
        (terminal, locale)
        for terminal in terminal_ids
        for locale in ("ko-KR", "en-US")
    }
    assert set(source_probe_counts.values()) == {2}

    # Known cross-generation aliases remain useful as screen labels, but may
    # not become unqualified goal-owner rules in v5.
    for blocked_alias in ("visit record", "door code", "price range", "courier note"):
        blocked_key = _goal_cue_key(blocked_alias)
        assert blocked_key in base_cues
        assert not any(
            rule["v5_alias_key"] == blocked_key
            and rule["rule_kind"] in {"v5_distinctive_alias", "v5_request_framing"}
            for intent in expected_intents
            for rule in intent["goal_rules"]
        )

    policy_path = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
    with tempfile.TemporaryDirectory(prefix="exitguide-v5-audit-") as temp_dir:
        catalog_path = Path(temp_dir) / "catalog.json"
        quality_path = Path(temp_dir) / "catalog-with-v7.json"
        base_path = Path(temp_dir) / "pre-v5-catalog.json"
        catalog_path.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
        # The monotonic quality policy tracks the current canonical generation.
        # Audit the current v5 definitions with every later generation layered
        # in order, while v4/v5 remain isolated for winner-regression checks.
        full_quality_payload = merge_v15_with_base(
            merge_v14_with_base(
                merge_v13_with_base(
                    merge_v12_with_base(
                        merge_v11_with_base(
                            merge_v10_with_base(
                                merge_v9_with_base(
                                    merge_v8_with_base(merge_v7_with_base(merge_v6_with_base(merged)))
                                )
                            )
                        )
                    )
                )
            )
        )
        quality_path.write_text(
            json.dumps(
                apply_alias_context_overrides(
                    strip_alias_context_overrides(full_quality_payload)
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        base_path.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
        quality = audit_navigation_catalog(quality_path, policy_path)
        baseline_catalog = NavigationFunctionCatalog(Path(temp_dir) / "pre-v5.sqlite", base_path)
        production_catalog = NavigationFunctionCatalog(Path(temp_dir) / "v5.sqlite", catalog_path)

        # Every reviewed pre-v5 pattern must keep exactly the same winner after
        # v5 is added.  This exercises runtime precedence, not merely static
        # string-set disjointness.
        pre_v5_pattern_count = 0
        for intent in base["intents"]:
            for pattern in intent.get("patterns", []):
                pre_v5_pattern_count += 1
                before = baseline_catalog.plan_goal(str(pattern))
                after = production_catalog.plan_goal(str(pattern))
                assert (after.intent, after.terminal_function) == (
                    before.intent,
                    before.terminal_function,
                )
        assert pre_v5_pattern_count == 6407

        # Exercise one generated alias and one request framing per terminal
        # and locale.  The inputs are assembled from ontology rules only.
        for intent in expected_intents:
            for locale in ("ko-KR", "en-US"):
                for kind in ("v5_distinctive_alias", "v5_request_framing"):
                    rule = next(
                        item
                        for item in intent["goal_rules"]
                        if item["v5_locale"] == locale and item["rule_kind"] == kind
                    )
                    plan = production_catalog.plan_goal(" ".join(rule["all_of"]))
                    assert plan.terminal_function == intent["terminal_function"]

        # Drop/reorder/stem/context probes are generated from the ontology
        # itself.  They deliberately avoid complete alias substrings.
        for probe in compositional_probes:
            plan = production_catalog.plan_goal(str(probe["goal"]))
            assert plan.terminal_function == probe["terminal_function"]

        # Purpose probes use the same atoms in a different order and neutral
        # framing.  This proves the rules are compositional rather than one
        # copied natural-language request.
        for probe in purpose_probes:
            plan = production_catalog.plan_goal(str(probe["goal"]))
            assert plan.terminal_function == probe["terminal_function"]

        for probe in source_paraphrase_probes:
            plan = production_catalog.plan_goal(str(probe["goal"]))
            assert plan.terminal_function == probe["terminal_function"]

        # All independent suites that predate v5 must retain their winner.
        # The v5 holdout is intentionally excluded here: this is a regression
        # check, not a claim about unseen v5 performance.
        independent_fixtures = [
            ROOT / "fixtures" / "navigation" / "db-gym" / filename
            for filename in (
                "public-web.v1.json",
                "public-insurance.v1.json",
                "public-productivity-system.v1.json",
                "independent-core.v2.json",
                "alias-collision-adversarial.v2.json",
                "independent-coverage.v2.json",
                "independent-recovery.v2.json",
                "independent-long-tail-v3.json",
                "independent-broad-services-v4.json",
            )
        ]
        regression = evaluate_independent_goals(
            catalog_path=catalog_path,
            fixture_paths=independent_fixtures,
        )
        assert regression["total"] == 784
        assert regression["correct"] == 784
        assert regression["failures"] == []
    assert quality["quality_score"] == 100.0
    assert quality["severity_counts"] == {}
    assert quality["goal_pattern_collisions"] == []

    merged_snapshot = copy.deepcopy(merged)
    merged_again = merge_with_base(merged)
    assert merged == merged_snapshot
    assert merged_again == merged
    assert validate_v5_data(merged)["materialized"] is True

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V5_FUNCTIONS[0]))
    try:
        validate_v5_data(partial)
    except V5CatalogValidationError as exc:
        assert "partial v5 ID collision" in str(exc)
    else:
        raise AssertionError("partial v5 materialization must fail closed")

    changed = copy.deepcopy(merged)
    for item in changed["functions"]:
        if item["function_id"] == V5_FUNCTIONS[0]["function_id"]:
            item["description"] = "conflicting v5 definition"
            break
    try:
        merge_with_base(changed)
    except V5CatalogValidationError as exc:
        assert "different v5 definition" in str(exc)
    else:
        raise AssertionError("changed materialized definition must fail closed")

    changed_intent = copy.deepcopy(merged)
    for item in changed_intent["intents"]:
        if item["intent_id"] in v5_intent_ids:
            item["goal_rules"] = item["goal_rules"][:-1]
            break
    try:
        merge_with_base(changed_intent)
    except V5CatalogValidationError as exc:
        assert "different v5 definition" in str(exc)
    else:
        raise AssertionError("changed materialized intent must fail closed")

    changed_metadata = copy.deepcopy(merged)
    changed_metadata["catalog_version"] = "5.0.0-modified"
    try:
        merge_with_base(changed_metadata)
    except V5CatalogValidationError as exc:
        assert "different v5 definition" in str(exc)
    else:
        raise AssertionError("changed v5 materialization metadata must fail closed")

    print(
        "navigation catalog v5 data checks ok: "
        f"functions={stats['functions']} terminals={stats['terminal_functions']} "
        f"intents={stats['intents']} domains={stats['domains']} sources={stats['official_sources']} "
        f"aliases={stats['aliases']} patterns={stats['goal_patterns']} "
        f"rules_raw={stats['raw_goal_rules']} rules_materialized={stats['materialized_goal_rules']} "
        f"compositional_raw={stats['raw_compositional_rules']} "
        f"compositional_materialized={stats['materialized_compositional_rules']} "
        f"purpose={stats['materialized_purpose_rules']} "
        f"source_paraphrase={stats['materialized_source_paraphrase_rules']} "
        f"probes={stats['compositional_probes']}+{stats['purpose_probes']}+"
        f"{stats['source_paraphrase_probes']} "
        "pre_v5_patterns=6407 independent_regression=784/784"
    )


if __name__ == "__main__":
    main()
