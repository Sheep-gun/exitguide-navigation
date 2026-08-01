from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.dataset_adapters.source_roles import build_source_role_report, load_source_roles


ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    role_path = ROOT / "fixtures" / "public-datasets" / "processing-roles.json"
    inventory_path = ROOT / "fixtures" / "public-datasets" / "sources.json"
    roles = load_source_roles(role_path, inventory_path)

    assert len(roles) == 24
    assert roles["ftc_standard_terms"]["processing_roles"] == ["corpus_candidate"]
    assert roles["ftc_standard_terms"]["sectioning_strategy"] == "korean_legal_articles"
    assert roles["data_go_kr_kca_standard_answers"]["rag_policy"] == "separate_index"
    assert roles["privacyqa_emnlp"]["processing_roles"] == ["evaluation_only"]
    assert roles["usableprivacy_fsdk"]["processing_roles"] == ["excluded_from_rag"]
    assert roles["usableprivacy_maps_policies"]["processing_roles"] == ["crawl_seed"]

    with TemporaryDirectory() as temp_dir:
        report = build_source_role_report(role_path, inventory_path, Path(temp_dir) / "roles.json")
        assert report["source_count"] == 24
        assert report["ai_used"] is False
        assert report["rag_policy_counts"]["review_required"] >= 1

    print("source role checks ok")


if __name__ == "__main__":
    main()
