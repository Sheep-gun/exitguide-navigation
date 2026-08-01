#!/usr/bin/env python3
"""Audit the source-constrained V16 partial-terminal refinement.

The audit is deliberately development-data-only.  It reads the V16 proposal,
source verification/closure documents, the canonical catalog, and the explicit
function-equivalence projection.  Independent fixtures, answers, failures,
evaluation outputs, and reports are outside this script's input surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, NamedTuple
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROPOSAL = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V16.md"
DEFAULT_REFINEMENT = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V16_REFINEMENT.md"
DEFAULT_SOURCE_DOCUMENTS = (
    ROOT / "docs" / "NAVIGATION_SOURCES_V16_PART1.md",
    ROOT / "docs" / "NAVIGATION_SOURCES_V16_PART2.md",
)
DEFAULT_CLOSURE_DOCUMENTS = (
    ROOT / "docs" / "NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART1.md",
    ROOT / "docs" / "NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2A.md",
    ROOT / "docs" / "NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2B.md",
)
DEFAULT_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DEFAULT_EQUIVALENCE = ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json"

EXPECTED_DATE = "2026-07-30"
EXPECTED_DOMAIN_COUNT = 12
EXPECTED_TERMINALS_PER_DOMAIN = 20
EXPECTED_SENSITIVE_PER_DOMAIN = 7
EXPECTED_CONSEQUENTIAL_PER_DOMAIN = 13
EXPECTED_MAPPING_COUNT = 16
EXPECTED_REPLACEMENT_SENSITIVE = 1
EXPECTED_REPLACEMENT_CONSEQUENTIAL = 15
EXPECTED_REFINEMENT_SOURCE_COUNT = 21

PROPOSAL_SECTION_RE = re.compile(
    r"^##\s+(?P<number>\d+)\.\s+.+?\(`(?P<domain>[a-z0-9_]+)`\)\s*$",
    re.MULTILINE,
)
PROPOSAL_ROW_RE = re.compile(
    r"^\|\s*(?P<class>[SC])\s*\|\s*`(?P<function>[a-z0-9_.]+)`\s*\|"
    r"\s*(?P<name>.*?)\s*\|\s*(?P<goal>.*?)\s*\|\s*$",
    re.MULTILINE,
)
HUB_RE = re.compile(r"^Hub:\s*`(?P<hub>[a-z0-9_.]+)`", re.MULTILINE)
MAPPING_ROW_RE = re.compile(
    r"^\|\s*(?P<number>\d+)\s*\|\s*(?P<class>[SC])\s*\|\s*(?P<decision>[AB])\s*\|"
    r"\s*`(?P<old>[a-z0-9_.]+)`\s*\|\s*`(?P<new>[a-z0-9_.]+)`\s*\|\s*$",
    re.MULTILINE,
)
SPEC_HEADING_RE = re.compile(
    r"^###\s+3\.(?P<number>\d+)\s+.+?\s+\((?P<class>[SC])\)\s*$",
    re.MULTILINE,
)
MARKDOWN_URL_RE = re.compile(r"\[[^\]]+\]\((https://[^)\s]+)\)")
DATE_RE = re.compile(
    r"(?:Audit date|Verification date|검증일)\s*:\s*(?:\*\*)?(?P<date>\d{4}-\d{2}-\d{2})"
)
HEADING_RE = re.compile(r"^(?P<marks>#{2,3})\s+.+$", re.MULTILINE)
CODE_ID_RE = re.compile(r"`(?P<id>[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)?)`")
HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
LATIN_RE = re.compile(r"[A-Za-z]")


class Finding(NamedTuple):
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def _display_path(path: Path) -> str:
    path = path.resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_identity(value: str) -> str:
    """NFKC/case-fold and remove whitespace, punctuation, and symbols."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if unicodedata.category(character)[0] in {"L", "N"})


