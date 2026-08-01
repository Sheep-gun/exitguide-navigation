from app.config import Settings
from app.schemas import (
    DemoQualityCalibration,
    DemoQualityFlowCalibration,
    DemoQualityResponse,
    DemoQualitySummary,
    RiskLevel,
)
from app.services.analysis import analyze_screenshot
from app.services.errors import ProviderUnavailableError
from app.services.flow import analyze_demo_flow
from app.services.flow_catalog import DEMO_FLOWS
from app.services.goals import UnsupportedGoalError
from app.services.model_output import ModelOutputError
from app.services.provider_runtime import RuntimeProviderOptions
from app.services.readiness import build_demo_readiness
from app.services.scenarios import DEMO_SCENARIOS
from app.services.synthetic_catalog import load_synthetic_screen_catalog


QUALITY_PROVIDER_OPTIONS = RuntimeProviderOptions(provider_id="mock")


def build_demo_quality(settings: Settings) -> DemoQualityResponse:
    readiness = build_demo_readiness(settings)
    synthetic_catalog = load_synthetic_screen_catalog()
    expected_risk_by_filename = {
        screen.filename: screen.risk_fixture
        for screen in synthetic_catalog.screens
    }
    expected_risk_by_scenario_id = {
        scenario.id: expected_risk_by_filename.get(scenario.fixture_filename)
        for scenario in DEMO_SCENARIOS.values()
    }
    scenario_calibrations = [
        _calibrate(
            id=scenario.id,
            label=scenario.label,
            source="scenario",
            goal_id=scenario.recommended_goal_id,
            filename=scenario.fixture_filename,
            expected_risk=expected_risk_by_filename.get(scenario.fixture_filename),
        )
        for scenario in DEMO_SCENARIOS.values()
    ]

    flow_calibrations = [
        _calibrate_flow(
            id=flow.id,
            label=flow.label,
            goal_id=flow.goal_id,
            scenario_ids=flow.scenario_ids,
            expected_risk_by_scenario_id=expected_risk_by_scenario_id,
        )
        for flow in DEMO_FLOWS.values()
    ]

    synthetic_calibrations = [
        _calibrate(
            id=screen.filename,
            label=screen.filename,
            source="synthetic",
            goal_id=screen.recommended_goal_id,
            filename=screen.filename,
            expected_risk=screen.risk_fixture,
        )
        for screen in synthetic_catalog.screens
    ]

    readiness_passed = sum(1 for check in readiness.checks if check.passed)
    status = "pass" if (
        readiness.status == "ready"
        and all(item.passed for item in scenario_calibrations)
        and all(item.passed for item in flow_calibrations)
        and all(item.passed for item in synthetic_calibrations)
    ) else "fail"

    return DemoQualityResponse(
        status=status,
        summary=DemoQualitySummary(
            readiness_passed=readiness_passed,
            readiness_total=len(readiness.checks),
            scenarios_passed=sum(1 for item in scenario_calibrations if item.passed),
            scenarios_total=len(scenario_calibrations),
            flows_passed=sum(1 for item in flow_calibrations if item.passed),
            flows_total=len(flow_calibrations),
            synthetic_passed=sum(1 for item in synthetic_calibrations if item.passed),
            synthetic_total=len(synthetic_calibrations),
        ),
        checks=readiness.checks,
        scenario_calibrations=scenario_calibrations,
        flow_calibrations=flow_calibrations,
        synthetic_calibrations=synthetic_calibrations,
    )


def _calibrate(
    id: str,
    label: str,
    source: str,
    goal_id: str,
    filename: str,
    expected_risk: RiskLevel | None,
) -> DemoQualityCalibration:
    if expected_risk is None:
        return DemoQualityCalibration(
            id=id,
            label=label,
            source=source,
            goal_id=goal_id,
            expected_risk=None,
            passed=False,
            detail=f"No expected risk label is cataloged for {filename}.",
        )

    try:
        analysis = analyze_screenshot(
            goal_id=goal_id,
            image_bytes=b"demo quality calibration",
            filename=filename,
            analysis_mode="demo" if source == "scenario" else "upload",
            provider_options=QUALITY_PROVIDER_OPTIONS,
        )
    except (ProviderUnavailableError, ModelOutputError, UnsupportedGoalError, ValueError) as exc:
        return DemoQualityCalibration(
            id=id,
            label=label,
            source=source,
            goal_id=goal_id,
            expected_risk=expected_risk,
            passed=False,
            detail=str(exc),
        )

    passed = analysis.overall_risk == expected_risk
    return DemoQualityCalibration(
        id=id,
        label=label,
        source=source,
        goal_id=goal_id,
        expected_risk=expected_risk,
        actual_risk=analysis.overall_risk,
        alignment_score=analysis.alignment_score,
        passed=passed,
        detail=(
            f"Risk matched expected {expected_risk}."
            if passed
            else f"Expected {expected_risk}, got {analysis.overall_risk}."
        ),
    )


def _calibrate_flow(
    id: str,
    label: str,
    goal_id: str,
    scenario_ids: list[str],
    expected_risk_by_scenario_id: dict[str, RiskLevel | None],
) -> DemoQualityFlowCalibration:
    expected_path = [
        expected_risk_by_scenario_id.get(scenario_id)
        for scenario_id in scenario_ids
    ]
    if any(risk is None for risk in expected_path):
        missing = [
            scenario_id
            for scenario_id, risk in zip(scenario_ids, expected_path, strict=False)
            if risk is None
        ]
        return DemoQualityFlowCalibration(
            id=id,
            label=label,
            goal_id=goal_id,
            passed=False,
            detail=f"No expected risk label is cataloged for flow scenario(s): {', '.join(missing)}.",
        )

    typed_expected_path = [risk for risk in expected_path if risk is not None]
    expected_overall_risk = _overall_risk(typed_expected_path)

    try:
        flow = analyze_demo_flow(
            goal_id=goal_id,
            scenario_ids=scenario_ids,
            provider_options=QUALITY_PROVIDER_OPTIONS,
        )
    except (ProviderUnavailableError, ModelOutputError, UnsupportedGoalError, ValueError) as exc:
        return DemoQualityFlowCalibration(
            id=id,
            label=label,
            goal_id=goal_id,
            expected_overall_risk=expected_overall_risk,
            expected_risk_path=typed_expected_path,
            passed=False,
            detail=str(exc),
        )

    passed = flow.overall_risk == expected_overall_risk and flow.risk_path == typed_expected_path
    return DemoQualityFlowCalibration(
        id=id,
        label=label,
        goal_id=goal_id,
        expected_overall_risk=expected_overall_risk,
        actual_overall_risk=flow.overall_risk,
        expected_risk_path=typed_expected_path,
        actual_risk_path=flow.risk_path,
        alignment_score=flow.alignment_score,
        passed=passed,
        detail=(
            f"Flow matched expected path {' -> '.join(typed_expected_path)}."
            if passed
            else (
                f"Expected {expected_overall_risk} / {' -> '.join(typed_expected_path)}, "
                f"got {flow.overall_risk} / {' -> '.join(flow.risk_path)}."
            )
        ),
    )


def _overall_risk(risks: list[RiskLevel]) -> RiskLevel:
    if "high" in risks:
        return "high"
    if "medium" in risks:
        return "medium"
    return "low"
