from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _load_auditor():
    path = ROOT / "scripts" / "Audit-NavigationCoverageDraft.py"
    spec = importlib.util.spec_from_file_location("navigation_coverage_draft_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    auditor = _load_auditor()
    draft = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V16.md"
    catalog = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
    report = auditor.audit_draft(draft, catalog)

    assert report["passed"], report["findings"]
    assert report["catalog_version"] == "15.0.0"
    assert report["catalog_function_count"] == 2866
    assert report["equivalence_version"] == "1.1.0"
    assert report["domain_count"] == 12
    assert report["terminal_count"] == 240
    assert report["sensitive_count"] == 84
    assert report["consequential_count"] == 156
    assert report["source_candidate_count"] == 81
    assert report["unique_source_candidate_count"] == 81
    assert report["projection"]["Domains"] == [179, 12, 191]
    assert report["projection"]["Physical functions"] == [2866, 252, 3118]
    assert report["projection"]["Physical intents"] == [2660, 240, 2900]
    assert report["projection"]["Logical functions"] == [2856, 252, 3108]

    # The gate must detect collisions against the canonical catalog, not only
    # duplicate IDs inside the draft itself.
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    first_function = payload["functions"][0]
    existing_domain = str(first_function["domain"])
    existing_function = str(first_function["function_id"])
    synthetic = (
        f"## 1. Collision (`{existing_domain}`)\n\n"
        f"Hub: `{existing_domain}.hub` — 충돌 / Collision\n\n"
        "| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |\n"
        "|:---:|---|---|---|\n"
        f"| S | `{existing_function}` | 기존 기능 / Existing function | 기존 목적을 보여 줘 / Show the existing goal |\n\n"
        "Roles/assets/states: role; asset; state.\n\n"
        "Boundary and collision guard: explicit.\n\n"
        "Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**:\n\n"
        "1. [a](https://example.com/a)\n2. [b](https://example.com/b)\n"
        "3. [c](https://example.com/c)\n4. [d](https://example.com/d)\n"
        "5. [e](https://example.com/e)\n"
    )
    with tempfile.TemporaryDirectory() as temporary_directory:
        synthetic_path = Path(temporary_directory) / "draft.md"
        synthetic_path.write_text(synthetic, encoding="utf-8")
        failed = auditor.audit_draft(
            synthetic_path,
            catalog,
            expected_domains=1,
            expected_terminals_per_domain=1,
            expected_sensitive_per_domain=1,
            expected_consequential_per_domain=0,
        )
    codes = {item["code"] for item in failed["findings"]}
    assert not failed["passed"]
    assert "existing_domain_collision" in codes
    assert "existing_function_collision" in codes

    print(
        "navigation coverage draft audit checks ok | "
        f"domains={report['domain_count']} terminals={report['terminal_count']} "
        f"sources={report['source_candidate_count']} sha256={report['draft_sha256']}"
    )


if __name__ == "__main__":
    main()