def _split_bilingual(value: str) -> tuple[str, str] | None:
    if value.count(" / ") != 1:
        return None
    korean, english = (part.strip() for part in value.split(" / ", 1))
    if not korean or not english:
        return None
    if not HANGUL_RE.search(korean) or not LATIN_RE.search(english):
        return None
    return korean, english


def _normalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    scheme = parts.scheme.casefold()
    hostname = (parts.hostname or "").casefold()
    port = parts.port
    if port and not (scheme == "https" and port == 443):
        hostname = f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    # Closure packs intentionally compare evidence resources without tracking
    # fragments or transient query parameters.
    return urlunsplit((scheme, hostname, path, "", ""))


def _field_values(body: str, label_pattern: str) -> list[str]:
    pattern = re.compile(
        rf"^-\s+\*\*(?:{label_pattern}):\*\*\s*(?P<value>.+?)\s*$",
        re.MULTILINE,
    )
    return [match.group("value").strip() for match in pattern.finditer(body)]


def _parse_proposal(text: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    matches = list(PROPOSAL_SECTION_RE.finditer(text))
    sections: list[dict[str, Any]] = []
    rows: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        domain = match.group("domain")
        section_rows = [row.groupdict() for row in PROPOSAL_ROW_RE.finditer(body)]
        hub_match = HUB_RE.search(body)
        sections.append(
            {
                "number": int(match.group("number")),
                "domain": domain,
                "hub": hub_match.group("hub") if hub_match else None,
                "terminal_count": len(section_rows),
                "class_counts": dict(Counter(row["class"] for row in section_rows)),
            }
        )
        for row in section_rows:
            row["domain"] = domain
            rows.append(row)
    return sections, rows


def _parse_mapping(text: str) -> list[dict[str, Any]]:
    return [
        {
            "number": int(match.group("number")),
            "class": match.group("class"),
            "decision": match.group("decision"),
            "old": match.group("old"),
            "new": match.group("new"),
        }
        for match in MAPPING_ROW_RE.finditer(text)
    ]


def _parse_specs(text: str) -> list[dict[str, Any]]:
    matches = list(SPEC_HEADING_RE.finditer(text))
    specs: list[dict[str, Any]] = []
    labels = {
        "mapping": r"Exact mapping",
        "name": r"이름",
        "goal": r"목표",
        "role_asset": r"Role\s*/\s*asset",
        "state_transition": r"State\s*/\s*transition",
        "jurisdiction": r"Jurisdiction guard",
        "sources": r"Accepted official sources?",
        "non_equivalence": r"Nearest existing-domain non-equivalence",
    }
    mapping_value_re = re.compile(
        r"^`(?P<old>[a-z0-9_.]+)`\s*→\s*`(?P<new>[a-z0-9_.]+)`$"
    )
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        fields = {key: _field_values(body, pattern) for key, pattern in labels.items()}
        mapping_match = mapping_value_re.match(fields["mapping"][0]) if len(fields["mapping"]) == 1 else None
        sources = MARKDOWN_URL_RE.findall(fields["sources"][0]) if len(fields["sources"]) == 1 else []
        specs.append(
            {
                "number": int(match.group("number")),
                "class": match.group("class"),
                "old": mapping_match.group("old") if mapping_match else None,
                "new": mapping_match.group("new") if mapping_match else None,
                "name": fields["name"][0] if len(fields["name"]) == 1 else None,
                "goal": fields["goal"][0] if len(fields["goal"]) == 1 else None,
                "role_asset": fields["role_asset"][0] if len(fields["role_asset"]) == 1 else None,
                "state_transition": fields["state_transition"][0] if len(fields["state_transition"]) == 1 else None,
                "jurisdiction": fields["jurisdiction"][0] if len(fields["jurisdiction"]) == 1 else None,
                "non_equivalence": fields["non_equivalence"][0]
                if len(fields["non_equivalence"]) == 1
                else None,
                "source_urls": sources,
                "field_counts": {key: len(values) for key, values in fields.items()},
            }
        )
    return specs


def _parse_partial_ids(text: str) -> list[str]:
    """Parse full IDs whose closure section is explicitly partially resolved."""

    headings = list(HEADING_RE.finditer(text))
    current_domain: str | None = None
    partial_ids: list[str] = []
    for index, heading in enumerate(headings):
        line = heading.group(0)
        codes = [match.group("id") for match in CODE_ID_RE.finditer(line)]
        if heading.group("marks") == "##" and codes:
            domain_candidate = codes[-1]
            if "." not in domain_candidate:
                current_domain = domain_candidate
        if not codes:
            continue
        code = codes[-1]
        if "." in code:
            function_id = code
        elif heading.group("marks") == "###" and current_domain:
            function_id = f"{current_domain}.{code}"
        else:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.start() : end]
        if re.search(r"`partially_resolved`|\bpartially_resolved\b", section):
            partial_ids.append(function_id)
    return partial_ids


