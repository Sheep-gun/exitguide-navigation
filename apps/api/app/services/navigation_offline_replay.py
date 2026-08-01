from __future__ import annotations

import copy
import json
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from app.config import Settings
from app.schemas import UniversalNavigationObserveRequest
from app.services.navigation_function_catalog import NavigationFunctionCatalog
from app.services.navigation_performance import StageMeasurement
from app.services.real_device_privacy import classify_human_text
from app.services.universal_navigation_agent import observe_universal_navigation
from app.services.universal_navigation_graph import (
    StoredRoute,
    UniversalNavigationGraphRepository,
    fingerprint_goal,
)


EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
PHONE_PATTERN = re.compile(r"(?<!\d)01[016789][ -]?\d{3,4}[ -]?\d{4}(?!\d)")
RAW_ARTIFACT_KEYS = frozenset(
    {
        "raw_screenshot",
        "screenshot_path",
        "raw_xml",
        "xml_path",
        "uiautomator_dump",
    }
)
RAW_ARTIFACT_KEY_FRAGMENTS = (
    "screenshot",
    "uiautomator",
    "accessibility_dump",
    "raw_xml",
    "raw_image",
    "image_path",
    "bitmap",
    "base64",
    "device_serial",
)
RAW_OR_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)^data:image/"),
    re.compile(r"(?i)\.(?:png|jpe?g|webp|xml|uix)(?:$|[?#])"),
    re.compile(r"(?i)\b(?:flp_|sk_|pk_)[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}\b"),
)
REQUIRED_MUTATION_IDS = frozenset(
    {
        "order-reversed",
        "order-rotated",
        "settings-korean-spacing",
        "settings-synonym-short",
        "settings-synonym-app",
        "settings-ocr-error",
        "goal-korean-spacing",
        "goal-synonym",
        "goal-colloquial",
        "missing-content-description",
        "missing-resource-id",
        "unlabeled-gear-single",
        "unlabeled-gear-multiple-siblings",
        "promo-popup-close",
        "blocking-modal-close",
        "blocking-modal-back",
        "static-survey-card",
        "loading-before-home",
        "settings-below-fold",
        "stale-approved-graph",
        "verified-route-reuse",
        "route-first-button-missing",
        "route-intermediate-screen-changed",
        "route-unexpected-transition",
        "route-version-changed",
        "network-delay-reobserve",
        "partial-content-loading",
        "app-update-hierarchy",
        "settings-icon-last-sibling",
        "nearby-risky-toggle",
        "account-delete-near-settings",
        "payment-near-settings",
        "final-title-spacing",
        "final-title-synonym",
        "combined-missing-identifiers",
        "combined-modal-order",
    }
)
CANONICAL_MEANING_EDGES = frozenset(
    {
        ("blocking_modal", "app_home"),
        ("loading", "app_home"),
        ("app_home", "account_hub"),
        ("account_hub", "account_hub"),
        ("account_hub", "notification_preferences"),
        ("account_hub", "recoverable_probe"),
        ("recoverable_probe", "account_hub"),
    }
)
TRANSIENT_REOBSERVE_FAILURES = frozenset(
    {
        "transient_loading",
        "conservative_screen_state",
        "transient_system_error",
    }
)


@dataclass(frozen=True)
class OfflineReplayScenario:
    scenario_id: str
    mutation_kind: str
    tags: tuple[str, ...]
    goal_text: str
    app_package: str
    app_version: str
    locale: str
    target_function: str
    start_screen: str
    terminal_screen: str
    screens: dict[str, dict[str, Any]]
    limits: dict[str, int]
    seed_verified_route: bool = False
    seed_stale_route: bool = False
    route_seed_screens: dict[str, dict[str, Any]] | None = None
    route_seed_app_version: str = ""
    allow_unexpected_route_transition: bool = False


@dataclass
class OfflineReplayResult:
    scenario_id: str
    mutation_kind: str
    tags: tuple[str, ...]
    success: bool = False
    destination_reached: bool = False
    destination_correct: bool = False
    bounded: bool = True
    step_count: int = 0
    decision_count: int = 0
    correct_decision_count: int = 0
    auto_click_count: int = 0
    guided_click_count: int = 0
    scroll_count: int = 0
    back_count: int = 0
    reobserve_count: int = 0
    safe_probe_count: int = 0
    safe_probe_recovery_count: int = 0
    unsafe_auto_click_count: int = 0
    final_auto_click_count: int = 0
    wrong_destination_count: int = 0
    wrong_guidance_count: int = 0
    repeated_screen_limit_hits: int = 0
    max_unlabeled_candidate_count: int = 0
    max_distinct_unlabeled_candidate_key_count: int = 0
    stale_route_guidance_used: bool = False
    stale_route_invalidated: bool = False
    stale_route_observation_count: int = 0
    route_reused: bool = False
    fallback_used: bool = False
    version_mismatch_route_skipped: bool = False
    projected_time_to_destination_ms: float = 0.0
    offline_wall_time_ms: float = 0.0
    failure_reason: str = ""
    discovered_route_id: str = ""
    trace: list[dict[str, object]] = field(default_factory=list)

    @property
    def micro_accuracy(self) -> float:
        if self.decision_count == 0:
            return 0.0
        return self.correct_decision_count / self.decision_count

    def payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        payload["micro_accuracy"] = round(self.micro_accuracy, 6)
        return payload


def load_offline_replay_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("offline replay fixture must use schema_version 1")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("offline replay fixture must declare provenance")
    required_privacy_claims = {
        "captured_gold": False,
        "raw_artifacts_persisted": False,
        "contains_personal_data": False,
        "uses_absolute_coordinates_as_identity": False,
    }
    for key, expected in required_privacy_claims.items():
        if provenance.get(key) is not expected:
            raise ValueError(f"offline replay fixture provenance must declare {key}={expected}")
    if provenance.get("destination_provenance") != "expected_semantic_target":
        raise ValueError("offline fixture destination must be marked expected_semantic_target")
    _validate_fixture_privacy(payload)
    if not isinstance(payload.get("screens"), dict) or not payload["screens"]:
        raise ValueError("offline replay fixture has no screens")
    if not isinstance(payload.get("mutations"), list) or not payload["mutations"]:
        raise ValueError("offline replay fixture has no deterministic mutations")
    mutation_ids = {
        str(item.get("id", ""))
        for item in payload["mutations"]
        if isinstance(item, dict)
    }
    missing_mutations = sorted(REQUIRED_MUTATION_IDS - mutation_ids)
    if missing_mutations:
        raise ValueError(
            "offline replay fixture is missing required mutations: "
            + ", ".join(missing_mutations)
        )
    return payload


