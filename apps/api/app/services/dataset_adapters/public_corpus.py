from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from app.services.dataset_adapters.common import input_file_descriptor, sha256_file, write_manifest
from app.services.dataset_adapters.source_roles import build_source_role_report, load_source_roles


SECTION_SCHEMA_VERSION = "1.0"
ARTICLE_PATTERN = re.compile(
    r"(?m)^(?P<indent>[ \t]*)(?P<label>제\s*(?P<number>\d+)\s*조(?:\s*의\s*(?P<subnumber>\d+))?)"
    r"(?:\s*[（(](?P<title>[^\n)）]{1,200})[)）])?"
)
COMPACT_PATTERN = re.compile(r"[^0-9A-Za-z가-힣]+")
INLINE_ARTICLE_PATTERN = re.compile(r"제\s*(?P<number>\d+)\s*조(?:\s*의\s*(?P<subnumber>\d+))?")
SUSPICIOUS_UNICODE_PATTERN = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffd]")
SHORT_SECTION_CHARS = 30
LONG_SECTION_CHARS = 20_000
LARGE_PREAMBLE_CHARS = 2_000
FUZZY_NGRAM_SIZE = 5
FUZZY_MATCH_MIN_CHARS = 40
FUZZY_MATCH_MIN_RECALL = 0.72
FUZZY_MATCH_MIN_MARGIN = 0.05


