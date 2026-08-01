from __future__ import annotations

"""Catalog-derived stress tests for exact UI-label collisions.

The navigation catalog intentionally reuses short labels such as ``파일``,
``메시지``, and ``구매 취소`` across different products and domains.  This
module turns every exact, same-locale alias collision into deterministic
positive-context and negative-context probes against the real runtime matcher.

The probes are catalog-derived and therefore do *not* claim independent app
accuracy.  Their job is narrower: make sure the context metadata stored in the
database is actually strong enough to resolve the ambiguity it declares.
"""

import json
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from app.services.navigation_catalog_quality import normalize_catalog_text
from app.services.navigation_function_catalog import NavigationFunctionCatalog


def evaluate_alias_collisions(
    *,
    catalog_path: Path,
    maximum_groups: int = 0,
) -> dict[str, Any]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    functions = {
        str(item["function_id"]): item
        for item in payload.get("functions", [])
    }
    aliases: dict[tuple[str, str], set[str]] = defaultdict(set)
    raw_aliases: dict[tuple[str, str], set[str]] = defaultdict(set)
    for function_id, function in functions.items():
        for locale, values in _mapping_lists(function.get("aliases", {})):
            normalized_locale = str(locale).casefold()
            for raw_value in values:
                phrase = str(raw_value).strip()
                normalized = normalize_catalog_text(phrase)
                if not normalized:
                    continue
                key = (normalized_locale, normalized)
                aliases[key].add(function_id)
                raw_aliases[key].add(phrase)

    collision_groups = [
        (key, tuple(sorted(owners)))
        for key, owners in aliases.items()
        if len(owners) >= 2
    ]
    collision_groups.sort(key=lambda item: (-len(item[1]), item[0][0], item[0][1]))
    total_group_count = len(collision_groups)
    if maximum_groups > 0:
        collision_groups = collision_groups[:maximum_groups]

    positive_probes: list[dict[str, Any]] = []
    negative_probes: list[dict[str, Any]] = []
    unresolved_context_owners: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="egl-alias-robustness-") as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "catalog.sqlite",
            catalog_path,
        )
        for (locale, normalized_alias), owners in collision_groups:
            label = sorted(
                raw_aliases[(locale, normalized_alias)],
                key=lambda value: (len(value), value.casefold(), value),
            )[0]
            positive_owners = _context_owners(functions, owners, "positive_context")
            negative_owners = _context_owners(functions, owners, "negative_context")
            for expected_function in owners:
                positive_contexts = [
                    value
                    for value in _string_values(functions[expected_function].get("positive_context", []))
                    if positive_owners.get(normalize_catalog_text(value)) == {expected_function}
                ]
                if not positive_contexts:
                    unresolved_context_owners.append(
                        {
                            "locale": locale,
                            "alias": label,
                            "normalized_alias": normalized_alias,
                            "expected_function": expected_function,
                            "collision_functions": list(owners),
                            "reason": "no_owner_unique_positive_context",
                        }
                    )
                else:
                    nearby_text = _best_context(positive_contexts)
                    matches = catalog.match_candidate(
                        label=label,
                        nearby_text=nearby_text,
                        role="menuitem",
                        locale=locale,
                        limit=max(8, len(owners) + 2),
                    )
                    actual_function = matches[0].function_id if matches else ""
                    expected_canonical = catalog.canonical_function_id(
                        expected_function
                    )
                    positive_probes.append(
                        {
                            "locale": locale,
                            "alias": label,
                            "normalized_alias": normalized_alias,
                            "nearby_text": nearby_text,
                            "expected_function": expected_function,
                            "expected_canonical_function": expected_canonical,
                            "actual_function": actual_function,
                            "collision_functions": list(owners),
                            "correct": actual_function == expected_canonical,
                            "top_score": matches[0].score if matches else 0.0,
                        }
                    )

                negative_contexts = _string_values(
                    functions[expected_function].get("negative_context", [])
                )
                # Shared generated guards cannot distinguish the rejected
                # owner from an alternative.  Keep only negative evidence
                # unique within this exact-alias collision group; otherwise
                # the probe would penalize the expected alternative too.
                negative_contexts = [
                    value
                    for value in negative_contexts
                    if negative_owners.get(normalize_catalog_text(value))
                    == {expected_function}
                ]
                if not negative_contexts:
                    continue
                rejected_context = _best_context(negative_contexts)
                # A negative phrase alone does not identify which colliding
                # owner *should* win.  Pair it with owner-unique positive
                # evidence for every alternative and require that exact owner.
                # This makes the probe contrastive instead of merely checking
                # that an arbitrary different function happened to rank first.
                for alternative_function in owners:
                    if alternative_function == expected_function:
                        continue
                    rejected_canonical = catalog.canonical_function_id(
                        expected_function
                    )
                    alternative_canonical = catalog.canonical_function_id(
                        alternative_function
                    )
                    # Two physical IDs in one reviewed equivalence class are
                    # not a negative contrast. Runtime correctly returns their
                    # shared logical destination, so do not manufacture a
                    # rejection requirement between them.
                    if alternative_canonical == rejected_canonical:
                        continue
                    alternative_contexts = [
                        value
                        for value in _string_values(
                            functions[alternative_function].get("positive_context", [])
                        )
                        if positive_owners.get(normalize_catalog_text(value))
                        == {alternative_function}
                    ]
                    if not alternative_contexts:
                        continue
                    alternative_context = _best_context(alternative_contexts)
                    nearby_text = f"{alternative_context} {rejected_context}".strip()
                    matches = catalog.match_candidate(
                        label=label,
                        nearby_text=nearby_text,
                        role="menuitem",
                        locale=locale,
                        limit=max(8, len(owners) + 2),
                    )
                    actual_function = matches[0].function_id if matches else ""
                    negative_probes.append(
                        {
                            "locale": locale,
                            "alias": label,
                            "normalized_alias": normalized_alias,
                            "nearby_text": nearby_text,
                            "rejected_function": expected_function,
                            "expected_function": alternative_function,
                            "expected_canonical_function": alternative_canonical,
                            "actual_function": actual_function,
                            "collision_functions": list(owners),
                            "correct": actual_function == alternative_canonical,
                            "top_score": matches[0].score if matches else 0.0,
                        }
                    )

    positive_correct = sum(bool(item["correct"]) for item in positive_probes)
    negative_correct = sum(bool(item["correct"]) for item in negative_probes)
    selected_cross_domain = sum(
        len({str(functions[owner].get("domain", "")) for owner in owners}) > 1
        for _key, owners in collision_groups
    )
    return {
        "schema_version": 1,
        "catalog_version": str(payload.get("catalog_version", "")),
        "catalog_derived": True,
        "independent_accuracy_claim": False,
        "purpose": "Verify that declared context metadata resolves exact same-locale UI alias collisions.",
        "total_collision_group_count": total_group_count,
        "evaluated_collision_group_count": len(collision_groups),
        "cross_domain_collision_group_count": selected_cross_domain,
        "maximum_groups": max(0, int(maximum_groups)),
        "positive": {
            "total": len(positive_probes),
            "correct": positive_correct,
            "accuracy": _ratio(positive_correct, len(positive_probes)),
            "failures": [item for item in positive_probes if not item["correct"]],
        },
        "negative_rejection": {
            "total": len(negative_probes),
            "correct": negative_correct,
            "accuracy": _ratio(negative_correct, len(negative_probes)),
            "failures": [item for item in negative_probes if not item["correct"]],
        },
        "unresolved_context_owners": unresolved_context_owners,
    }


def _mapping_lists(value: object) -> Iterable[tuple[str, list[object]]]:
    if not isinstance(value, dict):
        return ()
    return (
        (str(key), list(items))
        for key, items in value.items()
        if isinstance(items, list)
    )


def _string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _context_owners(
    functions: dict[str, dict[str, Any]],
    owners: tuple[str, ...],
    field: str,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for function_id in owners:
        for value in _string_values(functions[function_id].get(field, [])):
            normalized = normalize_catalog_text(value)
            if normalized:
                result[normalized].add(function_id)
    return result


def _best_context(values: list[str]) -> str:
    return sorted(
        set(values),
        key=lambda value: (-len(normalize_catalog_text(value)), normalize_catalog_text(value), value),
    )[0]


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0
