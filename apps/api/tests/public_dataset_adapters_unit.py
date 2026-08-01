import json
import sqlite3
import struct
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.dataset_adapters.coverage import build_source_coverage
from app.services.dataset_adapters.cli import _validation_targets
from app.services.dataset_adapters.ftc_standard_terms import _decode_hwp_paragraph
from app.services.dataset_adapters.hf_terms import convert_hf_online_terms
from app.services.dataset_adapters.princeton import convert_princeton_policies
from app.services.dataset_adapters.text_utils import html_to_text
from app.services.dataset_adapters.validation import validate_normalized_jsonl


def main() -> None:
    _check_text_extraction()
    targets = _validation_targets(include_princeton=True)
    assert len(targets) == 18
    assert len({f"{source_id}:{data_file}" for source_id, data_file, _ in targets}) == 18
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _check_hf_conversion(root)
        _check_princeton_conversion(root)
        _check_coverage(root)
    print("public dataset adapter checks ok")


def _check_text_extraction() -> None:
    html = "<main><h1>Terms</h1><script>hidden()</script><p>Visible &amp; safe</p></main>"
    extracted = html_to_text(html)
    assert [line for line in extracted.splitlines() if line] == ["Terms", "Visible & safe"]
    assert "hidden" not in extracted

    units = [ord("앞"), 2, ord("d"), ord("c"), ord("e"), ord("s"), 0, 0, 0, ord("뒤")]
    payload = struct.pack(f"<{len(units)}H", *units)
    assert _decode_hwp_paragraph(payload) == "앞뒤"


def _check_hf_conversion(root: Path) -> None:
    source_dir = root / "raw" / "hf_online_terms_of_service"
    source_dir.mkdir(parents=True)
    for split in ("train", "validation", "test"):
        row = {
            "sentence": f"{split} clause",
            "language": "en",
            "unfairness_level": "clearly fair",
            "company": "Example",
            "all_topics": ["use"],
        }
        (source_dir / f"{split}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    output_root = root / "normalized"
    manifest = convert_hf_online_terms(source_dir, output_root)
    assert manifest["document_count"] == 3
    validation = validate_normalized_jsonl(
        output_root / "hf_online_terms_of_service" / "segments.jsonl",
        output_root / "hf_online_terms_of_service" / "manifest.json",
        "hf_online_terms_of_service",
    )
    assert validation["record_type_counts"] == {"terms_clause": 3}


def _check_princeton_conversion(root: Path) -> None:
    database_path = root / "princeton.sqlite"
    database = sqlite3.connect(database_path)
    database.executescript(
        """
        CREATE TABLE policy_texts (
            id INTEGER PRIMARY KEY, policy_text TEXT, flesch_kincaid REAL,
            smog REAL, flesch_ease TEXT, length INTEGER, sha1 TEXT, simhash TEXT
        );
        CREATE TABLE sites (id INTEGER PRIMARY KEY, domain TEXT, categories TEXT);
        CREATE TABLE policy_snapshots (
            id INTEGER PRIMARY KEY, site_id INTEGER, homepage_snapshot_url TEXT,
            policy_snapshot_url TEXT, policy_url TEXT, year INTEGER, phase TEXT,
            policy_text_id INTEGER, file_type TEXT, policy_title TEXT,
            classifier_probability REAL, analysis_subcorpus INTEGER
        );
        INSERT INTO policy_texts VALUES (1, 'Policy text', 1.0, 2.0, 'easy', 11, 'sha1', 'sim');
        INSERT INTO sites VALUES (1, 'example.test', 'news');
        INSERT INTO policy_snapshots VALUES
            (1, 1, 'home1', 'snap1', 'policy1', 2001, 'A', 1, 'html', 'Privacy', 0.9, 1),
            (2, 1, 'home2', 'snap2', 'policy2', 2002, 'B', 1, 'html', 'Privacy', 0.8, 1);
        """
    )
    database.commit()
    database.close()

    output_root = root / "princeton-output"
    manifest = convert_princeton_policies(database_path, output_root)
    assert manifest["document_count"] == 1
    assert manifest["snapshot_count"] == 2
    records = _read_jsonl(output_root / "princeton_leuven_privacy_policies" / "documents.jsonl")
    assert records[0]["version_at"] == "2001-2002"
    assert records[0]["provenance"]["source_database"] == "princeton.sqlite"
    assert len(records[0]["annotations"]) == 3


def _check_coverage(root: Path) -> None:
    inventory = root / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "sources": [
                    {"id": "hf_online_terms_of_service", "name": "HF", "category": "terms"},
                    {"id": "tosdr_api_index", "name": "API", "category": "metadata"},
                    {"id": "common_crawl_wayback_privacy_terms", "name": "CC", "category": "archive"},
                ]
            }
        ),
        encoding="utf-8",
    )
    raw_root = root / "raw"
    metadata_dir = raw_root / "tosdr_api_index"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "page.html").write_text("metadata", encoding="utf-8")
    report = build_source_coverage(inventory, raw_root, root / "normalized")
    statuses = {entry["source_id"]: entry["status"] for entry in report["sources"]}
    assert statuses["hf_online_terms_of_service"] == "full_text_normalized"
    assert statuses["tosdr_api_index"] == "metadata_collected"
    assert statuses["common_crawl_wayback_privacy_terms"] == "deferred_scope_required"
    assert report["ai_used"] is False


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    main()
