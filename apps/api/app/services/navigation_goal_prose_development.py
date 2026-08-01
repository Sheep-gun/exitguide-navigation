from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from app.services.navigation_function_catalog import NavigationFunctionCatalog, _normalize


_GENERIC_UI_ROLES = frozenset(
    {
        "button",
        "heading",
        "image",
        "image_button",
        "link",
        "menu",
        "menuitem",
        "switch",
        "tab",
        "text",
        "textbox",
    }
)
_GENERIC_METADATA_VALUES = frozenset(
    {
        "active",
        "available",
        "button",
        "continue",
        "destination",
        "disabled",
        "enabled",
        "error",
        "loading",
        "menu",
        "offline",
        "open",
        "ready",
        "services",
        "visible",
    }
)


@dataclass(frozen=True)
class CatalogDerivedProseCase:
    """One development-only case whose text is produced from catalog fields."""

    case_id: str
    category: str
    goal_text: str
    intent_id: str
    raw_terminal_function: str
    risk_level: str


@dataclass(frozen=True)
class _TargetProfile:
    intent_id: str
    terminal_function: str
    risk_level: str
    target: str
    role: str
    asset: str
    state: str
    avoid_function_ids: tuple[str, ...]


@dataclass(frozen=True)
class _GovernanceProfile:
    intent_id: str
    terminal_function: str
    risk_level: str
    target: str
    role: str
    asset: str
    state: str
    jurisdiction: str


def validate_catalog_derived_prose_policy(payload: Mapping[str, object]) -> None:
    """Reject any policy that could be mistaken for independent evidence."""

    required_metadata = {
        "catalog_derived": True,
        "tuning_allowed": True,
        "independent_accuracy_evidence": False,
    }
    for key, expected in required_metadata.items():
        if payload.get(key) is not expected:
            raise ValueError(f"development prose policy requires {key}={expected!r}")
    if str(payload.get("split", "")) != "development":
        raise ValueError("development prose policy must use split=development")
    templates = payload.get("templates")
    if not isinstance(templates, Mapping):
        raise ValueError("development prose policy templates must be an object")
    required_categories = {
        "long_prose",
        "role",
        "asset",
        "lifecycle_state",
        "negation",
        "decoy_clause",
    }
    if set(templates) != required_categories:
        raise ValueError("development prose policy must define the six reviewed categories")
    for category, template in templates.items():
        text = str(template)
        if "{target}" not in text:
            raise ValueError(f"template {category} must contain {{target}}")


def validate_catalog_derived_governance_policy(
    payload: Mapping[str, object],
) -> None:
    """Validate a development-only role/asset/state prose generator policy."""

    required_metadata = {
        "catalog_derived": True,
        "tuning_allowed": True,
        "independent_accuracy_evidence": False,
    }
    for key, expected in required_metadata.items():
        if payload.get(key) is not expected:
            raise ValueError(
                f"governance prose policy requires {key}={expected!r}"
            )
    if str(payload.get("split", "")) != "development":
        raise ValueError("governance prose policy must use split=development")
    scope = payload.get("intent_scope")
    if not isinstance(scope, Mapping):
        raise ValueError("governance prose policy intent_scope must be an object")
    prefix = str(scope.get("intent_id_prefix", "")).strip()
    exact_intents = int(scope.get("exact_intents", 0))
    if not prefix or exact_intents <= 0:
        raise ValueError(
            "governance prose policy requires an intent prefix and exact intent count"
        )
    templates = payload.get("templates")
    if not isinstance(templates, Mapping):
        raise ValueError("governance prose policy templates must be an object")
    required_categories = {
        "role_clause",
        "asset_clause",
        "state_clause",
        "jurisdiction_clause",
        "purpose_clause",
    }
    if set(templates) != required_categories:
        raise ValueError(
            "governance prose policy must define the five reviewed clause categories"
        )
    required_placeholders = ("role", "asset", "state", "jurisdiction", "target")
    for category, template in templates.items():
        text = str(template)
        missing = [
            placeholder
            for placeholder in required_placeholders
            if "{" + placeholder + "}" not in text
        ]
        if missing:
            raise ValueError(
                f"template {category} is missing governance placeholders: {missing}"
            )