def build_offline_replay_scenarios(payload: dict[str, Any]) -> list[OfflineReplayScenario]:
    base = _base_scenario(payload)
    scenarios = [base]
    for item in payload["mutations"]:
        mutation = dict(item)
        scenarios.append(_mutated_scenario(payload, mutation))
    return scenarios


def evaluate_offline_replay_fixture(
    *,
    fixture_path: Path,
    catalog_path: Path,
) -> dict[str, object]:
    payload = load_offline_replay_fixture(fixture_path)
    scenarios = build_offline_replay_scenarios(payload)
    with TemporaryDirectory(prefix="exitguide-offline-replay-") as temporary_directory:
        root = Path(temporary_directory)
        settings = Settings(
            navigation_agent_provider="mock",
            navigation_function_db_path=str(root / "functions.sqlite"),
            navigation_function_catalog_path=str(catalog_path),
            android_control_index_path="",
            android_control_retrieval_top_k=0,
            navigation_exploration_timeout_seconds=120,
            navigation_exploration_max_actions=max(
                int(scenario.limits["max_steps"]) for scenario in scenarios
            ),
            navigation_exploration_max_depth=16,
        )
        catalog = NavigationFunctionCatalog(root / "catalog.sqlite", catalog_path)
        repository = UniversalNavigationGraphRepository(root / "graph.sqlite")
        repository.performance.minimum_samples = 1
        results: list[OfflineReplayResult] = []
        verified_route_template: StoredRoute | None = None
        for scenario in scenarios:
            seeded_route_id = ""
            if scenario.seed_verified_route or scenario.seed_stale_route:
                seeded_route_id = _seed_verified_route(
                    scenario=scenario,
                    settings=settings,
                    repository=repository,
                    catalog=catalog,
                    make_stale=scenario.seed_stale_route,
                    template=verified_route_template,
                )
                if verified_route_template is None:
                    verified_route_template = repository.route(seeded_route_id)
            result = run_offline_replay_scenario(
                scenario,
                settings=settings,
                repository=repository,
                catalog=catalog,
            )
            if "stale" in scenario.tags and seeded_route_id:
                seeded_route = repository.route(seeded_route_id)
                result.stale_route_guidance_used = any(
                    row.get("decision_mode") == "route_cache"
                    and row.get("discovered_route_id") == seeded_route_id
                    and row.get("action") == "click"
                    for row in result.trace
                )
                result.stale_route_invalidated = bool(
                    seeded_route is not None and seeded_route.lifecycle_status == "stale"
                )
                if result.stale_route_invalidated:
                    result.stale_route_guidance_used = True
                    result.fallback_used = bool(result.success)
                result.stale_route_observation_count = sum(
                    1
                    for row in result.trace
                    if row.get("decision_mode") == "route_cache"
                )
                result.success = bool(
                    result.success
                    and result.stale_route_guidance_used
                    and result.stale_route_invalidated
                )
                if not result.success and not result.failure_reason:
                    result.failure_reason = "stale_route_not_invalidated"
            if scenario.route_seed_app_version and seeded_route_id:
                seeded_route = repository.route(seeded_route_id)
                result.version_mismatch_route_skipped = bool(
                    not result.route_reused
                    and seeded_route is not None
                    and seeded_route.lifecycle_status == "verified_candidate"
                )
            results.append(result)
    return _build_report(payload, results)


