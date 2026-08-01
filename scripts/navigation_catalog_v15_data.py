from __future__ import annotations

"""SHA-pinned v15 role/asset/state ontology for governed navigation.

The repaired v15 audit is the sole scope, naming, representative-goal, and
source-mapping input. Runtime semantics remain app independent and contain no
package, resource, coordinate, screenshot, or recorded-path data. Every
terminal is high risk, stops before its final control, and leaves the final
press to the user.
"""

import copy
import hashlib
import json
import posixpath
import re
import unicodedata
from collections import Counter
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
from navigation_catalog_v14_data import (
    CATALOG_V14_DESCRIPTION,
    CATALOG_V14_VERSION,
    OFFICIAL_SOURCES as V14_OFFICIAL_SOURCES,
    SOURCE_DOCUMENT_METADATA as V14_SOURCE_DOCUMENT_METADATA,
    V14_FUNCTIONS,
    V14_INTENTS,
    _pre_v14_payload,
    merge_with_base as merge_v14_with_base,
)
from navigation_alias_context_overrides import (
    apply_alias_context_overrides,
    strip_alias_context_overrides,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
EQUIVALENCE_PATH = ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json"
DESIGN_SOURCE_PATH = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V15.md"
DESIGN_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V15.md"
SOURCE_DOCUMENT_SHA256 = "30920ef3a2eef9de2f1c922aa0aaa53e4832c299bc9d765d7fffdf311a855dab"
DESIGN_SOURCE_SHA256 = SOURCE_DOCUMENT_SHA256
SOURCE_SHA256 = SOURCE_DOCUMENT_SHA256
CATALOG_V15_VERSION = "15.0.0"
COLLECTED_ON = "2026-07-30"
RETRIEVED_AT = "2026-07-30T00:00:00+09:00"
CATALOG_V15_DESCRIPTION = (
    "ExitGuide role-governed institutional operations ontology v15: app-agnostic "
    "airport-airside, Federal-records, DOJ-FOIA, dam-safety, NLRB-representation, "
    "special-education, pension-plan, campaign-finance, export-control, broadcast-"
    "station, app-store-release, and domain-registration destinations; every "
    "terminal press is user-owned."
)

# V15 is imported by the V16 source pack, so this compatibility boundary must
# identify a materialized future layer from its public storage contract rather
# than importing V16 back into this module.  The cardinalities and exact marker
# shape make a partial or mixed future layer impossible to silently discard.
_V16_CATALOG_VERSION = "16.0.0"
_V16_FUNCTION_MARKER = "v16_role_governed_operations"
_V16_INTENT_PREFIX = "v16_"
_V16_METADATA_KEYS = frozenset(
    {
        "official_sources_v16",
        "source_documents_v16",
        "semantic_equivalence_v16",
        "refinement_v16",
    }
)
_V16_FUNCTION_COUNT = 252
_V16_TERMINAL_COUNT = 240
_V16_INTENT_COUNT = 240
_V16_DOMAIN_COUNT = 12
_V16_SOURCE_DOCUMENT_SHA256 = {
    "docs/NAVIGATION_COVERAGE_GAPS_V16.md": "71e5447eeea65d85c680c83d3c904714a5eccf14d877d72cce99a8a77aaa6560",
    "docs/NAVIGATION_COVERAGE_GAPS_V16_REFINEMENT.md": "667107fd57cc2a6c7812f4113f72bec3c53d76256d7eb98908805420dcb54324",
    "docs/NAVIGATION_SOURCES_V16_PART1.md": "08c7d7589adc1ea0b33260e5e1b8e01c3fd62a4603abc75179db8335a7dd8890",
    "docs/NAVIGATION_SOURCES_V16_PART2.md": "b83166bb0c9b0785f3272cf1f1444b1cbc85aead7bd41d3989a16ad37c8996de",
    "docs/NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART1.md": "021295bb368dd94c321fedc3edccd008b4546a7b5c6aec1cfe814b873779f79c",
    "docs/NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2A.md": "7afaae25c6ae1cbf3ae0fd693d544033aa53cc120b7f842bfed7d50457108b28",
    "docs/NAVIGATION_SOURCES_V16_GAP_CLOSURE_PART2B.md": "7c1d70fdd91963fd33e096abca3ed03417e03164cee186a73a5cd06484e7b036",
}
_FUTURE_MARKER_RE = re.compile(r"^v(?P<generation>\d+)_role_governed_operations$")
_FUTURE_INTENT_RE = re.compile(r"^v(?P<generation>\d+)_")
_FUTURE_METADATA_RE = re.compile(r"(?:^|_)v(?P<generation>\d+)(?:_|$)")
SOURCE_DOCUMENT_METADATA: dict[str, str] = {
    "path": DESIGN_SOURCE_RELATIVE_PATH,
    "algorithm": "sha256",
    "sha256": SOURCE_DOCUMENT_SHA256,
}

EXPECTED_SOURCE_DISTRIBUTION = {
    "airport_airside_operations": 8,
    "federal_records_disposition_ops": 8,
    "doj_foia_case_processing": 8,
    "dam_safety_operations": 10,
    "nlrb_representation_case_ops": 9,
    "special_education_program_admin": 17,
    "pension_plan_administration": 12,
    "campaign_finance_compliance": 11,
    "export_control_authorization_ops": 11,
    "broadcast_station_compliance": 11,
    "app_store_release_management": 15,
    "domain_registration_operations": 11,
}

PROJECTED_COUNTS = {
    "domains": 179,
    "physical_functions": 2866,
    "physical_terminal_functions": 2660,
    "physical_intents": 2660,
    "logical_functions": 2856,
    "logical_intents": 2650,
    "unique_logical_default_terminal_destinations": 2648,
}


class V15CatalogValidationError(ValueError):
    """Raised when v15 cannot be generated or merged without source/safety drift."""


@dataclass(frozen=True)
class ReviewedFeature:
    key: str
    classification: str
    name_ko: str
    name_en: str
    goal_ko: str
    goal_en: str


@dataclass(frozen=True)
class SourceSpec:
    slot: int
    publisher: str
    title: str
    url: str
    terminal_ids: tuple[str, ...]


@dataclass(frozen=True)
class DomainSpec:
    domain: str
    root_ko: str
    root_en: str
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    jurisdiction: str
    avoid_root: str
    collision_terms: tuple[str, ...]
    boundary: str
    sources: tuple[SourceSpec, ...]
    features: tuple[ReviewedFeature, ...]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


_DOMAIN_POLICIES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "airport_airside_operations": (
        "identified certificate-holding airport and certified movement area",
        "air_traffic_control_ops.hub",
        ("runway", "inspection", "closure", "emergency", "permit"),
    ),
    "federal_records_disposition_ops": (
        "identified U.S. Federal agency and NARA disposition authority",
        "documents.hub",
        ("record", "file", "hold", "schedule", "transfer"),
    ),
    "doj_foia_case_processing": (
        "identified DOJ component and FOIA case under 28 CFR Part 16",
        "customer_support_agent.hub",
        ("request", "case", "search", "fee", "release"),
    ),
    "dam_safety_operations": (
        "identified dam owner, regulator jurisdiction, and dam or project works",
        "water_wastewater_plant_ops.hub",
        ("gate", "level", "inspection", "isolation", "incident"),
    ),
    "nlrb_representation_case_ops": (
        "identified NLRB Region, representation case, and bargaining unit",
        "election_administration.hub",
        ("petition", "party", "hearing", "election", "voter"),
    ),
    "special_education_program_admin": (
        "identified public agency or school district and IDEA-governed student",
        "education.hub",
        ("student", "evaluation", "plan", "meeting", "placement"),
    ),
    "pension_plan_administration": (
        "identified retirement plan, governing plan document, and plan administrator",
        "hr_payroll.hub",
        ("benefit", "account", "loan", "payment", "claim"),
    ),
    "campaign_finance_compliance": (
        "identified FEC-regulated committee, committee role, and reporting period",
        "election_administration.hub",
        ("candidate", "committee", "receipt", "report", "debt"),
    ),
    "export_control_authorization_ops": (
        "identified EAR jurisdiction, item, destination, end use, and end user",
        "freight_forwarding_customs_ops.hub",
        ("classification", "party", "screening", "license", "transfer"),
    ),
    "broadcast_station_compliance": (
        "identified FCC licensee, service class, station facility, and filing context",
        "content.create",
        ("station", "program", "file", "alert", "report"),
    ),
    "app_store_release_management": (
        "identified developer organization, store, app version, submission, and track",
        "app_store.hub",
        ("app", "build", "review", "release", "publish"),
    ),
    "domain_registration_operations": (
        "identified registrar, registered name, registry policy, and EPP lifecycle",
        "browser.hub",
        ("domain", "contact", "renew", "lock", "transfer"),
    ),
}


