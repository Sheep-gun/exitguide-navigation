from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.navigation_goal_robustness import evaluate_goal_robustness  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate metamorphic goal interpretation robustness.")
    parser.add_argument("--mode", choices=("fast", "full"), default="fast")
    parser.add_argument("--catalog", default=str(ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"))
    parser.add_argument("--output-dir", default=str(ROOT / ".artifacts" / "navigation-goal-robustness"))
    parser.add_argument("--minimum-accuracy", type=float, default=0.995)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = evaluate_goal_robustness(Path(args.catalog).resolve(), mode=args.mode)
    output_path = output_dir / f"{args.mode}-report.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"navigation goal robustness mode={args.mode} accuracy={report['accuracy']:.2%} "
        f"cases={report['total']} intents={report['intent_count']} failures={len(report['failures'])}"
    )
    print(f"report={output_path}")
    if args.gate and float(report["accuracy"]) < args.minimum_accuracy:
        raise SystemExit(
            f"Goal robustness gate failed: {report['accuracy']:.4f} < {args.minimum_accuracy:.4f}"
        )


if __name__ == "__main__":
    main()
