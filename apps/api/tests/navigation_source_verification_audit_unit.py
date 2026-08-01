from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "Audit-NavigationSourceVerification.py"
PROPOSAL = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V16.md"
PART1 = ROOT / "docs" / "NAVIGATION_SOURCES_V16_PART1.md"
PART2 = ROOT / "docs" / "NAVIGATION_SOURCES_V16_PART2.md"
CLOSURE_PART1 = ROOT / "docs" / "NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART1.md"
CLOSURE_PART2A = ROOT / "docs" / "NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2A.md"
CLOSURE_PART2B = ROOT / "docs" / "NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2B.md"
CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
EQUIVALENCE = ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json"


def _load_auditor() -> ModuleType:
    spec = importlib.util.spec_from_file_location("navigation_source_verification_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _codes(report: dict[str, object]) -> set[str]:
    findings = report["findings"]
    assert isinstance(findings, list)
    return {str(item["code"]) for item in findings if isinstance(item, dict)}


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _audit_with_texts(
    auditor: ModuleType,
    directory: Path,
    *,
    proposal_text: str,
    part1_text: str,
    part2_text: str,
    catalog_path: Path = CATALOG,
    closure_text: str | None = None,
) -> dict[str, object]:
    proposal = _write(directory / "proposal.md", proposal_text)
    part1 = _write(directory / "part1.md", part1_text)
    part2 = _write(directory / "part2.md", part2_text)
    closure_paths = [
        CLOSURE_PART1
        if closure_text is None
        else _write(directory / "NAVIGATION_SOURCES_V16_GAP_CLOSURE_SYNTHETIC.md", closure_text)
    ]
    return auditor.audit_source_verification(
        proposal,
        part1,
        part2,
        catalog_path,
        EQUIVALENCE,
        closure_paths=closure_paths,
    )


def _expect_corruption(report: dict[str, object], expected_code: str) -> None:
    assert report["passed"] is False, report
    assert int(report["finding_count"]) > 0
    assert expected_code in _codes(report), (expected_code, sorted(_codes(report)))


def main() -> None:
    auditor = _load_auditor()
    report = auditor.audit_source_verification(PROPOSAL, PART1, PART2, CATALOG, EQUIVALENCE)
    assert report["passed"] is True, report["findings"]
    assert report["finding_count"] == 0
    assert report["verification_date"] == "2026-07-30"
    assert report["audit_boundary"]["independent_evaluation_inputs_read"] == 0
    assert report["proposal"] == {
        **report["proposal"],
        "domain_count": 12,
        "terminal_count": 240,
        "original_candidate_count": 81,
        "unique_original_candidate_count": 81,
        "normalized_candidate_duplicate_count": 0,
    }
    assert list(report["proposal"]["candidate_distribution"].values()) == [7, 7, 6, 6, 8, 6, 6, 7, 7, 7, 7, 7]
    assert report["part1"] == {
        **report["part1"],
        "domain_count": 6,
        "original_candidate_count": 40,
        "unique_original_candidate_count": 40,
        "decisions": {"accepted": 32, "replaced": 8, "rejected": 0},
        "candidate_derived_usable_count": 39,
        "gap_closing_usable_count": 4,
        "usable_count": 43,
        "normalized_original_duplicate_count": 0,
        "normalized_unresolved_usable_duplicate_count": 0,
        "documented_shared_final_url_count": 1,
        "gap_url_duplicate_count": 0,
        "candidate_gap_overlap_count": 0,
        "unresolved_terminal_count": 7,
        "summary_total": [40, 32, 8, 0, 39, 4, 43],
    }
    assert all(item["valid"] for item in report["part1"]["unresolved_terminals"])
    assert report["part2"] == {
        **report["part2"],
        "domain_count": 6,
        "original_candidate_count": 41,
        "unique_original_candidate_count": 41,
        "decisions": {"accepted": 24, "replaced": 17, "rejected": 0},
        "candidate_derived_usable_count": 41,
        "gap_closing_usable_count": 0,
        "usable_count": 41,
        "normalized_original_duplicate_count": 0,
        "normalized_unresolved_usable_duplicate_count": 0,
        "documented_shared_final_url_count": 0,
        "gap_url_duplicate_count": 0,
        "candidate_gap_overlap_count": 0,
        "summary_total": [41, 24, 17, 0, 41, 22],
    }
    assert len(report["part2"]["unresolved_terminals"]) == 22
    assert all(item["valid"] for item in report["part2"]["unresolved_terminals"])
    assert report["canonical"] == {
        **report["canonical"],
        "catalog_version": "15.0.0",
        "equivalence_version": "1.1.0",
        "canonical_domain_count": 179,
        "canonical_function_count": 2866,
        "canonical_intent_count": 2660,
        "proposed_function_count": 252,
        "proposed_intent_count": 240,
        "domain_collision_count": 0,
        "function_collision_count": 0,
        "intent_collision_count": 0,
        "equivalence_collision_count": 0,
    }
    assert report["closures"]["document_count"] == len(report["closures"]["documents"])
    assert report["closures"]["document_count"] >= 1
    assert report["closures"]["terminal_count"] >= 7
    assert report["closures"]["unique_terminal_count"] == report["closures"]["terminal_count"]
    closure = next(
        item
        for item in report["closures"]["documents"]
        if item["path"].endswith("NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART1.md")
    )
    assert closure == {
        **closure,
        "verification_date": "2026-07-30",
        "terminal_count": 7,
        "status_counts": {"resolved": 6, "partially_resolved": 1, "unresolved": 0},
        "summary_total": [7, 6, 1, 0],
        "category_count": 6,
        "source_reference_count": 17,
        "unique_url_count": 17,
        "duplicate_reference_count": 0,
        "cross_terminal_url_reuse_count": 0,
        "url_declarations": {
            "terminal_to_source_references": 17,
            "normalized_official_urls": 17,
            "unique_normalized_urls": 17,
            "duplicate_references": 0,
            "cross_terminal_url_reuse": 0,
        },
    }
    closure_part2a = next(
        item
        for item in report["closures"]["documents"]
        if item["path"].endswith("NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2A.md")
    )
    assert closure_part2a == {
        **closure_part2a,
        "verification_date": "2026-07-30",
        "terminal_count": 10,
        "status_counts": {"resolved": 2, "partially_resolved": 8, "unresolved": 0},
        "summary_total": [10, 2, 8, 0],
        "category_count": 3,
        "source_reference_count": 18,
        "unique_url_count": 18,
        "duplicate_reference_count": 0,
        "cross_terminal_url_reuse_count": 1,
        "url_declarations": {
            "source_url_count": 18,
            "unique_normalized_urls": 18,
            "duplicate_references": 0,
            "terminal_count": 10,
            "non_official_source_count": 0,
        },
    }
    closure_part2b = next(
        item
        for item in report["closures"]["documents"]
        if item["path"].endswith("NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2B.md")
    )
    assert closure_part2b == {
        **closure_part2b,
        "verification_date": "2026-07-30",
        "terminal_count": 12,
        "status_counts": {"resolved": 5, "partially_resolved": 7, "unresolved": 0},
        "summary_total": [12, 5, 7, 0],
        "category_count": 3,
        "source_reference_count": 12,
        "unique_url_count": 12,
        "duplicate_reference_count": 0,
        "cross_terminal_url_reuse_count": 0,
        "url_declarations": {
            "source_url_count": 12,
            "unique_normalized_urls": 12,
            "duplicate_references": 0,
            "terminal_count": None,
            "non_official_source_count": None,
        },
    }

    proposal_text = PROPOSAL.read_text(encoding="utf-8")
    part1_text = PART1.read_text(encoding="utf-8")
    part2_text = PART2.read_text(encoding="utf-8")
    closure_text = CLOSURE_PART1.read_text(encoding="utf-8")
    closure_part2a_text = CLOSURE_PART2A.read_text(encoding="utf-8")
    closure_part2b_text = CLOSURE_PART2B.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="navigation-source-audit-") as temporary:
        temp = Path(temporary)

        bad_date = part1_text.replace(
            "Verification date: **2026-07-30**",
            "Verification date: **2026-07-29**",
            1,
        )
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=bad_date,
                part2_text=part2_text,
            ),
            "verification_date",
        )

        bad_total = part1_text.replace(
            "| **Total** | **40** | **32** | **8** | **0** | **39** | **4** | **43** |",
            "| **Total** | **40** | **32** | **8** | **0** | **39** | **4** | **42** |",
            1,
        )
        assert bad_total != part1_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=bad_total,
                part2_text=part2_text,
            ),
            "summary_total_arithmetic",
        )

        bad_terminal = part2_text.replace(
            "**미해결 source gap 4개:** `frequency_coordination_attach`",
            "**미해결 source gap 4개:** `invented_terminal_suffix`",
            1,
        )
        assert bad_terminal != part2_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=bad_terminal,
            ),
            "unresolved_terminal_suffix",
        )

        bad_https = proposal_text.replace(
            "https://www.ecfr.gov/current/title-21/chapter-II/part-1301",
            "http://www.ecfr.gov/current/title-21/chapter-II/part-1301",
            1,
        )
        assert bad_https != proposal_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=bad_https,
                part1_text=part1_text,
                part2_text=part2_text,
            ),
            "non_https_link",
        )

        duplicated_candidate = part2_text.replace(
            "](https://www.faa.gov/space/licenses) — HTTP 200",
            "](https://www.fcc.gov/wireless/universal-licensing-system) — HTTP 200",
            1,
        )
        assert duplicated_candidate != part2_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=duplicated_candidate,
            ),
            "original_url_duplicate",
        )

        duplicated_domain = part1_text.replace(
            "Domain prefix: `medical_device_regulatory_ops.`",
            "Domain prefix: `controlled_substance_compliance_ops.`",
            1,
        )
        assert duplicated_domain != part1_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=duplicated_domain,
                part2_text=part2_text,
            ),
            "duplicate_report_domain",
        )

        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        collided_catalog = copy.deepcopy(catalog)
        collision = copy.deepcopy(collided_catalog["functions"][0])
        collision["function_id"] = "controlled_substance_compliance_ops.dea_registration_profile"
        collision["domain"] = "controlled_substance_compliance_ops"
        collided_catalog["functions"].append(collision)
        synthetic_catalog = temp / "catalog-collision.json"
        synthetic_catalog.write_text(json.dumps(collided_catalog, ensure_ascii=False), encoding="utf-8")
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                catalog_path=synthetic_catalog,
            ),
            "canonical_function_collision",
        )

        bad_closure_date = closure_text.replace(
            "Verification date: **2026-07-30**",
            "Verification date: **2026-07-29**",
            1,
        )
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_closure_date,
            ),
            "closure_verification_date",
        )

        bad_closure_total = closure_text.replace(
            "| **Total** | **7** | **6** | **1** | **0** |",
            "| **Total** | **7** | **5** | **1** | **0** |",
            1,
        )
        assert bad_closure_total != closure_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_closure_total,
            ),
            "closure_summary_arithmetic",
        )

        bad_closure_terminal = closure_text.replace(
            "## 1. `occupational_safety_case_ops.safety_program_audit_status`",
            "## 1. `occupational_safety_case_ops.invented_terminal`",
            1,
        )
        assert bad_closure_terminal != closure_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_closure_terminal,
            ),
            "closure_terminal_id",
        )

        bad_closure_status = closure_text.replace(
            "**Status: `resolved` for internal employer-program ontology;",
            "**Status: `unresolved` for internal employer-program ontology;",
            1,
        )
        assert bad_closure_status != closure_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_closure_status,
            ),
            "closure_status_total",
        )

        bad_closure_https = closure_text.replace(
            "https://www.osha.gov/safety-management/program-evaluation",
            "http://www.osha.gov/safety-management/program-evaluation",
            1,
        )
        assert bad_closure_https != closure_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_closure_https,
            ),
            "non_https_link",
        )

        bad_closure_declaration = closure_text.replace(
            "- Unique normalized URLs: **17**",
            "- Unique normalized URLs: **16**",
            1,
        )
        assert bad_closure_declaration != closure_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_closure_declaration,
            ),
            "closure_url_declaration",
        )

        duplicated_closure_url = closure_text.replace(
            "https://www.osha.gov/safety-management/program-evaluation",
            "https://www.fda.gov/food/compliance-enforcement-food/human-foods-complaint-system-hfcs",
            1,
        )
        assert duplicated_closure_url != closure_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=duplicated_closure_url,
            ),
            "closure_url_duplicate",
        )

        bad_part2a_date = closure_part2a_text.replace(
            "- 검증일: **2026-07-30**",
            "- 검증일: **2026-07-29**",
            1,
        )
        assert bad_part2a_date != closure_part2a_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_part2a_date,
            ),
            "closure_verification_date",
        )

        bad_part2a_total = closure_part2a_text.replace(
            "| **합계** | **10** | **2** | **8** | **0** |",
            "| **합계** | **10** | **1** | **8** | **0** |",
            1,
        )
        assert bad_part2a_total != closure_part2a_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_part2a_total,
            ),
            "closure_summary_arithmetic",
        )

        bad_part2a_status = closure_part2a_text.replace(
            "**판정: `partially_resolved`**",
            "**판정: `resolved`**",
            1,
        )
        assert bad_part2a_status != closure_part2a_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_part2a_status,
            ),
            "closure_status_total",
        )

        bad_part2a_terminal = closure_part2a_text.replace(
            "### 3.1 `wireless_spectrum_license_ops.frequency_coordination_attach`",
            "### 3.1 `wireless_spectrum_license_ops.invented_terminal`",
            1,
        )
        assert bad_part2a_terminal != closure_part2a_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_part2a_terminal,
            ),
            "closure_terminal_id",
        )

        bad_part2a_url_count = closure_part2a_text.replace(
            "- 정규화 후 고유 URL 수: **18**",
            "- 정규화 후 고유 URL 수: **17**",
            1,
        )
        assert bad_part2a_url_count != closure_part2a_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_part2a_url_count,
            ),
            "closure_url_declaration",
        )

        bad_part2a_https = closure_part2a_text.replace(
            "https://docs.fcc.gov/public/attachments/DA-14-1904A1.pdf",
            "http://docs.fcc.gov/public/attachments/DA-14-1904A1.pdf",
            1,
        )
        assert bad_part2a_https != closure_part2a_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_part2a_https,
            ),
            "non_https_link",
        )

        bad_part2b_status = closure_part2b_text.replace(
            "### 3.1 `route_plan_approve` — partially_resolved",
            "### 3.1 `route_plan_approve` — resolved",
            1,
        )
        assert bad_part2b_status != closure_part2b_text
        _expect_corruption(
            _audit_with_texts(
                auditor,
                temp,
                proposal_text=proposal_text,
                part1_text=part1_text,
                part2_text=part2_text,
                closure_text=bad_part2b_status,
            ),
            "closure_status_total",
        )

        cli_report = temp / "report.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--gate",
                "--output",
                str(cli_report),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout
        cli_payload = json.loads(cli_report.read_text(encoding="utf-8"))
        assert cli_payload["passed"] is True
        assert cli_payload["finding_count"] == 0

        bad_cli_proposal = _write(temp / "bad-cli-proposal.md", bad_https)
        bad_cli_report = temp / "bad-cli-report.json"
        rejected = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--proposal",
                str(bad_cli_proposal),
                "--part1",
                str(PART1),
                "--part2",
                str(PART2),
                "--catalog",
                str(CATALOG),
                "--equivalence",
                str(EQUIVALENCE),
                "--closure",
                str(CLOSURE_PART1),
                "--gate",
                "--output",
                str(bad_cli_report),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert rejected.returncode == 1, rejected.stderr or rejected.stdout
        rejected_payload = json.loads(bad_cli_report.read_text(encoding="utf-8"))
        assert rejected_payload["passed"] is False
        assert "non_https_link" in _codes(rejected_payload)

    print(
        "navigation source verification audit: pass | "
        "domains=12 | candidates=81 (40+41) | usable=43+41 | "
        "unresolved=7+22 valid | closures=29 terminals, urls=17+18+12 unique | "
        "canonical collisions=0 | synthetic corruptions rejected=21"
    )


if __name__ == "__main__":
    main()
