#!/usr/bin/env python3
"""Audit the V16 official-source verification reports against their proposal.

The audit is deliberately limited to the V16 proposal, its two source reports,
the materialized canonical catalog, and the function-equivalence overlay.  It
must never inspect independent fixtures, answers, failures, or evaluations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROPOSAL = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V16.md"
DEFAULT_PART1 = ROOT / "docs" / "NAVIGATION_SOURCES_V16_PART1.md"
DEFAULT_PART2 = ROOT / "docs" / "NAVIGATION_SOURCES_V16_PART2.md"
DEFAULT_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DEFAULT_EQUIVALENCE = ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json"
DEFAULT_CLOSURE_GLOB = "NAVIGATION_SOURCES_V16_GAP_CLOSURE_*.md"

EXPECTED_DATE = "2026-07-30"
EXPECTED_DOMAIN_COUNT = 12
EXPECTED_TERMINALS_PER_DOMAIN = 20
EXPECTED_ORIGINAL_CANDIDATES = 81
EXPECTED_PART1_CANDIDATES = 40
EXPECTED_PART2_CANDIDATES = 41
EXPECTED_PART1_USABLE = 43
EXPECTED_PART2_USABLE = 41

H2_RE = re.compile(r"^##\s+.+$", re.MULTILINE)
CLOSURE_HEADING_RE = re.compile(r"^#{2,3}\s+.+$", re.MULTILINE)
PROPOSAL_SECTION_RE = re.compile(
    r"^##\s+(?P<number>\d+)\.\s+.+?\(`(?P<domain>[a-z0-9_]+)`\)\s*$",
    re.MULTILINE,
)
PROPOSAL_ROW_RE = re.compile(
    r"^\|\s*(?P<class>[SC])\s*\|\s*`(?P<function>[a-z0-9_.]+)`\s*\|",
    re.MULTILINE,
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<target>[^)\s]+)\)")
BACKTICK_ID_RE = re.compile(r"`(?P<id>[a-z][a-z0-9_]+)`")


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    source: str | None = None

    def as_dict(self) -> dict[str, str]:
        value = {"code": self.code, "message": self.message}
        if self.source is not None:
            value["source"] = self.source
        return value


@dataclass(frozen=True)
class ProposalDomain:
    number: int
    domain: str
    hub_id: str | None
    terminal_ids: tuple[str, ...]
    terminal_suffixes: tuple[str, ...]
    candidate_urls: tuple[str, ...]


@dataclass(frozen=True)
class SourceRow:
    row_id: str
    date: str | None
    original_url: str | None
    final_url: str | None
    decision: str | None
    candidate_cell: str
    decision_cell: str
    scope_cell: str


@dataclass(frozen=True)
class SourceSection:
    domain: str
    proposal_number: int
    rows: tuple[SourceRow, ...]
    gap_urls: tuple[str, ...]
    unresolved_suffixes: tuple[str, ...]
    unresolved_claimed_count: int | None


@dataclass(frozen=True)
class ClosureSection:
    terminal_id: str
    status: str | None
    source_urls: tuple[str, ...]
    source_refs: tuple[str, ...]
    observed_dates: tuple[str, ...]
    has_access_observation: bool


def _source_name(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _links(text: str) -> list[str]:
    return [match.group("target") for match in MARKDOWN_LINK_RE.finditer(text)]


def normalize_url(url: str) -> str:
    """Normalize an HTTPS evidence URL without erasing path/query semantics."""

    parts = urlsplit(url.strip())
    scheme = parts.scheme.casefold()
    host = (parts.hostname or "").casefold()
    port = parts.port
    if port is not None and not (scheme == "https" and port == 443):
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)), doseq=True)
    return urlunsplit((scheme, host, path, query, ""))


def _section_slices(text: str, matches: list[re.Match[str]]) -> Iterable[tuple[re.Match[str], str]]:
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match, text[match.end() : end]


def _until_next_h2(text: str) -> str:
    match = re.search(r"\n##\s+", text)
    return text[: match.start()] if match else text


def _parse_proposal(text: str, findings: list[Finding], source: str) -> list[ProposalDomain]:
    matches = list(PROPOSAL_SECTION_RE.finditer(text))
    domains: list[ProposalDomain] = []
    for index, (match, body) in enumerate(_section_slices(text, matches), start=1):
        number = int(match.group("number"))
        domain = match.group("domain")
        if number != index:
            findings.append(Finding("proposal_section_order", f"{domain}: section {number}, expected {index}", source))

        hub_match = re.search(r"^Hub:\s*`(?P<hub>[a-z0-9_.]+)`", body, re.MULTILINE)
        hub_id = hub_match.group("hub") if hub_match else None
        if hub_id != f"{domain}.hub":
            findings.append(Finding("proposal_hub_id", f"{domain}: expected {domain}.hub, got {hub_id!r}", source))

        terminal_ids = tuple(row.group("function") for row in PROPOSAL_ROW_RE.finditer(body))
        suffixes: list[str] = []
        for function_id in terminal_ids:
            prefix = f"{domain}."
            if not function_id.startswith(prefix) or function_id == f"{domain}.hub":
                findings.append(Finding("proposal_terminal_scope", f"{domain}: invalid terminal {function_id}", source))
            else:
                suffixes.append(function_id[len(prefix) :])
        if len(terminal_ids) != EXPECTED_TERMINALS_PER_DOMAIN:
            findings.append(
                Finding(
                    "proposal_terminal_count",
                    f"{domain}: expected {EXPECTED_TERMINALS_PER_DOMAIN}, got {len(terminal_ids)}",
                    source,
                )
            )

        marker = "Official primary-source URL candidates"
        marker_index = body.find(marker)
        if marker_index < 0:
            candidate_urls: tuple[str, ...] = ()
            findings.append(Finding("proposal_candidate_block", f"{domain}: candidate block is missing", source))
        else:
            candidate_block = _until_next_h2(body[marker_index + len(marker) :])
            candidate_urls = tuple(_links(candidate_block))
        domains.append(
            ProposalDomain(
                number=number,
                domain=domain,
                hub_id=hub_id,
                terminal_ids=terminal_ids,
                terminal_suffixes=tuple(suffixes),
                candidate_urls=candidate_urls,
            )
        )
    return domains


def _markdown_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _decision(cell: str) -> str | None:
    lowered = cell.casefold()
    present = [name for name in ("accepted", "replaced", "rejected") if name in lowered]
    return present[0] if len(present) == 1 else None


def _parse_source_rows(body: str, *, part: int) -> tuple[SourceRow, ...]:
    rows: list[SourceRow] = []
    row_pattern = re.compile(r"\d+" if part == 1 else r"\d+-\d+")
    for line in body.splitlines():
        cells = _markdown_cells(line)
        if len(cells) != 5 or not row_pattern.fullmatch(cells[0]):
            continue
        if part == 1:
            row_id, candidate_cell, decision_cell, _, scope_cell = cells
            date = None
        else:
            row_id, date, candidate_cell, decision_cell, scope_cell = cells
        candidate_links = _links(candidate_cell)
        decision_links = _links(decision_cell)
        decision = _decision(decision_cell)
        original_url = candidate_links[0] if candidate_links else None
        final_url: str | None = None
        if decision == "accepted":
            final_url = candidate_links[-1] if candidate_links else None
        elif decision == "replaced":
            replacement_links = decision_links if decision_links else candidate_links[1:]
            final_url = replacement_links[-1] if replacement_links else None
        rows.append(
            SourceRow(
                row_id=row_id,
                date=date,
                original_url=original_url,
                final_url=final_url,
                decision=decision,
                candidate_cell=candidate_cell,
                decision_cell=decision_cell,
                scope_cell=scope_cell,
            )
        )
    return tuple(rows)


def _part1_sections(text: str, proposal_domains: set[str]) -> list[SourceSection]:
    matches = list(H2_RE.finditer(text))
    sections: list[SourceSection] = []
    for match, body in _section_slices(text, matches):
        prefix = re.search(r"Domain prefix:\s*`(?P<domain>[a-z0-9_]+)\.`", body)
        if not prefix or prefix.group("domain") not in proposal_domains:
            continue
        heading_number = re.match(r"^##\s+(\d+)\.", match.group(0))
        gap_match = re.search(
            r"Verified gap-closing sources?:\s*(?P<body>.*?)(?:\nCoverage verdict:|\Z)",
            body,
            re.DOTALL,
        )
        gap_urls = tuple(_links(gap_match.group("body"))) if gap_match else ()
        sections.append(
            SourceSection(
                domain=prefix.group("domain"),
                proposal_number=int(heading_number.group(1)) if heading_number else -1,
                rows=_parse_source_rows(body, part=1),
                gap_urls=gap_urls,
                unresolved_suffixes=(),
                unresolved_claimed_count=None,
            )
        )
    return sections


def _part2_sections(text: str, proposal_domains: set[str]) -> list[SourceSection]:
    matches = list(H2_RE.finditer(text))
    sections: list[SourceSection] = []
    for match, body in _section_slices(text, matches):
        domain_matches = [value for value in re.findall(r"`([a-z0-9_]+)`", match.group(0)) if value in proposal_domains]
        if len(domain_matches) != 1:
            continue
        proposal_number_match = re.search(r"(?:domain|\ub3c4\uba54\uc778)\s+(\d+)", match.group(0), re.IGNORECASE)
        gap_match = re.search(
            r"\*\*\ubbf8\ud574\uacb0 source gap\s+(?P<count>\d+)\uac1c:\*\*\s*(?P<items>[^.]+)\.",
            body,
        )
        unresolved = tuple(BACKTICK_ID_RE.findall(gap_match.group("items"))) if gap_match else ()
        sections.append(
            SourceSection(
                domain=domain_matches[0],
                proposal_number=int(proposal_number_match.group(1)) if proposal_number_match else -1,
                rows=_parse_source_rows(body, part=2),
                gap_urls=(),
                unresolved_suffixes=unresolved,
                unresolved_claimed_count=int(gap_match.group("count")) if gap_match else None,
            )
        )
    return sections


def _int_cell(cell: str) -> int | None:
    match = re.fullmatch(r"\*{0,2}\s*(\d+)\s*\*{0,2}", cell.strip())
    return int(match.group(1)) if match else None


def _summary_region(text: str, marker: str) -> str:
    start = text.find(marker)
    if start < 0:
        return ""
    return _until_next_h2(text[start + len(marker) :])


def _parse_summary(
    text: str,
    *,
    marker: str,
    expected_columns: int,
) -> tuple[dict[str, tuple[int, ...]], tuple[int, ...] | None, list[str]]:
    region = _summary_region(text, marker)
    rows: dict[str, tuple[int, ...]] = {}
    duplicates: list[str] = []
    total: tuple[int, ...] | None = None
    for line in region.splitlines():
        cells = _markdown_cells(line)
        if len(cells) != expected_columns + 1:
            continue
        numbers = tuple(_int_cell(cell) for cell in cells[1:])
        if any(value is None for value in numbers):
            continue
        values = tuple(int(value) for value in numbers if value is not None)
        domain_match = re.search(r"`([a-z0-9_]+)`", cells[0])
        if domain_match:
            domain = domain_match.group(1)
            if domain in rows:
                duplicates.append(domain)
            rows[domain] = values
        elif "Total" in cells[0] or "\ud569\uacc4" in cells[0]:
            total = values
    return rows, total, duplicates


def _closure_summary_region(text: str) -> str:
    for marker in (
        "## Exact closure summary",
        "## 2. \uc0c1\ud0dc \uc694\uc57d",
        "## 2. \uc0c1\ud0dc\ubcc4 \ucd1d\uacc4",
    ):
        region = _summary_region(text, marker)
        if region:
            return region
    return ""


def _parse_closure_summary(text: str) -> tuple[list[tuple[str, tuple[int, int, int, int]]], tuple[int, int, int, int] | None]:
    region = _closure_summary_region(text)
    rows: list[tuple[str, tuple[int, int, int, int]]] = []
    total: tuple[int, int, int, int] | None = None
    for line in region.splitlines():
        cells = _markdown_cells(line)
        if len(cells) not in {5, 6}:
            continue
        values = tuple(_int_cell(cell) for cell in cells[1:5])
        if any(value is None for value in values):
            continue
        numeric = tuple(int(value) for value in values if value is not None)
        assert len(numeric) == 4
        if "Total" in cells[0] or "\ud569\uacc4" in cells[0]:
            total = numeric  # type: ignore[assignment]
        else:
            rows.append((cells[0].replace("**", "").strip(), numeric))  # type: ignore[arg-type]
    return rows, total


def _parse_closure_sections(text: str) -> list[ClosureSection]:
    matches = list(CLOSURE_HEADING_RE.finditer(text))
    sections: list[ClosureSection] = []
    current_domain: str | None = None
    for match, body in _section_slices(text, matches):
        heading = match.group(0)
        backticked_ids = re.findall(r"`([a-z0-9_.]+)`", heading)
        full_terminal = next((value for value in backticked_ids if "." in value), None)
        if full_terminal is None and heading.startswith("## "):
            domain_id = next((value for value in backticked_ids if "." not in value), None)
            if domain_id is not None:
                current_domain = domain_id
                continue
        suffix = next((value for value in backticked_ids if "." not in value), None)
        terminal_id = full_terminal or (f"{current_domain}.{suffix}" if current_domain and suffix else None)
        if terminal_id is None or not heading.startswith(("## ", "### ")):
            continue
        status_match = re.search(
            r"\*\*(?:Status|\uc0c1\ud0dc|\ud310\uc815):\s*`(?P<status>resolved|partially_resolved|unresolved)`",
            body,
            re.IGNORECASE,
        )
        heading_status = re.search(
            r"(?:\u2014|-)\s*(?P<status>partially_resolved|resolved|unresolved)\s*$",
            heading,
            re.IGNORECASE,
        )
        observed_dates = tuple(
            re.findall(r"(?:Observed access on|\uad00\ucc30\uc77c|\uac80\uc99d\uc77c)\s*:?\s*(\d{4}-\d{2}-\d{2})", body)
        )
        sections.append(
            ClosureSection(
                terminal_id=terminal_id,
                status=(
                    status_match.group("status")
                    if status_match
                    else heading_status.group("status") if heading_status else None
                ),
                source_urls=tuple(_links(body)),
                source_refs=tuple(dict.fromkeys(re.findall(r"`\[(S\d+)\]`", body))),
                observed_dates=observed_dates,
                has_access_observation=bool(
                    re.search(r"(?:Observed access|\uc811\uadfc \uad00\ucc30|\uad00\ucc30\uc77c|\uac80\uc99d\uc77c)", body)
                ),
            )
        )
    return sections


def _declared_count(text: str, label: str) -> int | None:
    match = re.search(rf"^-\s*{re.escape(label)}:\s*\*\*(\d+)(?:\uac1c)?\*\*", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def _declared_count_any(text: str, labels: Iterable[str]) -> int | None:
    for label in labels:
        value = _declared_count(text, label)
        if value is not None:
            return value
    return None


def _source_registry(text: str) -> tuple[dict[str, str], list[str]]:
    registry: dict[str, str] = {}
    duplicates: list[str] = []
    pattern = re.compile(
        r"^-\s*`\[(?P<source_id>S\d+)\]`.*?\[[^\]]+\]\((?P<url>[^)\s]+)\)\s*$",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        source_id = match.group("source_id")
        if source_id in registry:
            duplicates.append(source_id)
        registry[source_id] = match.group("url")
    return registry, duplicates


def _audit_closure(
    *,
    path: Path,
    text: str,
    valid_terminal_ids: set[str],
    declared_gap_ids: set[str],
    findings: list[Finding],
    expected_date: str,
) -> dict[str, Any]:
    source = _source_name(path)
    _check_https_links(text, findings, source)
    date_match = re.search(
        r"^\s*(?:-\s*)?(?:Verification date|\uac80\uc99d\uc77c):\s*\*\*(\d{4}-\d{2}-\d{2})\*\*",
        text,
        re.MULTILINE,
    )
    verification_date = date_match.group(1) if date_match else None
    if verification_date != expected_date:
        findings.append(
            Finding("closure_verification_date", f"expected {expected_date}, got {verification_date!r}", source)
        )

    sections = _parse_closure_sections(text)
    registry, registry_duplicate_ids = _source_registry(text)
    for source_id in registry_duplicate_ids:
        findings.append(Finding("duplicate_closure_source_id", f"duplicate registry ID {source_id}", source))
    global_access_match = re.search(
        r"URL[^\n]*?(\d{4}-\d{2}-\d{2})[^\n]*(?:\uc2e4\uc81c \uc811\uadfc|actual(?:ly)? (?:accessed|retrieved))",
        text,
        re.IGNORECASE,
    )
    global_access_date = global_access_match.group(1) if global_access_match else None
    terminal_ids = [item.terminal_id for item in sections]
    for terminal_id, count in _duplicates(terminal_ids).items():
        findings.append(
            Finding("duplicate_closure_terminal", f"{terminal_id} appears {count} times", source)
        )
    for item in sections:
        if item.terminal_id not in valid_terminal_ids:
            findings.append(
                Finding("closure_terminal_id", f"not a V16 proposed terminal: {item.terminal_id}", source)
            )
        if item.terminal_id not in declared_gap_ids:
            findings.append(
                Finding("closure_not_declared_gap", f"not declared unresolved by source reports: {item.terminal_id}", source)
            )
        if item.status not in {"resolved", "partially_resolved", "unresolved"}:
            findings.append(
                Finding("closure_terminal_status", f"{item.terminal_id}: invalid status {item.status!r}", source)
            )
        if item.observed_dates and item.observed_dates != (expected_date,):
            findings.append(
                Finding(
                    "closure_observed_date",
                    f"{item.terminal_id}: expected one observed-access date {expected_date}, got {item.observed_dates}",
                    source,
                )
            )
        if (
            not item.observed_dates
            and global_access_date != expected_date
            and not (item.has_access_observation and verification_date == expected_date)
        ):
            findings.append(
                Finding(
                    "closure_observed_date",
                    f"{item.terminal_id}: no exact per-terminal or global access date {expected_date}",
                    source,
                )
            )
        if registry:
            if not item.source_refs:
                findings.append(
                    Finding("closure_terminal_sources", f"{item.terminal_id}: no registry source reference", source)
                )
            for source_id in item.source_refs:
                if source_id not in registry:
                    findings.append(
                        Finding(
                            "closure_unknown_source_ref",
                            f"{item.terminal_id}: source {source_id} is absent from registry",
                            source,
                        )
                    )
        elif not item.source_urls:
            findings.append(Finding("closure_terminal_sources", f"{item.terminal_id}: no official source URL", source))

    scope_matches: list[int] = []
    english_scope = re.search(r"^Scope:.*?/\s*(\d+)\s+terminals", text, re.MULTILINE)
    korean_scope = re.search(
        r"^\s*-\s*(?:\ubc94\uc704|\ub300\uc0c1):.*?(?:terminal/source[- ]?gap|terminal)\s*\*{0,2}(\d+)\s*\uac1c\*{0,2}",
        text,
        re.MULTILINE,
    )
    for match in (english_scope, korean_scope):
        if match:
            scope_matches.append(int(match.group(1)))
    scope_terminal_count = scope_matches[0] if scope_matches else None
    if len(set(scope_matches)) > 1:
        findings.append(Finding("closure_scope_count", f"conflicting scope counts {scope_matches}", source))
    if scope_terminal_count != len(sections):
        findings.append(
            Finding(
                "closure_scope_count",
                f"scope claims {scope_terminal_count}, parsed {len(sections)} terminal sections",
                source,
            )
        )

    category_rows, summary_total = _parse_closure_summary(text)
    category_labels = [label for label, _ in category_rows]
    for label, count in _duplicates(category_labels).items():
        findings.append(Finding("duplicate_closure_category", f"{label} appears {count} times", source))
    for label, values in category_rows:
        terminal_count, resolved, partial, unresolved = values
        if resolved + partial + unresolved != terminal_count:
            findings.append(
                Finding(
                    "closure_category_arithmetic",
                    f"{label}: {resolved}+{partial}+{unresolved} != {terminal_count}",
                    source,
                )
            )
    computed_total = tuple(sum(values[index] for _, values in category_rows) for index in range(4))
    if summary_total is None:
        findings.append(Finding("missing_closure_summary_total", "closure total row is missing", source))
    elif summary_total != computed_total:
        findings.append(
            Finding(
                "closure_summary_arithmetic",
                f"total row {summary_total}, computed {computed_total}",
                source,
            )
        )
    status_counts = Counter(item.status for item in sections if item.status is not None)
    actual_status_total = (
        len(sections),
        status_counts["resolved"],
        status_counts["partially_resolved"],
        status_counts["unresolved"],
    )
    if summary_total != actual_status_total:
        findings.append(
            Finding(
                "closure_status_total",
                f"summary {summary_total}, terminal sections {actual_status_total}",
                source,
            )
        )

    if registry:
        evidence_urls = list(registry.values())
        used_source_ids = {source_id for item in sections for source_id in item.source_refs}
        for source_id in sorted(set(registry) - used_source_ids):
            findings.append(Finding("closure_unused_source_ref", f"unused registry source {source_id}", source))
    else:
        evidence_urls = [url for item in sections for url in item.source_urls]
    normalized_urls = [normalize_url(url) for url in evidence_urls]
    unique_urls = set(normalized_urls)
    duplicate_reference_count = len(normalized_urls) - len(unique_urls)
    url_terminals: dict[str, set[str]] = defaultdict(set)
    for item in sections:
        if registry:
            for source_id in item.source_refs:
                if source_id in registry:
                    url_terminals[normalize_url(registry[source_id])].add(item.terminal_id)
        else:
            for url in item.source_urls:
                url_terminals[normalize_url(url)].add(item.terminal_id)
    cross_terminal_reuse_count = sum(len(terminals) > 1 for terminals in url_terminals.values())
    english_declarations = {
        "terminal_to_source_references": _declared_count(text, "Terminal-to-source references"),
        "normalized_official_urls": _declared_count(text, "Normalized official URLs"),
        "unique_normalized_urls": _declared_count(text, "Unique normalized URLs"),
        "duplicate_references": _declared_count(text, "Duplicate references"),
        "cross_terminal_url_reuse": _declared_count(text, "Cross-terminal URL reuse"),
    }
    english_actual = {
        "terminal_to_source_references": len(normalized_urls),
        "normalized_official_urls": len(normalized_urls),
        "unique_normalized_urls": len(unique_urls),
        "duplicate_references": duplicate_reference_count,
        "cross_terminal_url_reuse": cross_terminal_reuse_count,
    }
    korean_declarations = {
        "source_url_count": _declared_count_any(
            text,
            ("\ub808\uc9c0\uc2a4\ud2b8\ub9ac URL \uc218", "terminal\ubcc4 \ub300\ud45c URL"),
        ),
        "unique_normalized_urls": _declared_count_any(
            text,
            ("\uc815\uaddc\ud654 \ud6c4 \uace0\uc720 URL \uc218", "\uc815\uaddc\ud654 \ud6c4 \uace0\uc720 URL"),
        ),
        "duplicate_references": _declared_count_any(
            text,
            ("\uc815\uaddc\ud654 URL \uc911\ubcf5 \uc218", "\uc815\uaddc\ud654 \uc911\ubcf5"),
        ),
        "terminal_count": _declared_count_any(text, ("terminal \uc218",)),
        "non_official_source_count": _declared_count_any(text, ("\ube44\uacf5\uc2dd\u00b72\ucc28 \ucd9c\ucc98 \uc218",)),
    }
    korean_actual = {
        "source_url_count": len(normalized_urls),
        "unique_normalized_urls": len(unique_urls),
        "duplicate_references": duplicate_reference_count,
        "terminal_count": len(sections),
        "non_official_source_count": 0,
    }
    if any(value is not None for value in english_declarations.values()):
        declarations = english_declarations
        for label, actual in english_actual.items():
            if declarations[label] != actual:
                findings.append(
                    Finding(
                        "closure_url_declaration",
                        f"{label}: declared {declarations[label]}, actual {actual}",
                        source,
                    )
                )
    elif any(value is not None for value in korean_declarations.values()):
        declarations = korean_declarations
        required_korean = {"source_url_count", "unique_normalized_urls", "duplicate_references"}
        for label, actual in korean_actual.items():
            if (label in required_korean or declarations[label] is not None) and declarations[label] != actual:
                findings.append(
                    Finding(
                        "closure_url_declaration",
                        f"{label}: declared {declarations[label]}, actual {actual}",
                        source,
                    )
                )
    else:
        declarations = {}
        findings.append(Finding("closure_url_declaration", "URL count declarations are missing", source))

    status_declaration_match = re.search(
        r"\uc0c1\ud0dc \ud569\uacc4 \uac80\uc0b0:\s*\*\*(\d+) resolved \+ (\d+) partially_resolved \+ (\d+) unresolved = (\d+)\*\*",
        text,
    )
    if status_declaration_match:
        declared_status = tuple(int(value) for value in status_declaration_match.groups())
        actual_status_declaration = (
            status_counts["resolved"],
            status_counts["partially_resolved"],
            status_counts["unresolved"],
            len(sections),
        )
        if declared_status != actual_status_declaration:
            findings.append(
                Finding(
                    "closure_status_declaration",
                    f"declared {declared_status}, actual {actual_status_declaration}",
                    source,
                )
            )
    elif registry:
        findings.append(Finding("closure_status_declaration", "registry-format status checksum is missing", source))
    if duplicate_reference_count:
        findings.append(
            Finding("closure_url_duplicate", f"{duplicate_reference_count} duplicate URL references", source)
        )
    if english_declarations["cross_terminal_url_reuse"] is not None and cross_terminal_reuse_count:
        findings.append(
            Finding("closure_cross_terminal_url_reuse", f"{cross_terminal_reuse_count} reused URLs", source)
        )

    return {
        "path": source,
        "verification_date": verification_date,
        "terminal_count": len(sections),
        "terminals": terminal_ids,
        "status_counts": {
            "resolved": status_counts["resolved"],
            "partially_resolved": status_counts["partially_resolved"],
            "unresolved": status_counts["unresolved"],
        },
        "summary_total": list(summary_total) if summary_total is not None else None,
        "category_count": len(category_rows),
        "source_reference_count": len(normalized_urls),
        "unique_url_count": len(unique_urls),
        "duplicate_reference_count": duplicate_reference_count,
        "cross_terminal_url_reuse_count": cross_terminal_reuse_count,
        "url_declarations": declarations,
    }


def _duplicates(values: Iterable[str]) -> dict[str, int]:
    return {value: count for value, count in Counter(values).items() if count > 1}


def _check_https_links(text: str, findings: list[Finding], source: str) -> None:
    targets = _links(text)
    if not targets:
        findings.append(Finding("missing_https_links", "document has no Markdown links", source))
    for target in targets:
        if not target.casefold().startswith("https://"):
            findings.append(Finding("non_https_link", f"non-HTTPS Markdown link: {target}", source))


def _check_source_part(
    *,
    part: int,
    text: str,
    sections: list[SourceSection],
    proposal: list[ProposalDomain],
    summary_rows: dict[str, tuple[int, ...]],
    summary_total: tuple[int, ...] | None,
    summary_duplicates: list[str],
    findings: list[Finding],
    source: str,
) -> dict[str, Any]:
    expected_proposal = proposal[:6] if part == 1 else proposal[6:]
    expected_domains = [item.domain for item in expected_proposal]
    section_domains = [item.domain for item in sections]
    for domain, count in _duplicates(section_domains).items():
        findings.append(Finding("duplicate_report_domain", f"part {part}: {domain} appears {count} times", source))
    missing = sorted(set(expected_domains) - set(section_domains))
    unexpected = sorted(set(section_domains) - set(expected_domains))
    if missing:
        findings.append(Finding("missing_report_domain", f"part {part}: missing {missing}", source))
    if unexpected:
        findings.append(Finding("unexpected_report_domain", f"part {part}: unexpected {unexpected}", source))
    if section_domains != expected_domains:
        findings.append(
            Finding("report_domain_order", f"part {part}: expected {expected_domains}, got {section_domains}", source)
        )
    for duplicate in summary_duplicates:
        findings.append(Finding("duplicate_summary_domain", f"part {part}: duplicate summary row {duplicate}", source))
    if set(summary_rows) != set(expected_domains):
        findings.append(
            Finding(
                "summary_domain_set",
                f"part {part}: expected summary domains {expected_domains}, got {sorted(summary_rows)}",
                source,
            )
        )

    proposal_by_domain = {item.domain: item for item in proposal}
    row_count = 0
    decision_counts: Counter[str] = Counter()
    originals: list[str] = []
    final_entries: list[tuple[str, SourceRow]] = []
    gap_urls: list[str] = []
    unresolved: list[dict[str, Any]] = []
    per_domain: list[dict[str, Any]] = []

    for section in sections:
        expected = proposal_by_domain.get(section.domain)
        if expected is None:
            continue
        if section.proposal_number != expected.number:
            findings.append(
                Finding(
                    "report_domain_number",
                    f"{section.domain}: report number {section.proposal_number}, expected {expected.number}",
                    source,
                )
            )
        row_count += len(section.rows)
        row_ids = [row.row_id for row in section.rows]
        expected_row_ids = (
            [str(index) for index in range(1, len(section.rows) + 1)]
            if part == 1
            else [f"{expected.number}-{index}" for index in range(1, len(section.rows) + 1)]
        )
        if row_ids != expected_row_ids:
            findings.append(
                Finding("source_row_order", f"{section.domain}: expected row IDs {expected_row_ids}, got {row_ids}", source)
            )

        section_originals: list[str] = []
        section_finals: list[str] = []
        section_decisions: Counter[str] = Counter()
        for row in section.rows:
            if row.decision is None:
                findings.append(Finding("source_decision", f"{section.domain} row {row.row_id}: invalid decision", source))
            else:
                decision_counts[row.decision] += 1
                section_decisions[row.decision] += 1
            if part == 2 and row.date != EXPECTED_DATE:
                findings.append(
                    Finding(
                        "verification_date",
                        f"{section.domain} row {row.row_id}: expected {EXPECTED_DATE}, got {row.date!r}",
                        source,
                    )
                )
            if row.original_url is None:
                findings.append(Finding("missing_original_url", f"{section.domain} row {row.row_id}", source))
            else:
                normalized = normalize_url(row.original_url)
                originals.append(normalized)
                section_originals.append(normalized)
            if row.decision != "rejected" and row.final_url is None:
                findings.append(Finding("missing_final_url", f"{section.domain} row {row.row_id}", source))
            if row.final_url is not None:
                normalized_final = normalize_url(row.final_url)
                section_finals.append(normalized_final)
                final_entries.append((normalized_final, row))

        expected_originals = [normalize_url(value) for value in expected.candidate_urls]
        if section_originals != expected_originals:
            findings.append(
                Finding(
                    "original_candidate_mismatch",
                    f"{section.domain}: proposal/report original URL sequence differs",
                    source,
                )
            )
        if len(section.rows) != len(expected.candidate_urls):
            findings.append(
                Finding(
                    "original_candidate_count",
                    f"{section.domain}: proposal {len(expected.candidate_urls)}, report {len(section.rows)}",
                    source,
                )
            )

        section_gap_urls = [normalize_url(value) for value in section.gap_urls]
        gap_urls.extend(section_gap_urls)
        unique_finals = set(section_finals)
        unique_gaps = set(section_gap_urls)
        usable = unique_finals | unique_gaps
        summary = summary_rows.get(section.domain)
        if part == 1:
            actual = (
                len(section.rows),
                section_decisions["accepted"],
                section_decisions["replaced"],
                section_decisions["rejected"],
                len(unique_finals),
                len(unique_gaps),
                len(usable),
            )
        else:
            actual = (
                len(section.rows),
                section_decisions["accepted"],
                section_decisions["replaced"],
                section_decisions["rejected"],
                len(unique_finals),
                len(section.unresolved_suffixes),
            )
        if summary != actual:
            findings.append(
                Finding("summary_actual_mismatch", f"{section.domain}: expected actual {actual}, got {summary}", source)
            )
        if summary is not None and sum(summary[1:4]) != summary[0]:
            findings.append(
                Finding("summary_decision_arithmetic", f"{section.domain}: decisions do not sum to candidates", source)
            )

        if part == 2:
            if section.unresolved_claimed_count != len(section.unresolved_suffixes):
                findings.append(
                    Finding(
                        "unresolved_count",
                        f"{section.domain}: claimed {section.unresolved_claimed_count}, parsed {len(section.unresolved_suffixes)}",
                        source,
                    )
                )
            valid_suffixes = set(expected.terminal_suffixes)
            for suffix in section.unresolved_suffixes:
                valid = suffix in valid_suffixes
                unresolved.append({"domain": section.domain, "suffix": suffix, "valid": valid})
                if not valid:
                    findings.append(
                        Finding(
                            "unresolved_terminal_suffix",
                            f"{section.domain}: {suffix} is not a proposed terminal suffix",
                            source,
                        )
                    )
        per_domain.append(
            {
                "domain": section.domain,
                "original_candidates": len(section.rows),
                "decisions": dict(sorted(section_decisions.items())),
                "candidate_derived_usable": len(unique_finals),
                "gap_closing_usable": len(unique_gaps),
                "usable": len(usable),
                "unresolved_terminal_count": len(section.unresolved_suffixes),
            }
        )

    normalized_original_duplicates = _duplicates(originals)
    for url, count in normalized_original_duplicates.items():
        findings.append(Finding("original_url_duplicate", f"part {part}: {url} appears {count} times", source))

    grouped_finals: dict[str, list[SourceRow]] = defaultdict(list)
    for url, row in final_entries:
        grouped_finals[url].append(row)
    unresolved_final_duplicates: dict[str, int] = {}
    documented_shared_final_count = 0
    for url, rows in grouped_finals.items():
        if len(rows) < 2:
            continue
        documented = (
            part == 1
            and len(rows) == 2
            and any(
                row.decision == "replaced"
                and "shared" in row.scope_cell.casefold()
                and "counted once" in row.scope_cell.casefold()
                for row in rows
            )
        )
        if documented:
            documented_shared_final_count += 1
        else:
            unresolved_final_duplicates[url] = len(rows)
            findings.append(
                Finding("usable_url_duplicate", f"part {part}: {url} appears {len(rows)} times", source)
            )
    if part == 1 and documented_shared_final_count != 1:
        findings.append(
            Finding(
                "documented_shared_url",
                f"part 1: expected one documented shared final URL, got {documented_shared_final_count}",
                source,
            )
        )

    unique_candidate_finals = set(grouped_finals)
    unique_gap_urls = set(gap_urls)
    gap_duplicates = _duplicates(gap_urls)
    for url, count in gap_duplicates.items():
        findings.append(Finding("gap_url_duplicate", f"part {part}: {url} appears {count} times", source))
    gap_intersection = unique_candidate_finals & unique_gap_urls
    for url in sorted(gap_intersection):
        findings.append(Finding("gap_candidate_url_overlap", f"part {part}: {url}", source))
    combined_usable = unique_candidate_finals | unique_gap_urls

    expected_candidates = EXPECTED_PART1_CANDIDATES if part == 1 else EXPECTED_PART2_CANDIDATES
    expected_usable = EXPECTED_PART1_USABLE if part == 1 else EXPECTED_PART2_USABLE
    if row_count != expected_candidates:
        findings.append(
            Finding("part_candidate_total", f"part {part}: expected {expected_candidates}, got {row_count}", source)
        )
    if len(combined_usable) != expected_usable:
        findings.append(
            Finding("part_usable_total", f"part {part}: expected {expected_usable}, got {len(combined_usable)}", source)
        )

    if summary_total is None:
        findings.append(Finding("missing_summary_total", f"part {part}: total row is missing", source))
    elif summary_rows:
        computed_total = tuple(sum(values[index] for values in summary_rows.values()) for index in range(len(summary_total)))
        if summary_total != computed_total:
            findings.append(
                Finding(
                    "summary_total_arithmetic",
                    f"part {part}: total row {summary_total}, computed {computed_total}",
                    source,
                )
            )
        if summary_total[0] != expected_candidates:
            findings.append(
                Finding(
                    "summary_candidate_total",
                    f"part {part}: expected {expected_candidates}, total row has {summary_total[0]}",
                    source,
                )
            )
        usable_index = 6 if part == 1 else 4
        if summary_total[usable_index] != expected_usable:
            findings.append(
                Finding(
                    "summary_usable_total",
                    f"part {part}: expected {expected_usable}, total row has {summary_total[usable_index]}",
                    source,
                )
            )

    duplicate_claim_ok = (
        "Combined usable registry: **43 unique normalized URLs, 0 unresolved duplicates**" in text
        if part == 1
        else "**\uc911\ubcf5 URL\uc740 0\uac1c**" in text and "\ucd5c\uc885 usable URL 41\uac1c" in text
    )
    if not duplicate_claim_ok:
        findings.append(Finding("normalized_duplicate_claim", f"part {part}: exact zero-duplicate claim is missing", source))

    return {
        "domain_count": len(sections),
        "domains": section_domains,
        "original_candidate_count": row_count,
        "unique_original_candidate_count": len(set(originals)),
        "decisions": {name: decision_counts[name] for name in ("accepted", "replaced", "rejected")},
        "candidate_derived_usable_count": len(unique_candidate_finals),
        "gap_closing_usable_count": len(unique_gap_urls),
        "usable_count": len(combined_usable),
        "normalized_original_duplicate_count": len(normalized_original_duplicates),
        "normalized_unresolved_usable_duplicate_count": len(unresolved_final_duplicates),
        "documented_shared_final_url_count": documented_shared_final_count,
        "gap_url_duplicate_count": len(gap_duplicates),
        "candidate_gap_overlap_count": len(gap_intersection),
        "unresolved_terminals": unresolved,
        "summary_total": list(summary_total) if summary_total is not None else None,
        "per_domain": per_domain,
    }


def _part1_unresolved(
    text: str,
    proposal: list[ProposalDomain],
    findings: list[Finding],
    source: str,
) -> list[dict[str, Any]]:
    line = next((value for value in text.splitlines() if value.startswith("Unresolved terminal-level items:")), "")
    count_match = re.search(r"covering\s+(\d+)\s+terminals", line)
    item_text = line.split(" \u2014 ", 1)[1].split(". Product-interface", 1)[0] if " \u2014 " in line else ""
    suffixes = BACKTICK_ID_RE.findall(item_text)
    claimed = int(count_match.group(1)) if count_match else None
    if claimed != len(suffixes):
        findings.append(
            Finding("unresolved_count", f"part 1: claimed {claimed}, parsed {len(suffixes)}", source)
        )
    suffix_domains: dict[str, list[str]] = defaultdict(list)
    for item in proposal:
        for suffix in item.terminal_suffixes:
            suffix_domains[suffix].append(item.domain)
    results: list[dict[str, Any]] = []
    for suffix in suffixes:
        domains = suffix_domains.get(suffix, [])
        valid = bool(domains)
        results.append({"suffix": suffix, "domains": domains, "valid": valid})
        if not valid:
            findings.append(
                Finding("unresolved_terminal_suffix", f"part 1: {suffix} is not a proposed terminal suffix", source)
            )
    return results


def _canonical_audit(
    proposal: list[ProposalDomain],
    catalog: dict[str, Any],
    equivalence: dict[str, Any],
    findings: list[Finding],
    catalog_source: str,
    equivalence_source: str,
) -> dict[str, Any]:
    functions = [item for item in catalog.get("functions", []) if isinstance(item, dict)]
    intents = [item for item in catalog.get("intents", []) if isinstance(item, dict)]
    canonical_function_ids = {str(item.get("function_id")) for item in functions if item.get("function_id")}
    canonical_intent_ids = {str(item.get("intent_id")) for item in intents if item.get("intent_id")}
    canonical_domains = {str(item.get("domain")) for item in functions if item.get("domain")}

    proposal_domains = [item.domain for item in proposal]
    proposal_function_ids = [
        function_id
        for item in proposal
        for function_id in ((item.hub_id,) if item.hub_id else ()) + item.terminal_ids
    ]
    proposal_intent_ids = [
        f"v16_{item.domain}_{suffix}"
        for item in proposal
        for suffix in item.terminal_suffixes
    ]
    for label, values in (
        ("domain", proposal_domains),
        ("function", proposal_function_ids),
        ("intent", proposal_intent_ids),
    ):
        for value, count in _duplicates(values).items():
            findings.append(
                Finding("proposal_id_duplicate", f"proposed {label} ID {value} appears {count} times", catalog_source)
            )

    domain_collisions = sorted(set(proposal_domains) & canonical_domains)
    function_collisions = sorted(set(proposal_function_ids) & canonical_function_ids)
    intent_collisions = sorted(set(proposal_intent_ids) & canonical_intent_ids)
    for value in domain_collisions:
        findings.append(Finding("canonical_domain_collision", value, catalog_source))
    for value in function_collisions:
        findings.append(Finding("canonical_function_collision", value, catalog_source))
    for value in intent_collisions:
        findings.append(Finding("canonical_intent_collision", value, catalog_source))

    equivalence_ids: set[str] = set()
    for item in equivalence.get("classes", []):
        if not isinstance(item, dict):
            continue
        if item.get("canonical_function_id"):
            equivalence_ids.add(str(item["canonical_function_id"]))
        equivalence_ids.update(str(value) for value in item.get("alias_function_ids", []))
    equivalence_collisions = sorted(set(proposal_function_ids) & equivalence_ids)
    for value in equivalence_collisions:
        findings.append(Finding("equivalence_function_collision", value, equivalence_source))

    counts = equivalence.get("audit_counts", {})
    if counts.get("physical_function_count") != len(canonical_function_ids):
        findings.append(
            Finding(
                "equivalence_catalog_baseline",
                f"physical functions {counts.get('physical_function_count')} != {len(canonical_function_ids)}",
                equivalence_source,
            )
        )
    if counts.get("physical_intent_count") != len(canonical_intent_ids):
        findings.append(
            Finding(
                "equivalence_catalog_baseline",
                f"physical intents {counts.get('physical_intent_count')} != {len(canonical_intent_ids)}",
                equivalence_source,
            )
        )

    return {
        "catalog_version": catalog.get("catalog_version"),
        "equivalence_version": equivalence.get("equivalence_version"),
        "canonical_domain_count": len(canonical_domains),
        "canonical_function_count": len(canonical_function_ids),
        "canonical_intent_count": len(canonical_intent_ids),
        "proposed_function_count": len(proposal_function_ids),
        "proposed_intent_count": len(proposal_intent_ids),
        "domain_collision_count": len(domain_collisions),
        "function_collision_count": len(function_collisions),
        "intent_collision_count": len(intent_collisions),
        "equivalence_collision_count": len(equivalence_collisions),
    }


def audit_source_verification(
    proposal_path: Path = DEFAULT_PROPOSAL,
    part1_path: Path = DEFAULT_PART1,
    part2_path: Path = DEFAULT_PART2,
    catalog_path: Path = DEFAULT_CATALOG,
    equivalence_path: Path = DEFAULT_EQUIVALENCE,
    *,
    expected_date: str = EXPECTED_DATE,
    closure_paths: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Return a deterministic gate/report for the V16 verification documents."""

    proposal_path = proposal_path.resolve()
    part1_path = part1_path.resolve()
    part2_path = part2_path.resolve()
    catalog_path = catalog_path.resolve()
    equivalence_path = equivalence_path.resolve()
    if closure_paths is None:
        resolved_closure_paths = sorted(proposal_path.parent.glob(DEFAULT_CLOSURE_GLOB))
    else:
        resolved_closure_paths = sorted(Path(path).resolve() for path in closure_paths)
    findings: list[Finding] = []
    proposal_text = proposal_path.read_text(encoding="utf-8-sig")
    part1_text = part1_path.read_text(encoding="utf-8-sig")
    part2_text = part2_path.read_text(encoding="utf-8-sig")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    equivalence = json.loads(equivalence_path.read_text(encoding="utf-8"))

    source_names = {
        "proposal": _source_name(proposal_path),
        "part1": _source_name(part1_path),
        "part2": _source_name(part2_path),
        "catalog": _source_name(catalog_path),
        "equivalence": _source_name(equivalence_path),
    }
    closure_source_names = [_source_name(path) for path in resolved_closure_paths]
    for path, text, key in (
        (proposal_path, proposal_text, "proposal"),
        (part1_path, part1_text, "part1"),
        (part2_path, part2_text, "part2"),
    ):
        _check_https_links(text, findings, source_names[key])

    proposal_date_match = re.search(r"^Audit date:\s*(\d{4}-\d{2}-\d{2})", proposal_text, re.MULTILINE)
    part1_date_match = re.search(r"^Verification date:\s*\*\*(\d{4}-\d{2}-\d{2})\*\*", part1_text, re.MULTILINE)
    part2_date_match = re.search(r"^\uac80\uc99d\uc77c:\s*\*\*(\d{4}-\d{2}-\d{2})\*\*", part2_text, re.MULTILINE)
    for label, match, key in (
        ("proposal audit", proposal_date_match, "proposal"),
        ("part 1 verification", part1_date_match, "part1"),
        ("part 2 verification", part2_date_match, "part2"),
    ):
        actual = match.group(1) if match else None
        if actual != expected_date:
            findings.append(
                Finding("verification_date", f"{label}: expected {expected_date}, got {actual!r}", source_names[key])
            )
    if f"Every candidate row below was verified on {expected_date}." not in part1_text:
        findings.append(
            Finding("verification_date_scope", "part 1 does not bind its global date to every candidate row", source_names["part1"])
        )

    proposal = _parse_proposal(proposal_text, findings, source_names["proposal"])
    proposal_domains = [item.domain for item in proposal]
    if len(proposal) != EXPECTED_DOMAIN_COUNT:
        findings.append(
            Finding(
                "proposal_domain_count",
                f"expected {EXPECTED_DOMAIN_COUNT}, got {len(proposal)}",
                source_names["proposal"],
            )
        )
    for domain, count in _duplicates(proposal_domains).items():
        findings.append(
            Finding("proposal_domain_duplicate", f"{domain} appears {count} times", source_names["proposal"])
        )
    proposal_candidates = [normalize_url(url) for item in proposal for url in item.candidate_urls]
    proposal_candidate_duplicates = _duplicates(proposal_candidates)
    for url, count in proposal_candidate_duplicates.items():
        findings.append(
            Finding("proposal_candidate_duplicate", f"{url} appears {count} times", source_names["proposal"])
        )
    if len(proposal_candidates) != EXPECTED_ORIGINAL_CANDIDATES:
        findings.append(
            Finding(
                "proposal_candidate_total",
                f"expected {EXPECTED_ORIGINAL_CANDIDATES}, got {len(proposal_candidates)}",
                source_names["proposal"],
            )
        )

    proposal_domain_set = set(proposal_domains)
    part1_sections = _part1_sections(part1_text, proposal_domain_set)
    part2_sections = _part2_sections(part2_text, proposal_domain_set)
    part1_summary, part1_total, part1_summary_duplicates = _parse_summary(
        part1_text,
        marker="## Exact decision and accepted-source counts",
        expected_columns=7,
    )
    part2_summary, part2_total, part2_summary_duplicates = _parse_summary(
        part2_text,
        marker="## 2. \uc804\uccb4 \uacb0\uacfc",
        expected_columns=6,
    )
    part1 = _check_source_part(
        part=1,
        text=part1_text,
        sections=part1_sections,
        proposal=proposal,
        summary_rows=part1_summary,
        summary_total=part1_total,
        summary_duplicates=part1_summary_duplicates,
        findings=findings,
        source=source_names["part1"],
    )
    part2 = _check_source_part(
        part=2,
        text=part2_text,
        sections=part2_sections,
        proposal=proposal,
        summary_rows=part2_summary,
        summary_total=part2_total,
        summary_duplicates=part2_summary_duplicates,
        findings=findings,
        source=source_names["part2"],
    )
    part1_unresolved = _part1_unresolved(part1_text, proposal, findings, source_names["part1"])
    part1["unresolved_terminals"] = part1_unresolved
    part1["unresolved_terminal_count"] = len(part1_unresolved)

    valid_terminal_ids = {function_id for item in proposal for function_id in item.terminal_ids}
    declared_gap_ids = {
        f"{domain}.{item['suffix']}"
        for item in part1_unresolved
        for domain in item["domains"]
    }
    declared_gap_ids.update(
        f"{item['domain']}.{item['suffix']}"
        for item in part2["unresolved_terminals"]
        if item["valid"]
    )
    closure_reports: list[dict[str, Any]] = []
    closure_terminal_ids: list[str] = []
    for closure_path in resolved_closure_paths:
        closure_text = closure_path.read_text(encoding="utf-8-sig")
        closure_report = _audit_closure(
            path=closure_path,
            text=closure_text,
            valid_terminal_ids=valid_terminal_ids,
            declared_gap_ids=declared_gap_ids,
            findings=findings,
            expected_date=expected_date,
        )
        closure_reports.append(closure_report)
        closure_terminal_ids.extend(closure_report["terminals"])
    for terminal_id, count in _duplicates(closure_terminal_ids).items():
        findings.append(
            Finding(
                "duplicate_closure_terminal_across_documents",
                f"{terminal_id} appears in {count} closure documents/sections",
                "gap closures",
            )
        )

    combined_report_domains = part1["domains"] + part2["domains"]
    for domain, count in _duplicates(combined_report_domains).items():
        findings.append(
            Finding("duplicate_report_domain", f"combined reports: {domain} appears {count} times", "parts 1+2")
        )
    if set(combined_report_domains) != set(proposal_domains):
        findings.append(
            Finding(
                "combined_report_domain_set",
                f"proposal domains and report domains differ",
                "parts 1+2",
            )
        )
    combined_original_count = part1["original_candidate_count"] + part2["original_candidate_count"]
    if combined_original_count != EXPECTED_ORIGINAL_CANDIDATES:
        findings.append(
            Finding(
                "combined_candidate_total",
                f"expected {EXPECTED_ORIGINAL_CANDIDATES}, got {combined_original_count}",
                "parts 1+2",
            )
        )

    canonical = _canonical_audit(
        proposal,
        catalog,
        equivalence,
        findings,
        source_names["catalog"],
        source_names["equivalence"],
    )
    inputs = {
        key: {"path": source_names[key], "sha256": _sha256(path)}
        for key, path in (
            ("proposal", proposal_path),
            ("part1", part1_path),
            ("part2", part2_path),
            ("catalog", catalog_path),
            ("equivalence", equivalence_path),
        )
    }
    inputs["closures"] = [
        {"path": source_name, "sha256": _sha256(path)}
        for path, source_name in zip(resolved_closure_paths, closure_source_names)
    ]
    allowed_inputs = [
        source_names["proposal"],
        source_names["part1"],
        source_names["part2"],
        source_names["catalog"],
        source_names["equivalence"],
        *closure_source_names,
    ]
    return {
        "schema_version": "1.0.0",
        "audit_boundary": {
            "allowed_inputs": allowed_inputs,
            "independent_evaluation_inputs_read": 0,
        },
        "verification_date": expected_date,
        "inputs": inputs,
        "proposal": {
            "domain_count": len(proposal),
            "domains": proposal_domains,
            "terminal_count": sum(len(item.terminal_ids) for item in proposal),
            "original_candidate_count": len(proposal_candidates),
            "unique_original_candidate_count": len(set(proposal_candidates)),
            "normalized_candidate_duplicate_count": len(proposal_candidate_duplicates),
            "candidate_distribution": {item.domain: len(item.candidate_urls) for item in proposal},
        },
        "part1": part1,
        "part2": part2,
        "combined": {
            "domain_count": len(combined_report_domains),
            "original_candidate_count": combined_original_count,
            "usable_count": part1["usable_count"] + part2["usable_count"],
        },
        "closures": {
            "document_count": len(closure_reports),
            "terminal_count": len(closure_terminal_ids),
            "unique_terminal_count": len(set(closure_terminal_ids)),
            "documents": closure_reports,
        },
        "canonical": canonical,
        "finding_count": len(findings),
        "findings": [finding.as_dict() for finding in findings],
        "passed": not findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, default=DEFAULT_PROPOSAL)
    parser.add_argument("--part1", type=Path, default=DEFAULT_PART1)
    parser.add_argument("--part2", type=Path, default=DEFAULT_PART2)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--equivalence", type=Path, default=DEFAULT_EQUIVALENCE)
    parser.add_argument("--expected-date", default=EXPECTED_DATE)
    parser.add_argument(
        "--closure",
        dest="closures",
        action="append",
        type=Path,
        help=f"closure report path; repeatable (default: auto-discover docs/{DEFAULT_CLOSURE_GLOB})",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()

    report = audit_source_verification(
        args.proposal,
        args.part1,
        args.part2,
        args.catalog,
        args.equivalence,
        expected_date=args.expected_date,
        closure_paths=args.closures,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 1 if args.gate and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
