from __future__ import annotations

import ast
import csv
import io
import json
import os
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator
from xml.etree import ElementTree
from zipfile import ZipFile, ZipInfo

import yaml

from app.services.dataset_adapters.common import (
    STAGING_SCHEMA_VERSION,
    NormalizedTermsRecord,
    input_file_descriptor,
    normalize_text,
    sha256_file,
    sha256_text,
    stable_record_id,
    write_jsonl,
    write_manifest,
)
from app.services.dataset_adapters.text_utils import decode_bytes, html_to_text


SOURCE_URLS = {
    "usableprivacy_opp_115": "https://usableprivacy.org/data",
    "usableprivacy_app_350": "https://usableprivacy.org/data",
    "usableprivacy_mapp": "https://usableprivacy.org/data",
    "usableprivacy_maps_policies": "https://usableprivacy.org/data",
    "usableprivacy_optoutchoice_2017": "https://usableprivacy.org/data",
    "usableprivacy_optoutchoice_2020": "https://usableprivacy.org/data",
    "usableprivacy_acl_coling_2014": "https://usableprivacy.org/data",
    "usableprivacy_opp115_gdpr": "https://usableprivacy.org/data",
    "usableprivacy_fsdk": "https://usableprivacy.org/data",
}
LICENSE_NOTES = "See the source archive license and documentation; keep as needs_review until reuse terms are confirmed."


def convert_privacy_corpora(raw_root: Path, output_root: Path) -> dict[str, object]:
    results: dict[str, object] = {}
    results["usableprivacy_opp_115"] = _convert_zip_documents(
        raw_root / "usableprivacy_opp_115",
        output_root,
        "usableprivacy_opp_115",
        lambda name: name.startswith("OPP-115/sanitized_policies/") and name.endswith(".html"),
        _html_entry,
        _service_from_numbered_name,
        lambda name: "en",
    )
    results["usableprivacy_mapp"] = _convert_zip_documents(
        raw_root / "usableprivacy_mapp",
        output_root,
        "usableprivacy_mapp",
        lambda name: "sanitized_policies/" in name.lower() and name.endswith(".txt"),
        _text_entry,
        _service_from_numbered_name,
        lambda name: "de" if "german_" in name.lower() else "en",
    )
    results["usableprivacy_optoutchoice_2017"] = _convert_zip_documents(
        raw_root / "usableprivacy_optoutchoice_2017",
        output_root,
        "usableprivacy_optoutchoice_2017",
        lambda name: "/SanitizedPrivacyPolicies/" in name and name.endswith(".html"),
        _html_entry,
        _service_from_numbered_name,
        lambda name: "en",
    )
    results["usableprivacy_acl_coling_2014"] = _convert_zip_documents(
        raw_root / "usableprivacy_acl_coling_2014",
        output_root,
        "usableprivacy_acl_coling_2014",
        lambda name: name.startswith("corpus/") and name.endswith(".xml"),
        _xml_entry,
        _service_from_numbered_name,
        lambda name: "en",
    )
    results["usableprivacy_app_350"] = convert_app350(raw_root / "usableprivacy_app_350", output_root)
    results["usableprivacy_optoutchoice_2020"] = convert_optout2020(
        raw_root / "usableprivacy_optoutchoice_2020", output_root
    )
    results["usableprivacy_maps_policies"] = convert_maps_targets(
        raw_root / "usableprivacy_maps_policies", output_root
    )
    results["usableprivacy_opp115_gdpr"] = convert_gdpr_mappings(
        raw_root / "usableprivacy_opp115_gdpr", output_root
    )
    results["usableprivacy_fsdk"] = profile_fsdk(raw_root / "usableprivacy_fsdk", output_root)
    return results


