import hashlib
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.dataset_adapters.review_import import import_reviewed_public_sections
from app.services.terms_review import record_terms_review_decision


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        results_path = root / "validated-results.jsonl"
        items_path = root / "review-items.jsonl"
        processed_root = root / "processed"
        sections_path = processed_root / "ftc_standard_terms" / "sections.jsonl"
        db_path = root / "terms-corpus.sqlite"
        text = "제1조 (해지)\n이용자는 언제든 계약을 해지할 수 있고 다음 결제일부터 과금되지 않습니다."
        section_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        section = {
            "schema_version": "1.0",
            "section_id": "ps_reviewed_unit",
            "source_id": "ftc_standard_terms",
            "document_record_id": "nd_reviewed_unit",
            "section_index": 0,
            "section_type": "article",
            "article_label": "제1조",
            "heading": "제1조 (해지)",
            "text": text,
            "content_sha256": section_hash,
            "source_content_sha256": "source-hash",
            "review_status": "needs_review",
            "quality_flags": [],
            "annotation_refs": [],
            "provenance": {"source_url": "https://example.invalid/terms"},
        }
        sections_path.parent.mkdir(parents=True)
        sections_path.write_text(json.dumps(section, ensure_ascii=False) + "\n", encoding="utf-8")
        source_review = {
            "source_id": "ftc_standard_terms",
            "license_status": "research_only",
            "local_search_allowed": True,
            "reviewer": "unit-source-reviewer",
            "reason": "Unit source permits local research search only.",
            "reviewed_at": "2026-07-15T12:00:00+09:00",
            "evidence_urls": ["https://example.invalid/license"],
            "reviewed": True,
        }
        result = {
            "schema_version": "1.0",
            "review_item_id": "pri_reviewed_unit",
            "source_id": "ftc_standard_terms",
            "document_record_id": "nd_reviewed_unit",
            "section_id": "ps_reviewed_unit",
            "section_content_sha256": section_hash,
            "source_content_sha256": "source-hash",
            "review": {
                "reviewer": "unit-item-reviewer",
                "license_status": "research_only",
                "privacy_status": "clear",
                "parse_quality": "pass",
                "annotation_quality": "not_applicable",
                "final_decision": "candidate_for_search",
                "reason": "Unit section passed all local review checks.",
            },
            "source_review": source_review,
            "annotation_usable": False,
            "eligible_for_pending_import": True,
            "review_sha256": hashlib.sha256(
                json.dumps(
                    {
                        "reviewer": "unit-item-reviewer",
                        "license_status": "research_only",
                        "privacy_status": "clear",
                        "parse_quality": "pass",
                        "annotation_quality": "not_applicable",
                        "final_decision": "candidate_for_search",
                        "reason": "Unit section passed all local review checks.",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        }
        results_path.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
        item = {
            "review_item_id": "pri_reviewed_unit",
            "source_id": "ftc_standard_terms",
            "document_record_id": "nd_reviewed_unit",
            "service_name": "단위 표준약관",
            "document_type": "standard_terms",
            "locale": "ko-KR",
            "license_notes": "unit license note",
            "version_at": "",
            "source_content_sha256": "source-hash",
            "section": {"section_id": "ps_reviewed_unit", "content_sha256": section_hash},
            "provenance": {"source_url": "https://example.invalid/terms"},
        }
        items_path.write_text(json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8")

        dry_run = import_reviewed_public_sections(results_path, items_path, processed_root, db_path, apply=False)
        assert dry_run["pending_document_count"] == 1
        assert dry_run["search_approval_changed"] is False
        assert not db_path.exists()

        applied = import_reviewed_public_sections(results_path, items_path, processed_root, db_path, apply=True)
        assert applied["imported_document_count"] == 1
        connection = sqlite3.connect(db_path)
        try:
            version_id, status = connection.execute(
                "SELECT version_id, review_status FROM terms_document_versions"
            ).fetchone()
            assert status == "pending_review"
            assert connection.execute("SELECT COUNT(*) FROM terms_documents").fetchone()[0] == 3
            assert connection.execute("SELECT COUNT(*) FROM terms_public_review_item_links").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM terms_public_review_import_runs").fetchone()[0] == 1
        finally:
            connection.close()

        approval = record_terms_review_decision(
            db_path=db_path,
            version_id=version_id,
            decision="approved_for_search",
            reviewer="unit-final-reviewer",
            reason="Unit pending version passed the final registry approval gate.",
        )
        assert approval["search_eligible"] is True
        connection = sqlite3.connect(db_path)
        try:
            assert connection.execute("SELECT COUNT(*) FROM terms_documents").fetchone()[0] == 4
            imported = connection.execute(
                "SELECT COUNT(*) FROM terms_documents WHERE collection_method = 'imported'"
            ).fetchone()[0]
            assert imported == 1
        finally:
            connection.close()

        repeated = import_reviewed_public_sections(results_path, items_path, processed_root, db_path, apply=True)
        assert repeated["duplicate_document_count"] == 1

        tampered_path = root / "tampered-results.jsonl"
        tampered = {**result, "review": {**result["review"], "privacy_status": "blocked"}}
        tampered["review_sha256"] = hashlib.sha256(
            json.dumps(
                tampered["review"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        tampered_path.write_text(json.dumps(tampered, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            import_reviewed_public_sections(tampered_path, items_path, processed_root, root / "tampered.sqlite")
            raise AssertionError("tampered eligible result should fail")
        except ValueError as error:
            assert "privacy or parse gate" in str(error)

    print("review import checks ok")


if __name__ == "__main__":
    main()
