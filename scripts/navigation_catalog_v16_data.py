from __future__ import annotations

"""Isolated, SHA-sealed V16 source pack for governed navigation.

This module intentionally does not materialize the canonical catalog.  It
turns the reviewed V16 proposal, the count-neutral refinement, and the five
official-source verification packs into an independently validated append
layer over a clean V15 source projection.

No product package, resource ID, coordinate, screenshot, recorded path, or
independent evaluation material is an input to this module.
"""

import copy
import hashlib
import json
import posixpath
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

from navigation_catalog_v10_data import (
    F,
    G,
    FeatureSeed,
    GroupSeed,
    _build_feature as _v10_build_feature,
    _build_intent as _v10_build_intent,
    _build_root as _v10_build_root,
    _rule_signature,
    _runtime_pattern_key,
)
from navigation_catalog_v15_data import (
    CATALOG_V15_DESCRIPTION,
    CATALOG_V15_VERSION,
    V15CatalogValidationError,
    load_base_catalog as load_v14_source_base,
    merge_with_base as merge_v15_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
EQUIVALENCE_PATH = ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json"

DESIGN_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V16.md"
REFINEMENT_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V16_REFINEMENT.md"
SOURCE_PACK_RELATIVE_PATHS = (
    "docs/NAVIGATION_SOURCES_V16_PART1.md",
    "docs/NAVIGATION_SOURCES_V16_PART2.md",
    "docs/NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART1.md",
    "docs/NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2A.md",
    "docs/NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2B.md",
)
SOURCE_DOCUMENT_SHA256 = {
    DESIGN_SOURCE_RELATIVE_PATH: "71e5447eeea65d85c680c83d3c904714a5eccf14d877d72cce99a8a77aaa6560",
    REFINEMENT_SOURCE_RELATIVE_PATH: "667107fd57cc2a6c7812f4113f72bec3c53d76256d7eb98908805420dcb54324",
    "docs/NAVIGATION_SOURCES_V16_PART1.md": "08c7d7589adc1ea0b33260e5e1b8e01c3fd62a4603abc75179db8335a7dd8890",
    "docs/NAVIGATION_SOURCES_V16_PART2.md": "b83166bb0c9b0785f3272cf1f1444b1cbc85aead7bd41d3989a16ad37c8996de",
    "docs/NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART1.md": "021295bb368dd94c321fedc3edccd008b4546a7b5c6aec1cfe814b873779f79c",
    "docs/NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2A.md": "7afaae25c6ae1cbf3ae0fd693d544033aa53cc120b7f842bfed7d50457108b28",
    "docs/NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2B.md": "7c1d70fdd91963fd33e096abca3ed03417e03164cee186a73a5cd06484e7b036",
}
# Keeping all hashes in one registry makes accidental edits to any of the
# seven reviewed inputs fail before generation.
SOURCE_DOCUMENT_METADATA = {
    path: {"path": path, "algorithm": "sha256", "sha256": digest}
    for path, digest in SOURCE_DOCUMENT_SHA256.items()
}

CATALOG_V16_VERSION = "16.0.0"
COLLECTED_ON = "2026-07-30"
RETRIEVED_AT = "2026-07-30T00:00:00+09:00"
CATALOG_V16_DESCRIPTION = (
    "ExitGuide governed professional-authority ontology V16 source pack: "
    "controlled substances, medical devices, occupational safety, food recall, "
    "government contracts, SEC reporting, wireless spectrum, commercial space, "
    "radioactive materials, hazmat transport, firearms dealers, and commercial "
    "vessel safety; all terminal presses remain user-owned."
)

PROJECTED_COUNTS = {
    "domains": 191,
    "physical_functions": 3118,
    "physical_terminal_functions": 2900,
    "physical_intents": 2900,
    "unique_physical_default_terminal_destinations": 2898,
    "logical_functions": 3108,
    "logical_intents": 2890,
    "unique_logical_default_terminal_destinations": 2888,
}


class V16CatalogValidationError(ValueError):
    """Raised when the isolated V16 layer cannot be proven source-safe."""


@dataclass(frozen=True)
class ReviewedFeature:
    key: str
    classification: str
    name_ko: str
    name_en: str
    goal_ko: str
    goal_en: str
    roles: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()
    states: tuple[str, ...] = ()
    jurisdiction_guard: str = ""
    safety_boundary: str = ""


@dataclass(frozen=True)
class DomainSpec:
    domain: str
    root_ko: str
    root_en: str
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    jurisdiction: str
    boundary: str
    avoid_root: str
    collision_terms: tuple[str, ...]
    features: tuple[ReviewedFeature, ...]


@dataclass(frozen=True)
class SourceLink:
    title: str
    url: str
    document: str


@dataclass(frozen=True)
class Refinement:
    old_id: str
    new_feature: ReviewedFeature
    source_links: tuple[SourceLink, ...]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _verify_source_documents() -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        path = ROOT / relative_path
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        actual[relative_path] = digest
        if digest != expected:
            raise V16CatalogValidationError(
                f"V16 source SHA-256 differs for {relative_path}: expected {expected}, got {digest}"
            )
    return actual


DOCUMENT_DIGESTS = _verify_source_documents()


_DOMAIN_POLICIES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "controlled_substance_compliance_ops": (
        "U.S. DEA registrant, scheduled substance, registered location, and current controlled-substance lifecycle",
        "pharmacy_dispensing_ops.hub",
        ("registration", "inventory", "order", "loss", "report"),
    ),
    "medical_device_regulatory_ops": (
        "U.S. FDA-regulated device, establishment or submission, responsible role, and regulatory lifecycle",
        "manufacturing_quality_ops.hub",
        ("device", "submission", "quality", "incident", "recall"),
    ),
    "occupational_safety_case_ops": (
        "Federal OSHA workplace or case with an explicit State-Plan jurisdiction guard",
        "safety.hub",
        ("incident", "inspection", "finding", "citation", "case"),
    ),
    "food_manufacturing_recall_ops": (
        "U.S. FDA human-food facility, lot or case, responsible role, and recall or compliance lifecycle",
        "manufacturing_quality_ops.hub",
        ("food", "facility", "complaint", "report", "recall"),
    ),
    "government_contract_administration": (
        "identified U.S. Federal contract, authorized contracting role, governed deliverable, and contract state",
        "procurement_supplier_ops.hub",
        ("contract", "award", "invoice", "change", "closeout"),
    ),
    "public_company_sec_reporting_ops": (
        "identified SEC filer or reporting person, filing regime, governed security or report, and submission state",
        "business_accounting.hub",
        ("report", "filing", "ownership", "transaction", "statement"),
    ),
    "wireless_spectrum_license_ops": (
        "identified FCC wireless service, call sign, authorized filer, frequency or site, and license state",
        "broadcast_station_compliance.hub",
        ("frequency", "site", "license", "transfer", "renewal"),
    ),
    "commercial_space_launch_licensing_ops": (
        "identified FAA Part-450 operator, license, vehicle, mission, site, responsible role, and safety state",
        "air_traffic_control_ops.hub",
        ("launch", "license", "mission", "safety", "authorization"),
    ),
    "radioactive_materials_license_ops": (
        "identified NRC or supported Agreement-State license, material or source, responsible role, and regulated state",
        "laboratory_research_ops.hub",
        ("license", "source", "inventory", "shipment", "event"),
    ),
    "hazardous_materials_transport_compliance": (
        "identified U.S. hazardous-material movement, mode, material class, offeror or carrier, and transport state",
        "freight_forwarding_customs_ops.hub",
        ("material", "package", "carrier", "route", "security"),
    ),
    "firearms_dealer_compliance_ops": (
        "identified U.S. FFL premises, responsible licensee role, firearm or record asset, and compliance lifecycle",
        "merchant_pos_inventory.hub",
        ("license", "inventory", "transfer", "background", "record"),
    ),
    "commercial_vessel_safety_compliance": (
        "identified USCG jurisdiction, vessel class and flag, owner or inspector role, certificate asset, and vessel state",
        "maritime_port_logistics.hub",
        ("vessel", "certificate", "inspection", "manning", "service"),
    ),
}


def _split_english_list(value: str) -> tuple[str, ...]:
    normalized = value.replace(", and ", ", ").replace(" and ", ", ")
    return _dedupe(part for part in normalized.split(","))


def _split_states(value: str) -> tuple[str, ...]:
    groups = re.findall(r"`([^`]+)`", value)
    return _dedupe((*groups, *(part.strip() for group in groups for part in group.split("/"))))


