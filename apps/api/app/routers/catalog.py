from fastapi import APIRouter

from app.schemas import (
    ConsentCaseCatalog,
    ConsentCaseQualityResponse,
    CollectionRegistryCatalog,
    CollectionRegistryQualityResponse,
    DemoFlowDefinition,
    DemoScenarioDefinition,
    GoalDefinition,
    SolarDemoWorkflowCatalog,
    SyntheticScreenCatalog,
)
from app.services.case_dataset import build_consent_case_quality, load_consent_case_catalog
from app.services.collection_registry import build_collection_registry_quality, load_collection_registry
from app.services.flow_catalog import DEMO_FLOWS
from app.services.goals import GOAL_DESCRIPTIONS, GOAL_LABELS
from app.services.scenarios import DEMO_SCENARIOS
from app.services.solar_demo_workflows import load_solar_demo_workflows
from app.services.synthetic_catalog import load_synthetic_screen_catalog

router = APIRouter(tags=["catalog"])


@router.get("/v1/goals", response_model=list[GoalDefinition])
def goals() -> list[GoalDefinition]:
    return [
        GoalDefinition(
            id=goal_id,
            label=label,
            description=GOAL_DESCRIPTIONS[goal_id],
        )
        for goal_id, label in GOAL_LABELS.items()
    ]


@router.get("/v1/demo-scenarios", response_model=list[DemoScenarioDefinition])
def demo_scenarios() -> list[DemoScenarioDefinition]:
    return [
        DemoScenarioDefinition(
            id=scenario.id,
            label=scenario.label,
            description=scenario.description,
            recommended_goal_id=scenario.recommended_goal_id,
            fixture_filename=scenario.fixture_filename,
        )
        for scenario in DEMO_SCENARIOS.values()
    ]


@router.get("/v1/demo-flows", response_model=list[DemoFlowDefinition])
def demo_flows() -> list[DemoFlowDefinition]:
    return [
        DemoFlowDefinition(
            id=flow.id,
            label=flow.label,
            description=flow.description,
            goal_id=flow.goal_id,
            scenario_ids=flow.scenario_ids,
        )
        for flow in DEMO_FLOWS.values()
    ]


@router.get("/v1/solar-demo-workflows", response_model=SolarDemoWorkflowCatalog)
def solar_demo_workflows() -> SolarDemoWorkflowCatalog:
    return load_solar_demo_workflows()


@router.get("/v1/synthetic-screens", response_model=SyntheticScreenCatalog)
def synthetic_screens() -> SyntheticScreenCatalog:
    return load_synthetic_screen_catalog()


@router.get("/v1/consent-cases", response_model=ConsentCaseCatalog)
def consent_cases() -> ConsentCaseCatalog:
    return load_consent_case_catalog()


@router.get("/v1/consent-cases/quality", response_model=ConsentCaseQualityResponse)
def consent_cases_quality() -> ConsentCaseQualityResponse:
    return build_consent_case_quality()


@router.get("/v1/collection-registry", response_model=CollectionRegistryCatalog)
def collection_registry() -> CollectionRegistryCatalog:
    return load_collection_registry()


@router.get("/v1/collection-registry/quality", response_model=CollectionRegistryQualityResponse)
def collection_registry_quality() -> CollectionRegistryQualityResponse:
    return build_collection_registry_quality()
