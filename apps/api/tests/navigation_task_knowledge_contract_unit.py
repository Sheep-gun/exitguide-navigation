from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "Validate-NavigationTaskKnowledge.py"
SPEC = importlib.util.spec_from_file_location("task_knowledge_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _record(task_id: str = "fixture:1") -> dict[str, object]:
    return {
        "schema_version": "navigation-task-knowledge.v1",
        "task_id": task_id,
        "goal": "Open subscription settings and review available management options.",
        "task_type": "input",
        "source_name": "fixture",
        "source_dataset": "fixture-dataset",
        "source_revision": "fixture-revision",
        "license": "cc-by-nc-sa-4.0",
        "role": "goal_ontology_and_ambiguity_auxiliary",
        "core_experience_eligible": False,
        "reason": "no linked structured action outcome",
        "curation": {
            "policy_version": "navigation-curation-policy.v2",
            "tier": "task_knowledge",
            "service_categories": ["subscription_billing"],
            "reason": "service_goal_task_knowledge",
        },
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_task_knowledge_contract_is_advisory_only() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "tasks.jsonl"
        _write_jsonl(source, [_record()])
        report = MODULE.validate_jsonl(source, MODULE.DEFAULT_SCHEMA)
        assert report["rows"] == 1
        assert report["unique_task_ids"] == 1
        assert report["runtime_execution_allowed"] is False
        assert report["canonical_promotion_allowed"] is False


def test_task_knowledge_contract_rejects_executable_claim() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "tasks.jsonl"
        record = _record()
        record["core_experience_eligible"] = True
        _write_jsonl(source, [record])
        try:
            MODULE.validate_jsonl(source, MODULE.DEFAULT_SCHEMA)
        except ValueError as error:
            assert "False was expected" in str(error)
        else:
            raise AssertionError("task knowledge must never claim core experience eligibility")


def test_task_knowledge_contract_rejects_duplicate_ids() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "tasks.jsonl"
        _write_jsonl(source, [_record(), _record()])
        try:
            MODULE.validate_jsonl(source, MODULE.DEFAULT_SCHEMA)
        except ValueError as error:
            assert "duplicate task_id" in str(error)
        else:
            raise AssertionError("task IDs must be unique")


if __name__ == "__main__":
    test_task_knowledge_contract_is_advisory_only()
    test_task_knowledge_contract_rejects_executable_claim()
    test_task_knowledge_contract_rejects_duplicate_ids()
    print("navigation task knowledge contract checks passed")
