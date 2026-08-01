from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.config import Settings  # noqa: E402
from app.services.navigation_db_proposer import propose_with_exaone  # noqa: E402
from app.services.navigation_function_catalog import NavigationFunctionCatalog  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate review-only K-EXAONE hypotheses for Navigation DB failures.")
    parser.add_argument("--report", default=str(ROOT / ".artifacts/navigation-db-gym/full-report.json"))
    parser.add_argument("--output", default=str(ROOT / ".artifacts/navigation-db-gym/exaone-proposals.json"))
    parser.add_argument("--max-failures", type=int, default=40)
    args = parser.parse_args()

    report_path = Path(args.report).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    catalog_path = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
    catalog = NavigationFunctionCatalog(output_path.parent / "proposal-function-index.sqlite", catalog_path)
    proposals = propose_with_exaone(
        report=report,
        catalog=catalog,
        settings=Settings(),
        max_failures=args.max_failures,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(proposals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"review-only K-EXAONE proposals={len(proposals['suggestions'])} output={output_path}")


if __name__ == "__main__":
    main()
