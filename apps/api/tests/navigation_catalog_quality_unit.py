import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_catalog_quality import audit_navigation_catalog, normalize_catalog_text


ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
POLICY = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_alias_context_overrides import apply_alias_context_overrides, strip_alias_context_overrides  # noqa: E402
from navigation_catalog_v15_data import (  # noqa: E402
    CATALOG_V15_VERSION,
    REQUIRED_DOMAINS as V15_REQUIRED_DOMAINS,
    load_base_catalog,
    merge_with_base,
)


EXPECTED_V15_TOTALS = {
    "function_count": 2866,
    "intent_count": 2660,
    "alias_count": 53017,
    "context_count": 109230,
    "intent_pattern_count": 67092,
    "goal_rule_count": 98737,
    "route_step_count": 5566,
    "domain_count": 179,
    "role_hint_count": 24047,
    "state_cue_count": 112395,
    "risk_cue_count": 35102,
    "official_source_count": 667,
    "sourced_function_count": 2360,
}


def main() -> None:
    assert normalize_catalog_text("Ｃａｆé 설정") == "café 설정"
    assert normalize_catalog_text("アプリの設定") == "アプリの設定"
    assert normalize_catalog_text("应用设置") == "应用设置"
    with TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        materialized_payload = apply_alias_context_overrides(
            strip_alias_context_overrides(merge_with_base(load_base_catalog(CATALOG)))
        )
        materialized_path = temporary / "v15-catalog.json"
        materialized_path.write_text(
            json.dumps(materialized_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        report = audit_navigation_catalog(materialized_path, POLICY)
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        assert policy["minimum_totals"] == EXPECTED_V15_TOTALS
        assert V15_REQUIRED_DOMAINS <= set(policy["required_domains"])
        assert len(set(policy["required_domains"])) == 179
        assert report["catalog_version"] == CATALOG_V15_VERSION
        assert report["totals"] == EXPECTED_V15_TOTALS, json.dumps(
            {
                "expected": EXPECTED_V15_TOTALS,
                "actual": report["totals"],
            },
            ensure_ascii=False,
            indent=2,
        )
        assert report["status"] == "pass", json.dumps(report["findings"], ensure_ascii=False, indent=2)
        assert report["quality_score"] == 100.0
        assert not [item for item in report["findings"] if item["code"].startswith("unsafe_")]
        assert not report["goal_pattern_collisions"]
        assert not [
            item
            for item in report["findings"]
            if item["code"].startswith("thin_")
            or item["code"] == "missing_function_alias_language"
        ]

        broken_payload = json.loads(json.dumps(materialized_payload, ensure_ascii=False))
        broken_payload["functions"][0]["aliases"] = {"en": ["only one alias"]}
        broken_payload["functions"][0]["positive_context"] = []
        broken_path = temporary / "thin-catalog.json"
        broken_path.write_text(
            json.dumps(broken_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        broken_report = audit_navigation_catalog(broken_path, POLICY)
        broken_codes = {item["code"] for item in broken_report["findings"]}
        assert broken_report["status"] == "fail"
        assert {
            "thin_function_aliases",
            "missing_function_alias_language",
            "thin_positive_context",
        } <= broken_codes

        broken_payload = json.loads(json.dumps(materialized_payload, ensure_ascii=False))
        sourced_function = next(
            item for item in broken_payload["functions"] if item.get("source_refs")
        )
        sourced_function["source_refs"] = ["missing_source_id"]
        source_path = temporary / "broken-source-catalog.json"
        source_path.write_text(
            json.dumps(broken_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        source_report = audit_navigation_catalog(source_path, POLICY)
        source_codes = {item["code"] for item in source_report["findings"]}
        assert source_report["status"] == "fail"
        assert "unknown_official_source_ref" in source_codes
    print(
        "navigation catalog quality checks ok: "
        f"score={report['quality_score']} functions={report['totals']['function_count']} "
        f"intents={report['totals']['intent_count']}"
    )


if __name__ == "__main__":
    main()
