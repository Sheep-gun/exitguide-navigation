from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.navigation_goal_generalization import evaluate_independent_goals  # noqa: E402


DEFAULT_FIXTURES = (
    ROOT / "fixtures" / "navigation" / "db-gym" / "public-web.v1.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "public-insurance.v1.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "public-productivity-system.v1.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-core.v2.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "alias-collision-adversarial.v2.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-coverage.v2.json",
)
OPTIONAL_FIXTURES = (
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-recovery.v2.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-long-tail-v3.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-broad-services-v4.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-service-gaps-v5.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-open-world-v6.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-long-tail-v7.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-enterprise-ops-v8.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-cross-domain-v9.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-operational-v10.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-critical-ops-v11.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-specialized-ops-v12.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-regulated-systems-v13.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-institutional-systems-v14.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-authority-systems-v15.json",
)
V14_FIXTURE_NAME = "independent-institutional-systems-v14.json"
V15_FIXTURE_NAME = "independent-authority-systems-v15.json"


def _normalize_v14_goal_fixture(
    source_path: Path,
    catalog_path: Path,
    output_path: Path,
) -> Path | None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    terminal_intents = {
        str(item.get("terminal_function", "")): str(item.get("intent_id", ""))
        for item in catalog.get("intents", [])
    }
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    routable = [
        case
        for case in payload.get("cases", [])
        if case.get("expected", {}).get("disposition") != "abstain_at_hub"
    ]
    if not {
        str(case["expected"]["route_id"]) for case in routable
    } <= set(terminal_intents):
        return None
    output_path.write_text(
        json.dumps(
            {
                "split": "independent_institutional_systems_v14",
                "frozen": True,
                "catalog_derived": False,
                "tuning_allowed": False,
                "cases": [
                    {
                        "case_id": str(case["case_id"]),
                        "intent_id": terminal_intents[str(case["expected"]["route_id"])],
                        "goal_text": str(case["goal"]),
                        "locale": "ko-KR" if case.get("locale") == "ko" else "en-US",
                    }
                    for case in routable
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _normalize_v15_goal_fixture(
    source_path: Path,
    catalog_path: Path,
    output_path: Path,
) -> Path | None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if (
        catalog.get("catalog_version") != "15.0.0"
        or len(catalog.get("functions", [])) != 2866
        or len(catalog.get("intents", [])) != 2660
    ):
        return None

    adapter_path = ROOT / "scripts" / "Normalize-NavigationAuthorityFixture.py"
    spec = importlib.util.spec_from_file_location("navigation_authority_fixture_adapter", adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load authority fixture adapter: {adapter_path}")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    normalized = adapter.normalize_goal_fixture(source=source, catalog=catalog)
    output_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate intent resolution on independent goals.")
    parser.add_argument(
        "--catalog",
        default=str(ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".artifacts" / "navigation-goal-generalization" / "report.json"),
    )
    parser.add_argument("--minimum-accuracy", type=float, default=0.95)
    parser.add_argument("--minimum-split-accuracy", type=float, default=0.90)
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("fixtures", nargs="*")
    args = parser.parse_args()

    fixture_paths = (
        [Path(value).expanduser().resolve() for value in args.fixtures]
        if args.fixtures
        else [*DEFAULT_FIXTURES, *(path for path in OPTIONAL_FIXTURES if path.is_file())]
    )
    catalog_path = Path(args.catalog).expanduser().resolve()
    with TemporaryDirectory() as temporary_directory:
        evaluation_paths: list[Path] = []
        for fixture_path in fixture_paths:
            if fixture_path.name not in {V14_FIXTURE_NAME, V15_FIXTURE_NAME}:
                evaluation_paths.append(fixture_path)
                continue
            if fixture_path.name == V14_FIXTURE_NAME:
                normalized = _normalize_v14_goal_fixture(
                    fixture_path,
                    catalog_path,
                    Path(temporary_directory) / V14_FIXTURE_NAME,
                )
            else:
                normalized = _normalize_v15_goal_fixture(
                    fixture_path,
                    catalog_path,
                    Path(temporary_directory) / V15_FIXTURE_NAME,
                )
            if normalized is not None:
                evaluation_paths.append(normalized)
            elif args.fixtures:
                version = "V14" if fixture_path.name == V14_FIXTURE_NAME else "V15"
                raise SystemExit(
                    f"The {version} independent fixture requires a projected or materialized {version} catalog"
                )
        report = evaluate_independent_goals(
            catalog_path=catalog_path,
            fixture_paths=evaluation_paths,
        )
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "navigation independent goals "
        f"accuracy={report['accuracy']:.2%} correct={report['correct']}/{report['total']} "
        f"generic={report['generic_rate']:.2%} failures={len(report['failures'])}"
    )
    print(f"report={output_path}")
    if args.gate and float(report["accuracy"]) < args.minimum_accuracy:
        raise SystemExit(
            f"Independent goal gate failed: {report['accuracy']:.4f} < {args.minimum_accuracy:.4f}"
        )
    if args.gate:
        weak_splits = {
            split: values["accuracy"]
            for split, values in report["split_results"].items()
            if float(values["accuracy"]) < args.minimum_split_accuracy
        }
        if weak_splits:
            raise SystemExit(
                "Independent goal split gate failed: "
                + ", ".join(
                    f"{split}={accuracy:.4f}"
                    for split, accuracy in sorted(weak_splits.items())
                )
            )


if __name__ == "__main__":
    main()
