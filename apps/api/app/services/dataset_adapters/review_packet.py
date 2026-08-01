from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.services.dataset_adapters.common import input_file_descriptor, sha256_file, write_manifest


REVIEW_PACKET_SCHEMA_VERSION = "1.0"
DEFAULT_SAMPLE_LIMIT = 8
MAX_EXCERPT_CHARS = 3_000
SOURCE_IDS = ("ftc_standard_terms", "aihub_legal_regulation_terms")
REVIEW_FIELDS = {
    "reviewer": "",
    "license_status": "",
    "privacy_status": "",
    "parse_quality": "",
    "annotation_quality": "",
    "final_decision": "",
    "reason": "",
}
REVIEW_FOCUS = {
    "clean_article": "조항 경계와 본문이 정상인지 확인",
    "annotation_exact": "정확 포함으로 연결된 AI Hub 라벨이 실제 조항과 일치하는지 확인",
    "annotation_fuzzy_high": "높은 5-gram 점수 연결이 의미상 같은 조항인지 확인",
    "annotation_fuzzy_mid": "중간 5-gram 점수 연결이 의미상 같은 조항인지 확인",
    "annotation_fuzzy_boundary": "임계값 부근 연결의 오탐 여부를 우선 확인",
    "annotation_unmatched_low_score": "미연결 라벨과 최고 후보가 같은 조항인지 확인",
    "annotation_unmatched_short": "짧아서 자동 비교하지 않은 라벨을 수동 확인",
    "annotation_unmatched_ambiguous": "복수 후보가 비슷한 라벨의 올바른 위치를 확인",
    "annotation_unmatched_other": "기타 미연결 원인을 확인",
}


class DeterministicSampler:
    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("sample limit must be positive")
        self.limit = limit
        self.candidate_counts: Counter[str] = Counter()
        self._buckets: dict[str, list[tuple[int, str, dict[str, Any]]]] = defaultdict(list)

    def add(self, bucket: str, key: str, payload: dict[str, Any]) -> None:
        self.candidate_counts[bucket] += 1
        rank = int(hashlib.sha256(f"{bucket}:{key}".encode("utf-8")).hexdigest(), 16)
        entry = (rank, key, payload)
        entries = self._buckets[bucket]
        if len(entries) < self.limit:
            entries.append(entry)
            return
        worst_index = max(range(len(entries)), key=lambda index: (entries[index][0], entries[index][1]))
        if (rank, key) < (entries[worst_index][0], entries[worst_index][1]):
            entries[worst_index] = entry

    def selected(self) -> list[tuple[str, dict[str, Any]]]:
        rows: list[tuple[str, dict[str, Any]]] = []
        for bucket in sorted(self._buckets):
            for _rank, _key, payload in sorted(self._buckets[bucket], key=lambda item: (item[0], item[1])):
                rows.append((bucket, payload))
        return rows


