from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.services.dataset_adapters.common import sha256_file, write_manifest


SUPPLEMENTAL_SOURCE_IDS = {"open_terms_archive_contrib"}


def load_source_roles(role_path: Path, inventory_path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(role_path.read_text(encoding="utf-8"))
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    allowed_kinds = set(payload["source_kinds"])
    allowed_roles = set(payload["processing_roles"])
    allowed_strategies = set(payload["sectioning_strategies"])
    allowed_policies = set(payload["rag_policies"])
    entries: dict[str, dict[str, object]] = {}

    for entry in payload["sources"]:
        source_id = str(entry.get("source_id", "")).strip()
        if not source_id:
            raise ValueError("Source role entry is missing source_id")
        if source_id in entries:
            raise ValueError(f"Duplicate source role entry: {source_id}")
        kinds = set(entry.get("source_kinds", []))
        roles = set(entry.get("processing_roles", []))
        strategy = str(entry.get("sectioning_strategy", ""))
        policy = str(entry.get("rag_policy", ""))
        reason = str(entry.get("reason", "")).strip()
        if not kinds or not kinds <= allowed_kinds:
            raise ValueError(f"Invalid source_kinds for {source_id}: {sorted(kinds)}")
        if not roles or not roles <= allowed_roles:
            raise ValueError(f"Invalid processing_roles for {source_id}: {sorted(roles)}")
        if strategy not in allowed_strategies:
            raise ValueError(f"Invalid sectioning_strategy for {source_id}: {strategy}")
        if policy not in allowed_policies:
            raise ValueError(f"Invalid rag_policy for {source_id}: {policy}")
        if not reason:
            raise ValueError(f"Missing role reason for {source_id}")
        if "corpus_candidate" in roles and policy != "review_required":
            raise ValueError(f"Corpus candidate must require review: {source_id}")
        if "corpus_candidate" in roles and "excluded_from_rag" in roles:
            raise ValueError(f"Source cannot be both corpus candidate and excluded: {source_id}")
        if policy == "not_eligible" and "corpus_candidate" in roles:
            raise ValueError(f"Ineligible source cannot be a corpus candidate: {source_id}")
        entries[source_id] = entry

    inventory_ids = {str(source["id"]) for source in inventory["sources"]}
    expected_ids = inventory_ids | SUPPLEMENTAL_SOURCE_IDS
    missing = sorted(expected_ids - entries.keys())
    unknown = sorted(entries.keys() - expected_ids)
    if missing or unknown:
        raise ValueError(f"Source role coverage mismatch: missing={missing}, unknown={unknown}")
    return entries


def build_source_role_report(
    role_path: Path,
    inventory_path: Path,
    output_path: Path,
) -> dict[str, object]:
    entries = load_source_roles(role_path, inventory_path)
    kind_counts = Counter(kind for entry in entries.values() for kind in entry["source_kinds"])
    role_counts = Counter(role for entry in entries.values() for role in entry["processing_roles"])
    strategy_counts = Counter(str(entry["sectioning_strategy"]) for entry in entries.values())
    policy_counts = Counter(str(entry["rag_policy"]) for entry in entries.values())
    report = {
        "schema_version": "1.0",
        "decision_method": "developer_defined_source_taxonomy_with_deterministic_validation",
        "ai_used": False,
        "source_count": len(entries),
        "source_kind_counts": dict(sorted(kind_counts.items())),
        "processing_role_counts": dict(sorted(role_counts.items())),
        "sectioning_strategy_counts": dict(sorted(strategy_counts.items())),
        "rag_policy_counts": dict(sorted(policy_counts.items())),
        "role_file": {
            "name": role_path.name,
            "bytes": role_path.stat().st_size,
            "sha256": sha256_file(role_path),
        },
        "inventory_file": {
            "name": inventory_path.name,
            "bytes": inventory_path.stat().st_size,
            "sha256": sha256_file(inventory_path),
        },
        "sources": [entries[source_id] for source_id in sorted(entries)],
    }
    write_manifest(output_path, report)
    return report
