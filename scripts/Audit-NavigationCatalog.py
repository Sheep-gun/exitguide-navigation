from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.navigation_catalog_quality import (  # noqa: E402
    audit_navigation_catalog,
    render_catalog_quality_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit ExitGuide navigation catalog coverage and safety.")
    parser.add_argument("--catalog", default=str(ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"))
    parser.add_argument("--policy", default=str(ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"))
    parser.add_argument("--output-dir", default=str(ROOT / ".artifacts" / "navigation-catalog-quality"))
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = audit_navigation_catalog(Path(args.catalog).resolve(), Path(args.policy).resolve())
    json_path = output_dir / "catalog-quality-report.json"
    markdown_path = output_dir / "catalog-quality-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_catalog_quality_markdown(report), encoding="utf-8")
    totals = report["totals"]
    print(
        f"navigation catalog quality status={report['status']} score={report['quality_score']:.1f} "
        f"functions={totals['function_count']} intents={totals['intent_count']} "
        f"aliases={totals['alias_count']} contexts={totals['context_count']}"
    )
    print(f"report={json_path}")
    if args.gate and report["status"] != "pass":
        errors = [item for item in report["findings"] if item["severity"] == "error"]
        raise SystemExit("Catalog quality gate failed: " + "; ".join(item["message"] for item in errors[:10]))


if __name__ == "__main__":
    main()
