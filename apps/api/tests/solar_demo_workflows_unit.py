from app.services.solar_demo_workflows import load_solar_demo_workflows


def main() -> None:
    catalog = load_solar_demo_workflows()

    assert catalog.metadata.dataset_schema_version == "1.0"
    assert catalog.metadata.source_dataset == "data_go_kr_kca_standard_answers"
    assert catalog.metadata.legal_advice_policy == "not_legal_advice"
    assert catalog.summary.workflow_count == 6
    assert catalog.summary.risk_counts["medium"] == 3
    assert catalog.summary.risk_counts["needs_check"] == 2
    assert catalog.summary.risk_counts["high"] == 1

    workflows_by_case = {workflow.case_number: workflow for workflow in catalog.workflows}
    assert workflows_by_case["873"].model_result.risk_level == "medium"
    assert workflows_by_case["435"].model_result.risk_level == "high"

    for workflow in catalog.workflows:
        assert workflow.model_result.reference_guidance.not_legal_advice is True
        assert workflow.demo_input.visible_screen_text
        assert workflow.model_result.goal_conflicts
        assert workflow.model_result.recommended_action.primary

    print("solar demo workflow checks ok")


if __name__ == "__main__":
    main()
