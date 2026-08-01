from __future__ import annotations

import json
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


@dataclass(frozen=True)
class QualityFinding:
    severity: str
    code: str
    subject: str
    message: str
    evidence: tuple[str, ...] = ()


def audit_navigation_catalog(
    catalog_path: Path,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    policy = _load_policy(policy_path)
    functions = list(payload.get("functions", []))
    intents = list(payload.get("intents", []))
    function_ids = {str(item.get("function_id", "")) for item in functions}
    intent_ids = {str(item.get("intent_id", "")) for item in intents}
    findings: list[QualityFinding] = []

    official_sources: dict[str, dict[str, Any]] = {}
    for registry_name, registry in payload.items():
        if not str(registry_name).startswith("official_sources_"):
            continue
        if not isinstance(registry, dict):
            findings.append(
                QualityFinding(
                    "error",
                    "invalid_official_source_registry",
                    str(registry_name),
                    "Official source registry must be an object keyed by source ID.",
                )
            )
            continue
        for raw_source_id, raw_source in registry.items():
            source_id = str(raw_source_id).strip()
            if not source_id or not isinstance(raw_source, dict):
                findings.append(
                    QualityFinding(
                        "error",
                        "invalid_official_source",
                        source_id or str(registry_name),
                        "Official source entries require a non-empty ID and object metadata.",
                    )
                )
                continue
            source = dict(raw_source)
            if source_id in official_sources and official_sources[source_id] != source:
                findings.append(
                    QualityFinding(
                        "error",
                        "conflicting_official_source",
                        source_id,
                        "The same source ID has different definitions across source packs.",
                    )
                )
                continue
            official_sources[source_id] = source
            parsed_url = urlparse(str(source.get("url", "")))
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                findings.append(
                    QualityFinding(
                        "error",
                        "invalid_official_source_url",
                        source_id,
                        "Official evidence must use an absolute HTTPS URL.",
                    )
                )
            for field_name in ("publisher", "title"):
                if not str(source.get(field_name, "")).strip():
                    findings.append(
                        QualityFinding(
                            "error",
                            "incomplete_official_source",
                            source_id,
                            f"Official evidence is missing {field_name}.",
                        )
                    )

    domain_counts = Counter(str(item.get("domain", "unknown")) for item in functions)
    risk_counts = Counter(str(item.get("risk_level", "unknown")) for item in functions)
    policy_counts = Counter(str(item.get("automation_policy", "unknown")) for item in functions)
    locale_alias_counts: Counter[str] = Counter()
    alias_count = 0
    context_count = 0
    state_cue_count = 0
    risk_cue_count = 0
    role_hint_count = 0
    functions_with_positive = 0
    functions_with_negative = 0
    functions_with_state_cues = 0
    functions_with_risk_cues = 0
    aliases_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    duplicate_aliases: list[tuple[str, str, str]] = []
    sourced_function_count = 0

    for item in functions:
        function_id = str(item.get("function_id", ""))
        source_refs = {
            str(value).strip()
            for value in item.get("source_refs", [])
            if str(value).strip()
        }
        evidence_level = str(item.get("evidence_level", "")).strip()
        if source_refs:
            sourced_function_count += 1
            unknown_source_refs = sorted(source_refs - set(official_sources))
            if unknown_source_refs:
                findings.append(
                    QualityFinding(
                        "error",
                        "unknown_official_source_ref",
                        function_id,
                        "Function references evidence absent from the catalog source registries.",
                        tuple(unknown_source_refs),
                    )
                )
            if evidence_level != "official":
                findings.append(
                    QualityFinding(
                        "error",
                        "source_evidence_level_mismatch",
                        function_id,
                        "Functions with official source references must use evidence_level=official.",
                    )
                )
        elif evidence_level == "official":
            findings.append(
                QualityFinding(
                    "error",
                    "missing_official_source_ref",
                    function_id,
                    "Officially evidenced functions must cite at least one registered source.",
                )
            )
        aliases = item.get("aliases", {})
        if not isinstance(aliases, dict):
            aliases = {}
        function_alias_count = 0
        alias_languages: set[str] = set()
        for locale, values in aliases.items():
            seen: set[str] = set()
            for raw_value in values if isinstance(values, list) else []:
                value = str(raw_value)
                normalized = normalize_catalog_text(value)
                if not normalized:
                    findings.append(
                        QualityFinding("error", "empty_normalized_alias", function_id, f"Alias normalizes to empty: {value!r}")
                    )
                    continue
                if normalized in seen:
                    duplicate_aliases.append((function_id, str(locale), value))
                seen.add(normalized)
                aliases_by_key[(str(locale).lower(), normalized)].add(function_id)
                locale_alias_counts[str(locale)] += 1
                alias_count += 1
                function_alias_count += 1
                alias_languages.add(str(locale).casefold().replace("_", "-").split("-", 1)[0])
        minimum_aliases = int(policy.get("minimum_aliases_per_function", 0))
        if function_alias_count < minimum_aliases:
            findings.append(
                QualityFinding(
                    "error",
                    "thin_function_aliases",
                    function_id,
                    f"Only {function_alias_count} aliases are defined; minimum is {minimum_aliases}.",
                )
            )
        required_alias_languages = {
            str(value).casefold().replace("_", "-").split("-", 1)[0]
            for value in policy.get("required_alias_languages", [])
            if str(value).strip()
        }
        missing_alias_languages = sorted(required_alias_languages - alias_languages)
        if missing_alias_languages:
            findings.append(
                QualityFinding(
                    "error",
                    "missing_function_alias_language",
                    function_id,
                    "Function lacks aliases for required language families.",
                    tuple(missing_alias_languages),
                )
            )
        positive = [str(value) for value in item.get("positive_context", []) if str(value).strip()]
        negative = [str(value) for value in item.get("negative_context", []) if str(value).strip()]
        if positive:
            functions_with_positive += 1
        if negative:
            functions_with_negative += 1
        context_count += len(positive) + len(negative)
        for context_kind, values, policy_key in (
            ("positive", positive, "minimum_positive_contexts_per_function"),
            ("negative", negative, "minimum_negative_contexts_per_function"),
        ):
            minimum_contexts = int(policy.get(policy_key, 0))
            if len(values) < minimum_contexts:
                findings.append(
                    QualityFinding(
                        "error",
                        f"thin_{context_kind}_context",
                        function_id,
                        f"Only {len(values)} {context_kind} contexts are defined; minimum is {minimum_contexts}.",
                    )
                )
        state_cues = item.get("state_cues", {})
        risk_cues = item.get("risk_cues", {})
        if isinstance(state_cues, dict) and state_cues:
            functions_with_state_cues += 1
            state_cue_count += sum(len(values) for values in state_cues.values() if isinstance(values, list))
        if isinstance(risk_cues, dict) and risk_cues:
            functions_with_risk_cues += 1
            risk_cue_count += sum(len(values) for values in risk_cues.values() if isinstance(values, list))
        role_hints = [str(value) for value in item.get("role_hints", []) if str(value).strip()]
        role_hint_count += len(role_hints)
        minimum_role_hints = int(policy.get("minimum_role_hints_per_function", 0))
        if len(role_hints) < minimum_role_hints:
            findings.append(
                QualityFinding(
                    "error",
                    "thin_function_role_hints",
                    function_id,
                    f"Only {len(role_hints)} role hints are defined; minimum is {minimum_role_hints}.",
                )
            )

        risk = str(item.get("risk_level", ""))
        automation = str(item.get("automation_policy", ""))
        changing = bool(item.get("state_changing", False))
        if changing and automation != "never_auto":
            findings.append(
                QualityFinding("error", "unsafe_state_change_policy", function_id, "State-changing functions must be never_auto.")
            )
        if risk == "high" and automation != "never_auto":
            findings.append(
                QualityFinding("error", "unsafe_high_risk_policy", function_id, "High-risk functions must be never_auto.")
            )
        if (changing or risk == "high") and not _stops_before_activation(item):
            findings.append(
                QualityFinding(
                    "error",
                    "unsafe_stop_policy",
                    function_id,
                    "Risky functions must stop before activation or require explicit user confirmation.",
                )
            )
        if changing and not risk_cues:
            findings.append(
                QualityFinding("warning", "missing_risk_cues", function_id, "State-changing function has no structured risk cues.")
            )

    collisions = []
    for (locale, normalized), ids in sorted(aliases_by_key.items()):
        if len(ids) < 2:
            continue
        collision = {"locale": locale, "normalized": normalized, "function_ids": sorted(ids)}
        collisions.append(collision)
        collision_items = [item for item in functions if str(item.get("function_id")) in ids]
        if not all(item.get("negative_context") for item in collision_items):
            findings.append(
                QualityFinding(
                    "warning",
                    "undisambiguated_alias_collision",
                    normalized,
                    "Cross-function exact alias collision lacks negative context on every function.",
                    tuple(sorted(ids)),
                )
            )

    referenced_functions: set[str] = set()
    intent_pattern_count = 0
    goal_rule_count = 0
    route_step_count = 0
    intent_pattern_keys: dict[str, set[str]] = defaultdict(set)
    duplicate_patterns: list[tuple[str, str]] = []
    for item in intents:
        intent_id = str(item.get("intent_id", ""))
        terminal = str(item.get("terminal_function", ""))
        referenced_functions.add(terminal)
        if terminal not in function_ids:
            findings.append(QualityFinding("error", "unknown_terminal", intent_id, f"Unknown terminal function: {terminal}"))
        patterns = [str(value) for value in item.get("patterns", []) if str(value).strip()]
        intent_pattern_count += len(patterns)
        if len(patterns) < int(policy.get("minimum_patterns_per_intent", 4)):
            findings.append(
                QualityFinding("warning", "thin_intent_patterns", intent_id, f"Only {len(patterns)} goal patterns are defined.")
            )
        for pattern in patterns:
            normalized = normalize_catalog_text(pattern)
            if intent_id in intent_pattern_keys[normalized]:
                duplicate_patterns.append((intent_id, pattern))
            intent_pattern_keys[normalized].add(intent_id)
        goal_rule_count += len(item.get("goal_rules", []))
        for step in item.get("route", []):
            function_id = str(step.get("function_id", ""))
            referenced_functions.add(function_id)
            route_step_count += 1
            if function_id not in function_ids:
                findings.append(QualityFinding("error", "unknown_route_function", intent_id, function_id))
        for function_id in item.get("avoid_functions", []):
            function_id = str(function_id)
            referenced_functions.add(function_id)
            if function_id not in function_ids:
                findings.append(QualityFinding("error", "unknown_avoid_function", intent_id, function_id))

    pattern_collisions = [
        {"normalized": normalized, "intent_ids": sorted(ids)}
        for normalized, ids in sorted(intent_pattern_keys.items())
        if normalized and len(ids) > 1
    ]
    for collision in pattern_collisions:
        findings.append(
            QualityFinding(
                "warning",
                "goal_pattern_collision",
                collision["normalized"],
                "The exact normalized goal pattern maps to multiple intents.",
                tuple(collision["intent_ids"]),
            )
        )

    orphan_functions = sorted(function_ids - referenced_functions)
    required_domains = {str(value) for value in policy.get("required_domains", [])}
    missing_domains = sorted(required_domains - set(domain_counts))
    for domain in missing_domains:
        findings.append(QualityFinding("error", "missing_required_domain", domain, "Required domain is absent."))

    totals = {
        "function_count": len(functions),
        "intent_count": len(intents),
        "alias_count": alias_count,
        "context_count": context_count,
        "intent_pattern_count": intent_pattern_count,
        "goal_rule_count": goal_rule_count,
        "route_step_count": route_step_count,
        "role_hint_count": role_hint_count,
        "state_cue_count": state_cue_count,
        "risk_cue_count": risk_cue_count,
        "official_source_count": len(official_sources),
        "sourced_function_count": sourced_function_count,
        "domain_count": len(domain_counts),
    }
    ratios = {
        "positive_context_function_rate": _ratio(functions_with_positive, len(functions)),
        "negative_context_function_rate": _ratio(functions_with_negative, len(functions)),
        "state_cue_function_rate": _ratio(functions_with_state_cues, len(functions)),
        "risk_cue_function_rate": _ratio(functions_with_risk_cues, len(functions)),
        "orphan_function_rate": _ratio(len(orphan_functions), len(functions)),
    }
    _apply_threshold_findings(totals, ratios, policy, findings)
    severity_counts = Counter(finding.severity for finding in findings)
    score = _quality_score(totals, ratios, severity_counts, policy)
    status = "fail" if severity_counts["error"] else "pass"
    return {
        "schema_version": 1,
        "catalog_version": str(payload.get("catalog_version", "")),
        "status": status,
        "quality_score": score,
        "totals": totals,
        "ratios": ratios,
        "domains": dict(sorted(domain_counts.items())),
        "risk_levels": dict(sorted(risk_counts.items())),
        "automation_policies": dict(sorted(policy_counts.items())),
        "aliases_by_locale": dict(sorted(locale_alias_counts.items())),
        "orphan_functions": orphan_functions,
        "duplicate_aliases": [
            {"function_id": function_id, "locale": locale, "value": value}
            for function_id, locale, value in duplicate_aliases
        ],
        "alias_collisions": collisions,
        "duplicate_goal_patterns": [
            {"intent_id": intent_id, "value": value} for intent_id, value in duplicate_patterns
        ],
        "goal_pattern_collisions": pattern_collisions,
        "missing_required_domains": missing_domains,
        "severity_counts": dict(sorted(severity_counts.items())),
        "findings": [asdict(finding) for finding in findings],
        "policy": policy,
    }


def normalize_catalog_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(character if (character.isalpha() or character.isdigit()) else " " for character in value).split())


