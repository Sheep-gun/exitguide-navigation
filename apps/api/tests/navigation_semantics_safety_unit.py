from __future__ import annotations

import sys
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_function_catalog import (  # noqa: E402
    CatalogGoalPlan,
    GOAL_GOVERNANCE_BLOCKED_INTENT,
)
from app.services.navigation_semantics import infer_goal_plan  # noqa: E402


class _GovernanceCatalog:
    def plan_goal(self, _goal_text: str) -> CatalogGoalPlan:
        return CatalogGoalPlan(
            intent=GOAL_GOVERNANCE_BLOCKED_INTENT,
            terminal_function="medical_device_regulatory_ops.hub",
            preferred_functions=(("medical_device_regulatory_ops.hub", 1.0),),
            avoid_functions=(
                "medical_device_regulatory_ops.device_shortage_notification_submit",
            ),
            confidence=0.99,
        )

    def function(self, function_id: str) -> object | None:
        # The notification override would otherwise be eligible.  Keeping the
        # target present proves the governance boundary, rather than a missing
        # catalog function, prevents the rewrite.
        return object() if function_id == "notification.settings" else None


def main() -> None:
    plan = infer_goal_plan(
        "Medical-device regulatory operations Device-shortage notification "
        "submission disabled control interlock",
        catalog=_GovernanceCatalog(),  # type: ignore[arg-type]
    )
    assert plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
    assert plan.terminal_function == "medical_device_regulatory_ops.hub"
    assert plan.preferred_functions == (("medical_device_regulatory_ops.hub", 1.0),)
    assert plan.avoid_functions == (
        "medical_device_regulatory_ops.device_shortage_notification_submit",
    )
    assert plan.confidence == 0.99
    print("Navigation semantics governance precedence checks passed.")


if __name__ == "__main__":
    main()
