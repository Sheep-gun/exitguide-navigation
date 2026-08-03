from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = (
    ROOT
    / "db"
    / "contracts"
    / "shared_app_knowledge_v0_9_1"
    / "navigation-task-knowledge.v1.schema.json"
)


def validate_jsonl(source: Path, schema_path: Path) -> dict[str, Any]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    task_ids: set[str] = set()
    categories: Counter[str] = Counter()
    rows = 0

    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            rows += 1
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"line {line_number}: invalid JSON: {error}") from error
            errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
            if errors:
                first = errors[0]
                location = ".".join(str(part) for part in first.path) or "$"
                raise ValueError(f"line {line_number} at {location}: {first.message}")
            task_id = str(payload["task_id"])
            if task_id in task_ids:
                raise ValueError(f"line {line_number}: duplicate task_id {task_id}")
            task_ids.add(task_id)
            categories.update(payload["curation"]["service_categories"])

    if rows == 0:
        raise ValueError("task knowledge JSONL is empty")
    return {
        "valid": True,
        "schema_version": "navigation-task-knowledge.v1",
        "rows": rows,
        "unique_task_ids": len(task_ids),
        "service_categories": dict(sorted(categories.items())),
        "runtime_execution_allowed": False,
        "canonical_promotion_allowed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate advisory Navigation Task Knowledge JSONL."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    arguments = parser.parse_args()
    report = validate_jsonl(arguments.source.resolve(), arguments.schema.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
