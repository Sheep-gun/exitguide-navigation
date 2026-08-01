from __future__ import annotations

import importlib.util
import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _load_auditor():
    path = ROOT / "scripts" / "Audit-NavigationCoverageRefinement.py"
    spec = importlib.util.spec_from_file_location("navigation_coverage_refinement_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _codes(report: dict) -> set[str]:
    return {str(item["code"]) for item in report["findings"]}


def main() -> None:
    auditor = _load_auditor()
    proposal = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V16.md"
    refinement = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V16_REFINEMENT.md"
    proposal_text = proposal.read_text(encoding="utf-8")
    refinement_text = refinement.read_text(encoding="utf-8")

    report = auditor.audit_refinement(proposal, refinement)
    assert report["passed"], report["findings"]
    assert report["verification_date"] == "2026-07-30"
    assert set(report["declared_dates"].values()) == {"2026-07-30"}
    assert report["inputs"]["catalog_version"] == "15.0.0"
    assert report["inputs"]["equivalence_version"] == "1.1.0"
    assert report["proposal"] == {
        "domain_count": 12,
        "hub_count": 12,
        "terminal_count": 240,
        "sensitive_count": 84,
        "consequential_count": 156,
    }
    assert report["closure"]["partially_resolved_count"] == 16
    assert report["refinement"]["mapping_count"] == 16
    assert report["refinement"]["spec_count"] == 16
    assert report["refinement"]["old_id_count"] == 16
    assert report["refinement"]["new_id_count"] == 16
    assert report["refinement"]["sensitive_count"] == 1
    assert report["refinement"]["consequential_count"] == 15
    assert report["refinement"]["source_url_count"] == 21
    assert report["refinement"]["unique_source_url_count"] == 21
    assert report["projection"] == {
        "remaining_proposal_terminals": 224,
        "domain_count": 12,
        "hub_count": 12,
        "terminal_count": 240,
        "unique_terminal_id_count": 240,
        "sensitive_count": 84,
        "consequential_count": 156,
    }
    assert all(value == 0 for value in report["collisions"].values())

    original_old = "food_manufacturing_recall_ops.product_complaint_signal_queue"
    original_new = "food_manufacturing_recall_ops.fda_hfcs_case_review_status"
    first_mapping_row = (
        "| 1 | S | A | `food_manufacturing_recall_ops.product_complaint_signal_queue` | "
        "`food_manufacturing_recall_ops.fda_hfcs_case_review_status` |"
    )
    first_name = (
        "- **이름:** FDA 인체식품 불만사건 검토 상태 / "
        "FDA human-food complaint case review status"
    )
    second_name = (
        "- **이름:** 공석 800 MHz 채널 조정인증서 첨부 / "
        "Vacated-800-MHz channel coordination-certification attachment"
    )

    cases: list[tuple[str, str, str, str]] = []

    # Missing one of the exact 16 table mappings.
    cases.append(
        (
            "missing_mapping",
            proposal_text,
            refinement_text.replace(first_mapping_row + "\n", "", 1),
            "mapping_count",
        )
    )

    # Duplicate mappings must not be accepted as a nominal count-neutral swap.
    cases.append(
        (
            "duplicate_mapping",
            proposal_text,
            refinement_text.replace(first_mapping_row, first_mapping_row + "\n" + first_mapping_row, 1),
            "duplicate_old_id",
        )
    )

    # Domain preservation is exact, even when all table/spec references agree.
    wrong_domain_new = "controlled_substance_compliance_ops.fda_hfcs_case_review_status"
    cases.append(
        (
            "wrong_domain",
            proposal_text,
            refinement_text.replace(original_new, wrong_domain_new),
            "domain_preservation",
        )
    )

    # The source closure class cannot silently change during refinement.
    cases.append(
        (
            "wrong_class",
            proposal_text,
            refinement_text.replace("| 1 | S | A |", "| 1 | C | A |", 1),
            "class_preservation",
        )
    )

    # Proposal cardinality is part of the projected 12 x (hub1 + terminal20).
    proposal_without_one = re.sub(
        r"^\| S \| `controlled_substance_compliance_ops\.dea_registration_profile`.*\n",
        "",
        proposal_text,
        count=1,
        flags=re.MULTILINE,
    )
    assert proposal_without_one != proposal_text
    cases.append(
        (
            "wrong_proposal_count",
            proposal_without_one,
            refinement_text,
            "proposal_terminal_count",
        )
    )

    # Every accepted source must resolve into the frozen verification/closure registry.
    cases.append(
        (
            "unregistered_source",
            proposal_text,
            refinement_text.replace(
                "https://www.fda.gov/food/compliance-enforcement-food/human-foods-complaint-system-hfcs",
                "https://example.com/not-an-official-v16-source",
                1,
            ),
            "source_registry",
        )
    )

    # A replacement cannot reuse one of the remaining 224 proposal IDs.
    remaining_collision = "food_manufacturing_recall_ops.food_facility_registration_status"
    cases.append(
        (
            "remaining_id_collision",
            proposal_text,
            refinement_text.replace(original_new, remaining_collision),
            "remaining_id_collision",
        )
    )

    # Bilingual identity is mandatory, not an advisory prose convention.
    cases.append(
        (
            "non_bilingual_name",
            proposal_text,
            refinement_text.replace(
                first_name,
                "- **이름:** FDA human-food complaint case review status",
                1,
            ),
            "bilingual_name",
        )
    )

    # Normalized names and goals must remain unique after punctuation folding.
    cases.append(
        (
            "duplicate_name",
            proposal_text,
            refinement_text.replace(second_name, first_name, 1),
            "duplicate_ko_name",
        )
    )

    # Required ontology evidence fields fail closed when absent.
    cases.append(
        (
            "missing_role_asset",
            proposal_text,
            refinement_text.replace("- **Role / asset:**", "- **Role and asset:**", 1),
            "spec_field",
        )
    )

    # Canonical function-name and intent-pattern collisions are separate gates.
    cases.append(
        (
            "canonical_name_collision",
            proposal_text,
            refinement_text.replace(first_name, "- **이름:** 홈 화면 / Home", 1),
            "canonical_name_collision",
        )
    )
    first_goal_line = next(
        line for line in refinement_text.splitlines() if line.startswith("- **목표:**")
    )
    cases.append(
        (
            "canonical_goal_collision",
            proposal_text,
            refinement_text.replace(first_goal_line, "- **목표:** 회원가입 / sign up", 1),
            "canonical_goal_collision",
        )
    )

    # The source pack is date-pinned; a stale refinement cannot pass.
    cases.append(
        (
            "wrong_date",
            proposal_text,
            refinement_text.replace("- 검증일: **2026-07-30**", "- 검증일: **2026-07-29**", 1),
            "verification_date",
        )
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        for name, synthetic_proposal, synthetic_refinement, expected_code in cases:
            proposal_path = temporary / f"{name}-proposal.md"
            refinement_path = temporary / f"{name}-refinement.md"
            proposal_path.write_text(synthetic_proposal, encoding="utf-8")
            refinement_path.write_text(synthetic_refinement, encoding="utf-8")
            failed = auditor.audit_refinement(proposal_path, refinement_path)
            assert not failed["passed"], name
            assert expected_code in _codes(failed), (name, expected_code, failed["findings"])

    # Sanity-check that the closure set really is the refinement old set.
    parsed_mapping = auditor._parse_mapping(refinement_text)
    assert {item["old"] for item in parsed_mapping} == set(report["closure"]["partially_resolved_ids"])
    assert original_old in report["closure"]["partially_resolved_ids"]

    print(
        "navigation coverage refinement audit checks ok | "
        f"partial={report['closure']['partially_resolved_count']} "
        f"mapped={report['refinement']['mapping_count']} "
        f"remaining={report['projection']['remaining_proposal_terminals']} "
        f"sources={report['refinement']['source_url_count']} "
        f"negative_cases={len(cases)}"
    )


if __name__ == "__main__":
    main()
