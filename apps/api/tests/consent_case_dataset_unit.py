from copy import deepcopy

from app.schemas import ConsentCaseDefinition
from app.services.case_dataset import _validate_case_dataset, load_consent_case_catalog


def main() -> None:
    catalog = load_consent_case_catalog()
    assert catalog.metadata.dataset_schema_version == "1.0"
    assert catalog.metadata.label_rubric_version == "1.0"
    assert catalog.summary.case_count == 14
    assert catalog.summary.risk_counts["medium"] == 2
    assert catalog.summary.tag_counts["false_positive_guard"] == 3

    valid_case = catalog.cases[0].model_dump()

    expect_invalid(
        [valid_case, valid_case],
        "duplicate case id",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case["elements"][1].update({"id": case["elements"][0]["id"]}))],
        "duplicate element id",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case.update({"locale": "en-US"}))],
        "locale must be ko-KR",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case.update({"recommended_goal_id": "unknown_goal"}))],
        "invalid recommended_goal_id",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case.update({"screen_text": ""}))],
        "empty screen_text",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case.update({"expected_risk": "low"}))],
        "expected_risk should match highest element risk",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case["source"].update({"raw_artifact_in_repo": True}))],
        "must not store raw artifacts",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case["source"].update({"contains_raw_screenshot": True}))],
        "must not include raw screenshots",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case["source"].update({"contains_ocr_text": True}))],
        "OCR text must be redacted",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case["source"].update({"public_fixture_allowed": False}))],
        "must be approved before appearing",
    )
    expect_invalid(
        [
            mutated(
                valid_case,
                lambda case: (
                    case.update({"source_type": "field_candidate"}),
                    case["source"].update(
                        {
                            "capture_method": "manual_field_observation",
                            "artifact_type": "redacted_text_only",
                            "redaction_status": "pending_review",
                            "review_status": "pending_review",
                        }
                    ),
                ),
            )
        ],
        "non-synthetic case must be redacted",
    )
    expect_invalid(
        [mutated(valid_case, lambda case: case["source"].update({"notes": "Captured from https://example.com"}))],
        "source.notes contains forbidden url-like text",
    )

    print("consent case dataset checks ok")


def mutated(case: dict, edit) -> dict:
    updated = deepcopy(case)
    edit(updated)
    return updated


def expect_invalid(raw_cases: list[dict], expected_detail: str) -> None:
    cases = [ConsentCaseDefinition.model_validate(raw_case) for raw_case in raw_cases]
    try:
        _validate_case_dataset(cases)
    except ValueError as exc:
        assert expected_detail in str(exc), str(exc)
        return
    raise AssertionError(f"Expected invalid consent dataset: {expected_detail}")


if __name__ == "__main__":
    main()
