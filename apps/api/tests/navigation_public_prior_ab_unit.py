from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "Compare-NavigationPublicPriorAB.py"
SPEC = importlib.util.spec_from_file_location("public_prior_ab", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _report(*, enabled: bool, accuracy: float, dangerous: int = 0) -> dict[str, object]:
    return {
        "case_count": 10,
        "evaluation_cases_sha256": "cases-sha",
        "database_sha256": "decision-sha",
        "public_prior": {"enabled": enabled},
        "positive_exact_next_action_accuracy": accuracy,
        "positive_first_action_accuracy": accuracy,
        "failed_click_avoidance_rate": 1.0,
        "recognized_goal_rate": 1.0,
        "dangerous_auto_click_count": dangerous,
    }


def test_ab_accepts_real_improvement_without_regression() -> None:
    result = MODULE.compare(
        _report(enabled=False, accuracy=0.6),
        _report(enabled=True, accuracy=0.7),
    )
    assert result["passed"] is True


def test_ab_rejects_no_improvement() -> None:
    result = MODULE.compare(
        _report(enabled=False, accuracy=0.7),
        _report(enabled=True, accuracy=0.7),
    )
    assert result["passed"] is False


def test_ab_rejects_safety_regression() -> None:
    result = MODULE.compare(
        _report(enabled=False, accuracy=0.6),
        _report(enabled=True, accuracy=0.7, dangerous=1),
    )
    assert result["passed"] is False


if __name__ == "__main__":
    test_ab_accepts_real_improvement_without_regression()
    test_ab_rejects_no_improvement()
    test_ab_rejects_safety_regression()
    print("navigation public prior A/B checks passed")
