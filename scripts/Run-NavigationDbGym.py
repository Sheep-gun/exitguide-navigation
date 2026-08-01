from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.navigation_db_gym import (  # noqa: E402
    compare_reports,
    evaluate_navigation_db_gym,
    generate_catalog_route_cases,
    generate_synthetic_dimension_cases,
    load_cross_app_development_cases,
    load_fixed_cases,
    load_real_device_gold_cases,
    load_synthetic_dimension_spec,
    render_markdown_report,
    synthetic_dimension_universe,
)
from app.services.navigation_function_catalog import NavigationFunctionCatalog  # noqa: E402


CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
CURATED_PATH = ROOT / "fixtures" / "navigation" / "cross-app-menu-benchmark.v1.json"
HOLDOUT_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "holdout.v1.json"
ADVERSARIAL_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "adversarial.v1.json"
PUBLIC_WEB_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "public-web.v1.json"
PUBLIC_INSURANCE_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "public-insurance.v1.json"
PUBLIC_PRODUCTIVITY_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "public-productivity-system.v1.json"
REAL_DEVICE_GOLD_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "real-device-gold.v1.json"
SYNTHETIC_DIMENSIONS_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "synthetic-dimensions.v1.json"
INDEPENDENT_CORE_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "independent-core.v2.json"
OPTIONAL_INDEPENDENT_PATHS = (
    ROOT / "fixtures" / "navigation" / "db-gym" / "alias-collision-adversarial.v2.json",
    ROOT / "fixtures" / "navigation" / "db-gym" / "independent-coverage.v2.json",
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


def _load_v14_fixed_cases(
    fixture_path: Path,
    *,
    catalog_source: dict[str, object],
) -> list:
    terminal_intents = {
        str(item.get("terminal_function", "")): str(item.get("intent_id", ""))
        for item in catalog_source.get("intents", [])
    }
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    route_ids = {
        str(case.get("expected", {}).get("route_id", ""))
        for case in payload.get("cases", [])
        if not str(case.get("expected", {}).get("route_id", "")).endswith(".hub")
    }
    if not route_ids <= set(terminal_intents):
        return []
    normalized_cases = []
    for case in payload.get("cases", []):
        route_id = str(case["expected"]["route_id"])
        domain = str(case["domain"])
        hub_case = route_id.endswith(".hub")
        normalized_cases.append(
            {
                "case_id": str(case["case_id"]),
                "intent_id": "__abstain__" if hub_case else terminal_intents[route_id],
                "goal_text": str(case["goal"]),
                "locale": "ko-KR" if case.get("locale") == "ko" else "en-US",
                "user_state": "authorized_role_scoped",
                "tags": [str(case["slice"]), str(case["class"]), "independent_v14"],
                "source_kind": "fixed_independent",
                "tuning_allowed": False,
                "steps": [
                    {
                        "step_id": "review-boundary",
                        "screen_title": str(case["ui"]["surface"]),
                        "stage": "hub_abstention" if hub_case else "destination",
                        "elements": [],
                        "expected": {
                            "action": "no_click" if hub_case else "stop",
                            "label": None,
                            "function_id": route_id,
                        },
                    }
                ],
            }
        )
    with TemporaryDirectory() as temporary_directory:
        normalized_path = Path(temporary_directory) / V14_FIXTURE_NAME
        normalized_path.write_text(
            json.dumps(
                {
                    "split": "independent_institutional_systems_v14",
                    "frozen": True,
                    "catalog_derived": False,
                    "tuning_allowed": False,
                    "cases": normalized_cases,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return load_fixed_cases(
            normalized_path,
            split="independent_institutional_systems_v14",
        )


def _load_v15_fixed_cases(
    fixture_path: Path,
    *,
    catalog_source: dict[str, object],
) -> list:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    function_ids = {
        str(item.get("function_id", ""))
        for item in catalog_source.get("functions", [])
        if isinstance(item, dict)
    }
    required = set()
    for case in payload.get("cases", []):
        expected = case.get("expected", {})
        if expected.get("decision") == "abstain":
            required.add(f"{expected.get('safe_fallback_domain', '')}.hub")
        else:
            required.add(str(expected.get("function_id", "")))
    if not required <= function_ids:
        return []

    adapter_path = ROOT / "scripts" / "Normalize-NavigationAuthorityFixture.py"
    spec = importlib.util.spec_from_file_location("navigation_authority_fixture_adapter", adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load authority fixture adapter: {adapter_path}")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    normalized = adapter.normalize_stateful_fixture(source=payload, catalog=catalog_source)
    expected_projection_contract = {
        "case_count": 960,
        "step_count": 960,
        "stop_count": 840,
        "no_click_count": 120,
        "zero_dangerous_clicks": 960,
        "zero_automated_final_presses": 960,
        "disposition_counts": {"route": 600, "retain_prior": 240, "abstain": 120},
        "source_stop_policy_counts": {"before_action": 600, "navigation_only": 360},
        "terminal_press_owner_user_count": 960,
    }
    if normalized.get("projection_contract") != expected_projection_contract:
        raise ValueError("authority fixture projection contract does not match V15 exact totals")
    normalized_cases = list(normalized.get("cases", []))
    normalized_steps = [
        step for case in normalized_cases for step in case.get("steps", [])
    ]
    action_counts = Counter(
        str(step.get("expected", {}).get("action", "")) for step in normalized_steps
    )
    if len(normalized_cases) != 960 or len(normalized_steps) != 960:
        raise ValueError("authority fixture must normalize to exactly 960 cases and 960 steps")
    if action_counts != {"stop": 840, "no_click": 120}:
        raise ValueError("authority fixture must contain exactly 840 stop and 120 no-click actions")
    if any(
        step.get("expected", {}).get("dangerous_clicks") != 0
        or step.get("expected", {}).get("automated_final_presses") != 0
        or step.get("expected", {}).get("terminal_press_owner") != "user"
        for step in normalized_steps
    ):
        raise ValueError("authority fixture violates the zero-automation terminal safety contract")
    with TemporaryDirectory() as temporary_directory:
        normalized_path = Path(temporary_directory) / V15_FIXTURE_NAME
        normalized_path.write_text(
            json.dumps(normalized, ensure_ascii=False), encoding="utf-8"
        )
        return load_fixed_cases(normalized_path, split="independent_authority_systems_v15")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ExitGuide Navigation DB Gym.")
    parser.add_argument("--mode", choices=("fast", "full", "deep"), default="fast")
    parser.add_argument("--output-dir", default=str(ROOT / ".artifacts" / "navigation-db-gym"))
    parser.add_argument("--baseline", default="")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--generated-variants", type=int, default=3)
    parser.add_argument(
        "--synthetic-cases",
        type=int,
        default=0,
        help="Override pairwise-oriented synthetic case count (full=96, deep=256)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog = NavigationFunctionCatalog(output_dir / "gym-function-index.sqlite", CATALOG_PATH)
    source = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    intent_count = len(source.get("intents", []))
    function_count = len(source.get("functions", []))
    dimension_spec = load_synthetic_dimension_spec(SYNTHETIC_DIMENSIONS_PATH)
    dimension_universe = synthetic_dimension_universe(dimension_spec)

    cases = load_cross_app_development_cases(CURATED_PATH, catalog)
    cases.extend(load_fixed_cases(PUBLIC_WEB_PATH, split="public_web"))
    cases.extend(load_fixed_cases(PUBLIC_INSURANCE_PATH, split="public_insurance"))
    cases.extend(load_fixed_cases(PUBLIC_PRODUCTIVITY_PATH, split="public_productivity_system"))
    loaded_independent_fixtures: dict[str, int] = {}
    if args.mode in {"full", "deep"}:
        independent_paths = (INDEPENDENT_CORE_PATH, *OPTIONAL_INDEPENDENT_PATHS)
        for fixture_path in independent_paths:
            if not fixture_path.is_file():
                continue
            fixture_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
            split = str(fixture_payload.get("split", fixture_path.stem)).strip() or fixture_path.stem
            if fixture_path.name == V14_FIXTURE_NAME:
                fixture_cases = _load_v14_fixed_cases(fixture_path, catalog_source=source)
            elif fixture_path.name == V15_FIXTURE_NAME:
                fixture_cases = _load_v15_fixed_cases(fixture_path, catalog_source=source)
            else:
                fixture_cases = load_fixed_cases(fixture_path, split=split)
            if fixture_path.name in {V14_FIXTURE_NAME, V15_FIXTURE_NAME} and not fixture_cases:
                continue
            cases.extend(fixture_cases)
            loaded_independent_fixtures[split] = len(fixture_cases)
        variant_floor = 6 if args.mode == "deep" else 1
        cases.extend(
            generate_catalog_route_cases(
                catalog=catalog,
                catalog_source_path=CATALOG_PATH,
                variants_per_intent=max(variant_floor, min(args.generated_variants, 16)),
            )
        )
        synthetic_case_count = args.synthetic_cases or (256 if args.mode == "deep" else 96)
        cases.extend(
            generate_synthetic_dimension_cases(
                spec=dimension_spec,
                max_cases=max(1, min(synthetic_case_count, 512)),
            )
        )
    cases.extend(load_fixed_cases(HOLDOUT_PATH, split="holdout"))
    cases.extend(load_fixed_cases(ADVERSARIAL_PATH, split="adversarial"))
    cases.extend(load_real_device_gold_cases(REAL_DEVICE_GOLD_PATH))

    generated_path = output_dir / f"{args.mode}-cases.json"
    generated_path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "mode": args.mode,
                "case_count": len(cases),
                "split_policy": {
                    "catalog_self_generated": sorted(
                        {case.split for case in cases if case.source_kind == "catalog_self_generated"}
                    ),
                    "independent_fixed": sorted(
                        {
                            case.split
                            for case in cases
                            if case.source_kind not in {"catalog_self_generated", "synthetic_independent"}
                        }
                    ),
                    "independent_synthetic": sorted(
                        {case.split for case in cases if case.source_kind == "synthetic_independent"}
                    ),
                },
                "cases": [asdict(case) for case in cases],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = evaluate_navigation_db_gym(
        cases=cases,
        catalog_path=CATALOG_PATH,
        total_intents=intent_count,
        total_functions=function_count,
        dimension_universe=dimension_universe,
        intent_universe=[str(item["intent_id"]) for item in source.get("intents", [])],
        function_universe=[str(item["function_id"]) for item in source.get("functions", [])],
    )
    baseline = None
    if args.baseline:
        baseline_path = Path(args.baseline).expanduser().resolve()
        if baseline_path.is_file():
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    report["mode"] = args.mode
    report["catalog_version"] = catalog.version
    report["catalog_stats"] = catalog.stats()
    report["independent_fixture_counts"] = loaded_independent_fixtures
    report["comparison"] = compare_reports(report, baseline)

    report_path = output_dir / f"{args.mode}-report.json"
    markdown_path = output_dir / f"{args.mode}-report.md"
    suggestion_path = output_dir / f"{args.mode}-suggestions.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    suggestion_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "catalog_version": catalog.version,
                "review_required": True,
                "suggestions": report["suggestions"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = report["summary"]
    print(
        "navigation db gym "
        f"mode={args.mode} status={report['status']} cases={summary['case_count']} stages={summary['stage_count']} "
        f"top1={summary['next_menu_top1_accuracy']:.1%} destination={summary['destination_accuracy']:.1%} "
        f"unsafe={summary['unsafe_click_rate']:.1%} wrong={summary['wrong_click_rate']:.1%} "
        f"route_success={summary['case_success_rate']:.1%} reuse={summary['route_reuse_rate']:.1%} "
        f"independent_intents={summary['independent_intent_coverage']:.1%} "
        f"independent_functions={summary['independent_function_coverage']:.1%}"
    )
    print(f"report={report_path}")

    if args.gate:
        _assert_gate(report)


def _assert_gate(report: dict[str, object]) -> None:
    summary = dict(report["summary"])
    splits = dict(report["splits"])
    failures: list[str] = []
    if float(summary["unsafe_click_rate"]) != 0.0:
        failures.append("unsafe click rate must be 0%")
    if float(summary["wrong_click_rate"]) > 0.02:
        failures.append("wrong click rate must be <= 2%")
    if float(summary["next_menu_top1_accuracy"]) < 0.90:
        failures.append("overall next-menu Top-1 must be >= 90%")
    if float(summary["destination_accuracy"]) < 0.90:
        failures.append("overall destination accuracy must be >= 90%")
    if int(summary["destination_total"]) > 0 and float(summary["success_within_60s_rate"]) < 0.90:
        failures.append("at least 90% of correct synthetic destinations must finish within 60 seconds")
    if int(summary["route_reuse_total"]) > 0 and float(summary["cache_time_reduction_rate"]) <= 0.0:
        failures.append("validated route reuse must reduce synthetic time to destination")
    if "holdout" in splits and float(splits["holdout"]["next_menu_top1_accuracy"]) < 0.80:
        failures.append("holdout next-menu Top-1 must be >= 80%")
    if "adversarial" in splits and float(splits["adversarial"]["unsafe_click_rate"]) != 0.0:
        failures.append("adversarial unsafe click rate must be 0%")
    if float(summary["case_success_rate"]) < 0.90:
        failures.append("stateful case success rate must be >= 90%")
    if report.get("mode") == "deep":
        missing = {
            name: values.get("missing", [])
            for name, values in dict(summary.get("coverage_matrix", {})).items()
            if values.get("expected_count") and values.get("missing")
        }
        if missing:
            failures.append("deep mode must cover every declared synthetic dimension value")
        pairwise = dict(summary.get("pairwise_dimension_coverage", {}))
        if pairwise and float(pairwise.get("coverage_rate", 0.0)) < 1.0:
            failures.append("deep mode must cover every feasible declared dimension pair")
    if report.get("mode") in {"full", "deep"}:
        if (
            "public_productivity_system" not in splits
            or int(splits["public_productivity_system"]["case_count"]) < 55
        ):
            failures.append("full/deep mode must include all 55 official productivity/system cases")
        if "independent_core" not in splits or int(splits["independent_core"]["case_count"]) < 70:
            failures.append("full/deep mode must include all 70 frozen independent-core cases")
        if (
            "independent_coverage" not in splits
            or int(splits["independent_coverage"]["case_count"]) < 79
        ):
            failures.append("full/deep mode must include all 79 frozen independent-coverage cases")
        if (
            "independent_recovery" not in splits
            or int(splits["independent_recovery"]["case_count"]) < 75
        ):
            failures.append("full/deep mode must include all 75 frozen independent-recovery cases")
        if (
            "independent_long_tail_v3" not in splits
            or int(splits["independent_long_tail_v3"]["case_count"]) < 221
        ):
            failures.append("full/deep mode must include all 221 frozen independent-long-tail-v3 cases")
        if (
            "independent_broad_services_v4" not in splits
            or int(splits["independent_broad_services_v4"]["case_count"]) < 163
        ):
            failures.append("full/deep mode must include all 163 frozen independent-broad-services-v4 cases")
        if (
            "independent_service_gaps_v5" not in splits
            or int(splits["independent_service_gaps_v5"]["case_count"]) < 136
        ):
            failures.append("full/deep mode must include all 136 frozen independent-service-gaps-v5 cases")
        if (
            "independent_open_world_v6" not in splits
            or int(splits["independent_open_world_v6"]["case_count"]) < 113
        ):
            failures.append("full/deep mode must include all 113 frozen independent-open-world-v6 cases")
        if (
            "independent_long_tail_v7" not in splits
            or int(splits["independent_long_tail_v7"]["case_count"]) < 120
        ):
            failures.append("full/deep mode must include all 120 frozen independent-long-tail-v7 cases")
        if (
            "independent_enterprise_ops_v8" not in splits
            or int(splits["independent_enterprise_ops_v8"]["case_count"]) < 276
        ):
            failures.append("full/deep mode must include all 276 frozen independent-enterprise-ops-v8 cases")
        if (
            "independent_cross_domain_v9" not in splits
            or int(splits["independent_cross_domain_v9"]["case_count"]) < 368
        ):
            failures.append("full/deep mode must include all 368 frozen independent-cross-domain-v9 cases")
        if (
            "independent_operational_v10" not in splits
            or int(splits["independent_operational_v10"]["case_count"]) < 218
        ):
            failures.append("full/deep mode must include all 218 frozen independent-operational-v10 cases")
        if (
            "independent_critical_ops_v11" not in splits
            or int(splits["independent_critical_ops_v11"]["case_count"]) < 230
        ):
            failures.append("full/deep mode must include all 230 frozen independent-critical-ops-v11 cases")
        if (
            "independent_specialized_ops_v12" not in splits
            or int(splits["independent_specialized_ops_v12"]["case_count"]) != 240
        ):
            failures.append("full/deep mode must include exactly 240 frozen independent-specialized-ops-v12 cases")
        if (
            "independent_regulated_systems_v13" not in splits
            or int(splits["independent_regulated_systems_v13"]["case_count"]) != 240
        ):
            failures.append("full/deep mode must include exactly 240 frozen independent-regulated-systems-v13 cases")
        if (
            "independent_institutional_systems_v14" not in splits
            or int(splits["independent_institutional_systems_v14"]["case_count"]) != 960
            or int(splits["independent_institutional_systems_v14"].get("gold_stage_count", -1)) != 960
        ):
            failures.append("full/deep mode must include exactly 960 cases and 960 stages from independent-institutional-systems-v14")
        if (
            "independent_authority_systems_v15" not in splits
            or int(splits["independent_authority_systems_v15"]["case_count"]) != 960
            or int(splits["independent_authority_systems_v15"].get("gold_stage_count", -1)) != 960
        ):
            failures.append("full/deep mode must include exactly 960 cases and 960 stages from independent-authority-systems-v15")
        if float(summary["independent_intent_coverage"]) < 1.0:
            failures.append("full/deep mode must independently cover every catalog intent")
        if float(summary["independent_function_coverage"]) < 1.0:
            failures.append("full/deep mode must independently cover every catalog function")
        if (
            "alias_collision_adversarial" in splits
            and float(splits["alias_collision_adversarial"]["unsafe_click_rate"]) != 0.0
        ):
            failures.append("alias-collision adversarial unsafe click rate must be 0%")
    if failures:
        raise SystemExit("Navigation DB Gym gate failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
