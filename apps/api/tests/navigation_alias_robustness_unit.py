from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_alias_robustness import evaluate_alias_collisions  # noqa: E402


CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"


def main() -> None:
    report = evaluate_alias_collisions(catalog_path=CATALOG, maximum_groups=4)
    assert report["catalog_derived"] is True
    assert report["independent_accuracy_claim"] is False
    assert report["total_collision_group_count"] >= report["evaluated_collision_group_count"] == 4
    assert report["positive"]["total"] >= 8
    assert report["negative_rejection"]["total"] >= 8
    assert not report["unresolved_context_owners"]
    assert 0.90 <= report["positive"]["accuracy"] <= 1.0
    assert 0.90 <= report["negative_rejection"]["accuracy"] <= 1.0
    print(
        "navigation alias robustness checks ok: "
        f"groups={report['evaluated_collision_group_count']} "
        f"positive={report['positive']['correct']}/{report['positive']['total']} "
        f"negative={report['negative_rejection']['correct']}/{report['negative_rejection']['total']}"
    )


if __name__ == "__main__":
    main()
