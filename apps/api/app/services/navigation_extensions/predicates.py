from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class PredicateError(ValueError):
    pass


def fact_value(facts: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = facts
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def evaluate_predicate(expression: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    """Evaluate a small, data-only predicate language without Python eval."""

    if not isinstance(expression, Mapping) or len(expression) != 1:
        raise PredicateError("predicate must contain exactly one operator")
    operator, payload = next(iter(expression.items()))

    if operator in {"all", "any"}:
        if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
            raise PredicateError(f"{operator} requires a list")
        values = [evaluate_predicate(item, facts) for item in payload]
        return all(values) if operator == "all" else any(values)
    if operator == "not":
        if not isinstance(payload, Mapping):
            raise PredicateError("not requires one predicate")
        return not evaluate_predicate(payload, facts)

    if not isinstance(payload, Mapping):
        raise PredicateError(f"{operator} requires an object")
    path = str(payload.get("fact", ""))
    if not path:
        raise PredicateError(f"{operator} requires fact")
    exists, value = fact_value(facts, path)

    if operator == "exists":
        return exists
    if operator == "missing":
        return not exists
    if operator == "truthy":
        return exists and bool(value)
    if operator == "equals":
        return exists and value == payload.get("value")
    if operator == "not_equals":
        return exists and value != payload.get("value")
    if operator == "in":
        choices = payload.get("values")
        if not isinstance(choices, list):
            raise PredicateError("in requires values list")
        return exists and value in choices
    if operator == "not_in":
        choices = payload.get("values")
        if not isinstance(choices, list):
            raise PredicateError("not_in requires values list")
        return exists and value not in choices

    raise PredicateError(f"unsupported predicate operator: {operator}")


def all_conditions(
    conditions: Sequence[Mapping[str, Any]],
    facts: Mapping[str, Any],
) -> bool:
    return all(evaluate_predicate(condition, facts) for condition in conditions)
