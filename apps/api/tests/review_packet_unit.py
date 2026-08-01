import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.dataset_adapters.review_packet import build_public_corpus_review_packet


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _section(
    source_id: str,
    document_id: str,
    index: int,
    flags: list[str],
    annotations: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "section_id": f"ps_{source_id}_{index}",
        "source_id": source_id,
        "document_record_id": document_id,
        "section_index": index,
        "section_type": "article",
        "article_label": f"제{index + 1}조",
        "heading": f"제{index + 1}조 (단위 테스트)",
        "text": "이 조항은 검토 패킷 단위 테스트를 위한 충분한 길이의 본문입니다. " * 3,
        "content_sha256": "section-hash",
        "source_content_sha256": "source-hash",
        "start_offset": 0,
        "end_offset": 100,
        "review_status": "needs_review",
        "quality_flags": flags,
        "annotation_refs": annotations,
        "provenance": {"source_entry": f"{source_id}.xml"},
    }


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        processed_root = root / "processed"
        normalized_root = root / "normalized"

        ftc_id = "nd_ftc_unit"
        aihub_id = "nd_aihub_unit"
        _write_jsonl(
            normalized_root / "ftc_standard_terms" / "documents.jsonl",
            [
                {
                    "record_id": ftc_id,
                    "service_name": "공정위 단위 약관",
                    "document_type": "terms_of_service",
                    "locale": "ko-KR",
                    "license_notes": "review required",
                    "content_sha256": "ftc-source-hash",
                    "provenance": {"source_entry": "ftc.hwp"},
                    "annotations": [],
                }
            ],
        )
        _write_jsonl(
            processed_root / "ftc_standard_terms" / "sections.jsonl",
            [
                _section("ftc_standard_terms", ftc_id, 0, [], []),
                _section("ftc_standard_terms", ftc_id, 1, ["short_section"], []),
            ],
        )
        _write_jsonl(
            processed_root / "ftc_standard_terms" / "review-queue.jsonl",
            [
                {
                    "review_type": "document_structure",
                    "source_id": "ftc_standard_terms",
                    "document_record_id": ftc_id,
                    "input_line": 1,
                    "quality_flags": ["duplicate_article_number"],
                }
            ],
        )

        annotations = [
            {
                "label": "advantageous",
                "clause_field_code": "1",
                "clause_articles": ["제1조 이용자는 언제든 계약을 해지할 수 있습니다."],
            }
        ]
        _write_jsonl(
            normalized_root / "aihub_legal_regulation_terms" / "documents.jsonl",
            [
                {
                    "record_id": aihub_id,
                    "service_name": "AI Hub 단위 약관",
                    "document_type": "terms_of_service",
                    "locale": "ko-KR",
                    "license_notes": "AI Hub review required",
                    "content_sha256": "aihub-source-hash",
                    "provenance": {"source_entry": "aihub.xml"},
                    "annotations": annotations,
                }
            ],
        )
        exact_ref = {
            "annotation_index": 0,
            "target_index": 0,
            "label": "advantageous",
            "clause_field_code": "1",
            "match_method": "normalized_exact_containment",
            "match_score": 1.0,
            "target_sha256": "target-hash",
        }
        _write_jsonl(
            processed_root / "aihub_legal_regulation_terms" / "sections.jsonl",
            [_section("aihub_legal_regulation_terms", aihub_id, 0, [], [exact_ref])],
        )
        _write_jsonl(
            processed_root / "aihub_legal_regulation_terms" / "review-queue.jsonl",
            [
                {
                    "review_type": "annotation_unmatched",
                    "source_id": "aihub_legal_regulation_terms",
                    "document_record_id": aihub_id,
                    "input_line": 1,
                    "annotation_index": 0,
                    "target_index": 0,
                    "label": "advantageous",
                    "target_text": "제1조 이용자는 언제든 계약을 해지할 수 있습니다.",
                    "target_sha256": "target-hash",
                    "match_failure_reason": "fuzzy_score_below_threshold",
                    "best_match_score": 0.6,
                    "best_candidate_section_index": 0,
                    "best_candidate_article_label": "제1조",
                    "best_candidate_heading": "제1조 (단위 테스트)",
                }
            ],
        )

        first_output = root / "packet-one"
        second_output = root / "packet-two"
        first = build_public_corpus_review_packet(processed_root, normalized_root, first_output, sample_limit=2)
        second = build_public_corpus_review_packet(processed_root, normalized_root, second_output, sample_limit=2)
        assert first["ai_used"] is False
        assert first["search_approval_changed"] is False
        assert first["review_item_count"] == 5
        assert first["outputs"]["review_items"]["sha256"] == second["outputs"]["review_items"]["sha256"]

        items = [json.loads(line) for line in (first_output / "review-items.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len({item["review_item_id"] for item in items}) == len(items)
        assert all(not any(item["review"].values()) for item in items)
        annotation_items = [item for item in items if item["annotation"]]
        assert len(annotation_items) == 2
        assert all(item["annotation"]["target_text"] for item in annotation_items)
        assert (first_output / "review-checklist.csv").read_bytes().startswith(b"\xef\xbb\xbf")
        assert "candidate_for_search" in (first_output / "README.md").read_text(encoding="utf-8")

    print("review packet checks ok")


if __name__ == "__main__":
    main()