def _duplicate_values(values: Iterable[str]) -> list[str]:
    counts = Counter(value for value in values if value)
    return sorted(value for value, count in counts.items() if count > 1)


@lru_cache(maxsize=4)
def _catalog_projection(path_string: str, modified_ns: int, size: int) -> dict[str, Any]:
    del modified_ns, size
    path = Path(path_string)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog root must be an object")
    function_ids: set[str] = set()
    normalized_names: set[str] = set()
    domain_ids: set[str] = set()
    terminal_count = 0
    for item in payload.get("functions", []):
        if not isinstance(item, dict):
            continue
        function_id = item.get("function_id")
        if isinstance(function_id, str) and function_id:
            function_ids.add(function_id)
        domain = item.get("domain")
        if isinstance(domain, str) and domain:
            domain_ids.add(domain)
        terminal_count += bool(item.get("terminal"))
        for key in ("name_ko", "name_en"):
            value = item.get(key)
            if isinstance(value, str) and value:
                normalized_names.add(_normalize_identity(value))
    normalized_patterns: set[str] = set()
    intent_count = 0
    for item in payload.get("intents", []):
        if not isinstance(item, dict):
            continue
        intent_count += 1
        for pattern in item.get("patterns", []):
            if isinstance(pattern, str) and pattern:
                normalized_patterns.add(_normalize_identity(pattern))
    return {
        "catalog_version": payload.get("catalog_version"),
        "function_ids": function_ids,
        "normalized_names": normalized_names,
        "normalized_patterns": normalized_patterns,
        "domain_ids": domain_ids,
        "function_count": len(function_ids),
        "terminal_count": terminal_count,
        "intent_count": intent_count,
    }


