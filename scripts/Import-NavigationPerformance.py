from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.navigation_performance import (  # noqa: E402
    NavigationPerformanceStore,
    plan_real_device_import,
)
from app.services.universal_navigation_graph import DEFAULT_DATABASE_PATH  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and import privacy-masked real-device navigation timing logs."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE_PATH))
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--summary-output", default="")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"Navigation performance log was not found: {input_path}")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Navigation performance log root must be an object")
    # The exact same immutable plan is used for check-only and for the real
    # transaction, preventing shallow preflight checks from disagreeing with
    # import-time validation.
    plan = plan_real_device_import(payload)

    if args.check_only:
        result: dict[str, object] = {
            "validated_sessions": len(plan.sessions),
            "measurement_source": plan.measurement_source,
            "verification_level": plan.verification_level,
            "privacy_check": "pass",
            "imported": False,
        }
    else:
        database_path = Path(args.database).expanduser().resolve()
        store = NavigationPerformanceStore(database_path)
        result = {
            **store.import_real_device_plan(plan),
            "database": str(database_path),
            "imported": True,
            "real_device_summary": store.summary(measurement_source="real_device"),
            "real_device_gold_summary": store.summary(measurement_source="real_device_gold"),
        }

    if args.summary_output:
        output_path = Path(args.summary_output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
