import json
import re
from collections import Counter
from pathlib import Path

from app.resource_paths import get_resource_root
from app.schemas import (
    ConsentCaseCalibrationSummary,
    ConsentCaseCatalog,
    ConsentCaseDefinition,
    ConsentCaseDatasetMetadata,
    ConsentCaseCoverageReport,
    ConsentCaseCoverageTarget,
    ConsentCaseQualityCalibration,
    ConsentCaseQualityResponse,
    ConsentCaseSummary,
    RiskLevel,
)
from app.services.errors import ProviderUnavailableError
from app.services.goals import get_goal_label
from app.services.llm import MockLlmProvider
from app.services.model_output import ModelOutputError
from app.services.rules import build_response_parts
from app.services.types import ExtractedElement, ExtractedScreen


ROOT = get_resource_root()
CONSENT_CASES_PATH = ROOT / "fixtures" / "consent-cases" / "cases.json"
RISK_RANK: dict[RiskLevel, int] = {"low": 0, "medium": 1, "high": 2}
CONSENT_CASE_NOT_EVALUATED = [
    "ocr_extraction",
    "provider_reasoning",
    "mobile_capture",
    "end_to_end_runtime_accuracy",
]
CONSENT_CASE_LIMITATIONS = [
    "This endpoint calibrates curated consent fixtures against the deterministic rule path only.",
    "It does not measure OCR extraction, live provider reasoning, or end-to-end mobile accuracy.",
]
CONSENT_CASE_COVERAGE_TARGETS = {
    "total_cases": ("Total consent cases", 14),
    "risk_low": ("Low-risk cases", 5),
    "risk_medium": ("Medium-risk cases", 2),
    "risk_high": ("High-risk cases", 7),
    "false_positive_guard": ("False-positive guard cases", 3),
    "field_candidate": ("Generalized field-candidate cases", 1),
    "prompt_injection": ("Prompt-injection resilience cases", 1),
    "third_party": ("Third-party sharing cases", 3),
}
PUBLIC_TEXT_FORBIDDEN_PATTERNS = {
    "url": re.compile(r"https?://|www\.", re.IGNORECASE),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "phone": re.compile(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b"),
}


def load_consent_case_catalog() -> ConsentCaseCatalog:
    payload = json.loads(CONSENT_CASES_PATH.read_text(encoding="utf-8-sig"))
    metadata = ConsentCaseDatasetMetadata.model_validate(payload)
    cases = [ConsentCaseDefinition.model_validate(case) for case in payload["cases"]]
    _validate_case_dataset(cases)
    return ConsentCaseCatalog(
        description=payload["description"],
        metadata=metadata,
        summary=_summarize_cases(cases),
        cases=cases,
    )


def build_consent_case_quality() -> ConsentCaseQualityResponse:
    catalog = load_consent_case_catalog()
    calibrations = [_calibrate_case(case) for case in catalog.cases]
    status = "pass" if all(calibration.passed for calibration in calibrations) else "fail"
    calibration_summary = _summarize_calibrations(calibrations)
    coverage = _build_coverage_report(catalog.summary)
    return ConsentCaseQualityResponse(
        status=status,
        evaluation_scope="deterministic_rule_calibration",
        not_evaluated=CONSENT_CASE_NOT_EVALUATED,
        limitations=CONSENT_CASE_LIMITATIONS,
        metadata=catalog.metadata,
        summary=catalog.summary,
        calibration_summary=calibration_summary,
        coverage=coverage,
        calibrations=calibrations,
    )


def _validate_case_dataset(cases: list[ConsentCaseDefinition]) -> None:
    errors: list[str] = []

    ids = [case.id for case in cases]
    duplicates = sorted(case_id for case_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate case id(s): {', '.join(duplicates)}")

    for case in cases:
        _validate_case_shape(case, errors)
        _validate_case_provenance(case, errors)
        _validate_public_text_hygiene(case, errors)

    if errors:
        raise ValueError("Invalid consent case dataset: " + "; ".join(errors))


def _validate_case_shape(case: ConsentCaseDefinition, errors: list[str]) -> None:
    for field_name in ("id", "title", "category", "screen_title", "screen_text"):
        value = getattr(case, field_name)
        if not value.strip():
            errors.append(f"{case.id or '<missing id>'} has empty {field_name}")

    if case.locale != "ko-KR":
        errors.append(f"{case.id} locale must be ko-KR, got {case.locale}")

    try:
        get_goal_label(case.recommended_goal_id)
    except ValueError as exc:
        errors.append(f"{case.id} has invalid recommended_goal_id: {exc}")

    element_ids = [element.id for element in case.elements]
    duplicate_elements = sorted(
        element_id for element_id, count in Counter(element_ids).items() if count > 1
    )
    if duplicate_elements:
        errors.append(f"{case.id} duplicate element id(s): {', '.join(duplicate_elements)}")

    highest_element_risk = max(
        case.elements,
        key=lambda element: RISK_RANK[element.expected_risk],
    ).expected_risk
    if case.expected_risk != highest_element_risk:
        errors.append(
            f"{case.id} expected_risk should match highest element risk "
            f"({highest_element_risk}), got {case.expected_risk}"
        )


def _validate_case_provenance(case: ConsentCaseDefinition, errors: list[str]) -> None:
    source = case.source

    if source.raw_artifact_in_repo:
        errors.append(f"{case.id} must not store raw artifacts in the repository")
    if source.contains_raw_screenshot:
        errors.append(f"{case.id} must not include raw screenshots in public fixtures")
    if source.contains_ocr_text and source.redaction_status != "redacted":
        errors.append(f"{case.id} OCR text must be redacted before fixture use")
    if not source.public_fixture_allowed:
        errors.append(f"{case.id} must be approved before appearing in the public fixture catalog")

    if case.source_type == "synthetic":
        if source.capture_method != "manual_synthetic":
            errors.append(f"{case.id} synthetic case must use manual_synthetic capture_method")
        if source.redaction_status != "not_required":
            errors.append(f"{case.id} synthetic case must use not_required redaction_status")
        if source.review_status != "not_required":
            errors.append(f"{case.id} synthetic case must use not_required review_status")
        return

    if source.redaction_status != "redacted":
        errors.append(f"{case.id} non-synthetic case must be redacted")
    if source.review_status != "approved":
        errors.append(f"{case.id} non-synthetic case must be approved")

    if case.source_type == "field_candidate":
        if source.capture_method != "manual_field_observation":
            errors.append(f"{case.id} field candidate must use manual_field_observation capture_method")
        if source.artifact_type != "redacted_text_only":
            errors.append(f"{case.id} field candidate must use redacted_text_only artifact_type")
    elif case.source_type == "captured_redacted":
        if source.capture_method not in {"user_submitted_screen", "user_submitted_text"}:
            errors.append(f"{case.id} captured case must come from a user-submitted artifact")
        if source.artifact_type not in {"redacted_text_only", "redacted_screenshot"}:
            errors.append(f"{case.id} captured case must use a redacted artifact_type")


def _validate_public_text_hygiene(case: ConsentCaseDefinition, errors: list[str]) -> None:
    checked_text = {
        "data_notes": case.data_notes,
        "source.notes": case.source.notes,
    }
    for element in case.elements:
        checked_text[f"elements.{element.id}.notes"] = element.notes

    for field_name, text in checked_text.items():
        for label, pattern in PUBLIC_TEXT_FORBIDDEN_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{case.id} {field_name} contains forbidden {label}-like text")


def _summarize_cases(cases: list[ConsentCaseDefinition]) -> ConsentCaseSummary:
    tags = Counter(tag for case in cases for tag in case.tags)
    return ConsentCaseSummary(
        case_count=len(cases),
        element_count=sum(len(case.elements) for case in cases),
        source_counts=dict(sorted(Counter(case.source_type for case in cases).items())),
        category_counts=dict(sorted(Counter(case.category for case in cases).items())),
        risk_counts=dict(sorted(Counter(case.expected_risk for case in cases).items())),
        tag_counts=dict(sorted(tags.items())),
    )


def _summarize_calibrations(
    calibrations: list[ConsentCaseQualityCalibration],
) -> ConsentCaseCalibrationSummary:
    passed = [calibration for calibration in calibrations if calibration.passed]
    failed = [calibration for calibration in calibrations if not calibration.passed]
    return ConsentCaseCalibrationSummary(
        total=len(calibrations),
        passed=len(passed),
        failed=len(failed),
        passed_by_risk=dict(sorted(Counter(item.expected_risk for item in passed).items())),
        failed_by_risk=dict(sorted(Counter(item.expected_risk for item in failed).items())),
        passed_by_source=dict(sorted(Counter(item.source_type for item in passed).items())),
        failed_by_source=dict(sorted(Counter(item.source_type for item in failed).items())),
        failed_case_ids=[item.id for item in failed],
    )


def _build_coverage_report(summary: ConsentCaseSummary) -> ConsentCaseCoverageReport:
    actuals = {
        "total_cases": summary.case_count,
        "risk_low": summary.risk_counts.get("low", 0),
        "risk_medium": summary.risk_counts.get("medium", 0),
        "risk_high": summary.risk_counts.get("high", 0),
        "false_positive_guard": summary.tag_counts.get("false_positive_guard", 0),
        "field_candidate": summary.source_counts.get("field_candidate", 0),
        "prompt_injection": summary.tag_counts.get("prompt_injection", 0),
        "third_party": summary.tag_counts.get("third_party", 0),
    }
    targets = [
        ConsentCaseCoverageTarget(
            id=target_id,
            label=label,
            target=target,
            actual=actuals[target_id],
            passed=actuals[target_id] >= target,
        )
        for target_id, (label, target) in CONSENT_CASE_COVERAGE_TARGETS.items()
    ]
    warnings = [
        f"{target.label}: {target.actual}/{target.target}"
        for target in targets
        if not target.passed
    ]
    return ConsentCaseCoverageReport(
        status="pass" if not warnings else "warn",
        targets=targets,
        warnings=warnings,
    )


def _calibrate_case(case: ConsentCaseDefinition) -> ConsentCaseQualityCalibration:
    expected_element_risks = {element.id: element.expected_risk for element in case.elements}
    expected_element_directions = {element.id: element.expected_direction for element in case.elements}

    try:
        actual_risk, actual_element_risks, actual_element_directions = _judge_case(case)
    except (ProviderUnavailableError, ModelOutputError, ValueError) as exc:
        return ConsentCaseQualityCalibration(
            id=case.id,
            title=case.title,
            category=case.category,
            source_type=case.source_type,
            goal_id=case.recommended_goal_id,
            expected_risk=case.expected_risk,
            expected_element_risks=expected_element_risks,
            expected_element_directions=expected_element_directions,
            passed=False,
            detail=str(exc),
        )

    risk_mismatches = [
        element_id
        for element_id, expected in expected_element_risks.items()
        if actual_element_risks.get(element_id) != expected
    ]
    direction_mismatches = [
        element_id
        for element_id, expected in expected_element_directions.items()
        if actual_element_directions.get(element_id) != expected
    ]
    passed = (
        actual_risk == case.expected_risk
        and not risk_mismatches
        and not direction_mismatches
    )
    mismatch_detail = []
    if actual_risk != case.expected_risk:
        mismatch_detail.append(f"overall expected {case.expected_risk}, got {actual_risk}")
    if risk_mismatches:
        mismatch_detail.append(f"risk mismatch: {', '.join(risk_mismatches)}")
    if direction_mismatches:
        mismatch_detail.append(f"direction mismatch: {', '.join(direction_mismatches)}")

    return ConsentCaseQualityCalibration(
        id=case.id,
        title=case.title,
        category=case.category,
        source_type=case.source_type,
        goal_id=case.recommended_goal_id,
        expected_risk=case.expected_risk,
        actual_risk=actual_risk,
        expected_element_risks=expected_element_risks,
        actual_element_risks=actual_element_risks,
        expected_element_directions=expected_element_directions,
        actual_element_directions=actual_element_directions,
        passed=passed,
        detail="Case matched expected risk and element judgments." if passed else "; ".join(mismatch_detail),
    )


def _judge_case(
    case: ConsentCaseDefinition,
) -> tuple[RiskLevel, dict[str, RiskLevel], dict[str, str]]:
    screen = ExtractedScreen(
        title=case.screen_title,
        text=case.screen_text,
        elements=[
            ExtractedElement(
                id=element.id,
                label=element.label,
                element_type=element.element_type,
                prominence=element.prominence,
                default_selected=element.default_selected,
                monetary_impact=element.monetary_impact,
                optional=element.optional,
            )
            for element in case.elements
        ],
    )
    goal_label = get_goal_label(case.recommended_goal_id)
    judgments = MockLlmProvider().judge_elements(
        goal_id=case.recommended_goal_id,
        goal_label=goal_label,
        screen=screen,
    )
    parts = build_response_parts(goal_label=goal_label, judgments=judgments)
    return (
        parts.overall_risk,
        {element.id: element.risk_level for element in parts.elements},
        {element.id: element.direction for element in parts.elements},
    )