def _load_catalog_projection(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return _catalog_projection(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _equivalence_projection(path_string: str, modified_ns: int, size: int) -> dict[str, Any]:
    del modified_ns, size
    payload = json.loads(Path(path_string).read_text(encoding="utf-8"))
    ids: set[str] = set()
    classes = payload.get("classes", []) if isinstance(payload, dict) else []
    for item in classes:
        if not isinstance(item, dict):
            continue
        canonical = item.get("canonical_function_id")
        if isinstance(canonical, str) and canonical:
            ids.add(canonical)
        for alias in item.get("alias_function_ids", []):
            if isinstance(alias, str) and alias:
                ids.add(alias)
    return {
        "equivalence_version": payload.get("equivalence_version"),
        "member_ids": ids,
        "class_count": len(classes),
        "audit_counts": dict(payload.get("audit_counts", {})),
    }


def _load_equivalence_projection(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return _equivalence_projection(str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def audit_refinement(
    proposal_path: Path = DEFAULT_PROPOSAL,
    refinement_path: Path = DEFAULT_REFINEMENT,
    *,
    source_documents: Iterable[Path] = DEFAULT_SOURCE_DOCUMENTS,
    closure_documents: Iterable[Path] = DEFAULT_CLOSURE_DOCUMENTS,
    catalog_path: Path = DEFAULT_CATALOG,
    equivalence_path: Path = DEFAULT_EQUIVALENCE,
    expected_date: str = EXPECTED_DATE,
) -> dict[str, Any]:
    proposal_path = proposal_path.resolve()
    refinement_path = refinement_path.resolve()
    source_paths = tuple(path.resolve() for path in source_documents)
    closure_paths = tuple(path.resolve() for path in closure_documents)
    catalog_path = catalog_path.resolve()
    equivalence_path = equivalence_path.resolve()

    findings: list[Finding] = []
    proposal_text = proposal_path.read_text(encoding="utf-8")
    refinement_text = refinement_path.read_text(encoding="utf-8")
    source_texts = {path: path.read_text(encoding="utf-8") for path in source_paths}
    closure_texts = {path: path.read_text(encoding="utf-8") for path in closure_paths}
    catalog = _load_catalog_projection(catalog_path)
    equivalence = _load_equivalence_projection(equivalence_path)

    dated_documents = {
        proposal_path: proposal_text,
        refinement_path: refinement_text,
        **source_texts,
        **closure_texts,
    }
    declared_dates: dict[str, str | None] = {}
    for path, text in dated_documents.items():
        match = DATE_RE.search("\n".join(text.splitlines()[:20]))
        declared = match.group("date") if match else None
        declared_dates[_display_path(path)] = declared
        if declared != expected_date:
            findings.append(
                Finding("verification_date", f"{_display_path(path)}: expected {expected_date}, got {declared!r}")
            )

    proposal_sections, proposal_rows = _parse_proposal(proposal_text)
    proposal_by_id = {row["function"]: row for row in proposal_rows}
    proposal_domains = [section["domain"] for section in proposal_sections]
    if len(proposal_sections) != EXPECTED_DOMAIN_COUNT:
        findings.append(
            Finding("proposal_domain_count", f"expected {EXPECTED_DOMAIN_COUNT}, got {len(proposal_sections)}")
        )
    if len(proposal_rows) != EXPECTED_DOMAIN_COUNT * EXPECTED_TERMINALS_PER_DOMAIN:
        findings.append(Finding("proposal_terminal_count", f"expected 240, got {len(proposal_rows)}"))
    for expected_number, section in enumerate(proposal_sections, 1):
        domain = section["domain"]
        if section["number"] != expected_number:
            findings.append(
                Finding("proposal_section_order", f"{domain}: expected {expected_number}, got {section['number']}")
            )
        if section["hub"] != f"{domain}.hub":
            findings.append(
                Finding("proposal_hub", f"{domain}: expected {domain}.hub, got {section['hub']!r}")
            )
        if section["terminal_count"] != EXPECTED_TERMINALS_PER_DOMAIN:
            findings.append(
                Finding(
                    "proposal_domain_terminal_count",
                    f"{domain}: expected {EXPECTED_TERMINALS_PER_DOMAIN}, got {section['terminal_count']}",
                )
            )
        expected_classes = {"S": EXPECTED_SENSITIVE_PER_DOMAIN, "C": EXPECTED_CONSEQUENTIAL_PER_DOMAIN}
        if section["class_counts"] != expected_classes:
            findings.append(
                Finding("proposal_domain_class_count", f"{domain}: expected {expected_classes}, got {section['class_counts']}")
            )
    for value in _duplicate_values(proposal_domains):
        findings.append(Finding("proposal_duplicate_domain", f"duplicate proposal domain: {value}"))
    for value in _duplicate_values(row["function"] for row in proposal_rows):
        findings.append(Finding("proposal_duplicate_id", f"duplicate proposal terminal: {value}"))

    mappings = _parse_mapping(refinement_text)
    specs = _parse_specs(refinement_text)
    if len(mappings) != EXPECTED_MAPPING_COUNT:
        findings.append(Finding("mapping_count", f"expected {EXPECTED_MAPPING_COUNT}, got {len(mappings)}"))
    if len(specs) != EXPECTED_MAPPING_COUNT:
        findings.append(Finding("spec_count", f"expected {EXPECTED_MAPPING_COUNT}, got {len(specs)}"))
    mapping_numbers = [item["number"] for item in mappings]
    spec_numbers = [item["number"] for item in specs]
    if mapping_numbers != list(range(1, EXPECTED_MAPPING_COUNT + 1)):
        findings.append(Finding("mapping_order", f"expected mapping order 1..16, got {mapping_numbers}"))
    if spec_numbers != list(range(1, EXPECTED_MAPPING_COUNT + 1)):
        findings.append(Finding("spec_order", f"expected spec order 1..16, got {spec_numbers}"))

    old_ids = [item["old"] for item in mappings]
    new_ids = [item["new"] for item in mappings]
    for value in _duplicate_values(old_ids):
        findings.append(Finding("duplicate_old_id", f"old terminal is mapped more than once: {value}"))
    for value in _duplicate_values(new_ids):
        findings.append(Finding("duplicate_new_id", f"replacement terminal is used more than once: {value}"))

    partial_ids: list[str] = []
    closure_partial_by_document: dict[str, list[str]] = {}
    for path, text in closure_texts.items():
        parsed = _parse_partial_ids(text)
        closure_partial_by_document[_display_path(path)] = parsed
        partial_ids.extend(parsed)
    for value in _duplicate_values(partial_ids):
        findings.append(Finding("duplicate_closure_partial", f"partially_resolved terminal repeated: {value}"))
    if len(partial_ids) != EXPECTED_MAPPING_COUNT:
        findings.append(
            Finding("closure_partial_count", f"expected {EXPECTED_MAPPING_COUNT} partially_resolved IDs, got {len(partial_ids)}")
        )
    if set(partial_ids) != set(old_ids) or len(partial_ids) != len(old_ids):
        missing = sorted(set(partial_ids) - set(old_ids))
        extra = sorted(set(old_ids) - set(partial_ids))
        findings.append(
            Finding(
                "closure_mapping_set",
                f"closure/refinement old-ID sets differ; missing_from_mapping={missing}, extra_in_mapping={extra}",
            )
        )

    spec_by_number = {item["number"]: item for item in specs}
    # The closure packs are the admission registry: unlike the earlier source
    # verification tables, they contain no rejected/original candidate URLs as
    # usable evidence.  All replacement citations must occur in this stricter
    # registry (and the two source-verification packs remain date-pinned inputs).
    registry_urls = {
        _normalize_url(url)
        for text in closure_texts.values()
        for url in MARKDOWN_URL_RE.findall(text)
    }
    refinement_urls: list[str] = []
    replacement_rows: list[dict[str, str]] = []
    for mapping in mappings:
        number = mapping["number"]
        old_id = mapping["old"]
        new_id = mapping["new"]
        old = proposal_by_id.get(old_id)
        spec = spec_by_number.get(number)
        old_domain = old_id.rsplit(".", 1)[0] if "." in old_id else ""
        new_domain = new_id.rsplit(".", 1)[0] if "." in new_id else ""

        if old is None:
            findings.append(Finding("old_id_missing", f"mapping {number}: old terminal not in proposal: {old_id}"))
        if old_domain != new_domain:
            findings.append(
                Finding("domain_preservation", f"mapping {number}: domain changed {old_domain!r} -> {new_domain!r}")
            )
        if mapping["class"] not in {"S", "C"}:
            findings.append(Finding("replacement_class", f"mapping {number}: invalid class {mapping['class']!r}"))
        if old is not None and mapping["class"] != old["class"]:
            findings.append(
                Finding(
                    "class_preservation",
                    f"mapping {number}: {old_id} is {old['class']}, replacement declares {mapping['class']}",
                )
            )
        if spec is None:
            findings.append(Finding("missing_spec", f"mapping {number}: no detailed refinement specification"))
            continue
        if spec["old"] != old_id or spec["new"] != new_id:
            findings.append(
                Finding(
                    "spec_mapping",
                    f"mapping {number}: table {old_id}->{new_id}, spec {spec['old']}->{spec['new']}",
                )
            )
        if spec["class"] != mapping["class"]:
            findings.append(
                Finding(
                    "spec_class",
                    f"mapping {number}: table class {mapping['class']}, spec class {spec['class']}",
                )
            )
        for field_name, count in spec["field_counts"].items():
            if count != 1:
                findings.append(
                    Finding(
                        "spec_field",
                        f"mapping {number} {new_id}: field {field_name} must occur exactly once, got {count}",
                    )
                )
        if spec["name"] is None or _split_bilingual(spec["name"]) is None:
            findings.append(Finding("bilingual_name", f"mapping {number} {new_id}: name is not KO/EN bilingual"))
        if spec["goal"] is None or _split_bilingual(spec["goal"]) is None:
            findings.append(Finding("bilingual_goal", f"mapping {number} {new_id}: goal is not KO/EN bilingual"))
        if not spec["role_asset"]:
            findings.append(Finding("role_asset", f"mapping {number} {new_id}: missing role/asset ontology"))
        if not spec["state_transition"] or "->" not in spec["state_transition"]:
            findings.append(
                Finding("state_transition", f"mapping {number} {new_id}: missing explicit state transition")
            )
        if not spec["jurisdiction"]:
            findings.append(
                Finding("jurisdiction", f"mapping {number} {new_id}: missing jurisdiction guard")
            )
        if not spec["non_equivalence"]:
            findings.append(
                Finding("non_equivalence", f"mapping {number} {new_id}: missing nearest-domain non-equivalence")
            )
        if not spec["source_urls"]:
            findings.append(Finding("source_url", f"mapping {number} {new_id}: no accepted official HTTPS URL"))
        for url in spec["source_urls"]:
            refinement_urls.append(url)
            if _normalize_url(url) not in registry_urls:
                findings.append(
                    Finding("source_registry", f"mapping {number} {new_id}: URL absent from verified registry: {url}")
                )
        if spec["name"] and spec["goal"]:
            replacement_rows.append(
                {
                    "class": mapping["class"],
                    "function": new_id,
                    "domain": new_domain,
                    "name": spec["name"],
                    "goal": spec["goal"],
                }
            )

    mapping_class_counts = Counter(item["class"] for item in mappings)
    expected_mapping_classes = {
        "S": EXPECTED_REPLACEMENT_SENSITIVE,
        "C": EXPECTED_REPLACEMENT_CONSEQUENTIAL,
    }
    if dict(mapping_class_counts) != expected_mapping_classes:
        findings.append(
            Finding("replacement_class_count", f"expected {expected_mapping_classes}, got {dict(mapping_class_counts)}")
        )

    normalized_refinement_urls = [_normalize_url(url) for url in refinement_urls]
    if len(refinement_urls) != EXPECTED_REFINEMENT_SOURCE_COUNT:
        findings.append(
            Finding("refinement_source_count", f"expected {EXPECTED_REFINEMENT_SOURCE_COUNT}, got {len(refinement_urls)}")
        )
    if len(set(normalized_refinement_urls)) != EXPECTED_REFINEMENT_SOURCE_COUNT:
        findings.append(
            Finding(
                "refinement_source_uniqueness",
                f"expected {EXPECTED_REFINEMENT_SOURCE_COUNT} unique normalized URLs, got {len(set(normalized_refinement_urls))}",
            )
        )

    old_set = set(old_ids)
    remaining_rows = [row for row in proposal_rows if row["function"] not in old_set]
    if len(remaining_rows) != 224:
        findings.append(Finding("remaining_proposal_count", f"expected 224, got {len(remaining_rows)}"))
    projected_rows = remaining_rows + replacement_rows
    projected_unique_ids = {row["function"] for row in projected_rows}
    projected_domains: dict[str, Counter[str]] = {
        domain: Counter() for domain in proposal_domains
    }
    for row in projected_rows:
        projected_domains.setdefault(row["domain"], Counter())[row["class"]] += 1
    if len(projected_rows) != 240:
        findings.append(Finding("projected_terminal_count", f"expected 240, got {len(projected_rows)}"))
    if len(projected_unique_ids) != 240:
        findings.append(
            Finding("projected_unique_id_count", f"expected 240 unique projected IDs, got {len(projected_unique_ids)}")
        )
    projected_class_counts = Counter(row["class"] for row in projected_rows)
    if projected_class_counts != Counter({"S": 84, "C": 156}):
        findings.append(
            Finding("projected_class_count", f"expected S84/C156, got {dict(projected_class_counts)}")
        )
    if len(projected_domains) != EXPECTED_DOMAIN_COUNT:
        findings.append(
            Finding("projected_domain_count", f"expected {EXPECTED_DOMAIN_COUNT}, got {len(projected_domains)}")
        )
    for domain, counts in projected_domains.items():
        if counts != Counter({"S": 7, "C": 13}):
            findings.append(
                Finding("projected_domain_shape", f"{domain}: expected hub1 + S7/C13, got {dict(counts)}")
            )

    new_id_set = set(new_ids)
    remaining_ids = {row["function"] for row in remaining_rows}
    canonical_ids = catalog["function_ids"]
    equivalence_ids = equivalence["member_ids"]
    collision_details: dict[str, list[str]] = {}

    def record_collision(code: str, values: Iterable[str], message: str) -> None:
        hits = sorted(set(values))
        collision_details[code] = hits
        for value in hits:
            findings.append(Finding(code, f"{message}: {value}"))

    record_collision("remaining_id_collision", new_id_set & remaining_ids, "replacement ID collides with remaining proposal")
    record_collision("canonical_id_collision", new_id_set & canonical_ids, "replacement ID collides with canonical catalog")
    record_collision(
        "equivalence_id_collision",
        new_id_set & equivalence_ids,
        "replacement ID collides with equivalence member",
    )

    valid_replacements = [row for row in replacement_rows if _split_bilingual(row["name"]) and _split_bilingual(row["goal"])]
    replacement_name_pairs = [_split_bilingual(row["name"]) for row in valid_replacements]
    replacement_goal_pairs = [_split_bilingual(row["goal"]) for row in valid_replacements]
    for locale_index, locale in enumerate(("ko", "en")):
        names = [_normalize_identity(pair[locale_index]) for pair in replacement_name_pairs if pair]
        goals = [_normalize_identity(pair[locale_index]) for pair in replacement_goal_pairs if pair]
        record_collision(f"duplicate_{locale}_name", _duplicate_values(names), f"duplicate normalized {locale} name")
        record_collision(f"duplicate_{locale}_goal", _duplicate_values(goals), f"duplicate normalized {locale} goal")

    remaining_name_values: set[str] = set()
    remaining_goal_values: set[str] = set()
    for row in remaining_rows:
        name_pair = _split_bilingual(row["name"])
        goal_pair = _split_bilingual(row["goal"])
        if name_pair:
            remaining_name_values.update(_normalize_identity(value) for value in name_pair)
        if goal_pair:
            remaining_goal_values.update(_normalize_identity(value) for value in goal_pair)
    replacement_name_values = {
        _normalize_identity(value)
        for pair in replacement_name_pairs
        if pair
        for value in pair
    }
    replacement_goal_values = {
        _normalize_identity(value)
        for pair in replacement_goal_pairs
        if pair
        for value in pair
    }
    record_collision(
        "remaining_name_collision",
        replacement_name_values & remaining_name_values,
        "replacement name collides with remaining proposal",
    )
    record_collision(
        "remaining_goal_collision",
        replacement_goal_values & remaining_goal_values,
        "replacement goal collides with remaining proposal",
    )
    record_collision(
        "canonical_name_collision",
        replacement_name_values & catalog["normalized_names"],
        "replacement name collides with canonical function name",
    )
    record_collision(
        "canonical_goal_collision",
        replacement_goal_values & catalog["normalized_patterns"],
        "replacement goal collides with canonical intent pattern",
    )

    if catalog["catalog_version"] != "15.0.0":
        findings.append(
            Finding("canonical_version", f"expected canonical 15.0.0, got {catalog['catalog_version']!r}")
        )
    if catalog["function_count"] != 2866 or catalog["intent_count"] != 2660:
        findings.append(
            Finding(
                "canonical_count",
                f"expected functions/intents 2866/2660, got {catalog['function_count']}/{catalog['intent_count']}",
            )
        )
    audit_counts = equivalence["audit_counts"]
    if audit_counts.get("physical_function_count") != catalog["function_count"]:
        findings.append(Finding("equivalence_baseline", "equivalence physical-function count differs from catalog"))
    if audit_counts.get("physical_intent_count") != catalog["intent_count"]:
        findings.append(Finding("equivalence_baseline", "equivalence physical-intent count differs from catalog"))

    return {
        "schema_version": "1.0.0",
        "verification_date": expected_date,
        "inputs": {
            "proposal": _display_path(proposal_path),
            "proposal_sha256": _sha256(proposal_path),
            "refinement": _display_path(refinement_path),
            "refinement_sha256": _sha256(refinement_path),
            "source_documents": [_display_path(path) for path in source_paths],
            "closure_documents": [_display_path(path) for path in closure_paths],
            "catalog": _display_path(catalog_path),
            "catalog_version": catalog["catalog_version"],
            "equivalence": _display_path(equivalence_path),
            "equivalence_version": equivalence["equivalence_version"],
        },
        "declared_dates": declared_dates,
        "proposal": {
            "domain_count": len(proposal_sections),
            "hub_count": sum(section["hub"] is not None for section in proposal_sections),
            "terminal_count": len(proposal_rows),
            "sensitive_count": sum(row["class"] == "S" for row in proposal_rows),
            "consequential_count": sum(row["class"] == "C" for row in proposal_rows),
        },
        "closure": {
            "partially_resolved_count": len(partial_ids),
            "partially_resolved_ids": sorted(partial_ids),
            "by_document": closure_partial_by_document,
        },
        "refinement": {
            "mapping_count": len(mappings),
            "spec_count": len(specs),
            "old_id_count": len(set(old_ids)),
            "new_id_count": len(set(new_ids)),
            "sensitive_count": mapping_class_counts["S"],
            "consequential_count": mapping_class_counts["C"],
            "source_url_count": len(refinement_urls),
            "unique_source_url_count": len(set(normalized_refinement_urls)),
            "official_registry_url_count": len(registry_urls),
        },
        "projection": {
            "remaining_proposal_terminals": len(remaining_rows),
            "domain_count": len(projected_domains),
            "hub_count": len(proposal_sections),
            "terminal_count": len(projected_rows),
            "unique_terminal_id_count": len(projected_unique_ids),
            "sensitive_count": projected_class_counts["S"],
            "consequential_count": projected_class_counts["C"],
        },
        "collisions": {key: len(values) for key, values in sorted(collision_details.items())},
        "finding_count": len(findings),
        "findings": [finding.as_dict() for finding in findings],
        "passed": not findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument("--refinement", type=Path, default=DEFAULT_REFINEMENT)
    parser.add_argument("--source-document", type=Path, action="append", dest="source_documents")
    parser.add_argument("--closure-document", type=Path, action="append", dest="closure_documents")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--equivalence", type=Path, default=DEFAULT_EQUIVALENCE)
    parser.add_argument("--expected-date", default=EXPECTED_DATE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()

    report = audit_refinement(
        args.proposal,
        args.refinement,
        source_documents=args.source_documents or DEFAULT_SOURCE_DOCUMENTS,
        closure_documents=args.closure_documents or DEFAULT_CLOSURE_DOCUMENTS,
        catalog_path=args.catalog,
        equivalence_path=args.equivalence,
        expected_date=args.expected_date,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 1 if args.gate and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