def render_catalog_quality_markdown(report: dict[str, Any]) -> str:
    totals = report["totals"]
    ratios = report["ratios"]
    lines = [
        "# Navigation Catalog Quality Audit",
        "",
        f"- Status: **{report['status'].upper()}**",
        f"- Catalog: `{report['catalog_version']}`",
        f"- Quality score: **{float(report['quality_score']):.1f}/100**",
        f"- Functions / intents: **{totals['function_count']} / {totals['intent_count']}**",
        f"- Aliases / contexts: **{totals['alias_count']} / {totals['context_count']}**",
        f"- Goal patterns / rules: **{totals['intent_pattern_count']} / {totals['goal_rule_count']}**",
        f"- Domains: **{totals['domain_count']}**",
        f"- Orphan function rate: **{float(ratios['orphan_function_rate']):.1%}**",
        "",
        "## Domains",
        "",
    ]
    lines.extend(f"- `{domain}`: {count}" for domain, count in report["domains"].items())
    lines.extend(["", "## Findings", ""])
    findings = list(report.get("findings", []))
    if not findings:
        lines.append("- No findings.")
    for finding in findings[:200]:
        evidence = ", ".join(f"`{value}`" for value in finding.get("evidence", []))
        suffix = f" ({evidence})" if evidence else ""
        lines.append(
            f"- **{str(finding['severity']).upper()}** `{finding['code']}` "
            f"`{finding['subject']}` — {finding['message']}{suffix}"
        )
    return "\n".join(lines) + "\n"


