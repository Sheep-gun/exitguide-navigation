import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.dataset_adapters.review_results import validate_public_corpus_review


CSV_FIELDS = [
    "review_item_id",
    "source_id",
    "stratum",
    "document_record_id",
    "reviewer",
    "license_status",
    "privacy_status",
    "parse_quality",
    "annotation_quality",
    "final_decision",
    "reason",
]


def _write_checklist(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        items_path = root / "review-items.jsonl"
        checklist_path = root / "review-checklist.csv"
        source_path = root / "source-review.json"
        output_root = root / "results"
        base_item = {
            "schema_version": "1.0",
            "source_id": "ftc_standard_terms",
            "stratum": "clean_article",
            "document_record_id": "nd_unit",
            "source_content_sha256": "source-hash",
            "annotation": None,
            "section": {"section_id": "ps_unit", "content_sha256": "section-hash"},
        }
        items = [
            {**base_item, "review_item_id": "pri_candidate"},
            {
                **base_item,
                "review_item_id": "pri_pending",
                "document_record_id": "nd_pending",
                "section": {"section_id": "ps_pending", "content_sha256": "pending-hash"},
            },
        ]
        items_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
            encoding="utf-8",
        )
        source_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "sources": [
                        {
                            "source_id": "ftc_standard_terms",
                            "license_status": "research_only",
                            "local_search_allowed": True,
                            "reviewer": "unit-source-reviewer",
                            "reason": "Unit source terms permit local research search only.",
                            "reviewed_at": "2026-07-15T12:00:00+09:00",
                            "evidence_urls": ["https://example.invalid/license"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        candidate_review = {
            "reviewer": "unit-item-reviewer",
            "license_status": "research_only",
            "privacy_status": "clear",
            "parse_quality": "pass",
            "annotation_quality": "not_applicable",
            "final_decision": "candidate_for_search",
            "reason": "Unit section passed all required local review checks.",
        }
        _write_checklist(
            checklist_path,
            [
                {
                    "review_item_id": "pri_candidate",
                    "source_id": "ftc_standard_terms",
                    "stratum": "clean_article",
                    "document_record_id": "nd_unit",
                    **candidate_review,
                },
                {
                    "review_item_id": "pri_pending",
                    "source_id": "ftc_standard_terms",
                    "stratum": "clean_article",
                    "document_record_id": "nd_pending",
                    **{field: "" for field in candidate_review},
                },
            ],
        )
        summary = validate_public_corpus_review(checklist_path, items_path, source_path, output_root)
        assert summary["counters"]["completed_count"] == 1
        assert summary["counters"]["pending_count"] == 1
        assert summary["counters"]["eligible_for_pending_import_count"] == 1
        result = json.loads((output_root / "validated-results.jsonl").read_text(encoding="utf-8"))
        assert result["eligible_for_pending_import"] is True
        assert result["review"]["reviewer"] == "unit-item-reviewer"

        bad_checklist = root / "bad.csv"
        _write_checklist(
            bad_checklist,
            [
                {
                    "review_item_id": "pri_candidate",
                    "source_id": "ftc_standard_terms",
                    "stratum": "clean_article",
                    "document_record_id": "nd_unit",
                    **{**candidate_review, "privacy_status": "blocked"},
                },
                {
                    "review_item_id": "pri_pending",
                    "source_id": "ftc_standard_terms",
                    "stratum": "clean_article",
                    "document_record_id": "nd_pending",
                    **{field: "" for field in candidate_review},
                },
            ],
        )
        try:
            validate_public_corpus_review(bad_checklist, items_path, source_path, root / "bad-results")
            raise AssertionError("blocked candidate review should fail")
        except ValueError as error:
            assert "clear privacy status" in str(error)

    print("review results checks ok")


if __name__ == "__main__":
    main()