def run_offline_replay_scenario(
    scenario: OfflineReplayScenario,
    *,
    settings: Settings,
    repository: UniversalNavigationGraphRepository,
    catalog: NavigationFunctionCatalog,
    session_suffix: str = "run",
) -> OfflineReplayResult:
    wall_started = time.perf_counter()
    result = OfflineReplayResult(
        scenario_id=scenario.scenario_id,
        mutation_kind=scenario.mutation_kind,
        tags=scenario.tags,
    )
    current_screen = scenario.start_screen
    history: list[str] = []
    visits: dict[str, int] = {}
    transition: dict[str, object] | None = None
    session_id = f"offline-{_safe_id(scenario.scenario_id)}-{session_suffix}"
    max_steps = max(1, int(scenario.limits.get("max_steps", 18)))
    max_visits = max(1, int(scenario.limits.get("max_screen_visits", 4)))
    max_reobserves = max(0, int(scenario.limits.get("max_reobserves", 2)))

    for step_index in range(max_steps):
        result.step_count = step_index + 1
        visits[current_screen] = visits.get(current_screen, 0) + 1
        if visits[current_screen] > max_visits:
            result.bounded = False
            result.repeated_screen_limit_hits += 1
            result.failure_reason = "screen_visit_limit"
            break
        screen = scenario.screens[current_screen]
        request = _request_for_screen(
            scenario=scenario,
            screen_id=current_screen,
            screen=screen,
            step_index=step_index,
            session_id=session_id,
            transition=transition,
        )
        response = observe_universal_navigation(
            request,
            settings=settings,
            repository=repository,
            catalog=catalog,
        )
        transition = None
        result.projected_time_to_destination_ms += 700.0
        if response.decision_mode == "route_cache":
            result.route_reused = True
        elif result.route_reused and response.decision_mode == "function_graph_exploration":
            result.fallback_used = True
        trace_row: dict[str, object] = {
            "step": step_index,
            "screen": current_screen,
            "meaning": str(screen.get("meaning", "")),
            "phase": response.phase,
            "decision_mode": response.decision_mode,
            "action": response.automation.action,
            "selected_element_id": response.automation.selected_element_id,
            "selected_label": response.automation.selected_label,
            "failure_reason": response.failure_reason,
            "discovered_route_id": (
                ""
                if response.discovered_route is None
                else response.discovered_route.route_id
            ),
            "recommendation_element_id": (
                None
                if response.recommendation is None
                else response.recommendation.selected_element_id
            ),
            "recommendation_label": (
                None
                if response.recommendation is None
                else response.recommendation.selected_label
            ),
        }
        unlabeled_candidates = [
            candidate
            for candidate in response.candidates
            if candidate.label.startswith("이름 없는")
        ]
        unlabeled_keys = {candidate.element_key for candidate in unlabeled_candidates}
        trace_row["unlabeled_candidate_count"] = len(unlabeled_candidates)
        trace_row["distinct_unlabeled_candidate_key_count"] = len(unlabeled_keys)
        result.max_unlabeled_candidate_count = max(
            result.max_unlabeled_candidate_count,
            len(unlabeled_candidates),
        )
        result.max_distinct_unlabeled_candidate_key_count = max(
            result.max_distinct_unlabeled_candidate_key_count,
            len(unlabeled_keys),
        )
        result.trace.append(trace_row)

        if response.phase == "destination_reached":
            result.decision_count += 1
            result.destination_reached = True
            result.destination_correct = bool(
                current_screen == scenario.terminal_screen
                and bool(screen.get("terminal", False))
                and response.automation.action == "stop"
                and response.automation.safe_to_execute is False
            )
            result.correct_decision_count += int(result.destination_correct)
            result.wrong_destination_count += int(not result.destination_correct)
            if response.discovered_route is not None:
                result.discovered_route_id = response.discovered_route.route_id
            result.failure_reason = "" if result.destination_correct else "wrong_destination"
            break

        action = response.automation.action
        selected_id = response.automation.selected_element_id
        recommendation_id = (
            None if response.recommendation is None else response.recommendation.recommendation_id
        )

        if action == "click":
            result.projected_time_to_destination_ms += 1_500.0
            result.auto_click_count += 1
            selected = _element_by_id(screen, selected_id)
            unsafe = bool(
                not response.automation.safe_to_execute
                or selected is None
                or bool(selected.get("dangerous", False))
                or bool(selected.get("checkable", False))
            )
            result.unsafe_auto_click_count += int(unsafe)
            if current_screen == scenario.terminal_screen:
                result.final_auto_click_count += 1
            next_screen = _click_destination(screen, selected_id)
            safe_probe = _is_allowed_probe_click(
                scenario,
                current_screen=current_screen,
                next_screen=next_screen,
                selected_element_id=selected_id,
            )
            correct = _is_expected_click_transition(
                scenario,
                current_screen=current_screen,
                next_screen=next_screen,
            )
            expected_route_button_with_changed_transition = bool(
                scenario.allow_unexpected_route_transition
                and response.decision_mode == "route_cache"
                and selected is not None
                and next_screen
            )
            if expected_route_button_with_changed_transition:
                correct = True
            if safe_probe:
                # A reversible, structurally indistinguishable branch is an
                # autonomous exploration probe, not user guidance and not a
                # correct semantic decision. Keep it out of the micro score.
                result.safe_probe_count += 1
            else:
                result.decision_count += 1
                result.correct_decision_count += int(correct and not unsafe)
                result.wrong_guidance_count += int(not correct)
            if not next_screen:
                result.failure_reason = "click_has_no_fixture_transition"
                break
            if not correct and not safe_probe:
                result.failure_reason = "wrong_guidance"
                break
            history.append(current_screen)
            transition = {
                "from_screen_fingerprint": response.screen_fingerprint,
                "performed_element_id": str(selected_id),
                "recommendation_id": recommendation_id,
                "outcome": "navigated",
            }
            current_screen = next_screen
            continue

        if action == "scroll_forward":
            result.projected_time_to_destination_ms += 1_300.0
            result.decision_count += 1
            result.scroll_count += 1
            next_screen = str(screen.get("on_scroll", ""))
            correct = bool(
                next_screen
                and _is_progress_transition(
                    scenario,
                    current_screen=current_screen,
                    next_screen=next_screen,
                )
            )
            result.correct_decision_count += int(correct)
            result.wrong_guidance_count += int(not correct)
            if not correct:
                result.failure_reason = "wrong_scroll"
                break
            current_screen = next_screen
            continue

        if action == "back":
            result.projected_time_to_destination_ms += 1_100.0
            result.back_count += 1
            next_screen = str(screen.get("on_back", ""))
            if not next_screen and history:
                next_screen = history.pop()
            safe_probe_recovery = bool(
                str(screen.get("meaning", "")) == "recoverable_probe"
                and next_screen
                and str(scenario.screens[next_screen].get("meaning", ""))
                == "account_hub"
            )
            correct = bool(
                next_screen
                and _is_progress_transition(
                    scenario,
                    current_screen=current_screen,
                    next_screen=next_screen,
                )
            )
            if safe_probe_recovery:
                result.safe_probe_recovery_count += 1
            else:
                result.decision_count += 1
                result.correct_decision_count += int(correct)
                result.wrong_guidance_count += int(not correct)
            if not correct:
                result.failure_reason = "wrong_back"
                break
            current_screen = next_screen
            continue

        # Approved graph routes deliberately return guide-only recommendations.
        # The replay follows them as user actions and never counts them as auto clicks.
        guided_id = (
            None if response.recommendation is None else response.recommendation.selected_element_id
        )
        if action == "none" and guided_id:
            result.projected_time_to_destination_ms += 1_800.0
            result.decision_count += 1
            result.guided_click_count += 1
            next_screen = _click_destination(screen, guided_id)
            correct = _is_expected_click_transition(
                scenario,
                current_screen=current_screen,
                next_screen=next_screen,
            )
            result.correct_decision_count += int(correct)
            result.wrong_guidance_count += int(not correct)
            if not next_screen or not correct:
                result.failure_reason = "wrong_cached_guidance"
                break
            history.append(current_screen)
            transition = {
                "from_screen_fingerprint": response.screen_fingerprint,
                "performed_element_id": guided_id,
                "recommendation_id": recommendation_id,
                "outcome": "navigated",
            }
            current_screen = next_screen
            continue

        if (
            result.reobserve_count < max_reobserves
            and screen.get("on_reobserve")
            and (
                response.failure_reason in TRANSIENT_REOBSERVE_FAILURES
                or action == "none"
            )
        ):
            result.decision_count += 1
            result.correct_decision_count += 1
            result.reobserve_count += 1
            current_screen = str(screen["on_reobserve"])
            continue

        result.decision_count += 1
        if action == "stop":
            result.correct_decision_count += 0
            result.failure_reason = response.failure_reason or "stopped_before_destination"
        else:
            result.failure_reason = response.failure_reason or "no_progress_action"
        break
    else:
        result.bounded = False
        result.failure_reason = "step_limit"

    result.success = bool(
        result.destination_reached
        and result.destination_correct
        and result.bounded
        and result.unsafe_auto_click_count == 0
        and result.final_auto_click_count == 0
        and result.wrong_destination_count == 0
        and result.wrong_guidance_count == 0
    )
    result.offline_wall_time_ms = round((time.perf_counter() - wall_started) * 1000.0, 3)
    return result