def build_public_corpus_review_packet(
    processed_root: Path,
    normalized_root: Path,
    output_root: Path,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
) -> dict[str, Any]:
    queue_sampler = DeterministicSampler(sample_limit)
    section_sampler = DeterministicSampler(sample_limit)
    input_descriptors: dict[str, Any] = {}

    for source_id in SOURCE_IDS:
        source_processed = processed_root / source_id
        queue_path = source_processed / "review-queue.jsonl"
        sections_path = source_processed / "sections.jsonl"
        normalized_path = normalized_root / source_id / "documents.jsonl"
        for path in (queue_path, sections_path, normalized_path):
            if not path.exists():
                raise FileNotFoundError(f"review packet input does not exist: {path}")
        input_descriptors[source_id] = {
            "review_queue": input_file_descriptor(queue_path),
            "sections": input_file_descriptor(sections_path),
            "normalized_documents": input_file_descriptor(normalized_path),
        }
        _sample_review_queue(source_id, queue_path, queue_sampler)

    selected_queue = queue_sampler.selected()
    queue_section_requests: dict[tuple[str, str, int], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for bucket, row in selected_queue:
        source_id = row["source_id"]
        document_id = row["document_record_id"]
        if row["review_type"] == "annotation_unmatched":
            section_index = row.get("best_candidate_section_index")
            if section_index is not None:
                queue_section_requests[(source_id, document_id, int(section_index))].append((bucket, row))
        else:
            queue_section_requests[(source_id, document_id, 0)].append((bucket, row))

    queue_sections: dict[tuple[str, str, int], dict[str, Any]] = {}
    for source_id in SOURCE_IDS:
        sections_path = processed_root / source_id / "sections.jsonl"
        _sample_sections(source_id, sections_path, section_sampler, queue_section_requests, queue_sections)

    selected_sections = section_sampler.selected()
    selected_document_ids: dict[str, set[str]] = defaultdict(set)
    annotation_requests: dict[str, dict[str, set[tuple[int, int]]]] = defaultdict(lambda: defaultdict(set))
    for _bucket, row in selected_queue:
        selected_document_ids[row["source_id"]].add(row["document_record_id"])
    for _bucket, payload in selected_sections:
        section = payload["section"]
        source_id = section["source_id"]
        document_id = section["document_record_id"]
        selected_document_ids[source_id].add(document_id)
        annotation = payload.get("annotation")
        if annotation:
            annotation_requests[source_id][document_id].add(
                (int(annotation["annotation_index"]), int(annotation["target_index"]))
            )

    document_metadata: dict[tuple[str, str], dict[str, Any]] = {}
    annotation_targets: dict[tuple[str, str, int, int], str] = {}
    for source_id in SOURCE_IDS:
        _collect_normalized_metadata(
            source_id=source_id,
            normalized_path=normalized_root / source_id / "documents.jsonl",
            selected_document_ids=selected_document_ids[source_id],
            annotation_requests=annotation_requests[source_id],
            document_metadata=document_metadata,
            annotation_targets=annotation_targets,
        )

    review_items: list[dict[str, Any]] = []
    for bucket, queue_row in selected_queue:
        source_id, stratum = _split_bucket(bucket)
        document_id = queue_row["document_record_id"]
        if queue_row["review_type"] == "annotation_unmatched":
            section_index = queue_row.get("best_candidate_section_index")
            section = (
                queue_sections.get((source_id, document_id, int(section_index)))
                if section_index is not None
                else None
            )
            annotation = {
                "label": queue_row.get("label", ""),
                "annotation_index": queue_row.get("annotation_index"),
                "target_index": queue_row.get("target_index"),
                "target_text": queue_row.get("target_text", ""),
                "match_method": "",
                "match_score": queue_row.get("best_match_score", 0.0),
                "match_failure_reason": queue_row.get("match_failure_reason", ""),
            }
        else:
            section = queue_sections.get((source_id, document_id, 0))
            annotation = None
        review_items.append(
            _make_review_item(
                source_id=source_id,
                stratum=stratum,
                source_key=_queue_source_key(queue_row),
                document_id=document_id,
                section=section,
                annotation=annotation,
                metadata=document_metadata.get((source_id, document_id), {}),
                queue_context=queue_row,
            )
        )

    for bucket, payload in selected_sections:
        source_id, stratum = _split_bucket(bucket)
        section = payload["section"]
        annotation_ref = payload.get("annotation")
        annotation = None
        if annotation_ref:
            annotation_index = int(annotation_ref["annotation_index"])
            target_index = int(annotation_ref["target_index"])
            annotation = {
                **annotation_ref,
                "target_text": annotation_targets.get(
                    (source_id, section["document_record_id"], annotation_index, target_index), ""
                ),
                "match_failure_reason": "",
            }
        review_items.append(
            _make_review_item(
                source_id=source_id,
                stratum=stratum,
                source_key=payload["source_key"],
                document_id=section["document_record_id"],
                section=section,
                annotation=annotation,
                metadata=document_metadata.get((source_id, section["document_record_id"]), {}),
                queue_context=None,
            )
        )

    review_items.sort(key=lambda row: (row["source_id"], row["stratum"], row["review_item_id"]))
    _validate_review_items(review_items)
    output_root.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_root / "review-items.jsonl"
    csv_path = output_root / "review-checklist.csv"
    guide_path = output_root / "README.md"
    source_template_path = output_root / "source-review.template.json"
    _write_review_jsonl(jsonl_path, review_items)
    _write_review_csv(csv_path, review_items)
    guide_path.write_text(_packet_guide(len(review_items), sample_limit), encoding="utf-8")
    write_manifest(source_template_path, _source_review_template())

    selected_counts = Counter(f"{row['source_id']}:{row['stratum']}" for row in review_items)
    candidate_counts = Counter(queue_sampler.candidate_counts)
    candidate_counts.update(section_sampler.candidate_counts)
    summary = {
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "selection_method": "lowest_sha256_rank_per_source_and_stratum",
        "ai_used": False,
        "search_approval_changed": False,
        "sample_limit_per_source_stratum": sample_limit,
        "review_item_count": len(review_items),
        "max_excerpt_chars": MAX_EXCERPT_CHARS,
        "candidate_counts": dict(sorted(candidate_counts.items())),
        "selected_counts": dict(sorted(selected_counts.items())),
        "inputs": input_descriptors,
        "outputs": {
            "review_items": _output_descriptor(jsonl_path, len(review_items)),
            "review_checklist": _output_descriptor(csv_path, len(review_items)),
            "guide": _output_descriptor(guide_path, 1),
            "source_review_template": _output_descriptor(source_template_path, len(SOURCE_IDS)),
        },
    }
    write_manifest(output_root / "summary.json", summary)
    return summary


def _sample_review_queue(source_id: str, queue_path: Path, sampler: DeterministicSampler) -> None:
    with queue_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["review_type"] == "annotation_unmatched":
                reason = row.get("match_failure_reason", "")
                stratum = {
                    "fuzzy_score_below_threshold": "annotation_unmatched_low_score",
                    "target_too_short_for_fuzzy_match": "annotation_unmatched_short",
                    "ambiguous_fuzzy_match": "annotation_unmatched_ambiguous",
                }.get(reason, "annotation_unmatched_other")
                sampler.add(_bucket(source_id, stratum), _queue_source_key(row), row)
                continue
            if row["review_type"] == "document_structure":
                for flag in row.get("quality_flags", []):
                    stratum = f"document_structure_{flag}"
                    sampler.add(_bucket(source_id, stratum), f"{row['document_record_id']}:{flag}", row)


def _sample_sections(
    source_id: str,
    sections_path: Path,
    sampler: DeterministicSampler,
    queue_section_requests: dict[tuple[str, str, int], list[tuple[str, dict[str, Any]]]],
    queue_sections: dict[tuple[str, str, int], dict[str, Any]],
) -> None:
    with sections_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            section = json.loads(line)
            document_id = section["document_record_id"]
            section_index = int(section["section_index"])
            lookup_key = (source_id, document_id, section_index)
            if lookup_key in queue_section_requests:
                queue_sections[lookup_key] = section

            base_key = f"{document_id}:{section['section_id']}"
            flags = set(section.get("quality_flags", []))
            if section["section_type"] == "article" and not flags and not section.get("annotation_refs"):
                sampler.add(
                    _bucket(source_id, "clean_article"),
                    base_key,
                    {"section": section, "source_key": base_key},
                )
            for flag in sorted(flags):
                if flag in {"short_section", "long_section", "suspicious_unicode", "large_preamble"}:
                    stratum = f"section_{flag}"
                    sampler.add(
                        _bucket(source_id, stratum),
                        f"{base_key}:{flag}",
                        {"section": section, "source_key": f"{base_key}:{flag}"},
                    )
            for annotation in section.get("annotation_refs", []):
                method = annotation.get("match_method", "")
                score = float(annotation.get("match_score", 0.0))
                if method == "normalized_exact_containment":
                    stratum = "annotation_exact"
                elif score < 0.80:
                    stratum = "annotation_fuzzy_boundary"
                elif score >= 0.90:
                    stratum = "annotation_fuzzy_high"
                else:
                    stratum = "annotation_fuzzy_mid"
                annotation_key = f"{annotation['annotation_index']}:{annotation['target_index']}"
                source_key = f"{base_key}:{annotation_key}"
                sampler.add(
                    _bucket(source_id, stratum),
                    source_key,
                    {"section": section, "annotation": annotation, "source_key": source_key},
                )


def _collect_normalized_metadata(
    source_id: str,
    normalized_path: Path,
    selected_document_ids: set[str],
    annotation_requests: dict[str, set[tuple[int, int]]],
    document_metadata: dict[tuple[str, str], dict[str, Any]],
    annotation_targets: dict[tuple[str, str, int, int], str],
) -> None:
    if not selected_document_ids:
        return
    with normalized_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            document_id = row["record_id"]
            if document_id not in selected_document_ids:
                continue
            document_metadata[(source_id, document_id)] = {
                "service_name": row.get("service_name", ""),
                "document_type": row.get("document_type", ""),
                "locale": row.get("locale", ""),
                "license_notes": row.get("license_notes", ""),
                "version_at": row.get("version_at", ""),
                "source_content_sha256": row.get("content_sha256", ""),
                "provenance": row.get("provenance", {}),
            }
            wanted = annotation_requests.get(document_id, set())
            for annotation_index, target_index in wanted:
                annotations = row.get("annotations", [])
                if annotation_index >= len(annotations):
                    continue
                targets = annotations[annotation_index].get("clause_articles", [])
                if target_index >= len(targets):
                    continue
                annotation_targets[(source_id, document_id, annotation_index, target_index)] = str(
                    targets[target_index]
                )


def _make_review_item(
    source_id: str,
    stratum: str,
    source_key: str,
    document_id: str,
    section: dict[str, Any] | None,
    annotation: dict[str, Any] | None,
    metadata: dict[str, Any],
    queue_context: dict[str, Any] | None,
) -> dict[str, Any]:
    review_item_id = "pri_" + hashlib.sha256(
        f"{source_id}:{stratum}:{source_key}".encode("utf-8")
    ).hexdigest()[:20]
    section_text = section.get("text", "") if section else ""
    return {
        "schema_version": REVIEW_PACKET_SCHEMA_VERSION,
        "review_item_id": review_item_id,
        "source_id": source_id,
        "stratum": stratum,
        "review_focus": REVIEW_FOCUS.get(stratum, _fallback_review_focus(stratum)),
        "document_record_id": document_id,
        "service_name": metadata.get("service_name", ""),
        "document_type": metadata.get("document_type", ""),
        "locale": metadata.get("locale", ""),
        "license_notes": metadata.get("license_notes", ""),
        "version_at": metadata.get("version_at", ""),
        "source_content_sha256": metadata.get("source_content_sha256", ""),
        "section": {
            "section_id": section.get("section_id", "") if section else "",
            "section_index": section.get("section_index") if section else None,
            "section_type": section.get("section_type", "") if section else "",
            "article_label": section.get("article_label", "") if section else "",
            "heading": section.get("heading", "") if section else "",
            "full_text_chars": len(section_text),
            "text_excerpt": _excerpt(section_text),
            "content_sha256": section.get("content_sha256", "") if section else "",
            "quality_flags": section.get("quality_flags", []) if section else [],
        },
        "annotation": annotation,
        "queue_context": queue_context,
        "provenance": metadata.get("provenance", section.get("provenance", {}) if section else {}),
        "review": dict(REVIEW_FIELDS),
    }


def _validate_review_items(items: list[dict[str, Any]]) -> None:
    ids: set[str] = set()
    for item in items:
        item_id = item["review_item_id"]
        if item_id in ids:
            raise ValueError(f"duplicate review item id: {item_id}")
        ids.add(item_id)
        if len(item["section"]["text_excerpt"]) > MAX_EXCERPT_CHARS:
            raise ValueError(f"review excerpt exceeds limit: {item_id}")
        if item["review"] != REVIEW_FIELDS:
            raise ValueError(f"review decisions must be blank in generated packet: {item_id}")
        if item["annotation"] and item["stratum"].startswith("annotation_"):
            if not item["annotation"].get("target_text"):
                raise ValueError(f"annotation review item is missing target text: {item_id}")


def _write_review_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def _write_review_csv(path: Path, items: list[dict[str, Any]]) -> None:
    fieldnames = [
        "review_item_id",
        "source_id",
        "stratum",
        "review_focus",
        "document_record_id",
        "service_name",
        "document_type",
        "article_label",
        "heading",
        "section_text_excerpt",
        "quality_flags",
        "annotation_label",
        "annotation_target_text",
        "match_method",
        "match_score",
        "match_failure_reason",
        "license_notes",
        "source_entry",
        *REVIEW_FIELDS.keys(),
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            annotation = item.get("annotation") or {}
            provenance = item.get("provenance") or {}
            writer.writerow(
                {
                    "review_item_id": item["review_item_id"],
                    "source_id": item["source_id"],
                    "stratum": item["stratum"],
                    "review_focus": item["review_focus"],
                    "document_record_id": item["document_record_id"],
                    "service_name": item["service_name"],
                    "document_type": item["document_type"],
                    "article_label": item["section"]["article_label"],
                    "heading": item["section"]["heading"],
                    "section_text_excerpt": item["section"]["text_excerpt"],
                    "quality_flags": "|".join(item["section"]["quality_flags"]),
                    "annotation_label": annotation.get("label", ""),
                    "annotation_target_text": annotation.get("target_text", ""),
                    "match_method": annotation.get("match_method", ""),
                    "match_score": annotation.get("match_score", ""),
                    "match_failure_reason": annotation.get("match_failure_reason", ""),
                    "license_notes": item["license_notes"],
                    "source_entry": provenance.get("source_entry", ""),
                    **item["review"],
                }
            )


def _packet_guide(item_count: int, sample_limit: int) -> str:
    return f"""# 공개 약관 1차 검토 패킷

이 패킷은 규칙 기반으로 뽑은 {item_count}개 표본이다. source/stratum별 최대 {sample_limit}개이며 검색 승인이나 법적 판단을 자동 수행하지 않았다.

## 검토 순서

1. `review-checklist.csv`를 연다.
2. `section_text_excerpt`와 `annotation_target_text`가 같은 조항인지 확인한다.
3. 출처와 `license_notes`를 확인한다. 메모만으로 재배포 가능 여부를 확정하지 않는다.
4. 개인정보, 계정정보, 거래 식별자, token/cookie 흔적을 확인한다.
5. 조항 경계와 OCR/파싱 품질을 확인한다.
6. 아래 허용값으로 빈 검토 열을 채우고 구체적인 `reason`을 적는다.
7. `source-review.json`에 출처별 이용 조건 검토 결과와 근거 URL을 적는다.

## 허용값

- `license_status`: `unknown`, `research_only`, `redistributable`, `blocked`
- `privacy_status`: `clear`, `redaction_required`, `blocked`
- `parse_quality`: `pass`, `minor_issue`, `major_issue`
- `annotation_quality`: `correct`, `incorrect`, `uncertain`, `not_applicable`
- `final_decision`: `candidate_for_search`, `needs_followup`, `reject`

`candidate_for_search`는 표본 검토 결과일 뿐 SQLite의 `approved_for_search`를 자동 기록하지 않는다. 실제 승격은 별도 version registry와 audit 경로에서 수행한다.
"""


def _source_review_template() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "sources": [
            {
                "source_id": source_id,
                "license_status": "",
                "local_search_allowed": False,
                "reviewer": "",
                "reason": "",
                "reviewed_at": "",
                "evidence_urls": [],
            }
            for source_id in SOURCE_IDS
        ],
    }


def _excerpt(text: str) -> str:
    if len(text) <= MAX_EXCERPT_CHARS:
        return text
    marker = "\n...[중간 생략]...\n"
    side = (MAX_EXCERPT_CHARS - len(marker)) // 2
    return text[:side] + marker + text[-side:]


def _queue_source_key(row: dict[str, Any]) -> str:
    return ":".join(
        str(value)
        for value in (
            row.get("document_record_id", ""),
            row.get("review_type", ""),
            row.get("annotation_index", ""),
            row.get("target_index", ""),
            ",".join(row.get("quality_flags", [])),
        )
    )


def _fallback_review_focus(stratum: str) -> str:
    if stratum.startswith("document_structure_"):
        return f"문서 구조 flag `{stratum.removeprefix('document_structure_')}`가 실제 오류인지 확인"
    if stratum.startswith("section_"):
        return f"section 품질 flag `{stratum.removeprefix('section_')}`를 확인"
    return "표본의 출처, 개인정보, 파싱 품질을 확인"


def _bucket(source_id: str, stratum: str) -> str:
    return f"{source_id}:{stratum}"


def _split_bucket(bucket: str) -> tuple[str, str]:
    return tuple(bucket.split(":", 1))  # type: ignore[return-value]


def _output_descriptor(path: Path, record_count: int) -> dict[str, Any]:
    return {
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "record_count": record_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deterministic human-review packet from processed terms.")
    parser.add_argument("--processed-root", type=Path, required=True)
    parser.add_argument("--normalized-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sample-limit", type=int, default=DEFAULT_SAMPLE_LIMIT)
    args = parser.parse_args()
    summary = build_public_corpus_review_packet(
        processed_root=args.processed_root,
        normalized_root=args.normalized_root,
        output_root=args.output_root,
        sample_limit=args.sample_limit,
    )
    print(json.dumps({"review_item_count": summary["review_item_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
