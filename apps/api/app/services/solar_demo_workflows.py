import json
from collections import Counter
from pathlib import Path

from app.resource_paths import get_resource_root
from app.schemas import (
    SolarDemoWorkflow,
    SolarDemoWorkflowCatalog,
    SolarDemoWorkflowMetadata,
    SolarDemoWorkflowSummary,
)


ROOT = get_resource_root()
SOLAR_DEMO_WORKFLOWS_PATH = ROOT / "fixtures" / "solar-demo-workflows" / "workflows.json"
FORBIDDEN_TEXT_PATTERNS = [
    "UPSTAGE_API_KEY",
    "Authorization",
    "Bearer ",
    "up_",
]


def load_solar_demo_workflows() -> SolarDemoWorkflowCatalog:
    payload = json.loads(SOLAR_DEMO_WORKFLOWS_PATH.read_text(encoding="utf-8-sig"))
    metadata = SolarDemoWorkflowMetadata.model_validate(payload["metadata"])
    workflows = [SolarDemoWorkflow.model_validate(item) for item in payload["workflows"]]
    _validate_solar_demo_workflows(metadata, workflows, payload)
    return SolarDemoWorkflowCatalog(
        description=payload["description"],
        metadata=metadata,
        summary=_summarize_solar_demo_workflows(workflows),
        workflows=workflows,
    )


def _validate_solar_demo_workflows(
    metadata: SolarDemoWorkflowMetadata,
    workflows: list[SolarDemoWorkflow],
    raw_payload: dict,
) -> None:
    errors: list[str] = []

    workflow_ids = [workflow.id for workflow in workflows]
    duplicate_ids = sorted(
        workflow_id
        for workflow_id, count in Counter(workflow_ids).items()
        if count > 1
    )
    if duplicate_ids:
        errors.append(f"duplicate workflow id(s): {', '.join(duplicate_ids)}")

    case_numbers = [workflow.case_number for workflow in workflows]
    duplicate_cases = sorted(
        case_number
        for case_number, count in Counter(case_numbers).items()
        if count > 1
    )
    if duplicate_cases:
        errors.append(f"duplicate case number(s): {', '.join(duplicate_cases)}")

    if metadata.legal_advice_policy != "not_legal_advice":
        errors.append("solar demo workflows must stay under not_legal_advice policy")

    serialized = json.dumps(raw_payload, ensure_ascii=False)
    for pattern in FORBIDDEN_TEXT_PATTERNS:
        if pattern in serialized:
            errors.append(f"solar demo workflow fixture contains forbidden secret-like text: {pattern}")

    for workflow in workflows:
        if workflow.source_reference.dataset != metadata.source_dataset:
            errors.append(f"{workflow.id} source dataset does not match metadata")
        if workflow.model_result.reference_guidance.not_legal_advice is not True:
            errors.append(f"{workflow.id} reference guidance must be marked not legal advice")
        if not workflow.demo_input.visible_screen_text:
            errors.append(f"{workflow.id} must include visible screen text")

    if errors:
        raise ValueError("Invalid solar demo workflow dataset: " + "; ".join(errors))


def _summarize_solar_demo_workflows(
    workflows: list[SolarDemoWorkflow],
) -> SolarDemoWorkflowSummary:
    return SolarDemoWorkflowSummary(
        workflow_count=len(workflows),
        risk_counts=dict(sorted(Counter(item.model_result.risk_level for item in workflows).items())),
        confidence_counts=dict(sorted(Counter(item.model_result.confidence for item in workflows).items())),
        source_dataset_counts=dict(sorted(Counter(item.source_reference.dataset for item in workflows).items())),
    )
