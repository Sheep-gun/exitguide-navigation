from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.navigation_independent_coverage import audit_independent_coverage  # noqa: E402


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


def _normalize_v14_fixture(
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
    route_ids = {
        str(case.get("expected", {}).get("route_id", ""))
        for case in payload.get("cases", [])
        if not str(case.get("expected", {}).get("route_id", "")).endswith(".hub")
    }
    if not route_ids <= set(terminal_intents):
        return None
    surfaces = ("screen", "dialog", "drawer", "bottom_sheet", "webview", "scroll_view", "endless_feed", "system_dialog")
    states = ("ready", "loading", "offline", "error", "relogin_required", "permission_rationale", "stale_cache", "transient_error", "recovered", "confirmation_required", "repeated_content")
    normalized_cases = []
    for index, case in enumerate(payload.get("cases", [])):
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
                        "ui_surface": surfaces[index % len(surfaces)],
                        "screen_state": states[index % len(states)],
                        "elements": [
                            {
                                "id": "governed-decoy",
                                "label": str(case["ui"]["decoys"][0]),
                                "enabled": index % 7 != 0,
                                "visible": index % 11 != 0,
                                "selected": index % 13 == 0,
                                "checkable": index % 17 == 0,
                                "scrollable": index % 19 == 0,
                                "dangerous": index % 5 == 0,
                            },
                            {
                                "id": "icon-only-decoy",
                                "label": "",
                                "content_description": str(case["ui"]["decoys"][1]),
                            },
                        ],
                        "expected": {
                            "action": "no_click" if hub_case else "stop",
                            "label": None,
                            "function_id": route_id,
                        },
                    }
                ],
            }
        )
    output_path.write_text(
        json.dumps(
            {
                "split": "independent_institutional_systems_v14",
                "frozen": True,
                "catalog_derived": False,
                "tuning_allowed": False,
                "cases": normalized_cases,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _normalize_v15_fixture(
    source_path: Path,
    catalog_path: Path,
    output_path: Path,
) -> Path | None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    source = json.loads(source_path.read_text(encoding="utf-8"))
    function_ids = {
        str(item.get("function_id", ""))
        for item in catalog.get("functions", [])
        if isinstance(item, dict)
    }
    required = set()
    for case in source.get("cases", []):
        expected = case.get("expected", {})
        if expected.get("decision") == "abstain":
            required.add(f"{expected.get('safe_fallback_domain', '')}.hub")
        else:
            required.add(str(expected.get("function_id", "")))
    if not required <= function_ids:
        return None

    adapter_path = ROOT / "scripts" / "Normalize-NavigationAuthorityFixture.py"
    spec = importlib.util.spec_from_file_location("navigation_authority_fixture_adapter", adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load authority fixture adapter: {adapter_path}")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    normalized = adapter.normalize_stateful_fixture(source=source, catalog=catalog)
    output_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit frozen independent Navigation DB coverage.")
    parser.add_argument(
        "--catalog",
        default=str(ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / ".artifacts" / "navigation-independent-coverage" / "report.json"),
    )
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("fixtures", nargs="*")
    args = parser.parse_args()

    fixture_paths = (
        [Path(value).expanduser().resolve() for value in args.fixtures]
        if args.fixtures
        else [*DEFAULT_FIXTURES, *(path for path in OPTIONAL_FIXTURES if path.is_file())]
    )
    missing_paths = [str(path) for path in fixture_paths if not path.is_file()]
    if missing_paths:
        raise SystemExit("Missing independent fixtures: " + ", ".join(missing_paths))
    catalog_path = Path(args.catalog).expanduser().resolve()
    with TemporaryDirectory() as temporary_directory:
        audit_paths: list[Path] = []
        for fixture_path in fixture_paths:
            if fixture_path.name not in {V14_FIXTURE_NAME, V15_FIXTURE_NAME}:
                audit_paths.append(fixture_path)
                continue
            if fixture_path.name == V14_FIXTURE_NAME:
                normalized = _normalize_v14_fixture(
                    fixture_path,
                    catalog_path,
                    Path(temporary_directory) / V14_FIXTURE_NAME,
                )
            else:
                normalized = _normalize_v15_fixture(
                    fixture_path,
                    catalog_path,
                    Path(temporary_directory) / V15_FIXTURE_NAME,
                )
            if normalized is not None:
                audit_paths.append(normalized)
            elif args.fixtures:
                version = "V14" if fixture_path.name == V14_FIXTURE_NAME else "V15"
                raise SystemExit(
                    f"The {version} independent fixture requires a projected or materialized {version} catalog"
                )
        report = audit_independent_coverage(
            catalog_path=catalog_path,
            fixture_paths=audit_paths,
        )
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "navigation independent coverage "
        f"status={report['status']} fixtures={report['fixture_count']} "
        f"cases={report['case_count']} steps={report['step_count']} "
        f"intents={report['intent_covered']}/{report['intent_total']} "
        f"functions={report['function_covered']}/{report['function_total']} "
        f"errors={report['error_count']}"
    )
    print(f"report={output_path}")
    if args.gate and report["status"] != "pass":
        raise SystemExit("Independent coverage gate failed")


if __name__ == "__main__":
    main()