def generate_catalog_derived_prose_cases(
    *,
    catalog_payload: Mapping[str, object],
    policy_payload: Mapping[str, object],
) -> tuple[CatalogDerivedProseCase, ...]:
    """Generate deterministic prose cases from canonical catalog metadata only.

    No generated sentence is persisted into the runtime catalog or presented as
    independent evidence.  Stable spread sampling prevents the development unit
    from becoming dominated by adjacent catalog domains.
    """

    validate_catalog_derived_prose_policy(policy_payload)
    raw_functions = catalog_payload.get("functions", [])
    raw_intents = catalog_payload.get("intents", [])
    if not isinstance(raw_functions, list) or not isinstance(raw_intents, list):
        raise ValueError("catalog functions and intents must be lists")
    functions = {
        str(item.get("function_id", "")): item
        for item in raw_functions
        if isinstance(item, Mapping) and str(item.get("function_id", ""))
    }
    terminal_counts = Counter(
        str(item.get("terminal_function", ""))
        for item in raw_intents
        if isinstance(item, Mapping)
    )
    phrase_counts = _catalog_anchor_counts(functions.values())

    profiles: list[_TargetProfile] = []
    for raw_intent in raw_intents:
        if not isinstance(raw_intent, Mapping):
            continue
        intent_id = str(raw_intent.get("intent_id", "")).strip()
        terminal = str(raw_intent.get("terminal_function", "")).strip()
        definition = functions.get(terminal)
        if not intent_id or definition is None or terminal_counts[terminal] != 1:
            continue
        target = _select_unique_anchor(definition, phrase_counts)
        if not target:
            continue
        profiles.append(
            _TargetProfile(
                intent_id=intent_id,
                terminal_function=terminal,
                risk_level=str(definition.get("risk_level", "low")),
                target=target,
                role=_select_role(definition.get("role_hints")),
                asset=_asset_name(definition),
                state=_select_state(definition.get("state_cues")),
                avoid_function_ids=tuple(
                    str(value)
                    for value in raw_intent.get("avoid_functions", [])
                    if str(value) in functions and str(value) != terminal
                ),
            )
        )

    if not profiles:
        raise ValueError("catalog does not provide eligible prose targets")
    templates = policy_payload["templates"]
    assert isinstance(templates, Mapping)
    limit = max(1, int(policy_payload.get("cases_per_category", 40)))
    cases: list[CatalogDerivedProseCase] = []

    def append_category(category: str, eligible: Sequence[_TargetProfile]) -> None:
        for ordinal, profile in enumerate(_spread(eligible, limit)):
            decoy = _decoy_anchor(
                profile=profile,
                ordinal=ordinal,
                profiles=profiles,
                functions=functions,
                phrase_counts=phrase_counts,
            )
            values = {
                "target": profile.target,
                "role": profile.role,
                "asset": profile.asset,
                "state": profile.state,
                "decoy": decoy,
            }
            goal_text = str(templates[category]).format_map(values)
            cases.append(
                CatalogDerivedProseCase(
                    case_id=f"{category}-{ordinal:03d}",
                    category=category,
                    goal_text=goal_text,
                    intent_id=profile.intent_id,
                    raw_terminal_function=profile.terminal_function,
                    risk_level=profile.risk_level,
                )
            )

    append_category("long_prose", profiles)
    append_category("role", [profile for profile in profiles if profile.role])
    append_category("asset", [profile for profile in profiles if profile.asset])
    append_category(
        "lifecycle_state",
        [profile for profile in profiles if profile.state],
    )
    append_category(
        "negation",
        [profile for profile in profiles if profile.avoid_function_ids],
    )
    append_category("decoy_clause", profiles)
    return tuple(cases)