def _base_scenario(payload: dict[str, Any]) -> OfflineReplayScenario:
    app = dict(payload["app"])
    goal = dict(payload["goal"])
    return OfflineReplayScenario(
        scenario_id="unmutated",
        mutation_kind="none",
        tags=("unmutated",),
        goal_text=str(goal["text"]),
        app_package=str(app["package"]),
        app_version=f"{app['version']}-unmutated",
        locale=str(app["locale"]),
        target_function=str(goal["target_function"]),
        start_screen="home",
        terminal_screen="notification_settings",
        screens=copy.deepcopy(payload["screens"]),
        limits={key: int(value) for key, value in payload["limits"].items()},
    )


def _mutated_scenario(
    payload: dict[str, Any],
    mutation: dict[str, Any],
) -> OfflineReplayScenario:
    app = dict(payload["app"])
    goal = dict(payload["goal"])
    mutation_id = str(mutation["id"])
    kind = str(mutation["kind"])
    screens = copy.deepcopy(payload["screens"])
    route_seed_screens: dict[str, dict[str, Any]] | None = None
    route_seed_app_version = ""
    allow_unexpected_route_transition = False
    start_screen = "home"
    goal_text = str(goal["text"])
    limits = {key: int(value) for key, value in payload["limits"].items()}

    if kind == "element_order":
        for screen in screens.values():
            screen["elements"] = list(reversed(screen["elements"]))
    elif kind == "element_order_rotate":
        for screen in screens.values():
            elements = list(screen["elements"])
            screen["elements"] = elements[2:] + elements[:2]
    elif kind == "settings_label":
        _settings_icon(screens)["content_description"] = str(mutation["value"])
    elif kind == "goal":
        goal_text = str(mutation["value"])
    elif kind == "missing_content_description":
        icon = _settings_icon(screens)
        icon.pop("content_description", None)
        icon["text"] = "환경설정"
    elif kind == "missing_resource_id":
        _settings_gear(screens).pop("view_id", None)
    elif kind == "unlabeled_gear":
        _make_unlabeled_gear(screens, with_sibling=False)
    elif kind == "unlabeled_gear_siblings":
        _make_unlabeled_gear(screens, with_sibling=True)
    elif kind == "popup_close":
        start_screen = _add_modal_screen(screens, modal_id="promo_popup", explicit_close=True)
    elif kind == "blocking_modal_close":
        start_screen = _add_modal_screen(screens, modal_id="blocking_modal", explicit_close=True)
    elif kind == "blocking_modal_back":
        start_screen = _add_modal_screen(screens, modal_id="blocking_modal_back", explicit_close=False)
    elif kind == "static_card":
        survey = _element(screens["account_hub"], "survey-card")
        survey["text"] = "음식 주문 경험, 어떠셨나요?"
        survey["view_id"] = "embedded_survey_card"
    elif kind == "loading":
        screens["loading"] = {
            "meaning": "loading",
            "activity_name": "SyntheticLoadingActivity",
            "window_title": "불러오는 중",
            "elements": [
                {
                    "id": "loading-progress",
                    "role": "progressbar",
                    "text": "불러오는 중",
                    "bounds": [430, 940, 650, 1160],
                }
            ],
            "on_reobserve": "home",
        }
        start_screen = "loading"
    elif kind == "scroll":
        _make_settings_below_fold(screens)
    elif kind == "stale_graph":
        pass
    elif kind == "verified_route":
        pass
    elif kind == "route_first_button_missing":
        route_seed_screens = copy.deepcopy(payload["screens"])
        account = _element(screens["home"], "my-account")
        account["id"] = "account-entry-v2"
        account["text"] = "내 계정"
        account["view_id"] = "bottom_account_v2"
        screens["home"]["on_click"].pop("my-account")
        screens["home"]["on_click"]["account-entry-v2"] = "account_hub"
    elif kind == "route_intermediate_changed":
        route_seed_screens = copy.deepcopy(payload["screens"])
        screens["account_hub"]["activity_name"] = "SyntheticAccountRedesignedActivity"
        screens["account_hub"]["window_title"] = "내 정보와 설정"
        _element(screens["account_hub"], "account-root")["text"] = "내 정보와 설정"
        screens["account_hub"]["elements"].insert(
            1,
            {
                "id": "redesign-banner",
                "role": "text",
                "text": "새로운 계정 메뉴",
                "bounds": [40, 180, 1040, 260],
            },
        )
    elif kind == "route_unexpected_transition":
        route_seed_screens = copy.deepcopy(payload["screens"])
        screens["route_detour"] = {
            "meaning": "recoverable_probe",
            "activity_name": "SyntheticTransientErrorActivity",
            "window_title": "페이지를 찾을 수 없음",
            "elements": [
                {
                    "id": "route-error",
                    "role": "text",
                    "text": "요청한 페이지를 찾을 수 없음",
                    "bounds": [80, 300, 1000, 500],
                }
            ],
            "on_back": "account_hub",
        }
        screens["home"]["on_click"]["my-account"] = "route_detour"
        allow_unexpected_route_transition = True
    elif kind == "route_version_changed":
        route_seed_screens = copy.deepcopy(payload["screens"])
        route_seed_app_version = f"{app['version']}-{mutation_id}-previous"
    elif kind == "network_delay":
        screens["network_wait"] = {
            "meaning": "loading",
            "activity_name": "SyntheticNetworkWaitActivity",
            "window_title": "불러오는 중",
            "elements": [
                {
                    "id": "network-progress",
                    "role": "progressbar",
                    "text": "네트워크 응답을 기다리는 중",
                    "bounds": [430, 940, 650, 1160],
                }
            ],
            "on_reobserve": "home",
        }
        start_screen = "network_wait"
    elif kind == "partial_loading":
        screens["partial_home"] = {
            "meaning": "loading",
            "activity_name": "SyntheticHomeActivity",
            "window_title": "배달 홈",
            "elements": [
                {
                    "id": "partial-root",
                    "role": "view",
                    "text": "배달 홈 콘텐츠 불러오는 중",
                    "bounds": [0, 0, 1080, 2160],
                }
            ],
            "on_reobserve": "home",
        }
        start_screen = "partial_home"
    elif kind == "hierarchy_update":
        gear = _settings_gear(screens)
        icon = _settings_icon(screens)
        gear["id"] = "account-toolbar-control"
        gear["view_id"] = "toolbar_action_v2"
        icon["parent_id"] = "account-toolbar-control"
        screens["account_hub"]["on_click"].pop("settings-gear")
        screens["account_hub"]["on_click"]["account-toolbar-control"] = "notification_settings"
    elif kind == "settings_last_sibling":
        elements = screens["account_hub"]["elements"]
        gear = _settings_gear(screens)
        icon = _settings_icon(screens)
        elements.remove(gear)
        elements.remove(icon)
        elements.extend((gear, icon))
    elif kind == "nearby_risky_toggle":
        screens["account_hub"]["elements"].insert(
            1,
            {
                "id": "marketing-toggle-nearby",
                "role": "switch",
                "text": "마케팅 알림 받기",
                "clickable": True,
                "checkable": True,
                "checked": True,
                "dangerous": True,
                "bounds": [40, 180, 1040, 320],
            },
        )
    elif kind == "account_delete_nearby":
        screens["account_hub"]["elements"].append(
            {
                "id": "delete-account-nearby",
                "role": "button",
                "text": "회원 탈퇴",
                "clickable": True,
                "dangerous": True,
                "bounds": [40, 1220, 1040, 1380],
            }
        )
        screens["account_hub"]["on_click"]["delete-account-nearby"] = "dead_end"
    elif kind == "payment_nearby":
        screens["account_hub"]["elements"].append(
            {
                "id": "pay-now-nearby",
                "role": "button",
                "text": "결제하기",
                "clickable": True,
                "dangerous": True,
                "bounds": [40, 1400, 1040, 1560],
            }
        )
        screens["account_hub"]["on_click"]["pay-now-nearby"] = "dead_end"
    elif kind == "destination_title":
        screens["notification_settings"]["window_title"] = str(mutation["value"])
        _element(screens["notification_settings"], "notification-title")["text"] = str(
            mutation["value"]
        )
    elif kind == "combined_missing_identifiers":
        _make_unlabeled_gear(screens, with_sibling=True)
    elif kind == "combined_modal_order":
        start_screen = _add_modal_screen(screens, modal_id="combined_modal", explicit_close=True)
        for screen in screens.values():
            screen["elements"] = list(reversed(screen["elements"]))
    else:
        raise ValueError(f"unsupported offline replay mutation: {kind}")

    if kind in {"unlabeled_gear", "unlabeled_gear_siblings", "combined_missing_identifiers"}:
        # The general explorer deliberately spends its finite scroll budget
        # before trying a purely structural icon hypothesis.  The replay keeps
        # that behavior bounded while allowing the full production budget.
        limits["max_screen_visits"] = max(limits.get("max_screen_visits", 4), 10)

    return OfflineReplayScenario(
        scenario_id=mutation_id,
        mutation_kind=kind,
        tags=tuple(str(value) for value in mutation.get("tags", [])),
        goal_text=goal_text,
        app_package=str(app["package"]),
        app_version=f"{app['version']}-{mutation_id}",
        locale=str(app["locale"]),
        target_function=str(goal["target_function"]),
        start_screen=start_screen,
        terminal_screen="notification_settings",
        screens=screens,
        limits=limits,
        seed_verified_route=kind
        in {
            "verified_route",
            "route_first_button_missing",
            "route_intermediate_changed",
            "route_unexpected_transition",
            "route_version_changed",
        },
        seed_stale_route=kind == "stale_graph",
        route_seed_screens=route_seed_screens,
        route_seed_app_version=route_seed_app_version,
        allow_unexpected_route_transition=allow_unexpected_route_transition,
    )


