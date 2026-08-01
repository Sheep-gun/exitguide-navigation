from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_offline_replay import (  # noqa: E402
    assert_offline_replay_quality_gate,
    evaluate_offline_replay_fixture,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Replay privacy-safe semantic Android screens through the production "
            "ExitGuide navigation candidate/ranking/safety path."
        )
    )
    parser.add_argument(
        "--fixture",
        default=str(
            ROOT
            / "fixtures"
            / "navigation"
            / "offline"
            / "baemin-notification-settings.synthetic.v1.json"
        ),
    )
    parser.add_argument(
        "--catalog",
        default=str(ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"),
    )
    parser.add_argument(
        "--output",
        default=str(
            ROOT
            / ".artifacts"
            / "navigation-offline"
            / "baemin-notification-settings.report.json"
        ),
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Compatibility flag; the quality gate is enforced by default.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Write a report without failing the process when the quality gate fails.",
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = evaluate_offline_replay_fixture(
        fixture_path=Path(args.fixture).expanduser().resolve(),
        catalog_path=Path(args.catalog).expanduser().resolve(),
    )
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            separators=(",", ":") if args.compact else None,
        )
        + "\n",
        encoding="utf-8",
    )
    summary = report["summary"]
    print(
        "offline navigation replay "
        f"gate={report['quality_gate']['status']} "
        f"cases={summary['scenario_count']} "
        f"mutation_macro={summary['mutation_macro_success_rate']:.2%} "
        f"mutation_micro={summary['mutation_micro_decision_accuracy']:.2%} "
        f"unsafe={summary['unsafe_auto_click_count']} "
        f"wrong={summary['wrong_guidance_count']}"
    )
    print(f"report={output_path}")
    if not args.report_only:
        assert_offline_replay_quality_gate(report)


if __name__ == "__main__":
    main()
