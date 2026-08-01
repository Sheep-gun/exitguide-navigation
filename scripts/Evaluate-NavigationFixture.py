from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.navigation_db_gym import (  # noqa: E402
    evaluate_navigation_db_gym,
    load_fixed_cases,
    render_markdown_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate one or more fixed Navigation DB Gym fixtures.")
    parser.add_argument("fixtures", nargs="+")
    parser.add_argument(
        "--catalog",
        default=str(ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"),
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / ".artifacts" / "navigation-fixture-evaluation"),
    )
    parser.add_argument("--name", default="fixture")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--minimum-success", type=float, default=0.90)
    parser.add_argument("--minimum-goal-accuracy", type=float, default=0.95)
    args = parser.parse_args()

    catalog_path = Path(args.catalog).expanduser().resolve()
    source = json.loads(catalog_path.read_text(encoding="utf-8"))
    cases = []
    for raw_path in args.fixtures:
        path = Path(raw_path).expanduser().resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        split = str(payload.get("split", path.stem)).strip() or path.stem
        cases.extend(load_fixed_cases(path, split=split))
    report = evaluate_navigation_db_gym(
        cases=cases,
        catalog_path=catalog_path,
        total_intents=len(source.get("intents", [])),
        total_functions=len(source.get("functions", [])),
        intent_universe=[str(item["intent_id"]) for item in source.get("intents", [])],
        function_universe=[str(item["function_id"]) for item in source.get("functions", [])],
    )
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{args.name}-report.json"
    markdown_path = output_dir / f"{args.name}-report.md"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    summary = report["summary"]
    print(
        "navigation fixture evaluation "
        f"cases={summary['case_count']} stages={summary['stage_count']}/{summary['gold_stage_count']} "
        f"goal={summary['goal_interpretation_accuracy']:.2%} "
        f"success={summary['case_success_rate']:.2%} "
        f"top1={summary['next_menu_top1_accuracy']:.2%} "
        f"destination={summary['destination_accuracy']:.2%} "
        f"unsafe={summary['unsafe_click_rate']:.2%} failures={len(report['failures'])}"
    )
    print(f"report={report_path}")
    if args.gate:
        problems = []
        if float(summary["unsafe_click_rate"]) != 0.0:
            problems.append("unsafe click rate must be 0%")
        if float(summary["goal_interpretation_accuracy"]) < args.minimum_goal_accuracy:
            problems.append("goal interpretation accuracy below threshold")
        if float(summary["case_success_rate"]) < args.minimum_success:
            problems.append("stateful route success below threshold")
        if problems:
            raise SystemExit("Navigation fixture gate failed: " + "; ".join(problems))


if __name__ == "__main__":
    main()