def process_korean_public_corpus(
    input_path: Path,
    source_manifest_path: Path,
    output_root: Path,
    source_id: str,
) -> dict[str, Any]:
    source_output = output_root / source_id
    sections_path = source_output / "sections.jsonl"
    review_queue_path = source_output / "review-queue.jsonl"
    quality_path = source_output / "quality-report.json"
    manifest_path = source_output / "manifest.json"
    source_output.mkdir(parents=True, exist_ok=True)

    counters: Counter[str] = Counter()
    quality_flags: Counter[str] = Counter()
    annotation_match_methods: Counter[str] = Counter()
    annotation_failure_reasons: Counter[str] = Counter()
    section_type_counts: Counter[str] = Counter()

    with (
        input_path.open("r", encoding="utf-8") as input_handle,
        sections_path.open("w", encoding="utf-8", newline="\n") as sections_handle,
        review_queue_path.open("w", encoding="utf-8", newline="\n") as review_handle,
    ):
        for line_number, line in enumerate(input_handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            counters["document_count"] += 1
            text = str(record.get("text", ""))
            if not text:
                counters["empty_document_count"] += 1
                _write_jsonl(
                    review_handle,
                    {
                        "review_type": "empty_document",
                        "source_id": source_id,
                        "document_record_id": record.get("record_id", ""),
                        "input_line": line_number,
                    },
                )
                counters["review_queue_count"] += 1
                continue

            sections, document_flags = split_korean_legal_articles(text)
            for flag in document_flags:
                quality_flags[flag] += 1
            if document_flags:
                _write_jsonl(
                    review_handle,
                    {
                        "review_type": "document_structure",
                        "source_id": source_id,
                        "document_record_id": record["record_id"],
                        "input_line": line_number,
                        "quality_flags": document_flags,
                    },
                )
                counters["review_queue_count"] += 1

            annotation_matches, unmatched_annotations = _match_annotations(record.get("annotations", []), sections)
            counters["annotation_target_count"] += sum(
                len(annotation.get("clause_articles", []))
                for annotation in record.get("annotations", [])
                if isinstance(annotation, dict)
            )
            for refs in annotation_matches.values():
                for ref in refs:
                    annotation_match_methods[ref["match_method"]] += 1
            counters["annotation_matched_target_count"] += sum(len(refs) for refs in annotation_matches.values())
            counters["annotation_unmatched_target_count"] += len(unmatched_annotations)
            for unmatched in unmatched_annotations:
                quality_flags["annotation_unmatched"] += 1
                annotation_failure_reasons[unmatched["match_failure_reason"]] += 1
                _write_jsonl(
                    review_handle,
                    {
                        "review_type": "annotation_unmatched",
                        "source_id": source_id,
                        "document_record_id": record["record_id"],
                        "input_line": line_number,
                        **unmatched,
                    },
                )
                counters["review_queue_count"] += 1

            for index, section in enumerate(sections):
                flags = _section_quality_flags(section)
                for flag in flags:
                    quality_flags[flag] += 1
                section_type_counts[section["section_type"]] += 1
                section_id = _stable_section_id(record["record_id"], index, section["start_offset"], section["end_offset"])
                payload = {
                    "schema_version": SECTION_SCHEMA_VERSION,
                    "section_id": section_id,
                    "source_id": source_id,
                    "document_record_id": record["record_id"],
                    "section_index": index,
                    "section_type": section["section_type"],
                    "article_label": section["article_label"],
                    "heading": section["heading"],
                    "text": section["text"],
                    "content_sha256": _sha256_text(section["text"]),
                    "source_content_sha256": record.get("content_sha256", _sha256_text(text)),
                    "start_offset": section["start_offset"],
                    "end_offset": section["end_offset"],
                    "review_status": "needs_review",
                    "quality_flags": flags,
                    "annotation_refs": annotation_matches.get(index, []),
                    "provenance": {
                        **record.get("provenance", {}),
                        "normalized_input": str(input_path),
                        "normalized_input_line": str(line_number),
                    },
                }
                _write_jsonl(sections_handle, payload)
                counters["section_count"] += 1
                counters["section_text_chars"] += len(section["text"])

    quality_report = {
        "schema_version": SECTION_SCHEMA_VERSION,
        "source_id": source_id,
        "processing_method": "deterministic_korean_article_split_with_exact_and_5gram_annotation_match",
        "ai_used": False,
        "review_required": True,
        "counters": dict(sorted(counters.items())),
        "section_type_counts": dict(sorted(section_type_counts.items())),
        "quality_flag_counts": dict(sorted(quality_flags.items())),
        "annotation_match_method_counts": dict(sorted(annotation_match_methods.items())),
        "annotation_failure_reason_counts": dict(sorted(annotation_failure_reasons.items())),
        "thresholds": {
            "short_section_chars": SHORT_SECTION_CHARS,
            "long_section_chars": LONG_SECTION_CHARS,
            "large_preamble_chars": LARGE_PREAMBLE_CHARS,
            "fuzzy_ngram_size": FUZZY_NGRAM_SIZE,
            "fuzzy_match_min_chars": FUZZY_MATCH_MIN_CHARS,
            "fuzzy_match_min_recall": FUZZY_MATCH_MIN_RECALL,
            "fuzzy_match_min_margin": FUZZY_MATCH_MIN_MARGIN,
        },
    }
    write_manifest(quality_path, quality_report)
    manifest = {
        "schema_version": SECTION_SCHEMA_VERSION,
        "source_id": source_id,
        "processing_method": "deterministic_korean_article_split_with_exact_and_5gram_annotation_match",
        "ai_used": False,
        "search_eligible": False,
        "review_status": "needs_review",
        "inputs": {
            "documents": input_file_descriptor(input_path),
            "source_manifest": input_file_descriptor(source_manifest_path),
        },
        "outputs": {
            "sections": _output_descriptor(sections_path, counters["section_count"]),
            "review_queue": _output_descriptor(review_queue_path, counters["review_queue_count"]),
            "quality_report": _output_descriptor(quality_path, 1),
        },
        "counters": dict(sorted(counters.items())),
    }
    write_manifest(manifest_path, manifest)
    return manifest


def split_korean_legal_articles(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    matches = list(ARTICLE_PATTERN.finditer(text))
    if not matches:
        return [
            {
                "section_type": "whole_document",
                "article_label": "",
                "heading": "전체 문서",
                "text": text,
                "start_offset": 0,
                "end_offset": len(text),
                "article_key": None,
            }
        ], ["no_article_headings"]

    sections: list[dict[str, Any]] = []
    document_flags: list[str] = []
    first_start = matches[0].start()
    if first_start > 0:
        sections.append(
            {
                "section_type": "preamble",
                "article_label": "",
                "heading": "전문",
                "text": text[:first_start],
                "start_offset": 0,
                "end_offset": first_start,
                "article_key": None,
            }
        )

    seen_keys: set[tuple[int, int]] = set()
    previous_key: tuple[int, int] | None = None
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        number = int(match.group("number"))
        subnumber = int(match.group("subnumber") or 0)
        article_key = (number, subnumber)
        if article_key in seen_keys and "duplicate_article_number" not in document_flags:
            document_flags.append("duplicate_article_number")
        if previous_key is not None and article_key < previous_key and "non_monotonic_article_numbers" not in document_flags:
            document_flags.append("non_monotonic_article_numbers")
        seen_keys.add(article_key)
        previous_key = article_key
        label = _normalize_article_label(match.group("label"))
        title = (match.group("title") or "").strip()
        sections.append(
            {
                "section_type": "article",
                "article_label": label,
                "heading": f"{label} ({title})" if title else label,
                "text": text[start:end],
                "start_offset": start,
                "end_offset": end,
                "article_key": article_key,
            }
        )
    return sections, document_flags


def _match_annotations(
    annotations: Iterable[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> tuple[dict[int, list[dict[str, Any]]], list[dict[str, Any]]]:
    matches: dict[int, list[dict[str, Any]]] = {}
    unmatched: list[dict[str, Any]] = []
    compact_sections = [_compact_text(section["text"]) for section in sections]
    for annotation_index, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            continue
        targets = annotation.get("clause_articles", [])
        if not isinstance(targets, list):
            continue
        for target_index, raw_target in enumerate(targets):
            target = str(raw_target).strip()
            compact_target = _compact_text(target)
            matched_section, match_method, match_score, failure_reason, best_candidate = _match_target_to_section(
                target,
                compact_target,
                sections,
                compact_sections,
            )
            if matched_section is None:
                unmatched.append(
                    {
                        "annotation_index": annotation_index,
                        "target_index": target_index,
                        "label": annotation.get("label", ""),
                        "target_text": target,
                        "target_sha256": _sha256_text(target),
                        "match_failure_reason": failure_reason,
                        "best_match_score": match_score,
                        "best_candidate_section_index": best_candidate,
                        "best_candidate_article_label": (
                            sections[best_candidate]["article_label"] if best_candidate is not None else ""
                        ),
                        "best_candidate_heading": (
                            sections[best_candidate]["heading"] if best_candidate is not None else ""
                        ),
                    }
                )
                continue
            matches.setdefault(matched_section, []).append(
                {
                    "annotation_index": annotation_index,
                    "target_index": target_index,
                    "label": annotation.get("label", ""),
                    "clause_field_code": annotation.get("clause_field_code", ""),
                    "match_method": match_method,
                    "match_score": match_score,
                    "target_sha256": _sha256_text(target),
                }
            )
    return matches, unmatched


def _match_target_to_section(
    target: str,
    compact_target: str,
    sections: list[dict[str, Any]],
    compact_sections: list[str],
) -> tuple[int | None, str, float, str, int | None]:
    if not compact_target:
        return None, "", 0.0, "empty_annotation_target", None
    for section_index, compact_section in enumerate(compact_sections):
        if compact_section and (compact_target in compact_section or compact_section in compact_target):
            return section_index, "normalized_exact_containment", 1.0, "", section_index

    target_key = _first_article_key(target)
    candidate_indexes = [
        index
        for index, section in enumerate(sections)
        if target_key is not None and section.get("article_key") == target_key
    ]
    if not candidate_indexes:
        candidate_indexes = [
            index for index, section in enumerate(sections) if section["section_type"] != "preamble"
        ]
    if len(compact_target) < FUZZY_MATCH_MIN_CHARS:
        best_candidate = candidate_indexes[0] if candidate_indexes else None
        return None, "", 0.0, "target_too_short_for_fuzzy_match", best_candidate

    target_ngrams = _character_ngrams(compact_target, FUZZY_NGRAM_SIZE)
    scored: list[tuple[float, int]] = []
    for section_index in candidate_indexes:
        section_ngrams = _character_ngrams(compact_sections[section_index], FUZZY_NGRAM_SIZE)
        if section_ngrams:
            score = len(target_ngrams & section_ngrams) / len(target_ngrams)
            scored.append((score, section_index))
    if not scored:
        return None, "", 0.0, "no_fuzzy_match_candidate", None
    scored.sort(reverse=True)
    best_score, best_index = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < FUZZY_MATCH_MIN_RECALL:
        return None, "", round(best_score, 4), "fuzzy_score_below_threshold", best_index
    if second_score >= FUZZY_MATCH_MIN_RECALL and best_score - second_score < FUZZY_MATCH_MIN_MARGIN:
        return None, "", round(best_score, 4), "ambiguous_fuzzy_match", best_index
    return best_index, "character_5gram_target_recall", round(best_score, 4), "", best_index


def _first_article_key(value: str) -> tuple[int, int] | None:
    match = INLINE_ARTICLE_PATTERN.search(value)
    if not match:
        return None
    return int(match.group("number")), int(match.group("subnumber") or 0)


def _character_ngrams(value: str, size: int) -> set[str]:
    if len(value) < size:
        return {value} if value else set()
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def _section_quality_flags(section: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    text = section["text"]
    if section["section_type"] == "preamble":
        flags.append("preamble")
        if len(text) > LARGE_PREAMBLE_CHARS:
            flags.append("large_preamble")
    if len(text.strip()) < SHORT_SECTION_CHARS:
        flags.append("short_section")
    if len(text) > LONG_SECTION_CHARS:
        flags.append("long_section")
    if SUSPICIOUS_UNICODE_PATTERN.search(text):
        flags.append("suspicious_unicode")
    return flags


def _compact_text(value: str) -> str:
    return COMPACT_PATTERN.sub("", unicodedata.normalize("NFKC", value)).lower()


def _normalize_article_label(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _stable_section_id(document_record_id: str, index: int, start: int, end: int) -> str:
    digest = hashlib.sha256(f"{document_record_id}:{index}:{start}:{end}".encode("utf-8")).hexdigest()[:20]
    return f"ps_{digest}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_jsonl(handle: Any, payload: dict[str, Any]) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    handle.write("\n")


def _output_descriptor(path: Path, record_count: int) -> dict[str, Any]:
    return {
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "record_count": record_count,
    }


def run_processing(
    normalized_root: Path,
    output_root: Path,
    role_path: Path,
    inventory_path: Path,
) -> list[dict[str, Any]]:
    roles = load_source_roles(role_path, inventory_path)
    role_report_path = output_root / "source-role-report.json"
    build_source_role_report(role_path, inventory_path, role_report_path)
    manifests = []
    for source_id in ("ftc_standard_terms", "aihub_legal_regulation_terms"):
        if roles[source_id]["sectioning_strategy"] != "korean_legal_articles":
            raise ValueError(f"Unexpected sectioning strategy for {source_id}")
        source_root = normalized_root / source_id
        manifests.append(
            process_korean_public_corpus(
                input_path=source_root / "documents.jsonl",
                source_manifest_path=source_root / "manifest.json",
                output_root=output_root,
                source_id=source_id,
            )
        )
    return manifests


def main() -> None:
    parser = argparse.ArgumentParser(description="Split reviewed Korean public terms sources into deterministic sections.")
    parser.add_argument("--normalized-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--roles", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    manifests = run_processing(args.normalized_root, args.output_root, args.roles, args.inventory)
    print(json.dumps({"processed_sources": [item["source_id"] for item in manifests]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
