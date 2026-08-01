import json
from pathlib import Path

from app.services.goals import GOAL_LABELS


ROOT = Path(__file__).resolve().parents[3]
GOALS_PATH = ROOT / "contracts" / "goals.v1.json"


def main() -> None:
    payload = json.loads(GOALS_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"

    goals = payload["goals"]
    contract_labels = {goal["id"]: goal["label_ko"] for goal in goals}
    assert len(contract_labels) == len(goals), "Shared goal IDs must be unique"
    assert contract_labels == GOAL_LABELS, "Backend goal catalog must match contracts/goals.v1.json"

    print("shared contract checks ok")


if __name__ == "__main__":
    main()
