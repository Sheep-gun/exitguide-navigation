from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from itertools import combinations, product
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from app.config import Settings
from app.schemas import UniversalNavigationObserveRequest, UniversalNavigationObserveResponse
from app.services.navigation_function_catalog import NavigationFunctionCatalog
from app.services.navigation_semantics import infer_goal_plan
from app.services.universal_navigation_agent import observe_universal_navigation
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


FAILURE_TYPES = {
    "goal_interpretation_failure",
    "alias_gap",
    "missing_gateway",
    "semantic_ambiguity",
    "advertisement_decoy",
    "premature_destination",
    "destination_missed",
    "safe_menu_not_explored",
    "unnecessary_scroll",
    "wrong_backtrack",
    "wrong_menu",
    "unsafe_action_attempt",
    "route_reuse_failure",
    "expected_scroll_missed",
    "expected_back_missed",
}


@dataclass(frozen=True)
class GymElement:
    id: str
    label: str = ""
    role: str = "button"
    view_id: str = ""
    content_description: str = ""
    clickable: bool = True
    enabled: bool = True
    visible: bool = True
    scrollable: bool = False
    checkable: bool = False
    checked: bool | None = None
    selected: bool = False
    password: bool = False
    dangerous: bool = False
    decoy_kind: str = ""


@dataclass(frozen=True)
class GymStep:
    step_id: str
    screen_title: str
    elements: tuple[GymElement, ...]
    expected_action: str
    expected_label: str | None
    expected_function: str
    stage: str
    activity_name: str = "NavigationDbGymActivity"
    ui_surface: str = "screen"
    screen_state: str = "ready"


@dataclass(frozen=True)
class GymCase:
    case_id: str
    split: str
    intent_id: str
    goal_text: str
    locale: str
    user_state: str
    tags: tuple[str, ...]
    steps: tuple[GymStep, ...]
    app_package: str = ""
    app_version: str = "1.0"
    device_model: str = "synthetic-device"
    android_version: str = "synthetic"
    orientation: str = "portrait"
    source_kind: str = "fixed_independent"
    tuning_allowed: bool = True


@dataclass
class GymFailure:
    case_id: str
    split: str
    goal_text: str
    step_id: str
    failure_type: str
    expected_action: str
    expected_label: str | None
    expected_function: str
    actual_action: str
    actual_label: str | None
    actual_phase: str
    goal_interpretation: str
    details: str
    tuning_allowed: bool = True


@dataclass(frozen=True)
class GymCaseResult:
    case_id: str
    split: str
    source_kind: str
    intent_id: str
    user_state: str
    tags: tuple[str, ...]
    app_package: str
    app_version: str
    device_model: str
    android_version: str
    orientation: str
    status: str
    gold_stage_count: int
    attempted_stage_count: int
    skipped_stage_count: int
    failed_step_id: str
    failure_type: str
    unsafe_clicks: int
    wrong_clicks: int


@dataclass
class GymMetrics:
    split: str
    case_count: int = 0
    case_success_count: int = 0
    case_failure_count: int = 0
    goal_interpretation_total: int = 0
    goal_interpretation_correct: int = 0
    independent_goal_interpretation_total: int = 0
    independent_goal_interpretation_correct: int = 0
    catalog_generated_goal_interpretation_total: int = 0
    catalog_generated_goal_interpretation_correct: int = 0
    gold_stage_count: int = 0
    stage_count: int = 0
    skipped_stage_count: int = 0
    action_total: int = 0
    action_correct: int = 0
    next_menu_total: int = 0
    next_menu_correct: int = 0
    scroll_total: int = 0
    scroll_correct: int = 0
    back_total: int = 0
    back_correct: int = 0
    destination_total: int = 0
    destination_correct: int = 0
    safe_stop_total: int = 0
    safe_stop_correct: int = 0
    unsafe_clicks: int = 0
    wrong_clicks: int = 0
    click_count: int = 0
    scroll_count: int = 0
    back_count: int = 0
    route_reuse_total: int = 0
    route_reuse_correct: int = 0
    latency_ms: list[float] = field(default_factory=list)
    destination_time_ms: list[float] = field(default_factory=list)
    decision_time_ms: list[float] = field(default_factory=list)
    cold_destination_time_ms: list[float] = field(default_factory=list)
    warm_destination_time_ms: list[float] = field(default_factory=list)
    fastest_routes: dict[str, dict[str, object]] = field(default_factory=dict)
    measurement_sources: set[str] = field(default_factory=set)
    intent_ids: set[str] = field(default_factory=set)
    function_ids: set[str] = field(default_factory=set)
    independent_intent_ids: set[str] = field(default_factory=set)
    independent_function_ids: set[str] = field(default_factory=set)
    fixed_independent_intent_ids: set[str] = field(default_factory=set)
    fixed_independent_function_ids: set[str] = field(default_factory=set)
    synthetic_independent_intent_ids: set[str] = field(default_factory=set)
    synthetic_independent_function_ids: set[str] = field(default_factory=set)
    catalog_generated_intent_ids: set[str] = field(default_factory=set)
    catalog_generated_function_ids: set[str] = field(default_factory=set)
    stages: set[str] = field(default_factory=set)
    source_kind_counts: dict[str, int] = field(default_factory=dict)
    dimension_values: dict[str, set[str]] = field(default_factory=dict)

    def payload(
        self,
        total_intents: int,
        total_functions: int = 0,
        dimension_universe: dict[str, Iterable[str]] | None = None,
        intent_universe: Iterable[str] | None = None,
        function_universe: Iterable[str] | None = None,
    ) -> dict[str, object]:
        expected_intents = {str(value) for value in (intent_universe or ()) if str(value)}
        expected_functions = {str(value) for value in (function_universe or ()) if str(value)}
        return {
            "split": self.split,
            "case_count": self.case_count,
            "case_success_count": self.case_success_count,
            "case_failure_count": self.case_failure_count,
            "case_success_rate": _ratio(self.case_success_count, self.case_count),
            "goal_interpretation_total": self.goal_interpretation_total,
            "goal_interpretation_correct": self.goal_interpretation_correct,
            "goal_interpretation_accuracy": _ratio(
                self.goal_interpretation_correct,
                self.goal_interpretation_total,
            ),
            "independent_goal_interpretation_accuracy": _ratio(
                self.independent_goal_interpretation_correct,
                self.independent_goal_interpretation_total,
            ),
            "independent_goal_interpretation_total": self.independent_goal_interpretation_total,
            "independent_goal_interpretation_correct": self.independent_goal_interpretation_correct,
            "catalog_generated_goal_interpretation_accuracy": _ratio(
                self.catalog_generated_goal_interpretation_correct,
                self.catalog_generated_goal_interpretation_total,
            ),
            "catalog_generated_goal_interpretation_total": self.catalog_generated_goal_interpretation_total,
            "catalog_generated_goal_interpretation_correct": self.catalog_generated_goal_interpretation_correct,
            "gold_stage_count": self.gold_stage_count,
            "stage_count": self.stage_count,
            "attempted_stage_count": self.stage_count,
            "skipped_stage_count": self.skipped_stage_count,
            "attempted_stage_rate": _ratio(self.stage_count, self.gold_stage_count),
            "expected_action_total": self.action_total,
            "expected_action_correct": self.action_correct,
            "next_menu_total": self.next_menu_total,
            "scroll_total": self.scroll_total,
            "scroll_correct": self.scroll_correct,
            "back_total": self.back_total,
            "back_correct": self.back_correct,
            "safe_stop_total": self.safe_stop_total,
            "safe_stop_correct": self.safe_stop_correct,
            "destination_total": self.destination_total,
            "route_reuse_total": self.route_reuse_total,
            "expected_action_accuracy": _ratio(self.action_correct, self.action_total),
            "next_menu_top1_accuracy": _ratio(self.next_menu_correct, self.next_menu_total),
            "scroll_action_accuracy": _ratio(self.scroll_correct, self.scroll_total),
            "back_action_accuracy": _ratio(self.back_correct, self.back_total),
            "destination_accuracy": _ratio(self.destination_correct, self.destination_total),
            "safe_stop_accuracy": _ratio(self.safe_stop_correct, self.safe_stop_total),
            "safe_stop_rate": _ratio(self.safe_stop_correct, self.safe_stop_total),
            "unsafe_click_rate": _ratio(self.unsafe_clicks, self.stage_count),
            "wrong_click_rate": _ratio(self.wrong_clicks, self.stage_count),
            "mean_clicks_per_case": _ratio(self.click_count, self.case_count),
            "mean_scrolls_per_case": _ratio(self.scroll_count, self.case_count),
            "mean_backs_per_case": _ratio(self.back_count, self.case_count),
            "mean_latency_ms": round(mean(self.latency_ms), 3) if self.latency_ms else 0.0,
            "time_to_destination_p50_ms": _percentile(self.destination_time_ms, 0.50),
            "time_to_destination_p90_ms": _percentile(self.destination_time_ms, 0.90),
            "decision_time_p50_ms": _percentile(self.decision_time_ms, 0.50),
            "decision_time_p90_ms": _percentile(self.decision_time_ms, 0.90),
            "success_within_10s_rate": _within_rate(self.destination_time_ms, 10_000.0),
            "success_within_30s_rate": _within_rate(self.destination_time_ms, 30_000.0),
            "success_within_60s_rate": _within_rate(self.destination_time_ms, 60_000.0),
            "cold_time_to_destination_p50_ms": _percentile(self.cold_destination_time_ms, 0.50),
            "warm_time_to_destination_p50_ms": _percentile(self.warm_destination_time_ms, 0.50),
            "cache_time_reduction_rate": _cache_reduction_rate(
                self.cold_destination_time_ms,
                self.warm_destination_time_ms,
            ),
            "route_reuse_rate": _ratio(self.route_reuse_correct, self.route_reuse_total),
            "intent_coverage": _ratio(len(self.intent_ids), total_intents),
            "function_coverage": _ratio(len(self.function_ids), total_functions),
            "independent_intent_coverage": _ratio(len(self.independent_intent_ids), total_intents),
            "independent_function_coverage": _ratio(len(self.independent_function_ids), total_functions),
            "fixed_independent_intent_coverage": _ratio(
                len(self.fixed_independent_intent_ids), total_intents
            ),
            "fixed_independent_function_coverage": _ratio(
                len(self.fixed_independent_function_ids), total_functions
            ),
            "synthetic_independent_intent_coverage": _ratio(
                len(self.synthetic_independent_intent_ids), total_intents
            ),
            "synthetic_independent_function_coverage": _ratio(
                len(self.synthetic_independent_function_ids), total_functions
            ),
            "catalog_generated_intent_coverage": _ratio(
                len(self.catalog_generated_intent_ids), total_intents
            ),
            "catalog_generated_function_coverage": _ratio(
                len(self.catalog_generated_function_ids), total_functions
            ),
            "covered_intents": sorted(self.intent_ids),
            "covered_functions": sorted(self.function_ids),
            "independent_covered_intents": sorted(self.independent_intent_ids),
            "independent_covered_functions": sorted(self.independent_function_ids),
            "fixed_independent_covered_intents": sorted(self.fixed_independent_intent_ids),
            "fixed_independent_covered_functions": sorted(self.fixed_independent_function_ids),
            "synthetic_independent_covered_intents": sorted(self.synthetic_independent_intent_ids),
            "synthetic_independent_covered_functions": sorted(self.synthetic_independent_function_ids),
            "catalog_generated_covered_intents": sorted(self.catalog_generated_intent_ids),
            "catalog_generated_covered_functions": sorted(self.catalog_generated_function_ids),
            "missing_intents": sorted(expected_intents.difference(self.intent_ids)),
            "missing_functions": sorted(expected_functions.difference(self.function_ids)),
            "independent_missing_intents": sorted(
                expected_intents.difference(self.independent_intent_ids)
            ),
            "independent_missing_functions": sorted(
                expected_functions.difference(self.independent_function_ids)
            ),
            "fixed_independent_missing_intents": sorted(
                expected_intents.difference(self.fixed_independent_intent_ids)
            ),
            "fixed_independent_missing_functions": sorted(
                expected_functions.difference(self.fixed_independent_function_ids)
            ),
            "covered_stages": sorted(self.stages),
            "source_kind_counts": dict(sorted(self.source_kind_counts.items())),
            "coverage_matrix": _dimension_coverage_matrix(
                self.dimension_values,
                dimension_universe or {},
            ),
            "measurement_sources": sorted(self.measurement_sources),
            "fastest_routes": sorted(
                self.fastest_routes.values(),
                key=lambda item: (float(item["time_to_destination_ms"]), str(item["app_package"])),
            )[:50],
        }


