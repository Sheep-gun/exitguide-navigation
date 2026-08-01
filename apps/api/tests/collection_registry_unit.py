import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.collection_registry import (
    build_collection_registry_quality,
    build_collection_registry_sqlite,
    load_collection_registry,
)


def main() -> None:
    catalog = load_collection_registry()
    assert catalog.metadata.dataset_schema_version == "1.0"
    assert catalog.summary.service_count == 3
    assert catalog.summary.document_source_count == 6
    assert catalog.summary.review_task_count == 2
    assert catalog.summary.flow_count == 2
    assert catalog.summary.flow_step_count == 5
    assert catalog.summary.document_type_counts["terms"] == 2
    assert catalog.summary.document_type_counts["privacy"] == 2
    assert catalog.summary.review_status_counts["pending"] == 2
    assert catalog.summary.collection_status_counts["seed"] == 3

    quality = build_collection_registry_quality()
    assert quality.status == "pass"
    assert not quality.warnings
    assert all(target.passed for target in quality.coverage_targets)

    with TemporaryDirectory() as temp_dir:
        db_path = build_collection_registry_sqlite(Path(temp_dir) / "collection-registry.sqlite")
        connection = sqlite3.connect(db_path)
        try:
            service_count = connection.execute("SELECT COUNT(*) FROM services").fetchone()[0]
            alias_count = connection.execute("SELECT COUNT(*) FROM service_aliases").fetchone()[0]
            platform_count = connection.execute("SELECT COUNT(*) FROM service_platforms").fetchone()[0]
            source_count = connection.execute("SELECT COUNT(*) FROM document_sources").fetchone()[0]
            flow_count = connection.execute("SELECT COUNT(*) FROM cancellation_flows").fetchone()[0]
            step_count = connection.execute("SELECT COUNT(*) FROM flow_steps").fetchone()[0]
            review_count = connection.execute("SELECT COUNT(*) FROM review_tasks WHERE status = 'pending'").fetchone()[0]
            streaming_step_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM flow_steps
                WHERE flow_id = 'flow_seed_streaming_cancel_android'
                """
            ).fetchone()[0]
        finally:
            connection.close()

        assert service_count == 3
        assert alias_count == 3
        assert platform_count == 7
        assert source_count == 6
        assert flow_count == 2
        assert step_count == 5
        assert review_count == 2
        assert streaming_step_count == 3

    print("collection registry checks ok")


if __name__ == "__main__":
    main()
