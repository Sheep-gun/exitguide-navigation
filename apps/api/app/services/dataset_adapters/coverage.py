from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.services.dataset_adapters.common import sha256_file, write_manifest


METADATA_ONLY_SOURCES = {
    "claudette_corpora_page",
    "opentermsarchive_datasets_page",
    "tosdr_api_index",
}
EQUIVALENT_SOURCES = {
    "kaggle_tosdr_terms_corpus": "tosdr_terms_corpus_github",
}
DEFERRED_SOURCES = {
    "common_crawl_wayback_privacy_terms": "A domain and date scope is required before collection.",
}


def build_source_coverage(
    inventory_path: Path,
    raw_root: Path,
    output_root: Path,
) -> dict[str, object]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    entries = [
        _inventory_entry(source, raw_root, output_root)
        for source in inventory["sources"]
    ]
    supplemental = _supplemental_entries(output_root)
    status_counts = Counter(entry["status"] for entry in [*entries, *supplemental])
    report = {
        "schema_version": "1.0",
        "decision_method": "filesystem_inventory_manifest_inspection_and_developer_confirmation",
        "ai_used": False,
        "inventory": {
            "name": inventory_path.name,
            "bytes": inventory_path.stat().st_size,
            "sha256": sha256_file(inventory_path),
        },
        "source_count": len(entries),
        "supplemental_source_count": len(supplemental),
        "status_counts": dict(sorted(status_counts.items())),
        "sources": entries,
        "supplemental_sources": supplemental,
    }
    write_manifest(output_root / "source-coverage.json", report)
    return report


def _inventory_entry(
    source: dict[str, object],
    raw_root: Path,
    output_root: Path,
) -> dict[str, object]:
    source_id = str(source["id"])
    source_dir = raw_root / source_id
    files = sorted(path for path in source_dir.rglob("*") if path.is_file()) if source_dir.is_dir() else []
    manifest_path = output_root / source_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else None

    if manifest and int(manifest.get("document_count", 0)) > 0:
        status = "full_text_normalized"
        reason = "All selected full-text records were converted to staging JSONL."
    elif manifest:
        status = str(manifest.get("status", "metadata_or_auxiliary_normalized"))
        reason = str(manifest.get("reason", "The source has no directly usable policy full text."))
    elif source_id in METADATA_ONLY_SOURCES and files:
        status = "metadata_collected"
        reason = "The collected source describes another corpus or API and contains no bulk full text."
    elif source_id in EQUIVALENT_SOURCES:
        status = "source_absent_equivalent_normalized"
        reason = f"The account-gated copy is absent; {EQUIVALENT_SOURCES[source_id]} is normalized."
    elif source_id in DEFERRED_SOURCES:
        status = "deferred_scope_required"
        reason = DEFERRED_SOURCES[source_id]
    elif files:
        status = "raw_present_not_normalized"
        reason = "Raw files are present but no normalized manifest exists."
    else:
        status = "source_absent"
        reason = "No local raw files or normalized manifest were found."

    result: dict[str, object] = {
        "source_id": source_id,
        "name": source.get("name", source_id),
        "category": source.get("category", ""),
        "status": status,
        "reason": reason,
        "raw_file_count": len(files),
        "raw_bytes": sum(path.stat().st_size for path in files),
        "normalized_manifest": manifest_path.name if manifest else None,
    }
    if manifest:
        result["normalized_count"] = int(
            manifest.get("document_count", manifest.get("record_count", manifest.get("row_count", 0)))
        )
        result["review_status"] = manifest.get("review_status", manifest.get("status", ""))
        result["output"] = manifest.get("output")
    return result


def _supplemental_entries(output_root: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    source_id = "open_terms_archive_contrib"
    manifest_path = output_root / source_id / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result.append(
            {
                "source_id": source_id,
                "name": "Open Terms Archive contrib collection",
                "status": "full_text_normalized",
                "reason": "User-downloaded full archive was converted to latest document versions.",
                "normalized_count": int(manifest["document_count"]),
                "review_status": manifest["review_status"],
                "output": manifest["output"],
            }
        )
    return result
