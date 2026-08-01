#!/usr/bin/env python3
"""Audit an append-only navigation coverage draft before implementation.

The draft is intentionally checked against the materialized catalog only.  This
tool never reads independent evaluation fixtures, answer keys, or failure
reports, so it is safe to use in the development feedback loop.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DRAFT = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V16.md"
DEFAULT_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DEFAULT_EQUIVALENCE = ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json"

SECTION_RE = re.compile(
    r"^##\s+(?P<number>\d+)\.\s+.+?\(`(?P<domain>[a-z0-9_]+)`\)\s*$",
    re.MULTILINE,
)
ROW_RE = re.compile(
    r"^\|\s*(?P<class>[SC])\s*\|\s*`(?P<function>[a-z0-9_.]+)`\s*\|"
    r"\s*(?P<name>.*?)\s*\|\s*(?P<goal>.*?)\s*\|\s*$",
    re.MULTILINE,
)
HUB_RE = re.compile(r"^Hub:\s*`(?P<hub>[a-z0-9_.]+)`", re.MULTILINE)
URL_RE = re.compile(r"\[[^\]]+\]\((https://[^)\s]+)\)")
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
LATIN_RE = re.compile(r"[A-Za-z]")


class Finding(NamedTuple):
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def _normalized_english(value: str) -> str:
    english = value.rsplit(" / ", 1)[-1]
    return re.sub(r"[^a-z0-9]+", " ", english.casefold()).strip()


def _is_bilingual(value: str) -> bool:
    return " / " in value and bool(HANGUL_RE.search(value)) and bool(LATIN_RE.search(value))


def _load_catalog(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog root must be an object")
    return payload


def _numeric_table_row(text: str, label: str) -> tuple[int, int, int] | None:
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0].replace("**", "") != label:
            continue
        values: list[int] = []
        for cell in cells[1:4]:
            normalized = re.sub(r"[^0-9]", "", cell)
            if not normalized:
                return None
            values.append(int(normalized))
        return tuple(values)  # type: ignore[return-value]
    return None


def audit_draft(
    draft_path: Path,
    catalog_path: Path,
    *,
    equivalence_path: Path = DEFAULT_EQUIVALENCE,
    expected_domains: int = 12,
    expected_terminals_per_domain: int = 20,
    expected_sensitive_per_domain: int = 7,
    expected_consequential_per_domain: int = 13,
    minimum_sources_per_domain: int = 5,
) -> dict[str, Any]:
    raw = draft_path.read_bytes()
    text = raw.decode("utf-8")
    catalog = _load_catalog(catalog_path)
    equivalence = json.loads(equivalence_path.read_text(encoding="utf-8"))
    equivalence_counts = dict(equivalence.get("audit_counts", {}))
    findings: list[Finding] = []

    matches = list(SECTION_RE.finditer(text))
    sections: list[dict[str, Any]] = []
    all_function_ids: list[str] = []
    all_english_names: list[str] = []
    all_english_goals: list[str] = []
    all_urls: list[str] = []

    for index, match in enumerate(matches):
        number = int(match.group("number"))
        domain = match.group("domain")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        rows = [row.groupdict() for row in ROW_RE.finditer(body)]
        class_counts = Counter(row["class"] for row in rows)
        hub_match = HUB_RE.search(body)
        hub = hub_match.group("hub") if hub_match else None
        sources_marker = "unverified candidates" in body and "미검증 후보" in body
        urls = URL_RE.findall(body)

        if number != index + 1:
            findings.append(Finding("section_order", f"{domain}: section number is {number}, expected {index + 1}"))
        if hub != f"{domain}.hub":
            findings.append(Finding("hub_id", f"{domain}: expected hub {domain}.hub, got {hub!r}"))
        if len(rows) != expected_terminals_per_domain:
            findings.append(
                Finding(
                    "terminal_count",
                    f"{domain}: expected {expected_terminals_per_domain} terminals, got {len(rows)}",
                )
            )
        if class_counts != Counter(
            {"S": expected_sensitive_per_domain, "C": expected_consequential_per_domain}
        ):
            findings.append(Finding("class_count", f"{domain}: S/C counts are {dict(class_counts)}"))
        if "Roles/assets/states:" not in body:
            findings.append(Finding("semantic_boundary", f"{domain}: missing roles/assets/states contract"))
        if "Boundary and collision guard:" not in body:
            findings.append(Finding("collision_boundary", f"{domain}: missing collision boundary"))
        if not sources_marker:
            findings.append(Finding("source_status", f"{domain}: source candidates are not explicitly unverified"))
        if len(urls) < minimum_sources_per_domain:
            findings.append(
                Finding(
                    "source_count",
                    f"{domain}: expected at least {minimum_sources_per_domain} HTTPS source candidates, got {len(urls)}",
                )
            )

        for row in rows:
            function_id = row["function"]
            if not function_id.startswith(f"{domain}.") or function_id == f"{domain}.hub":
                findings.append(Finding("function_scope", f"{domain}: invalid terminal ID {function_id}"))
            if not _is_bilingual(row["name"]):
                findings.append(Finding("bilingual_name", f"{function_id}: name is not Korean/English bilingual"))
            if not _is_bilingual(row["goal"]):
                findings.append(Finding("bilingual_goal", f"{function_id}: goal is not Korean/English bilingual"))
            all_function_ids.append(function_id)
            all_english_names.append(_normalized_english(row["name"]))
            all_english_goals.append(_normalized_english(row["goal"]))
        all_urls.extend(urls)
        sections.append(
            {
                "number": number,
                "domain": domain,
                "hub": hub,
                "terminal_count": len(rows),
                "sensitive_count": class_counts["S"],
                "consequential_count": class_counts["C"],
                "source_candidate_count": len(urls),
            }
        )

    domains = [item["domain"] for item in sections]
    if len(sections) != expected_domains:
        findings.append(Finding("domain_count", f"expected {expected_domains} domains, got {len(sections)}"))

    def record_duplicates(values: list[str], code: str, label: str) -> None:
        duplicates = sorted(value for value, count in Counter(values).items() if value and count > 1)
        for value in duplicates:
            findings.append(Finding(code, f"duplicate {label}: {value}"))

    record_duplicates(domains, "duplicate_domain", "domain")
    record_duplicates(all_function_ids, "duplicate_function", "function ID")
    record_duplicates(all_english_names, "duplicate_name", "normalized English name")
    record_duplicates(all_english_goals, "duplicate_goal", "normalized English goal")

    existing_functions = {
        str(item.get("function_id"))
        for item in catalog.get("functions", [])
        if isinstance(item, dict) and item.get("function_id")
    }
    existing_domains = {
        str(item.get("domain"))
        for item in catalog.get("functions", [])
        if isinstance(item, dict) and item.get("domain")
    }
    for domain in sorted(set(domains) & existing_domains):
        findings.append(Finding("existing_domain_collision", f"domain already exists in catalog: {domain}"))
    for function_id in sorted(set(all_function_ids) & existing_functions):
        findings.append(Finding("existing_function_collision", f"function already exists in catalog: {function_id}"))
    for domain in domains:
        if f"{domain}.hub" in existing_functions:
            findings.append(Finding("existing_hub_collision", f"hub already exists in catalog: {domain}.hub"))

    canonical_domain_count = len(existing_domains)
    canonical_function_count = len(existing_functions)
    canonical_terminal_count = sum(
        bool(item.get("terminal"))
        for item in catalog.get("functions", [])
        if isinstance(item, dict)
    )
    canonical_intent_count = sum(isinstance(item, dict) for item in catalog.get("intents", []))
    new_function_count = expected_domains * (expected_terminals_per_domain + 1)
    new_terminal_count = expected_domains * expected_terminals_per_domain
    projection_expectations = {
        "Domains": (canonical_domain_count, expected_domains, canonical_domain_count + expected_domains),
        "Physical functions": (
            canonical_function_count,
            new_function_count,
            canonical_function_count + new_function_count,
        ),
        "Physical terminal functions": (
            canonical_terminal_count,
            new_terminal_count,
            canonical_terminal_count + new_terminal_count,
        ),
        "Physical intents": (
            canonical_intent_count,
            new_terminal_count,
            canonical_intent_count + new_terminal_count,
        ),
        "Unique physical default-terminal IDs": (
            int(equivalence_counts.get("physical_default_terminal_count", -1)),
            new_terminal_count,
            int(equivalence_counts.get("physical_default_terminal_count", -1)) + new_terminal_count,
        ),
        "Logical functions": (
            int(equivalence_counts.get("logical_function_count", -1)),
            new_function_count,
            int(equivalence_counts.get("logical_function_count", -1)) + new_function_count,
        ),
        "Logical intents": (
            int(equivalence_counts.get("logical_intent_count", -1)),
            new_terminal_count,
            int(equivalence_counts.get("logical_intent_count", -1)) + new_terminal_count,
        ),
        "Unique logical default-terminal destinations": (
            int(equivalence_counts.get("logical_default_terminal_count", -1)),
            new_terminal_count,
            int(equivalence_counts.get("logical_default_terminal_count", -1)) + new_terminal_count,
        ),
    }
    if int(equivalence_counts.get("physical_function_count", -1)) != canonical_function_count:
        findings.append(Finding("equivalence_baseline", "equivalence physical function count differs from catalog"))
    if int(equivalence_counts.get("physical_intent_count", -1)) != canonical_intent_count:
        findings.append(Finding("equivalence_baseline", "equivalence physical intent count differs from catalog"))
    projection_rows: dict[str, tuple[int, int, int] | None] = {}
    for label, expected in projection_expectations.items():
        actual = _numeric_table_row(text, label)
        projection_rows[label] = actual
        if actual != expected:
            findings.append(Finding("projection_count", f"{label}: expected {expected}, got {actual}"))

    safety_contract_terms = (
        "at least two positive discriminators",
        "never_auto",
        "before_action",
        "user_owned_final_press=true",
        "causes abstention or a stop at the hub",
    )
    for term in safety_contract_terms:
        if term not in text:
            findings.append(Finding("safety_contract", f"draft is missing safety invariant: {term}"))

    expected_total = expected_domains * expected_terminals_per_domain
    if len(all_function_ids) != expected_total:
        findings.append(Finding("aggregate_terminal_count", f"expected {expected_total} terminals, got {len(all_function_ids)}"))

    return {
        "schema_version": "1.0.0",
        "draft": draft_path.relative_to(ROOT).as_posix() if draft_path.is_relative_to(ROOT) else str(draft_path),
        "draft_sha256": hashlib.sha256(raw).hexdigest(),
        "catalog": catalog_path.relative_to(ROOT).as_posix() if catalog_path.is_relative_to(ROOT) else str(catalog_path),
        "catalog_version": catalog.get("catalog_version"),
        "catalog_function_count": len(existing_functions),
        "domain_count": len(sections),
        "terminal_count": len(all_function_ids),
        "sensitive_count": sum(item["sensitive_count"] for item in sections),
        "consequential_count": sum(item["consequential_count"] for item in sections),
        "source_candidate_count": len(all_urls),
        "unique_source_candidate_count": len(set(all_urls)),
        "equivalence_version": equivalence.get("equivalence_version"),
        "projection": {
            label: list(value) if value is not None else None
            for label, value in projection_rows.items()
        },
        "sections": sections,
        "finding_count": len(findings),
        "findings": [finding.as_dict() for finding in findings],
        "passed": not findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--equivalence", type=Path, default=DEFAULT_EQUIVALENCE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()

    report = audit_draft(
        args.draft.resolve(),
        args.catalog.resolve(),
        equivalence_path=args.equivalence.resolve(),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 1 if args.gate and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
