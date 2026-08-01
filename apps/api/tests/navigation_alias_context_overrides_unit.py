from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
API_ROOT = ROOT / "apps" / "api"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from navigation_alias_context_overrides import (  # noqa: E402
    OVERRIDE_VERSION,
    _BRAND_MARKERS,
    _COORDINATE_RE,
    _canonical_payload_sha256,
    _same_normalized_phrase,
    apply_alias_context_overrides,
    build_development_fixture,
    evaluate_fixture_runtime,
    normalize_text,
    strip_alias_context_overrides,
)

from app.services.navigation_catalog_quality import audit_navigation_catalog  # noqa: E402


CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-alias-collisions.v1.json"
)
POLICY_PATH = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
SAFETY_FIELDS = {
    "risk_level",
    "automation_policy",
    "terminal",
    "state_changing",
    "node_kind",
    "stop_policy",
    "role_hints",
    "state_cues",
    "risk_cues",
    "scope",
}


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> None:
    raw_catalog = CATALOG_PATH.read_text(encoding="utf-8")
    source = json.loads(raw_catalog)
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert source["catalog_version"] == "15.0.0"
    assert len(source["functions"]) == 2866
    assert len(source["intents"]) == 2660
    assert len({str(item["domain"]) for item in source["functions"]}) == 179

    assert fixture["schema_version"] == 1
    assert fixture["fixture_version"] == "1.0.0"
    assert fixture["split"] == "development_alias_collisions_v1"
    assert fixture["frozen"] is True
    assert fixture["catalog_derived"] is True
    assert fixture["independent_accuracy_claim"] is False
    assert fixture["tuning_allowed"] is True
    assert fixture["source_kind"] == "alias_collision_development"
    assert "must not be reported as independent accuracy" in fixture["description"]
    assert fixture["coverage_contract"] == {
        "collision_group_count": 225,
        "collision_owner_reference_count": 460,
        "unresolved_owner_count": 0,
    }
    assert fixture["unresolved_context_owners"] == []
    assert len(fixture["cases"]) == 939
    assert Counter(str(case["probe_type"]) for case in fixture["cases"]) == {
        "positive_context": 460,
        "contrastive_negative": 479,
    }
    assert len({str(case["case_id"]) for case in fixture["cases"]}) == 939
    for case in fixture["cases"]:
        assert case["source_kind"] == "alias_collision_development"
        assert case["tuning_allowed"] is True
        assert "not_accuracy_evidence" in case["tags"]
        assert not _COORDINATE_RE.search(str(case["nearby_text"]))
        assert not any(
            marker in normalize_text(case["nearby_text"])
            for marker in _BRAND_MARKERS
        )

    already_applied = (
        str(source.get("alias_context_overrides", {}).get("version", ""))
        == OVERRIDE_VERSION
    )
    fixture_source_sha = str(fixture["source_catalog"]["canonical_sha256"])
    fixture_baseline_sha = str(fixture["baseline"]["catalog_sha256"])
    assert len(fixture_source_sha) == 64 and all(character in "0123456789abcdef" for character in fixture_source_sha)
    assert len(fixture_baseline_sha) == 64 and all(character in "0123456789abcdef" for character in fixture_baseline_sha)
    current_source_sha = _canonical_payload_sha256(source)
    if not already_applied and current_source_sha == fixture_source_sha:
        # The generated inputs and pre-override top-1 outputs are a fixed
        # snapshot, so later context tuning cannot silently rewrite its own
        # benchmark.
        regenerated = build_development_fixture(source)
        assert _canonical_json(regenerated["cases"]) == _canonical_json(
            [
                {key: value for key, value in case.items() if not key.startswith("baseline_")}
                for case in fixture["cases"]
            ]
        )
        assert fixture["source_catalog"]["canonical_sha256"] == current_source_sha
        assert fixture["baseline"]["catalog_sha256"] == hashlib.sha256(
            raw_catalog.encode("utf-8")
        ).hexdigest()
    # Once later ontology packs are materialized, this fixture intentionally
    # remains a frozen v6 development snapshot.  Never regenerate it from the
    # newer canonical catalog: doing so would let the benchmark rewrite itself.
    baseline_correct = sum(bool(case["baseline_correct"]) for case in fixture["cases"])
    assert baseline_correct == fixture["baseline"]["correct"]
    assert fixture["baseline"]["total"] == 939

    first = apply_alias_context_overrides(source)
    second = apply_alias_context_overrides(first)
    assert _canonical_json(first) == _canonical_json(second)
    metadata = first["alias_context_overrides"]
    assert metadata["version"] == OVERRIDE_VERSION
    assert len(str(metadata["source_catalog_sha256"])) == 64
    assert all(character in "0123456789abcdef" for character in str(metadata["source_catalog_sha256"]))
    assert metadata["collision_group_count"] >= 225
    assert metadata["guarded_owner_pair_count"] >= 460
    assert metadata["positive_context_addition_count"] > 0
    assert metadata["negative_context_addition_count"] > 0
    ledger = metadata["context_additions"]
    assert ledger == sorted(ledger, key=lambda item: str(item["function_id"]))
    assert sum(len(item["positive_context"]) for item in ledger) == metadata[
        "positive_context_addition_count"
    ]
    assert sum(len(item["negative_context"]) for item in ledger) == metadata[
        "negative_context_addition_count"
    ]
    assert metadata["constraints"] == {
        "aliases_added": 0,
        "goal_sentences_copied": 0,
        "app_names_added": 0,
        "coordinates_added": 0,
    }
    functions_by_id = {
        str(item["function_id"]): item for item in first["functions"]
    }
    for entry in ledger:
        function = functions_by_id[str(entry["function_id"])]
        own_aliases = {
            normalize_text(alias)
            for aliases in function.get("aliases", {}).values()
            for alias in aliases
        }
        assert not [
            value
            for value in entry["negative_context"]
            if any(_same_normalized_phrase(value, alias) for alias in own_aliases)
        ]

    stripped = strip_alias_context_overrides(first)
    assert "alias_context_overrides" not in stripped
    reapplied = apply_alias_context_overrides(stripped)
    assert _canonical_json(reapplied) == _canonical_json(first)

    # Goal resolution and all safety policy are byte-identical when applying
    # from the pre-override source.  A materialized canonical catalog carries
    # the source hash above so this proof remains tied to the fixed snapshot.
    assert first["intents"] == source["intents"]
    before_functions = {str(item["function_id"]): item for item in source["functions"]}
    after_functions = {str(item["function_id"]): item for item in first["functions"]}
    assert list(before_functions) == list(after_functions)
    assert len(after_functions) == 2866
    for function_id, before in before_functions.items():
        after = after_functions[function_id]
        assert before["aliases"] == after["aliases"]
        if not already_applied:
            assert {field: before.get(field) for field in SAFETY_FIELDS} == {
                field: after.get(field) for field in SAFETY_FIELDS
            }
            assert {
                key: value
                for key, value in before.items()
                if key not in {"positive_context", "negative_context"}
            } == {
                key: value
                for key, value in after.items()
                if key not in {"positive_context", "negative_context"}
            }
        for field in ("positive_context", "negative_context"):
            before_values = {normalize_text(value) for value in before.get(field, [])}
            additions = [
                str(value)
                for value in after.get(field, [])
                if normalize_text(value) not in before_values
            ]
            assert all(not _COORDINATE_RE.search(value) for value in additions)
            assert all(
                not any(marker in normalize_text(value) for marker in _BRAND_MARKERS)
                for value in additions
            )

    with TemporaryDirectory(prefix="egl-alias-context-unit-") as temporary_directory:
        generated_catalog = Path(temporary_directory) / "catalog.json"
        generated_catalog.write_text(
            json.dumps(first, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        quality = audit_navigation_catalog(generated_catalog, POLICY_PATH)
        assert quality["status"] == "pass"
        assert quality["quality_score"] == 100.0
        assert quality["totals"]["function_count"] == 2866
        assert quality["totals"]["intent_count"] == 2660

    report = evaluate_fixture_runtime(fixture, catalog_payload=first)
    assert report["total"] == 939
    assert report["accuracy"] >= 0.98
    assert report["correct"] > fixture["baseline"]["correct"]
    assert report["by_probe_type"]["positive_context"]["accuracy"] >= 0.98
    assert report["by_probe_type"]["contrastive_negative"]["accuracy"] >= 0.98
    print(
        "navigation alias-context override checks ok: "
        f"groups=225 probes=939 baseline={fixture['baseline']['correct']}/939 "
        f"after={report['correct']}/939 ({report['accuracy']:.2%}) "
        f"positive={report['by_probe_type']['positive_context']['accuracy']:.2%} "
        f"negative={report['by_probe_type']['contrastive_negative']['accuracy']:.2%} "
        f"quality={quality['quality_score']} idempotent=true"
    )


if __name__ == "__main__":
    main()