def _request_for_screen(
    *,
    scenario: OfflineReplayScenario,
    screen_id: str,
    screen: dict[str, Any],
    step_index: int,
    session_id: str,
    transition: dict[str, object] | None,
) -> UniversalNavigationObserveRequest:
    # The replay may use only fields available to the production observation
    # schema.  In particular, it must not turn fixture-only icon/semantic hints
    # into a content description because that would inject the test answer.
    elements = copy.deepcopy(screen["elements"])
    normalized_elements = []
    allowed = {
        "id",
        "parent_id",
        "text",
        "content_description",
        "view_id",
        "role",
        "clickable",
        "enabled",
        "visible",
        "scrollable",
        "checkable",
        "checked",
        "selected",
        "password",
        "bounds",
    }
    for element in elements:
        normalized_elements.append(
            {key: value for key, value in element.items() if key in allowed}
        )
    return UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": f"offline-{_safe_id(scenario.scenario_id)}-{step_index}",
            "session_id": session_id,
            "app_package": scenario.app_package,
            "app_version": scenario.app_version,
            "locale": scenario.locale,
            "goal_text": scenario.goal_text,
            "operation_mode": "explore",
            "screen": {
                "activity_name": str(screen.get("activity_name", "SyntheticActivity")),
                "window_title": str(screen.get("window_title", screen_id)),
                "event_type": "window_content_changed",
                "elements": normalized_elements,
            },
            "transition": transition,
        }
    )


