import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.terms_ingestion import ingest_terms_captures
from app.services.terms_review import record_terms_review_decision


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        capture_path = temp_root / "captures.json"
        db_path = temp_root / "terms-corpus.sqlite"
        capture_path.write_text(
            json.dumps(
                {
                    "captures": [
                        {
                            "capture_id": "unit_openclaw_subscription_terms",
                            "source_tool": "openclaw",
                            "service_name": "Unit Membership",
                            "provider_name": "Unit Provider",
                            "document_type": "subscription_terms",
                            "source_url": "https://example.invalid/unit/membership",
                            "collection_method": "openclaw",
                            "retrieval_status": "captured",
                            "raw_text": (
                                "제1조 자동 갱신\n"
                                "월간 구독은 해지 전까지 자동 갱신됩니다. 다음 결제일과 결제 금액은 "
                                "결제 화면에서 고지되어야 합니다.\n\n"
                                "제2조 해지\n"
                                "사용자는 계정 설정에서 해지할 수 있고 해지 완료 후 다음 결제일부터 과금되지 않습니다."
                            ),
                        },
                        {
                            "capture_id": "unit_duplicate_subscription_terms",
                            "source_tool": "openclaw",
                            "service_name": "Unit Membership Duplicate",
                            "source_url": "https://example.invalid/unit/membership-duplicate",
                            "retrieval_status": "captured",
                            "raw_text": (
                                "제1조 자동 갱신\n"
                                "월간 구독은 해지 전까지 자동 갱신됩니다. 다음 결제일과 결제 금액은 "
                                "결제 화면에서 고지되어야 합니다.\n\n"
                                "제2조 해지\n"
                                "사용자는 계정 설정에서 해지할 수 있고 해지 완료 후 다음 결제일부터 과금되지 않습니다."
                            ),
                        },
                        {
                            "capture_id": "unit_rejected_private_text",
                            "source_tool": "manual",
                            "service_name": "Unit Rejected",
                            "source_url": "https://example.invalid/unit/rejected",
                            "raw_text": (
                                "제1조 안내\n"
                                "개인 계정 연락처 user@example.com 이 포함된 원문은 저장할 수 없습니다. "
                                "이 텍스트는 최소 길이 조건을 만족하지만 개인정보 후보를 포함합니다."
                            ),
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = ingest_terms_captures(capture_path, db_path)
        assert result.capture_count == 3
        assert result.imported_document_count == 1
        assert result.duplicate_count == 1
        assert result.rejected_count == 1
        assert result.items[0].status == "imported"
        assert result.items[0].collection_method == "openclaw"
        assert result.items[0].document_id
        assert "fixtures/terms-corpus" not in result.items[0].source_path
        assert result.items[1].status == "duplicate"
        assert result.items[2].status == "rejected"

        connection = sqlite3.connect(db_path)
        try:
            document_count = connection.execute("SELECT COUNT(*) FROM terms_documents").fetchone()[0]
            openclaw_count = connection.execute(
                "SELECT COUNT(*) FROM terms_documents WHERE collection_method = 'openclaw'"
            ).fetchone()[0]
            staging_count = connection.execute("SELECT COUNT(*) FROM terms_capture_staging").fetchone()[0]
            rejected_count = connection.execute(
                "SELECT COUNT(*) FROM terms_capture_staging WHERE status = 'rejected'"
            ).fetchone()[0]
            signal_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM terms_signals
                WHERE signal IN ('auto_renewal', 'cancellation', 'billing_notice')
                """
            ).fetchone()[0]
            version_status = connection.execute(
                "SELECT review_status FROM terms_document_versions WHERE version_id = ?",
                (result.items[0].document_id,),
            ).fetchone()[0]
            pending_in_search = connection.execute(
                "SELECT COUNT(*) FROM terms_documents WHERE id = ?",
                (result.items[0].document_id,),
            ).fetchone()[0]
        finally:
            connection.close()

        assert document_count == 3
        assert openclaw_count == 0
        assert staging_count == 3
        assert rejected_count == 1
        assert signal_count >= 0
        assert version_status == "pending_review"
        assert pending_in_search == 0

        review = record_terms_review_decision(
            db_path=db_path,
            version_id=result.items[0].document_id,
            decision="approved_for_search",
            reviewer="unit-reviewer",
            reason="Unit fixture passed license, privacy, and quality review.",
        )
        assert review["search_eligible"] is True
        connection = sqlite3.connect(db_path)
        try:
            assert connection.execute("SELECT COUNT(*) FROM terms_documents").fetchone()[0] == 4
            assert connection.execute(
                "SELECT COUNT(*) FROM terms_documents WHERE collection_method = 'openclaw'"
            ).fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM terms_review_events").fetchone()[0] == 1
            assert connection.execute(
                "SELECT review_status FROM terms_document_versions WHERE version_id = ?",
                (result.items[0].document_id,),
            ).fetchone()[0] == "approved_for_search"
        finally:
            connection.close()

        reimport = ingest_terms_captures(capture_path, db_path)
        assert reimport.imported_document_count == 0
        assert reimport.duplicate_count == 2
        assert reimport.rejected_count == 1

        second_capture_path = temp_root / "second.json"
        second_capture_path.write_text(
            json.dumps(
                {
                    "capture_id": "unit_privacy_policy_terms",
                    "source_tool": "manual",
                    "service_name": "Unit Privacy",
                    "provider_name": "Unit Provider",
                    "document_type": "privacy_policy",
                    "source_url": "https://example.invalid/unit/privacy?token=secret",
                    "retrieval_status": "captured",
                    "public_fixture_allowed": True,
                    "raw_text": (
                        "제1조 개인정보 처리\n"
                        "서비스 제공을 위해 필요한 개인정보는 필수 항목으로 처리됩니다. "
                        "마케팅 및 제3자 제공은 선택 동의로 분리되어야 합니다.\n\n"
                        "제2조 동의 철회\n"
                        "사용자는 계정 설정에서 마케팅 동의와 제3자 제공 동의를 철회할 수 있습니다."
                    ),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        second_result = ingest_terms_captures(second_capture_path, db_path)
        assert second_result.imported_document_count == 1
        assert second_result.items[0].source_url == "https://example.invalid/unit/privacy"
        assert "public_fixture_allowed is ignored" in " ".join(second_result.items[0].warnings)
        rejected_review = record_terms_review_decision(
            db_path=db_path,
            version_id=second_result.items[0].document_id,
            decision="rejected_privacy",
            reviewer="unit-reviewer",
            reason="Unit fixture exercises the explicit rejection path.",
        )
        assert rejected_review["search_eligible"] is False

        failed_capture_path = temp_root / "failed.json"
        failed_capture_path.write_text(
            json.dumps(
                {
                    "capture_id": "unit_failed_capture",
                    "source_tool": "openclaw",
                    "service_name": "Unit Failed",
                    "source_url": "https://example.invalid/unit/failed",
                    "retrieval_status": "blocked",
                    "raw_text": (
                        "제1조 차단된 캡처\n"
                        "이 본문은 길이 조건을 만족하지만 수집 상태가 차단이므로 검색 코퍼스에 들어가면 안 됩니다."
                    ),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        failed_result = ingest_terms_captures(failed_capture_path, db_path)
        assert failed_result.imported_document_count == 0
        assert failed_result.rejected_count == 1
        assert "retrieval_status must be captured" in " ".join(failed_result.items[0].errors)

        connection = sqlite3.connect(db_path)
        try:
            current_openclaw_count = connection.execute(
                "SELECT COUNT(*) FROM terms_documents WHERE collection_method = 'openclaw'"
            ).fetchone()[0]
            privacy_count = connection.execute(
                "SELECT COUNT(*) FROM terms_documents WHERE document_type = 'privacy_policy'"
            ).fetchone()[0]
            public_imported_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM terms_documents
                WHERE collection_method != 'synthetic_seed'
                  AND public_fixture_allowed = 1
                """
            ).fetchone()[0]
            version_count = connection.execute("SELECT COUNT(*) FROM terms_document_versions").fetchone()[0]
            fts_count = connection.execute(
                "SELECT COUNT(*) FROM terms_chunks_fts WHERE terms_chunks_fts MATCH '자동 OR 개인정보'"
            ).fetchone()[0]
        finally:
            connection.close()

        assert current_openclaw_count == 1
        assert privacy_count == 1
        assert public_imported_count == 0
        assert version_count == 2
        assert fts_count >= 1

    print("terms ingestion checks ok")


if __name__ == "__main__":
    main()