def _convert_zip_documents(
    source_dir: Path,
    output_root: Path,
    source_id: str,
    predicate: Callable[[str], bool],
    extractor: Callable[[bytes], str],
    service_parser: Callable[[str], str],
    locale_parser: Callable[[str], str],
) -> dict[str, object]:
    archive_path = _single_zip(source_dir)
    output_dir = output_root / source_id
    output_path = output_dir / "documents.jsonl"
    content_hashes: set[str] = set()
    locale_counts: Counter[str] = Counter()

    with ZipFile(archive_path) as archive:
        entries = sorted(
            [
                entry
                for entry in archive.infolist()
                if not entry.is_dir() and "__MACOSX" not in entry.filename and predicate(entry.filename)
            ],
            key=lambda entry: entry.filename,
        )
        if not entries:
            raise ValueError(f"No policy entries found in {archive_path}")

        def records() -> Iterator[NormalizedTermsRecord]:
            for entry in entries:
                text = normalize_text(extractor(archive.read(entry)))
                if not text:
                    raise ValueError(f"Empty policy text: {entry.filename}")
                locale = locale_parser(entry.filename)
                record = _privacy_document(
                    source_id=source_id,
                    locator=entry.filename,
                    service_name=service_parser(entry.filename),
                    locale=locale,
                    text=text,
                    provenance={
                        "source_url": SOURCE_URLS[source_id],
                        "source_archive": archive_path.name,
                        "source_entry": entry.filename,
                    },
                )
                locale_counts[locale] += 1
                content_hashes.add(record.content_sha256)
                yield record

        document_count, output_bytes = write_jsonl(records(), output_path)

    manifest = _document_manifest(
        source_id,
        archive_path,
        output_path,
        output_bytes,
        document_count,
        content_hashes,
        {"locale_counts": dict(sorted(locale_counts.items()))},
    )
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def convert_app350(source_dir: Path, output_root: Path) -> dict[str, object]:
    source_id = "usableprivacy_app_350"
    archive_path = _single_zip(source_dir)
    output_dir = output_root / source_id
    documents_path = output_dir / "documents.jsonl"
    segments_path = output_dir / "segments.jsonl"
    document_hashes: set[str] = set()
    segment_hashes: set[str] = set()

    with ZipFile(archive_path) as archive:
        document_entries = sorted(
            [
                entry
                for entry in archive.infolist()
                if not entry.is_dir()
                and "__MACOSX" not in entry.filename
                and "/original_documents/" in entry.filename
                and entry.filename.endswith(".html")
            ],
            key=lambda entry: entry.filename,
        )
        annotation_entries = sorted(
            [
                entry
                for entry in archive.infolist()
                if not entry.is_dir()
                and "__MACOSX" not in entry.filename
                and "/annotations/" in entry.filename
                and entry.filename.endswith(".yml")
            ],
            key=lambda entry: entry.filename,
        )

        def documents() -> Iterator[NormalizedTermsRecord]:
            for entry in document_entries:
                text = html_to_text(decode_bytes(archive.read(entry))[0])
                record = _privacy_document(
                    source_id,
                    entry.filename,
                    PurePosixPath(entry.filename).stem,
                    "en",
                    text,
                    {
                        "source_url": SOURCE_URLS[source_id],
                        "source_archive": archive_path.name,
                        "source_entry": entry.filename,
                    },
                )
                document_hashes.add(record.content_sha256)
                yield record

        def segments() -> Iterator[NormalizedTermsRecord]:
            for entry in annotation_entries:
                payload = yaml.safe_load(archive.read(entry).decode("utf-8-sig"))
                policy_id = str(payload.get("policy_id", ""))
                service_name = normalize_text(str(payload.get("policy_name", policy_id)))
                split = normalize_text(str(payload.get("policy_type", "all"))).lower()
                for segment in payload.get("segments", []):
                    text = normalize_text(str(segment.get("segment_text", "")))
                    if not text:
                        continue
                    segment_id = str(segment.get("segment_id", ""))
                    annotation = {key: value for key, value in segment.items() if key != "segment_text"}
                    locator = f"{entry.filename}:{segment_id}"
                    record = NormalizedTermsRecord(
                        record_id=stable_record_id(source_id, locator),
                        source_id=source_id,
                        split=split,
                        locale="en",
                        service_name=service_name,
                        document_type="privacy_policy",
                        category="annotated_segment",
                        version_at="",
                        text=text,
                        content_sha256=sha256_text(text),
                        review_status="needs_review",
                        license_notes=LICENSE_NOTES,
                        provenance={
                            "source_url": SOURCE_URLS[source_id],
                            "source_archive": archive_path.name,
                            "source_entry": entry.filename,
                            "policy_id": policy_id,
                        },
                        annotations=[annotation],
                        record_type="privacy_policy_segment",
                    )
                    segment_hashes.add(record.content_sha256)
                    yield record

        document_count, document_bytes = write_jsonl(documents(), documents_path)
        segment_count, segment_bytes = write_jsonl(segments(), segments_path)

    manifest = _document_manifest(
        source_id,
        archive_path,
        documents_path,
        document_bytes,
        document_count,
        document_hashes,
        {
            "annotation_file_count": len(annotation_entries),
            "segment_count": segment_count,
            "segment_unique_content_count": len(segment_hashes),
            "segment_output": {
                "name": segments_path.name,
                "bytes": segment_bytes,
                "sha256": sha256_file(segments_path),
            },
        },
    )
    write_manifest(output_dir / "manifest.json", manifest)
    segment_manifest = {
        **manifest,
        "conversion_scope": "all_annotation_segments",
        "document_count": segment_count,
        "unique_content_count": len(segment_hashes),
        "duplicate_content_count": segment_count - len(segment_hashes),
        "output": manifest["segment_output"],
    }
    write_manifest(output_dir / "segments-manifest.json", segment_manifest)
    return {"documents": manifest, "segments": segment_manifest}