def generate_catalog_derived_governance_prose_cases(
    *,
    catalog_payload: Mapping[str, object],
    policy_payload: Mapping[str, object],
) -> tuple[CatalogDerivedProseCase, ...]:
    """Generate one five-dimension prose case for every scoped catalog intent.

    The five generic templates rotate evenly across the selected intents, but
    every sentence contains role, governed asset, lifecycle state,
    jurisdiction, and purpose clauses.  All inserted values come from the
    canonical catalog; no evaluation sentence or runtime rule is persisted.
    """

    validate_catalog_derived_governance_policy(policy_payload)
    raw_functions = catalog_payload.get("functions", [])
    raw_intents = catalog_payload.get("intents", [])
    if not isinstance(raw_functions, list) or not isinstance(raw_intents, list):
        raise ValueError("catalog functions and intents must be lists")
    functions = {
        str(item.get("function_id", "")): item
        for item in raw_functions
        if isinstance(item, Mapping) and str(item.get("function_id", ""))
    }
    terminal_counts = Counter(
        str(item.get("terminal_function", ""))
        for item in raw_intents
        if isinstance(item, Mapping)
    )
    phrase_counts = _catalog_anchor_counts(functions.values())
    scope = policy_payload["intent_scope"]
    assert isinstance(scope, Mapping)
    prefix = str(scope["intent_id_prefix"])
    exact_intents = int(scope["exact_intents"])

    profiles: list[_GovernanceProfile] = []
    for raw_intent in raw_intents:
        if not isinstance(raw_intent, Mapping):
            continue
        intent_id = str(raw_intent.get("intent_id", "")).strip()
        if not intent_id.startswith(prefix):
            continue
        terminal = str(raw_intent.get("terminal_function", "")).strip()
        definition = functions.get(terminal)
        if definition is None or terminal_counts[terminal] != 1:
            raise ValueError(f"scoped intent has no unique terminal: {intent_id}")
        profile = _GovernanceProfile(
            intent_id=intent_id,
            terminal_function=terminal,
            risk_level=str(definition.get("risk_level", "low")),
            target=_select_unique_anchor(definition, phrase_counts),
            role=_select_role(definition.get("role_hints")),
            asset=_select_metadata_value(definition.get("asset_cues")),
            state=_select_state_group(definition.get("state_cues"), "lifecycle"),
            jurisdiction=_select_state_group(
                definition.get("state_cues"), "jurisdiction"
            ),
        )
        missing = [
            field
            for field in ("target", "role", "asset", "state", "jurisdiction")
            if not getattr(profile, field)
        ]
        if missing:
            raise ValueError(
                f"scoped intent lacks governance prose metadata: {intent_id}:{missing}"
            )
        profiles.append(profile)

    if len(profiles) != exact_intents:
        raise ValueError(
            f"governance prose scope must contain exactly {exact_intents} intents; "
            f"got {len(profiles)}"
        )
    templates = policy_payload["templates"]
    assert isinstance(templates, Mapping)
    categories = tuple(sorted(str(value) for value in templates))
    cases: list[CatalogDerivedProseCase] = []
    for ordinal, profile in enumerate(profiles):
        category = categories[ordinal % len(categories)]
        goal_text = str(templates[category]).format_map(
            {
                "target": profile.target,
                "role": profile.role,
                "asset": profile.asset,
                "state": profile.state,
                "jurisdiction": profile.jurisdiction,
            }
        )
        cases.append(
            CatalogDerivedProseCase(
                case_id=f"governance-{category}-{ordinal:03d}",
                category=category,
                goal_text=goal_text,
                intent_id=profile.intent_id,
                raw_terminal_function=profile.terminal_function,
                risk_level=profile.risk_level,
            )
        )
    return tuple(cases)


def evaluate_catalog_derived_prose_cases(
    catalog: NavigationFunctionCatalog,
    cases: Iterable[CatalogDerivedProseCase],
) -> dict[str, object]:
    """Return aggregate-only development diagnostics, never case failures."""

    totals: Counter[str] = Counter()
    correct: Counter[str] = Counter()
    generic: Counter[str] = Counter()
    preserved_terminal: Counter[str] = Counter()
    for case in cases:
        plan = catalog.plan_goal(case.goal_text)
        totals[case.category] += 1
        if plan.intent == case.intent_id:
            correct[case.category] += 1
        if plan.intent == "generic_navigation":
            generic[case.category] += 1
        if (
            plan.raw_terminal_function == case.raw_terminal_function
            and plan.terminal_function
            == catalog.canonical_function_id(case.raw_terminal_function)
        ):
            preserved_terminal[case.category] += 1
    categories = {
        category: {
            "total": totals[category],
            "correct": correct[category],
            "generic": generic[category],
            "logical_terminal_correct": preserved_terminal[category],
        }
        for category in sorted(totals)
    }
    total = sum(totals.values())
    total_correct = sum(correct.values())
    return {
        "catalog_derived": True,
        "tuning_allowed": True,
        "independent_accuracy_evidence": False,
        "total": total,
        "correct": total_correct,
        "generic": sum(generic.values()),
        "logical_terminal_correct": sum(preserved_terminal.values()),
        "accuracy": round(total_correct / total, 6) if total else 0.0,
        "categories": categories,
    }


