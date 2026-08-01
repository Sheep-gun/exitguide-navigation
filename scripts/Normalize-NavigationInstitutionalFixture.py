from __future__ import annotations

import argparse
import json
from pathlib import Path


def normalize_fixture(
    *,
    source: dict[str, object],
    catalog: dict[str, object],
) -> dict[str, object]:
    """Convert the sealed V14 fixture to the stateful DB-Gym schema.

    The source fixture intentionally has a separate authorship schema.  This
    adapter changes only its envelope; goal text and expected route IDs remain
    untouched.  Python performs the UTF-8 parsing because Windows PowerShell
    5 can corrupt a large no-BOM multilingual catalog before ConvertFrom-Json.
    """

    terminal_intents = {
        str(item.get("terminal_function", "")): str(item.get("intent_id", ""))
        for item in catalog.get("intents", [])
        if isinstance(item, dict)
    }
    cases = source.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("institutional fixture cases must be a list")

    required_routes = {
        str(case.get("expected", {}).get("route_id", ""))
        for case in cases
        if isinstance(case, dict)
        and not str(case.get("expected", {}).get("route_id", "")).endswith(".hub")
    }
    missing = sorted(required_routes.difference(terminal_intents))
    if missing:
        raise ValueError(
            "institutional fixture references unknown terminal routes: "
            + ", ".join(missing[:8])
        )

    normalized_cases: list[dict[str, object]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("institutional fixture case must be an object")
        expected = case.get("expected", {})
        if not isinstance(expected, dict):
            raise ValueError("institutional fixture expected must be an object")
        route_id = str(expected.get("route_id", ""))
        hub_case = route_id.endswith(".hub")
        normalized_cases.append(
            {
                "case_id": str(case.get("case_id", "")),
                "intent_id": "__abstain__" if hub_case else terminal_intents[route_id],
                "goal_text": str(case.get("goal", "")),
                "locale": "ko-KR" if str(case.get("locale", "")) == "ko" else "en-US",
                "user_state": "authorized_role_scoped",
                "tags": [
                    str(case.get("slice", "")),
                    str(case.get("class", "")),
                    "independent_v14",
                ],
                "source_kind": "fixed_independent",
                "tuning_allowed": False,
                "steps": [
                    {
                        "step_id": "review-boundary",
                        "screen_title": str(
                            (case.get("ui", {}) or {}).get("surface", "")
                        ),
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

    return {
        "split": "independent_institutional_systems_v14",
        "frozen": True,
        "catalog_derived": False,
        "tuning_allowed": False,
        "cases": normalized_cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize the sealed V14 institutional fixture for stateful evaluation."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    catalog_path = Path(args.catalog).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    payload = normalize_fixture(
        source=json.loads(source_path.read_text(encoding="utf-8")),
        catalog=json.loads(catalog_path.read_text(encoding="utf-8")),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "institutional fixture normalized "
        f"cases={len(payload['cases'])} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