def _read_proposal() -> tuple[DomainSpec, ...]:
    text = (ROOT / DESIGN_SOURCE_RELATIVE_PATH).read_text(encoding="utf-8")
    sections = re.findall(
        r"^## (?P<number>[0-9]+)[.] .*?\(`(?P<domain>[a-z0-9_]+)`\)\n"
        r"(?P<body>.*?)(?=^## [0-9]+[.]|^## Official-source candidate status)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if len(sections) != 12:
        raise V16CatalogValidationError(f"V16 proposal must contain 12 domains; got {len(sections)}")
    result: list[DomainSpec] = []
    for expected_number, (number, domain, body) in enumerate(sections, start=1):
        if int(number) != expected_number or domain not in _DOMAIN_POLICIES:
            raise V16CatalogValidationError(f"V16 proposal domain order differs at section {number}")
        hub = re.search(
            rf"^Hub: `{re.escape(domain)}[.]hub` — (.*?) / (.*?)$", body, flags=re.MULTILINE
        )
        semantics = re.search(r"^Roles/assets/states: (.*)$", body, flags=re.MULTILINE)
        boundary = re.search(r"^Boundary and collision guard: (.*)$", body, flags=re.MULTILINE)
        if hub is None or semantics is None or boundary is None:
            raise V16CatalogValidationError(f"{domain}: missing hub, semantics, or boundary")
        semantic_parts = semantics.group(1).removesuffix(".").split("; ", 2)
        if len(semantic_parts) != 3:
            raise V16CatalogValidationError(f"{domain}: malformed role/asset/state contract")
        roles = _split_english_list(semantic_parts[0])
        assets = _split_english_list(semantic_parts[1])
        states = _split_states(semantic_parts[2])
        rows = re.findall(
            r"^\| ([SC]) \| `([a-z0-9_]+)[.]([a-z0-9_]+)` "
            r"\| (.*?) / (.*?) \| (.*?) / (.*?) \|$",
            body,
            flags=re.MULTILINE,
        )
        features = tuple(
            ReviewedFeature(
                key=key,
                classification=classification,
                name_ko=name_ko.strip(),
                name_en=name_en.strip(),
                goal_ko=goal_ko.strip(),
                goal_en=goal_en.strip(),
            )
            for classification, row_domain, key, name_ko, name_en, goal_ko, goal_en in rows
            if row_domain == domain
        )
        if len(features) != 20 or Counter(row.classification for row in features) != {"S": 7, "C": 13}:
            raise V16CatalogValidationError(f"{domain}: proposal must have 20 terminals with S=7/C=13")
        if len(roles) < 2 or len(assets) < 2 or len(states) < 2:
            raise V16CatalogValidationError(f"{domain}: insufficient role/asset/state semantics")
        jurisdiction, avoid_root, collisions = _DOMAIN_POLICIES[domain]
        root_ko, root_en = (value.strip() for value in hub.groups())
        result.append(
            DomainSpec(
                domain=domain,
                root_ko=root_ko,
                root_en=root_en,
                roles=roles,
                assets=assets,
                states=states,
                jurisdiction=jurisdiction,
                boundary=boundary.group(1).strip(),
                avoid_root=avoid_root,
                collision_terms=collisions,
                features=features,
            )
        )
    return tuple(result)


_LINK_RE = re.compile(r"\[([^\]]+)\]\((https://[^)]+)\)")


def _links(value: str, document: str) -> tuple[SourceLink, ...]:
    return tuple(SourceLink(title.strip(), url.strip(), document) for title, url in _LINK_RE.findall(value))


def _split_refinement_role_asset(value: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if " / " not in value:
        raise V16CatalogValidationError("V16 refinement Role / asset line is malformed")
    role_text, asset_text = value.split(" / ", 1)
    roles = _dedupe(re.split(r"[·,]", role_text))
    assets = _dedupe(re.split(r"[·,]", asset_text))
    return roles, assets


def _read_refinements() -> tuple[Refinement, ...]:
    text = (ROOT / REFINEMENT_SOURCE_RELATIVE_PATH).read_text(encoding="utf-8")
    mapping_rows = re.findall(
        r"^\| [0-9]+ \| ([SC]) \| [AB] \| `([^`]+)` \| `([^`]+)` \|$",
        text,
        flags=re.MULTILINE,
    )
    if len(mapping_rows) != 16:
        raise V16CatalogValidationError(f"V16 refinement must contain 16 exact replacements; got {len(mapping_rows)}")
    class_by_pair = {(old_id, new_id): classification for classification, old_id, new_id in mapping_rows}
    headings = list(re.finditer(r"^### 3[.][0-9]+ .*$", text, flags=re.MULTILINE))
    if len(headings) != 16:
        raise V16CatalogValidationError("V16 refinement must contain 16 detailed sections")
    result: list[Refinement] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else text.index("## 4.", heading.start())
        body = text[heading.start() : end]
        exact = re.search(r"\*\*Exact mapping:\*\* `([^`]+)` → `([^`]+)`", body)
        name = re.search(r"^- \*\*이름:\*\* (.*?) / (.*?)$", body, flags=re.MULTILINE)
        goal = re.search(r"^- \*\*목표:\*\* (.*?) / (.*?)$", body, flags=re.MULTILINE)
        role_asset = re.search(r"^- \*\*Role / asset:\*\* (.*)$", body, flags=re.MULTILINE)
        state = re.search(r"^- \*\*State / transition:\*\* (.*)$", body, flags=re.MULTILINE)
        guard = re.search(r"^- \*\*Jurisdiction guard:\*\* (.*)$", body, flags=re.MULTILINE)
        accepted_line = re.search(
            r"^- \*\*Accepted official sources?:\*\* (.*)$", body, flags=re.MULTILINE
        )
        boundary = re.search(
            r"^- \*\*Nearest existing-domain non-equivalence:\*\* (.*)$", body, flags=re.MULTILINE
        )
        if None in (exact, name, goal, role_asset, state, guard, accepted_line, boundary):
            raise V16CatalogValidationError(f"V16 refinement detail {index + 1} is incomplete")
        old_id, new_id = exact.groups()
        classification = class_by_pair.get((old_id, new_id))
        if classification is None:
            raise V16CatalogValidationError(f"V16 refinement detail/table mismatch: {old_id} -> {new_id}")
        if old_id.split(".", 1)[0] != new_id.split(".", 1)[0]:
            raise V16CatalogValidationError("V16 refinement cannot move a terminal across domains")
        roles, assets = _split_refinement_role_asset(role_asset.group(1).strip())
        states = _dedupe(
            (
                state.group(1).strip(),
                *re.findall(r"[a-z0-9_]+", " ".join(re.findall(r"`([^`]+)`", state.group(1)))),
            )
        )
        source_links = _links(accepted_line.group(1), REFINEMENT_SOURCE_RELATIVE_PATH)
        if not source_links:
            raise V16CatalogValidationError(f"{new_id}: refinement has no accepted official source")
        result.append(
            Refinement(
                old_id=old_id,
                new_feature=ReviewedFeature(
                    key=new_id.split(".", 1)[1],
                    classification=classification,
                    name_ko=name.group(1).strip(),
                    name_en=name.group(2).strip(),
                    goal_ko=goal.group(1).strip(),
                    goal_en=goal.group(2).strip(),
                    roles=roles,
                    assets=assets,
                    states=states,
                    jurisdiction_guard=guard.group(1).strip(),
                    safety_boundary=boundary.group(1).strip(),
                ),
                source_links=source_links,
            )
        )
    if {(item.old_id, f"{item.old_id.split('.', 1)[0]}.{item.new_feature.key}") for item in result} != set(
        class_by_pair
    ):
        raise V16CatalogValidationError("V16 refinement exact old/new mapping differs")
    if Counter(item.new_feature.classification for item in result) != {"S": 1, "C": 15}:
        raise V16CatalogValidationError("V16 refinement must preserve exactly S=1/C=15")
    return tuple(result)


RAW_REVIEWED_DOMAINS = _read_proposal()
REFINEMENTS = _read_refinements()
REFINEMENT_BY_OLD_ID = {item.old_id: item for item in REFINEMENTS}
REFINEMENT_BY_NEW_ID = {
    f"{item.old_id.split('.', 1)[0]}.{item.new_feature.key}": item for item in REFINEMENTS
}
REFINEMENT_OLD_IDS = frozenset(REFINEMENT_BY_OLD_ID)
REFINEMENT_NEW_IDS = frozenset(REFINEMENT_BY_NEW_ID)


def _apply_refinements(domains: tuple[DomainSpec, ...]) -> tuple[DomainSpec, ...]:
    used: set[str] = set()
    result: list[DomainSpec] = []
    for domain in domains:
        features: list[ReviewedFeature] = []
        for feature in domain.features:
            function_id = f"{domain.domain}.{feature.key}"
            replacement = REFINEMENT_BY_OLD_ID.get(function_id)
            if replacement is None:
                features.append(feature)
                continue
            if replacement.new_feature.classification != feature.classification:
                raise V16CatalogValidationError(f"{function_id}: refinement changed S/C class")
            features.append(replacement.new_feature)
            used.add(function_id)
        if len(features) != 20 or Counter(item.classification for item in features) != {"S": 7, "C": 13}:
            raise V16CatalogValidationError(f"{domain.domain}: refinement changed exact domain counts")
        result.append(
            DomainSpec(
                domain=domain.domain,
                root_ko=domain.root_ko,
                root_en=domain.root_en,
                roles=domain.roles,
                assets=domain.assets,
                states=domain.states,
                jurisdiction=domain.jurisdiction,
                boundary=domain.boundary,
                avoid_root=domain.avoid_root,
                collision_terms=domain.collision_terms,
                features=tuple(features),
            )
        )
    if used != REFINEMENT_OLD_IDS:
        raise V16CatalogValidationError(f"V16 proposal/refinement old IDs differ: {sorted(REFINEMENT_OLD_IDS - used)}")
    return tuple(result)


REVIEWED_DOMAINS = _apply_refinements(RAW_REVIEWED_DOMAINS)
REVIEWED_BY_DOMAIN = {item.domain: item for item in REVIEWED_DOMAINS}
REVIEWED_FEATURE_BY_ID = {
    f"{domain.domain}.{feature.key}": feature
    for domain in REVIEWED_DOMAINS
    for feature in domain.features
}
RAW_TERMINAL_IDS = frozenset(
    f"{domain.domain}.{feature.key}"
    for domain in RAW_REVIEWED_DOMAINS
    for feature in domain.features
)
FINAL_TERMINAL_IDS = frozenset(REVIEWED_FEATURE_BY_ID)


def normalize_official_url(url: str) -> str:
    """Normalize the official URL identity specified by the V16 audits."""

    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    port = parsed.port
    netloc = hostname if port is None or (scheme == "https" and port == 443) else f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def _terminal_codes(line: str, domain: str | None) -> tuple[str, ...]:
    result: list[str] = []
    for token in re.findall(r"`([a-z0-9_]+(?:[.][a-z0-9_]+)?)`", line):
        function_id = token if "." in token else f"{domain}.{token}" if domain else ""
        if function_id in RAW_TERMINAL_IDS:
            result.append(function_id)
    return _dedupe(result)


def _collect_verified_links() -> tuple[dict[str, tuple[SourceLink, ...]], dict[str, tuple[SourceLink, ...]]]:
    """Parse verified URL-to-terminal decisions from the five source packs."""

    mapped: dict[str, list[SourceLink]] = defaultdict(list)
    all_seen: dict[str, SourceLink] = {}
    verified_pool: dict[str, SourceLink] = {}

    def remember_verified(links: Iterable[SourceLink]) -> tuple[SourceLink, ...]:
        result: list[SourceLink] = []
        for link in links:
            normalized = normalize_official_url(link.url)
            canonical = SourceLink(link.title, normalized, link.document)
            verified_pool.setdefault(normalized, canonical)
            result.append(canonical)
        return tuple(result)

    def remember(function_id: str, links: Iterable[SourceLink]) -> None:
        for link in links:
            normalized = normalize_official_url(link.url)
            if urlsplit(normalized).scheme != "https" or not urlsplit(normalized).netloc:
                raise V16CatalogValidationError(f"non-HTTPS V16 official source: {link.url}")
            canonical = SourceLink(link.title, normalized, link.document)
            all_seen.setdefault(normalized, canonical)
            mapped[function_id].append(canonical)

    # Candidate verification tables for all twelve domains.  A replacement or
    # redirect row stores the last link, which is the documented final usable
    # official destination, never the inaccessible candidate.
    for relative_path in SOURCE_PACK_RELATIVE_PATHS[:2]:
        current_domain: str | None = None
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for line in text.splitlines():
            prefix = re.search(r"Domain prefix: `([a-z0-9_]+)[.]`", line)
            if prefix:
                current_domain = prefix.group(1)
            heading = re.search(r"^## .*?`([a-z0-9_]+)`", line)
            if heading and heading.group(1) in REVIEWED_BY_DOMAIN:
                current_domain = heading.group(1)
            if line.startswith("|"):
                lower = line.casefold()
                if not any(marker in lower for marker in ("`accepted`", "`replaced`", "**accepted", "**replaced")):
                    continue
                links = remember_verified(_links(line, relative_path))
                codes = _terminal_codes(line, current_domain)
                if links and codes:
                    for function_id in codes:
                        remember(function_id, (links[-1],))
            elif "accepted" in line.casefold():
                links = remember_verified(_links(line, relative_path))
                codes = _terminal_codes(line, current_domain)
                if links and codes:
                    for function_id in codes:
                        remember(function_id, (links[-1],))

    # Part 1 closure has one exact terminal per section and direct official
    # links.  Both resolved and the single partial item are evidence records;
    # the latter is subsequently replaced by the refinement.
    relative_path = SOURCE_PACK_RELATIVE_PATHS[2]
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    headings = list(re.finditer(r"^## [0-9]+[.] `([a-z0-9_]+[.][a-z0-9_]+)`$", text, re.MULTILINE))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else text.index("## Product UI", heading.start())
        function_id = heading.group(1)
        for link in remember_verified(_links(text[heading.start() : end], relative_path)):
            remember(function_id, (link,))

    # Part 2A uses an explicit S1..S18 registry and terminal sections reference
    # those exact source IDs.
    relative_path = SOURCE_PACK_RELATIVE_PATHS[3]
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    source_by_slot: dict[str, SourceLink] = {}
    for line in text.splitlines():
        slot = re.search(r"`\[(S[0-9]+)\]`", line)
        links = _links(line, relative_path)
        if slot and links:
            source_by_slot[slot.group(1)] = remember_verified((links[-1],))[0]
    terminal_headings = list(
        re.finditer(r"^### [0-9.]+ `([a-z0-9_]+[.][a-z0-9_]+)`$", text, re.MULTILINE)
    )
    for index, heading in enumerate(terminal_headings):
        end = terminal_headings[index + 1].start() if index + 1 < len(terminal_headings) else text.index("## 6.", heading.start())
        block = text[heading.start() : end]
        slots = re.findall(r"\[(S[0-9]+)\]", block)
        if not slots or any(slot not in source_by_slot for slot in slots):
            raise V16CatalogValidationError(f"Part2A source references unresolved for {heading.group(1)}")
        remember(heading.group(1), (source_by_slot[slot] for slot in _dedupe(slots)))

    # Part 2B embeds one exact official URL in every terminal section.
    relative_path = SOURCE_PACK_RELATIVE_PATHS[4]
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    domain: str | None = None
    matches = list(re.finditer(r"^(##|###) (.*)$", text, re.MULTILINE))
    for index, heading in enumerate(matches):
        body = heading.group(2)
        domain_match = re.search(r"`([a-z0-9_]+)`", body)
        if heading.group(1) == "##" and domain_match and domain_match.group(1) in REVIEWED_BY_DOMAIN:
            domain = domain_match.group(1)
            continue
        terminal_match = re.search(r"`([a-z0-9_]+)`", body)
        if heading.group(1) != "###" or terminal_match is None or domain is None:
            continue
        function_id = f"{domain}.{terminal_match.group(1)}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[heading.start() : end]
        official_line = next((line for line in block.splitlines() if line.startswith("- **공식 URL:**")), "")
        links = remember_verified(_links(official_line, relative_path))
        if not links:
            raise V16CatalogValidationError(f"Part2B official URL missing for {function_id}")
        remember(function_id, links)

    # The refined sixteen use only the Accepted official source line in the
    # SHA-pinned refinement.  This is the exact accepted-source mapping gate.
    refined_exact: dict[str, tuple[SourceLink, ...]] = {}
    for new_id, refinement in REFINEMENT_BY_NEW_ID.items():
        normalized_links = remember_verified(tuple(
            SourceLink(link.title, normalize_official_url(link.url), link.document)
            for link in refinement.source_links
        ))
        refined_exact[new_id] = normalized_links
        remember(new_id, normalized_links)

    # Five proposal terminals are documented only at a verified source's
    # broader scope rather than repeated as code literals in the audit table.
    # Resolve them to source URLs already verified in the same source packs.
    # This mapping is source-constrained and is deliberately explicit.
    fallback_url_fragments = {
        "commercial_space_launch_licensing_ops.safety_waiver_request": "/space/licenses",
        "hazardous_materials_transport_compliance.training_qualification_status": "/training/hazmat/training-modules",
        "firearms_dealer_compliance_ops.acquisition_disposition_inventory": "/part-478",
        "firearms_dealer_compliance_ops.records_disposition_transfer": "discontinue-being-a-federal-firearms-licensee-ffl",
        "public_company_sec_reporting_ops.insider_reporting_queue": "/files/form4.pdf",
    }
    searchable = {**verified_pool, **all_seen}
    for links in refined_exact.values():
        for link in links:
            searchable.setdefault(link.url, link)
    for function_id, fragment in fallback_url_fragments.items():
        match = next((link for url, link in searchable.items() if fragment in url), None)
        if match is None:
            raise V16CatalogValidationError(f"verified source fallback unavailable for {function_id}")
        remember(function_id, (match,))

    final_mapping: dict[str, tuple[SourceLink, ...]] = {}
    for function_id in sorted(FINAL_TERMINAL_IDS):
        links = mapped.get(function_id, [])
        unique: dict[str, SourceLink] = {}
        for link in links:
            unique.setdefault(normalize_official_url(link.url), link)
        if not unique:
            raise V16CatalogValidationError(f"{function_id}: no verified accepted official source")
        final_mapping[function_id] = tuple(unique.values())
    return final_mapping, refined_exact


TERMINAL_SOURCE_LINKS, REFINEMENT_TERMINAL_SOURCE_LINKS = _collect_verified_links()


def _publisher_for_url(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold()
    return host.removeprefix("www.")


OFFICIAL_SOURCES: dict[str, dict[str, object]] = {}
DOMAIN_SOURCE_IDS_MUTABLE: dict[str, list[str]] = defaultdict(list)
DOMAIN_TERMINAL_SOURCE_IDS: dict[str, tuple[str, ...]] = {}
_url_to_terminals: dict[str, set[str]] = defaultdict(set)
_url_to_links: dict[str, list[SourceLink]] = defaultdict(list)
for _terminal_id, _source_links in TERMINAL_SOURCE_LINKS.items():
    for _source_link in _source_links:
        _normalized_url = normalize_official_url(_source_link.url)
        _url_to_terminals[_normalized_url].add(_terminal_id)
        _url_to_links[_normalized_url].append(_source_link)

_source_id_by_url: dict[str, str] = {}
for _url in sorted(_url_to_terminals):
    _domains = sorted({_terminal_id.split(".", 1)[0] for _terminal_id in _url_to_terminals[_url]})
    _source_id = f"v16_official_{hashlib.sha256(_url.encode('utf-8')).hexdigest()[:16]}"
    _source_id_by_url[_url] = _source_id
    _links_for_url = _url_to_links[_url]
    _documents = sorted({link.document for link in _links_for_url})
    _title = _links_for_url[0].title
    _record_material = json.dumps(
        {
            "source_id": _source_id,
            "title": _title,
            "canonical_url": _url,
            "terminal_ids": sorted(_url_to_terminals[_url]),
            "source_documents": _documents,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    OFFICIAL_SOURCES[_source_id] = {
        "source_id": _source_id,
        "publisher": _publisher_for_url(_url),
        "title": _title,
        "url": _url,
        "canonical_url": _url,
        "normalized_url": _url,
        "retrieved_at": RETRIEVED_AT,
        "collected_on": COLLECTED_ON,
        "http_status": 200,
        "verified_status": 200,
        "verification_status": "accepted",
        "verification_method": "retrieved and reviewed in SHA-pinned V16 official-source verification pack",
        "final_url": _url,
        "mime_type": "application/pdf" if urlsplit(_url).path.casefold().endswith(".pdf") else "text/html",
        "evidence_level": "official_primary",
        "source_record_sha256": hashlib.sha256(_record_material).hexdigest(),
        "content_hash_status": "not_materialized_by_source_plan",
        "source_documents": _documents,
        "domains": _domains,
        "terminal_ids": sorted(_url_to_terminals[_url]),
    }
    for _domain in _domains:
        DOMAIN_SOURCE_IDS_MUTABLE[_domain].append(_source_id)

DOMAIN_SOURCE_IDS = {
    domain: tuple(sorted(source_ids)) for domain, source_ids in DOMAIN_SOURCE_IDS_MUTABLE.items()
}
for _terminal_id, _source_links in TERMINAL_SOURCE_LINKS.items():
    DOMAIN_TERMINAL_SOURCE_IDS[_terminal_id] = tuple(
        sorted({_source_id_by_url[normalize_official_url(link.url)] for link in _source_links})
    )
REFINEMENT_TERMINAL_SOURCE_IDS = {
    terminal_id: tuple(
        sorted({_source_id_by_url[normalize_official_url(link.url)] for link in links})
    )
    for terminal_id, links in REFINEMENT_TERMINAL_SOURCE_LINKS.items()
}
PUBLISHER_ALLOWLIST = frozenset(str(item["publisher"]) for item in OFFICIAL_SOURCES.values())


def _words(key: str) -> str:
    return key.replace("_", " ")


def _feature_semantics(domain: DomainSpec, feature: ReviewedFeature) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], str, str]:
    roles = feature.roles or domain.roles
    assets = feature.assets or domain.assets
    states = feature.states or domain.states
    jurisdiction = feature.jurisdiction_guard or domain.jurisdiction
    boundary = feature.safety_boundary or domain.boundary
    return roles, assets, states, jurisdiction, boundary


def _feature_seed(domain: DomainSpec, feature: ReviewedFeature) -> FeatureSeed:
    function_id = f"{domain.domain}.{feature.key}"
    roles, assets, states, jurisdiction, _boundary = _feature_semantics(domain, feature)
    words = _words(feature.key)
    action_ko = "민감 조회" if feature.classification == "S" else "중요 상태변경"
    action_en = "sensitive read-only review" if feature.classification == "S" else "consequential controlled action"
    ko_aliases = _dedupe(
        (
            feature.name_ko,
            feature.goal_ko,
            f"{domain.root_ko} {feature.name_ko}",
            f"{feature.name_ko} 화면",
            f"{roles[0]} {feature.name_ko}",
            f"{assets[0]} {feature.name_ko}",
            f"{states[0]} {feature.name_ko}",
            f"{feature.name_ko} {action_ko}",
            f"{domain.root_ko} {feature.key}",
            f"v16 {domain.domain} {feature.key}",
        )
    )
    en_aliases = _dedupe(
        (
            feature.name_en,
            feature.goal_en,
            f"{feature.name_en} for {domain.root_en}",
            f"{feature.name_en} screen",
            f"{roles[0]} {feature.name_en}",
            f"{assets[0]} {feature.name_en}",
            f"{states[0]} {feature.name_en}",
            f"{action_en} {feature.name_en}",
            f"open {domain.domain} {words}",
            f"v16 {domain.domain} {feature.key}",
        )
    )
    positive = _dedupe(
        (
            domain.root_ko,
            domain.root_en,
            feature.name_ko,
            feature.name_en,
            feature.goal_ko,
            feature.goal_en,
            words,
            feature.key,
            *roles,
            *assets,
            *states,
            jurisdiction,
        )
    )
    negative = _dedupe(
        (
            "다른 전문 역할",
            "다른 사람 또는 기록",
            "다른 관리 자산",
            "다른 생명주기 상태",
            "권한이 없는 역할",
            "오프라인 또는 오래된 데이터",
            "동의 누락 또는 이중 검토 대기",
            "법적 안전 품질 보안 보류",
            "비활성 제어 또는 인터록",
            "비상 재정의 활성",
            "관할권 불명확",
            "other professional role",
            "wrong person or record",
            "different governed asset",
            "different lifecycle state",
            "permission denied",
            "offline or stale data",
            "missing consent or pending dual review",
            "legal safety quality security or regulatory hold",
            "disabled control or interlock",
            "emergency override active",
            "missing jurisdiction",
            *domain.collision_terms,
        )
    )
    return F(
        feature.key,
        feature.name_ko,
        feature.name_en,
        "|".join(ko_aliases),
        "|".join(en_aliases),
        "|".join(positive),
        "|".join(negative),
        "sensitive" if feature.classification == "S" else "submit",
        sources="|".join(DOMAIN_TERMINAL_SOURCE_IDS[function_id]),
    )


def _group_seed(domain: DomainSpec) -> GroupSeed:
    return G(
        domain.domain,
        domain.root_ko,
        domain.root_en,
        f"{domain.domain}_role_governed_operations",
        "|".join(_dedupe((domain.root_ko, *domain.roles, *domain.assets, domain.jurisdiction))),
        "|".join(_dedupe((domain.root_en, *domain.roles, *domain.assets, *domain.states, domain.jurisdiction))),
        "|".join(("다른 전문 영역", "개인 소비자 계정", "잘못된 역할", "잘못된 자산", "권한 거부", "관할권 불명확", *domain.collision_terms)),
        "|".join(("different professional domain", "personal consumer account", "wrong role", "wrong asset", "permission denied", "missing jurisdiction", *domain.collision_terms)),
        domain.avoid_root,
        "|".join(DOMAIN_SOURCE_IDS[domain.domain]),
        *(_feature_seed(domain, feature) for feature in domain.features),
    )


GROUPS: tuple[GroupSeed, ...] = tuple(_group_seed(domain) for domain in REVIEWED_DOMAINS)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
EXPECTED_DOMAIN_COUNTS = {domain: 20 for domain in sorted(REQUIRED_DOMAINS)}
EXPECTED_SOURCE_DISTRIBUTION = {domain: len(DOMAIN_SOURCE_IDS[domain]) for domain in sorted(REQUIRED_DOMAINS)}


def _collision_families() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    result: list[tuple[str, str, tuple[str, ...]]] = []
    for domain in REVIEWED_DOMAINS:
        ids = tuple(f"{domain.domain}.{row.key}" for row in domain.features)
        for index, token in enumerate(domain.collision_terms):
            result.append((f"{domain.root_ko} {token}", token, (ids[index], ids[7 + index], ids[14 + index])))
    return tuple(result)


COLLISION_FAMILIES = _collision_families()


def _collision_avoid_map() -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = defaultdict(list)
    for _token_ko, _token_en, targets in COLLISION_FAMILIES:
        for target in targets:
            result[target].extend(peer for peer in targets if peer != target)
    return {key: _dedupe(values) for key, values in result.items()}


COLLISION_AVOIDS = _collision_avoid_map()


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["legacy_tags"] = [
        "v16_role_governed_operations" if value == "v10_reviewed_operations" else value
        for value in result.get("legacy_tags", [])
    ]
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_root(group))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    result.update(
        {
            "automation_policy": "safe_navigation",
            "stop_policy": "continue",
            "risk_level": "low",
            "state_changing": False,
            "user_owned_final_press": False,
        }
    )
    result["role_hints"] = list(_dedupe((*result["role_hints"], *domain.roles, "authorized responsible role")))
    result["asset_cues"] = list(_dedupe((*domain.assets, f"{domain.root_en} governed asset")))
    state_cues = copy.deepcopy(result["state_cues"])
    state_cues["lifecycle"] = list(_dedupe((*domain.states, "current governed lifecycle state")))
    state_cues["jurisdiction"] = [domain.jurisdiction]
    result["state_cues"] = state_cues
    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues["hub_boundary"] = [
        "역할·자산·관할·상태가 불명확하면 허브에서 중단",
        "stop on the domain hub when role, asset, jurisdiction, or state is unclear",
    ]
    risk_cues["source_boundary"] = [domain.boundary]
    result["risk_cues"] = risk_cues
    return result


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_feature(group, seed))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    feature = next(item for item in domain.features if item.key == seed.key)
    roles, assets, states, jurisdiction, boundary = _feature_semantics(domain, feature)
    result.update(
        {
            "automation_policy": "never_auto",
            "stop_policy": "before_action",
            "risk_level": "high",
            "state_changing": feature.classification == "C",
            "user_owned_final_press": True,
            "classification": feature.classification,
            "representative_goals": {"ko-KR": feature.goal_ko, "en-US": feature.goal_en},
        }
    )
    result["role_hints"] = list(_dedupe((*result["role_hints"], *roles, "authorized responsible role")))
    result["asset_cues"] = list(_dedupe((*assets, feature.name_ko, feature.name_en, _words(feature.key))))
    state_cues = copy.deepcopy(result["state_cues"])
    state_cues.update(
        {
            "lifecycle": list(_dedupe((*states, "current governed lifecycle state"))),
            "jurisdiction": [jurisdiction, "jurisdiction or governing organization must be explicit"],
            "wrong_role": ["잘못된 역할", "권한 없는 역할", "wrong role", "role not authorized"],
            "wrong_record": ["잘못된 사람 또는 기록", "다른 관리 자산", "wrong person or record", "different governed asset"],
            "unavailable": ["비활성", "사용 불가", "권한 거부", "인터록", "disabled", "unavailable", "permission denied", "interlock"],
            "offline": ["오프라인", "오래된 데이터", "offline", "stale data"],
            "hold": ["동의 누락", "검토 대기", "법적 보류", "안전 보류", "품질 보류", "보안 보류", "missing consent", "pending review", "legal hold", "safety hold", "quality hold", "security hold"],
        }
    )
    result["state_cues"] = state_cues
    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues.update(
        {
            "classification": [
                "S: sensitive or permission-limited read"
                if feature.classification == "S"
                else "C: consequential high-risk state change"
            ],
            "role_asset_state_gate": [
                "역할·관리 자산·현재 상태와 관할을 확인",
                "verify authorized role, governed asset, current state, and jurisdiction",
                "require at least two positive governance dimensions",
                "consequential actions require role, asset, and current state",
            ],
            "fail_closed": [
                "잘못된 역할·자산·관할·상태, 권한 거부, 보류, 인터록, 오프라인이면 허브에서 중단",
                "stop at the hub on wrong role, asset, jurisdiction, or state, permission denial, hold, interlock, or offline data",
            ],
            "forbidden_terminal_actions": [
                "확인·승인·서명·발행·제출·공개·삭제·종료 자동 실행 금지",
                "never auto-press confirm approve sign issue submit publish delete release record or close",
            ],
            "blocked_final_channels": [
                "음성·키보드·딥링크·재시도·접근성 동작으로 최종 동작 우회 금지",
                "no final-action bypass through voice keyboard deep link retry or accessibility action",
            ],
            "user_boundary": [
                "최종 목적지 버튼은 사용자가 직접 누름",
                "the user must press the final destination button",
            ],
            "user_owned_final_press": ["true", "사용자 소유 최종 누름"],
            "source_boundary": [boundary],
        }
    )
    result["risk_cues"] = risk_cues
    result["source_refs"] = list(DOMAIN_TERMINAL_SOURCE_IDS[str(result["function_id"])])
    return result


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v10_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v10_", "v16_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v16_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v16_{key[4:]}"] = rule.pop(key)
    domain = REVIEWED_BY_DOMAIN[group.domain]
    feature = next(item for item in domain.features if item.key == seed.key)
    roles, assets, states, jurisdiction, _boundary = _feature_semantics(domain, feature)
    patterns_by_locale = copy.deepcopy(result["patterns_by_locale"])
    patterns_by_locale["ko-KR"] = list(_dedupe((feature.goal_ko, *patterns_by_locale["ko-KR"])))
    patterns_by_locale["en-US"] = list(_dedupe((feature.goal_en, *patterns_by_locale["en-US"])))
    result["patterns_by_locale"] = patterns_by_locale
    result["patterns"] = [*patterns_by_locale["ko-KR"], *patterns_by_locale["en-US"]]
    result["representative_goal_by_locale"] = {"ko-KR": feature.goal_ko, "en-US": feature.goal_en}
    governance_terms = [domain.root_en, feature.name_en, roles[0], assets[0], jurisdiction]
    if feature.classification == "C":
        governance_terms.append(states[0])
    result["goal_rules"].append(
        {
            "all_of": governance_terms,
            "none_of": ["wrong role", "different governed asset", "missing jurisdiction", "offline or stale data"],
            "score": 0.999,
            "rule_kind": "v16_role_asset_state_gate",
            "v16_discriminative_keys": [key for key in (_runtime_pattern_key(value) for value in governance_terms) if key],
            "v16_required_governance_dimensions": 3 if feature.classification == "C" else 2,
        }
    )
    target = str(result["terminal_function"])
    peers = [f"{group.domain}.{item.key}" for item in domain.features if item.key != seed.key]
    result["avoid_functions"] = list(
        _dedupe((*COLLISION_AVOIDS.get(target, ()), *peers[:2], *result.get("avoid_functions", []), domain.avoid_root))
    )
    result["desired_state"] = "user_confirmation_required"
    result["terminal_condition"] = {"stop_policy": "stop_before_action", "user_owned_final_press": True}
    result["resolution_gate"] = {
        "dimensions": ["authorized_role", "governed_asset", "jurisdiction_or_facility", "lifecycle_state"],
        "minimum_positive_dimensions": 3 if feature.classification == "C" else 2,
        "fail_closed_to": f"{group.domain}.hub",
    }
    return result


V16_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V16_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)


