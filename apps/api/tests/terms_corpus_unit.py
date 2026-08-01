import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.terms_corpus import (
    build_terms_corpus_quality,
    build_terms_corpus_sqlite,
    load_terms_corpus,
    search_terms_corpus_sqlite,
    search_terms_corpus,
)


def main() -> None:
    catalog = load_terms_corpus()
    assert catalog.metadata.dataset_schema_version == "1.0"
    assert catalog.summary.document_count == 3
    assert catalog.summary.section_count == 9
    assert catalog.summary.chunk_count == 9
    assert catalog.summary.document_type_counts["subscription_terms"] == 1
    assert catalog.summary.document_type_counts["privacy_policy"] == 1
    assert catalog.summary.document_type_counts["location_terms"] == 1

    search = search_terms_corpus("자동 갱신 해지 결제", top_k=3)
    assert search.total >= 1
    assert search.results[0].chunk.document_id == "seed_streaming_subscription_terms"
    assert "cancellation" in search.results[0].chunk.signals or "auto_renewal" in search.results[0].chunk.signals

    quality = build_terms_corpus_quality()
    assert quality.status == "pass"
    assert not quality.warnings
    assert all(target.passed for target in quality.coverage_targets)

    with TemporaryDirectory() as temp_dir:
        db_path = build_terms_corpus_sqlite(Path(temp_dir) / "terms-corpus.sqlite")
        connection = sqlite3.connect(db_path)
        try:
            document_count = connection.execute("SELECT COUNT(*) FROM terms_documents").fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM terms_chunks").fetchone()[0]
            signal_count = connection.execute("SELECT COUNT(*) FROM terms_signals").fetchone()[0]
            fts_count = connection.execute(
                "SELECT COUNT(*) FROM terms_chunks_fts WHERE terms_chunks_fts MATCH '자동 OR 해지'"
            ).fetchone()[0]
            tag_count = connection.execute(
                "SELECT COUNT(*) FROM terms_document_tags WHERE tag = 'marketing'"
            ).fetchone()[0]
        finally:
            connection.close()
        assert document_count == 3
        assert chunk_count == 9
        assert signal_count >= 6
        assert fts_count >= 1
        assert tag_count == 1

        sqlite_search = search_terms_corpus_sqlite("자동 갱신 해지 결제", top_k=3, db_path=db_path)
        assert sqlite_search.total >= 1
        assert sqlite_search.results[0].chunk.document_id == "seed_streaming_subscription_terms"

    print("terms corpus checks ok")


if __name__ == "__main__":
    main()
