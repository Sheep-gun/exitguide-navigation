from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT / "fixtures" / "navigation" / "db-gym" / "real-device-gold.v1.json"
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)01[016789][ -]?\d{3,4}[ -]?\d{4}(?!\d)")
CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){15,16}(?!\d)")
FORBIDDEN_KEYS = {"email", "phone", "phone_number", "account_id", "user_id", "address", "card_number", "message"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and import privacy-masked real-device Navigation gold cases.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--target", default=str(DEFAULT_TARGET))
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    target_path = Path(args.target).expanduser().resolve()
    incoming = json.loads(input_path.read_text(encoding="utf-8"))
    cases = incoming.get("cases", incoming if isinstance(incoming, list) else [incoming])
    if not isinstance(cases, list) or not cases:
        raise SystemExit("No gold cases were supplied.")
    for case in cases:
        _validate_case(case)
        _assert_privacy_masked(case)

    if args.check_only:
        print(f"navigation gold validation ok: {len(cases)} case(s); no files changed")
        return

    target = json.loads(target_path.read_text(encoding="utf-8"))
    existing = {str(item["case_id"]): item for item in target.get("cases", [])}
    duplicates = sorted(str(item["case_id"]) for item in cases if str(item["case_id"]) in existing)
    if duplicates:
        raise SystemExit("Duplicate case_id(s): " + ", ".join(duplicates))
    target["cases"] = sorted([*existing.values(), *cases], key=lambda item: str(item["case_id"]))
    target["collection_status"] = "contains_device_validated_cases"
    target_path.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"navigation gold imported: {len(cases)} case(s) -> {target_path}")


def _validate_case(case: dict[str, Any]) -> None:
    required = {
        "case_id",
        "app_package",
        "app_version",
        "intent_id",
        "goal_text",
        "locale",
        "device_model",
        "android_version",
        "verified_by",
        "verified_at",
        "steps",
    }
    missing = sorted(required - set(case))
    if missing:
        raise SystemExit(f"{case.get('case_id', '<unknown>')}: missing fields: {', '.join(missing)}")
    if not str(case["case_id"]).startswith("gold-"):
        raise SystemExit(f"{case['case_id']}: case_id must start with 'gold-'")
    if not str(case["app_package"]).count(".") >= 1:
        raise SystemExit(f"{case['case_id']}: invalid app_package")
    steps = case["steps"]
    if not isinstance(steps, list) or not steps:
        raise SystemExit(f"{case['case_id']}: at least one step is required")
    step_required = {"screen_title", "stage", "elements", "expected_function", "expected_action", "source"}
    for index, step in enumerate(steps):
        missing_step = sorted(step_required - set(step))
        if missing_step:
            raise SystemExit(f"{case['case_id']} step {index + 1}: missing fields: {', '.join(missing_step)}")
        if step["expected_action"] not in {"click", "stop", "no_click"}:
            raise SystemExit(f"{case['case_id']} step {index + 1}: invalid expected_action")
        if not isinstance(step["elements"], list) or not step["elements"]:
            raise SystemExit(f"{case['case_id']} step {index + 1}: sanitized elements are required")


def _assert_privacy_masked(value: Any, path: str = "case") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise SystemExit(f"Privacy-sensitive field must be removed or renamed after masking: {path}.{key}")
            _assert_privacy_masked(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_privacy_masked(child, f"{path}[{index}]")
        return
    if isinstance(value, str) and (EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value) or CARD_PATTERN.search(value)):
        raise SystemExit(f"Possible unmasked personal data at {path}")


if __name__ == "__main__":
    main()