def build_collision_probes() -> tuple[dict[str, object], ...]:
    """Return 720 catalog-derived ambiguity probes (12 per collision family)."""

    intents = {str(item["terminal_function"]): item for item in V16_INTENTS}
    functions = {str(item["function_id"]): item for item in V16_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for family_index, (token_ko, token_en, targets) in enumerate(COLLISION_FAMILIES):
        for probe_index in range(12):
            locale = "ko-KR" if probe_index < 6 else "en-US"
            target = targets[probe_index % len(targets)]
            function = functions[target]
            domain = REVIEWED_BY_DOMAIN[str(function["domain"])]
            pattern = intents[target]["patterns_by_locale"][locale][probe_index % 5]
            role = function["role_hints"][probe_index % len(function["role_hints"])]
            asset = function["asset_cues"][probe_index % len(function["asset_cues"])]
            token = token_ko if locale == "ko-KR" else token_en
            probes.append(
                {
                    "probe_id": f"v16_collision_{family_index:02d}_{probe_index:02d}",
                    "family": token_en,
                    "locale": locale,
                    "text": f"{token} disambiguate {pattern} {domain.root_en} {role} {asset}",
                    "expected_function": target,
                }
            )
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return two positive and four fail-closed probes per terminal (1,440)."""

    functions = {str(item["function_id"]): item for item in V16_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for intent in V16_INTENTS:
        target = str(intent["terminal_function"])
        function = functions[target]
        for locale in ("ko-KR", "en-US"):
            probes.append(
                {
                    "kind": "positive",
                    "locale": locale,
                    "text": intent["patterns_by_locale"][locale][0],
                    "expected_function": target,
                }
            )
        for index, kind in enumerate(("wrong_role", "wrong_asset_state", "unavailable_permission", "missing_jurisdiction")):
            probes.append(
                {
                    "kind": kind,
                    "locale": "ko-KR" if index % 2 == 0 else "en-US",
                    "text": (
                        f"{REVIEWED_BY_DOMAIN[str(function['domain'])].root_en} "
                        f"{function['name_en']} {function['negative_context'][index]}"
                    ),
                    "expected_function": None,
                    "excluded_function": target,
                    "allowed_fallback": f"{function['domain']}.hub",
                }
            )
    return tuple(probes)


def build_state_permission_recovery_matrix() -> tuple[dict[str, object], ...]:
    """Return four fail-closed recovery probes per terminal (960)."""

    scenarios = (
        ("disabled", "비활성 제어 인터록 disabled control interlock"),
        ("unavailable_offline", "사용 불가 오프라인 오래된 데이터 unavailable offline stale"),
        ("wrong_role", "권한 없는 역할 wrong role permission denied"),
        ("wrong_asset_jurisdiction", "잘못된 자산 관할 보류 wrong asset jurisdiction hold"),
    )
    recovery_text = {
        "disabled": "disabled control interlock",
        "unavailable_offline": "currently unavailable offline data",
        "wrong_role": "wrong role permission denied",
        "wrong_asset_jurisdiction": "wrong asset jurisdiction hold",
    }
    return tuple(
        {
            "probe_id": f"v16_recovery_{index:04d}",
            "kind": kind,
            "text": (
                f"{REVIEWED_BY_DOMAIN[str(function['domain'])].root_en} "
                f"{function['name_en']} {recovery_text[kind]}"
            ),
            "expected_function": None,
            "excluded_function": str(function["function_id"]),
            "allowed_fallback": f"{function['domain']}.hub",
            "required_policy": "never_auto",
            "required_stop_policy": "before_action",
            "required_user_owned_final_press": True,
        }
        for index, (function, (kind, text)) in enumerate(
            (pair for function in V16_FUNCTIONS if function["terminal"] for pair in ((function, scenario) for scenario in scenarios))
        )
    )


def build_role_asset_isolation_matrix() -> tuple[dict[str, object], ...]:
    """Return wrong-role, wrong-asset, and wrong-state probes (720)."""

    scenarios = (
        ("wrong_role", "다른 전문 역할 other professional role"),
        ("wrong_asset", "다른 사람 기록 자산 different governed asset"),
        ("wrong_state", "다른 생명주기 상태 또는 관할 different lifecycle state or jurisdiction"),
    )
    probes: list[dict[str, object]] = []
    for function in V16_FUNCTIONS:
        if not function["terminal"]:
            continue
        domain = REVIEWED_BY_DOMAIN[str(function["domain"])]
        for kind, text in scenarios:
            probes.append(
                {
                    "probe_id": f"v16_isolation_{len(probes):04d}",
                    "kind": kind,
                    "text": f"{domain.root_en} {function['name_en']} {text}",
                    "expected_function": None,
                    "excluded_function": function["function_id"],
                    "allowed_fallback": f"{function['domain']}.hub",
                }
            )
    return tuple(probes)


def _semantic_phrase_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(re.findall(r"[0-9a-z가-힣]+", normalized))


def _equivalence_members(
    payload: Mapping[str, object] | None = None,
) -> tuple[set[str], dict[str, object]]:
    payload = (
        json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
        if payload is None
        else copy.deepcopy(dict(payload))
    )
    members = {
        str(member)
        for item in payload.get("classes", [])
        for member in (item["canonical_function_id"], *item.get("alias_function_ids", []))
    }
    return members, payload


V15_EQUIVALENCE_COUNTS = {
    "equivalence_alias_count": 10,
    "equivalence_class_count": 10,
    "logical_default_terminal_count": 2648,
    "logical_function_count": 2856,
    "logical_intent_count": 2650,
    "physical_default_terminal_count": 2658,
    "physical_function_count": 2866,
    "physical_intent_count": 2660,
    "v13_added_function_count": 252,
    "v14_added_function_count": 252,
    "v15_added_function_count": 252,
}
V16_EQUIVALENCE_COUNTS = {
    **V15_EQUIVALENCE_COUNTS,
    "logical_default_terminal_count": PROJECTED_COUNTS[
        "unique_logical_default_terminal_destinations"
    ],
    "logical_function_count": PROJECTED_COUNTS["logical_functions"],
    "logical_intent_count": PROJECTED_COUNTS["logical_intents"],
    "physical_default_terminal_count": PROJECTED_COUNTS[
        "unique_physical_default_terminal_destinations"
    ],
    "physical_function_count": PROJECTED_COUNTS["physical_functions"],
    "physical_intent_count": PROJECTED_COUNTS["physical_intents"],
    "v16_added_function_count": len(V16_FUNCTIONS),
}


def _equivalence_document_digest(payload: Mapping[str, object]) -> str:
    document = copy.deepcopy(dict(payload))
    integrity = document.get("integrity")
    if not isinstance(integrity, dict):
        raise V16CatalogValidationError("equivalence integrity metadata is missing")
    integrity.pop("canonical_sha256", None)
    serialized = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _equivalence_state(payload: Mapping[str, object]) -> str:
    counts = payload.get("audit_counts")
    provenance = payload.get("provenance")
    if not isinstance(counts, Mapping) or not isinstance(provenance, Mapping):
        raise V16CatalogValidationError("equivalence counts or provenance is missing")
    if dict(counts) == V15_EQUIVALENCE_COUNTS:
        if provenance.get("catalog_version") != CATALOG_V15_VERSION:
            raise V16CatalogValidationError("V15 equivalence provenance differs")
        return "v15"
    if dict(counts) == V16_EQUIVALENCE_COUNTS:
        if (
            provenance.get("catalog_version") != CATALOG_V16_VERSION
            or provenance.get("v16_added_marker")
            != "v16_role_governed_operations"
            or payload.get("equivalence_version") != "1.2.0"
        ):
            raise V16CatalogValidationError("V16 equivalence provenance differs")
        return "v16"
    raise V16CatalogValidationError("equivalence audit counts differ from V15/V16")


def validate_v16_equivalence_payload(
    payload: Mapping[str, object],
    catalog_payload: Mapping[str, object],
) -> dict[str, object]:
    """Validate the count-neutral V16 projection over the ten prior classes."""

    state = _equivalence_state(payload)
    classes = payload.get("classes")
    if payload.get("equivalence_kind") != "true_equivalent" or not isinstance(
        classes, list
    ):
        raise V16CatalogValidationError("equivalence class registry differs")
    members = {
        str(member)
        for item in classes
        if isinstance(item, Mapping)
        for member in (
            item.get("canonical_function_id", ""),
            *item.get("alias_function_ids", []),
        )
        if str(member)
    }
    alias_count = sum(
        len(item.get("alias_function_ids", []))
        for item in classes
        if isinstance(item, Mapping)
    )
    if len(classes) != 10 or alias_count != 10 or len(members) != 20:
        raise V16CatalogValidationError("equivalence class cardinality differs")
    v16_ids = {str(item["function_id"]) for item in V16_FUNCTIONS}
    if v16_ids.intersection(members):
        raise V16CatalogValidationError("V16 function joined a prior equivalence class")

    functions = catalog_payload.get("functions")
    intents = catalog_payload.get("intents")
    if not isinstance(functions, list) or not isinstance(intents, list):
        raise V16CatalogValidationError("catalog collections are missing")
    catalog_ids = {str(item.get("function_id", "")) for item in functions}
    if not members <= catalog_ids:
        raise V16CatalogValidationError("equivalence member is absent from catalog")
    integrity = payload.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get(
        "canonical_sha256"
    ) != _equivalence_document_digest(payload):
        raise V16CatalogValidationError("equivalence integrity hash differs")
    if state == "v16":
        if (
            catalog_payload.get("catalog_version") != CATALOG_V16_VERSION
            or len(functions) != PROJECTED_COUNTS["physical_functions"]
            or len(intents) != PROJECTED_COUNTS["physical_intents"]
        ):
            raise V16CatalogValidationError("V16 equivalence/catalog projection differs")
    return {
        "state": state,
        "class_count": len(classes),
        "alias_count": alias_count,
        "member_count": len(members),
    }


def merge_equivalence_with_v16(
    base_payload: Mapping[str, object],
    catalog_payload: Mapping[str, object],
) -> dict[str, object]:
    """Return an idempotent V16 equivalence ledger without adding a class."""

    stats = validate_v16_equivalence_payload(base_payload, catalog_payload)
    if stats["state"] == "v16":
        return copy.deepcopy(dict(base_payload))

    result = copy.deepcopy(dict(base_payload))
    result["equivalence_version"] = "1.2.0"
    result["audit_counts"] = copy.deepcopy(V16_EQUIVALENCE_COUNTS)
    provenance = result.get("provenance")
    if not isinstance(provenance, dict):
        raise V16CatalogValidationError("equivalence provenance is missing")
    provenance.update(
        {
            "catalog_version": CATALOG_V16_VERSION,
            "scope": (
                "The ten audited true-equivalent classes only; the v13, v14, "
                "v15, and v16 append-only packs introduce no new equivalence "
                "member, and rejected context-distinct, parent-child, and "
                "unsafe-to-merge candidates are intentionally absent."
            ),
            "v16_added_marker": "v16_role_governed_operations",
            "v16_coverage_document": DESIGN_SOURCE_RELATIVE_PATH,
            "v16_refinement_document": REFINEMENT_SOURCE_RELATIVE_PATH,
        }
    )
    integrity = result.get("integrity")
    if not isinstance(integrity, dict):
        raise V16CatalogValidationError("equivalence integrity metadata is missing")
    integrity["canonical_sha256"] = _equivalence_document_digest(result)
    validate_v16_equivalence_payload(result, catalog_payload)
    return result


def project_equivalence_to_v15(
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Return the exact-count V15 ledger needed to rebuild V16 idempotently."""

    state = _equivalence_state(payload)
    result = copy.deepcopy(dict(payload))
    if state == "v15":
        # The integrity check also rejects a modified V15 ledger before it can
        # participate in source reconstruction.
        expected = _equivalence_document_digest(result)
        if result.get("integrity", {}).get("canonical_sha256") != expected:
            raise V16CatalogValidationError("equivalence integrity hash differs")
        return result

    result["equivalence_version"] = "1.1.0"
    result["audit_counts"] = copy.deepcopy(V15_EQUIVALENCE_COUNTS)
    provenance = result.get("provenance")
    if not isinstance(provenance, dict):
        raise V16CatalogValidationError("equivalence provenance is missing")
    provenance["catalog_version"] = CATALOG_V15_VERSION
    provenance["scope"] = (
        "The ten audited true-equivalent classes only; the v13, v14, and v15 "
        "append-only packs introduce no new equivalence member, and rejected "
        "context-distinct, parent-child, and unsafe-to-merge candidates are "
        "intentionally absent."
    )
    provenance.pop("v16_added_marker", None)
    provenance.pop("v16_coverage_document", None)
    provenance.pop("v16_refinement_document", None)
    integrity = result.get("integrity")
    if not isinstance(integrity, dict):
        raise V16CatalogValidationError("equivalence integrity metadata is missing")
    integrity["canonical_sha256"] = _equivalence_document_digest(result)
    return result


def build_semantic_equivalence_report(base_payload: Mapping[str, object] | None = None) -> tuple[dict[str, object], ...]:
    """Return one distinct/reject decision for each proposed V16 terminal."""

    base = load_base_catalog() if base_payload is None else _pre_v16_payload(base_payload)
    prior_functions = list(base.get("functions", []))
    prior_intents = list(base.get("intents", []))
    prior_ids = {str(item["function_id"]) for item in prior_functions}
    name_owners: dict[str, set[str]] = defaultdict(set)
    for item in prior_functions:
        for field in ("name_ko", "name_en"):
            key = _semantic_phrase_key(item.get(field, ""))
            if key:
                name_owners[key].add(str(item["function_id"]))
    pattern_owners: dict[str, set[str]] = defaultdict(set)
    for item in prior_intents:
        for pattern in item.get("patterns", []):
            key = _semantic_phrase_key(pattern)
            if key:
                pattern_owners[key].add(str(item["intent_id"]))
    equivalence_members, _overlay = _equivalence_members()
    intent_by_function = {str(item["terminal_function"]): item for item in V16_INTENTS}
    reports: list[dict[str, object]] = []
    for function in V16_FUNCTIONS:
        if not function["terminal"]:
            continue
        function_id = str(function["function_id"])
        feature = REVIEWED_FEATURE_BY_ID[function_id]
        name_matches = sorted(
            set().union(*(name_owners.get(_semantic_phrase_key(function[field]), set()) for field in ("name_ko", "name_en")))
        )
        goal_matches = sorted(
            set().union(*(pattern_owners.get(_semantic_phrase_key(value), set()) for value in (feature.goal_ko, feature.goal_en)))
        )
        findings: list[str] = []
        if function_id in prior_ids:
            findings.append("same_id")
        if name_matches:
            findings.append("normalized_name_collision")
        if goal_matches:
            findings.append("normalized_goal_collision")
        if function_id in equivalence_members:
            findings.append("prior_equivalence_member")
        reports.append(
            {
                "report_id": f"v16_equivalence_{len(reports):04d}",
                "function_id": function_id,
                "exact_match": [function_id] if function_id in prior_ids else [],
                "normalized_phrase": {"function_name_matches": name_matches, "representative_goal_matches": goal_matches},
                "semantic_neighbors": list(intent_by_function[function_id].get("avoid_functions", [])),
                "equivalence_member": function_id in equivalence_members,
                "role_asset_state": {
                    "roles": list(function["role_hints"]),
                    "assets": list(function["asset_cues"]),
                    "jurisdiction": list(function["state_cues"]["jurisdiction"]),
                    "lifecycle": list(function["state_cues"]["lifecycle"]),
                    "state_changing": bool(function["state_changing"]),
                },
                "decision": "distinct_append" if not findings else "reject",
                "unresolved_findings": findings,
            }
        )
    return tuple(reports)


def _duplicates(values: Iterable[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Return a clean V15 source projection without materializing V16."""

    return merge_v15_with_base(load_v14_source_base(path))


def _pre_v16_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V16_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V16_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids]
    result["intents"] = [item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids]
    result.pop("official_sources_v16", None)
    result.pop("source_documents_v16", None)
    result.pop("semantic_equivalence_v16", None)
    result.pop("refinement_v16", None)
    result["catalog_version"] = CATALOG_V15_VERSION
    result["description"] = CATALOG_V15_DESCRIPTION
    return result


def project_catalog_to_v15(payload: Mapping[str, object]) -> dict[str, object]:
    """Rebuild the exact runtime V15 projection from V15 or V16 storage."""

    # Import locally so the sealed source pack remains usable without making
    # the collision-overlay module a generation-construction dependency.
    from navigation_alias_context_overrides import (
        apply_alias_context_overrides,
        strip_alias_context_overrides,
    )

    source = _pre_v16_payload(strip_alias_context_overrides(payload))
    projected = apply_alias_context_overrides(source)
    if (
        projected.get("catalog_version") != CATALOG_V15_VERSION
        or len(projected.get("functions", [])) != 2866
        or len(projected.get("intents", [])) != 2660
        or len(
            {
                str(item.get("domain", ""))
                for item in projected.get("functions", [])
            }
        )
        != 179
    ):
        raise V16CatalogValidationError("exact V15 runtime projection differs")
    return projected


def _materialization_state(payload: Mapping[str, object], report: tuple[dict[str, object], ...]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V16_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V16_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", []) if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", []) if str(item["intent_id"]) in expected_intents
    }
    metadata_keys = ("official_sources_v16", "source_documents_v16", "semantic_equivalence_v16", "refinement_v16")
    has_metadata = any(key in payload for key in metadata_keys)
    if not present_functions and not present_intents and not has_metadata:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V16CatalogValidationError("partial V16 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V16CatalogValidationError("V16 collides with a different function or intent definition")
    if payload.get("official_sources_v16") != OFFICIAL_SOURCES:
        raise V16CatalogValidationError("V16 official-source registry differs")
    if payload.get("source_documents_v16") != SOURCE_DOCUMENT_METADATA:
        raise V16CatalogValidationError("V16 source-document SHA registry differs")
    if payload.get("semantic_equivalence_v16") != list(report):
        raise V16CatalogValidationError("V16 semantic-equivalence report differs")
    expected_refinement = {
        "old_ids": sorted(REFINEMENT_OLD_IDS),
        "new_ids": sorted(REFINEMENT_NEW_IDS),
        "mapping": {old: f"{old.split('.', 1)[0]}.{REFINEMENT_BY_OLD_ID[old].new_feature.key}" for old in sorted(REFINEMENT_OLD_IDS)},
    }
    if payload.get("refinement_v16") != expected_refinement:
        raise V16CatalogValidationError("V16 refinement metadata differs")
    if payload.get("catalog_version") != CATALOG_V16_VERSION or payload.get("description") != CATALOG_V16_DESCRIPTION:
        raise V16CatalogValidationError("V16 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def validate_v16_data(
    base_payload: Mapping[str, object] | None = None,
    equivalence_payload: Mapping[str, object] | None = None,
    *,
    _include_equivalence_report: bool = False,
) -> dict[str, object]:
    """Validate frozen inputs, exact scope, official evidence, safety, and disjointness."""

    base = load_base_catalog() if base_payload is None else copy.deepcopy(dict(base_payload))
    errors: list[str] = []
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"source SHA differs for {relative_path}: {actual}")

    function_ids = [str(item["function_id"]) for item in V16_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V16_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V16_FUNCTIONS if item["terminal"]}
    domain_counts = Counter(str(item["domain"]) for item in V16_FUNCTIONS if item["terminal"])
    if _duplicates(function_ids) or _duplicates(intent_ids):
        errors.append("V16 contains duplicate function or intent IDs")
    if len(REQUIRED_DOMAINS) != 12 or len(V16_FUNCTIONS) != 252 or len(terminal_ids) != 240 or len(V16_INTENTS) != 240:
        errors.append("V16 requires 12 domains, 12 hubs, 240 terminals, 252 functions, and 240 intents")
    if dict(sorted(domain_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"V16 domain terminal counts differ: {dict(sorted(domain_counts.items()))}")
    sensitive = sum(bool(item["terminal"]) and item.get("classification") == "S" and not item["state_changing"] for item in V16_FUNCTIONS)
    consequential = sum(bool(item["terminal"]) and item.get("classification") == "C" and item["state_changing"] for item in V16_FUNCTIONS)
    if (sensitive, consequential) != (84, 156):
        errors.append(f"V16 S/C counts differ: S={sensitive}, C={consequential}")
    if terminal_ids != FINAL_TERMINAL_IDS or terminal_ids.intersection(REFINEMENT_OLD_IDS) or not REFINEMENT_NEW_IDS <= terminal_ids:
        errors.append("V16 refinement is not an exact count-neutral old-to-new replacement")

    normalized_urls: set[str] = set()
    source_terminal_union: set[str] = set()
    source_reference_counts: Counter[str] = Counter()
    for source_id, source in OFFICIAL_SOURCES.items():
        normalized = normalize_official_url(str(source.get("canonical_url", "")))
        if normalized in normalized_urls:
            errors.append(f"duplicate normalized V16 source URL: {normalized}")
        normalized_urls.add(normalized)
        if source.get("source_id") != source_id or source.get("normalized_url") != normalized:
            errors.append(f"source identity differs: {source_id}")
        if (
            urlsplit(normalized).scheme != "https"
            or source.get("verification_status") != "accepted"
            or source.get("evidence_level") != "official_primary"
            or source.get("http_status") != 200
            or source.get("verified_status") != 200
            or source.get("final_url") != source.get("canonical_url")
            or source.get("publisher") not in PUBLISHER_ALLOWLIST
            or not re.fullmatch(r"[0-9a-f]{64}", str(source.get("source_record_sha256", "")))
        ):
            errors.append(f"source verification metadata differs: {source_id}")
        if not set(source.get("source_documents", [])) <= set(SOURCE_DOCUMENT_SHA256):
            errors.append(f"source cites an unsealed document: {source_id}")
        mapped_terminals = {str(value) for value in source.get("terminal_ids", [])}
        if not mapped_terminals or not mapped_terminals <= terminal_ids:
            errors.append(f"source has empty or invalid terminal mapping: {source_id}")
        source_terminal_union.update(mapped_terminals)
        for terminal_id in mapped_terminals:
            source_reference_counts[terminal_id] += 1
    if source_terminal_union != terminal_ids or set(DOMAIN_TERMINAL_SOURCE_IDS) != terminal_ids:
        errors.append("V16 official source-to-terminal mapping is incomplete")
    if any(source_reference_counts[terminal_id] < 1 for terminal_id in terminal_ids):
        errors.append("V16 contains a terminal without an official source")
    referenced_source_ids = {source_id for source_ids in DOMAIN_TERMINAL_SOURCE_IDS.values() for source_id in source_ids}
    if referenced_source_ids != set(OFFICIAL_SOURCES):
        errors.append("V16 official registry has orphan or missing source records")
    if set(DOMAIN_SOURCE_IDS) != REQUIRED_DOMAINS:
        errors.append("V16 domain source registry differs")
    for new_id, expected_ids in REFINEMENT_TERMINAL_SOURCE_IDS.items():
        if DOMAIN_TERMINAL_SOURCE_IDS.get(new_id) != expected_ids:
            errors.append(f"{new_id}: refined accepted-source mapping differs")

    forbidden = {"x", "y", "bounds", "coordinate", "coordinates", "package", "package_name", "resource_id", "screenshot_hash", "screen_path", "recorded_path", "fixed_ui_path", "pixel", "click_sequence"}
    functions_by_id = {str(item["function_id"]): item for item in V16_FUNCTIONS}
    for function in V16_FUNCTIONS:
        function_id = str(function["function_id"])
        if _contains_forbidden_key(function, forbidden):
            errors.append(f"{function_id}: forbidden UI-specific key")
        if not function.get("source_refs") or set(function["source_refs"]) - set(OFFICIAL_SOURCES):
            errors.append(f"{function_id}: invalid official source references")
        if len(function["aliases"]["ko-KR"]) < 8 or len(function["aliases"]["en-US"]) < 8:
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if not function.get("role_hints") or not function.get("asset_cues") or not function.get("state_cues", {}).get("jurisdiction"):
            errors.append(f"{function_id}: missing role/asset/jurisdiction semantics")
        if function["terminal"]:
            feature = REVIEWED_FEATURE_BY_ID[function_id]
            if function.get("classification") != feature.classification:
                errors.append(f"{function_id}: class differs from reviewed source")
            if function.get("name_ko") != feature.name_ko or function.get("name_en") != feature.name_en:
                errors.append(f"{function_id}: bilingual name differs")
            if function.get("representative_goals") != {"ko-KR": feature.goal_ko, "en-US": feature.goal_en}:
                errors.append(f"{function_id}: bilingual representative goal differs")
            if (
                function.get("automation_policy") != "never_auto"
                or function.get("stop_policy") != "before_action"
                or function.get("risk_level") != "high"
                or function.get("user_owned_final_press") is not True
                or not function.get("risk_cues", {}).get("source_boundary")
            ):
                errors.append(f"{function_id}: terminal safety boundary differs")
            if set(function["source_refs"]) != set(DOMAIN_TERMINAL_SOURCE_IDS[function_id]):
                errors.append(f"{function_id}: source_refs differ from registry mapping")
        elif (
            function.get("node_kind") != "hub"
            or function.get("risk_level") != "low"
            or function.get("automation_policy") != "safe_navigation"
            or function.get("stop_policy") != "continue"
            or function.get("state_changing") is not False
            or function.get("user_owned_final_press") is not False
        ):
            errors.append(f"{function_id}: hub safety policy differs")

    for intent in V16_INTENTS:
        target = str(intent["terminal_function"])
        feature = REVIEWED_FEATURE_BY_ID[target]
        if str(intent["intent_id"]) != f"v16_{target.replace('.', '_')}":
            errors.append(f"{target}: intent ID differs")
        if intent["patterns_by_locale"]["ko-KR"][0] != feature.goal_ko or intent["patterns_by_locale"]["en-US"][0] != feature.goal_en:
            errors.append(f"{target}: intent representative patterns differ")
        if len(intent["patterns_by_locale"]["ko-KR"]) < 5 or len(intent["patterns_by_locale"]["en-US"]) < 5 or len(intent["goal_rules"]) < 20:
            errors.append(f"{target}: insufficient bilingual patterns or rules")
        if not any(rule.get("rule_kind") == "v16_role_asset_state_gate" for rule in intent["goal_rules"]):
            errors.append(f"{target}: missing role/asset/state resolution gate")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != target:
            errors.append(f"{target}: route differs")
        if intent.get("terminal_condition") != {"stop_policy": "stop_before_action", "user_owned_final_press": True}:
            errors.append(f"{target}: terminal condition differs")
        if intent.get("resolution_gate", {}).get("minimum_positive_dimensions") != (3 if feature.classification == "C" else 2):
            errors.append(f"{target}: resolution gate differs")
        if target not in functions_by_id:
            errors.append(f"{target}: intent target missing")

    semantic = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    if len(semantic) != 1440 or len(collisions) != 720 or len(recovery) != 960 or len(isolation) != 720:
        errors.append("V16 derived probe cardinality differs")

    pre_v16 = _pre_v16_payload(base)
    if (
        pre_v16.get("catalog_version") != CATALOG_V15_VERSION
        or len(pre_v16.get("functions", [])) != 2866
        or len(pre_v16.get("intents", [])) != 2660
        or len({str(item["domain"]) for item in pre_v16.get("functions", [])}) != 179
    ):
        errors.append("V16 base must be a clean exact V15 source projection")
    base_function_ids = {str(item["function_id"]) for item in pre_v16.get("functions", [])}
    base_intent_ids = {str(item["intent_id"]) for item in pre_v16.get("intents", [])}
    base_domains = {str(item["domain"]) for item in pre_v16.get("functions", [])}
    if set(function_ids).intersection(base_function_ids) or set(intent_ids).intersection(base_intent_ids) or REQUIRED_DOMAINS.intersection(base_domains):
        errors.append("V16 IDs or domains collide with V15")
    equivalence_members, overlay = _equivalence_members(equivalence_payload)
    if terminal_ids.intersection(equivalence_members):
        errors.append("V16 terminal joined a prior equivalence class")
    try:
        equivalence_state = _equivalence_state(overlay)
        input_is_v16 = base.get("catalog_version") == CATALOG_V16_VERSION
        if input_is_v16 != (equivalence_state == "v16"):
            errors.append("catalog/equivalence generation differs")
        elif equivalence_state == "v16":
            validate_v16_equivalence_payload(overlay, base)
    except V16CatalogValidationError as error:
        errors.append(str(error))

    reports = build_semantic_equivalence_report(pre_v16)
    unresolved = [item for item in reports if item["unresolved_findings"]]
    if len(reports) != 240 or unresolved:
        errors.append(f"V16 equivalence/collision report has unresolved findings: {unresolved[:3]}")
    materialized = False
    if not errors:
        materialized = _materialization_state(base, reports)
    if errors:
        raise V16CatalogValidationError("; ".join(errors))
    result: dict[str, object] = {
        "functions": len(V16_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V16_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_counts.items())),
        "sensitive_reads": sensitive,
        "state_changing": consequential,
        "official_sources": len(OFFICIAL_SOURCES),
        "source_distribution": EXPECTED_SOURCE_DISTRIBUTION,
        "source_documents": copy.deepcopy(DOCUMENT_DIGESTS),
        "source_orphans": len(set(OFFICIAL_SOURCES) - referenced_source_ids),
        "refinement_replacements": len(REFINEMENTS),
        "aliases": sum(len(values) for item in V16_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V16_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V16_INTENTS),
        "semantic_smoke_probes": len(semantic),
        "collision_probes": len(collisions),
        "recovery_probes": len(recovery),
        "isolation_probes": len(isolation),
        "equivalence_reports": len(reports),
        "equivalence_collisions": len(unresolved),
        "projected_counts": copy.deepcopy(PROJECTED_COUNTS),
        "materialized": materialized,
    }
    if _include_equivalence_report:
        result["_validated_equivalence_report"] = copy.deepcopy(reports)
    return result


def merge_with_base(
    base_payload: Mapping[str, object],
    equivalence_payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return a deterministic, non-mutating, idempotent V15+V16 copy."""

    stats = validate_v16_data(
        base_payload,
        equivalence_payload,
        _include_equivalence_report=True,
    )
    report = tuple(stats.pop("_validated_equivalence_report"))
    if stats["materialized"]:
        return copy.deepcopy(dict(base_payload))
    merged = _pre_v16_payload(base_payload)
    merged["catalog_version"] = CATALOG_V16_VERSION
    merged["description"] = CATALOG_V16_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V16_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V16_INTENTS)]
    merged["official_sources_v16"] = copy.deepcopy(OFFICIAL_SOURCES)
    merged["source_documents_v16"] = copy.deepcopy(SOURCE_DOCUMENT_METADATA)
    merged["semantic_equivalence_v16"] = copy.deepcopy(list(report))
    merged["refinement_v16"] = {
        "old_ids": sorted(REFINEMENT_OLD_IDS),
        "new_ids": sorted(REFINEMENT_NEW_IDS),
        "mapping": {old: f"{old.split('.', 1)[0]}.{REFINEMENT_BY_OLD_ID[old].new_feature.key}" for old in sorted(REFINEMENT_OLD_IDS)},
    }
    return merged


def main() -> int:
    print(json.dumps(validate_v16_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
