from app.config import Settings
from app.schemas import DemoReadinessResponse, ReadinessCheck, SyntheticScreenCatalog
from app.services.flow_catalog import DEMO_FLOWS
from app.services.goals import GOAL_LABELS
from app.services.provider_readiness import provider_readiness
from app.services.scenarios import DEMO_SCENARIOS
from app.services.synthetic_catalog import list_synthetic_screen_files, load_synthetic_screen_catalog


def build_demo_readiness(settings: Settings) -> DemoReadinessResponse:
    provider_ready, provider_notes = provider_readiness(settings)
    synthetic_catalog = load_synthetic_screen_catalog()
    cataloged_files = {screen.filename for screen in synthetic_catalog.screens}
    actual_files = set(list_synthetic_screen_files())
    missing_files = sorted(cataloged_files - actual_files)
    uncataloged_files = sorted(actual_files - cataloged_files)
    synthetic_catalog_ready = synthetic_catalog.screen_count >= 15 and not missing_files and not uncataloged_files
    catalog_integrity_errors = _catalog_integrity_errors(synthetic_catalog)
    checks = [
        ReadinessCheck(
            id="goals",
            label="목표 카탈로그",
            passed=len(GOAL_LABELS) >= 6,
            detail=f"{len(GOAL_LABELS)}개의 이용 목표가 준비되어 있습니다.",
        ),
        ReadinessCheck(
            id="demo_scenarios",
            label="데모 시나리오",
            passed=len(DEMO_SCENARIOS) >= 10,
            detail=f"{len(DEMO_SCENARIOS)}개의 API 데모 시나리오가 준비되어 있습니다.",
        ),
        ReadinessCheck(
            id="demo_flows",
            label="흐름 데모",
            passed=len(DEMO_FLOWS) >= 4,
            detail=f"{len(DEMO_FLOWS)}개의 다중 화면 흐름 데모가 준비되어 있습니다.",
        ),
        ReadinessCheck(
            id="synthetic_screens",
            label="합성 화면",
            passed=synthetic_catalog_ready,
            detail=_synthetic_fixture_detail(
                screen_count=synthetic_catalog.screen_count,
                missing_files=missing_files,
                uncataloged_files=uncataloged_files,
            ),
        ),
        ReadinessCheck(
            id="catalog_integrity",
            label="카탈로그 정합성",
            passed=not catalog_integrity_errors,
            detail=(
                "목표, 시나리오, 흐름, 합성 fixture 참조가 서로 맞습니다."
                if not catalog_integrity_errors
                else " ".join(catalog_integrity_errors)
            ),
        ),
        ReadinessCheck(
            id="provider_setup",
            label="Provider 설정",
            passed=provider_ready,
            detail=" ".join(provider_notes),
        ),
        ReadinessCheck(
            id="flow_upload",
            label="흐름 업로드",
            passed=True,
            detail="다중 스크린샷 업로드는 순서가 있는 2-6장 이미지를 받습니다.",
        ),
    ]
    status = "ready" if all(check.passed for check in checks) else "needs_setup"
    return DemoReadinessResponse(status=status, checks=checks)


def _catalog_integrity_errors(synthetic_catalog: SyntheticScreenCatalog) -> list[str]:
    errors: list[str] = []

    for scenario in DEMO_SCENARIOS.values():
        if scenario.recommended_goal_id not in GOAL_LABELS:
            errors.append(f"시나리오 {scenario.id}가 알 수 없는 목표 {scenario.recommended_goal_id}를 참조합니다.")

    for flow in DEMO_FLOWS.values():
        if flow.goal_id not in GOAL_LABELS:
            errors.append(f"흐름 {flow.id}가 알 수 없는 목표 {flow.goal_id}를 참조합니다.")
        if not 2 <= len(flow.scenario_ids) <= 6:
            errors.append(f"흐름 {flow.id}에는 2-6개 시나리오가 필요합니다.")
        missing_scenarios = [scenario_id for scenario_id in flow.scenario_ids if scenario_id not in DEMO_SCENARIOS]
        if missing_scenarios:
            errors.append(f"흐름 {flow.id}가 알 수 없는 시나리오를 참조합니다: {', '.join(missing_scenarios)}.")

    for screen in synthetic_catalog.screens:
        if screen.recommended_goal_id not in GOAL_LABELS:
            errors.append(f"합성 화면 {screen.filename}이 알 수 없는 목표 {screen.recommended_goal_id}를 참조합니다.")

    return errors


def _synthetic_fixture_detail(
    screen_count: int,
    missing_files: list[str],
    uncataloged_files: list[str],
) -> str:
    if missing_files:
        return f"Manifest가 누락된 fixture 파일을 참조합니다: {', '.join(missing_files)}."
    if uncataloged_files:
        return f"Fixture 폴더에 카탈로그되지 않은 PNG 파일이 있습니다: {', '.join(uncataloged_files)}."
    return f"{screen_count}개의 생성 스크린샷 fixture가 카탈로그되어 있습니다."
