from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.navigation_alias_robustness import evaluate_alias_collisions  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate exact UI-alias collision disambiguation with catalog contexts."
    )
    parser.add_argument(
        "--catalog",
        default=str(ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".artifacts" / "navigation-alias-robustness" / "report.json"),
    )
    parser.add_argument("--maximum-groups", type=int, default=0)
    parser.add_argument("--minimum-positive-accuracy", type=float, default=0.90)
    parser.add_argument("--minimum-negative-accuracy", type=float, default=0.75)
    parser.add_argument("--maximum-unresolved", type=int, default=0)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()

    report = evaluate_alias_collisions(
        catalog_path=Path(args.catalog).expanduser().resolve(),
        maximum_groups=max(0, int(args.maximum_groups)),
    )
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "navigation alias robustness "
        f"groups={report['evaluated_collision_group_count']}/{report['total_collision_group_count']} "
        f"positive={report['positive']['correct']}/{report['positive']['total']} "
        f"({report['positive']['accuracy']:.2%}) "
        f"negative={report['negative_rejection']['correct']}/{report['negative_rejection']['total']} "
        f"({report['negative_rejection']['accuracy']:.2%}) "
        f"unresolved={len(report['unresolved_context_owners'])}"
    )
    print(f"report={output_path}")
    if not args.gate:
        return
    failures: list[str] = []
    if float(report["positive"]["accuracy"]) < args.minimum_positive_accuracy:
        failures.append(
            f"positive {report['positive']['accuracy']:.4f} < {args.minimum_positive_accuracy:.4f}"
        )
    if float(report["negative_rejection"]["accuracy"]) < args.minimum_negative_accuracy:
        failures.append(
            f"negative {report['negative_rejection']['accuracy']:.4f} < {args.minimum_negative_accuracy:.4f}"
        )
    unresolved = len(report["unresolved_context_owners"])
    if unresolved > args.maximum_unresolved:
        failures.append(f"unresolved {unresolved} > {args.maximum_unresolved}")
    if failures:
        raise SystemExit("Alias robustness gate failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