def _load_policy(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _stops_before_activation(item: dict[str, Any]) -> bool:
    if str(item.get("automation_policy", "")) != "never_auto":
        return True
    return str(item.get("stop_policy", "before_activation")) in {
        "before_action",
        "before_activation",
        "stop_before_action",
        "user_confirmation",
        "user_only",
    }


def _apply_threshold_findings(
    totals: dict[str, int],
    ratios: dict[str, float],
    policy: dict[str, Any],
    findings: list[QualityFinding],
) -> None:
    for name, minimum in policy.get("minimum_totals", {}).items():
        actual = int(totals.get(str(name), 0))
        if actual < int(minimum):
            findings.append(
                QualityFinding("error", "minimum_total_not_met", str(name), f"Expected >= {minimum}, got {actual}.")
            )
    for name, minimum in policy.get("minimum_ratios", {}).items():
        actual = float(ratios.get(str(name), 0.0))
        if actual < float(minimum):
            findings.append(
                QualityFinding("error", "minimum_ratio_not_met", str(name), f"Expected >= {minimum:.3f}, got {actual:.3f}.")
            )
    for name, maximum in policy.get("maximum_ratios", {}).items():
        actual = float(ratios.get(str(name), 0.0))
        if actual > float(maximum):
            findings.append(
                QualityFinding("error", "maximum_ratio_exceeded", str(name), f"Expected <= {maximum:.3f}, got {actual:.3f}.")
            )


def _quality_score(
    totals: dict[str, int],
    ratios: dict[str, float],
    severity_counts: Counter[str],
    policy: dict[str, Any],
) -> float:
    coverage_components: list[float] = []
    for name, target in policy.get("minimum_totals", {}).items():
        coverage_components.append(min(1.0, int(totals.get(str(name), 0)) / max(1, int(target))))
    for name, target in policy.get("minimum_ratios", {}).items():
        coverage_components.append(min(1.0, float(ratios.get(str(name), 0.0)) / max(0.0001, float(target))))
    coverage = sum(coverage_components) / len(coverage_components) if coverage_components else 1.0
    penalty = severity_counts["error"] * 8.0 + severity_counts["warning"] * 0.12
    return round(max(0.0, min(100.0, coverage * 100.0 - penalty)), 2)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 6) if denominator else 0.0