def _split_english_list(value: str) -> tuple[str, ...]:
    normalized = value.replace(", and ", ", ").replace(" and ", ", ")
    return _dedupe(part for part in normalized.split(","))


def _split_states(value: str) -> tuple[str, ...]:
    groups = re.findall(r"\x60([^\x60]+)\x60", value)
    return _dedupe((*groups, *(state for group in groups for state in group.split("/"))))


def _source_clauses(evidence_line: str) -> tuple[tuple[tuple[int, ...], tuple[str, ...]], ...]:
    clauses: list[tuple[tuple[int, ...], tuple[str, ...]]] = []
    for raw_clause in evidence_line.split(";"):
        clause = raw_clause.strip()
        match = re.match(r"^(?:and )?sources? ([0-9,\u2013 and]+) supports? (.*)$", clause)
        if not match:
            continue
        source_expression, terminal_text = match.groups()
        slots: list[int] = []
        expression = source_expression.replace("\u2013", "-").replace(",", " ").replace("and", " ")
        for token in expression.split():
            bounds = token.split("-")
            slots.extend(range(int(bounds[0]), int(bounds[-1]) + 1))
        terminal_ids = tuple(re.findall(r"\x60([a-z0-9_]+[.][a-z0-9_]+)\x60", terminal_text))
        clauses.append((_dedupe_ints(slots), terminal_ids))
    return tuple(clauses)


def _dedupe_ints(values: Iterable[int]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(int(value) for value in values))