def load_fixed_cases(path: Path, *, split: str) -> list[GymCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixture_tuning_allowed = bool(payload.get("tuning_allowed", True))
    return [
        _case_from_payload(
            {
                **item,
                "tuning_allowed": bool(item.get("tuning_allowed", fixture_tuning_allowed)),
            },
            split=split,
        )
        for item in payload.get("cases", [])
    ]


def load_real_device_gold_cases(path: Path) -> list[GymCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[GymCase] = []
    for item in payload.get("cases", []):
        normalized_steps = []
        for index, step in enumerate(item.get("steps", [])):
            normalized_steps.append(
                {
                    "step_id": step.get("step_id", f"device-stage-{index + 1}"),
                    "screen_title": step.get("screen_title", "Real device screen"),
                    "activity_name": step.get("activity_name", item.get("activity_name", "")),
                    "stage": step.get("stage", "real_device"),
                    "ui_surface": step.get("ui_surface", "screen"),
                    "screen_state": step.get("screen_state", "ready"),
                    "elements": step.get("elements", []),
                    "expected": {
                        "action": step.get("expected_action", "stop"),
                        "label": step.get("expected_label"),
                        "function_id": step.get("expected_function", ""),
                    },
                }
            )
        normalized = {**item, "steps": normalized_steps}
        normalized["source_kind"] = "real_device_gold"
        cases.append(_case_from_payload(normalized, split="real_device_gold"))
    return cases


def load_cross_app_development_cases(path: Path, catalog: NavigationFunctionCatalog) -> list[GymCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[GymCase] = []
    for item in payload.get("cases", []):
        plan = infer_goal_plan(str(item["goal_text"]), catalog)
        expected_label = str(item["expected_label"])
        expected_function = plan.terminal_function
        if item["expected_action"] == "click":
            expected_function = _best_progress_function(catalog, plan, expected_label)
        elements = tuple(
            GymElement(
                id=f"button-{index}",
                label=str(label),
                role=("tab" if index == 1 and "마이" in str(label) else "button"),
                decoy_kind=_decoy_kind(str(label), expected_label),
            )
            for index, label in enumerate(item["buttons"])
        )
        cases.append(
            GymCase(
                case_id=f"curated-{item['id']}",
                split="development",
                intent_id=plan.intent,
                goal_text=str(item["goal_text"]),
                locale="ko-KR",
                user_state="unspecified",
                tags=("curated", "single_screen"),
                steps=(
                    GymStep(
                        step_id="screen-1",
                        screen_title=str(item["screen_title"]),
                        elements=elements,
                        expected_action=str(item["expected_action"]),
                        expected_label=expected_label,
                        expected_function=expected_function,
                        stage="destination" if item["expected_action"] == "stop" else "gateway",
                    ),
                ),
                source_kind="fixed_independent",
            )
        )
    return cases


def generate_catalog_route_cases(
    *,
    catalog: NavigationFunctionCatalog,
    catalog_source_path: Path,
    variants_per_intent: int = 3,
) -> list[GymCase]:
    source = json.loads(catalog_source_path.read_text(encoding="utf-8"))
    source_functions = {str(item["function_id"]): item for item in source.get("functions", [])}
    source_intents = {str(item["intent_id"]): item for item in source.get("intents", [])}
    alias_owners = _alias_owners(source_functions)
    decoy_functions = [
        function_id
        for function_id, item in source_functions.items()
        if item.get("automation_policy") == "safe_navigation"
        and not item.get("state_changing")
        and _aliases(item, "ko")
    ]
    cases: list[GymCase] = []
    for intent_id in sorted(source_intents):
        intent = source_intents[intent_id]
        patterns = [str(value) for value in intent.get("patterns", [])]
        if not patterns:
            continue
        for variant in range(max(1, variants_per_intent)):
            goal_text = patterns[variant % len(patterns)]
            locale_key = "en" if _looks_english(goal_text) else "ko"
            locale = "en-US" if locale_key == "en" else "ko-KR"
            # These cases exercise the catalog's declared route.  Re-running
            # fuzzy goal planning and all-function alias matching here made
            # generation quadratic in catalog size and duplicated the
            # independent semantic assertions in navigation_db_gym_unit.py.
            route_function_ids = [
                str(step.get("function_id", ""))
                for step in intent.get("route", [])
                if isinstance(step, dict)
                and catalog.function(str(step.get("function_id", ""))) is not None
            ]
            terminal = str(intent.get("terminal_function", ""))
            ordered = _dedupe(route_function_ids + ([terminal] if terminal else []))
            safe_intermediates = [
                function_id
                for function_id in ordered
                if function_id != terminal
                and (definition := catalog.function(function_id)) is not None
                and definition.automation_policy == "safe_navigation"
                and not definition.state_changing
            ]
            selected_route = safe_intermediates[:9] + ([terminal] if terminal else [])
            steps: list[GymStep] = []
            for step_index, function_id in enumerate(selected_route):
                function_source = source_functions.get(function_id, {})
                aliases = _aliases(function_source, locale_key) or _aliases(function_source, "ko")
                if not aliases:
                    continue
                is_terminal = function_id == terminal
                expected_label = _select_route_alias(
                    aliases=aliases,
                    alias_owners=alias_owners,
                    expected_function=function_id,
                    terminal_function=terminal,
                    variant=variant,
                    is_terminal=is_terminal,
                )
                decoys = _deterministic_decoys(
                    seed=f"{intent_id}|{variant}|{step_index}",
                    expected_function=function_id,
                    route_functions=set(selected_route),
                    source_functions=source_functions,
                    candidates=decoy_functions,
                    locale_key=locale_key,
                    alias_owners=alias_owners,
                    count=3,
                )
                labels = [expected_label, *decoys]
                shift = _stable_int(f"{intent_id}|{variant}|{step_index}") % len(labels)
                labels = labels[shift:] + labels[:shift]
                elements = tuple(
                    GymElement(
                        id=f"element-{element_index}",
                        label=label,
                        role=("tab", "button", "menuitem", "image")[
                            (variant + element_index) % 4
                        ],
                        decoy_kind=_decoy_kind(label, expected_label),
                    )
                    for element_index, label in enumerate(labels)
                )
                steps.append(
                    GymStep(
                        step_id=f"stage-{step_index + 1}",
                        screen_title=f"{intent_id} stage {step_index + 1}",
                        elements=elements,
                        expected_action="stop" if is_terminal else "click",
                        expected_label=expected_label,
                        expected_function=function_id,
                        stage="destination" if is_terminal else _stage_name(function_id),
                    )
                )
            if not steps:
                continue
            cases.append(
                GymCase(
                    case_id=f"generated-{intent_id}-{variant + 1}",
                    split="catalog_generated",
                    intent_id=intent_id,
                    goal_text=goal_text,
                    locale=locale,
                    user_state=("signed_out", "signed_in", "active_service")[variant % 3],
                    tags=("generated", "catalog_route", f"variant_{variant + 1}"),
                    steps=tuple(steps),
                    source_kind="catalog_self_generated",
                )
            )
    return cases


def load_synthetic_dimension_spec(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("synthetic dimension fixture must use schema_version 1")
    dimensions = payload.get("dimensions")
    scenarios = payload.get("scenarios")
    if not isinstance(dimensions, dict) or not dimensions:
        raise ValueError("synthetic dimension fixture has no dimensions")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("synthetic dimension fixture has no scenarios")
    return payload


def synthetic_dimension_universe(spec: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    dimensions = dict(spec.get("dimensions", {}))
    device_profiles = list(dimensions.get("device_profiles", []))
    scenarios = list(spec.get("scenarios", []))
    universe: dict[str, tuple[str, ...]] = {}
    for name in (
        "locale",
        "user_state",
        "ui_surface",
        "screen_state",
        "element_state",
        "activity_name",
    ):
        universe[name] = tuple(str(value) for value in dimensions.get(name, []))
    for name in ("device_model", "android_version", "orientation"):
        universe[name] = tuple(
            _dedupe(str(profile.get(name, "unspecified")) for profile in device_profiles)
        )
    universe["expected_action"] = tuple(
        _dedupe(str(scenario.get("expected_action", "stop")) for scenario in scenarios)
    )
    return {name: values for name, values in universe.items() if values}


def generate_synthetic_dimension_cases(
    *,
    spec: dict[str, Any],
    max_cases: int,
) -> list[GymCase]:
    """Build a deterministic pairwise-oriented UI state stress set.

    The fixture owns the semantic labels and expected functions.  The generator
    only combines independent presentation and device dimensions, so these
    cases remain separate from catalog-self-generated alias/route cases.
    """

    if max_cases < 1:
        return []
    dimensions = dict(spec.get("dimensions", {}))
    scenarios = {
        str(item["scenario_id"]): dict(item)
        for item in spec.get("scenarios", [])
    }
    device_profiles = {
        str(item["profile_id"]): dict(item)
        for item in dimensions.get("device_profiles", [])
    }
    axes = [
        ("scenario", tuple(sorted(scenarios))),
        ("locale", tuple(str(value) for value in dimensions.get("locale", []))),
        ("user_state", tuple(str(value) for value in dimensions.get("user_state", []))),
        ("ui_surface", tuple(str(value) for value in dimensions.get("ui_surface", []))),
        ("screen_state", tuple(str(value) for value in dimensions.get("screen_state", []))),
        ("element_state", tuple(str(value) for value in dimensions.get("element_state", []))),
        ("device_profile", tuple(sorted(device_profiles))),
        ("activity_name", tuple(str(value) for value in dimensions.get("activity_name", []))),
    ]
    if any(not values for _name, values in axes):
        missing = [name for name, values in axes if not values]
        raise ValueError(f"synthetic dimension fixture has empty axes: {', '.join(missing)}")
    rows = _pairwise_covering_rows(axes, max_rows=max_cases)
    cases: list[GymCase] = []
    for index, row in enumerate(rows):
        scenario = scenarios[row["scenario"]]
        profile = device_profiles[row["device_profile"]]
        locale = row["locale"]
        expected_action = str(scenario["expected_action"])
        expected_function = str(scenario["expected_function"])
        expected_label = _localized_value(scenario.get("expected_label"), locale)
        if expected_action == "scroll_forward":
            expected_label = "아래로 스크롤"
        elif expected_action in {"back", "no_click"}:
            expected_label = None
        elements = _synthetic_elements(
            spec=spec,
            scenario=scenario,
            locale=locale,
            ui_surface=row["ui_surface"],
            screen_state=row["screen_state"],
            element_state=row["element_state"],
        )
        tags = (
            "synthetic_dimensions",
            "pairwise_oriented",
            f"surface:{row['ui_surface']}",
            f"screen_state:{row['screen_state']}",
            f"element_state:{row['element_state']}",
            f"expected_action:{expected_action}",
        )
        cases.append(
            GymCase(
                case_id=f"synthetic-dim-{index + 1:04d}-{scenario['scenario_id']}",
                split="synthetic_dimensions",
                intent_id=str(scenario["intent_id"]),
                goal_text=_localized_value(scenario.get("goal_text"), locale) or "기능 찾기",
                locale=locale,
                user_state=row["user_state"],
                tags=tags,
                steps=(
                    GymStep(
                        step_id="dimension-screen-1",
                        screen_title=(
                            _localized_value(scenario.get("screen_title"), locale)
                            or str(scenario["scenario_id"])
                        ),
                        elements=elements,
                        expected_action=expected_action,
                        expected_label=expected_label,
                        expected_function=expected_function,
                        stage=str(scenario.get("stage", "synthetic_dimension")),
                        activity_name=row["activity_name"],
                        ui_surface=row["ui_surface"],
                        screen_state=row["screen_state"],
                    ),
                ),
                app_package=f"com.exitguide.synthetic.{scenario['scenario_id']}",
                app_version=str(spec.get("fixture_version", "1.0")),
                device_model=str(profile.get("device_model", "synthetic-device")),
                android_version=str(profile.get("android_version", "synthetic")),
                orientation=str(profile.get("orientation", "portrait")),
                source_kind="synthetic_independent",
            )
        )
    return cases


def _pairwise_covering_rows(
    axes: list[tuple[str, tuple[str, ...]]],
    *,
    max_rows: int,
) -> list[dict[str, str]]:
    """Greedily cover dimension-value pairs, then add deterministic stress rows."""

    candidates: set[tuple[str, ...]] = set()
    for left_index, right_index in combinations(range(len(axes)), 2):
        left_name, left_values = axes[left_index]
        right_name, right_values = axes[right_index]
        for left_value, right_value in product(left_values, right_values):
            seed = f"{left_name}:{left_value}|{right_name}:{right_value}"
            row = []
            for axis_index, (_axis_name, values) in enumerate(axes):
                if axis_index == left_index:
                    row.append(left_value)
                elif axis_index == right_index:
                    row.append(right_value)
                else:
                    row.append(values[_stable_int(f"{seed}|{axis_index}") % len(values)])
            candidates.add(tuple(row))

    all_pairs = {
        (left_index, left_value, right_index, right_value)
        for left_index, right_index in combinations(range(len(axes)), 2)
        for left_value in axes[left_index][1]
        for right_value in axes[right_index][1]
    }
    candidate_pairs = {
        row: {
            (left_index, row[left_index], right_index, row[right_index])
            for left_index, right_index in combinations(range(len(axes)), 2)
        }
        for row in candidates
    }
    uncovered = set(all_pairs)
    selected: list[tuple[str, ...]] = []
    remaining = set(candidates)
    while uncovered and remaining and len(selected) < max_rows:
        best = min(
            remaining,
            key=lambda row: (
                -len(candidate_pairs[row].intersection(uncovered)),
                _stable_int("|".join(row)),
                row,
            ),
        )
        selected.append(best)
        uncovered.difference_update(candidate_pairs[best])
        remaining.remove(best)

    # Deep mode intentionally keeps more than the minimum covering array.  The
    # extra stable rows expose higher-order (3+) interactions while remaining
    # byte-for-byte reproducible across runs.
    for row in sorted(remaining, key=lambda value: (_stable_int("|".join(value)), value)):
        if len(selected) >= max_rows:
            break
        selected.append(row)
    return [
        {axes[index][0]: value for index, value in enumerate(row)}
        for row in selected
    ]


def _synthetic_elements(
    *,
    spec: dict[str, Any],
    scenario: dict[str, Any],
    locale: str,
    ui_surface: str,
    screen_state: str,
    element_state: str,
) -> tuple[GymElement, ...]:
    expected_action = str(scenario["expected_action"])
    expected_label = _localized_value(scenario.get("expected_label"), locale) or "목적 메뉴"
    role = str(scenario.get("target_role", "button"))
    target_label = expected_label
    target_description = ""
    target_checked: bool | None = None
    target_selected = False
    target_checkable = False
    if element_state in {"content_description", "icon_only"} and expected_action in {"click", "stop"}:
        target_label = ""
        target_description = expected_label
        role = "image" if element_state == "icon_only" else role
    elif element_state == "checked" and expected_action in {"click", "stop"}:
        target_checkable = True
        target_checked = True
    elif element_state == "selected" and expected_action in {"click", "stop"}:
        target_selected = True

    elements: list[GymElement] = []
    if expected_action in {"click", "stop"}:
        elements.append(
            GymElement(
                id="expected-target",
                label=target_label,
                content_description=target_description,
                role=role,
                clickable=True,
                checkable=target_checkable,
                checked=target_checked,
                selected=target_selected,
            )
        )

    for index, item in enumerate(spec.get("decoys", [])):
        label = _localized_value(item.get("label"), locale) or f"decoy {index + 1}"
        elements.append(
            GymElement(
                id=f"decoy-{index + 1}",
                label=label,
                role=str(item.get("role", "button")),
                dangerous=bool(item.get("dangerous", False)),
                decoy_kind=str(item.get("decoy_kind", "")),
            )
        )

    if element_state == "disabled":
        elements.append(GymElement(id="state-disabled", label="사용할 수 없음", enabled=False))
    elif element_state == "invisible":
        elements.append(GymElement(id="state-invisible", label="숨겨진 메뉴", visible=False))
    elif element_state == "checked" and expected_action not in {"click", "stop"}:
        elements.append(
            GymElement(id="state-checked", label="선택됨", role="checkbox", checkable=True, checked=True)
        )
    elif element_state == "selected" and expected_action not in {"click", "stop"}:
        elements.append(GymElement(id="state-selected", label="현재 탭", role="tab", selected=True))
    elif element_state in {"content_description", "icon_only"} and expected_action not in {"click", "stop"}:
        elements.append(
            GymElement(
                id="state-icon",
                content_description="더보기",
                role="image" if element_state == "icon_only" else "button",
            )
        )

    if ui_surface in {"lazy_list", "endless_feed"} or expected_action == "scroll_forward":
        elements.append(
            GymElement(
                id="scroll-container",
                label="콘텐츠 목록" if ui_surface != "endless_feed" else "새 게시물 피드",
                role="list",
                clickable=False,
                scrollable=True,
            )
        )
    if screen_state == "permission":
        elements.extend(
            (
                GymElement(id="permission-message", label="권한이 필요합니다", role="text", clickable=False),
                GymElement(id="permission-deny", label="허용 안 함"),
            )
        )
    elif screen_state == "error":
        elements.extend(
            (
                GymElement(id="error-message", label="문제가 발생했습니다", role="text", clickable=False),
                GymElement(id="error-retry", label="다시 시도"),
            )
        )
    elif screen_state == "loading":
        elements.append(GymElement(id="loading", label="불러오는 중", role="progressbar", clickable=False))
    if ui_surface in {"dialog", "sheet", "drawer"}:
        elements.append(
            GymElement(
                id=f"surface-{ui_surface}",
                label=f"{ui_surface} container",
                role=ui_surface,
                clickable=False,
            )
        )
    if not elements:
        elements.append(GymElement(id="empty-state", label="표시할 항목 없음", role="text", clickable=False))
    return tuple(elements)


def _localized_value(value: Any, locale: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        locale_key = locale if locale in value else ("ko-KR" if "ko-KR" in value else next(iter(value), ""))
        return str(value.get(locale_key, "")) or None
    return str(value)


def evaluate_navigation_db_gym(
    *,
    cases: Iterable[GymCase],
    catalog_path: Path,
    total_intents: int,
    total_functions: int = 0,
    dimension_universe: dict[str, Iterable[str]] | None = None,
    intent_universe: Iterable[str] | None = None,
    function_universe: Iterable[str] | None = None,
) -> dict[str, object]:
    cases = list(cases)
    intent_universe = tuple(str(value) for value in (intent_universe or ()) if str(value))
    function_universe = tuple(str(value) for value in (function_universe or ()) if str(value))
    failures: list[GymFailure] = []
    case_results: list[GymCaseResult] = []
    metrics_by_split: dict[str, GymMetrics] = {}
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        settings = Settings(
            navigation_agent_provider="mock",
            navigation_function_db_path=str(root / "functions.sqlite"),
            navigation_function_catalog_path=str(catalog_path),
            navigation_exploration_timeout_seconds=120,
            navigation_exploration_max_actions=40,
            navigation_exploration_max_depth=16,
        )
        catalog = NavigationFunctionCatalog(root / "catalog.sqlite", catalog_path)
        repository = UniversalNavigationGraphRepository(root / "graph.sqlite")
        # Every fixed Gym case is already benchmark-gold evidence.  The
        # isolated repository therefore permits reuse after one successful
        # trusted validation; production keeps its stricter multi-sample
        # threshold.  Catalog-self-generated cases are never promoted below.
        repository.performance.minimum_samples = 1
        for case_index, case in enumerate(cases):
            metrics = metrics_by_split.setdefault(case.split, GymMetrics(split=case.split))
            metrics.case_count += 1
            metrics.goal_interpretation_total += 1
            goal_plan = infer_goal_plan(case.goal_text, catalog)
            goal_correct = int(goal_plan.intent == case.intent_id)
            metrics.goal_interpretation_correct += goal_correct
            metrics.gold_stage_count += len(case.steps)
            metrics.action_total += len(case.steps)
            metrics.next_menu_total += sum(step.expected_action == "click" for step in case.steps)
            metrics.scroll_total += sum(step.expected_action == "scroll_forward" for step in case.steps)
            metrics.back_total += sum(step.expected_action == "back" for step in case.steps)
            metrics.destination_total += sum(step.expected_action == "stop" for step in case.steps)
            metrics.safe_stop_total += sum(step.expected_action == "no_click" for step in case.steps)
            metrics.intent_ids.add(case.intent_id)
            metrics.function_ids.update(
                step.expected_function for step in case.steps if step.expected_function
            )
            metrics.stages.update(step.stage for step in case.steps)
            metrics.source_kind_counts[case.source_kind] = (
                metrics.source_kind_counts.get(case.source_kind, 0) + 1
            )
            if case.source_kind == "catalog_self_generated":
                metrics.catalog_generated_goal_interpretation_total += 1
                metrics.catalog_generated_goal_interpretation_correct += goal_correct
                metrics.catalog_generated_intent_ids.add(case.intent_id)
                metrics.catalog_generated_function_ids.update(
                    step.expected_function for step in case.steps if step.expected_function
                )
            else:
                metrics.independent_goal_interpretation_total += 1
                metrics.independent_goal_interpretation_correct += goal_correct
                metrics.independent_intent_ids.add(case.intent_id)
                metrics.independent_function_ids.update(
                    step.expected_function for step in case.steps if step.expected_function
                )
                if case.source_kind == "synthetic_independent":
                    metrics.synthetic_independent_intent_ids.add(case.intent_id)
                    metrics.synthetic_independent_function_ids.update(
                        step.expected_function for step in case.steps if step.expected_function
                    )
                else:
                    metrics.fixed_independent_intent_ids.add(case.intent_id)
                    metrics.fixed_independent_function_ids.update(
                        step.expected_function for step in case.steps if step.expected_function
                    )
            _record_case_dimensions(metrics, case)
            transition: dict[str, object] | None = None
            first_request: UniversalNavigationObserveRequest | None = None
            completed_route = False
            completed_route_id = ""
            attempted_steps = 0
            case_destination_correct = False
            case_safe_stop = True
            case_unsafe_clicks = 0
            case_wrong_clicks = 0
            case_failure_type = ""
            failed_step_id = ""
            for step_index, step in enumerate(case.steps):
                metrics.stage_count += 1
                attempted_steps += 1
                request = _request_for_step(case, step, case_index, step_index, transition=transition)
                if first_request is None:
                    first_request = request
                started = time.perf_counter()
                response = observe_universal_navigation(
                    request,
                    settings=settings,
                    repository=repository,
                    catalog=catalog,
                )
                metrics.latency_ms.append((time.perf_counter() - started) * 1000)
                if response.performance is not None:
                    # The public request schema deliberately accepts only
                    # real-device client provenance.  DB Gym owns this request
                    # and records its timings as synthetic in the report rather
                    # than claiming that generated screens came from a phone.
                    metrics.measurement_sources.add("synthetic")
                    metrics.decision_time_ms.append(response.performance.model_decision_ms)
                _record_action(metrics, response)
                selected = next(
                    (
                        element
                        for element in step.elements
                        if element.id == response.automation.selected_element_id
                    ),
                    None,
                )
                unsafe = bool(
                    response.automation.action == "click"
                    and selected is not None
                    and selected.dangerous
                )
                if unsafe:
                    metrics.unsafe_clicks += 1
                    case_unsafe_clicks += 1
                action_correct = _expected_action_is_correct(step, response)
                correct = bool(action_correct and not unsafe)
                metrics.action_correct += int(correct)
                if step.expected_action == "click":
                    metrics.next_menu_correct += int(correct)
                elif step.expected_action == "scroll_forward":
                    metrics.scroll_correct += int(correct)
                elif step.expected_action == "back":
                    metrics.back_correct += int(correct)
                elif step.expected_action == "no_click":
                    metrics.safe_stop_correct += int(correct)
                elif step.expected_action == "stop":
                    metrics.destination_correct += int(correct)
                if response.automation.action == "click" and not action_correct:
                    metrics.wrong_clicks += 1
                    case_wrong_clicks += 1
                if not correct:
                    failure = classify_failure(
                        case=case,
                        step=step,
                        response=response,
                        catalog=catalog,
                        selected_element=selected,
                    )
                    failures.append(failure)
                    if not case_failure_type:
                        case_failure_type = failure.failure_type
                        failed_step_id = step.step_id
                if step.expected_action == "stop":
                    case_destination_correct = bool(correct)
                    case_safe_stop = bool(
                        response.automation.action == "stop"
                        and response.automation.safe_to_execute is False
                    )
                    if correct and response.performance is not None:
                        destination_ms = response.performance.time_to_confirmed_destination_ms
                        if destination_ms is not None:
                            metrics.destination_time_ms.append(destination_ms)
                            if len(case.steps) > 1:
                                metrics.cold_destination_time_ms.append(destination_ms)
                            route_key = f"{case.app_package or f'com.exitguide.gym.{case.split}.{case_index}'}|{case.intent_id}"
                            current_fastest = metrics.fastest_routes.get(route_key)
                            if current_fastest is None or destination_ms < float(current_fastest["time_to_destination_ms"]):
                                metrics.fastest_routes[route_key] = {
                                    "app_package": case.app_package or f"com.exitguide.gym.{case.split}.{case_index}",
                                    "intent_id": case.intent_id,
                                    "case_id": case.case_id,
                                    "route_id": (
                                        ""
                                        if response.discovered_route is None
                                        else response.discovered_route.route_id
                                    ),
                                    "time_to_destination_ms": round(destination_ms, 3),
                                    "measurement_source": "synthetic",
                                }
                if correct and response.automation.action == "click" and response.recommendation is not None:
                    transition = {
                        "from_screen_fingerprint": response.screen_fingerprint,
                        "performed_element_id": response.automation.selected_element_id,
                        "recommendation_id": response.recommendation.recommendation_id,
                        "outcome": "navigated",
                    }
                else:
                    transition = None
                if correct and step.expected_action == "stop":
                    completed_route = True
                    if response.discovered_route is not None:
                        completed_route_id = response.discovered_route.route_id
                if not correct:
                    # A real explorer would now be on a different screen (or
                    # may have performed an unsafe action).  Continuing with
                    # the next gold screen would leak the answer and inflate
                    # downstream destination accuracy, so terminate the route.
                    break

            skipped_steps = max(0, len(case.steps) - attempted_steps)
            metrics.skipped_stage_count += skipped_steps
            case_success = bool(
                case.steps
                and attempted_steps == len(case.steps)
                and not case_failure_type
                and case_unsafe_clicks == 0
            )
            metrics.case_success_count += int(case_success)
            metrics.case_failure_count += int(not case_success)
            case_results.append(
                GymCaseResult(
                    case_id=case.case_id,
                    split=case.split,
                    source_kind=case.source_kind,
                    intent_id=case.intent_id,
                    user_state=case.user_state,
                    tags=case.tags,
                    app_package=case.app_package,
                    app_version=case.app_version,
                    device_model=case.device_model,
                    android_version=case.android_version,
                    orientation=case.orientation,
                    status="success" if case_success else "route_failed",
                    gold_stage_count=len(case.steps),
                    attempted_stage_count=attempted_steps,
                    skipped_stage_count=skipped_steps,
                    failed_step_id=failed_step_id,
                    failure_type=case_failure_type or ("empty_route" if not case.steps else ""),
                    unsafe_clicks=case_unsafe_clicks,
                    wrong_clicks=case_wrong_clicks,
                )
            )

            trusted_for_route_promotion = case.source_kind != "catalog_self_generated"
            if completed_route and case_success and trusted_for_route_promotion:
                repository.performance.apply_validation(
                    session_id=f"gym-session-{case_index}",
                    destination_correct=case_destination_correct,
                    safe_stop=case_safe_stop,
                    unsafe_clicks=case_unsafe_clicks,
                    wrong_clicks=case_wrong_clicks,
                    failure_type=case_failure_type,
                    verification_level="benchmark_gold",
                )
                if completed_route_id:
                    # Benchmark truth updates performance only. Route reuse in
                    # this isolated Gym requires a separate explicit lifecycle
                    # approval, just like production review.
                    repository.approve_route(completed_route_id)

            if (
                completed_route
                and case_success
                and trusted_for_route_promotion
                and first_request is not None
                and _is_reusable_click_route(case)
            ):
                metrics.route_reuse_total += 1
                replay_payload = first_request.model_dump()
                replay_payload["request_id"] = f"gym-reuse-{case_index}"
                replay_payload["session_id"] = f"gym-reuse-session-{case_index}"
                replay_payload["operation_mode"] = "guide"
                replay_payload["transition"] = None
                replay = observe_universal_navigation(
                    UniversalNavigationObserveRequest.model_validate(replay_payload),
                    settings=settings,
                    repository=repository,
                    catalog=catalog,
                )
                first_expected = case.steps[0].expected_label
                reuse_correct = (
                    replay.decision_mode == "route_cache"
                    and replay.automation.action == "none"
                    and replay.recommendation is not None
                    and replay.recommendation.selected_label == first_expected
                )
                metrics.route_reuse_correct += int(reuse_correct)
                if not reuse_correct:
                    failures.append(
                        GymFailure(
                            case_id=case.case_id,
                            split=case.split,
                            goal_text=case.goal_text,
                            step_id="route-reuse",
                            failure_type="route_reuse_failure",
                            expected_action="none",
                            expected_label=first_expected,
                            expected_function=case.steps[0].expected_function,
                            actual_action=replay.automation.action,
                            actual_label=replay.automation.selected_label,
                            actual_phase=replay.phase,
                            goal_interpretation=replay.goal_interpretation,
                            details="Discovered route was not reused as a manual guide from the start screen.",
                            tuning_allowed=case.tuning_allowed,
                        )
                    )
                warm_transition: dict[str, object] | None = None
                warm_final: UniversalNavigationObserveResponse | None = None
                for warm_step_index, warm_step in enumerate(case.steps):
                    warm_request = _request_for_step(
                        case,
                        warm_step,
                        case_index,
                        warm_step_index,
                        transition=warm_transition,
                        session_id=f"gym-warm-session-{case_index}",
                        operation_mode="guide",
                        stage_elapsed_ms=(warm_step_index + 1) * 450.0,
                    )
                    warm_final = observe_universal_navigation(
                        warm_request,
                        settings=settings,
                        repository=repository,
                        catalog=catalog,
                    )
                    performed_element_id = (
                        None
                        if warm_final.recommendation is None
                        else warm_final.recommendation.selected_element_id
                    )
                    if (
                        warm_final.recommendation is not None
                        and performed_element_id
                        and warm_step_index < len(case.steps) - 1
                    ):
                        warm_transition = {
                            "from_screen_fingerprint": warm_final.screen_fingerprint,
                            "performed_element_id": performed_element_id,
                            "recommendation_id": warm_final.recommendation.recommendation_id,
                            "outcome": "navigated",
                        }
                    else:
                        warm_transition = None
                if (
                    warm_final is not None
                    and warm_final.phase == "destination_reached"
                    and warm_final.performance is not None
                    and warm_final.performance.time_to_confirmed_destination_ms is not None
                ):
                    metrics.warm_destination_time_ms.append(
                        warm_final.performance.time_to_confirmed_destination_ms
                    )

    split_payloads = {
        split: metrics.payload(
            total_intents,
            total_functions,
            dimension_universe,
            intent_universe,
            function_universe,
        )
        for split, metrics in sorted(metrics_by_split.items())
    }
    for split, payload in split_payloads.items():
        payload["pairwise_dimension_coverage"] = _pairwise_dimension_coverage(
            (case for case in cases if case.split == split),
            dimension_universe or {},
        )
    totals = _aggregate_metrics(
        metrics_by_split.values(),
        total_intents,
        total_functions,
        dimension_universe,
        intent_universe,
        function_universe,
    )
    totals["pairwise_dimension_coverage"] = _pairwise_dimension_coverage(
        cases,
        dimension_universe or {},
    )
    split_policy = {
        "catalog_self_generated": sorted(
            {case.split for case in cases if case.source_kind == "catalog_self_generated"}
        ),
        "independent_fixed": sorted(
            {
                case.split
                for case in cases
                if case.source_kind not in {"catalog_self_generated", "synthetic_independent"}
            }
        ),
        "independent_synthetic": sorted(
            {case.split for case in cases if case.source_kind == "synthetic_independent"}
        ),
    }
    return {
        "schema_version": 3,
        "generated_at": _utc_timestamp(),
        "evaluation_policy": {
            "stateful_routes": True,
            "stop_after_first_wrong_or_unsafe_action": True,
            "skipped_gold_screens_award_credit": False,
            "catalog_self_generated_is_independent_evidence": False,
        },
        "split_policy": split_policy,
        "timing_policy": {
            "primary_metric": "time_to_confirmed_destination_ms",
            "optimization_order": [
                "unsafe_click_rate",
                "case_success_rate",
                "destination_accuracy",
                "safe_stop",
                "app_version_success",
                "p90_time_to_destination_ms",
                "p50_time_to_destination_ms",
                "interaction_cost",
            ],
            "desktop_measurements_are_real_device_baseline": False,
            "synthetic_cold_stage_ms": 1200.0,
            "synthetic_warm_stage_ms": 450.0,
        },
        "status": (
            "pass"
            if not failures
            and totals["unsafe_click_rate"] == 0.0
            and totals["case_success_rate"] == 1.0
            else "fail"
        ),
        "summary": totals,
        "splits": split_payloads,
        "failure_counts": _failure_counts(failures),
        "failures": [asdict(failure) for failure in failures],
        "case_results": [asdict(result) for result in case_results],
        "suggestions": build_db_suggestions(failures),
    }


def classify_failure(
    *,
    case: GymCase,
    step: GymStep,
    response: UniversalNavigationObserveResponse,
    catalog: NavigationFunctionCatalog,
    selected_element: GymElement | None,
) -> GymFailure:
    plan = infer_goal_plan(case.goal_text, catalog)
    actual_action = response.automation.action
    actual_label = response.automation.selected_label
    expected_matches = catalog.match_candidate(label=step.expected_label or "", limit=12)
    expected_match_ids = {match.function_id for match in expected_matches if match.score >= 0.46}
    if actual_action == "click" and selected_element is not None and selected_element.dangerous:
        failure_type = "unsafe_action_attempt"
        details = "A dangerous or state-changing decoy was selected for automatic click."
    elif not plan.terminal_function or plan.intent == "generic_navigation":
        failure_type = "goal_interpretation_failure"
        details = "Goal text did not resolve to a safe terminal function."
    elif step.expected_action == "scroll_forward" and actual_action != "scroll_forward":
        failure_type = "expected_scroll_missed"
        details = "The gold route required scrolling this screen, but another action was produced."
    elif step.expected_action == "back" and actual_action != "back":
        failure_type = "expected_back_missed"
        details = "The gold route required leaving a dead-end screen with Back."
    elif step.expected_action == "click" and actual_action == "scroll_forward":
        if step.expected_function not in expected_match_ids:
            failure_type = "alias_gap"
            details = "Expected visible label is not mapped strongly enough to its function."
        elif step.expected_function not in {function_id for function_id, _ in plan.preferred_functions}:
            failure_type = "missing_gateway"
            details = "Expected function is recognized but absent from the goal route."
        else:
            failure_type = "unnecessary_scroll"
            details = "A visible safe progress menu was skipped in favor of scrolling."
    elif step.expected_action == "click" and actual_action == "back":
        failure_type = "wrong_backtrack"
        details = "Explorer backed out despite a visible expected progress menu."
    elif step.expected_action == "click" and response.phase == "destination_reached":
        failure_type = "premature_destination"
        details = "An intermediate menu was mistaken for the final destination."
    elif step.expected_action == "stop" and actual_action != "stop":
        failure_type = "destination_missed"
        details = "Final destination was not identified before exploration stopped."
    elif selected_element is not None and selected_element.decoy_kind in {"advertisement", "product"}:
        failure_type = "advertisement_decoy"
        details = "Promotional or product UI outranked the requested function."
    elif actual_label:
        actual_matches = catalog.match_candidate(label=actual_label, limit=12)
        actual_ids = {match.function_id for match in actual_matches if match.score >= 0.46}
        if expected_match_ids.intersection(actual_ids):
            failure_type = "semantic_ambiguity"
            details = "Competing labels share a function mapping and need contextual disambiguation."
        else:
            failure_type = "wrong_menu"
            details = "A semantically unrelated menu was selected."
    else:
        failure_type = "safe_menu_not_explored"
        details = "No usable action was produced for a visible safe progress menu."
    assert failure_type in FAILURE_TYPES
    return GymFailure(
        case_id=case.case_id,
        split=case.split,
        goal_text=case.goal_text,
        step_id=step.step_id,
        failure_type=failure_type,
        expected_action=step.expected_action,
        expected_label=step.expected_label,
        expected_function=step.expected_function,
        actual_action=actual_action,
        actual_label=actual_label,
        actual_phase=response.phase,
        goal_interpretation=response.goal_interpretation,
        details=details,
        tuning_allowed=case.tuning_allowed,
    )


def build_db_suggestions(failures: Iterable[GymFailure]) -> list[dict[str, object]]:
    suggestions: dict[tuple[str, str, str], dict[str, object]] = {}
    for failure in failures:
        # Frozen evaluation-only packs may expose a regression score but must
        # never leak their wording or expected labels into the tuning queue.
        if not failure.tuning_allowed:
            continue
        if failure.failure_type == "goal_interpretation_failure":
            action, value = "add_goal_rule", failure.goal_text
        elif failure.failure_type == "alias_gap":
            action, value = "add_alias", failure.expected_label or ""
        elif failure.failure_type == "missing_gateway":
            action, value = "add_route_function", failure.expected_function
        elif failure.failure_type in {"semantic_ambiguity", "advertisement_decoy", "wrong_menu"}:
            action, value = "add_context_guard", failure.actual_label or ""
        elif failure.failure_type == "premature_destination":
            action, value = "add_terminal_cue_guard", failure.expected_function
        elif failure.failure_type == "unsafe_action_attempt":
            action, value = "tighten_automation_policy", failure.actual_label or ""
        else:
            action, value = "add_regression_case", failure.case_id
        key = (action, failure.expected_function, value)
        item = suggestions.setdefault(
            key,
            {
                "action": action,
                "function_id": failure.expected_function,
                "value": value,
                "evidence_count": 0,
                "source_cases": [],
                "auto_apply": False,
            },
        )
        item["evidence_count"] = int(item["evidence_count"]) + 1
        item["source_cases"].append(failure.case_id)
    return sorted(suggestions.values(), key=lambda item: (-int(item["evidence_count"]), str(item["action"])))


def compare_reports(current: dict[str, object], baseline: dict[str, object] | None) -> dict[str, object]:
    if baseline is None:
        return {"baseline_available": False, "deltas": {}}
    current_summary = dict(current.get("summary", {}))
    baseline_summary = dict(baseline.get("summary", {}))
    deltas: dict[str, float] = {}
    for key in (
        "case_success_rate",
        "goal_interpretation_accuracy",
        "independent_goal_interpretation_accuracy",
        "catalog_generated_goal_interpretation_accuracy",
        "attempted_stage_rate",
        "expected_action_accuracy",
        "next_menu_top1_accuracy",
        "scroll_action_accuracy",
        "back_action_accuracy",
        "destination_accuracy",
        "safe_stop_accuracy",
        "unsafe_click_rate",
        "wrong_click_rate",
        "mean_clicks_per_case",
        "mean_scrolls_per_case",
        "mean_backs_per_case",
        "mean_latency_ms",
        "time_to_destination_p50_ms",
        "time_to_destination_p90_ms",
        "decision_time_p50_ms",
        "decision_time_p90_ms",
        "success_within_10s_rate",
        "success_within_30s_rate",
        "success_within_60s_rate",
        "cold_time_to_destination_p50_ms",
        "warm_time_to_destination_p50_ms",
        "cache_time_reduction_rate",
        "route_reuse_rate",
        "intent_coverage",
        "function_coverage",
        "independent_intent_coverage",
        "independent_function_coverage",
        "fixed_independent_intent_coverage",
        "fixed_independent_function_coverage",
    ):
        if key in current_summary and key in baseline_summary:
            deltas[key] = round(float(current_summary[key]) - float(baseline_summary[key]), 6)
    return {"baseline_available": True, "deltas": deltas}


def render_markdown_report(report: dict[str, object]) -> str:
    summary = dict(report["summary"])
    comparison = dict(report.get("comparison", {}))
    lines = [
        "# Navigation DB Gym Report",
        "",
        f"- Status: **{report['status']}**",
        f"- Generated: `{report['generated_at']}`",
        f"- Cases / stages: {summary['case_count']} / {summary['stage_count']}",
        f"- Stateful route success: {float(summary['case_success_rate']):.1%}",
        f"- Goal interpretation accuracy: {float(summary['goal_interpretation_accuracy']):.1%}",
        f"- Independent goal interpretation: {float(summary['independent_goal_interpretation_accuracy']):.1%}",
        f"- Catalog-generated goal interpretation: {float(summary['catalog_generated_goal_interpretation_accuracy']):.1%}",
        f"- Gold / attempted / skipped stages: {summary['gold_stage_count']} / {summary['attempted_stage_count']} / {summary['skipped_stage_count']}",
        f"- Expected-action accuracy: {float(summary['expected_action_accuracy']):.1%}",
        f"- Next-menu Top-1: {float(summary['next_menu_top1_accuracy']):.1%}",
        f"- Scroll / Back accuracy: {float(summary['scroll_action_accuracy']):.1%} / {float(summary['back_action_accuracy']):.1%}",
        f"- Destination accuracy: {float(summary['destination_accuracy']):.1%}",
        f"- Safe-stop accuracy: {float(summary['safe_stop_accuracy']):.1%}",
        f"- Unsafe click rate: {float(summary['unsafe_click_rate']):.1%}",
        f"- Wrong click rate: {float(summary['wrong_click_rate']):.1%}",
        f"- Mean clicks / scrolls / backs: {summary['mean_clicks_per_case']:.3f} / {summary['mean_scrolls_per_case']:.3f} / {summary['mean_backs_per_case']:.3f}",
        f"- Mean stage latency: {summary['mean_latency_ms']:.3f} ms",
        f"- Time to confirmed destination p50 / p90: {summary['time_to_destination_p50_ms']:.3f} / {summary['time_to_destination_p90_ms']:.3f} ms",
        f"- Model decision p50 / p90: {summary['decision_time_p50_ms']:.3f} / {summary['decision_time_p90_ms']:.3f} ms",
        f"- Success within 10s / 30s / 60s: {float(summary['success_within_10s_rate']):.1%} / {float(summary['success_within_30s_rate']):.1%} / {float(summary['success_within_60s_rate']):.1%}",
        f"- Cold / warm destination p50: {summary['cold_time_to_destination_p50_ms']:.3f} / {summary['warm_time_to_destination_p50_ms']:.3f} ms",
        f"- Cache time reduction: {float(summary['cache_time_reduction_rate']):.1%}",
        f"- Timing source: {', '.join(summary['measurement_sources']) or 'none'}",
        f"- Route reuse: {float(summary['route_reuse_rate']):.1%}",
        f"- Intent coverage: {float(summary['intent_coverage']):.1%}",
        f"- Function coverage: {float(summary['function_coverage']):.1%}",
        f"- Independent intent / function coverage: {float(summary['independent_intent_coverage']):.1%} / {float(summary['independent_function_coverage']):.1%}",
        f"- Fixed-independent intent / function coverage: {float(summary['fixed_independent_intent_coverage']):.1%} / {float(summary['fixed_independent_function_coverage']):.1%}",
        "",
        "## Split results",
        "",
        "| Split | Cases | Route success | Stages | Top-1 | Destination | Unsafe | Wrong | TTD p50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for split, values in dict(report["splits"]).items():
        lines.append(
            f"| {split} | {values['case_count']} | {float(values['case_success_rate']):.1%} | {values['stage_count']} | "
            f"{float(values['next_menu_top1_accuracy']):.1%} | {float(values['destination_accuracy']):.1%} | "
            f"{float(values['unsafe_click_rate']):.1%} | {float(values['wrong_click_rate']):.1%} | "
            f"{float(values['time_to_destination_p50_ms']):.1f} ms |"
        )
    lines.extend(["", "## Dimension coverage gaps", ""])
    missing_any = False
    for name, values in dict(summary.get("coverage_matrix", {})).items():
        missing = list(values.get("missing", []))
        if not missing:
            continue
        missing_any = True
        lines.append(f"- `{name}`: {', '.join(str(value) for value in missing)}")
    if not missing_any:
        lines.append("- No declared dimension values are missing.")
    pairwise = dict(summary.get("pairwise_dimension_coverage", {}))
    if pairwise:
        lines.append(
            f"- Pairwise-oriented coverage: {float(pairwise['coverage_rate']):.1%} "
            f"({pairwise['covered_pair_count']} / {pairwise['expected_pair_count']}; "
            f"missing {pairwise['missing_pair_count']})"
        )
    missing_intents = list(summary.get("independent_missing_intents", []))
    missing_functions = list(summary.get("independent_missing_functions", []))
    lines.extend(["", "## Independent coverage backlog", ""])
    lines.append(
        "- Missing intents: "
        + (", ".join(f"`{value}`" for value in missing_intents[:50]) or "none")
    )
    lines.append(
        "- Missing functions: "
        + (", ".join(f"`{value}`" for value in missing_functions[:50]) or "none")
    )
    if len(missing_intents) > 50 or len(missing_functions) > 50:
        lines.append("- The JSON report contains the complete backlog; Markdown shows the first 50 IDs.")
    fastest_routes = list(summary.get("fastest_routes", []))
    lines.extend(["", "## Fastest safe routes", ""])
    if fastest_routes:
        for item in fastest_routes[:20]:
            lines.append(
                f"- `{item['app_package']}` / `{item['intent_id']}`: "
                f"{float(item['time_to_destination_ms']):.1f} ms "
                f"(`{item['route_id'] or 'unpersisted'}`, {item['measurement_source']})"
            )
    else:
        lines.append("- No correctly completed route timing was recorded.")
    lines.extend(["", "## Failure taxonomy", ""])
    failure_counts = dict(report.get("failure_counts", {}))
    if failure_counts:
        for failure_type, count in sorted(failure_counts.items()):
            lines.append(f"- {failure_type}: {count}")
    else:
        lines.append("- No failures.")
    lines.extend(["", "## Suggested DB changes", ""])
    suggestions = list(report.get("suggestions", []))
    if suggestions:
        for suggestion in suggestions[:30]:
            lines.append(
                f"- `{suggestion['action']}` `{suggestion['function_id']}` → `{suggestion['value']}` "
                f"({suggestion['evidence_count']} cases, review required)"
            )
    else:
        lines.append("- No DB change proposed.")
    if comparison.get("baseline_available"):
        lines.extend(["", "## Baseline deltas", ""])
        for key, value in dict(comparison.get("deltas", {})).items():
            lines.append(f"- {key}: {float(value):+.6f}")
    return "\n".join(lines) + "\n"


def _case_from_payload(item: dict[str, Any], *, split: str) -> GymCase:
    steps = []
    for step_index, step in enumerate(item.get("steps", [])):
        elements = tuple(
            GymElement(
                id=str(element.get("id", f"element-{element_index}")),
                label=str(element.get("label", "")),
                role=str(element.get("role", "button")),
                view_id=str(element.get("view_id", "")),
                content_description=str(element.get("content_description", "")),
                clickable=bool(element.get("clickable", True)),
                enabled=bool(element.get("enabled", True)),
                visible=bool(element.get("visible", True)),
                scrollable=bool(element.get("scrollable", False)),
                checkable=bool(element.get("checkable", False)),
                checked=element.get("checked"),
                selected=bool(element.get("selected", False)),
                password=bool(element.get("password", False)),
                dangerous=bool(element.get("dangerous", False)),
                decoy_kind=str(element.get("decoy_kind", "")),
            )
            for element_index, element in enumerate(step.get("elements", []))
        )
        expected = dict(step.get("expected", {}))
        steps.append(
            GymStep(
                step_id=str(step.get("step_id", f"stage-{step_index + 1}")),
                screen_title=str(step.get("screen_title", "Synthetic screen")),
                elements=elements,
                expected_action=str(expected.get("action", "stop")),
                expected_label=expected.get("label"),
                expected_function=str(expected.get("function_id", "")),
                stage=str(step.get("stage", "unknown")),
                activity_name=str(step.get("activity_name", item.get("activity_name", "NavigationDbGymActivity"))),
                ui_surface=str(step.get("ui_surface", "screen")),
                screen_state=str(step.get("screen_state", "ready")),
            )
        )
    return GymCase(
        case_id=str(item["case_id"]),
        split=split,
        intent_id=str(item["intent_id"]),
        goal_text=str(item["goal_text"]),
        locale=str(item.get("locale", "ko-KR")),
        user_state=str(item.get("user_state", "unspecified")),
        tags=tuple(str(value) for value in item.get("tags", [])),
        steps=tuple(steps),
        app_package=str(item.get("app_package", "")),
        app_version=str(item.get("app_version", "1.0")),
        device_model=str(item.get("device_model", "synthetic-device")),
        android_version=str(item.get("android_version", "synthetic")),
        orientation=str(item.get("orientation", "portrait")),
        source_kind=str(item.get("source_kind", "fixed_independent")),
        tuning_allowed=bool(item.get("tuning_allowed", True)),
    )


def _request_for_step(
    case: GymCase,
    step: GymStep,
    case_index: int,
    step_index: int,
    *,
    transition: dict[str, object] | None,
    session_id: str | None = None,
    operation_mode: str = "explore",
    stage_elapsed_ms: float | None = None,
) -> UniversalNavigationObserveRequest:
    elements = []
    screen_right = 2200 if case.orientation == "landscape" else 1060
    for element_index, element in enumerate(step.elements):
        top = 160 + element_index * 140
        elements.append(
            {
                "id": element.id,
                "text": element.label or None,
                "content_description": element.content_description or None,
                "view_id": element.view_id or None,
                "role": element.role,
                "clickable": element.clickable,
                "enabled": element.enabled,
                "visible": element.visible,
                "scrollable": element.scrollable,
                "checkable": element.checkable,
                "checked": element.checked,
                "selected": element.selected,
                "password": element.password,
                "bounds": [20, top, screen_right, top + 120],
            }
        )
    return UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": f"gym-{case_index}-{step_index}",
            "session_id": session_id or f"gym-session-{case_index}",
            "app_package": case.app_package or f"com.exitguide.gym.{case.split}.{case_index}",
            "app_version": case.app_version,
            "locale": case.locale,
            "goal_text": case.goal_text,
            "operation_mode": operation_mode,
            "screen": {
                "activity_name": step.activity_name,
                "window_title": step.screen_title,
                "event_type": (
                    "window_content_changed"
                    if step.ui_surface in {"lazy_list", "endless_feed"} or step.screen_state == "loading"
                    else "window_state_changed"
                ),
                "elements": elements,
            },
            "transition": transition,
            "client_timing": {
                # Public clients cannot self-assert synthetic/gold provenance;
                # the evaluator relabels this server-owned fixture in its report.
                "measurement_source": "real_device",
                "exploration_elapsed_ms": (
                    stage_elapsed_ms if stage_elapsed_ms is not None else (step_index + 1) * 1200.0
                ),
                "screen_capture_ms": 80.0,
                "action_execution_ms": 70.0 if transition is not None else 0.0,
                "ui_settle_ms": 600.0 if transition is not None else 0.0,
                "external_wait_ms": 200.0 if transition is not None else 0.0,
            },
        }
    )


def _best_progress_function(catalog: NavigationFunctionCatalog, plan, label: str) -> str:
    preferred = {function_id for function_id, _ in plan.preferred_functions}
    matches = catalog.match_candidate(label=label, limit=12)
    return next(
        (match.function_id for match in matches if match.function_id in preferred),
        matches[0].function_id if matches else "",
    )


def _record_action(metrics: GymMetrics, response: UniversalNavigationObserveResponse) -> None:
    metrics.click_count += int(response.automation.action == "click")
    metrics.scroll_count += int(response.automation.action == "scroll_forward")
    metrics.back_count += int(response.automation.action == "back")


def _expected_action_is_correct(
    step: GymStep,
    response: UniversalNavigationObserveResponse,
) -> bool:
    actual_action = response.automation.action
    expected_element_ids = {
        element.id
        for element in step.elements
        if element.label == (step.expected_label or "")
    }
    selected_expected_element = bool(
        response.automation.selected_element_id
        and response.automation.selected_element_id in expected_element_ids
    )
    if step.expected_action == "click":
        return bool(
            actual_action == "click"
            and (
                response.automation.selected_label == step.expected_label
                or selected_expected_element
            )
        )
    if step.expected_action == "scroll_forward":
        return actual_action == "scroll_forward"
    if step.expected_action == "back":
        return actual_action == "back"
    if step.expected_action == "no_click":
        return actual_action != "click"
    if step.expected_action == "stop":
        return bool(
            actual_action == "stop"
            and (
                response.automation.selected_label == step.expected_label
                or selected_expected_element
            )
        )
    return False


def _is_reusable_click_route(case: GymCase) -> bool:
    return bool(
        len(case.steps) > 1
        and case.steps[-1].expected_action == "stop"
        and all(step.expected_action == "click" for step in case.steps[:-1])
    )


def _record_case_dimensions(metrics: GymMetrics, case: GymCase) -> None:
    def add(name: str, value: object) -> None:
        normalized = str(value).strip()
        if normalized:
            metrics.dimension_values.setdefault(name, set()).add(normalized)

    add("locale", case.locale)
    add("user_state", case.user_state)
    add("device_model", case.device_model)
    add("android_version", case.android_version)
    add("orientation", case.orientation)
    add("source_kind", case.source_kind)
    add("app_package", case.app_package or "synthetic-package")
    for tag in case.tags:
        add("tag", tag)
    for step in case.steps:
        add("activity_name", step.activity_name)
        add("ui_surface", step.ui_surface)
        add("screen_state", step.screen_state)
        add("expected_action", step.expected_action)
        add("stage", step.stage)
        for element in step.elements:
            add("role", element.role)
            if not element.enabled:
                add("element_state", "disabled")
            if not element.visible:
                add("element_state", "invisible")
            if element.checkable and element.checked is True:
                add("element_state", "checked")
            if element.selected:
                add("element_state", "selected")
            if element.content_description:
                add("element_state", "content_description")
            if element.content_description and not element.label:
                add("element_state", "icon_only")
            if element.scrollable:
                add("element_state", "scrollable")
            if element.dangerous:
                add("element_state", "dangerous")
            if (
                element.enabled
                and element.visible
                and not element.checked
                and not element.selected
                and not element.content_description
            ):
                add("element_state", "enabled")


def _dimension_coverage_matrix(
    observed: dict[str, set[str]],
    universe: dict[str, Iterable[str]],
) -> dict[str, dict[str, object]]:
    names = sorted(set(observed).union(universe))
    matrix: dict[str, dict[str, object]] = {}
    for name in names:
        covered = set(observed.get(name, set()))
        expected = {str(value) for value in universe.get(name, ()) if str(value)}
        missing = expected.difference(covered)
        matrix[name] = {
            "covered_count": len(covered.intersection(expected)) if expected else len(covered),
            "expected_count": len(expected),
            "coverage_rate": _ratio(len(covered.intersection(expected)), len(expected)) if expected else 1.0,
            "covered": sorted(covered),
            "missing": sorted(missing),
        }
    return matrix


def _pairwise_dimension_coverage(
    cases: Iterable[GymCase],
    universe: dict[str, Iterable[str]],
) -> dict[str, object]:
    normalized_universe: dict[str, tuple[str, ...]] = {}
    for name, raw_values in universe.items():
        values = tuple(str(value) for value in raw_values if str(value))
        if values:
            normalized_universe[name] = tuple(_dedupe(values))
    names = sorted(normalized_universe)
    profile_fields = {"device_model", "android_version", "orientation"}
    expected: set[tuple[str, str, str, str]] = set()
    for left_name, right_name in combinations(names, 2):
        # These values originate from one declared device profile and are not
        # independent axes; impossible cross-profile pairs must not be counted
        # as coverage gaps.
        if left_name in profile_fields and right_name in profile_fields:
            continue
        expected.update(
            (left_name, left_value, right_name, right_value)
            for left_value in normalized_universe[left_name]
            for right_value in normalized_universe[right_name]
        )
    covered: set[tuple[str, str, str, str]] = set()
    for case in cases:
        assignments = _declared_case_dimensions(case)
        for left_name, right_name in combinations(names, 2):
            if left_name in profile_fields and right_name in profile_fields:
                continue
            for left_value in assignments.get(left_name, ()):
                for right_value in assignments.get(right_name, ()):
                    pair = (left_name, left_value, right_name, right_value)
                    if pair in expected:
                        covered.add(pair)
    missing = sorted(expected.difference(covered))
    return {
        "expected_pair_count": len(expected),
        "covered_pair_count": len(covered),
        "coverage_rate": _ratio(len(covered), len(expected)),
        "missing_pair_count": len(missing),
        "missing_pairs_sample": [
            {
                "left_dimension": left_name,
                "left_value": left_value,
                "right_dimension": right_name,
                "right_value": right_value,
            }
            for left_name, left_value, right_name, right_value in missing[:100]
        ],
    }


def _declared_case_dimensions(case: GymCase) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {
        "locale": {case.locale},
        "user_state": {case.user_state},
        "device_model": {case.device_model},
        "android_version": {case.android_version},
        "orientation": {case.orientation},
        "activity_name": {step.activity_name for step in case.steps},
        "ui_surface": {step.ui_surface for step in case.steps},
        "screen_state": {step.screen_state for step in case.steps},
        "expected_action": {step.expected_action for step in case.steps},
    }
    tagged_element_states = {
        tag.split(":", 1)[1]
        for tag in case.tags
        if tag.startswith("element_state:") and ":" in tag
    }
    if tagged_element_states:
        values["element_state"] = tagged_element_states
    else:
        observed = GymMetrics(split="dimension-probe")
        _record_case_dimensions(observed, case)
        values["element_state"] = set(observed.dimension_values.get("element_state", ()))
    return {
        name: {str(value) for value in dimension_values if str(value)}
        for name, dimension_values in values.items()
    }


def _aggregate_metrics(
    metrics_values: Iterable[GymMetrics],
    total_intents: int,
    total_functions: int = 0,
    dimension_universe: dict[str, Iterable[str]] | None = None,
    intent_universe: Iterable[str] | None = None,
    function_universe: Iterable[str] | None = None,
) -> dict[str, object]:
    values = list(metrics_values)
    aggregate = GymMetrics(split="all")
    for metrics in values:
        for name in (
            "case_count",
            "case_success_count",
            "case_failure_count",
            "goal_interpretation_total",
            "goal_interpretation_correct",
            "independent_goal_interpretation_total",
            "independent_goal_interpretation_correct",
            "catalog_generated_goal_interpretation_total",
            "catalog_generated_goal_interpretation_correct",
            "gold_stage_count",
            "stage_count",
            "skipped_stage_count",
            "action_total",
            "action_correct",
            "next_menu_total",
            "next_menu_correct",
            "scroll_total",
            "scroll_correct",
            "back_total",
            "back_correct",
            "destination_total",
            "destination_correct",
            "safe_stop_total",
            "safe_stop_correct",
            "unsafe_clicks",
            "wrong_clicks",
            "click_count",
            "scroll_count",
            "back_count",
            "route_reuse_total",
            "route_reuse_correct",
        ):
            setattr(aggregate, name, getattr(aggregate, name) + getattr(metrics, name))
        aggregate.latency_ms.extend(metrics.latency_ms)
        aggregate.destination_time_ms.extend(metrics.destination_time_ms)
        aggregate.decision_time_ms.extend(metrics.decision_time_ms)
        aggregate.cold_destination_time_ms.extend(metrics.cold_destination_time_ms)
        aggregate.warm_destination_time_ms.extend(metrics.warm_destination_time_ms)
        for key, value in metrics.fastest_routes.items():
            current = aggregate.fastest_routes.get(key)
            if current is None or float(value["time_to_destination_ms"]) < float(current["time_to_destination_ms"]):
                aggregate.fastest_routes[key] = dict(value)
        aggregate.measurement_sources.update(metrics.measurement_sources)
        aggregate.intent_ids.update(metrics.intent_ids)
        aggregate.function_ids.update(metrics.function_ids)
        aggregate.independent_intent_ids.update(metrics.independent_intent_ids)
        aggregate.independent_function_ids.update(metrics.independent_function_ids)
        aggregate.fixed_independent_intent_ids.update(metrics.fixed_independent_intent_ids)
        aggregate.fixed_independent_function_ids.update(metrics.fixed_independent_function_ids)
        aggregate.synthetic_independent_intent_ids.update(metrics.synthetic_independent_intent_ids)
        aggregate.synthetic_independent_function_ids.update(metrics.synthetic_independent_function_ids)
        aggregate.catalog_generated_intent_ids.update(metrics.catalog_generated_intent_ids)
        aggregate.catalog_generated_function_ids.update(metrics.catalog_generated_function_ids)
        aggregate.stages.update(metrics.stages)
        for source_kind, count in metrics.source_kind_counts.items():
            aggregate.source_kind_counts[source_kind] = aggregate.source_kind_counts.get(source_kind, 0) + count
        for name, values_for_dimension in metrics.dimension_values.items():
            aggregate.dimension_values.setdefault(name, set()).update(values_for_dimension)
    return aggregate.payload(
        total_intents,
        total_functions,
        dimension_universe,
        intent_universe,
        function_universe,
    )


def _percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    return round(ordered[lower] * (1.0 - weight) + ordered[upper] * weight, 3)


def _within_rate(values: Iterable[float], threshold_ms: float) -> float:
    values = list(values)
    return _ratio(sum(int(value <= threshold_ms) for value in values), len(values))


def _cache_reduction_rate(cold: Iterable[float], warm: Iterable[float]) -> float:
    pairs = [
        (float(cold_value), float(warm_value))
        for cold_value, warm_value in zip(cold, warm)
        if float(cold_value) > 0.0
    ]
    if not pairs:
        return 0.0
    reductions = [max(-1.0, min(1.0, (cold_value - warm_value) / cold_value)) for cold_value, warm_value in pairs]
    return round(sum(reductions) / len(reductions), 6)


def _aliases(function_source: dict[str, Any], locale_key: str) -> list[str]:
    aliases = dict(function_source.get("aliases", {}))
    normalized_locale = locale_key.casefold().split("-", 1)[0]
    values: list[str] = []
    for raw_locale, raw_values in aliases.items():
        if str(raw_locale).casefold().split("-", 1)[0] != normalized_locale:
            continue
        entries = raw_values if isinstance(raw_values, (list, tuple)) else [raw_values]
        values.extend(str(value) for value in entries if str(value).strip())
    return _dedupe(values)


def _deterministic_decoys(
    *,
    seed: str,
    expected_function: str,
    route_functions: set[str],
    source_functions: dict[str, dict[str, Any]],
    candidates: list[str],
    locale_key: str,
    alias_owners: dict[str, set[str]],
    count: int,
) -> list[str]:
    ranked = sorted(
        (function_id for function_id in candidates if function_id != expected_function and function_id not in route_functions),
        key=lambda function_id: hashlib.sha256(f"{seed}|{function_id}".encode("utf-8")).hexdigest(),
    )
    values: list[str] = []
    for function_id in ranked:
        aliases = _aliases(source_functions[function_id], locale_key) or _aliases(source_functions[function_id], "ko")
        if aliases:
            candidate_label = aliases[_stable_int(f"{seed}|{function_id}") % len(aliases)]
            mapped_route_functions = alias_owners.get(_normalize_alias(candidate_label), set())
            # Generated development cases should mutate layout and wording,
            # not contain two labels that both map to the asserted next step.
            # Deliberate semantic collisions live in the adversarial split.
            if mapped_route_functions.intersection(route_functions):
                continue
            values.append(candidate_label)
        if len(values) >= count:
            break
    return values


def _select_route_alias(
    *,
    aliases: list[str],
    alias_owners: dict[str, set[str]],
    expected_function: str,
    terminal_function: str,
    variant: int,
    is_terminal: bool,
) -> str:
    if is_terminal:
        return aliases[variant % len(aliases)]
    unambiguous: list[str] = []
    for alias in aliases:
        owners = alias_owners.get(_normalize_alias(alias), set())
        if expected_function not in owners:
            continue
        if terminal_function and terminal_function in owners:
            continue
        unambiguous.append(alias)
    candidates = unambiguous or aliases
    return candidates[variant % len(candidates)]


def _alias_owners(
    source_functions: dict[str, dict[str, Any]],
) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for function_id, source in source_functions.items():
        for locale_key in ("ko", "en"):
            for alias in _aliases(source, locale_key):
                normalized = _normalize_alias(alias)
                if normalized:
                    owners.setdefault(normalized, set()).add(function_id)
    return owners


def _normalize_alias(value: str) -> str:
    return "".join(character.casefold() for character in value if character.isalnum())


def _stage_name(function_id: str) -> str:
    if function_id in {"navigation.menu", "navigation.drawer", "navigation.more"}:
        return "global_navigation"
    if function_id in {"account.entry", "auth.entry", "auth.login.entry"}:
        return "account_gateway"
    return function_id.split(".", 1)[0] + "_hub"


def _decoy_kind(label: str, expected_label: str) -> str:
    if label == expected_label:
        return ""
    normalized = label.lower()
    if any(token in normalized for token in ("이벤트", "혜택", "추천", "광고", "쿠폰", "특가", "promotion")):
        return "advertisement"
    if any(token in normalized for token in ("상품", "구매", "장바구니", "요금제", "product")):
        return "product"
    return "semantic"


def _failure_counts(failures: Iterable[GymFailure]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for failure in failures:
        counts[failure.failure_type] = counts.get(failure.failure_type, 0) + 1
    return dict(sorted(counts.items()))


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _stable_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def _looks_english(value: str) -> bool:
    return not any("가" <= character <= "힣" for character in value)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 6) if denominator else 0.0


def _utc_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
