import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.dataset_adapters.public_corpus import (
    process_korean_public_corpus,
    split_korean_legal_articles,
)


def main() -> None:
    text = (
        "표준약관 전문\n"
        "제1조 (목적)\n이 약관은 서비스 이용 조건을 정합니다.\n"
        "제2조 이용자의 권리\n이용자는 언제든 계약을 해지할 수 있습니다.\n"
        "제2조의2 (환불)\n결제 후 정해진 기간 안에는 환불을 신청할 수 있습니다. "
        "회사는 접수 내용을 확인하고 처리 결과를 이용자에게 알립니다."
    )
    sections, flags = split_korean_legal_articles(text)
    assert flags == []
    assert [section["section_type"] for section in sections] == ["preamble", "article", "article", "article"]
    assert [section["article_label"] for section in sections[1:]] == ["제1조", "제2조", "제2조의2"]
    assert "".join(section["text"] for section in sections) == text
    for index, section in enumerate(sections):
        assert text[section["start_offset"] : section["end_offset"]] == section["text"]
        if index:
            assert sections[index - 1]["end_offset"] == section["start_offset"]

    fallback, fallback_flags = split_korean_legal_articles("조 번호가 없는 짧은 문서입니다.")
    assert fallback[0]["section_type"] == "whole_document"
    assert fallback_flags == ["no_article_headings"]

    duplicate_text = "제1조 첫째\n내용입니다.\n제1조 둘째\n중복입니다."
    _, duplicate_flags = split_korean_legal_articles(duplicate_text)
    assert "duplicate_article_number" in duplicate_flags

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        input_path = root / "documents.jsonl"
        source_manifest_path = root / "source-manifest.json"
        record = {
            "record_id": "nd_unit_document",
            "content_sha256": "unit-source-hash",
            "text": text,
            "provenance": {"source_entry": "unit.xml"},
            "annotations": [
                {
                    "label": "advantageous",
                    "clause_field_code": "1",
                    "clause_articles": [
                        "제2조 이용자의 권리 이용자는 언제든 계약을 해지할 수 있습니다.",
                        "제2조의2 환불 결제 후 정해진 기간 안에는 환불을 요구할 수 있습니다. "
                        "회사는 접수 내용을 확인하고 처리 결과를 이용자에게 알립니다.",
                        "원문에 존재하지 않는 임의 조항",
                    ],
                }
            ],
        }
        input_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
        source_manifest_path.write_text("{}\n", encoding="utf-8")
        manifest = process_korean_public_corpus(
            input_path=input_path,
            source_manifest_path=source_manifest_path,
            output_root=root / "output",
            source_id="unit_korean_terms",
        )
        assert manifest["review_status"] == "needs_review"
        assert manifest["search_eligible"] is False
        assert manifest["counters"]["section_count"] == 4
        assert manifest["counters"]["annotation_matched_target_count"] == 2
        assert manifest["counters"]["annotation_unmatched_target_count"] == 1

        output_root = root / "output" / "unit_korean_terms"
        section_rows = [json.loads(line) for line in (output_root / "sections.jsonl").read_text(encoding="utf-8").splitlines()]
        assert all(row["review_status"] == "needs_review" for row in section_rows)
        assert sum(len(row["annotation_refs"]) for row in section_rows) == 2
        assert {ref["match_method"] for row in section_rows for ref in row["annotation_refs"]} == {
            "normalized_exact_containment",
            "character_5gram_target_recall",
        }
        queue_rows = [json.loads(line) for line in (output_root / "review-queue.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [row["review_type"] for row in queue_rows] == ["annotation_unmatched"]
        assert queue_rows[0]["best_candidate_section_index"] == 1

    print("public corpus checks ok")


if __name__ == "__main__":
    main()