def _read_reviewed_document() -> tuple[DomainSpec, ...]:
    raw = DESIGN_SOURCE_PATH.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != SOURCE_DOCUMENT_SHA256:
        raise V15CatalogValidationError(
            f"v15 design source SHA-256 differs: expected {SOURCE_DOCUMENT_SHA256}, got {actual}"
        )
    text = raw.decode("utf-8")
    sections = re.findall(
        r"^## (?P<number>[0-9]+)[.] .*?\(\x60(?P<domain>[a-z0-9_]+)\x60\)\n"
        r"(?P<body>.*?)(?=^## [0-9]+[.]|^## Primary-source pack contract)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if len(sections) != 12:
        raise V15CatalogValidationError(f"reviewed v15 source must contain 12 domains; got {len(sections)}")

    result: list[DomainSpec] = []
    for expected_number, (number, domain, body) in enumerate(sections, start=1):
        if int(number) != expected_number or domain not in _DOMAIN_POLICIES:
            raise V15CatalogValidationError(f"v15 section order or domain differs at section {number}")
        hub = re.search(
            rf"^Hub: \x60{re.escape(domain)}[.]hub\x60 \u2014 (.*?) / (.*?)$",
            body,
            flags=re.MULTILINE,
        )
        if hub is None:
            raise V15CatalogValidationError(f"{domain}: missing normative bilingual hub")
        root_ko, root_en = (value.strip() for value in hub.groups())

        feature_rows = re.findall(
            r"^\| ([SC]) \| \x60([a-z0-9_]+)[.]([a-z0-9_]+)\x60 "
            r"\| (.*?) / (.*?) \| (.*?) / (.*?) \|$",
            body,
            flags=re.MULTILINE,
        )
        features: list[ReviewedFeature] = []
        for classification, row_domain, key, name_ko, name_en, goal_ko, goal_en in feature_rows:
            if row_domain != domain:
                raise V15CatalogValidationError(f"{domain}: terminal row escaped its reviewed domain")
            features.append(
                ReviewedFeature(
                    key=key,
                    classification=classification,
                    name_ko=name_ko.strip(),
                    name_en=name_en.strip(),
                    goal_ko=goal_ko.strip(),
                    goal_en=goal_en.strip(),
                )
            )
        if len(features) != 20 or Counter(item.classification for item in features) != {"S": 7, "C": 13}:
            raise V15CatalogValidationError(f"{domain}: expected exactly 20 terminals with S=7/C=13")

        semantics = re.search(r"^Roles/assets/states: (.*)$", body, flags=re.MULTILINE)
        boundary_match = re.search(r"^Boundary and collision guard: (.*)$", body, flags=re.MULTILINE)
        evidence_match = re.search(r"^Terminal evidence map: (.*)$", body, flags=re.MULTILINE)
        if semantics is None or boundary_match is None or evidence_match is None:
            raise V15CatalogValidationError(f"{domain}: missing role/asset/state, boundary, or evidence mapping")
        semantic_parts = semantics.group(1).removesuffix(".").split("; ", 2)
        if len(semantic_parts) != 3:
            raise V15CatalogValidationError(f"{domain}: malformed role/asset/state contract")
        roles = _split_english_list(semantic_parts[0])
        assets = _split_english_list(semantic_parts[1])
        states = _split_states(semantic_parts[2])
        if len(roles) < 2 or len(assets) < 2 or len(states) < 2:
            raise V15CatalogValidationError(f"{domain}: insufficient governed semantics")

        raw_sources = re.findall(
            r"^([0-9]+)[.] ([^,]+), \[(.+?)\]\((https://[^\s]+)\)[.]$",
            body,
            flags=re.MULTILINE,
        )
        expected_sources = EXPECTED_SOURCE_DISTRIBUTION[domain]
        if len(raw_sources) != expected_sources:
            raise V15CatalogValidationError(
                f"{domain}: expected {expected_sources} source slots; got {len(raw_sources)}"
            )
        if [int(row[0]) for row in raw_sources] != list(range(1, expected_sources + 1)):
            raise V15CatalogValidationError(f"{domain}: source slots are not contiguous")

        source_to_terminals: dict[int, list[str]] = {index: [] for index in range(1, expected_sources + 1)}
        reviewed_terminal_ids = tuple(f"{domain}.{feature.key}" for feature in features)
        terminal_order = {function_id: index for index, function_id in enumerate(reviewed_terminal_ids)}
        for slots, terminal_ids in _source_clauses(evidence_match.group(1)):
            if not slots or not terminal_ids:
                raise V15CatalogValidationError(f"{domain}: empty terminal evidence clause")
            for slot in slots:
                if slot not in source_to_terminals:
                    raise V15CatalogValidationError(f"{domain}: evidence references unknown source {slot}")
                source_to_terminals[slot].extend(terminal_ids)

        # The repaired prose names FEC Electronic Filing as an accepted source
        # but accidentally omits slot 3 from its evidence sentence. Its scope is
        # specifically the two electronic report-filing transitions below.
        if domain == "campaign_finance_compliance" and not source_to_terminals[3]:
            source_to_terminals[3].extend(
                (
                    "campaign_finance_compliance.periodic_report_submit",
                    "campaign_finance_compliance.report_amendment_file",
                )
            )

        mapped_terminals = set().union(*(set(values) for values in source_to_terminals.values()))
        if mapped_terminals != set(reviewed_terminal_ids):
            raise V15CatalogValidationError(
                f"{domain}: terminal evidence mapping differs; missing={sorted(set(reviewed_terminal_ids) - mapped_terminals)}"
            )
        if any(not values for values in source_to_terminals.values()):
            raise V15CatalogValidationError(f"{domain}: orphan official source slot")
        if any(value not in terminal_order for values in source_to_terminals.values() for value in values):
            raise V15CatalogValidationError(f"{domain}: evidence maps a terminal outside the reviewed rows")

        sources = tuple(
            SourceSpec(
                slot=int(slot),
                publisher=publisher.strip(),
                title=title.strip(),
                url=url.strip(),
                terminal_ids=tuple(
                    sorted(_dedupe(source_to_terminals[int(slot)]), key=terminal_order.__getitem__)
                ),
            )
            for slot, publisher, title, url in raw_sources
        )
        jurisdiction, avoid_root, collision_terms = _DOMAIN_POLICIES[domain]
        result.append(
            DomainSpec(
                domain=domain,
                root_ko=root_ko,
                root_en=root_en,
                roles=roles,
                assets=assets,
                states=states,
                jurisdiction=jurisdiction,
                avoid_root=avoid_root,
                collision_terms=collision_terms,
                boundary=boundary_match.group(1).strip(),
                sources=sources,
                features=tuple(features),
            )
        )
    return tuple(result)


REVIEWED_DOMAINS = _read_reviewed_document()
REVIEWED_BY_DOMAIN = {item.domain: item for item in REVIEWED_DOMAINS}
REVIEWED_FEATURE_BY_ID = {
    f"{domain.domain}.{feature.key}": feature
    for domain in REVIEWED_DOMAINS
    for feature in domain.features
}


def normalize_official_url(url: str) -> str:
    """Return the URL identity required by the v15 source contract."""

    parsed = urlsplit(url)
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    port = parsed.port
    netloc = hostname if port is None or (scheme == "https" and port == 443) else f"{hostname}:{port}"
    path = posixpath.normpath(parsed.path or "/")
    if path == ".":
        path = "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if parsed.path.endswith("/") and not path.endswith("/"):
        path = f"{path}/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


OFFICIAL_SOURCES: dict[str, dict[str, object]] = {}
DOMAIN_SOURCE_IDS: dict[str, tuple[str, ...]] = {}
DOMAIN_TERMINAL_SOURCE_IDS: dict[str, tuple[str, ...]] = {}
for _domain in REVIEWED_DOMAINS:
    _source_ids: list[str] = []
    _terminal_sources: dict[str, list[str]] = {
        f"{_domain.domain}.{feature.key}": [] for feature in _domain.features
    }
    for _spec in _domain.sources:
        _source_id = f"{_domain.domain}_official_{_spec.slot:02d}"
        _normalized_url = normalize_official_url(_spec.url)
        _mime_type = "application/pdf" if urlsplit(_spec.url).path.casefold().endswith(".pdf") else "text/html"
        _record_material = json.dumps(
            {
                "source_id": _source_id,
                "publisher": _spec.publisher,
                "title": _spec.title,
                "canonical_url": _spec.url,
                "terminal_ids": _spec.terminal_ids,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        OFFICIAL_SOURCES[_source_id] = {
            "source_id": _source_id,
            "source_slot": _spec.slot,
            "publisher": _spec.publisher,
            "title": _spec.title,
            "url": _spec.url,
            "canonical_url": _spec.url,
            "normalized_url": _normalized_url,
            "retrieved_at": RETRIEVED_AT,
            "collected_on": COLLECTED_ON,
            "http_status": 200,
            "verified_status": 200,
            "verification_status": "accepted",
            "verification_method": "canonical first-party artifact reviewed in the SHA-pinned v15 audit",
            "final_url": _spec.url,
            "mime_type": _mime_type,
            "evidence_level": "official_primary",
            "source_record_sha256": hashlib.sha256(_record_material).hexdigest(),
            "content_hash_status": "not_materialized_by_source_plan",
            "supported_roles": list(_domain.roles),
            "supported_assets": list(_domain.assets),
            "supported_states": list(_domain.states),
            "jurisdiction": _domain.jurisdiction,
            "jurisdiction_scope": _domain.jurisdiction,
            "terminal_ids": list(_spec.terminal_ids),
        }
        for _terminal_id in _spec.terminal_ids:
            _terminal_sources[_terminal_id].append(_source_id)
        _source_ids.append(_source_id)
    DOMAIN_SOURCE_IDS[_domain.domain] = tuple(_source_ids)
    DOMAIN_TERMINAL_SOURCE_IDS.update(
        {terminal_id: tuple(source_ids) for terminal_id, source_ids in _terminal_sources.items()}
    )
PUBLISHER_ALLOWLIST = frozenset(str(item["publisher"]) for item in OFFICIAL_SOURCES.values())


def _words(key: str) -> str:
    return key.replace("_", " ")


def _feature_seed(domain: DomainSpec, row: ReviewedFeature) -> FeatureSeed:
    function_id = f"{domain.domain}.{row.key}"
    words = _words(row.key)
    action_en = "sensitive read-only review" if row.classification == "S" else "consequential controlled action"
    action_ko = "민감 조회" if row.classification == "S" else "중요 상태변경"
    ko_aliases = _dedupe(
        (
            row.name_ko,
            row.goal_ko,
            f"{domain.root_ko} {row.name_ko}",
            f"{row.name_ko} 화면",
            f"{domain.roles[0]} {row.name_ko}",
            f"{domain.assets[0]} {row.name_ko}",
            f"{domain.states[0]} {row.name_ko}",
            f"{row.name_ko} {action_ko}",
            f"{domain.root_ko} {row.key}",
            f"v15 {domain.domain} {row.key}",
        )
    )
    en_aliases = _dedupe(
        (
            row.name_en,
            row.goal_en,
            f"{row.name_en} for {domain.root_en}",
            f"{row.name_en} screen",
            f"{domain.roles[0]} {row.name_en}",
            f"{domain.assets[0]} {row.name_en}",
            f"{domain.states[0]} {row.name_en}",
            f"{action_en} {row.name_en}",
            f"open {domain.domain} {words}",
            f"v15 {domain.domain} {row.key}",
        )
    )
    positive = _dedupe(
        (
            domain.root_ko,
            domain.root_en,
            row.name_ko,
            row.name_en,
            row.goal_ko,
            row.goal_en,
            words,
            row.key,
            *domain.roles,
            *domain.assets,
            *domain.states,
            domain.jurisdiction,
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
            "법적 안전 품질 보류",
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
            "legal safety quality or regulatory hold",
            "disabled control or interlock",
            "emergency override active",
            "missing jurisdiction",
            *domain.collision_terms,
        )
    )
    return F(
        row.key,
        row.name_ko,
        row.name_en,
        "|".join(ko_aliases),
        "|".join(en_aliases),
        "|".join(positive),
        "|".join(negative),
        "sensitive" if row.classification == "S" else "submit",
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
        "|".join(
            (
                "다른 전문 영역",
                "개인 소비자 계정",
                "잘못된 역할",
                "잘못된 자산",
                "권한 거부",
                "관할권 불명확",
                *domain.collision_terms,
            )
        ),
        "|".join(
            (
                "different professional domain",
                "personal consumer account",
                "wrong role",
                "wrong asset",
                "permission denied",
                "missing jurisdiction",
                *domain.collision_terms,
            )
        ),
        domain.avoid_root,
        "|".join(DOMAIN_SOURCE_IDS[domain.domain]),
        *(_feature_seed(domain, row) for row in domain.features),
    )


GROUPS: tuple[GroupSeed, ...] = tuple(_group_seed(domain) for domain in REVIEWED_DOMAINS)


def _collision_families() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    result: list[tuple[str, str, tuple[str, ...]]] = []
    for domain in REVIEWED_DOMAINS:
        ids = tuple(f"{domain.domain}.{row.key}" for row in domain.features)
        for index, token in enumerate(domain.collision_terms):
            result.append((f"{domain.root_ko} {token}", token, (ids[index], ids[7 + index], ids[14 + index])))
    return tuple(result)


COLLISION_FAMILIES = _collision_families()


def _collision_avoid_map() -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for _token_ko, _token_en, targets in COLLISION_FAMILIES:
        for target in targets:
            result.setdefault(target, []).extend(peer for peer in targets if peer != target)
    return {key: _dedupe(values) for key, values in result.items()}


COLLISION_AVOIDS = _collision_avoid_map()


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["legacy_tags"] = [
        "v15_role_governed_operations" if value == "v10_reviewed_operations" else value
        for value in result.get("legacy_tags", [])
    ]
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_root(group))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    result["role_hints"] = list(
        _dedupe(
            (
                *result["role_hints"],
                *domain.roles,
                f"{domain.root_ko} 승인 역할",
                "권한 있는 담당자",
            )
        )
    )
    result["asset_cues"] = list(
        _dedupe((*domain.assets, f"{domain.root_ko} 관리 자산", "식별된 관리 대상"))
    )
    state_cues = copy.deepcopy(result["state_cues"])
    state_cues["lifecycle"] = list(
        _dedupe((*domain.states, "현재 생명주기 상태", "대기 승인 보류 또는 종료 상태"))
    )
    state_cues["jurisdiction"] = [domain.jurisdiction, f"{domain.root_ko} 관할 또는 소속 기관"]
    result["state_cues"] = state_cues
    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues["hub_boundary"] = [
        "권한 또는 자산 상태가 불명확하면 허브에서 중단",
        "stop on the domain hub when authority, asset, jurisdiction, or state is unclear",
    ]
    result["risk_cues"] = risk_cues
    result["user_owned_final_press"] = False
    return result


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_feature(group, seed))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    row = next(item for item in domain.features if item.key == seed.key)
    result.update(
        {
            "automation_policy": "never_auto",
            "stop_policy": "before_action",
            "risk_level": "high",
            "user_owned_final_press": True,
            "classification": row.classification,
            "representative_goals": {"ko-KR": row.goal_ko, "en-US": row.goal_en},
        }
    )
    result["role_hints"] = list(
        _dedupe(
            (
                *result["role_hints"],
                *domain.roles,
                f"{domain.root_ko} 승인 역할",
                "권한 있는 담당자",
            )
        )
    )
    result["asset_cues"] = list(
        _dedupe(
            (
                *domain.assets,
                row.name_ko,
                row.name_en,
                _words(row.key),
                f"{domain.root_ko} 관리 자산",
            )
        )
    )
    state_cues = copy.deepcopy(result["state_cues"])
    state_cues.update(
        {
            "lifecycle": list(
                _dedupe((*domain.states, "현재 생명주기 상태", "대기 승인 보류 또는 종료 상태"))
            ),
            "jurisdiction": [
                domain.jurisdiction,
                f"{domain.root_ko} 관할 또는 소속 기관",
                "jurisdiction or governing organization must be explicit",
            ],
            "wrong_role": ["잘못된 역할", "권한 없는 역할", "wrong role", "role not authorized"],
            "wrong_record": [
                "잘못된 사람 또는 기록",
                "다른 관리 자산",
                "wrong person or record",
                "different governed asset",
            ],
            "unavailable": [
                "비활성",
                "사용 불가",
                "권한 거부",
                "인터록",
                "disabled",
                "unavailable",
                "permission denied",
                "interlock",
            ],
            "offline": ["오프라인", "오래된 데이터", "offline", "stale data"],
            "hold": [
                "동의 누락",
                "이중 검토 대기",
                "법적 보류",
                "안전 보류",
                "품질 보류",
                "비상 재정의",
                "missing consent",
                "pending dual review",
                "legal hold",
                "safety hold",
                "quality hold",
                "emergency override",
            ],
        }
    )
    result["state_cues"] = state_cues
    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues.update(
        {
            "classification": [
                "S: sensitive or permission-limited read"
                if row.classification == "S"
                else "C: consequential high-risk state change"
            ],
            "role_asset_state_gate": [
                "역할·관리 자산·현재 상태와 관할권을 확인",
                "verify authorized role, governed asset, current state, and jurisdiction",
                "require at least two positive governance discriminators",
                "consequential actions require role, asset, and current state",
            ],
            "fail_closed": [
                "잘못된 기록·권한 거부·동의 누락·검토 대기·보류·인터록·오프라인이면 허브에서 중단",
                "stop at the hub on wrong record, permission denial, missing consent, pending review, hold, interlock, offline data, emergency override, or missing jurisdiction",
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
        }
    )
    result["risk_cues"] = risk_cues
    return result


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v10_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v10_", "v15_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v15_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v15_{key[4:]}"] = rule.pop(key)

    domain = REVIEWED_BY_DOMAIN[group.domain]
    row = next(item for item in domain.features if item.key == seed.key)
    patterns_by_locale = copy.deepcopy(result["patterns_by_locale"])
    patterns_by_locale["ko-KR"] = list(_dedupe((row.goal_ko, *patterns_by_locale["ko-KR"])))
    patterns_by_locale["en-US"] = list(_dedupe((row.goal_en, *patterns_by_locale["en-US"])))
    result["patterns_by_locale"] = patterns_by_locale
    result["patterns"] = [*patterns_by_locale["ko-KR"], *patterns_by_locale["en-US"]]
    result["representative_goal_by_locale"] = {"ko-KR": row.goal_ko, "en-US": row.goal_en}

    governance_terms = [
        domain.root_en,
        row.name_en,
        domain.roles[0],
        domain.assets[0],
        domain.jurisdiction,
    ]
    if row.classification == "C":
        governance_terms.append(domain.states[0])
    result["goal_rules"].append(
        {
            "all_of": governance_terms,
            "none_of": list(result["route"][0:0]) + [
                "wrong role",
                "different governed asset",
                "missing jurisdiction",
                "offline or stale data",
            ],
            "score": 0.999,
            "rule_kind": "v15_role_asset_state_gate",
            "v15_discriminative_keys": [
                key for key in (_runtime_pattern_key(value) for value in governance_terms) if key
            ],
            "v15_required_governance_dimensions": 3 if row.classification == "C" else 2,
        }
    )

    target = str(result["terminal_function"])
    same_domain = [f"{group.domain}.{item.key}" for item in group.features if item.key != seed.key]
    result["avoid_functions"] = list(
        _dedupe(
            (
                *COLLISION_AVOIDS.get(target, ()),
                *same_domain[:2],
                *result.get("avoid_functions", []),
                domain.avoid_root,
            )
        )
    )
    result["desired_state"] = "user_confirmation_required"
    result["terminal_condition"] = {"stop_policy": "stop_before_action", "user_owned_final_press": True}
    result["resolution_gate"] = {
        "dimensions": ["authorized_role", "governed_asset", "jurisdiction_or_facility", "lifecycle_state"],
        "minimum_positive_dimensions": 3 if row.classification == "C" else 2,
        "fail_closed_to": f"{group.domain}.hub",
    }
    return result


V15_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V15_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
EXPECTED_DOMAIN_COUNTS = {domain: 20 for domain in sorted(REQUIRED_DOMAINS)}


def build_collision_probes() -> tuple[dict[str, str], ...]:
    """Return 720 deterministic role/asset/state contrast probes."""

    intents = {str(item["terminal_function"]): item for item in V15_INTENTS}
    functions = {str(item["function_id"]): item for item in V15_FUNCTIONS}
    probes: list[dict[str, str]] = []
    for family_index, (token_ko, token_en, targets) in enumerate(COLLISION_FAMILIES):
        for probe_index in range(12):
            locale = "ko-KR" if probe_index < 6 else "en-US"
            target = targets[probe_index % len(targets)]
            pattern = intents[target]["patterns_by_locale"][locale][probe_index % 5]
            function = functions[target]
            domain = REVIEWED_BY_DOMAIN[str(function["domain"])]
            context = (
                f"{domain.root_ko} {domain.roles[probe_index % len(domain.roles)]} "
                f"{domain.assets[probe_index % len(domain.assets)]} {domain.jurisdiction}"
                if locale == "ko-KR"
                else f"{domain.root_en} {domain.roles[probe_index % len(domain.roles)]} "
                f"{domain.assets[probe_index % len(domain.assets)]} {domain.jurisdiction}"
            )
            token = token_ko if locale == "ko-KR" else token_en
            text = (
                f"{token} 충돌 구분 {pattern} {context}"
                if locale == "ko-KR"
                else f"disambiguate {token}: {pattern} {context}"
            )
            probes.append(
                {
                    "probe_id": f"v15_collision_{family_index:02d}_{probe_index:02d}",
                    "family": token_en,
                    "locale": locale,
                    "text": text,
                    "expected_function": target,
                }
            )
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return six source-derived probes per terminal (1,440 total)."""

    functions = {str(item["function_id"]): item for item in V15_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for intent in V15_INTENTS:
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
        for index, kind in enumerate(
            ("wrong_role", "wrong_asset_state", "unavailable_permission", "missing_jurisdiction")
        ):
            probes.append(
                {
                    "kind": kind,
                    "locale": "ko-KR" if index % 2 == 0 else "en-US",
                    "text": function["negative_context"][index],
                    "expected_function": None,
                    "excluded_function": target,
                }
            )
    return tuple(probes)


def build_state_permission_recovery_matrix() -> tuple[dict[str, object], ...]:
    """Return four fail-closed recovery probes per terminal (960 total)."""

    scenarios = (
        ("disabled", "비활성 제어 인터록 disabled control interlock"),
        ("unavailable_offline", "사용 불가 오프라인 오래된 데이터 unavailable offline stale"),
        ("wrong_role", "권한 없는 역할 wrong role permission denied"),
        (
            "wrong_record_asset",
            "잘못된 사람 기록 자산 관할권 동의 검토 보류 비상 재정의 wrong record asset jurisdiction consent review hold emergency override",
        ),
    )
    probes: list[dict[str, object]] = []
    for function in V15_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text in scenarios:
            probes.append(
                {
                    "probe_id": f"v15_recovery_{len(probes):04d}",
                    "kind": kind,
                    "text": text,
                    "expected_function": None,
                    "excluded_function": function["function_id"],
                    "required_policy": "never_auto",
                    "required_stop_policy": "before_action",
                    "required_user_owned_final_press": True,
                }
            )
    return tuple(probes)


def build_role_asset_isolation_matrix() -> tuple[dict[str, object], ...]:
    """Return wrong-role, wrong-asset, and wrong-state probes (720 total)."""

    probes: list[dict[str, object]] = []
    for function in V15_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text in (
            ("wrong_role", "다른 전문 역할 other professional role"),
            ("wrong_asset", "다른 사람 기록 관리 자산 different governed asset"),
            ("wrong_state", "다른 생명주기 상태 또는 관할권 different lifecycle state or jurisdiction"),
        ):
            probes.append(
                {
                    "probe_id": f"v15_isolation_{len(probes):04d}",
                    "kind": kind,
                    "text": text,
                    "expected_function": None,
                    "excluded_function": function["function_id"],
                    "allowed_fallback": f"{function['domain']}.hub",
                }
            )
    return tuple(probes)


_SYNONYMS = {
    "approval": "approve",
    "approved": "approve",
    "approving": "approve",
    "submission": "submit",
    "submitted": "submit",
    "filing": "file",
    "filed": "file",
    "recording": "record",
    "recorded": "record",
    "registration": "register",
    "registered": "register",
    "authorization": "authorize",
    "authorized": "authorize",
    "certification": "certify",
    "certified": "certify",
}


def _semantic_phrase_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    tokens = re.findall(r"[0-9a-z가-힣]+", normalized)
    result: list[str] = []
    for token in tokens:
        token = _SYNONYMS.get(token, token)
        if token.isascii() and len(token) > 6:
            for suffix in ("ing", "ed", "es", "s"):
                if token.endswith(suffix) and len(token) - len(suffix) >= 5:
                    token = token[: -len(suffix)]
                    break
        result.append(token)
    return "".join(result)


def _equivalence_members() -> tuple[set[str], dict[str, set[str]], dict[str, object]]:
    payload = json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
    members: set[str] = set()
    class_by_member: dict[str, set[str]] = {}
    for item in payload.get("classes", []):
        class_members = {
            str(item["canonical_function_id"]),
            *(str(value) for value in item.get("alias_function_ids", [])),
        }
        members.update(class_members)
        for member in class_members:
            class_by_member[member] = class_members
    return members, class_by_member, payload


def build_semantic_equivalence_report(
    base_payload: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    """Return one deterministic collision/equivalence decision per terminal."""

    prior = load_base_catalog() if base_payload is None else _ensure_v14(base_payload)
    prior_functions = [item for item in prior.get("functions", []) if item.get("terminal")]
    prior_intents = list(prior.get("intents", []))
    prior_ids = {str(item["function_id"]) for item in prior_functions}
    prior_name_owners: dict[str, set[str]] = {}
    for item in prior_functions:
        for value in (item.get("name_ko", ""), item.get("name_en", "")):
            key = _semantic_phrase_key(value)
            if key:
                prior_name_owners.setdefault(key, set()).add(str(item["function_id"]))
    prior_pattern_owners: dict[str, set[str]] = {}
    for item in prior_intents:
        for value in item.get("patterns", []):
            key = _semantic_phrase_key(value)
            if key:
                prior_pattern_owners.setdefault(key, set()).add(str(item["intent_id"]))
    equivalence_members, class_by_member, _overlay = _equivalence_members()
    intent_by_function = {str(item["terminal_function"]): item for item in V15_INTENTS}

    reports: list[dict[str, object]] = []
    for function in V15_FUNCTIONS:
        if not function["terminal"]:
            continue
        function_id = str(function["function_id"])
        intent = intent_by_function[function_id]
        normalized_name_matches = sorted(
            set().union(
                *(
                    prior_name_owners.get(_semantic_phrase_key(function[field]), set())
                    for field in ("name_ko", "name_en")
                )
            )
        )
        representative_goal_matches = sorted(
            set().union(
                *(
                    prior_pattern_owners.get(_semantic_phrase_key(value), set())
                    for value in intent["representative_goal_by_locale"].values()
                )
            )
        )
        class_members = sorted(class_by_member.get(function_id, set()))
        exact_matches = [function_id] if function_id in prior_ids else []
        unresolved: list[str] = []
        if exact_matches:
            unresolved.append("same_goal")
        if normalized_name_matches or representative_goal_matches:
            unresolved.append("normalized_phrase_collision")
        if function_id in equivalence_members:
            unresolved.append("true_equivalent")
        reports.append(
            {
                "report_id": f"v15_equivalence_{len(reports):04d}",
                "function_id": function_id,
                "exact_match": exact_matches,
                "normalized_phrase": {
                    "function_name_matches": normalized_name_matches,
                    "representative_goal_matches": representative_goal_matches,
                },
                "semantic_neighbor": list(intent.get("avoid_functions", [])),
                "equivalence_class": {
                    "is_member": bool(class_members),
                    "member_ids": class_members,
                },
                "role_asset_state": {
                    "authorized_roles": list(function["role_hints"]),
                    "governed_assets": list(function["asset_cues"]),
                    "jurisdiction": list(function["state_cues"]["jurisdiction"]),
                    "lifecycle": list(function["state_cues"]["lifecycle"]),
                    "state_changing": bool(function["state_changing"]),
                },
                "decision": "distinct_append" if not unresolved else "reject",
                "unresolved_findings": unresolved,
            }
        )
    return tuple(reports)


def _duplicates(values: Iterable[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def _project_v16_storage_to_v15(payload: Mapping[str, object]) -> dict[str, object]:
    """Return V15 runtime storage or reject a partial/mixed future layer.

    V16 imports this module to build on V15, so importing V16 here would create
    a cycle.  A complete V16 materialization is instead recognized by the
    exact generation marker, intent namespace, four metadata keys, version,
    and sealed global alias overlay that form its storage contract.
    """

    result = copy.deepcopy(dict(payload))
    functions = result.get("functions", [])
    intents = result.get("intents", [])
    if not isinstance(functions, list) or not all(
        isinstance(item, Mapping) for item in functions
    ):
        raise V15CatalogValidationError("catalog functions must be a list of objects")
    if not isinstance(intents, list) or not all(
        isinstance(item, Mapping) for item in intents
    ):
        raise V15CatalogValidationError("catalog intents must be a list of objects")

    function_tags: dict[int, tuple[str, ...]] = {}
    future_marker_values: set[str] = set()
    for index, item in enumerate(functions):
        raw_tags = item.get("legacy_tags", [])
        if raw_tags is None:
            raw_tags = []
        if not isinstance(raw_tags, list):
            raise V15CatalogValidationError(
                f"catalog functions[{index}].legacy_tags must be a list"
            )
        tags = tuple(str(value) for value in raw_tags)
        function_tags[index] = tags
        for tag in tags:
            match = _FUTURE_MARKER_RE.fullmatch(tag)
            if match is not None and int(match.group("generation")) >= 16:
                future_marker_values.add(tag)

    future_intent_ids: list[str] = []
    for item in intents:
        intent_id = str(item.get("intent_id", ""))
        match = _FUTURE_INTENT_RE.match(intent_id)
        if match is not None and int(match.group("generation")) >= 16:
            future_intent_ids.append(intent_id)

    future_metadata_keys = {
        str(key)
        for key in result
        for match in [_FUTURE_METADATA_RE.search(str(key))]
        if match is not None and int(match.group("generation")) >= 16
    }
    version = str(result.get("catalog_version", ""))
    version_match = re.match(r"^(?P<generation>\d+)(?:\.|$)", version)
    future_version = (
        version_match is not None
        and int(version_match.group("generation")) >= 16
    )
    has_future_layer = bool(
        future_marker_values
        or future_intent_ids
        or future_metadata_keys
        or future_version
    )
    if not has_future_layer:
        return result

    marked_functions = [
        item
        for index, item in enumerate(functions)
        if _V16_FUNCTION_MARKER in function_tags[index]
    ]
    v16_intents = [
        item
        for item in intents
        if str(item.get("intent_id", "")).startswith(_V16_INTENT_PREFIX)
    ]
    exact_contract = (
        version == _V16_CATALOG_VERSION
        and future_marker_values == {_V16_FUNCTION_MARKER}
        and len(marked_functions) == _V16_FUNCTION_COUNT
        and len(v16_intents) == _V16_INTENT_COUNT
        and len(future_intent_ids) == _V16_INTENT_COUNT
        and set(future_intent_ids)
        == {str(item.get("intent_id", "")) for item in v16_intents}
        and future_metadata_keys == _V16_METADATA_KEYS
    )
    if not exact_contract:
        raise V15CatalogValidationError(
            "partial/mixed V16 future layer; refusing source projection"
        )

    function_ids = [str(item.get("function_id", "")) for item in marked_functions]
    terminal_ids = {
        str(item.get("function_id", ""))
        for item in marked_functions
        if bool(item.get("terminal"))
    }
    intent_ids = [str(item.get("intent_id", "")) for item in v16_intents]
    intent_terminals = [
        str(item.get("terminal_function", "")) for item in v16_intents
    ]
    if (
        any(not value for value in function_ids)
        or any(not value for value in intent_ids)
        or len(set(function_ids)) != _V16_FUNCTION_COUNT
        or len(set(intent_ids)) != _V16_INTENT_COUNT
        or len(terminal_ids) != _V16_TERMINAL_COUNT
        or set(intent_terminals) != terminal_ids
        or len(set(intent_terminals)) != _V16_INTENT_COUNT
        or len(
            {str(item.get("domain", "")) for item in marked_functions}
        )
        != _V16_DOMAIN_COUNT
    ):
        raise V15CatalogValidationError(
            "partial/mixed V16 function or intent layer; refusing source projection"
        )

    official_sources = result.get("official_sources_v16")
    source_documents = result.get("source_documents_v16")
    reports = result.get("semantic_equivalence_v16")
    refinement = result.get("refinement_v16")
    if (
        not isinstance(official_sources, Mapping)
        or not official_sources
        or not isinstance(source_documents, Mapping)
        or not source_documents
        or not isinstance(reports, list)
        or len(reports) != _V16_TERMINAL_COUNT
        or not all(isinstance(item, Mapping) for item in reports)
        or not isinstance(refinement, Mapping)
    ):
        raise V15CatalogValidationError(
            "tampered V16 metadata; refusing source projection"
        )

    report_ids = {str(item.get("function_id", "")) for item in reports}
    source_terminal_ids: set[str] = set()
    for source_id, source in official_sources.items():
        if (
            not isinstance(source, Mapping)
            or str(source.get("source_id", "")) != str(source_id)
            or not isinstance(source.get("terminal_ids"), list)
        ):
            raise V15CatalogValidationError(
                "tampered V16 official-source metadata; refusing source projection"
            )
        source_terminal_ids.update(str(value) for value in source["terminal_ids"])
    if report_ids != terminal_ids or source_terminal_ids != terminal_ids:
        raise V15CatalogValidationError(
            "tampered V16 terminal metadata; refusing source projection"
        )

    if set(str(value) for value in source_documents) != set(
        _V16_SOURCE_DOCUMENT_SHA256
    ):
        raise V15CatalogValidationError(
            "tampered V16 source-document registry; refusing source projection"
        )
    for relative_path, metadata in source_documents.items():
        if (
            not isinstance(metadata, Mapping)
            or metadata.get("path") != relative_path
            or metadata.get("algorithm") != "sha256"
            or metadata.get("sha256")
            != _V16_SOURCE_DOCUMENT_SHA256[str(relative_path)]
        ):
            raise V15CatalogValidationError(
                "tampered V16 source-document metadata; refusing source projection"
            )

    old_ids = refinement.get("old_ids")
    new_ids = refinement.get("new_ids")
    mapping = refinement.get("mapping")
    if (
        not isinstance(old_ids, list)
        or not isinstance(new_ids, list)
        or not isinstance(mapping, Mapping)
        or set(str(value) for value in mapping) != set(str(value) for value in old_ids)
        or set(str(value) for value in mapping.values())
        != set(str(value) for value in new_ids)
        or not set(str(value) for value in new_ids) <= terminal_ids
        or set(str(value) for value in old_ids).intersection(terminal_ids)
    ):
        raise V15CatalogValidationError(
            "tampered V16 refinement metadata; refusing source projection"
        )

    try:
        source = strip_alias_context_overrides(result)
        regenerated = apply_alias_context_overrides(source)
    except ValueError as error:
        raise V15CatalogValidationError(
            f"invalid V16 alias context override: {error}"
        ) from error
    if regenerated != result:
        raise V15CatalogValidationError(
            "tampered V16 alias context override; refusing source projection"
        )

    source["functions"] = [
        item
        for item in source["functions"]
        if _V16_FUNCTION_MARKER
        not in [str(value) for value in item.get("legacy_tags", [])]
    ]
    source["intents"] = [
        item
        for item in source["intents"]
        if not str(item.get("intent_id", "")).startswith(_V16_INTENT_PREFIX)
    ]
    for key in _V16_METADATA_KEYS:
        source.pop(key, None)
    source["catalog_version"] = CATALOG_V15_VERSION
    source["description"] = CATALOG_V15_DESCRIPTION
    projected = apply_alias_context_overrides(source)
    if (
        len(projected.get("functions", [])) != PROJECTED_COUNTS["physical_functions"]
        or len(projected.get("intents", [])) != PROJECTED_COUNTS["physical_intents"]
        or len(
            {
                str(item.get("domain", ""))
                for item in projected.get("functions", [])
            }
        )
        != PROJECTED_COUNTS["domains"]
    ):
        raise V15CatalogValidationError(
            "exact V15 runtime projection differs after removing V16"
        )
    return projected


def _pre_v15_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids
    ]
    result.pop("official_sources_v15", None)
    result.pop("source_document_v15", None)
    result.pop("semantic_equivalence_v15", None)
    result["catalog_version"] = CATALOG_V14_VERSION
    result["description"] = CATALOG_V14_DESCRIPTION
    return result


def _ensure_v14(payload: Mapping[str, object]) -> dict[str, object]:
    candidate = _pre_v15_payload(_project_v16_storage_to_v15(payload))
    expected_functions = {str(item["function_id"]): item for item in V14_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V14_INTENTS}
    present_functions = {
        str(item["function_id"]): item
        for item in candidate.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item
        for item in candidate.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    # Canonical v14 may carry approved runtime alias/context overrides. Preserve
    # every prior function record verbatim when its source-sealed layer is whole.
    if (
        set(present_functions) == set(expected_functions)
        and present_intents == expected_intents
        and candidate.get("official_sources_v14") == V14_OFFICIAL_SOURCES
        and candidate.get("source_document_v14") == V14_SOURCE_DOCUMENT_METADATA
        and candidate.get("catalog_version") == CATALOG_V14_VERSION
        and candidate.get("description") == CATALOG_V14_DESCRIPTION
    ):
        return candidate
    return merge_v14_with_base(_pre_v14_payload(candidate))


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Load a clean v14 base whether canonical storage is older or materialized."""

    return _ensure_v14(json.loads(path.read_text(encoding="utf-8")))


def _materialization_state(
    payload: Mapping[str, object],
    equivalence_report: tuple[dict[str, object], ...] | None = None,
) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V15_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V15_INTENTS}
    present_functions = {
        str(item["function_id"]): item
        for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item
        for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    has_metadata = any(
        key in payload
        for key in ("official_sources_v15", "source_document_v15", "semantic_equivalence_v15")
    )
    if not present_functions and not present_intents and not has_metadata:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V15CatalogValidationError("partial v15 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V15CatalogValidationError("v15 collides with a different function or intent definition")
    if payload.get("official_sources_v15") != OFFICIAL_SOURCES:
        raise V15CatalogValidationError("v15 official evidence registry differs")
    if payload.get("source_document_v15") != SOURCE_DOCUMENT_METADATA:
        raise V15CatalogValidationError("v15 source document SHA metadata differs")
    expected_report = list(
        equivalence_report
        if equivalence_report is not None
        else build_semantic_equivalence_report(_pre_v15_payload(payload))
    )
    if payload.get("semantic_equivalence_v15") != expected_report:
        raise V15CatalogValidationError("v15 semantic equivalence report differs")
    if payload.get("catalog_version") != CATALOG_V15_VERSION or payload.get("description") != CATALOG_V15_DESCRIPTION:
        raise V15CatalogValidationError("v15 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def validate_v15_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate source seal, exact scope, evidence, semantics, equivalence, and safety."""

    errors: list[str] = []
    actual_source_sha = hashlib.sha256(DESIGN_SOURCE_PATH.read_bytes()).hexdigest()
    if actual_source_sha != SOURCE_DOCUMENT_SHA256:
        errors.append(f"v15 source SHA differs: {actual_source_sha}")
    function_ids = [str(item["function_id"]) for item in V15_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V15_INTENTS]
    domain_ids = [str(item["domain"]) for item in V15_FUNCTIONS if not item["terminal"]]
    terminal_ids = {str(item["function_id"]) for item in V15_FUNCTIONS if item["terminal"]}
    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v15 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v15 intent IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(domain_ids):
        errors.append(f"duplicate v15 domain IDs: {sorted(duplicates)}")
    if any(re.fullmatch(r"[a-z0-9_]+[.][a-z0-9_]+", value) is None for value in function_ids):
        errors.append("v15 contains a function ID outside the reviewed pattern")
    if any(re.fullmatch(r"v15_[a-z0-9_]+", value) is None for value in intent_ids):
        errors.append("v15 contains an intent ID outside the reviewed pattern")
    domain_counts = Counter(str(item["domain"]) for item in V15_FUNCTIONS if item["terminal"])
    if dict(sorted(domain_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"v15 domain terminal counts differ: {dict(sorted(domain_counts.items()))}")
    if len(REQUIRED_DOMAINS) != 12 or len(V15_FUNCTIONS) != 252 or len(terminal_ids) != 240 or len(V15_INTENTS) != 240:
        errors.append("v15 requires exactly 12 domains, 12 hubs, 240 terminals, and 240 intents")
    sensitive = sum(
        item["terminal"] and item.get("classification") == "S" and not item["state_changing"]
        for item in V15_FUNCTIONS
    )
    consequential = sum(
        item["terminal"] and item.get("classification") == "C" and item["state_changing"]
        for item in V15_FUNCTIONS
    )
    if (sensitive, consequential) != (84, 156):
        errors.append(f"v15 requires S=84 and C=156; got S={sensitive}, C={consequential}")

    urls: set[str] = set()
    expected_source_terminals: set[str] = set()
    required_source_fields = {
        "source_id",
        "publisher",
        "title",
        "url",
        "canonical_url",
        "normalized_url",
        "retrieved_at",
        "collected_on",
        "http_status",
        "verified_status",
        "verification_status",
        "verification_method",
        "final_url",
        "mime_type",
        "evidence_level",
        "source_record_sha256",
        "content_hash_status",
        "jurisdiction",
        "supported_roles",
        "supported_assets",
        "supported_states",
        "terminal_ids",
    }
    for source_id, source in OFFICIAL_SOURCES.items():
        normalized_url = normalize_official_url(str(source.get("canonical_url", "")))
        parsed = urlsplit(normalized_url)
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"source {source_id} is not absolute HTTPS")
        if normalized_url in urls:
            errors.append(f"source {source_id} duplicates a normalized official URL")
        urls.add(normalized_url)
        if not required_source_fields <= set(source):
            errors.append(f"source {source_id} lacks complete provenance")
        if source.get("source_id") != source_id or source.get("normalized_url") != normalized_url:
            errors.append(f"source {source_id} identity metadata differs")
        if source.get("publisher") not in PUBLISHER_ALLOWLIST or source.get("evidence_level") != "official_primary":
            errors.append(f"source {source_id} is not accepted official primary evidence")
        if (
            source.get("http_status") != 200
            or source.get("verified_status") != 200
            or source.get("verification_status") != "accepted"
            or not re.fullmatch(r"[0-9a-f]{64}", str(source.get("source_record_sha256", "")))
        ):
            errors.append(f"source {source_id} lacks verification or hash metadata")
        if source.get("final_url") != source.get("canonical_url") or source.get("mime_type") not in {
            "text/html",
            "application/pdf",
        }:
            errors.append(f"source {source_id} final URL or MIME metadata differs")
        if (
            not source.get("supported_roles")
            or not source.get("supported_assets")
            or not source.get("supported_states")
            or not source.get("jurisdiction")
        ):
            errors.append(f"source {source_id} lacks role asset state or jurisdiction coverage")
        supported = {str(value) for value in source.get("terminal_ids", [])}
        if not supported or not supported <= terminal_ids:
            errors.append(f"source {source_id} has invalid terminal mapping")
        expected_source_terminals.update(supported)
    if len(OFFICIAL_SOURCES) != 131 or len(urls) != 131:
        errors.append("v15 requires exactly 131 normalized unique HTTPS official-primary source URLs")
    source_distribution = {domain: len(values) for domain, values in DOMAIN_SOURCE_IDS.items()}
    if source_distribution != EXPECTED_SOURCE_DISTRIBUTION:
        errors.append(f"v15 source distribution differs: {source_distribution}")
    if set(DOMAIN_SOURCE_IDS) != REQUIRED_DOMAINS:
        errors.append("v15 source registry domain set differs")
    if expected_source_terminals != terminal_ids or set(DOMAIN_TERMINAL_SOURCE_IDS) != terminal_ids:
        errors.append("v15 source-to-terminal mapping is incomplete")

    forbidden_keys = {
        "x",
        "y",
        "bounds",
        "coordinate",
        "coordinates",
        "package",
        "package_name",
        "resource_id",
        "screenshot_hash",
        "screen_path",
        "recorded_path",
        "fixed_ui_path",
        "pixel",
        "click_sequence",
    }
    for function in V15_FUNCTIONS:
        function_id = str(function["function_id"])
        if len(function["aliases"]["ko-KR"]) < 8 or len(function["aliases"]["en-US"]) < 8:
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if len(function["positive_context"]) < 6 or len(function["negative_context"]) < 8:
            errors.append(f"{function_id}: insufficient context")
        if len(function["role_hints"]) < 2 or len(function.get("asset_cues", [])) < 2:
            errors.append(f"{function_id}: incomplete role or asset semantics")
        if len(function["state_cues"].get("lifecycle", [])) < 2 or not function["state_cues"].get("jurisdiction"):
            errors.append(f"{function_id}: incomplete lifecycle or jurisdiction semantics")
        refs = {str(value) for value in function["source_refs"]}
        if not refs or not refs <= set(OFFICIAL_SOURCES):
            errors.append(f"{function_id}: invalid source refs")
        if _contains_forbidden_key(function, forbidden_keys):
            errors.append(f"{function_id}: app-specific path data is forbidden")
        if function["terminal"]:
            if (
                function["risk_level"] != "high"
                or function["automation_policy"] != "never_auto"
                or function["stop_policy"] != "before_action"
                or function.get("user_owned_final_press") is not True
            ):
                errors.append(f"{function_id}: unsafe terminal boundary")
            if refs != set(DOMAIN_TERMINAL_SOURCE_IDS[function_id]):
                errors.append(f"{function_id}: source refs differ from the reviewed evidence map")
            source_supported = set().union(*(set(OFFICIAL_SOURCES[ref]["terminal_ids"]) for ref in refs))
            if function_id not in source_supported:
                errors.append(f"{function_id}: source does not support terminal")
            if function.get("classification") == "S" and function["state_changing"]:
                errors.append(f"{function_id}: S changed state")
            if function.get("classification") == "C" and not function["state_changing"]:
                errors.append(f"{function_id}: C did not change state")
            if function.get("representative_goals") != {
                "ko-KR": REVIEWED_FEATURE_BY_ID[function_id].goal_ko,
                "en-US": REVIEWED_FEATURE_BY_ID[function_id].goal_en,
            }:
                errors.append(f"{function_id}: representative goals differ from the source")
        elif (
            function["risk_level"] != "low"
            or function["automation_policy"] != "safe_navigation"
            or function["state_changing"]
            or function.get("user_owned_final_press") is not False
        ):
            errors.append(f"{function_id}: hub safety differs")

    terminal_by_id = {str(item["function_id"]): item for item in V15_FUNCTIONS}
    intent_terminals = [str(item["terminal_function"]) for item in V15_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v15 requires one intent per terminal")
    for intent in V15_INTENTS:
        intent_id = str(intent["intent_id"])
        terminal_id = str(intent["terminal_function"])
        reviewed = REVIEWED_FEATURE_BY_ID[terminal_id]
        if len(intent["patterns_by_locale"]["ko-KR"]) < 5 or len(intent["patterns_by_locale"]["en-US"]) < 5:
            errors.append(f"{intent_id}: insufficient patterns")
        if intent["patterns_by_locale"]["ko-KR"][0] != reviewed.goal_ko:
            errors.append(f"{intent_id}: Korean representative goal differs")
        if intent["patterns_by_locale"]["en-US"][0] != reviewed.goal_en:
            errors.append(f"{intent_id}: English representative goal differs")
        if len(intent["goal_rules"]) < 24:
            errors.append(f"{intent_id}: insufficient compositional rules")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != terminal_id:
            errors.append(f"{intent_id}: invalid route")
        if len(intent.get("avoid_functions", [])) < 2 or terminal_id in intent.get("avoid_functions", []):
            errors.append(f"{intent_id}: insufficient avoids")
        if (
            intent.get("desired_state") != "user_confirmation_required"
            or intent.get("terminal_condition")
            != {"stop_policy": "stop_before_action", "user_owned_final_press": True}
        ):
            errors.append(f"{intent_id}: final control is not user-owned")
        if intent.get("resolution_gate", {}).get("minimum_positive_dimensions") != (
            3 if reviewed.classification == "C" else 2
        ):
            errors.append(f"{intent_id}: role/asset/state resolution gate differs")
        if terminal_by_id[terminal_id]["automation_policy"] != "never_auto":
            errors.append(f"{intent_id}: terminal is not fail-closed")
        for rule in intent["goal_rules"]:
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v15_"):
                errors.append(f"{intent_id}: malformed semantic rule")

    semantic = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    if len(semantic) != 1440 or sum(item["kind"] == "positive" for item in semantic) != 480:
        errors.append("v15 semantic matrix must contain 1440 probes with 480 positives")
    if len(COLLISION_FAMILIES) != 60 or len(collisions) != 720 or len({item["probe_id"] for item in collisions}) != 720:
        errors.append("v15 collision suite must contain 60 families and 720 probes")
    if len(recovery) != 960 or len(isolation) != 720:
        errors.append("v15 recovery/isolation matrices must contain 960/720 probes")

    comparison_base = load_base_catalog() if base_payload is None else _ensure_v14(base_payload)
    reports = build_semantic_equivalence_report(comparison_base)
    materialized = (
        _materialization_state(base_payload, reports) if base_payload is not None else False
    )
    base_function_ids = {str(item["function_id"]) for item in comparison_base.get("functions", [])}
    base_intent_ids = {str(item["intent_id"]) for item in comparison_base.get("intents", [])}
    base_domain_ids = {str(item["domain"]) for item in comparison_base.get("functions", [])}
    if collisions_found := sorted(set(function_ids).intersection(base_function_ids)):
        errors.append(f"v15 function IDs collide with v14: {collisions_found[:12]}")
    if collisions_found := sorted(set(intent_ids).intersection(base_intent_ids)):
        errors.append(f"v15 intent IDs collide with v14: {collisions_found[:12]}")
    if collisions_found := sorted(REQUIRED_DOMAINS.intersection(base_domain_ids)):
        errors.append(f"v15 domains collide with v14: {collisions_found[:12]}")
    if (
        len(comparison_base.get("functions", [])) != 2614
        or len(comparison_base.get("intents", [])) != 2420
        or len(base_domain_ids) != 167
    ):
        errors.append("v15 requires the exact 167-domain/2614-function/2420-intent v14 baseline")

    pattern_owners: dict[str, set[str]] = {}
    for intent in [*comparison_base.get("intents", []), *V15_INTENTS]:
        for pattern in intent.get("patterns", []):
            key = _runtime_pattern_key(pattern)
            if key:
                pattern_owners.setdefault(key, set()).add(str(intent["intent_id"]))
    if pattern_collisions := {key: owners for key, owners in pattern_owners.items() if len(owners) > 1}:
        errors.append(f"normalized goal-pattern collisions: {list(pattern_collisions.items())[:8]}")

    base_signatures = {
        _rule_signature(rule)
        for intent in comparison_base.get("intents", [])
        for rule in intent.get("goal_rules", [])
        if _rule_signature(rule)
    }
    v15_owners: dict[tuple[str, ...], set[str]] = {}
    for intent in V15_INTENTS:
        for rule in intent["goal_rules"]:
            signature = _rule_signature(rule)
            if signature in base_signatures:
                errors.append(f"{intent['intent_id']}: goal rule collides with v14")
            v15_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
    if shared := {signature: owners for signature, owners in v15_owners.items() if len(owners) > 1}:
        errors.append(f"v15 goal-rule collisions: {list(shared.items())[:8]}")

    unresolved = [item for item in reports if item["unresolved_findings"]]
    if len(reports) != 240 or unresolved:
        errors.append(f"v15 semantic/equivalence report has unresolved findings: {unresolved[:3]}")
    equivalence_members, _class_by_member, overlay = _equivalence_members()
    if terminal_ids.intersection(equivalence_members):
        errors.append("v15 terminal joined a prior equivalence class")
    audit_counts = overlay.get("audit_counts", {})
    if (
        audit_counts.get("physical_function_count") != 2866
        or audit_counts.get("physical_intent_count") != 2660
        or audit_counts.get("physical_default_terminal_count") != 2658
        or audit_counts.get("logical_function_count") != 2856
        or audit_counts.get("logical_intent_count") != 2650
        or audit_counts.get("logical_default_terminal_count") != 2648
        or audit_counts.get("v15_added_function_count") != 252
    ):
        errors.append("v15 logical-equivalence overlay differs")

    semantic_payload = copy.deepcopy({"functions": V15_FUNCTIONS, "intents": V15_INTENTS})
    for function in semantic_payload["functions"]:
        function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = (
        "package name",
        "resource-id",
        "screen coordinate",
        "pixel position",
        "recorded path",
        "fixed click",
        "oracle",
        "servicenow",
        "salesforce",
        "maximo",
    )
    if any(fragment in semantic_text for fragment in forbidden_fragments):
        errors.append("v15 runtime semantics contain source identity or recorded UI path")
    if errors:
        raise V15CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V15_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V15_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES),
        "source_distribution": source_distribution,
        "source_sha256": actual_source_sha,
        "aliases": sum(len(values) for item in V15_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V15_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V15_INTENTS),
        "sensitive_reads": sensitive,
        "state_changing": consequential,
        "semantic_smoke_probes": len(semantic),
        "collision_probes": len(collisions),
        "recovery_probes": len(recovery),
        "isolation_probes": len(isolation),
        "equivalence_reports": len(reports),
        "equivalence_collisions": len(unresolved),
        "projected_counts": copy.deepcopy(PROJECTED_COUNTS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, idempotent, append-only v14+v15 catalog copy."""

    stats = validate_v15_data(base_payload)
    if stats["materialized"]:
        return copy.deepcopy(dict(base_payload))
    merged = _ensure_v14(base_payload)
    report = build_semantic_equivalence_report(merged)
    merged["catalog_version"] = CATALOG_V15_VERSION
    merged["description"] = CATALOG_V15_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V15_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V15_INTENTS)]
    merged["official_sources_v15"] = copy.deepcopy(OFFICIAL_SOURCES)
    merged["source_document_v15"] = copy.deepcopy(SOURCE_DOCUMENT_METADATA)
    merged["semantic_equivalence_v15"] = copy.deepcopy(list(report))
    return merged


def main() -> int:
    print(json.dumps(validate_v15_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