def _catalog_anchor_counts(
    definitions: Iterable[Mapping[str, object]],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for definition in definitions:
        counts.update(
            {
                normalized
                for value in _anchor_values(definition)
                if (normalized := _normalize(value))
            }
        )
    return counts


def _anchor_values(definition: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    aliases = definition.get("aliases", {})
    if isinstance(aliases, Mapping):
        for locale in sorted(aliases, key=lambda value: ("en" not in str(value).lower(), str(value))):
            raw_values = aliases[locale]
            items = raw_values if isinstance(raw_values, list) else [raw_values]
            values.extend(str(item).strip() for item in items if str(item).strip())
    values.extend(
        str(definition.get(key, "")).strip()
        for key in ("name_en", "name_ko")
        if str(definition.get(key, "")).strip()
    )
    return tuple(dict.fromkeys(values))


def _select_unique_anchor(
    definition: Mapping[str, object],
    phrase_counts: Mapping[str, int],
) -> str:
    candidates = []
    for ordinal, value in enumerate(_anchor_values(definition)):
        normalized = _normalize(value)
        tokens = value.split()
        if (
            phrase_counts.get(normalized, 0) != 1
            or len(normalized) < 5
            or len(value) > 72
            or normalized in _GENERIC_METADATA_VALUES
        ):
            continue
        specificity = min(6, len(tokens)) * 12 + min(72, len(normalized))
        ascii_bonus = 4 if value.isascii() else 0
        candidates.append((specificity + ascii_bonus, -ordinal, value))
    return max(candidates, default=(0, 0, ""))[2]


def _select_role(raw_roles: object) -> str:
    if not isinstance(raw_roles, list):
        return ""
    roles = [
        str(role).strip()
        for role in raw_roles
        if str(role).strip().casefold() not in _GENERIC_UI_ROLES
        and len(str(role).strip()) >= 4
    ]
    return max(roles, key=lambda value: (len(value.split()), len(value), value), default="")


def _asset_name(definition: Mapping[str, object]) -> str:
    domain = str(definition.get("domain", "")).replace("_", " ").strip()
    if len(domain) < 4 or domain.casefold() in _GENERIC_METADATA_VALUES:
        return ""
    return domain


def _select_state(raw_state_cues: object) -> str:
    if not isinstance(raw_state_cues, Mapping):
        return ""
    ranked: list[tuple[int, int, str]] = []
    for raw_group, raw_values in raw_state_cues.items():
        group = str(raw_group).casefold()
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        for raw_value in values:
            value = str(raw_value).strip()
            normalized = value.casefold()
            if len(value) < 4 or normalized in _GENERIC_METADATA_VALUES or len(value) > 64:
                continue
            group_priority = 2 if group in {"lifecycle", "state", "status"} else 1
            ranked.append((group_priority, len(value), value))
    return max(ranked, default=(0, 0, ""))[2]


def _select_metadata_value(raw_value: object) -> str:
    if raw_value is None:
        items = []
    elif isinstance(raw_value, Mapping):
        items = [
            item
            for value in raw_value.values()
            for item in (
                value if isinstance(value, (list, tuple, set)) else [value]
            )
        ]
    else:
        items = (
            raw_value
            if isinstance(raw_value, (list, tuple, set))
            else [raw_value]
        )
    candidates = [
        str(item).strip()
        for item in items
        if item is not None
        and 4 <= len(str(item).strip()) <= 96
        and str(item).strip().casefold() not in _GENERIC_METADATA_VALUES
    ]
    return max(
        candidates,
        key=lambda value: (len(value.split()), len(value), value),
        default="",
    )


def _select_state_group(raw_state_cues: object, group: str) -> str:
    if not isinstance(raw_state_cues, Mapping):
        return ""
    for raw_group, raw_values in raw_state_cues.items():
        if str(raw_group).casefold() == group.casefold():
            return _select_metadata_value(raw_values)
    return ""


def _decoy_anchor(
    *,
    profile: _TargetProfile,
    ordinal: int,
    profiles: Sequence[_TargetProfile],
    functions: Mapping[str, Mapping[str, object]],
    phrase_counts: Mapping[str, int],
) -> str:
    for function_id in profile.avoid_function_ids:
        value = _select_unique_anchor(functions[function_id], phrase_counts)
        if value and _normalize(value) != _normalize(profile.target):
            return value
    start = (profiles.index(profile) + 97 + ordinal * 17) % len(profiles)
    target_domain = str(functions[profile.terminal_function].get("domain", ""))
    for offset in range(len(profiles)):
        candidate = profiles[(start + offset) % len(profiles)]
        candidate_domain = str(functions[candidate.terminal_function].get("domain", ""))
        if candidate.intent_id != profile.intent_id and candidate_domain != target_domain:
            return candidate.target
    return "an unrelated destination"


def _spread(values: Sequence[_TargetProfile], limit: int) -> tuple[_TargetProfile, ...]:
    if len(values) <= limit:
        return tuple(values)
    # Integer midpoint sampling is deterministic, covers both ends of catalog
    # growth, and never selects the same profile twice.
    indices = [((2 * index + 1) * len(values)) // (2 * limit) for index in range(limit)]
    return tuple(values[index] for index in indices)