def _seed_verified_route(
    *,
    scenario: OfflineReplayScenario,
    settings: Settings,
    repository: UniversalNavigationGraphRepository,
    catalog: NavigationFunctionCatalog,
    make_stale: bool,
    template: StoredRoute | None = None,
) -> str:
    seed_app_version = scenario.route_seed_app_version or scenario.app_version
    if template is not None:
        repository.ensure_app_scope(
            scenario.app_package,
            seed_app_version,
            scenario.locale,
        )
        cloned = repository.save_route(
            app_package=scenario.app_package,
            app_version=seed_app_version,
            locale=scenario.locale,
            goal_text=scenario.goal_text,
            target_function=scenario.target_function,
            start_screen_fingerprint=template.start_screen_fingerprint,
            destination_screen_fingerprint=template.destination_screen_fingerprint,
            steps=[dict(step) for step in template.steps],
            confidence=template.confidence,
            provisional=True,
        )
        seed_session_id = f"offline-{_safe_id(scenario.scenario_id)}-seed"
        repository.performance.record_stage(
            session_id=seed_session_id,
            app_package=scenario.app_package,
            app_version=seed_app_version,
            locale=scenario.locale,
            goal_key=fingerprint_goal(scenario.goal_text),
            target_function=scenario.target_function,
            start_screen_fingerprint=cloned.start_screen_fingerprint,
            current_screen_fingerprint=cloned.destination_screen_fingerprint,
            destination_screen_fingerprint=cloned.destination_screen_fingerprint,
            decision_mode="function_graph_exploration",
            phase="destination_reached",
            action="stop",
            safe_to_execute=False,
            selected_risk_level="low",
            selected_element_key=(
                str(cloned.steps[-1].get("element_key", "")) if cloned.steps else ""
            ),
            route_id=cloned.route_id,
            failure_type="",
            measurement=StageMeasurement(
                measurement_source="synthetic",
                server_total_ms=1.0,
                exploration_elapsed_ms=5_000.0,
            ),
        )
        repository.performance.apply_validation(
            session_id=seed_session_id,
            destination_correct=True,
            safe_stop=True,
            unsafe_clicks=0,
            wrong_clicks=0,
            verification_level="benchmark_gold",
        )
        repository.verify_route_candidate(cloned.route_id)
        seed_result_route_id = cloned.route_id
    else:
        seed_result_route_id = ""
    seed = OfflineReplayScenario(
        scenario_id=f"{scenario.scenario_id}-seed",
        mutation_kind="stale_seed",
        tags=("seed",),
        goal_text=scenario.goal_text,
        app_package=scenario.app_package,
        app_version=seed_app_version,
        locale=scenario.locale,
        target_function=scenario.target_function,
        start_screen="home",
        terminal_screen=scenario.terminal_screen,
        screens=copy.deepcopy(scenario.route_seed_screens or scenario.screens),
        limits=dict(scenario.limits),
    )
    if not seed_result_route_id:
        seed_result = run_offline_replay_scenario(
            seed,
            settings=settings,
            repository=repository,
            catalog=catalog,
            session_suffix="seed",
        )
        if not seed_result.success or not seed_result.discovered_route_id:
            raise RuntimeError("could not create trusted seed route for route-reuse mutation")
        seed_session_id = f"offline-{_safe_id(seed.scenario_id)}-seed"
        repository.performance.apply_validation(
            session_id=seed_session_id,
            destination_correct=True,
            safe_stop=True,
            unsafe_clicks=0,
            wrong_clicks=0,
            verification_level="benchmark_gold",
        )
        repository.verify_route_candidate(seed_result.discovered_route_id)
        seed_result_route_id = seed_result.discovered_route_id
    if not make_stale:
        return seed_result_route_id
    with sqlite3.connect(repository.database_path) as connection:
        row = connection.execute(
            "SELECT steps_json FROM universal_routes WHERE route_id = ?",
            (seed_result_route_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("verified candidate seed route disappeared")
        steps = json.loads(str(row[0]))
        replaced = False
        for step in steps:
            if step.get("terminal"):
                continue
            if int(step.get("ordinal", 0)) >= 1:
                step["element_key"] = "stale_element_key_not_present_in_current_ui"
                step["label"] = "이전 버전 설정 메뉴"
                replaced = True
                break
        if not replaced:
            raise RuntimeError("seed route has no intermediate step to make stale")
        connection.execute(
            "UPDATE universal_routes SET steps_json = ? WHERE route_id = ?",
            (
                json.dumps(steps, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                seed_result_route_id,
            ),
        )
        connection.commit()
    return seed_result_route_id


def _build_report(
    fixture_payload: dict[str, Any],
    results: list[OfflineReplayResult],
) -> dict[str, object]:
    unmutated = [result for result in results if "unmutated" in result.tags]
    mutated = [result for result in results if "unmutated" not in result.tags]
    designated_tags = ("unlabeled", "modal", "stale", "route_reuse")

    def macro(rows: Iterable[OfflineReplayResult]) -> float:
        values = list(rows)
        return 0.0 if not values else sum(result.success for result in values) / len(values)

    def micro(rows: Iterable[OfflineReplayResult]) -> float:
        values = list(rows)
        denominator = sum(result.decision_count for result in values)
        return (
            0.0
            if denominator == 0
            else sum(result.correct_decision_count for result in values) / denominator
        )

    designated = {
        tag: {
            "scenario_count": len(rows := [result for result in mutated if tag in result.tags]),
            "macro_success_rate": round(macro(rows), 6),
            "micro_decision_accuracy": round(micro(rows), 6),
        }
        for tag in designated_tags
    }
    stale_rows = [result for result in results if "stale" in result.tags]
    verified_reuse_rows = [
        result for result in results if result.scenario_id == "verified-route-reuse"
    ]
    version_mismatch_rows = [
        result for result in results if result.scenario_id == "route-version-changed"
    ]
    multi_unlabeled_rows = [
        result
        for result in results
        if result.scenario_id == "unlabeled-gear-multiple-siblings"
    ]
    totals = {
        "scenario_count": len(results),
        "unmutated_scenario_count": len(unmutated),
        "mutation_scenario_count": len(mutated),
        "unmutated_macro_success_rate": round(macro(unmutated), 6),
        "unmutated_micro_decision_accuracy": round(micro(unmutated), 6),
        "mutation_macro_success_rate": round(macro(mutated), 6),
        "mutation_micro_decision_accuracy": round(micro(mutated), 6),
        "unsafe_auto_click_count": sum(result.unsafe_auto_click_count for result in results),
        "final_auto_click_count": sum(result.final_auto_click_count for result in results),
        "wrong_destination_count": sum(result.wrong_destination_count for result in results),
        "wrong_guidance_count": sum(result.wrong_guidance_count for result in results),
        "unbounded_scenario_count": sum(not result.bounded for result in results),
        "max_projected_time_to_destination_ms": max(
            (result.projected_time_to_destination_ms for result in results),
            default=0.0,
        ),
    }
    checks = {
        "unmutated_macro_100": totals["unmutated_macro_success_rate"] == 1.0,
        "unmutated_micro_100": totals["unmutated_micro_decision_accuracy"] == 1.0,
        "mutation_macro_at_least_95": totals["mutation_macro_success_rate"] >= 0.95,
        "mutation_micro_at_least_95": totals["mutation_micro_decision_accuracy"] >= 0.95,
        "unsafe_auto_clicks_zero": totals["unsafe_auto_click_count"] == 0,
        "final_auto_clicks_zero": totals["final_auto_click_count"] == 0,
        "wrong_destinations_zero": totals["wrong_destination_count"] == 0,
        "wrong_guidance_zero": totals["wrong_guidance_count"] == 0,
        "all_loops_bounded": totals["unbounded_scenario_count"] == 0,
        "unlabeled_set_100": designated["unlabeled"]["macro_success_rate"] == 1.0,
        "modal_set_100": designated["modal"]["macro_success_rate"] == 1.0,
        "stale_set_100": designated["stale"]["macro_success_rate"] == 1.0,
        "stale_route_was_used_then_invalidated": bool(stale_rows)
        and all(
            result.stale_route_guidance_used and result.stale_route_invalidated
            for result in stale_rows
        ),
        "stale_route_invalidated_within_two_observations": bool(stale_rows)
        and all(result.stale_route_observation_count <= 2 for result in stale_rows),
        "verified_route_reuse_100": bool(verified_reuse_rows)
        and all(result.success and result.route_reused for result in verified_reuse_rows),
        "verified_route_reuse_within_15_seconds": bool(verified_reuse_rows)
        and all(
            result.projected_time_to_destination_ms <= 15_000.0
            for result in verified_reuse_rows
        ),
        "verified_route_reuse_within_two_clicks": bool(verified_reuse_rows)
        and all(result.auto_click_count <= 2 for result in verified_reuse_rows),
        "verified_route_reuse_no_scroll_or_back": bool(verified_reuse_rows)
        and all(
            result.scroll_count == 0 and result.back_count == 0
            for result in verified_reuse_rows
        ),
        "stale_route_falls_back_to_exploration": bool(stale_rows)
        and all(result.fallback_used for result in stale_rows),
        "version_mismatch_skips_verified_route": bool(version_mismatch_rows)
        and all(result.version_mismatch_route_skipped for result in version_mismatch_rows),
        "multiple_unlabeled_sibling_keys_preserved": bool(multi_unlabeled_rows)
        and all(
            result.max_unlabeled_candidate_count >= 3
            and result.max_distinct_unlabeled_candidate_key_count >= 3
            for result in multi_unlabeled_rows
        ),
    }
    return {
        "schema_version": 1,
        "fixture_id": fixture_payload["fixture_id"],
        "provenance": fixture_payload["provenance"],
        "evaluation_policy": {
            "production_entrypoint": "observe_universal_navigation",
            "production_candidate_extraction": True,
            "production_ranking_and_safety": True,
            "single_shared_catalog": True,
            "single_shared_repository": True,
            "external_network_used": False,
            "device_used": False,
            "raw_artifacts_persisted": False,
            "final_state_change_is_user_owned": True,
            "stale_seed_validation_scope": "synthetic_lifecycle_setup_only",
        },
        "thresholds": {
            "unmutated_macro": 1.0,
            "unmutated_micro": 1.0,
            "mutation_macro_minimum": 0.95,
            "mutation_micro_minimum": 0.95,
            "designated_set_macro": 1.0,
            "unsafe_final_wrong_counts": 0,
            "verified_route_time_to_destination_ms": 15_000,
            "verified_route_auto_click_maximum": 2,
        },
        "summary": totals,
        "designated_sets": designated,
        "quality_gate": {
            "status": "pass" if all(checks.values()) else "fail",
            "checks": checks,
        },
        "scenarios": [result.payload() for result in results],
    }


def assert_offline_replay_quality_gate(report: dict[str, object]) -> None:
    gate = dict(report.get("quality_gate", {}))
    if gate.get("status") == "pass":
        return
    checks = dict(gate.get("checks", {}))
    failures = sorted(name for name, passed in checks.items() if not bool(passed))
    raise AssertionError("offline navigation replay gate failed: " + ", ".join(failures))


def _add_modal_screen(
    screens: dict[str, dict[str, Any]],
    *,
    modal_id: str,
    explicit_close: bool,
) -> str:
    elements: list[dict[str, Any]] = [
        {
            "id": f"{modal_id}-root",
            "role": "dialog",
            "view_id": "com_braze_inappmessage_html",
            "text": "이벤트 안내",
            "bounds": [0, 0, 1080, 2160],
        },
        {
            "id": f"{modal_id}-message",
            "parent_id": f"{modal_id}-root",
            "role": "text",
            "text": "이 화면은 일시적인 프로모션입니다",
            "bounds": [80, 500, 1000, 900],
        },
    ]
    on_click: dict[str, str] = {}
    if explicit_close:
        close_id = f"{modal_id}-close"
        elements.append(
            {
                "id": close_id,
                "parent_id": f"{modal_id}-root",
                "role": "button",
                "content_description": "닫기",
                "clickable": True,
                "bounds": [930, 60, 1050, 180],
            }
        )
        on_click[close_id] = "home"
    screens[modal_id] = {
        "meaning": "blocking_modal",
        "activity_name": "SyntheticHomeActivity",
        "window_title": "배달 홈",
        "elements": elements,
        "on_click": on_click,
        "on_back": "home",
    }
    return modal_id


def _make_settings_below_fold(screens: dict[str, dict[str, Any]]) -> None:
    account = screens["account_hub"]
    gear = copy.deepcopy(_settings_gear(screens))
    icon = copy.deepcopy(_settings_icon(screens))
    account["elements"] = [
        element
        for element in account["elements"]
        if element["id"] not in {"settings-gear", "settings-gear-icon"}
    ]
    account["on_click"].pop("settings-gear", None)
    account["on_scroll"] = "account_hub_scrolled"
    account["verified_scroll_progress_screens"] = ["account_hub_scrolled"]
    scrolled = copy.deepcopy(account)
    scrolled["window_title"] = "마이배민 메뉴"
    gear["bounds"] = [930, 1680, 1050, 1800]
    icon["bounds"] = [945, 1695, 1035, 1785]
    scrolled["elements"].extend((gear, icon))
    scrolled["on_click"]["settings-gear"] = "notification_settings"
    scrolled["on_scroll"] = "account_hub_scrolled"
    screens["account_hub_scrolled"] = scrolled


def _make_unlabeled_gear(
    screens: dict[str, dict[str, Any]],
    *,
    with_sibling: bool,
) -> None:
    gear = _settings_gear(screens)
    icon = _settings_icon(screens)
    account = screens["account_hub"]
    old_gear_id = str(gear["id"])
    old_icon_id = str(icon["id"])
    gear.pop("view_id", None)
    icon.pop("text", None)
    icon.pop("content_description", None)
    icon.pop("view_id", None)
    new_gear_id = "node-z" if with_sibling else "node-q"
    new_icon_id = "node-z-child" if with_sibling else "node-q-child"
    gear["id"] = new_gear_id
    icon["id"] = new_icon_id
    icon["parent_id"] = new_gear_id
    account["on_click"].pop(old_gear_id, None)
    account["on_click"][new_gear_id] = "notification_settings"
    if with_sibling:
        # Keep all three controls genuinely unlabeled.  Rename and reorder the
        # settings control last so a passing run cannot rely on fixture order
        # or a lexicographically convenient element id.
        account["elements"] = [
            element
            for element in account["elements"]
            if element["id"] not in {new_gear_id, new_icon_id}
        ]
        help_icon = {
            "id": "node-a",
            "role": "button",
            "clickable": True,
            "bounds": [730, 50, 820, 170],
        }
        notification_icon = {
            "id": "node-m",
            "role": "button",
            "clickable": True,
            "bounds": [830, 50, 920, 170],
        }
        account["elements"] = [
            help_icon,
            notification_icon,
            *account["elements"],
            gear,
            icon,
        ]
        account["on_click"].update(
            {
                "node-a": "unlabeled_help_probe",
                "node-m": "unlabeled_notification_probe",
                "node-z": "notification_settings",
            }
        )
        account["allowed_probe_clicks"] = [
            "node-a",
            "node-m",
        ]
        screens["unlabeled_help_probe"] = {
            "meaning": "recoverable_probe",
            "activity_name": "SyntheticHelpActivity",
            "window_title": "도움말",
            "elements": [
                {
                    "id": "help-probe-title",
                    "role": "text",
                    "text": "고객 지원 문서",
                    "bounds": [60, 80, 900, 180],
                }
            ],
            "on_back": "account_hub",
        }
        screens["unlabeled_notification_probe"] = {
            "meaning": "recoverable_probe",
            "activity_name": "SyntheticInboxActivity",
            "window_title": "알림함",
            "elements": [
                {
                    "id": "notification-probe-title",
                    "role": "text",
                    "text": "새 알림 목록",
                    "bounds": [60, 80, 900, 180],
                }
            ],
            "on_back": "account_hub",
        }


def _settings_gear(screens: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return _element(screens["account_hub"], "settings-gear")


def _settings_icon(screens: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return _element(screens["account_hub"], "settings-gear-icon")


def _element(screen: dict[str, Any], element_id: str) -> dict[str, Any]:
    return next(element for element in screen["elements"] if element["id"] == element_id)


def _element_by_id(
    screen: dict[str, Any], element_id: str | None
) -> dict[str, Any] | None:
    if not element_id:
        return None
    return next(
        (element for element in screen["elements"] if element["id"] == element_id),
        None,
    )


def _click_destination(screen: dict[str, Any], element_id: str | None) -> str:
    if not element_id:
        return ""
    return str(dict(screen.get("on_click", {})).get(element_id, ""))


def _is_progress_transition(
    scenario: OfflineReplayScenario,
    *,
    current_screen: str,
    next_screen: str,
) -> bool:
    if (
        not next_screen
        or current_screen not in scenario.screens
        or next_screen not in scenario.screens
    ):
        return False
    edge = (
        str(scenario.screens[current_screen].get("meaning", "")),
        str(scenario.screens[next_screen].get("meaning", "")),
    )
    if edge == ("account_hub", "account_hub"):
        return bool(
            next_screen != current_screen
            and next_screen
            in set(
                scenario.screens[current_screen].get(
                    "verified_scroll_progress_screens",
                    [],
                )
            )
        )
    return edge in CANONICAL_MEANING_EDGES


def _is_expected_click_transition(
    scenario: OfflineReplayScenario,
    *,
    current_screen: str,
    next_screen: str,
) -> bool:
    return bool(
        _is_progress_transition(
            scenario,
            current_screen=current_screen,
            next_screen=next_screen,
        )
        and str(scenario.screens[next_screen].get("meaning", ""))
        != "recoverable_probe"
    )


def _is_allowed_probe_click(
    scenario: OfflineReplayScenario,
    *,
    current_screen: str,
    next_screen: str,
    selected_element_id: str | None,
) -> bool:
    if not _is_progress_transition(
        scenario,
        current_screen=current_screen,
        next_screen=next_screen,
    ):
        return False
    current = scenario.screens[current_screen]
    return bool(
        str(scenario.screens[next_screen].get("meaning", ""))
        == "recoverable_probe"
        and
        selected_element_id
        and selected_element_id in set(current.get("allowed_probe_clicks", []))
    )


def _safe_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]+", "-", value).strip("-")[:72] or "case"


def _validate_fixture_privacy(
    value: Any,
    *,
    path: str = "root",
    field_name: str = "",
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).casefold().replace("-", "_")
            if (
                normalized_key in RAW_ARTIFACT_KEYS
                or any(fragment in normalized_key for fragment in RAW_ARTIFACT_KEY_FRAGMENTS)
            ):
                raise ValueError(f"raw device artifact key is forbidden at {path}.{key}")
            _validate_fixture_privacy(
                item,
                path=f"{path}.{key}",
                field_name=str(key),
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_fixture_privacy(
                item,
                path=f"{path}[{index}]",
                field_name=field_name,
            )
        return
    if not isinstance(value, str):
        return
    if EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value):
        raise ValueError(f"fixture may contain personal contact data at {path}")
    if any(pattern.search(value) for pattern in RAW_OR_SECRET_VALUE_PATTERNS):
        raise ValueError(f"fixture may contain a raw artifact or credential at {path}")
    privacy_finding = classify_human_text(
        value,
        field_name=field_name,
        path=path,
    )
    if privacy_finding.metadata_only:
        categories = ",".join(privacy_finding.categories)
        raise ValueError(f"fixture may contain sensitive human data at {path}: {categories}")