def convert_optout2020(source_dir: Path, output_root: Path) -> dict[str, object]:
    source_id = "usableprivacy_optoutchoice_2020"
    archive_path = _single_zip(source_dir)
    output_dir = output_root / source_id
    documents_path = output_dir / "documents.jsonl"
    segments_path = output_dir / "segments.jsonl"
    document_hashes: set[str] = set()
    segment_hashes: set[str] = set()
    fd, temp_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        with ZipFile(archive_path) as archive:
            db_entry = next(entry for entry in archive.infolist() if entry.filename.endswith("policies.db"))
            with archive.open(db_entry) as source, open(temp_path, "wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)

            database = sqlite3.connect(f"file:{Path(temp_path).as_posix()}?mode=ro", uri=True)
            database.row_factory = sqlite3.Row

            def documents() -> Iterator[NormalizedTermsRecord]:
                query = """
                    SELECT p.id, p.url, p.html, p.unfiltered_html, p.included,
                           s.url AS site_url, s.ml_set, s.status
                    FROM policies p LEFT JOIN sites s ON s.id = p.site_id ORDER BY p.id
                """
                for row in database.execute(query):
                    raw_html = row["html"] or row["unfiltered_html"]
                    text = html_to_text(raw_html or "")
                    if not text:
                        continue
                    locator = f"policy:{row['id']}"
                    record = _privacy_document(
                        source_id,
                        locator,
                        row["site_url"] or row["url"],
                        "en",
                        text,
                        {
                            "source_url": SOURCE_URLS[source_id],
                            "source_archive": archive_path.name,
                            "source_entry": db_entry.filename,
                            "policy_id": str(row["id"]),
                            "document_url": row["url"] or "",
                            "site_status": row["status"] or "",
                            "included": str(row["included"]),
                        },
                        split=(row["ml_set"] or "all").lower(),
                    )
                    document_hashes.add(record.content_sha256)
                    yield record

            document_count, document_bytes = write_jsonl(documents(), documents_path)
            database.close()

            jsonl_entries = sorted(
                [
                    entry
                    for entry in archive.infolist()
                    if "/category_data/" in entry.filename and entry.filename.endswith(".jsonl")
                ],
                key=lambda entry: entry.filename,
            )

            def segments() -> Iterator[NormalizedTermsRecord]:
                for entry in jsonl_entries:
                    split = PurePosixPath(entry.filename).stem
                    for line_number, raw_line in enumerate(archive.read(entry).decode("utf-8-sig").splitlines(), start=1):
                        row = json.loads(raw_line)
                        sentence = normalize_text(str(row.get("Sentence Text", "")))
                        if not sentence:
                            continue
                        label = normalize_text(str(row.get("Labels", ""))) or "unlabeled"
                        locator = f"{entry.filename}:{line_number}"
                        record = NormalizedTermsRecord(
                            record_id=stable_record_id(source_id, locator),
                            source_id=source_id,
                            split=split,
                            locale="en",
                            service_name=normalize_text(str(row.get("Policy Url", ""))),
                            document_type="privacy_policy",
                            category=label,
                            version_at="",
                            text=sentence,
                            content_sha256=sha256_text(sentence),
                            review_status="needs_review",
                            license_notes=LICENSE_NOTES,
                            provenance={
                                "source_url": SOURCE_URLS[source_id],
                                "source_archive": archive_path.name,
                                "source_entry": entry.filename,
                                "source_line": str(line_number),
                            },
                            annotations=[
                                {
                                    "label": row.get("Labels"),
                                    "opt_out_url": row.get("Opt Out Url"),
                                    "hyperlink_text": row.get("Hyperlink Text"),
                                }
                            ],
                            record_type="privacy_policy_segment",
                        )
                        segment_hashes.add(record.content_sha256)
                        yield record

            segment_count, segment_bytes = write_jsonl(segments(), segments_path)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    manifest = _document_manifest(
        source_id,
        archive_path,
        documents_path,
        document_bytes,
        document_count,
        document_hashes,
        {
            "segment_count": segment_count,
            "segment_unique_content_count": len(segment_hashes),
            "segment_output": {
                "name": segments_path.name,
                "bytes": segment_bytes,
                "sha256": sha256_file(segments_path),
            },
        },
    )
    write_manifest(output_dir / "manifest.json", manifest)
    segment_manifest = {
        **manifest,
        "conversion_scope": "all_labeled_opt_out_segments",
        "document_count": segment_count,
        "unique_content_count": len(segment_hashes),
        "duplicate_content_count": segment_count - len(segment_hashes),
        "output": manifest["segment_output"],
    }
    write_manifest(output_dir / "segments-manifest.json", segment_manifest)
    return {"documents": manifest, "segments": segment_manifest}


def convert_maps_targets(source_dir: Path, output_root: Path) -> dict[str, object]:
    source_id = "usableprivacy_maps_policies"
    archive_path = _single_zip(source_dir)
    output_dir = output_root / source_id
    output_path = output_dir / "targets.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    record_count = 0
    with ZipFile(archive_path) as archive:
        entry = next(item for item in archive.infolist() if item.filename.endswith("april_2018_policies.csv"))
        wrapper = io.TextIOWrapper(archive.open(entry), encoding="utf-8-sig", errors="replace", newline="")
        with output_path.open("w", encoding="utf-8", newline="\n") as output:
            for row in csv.DictReader(wrapper):
                try:
                    policy_sources = ast.literal_eval(row["Policy Sources"])
                except (SyntaxError, ValueError):
                    policy_sources = row["Policy Sources"]
                payload = {
                    "record_id": stable_record_id(source_id, row["ID"]),
                    "source_id": source_id,
                    "record_type": "policy_source_target",
                    "package_id": row["Package ID"],
                    "content_type": row["Content Type"],
                    "downloaded_at": row["Date Downloaded"],
                    "policy_sources": policy_sources,
                }
                output.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
                record_count += 1
    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": source_id,
        "source_url": SOURCE_URLS[source_id],
        "status": "normalized_metadata_only",
        "decision_method": "schema_probe_and_rule_based_conversion",
        "reason": "The dataset contains policy URL/source targets, not policy full text.",
        "record_count": record_count,
        "input_archive": input_file_descriptor(archive_path),
        "output": {"name": output_path.name, "bytes": output_path.stat().st_size, "sha256": sha256_file(output_path)},
        "review_status": "needs_review",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def convert_gdpr_mappings(source_dir: Path, output_root: Path) -> dict[str, object]:
    source_id = "usableprivacy_opp115_gdpr"
    archive_path = _single_zip(source_dir)
    output_dir = output_root / source_id
    output_path = output_dir / "mappings.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    record_count = 0
    with ZipFile(archive_path) as archive, output_path.open("w", encoding="utf-8", newline="\n") as output:
        entries = sorted(
            [
                entry
                for entry in archive.infolist()
                if entry.filename.endswith(".csv") and "__MACOSX" not in entry.filename
            ],
            key=lambda entry: entry.filename,
        )
        for entry in entries:
            wrapper = io.TextIOWrapper(archive.open(entry), encoding="utf-8-sig", errors="replace", newline="")
            for row_number, row in enumerate(csv.reader(wrapper), start=1):
                payload = {
                    "record_id": stable_record_id(source_id, f"{entry.filename}:{row_number}"),
                    "source_id": source_id,
                    "record_type": "gdpr_mapping_row",
                    "source_entry": entry.filename,
                    "row_number": row_number,
                    "values": row,
                }
                output.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
                record_count += 1
    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": source_id,
        "source_url": SOURCE_URLS[source_id],
        "status": "normalized_auxiliary_mapping",
        "decision_method": "schema_probe_and_rule_based_conversion",
        "reason": "This source maps OPP-115 categories to GDPR concepts and contains no policy full text.",
        "record_count": record_count,
        "input_archive": input_file_descriptor(archive_path),
        "output": {"name": output_path.name, "bytes": output_path.stat().st_size, "sha256": sha256_file(output_path)},
        "review_status": "needs_review",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def profile_fsdk(source_dir: Path, output_root: Path) -> dict[str, object]:
    source_id = "usableprivacy_fsdk"
    archive_path = _single_zip(source_dir)
    output_dir = output_root / source_id
    with ZipFile(archive_path) as archive:
        entry = next(
            item for item in archive.infolist() if item.filename.endswith(".csv") and "__MACOSX" not in item.filename
        )
        wrapper = io.TextIOWrapper(archive.open(entry), encoding="utf-8-sig", errors="replace", newline="")
        reader = csv.reader(wrapper)
        columns = next(reader)
        row_count = sum(1 for _ in reader)
    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": source_id,
        "source_url": SOURCE_URLS[source_id],
        "status": "auxiliary_profiled",
        "decision_method": "schema_probe_and_full_row_count",
        "reason": "The source contains SDK runtime telemetry, not terms or privacy-policy full text.",
        "row_count": row_count,
        "columns": columns,
        "input_archive": input_file_descriptor(archive_path),
        "review_status": "not_rag_candidate",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def _privacy_document(
    source_id: str,
    locator: str,
    service_name: str,
    locale: str,
    text: str,
    provenance: dict[str, str],
    split: str = "all",
) -> NormalizedTermsRecord:
    if not text:
        raise ValueError(f"Empty privacy policy: {locator}")
    return NormalizedTermsRecord(
        record_id=stable_record_id(source_id, locator),
        source_id=source_id,
        split=split,
        locale=locale,
        service_name=service_name,
        document_type="privacy_policy",
        category="privacy_policy",
        version_at="",
        text=text,
        content_sha256=sha256_text(text),
        review_status="needs_review",
        license_notes=LICENSE_NOTES,
        provenance=provenance,
        record_type="privacy_policy_document",
    )


def _document_manifest(
    source_id: str,
    archive_path: Path,
    output_path: Path,
    output_bytes: int,
    document_count: int,
    content_hashes: set[str],
    extra: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": source_id,
        "source_url": SOURCE_URLS[source_id],
        "conversion_scope": "all_selected_policy_documents",
        "decision_method": "archive_structure_probe_and_rule_based_conversion",
        "document_count": document_count,
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "input_archive": input_file_descriptor(archive_path),
        "output": {"name": output_path.name, "bytes": output_bytes, "sha256": sha256_file(output_path)},
        "review_status": "needs_review",
        "license_notes": LICENSE_NOTES,
        **extra,
    }


def _single_zip(source_dir: Path) -> Path:
    archives = list(source_dir.glob("*.zip"))
    if len(archives) != 1:
        raise ValueError(f"Expected one ZIP in {source_dir}, found {len(archives)}")
    return archives[0]


def _html_entry(payload: bytes) -> str:
    return html_to_text(decode_bytes(payload)[0])


def _text_entry(payload: bytes) -> str:
    return normalize_text(decode_bytes(payload)[0])


def _xml_entry(payload: bytes) -> str:
    root = ElementTree.fromstring(payload)
    return normalize_text("\n".join(text for text in root.itertext() if text and text.strip()))


def _service_from_numbered_name(entry_name: str) -> str:
    stem = PurePosixPath(entry_name).stem
    return stem.split("_", 1)[1] if "_" in stem else stem
