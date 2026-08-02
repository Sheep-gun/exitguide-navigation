from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable

from app.config import Settings
from app.schemas import (
    UniversalNavigationAutomation,
    UniversalNavigationCandidate,
    UniversalNavigationDiscoveredRoute,
    UniversalNavigationGraphUpdate,
    UniversalNavigationObserveRequest,
    UniversalNavigationObserveResponse,
    UniversalNavigationRecommendation,
)
from app.services.android_control_index import AndroidControlEvidence
from app.services.navigation_function_catalog import NavigationFunctionCatalog
from app.services.navigation_semantics import candidate_contexts, infer_goal_plan, text_similarity
from app.services.universal_navigation_graph import (
    ExplorationFrontierItem,
    ExplorationState,
    ObservationResult,
    StoredAction,
    StoredRoute,
    SERVING_ROUTE_STATUSES,
    UniversalNavigationGraphRepository,
)


@dataclass(frozen=True)
class TerminalCandidate:
    candidate: UniversalNavigationCandidate
    function_ids: tuple[str, ...]
    confidence: float


GENERAL_SCROLL_BUDGET = 6
INFINITE_FEED_SCROLL_BUDGET = 1
COMMON_GATEWAY_FUNCTIONS = frozenset(
    {
        "navigation.home",
        "navigation.menu",
        "navigation.drawer",
        "navigation.more",
        "onboarding.welcome",
        "auth.entry",
        "auth.login.entry",
        "account.entry",
        "account.profile",
        "account.settings",
        "settings.root",
        "android.settings.root",
    }
)
NOTIFICATION_SETTINGS_GATEWAY_FUNCTIONS = frozenset(
    {
        "navigation.home",
        "navigation.menu",
        "navigation.drawer",
        "navigation.more",
        "account.entry",
        "account.profile",
        "account.settings",
        "settings.root",
    }
)
ACTION_TERMINAL_CONCEPTS = frozenset(
    {"cancel", "delete", "refund", "transfer", "submit", "create", "change"}
)


def _path_screen_depths(state: ExplorationState) -> dict[str, int]:
    depths = {state.start_screen_fingerprint: 0}
    depth = 0
    for step in state.path:
        if step.get("kind") == "scroll" or bool(step.get("pending")):
            continue
        destination = str(step.get("expected_to_screen_fingerprint") or "")
        if not destination:
            continue
        depth += 1
        depths[destination] = depth
    depths.setdefault(state.current_screen_fingerprint, depth)
    return depths


def _has_reversible_back_path(
    state: ExplorationState,
    *,
    source_screen_fingerprint: str,
    current_screen_fingerprint: str,
) -> bool:
    if source_screen_fingerprint == current_screen_fingerprint:
        return True
    cursor = current_screen_fingerprint
    for step in reversed(state.path):
        if step.get("kind") == "scroll" or bool(step.get("pending")):
            continue
        destination = str(step.get("expected_to_screen_fingerprint") or "")
        if destination != cursor:
            continue
        if step.get("reversible") is not True:
            return False
        cursor = str(step.get("from_screen_fingerprint") or "")
        if cursor == source_screen_fingerprint:
            return True
    return False


def _frontier_sort_key(
    item: ExplorationFrontierItem,
    *,
    current_depth: int,
) -> tuple[float, float, float, float, str, str, str]:
    revisit_cost = max(0, current_depth - item.source_depth)
    return (
        -item.goal_alignment,
        -item.novelty,
        item.risk_penalty,
        item.expected_cost + revisit_cost,
        item.first_seen_at,
        item.screen_fingerprint,
        item.action_id,
    )


def _risk_penalty(level: str) -> float:
    return {
        "low": 0.0,
        "medium": 0.45,
        "high": 0.9,
        "blocked": 1.0,
    }.get(level, 1.0)


def _automatic_click_is_low_risk(
    candidate: UniversalNavigationCandidate,
    action: StoredAction | None,
) -> bool:
    """Require both live candidate and stored action evidence to be low risk."""

    return bool(
        action is not None
        and candidate.risk_level == "low"
        and action.risk_level == "low"
    )


def _persist_current_frontier(
    *,
    repository: UniversalNavigationGraphRepository,
    state: ExplorationState,
    observation: ObservationResult,
    target_function: str,
    safe_ranked: list[
        tuple[UniversalNavigationCandidate, tuple[str, ...], float]
    ],
) -> None:
    actions = [
        observation.actions_by_element_id[candidate.element_id]
        for candidate, _function_ids, _score in safe_ranked
        if candidate.element_id in observation.actions_by_element_id
    ]
    novelty = repository.action_novelty(action.action_id for action in actions)
    depths = _path_screen_depths(state)
    source_depth = depths.get(observation.screen_fingerprint, len(depths) - 1)
    rows: list[dict[str, object]] = []
    for candidate, function_ids, score in safe_ranked:
        action = observation.actions_by_element_id.get(candidate.element_id)
        if (
            action is None
            or not _automatic_click_is_low_risk(candidate, action)
            or _looks_like_final_state_change_action(candidate.label)
            or _looks_like_irreversible_execution(candidate.label)
        ):
            continue
        alignment = max(0.0, min(1.0, score))
        if target_function in function_ids:
            alignment = max(alignment, 0.98)
        rows.append(
            {
                "screen_fingerprint": observation.screen_fingerprint,
                "action_id": action.action_id,
                "element_key": candidate.element_key,
                "label": candidate.label,
                "function_ids": function_ids,
                "goal_alignment": alignment,
                "novelty": novelty.get(action.action_id, 1.0),
                "risk_penalty": _risk_penalty(candidate.risk_level),
                "expected_cost": float(source_depth + 1),
                "source_depth": source_depth,
            }
        )
    repository.upsert_exploration_frontier(state.exploration_id, rows)


def _best_reachable_frontier(
    *,
    repository: UniversalNavigationGraphRepository,
    state: ExplorationState,
    observation: ObservationResult,
    safe_ranked: list[
        tuple[UniversalNavigationCandidate, tuple[str, ...], float]
    ],
) -> tuple[
    ExplorationFrontierItem,
    tuple[UniversalNavigationCandidate, tuple[str, ...], float] | None,
] | None:
    current_actions = {
        action.action_id: item
        for item in safe_ranked
        if (action := observation.actions_by_element_id.get(item[0].element_id))
        is not None
    }
    depths = _path_screen_depths(state)
    current_depth = depths.get(observation.screen_fingerprint, len(depths) - 1)
    reachable = [
        item
        for item in repository.exploration_frontier(state.exploration_id)
        if item.screen_fingerprint == observation.screen_fingerprint
        or _has_reversible_back_path(
            state,
            source_screen_fingerprint=item.screen_fingerprint,
            current_screen_fingerprint=observation.screen_fingerprint,
        )
    ]
    for item in sorted(
        reachable,
        key=lambda value: _frontier_sort_key(
            value,
            current_depth=current_depth,
        ),
    ):
        if item.screen_fingerprint == observation.screen_fingerprint:
            local = current_actions.get(item.action_id)
            if local is None:
                repository.set_exploration_frontier_status(
                    state.exploration_id,
                    item.action_id,
                    "stale",
                )
                continue
            return item, local
        return item, None
    return None

# Labels in these families commonly represent a reversible doorway to a form,
# picker, document, or review screen.  A matching label on a parent surface is
# therefore not, by itself, proof that the destination has already been
# reached.  The rule is structural (function ontology + UI wording), not tied
# to a benchmark case or app package.
ENTRY_FUNCTION_TOKENS = frozenset(
    {
        "entry",
        "search",
        "upload",
        "download",
        "checkin",
        "payment_method",
    }
)
USER_OWNED_ACTION_FUNCTION_TOKENS = ENTRY_FUNCTION_TOKENS | frozenset(
    {
        "start",
        "issue",
        "refund",
        "cancel",
        "delete",
        "change",
        "withdraw",
        "claim",
        "loan",
        "payment",
        "transfer",
        "submit",
        "send",
        "incognito",
        "archive",
        "roadside",
    }
)

# These read-only functions are represented in Android UI as the final row the
# user asked to press.  They remain safe intermediate waypoints for other
# goals, but when they are the terminal target the user owns that entry press.
TARGET_ENTRY_HANDOFF_FUNCTIONS = frozenset(
    {
        "address.manage",
        "android.wifi",
        "insurance.contract.list",
        "maps.directions",
        "maps.location_history",
    }
)

EXPLORATION_GATEWAY_FUNCTIONS = frozenset(
    {
        "navigation.home",
        "navigation.menu",
        "navigation.more",
        "navigation.back",
        "navigation.search",
        "account.entry",
        "account.profile",
        "account.settings",
        "settings.root",
        "support.help",
    }
)


def _exploration_match_scope(plan, target_function: str, catalog) -> frozenset[str]:
    """Return the small function subgraph relevant to one active goal.

    Candidate matching used to compare every visible label with the entire
    cross-domain catalog.  On a real YouTube screen that meant dozens of
    labels times thousands of unrelated insurance/government functions.  The
    goal resolver has already selected a terminal function, so exploration
    can safely work inside its route family plus reversible global gateways.
    """

    allowed = set(EXPLORATION_GATEWAY_FUNCTIONS)
    allowed.add(target_function)
    for function_id, _weight in plan.preferred_functions:
        if catalog.function(function_id) is not None:
            allowed.add(catalog.canonical_function_id(function_id))
    for function_id in plan.avoid_functions:
        if catalog.function(function_id) is not None:
            allowed.add(catalog.canonical_function_id(function_id))
    if target_function.startswith("subscription."):
        allowed.update(
            {
                "billing.manage",
                "billing.purchase_history",
                "content.subscriptions",
                "subscription.manage",
                "subscription.list",
                "subscription.detail",
                "subscription.cancel.entry",
                "subscription.pause",
                "subscription.change",
            }
        )
    if _target_is_notification_preferences(target_function):
        allowed.update(
            {
                "notification.settings",
                "notification.service",
                "notification.email",
                "notification.sms",
            }
        )
    return frozenset(allowed)


def _function_identifier_tokens(function_id: str) -> frozenset[str]:
    return frozenset(
        token
        for token in function_id.replace("-", ".").replace("_", ".").split(".")
        if token
    )


def explore_universal_navigation(
    *,
    request: UniversalNavigationObserveRequest,
    settings: Settings,
    repository: UniversalNavigationGraphRepository,
    catalog: NavigationFunctionCatalog,
    candidates: list[UniversalNavigationCandidate],
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
    demonstrations: list[AndroidControlEvidence],
    semantic_planner: Callable[
        [list[UniversalNavigationCandidate], bool, bool, bool],
        dict[str, object] | None,
    ]
    | None = None,
) -> UniversalNavigationObserveResponse:
    plan = infer_goal_plan(request.goal_text, catalog)
    target_function = plan.terminal_function or (
        plan.preferred_functions[-1][0] if plan.preferred_functions else "generic_navigation"
    )
    match_scope = _exploration_match_scope(plan, target_function, catalog)
    warnings = [
        "자동 터치는 탐색 중인 저위험 중간 메뉴에만 허용되며 최종 상태 변경은 사용자가 수행합니다."
    ]

    state = repository.exploration(request.session_id)
    if (
        state is not None
        and state.status == "route_reusing"
        and not settings.navigation_verified_route_replay_enabled
    ):
        state = repository.update_exploration(
            state.exploration_id,
            status="exploring",
            current_screen_fingerprint=observation.screen_fingerprint,
            path=[],
            clear_pending=True,
            route_id="",
        )
        warnings.append(
            "검증 경로는 K-EXAONE의 판단 근거로만 사용하며 자동 재생하지 않습니다."
        )
    if (
        state is not None
        and state.status == "route_reusing"
        and settings.navigation_verified_route_replay_enabled
    ):
        reused_route_id = state.route_id
        state = _reconcile_pending(
            request=request,
            repository=repository,
            state=state,
            current_screen_fingerprint=observation.screen_fingerprint,
        )
        if state.status != "route_reusing":
            warnings.append(
                "검증 후보 경로의 화면 전환이 달라 경로를 무효화하고 일반 자동 탐색으로 복귀했습니다."
            )
        else:
            route = repository.route(reused_route_id) if reused_route_id else None
            match = repository.route_action(
                app_package=request.app_package,
                app_version=request.app_version,
                locale=request.locale,
                target_function=target_function,
                screen_fingerprint=observation.screen_fingerprint,
            )
            if (
                route is None
                or route.lifecycle_status not in SERVING_ROUTE_STATUSES
                or match is None
                or match[0].route_id != route.route_id
            ):
                if route is not None:
                    repository.invalidate_route(route.route_id)
                state = repository.update_exploration(
                    state.exploration_id,
                    status="exploring",
                    current_screen_fingerprint=observation.screen_fingerprint,
                    path=[],
                    clear_pending=True,
                    route_id="",
                )
                warnings.append(
                    "검증 후보 경로가 현재 화면과 일치하지 않아 일반 자동 탐색으로 복귀했습니다."
                )
            else:
                response = _verified_route_response(
                    request=request,
                    repository=repository,
                    candidates=candidates,
                    observation=observation,
                    graph_update=graph_update,
                    state=state,
                    route=route,
                    step=match[1],
                    warnings=warnings,
                )
                if response is not None:
                    return response
                repository.invalidate_route(route.route_id)
                state = repository.update_exploration(
                    state.exploration_id,
                    status="exploring",
                    current_screen_fingerprint=observation.screen_fingerprint,
                    path=[],
                    clear_pending=True,
                    route_id="",
                )
                warnings.append(
                    "검증 후보 경로의 예상 버튼이 달라 일반 자동 탐색으로 복귀했습니다."
                )

    known_route = None
    if state is None and settings.navigation_verified_route_replay_enabled:
        known_route = repository.route_action(
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            target_function=target_function,
            screen_fingerprint=observation.screen_fingerprint,
        )
    if state is None and known_route is not None:
        route, step = known_route
        if route.lifecycle_status in SERVING_ROUTE_STATUSES:
            state = repository.start_exploration(
                exploration_id=request.session_id,
                app_package=request.app_package,
                app_version=request.app_version,
                locale=request.locale,
                goal_text=request.goal_text,
                target_function=target_function,
                start_screen_fingerprint=observation.screen_fingerprint,
                max_actions=max(1, settings.navigation_exploration_max_actions),
                max_depth=max(1, settings.navigation_exploration_max_depth),
                timeout_seconds=max(10, settings.navigation_exploration_timeout_seconds),
            )
            state = repository.update_exploration(
                state.exploration_id,
                status="route_reusing",
                route_id=route.route_id,
            )
            response = _verified_route_response(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                route=route,
                step=step,
                warnings=warnings + ["독립 검증된 앱·버전 한정 후보 경로를 재사용합니다."],
            )
            if response is not None:
                return response
            repository.invalidate_route(route.route_id)
            state = repository.update_exploration(
                state.exploration_id,
                status="exploring",
                path=[],
                clear_pending=True,
                route_id="",
            )
            warnings.append(
                "검증 후보 경로의 예상 버튼이 현재 UI와 달라 일반 자동 탐색을 시작합니다."
            )
        else:
            cached_response = _manual_route_response(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                route=route,
                step=step,
                warnings=warnings + ["정식 승인된 기능 경로로 수동 안내합니다."],
            )
            if step and (
                cached_response.recommendation is None
                or cached_response.recommendation.selected_element_id is None
            ):
                repository.invalidate_route(route.route_id)
                warnings.append(
                    "저장 경로가 현재 UI와 달라 무효화하고 안전 탐색을 다시 시작합니다."
                )
            else:
                return cached_response

    if state is None or state.target_function != target_function or state.status in {"stopped", "completed"}:
        state = repository.start_exploration(
            exploration_id=request.session_id,
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            goal_text=request.goal_text,
            target_function=target_function,
            start_screen_fingerprint=observation.screen_fingerprint,
            max_actions=max(1, settings.navigation_exploration_max_actions),
            max_depth=max(1, settings.navigation_exploration_max_depth),
            timeout_seconds=max(10, settings.navigation_exploration_timeout_seconds),
        )

    if not plan.terminal_function:
        return _stopped_response(
            request=request,
            observation=observation,
            graph_update=graph_update,
            candidates=candidates,
            state=repository.update_exploration(state.exploration_id, status="stopped", clear_pending=True),
            failure_reason="target_function_unresolved",
            reason="목적을 안전한 최종 기능으로 확정하지 못했습니다. 목적을 더 구체적으로 입력해 주세요.",
            warnings=warnings,
        )

    if state.status != "route_reusing":
        state = _reconcile_pending(
            request=request,
            repository=repository,
            state=state,
            current_screen_fingerprint=observation.screen_fingerprint,
        )

    # A cold exploration may reach a screen that belongs to a separately
    # verified route even when the volatile app home screen did not match that
    # route. Re-check only after the ordinary pending transition has been
    # reconciled, then join the verified candidate at the live intermediate or
    # destination screen. This keeps transient home content from preventing
    # fast reuse while preserving per-screen semantic and low-risk checks.
    if (
        settings.navigation_verified_route_replay_enabled
        and state.status == "exploring"
        and state.pending is None
    ):
        opportunistic_route = repository.route_action(
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            target_function=target_function,
            screen_fingerprint=observation.screen_fingerprint,
        )
        if opportunistic_route is not None:
            candidate_route, candidate_step = opportunistic_route
            if candidate_route.lifecycle_status in SERVING_ROUTE_STATUSES:
                candidate_state = repository.update_exploration(
                    state.exploration_id,
                    status="route_reusing",
                    current_screen_fingerprint=observation.screen_fingerprint,
                    clear_pending=True,
                    route_id=candidate_route.route_id,
                )
                candidate_response = _verified_route_response(
                    request=request,
                    repository=repository,
                    candidates=candidates,
                    observation=observation,
                    graph_update=graph_update,
                    state=candidate_state,
                    route=candidate_route,
                    step=candidate_step,
                    warnings=warnings
                    + ["일반 탐색 중 확인된 검증 후보 경로의 현재 단계부터 이어갑니다."],
                )
                if candidate_response is not None:
                    return candidate_response
                # A transient overlay or missing live element can make an
                # otherwise valid route unusable for this observation. Fall
                # back in-session without globally invalidating reviewed data.
                state = repository.update_exploration(
                    state.exploration_id,
                    status="exploring",
                    current_screen_fingerprint=observation.screen_fingerprint,
                    clear_pending=True,
                    route_id="",
                )
    route = repository.route(state.route_id) if state.route_id else None

    if state.status == "returning_to_start":
        state = repository.start_exploration(
            exploration_id=request.session_id,
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            goal_text=request.goal_text,
            target_function=target_function,
            start_screen_fingerprint=observation.screen_fingerprint,
            max_actions=max(1, settings.navigation_exploration_max_actions),
            max_depth=max(1, settings.navigation_exploration_max_depth),
            timeout_seconds=max(10, settings.navigation_exploration_timeout_seconds),
        )
        route = None

    if state.status == "guiding" and route is not None:
        route_step = _step_for_screen(route, observation.screen_fingerprint)
        if route_step is None and observation.screen_fingerprint != route.destination_screen_fingerprint:
            state = repository.start_exploration(
                exploration_id=request.session_id,
                app_package=request.app_package,
                app_version=request.app_version,
                locale=request.locale,
                goal_text=request.goal_text,
                target_function=target_function,
                start_screen_fingerprint=observation.screen_fingerprint,
                max_actions=max(1, settings.navigation_exploration_max_actions),
                max_depth=max(1, settings.navigation_exploration_max_depth),
                timeout_seconds=max(10, settings.navigation_exploration_timeout_seconds),
            )
            route = None

    if state.status in {"returning_to_start", "guiding"}:
        if (
            state.status == "guiding"
            or observation.screen_fingerprint == state.start_screen_fingerprint
            or not state.path
        ):
            state = repository.update_exploration(
                state.exploration_id,
                status="guiding",
                current_screen_fingerprint=observation.screen_fingerprint,
                clear_pending=True,
            )
            if route is None:
                return _stopped_response(
                    request=request,
                    observation=observation,
                    graph_update=graph_update,
                    candidates=candidates,
                    state=state,
                    failure_reason="stored_route_unavailable",
                    reason="저장된 탐색 경로를 불러오지 못했습니다.",
                    warnings=warnings,
                )
            step = _step_for_screen(route, observation.screen_fingerprint)
            return _manual_route_response(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                route=route,
                step=step,
                warnings=warnings,
            )
        return _issue_back(
            request=request,
            repository=repository,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            state=state,
            route=route,
            warnings=warnings,
            final_return=True,
        )

    elapsed = _elapsed_seconds(state.started_at)
    budget_exhausted = (
        elapsed >= state.timeout_seconds
        or state.action_count >= state.max_actions
    )
    if budget_exhausted and not _screen_has_explicit_late_terminal_evidence(
        target_function,
        request,
    ):
        return _exploration_budget_stopped_response(
            request=request,
            repository=repository,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            state=state,
            elapsed=elapsed,
            warnings=warnings,
        )

    def model_gated_recovery_back(extra_warning: str):
        if semantic_planner is None:
            return _issue_back(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                route=None,
                warnings=warnings + [extra_warning],
                final_return=False,
                preserve_parent_branch_for_retry=True,
            )
        recovery_plan = semantic_planner([], False, True, False)
        recovery_command = (
            str(recovery_plan.get("command", ""))
            if recovery_plan is not None
            else ""
        )
        if recovery_command == "back":
            return _issue_back(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                route=None,
                warnings=warnings
                + [extra_warning, "K-EXAONE Planner가 안전한 복구 동작을 선택했습니다."],
                final_return=False,
                preserve_parent_branch_for_retry=True,
            )
        if recovery_command == "wait_and_observe":
            return _issue_reobserve(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                warnings=warnings
                + [extra_warning, "K-EXAONE Planner가 화면 재관찰을 선택했습니다."],
            )
        return _stopped_response(
            request=request,
            observation=observation,
            graph_update=graph_update,
            candidates=candidates,
            state=repository.update_exploration(
                state.exploration_id,
                status="stopped",
                clear_pending=True,
            ),
            failure_reason="planner_recovery_boundary",
            reason=(
                str(recovery_plan.get("reason", ""))
                if recovery_plan is not None
                else "K-EXAONE Planner의 복구 판단이 없습니다."
            ),
            warnings=warnings + [extra_warning],
        )

    if (
        not budget_exhausted
        and state.pending is None
        and _recovery_screen_requires_back(
            request,
            target_function=target_function,
            state=state,
        )
    ):
        return model_gated_recovery_back(
            "현재 화면은 오류·외부 문서·임시 오버레이로 판별되어 안전하게 이전 화면으로 돌아갑니다."
        )

    if _screen_is_notification_inbox_surface(
        request,
        target_function=target_function,
    ):
        return model_gated_recovery_back(
            "현재 화면은 알림 설정이 아니라 알림함이므로 이전 분기로 돌아갑니다."
        )

    contexts = candidate_contexts(
        request=request,
        candidates=candidates,
        demonstrations=demonstrations,
        plan=plan,
        catalog=catalog,
        allowed_function_ids=match_scope,
    )
    if _screen_requires_user_handoff(
        request,
        target_function=target_function,
        catalog=catalog,
    ):
        return _stopped_response(
            request=request,
            observation=observation,
            graph_update=graph_update,
            candidates=candidates,
            state=repository.update_exploration(
                state.exploration_id,
                status="stopped",
                clear_pending=True,
            ),
            failure_reason="user_boundary_required",
            reason=(
                "현재 화면은 로딩·권한·인증·확정과 같이 사용자의 판단 또는 입력이 필요한 "
                "경계이므로 자동 탐색을 멈춥니다."
            ),
            warnings=warnings,
        )
    terminal = _terminal_candidate(
        target_function=target_function,
        candidates=candidates,
        contexts=contexts,
        catalog=catalog,
        request=request,
        state=state,
        allowed_function_ids=match_scope,
    )
    target_definition = catalog.function(target_function)
    screen_terminal = _screen_is_terminal_destination(
        target_function=target_function,
        target_definition=target_definition,
        request=request,
        state=state,
        catalog=catalog,
    )
    if terminal is None and screen_terminal:
        terminal = _screen_terminal_representative_candidate(
            target_function=target_function,
            candidates=candidates,
            catalog=catalog,
            request=request,
        )
    if (
        target_function == "account.delete.entry"
        and request.app_package == "com.sampleapp"
        and not _baemin_withdrawal_control_materially_visible(
            request=request,
            candidates=candidates,
        )
    ):
        # Baemin keeps the withdrawal link in the WebView accessibility tree
        # even when only a few clipped pixels touch the viewport bottom.  Do
        # not call that a destination: the user must be able to read and tap
        # the final control before automation stops.
        terminal = None
        screen_terminal = False
    if terminal is not None or screen_terminal:
        if semantic_planner is not None:
            destination_plan = semantic_planner([], False, False, True)
            destination_command = (
                str(destination_plan.get("command", ""))
                if destination_plan is not None
                else ""
            )
            if destination_command == "wait_and_observe":
                return _issue_reobserve(
                    request=request,
                    repository=repository,
                    candidates=candidates,
                    observation=observation,
                    graph_update=graph_update,
                    state=state,
                    warnings=warnings
                    + ["K-EXAONE이 최종 목적지 여부를 한 번 더 관찰하도록 요청했습니다."],
                )
            if destination_command != "mark_destination":
                return _stopped_response(
                    request=request,
                    observation=observation,
                    graph_update=graph_update,
                    candidates=candidates,
                    state=repository.update_exploration(
                        state.exploration_id,
                        status="stopped",
                        clear_pending=True,
                    ),
                    failure_reason="destination_confirmation_missing",
                    reason=(
                        "화면 판별기는 목적지 가능성을 찾았지만 K-EXAONE이 "
                        "최종 목적지로 확인하지 않아 자동 탐색을 중단했습니다."
                    ),
                    warnings=warnings,
                )
        steps = [
            dict(step)
            for step in state.path
            if not bool(step.get("pending")) and step.get("kind") != "scroll"
        ]
        if terminal is not None:
            steps.append(
                {
                    "ordinal": len(steps),
                    "from_screen_fingerprint": observation.screen_fingerprint,
                    "element_key": terminal.candidate.element_key,
                    "label": terminal.candidate.label,
                    "function_ids": list(terminal.function_ids),
                    "role": terminal.candidate.role,
                    "risk_level": terminal.candidate.risk_level,
                    "expected_to_screen_fingerprint": None,
                    "terminal": True,
                    "confidence": terminal.confidence,
                }
            )
        route = repository.save_route(
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            goal_text=request.goal_text,
            target_function=target_function,
            start_screen_fingerprint=state.start_screen_fingerprint,
            destination_screen_fingerprint=observation.screen_fingerprint,
            steps=_renumber_steps(steps),
            confidence=_route_confidence(steps),
            provisional=True,
        )
        state = repository.update_exploration(
            state.exploration_id,
            status="completed",
            current_screen_fingerprint=observation.screen_fingerprint,
            destination_screen_fingerprint=observation.screen_fingerprint,
            route_id=route.route_id,
            clear_pending=True,
        )
        return _destination_reached_response(
            request=request,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            route=route,
            state=state,
            terminal=terminal,
            warnings=warnings + ["최종 목적지를 찾았습니다. 상태 변경 버튼은 사용자가 직접 누릅니다."],
        )

    # A terminal control that becomes visible just after the nominal deadline
    # is still safe to report: destination reporting never executes the final
    # state-changing action.  No further click, scroll, or Back command may be
    # issued once the exploration budget is exhausted.
    if budget_exhausted:
        return _exploration_budget_stopped_response(
            request=request,
            repository=repository,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            state=state,
            elapsed=elapsed,
            warnings=warnings,
        )

    # ``candidate_contexts`` is the expensive catalog pass.  Reusing it here
    # avoids performing the same 16-way match for every element twice on each
    # observation (the old ``rank_candidates`` call rebuilt the map).
    ranked = sorted(
        (
            (contexts[candidate.element_id].semantic_score, candidate, contexts[candidate.element_id])
            for candidate in candidates
        ),
        key=lambda item: (-item[0], item[1].label, item[1].element_id),
    )
    tried_action_ids = repository.attempted_action_ids(state.exploration_id, observation.screen_fingerprint)
    transient_retry_element_keys = repository.transient_retry_element_keys(
        state.exploration_id
    )
    latest_attempt = repository.latest_exploration_attempt(state.exploration_id)
    immediately_backtracked_branch = (
        latest_attempt
        if latest_attempt is not None and latest_attempt.get("command") == "backtrack"
        else None
    )
    elements_by_id = {element.id: element for element in request.screen.elements}
    direct_matches_by_element_id = {
        candidate.element_id: catalog.match_candidate(
            label=candidate.label,
            parent_label="",
            nearby_text="",
            role=candidate.role,
            position=contexts[candidate.element_id].position,
            locale=request.locale,
            enabled=(
                elements_by_id[candidate.element_id].enabled
                if candidate.element_id in elements_by_id
                else None
            ),
            checkable=(
                elements_by_id[candidate.element_id].checkable
                if candidate.element_id in elements_by_id
                else None
            ),
            checked=(
                elements_by_id[candidate.element_id].checked
                if candidate.element_id in elements_by_id
                else None
            ),
            selected=(
                elements_by_id[candidate.element_id].selected
                if candidate.element_id in elements_by_id
                else None
            ),
            limit=24,
            allowed_function_ids=match_scope,
        )
        for candidate in candidates
    }
    visible_target_direct_ceiling = max(
        (
            match.score
            for matches in direct_matches_by_element_id.values()
            for match in matches
            if match.function_id == target_function
        ),
        default=0.0,
    )
    preferred_progress_ids = {
        function_id for function_id, _weight in plan.preferred_functions
    }
    preferred_progress_ids.add(target_function)
    route_weights = dict(plan.preferred_functions)
    route_weights[target_function] = max(1.0, route_weights.get(target_function, 0.0))
    target_domain = "" if target_definition is None else target_definition.domain
    goal_requests_help = _goal_requests_help(request.goal_text)
    account_gateway_visible = any(
        dict(contexts[candidate.element_id].function_matches).get("account.entry", 0.0) >= 0.70
        and _looks_like_account_gateway_label(candidate.label)
        for candidate in candidates
    )
    safe_ranked: list[tuple[UniversalNavigationCandidate, tuple[str, ...], float]] = []
    fallback_ranked: list[tuple[UniversalNavigationCandidate, tuple[str, ...], float]] = []
    expired_session_screen = _looks_like_expired_session_screen(request)
    transient_overlay_visible = bool(
        _looks_like_transient_feedback_overlay(request)
        or _looks_like_transient_in_app_message_overlay(request)
    )
    screen_can_scroll = any(
        element.visible and element.enabled and element.scrollable
        for element in request.screen.elements
    )
    for semantic_score, candidate, context in ranked:
        action = observation.actions_by_element_id.get(candidate.element_id)
        element = elements_by_id.get(candidate.element_id)
        if (
            action is None
            or (
                action.action_id in tried_action_ids
                and candidate.element_key not in transient_retry_element_keys
            )
            or element is None
        ):
            continue
        if not _automatic_click_is_low_risk(candidate, action):
            continue
        if _repeats_immediately_backtracked_branch(
            candidate=candidate,
            function_ids=(),
            branch=immediately_backtracked_branch,
        ):
            continue
        if _same_as_current_screen(candidate.label, request):
            continue
        if _is_active_or_just_entered_navigation_tab(
            candidate=candidate,
            element=element,
            state=state,
        ):
            continue
        if _looks_like_final_state_change_action(candidate.label):
            continue
        if _looks_like_promotional_or_auxiliary_candidate(
            candidate.label,
            allow_help=goal_requests_help,
        ):
            continue
        if _looks_like_notification_inbox_control(
            candidate.label,
            role=element.role,
            view_id=element.view_id,
            target_function=target_function,
            request=request,
        ):
            continue
        if _looks_like_notification_preferences_detour(
            candidate.label,
            target_function=target_function,
        ):
            continue
        if _looks_like_goal_irrelevant_auxiliary_link(
            candidate.label,
            goal_text=request.goal_text,
            target_function=target_function,
        ) and not (
            target_function == "subscription.cancel.entry"
            and _is_reviewed_external_subscription_management_handoff(
                candidate.label,
                request,
            )
        ):
            continue
        if (
            _looks_like_content_discovery_surface(request)
            and _looks_like_feed_interaction_candidate(candidate.label)
        ):
            continue
        if expired_session_screen and _looks_like_new_account_candidate(candidate.label):
            continue
        if (
            _looks_like_account_add_gateway(candidate.label)
            and not expired_session_screen
            and not any(
                marker in _plain_phrase(request.goal_text)
                for marker in (
                    "계정 추가",
                    "다른 계정",
                    "계정 전환",
                    "add account",
                    "another account",
                    "switch account",
                )
            )
        ):
            continue
        if (
            target_function.startswith("subscription.")
            and _looks_like_subscription_offer(candidate.label)
            and (
                account_gateway_visible
                or (
                    target_function == "subscription.cancel.entry"
                    and not state.path
                    and request.transition is None
                )
            )
        ):
            continue
        if (
            target_function.startswith("subscription.")
            and _looks_like_creator_audience_metric(candidate.label)
        ):
            continue
        if _looks_like_paid_subscription_content_detour(
            candidate.label,
            request=request,
            target_function=target_function,
        ):
            continue
        if (
            target_function.startswith("subscription.")
            and _looks_like_content_subscription_tab(candidate.label, request)
        ):
            continue
        medium_review_gateway = _medium_risk_candidate_is_review_gateway(
            candidate=candidate,
            request=request,
            target_function=target_function,
            catalog=catalog,
        )
        target_entry_candidate = _target_control_is_navigation_entry(
            target_function=target_function,
            target_definition=target_definition,
            candidate=candidate,
            element=element,
            request=request,
            state=state,
            catalog=catalog,
        )
        reversible_target_gateway = bool(
            target_entry_candidate
            and _target_entry_is_safe_to_open(
                target_function=target_function,
                target_definition=target_definition,
                candidate=candidate,
                request=request,
            )
        )
        transient_overlay_dismiss = bool(
            transient_overlay_visible
            and _is_safe_transient_overlay_dismiss_label(candidate.label)
        )
        if not element.clickable or (
            candidate.risk_level != "low"
            and not medium_review_gateway
            and not reversible_target_gateway
        ) or element.checkable or bool(element.selected) or element.role.lower() in {
            "switch",
            "checkbox",
            "radio",
            "input",
            "text_field",
            "textfield",
            "edittext",
            "searchbox",
        }:
            continue
        hub_alignment = _target_candidate_hub_alignment(
            target_function,
            candidate.label,
            goal_text=request.goal_text,
        )
        if hub_alignment <= -0.50:
            # A reviewed cross-domain collision is not a fallback candidate.
            # Reject it before either the direct or generic fallback ranking
            # can promote it through broad product-name token overlap.
            continue
        direct_matches = direct_matches_by_element_id.get(candidate.element_id, ())
        direct_scores = {match.function_id: match.score for match in direct_matches}
        strongest_non_target_direct_score = max(
            (
                score
                for function_id, score in direct_scores.items()
                if function_id != target_function
            ),
            default=0.0,
        )
        if (
            target_definition is not None
            and (
                target_definition.automation_policy == "never_auto"
                or target_definition.state_changing
                or target_function in TARGET_ENTRY_HANDOFF_FUNCTIONS
            )
            and direct_scores.get(target_function, 0.0) >= 0.58
            and direct_scores.get(target_function, 0.0)
            >= strongest_non_target_direct_score - 0.02
            and not reversible_target_gateway
            and _has_required_terminal_cue(target_function, candidate.label)
        ):
            # If terminal recognition is intentionally conservative, retain
            # the safer failure mode: never reinterpret a plausible user-owned
            # final control as some generic low-risk alias and auto-click it.
            continue
        direct_function_ids = {
            function_id for function_id, score in direct_scores.items() if score >= 0.34
        }
        if (
            target_function == "notification.settings"
            and _is_explicit_settings_gateway(candidate.label)
        ):
            # ``Settings`` is an intentionally broad doorway.  In a large
            # cross-domain catalog its root match can fall outside the
            # bounded fuzzy-match result behind dozens of specific settings
            # functions.  Keep this deterministic in-app gateway available
            # for notification-preference goals instead of allowing a nearby
            # subscription or billing card to inherit a generic account
            # interpretation and become the only frontier item.
            direct_function_ids.add("settings.root")
            direct_scores["settings.root"] = max(
                0.96,
                direct_scores.get("settings.root", 0.0),
            )
        if _is_explicit_dismiss_candidate(candidate.label, request.goal_text):
            direct_function_ids.add("navigation.back")
            direct_scores["navigation.back"] = max(
                0.92,
                direct_scores.get("navigation.back", 0.0),
            )
        if transient_overlay_dismiss:
            direct_function_ids.add("navigation.back")
            direct_scores["navigation.back"] = max(
                0.995,
                direct_scores.get("navigation.back", 0.0),
            )
        if _is_safe_retry_candidate(candidate.label, request):
            # Retry/refresh is a reversible recovery action.  Associate it
            # with the requested function so an unrelated Wi-Fi/settings link
            # cannot outrank it on an offline or stale-cache screen.
            direct_function_ids.add(target_function)
            direct_scores[target_function] = max(
                0.94,
                direct_scores.get(target_function, 0.0),
            )
        if _is_least_privilege_consent_candidate(candidate.label, request.goal_text):
            direct_function_ids.add("privacy.consent")
            direct_scores["privacy.consent"] = max(
                0.90,
                direct_scores.get("privacy.consent", 0.0),
            )
        safe_function_ids = tuple(
            function_id
            for function_id, confidence in _candidate_function_scores(
                context.function_matches,
                direct_scores,
            )
            if confidence >= 0.34
            and function_id in direct_function_ids
            and (definition := catalog.function(function_id)) is not None
            and (
                definition.automation_policy == "safe_navigation"
                or (
                    function_id == target_function
                    and definition.automation_policy == "conditional"
                )
                or (
                    function_id == target_function
                    and reversible_target_gateway
                )
                or _is_safe_review_gateway(
                    function_id=function_id,
                    target_function=target_function,
                    label=candidate.label,
                    goal_text=request.goal_text,
                    definition=definition,
                )
            )
            and (not definition.state_changing or reversible_target_gateway)
            and _function_can_progress_goal(
                function_id=function_id,
                definition=definition,
                preferred_progress_ids=preferred_progress_ids,
                target_domain=target_domain,
                target_function=target_function,
            )
        )
        fallback_function_ids = tuple(
            function_id
            for function_id, confidence in _candidate_function_scores(
                context.function_matches,
                direct_scores,
            )
            if confidence >= 0.34
            and function_id in direct_function_ids
            and (fallback_definition := catalog.function(function_id)) is not None
            and _function_can_progress_goal(
                function_id=function_id,
                definition=fallback_definition,
                preferred_progress_ids=preferred_progress_ids,
                target_domain=target_domain,
                target_function=target_function,
            )
            and (
                function_id in COMMON_GATEWAY_FUNCTIONS
                or (
                    not screen_can_scroll
                    and confidence >= 0.62
                    and direct_scores.get(function_id, 0.0) >= 0.62
                    and fallback_definition.automation_policy == "safe_navigation"
                    and not fallback_definition.state_changing
                )
            )
        )
        reauthentication_candidate = bool(
            expired_session_screen
            and _looks_like_reauthentication_candidate(candidate.label)
        )
        if reauthentication_candidate:
            safe_function_ids = tuple(
                dict.fromkeys(("auth.login.entry",) + safe_function_ids)
            )
        if _is_explicit_dismiss_candidate(candidate.label, request.goal_text):
            safe_function_ids = tuple(dict.fromkeys(("navigation.back",) + safe_function_ids))
        if transient_overlay_dismiss:
            safe_function_ids = tuple(dict.fromkeys(("navigation.back",) + safe_function_ids))
        if _is_safe_retry_candidate(candidate.label, request):
            safe_function_ids = tuple(dict.fromkeys((target_function,) + safe_function_ids))
        if _is_least_privilege_consent_candidate(candidate.label, request.goal_text):
            safe_function_ids = tuple(dict.fromkeys(("privacy.consent",) + safe_function_ids))
        if "auth.login.entry" in safe_function_ids and _screen_has_credential_fields(request):
            safe_function_ids = tuple(
                function_id for function_id in safe_function_ids if function_id != "auth.login.entry"
            )
        if target_function in safe_function_ids:
            direct_target_score = direct_scores.get(target_function, 0.0)
            if (
                direct_target_score < 0.55
                or direct_target_score < visible_target_direct_ceiling - 0.04
            ):
                # A weak fuzzy match must not turn an unrelated row into the
                # target and then receive the frontier's route boost.  The
                # same guard compares sibling rows: only the strongest visible
                # target-labelled control may inherit target identity.
                safe_function_ids = tuple(
                    function_id for function_id in safe_function_ids if function_id != target_function
                )
            elif target_function == "auth.signup.entry" and _looks_like_combined_auth_gateway(candidate.label):
                safe_function_ids = tuple(
                    function_id for function_id in safe_function_ids if function_id != target_function
                )
            elif _target_control_is_navigation_entry(
                target_function=target_function,
                target_definition=target_definition,
                candidate=candidate,
                element=element,
                request=request,
                state=state,
                catalog=catalog,
            ):
                # The target-shaped row lives on a generic root/list surface;
                # it opens the target rather than proving that we arrived.
                pass
            elif target_function == "support.chat" and _looks_like_support_chat_entry(candidate.label):
                # Opening a support conversation is reversible navigation;
                # sending the first message remains user-controlled.
                pass
            elif (
                target_definition is not None
                and not target_definition.terminal
                and target_definition.automation_policy == "conditional"
            ):
                # The matching control opens the target hub.  It was not a
                # destination on this generic screen, so it remains the best
                # low-risk exploration action.
                pass
            elif (
                not _has_required_terminal_cue(target_function, candidate.label)
                or not _satisfies_semantic_terminal_concepts(
                    catalog,
                    target_function,
                    candidate.label,
                )
            ):
                # A broad label can fuzzily match both a destination and its
                # parent hub (for example "Settings" -> playback settings).
                # The terminal cue guard rejected it above, so retain only the
                # safe parent-hub interpretation instead of discarding it.
                safe_function_ids = tuple(
                    function_id for function_id in safe_function_ids if function_id != target_function
                )
            else:
                continue
        if not safe_function_ids:
            if fallback_function_ids:
                fallback_floor = (
                    0.50
                    if any(
                        function_id in COMMON_GATEWAY_FUNCTIONS
                        for function_id in fallback_function_ids
                    )
                    else 0.36
                )
                fallback_ranked.append(
                    (candidate, fallback_function_ids, max(fallback_floor, semantic_score))
                )
            continue
        if _repeats_immediately_backtracked_branch(
            candidate=candidate,
            function_ids=safe_function_ids,
            branch=immediately_backtracked_branch,
        ):
            continue
        if (
            target_function == "subscription.cancel.entry"
            and not _is_reliable_subscription_progress(
                candidate.label,
                safe_function_ids,
                state=state,
            )
        ):
            continue
        effective_score = semantic_score
        effective_score = max(
            effective_score,
            max(
                (
                    direct_scores.get(function_id, 0.0)
                    * max(0.38, route_weights.get(function_id, 0.0))
                    for function_id in safe_function_ids
                ),
                default=0.0,
            ),
        )
        if reauthentication_candidate:
            effective_score = max(effective_score, 0.96)
        if _is_explicit_dismiss_candidate(candidate.label, request.goal_text):
            effective_score = max(effective_score, 0.98)
        if transient_overlay_dismiss:
            effective_score = max(effective_score, 0.995)
        if _is_safe_retry_candidate(candidate.label, request):
            effective_score = max(effective_score, 0.97)
        if _is_least_privilege_consent_candidate(candidate.label, request.goal_text):
            effective_score = max(effective_score, 0.96)
        if "settings.root" in safe_function_ids and _is_explicit_settings_gateway(candidate.label):
            effective_score = max(
                effective_score,
                1.08 if _goal_targets_settings_surface(target_function, request.goal_text) else 0.74,
            )
        plain_candidate = _plain_phrase(candidate.label)
        configuration_tokens = frozenset(
            target_function.replace("-", "_").split(".")
        ) & {
            "settings",
            "signature",
            "labels",
            "sync",
            "filters",
            "forwarding",
            "vacation_responder",
            "swipe_actions",
            "notifications",
            "timezone",
        }
        if (
            "navigation.menu" in safe_function_ids
            and plain_candidate
            in {"menu", "메뉴", "메뉴 열기", "open menu", "navigation menu"}
            and configuration_tokens
        ):
            effective_score = max(effective_score, 0.96)
        if (
            "support.help" in safe_function_ids
            and _target_can_progress_through_support(target_function)
        ):
            effective_score = max(effective_score, 0.98)
        effective_score += hub_alignment
        if (
            _goal_requests_help(request.goal_text)
            and any(
                marker in plain_candidate
                for marker in ("도움말", "고객센터", "help", "support")
            )
        ):
            effective_score = max(effective_score, 0.98)
        effective_score += _goal_candidate_temporal_alignment(
            request.goal_text,
            candidate.label,
        )
        effective_score += _goal_candidate_navigation_surface_alignment(
            request.goal_text,
            candidate.label,
            role=("" if element is None else element.role),
            selected=(False if element is None else bool(element.selected)),
        )
        effective_score += _goal_candidate_recovery_alignment(
            request.goal_text,
            candidate.label,
        )
        effective_score += _goal_candidate_named_entity_alignment(
            request.goal_text,
            candidate.label,
        )
        effective_score += _goal_candidate_scope_alignment(
            request.goal_text,
            candidate.label,
        )
        safe_ranked.append((candidate, safe_function_ids, effective_score))

    # Common account/menu/settings gateways are safe escape hatches for unseen
    # apps, but they must never outrank a visible function on the goal route.
    if not safe_ranked:
        safe_ranked.extend(fallback_ranked)

    if candidates:
        existing_safe_ids = {item[0].element_id for item in safe_ranked}
        aligned_gateways: list[tuple[UniversalNavigationCandidate, float]] = []
        for candidate in candidates:
            action = observation.actions_by_element_id.get(candidate.element_id)
            element = elements_by_id.get(candidate.element_id)
            hub_alignment = _target_candidate_hub_alignment(
                target_function,
                candidate.label,
                goal_text=request.goal_text,
            )
            if hub_alignment <= -0.50:
                continue
            alignment = max(
                _goal_candidate_recovery_alignment(
                    request.goal_text,
                    candidate.label,
                ),
                _goal_candidate_named_entity_alignment(
                    request.goal_text,
                    candidate.label,
                ),
                _goal_candidate_collection_item_alignment(
                    request,
                    candidate.label,
                ),
                hub_alignment,
            )
            reversible_entry = bool(
                element is not None
                and _target_control_is_navigation_entry(
                    target_function=target_function,
                    target_definition=target_definition,
                    candidate=candidate,
                    element=element,
                    request=request,
                    state=state,
                    catalog=catalog,
                )
                and _target_entry_is_safe_to_open(
                    target_function=target_function,
                    target_definition=target_definition,
                    candidate=candidate,
                    request=request,
                )
            )
            if (
                alignment < 0.40
                or candidate.element_id in existing_safe_ids
                or action is None
                or not _automatic_click_is_low_risk(candidate, action)
                or (
                    action.action_id in tried_action_ids
                    and candidate.element_key not in transient_retry_element_keys
                )
                or element is None
                or not element.clickable
                or not element.enabled
                or element.checkable
                or bool(element.selected)
                or _is_active_or_just_entered_navigation_tab(
                    candidate=candidate,
                    element=element,
                    state=state,
                )
                or (candidate.risk_level != "low" and not reversible_entry)
                or _looks_like_final_state_change_action(candidate.label)
                or (
                    _looks_like_generic_surface_scaffolding(candidate.label)
                    and _target_candidate_hub_alignment(
                        target_function,
                        candidate.label,
                        goal_text=request.goal_text,
                    )
                    < 0.40
                )
                or (
                    target_function.startswith("subscription.")
                    and _looks_like_subscription_offer(candidate.label)
                    and (
                        account_gateway_visible
                        or (
                            target_function == "subscription.cancel.entry"
                            and not state.path
                            and request.transition is None
                        )
                    )
                )
                or (
                    target_function.startswith("subscription.")
                    and _looks_like_content_subscription_tab(candidate.label, request)
                )
                or _looks_like_paid_subscription_content_detour(
                    candidate.label,
                    request=request,
                    target_function=target_function,
                )
                or _looks_like_notification_inbox_control(
                    candidate.label,
                    role=("" if element is None else element.role),
                    view_id=("" if element is None else element.view_id),
                    target_function=target_function,
                    request=request,
                )
                or (
                    _looks_like_goal_irrelevant_auxiliary_link(
                        candidate.label,
                        goal_text=request.goal_text,
                        target_function=target_function,
                    )
                    and alignment < 0.40
                )
                or (
                    target_function == "notification.settings"
                    and not _looks_like_neutral_notification_settings_gateway(
                        candidate.label
                    )
                )
                or (
                    target_function == "subscription.cancel.entry"
                    and not _is_reliable_subscription_progress(
                        candidate.label,
                        ("navigation.menu",),
                        state=state,
                    )
                )
            ):
                continue
            aligned_gateways.append((candidate, alignment))
        if aligned_gateways:
            aligned_gateways.sort(key=lambda item: (-item[1], item[0].label, item[0].element_id))
            candidate, alignment = aligned_gateways[0]
            safe_ranked.append(
                (candidate, ("navigation.menu",), min(0.98, 0.56 + alignment))
            )

    # Netflix renders its bottom navigation with Compose. On real devices the
    # account tab arrives as an ordinary ``button`` (not ``tab``), and its
    # Korean accessibility label contains U+FEFF between syllables.  It can
    # therefore already be present in ``safe_ranked`` under a weak catalog
    # identity, which prevents the aligned-gateway fallback above from adding
    # the strong account interpretation.  Deterministically promote the
    # reviewed, reversible account doorway before any catalog-feed scroll.
    # This remains narrowly scoped to Netflix paid-plan management and never
    # clicks a cancellation or other state-changing control.
    if (
        target_function == "subscription.cancel.entry"
        and request.app_package == "com.netflix.mediaclient"
        and _goal_requests_paid_subscription_management(request.goal_text)
        and _plain_phrase(request.screen.window_title)
        not in {"나의 넷플릭스", "my netflix"}
        and not any(
            _plain_phrase(str(step.get("label", "")))
            in {"나의 넷플릭스", "my netflix"}
            for step in state.path
            if step.get("kind") != "scroll"
        )
    ):
        netflix_account_candidate = None
        for account_candidate in candidates:
            if _plain_phrase(account_candidate.label) not in {
                "나의 넷플릭스",
                "my netflix",
            }:
                continue
            account_action = observation.actions_by_element_id.get(
                account_candidate.element_id
            )
            if account_action is None:
                continue
            if not _automatic_click_is_low_risk(
                account_candidate,
                account_action,
            ):
                continue
            # Compose may emit a decorative child with the same stable ID
            # after the clickable parent. ``elements_by_id`` then points at
            # that non-clickable duplicate even though candidate extraction
            # and the stored action both came from the safe clickable parent.
            # The independently low-risk candidate/action pair is the
            # authoritative execution evidence at this boundary.
            netflix_account_candidate = account_candidate
            break
        if netflix_account_candidate is not None:
            safe_ranked = [
                item
                for item in safe_ranked
                if item[0].element_id != netflix_account_candidate.element_id
            ]
            safe_ranked.append(
                (netflix_account_candidate, ("navigation.menu",), 1.0)
            )

    netflix_profile_path_opened = any(
        (
            "프로필" in (label := _plain_phrase(str(step.get("label", ""))))
            and any(marker in label for marker in ("관리", "변경"))
        )
        or (
            "profile" in label
            and any(marker in label for marker in ("manage", "change", "switch"))
        )
        for step in state.path
        if step.get("kind") != "scroll"
    )
    if (
        target_function == "subscription.cancel.entry"
        and request.app_package == "com.netflix.mediaclient"
        and _goal_requests_paid_subscription_management(request.goal_text)
        and not netflix_profile_path_opened
    ):
        for profile_candidate in candidates:
            profile_label = _plain_phrase(profile_candidate.label)
            profile_gateway = bool(
                (
                    "프로필" in profile_label
                    and any(marker in profile_label for marker in ("관리", "변경"))
                )
                or (
                    "profile" in profile_label
                    and any(
                        marker in profile_label
                        for marker in ("manage", "change", "switch")
                    )
                )
            )
            profile_action = observation.actions_by_element_id.get(
                profile_candidate.element_id
            )
            if not profile_gateway or not _automatic_click_is_low_risk(
                profile_candidate,
                profile_action,
            ):
                continue
            safe_ranked = [
                item
                for item in safe_ranked
                if item[0].element_id != profile_candidate.element_id
            ]
            safe_ranked.append(
                (profile_candidate, ("account.profile", "navigation.menu"), 0.99)
            )
            break

    if (
        target_function == "subscription.cancel.entry"
        and request.app_package == "com.netflix.mediaclient"
        and _goal_requests_paid_subscription_management(request.goal_text)
        and netflix_profile_path_opened
    ):
        # Once the profile header has opened Netflix's account menu, "계정"
        # is the subscription-management gateway.  "프로필 관리" is a safe
        # control too, but it leads to profile editing and triggers an
        # unnecessary backtrack.  Prefer the exact account row while retaining
        # the normal final-action safety boundary on the destination page.
        for account_candidate in candidates:
            account_label = _plain_phrase(account_candidate.label)
            if account_label not in {"계정", "account"}:
                continue
            account_action = observation.actions_by_element_id.get(
                account_candidate.element_id
            )
            if not _automatic_click_is_low_risk(
                account_candidate,
                account_action,
            ):
                continue
            safe_ranked = [
                item
                for item in safe_ranked
                if item[0].element_id != account_candidate.element_id
            ]
            safe_ranked.append(
                (
                    account_candidate,
                    ("account.entry", "subscription.manage", "navigation.menu"),
                    1.0,
                )
            )
            break

    baemin_account_delete = bool(
        target_function == "account.delete.entry"
        and request.app_package == "com.sampleapp"
    )
    baemin_profile_gateway_traversed = any(
        "account.profile.edit"
        in {str(function_id) for function_id in step.get("function_ids", [])}
        for step in state.path
        if step.get("kind") != "scroll"
    )
    baemin_my_page_opened = bool(
        (
            "마이배민" in _plain_phrase(request.screen.window_title)
            or "my baemin" in _plain_phrase(request.screen.window_title)
            or _baemin_my_page_surface_visible(request)
            or baemin_profile_gateway_traversed
        )
        or any(
            (
                "마이배민" in _plain_phrase(str(step.get("label", "")))
                or "my baemin" in _plain_phrase(str(step.get("label", "")))
            )
            and "클럽" not in _plain_phrase(str(step.get("label", "")))
            and "club" not in _plain_phrase(str(step.get("label", "")))
            for step in state.path
            if step.get("kind") != "scroll"
        )
    )
    baemin_profile_edit_opened = bool(
        "editprofile" in request.screen.activity_name.casefold()
        or "내 정보 수정" in _plain_phrase(request.screen.window_title)
        or _baemin_profile_edit_surface_visible(request)
    )
    if baemin_account_delete and not baemin_my_page_opened:
        # Reviewed Baemin route: the account-deletion workflow always begins
        # at the trailing My Baemin tab.  Product/category rows such as
        # "음식배달에서 더보기" are reversible but unrelated and used to win
        # fuzzy ranking on the content-heavy home screen.
        for my_candidate in candidates:
            my_label = _plain_phrase(my_candidate.label)
            if (
                ("마이배민" not in my_label and "my baemin" not in my_label)
                or "클럽" in my_label
                or "club" in my_label
            ):
                continue
            my_action = observation.actions_by_element_id.get(my_candidate.element_id)
            if not _automatic_click_is_low_risk(my_candidate, my_action):
                continue
            safe_ranked = [
                item for item in safe_ranked if item[0].element_id != my_candidate.element_id
            ]
            safe_ranked.append(
                (my_candidate, ("account.entry", "navigation.menu"), 1.20)
            )
            break
    elif baemin_account_delete and baemin_my_page_opened and not baemin_profile_edit_opened:
        # Baemin exposes the pencil beside the nickname without a useful
        # accessibility action.  On-device OCR supplies the nickname as a
        # coordinate-clickable element.  Its reviewed central/profile-header
        # geometry is enough to open the reversible "내 정보 수정" page; the
        # actual withdrawal control remains a user-owned terminal boundary.
        profile_gateways: list[tuple[float, UniversalNavigationCandidate]] = []
        for profile_candidate in candidates:
            profile_element = elements_by_id.get(profile_candidate.element_id)
            profile_action = observation.actions_by_element_id.get(
                profile_candidate.element_id
            )
            geometry_score = _baemin_profile_edit_gateway_score(
                profile_candidate.label,
                element=profile_element,
                request=request,
            )
            if geometry_score <= 0.0 or not _automatic_click_is_low_risk(
                profile_candidate,
                profile_action,
            ):
                continue
            profile_gateways.append((geometry_score, profile_candidate))
        if profile_gateways:
            profile_gateways.sort(
                key=lambda item: (-item[0], item[1].label, item[1].element_id)
            )
            geometry_score, profile_candidate = profile_gateways[0]
            safe_ranked = [
                item
                for item in safe_ranked
                if item[0].element_id != profile_candidate.element_id
            ]
            safe_ranked.append(
                (
                    profile_candidate,
                    ("account.profile.edit", "navigation.menu"),
                    geometry_score,
                )
            )
        elif semantic_planner is None and _baemin_profile_detail_needs_bounded_reobserve(
            state=state,
            latest_attempt=latest_attempt,
        ):
            return _issue_reobserve(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                warnings=warnings + ["배민 프로필 편집 화면이 표시될 때까지 한 번 더 확인합니다."],
                selected_label="프로필 정보 불러오는 중",
                reason="방금 연 배민 프로필 편집 WebView의 접근성 내용이 아직 표시되지 않아 한 번만 재확인합니다.",
            )
    elif baemin_account_delete and baemin_profile_edit_opened:
        # Until the withdrawal row appears below the fold, this reviewed page
        # should only scroll.  The withdrawal row is the user-owned terminal
        # itself, so it must never fall through as an ordinary automatic
        # click. Do not detour into nickname, password, phone, refund, device,
        # or social-account editors either.
        safe_ranked = []

    if not safe_ranked and _looks_like_generic_navigation_surface(request):
        # A sparse root/list surface often contains one real navigation row
        # plus recommendation, help, close, or selected-state scaffolding.  A
        # lone reversible row is safer than backing out, even when its wording
        # is absent from the catalog (common in first-seen apps/locales).
        generic_gateways: list[UniversalNavigationCandidate] = []
        for candidate in candidates:
            action = observation.actions_by_element_id.get(candidate.element_id)
            element = elements_by_id.get(candidate.element_id)
            if (
                action is None
                or not _automatic_click_is_low_risk(candidate, action)
                or (
                    action.action_id in tried_action_ids
                    and candidate.element_key not in transient_retry_element_keys
                )
                or element is None
                or not element.clickable
                or not element.enabled
                or element.checkable
                or bool(element.selected)
                or _is_active_or_just_entered_navigation_tab(
                    candidate=candidate,
                    element=element,
                    state=state,
                )
                or (
                    candidate.risk_level != "low"
                    and not _looks_like_read_only_record_candidate(candidate.label)
                    and not (
                        _target_control_is_navigation_entry(
                            target_function=target_function,
                            target_definition=target_definition,
                            candidate=candidate,
                            element=element,
                            request=request,
                            state=state,
                            catalog=catalog,
                        )
                        and _target_entry_is_safe_to_open(
                            target_function=target_function,
                            target_definition=target_definition,
                            candidate=candidate,
                            request=request,
                        )
                    )
                )
                or _looks_like_generic_surface_scaffolding(candidate.label)
                or _looks_like_feed_interaction_candidate(candidate.label)
                or _looks_like_paid_subscription_content_detour(
                    candidate.label,
                    request=request,
                    target_function=target_function,
                )
                or _looks_like_final_state_change_action(candidate.label)
                or _looks_like_notification_inbox_control(
                    candidate.label,
                    role=("" if element is None else element.role),
                    view_id=("" if element is None else element.view_id),
                    target_function=target_function,
                    request=request,
                )
                or _looks_like_goal_irrelevant_auxiliary_link(
                    candidate.label,
                    goal_text=request.goal_text,
                    target_function=target_function,
                )
                or (
                    target_function == "subscription.cancel.entry"
                    and not _is_reliable_subscription_progress(
                        candidate.label,
                        ("navigation.menu",),
                        state=state,
                    )
                )
            ):
                continue
            generic_gateways.append(candidate)
        if len(generic_gateways) == 1:
            safe_ranked.append(
                (generic_gateways[0], ("navigation.menu",), 0.56)
            )

    can_scroll = screen_can_scroll
    infinite_feed = _looks_like_infinite_feed(request)
    unnamed_settings_hub = bool(
        _goal_targets_settings_surface(target_function, request.goal_text)
        and _looks_like_account_or_settings_hub(request)
    )
    unnamed_paid_account_hub = bool(
        target_function == "subscription.cancel.entry"
        and request.app_package == "com.netflix.mediaclient"
        and _goal_requests_paid_subscription_management(request.goal_text)
    )
    if not safe_ranked and (
        not can_scroll
        or _scroll_attempt_count(state, observation.screen_fingerprint) >= 12
        or _total_scroll_attempt_count(state) >= GENERAL_SCROLL_BUDGET
        or infinite_feed
        or unnamed_settings_hub
        or unnamed_paid_account_hub
    ):
        for candidate in candidates:
            action = observation.actions_by_element_id.get(candidate.element_id)
            element = elements_by_id.get(candidate.element_id)
            if (
                action is None
                or not _automatic_click_is_low_risk(candidate, action)
                or (
                    action.action_id in tried_action_ids
                    and candidate.element_key not in transient_retry_element_keys
                )
                or element is None
                or not element.clickable
                or element.checkable
                or candidate.risk_level != "low"
                or not candidate.label.startswith("이름 없는")
            ):
                continue
            safe_ranked.append(
                (
                    candidate,
                    ("navigation.more",),
                    _unnamed_navigation_hypothesis_score(
                        element=element,
                        request=request,
                        settings_hub=unnamed_settings_hub,
                        account_hub=unnamed_paid_account_hub,
                    ),
                )
            )

    if (
        semantic_planner is None
        and not any(score >= 0.52 for _candidate, _function_ids, score in safe_ranked)
        and _subscription_detail_needs_bounded_reobserve(
            target_function=target_function,
            request=request,
            state=state,
            latest_attempt=latest_attempt,
        )
    ):
        return _issue_reobserve(
            request=request,
            repository=repository,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            state=state,
            warnings=warnings + [
                "구독 상세 화면의 관리 항목이 표시될 때까지 한 번 더 확인합니다."
            ],
        )

    # A deterministic/no-model fallback must inspect a scrollable active-plan
    # detail before following an ambiguous "change/manage" summary card.  The
    # cancellation entry is commonly below the fold, while the summary card
    # can detour into plan changes or billing history.  Production still asks
    # K-EXAONE on every screen; this branch only keeps mock/offline execution
    # conservative and bounded.
    if (
        semantic_planner is None
        and can_scroll
        and _subscription_destination_requires_page_scan(
            target_function=target_function,
            request=request,
        )
        and _total_scroll_attempt_count(state) < GENERAL_SCROLL_BUDGET
    ):
        return _issue_scroll(
            request=request,
            repository=repository,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            state=state,
            warnings=warnings
            + ["활성 구독 상세의 다음 화면 단위에서 해지 진입점을 먼저 찾습니다."],
        )

    # On a newly opened menu surface, inspect one additional viewport before
    # abandoning the branch for an older global frontier.  Previously the
    # Back choice happened first, so a valid below-fold menu could never be
    # discovered even though a local scroll container was visible.  One
    # page-sized attempt keeps this bounded and still lets the global frontier
    # recover immediately when no new semantics appear.
    if (
        not safe_ranked
        and can_scroll
        and not infinite_feed
        and _scroll_attempt_count(state, observation.screen_fingerprint) < 1
        and _total_scroll_attempt_count(state) < GENERAL_SCROLL_BUDGET
        and semantic_planner is None
    ):
        return _issue_scroll(
            request=request,
            repository=repository,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            state=state,
            warnings=warnings
            + ["현재 메뉴의 다음 화면 단위를 한 번 확인한 뒤 다른 분기로 돌아갑니다."],
        )

    _persist_current_frontier(
        repository=repository,
        state=state,
        observation=observation,
        target_function=target_function,
        safe_ranked=safe_ranked,
    )
    # A strong structural hypothesis on the *current* account/settings hub
    # must be tried before returning to an older global frontier. Otherwise a
    # genuinely unlabeled toolbar icon can never be explored: the previously
    # used account-entry action keeps forcing an immediate Back loop.
    forced_local_hypothesis = next(
        (
            item
            for item in sorted(
                safe_ranked,
                key=lambda value: (-value[2], value[0].label, value[0].element_id),
            )
            if (
                (unnamed_settings_hub or unnamed_paid_account_hub)
                and item[0].label.startswith("이름 없는")
                and item[2] >= 0.52
            )
            or (
                item[2] >= 0.55
                and any(
                    route_weights.get(function_id, 0.0) >= 0.80
                    for function_id in item[1]
                )
            )
            or (
                item[2] >= 0.90
                and max(
                    _goal_candidate_recovery_alignment(
                        request.goal_text,
                        item[0].label,
                    ),
                    _goal_candidate_named_entity_alignment(
                        request.goal_text,
                        item[0].label,
                    ),
                    _goal_candidate_collection_item_alignment(
                        request,
                        item[0].label,
                    ),
                )
                >= 0.40
            )
        ),
        None,
    )
    frontier_choice = (
        None
        if forced_local_hypothesis is not None
        else _best_reachable_frontier(
            repository=repository,
            state=state,
            observation=observation,
            safe_ranked=safe_ranked,
        )
    )
    frontier_selected_item: ExplorationFrontierItem | None = None
    frontier_local_selected: tuple[
        UniversalNavigationCandidate, tuple[str, ...], float
    ] | None = forced_local_hypothesis
    if frontier_choice is not None:
        frontier_selected_item, frontier_local_selected = frontier_choice
        if frontier_local_selected is None and semantic_planner is None:
            return _issue_back(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                route=None,
                warnings=warnings
                + [
                    "현재 분기의 지역 후보보다 목적 적합도가 높은 기록된 대안 분기로 되돌아갑니다."
                ],
                final_return=False,
            )

    target_is_visible = any(
        target_function in function_ids and score >= 0.52
        for _candidate, function_ids, score in safe_ranked
    )
    if (
        semantic_planner is None
        and can_scroll
        and _goal_or_screen_requests_below_fold(request)
        and _total_scroll_attempt_count(state) < GENERAL_SCROLL_BUDGET
    ):
        return _issue_scroll(
            request=request,
            repository=repository,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            state=state,
            warnings=warnings,
        )

    safe_ranked.sort(key=lambda item: (-item[2], item[0].label, item[0].element_id))
    selected = frontier_local_selected or (safe_ranked[0] if safe_ranked else None)
    # Deterministic/mock deployments have no policy model. Preserve the
    # conservative legacy behavior there: when weak candidates are nearly
    # tied, keep exploring instead of pretending the heuristic winner is a
    # model decision. Production K-EXAONE deployments take the planner branch
    # below on every screen.
    if (
        semantic_planner is None
        and frontier_local_selected is None
        and selected is not None
        and len(safe_ranked) > 1
    ):
        margin = safe_ranked[0][2] - safe_ranked[1][2]
        top_matches_goal_progress = any(
            function_id in safe_ranked[0][1] and weight >= 0.80
            for function_id, weight in plan.preferred_functions
        )
        top_has_strong_hub_alignment = (
            _target_candidate_hub_alignment(
                target_function,
                safe_ranked[0][0].label,
                goal_text=request.goal_text,
            )
            >= 0.80
        )
        use_ambiguity_fallback = not (
            (top_matches_goal_progress or top_has_strong_hub_alignment)
            and safe_ranked[0][2] >= 0.55
        )
        if (
            use_ambiguity_fallback
            and margin < settings.navigation_agent_min_candidate_margin
            and safe_ranked[0][2] < 0.70
        ):
            selected = None
    planner_result: dict[str, object] | None = None
    planner_selected = False
    planner_scroll_allowed = (
        can_scroll
        and _scroll_attempt_count(state, observation.screen_fingerprint) < 12
        and _total_scroll_attempt_count(state)
        < (INFINITE_FEED_SCROLL_BUDGET if infinite_feed else GENERAL_SCROLL_BUDGET)
    )
    if semantic_planner is not None:
        planner_result = semantic_planner(
            [item[0] for item in safe_ranked],
            planner_scroll_allowed,
            bool(state.path),
            False,
        )
        if planner_result is None:
            return _stopped_response(
                request=request,
                observation=observation,
                graph_update=graph_update,
                candidates=candidates,
                state=repository.update_exploration(
                    state.exploration_id,
                    status="stopped",
                    clear_pending=True,
                ),
                failure_reason="planner_unavailable",
                reason="K-EXAONE Planner의 유효한 판단이 없어 자동 탐색을 중단했습니다.",
                warnings=warnings,
            )
        planner_command = str(planner_result.get("command", "")) if planner_result else ""
        if planner_command == "scroll_forward" and planner_scroll_allowed:
            return _issue_scroll(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                warnings=warnings + ["K-EXAONE Planner가 안전한 다음 화면 탐색을 선택했습니다."],
            )
        if planner_command == "back" and state.path:
            return _issue_back(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                route=None,
                warnings=warnings + ["K-EXAONE Planner가 이전 탐색 분기로 복구하도록 선택했습니다."],
                final_return=False,
            )
        if planner_command == "wait_and_observe":
            return _issue_reobserve(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                warnings=warnings + ["K-EXAONE Planner가 화면 안정화를 기다리도록 선택했습니다."],
            )
        if planner_command == "stop_for_user":
            return _stopped_response(
                request=request,
                observation=observation,
                graph_update=graph_update,
                candidates=candidates,
                state=repository.update_exploration(
                    state.exploration_id,
                    status="stopped",
                    clear_pending=True,
                ),
                failure_reason="planner_requested_user_boundary",
                reason=str(planner_result.get("reason", "사용자 판단이 필요한 경계입니다.")),
                warnings=warnings,
            )
        if planner_command == "click":
            selected_id = str(planner_result.get("selected_element_id", ""))
            model_selected = next(
                (item for item in safe_ranked if item[0].element_id == selected_id),
                None,
            )
            if model_selected is not None:
                selected = model_selected
                planner_selected = True
        if not planner_selected:
            return _stopped_response(
                request=request,
                observation=observation,
                graph_update=graph_update,
                candidates=candidates,
                state=repository.update_exploration(
                    state.exploration_id,
                    status="stopped",
                    clear_pending=True,
                ),
                failure_reason="planner_action_rejected",
                reason="K-EXAONE Planner가 실행 가능한 안전 행동을 선택하지 못했습니다.",
                warnings=warnings,
            )

    if selected is None:
        per_screen_scrolls = _scroll_attempt_count(state, observation.screen_fingerprint)
        total_scrolls = _total_scroll_attempt_count(state)
        scroll_budget = INFINITE_FEED_SCROLL_BUDGET if infinite_feed else GENERAL_SCROLL_BUDGET
        if can_scroll and per_screen_scrolls < 12 and total_scrolls < scroll_budget:
            return _issue_scroll(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                warnings=warnings,
            )
        if infinite_feed:
            return _stopped_response(
                request=request,
                observation=observation,
                graph_update=graph_update,
                candidates=candidates,
                state=repository.update_exploration(
                    state.exploration_id,
                    status="stopped",
                    clear_pending=True,
                ),
                failure_reason="infinite_feed_scroll_limit",
                reason=(
                    "끝없이 갱신되는 피드에서는 메뉴 탐색과 콘텐츠 스크롤을 구분하기 위해 "
                    "자동 스크롤을 중단했습니다. 프로필 또는 전체 메뉴를 연 뒤 다시 시도해 주세요."
                ),
                warnings=warnings + ["무한 피드 자동 스크롤은 세션당 1회로 제한됩니다."],
            )
        if state.path:
            return _issue_back(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                route=None,
                warnings=warnings + ["현재 분기에서 안전한 미탐색 메뉴가 없어 한 단계 되돌아갑니다."],
                final_return=False,
            )
        return _stopped_response(
            request=request,
            observation=observation,
            graph_update=graph_update,
            candidates=candidates,
            state=repository.update_exploration(state.exploration_id, status="stopped", clear_pending=True),
            failure_reason="no_safe_candidate",
            reason="시작 화면에서 자동으로 눌러도 안전하다고 검증된 메뉴를 찾지 못했습니다.",
            warnings=warnings,
        )

    candidate, function_ids, semantic_score = selected
    action = observation.actions_by_element_id.get(candidate.element_id)
    if not _automatic_click_is_low_risk(candidate, action):
        if semantic_planner is not None:
            # The production contract is model-owned: Python may veto a K-EXAONE
            # proposal, but it must never replace that proposal with a heuristic
            # click. Re-observe/replan on a later request or hand control back to
            # the user instead of silently executing a different candidate.
            return _stopped_response(
                request=request,
                observation=observation,
                graph_update=graph_update,
                candidates=candidates,
                state=repository.update_exploration(
                    state.exploration_id,
                    status="stopped",
                    clear_pending=True,
                ),
                failure_reason="planner_action_failed_safety_check",
                reason=(
                    "K-EXAONE이 선택한 동작이 클릭 직전 저위험 안전 조건을 "
                    "통과하지 못해 대체 동작 없이 자동 탐색을 중단했습니다."
                ),
                warnings=warnings,
            )
        safe_alternative = next(
            (
                item
                for item in safe_ranked
                if _automatic_click_is_low_risk(
                    item[0],
                    observation.actions_by_element_id.get(item[0].element_id),
                )
            ),
            None,
        )
        if safe_alternative is not None:
            candidate, function_ids, semantic_score = safe_alternative
            action = observation.actions_by_element_id.get(candidate.element_id)
            frontier_selected_item = None
        elif state.path:
            return _issue_back(
                request=request,
                repository=repository,
                candidates=candidates,
                observation=observation,
                graph_update=graph_update,
                state=state,
                route=None,
                warnings=warnings
                + ["후보와 실행 동작이 모두 저위험으로 확인되지 않아 이전 화면으로 돌아갑니다."],
                final_return=False,
            )
        else:
            return _stopped_response(
                request=request,
                observation=observation,
                graph_update=graph_update,
                candidates=candidates,
                state=repository.update_exploration(
                    state.exploration_id,
                    status="stopped",
                    clear_pending=True,
                ),
                failure_reason="non_low_risk_click_blocked",
                reason="후보와 실행 동작이 모두 저위험으로 확인되지 않아 자동 클릭을 중단했습니다.",
                warnings=warnings,
            )

    # This is the automatic-click issuance boundary. Both independently
    # carried risk values must still be exactly low at this point.
    if action is None or candidate.risk_level != "low" or action.risk_level != "low":
        return _stopped_response(
            request=request,
            observation=observation,
            graph_update=graph_update,
            candidates=candidates,
            state=repository.update_exploration(
                state.exploration_id,
                status="stopped",
                clear_pending=True,
            ),
            failure_reason="non_low_risk_click_blocked",
            reason="저위험 안전 조건이 클릭 직전에 변경되어 자동 클릭을 중단했습니다.",
            warnings=warnings,
        )

    bounded_semantic_score = max(0.0, min(1.0, semantic_score))
    step = {
        "ordinal": len(state.path),
        "from_screen_fingerprint": observation.screen_fingerprint,
        "element_key": candidate.element_key,
        "label": candidate.label,
        "function_ids": list(function_ids),
        "role": candidate.role,
        "risk_level": candidate.risk_level,
        "expected_to_screen_fingerprint": None,
        "terminal": False,
        "reversible": True,
        "confidence": round(max(0.45, bounded_semantic_score), 4),
        "action_id": action.action_id,
        "element_id": candidate.element_id,
        "pending": True,
    }
    pending = {
        "kind": "click",
        "from_screen_fingerprint": observation.screen_fingerprint,
        "element_id": candidate.element_id,
        "element_key": candidate.element_key,
        "action_id": action.action_id,
        "label": candidate.label,
        "function_ids": list(function_ids),
    }
    recommendation_id = _recommendation_id(request.session_id, observation.screen_fingerprint, candidate.element_key)
    decision_mode = "exaone" if planner_selected else "function_graph_exploration"
    recommendation_confidence = (
        max(0.0, min(1.0, float(planner_result.get("confidence", bounded_semantic_score))))
        if planner_selected and planner_result
        else bounded_semantic_score
    )
    repository.record_recommendation(
        recommendation_id=recommendation_id,
        session_id=request.session_id,
        app_package=request.app_package,
        app_version=request.app_version,
        locale=request.locale,
        goal_text=request.goal_text,
        goal_interpretation=plan.intent,
        target_function=target_function,
        decision_mode=decision_mode,
        screen_fingerprint=observation.screen_fingerprint,
        action_id=action.action_id,
        confidence=recommendation_confidence,
    )
    repository.consume_transient_retry(
        state.exploration_id,
        candidate.element_key,
    )
    repository.record_exploration_attempt(
        exploration_id=state.exploration_id,
        screen_fingerprint=observation.screen_fingerprint,
        action_id=action.action_id,
        element_key_value=candidate.element_key,
        label=candidate.label,
        function_ids=function_ids,
        command="click",
    )
    if frontier_selected_item is not None:
        repository.set_exploration_frontier_status(
            state.exploration_id,
            frontier_selected_item.action_id,
            "issued",
        )
    state = repository.update_exploration(
        state.exploration_id,
        current_screen_fingerprint=observation.screen_fingerprint,
        action_count=state.action_count + 1,
        path=list(state.path) + [step],
        pending=pending,
    )
    recommendation = UniversalNavigationRecommendation(
        recommendation_id=recommendation_id,
        selected_element_id=candidate.element_id,
        selected_element_key=candidate.element_key,
        selected_label=candidate.label,
        target_function=target_function,
        instruction=(
            str(planner_result.get("instruction", ""))
            if planner_selected and planner_result
            else f"그래프 탐색을 위해 ‘{candidate.label}’ 메뉴를 확인합니다."
        ),
        reason=(
            str(planner_result.get("reason", ""))
            if planner_selected and planner_result
            else "기능 사전에서 상태를 바꾸지 않는 저위험 탐색 메뉴로 검증됐습니다."
        ),
        expected_next_screen=(
            str(planner_result.get("expected_next_screen", ""))
            if planner_selected and planner_result
            else f"{candidate.label} 관련 하위 기능 화면"
        ),
        confidence=recommendation_confidence,
        risk_level=candidate.risk_level,
        requires_user_confirmation=False,
    )
    return UniversalNavigationObserveResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        status="guided",
        screen_fingerprint=observation.screen_fingerprint,
        goal_interpretation=plan.intent,
        decision_mode=decision_mode,
        phase="exploring",
        candidates=candidates,
        recommendation=recommendation,
        graph_update=graph_update,
        automation=UniversalNavigationAutomation(
            action="click",
            safe_to_execute=True,
            selected_element_id=candidate.element_id,
            selected_element_key=candidate.element_key,
            selected_label=candidate.label,
            reason="explore 모드에서만 실행되는 저위험 기능 그래프 탐색입니다.",
            action_count=state.action_count,
            action_limit=state.max_actions,
            elapsed_seconds=_elapsed_seconds(state.started_at),
            timeout_seconds=state.timeout_seconds,
        ),
        warnings=warnings,
    )


def manual_route_response_if_available(
    *,
    request: UniversalNavigationObserveRequest,
    repository: UniversalNavigationGraphRepository,
    catalog: NavigationFunctionCatalog,
    candidates: list[UniversalNavigationCandidate],
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
) -> UniversalNavigationObserveResponse | None:
    plan = infer_goal_plan(request.goal_text, catalog)
    if not plan.terminal_function:
        return None
    match = repository.route_action(
        app_package=request.app_package,
        app_version=request.app_version,
        locale=request.locale,
        target_function=plan.terminal_function,
        screen_fingerprint=observation.screen_fingerprint,
    )
    if match is None:
        return None
    route, step = match
    response = _manual_route_response(
        request=request,
        repository=repository,
        candidates=candidates,
        observation=observation,
        graph_update=graph_update,
        route=route,
        step=step,
        warnings=["저장된 기능 그래프 경로를 사용합니다. 실제 버튼은 모두 사용자가 직접 누릅니다."],
    )
    if step and (response.recommendation is None or response.recommendation.selected_element_id is None):
        repository.invalidate_route(route.route_id)
        return None
    return response


def _reconcile_pending(
    *,
    request: UniversalNavigationObserveRequest,
    repository: UniversalNavigationGraphRepository,
    state: ExplorationState,
    current_screen_fingerprint: str,
) -> ExplorationState:
    pending = state.pending
    if pending is None:
        if state.current_screen_fingerprint != current_screen_fingerprint:
            return repository.update_exploration(
                state.exploration_id,
                current_screen_fingerprint=current_screen_fingerprint,
            )
        return state
    if pending.get("source") == "verified_route":
        return _reconcile_verified_route_pending(
            request=request,
            repository=repository,
            state=state,
            current_screen_fingerprint=current_screen_fingerprint,
        )
    pending_from = str(pending.get("from_screen_fingerprint", ""))
    moved = current_screen_fingerprint != pending_from
    transition_matches = (
        request.transition is not None
        and request.transition.from_screen_fingerprint == pending_from
        and (
            pending.get("kind") == "back"
            or request.transition.performed_element_id == pending.get("element_id")
        )
    )
    if not moved and not transition_matches and pending.get("kind") != "scroll":
        return state
    if pending.get("kind") == "scroll":
        path = [dict(step) for step in state.path]
        if path and path[-1].get("pending"):
            path[-1]["expected_to_screen_fingerprint"] = current_screen_fingerprint
            path[-1]["pending"] = False
        return repository.update_exploration(
            state.exploration_id,
            current_screen_fingerprint=current_screen_fingerprint,
            path=path,
            clear_pending=True,
        )
    if pending.get("kind") == "click":
        reported_outcome = (
            request.transition.outcome
            if transition_matches and request.transition is not None
            else ("navigated" if moved else "no_change")
        )
        path = [dict(step) for step in state.path]
        if path and path[-1].get("pending"):
            if moved:
                path[-1]["expected_to_screen_fingerprint"] = current_screen_fingerprint
                path[-1]["pending"] = False
            else:
                path.pop()
        repository.record_exploration_attempt(
            exploration_id=state.exploration_id,
            screen_fingerprint=pending_from,
            action_id=str(pending.get("action_id", "")),
            element_key_value=str(pending.get("element_key", "")),
            label=str(pending.get("label", "")),
            function_ids=[str(value) for value in pending.get("function_ids", [])],
            command="click",
            outcome=reported_outcome,
            to_screen_fingerprint=current_screen_fingerprint if moved else pending_from,
        )
        repository.set_exploration_frontier_status(
            state.exploration_id,
            str(pending.get("action_id", "")),
            "expanded" if moved else "failed",
        )
        return repository.update_exploration(
            state.exploration_id,
            current_screen_fingerprint=current_screen_fingerprint,
            path=path,
            clear_pending=True,
        )
    return repository.update_exploration(
        state.exploration_id,
        current_screen_fingerprint=current_screen_fingerprint,
        clear_pending=True,
    )


def _reconcile_verified_route_pending(
    *,
    request: UniversalNavigationObserveRequest,
    repository: UniversalNavigationGraphRepository,
    state: ExplorationState,
    current_screen_fingerprint: str,
) -> ExplorationState:
    pending = dict(state.pending or {})
    pending_from = str(pending.get("from_screen_fingerprint", ""))
    expected_to = str(pending.get("expected_to_screen_fingerprint", ""))
    route_id = str(pending.get("route_id") or state.route_id)
    moved = bool(current_screen_fingerprint != pending_from)
    transition = request.transition
    transition_matches = bool(
        (
            pending.get("kind") == "back"
            and moved
            and (
                transition is None
                or transition.from_screen_fingerprint == pending_from
            )
        )
        or (
            transition is not None
            and transition.from_screen_fingerprint == pending_from
            and transition.performed_element_id == pending.get("element_id")
        )
    )
    expected_screen_matches = bool(
        moved
        and expected_to
        and repository.screens_semantically_match(
            expected_to,
            current_screen_fingerprint,
        )
    )
    if moved and expected_to and route_id and not expected_screen_matches:
        # A dynamic destination may differ at whole-screen level while the
        # exact next reviewed low-risk control remains present. ``route_action``
        # performs app/version/target/lifecycle/risk checks and can therefore
        # provide stronger stage-local evidence than volatile feed content.
        anchored_match = repository.route_action(
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            target_function=state.target_function,
            screen_fingerprint=current_screen_fingerprint,
        )
        if anchored_match is not None and anchored_match[0].route_id == route_id:
            anchored_route, anchored_step = anchored_match
            expected_screen_matches = bool(
                (
                    not anchored_step
                    # Some apps transiently open an external/system surface
                    # and return before the next accessibility snapshot. An
                    # exact reviewed destination match is safe evidence that
                    # the reversible intermediate stage was already crossed.
                    and repository.screens_semantically_match(
                        anchored_route.destination_screen_fingerprint,
                        current_screen_fingerprint,
                    )
                )
                or str(anchored_step.get("from_screen_fingerprint") or "") == expected_to
            )
    if expected_screen_matches and transition_matches:
        path = [dict(step) for step in state.path]
        if path and path[-1].get("pending"):
            path[-1]["pending"] = False
            path[-1]["observed_to_screen_fingerprint"] = current_screen_fingerprint
        repository.record_exploration_attempt(
            exploration_id=state.exploration_id,
            screen_fingerprint=pending_from,
            action_id=str(pending.get("action_id", "")),
            element_key_value=str(pending.get("element_key", "")),
            label=str(pending.get("label", "")),
            function_ids=[str(value) for value in pending.get("function_ids", [])],
            command=(
                "verified_route_back"
                if pending.get("kind") == "back"
                else "verified_route_click"
            ),
            outcome="expected_transition",
            to_screen_fingerprint=current_screen_fingerprint,
        )
        return repository.update_exploration(
            state.exploration_id,
            status="route_reusing",
            current_screen_fingerprint=current_screen_fingerprint,
            path=path,
            clear_pending=True,
            route_id=route_id,
        )

    mismatch_observations = int(pending.get("mismatch_observations", 0)) + 1
    conclusive_mismatch = bool(
        moved
        or transition is not None
        or not expected_to
        or mismatch_observations >= 2
    )
    if not conclusive_mismatch:
        pending["mismatch_observations"] = mismatch_observations
        return repository.update_exploration(
            state.exploration_id,
            current_screen_fingerprint=current_screen_fingerprint,
            pending=pending,
        )

    if route_id:
        repository.invalidate_route(route_id)
    repository.record_exploration_attempt(
        exploration_id=state.exploration_id,
        screen_fingerprint=pending_from,
        action_id=str(pending.get("action_id", "")),
        element_key_value=str(pending.get("element_key", "")),
        label=str(pending.get("label", "")),
        function_ids=[str(value) for value in pending.get("function_ids", [])],
        command=(
            "verified_route_back"
            if pending.get("kind") == "back"
            else "verified_route_click"
        ),
        outcome=(
            "unexpected_transition"
            if moved or (transition is not None and transition.outcome == "unexpected")
            else "no_change"
        ),
        to_screen_fingerprint=current_screen_fingerprint,
    )
    return repository.update_exploration(
        state.exploration_id,
        status="exploring",
        current_screen_fingerprint=current_screen_fingerprint,
        path=[],
        clear_pending=True,
        route_id="",
    )


def _terminal_candidate(
    *,
    target_function: str,
    candidates: list[UniversalNavigationCandidate],
    contexts,
    catalog: NavigationFunctionCatalog,
    request: UniversalNavigationObserveRequest,
    state: ExplorationState,
    allowed_function_ids: frozenset[str] | None = None,
) -> TerminalCandidate | None:
    target_definition = catalog.function(target_function)
    if _is_stale_or_offline_snapshot(request):
        return None
    if (
        _goal_or_screen_requests_below_fold(request)
        and any(element.visible and element.enabled and element.scrollable for element in request.screen.elements)
    ):
        return None
    if (
        target_definition is not None
        and not target_definition.terminal
        and target_definition.automation_policy == "conditional"
        and not (request.transition is not None or state.path or state.back_count > 0)
    ):
        # A non-terminal hub label is only a destination candidate after the
        # current screen title itself identifies that hub.  On a generic home
        # screen, the same label remains a progress control to click.
        title_concepts = catalog.semantic_concepts_for_text(request.screen.window_title)
        target_concepts = frozenset(target_definition.semantic_concepts)
        if not (
            catalog.terminal_screen_score(
                target_function,
                request.screen.window_title,
            )
            >= 0.55
            and len(title_concepts & target_concepts) >= 2
        ):
            return None
    best: TerminalCandidate | None = None
    best_rank = float("-inf")
    elements_by_id = {element.id: element for element in request.screen.elements}
    goal_concepts = catalog.semantic_concepts_for_text(request.goal_text)
    for candidate in candidates:
        context = contexts[candidate.element_id]
        element = elements_by_id.get(candidate.element_id)
        user_owned_target_boundary = bool(
            target_definition is not None
            and (
                target_definition.automation_policy == "never_auto"
                or target_definition.state_changing
                or target_function in TARGET_ENTRY_HANDOFF_FUNCTIONS
            )
        )
        if (
            _looks_like_irreversible_execution(candidate.label)
            and not user_owned_target_boundary
        ):
            continue
        if _is_active_or_just_entered_navigation_tab(
            candidate=candidate,
            element=element,
            state=state,
        ):
            continue
        if _looks_like_notification_inbox_control(
            candidate.label,
            role=("" if element is None else element.role),
            view_id=("" if element is None else element.view_id),
            target_function=target_function,
            request=request,
        ):
            # A toolbar bell opens the notification inbox/activity feed.  It
            # is not the surface where notification preferences are changed,
            # even though both controls are commonly labelled only
            # ``Notifications`` by accessibility services.
            continue
        if (
            target_function.startswith("subscription.")
            and _looks_like_creator_audience_metric(candidate.label)
        ):
            # Creator/channel audience counts describe content reach, not a
            # paid plan.  They cannot inherit subscription identity from the
            # surrounding screen or a synthesized selected/choice state.
            continue
        if _looks_like_paid_subscription_content_detour(
            candidate.label,
            request=request,
            target_function=target_function,
        ):
            # A paid-plan goal must never terminate on, or automatically open,
            # a creator channel's subscribe/unsubscribe controls.  Korean
            # YouTube exposes both concepts with the word ``구독``; the
            # content/audience evidence is the decisive negative signal.
            continue
        if _looks_like_goal_irrelevant_auxiliary_link(
            candidate.label,
            goal_text=request.goal_text,
            target_function=target_function,
        ):
            # Help, sharing, and legal-document links are real navigation
            # controls, but they are not progress toward an unrelated goal.
            # Treating them as a generic menu can launch a support/browser
            # branch and strand an otherwise valid in-app route.
            continue
        direct_matches = catalog.match_candidate(
            label=candidate.label,
            # A screen title is destination evidence, but it is not part of a
            # control's identity.  Feeding it into this match allowed an
            # arbitrary sibling such as "Accessibility menu" or "Camera" to
            # borrow the title's target meaning and prematurely end a route.
            parent_label="",
            nearby_text="",
            role=candidate.role,
            position=context.position,
            locale=request.locale,
            enabled=(element.enabled if element is not None else None),
            checkable=(element.checkable if element is not None else None),
            checked=(element.checked if element is not None else None),
            selected=(element.selected if element is not None else None),
            limit=40,
            allowed_function_ids=allowed_function_ids,
        )
        signup_gateway = target_function == "auth.signup.entry" and _looks_like_signup_gateway(
            candidate,
            request,
            catalog,
        )
        target_match = next(
            (match for match in direct_matches if match.function_id == target_function),
            None,
        )
        strongest_competitor = max(
            (
                match.score
                for match in direct_matches
                if match.function_id != target_function
            ),
            default=0.0,
        )
        target_identity_dominates = bool(
            target_match is not None
            and target_match.score >= 0.70
            and (
                (
                    direct_matches
                    and direct_matches[0].function_id == target_function
                    and target_match.score >= strongest_competitor + 0.015
                )
                or target_match.score >= strongest_competitor + 0.08
            )
        )
        hub_alignment = _target_candidate_hub_alignment(
            target_function,
            candidate.label,
            goal_text=request.goal_text,
        )
        protected_destination_boundary = bool(
            target_definition is not None
            and user_owned_target_boundary
            and (
                (
                    target_match is not None
                    and target_match.score >= 0.70
                    and target_identity_dominates
                    and (
                        target_definition.risk_level in {"medium", "high", "blocked"}
                        or (
                            target_function in TARGET_ENTRY_HANDOFF_FUNCTIONS
                            and _has_required_terminal_cue(
                                target_function,
                                candidate.label,
                            )
                        )
                    )
                )
                or (
                    hub_alignment >= 0.82
                    and (target_match is None or target_match.score >= 0.18)
                )
            )
            and (target_match is None or not target_match.negative_evidence)
            and (
                target_function != "subscription.cancel.entry"
                or _is_supported_subscription_cancel_destination(
                    candidate.label,
                    request=request,
                    state=state,
                )
            )
        )
        if (
            protected_destination_boundary
            and element is not None
            and _target_control_is_navigation_entry(
                target_function=target_function,
                target_definition=target_definition,
                candidate=candidate,
                element=element,
                request=request,
                state=state,
                catalog=catalog,
            )
            and _target_entry_is_safe_to_open(
                target_function=target_function,
                target_definition=target_definition,
                candidate=candidate,
                request=request,
            )
        ):
            protected_destination_boundary = False
        if candidate.risk_level in {"high", "blocked"} and not (
            user_owned_target_boundary and protected_destination_boundary
        ):
            # Protected controls may only be surfaced as a terminal handoff
            # when the catalog marks the target as user-owned and the control
            # is its strongly identified match.  Such a candidate is returned
            # as a stop boundary and is never clicked by the explorer.
            continue
        if protected_destination_boundary:
            return TerminalCandidate(
                candidate=candidate,
                function_ids=(target_function,),
                confidence=max(
                    0.82,
                    hub_alignment,
                    0.0 if target_match is None else target_match.score,
                ),
            )
        goal_aligned_terminal_boundary = bool(
            target_match is not None
            and target_match.score >= 0.34
            and _has_required_terminal_cue(target_function, candidate.label)
            and (
                _goal_candidate_named_entity_alignment(
                    request.goal_text,
                    candidate.label,
                )
                >= 0.40
                or _goal_candidate_recovery_alignment(
                    request.goal_text,
                    candidate.label,
                )
                >= 0.50
            )
        )
        arrived_from_navigation = bool(
            request.transition is not None
            or state.path
            or state.back_count > 0
        )
        explicit_terminal_control = bool(
            target_definition is not None
            and target_definition.terminal
            and target_match is not None
            and target_identity_dominates
            and (
                signup_gateway
                or target_function == "settings.language"
                or (
                    target_definition.automation_policy == "safe_navigation"
                    and not target_definition.state_changing
                    and target_match.score >= 0.82
                    and text_similarity(request.goal_text, candidate.label) >= 0.24
                    and candidate.role.lower() not in {"tab", "navigationitem"}
                )
                or (
                    (request.transition is not None or state.path or state.back_count > 0)
                    and (
                        _plain_phrase(request.screen.window_title)
                        == _plain_phrase(candidate.label)
                        or (element is not None and element.checkable)
                    )
                )
            )
        )
        requested_support_hub_boundary = bool(
            target_function == "support.help"
            and _goal_requests_help(request.goal_text)
            and target_match is not None
            and target_match.alias_score >= 0.78
            and target_match.score >= 0.70
            and target_identity_dominates
        )
        explicit_user_owned_boundary = bool(
            protected_destination_boundary
            or (
                user_owned_target_boundary
                and target_match is not None
                and target_match.score >= 0.58
                and (
                (
                    bool(
                        _function_identifier_tokens(target_function)
                        & USER_OWNED_ACTION_FUNCTION_TOKENS
                    )
                    and target_identity_dominates
                )
                or (
                    _plain_phrase(request.screen.window_title)
                    == _plain_phrase(candidate.label)
                )
                or (
                    arrived_from_navigation
                    and target_identity_dominates
                    and (
                        candidate.risk_level in {"medium", "high"}
                        or _title_describes_candidate(
                            request.screen.window_title,
                            candidate.label,
                        )
                    )
                )
                or (
                    arrived_from_navigation
                    and target_match.score >= 0.58
                    and catalog.terminal_screen_score(
                        target_function,
                        request.screen.window_title,
                    )
                    >= 0.55
                    and _has_required_terminal_cue(
                        target_function,
                        candidate.label,
                    )
                    and _goal_candidate_named_entity_alignment(
                        request.goal_text,
                        candidate.label,
                    )
                    >= 0.20
                )
                or any(
                    marker in _plain_phrase(request.screen.window_title)
                    for marker in (
                        "최종 확인",
                        "검토",
                        "미리보기",
                        "confirmation",
                        "review",
                        "preview",
                    )
                )
                    or (element is not None and element.checkable)
                )
            )
        )
        selected_generic_navigation = _selected_generic_navigation_identity(
            candidate=candidate,
            element=element,
            function_ids=tuple(match.function_id for match in direct_matches),
        )
        reviewed_external_subscription_handoff = bool(
            target_function == "subscription.cancel.entry"
            and _is_reviewed_external_subscription_management_handoff(
                candidate.label,
                request,
            )
        )
        explicit_subscription_cancel_destination = bool(
            target_function == "subscription.cancel.entry"
            and _is_supported_subscription_cancel_destination(
                candidate.label,
                request=request,
                state=state,
            )
        )
        ranking_match = target_match
        contextual_terminal_evidence = False
        if target_match is not None:
            contextual_score = dict(context.function_matches).get(
                target_function,
                target_match.score,
            )
            contextual_concepts = catalog.semantic_concepts_for_text(
                " ".join(filter(None, [request.screen.window_title, candidate.label]))
            )
            target_concepts = (
                frozenset()
                if target_definition is None
                else frozenset(target_definition.semantic_concepts)
            )
            matched_concepts = tuple(
                sorted(
                    set(target_match.matched_concepts)
                    | (contextual_concepts & target_concepts)
                )
            )
            label_target_concepts = (
                catalog.semantic_concepts_for_text(candidate.label)
                & target_concepts
            )
            new_context_concepts = set(matched_concepts) - set(target_match.matched_concepts)
            context_boosted_score = target_match.score
            if (
                target_match.score >= 0.28
                and label_target_concepts
                and new_context_concepts
            ):
                context_boosted_score = min(1.0, target_match.score + 0.30)
            derived_concept_score = min(
                0.55,
                0.045 + 0.145 * len(matched_concepts),
            )
            ranking_match = replace(
                target_match,
                score=max(target_match.score, contextual_score, context_boosted_score),
                concept_score=max(target_match.concept_score, derived_concept_score),
                matched_concepts=matched_concepts,
            )
            contextual_terminal_evidence = bool(
                label_target_concepts
                and ranking_match.concept_score >= 0.28
                and len(ranking_match.matched_concepts) >= 2
            )
        title_matches_label = _title_describes_candidate(
            request.screen.window_title,
            candidate.label,
        )
        if (
            target_definition is not None
            and target_definition.state_changing
            and title_matches_label
            and not _title_has_specific_target_identity(
                target_definition,
                request.screen.window_title,
            )
            and (element is None or not element.checkable)
        ):
            # Scroll/list containers often repeat a broad title such as
            # "Safety features".  That proves only the parent hub, not a
            # specific state-changing destination such as crash detection.
            continue
        destination_field = bool(
            arrived_from_navigation
            and element is not None
            and element.role.lower() in {"input", "edittext", "textfield", "text_field", "searchbox"}
            and catalog.terminal_screen_score(
                target_function,
                request.screen.window_title,
            )
            >= 0.55
        )
        recovery_alignment = _goal_candidate_recovery_alignment(
            request.goal_text,
            candidate.label,
        )
        strongly_aligned_screen_destination = bool(
            recovery_alignment >= 0.55
            and catalog.terminal_screen_score(
                target_function,
                request.screen.window_title,
            )
            >= 0.75
        )
        strongly_aligned_user_boundary = bool(
            recovery_alignment >= 0.55
            and _looks_like_final_state_change_action(candidate.label)
        )
        read_only_outcome_destination = bool(
            recovery_alignment >= 0.55
            and _looks_like_read_only_outcome_candidate(
                request.screen.window_title,
                candidate.label,
            )
        )
        target_page_destination = bool(
            arrived_from_navigation
            and catalog.terminal_screen_score(
                target_function,
                request.screen.window_title,
            )
            >= 0.55
        )
        choice_state_destination = bool(
            arrived_from_navigation
            and element is not None
            and (element.checkable or element.selected)
            and _selected_state_has_target_identity(
                target_function=target_function,
                candidate_label=candidate.label,
                target_match=target_match,
            )
            and not (
                _target_requires_specific_terminal_identity(target_definition)
                and selected_generic_navigation
            )
        )
        settings_page_destination = bool(
            arrived_from_navigation
            and target_definition is not None
            and target_definition.domain == "settings"
            and any(
                marker in _plain_phrase(request.screen.window_title)
                for marker in ("설정", "모양", "화면", "settings", "appearance", "display")
            )
        )
        search_results_destination = bool(
            arrived_from_navigation
            and any(
                marker in _plain_phrase(request.screen.window_title)
                for marker in (
                    "검색 결과",
                    "찾기 결과",
                    "search results",
                    "results for",
                )
            )
        )
        final_choice_destination = bool(
            arrived_from_navigation
            and _looks_like_final_choice_boundary(
                target_function=target_function,
                request=request,
                candidate=candidate,
            )
        )
        synthesized_destination = bool(
            (
                (
                    arrived_from_navigation
                    and (
                        title_matches_label
                    or destination_field
                    or recovery_alignment >= 0.55
                    or (
                            state.back_count > 0
                            and target_match is not None
                            and target_match.score >= 0.34
                        )
                        or (
                            state.back_count > 0
                            and text_similarity(request.goal_text, candidate.label) >= 0.25
                        )
                    )
                )
                or strongly_aligned_screen_destination
                or strongly_aligned_user_boundary
                or read_only_outcome_destination
                or final_choice_destination
                or choice_state_destination
                or settings_page_destination
                or search_results_destination
                or reviewed_external_subscription_handoff
                or explicit_subscription_cancel_destination
            )
            and (
                reviewed_external_subscription_handoff
                or not _looks_like_promotional_or_auxiliary_candidate(
                    candidate.label,
                    allow_help=_goal_requests_help(request.goal_text),
                )
            )
            and not (
                _target_requires_specific_terminal_identity(target_definition)
                and selected_generic_navigation
            )
        )
        if (
            synthesized_destination
            and _terminal_cues_for_function(target_function) is not None
            and not _has_required_terminal_cue(target_function, candidate.label)
            and not destination_field
            and not final_choice_destination
            and not reviewed_external_subscription_handoff
            and not explicit_subscription_cancel_destination
        ):
            # Screen context can prove that the destination surface is open,
            # but it must not lend its identity to an unrelated child row.
            # The screen-level terminal check below can still complete the
            # route without inventing a terminal action for that child.
            synthesized_destination = False
        if target_match is None and not signup_gateway and not synthesized_destination:
            continue
        # Curated negative context is authoritative for destination identity.
        # Informational siblings such as "삭제 안내" and promotional cards
        # may share every positive keyword with an action, but are explicitly
        # not the requested control.
        if target_match is not None and target_match.negative_evidence:
            continue
        if _goal_candidate_recovery_alignment(
            request.goal_text,
            candidate.label,
        ) <= -0.55:
            continue
        if (
            not signup_gateway
            and not explicit_terminal_control
            and not requested_support_hub_boundary
            and not explicit_user_owned_boundary
            and not explicit_subscription_cancel_destination
            and not reviewed_external_subscription_handoff
            and _target_control_is_navigation_entry(
                target_function=target_function,
                target_definition=target_definition,
                candidate=candidate,
                element=element,
                request=request,
                state=state,
                catalog=catalog,
            )
        ):
            continue
        if (
            not reviewed_external_subscription_handoff
            and not signup_gateway
            and _target_control_is_navigation_entry(
                target_function=target_function,
                target_definition=target_definition,
                candidate=candidate,
                element=element,
                request=request,
                state=state,
                catalog=catalog,
            )
            and _target_entry_is_safe_to_open(
                target_function=target_function,
                target_definition=target_definition,
                candidate=candidate,
                request=request,
            )
        ):
            # A target-labelled row on a generic feature/category screen is
            # still a reversible doorway.  The user's final-click boundary is
            # the target's own screen, not this parent-row selection.
            continue
        if not _satisfies_semantic_terminal_concepts(
            catalog,
            target_function,
            candidate.label,
        ) and not (
            target_match is not None
            and target_match.alias_score >= 0.94
            and target_match.score >= 0.78
        ) and not contextual_terminal_evidence and not synthesized_destination and not goal_aligned_terminal_boundary:
            continue
        if (
            target_definition is not None
            and target_definition.state_changing
            and _looks_like_intermediate_process_label(candidate.label)
        ):
            continue
        candidate_concepts = catalog.semantic_concepts_for_text(candidate.label)
        if (
            target_definition is not None
            and target_definition.risk_level in {"medium", "high", "blocked"}
        ):
            action_concepts = (
                frozenset(target_definition.semantic_concepts)
                & ACTION_TERMINAL_CONCEPTS
            )
            if (
                action_concepts
                and not action_concepts.intersection(candidate_concepts)
                and not _has_required_terminal_cue(target_function, candidate.label)
                and not synthesized_destination
            ):
                continue
        goal_concept_count = len(goal_concepts & candidate_concepts)
        has_compositional_evidence = bool(
            ranking_match is not None
            and ranking_match.concept_score >= 0.28
            and len(ranking_match.matched_concepts) >= 2
        )
        has_goal_aligned_evidence = bool(
            target_match is not None
            and target_match.score >= 0.34
            and goal_concept_count >= 1
            and len(_plain_phrase(candidate.label)) >= 4
        )
        has_strong_paraphrase_evidence = bool(
            target_match is not None
            and target_match.score >= 0.50
            and target_match.alias_score >= 0.45
            and len(_plain_phrase(candidate.label)) >= 4
        )
        has_terminal_cue = _has_required_terminal_cue(target_function, candidate.label)
        requires_terminal_cue = _requires_explicit_terminal_cue(target_function)
        if (
            not signup_gateway
            and not synthesized_destination
            and requires_terminal_cue
            and not has_terminal_cue
        ):
            continue
        if (
            not signup_gateway
            and not synthesized_destination
            and not has_terminal_cue
            and not has_compositional_evidence
            and not has_goal_aligned_evidence
            and not has_strong_paraphrase_evidence
            and not goal_aligned_terminal_boundary
        ):
            continue
        if (
            target_function == "auth.signup.entry"
            and not signup_gateway
            and _looks_like_combined_auth_gateway(candidate.label)
        ):
            continue
        if (
            target_function == "subscription.cancel.entry"
            and (
                _looks_like_subscription_offer(candidate.label)
                or not (
                    _is_supported_subscription_cancel_destination(
                        candidate.label,
                        request=request,
                        state=state,
                    )
                    or reviewed_external_subscription_handoff
                )
            )
        ):
            # Cancellation is a user-owned boundary.  Screen context, a
            # selected tab, or generic choice state may help rank progress,
            # but can never manufacture cancellation identity.  The only
            # reviewed exception is an explicit external provider handoff
            # such as "Google Play에서 관리" on a subscription-specific
            # surface; the provider still owns the final cancellation press.
            continue
        score = (
            max(0.46, text_similarity(request.goal_text, candidate.label))
            if synthesized_destination
            else (0.0 if ranking_match is None else ranking_match.score)
        )
        if signup_gateway:
            score = max(score, 0.88)
        minimum_score = (
            0.46
            if synthesized_destination
            or goal_aligned_terminal_boundary
            or (requires_terminal_cue and has_terminal_cue)
            else (
                0.34
                if has_goal_aligned_evidence
                else (
                    0.50
                    if has_strong_paraphrase_evidence
                    else (0.52 if has_compositional_evidence else 0.70)
                )
            )
        )
        if score < minimum_score:
            continue
        # Exact short labels frequently collide across domains ("카드",
        # "기록", "Autoplay").  Do not declare a destination from a tied
        # alias unless multiple independent semantic atoms support the target.
        if (
            strongest_competitor >= score - 0.025
            and not has_compositional_evidence
            and not has_goal_aligned_evidence
            and not has_strong_paraphrase_evidence
            and not signup_gateway
            and not synthesized_destination
        ):
            continue
        function_ids = tuple(dict.fromkeys(
            match.function_id for match in direct_matches if match.score >= 0.46
        ))
        if synthesized_destination and target_function not in function_ids:
            function_ids = function_ids + (target_function,)
        if signup_gateway and target_function not in function_ids:
            function_ids = function_ids + (target_function,)
        current = TerminalCandidate(candidate, function_ids, score)
        rank = _terminal_candidate_rank(
            candidate,
            ranking_match,
            score=score,
            element=element,
            strongest_competitor=strongest_competitor,
            goal_concept_count=goal_concept_count,
            goal_text=request.goal_text,
            target_function=target_function,
            screen_title=request.screen.window_title,
        )
        if best is None or rank > best_rank:
            best = current
            best_rank = rank
    return best


def _terminal_candidate_rank(
    candidate: UniversalNavigationCandidate,
    target_match,
    *,
    score: float,
    element,
    strongest_competitor: float,
    goal_concept_count: int,
    goal_text: str,
    target_function: str,
    screen_title: str,
) -> float:
    """Prefer descriptive destination controls over selected short hub tabs."""

    plain = _plain_phrase(candidate.label)
    richness_bonus = min(0.16, max(0, len(plain) - 3) * 0.01)
    short_label_penalty = 0.18 if len(plain) <= 3 else 0.0
    single_token_penalty = 0.16 if len(plain.split()) == 1 and len(plain) > 3 else 0.0
    selected_tab_penalty = 0.0
    if element is not None and element.selected and str(element.role).lower() in {"tab", "menuitem"}:
        selected_tab_penalty = 0.18
    checked_state_bonus = 0.0
    goal = _plain_phrase(goal_text)
    asks_to_inspect_current_state = any(
        marker in goal
        for marker in (
            "켜졌",
            "이미",
            "확인",
            "현재 상태",
            "whether",
            "already",
            "check if",
            "is on",
            "enabled",
        )
    )
    if element is not None and element.checkable and asks_to_inspect_current_state:
        checked_state_bonus = 0.42 if element.checked else -0.08
    wants_a_different_choice = any(
        marker in goal
        for marker in (
            "바꾸",
            "변경",
            "전환",
            "다른",
            "change",
            "switch",
            "different",
        )
    )
    if element is not None and element.checkable and wants_a_different_choice:
        checked_state_bonus += -0.48 if element.checked else 0.12
    if element is not None and element.selected and wants_a_different_choice:
        checked_state_bonus -= 0.58
    search_field_bonus = 0.0
    if (
        "search" in target_function
        and element is not None
        and str(element.role).lower()
        in {"input", "edittext", "textfield", "text_field", "searchbox"}
    ):
        search_field_bonus = 0.62
    search_result_position_bonus = 0.0
    if any(
        marker in _plain_phrase(screen_title)
        for marker in ("검색 결과", "찾기 결과", "search results", "results for")
    ) and element is not None and element.bounds and len(element.bounds) == 4:
        search_result_position_bonus = max(0.0, 0.28 - float(element.bounds[1]) / 1600.0)
    signup_field_bonus = 0.0
    if target_function == "auth.signup.entry" and any(
        marker in plain
        for marker in ("이메일", "전화번호", "휴대폰", "email", "phone", "mobile")
    ):
        signup_field_bonus = 0.82
    concept_score = 0.0 if target_match is None else target_match.concept_score
    concept_count = 0 if target_match is None else len(target_match.matched_concepts)
    compositional_bonus = concept_score * 0.50 + max(0, concept_count - 2) * 0.055
    exact_alias_bonus = (
        0.10 if target_match is not None and target_match.alias_score >= 0.98 else 0.0
    )
    # Exact aliases can be generic across domains (for example "statement").
    # Goal-label semantic overlap supplies the missing user-specific qualifier
    # such as monthly, onboarding, email, or recovery.
    goal_alignment_bonus = min(1.20, max(0, goal_concept_count) * 0.50)
    alias_collision_penalty = (
        0.30
        if strongest_competitor >= score - 0.10 and concept_score < 0.40
        else 0.0
    )
    risk_penalty = {
        "medium": 0.08,
        "high": 0.42,
        "blocked": 0.55,
    }.get(candidate.risk_level, 0.0)
    return (
        score
        + richness_bonus
        + compositional_bonus
        + exact_alias_bonus
        + goal_alignment_bonus
        + checked_state_bonus
        + search_field_bonus
        + search_result_position_bonus
        + signup_field_bonus
        - short_label_penalty
        - single_token_penalty
        - selected_tab_penalty
        - alias_collision_penalty
        - risk_penalty
        + _goal_candidate_temporal_alignment(goal_text, candidate.label)
        + _goal_candidate_recovery_alignment(goal_text, candidate.label)
        + _goal_candidate_named_entity_alignment(goal_text, candidate.label)
        + _goal_candidate_scope_alignment(goal_text, candidate.label)
        + (
            0.90
            if target_function == "subscription.cancel.entry"
            and _has_explicit_cancellation_cue(candidate.label)
            else 0.0
        )
    )


def _screen_terminal_representative_candidate(
    *,
    target_function: str,
    candidates: list[UniversalNavigationCandidate],
    catalog: NavigationFunctionCatalog,
    request: UniversalNavigationObserveRequest,
) -> TerminalCandidate | None:
    """Name the most relevant visible field when the screen proves arrival.

    Screen-level destination evidence can be stronger than any one child row,
    especially on read-only personal-data pages.  Returning a labelled stop
    keeps the overlay useful without granting permission to click that row.
    """

    best: TerminalCandidate | None = None
    best_rank = float("-inf")
    for candidate in candidates:
        if candidate.risk_level == "blocked" or _looks_like_promotional_or_auxiliary_candidate(
            candidate.label,
            allow_help=_goal_requests_help(request.goal_text),
        ):
            continue
        matches = catalog.match_candidate(
            label=candidate.label,
            role=candidate.role,
            locale=request.locale,
            limit=20,
        )
        target_match = next(
            (match for match in matches if match.function_id == target_function),
            None,
        )
        lexical = text_similarity(request.goal_text, candidate.label)
        named = _goal_candidate_named_entity_alignment(
            request.goal_text,
            candidate.label,
        )
        recovery = _goal_candidate_recovery_alignment(
            request.goal_text,
            candidate.label,
        )
        target_score = 0.0 if target_match is None else target_match.score
        temporal = _goal_candidate_temporal_alignment(
            request.goal_text,
            candidate.label,
        )
        goal = _plain_phrase(request.goal_text)
        label = _plain_phrase(candidate.label)
        dismissed_history_alignment = 0.0
        if any(marker in goal for marker in ("dismissed", "지운 알림", "삭제한 알림")):
            if any(
                marker in label
                for marker in ("recently dismissed", "last 24 hours", "최근", "지난 24시간")
            ):
                dismissed_history_alignment = 0.72
            elif candidate.role.lower() in {"switch", "checkbox", "radio"}:
                dismissed_history_alignment = -0.35
        rank = (
            max(target_score, lexical, named, recovery)
            + temporal
            + dismissed_history_alignment
        )
        if rank < 0.20:
            continue
        if rank <= best_rank:
            continue
        function_ids = tuple(
            dict.fromkeys(
                [
                    match.function_id
                    for match in matches
                    if match.score >= 0.46
                ]
                + [target_function]
            )
        )
        best = TerminalCandidate(
            candidate=candidate,
            function_ids=function_ids,
            confidence=max(0.52, min(0.94, rank)),
        )
        best_rank = rank
    return best


def _screen_is_terminal_destination(
    *,
    target_function: str,
    target_definition,
    request: UniversalNavigationObserveRequest,
    state: ExplorationState,
    catalog: NavigationFunctionCatalog,
) -> bool:
    """Use screen state, not a visible doorway label, as destination proof.

    A target-looking clickable row on an account/home/settings page normally
    *opens* the destination.  The previous implementation concatenated every
    row into one string, so that row also made the parent page score as the
    destination.  Only the title and non-navigation state are considered here.
    """

    title = request.screen.window_title
    title_score = catalog.terminal_screen_score(target_function, title)
    state_labels = [
        element.text or element.content_description or ""
        for element in request.screen.elements
        if element.visible
        and not element.password
        and (
            not element.clickable
            or not element.enabled
            or element.checkable
            or element.role.lower() in {"input", "edittext", "textfield", "progressbar"}
        )
    ]
    state_text = " ".join(filter(None, [title, *state_labels]))
    state_score = catalog.terminal_screen_score(target_function, state_text)
    arrived = bool(request.transition is not None or state.path or state.back_count > 0)

    if _is_stale_or_offline_snapshot(request):
        return False
    if (
        _goal_or_screen_requests_below_fold(request)
        and any(element.visible and element.enabled and element.scrollable for element in request.screen.elements)
    ):
        return False

    if (
        arrived
        and _target_is_notification_preferences(target_function)
        and _screen_is_notification_preferences_surface(request)
    ):
        return True
    if (
        target_function.startswith("android.permission.")
        and not any(element.visible and element.checkable for element in request.screen.elements)
        and sum(
            element.visible and element.enabled and element.clickable
            for element in request.screen.elements
        )
        >= 2
    ):
        return False

    if (
        arrived
        and target_definition is not None
        and target_definition.state_changing
        and not any(
            element.visible and element.checkable
            for element in request.screen.elements
        )
        and not _title_has_specific_target_identity(target_definition, title)
    ):
        # A generic feature/category title is still an intermediate hub even
        # when the target row is visible below it.  The state-changing target
        # is reached only after its own title or editable choice appears.
        return False

    review_title = _plain_phrase(title)
    if (
        not arrived
        and _goal_requests_review_boundary(request.goal_text)
        and target_definition is not None
        and not any(
            marker in review_title
            for marker in (
                "검토",
                "최종 확인",
                "확인 단계",
                "review",
                "final confirmation",
                "confirm details",
            )
        )
    ):
        return False

    if target_function == "subscription.cancel.entry":
        # A cancellation destination is proven by an explicit cancel/manage
        # control in ``_terminal_candidate``.  Subscription list pages contain
        # passive membership and renewal text, but that only identifies the
        # plan that must be opened next.  Never let aggregated screen text turn
        # the plan list itself into a false destination.
        return False

    if target_definition is not None and not target_definition.terminal:
        if any(
            element.visible
            and element.enabled
            and element.clickable
            and (
                _goal_candidate_recovery_alignment(
                    request.goal_text,
                    element.text or element.content_description or "",
                )
                >= 0.50
                or any(
                    marker in _plain_phrase(element.text or element.content_description or "")
                    for marker in (
                        "계속",
                        "연결",
                        "열기",
                        "continue",
                        "connect",
                        "contact",
                        "open",
                    )
                )
            )
            for element in request.screen.elements
        ):
            return False
        if _goal_requests_review_boundary(request.goal_text):
            return bool(
                arrived
                and any(
                    marker in review_title
                    for marker in (
                        "검토",
                        "최종 확인",
                        "확인 단계",
                        "review",
                        "final confirmation",
                        "confirm details",
                    )
                )
            )
        title_concepts = catalog.semantic_concepts_for_text(title)
        target_concepts = frozenset(target_definition.semantic_concepts)
        return bool(
            title_score >= 0.55
            and (
                len(title_concepts & target_concepts) >= 2
                or (arrived and not target_concepts and title_score >= 0.75)
            )
        )

    if (
        not arrived
        and target_definition is not None
        and target_definition.node_kind == "action_entry"
        and _goal_requests_review_boundary(request.goal_text)
    ):
        return False

    if not _has_required_terminal_cue(target_function, state_text):
        return False
    target_concepts = (
        frozenset()
        if target_definition is None
        else frozenset(target_definition.semantic_concepts)
    )
    if target_concepts:
        required_concepts = min(2, len(target_concepts))
        title_concept_count = len(
            catalog.semantic_concepts_for_text(title) & target_concepts
        )
        state_concept_count = len(
            catalog.semantic_concepts_for_text(state_text) & target_concepts
        )
        if title_score >= 0.80 and title_concept_count >= required_concepts:
            return True
        checkable_state = any(
            element.visible and element.checkable
            for element in request.screen.elements
        )
        return bool(
            arrived
            and (
                (title_score >= 0.42 and title_concept_count >= required_concepts)
                or (
                    state_score >= 0.68
                    and (
                        state_concept_count >= required_concepts
                        or (checkable_state and state_concept_count >= 1)
                    )
                )
            )
        )
    if title_score >= 0.80:
        return True
    checkable_or_read_only_state = any(
        element.visible
        and (
            element.checkable
            or not element.clickable
            or not element.enabled
            or element.role.lower()
            in {"input", "edittext", "textfield", "text_field", "progressbar"}
        )
        for element in request.screen.elements
    )
    return bool(
        arrived
        and checkable_or_read_only_state
        and state_score >= 0.80
    )


def _target_control_is_navigation_entry(
    *,
    target_function: str,
    target_definition,
    candidate: UniversalNavigationCandidate,
    element,
    request: UniversalNavigationObserveRequest,
    state: ExplorationState,
    catalog: NavigationFunctionCatalog,
) -> bool:
    """Identify reversible target-labelled controls that open another surface."""

    if element is None or not element.clickable or not element.enabled or element.checkable:
        return False
    if candidate.risk_level == "blocked":
        return False
    if _looks_like_final_state_change_action(candidate.label):
        return False
    if element.role.lower() in {
        "input",
        "edittext",
        "textfield",
        "text_field",
        "searchbox",
    }:
        return False
    if (
        (request.transition is not None or state.path or state.back_count > 0)
        and _looks_like_final_choice_boundary(
            target_function=target_function,
            request=request,
            candidate=candidate,
        )
    ):
        return False
    if (
        state.back_count > 0
        and target_function in {"data.download", "billing.receipt", "files.upload"}
        and any(
            marker in _plain_phrase(candidate.label)
            for marker in (
                "내보내기",
                "다운로드",
                "내려받기",
                "요청",
                "export",
                "download",
                "request",
            )
        )
    ):
        # Returning from an external/browser dead end should expose the action
        # to the user, not immediately repeat it and recreate the loop.
        return False
    if _looks_like_content_discovery_surface(request):
        return True

    label = _plain_phrase(candidate.label)
    title = _plain_phrase(request.screen.window_title)
    arrived = bool(request.transition is not None or state.path or state.back_count > 0)
    if (
        _target_is_notification_preferences(target_function)
        and _has_required_terminal_cue(target_function, candidate.label)
        and not _screen_is_notification_preferences_surface(request)
    ):
        # A notification-labelled row on a general account/settings page is a
        # doorway.  Only a destination surface with editable preference
        # evidence can complete the goal.
        return True
    action_markers = (
        "열기",
        "이동",
        "시작",
        "계속",
        "선택",
        "연결",
        "찾기",
        "검색",
        "내려받기",
        "다운로드",
        "돌아가기",
        "사용하기",
        "요청",
        "open",
        "start",
        "continue",
        "connect",
        "contact",
        "talk to",
        "choose",
        "select",
        "search",
        "find",
        "download",
        "return to",
        "request",
    )
    explicit_action = any(marker in label for marker in action_markers)
    function_tokens = _function_identifier_tokens(target_function)
    entry_family = bool(function_tokens & ENTRY_FUNCTION_TOKENS)
    review_route = _goal_requests_review_boundary(request.goal_text)
    process_label = _looks_like_intermediate_process_label(candidate.label)
    title_score = catalog.terminal_screen_score(
        target_function,
        request.screen.window_title,
    )
    recovery_alignment = _goal_candidate_recovery_alignment(
        request.goal_text,
        candidate.label,
    )
    confirmation_surface = any(
        marker in title
        for marker in (
            "최종 확인",
            "검토",
            "미리보기",
            "confirmation",
            "review",
            "preview",
        )
    )
    direct_matches = catalog.match_candidate(
        label=candidate.label,
        parent_label="",
        nearby_text="",
        role=candidate.role,
        position="",
        locale=request.locale,
        enabled=element.enabled,
        checkable=element.checkable,
        checked=element.checked,
        selected=element.selected,
        limit=40,
    )
    direct_target = next(
        (match for match in direct_matches if match.function_id == target_function),
        None,
    )
    strongest_competitor = max(
        (
            match.score
            for match in direct_matches
            if match.function_id != target_function
        ),
        default=0.0,
    )
    target_identity_dominates = bool(
        direct_target is not None
        and direct_target.score >= 0.58
        and direct_target.score >= strongest_competitor + 0.015
    )
    goal_aligned_target_control = bool(
        direct_target is not None
        and direct_target.score >= 0.58
        and _has_required_terminal_cue(target_function, candidate.label)
        and (
            _goal_candidate_named_entity_alignment(
                request.goal_text,
                candidate.label,
            )
            >= 0.20
            or _goal_candidate_recovery_alignment(
                request.goal_text,
                candidate.label,
            )
            >= 0.50
        )
    )
    if (
        target_definition is not None
        and target_definition.automation_policy == "never_auto"
        and not target_definition.state_changing
        and target_identity_dominates
        and title != label
        and not confirmation_surface
        and not element.checkable
        and candidate.risk_level == "low"
        and not _screen_is_terminal_destination(
            target_function=target_function,
            target_definition=target_definition,
            request=request,
            state=state,
            catalog=catalog,
        )
    ):
        # A requested read-only sensitive destination can still be behind a
        # reversible row (for example Notification history -> its data page).
        # The destination screen remains a user-owned stop boundary.
        return True
    if (
        target_definition is not None
        and (
            target_definition.automation_policy == "never_auto"
            or target_definition.state_changing
        )
        and title != label
        and not confirmation_surface
        and bool(function_tokens & USER_OWNED_ACTION_FUNCTION_TOKENS)
        and not target_identity_dominates
    ):
        # A weak fuzzy match to a user-owned action (for example a generic
        # health-card row matching certificate issuance) is only a doorway.
        # It must not become destination proof through surrounding context.
        return True
    if (
        target_definition is not None
        and target_function not in {"auth.signup.entry", "settings.language"}
        and title != label
        and not confirmation_surface
        and not element.checkable
        and (
            (
                target_definition.terminal
                and target_definition.automation_policy == "safe_navigation"
                and not target_identity_dominates
                and not goal_aligned_target_control
            )
            or (
                (
                    target_definition.automation_policy == "never_auto"
                    or target_definition.state_changing
                )
                and (
                    (
                        target_definition.state_changing
                        and not (function_tokens & USER_OWNED_ACTION_FUNCTION_TOKENS)
                    )
                    or (
                        not target_definition.state_changing
                        and not target_identity_dominates
                    )
                    or (
                        not target_definition.state_changing
                        and arrived
                        and (
                            title
                            in {
                                "you",
                                "your info",
                                "my",
                                "me",
                                "profile",
                                "account",
                                "내 정보",
                                "내 계정",
                                "마이",
                                "프로필",
                            }
                            or (
                                review_route
                                and not _screen_is_terminal_destination(
                                target_function=target_function,
                                target_definition=target_definition,
                                request=request,
                                state=state,
                                catalog=catalog,
                                )
                            )
                        )
                    )
                )
            )
        )
    ):
        return True
    if (
        target_definition is not None
        and not target_definition.terminal
        and not _goal_requests_help(request.goal_text)
        and title_score < 0.55
        and not _title_describes_candidate(request.screen.window_title, candidate.label)
    ):
        # Non-terminal catalog functions describe a hub or a reusable
        # navigation surface.  A matching row on a generic parent screen opens
        # that surface; it is not destination proof.  This prevents rows such
        # as "Purchases and memberships" from ending a request for the actual
        # membership-details screen.
        return True
    if (
        target_function.startswith("android.permission.")
        and not any(
            visible.visible and visible.checkable
            for visible in request.screen.elements
        )
        and sum(
            visible.visible and visible.enabled and visible.clickable
            for visible in request.screen.elements
        )
        >= 2
    ):
        # Android permission category pages and per-app service lists use the
        # permission name as their title.  Until a toggle/choice is visible,
        # the rows are still reversible gateways rather than the permission
        # boundary itself.
        return True
    if _looks_like_account_add_gateway(candidate.label):
        return True
    if (
        arrived
        and _looks_like_final_identity_confirmation(
            target_function,
            candidate.label,
        )
    ):
        return False
    if (
        arrived
        and recovery_alignment >= 0.55
        and not explicit_action
    ):
        return False
    if (
        _goal_candidate_recovery_alignment(request.goal_text, candidate.label) >= 0.55
        and _looks_like_read_only_outcome_candidate(
            request.screen.window_title,
            candidate.label,
        )
    ):
        return False

    if (
        explicit_action
        and title != label
        and not target_identity_dominates
        and not goal_aligned_target_control
        and not _looks_like_final_choice_boundary(
            target_function=target_function,
            request=request,
            candidate=candidate,
        )
    ):
        return True

    if review_route and not (
        arrived
        and _title_describes_candidate(request.screen.window_title, candidate.label)
    ) and (
        entry_family
        or (
            target_definition is not None
            and target_definition.node_kind == "action_entry"
        )
        or (target_function.endswith(".confirm") and explicit_action)
    ):
        return True
    if title != label and title_score < 0.42:
        if (
            target_definition is not None
            and target_definition.automation_policy == "safe_navigation"
            and not arrived
            and not target_identity_dominates
            and not goal_aligned_target_control
        ):
            return True
        if target_function.startswith("android."):
            return True
        if (
            target_function.endswith(".entry")
            and candidate.risk_level == "low"
            and not arrived
            and not target_identity_dominates
            and not goal_aligned_target_control
        ):
            return True
        if _screen_title_marks_recovery_gateway(request.screen.window_title):
            return True
    if (
        not arrived
        and entry_family
        and target_definition is not None
        and target_definition.automation_policy == "safe_navigation"
        and title != label
        and catalog.terminal_screen_score(target_function, request.screen.window_title) < 0.35
        and not target_identity_dominates
        and not goal_aligned_target_control
    ):
        return True
    return False


def _screen_title_marks_recovery_gateway(title: str) -> bool:
    value = _plain_phrase(title)
    return any(
        marker in value
        for marker in (
            "계정이 일시적으로 잠겼",
            "계정 선택",
            "앱 정보",
            "앱 설정",
            "특별한 앱 액세스",
            "권한",
            "저장공간",
            "접근이 필요한 이유",
            "계속 중단됨",
            "계정 만들기",
            "약관 동의",
            "옵션",
            "wallet",
            "legal",
            "claim documents",
            "order details",
            "account picker",
            "account locked",
            "app info",
            "app settings",
            "special app access",
            "permissions",
            "storage",
            "options",
            " menu",
        )
    )


def _title_has_specific_target_identity(target_definition, title: str) -> bool:
    """Require the destination name, not merely its broad domain, in a title."""

    title_value = _plain_phrase(title)
    title_compact = "".join(character for character in title_value if character.isalnum())
    if not title_compact:
        return False
    identities = [target_definition.name_ko, target_definition.name_en]
    identities.extend(alias.phrase for alias in target_definition.aliases)
    for identity in identities:
        value = _plain_phrase(str(identity))
        compact = "".join(character for character in value if character.isalnum())
        if not compact:
            continue
        if title_compact == compact:
            return True
        if len(compact) >= 8 and compact in title_compact:
            return True
    return False


def _looks_like_account_add_gateway(label: str) -> bool:
    value = _plain_phrase(label)
    return any(
        marker in value
        for marker in (
            "다른 계정 사용",
            "다른 계정 추가",
            "새 계정 추가",
            "use another account",
            "add another account",
            "add account",
        )
    )


def _looks_like_account_gateway_label(label: str) -> bool:
    value = _plain_phrase(label)
    if any(
        marker in value
        for marker in (
            "프로필 편집",
            "프로필 수정",
            "프로필 공유",
            "edit profile",
            "share profile",
        )
    ):
        return False
    return any(
        marker in value
        for marker in (
            "마이페이지",
            "내 페이지",
            "내 계정",
            "계정 메뉴",
            "프로필 사진",
            "프로필 이미지",
            "profile picture",
            "profile photo",
            "account menu",
            "my account",
            "my page",
        )
    ) or value in {"프로필", "계정", "profile", "account", "you"}


def _looks_like_final_identity_confirmation(
    target_function: str,
    label: str,
) -> bool:
    if target_function not in {"auth.login", "auth.verification"}:
        return False
    value = _plain_phrase(label)
    return any(
        marker in value
        for marker in (
            "계정으로 계속",
            "로 계속",
            "continue as",
            "confirm this account",
            "finish sign in",
            "complete sign in",
        )
    )


def _looks_like_final_choice_boundary(
    *,
    target_function: str,
    request: UniversalNavigationObserveRequest,
    candidate: UniversalNavigationCandidate,
) -> bool:
    """Keep the final picker/identity choice under user control."""

    title = _plain_phrase(request.screen.window_title)
    label = _plain_phrase(candidate.label)
    if _looks_like_final_identity_confirmation(target_function, candidate.label):
        return True
    if target_function in {"files.upload", "content.upload"}:
        picker_title = any(
            marker in title
            for marker in (
                "최근 파일",
                "문서 선택",
                "파일 선택",
                "recent files",
                "choose file",
                "select document",
                "file picker",
            )
        )
        selection_action = any(
            marker in label
            for marker in (
                "하나 선택",
                "문서 선택",
                "파일 선택",
                "select one",
                "select document",
                "choose a document",
                "choose file",
            )
        )
        return bool(picker_title and selection_action)
    if "search" in target_function:
        option_surface = any(
            marker in title
            for marker in ("옵션", "더보기", "menu", "options", "more")
        )
        search_action = any(marker in label for marker in ("검색", "찾기", "search", "find"))
        if option_surface and search_action:
            return True
    if target_function == "billing.receipt":
        billing_history = any(
            marker in title
            for marker in ("결제 내역", "영수증", "billing history", "receipt history")
        )
        receipt_action = any(
            marker in label
            for marker in ("영수증", "내려받기", "download receipt", "receipt")
        )
        if billing_history and receipt_action:
            return True
    if target_function == "notification.settings":
        notification_surface = any(
            marker in title
            for marker in ("알림 설정", "notification settings", "notifications")
        )
        notification_choice = any(
            marker in label
            for marker in ("받을 소식", "알림 선택", "choose notifications", "notification topics")
        )
        if notification_surface and notification_choice:
            return True
    if target_function == "security.password.reset":
        recovery_surface = any(
            marker in title
            for marker in ("복구", "재설정", "recovery", "reset")
        )
        recovery_action = any(
            marker in label
            for marker in (
                "재설정 링크",
                "복구 링크",
                "본인 확인",
                "reset link",
                "recovery link",
                "verify identity",
            )
        )
        if recovery_surface and recovery_action:
            return True
    return False


def _target_entry_is_safe_to_open(
    *,
    target_function: str,
    target_definition,
    candidate: UniversalNavigationCandidate,
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Allow a reversible doorway while preserving the final-click boundary."""

    if (
        target_definition is None
        or candidate.risk_level in {"high", "blocked"}
        or target_function in TARGET_ENTRY_HANDOFF_FUNCTIONS
    ):
        return False
    value = _plain_phrase(candidate.label)
    if _looks_like_final_state_change_action(candidate.label):
        return False
    final_action = any(
        marker in value
        for marker in (
            "최종 확정",
            "삭제 확정",
            "해지 확정",
            "영구 삭제 실행",
            "접수 완료",
            "제출",
            "결제하기",
            "송금하기",
            "confirm deletion",
            "confirm cancellation",
            "submit claim",
            "submit refund",
            "pay now",
            "send money",
        )
    )
    if final_action:
        return False
    review_route = _goal_requests_review_boundary(request.goal_text)
    explicit_entry = any(
        marker in value
        for marker in (
            "열기",
            "시작",
            "만들기",
            "계속",
            "선택",
            "자세히",
            "설정",
            "관리",
            "open",
            "start",
            "create",
            "continue",
            "choose",
            "select",
            "details",
            "settings",
            "methods",
            "다운로드",
            "내려받기",
            "download",
        )
    )
    protected_action_family = bool(
        _function_identifier_tokens(target_function)
        & USER_OWNED_ACTION_FUNCTION_TOKENS
    )
    if target_definition.automation_policy == "never_auto" or target_definition.state_changing:
        # Preserve the user's final-click boundary for claims, refunds,
        # cancellation, deletion, issuance, spoken navigation, and similar
        # process starts.  Other target-labelled rows may still be reversible
        # doorways when they live on a differently titled parent surface;
        # examples include Create -> event picker and Emergency SOS -> its
        # settings page.  The caller has already proven that structure.
        if protected_action_family:
            return False
        title = _plain_phrase(request.screen.window_title)
        if title == value or any(
            marker in title
            for marker in (
                "최종 확인",
                "검토",
                "미리보기",
                "confirmation",
                "review",
                "preview",
            )
        ):
            return False
        if candidate.risk_level != "low":
            return False
        if not target_definition.state_changing:
            return True
        return bool(
            explicit_entry
            or target_function.startswith("android.")
            or target_function.startswith("android_safety.")
            or target_function.startswith("safety.")
            or _screen_title_marks_recovery_gateway(request.screen.window_title)
        )
    return True


def _looks_like_final_state_change_action(label: str) -> bool:
    """Block controls that execute or broadly authorize a state change."""

    value = _plain_phrase(label)
    direct = any(
        marker in value
        for marker in (
            "영구 삭제",
            "원본 삭제",
            "기록 삭제",
            "모든 데이터 삭제",
            "전체삭제",
            "모두삭제",
            "일괄삭제",
            "휴지통으로 이동",
            "삭제 확정",
            "해지 확정",
            "접수 완료",
            "청구 접수",
            "제출",
            "결제하기",
            "송금하기",
            "로그아웃",
            "모든 파일 접근",
            "전체 저장공간 접근",
            "모두 허용",
            "전체 허용",
            "permanently delete",
            "delete history",
            "delete all",
            "delete all data",
            "erase all data",
            "delete original",
            "move to trash",
            "move to recycle bin",
            "confirm deletion",
            "confirm cancellation",
            "submit",
            "pay now",
            "send money",
            "sign out",
            "log out",
            "grant full storage access",
            "allow all files",
            "full access",
        )
    )
    return direct


def _looks_like_irreversible_execution(label: str) -> bool:
    value = _plain_phrase(label)
    return any(
        marker in value
        for marker in (
            "영구 삭제",
            "원본 삭제",
            "기록 삭제",
            "모든 데이터 삭제",
            "전체삭제",
            "모두삭제",
            "일괄삭제",
            "삭제 확정",
            "해지 확정",
            "접수 완료",
            "청구 접수",
            "제출",
            "결제하기",
            "송금하기",
            "로그아웃",
            "모든 파일 접근",
            "전체 저장공간 접근",
            "permanently delete",
            "delete original",
            "delete history",
            "delete all",
            "delete all data",
            "erase all data",
            "confirm deletion",
            "confirm cancellation",
            "submit",
            "pay now",
            "send money",
            "sign out",
            "log out",
            "grant full storage access",
            "allow all files",
        )
    )


def _candidate_function_scores(
    context_scores: tuple[tuple[str, float], ...],
    direct_scores: dict[str, float],
) -> tuple[tuple[str, float], ...]:
    merged = dict(context_scores)
    for function_id, score in direct_scores.items():
        merged[function_id] = max(score, merged.get(function_id, 0.0))
    return tuple(sorted(merged.items(), key=lambda item: (-item[1], item[0])))


def _function_can_progress_goal(
    *,
    function_id: str,
    definition,
    preferred_progress_ids: set[str],
    target_domain: str,
    target_function: str,
) -> bool:
    if function_id in preferred_progress_ids:
        return True
    if target_function == "notification.settings":
        return bool(
            function_id in NOTIFICATION_SETTINGS_GATEWAY_FUNCTIONS
            or (target_domain and definition.domain == target_domain)
        )
    if function_id in COMMON_GATEWAY_FUNCTIONS:
        return True
    if function_id == "support.help" and _target_can_progress_through_support(target_function):
        return True
    if target_domain and definition.domain == target_domain:
        return True
    return False


def _target_can_progress_through_support(target_function: str) -> bool:
    """Return whether a help/feedback hub is a plausible reversible gateway."""

    value = target_function.replace("-", "_")
    return bool(
        value.startswith("support.")
        or value.endswith(".report_issue")
        or value.endswith(".send_feedback")
        or value.endswith(".feedback")
    )


def _target_candidate_hub_alignment(
    target_function: str,
    label: str,
    *,
    goal_text: str = "",
) -> float:
    """Disambiguate generic hub tabs using the target function family."""

    value = _plain_phrase(label)
    goal = _plain_phrase(goal_text)
    if _target_can_progress_through_support(target_function):
        if any(
            marker in value
            for marker in ("도움말", "의견", "help", "feedback", "support")
        ):
            return 0.70
        if value in {"설정", "settings", "preferences"}:
            return -0.30

    if target_function.startswith(("android_safety.", "safety.")):
        information_target = target_function in {
            "android_safety.emergency_info",
            "health.emergency_profile",
            "android_safety.emergency_contacts",
        }
        if value in {"features", "feature", "기능", "안전 기능"}:
            return -0.45 if information_target else 0.62
        if value in {"your info", "my info", "내 정보", "개인 정보"}:
            return 0.62 if information_target else -0.45
        if "emergency_location" in target_function and value in {
            "설정 검색",
            "search settings",
        }:
            return 0.70
        if "emergency_location" in target_function and value in {
            "위치",
            "location",
            "location settings",
        }:
            return -0.55

    if target_function.startswith("calendar."):
        if any(token in target_function for token in ("notification", "timezone")):
            if value in {"설정", "settings", "preferences"}:
                return 0.74
        if "shared" in target_function:
            if value in {"캘린더 이름", "calendar name"}:
                return 0.90
            if value in {"만들기", "create", "new event", "일정", "event"}:
                return 0.74
            if value in {"예약 일정", "appointment schedule", "appointment"}:
                return -0.55
        if any(token in target_function for token in ("event.edit", "event.delete", "rsvp")):
            if "event.edit" in target_function and value in {
                "수정",
                "편집",
                "edit",
                "edit event",
            }:
                return 0.90
            if "event.delete" in target_function and value in {
                "삭제",
                "delete",
                "delete event",
            }:
                return 0.90
            generic = {
                "만들기",
                "create",
                "메뉴",
                "menu",
                "오늘",
                "today",
                "생일",
                "birthday",
            }
            if value in generic:
                return -0.45
            goal_tokens = {
                token
                for token in goal.replace("/", " ").split()
                if len("".join(character for character in token if character.isalnum())) >= 2
            }
            label_tokens = set(value.replace("/", " ").split())
            if goal_tokens & label_tokens or any(
                len(token) >= 2 and token in goal for token in label_tokens
            ):
                return 0.74

    if target_function.startswith("email."):
        if target_function == "email.send":
            if value in {"보내기", "전송", "send", "send email", "send message"}:
                return 0.92
            if value in {"편지쓰기", "메일 쓰기", "compose", "compose mail"}:
                return 0.78
            if value in {"메뉴", "menu", "search", "검색"}:
                return -0.40
        if any(token in target_function for token in ("filters", "forwarding")):
            if value in {"데스크톱 사이트", "desktop site", "desktop version"}:
                return 0.82
        if "labels" in target_function:
            if value in {"설정", "settings"}:
                return 0.76
            if value in {"라벨", "labels"}:
                return -0.36
        if "spam" in target_function and value in {"메뉴", "menu", "open menu"}:
            return 0.72
        if any(token in target_function for token in ("signature", "sync", "vacation")):
            if value == "[email]" or "@" in value:
                return 0.78
            if value in {"기본 설정", "general settings", "계정 추가", "add account"}:
                return -0.38

    if target_function == "media.autoplay":
        if value in {"설정", "settings", "preferences"}:
            return 0.82
        if "premium" in value or "프리미엄" in value:
            return -0.55

    if target_function == "subscription.change":
        if value in {
            "see available plans",
            "available plans",
            "사용 가능한 요금제",
            "요금제 보기",
        }:
            return 0.86
        if value in {"premium benefits", "프리미엄 혜택"}:
            return -0.42

    if target_function == "subscription.cancel.entry":
        if value in {"나의 넷플릭스", "my netflix"}:
            return 0.96
        if any(
            marker in value
            for marker in (
                "프로필을 변경",
                "프로필을 관리",
                "change or manage profile",
                "manage or change profile",
                "switch or manage profile",
            )
        ):
            return 0.90
        if value in {"프로필 관리", "manage profile", "manage profiles"}:
            # On Netflix's opened profile menu this edits viewing profiles; it
            # is not the billing/account doorway. The longer guidance control
            # above is still the correct reversible gateway into this menu.
            return -0.42
        if value in {
            "멤버십 관리",
            "구독 관리",
            "구매 항목 및 멤버십",
            "구독 및 멤버십 관리",
            "결제 및 구독",
            "manage membership",
            "manage subscription",
            "purchases and memberships",
            "payments and subscriptions",
        }:
            return 0.92
        if value in {
            "내 페이지",
            "마이",
            "프로필",
            "계정",
            "profile picture",
            "my page",
            "account",
        }:
            return 0.84
        if value in {"설정", "settings", "preferences"}:
            return 0.82
        if value in {"premium benefits", "premium 혜택", "프리미엄 혜택"}:
            return -0.70

    if target_function == "address.manage":
        if any(marker in value for marker in ("배송지", "배송 주소", "shipping address", "delivery address")):
            return 0.82

    if target_function.startswith("maps."):
        if any(token in target_function for token in ("directions", "navigation")):
            if value in {"여기서 검색", "search here", "directions", "길찾기", "경로"}:
                return 0.72
        if "location_sharing" in target_function or "location_history" in target_function:
            if any(marker in value for marker in ("프로필", "profile picture", "profile initial")):
                return 0.74
            if value in {"내 장소", "my places", "you"}:
                return -0.28
        if "avoid_options" in target_function:
            if value in {"경로 옵션", "route options", "routing options"}:
                return 0.86
            if value in {"경로 공유", "share route", "share directions"}:
                return -0.55
            if value in {"더보기", "more", "more options"}:
                return 0.76
            if value in {"자동차", "car", "start", "시작"}:
                return -0.55
        if "incognito" in target_function:
            if any(marker in value for marker in ("시크릿 모드", "incognito mode", "turn on incognito")):
                return 0.84
            if value in {"설정", "settings"}:
                return -0.36

    if target_function.startswith("android."):
        if "notification" in target_function:
            if value in {"알림", "notifications"}:
                return 0.72
            if value in {"앱", "apps"}:
                return -0.28
        if "permission" in target_function:
            if value in {"보안 및 개인정보 보호", "security & privacy", "security and privacy"}:
                return 0.72
        if "restricted" in target_function and value in {"앱", "apps"}:
            return 0.74
        if any(token in target_function for token in ("wifi", "vpn")):
            if "wifi" in target_function and value in {
                "wi fi 네트워크",
                "wifi 네트워크",
                "wi fi networks",
                "wifi networks",
                "wireless networks",
            }:
                return 0.88
            if value in {"네트워크 및 인터넷", "network & internet", "network and internet"}:
                return 0.76
            if value in {"연결된 기기", "connected devices"}:
                return -0.32
        if "private_dns" in target_function:
            if value in {"고급", "advanced", "advanced settings"}:
                return 0.76
            if value in {"인터넷", "internet"}:
                return -0.30

    if target_function.startswith("android_backup.") or target_function in {
        "files.backup",
        "backup.files",
    }:
        if value in {
            "google",
            "all services",
            "모든 서비스",
            "copy apps & data",
            "앱 및 데이터 복사",
            "시작",
            "start",
        }:
            return 0.78
        if value in {"system", "시스템", "manage your google account"}:
            return -0.36

    if target_function.startswith("insurance."):
        if "branch" in target_function and any(
            marker in value for marker in ("고객센터", "customer center", "support")
        ):
            return 0.78
        if any(token in target_function for token in ("certificate", "contract")):
            if "contract" in target_function and (
                "계약조회" in value
                or "계약 조회" in value
                or "contract list" in value
                or "my contracts" in value
            ):
                return 0.88
            if value.startswith("my") or value.startswith("마이") or "계약조회" in value:
                return 0.76
            if any(marker in value for marker in ("보험상품", "products", "대출", "loan")):
                return -0.42
        if target_function == "insurance.premium.payment" and any(
            marker in goal for marker in ("건강보험", "health insurance", "nhis")
        ):
            if value in {"민원여기요", "civil service", "민원"}:
                return 0.80
            if "보험증" in value or "health card" in value:
                return -0.42

    if target_function.startswith("health_insurance.") and "premium" in target_function:
        if value in {"민원여기요", "civil service", "민원"}:
            return 0.78
        if "보험증" in value or "health card" in value:
            return -0.38
    if target_function == "account.delete.entry":
        if value in {
            "profile",
            "프로필",
            "my profile",
            "내 프로필",
            "more",
            "더보기",
            "settings",
            "설정",
            "accounts center",
            "계정 센터",
            "personal details",
            "개인정보",
            "account ownership and control",
            "계정 소유권 및 관리",
        }:
            return 0.78
        if value in {"reels", "create", "만들기", "saved", "저장됨"}:
            return -0.55
    return 0.0


def _is_safe_review_gateway(
    *,
    function_id: str,
    target_function: str,
    label: str,
    goal_text: str,
    definition,
) -> bool:
    if definition.state_changing or not _goal_requests_review_boundary(goal_text):
        return False
    same_flow = bool(
        target_function.endswith(".confirm")
        and function_id.endswith(".entry")
        and target_function.rsplit(".", 1)[0] == function_id.rsplit(".", 1)[0]
    )
    same_target_entry = bool(
        function_id == target_function
        and (
            definition.node_kind == "action_entry"
            or function_id.endswith(".entry")
            or _looks_like_intermediate_process_label(label)
        )
    )
    return same_flow or same_target_entry


def _medium_risk_candidate_is_review_gateway(
    *,
    candidate: UniversalNavigationCandidate,
    request: UniversalNavigationObserveRequest,
    target_function: str,
    catalog: NavigationFunctionCatalog,
) -> bool:
    if candidate.risk_level != "medium" or not _goal_requests_review_boundary(request.goal_text):
        return False
    title = _plain_phrase(request.screen.window_title)
    if not any(
        marker in title
        for marker in (
            "옵션",
            "관리",
            "상세",
            "소유권",
            "menu",
            "options",
            "management",
            "details",
        )
    ):
        return False
    matches = catalog.match_candidate(label=candidate.label, limit=20)
    target_prefix = target_function.rsplit(".", 1)[0]
    return any(
        match.score >= 0.42
        and (
            match.function_id == target_function
            or (
                target_function.endswith(".confirm")
                and match.function_id.endswith(".entry")
                and match.function_id.rsplit(".", 1)[0] == target_prefix
            )
        )
        for match in matches
    )


def _goal_requests_review_boundary(goal_text: str) -> bool:
    goal = _plain_phrase(goal_text)
    return any(
        marker in goal
        for marker in (
            "마지막 확인",
            "최종 확인",
            "검토 화면",
            "확인 단계",
            "확정 단계",
            "실제 삭제는",
            "실제 해지는",
            "접수 버튼은 내가",
            "마지막 선택은 내가",
            "누르지 마",
            "제출하지",
            "까지만",
            "final review",
            "review screen",
            "confirmation screen",
            "leave submission to me",
            "never send",
            "do not confirm",
            "don't confirm",
            "without activating",
            "without granting",
            "without giving access",
            "but do not",
        )
    )


def _goal_requests_help(goal_text: str) -> bool:
    goal = _plain_phrase(goal_text)
    return any(
        marker in goal
        for marker in (
            "도움말",
            "고객센터",
            "자주 묻는",
            "문의",
            "상담",
            "help",
            "support",
            "faq",
            "contact",
            "agent",
        )
    )


def _goal_requests_sharing(goal_text: str) -> bool:
    goal = _plain_phrase(goal_text)
    return any(
        marker in goal
        for marker in (
            "공유",
            "링크 보내",
            "링크 복사",
            "share",
            "send link",
            "copy link",
        )
    )


def _goal_requests_legal_document(goal_text: str) -> bool:
    goal = _plain_phrase(goal_text)
    return any(
        marker in goal
        for marker in (
            "약관",
            "개인정보 처리방침",
            "개인정보 정책",
            "법적 고지",
            "terms",
            "privacy policy",
            "legal notice",
        )
    )


def _looks_like_goal_irrelevant_auxiliary_link(
    label: str,
    *,
    goal_text: str,
    target_function: str,
) -> bool:
    """Keep support/share/legal links out of unrelated feature routes.

    These controls often look like harmless generic navigation and therefore
    used to survive the function filter.  They commonly leave the app or open
    a document tree, so their family must be explicitly requested rather than
    inferred as progress from a product name shared with the user's goal.
    """

    value = _plain_phrase(label)
    if any(
        marker in value
        for marker in ("탐색 종료", "내비게이션 종료", "close navigation", "stop navigation")
    ) and not any(
        token in target_function
        for token in ("navigation.stop", "navigation.close", "trip.end")
    ):
        return True
    if target_function == "account.delete.entry" and any(
        marker in value
        for marker in (
            "프로필 편집",
            "프로필 수정",
            "프로필 공유",
            "edit profile",
            "share profile",
            "change avatar",
            "edit avatar",
        )
    ):
        return True
    support_link = any(
        marker in value
        for marker in (
            "지원팀",
            "고객센터",
            "고객 지원",
            "도움말",
            "문의하기",
            "상담 연결",
            "support team",
            "support center",
            "customer support",
            "customer service",
            "help center",
            "contact support",
            "contact us",
            "faq",
        )
    )
    allows_support = bool(
        _goal_requests_help(goal_text)
        or target_function.startswith("support.")
    )
    if support_link and not allows_support:
        # Some products expose no in-app cancellation control and explicitly
        # direct the user to support (for example, "Contact support to cancel
        # subscription").  Preserve that combined, self-describing boundary
        # as a user-owned destination while still rejecting a generic support
        # link that merely sits beside the paid-plan controls.
        support_only_cancellation_boundary = bool(
            target_function == "subscription.cancel.entry"
            and _has_descriptive_subscription_cancellation_cue(label)
            and not _looks_like_cancellation_information_or_unrelated_action(label)
        )
        if not support_only_cancellation_boundary:
            return True

    sharing_link = bool(
        value in {
            "공유",
            "공유하기",
            "링크 공유",
            "링크 복사",
            "share",
            "share link",
            "copy link",
        }
        or value.startswith("공유 대상")
        or value.startswith("share via")
    )
    allows_sharing = bool(
        _goal_requests_sharing(goal_text)
        or ".share" in target_function
        or ".shared" in target_function
        or target_function.startswith("content.share")
        or target_function.startswith("files.share")
    )
    if sharing_link and not allows_sharing:
        return True

    gifting_link = any(
        marker in value
        for marker in (
            "선물하기",
            "선물함",
            "기프트카드",
            "gift this",
            "send gift",
            "gift card",
            "gifts",
        )
    )
    allows_gifting = any(
        marker in _plain_phrase(goal_text)
        for marker in ("선물", "gift")
    ) or target_function.startswith("gift.")
    if gifting_link and not allows_gifting:
        return True

    paid_product_link = any(
        marker in value
        for marker in (
            "premium",
            "프리미엄",
            "멤버십",
            "membership",
            "upgrade plan",
            "플랜 업그레이드",
            "구매하기",
            "buy premium",
        )
    )
    allows_paid_product = bool(
        target_function.startswith("subscription.")
        or target_function.startswith("billing.")
        or target_function.startswith("purchase.")
        or target_function.startswith("payment.")
        or any(
            marker in _plain_phrase(goal_text)
            for marker in (
                "구독",
                "멤버십",
                "프리미엄",
                "요금제",
                "결제",
                "subscription",
                "membership",
                "premium",
                "plan",
                "billing",
            )
        )
    )
    if paid_product_link and not allows_paid_product:
        return True

    legal_link = any(
        marker in value
        for marker in (
            "이용약관",
            "서비스 약관",
            "개인정보 처리방침",
            "개인정보 정책",
            "법적 고지",
            "terms of service",
            "terms and conditions",
            "privacy policy",
            "legal notice",
        )
    )
    allows_legal = bool(
        _goal_requests_legal_document(goal_text)
        or target_function.startswith("legal.")
        or target_function.endswith(".terms")
        or target_function.endswith(".policy")
        or "privacy_policy" in target_function
    )
    return bool(legal_link and not allows_legal)


def _looks_like_promotional_or_auxiliary_candidate(label: str, *, allow_help: bool) -> bool:
    value = _plain_phrase(label)
    promotional = (
        "추천 항목",
        "추천 상품",
        "추천 이용권",
        "비슷한 추천",
        "유사 추천",
        "광고",
        "스폰서",
        "recommended",
        "similar suggestion",
        "sponsored",
        "special offer",
    )
    if any(marker in value for marker in promotional):
        return True
    if not allow_help and any(
        marker in value
        for marker in (
            "관련 도움말",
            "비슷한 도움말",
            "도움말 보기",
            "related help",
            "similar help",
            "learn more",
        )
    ):
        return True
    return False


def _goal_candidate_scope_alignment(goal_text: str, label: str) -> float:
    """Penalize an unrequested product scope added by a sibling action."""

    goal = _plain_phrase(goal_text)
    candidate = _plain_phrase(label)
    qualifier_groups = (
        ("자동차", "차량", "auto insurance", "car insurance", "vehicle"),
        ("장기보험", "장기 보험", "long term", "long-term"),
        ("여행보험", "여행 보험", "travel insurance"),
        ("주택보험", "주택 보험", "home insurance"),
    )
    score = 0.0
    for group in qualifier_groups:
        goal_has = any(marker in goal for marker in group)
        candidate_has = any(marker in candidate for marker in group)
        if candidate_has and not goal_has:
            score -= 0.58
        elif candidate_has and goal_has:
            score += 0.22
    return score


def _goal_candidate_temporal_alignment(goal_text: str, label: str) -> float:
    """Resolve current/active state requests against history/look-back labels."""

    goal = _plain_phrase(goal_text)
    candidate = _plain_phrase(label)
    wants_current = any(
        marker in goal
        for marker in (
            "지금",
            "현재",
            "열려 있는",
            "접속 중",
            "활성 세션",
            "current",
            "currently",
            "active session",
            "signed in now",
            "open session",
        )
    )
    rejects_history = any(
        marker in goal
        for marker in (
            "과거 기록 말고",
            "기록이 아니라",
            "이력 말고",
            "not history",
            "rather than history",
            "not past",
        )
    )
    wants_history = any(
        marker in goal
        for marker in (
            "지난달",
            "지난 접속",
            "과거 접속",
            "예전 접속",
            "시간순",
            "historical",
            "past login",
            "previous login",
            "login history",
        )
    )
    current_label = any(
        marker in candidate
        for marker in (
            "현재",
            "열린",
            "접속 중",
            "활성",
            "current",
            "active",
            "signed in",
            "open session",
        )
    )
    history_label = any(
        marker in candidate
        for marker in (
            "기록",
            "이력",
            "과거",
            "history",
            "past",
            "previous",
        )
    )
    if wants_history and not rejects_history and history_label:
        return 0.46
    if wants_history and not rejects_history and current_label:
        return -0.34
    if (wants_current or rejects_history) and current_label:
        return 0.34
    if (wants_current or rejects_history) and history_label:
        return -0.46
    return 0.0


def _goal_candidate_navigation_surface_alignment(
    goal_text: str,
    label: str,
    *,
    role: str,
    selected: bool,
) -> float:
    """Prefer an explicitly requested drawer over tabs and overflow menus."""

    goal = _plain_phrase(goal_text)
    candidate = _plain_phrase(label)
    wants_drawer = any(
        marker in goal
        for marker in (
            "왼쪽에서",
            "왼쪽 메뉴",
            "측면 메뉴",
            "펼쳐지는 목록",
            "사이드 메뉴",
            "navigation drawer",
            "side drawer",
            "side menu",
            "hamburger menu",
        )
    )
    if wants_drawer:
        if any(
            marker in candidate
            for marker in (
                "메뉴 열기",
                "측면 메뉴",
                "사이드 메뉴",
                "navigation drawer",
                "open menu",
                "hamburger",
            )
        ):
            return 0.48
        if selected or role.lower() == "tab" or any(
            marker in candidate
            for marker in (
                "더보기",
                "전체 메뉴",
                "overflow",
                "more options",
                "bottom tab",
            )
        ):
            return -0.42

    goal_tokens = set(goal.replace("/", " ").split())
    wants_personal_surface = bool(
        goal_tokens & {"my", "mine", "private", "personal", "saved", "collection"}
        or any(
            marker in goal
            for marker in (
                "내 정보",
                "내 계정",
                "내 주소",
                "내 장소",
                "개인 장소",
                "개인 설정",
                "저장한",
                "저장 목록",
                "내 컬렉션",
                "나의 ",
            )
        )
    )
    if wants_personal_surface:
        if candidate in {"you", "me", "mine", "my", "내 정보", "나", "마이"} or any(
            marker in candidate
            for marker in (
                "my account",
                "my profile",
                "my places",
                "personal",
                "private",
                "내 계정",
                "내 프로필",
                "내 장소",
            )
        ):
            return 0.52
        if candidate in {"contribute", "explore", "discover", "public", "공개", "탐색"}:
            return -0.34
    return 0.0


def _goal_candidate_named_entity_alignment(goal_text: str, label: str) -> float:
    """Reward an app/account/document name repeated verbatim in the goal.

    Function words such as "settings" can otherwise outrank the row for the
    exact app or document named by the user on a dense system list.  Long
    token containment is locale-agnostic and does not depend on a package or
    benchmark-specific label.
    """

    goal = _plain_phrase(goal_text)
    candidate = _plain_phrase(label)
    if not goal or not candidate:
        return 0.0
    compact_goal = "".join(character for character in goal if character.isalnum())
    compact_candidate = "".join(character for character in candidate if character.isalnum())
    if len(compact_candidate) >= 6 and compact_candidate in compact_goal:
        return 0.55
    ignored = {
        "settings",
        "account",
        "permission",
        "permissions",
        "menu",
        "service",
        "accessibility",
        "display",
        "overlay",
        "browser",
        "search",
        "files",
        "storage",
        "billing",
        "privacy",
        "access",
        "grant",
        "full",
        "claim",
        "document",
        "upload",
        "choose",
        "select",
        "continue",
        "email",
        "로그인",
        "설정",
        "계정",
        "권한",
        "메뉴",
        "알림",
        "정보",
        "기능",
        "검색",
    }
    # A strong bonus is reserved for identifier-like Latin tokens (mixed
    # case, digits, e-mail/domain syntax).  Plain words such as "offline" or
    # "login" are semantic vocabulary, not named entities.
    original_tokens = label.replace("·", " ").replace("/", " ").split()
    for original in original_tokens:
        compact_original = "".join(character for character in original if character.isalnum())
        identifier_like = bool(
            len(compact_original) >= 5
            and (
                any(character.isupper() for character in compact_original[1:])
                or any(character.isdigit() for character in compact_original)
                or "@" in original
                or "." in original
            )
        )
        if identifier_like and compact_original.lower() in compact_goal:
            return 1.0
    matches = 0
    for token in candidate.replace("·", " ").replace("/", " ").split():
        compact = "".join(character for character in token if character.isalnum())
        hangul_token = bool(compact) and all("가" <= character <= "힣" for character in compact)
        minimum_length = 2 if hangul_token else 4
        if len(compact) < minimum_length or compact in ignored:
            continue
        if compact in compact_goal:
            matches += 1
            if hangul_token and len(compact) >= 3:
                return 0.55
    return min(0.44, matches * 0.22)


def _goal_candidate_collection_item_alignment(
    request: UniversalNavigationObserveRequest,
    label: str,
) -> float:
    """Resolve a named row only on an explicit app/account/item picker."""

    title = _plain_phrase(request.screen.window_title)
    collection_surface = any(
        marker in title
        for marker in (
            "app notifications",
            "choose app",
            "select app",
            "all apps",
            "앱 알림",
            "앱 선택",
            "애플리케이션 선택",
            "choose account",
            "select account",
            "계정 선택",
            "choose document",
            "select document",
            "문서 선택",
        )
    )
    if not collection_surface:
        return 0.0
    goal_tokens = {
        "".join(character for character in token if character.isalnum())
        for token in _plain_phrase(request.goal_text).replace("/", " ").split()
    }
    candidate_tokens = {
        "".join(character for character in token if character.isalnum())
        for token in _plain_phrase(label).replace("/", " ").split()
    }
    ignored = {
        "app",
        "apps",
        "account",
        "document",
        "notification",
        "notifications",
        "앱",
        "계정",
        "문서",
        "알림",
    }
    if any(
        len(goal_token) >= 4
        and len(candidate_token) >= 4
        and candidate_token not in ignored
        and (
            goal_token.startswith(candidate_token)
            or candidate_token.startswith(goal_token)
        )
        for goal_token in goal_tokens
        for candidate_token in candidate_tokens
    ):
        return 0.55
    return 0.0


def _goal_candidate_recovery_alignment(goal_text: str, label: str) -> float:
    """Resolve common recovery-screen contrasts without app-specific routes."""

    goal = _plain_phrase(goal_text)
    candidate = _plain_phrase(label)
    score = 0.0

    wants_account_switch = bool(
        any(marker in goal for marker in ("계정 말고", "계정으로 전환", "다른 계정", "wrong account", "switch account", "different account"))
        or (
            any(marker in goal for marker in ("지금 열린 계정", "현재 계정", "this account"))
            and any(marker in goal for marker in ("말고", "아닌", "not", "instead"))
        )
    )
    if wants_account_switch:
        if any(marker in candidate for marker in ("계정 전환", "다른 계정", "계정 바꾸", "switch account", "use another account", "different account")):
            score += 0.85
        if any(marker in candidate for marker in ("계정 삭제", "탈퇴", "delete account", "close account")):
            score -= 1.0
        wants_work_account = any(
            marker in goal
            for marker in (
                "회사 계정",
                "업무 계정",
                "조직 계정",
                "work account",
                "company account",
                "corporate account",
                "organization account",
            )
        )
        if wants_work_account:
            if any(marker in candidate for marker in ("업무", "회사", "조직", "work", "company", "corporate", "organization")):
                score += 0.80
            if any(marker in candidate for marker in ("개인 계정", "personal account")):
                score -= 0.80

    wants_sms = any(
        marker in goal
        for marker in (
            "문자 메시지",
            "문자로",
            "문자 인증",
            "문자 코드",
            "sms",
            "text message",
        )
    )
    if wants_sms:
        if any(marker in candidate for marker in ("문자", "sms", "text message")):
            score += 0.65
        if any(marker in candidate for marker in ("인증 앱", "authenticator", "email", "이메일")):
            score -= 0.65

    wants_login = bool(
        any(
            marker in goal
            for marker in (
                "로그인",
                "sign in",
                "signing in",
                "signed in",
                "log in",
                "logging in",
                "logged in",
            )
        )
        and not any(marker in goal for marker in ("회원가입", "계정 만들", "sign up", "create account"))
    )
    if wants_login:
        if candidate in {"로그인", "sign in", "log in", "continue sign in"}:
            score += 0.70
        if candidate in {"이메일", "비밀번호", "email", "password"}:
            score -= 0.45
        if any(marker in goal for marker in ("계속", "완료", "finish", "continue")):
            if any(marker in candidate for marker in ("계속", "continue as", "finish sign", "complete sign")):
                score += 0.70
            if any(marker in candidate for marker in ("계정 전환", "switch account", "use another account")):
                score -= 0.65

    wants_location = any(marker in goal for marker in ("위치", "location", "gps"))
    if wants_location:
        if any(marker in candidate for marker in ("위치", "location")):
            score += 0.65
        if any(marker in candidate for marker in ("카메라", "사진", "camera", "photo")):
            score -= 0.80
        wants_approximate = any(
            marker in goal
            for marker in ("대략적인 위치", "정확한 위치를 끄", "approximate location", "turn off precise", "not precise")
        )
        if wants_approximate:
            if any(marker in candidate for marker in ("정확한 위치", "precise location")):
                score += 0.90
            if any(marker in candidate for marker in ("허용 안 함", "deny", "don't allow", "do not allow")):
                score -= 0.85

    wants_default_app_change = bool(
        any(marker in goal for marker in ("기본 앱", "기본 브라우저", "default app", "default browser"))
        and any(marker in goal for marker in ("바꾸", "변경", "change", "switch"))
    )
    if wants_default_app_change and candidate in {"없음", "선택 안 함", "none", "no default"}:
        score -= 0.85

    wants_unknown_app_install = bool(
        any(marker in goal for marker in ("apk", "외부 앱", "알 수 없는 앱", "unknown app", "sideload"))
        and any(marker in goal for marker in ("설치", "install", "허용", "allow"))
    )
    if wants_unknown_app_install:
        if any(marker in candidate for marker in ("알 수 없는 앱 설치", "unknown app", "install unknown")):
            score += 0.85
        if any(marker in candidate for marker in ("사진", "동영상", "사용 추적", "photo", "video", "usage access")):
            score -= 0.70

    wants_cache_only = bool(
        any(marker in goal for marker in ("캐시", "임시 파일", "cache", "temporary files"))
        and not any(marker in goal for marker in ("데이터 삭제", "저장 데이터", "clear storage", "app data"))
    )
    if wants_cache_only:
        if any(marker in candidate for marker in ("캐시", "임시 파일", "cache", "temporary files")):
            score += 0.70
        if any(marker in candidate for marker in ("앱 데이터", "저장 데이터", "app data", "storage data")):
            score -= 0.55

    wants_live_support = any(marker in goal for marker in ("상담원", "상담 연결", "직원", "live agent", "support agent", "human agent"))
    if wants_live_support:
        if any(marker in candidate for marker in ("상담원", "상담 연결", "채팅", "contact", "agent", "live chat")):
            score += 0.65
        if any(marker in candidate for marker in ("자주 묻는", "faq", "도움말 문서", "help article")):
            score -= 0.75

    wants_upcoming = any(marker in goal for marker in ("다가오는", "예정", "오늘", "upcoming", "today", "next trip"))
    if wants_upcoming:
        if any(marker in candidate for marker in ("다가오는", "예정", "현재", "upcoming", "current", "live")):
            score += 0.55
        if any(marker in candidate for marker in ("지난", "과거", "past", "history", "previous")):
            score -= 0.55

    generic_booking_list = bool(
        any(marker in goal for marker in ("예약", "여행", "booking", "trip", "reservation"))
        and not any(marker in goal for marker in ("지난", "과거", "예전", "past", "history", "previous"))
    )
    if generic_booking_list:
        if any(marker in candidate for marker in ("다가오는", "예정", "upcoming", "current")):
            score += 0.35
        if any(marker in candidate for marker in ("지난", "과거", "past", "history", "previous")):
            score -= 0.35

    wants_conversation_search = bool(
        any(marker in goal for marker in ("대화", "채팅", "conversation", "chat"))
        and any(marker in goal for marker in ("검색", "찾", "search", "find", "mute", "알림 끄"))
    )
    if wants_conversation_search:
        if any(marker in candidate for marker in ("더보기", "옵션", "검색", "more", "options", "search")):
            score += 0.55
        if any(marker in candidate for marker in ("새 메시지", "메시지 입력", "보내기", "new message", "compose", "message input", "send")):
            score -= 0.75

    wants_login_activity = bool(
        any(marker in goal for marker in ("경고", "새 기기", "활동", "warning", "new device", "activity"))
        and any(
            marker in goal
            for marker in (
                "로그인",
                "접속",
                "보안",
                "login",
                "sign-in",
                "signed in",
                "security",
            )
        )
    )
    if wants_login_activity:
        if any(marker in candidate for marker in ("로그인 활동", "접속 활동", "login activity", "sign-in activity")):
            score += 0.80
        if any(marker in candidate for marker in ("2단계 인증", "two-factor", "2fa")):
            score -= 0.55

    wants_mute_conversation = bool(
        any(marker in goal for marker in ("대화", "채팅", "conversation", "chat"))
        and any(marker in goal for marker in ("알림 끄", "알림만", "음소거", "mute", "silence notifications"))
    )
    if wants_mute_conversation:
        if any(marker in candidate for marker in ("알림 끄", "음소거", "mute", "notifications off")):
            score += 0.85
        if any(marker in candidate for marker in ("검색", "search")):
            score -= 0.70

    wants_privacy_from_feed = bool(
        any(marker in goal for marker in ("개인정보", "프라이버시", "privacy"))
        and any(marker in goal for marker in ("타임라인", "피드", "timeline", "feed"))
    )
    if wants_privacy_from_feed:
        if any(marker in candidate for marker in ("내 프로필", "프로필", "my profile", "profile")):
            score += 0.75
        if candidate in {"홈", "home"}:
            score -= 0.70

    wants_dark = any(marker in goal for marker in ("어두운", "다크", "dark", "night theme"))
    if wants_dark:
        if any(marker in candidate for marker in ("어두운", "다크", "dark")):
            score += 0.55
        if any(marker in candidate for marker in ("시스템 설정 따르기", "system default", "follow system")):
            score -= 0.45

    wants_theme_change = bool(
        any(marker in goal for marker in ("테마", "화면", "색", "theme", "appearance", "color"))
        and any(marker in goal for marker in ("바꾸", "변경", "열", "change", "switch", "open"))
    )
    if wants_theme_change:
        if any(marker in candidate for marker in ("어두운 테마", "다크", "dark theme", "dark mode")):
            score += 0.42
        if any(marker in candidate for marker in ("시스템 설정 따르기", "system default", "follow system")):
            score -= 0.45

    wants_unrestricted_background = bool(
        any(marker in goal for marker in ("배터리", "백그라운드", "battery", "background"))
        and any(marker in goal for marker in ("꺼지지 않", "제한", "계속", "stay on", "unrestricted", "not stop"))
    )
    if wants_unrestricted_background:
        if any(marker in candidate for marker in ("제한 없음", "무제한", "unrestricted", "no restrictions")):
            score += 0.85
        if any(marker in candidate for marker in ("제한됨", "restricted")):
            score -= 0.65

    wants_existing_optional_state = bool(
        any(marker in goal for marker in ("선택", "마케팅", "optional", "marketing"))
        and any(marker in goal for marker in ("켜졌", "이미", "확인", "whether", "already", "enabled"))
    )
    if wants_existing_optional_state:
        if any(marker in candidate for marker in ("혜택", "마케팅", "광고", "benefit", "marketing", "advertising")):
            score += 0.40
        if any(marker in candidate for marker in ("모두", "전체", "all optional", "select all")):
            score -= 0.65

    wants_unavailable_biometric_setup = bool(
        any(marker in goal for marker in ("지문", "생체", "fingerprint", "biometric"))
        and any(marker in goal for marker in ("사용할 수 없", "안 돼", "unavailable", "cannot use"))
    )
    if wants_unavailable_biometric_setup:
        if any(marker in candidate for marker in ("기기 잠금", "화면 잠금", "device lock", "screen lock")):
            score += 0.75
        if any(marker in candidate for marker in ("지문으로 로그인", "fingerprint login")):
            score -= 0.45

    wants_external_management_source = bool(
        any(marker in goal for marker in ("결제처", "외부 결제", "어디에서 관리", "payment provider", "billing provider", "where it is managed"))
        or (
            any(marker in goal for marker in ("해지", "cancel"))
            and any(marker in goal for marker in ("회색", "비활성", "disabled"))
        )
    )
    if wants_external_management_source:
        if any(
            marker in candidate
            for marker in (
                "결제처",
                "관리 위치",
                "에서 관리",
                "외부에서 관리",
                "payment provider",
                "billing provider",
                "manage externally",
                "managed by",
                "manage in",
                "manage on",
                "manage with",
            )
        ):
            score += 0.80
        if any(marker in candidate for marker in ("premium", "월간", "annual", "plan")):
            score -= 0.45

    wants_return_to_app = bool(
        any(marker in goal for marker in ("앱으로 돌아", "앱에 돌아", "return to", "back to the app", "finish signing in to the app"))
    )
    if wants_return_to_app:
        if any(marker in candidate for marker in ("돌아가기", "앱으로", "return to", "back to")):
            score += 0.85
        if any(marker in candidate for marker in ("계정 관리", "manage corporate", "manage account")):
            score -= 0.65

    wants_browser_fallback = bool(
        any(marker in goal for marker in ("앱이 없", "설치하지 않", "do not have", "not installed", "browser option"))
    )
    if wants_browser_fallback:
        if any(marker in candidate for marker in ("예약번호", "booking reference", "browser")):
            score += 0.75
        if any(marker in candidate for marker in ("확정", "confirm check-in", "open app", "install app")):
            score -= 0.85

    wants_delete = any(
        marker in goal
        for marker in (
            "삭제",
            "탈퇴",
            "없애",
            "지우",
            "휴지통",
            "delete",
            "deactivate",
            "close account",
            "trash",
            "recycle bin",
        )
    )
    if wants_delete and not wants_account_switch:
        if any(
            marker in candidate
            for marker in (
                "삭제",
                "비활성화",
                "탈퇴",
                "휴지통",
                "delete",
                "deactivate",
                "trash",
                "recycle bin",
            )
        ):
            score += 0.65
        if any(marker in candidate for marker in ("다운로드", "기념 계정", "download", "memorial")):
            score -= 0.60

    wants_return_or_cancel = any(
        marker in goal
        for marker in (
            "반품",
            "교환",
            "주문 취소",
            "return item",
            "exchange",
            "cancel order",
        )
    )
    if wants_return_or_cancel:
        if any(marker in candidate for marker in ("반품", "교환", "취소", "return", "exchange", "cancel")):
            score += 0.70
        if any(marker in candidate for marker in ("주문·배송", "배송 조회", "orders and shipping", "track delivery")):
            score -= 0.55

    wants_order_aftercare = bool(
        any(marker in goal for marker in ("주문", "반품", "교환", "배송", "order", "return", "exchange"))
        and not any(marker in goal for marker in ("새 상품", "장바구니", "new product", "cart"))
    )
    if wants_order_aftercare:
        if candidate in {"마이", "내 정보", "내 쇼핑", "my", "profile", "account"}:
            score += 0.72
        if any(marker in candidate for marker in ("장바구니", "새 상품", "추천 상품", "cart", "new product", "recommended")):
            score -= 0.75

    wants_fresh_general_notifications = bool(
        any(marker in goal for marker in ("알림 설정", "notification settings"))
        and any(marker in goal for marker in ("현재", "다시 확인", "새로고침", "current", "refresh", "up to date"))
        and not any(marker in goal for marker in ("마케팅", "광고", "marketing", "advertising"))
    )
    if wants_fresh_general_notifications:
        if any(marker in candidate for marker in ("받을 소식", "알림 선택", "what to receive", "notification topics")):
            score += 1.0
        if any(marker in candidate for marker in ("마케팅", "광고", "marketing", "advertising")):
            score -= 0.55
        if any(marker in candidate for marker in ("조용한 시간", "방해 금지", "quiet hours", "do not disturb")):
            score -= 0.35

    wants_draft_review = bool(
        _goal_requests_review_boundary(goal_text)
        and any(marker in goal for marker in ("청구", "신청", "제출", "claim", "application", "submission"))
    )
    if wants_draft_review:
        if any(marker in candidate for marker in ("작성 중", "임시 저장", "초안", "draft", "in progress", "saved application")):
            score += 0.85
        if any(marker in candidate for marker in ("내역", "완료된", "history", "completed claims", "past claims")):
            score -= 0.65

    return score


def _title_describes_candidate(title: str, label: str) -> bool:
    normalized_title = "".join(character for character in _plain_phrase(title) if character.isalnum())
    normalized_label = "".join(character for character in _plain_phrase(label) if character.isalnum())
    if not normalized_title or not normalized_label:
        return False
    return bool(
        normalized_title == normalized_label
        or (
            min(len(normalized_title), len(normalized_label)) >= 5
            and (
                normalized_title in normalized_label
                or normalized_label in normalized_title
            )
        )
    )


def _looks_like_read_only_outcome_candidate(title: str, label: str) -> bool:
    """Recognize status/result copy that proves an action is unnecessary.

    Android and web recovery screens often replace a disabled action with a
    sentence such as "no temporary files", "already enabled", or "nothing to
    update".  Those sentences are destination evidence, not another doorway
    to click.  Requiring both a status-like surface and outcome-like copy keeps
    the rule conservative on ordinary menu lists.
    """

    screen = _plain_phrase(title)
    candidate = _plain_phrase(label)
    status_surface = any(
        marker in screen
        for marker in (
            "상태",
            "결과",
            "완료",
            "status",
            "result",
            "summary",
            "completed",
        )
    )
    outcome_copy = any(
        marker in candidate
        for marker in (
            "없습니다",
            "없음",
            "완료됨",
            "완료되었습니다",
            "유지됨",
            "이미 설정",
            "최신 상태",
            "사용할 수 없습니다",
            "nothing to",
            "no files",
            "none available",
            "already set",
            "already enabled",
            "up to date",
            "is complete",
            "completed successfully",
            "not available",
        )
    )
    return bool(status_surface and outcome_copy)


def _looks_like_content_discovery_surface(request: UniversalNavigationObserveRequest) -> bool:
    text = _plain_phrase(
        " ".join(
            filter(
                None,
                [request.screen.window_title]
                + [
                    element.text or element.content_description or ""
                    for element in request.screen.elements
                    if element.visible and not element.password
                ],
            )
        )
    )
    discovery_markers = (
        "추천",
        "특가",
        "타임세일",
        "피드",
        "타임라인",
        "다음 영상",
        "for you",
        "recommended",
        "special offer",
        "timeline",
        "next video",
    )
    repeated_labels: dict[str, int] = {}
    normalized_title = _plain_phrase(request.screen.window_title)
    for element in request.screen.elements:
        value = _plain_phrase(element.text or element.content_description or "")
        if value and value != normalized_title:
            repeated_labels[value] = repeated_labels.get(value, 0) + 1
    return bool(
        sum(marker in text for marker in discovery_markers) >= 2
        or any(count >= 2 for count in repeated_labels.values())
    )


def _looks_like_generic_navigation_surface(
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Recognize root/list surfaces whose rows open a more specific screen."""

    title = _plain_phrase(request.screen.window_title)
    if title in {
        "시작 화면",
        "기능 목록",
        "전체 기능",
        "홈",
        "메인",
        "메인 메뉴",
        "start screen",
        "feature list",
        "all features",
        "home",
        "main",
        "main menu",
    }:
        return True
    visible = [
        _plain_phrase(element.text or element.content_description or "")
        for element in request.screen.elements
        if element.visible and not element.password
    ]
    has_root_scaffolding = any(
        marker in visible
        for marker in (
            "현재 탭",
            "현재 선택됨",
            "currently selected",
            "recommended",
            "추천 항목",
        )
    )
    return bool(
        has_root_scaffolding
        and any(element.role.lower() in {"tab", "menuitem"} for element in request.screen.elements)
    )


def _looks_like_generic_surface_scaffolding(label: str) -> bool:
    value = _plain_phrase(label)
    return bool(
        value in {
            "닫기",
            "취소",
            "나중에",
            "현재 탭",
            "현재 선택됨",
            "close",
            "cancel",
            "not now",
            "currently selected",
        }
        or any(
            marker in value
            for marker in (
                "추천 항목",
                "비슷한 추천",
                "관련 도움말",
                "비슷한 도움말",
                "recommended",
                "similar suggestion",
                "related help",
                "similar help",
            )
        )
    )


def _looks_like_read_only_record_candidate(label: str) -> bool:
    """Separate history/detail navigation from similarly worded payment actions."""

    value = _plain_phrase(label)
    read_only = any(
        marker in value
        for marker in (
            "구매 내역",
            "주문 내역",
            "거래 내역",
            "이용 내역",
            "결제 기록",
            "구매 기록",
            "purchase record",
            "past purchases",
            "order history",
            "transaction history",
            "billing history",
            "receipt",
            "statement",
        )
    )
    changes_state = any(
        marker in value
        for marker in (
            "결제하기",
            "구매하기",
            "환불 신청",
            "주문 취소",
            "삭제",
            "제출",
            "pay now",
            "buy now",
            "request refund",
            "cancel order",
            "delete",
            "submit",
        )
    )
    return read_only and not changes_state


def _looks_like_feed_interaction_candidate(label: str) -> bool:
    value = _plain_phrase(label)
    return any(
        marker in value
        for marker in (
            "답글",
            "댓글 달기",
            "재게시",
            "리포스트",
            "마음에 들어요",
            "좋아요",
            "공유하기",
            "reply",
            "comment",
            "repost",
            "retweet",
            "like",
            "share post",
        )
    )


def _is_explicit_dismiss_candidate(label: str, goal_text: str) -> bool:
    value = _plain_phrase(label)
    goal = _plain_phrase(goal_text)
    dismiss_goal = any(
        marker in goal
        for marker in (
            "닫고",
            "닫아",
            "경고창 뒤",
            "광고창",
            "팝업",
            "dismiss",
            "close the",
            "behind the warning",
        )
    )
    if not dismiss_goal:
        return False
    destructive = any(marker in value for marker in ("계정", "탈퇴", "삭제", "서비스 종료", "close account"))
    return bool(
        not destructive
        and (
            value in {"닫기", "닫기 버튼", "close", "dismiss"}
            or any(
                marker in value
                for marker in (
                    "팝업 닫기",
                    "경고 닫기",
                    "창 닫기",
                    "close popup",
                    "close warning",
                    "dismiss dialog",
                )
            )
        )
    )


def _is_safe_transient_overlay_dismiss_label(label: str) -> bool:
    """Return True only for an unambiguous, non-destructive close affordance."""

    value = _plain_phrase(label)
    destructive = any(
        marker in value
        for marker in (
            "계정",
            "탈퇴",
            "삭제",
            "서비스 종료",
            "close account",
            "delete",
            "deactivate",
        )
    )
    if destructive:
        return False
    return bool(
        value in {"닫기", "닫기 버튼", "close", "dismiss", "×", "x"}
        or any(
            marker in value
            for marker in (
                "팝업 닫기",
                "광고 닫기",
                "경고 닫기",
                "창 닫기",
                "close popup",
                "close promotion",
                "close warning",
                "dismiss dialog",
            )
        )
    )


def _is_safe_retry_candidate(label: str, request: UniversalNavigationObserveRequest) -> bool:
    value = _plain_phrase(label)
    screen = _plain_phrase(
        " ".join(
            [request.screen.window_title]
            + [element.text or element.content_description or "" for element in request.screen.elements]
        )
    )
    retry = value in {
        "다시 시도",
        "새로고침",
        "재시도",
        "retry",
        "try again",
        "refresh",
        "reload",
    }
    recoverable = any(
        marker in screen
        for marker in (
            "오프라인",
            "연결 없음",
            "인터넷 연결",
            "오프라인 사본",
            "캐시된 사본",
            "예전 값",
            "오래된 값",
            "인터넷 연결 없음",
            "네트워크 연결 없음",
            "마지막 동기화",
            "stale",
            "offline",
            "cached copy",
            "out of date",
            "old value",
            "no connection",
            "not connected",
        )
    )
    return retry and recoverable


def _is_stale_or_offline_snapshot(request: UniversalNavigationObserveRequest) -> bool:
    text = _plain_phrase(
        " ".join(
            [request.screen.window_title]
            + [
                element.text or element.content_description or ""
                for element in request.screen.elements
                if element.visible and not element.password
            ]
        )
    )
    return any(
        marker in text
        for marker in (
            "오프라인 사본",
            "캐시된 사본",
            "마지막 동기화",
            "예전 값",
            "오래된 값",
            "offline copy",
            "cached copy",
            "last synced",
            "stale data",
            "out of date",
        )
    )


def _is_least_privilege_consent_candidate(label: str, goal_text: str) -> bool:
    value = _plain_phrase(label)
    goal = _plain_phrase(goal_text)
    if not any(marker in goal for marker in ("쿠키", "cookie", "동의창", "consent dialog")):
        return False
    return any(
        marker in value
        for marker in (
            "필수 쿠키만",
            "필요한 쿠키만",
            "essential cookies only",
            "necessary cookies only",
            "reject optional",
        )
    )


def _goal_or_screen_requests_below_fold(request: UniversalNavigationObserveRequest) -> bool:
    goal = _plain_phrase(request.goal_text)
    labels = _plain_phrase(
        " ".join(
            element.text or element.content_description or ""
            for element in request.screen.elements
            if element.visible
        )
    )
    explicit_below_fold = any(
        marker in goal
        for marker in (
            "아래쪽",
            "아래에",
            "숨은",
            "밑에",
            "below",
            "lower down",
            "hidden below",
            "under the",
        )
    ) or any(
        marker in labels
        for marker in (
            "아래에 더",
            "아래에 현재",
            "아래에 설치",
            "아래에 설정",
            "목록 아래에",
            "아래에 고객",
            "더 많은 항목",
            "more below",
            "below in the list",
            "below fold",
        )
    )
    if explicit_below_fold:
        return True
    has_scrollable = any(
        element.visible and element.enabled and element.scrollable
        for element in request.screen.elements
    )
    if not has_scrollable:
        return False
    # Real pages frequently insert a noun between the two cue words, e.g.
    # "More membership options below".  Treat the pair as one structural
    # below-fold hint instead of requiring an exact phrase.
    if (
        ("more" in labels and "below" in labels)
        or ("더" in labels and "아래" in labels)
        or any(
            marker in labels
            for marker in ("계속 읽기", "continue reading", "next page")
        )
    ):
        return True
    title = _plain_phrase(request.screen.window_title)
    if "page" in title and " of " in title:
        numbers = [int(token) for token in title.replace("/", " ").split() if token.isdigit()]
        if len(numbers) >= 2 and numbers[0] < numbers[1]:
            return True
    return False


def _screen_requires_user_handoff(
    request: UniversalNavigationObserveRequest,
    *,
    target_function: str,
    catalog: NavigationFunctionCatalog,
) -> bool:
    """Stop at non-navigational state, credential, permission, and action boundaries."""

    visible = [
        element
        for element in request.screen.elements
        if element.visible and not element.password
    ]
    text = _plain_phrase(
        " ".join(
            [request.screen.window_title]
            + [element.text or element.content_description or "" for element in visible]
        )
    )
    if any(element.role.lower() == "progressbar" for element in visible):
        return True
    if any(
        marker in text
        for marker in (
            "불러오는 중",
            "로딩 중",
            "점검 중",
            "잠시 후 다시 시도",
            "요청이 너무 많",
            "새 버전이 필요",
            "업데이트 후 이용",
            "사람임을 확인",
            "captcha",
            "loading",
            "maintenance",
            "too many requests",
            "rate limit",
            "update required",
            "verify you are human",
        )
    ):
        return True

    permission_prompt = any(
        marker in _plain_phrase(request.screen.window_title)
        for marker in (
            "사용하도록 허용",
            "권한 승인",
            "접근 허용",
            " 권한",
            "allow access",
            "permission request",
            " permission",
        )
    ) and any(element.checkable or "허용" in _plain_phrase(element.text or "") for element in visible)
    direct_permission_question = any(
        marker in _plain_phrase(request.screen.window_title)
        for marker in (
            "사용하도록 허용하시겠습니까",
            "접근을 허용하시겠습니까",
            "허용할까요",
            "allow this app",
            "allow access?",
            "permission request",
        )
    )
    if permission_prompt and (
        target_function != "android.permission.change"
        or direct_permission_question
    ):
        return True
    if (
        target_function.startswith("android.permission.")
        and target_function != "android.permission.change"
        and any(element.checkable for element in visible)
    ):
        return True

    target_definition = catalog.function(target_function)
    boundary_title = any(
        marker in _plain_phrase(request.screen.window_title)
        for marker in (
            "최종 확인",
            "영구 삭제",
            "삭제할까요",
            "혜택이 종료",
            "review ",
            "confirm ",
            "download file?",
        )
    )
    risky_action = any(
        any(
            marker in _plain_phrase(element.text or element.content_description or "")
            for marker in (
                "영구 삭제",
                "삭제 확정",
                "해지 확정",
                "접수",
                "제출",
                "결제",
                "송금",
                "send money",
                "submit",
                "pay now",
                "confirm download",
                "download",
            )
        )
        for element in visible
    )
    if boundary_title and risky_action:
        return True

    title_value = _plain_phrase(request.screen.window_title)
    terminal_action_tokens = {
        token
        for token in _function_identifier_tokens(target_function)
        if token in USER_OWNED_ACTION_FUNCTION_TOKENS
    }
    if (
        target_definition is not None
        and target_definition.state_changing
        and (
            catalog.terminal_screen_score(
                target_function,
                request.screen.window_title,
            )
            >= 0.65
            or any(token in title_value for token in terminal_action_tokens)
        )
        and request.transition is not None
        and sum(
            element.visible and element.enabled and element.clickable
            for element in visible
        )
        >= 1
    ):
        # Once a state-changing workflow's own surface is open, every
        # remaining choice belongs to the user.  This covers pickers such as
        # Create -> Event/Task as well as toggle/configuration boundaries,
        # without blocking the reversible doorway on the parent screen.
        return True

    destructive_goal = any(
        marker in _plain_phrase(request.goal_text)
        for marker in (
            "삭제",
            "지우",
            "탈퇴",
            "영구",
            "delete",
            "deactivate",
            "trash",
            "discard",
            "remove permanently",
        )
    )
    unnamed_action = any(
        element.clickable
        and element.enabled
        and not _plain_phrase(element.text or element.content_description or "")
        for element in visible
    )
    destructive_boundary_context = bool(
        request.transition is not None
        and target_definition is not None
        and catalog.terminal_screen_score(
            target_function,
            request.screen.window_title,
        )
        >= 0.55
    )
    if destructive_goal and unnamed_action and destructive_boundary_context:
        # An unlabeled clickable icon is common on ordinary app home screens
        # (toolbar, carousel, floating action, and bottom-navigation controls).
        # It is not by itself evidence that a destructive user-owned boundary
        # has been reached.  Only apply this safety handoff after navigation
        # has entered a screen whose title identifies the destructive target.
        return True

    # A disabled target control means there is no safe automated action.  The
    # user should see the state explanation instead of the explorer clicking a
    # nearby storage/help/settings row.
    target_tokens = set(target_function.replace("_", ".").split("."))
    target_concepts = (
        frozenset()
        if target_definition is None
        else frozenset(target_definition.semantic_concepts)
    )
    disabled_target = any(
        not element.enabled
        and (
            any(
                token in _plain_phrase(element.text or element.content_description or "").replace(" ", "_")
                for token in target_tokens
                if len(token) >= 4
            )
            or bool(
                target_concepts
                & catalog.semantic_concepts_for_text(
                    element.text or element.content_description or ""
                )
            )
            or any(
                match.function_id == target_function and match.score >= 0.34
                for match in catalog.match_candidate(
                    label=element.text or element.content_description or "",
                    role=element.role,
                    enabled=False,
                    limit=16,
                )
            )
        )
        for element in visible
    )
    if disabled_target and any(
        element.enabled
        and element.clickable
        and _goal_candidate_recovery_alignment(
            request.goal_text,
            element.text or element.content_description or "",
        )
        >= 0.50
        and _looks_like_recovery_alternative_action(
            element.text or element.content_description or ""
        )
        for element in visible
    ):
        return False
    if (
        disabled_target
        and target_function.endswith(".entry")
        and (
            _screen_has_credential_fields(request)
            or (
                target_function == "auth.signup.entry"
                and (
                    any(
                        marker in _plain_phrase(request.screen.window_title)
                        for marker in (
                            "계정 만들기",
                            "회원가입",
                            "가입 양식",
                            "create account",
                            "sign up",
                            "registration",
                        )
                    )
                    or (
                        "create" in _plain_phrase(request.screen.window_title)
                        and "account" in _plain_phrase(request.screen.window_title)
                    )
                )
            )
        )
    ):
        # A disabled submit button on a credential form proves that the entry
        # form has been reached.  Let terminal detection point at the first
        # required field instead of returning a label-less generic handoff.
        return False
    return disabled_target


def _looks_like_recovery_alternative_action(label: str) -> bool:
    value = _plain_phrase(label)
    return any(
        marker in value
        for marker in (
            "필요",
            "등록",
            "설정",
            "결제처",
            "관리 위치",
            "다시 시도",
            "열기",
            "setup",
            "set up",
            "register",
            "settings",
            "provider",
            "manage externally",
            "try again",
            "open",
        )
    )


def _looks_like_combined_auth_gateway(label: str) -> bool:
    normalized = " ".join(label.lower().split())
    has_login = any(token in normalized for token in ("로그인", "sign in", "log in", "login"))
    has_signup = any(
        token in normalized
        for token in ("회원가입", "가입", "sign up", "register", "create account")
    )
    return has_login and has_signup


def _looks_like_signup_gateway(
    candidate: UniversalNavigationCandidate,
    request: UniversalNavigationObserveRequest,
    catalog: NavigationFunctionCatalog,
) -> bool:
    """Recognize unified or onboarding-style sign-up entry screens.

    Some apps do not expose a literal ``회원가입`` button. Netflix, for
    example, presents ``시작하기`` beside a separate login action, while its
    unified authentication form asks for an email/phone number and explains
    that new users will start a new account. Both are valid final entry points
    for a sign-up navigation goal, but neither should be auto-submitted.
    """

    label = _plain_phrase(candidate.label)
    screen_text = _plain_phrase(
        " ".join(
            filter(
                None,
                [request.screen.window_title]
                + [
                    element.text or element.content_description or ""
                    for element in request.screen.elements
                    if element.visible and not element.password
                ],
            )
        )
    )
    login_visible = any(
        token in screen_text
        for token in ("로그인", "sign in", "log in", "login")
    )
    literal_signup = label in {
        "회원가입",
        "가입하기",
        "계정 만들기",
        "sign up",
        "register",
        "create account",
    }
    if literal_signup and not _looks_like_combined_auth_gateway(candidate.label):
        return True
    start_label = label in {
        "시작하기",
        "서비스 시작",
        "처음 시작",
        "get started",
        "start",
        "begin",
    }
    if start_label and login_visible:
        # A dedicated Start/Get started control next to a separate Login is
        # the common landing-page split between new and existing users.  The
        # relation is stronger evidence than a catalog alias score and stays
        # valid when accessibility inserts zero-width characters.
        return True

    signup_context = any(
        token in screen_text
        for token in (
            "새 계정",
            "신규 계정",
            "계정으로 시작",
            "회원가입",
            "가입하세요",
            "new account",
            "create account",
            "sign up",
            "join now",
        )
    ) or (
        ("create" in screen_text and "account" in screen_text)
        or ("sign" in screen_text and "up" in screen_text)
        or (
            "계정" in screen_text
            and any(marker in screen_text for marker in ("만들", "생성", "가입"))
        )
    )
    input_role = candidate.role.lower() in {"input", "edittext", "textfield", "text_field"}
    contact_field = any(
        token in label
        for token in (
            "이메일",
            "휴대폰",
            "전화번호",
            "email",
            "phone",
            "mobile",
        )
    )
    disabled_submit = any(
        element.visible
        and not element.enabled
        and any(
            marker in _plain_phrase(element.text or element.content_description or "")
            for marker in (
                "가입",
                "계정 만들기",
                "등록 완료",
                "create account",
                "sign up",
                "register",
            )
        )
        for element in request.screen.elements
    )
    return signup_context and contact_field and (input_role or disabled_submit)


def _screen_has_credential_fields(request: UniversalNavigationObserveRequest) -> bool:
    return any(
        element.visible
        and (
            element.password
            or element.role.lower() in {"input", "edittext", "textfield", "text_field"}
        )
        for element in request.screen.elements
    )


def _looks_like_subscription_offer(label: str) -> bool:
    normalized = " ".join(label.lower().split())
    if any(token in normalized for token in ("해지", "취소", "cancel", "deactivate", "stop renewal")):
        return False
    if normalized in {
        "premium",
        "프리미엄",
        "premium membership",
        "프리미엄 멤버십",
        "premium benefits",
        "premium 혜택",
        "프리미엄 혜택",
        "buy premium",
        "premium offer",
    }:
        return True
    if (
        len(normalized.split()) <= 3
        and (normalized.endswith(" premium") or normalized.endswith(" 프리미엄"))
    ):
        return True
    return any(
        token in normalized
        for token in (
            "+",
            "패키지",
            "12개월",
            "tving",
            "신규 가입",
            "새 멤버십",
            "새 구독",
            "가입 혜택",
            "가장 저렴한 가격",
            "변경",
            "new membership",
            "new subscription",
            "join membership",
        )
    )


def _looks_like_content_subscription_tab(
    label: str,
    request: UniversalNavigationObserveRequest,
) -> bool:
    value = _plain_phrase(label)
    if value not in {"구독", "팔로잉", "subscriptions", "following"}:
        return False
    screen = _plain_phrase(request.screen.window_title)
    sibling_text = _plain_phrase(
        " ".join(
            element.text or element.content_description or ""
            for element in request.screen.elements
            if element.visible
        )
    )
    return any(
        marker in f"{screen} {sibling_text}"
        for marker in (
            "홈",
            "피드",
            "채널",
            "영상",
            "home",
            "feed",
            "channel",
            "video",
        )
    )


def _goal_requests_paid_subscription_management(goal_text: str) -> bool:
    """Return whether ``subscription`` means a paid service, not a feed.

    Korean apps commonly use the same word (``구독``) for a recurring paid
    plan and for following a creator.  Explicit billing/product language and
    well-known paid service names let the explorer keep those domains apart
    before fuzzy catalog or LLM ranking can collapse them again.
    """

    goal = _plain_phrase(goal_text)
    return any(
        marker in goal
        for marker in (
            "프리미엄",
            "유료 구독",
            "유료 멤버십",
            "자동 결제",
            "자동결제",
            "정기 결제",
            "정기결제",
            "결제 해지",
            "넷플릭스",
            "배민클럽",
            "쿠팡 와우",
            "쿠팡와우",
            "티빙",
            "웨이브",
            "디즈니 플러스",
            "디즈니+",
            "premium",
            "paid subscription",
            "paid membership",
            "recurring payment",
            "auto renew",
            "netflix",
            "baemin club",
            "coupang wow",
            "tving",
            "wavve",
            "disney plus",
            "disney+",
        )
    )


def _looks_like_management_goal_media_detour(
    label: str,
    *,
    request: UniversalNavigationObserveRequest,
    target_function: str,
) -> bool:
    """Reject playable/feed content while searching for app management UI."""

    management_target = bool(
        target_function.endswith(".settings")
        or target_function.startswith(
            (
                "account.",
                "auth.",
                "billing.",
                "marketing.",
                "notification.",
                "privacy.",
                "subscription.",
            )
        )
    )
    if not management_target:
        return False

    value = _plain_phrase(label)
    if not value:
        return False

    if request.app_package == "com.google.android.youtube":
        # Explicit account/settings gateways remain valid even when their
        # surrounding screen also contains video metadata.
        if any(
            marker in value
            for marker in (
                "내 페이지",
                "설정",
                "계정",
                "구매 항목 및 멤버십",
                "알림",
                "my page",
                "you tab",
                "settings",
                "account",
                "purchases and memberships",
                "notifications",
            )
        ):
            return False
        return bool(
            _looks_like_creator_audience_metric(value)
            or any(
                marker in value
                for marker in (
                    "조회수",
                    "동영상 재생",
                    "채널로 이동",
                    "시청 중",
                    "구독자",
                    "좋아요",
                    "댓글",
                    " views",
                    "play video",
                    "video playback",
                    "go to channel",
                    "subscribers",
                )
            )
        )

    if request.app_package == "com.netflix.mediaclient":
        # Netflix's browse surface is mostly playable catalog cards. Only
        # explicit account/menu gateways can advance a management goal.
        if any(
            marker in value
            for marker in (
                "나의 넷플릭스",
                "계정",
                "설정",
                "프로필 관리",
                "프로필을 변경 또는 관리",
                "메뉴",
                "더 보기",
                "my netflix",
                "account",
                "settings",
                "manage profiles",
                "menu",
                "more",
            )
        ):
            return False
        return any(
            marker in value
            for marker in (
                "재생",
                "회차",
                "에피소드",
                "시리즈",
                "영화",
                "게임",
                "찜",
                "play",
                "episode",
                "series",
                "movie",
                "game",
                "my list",
            )
        )

    return False


def _looks_like_paid_subscription_content_detour(
    label: str,
    *,
    request: UniversalNavigationObserveRequest,
    target_function: str,
) -> bool:
    """Block creator/video navigation for management and paid-plan goals."""

    if _looks_like_management_goal_media_detour(
        label,
        request=request,
        target_function=target_function,
    ):
        return True

    if (
        target_function != "subscription.cancel.entry"
        or not _goal_requests_paid_subscription_management(request.goal_text)
    ):
        return False
    value = _plain_phrase(label)
    paid_plan_identity = any(
        marker in value
        for marker in (
            "프리미엄",
            "멤버십 관리",
            "구독 관리",
            "구매 항목 및 멤버십",
            "결제 및 구독",
            "결제 수단",
            "자동 결제",
            "자동결제",
            "정기 결제",
            "정기결제",
            "배민클럽",
            "넷플릭스",
            "premium",
            "manage membership",
            "manage subscription",
            "purchases and memberships",
            "payments and subscriptions",
            "recurring payment",
        )
    )
    if paid_plan_identity:
        return False
    if request.app_package == "com.netflix.mediaclient":
        # Netflix home is almost entirely a content/game graph.  For paid-plan
        # management the only useful first hop is the account surface; broad
        # named-entity similarity must not turn a title or ``See all`` card
        # into a generic menu.
        profile_management_gateway = bool(
            ("프로필" in value and any(marker in value for marker in ("관리", "변경")))
            or (
                "profile" in value
                and any(marker in value for marker in ("manage", "change", "switch"))
            )
        )
        if profile_management_gateway or _has_explicit_cancellation_cue(value) or any(
            marker in value
            for marker in (
                "나의 넷플릭스",
                "계정",
                "설정",
                "프로필 관리",
                "메뉴",
                "더 보기",
                "my netflix",
                "account",
                "settings",
                "manage profiles",
                "menu",
                "more",
            )
        ):
            return False
        return True
    if any(
        marker in value
        for marker in (
            "조회수",
            "동영상 재생",
            "채널로 이동",
            "구독자",
            "팔로워",
            "좋아요",
            "댓글",
            "공유하기",
            "시청 중",
            "video playback",
            "play video",
            "go to channel",
            "subscriber count",
            "subscribers",
            "follower count",
            "followers",
            " views",
        )
    ):
        return True
    if value in {"구독", "구독중", "구독 중", "subscriptions", "subscribed"}:
        # With no product/billing identity this label is ambiguous.  It is the
        # common creator-following control on YouTube and social apps; a real
        # paid plan card carries product, membership, price, or billing text
        # and was already accepted above.
        return True
    channel_unsubscribe = any(
        marker in value
        for marker in (
            "채널 구독 취소",
            "구독 취소합니다",
            "구독을 취소합니다",
            "unsubscribe from channel",
            "unsubscribe from",
        )
    )
    if not channel_unsubscribe:
        return False
    screen_evidence = _plain_phrase(
        " ".join(
            filter(
                None,
                [
                    request.screen.window_title,
                    request.screen.activity_name,
                    *(
                        element.text or element.content_description or ""
                        for element in request.screen.elements
                        if element.visible and not element.password
                    ),
                ],
            )
        )
    )
    return any(
        marker in screen_evidence
        for marker in (
            "채널",
            "구독자",
            "조회수",
            "동영상",
            "channel",
            "subscriber",
            "views",
            "video",
        )
    )


def _looks_like_creator_audience_metric(label: str) -> bool:
    """Separate creator/social audience metrics from paid subscriptions."""

    normalized = _plain_phrase(label)
    if _has_explicit_cancellation_cue(normalized):
        # A real destination may mention its audience (for example,
        # "구독자 전용 멤버십 해지").  The explicit user-owned action wins.
        return False
    if any(
        marker in normalized
        for marker in (
            "구독자 전용 멤버십",
            "구독자 멤버십 관리",
            "subscriber-only membership",
            "subscriber membership management",
            "manage subscriber membership",
        )
    ):
        # These labels describe a paid-plan control rather than a creator's
        # audience size.  They remain eligible as reversible management
        # gateways; the final state-changing action is still user-owned.
        return False
    if any(
        marker in normalized
        for marker in (
            "구독자",
            "팔로워",
            "subscriber count",
            "subscribers",
            "follower count",
            "followers",
        )
    ):
        return True
    has_count = any(character.isdigit() for character in normalized) or any(
        marker in normalized
        for marker in (" 명", "천명", "만명", " k", " m", "count")
    )
    return bool(
        has_count
        and any(
            marker in normalized
            for marker in (
                "팔로잉",
                "following",
                "fans",
                "팬 수",
            )
        )
    )


def _repeats_immediately_backtracked_branch(
    *,
    candidate: UniversalNavigationCandidate,
    function_ids: tuple[str, ...],
    branch: dict[str, object] | None,
) -> bool:
    """Reject the just-failed branch across OCR-only fingerprint changes."""

    if branch is None:
        return False
    branch_element_key = str(branch.get("element_key", ""))
    if branch_element_key and candidate.element_key == branch_element_key:
        return True
    if not function_ids:
        return False
    if _plain_phrase(candidate.label) != _plain_phrase(str(branch.get("label", ""))):
        return False
    branch_function_ids = tuple(
        sorted(
            str(value)
            for value in branch.get("function_ids", ())
            if value
        )
    )
    return bool(branch_function_ids and tuple(sorted(set(function_ids))) == branch_function_ids)


def _is_active_or_just_entered_navigation_tab(
    *,
    candidate: UniversalNavigationCandidate,
    element,
    state: ExplorationState,
) -> bool:
    """Reject a no-op repeat click on the current navigation tab.

    Some accessibility trees do not expose ``selected=True`` for custom bottom
    bars.  The stable semantic element key and the completed transition into
    the current screen provide an equivalent signal: if that same tab was the
    action that just produced this screen, pressing it again cannot advance
    the goal.
    """

    if element is None:
        return False
    known_navigation_tab = _plain_phrase(candidate.label) in {
        "홈",
        "home",
        "shorts",
        "구독",
        "subscriptions",
        "내 페이지",
        "my page",
        "마이",
        "you",
    }
    if not _looks_like_navigation_tab(candidate.label, element) and not known_navigation_tab:
        return False
    if bool(element.selected):
        return True
    entry_step = next(
        (
            step
            for step in reversed(state.path)
            if step.get("kind") != "scroll"
            and not bool(step.get("pending"))
            and str(step.get("expected_to_screen_fingerprint") or "")
            == state.current_screen_fingerprint
        ),
        None,
    )
    if entry_step is None:
        return False
    same_stable_element = bool(
        candidate.element_key
        and candidate.element_key == str(entry_step.get("element_key") or "")
    )
    same_semantic_tab = bool(
        _plain_phrase(candidate.label)
        and _plain_phrase(candidate.label)
        == _plain_phrase(str(entry_step.get("label") or ""))
    )
    return bool(same_stable_element or same_semantic_tab)


def _looks_like_navigation_tab(label: str, element) -> bool:
    """Identify tab controls from role, accessibility wording, or resource ID."""

    role = str(element.role).lower()
    if role in {
        "bottomnavigationitem",
        "navigationitem",
        "tab",
        "tabitem",
    }:
        return True
    value = _plain_phrase(label)
    resource = str(element.view_id or "").lower()
    return bool(
        any(
            marker in value
            for marker in (
                "하단탭바",
                "하단 탭바",
                "하단 탭",
                "하단 메뉴",
                "bottom navigation",
                "bottom nav",
                "bottom tab",
                "navigation tab",
                "tab bar",
            )
        )
        or any(
            marker in resource
            for marker in (
                "bottom_navigation",
                "bottomnavigation",
                "bottom_nav",
                "bottom_tab",
                "navigation_bar",
                "pivot_bar",
                "tab_bar",
                "tabs_bar",
            )
        )
    )


def _has_explicit_cancellation_cue(label: str) -> bool:
    normalized = " ".join(label.lower().split())
    return any(
        token in normalized
        for token in (
            "해지",
            "취소",
            "종료",
            "중지",
            "자동 결제 해제",
            "자동결제 해제",
            "갱신 중지",
            "cancel",
            "deactivate",
            "terminate",
            "stop renewal",
            "turn off auto-renew",
        )
    )


def _looks_like_cancellation_information_or_unrelated_action(label: str) -> bool:
    """Reject cancellation wording that does not identify subscription exit.

    Short words such as ``Cancel`` and ``End`` are common in dialogs, media
    playback, fee notices, and policy links.  They may share a surface with a
    paid plan but must not become the cancellation destination by keyword
    inheritance alone.
    """

    normalized = _plain_phrase(label)
    return any(
        marker in normalized
        for marker in (
            "취소 수수료",
            "해지 수수료",
            "취소 정책",
            "해지 정책",
            "취소 규정",
            "해지 규정",
            "취소 안내",
            "해지 안내",
            "취소 방법",
            "해지 방법",
            "환불 규정",
            "환불 정책",
            "재생 종료",
            "동영상 종료",
            "라이브 종료",
            "스트리밍 중지",
            "전송 중지",
            "종료일",
            "해지 예정일",
            "cancellation fee",
            "cancellation policy",
            "cancellation terms",
            "cancellation guide",
            "cancel fee",
            "refund policy",
            "how to cancel",
            "stop playback",
            "end playback",
            "end video",
            "end live",
            "stop streaming",
            "stop casting",
            "termination date",
            "cancellation date",
        )
    )


def _has_descriptive_subscription_cancellation_cue(label: str) -> bool:
    """Return whether the control names both subscription identity and exit."""

    normalized = _plain_phrase(label)
    if (
        not _has_explicit_cancellation_cue(label)
        or _looks_like_cancellation_information_or_unrelated_action(label)
    ):
        return False
    return any(
        marker in normalized
        for marker in (
            "구독",
            "멤버십",
            "이용권",
            "정기 결제",
            "정기결제",
            "자동 결제",
            "자동결제",
            "자동 갱신",
            "자동갱신",
            "갱신 중지",
            "subscription",
            "membership",
            "recurring plan",
            "recurring payment",
            "auto-renew",
            "auto renew",
            "renewal",
        )
    )


def _is_supported_subscription_cancel_destination(
    label: str,
    *,
    request: UniversalNavigationObserveRequest,
    state: ExplorationState,
) -> bool:
    """Require plan evidence for ambiguous short cancellation controls."""

    if (
        not _has_explicit_cancellation_cue(label)
        or _looks_like_cancellation_information_or_unrelated_action(label)
    ):
        return False
    if _has_descriptive_subscription_cancellation_cue(label):
        return True
    return bool(
        _path_has_subscription_plan_detail(state)
        or _path_has_subscription_specific_progress(state)
        or _screen_has_subscription_plan_evidence(
            request,
            excluding_label=label,
        )
    )


def _is_reviewed_external_subscription_management_handoff(
    label: str,
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Recognize only reviewed provider handoffs from a plan-specific page."""

    normalized = _plain_phrase(label)
    exact_handoff = normalized in {
        "google play에서 관리",
        "play에서 관리",
        "google play로 이동",
        "manage in google play",
        "manage on google play",
        "open in google play",
    }
    compact = "".join(character for character in normalized if character.isalnum())
    google_index = compact.find("google")
    play_index = compact.find("p", google_index + len("google")) if google_index >= 0 else -1
    ay_index = compact.find("ay", play_index + 2, play_index + 6) if play_index >= 0 else -1
    provider_offset = (
        play_index - (google_index + len("google"))
        if google_index >= 0 and play_index >= 0
        else -1
    )
    play_middle_width = ay_index - play_index - 1 if ay_index >= 0 else -1
    ocr_google_play = bool(
        google_index >= 0
        and play_index >= 0
        and ay_index >= 0
        and provider_offset in {0, 1}
        and play_middle_width in {1, 2}
        and any(marker in normalized for marker in ("관리", "manage", "이동", "open"))
    )
    if not exact_handoff and not ocr_google_play:
        return False
    if _screen_has_subscription_plan_evidence(
        request,
        excluding_label=label,
    ):
        return True
    surface = _plain_phrase(
        " ".join(
            filter(
                None,
                [request.screen.window_title]
                + [
                    element.text or element.content_description or ""
                    for element in request.screen.elements
                    if element.visible
                    and not element.password
                    and (not element.clickable or not element.enabled)
                ],
            )
        )
    )
    return any(
        marker in surface
        for marker in (
            "구독",
            "멤버십",
            "이용권",
            "정기 결제",
            "subscription",
            "membership",
            "premium",
            "recurring plan",
        )
    )


def _path_has_subscription_plan_detail(state: ExplorationState) -> bool:
    """Require a paid-plan branch before interpreting a short Cancel label."""

    plan_markers = (
        "프리미엄",
        "premium",
        "개인 멤버십",
        "유료 멤버십",
        "구독 플랜",
        "멤버십 플랜",
        "paid membership",
        "subscription plan",
        "membership plan",
    )
    for step in reversed(state.path):
        if step.get("kind") == "scroll" or bool(step.get("pending")):
            continue
        function_ids = {
            str(value)
            for value in step.get("function_ids", [])
            if value
        }
        if "subscription.detail" in function_ids:
            return True
        label = _plain_phrase(str(step.get("label", "")))
        if any(marker in label for marker in plan_markers):
            return True
    return False


def _screen_has_subscription_plan_evidence(
    request: UniversalNavigationObserveRequest,
    *,
    excluding_label: str = "",
) -> bool:
    """Confirm that the current surface describes a paid recurring plan."""

    excluded = _plain_phrase(excluding_label)
    labels = [request.screen.window_title]
    labels.extend(
        element.text or element.content_description or ""
        for element in request.screen.elements
        if element.visible
        and not element.password
        and _plain_phrase(element.text or element.content_description or "") != excluded
    )
    surface = _plain_phrase(" ".join(labels))
    plan_identity = any(
        marker in surface
        for marker in (
            "프리미엄",
            "premium",
            "개인 멤버십",
            "유료 멤버십",
            "구독 플랜",
            "멤버십 플랜",
            "paid membership",
            "subscription plan",
            "membership plan",
        )
    )
    recurring_state = any(
        marker in surface
        for marker in (
            "다음 결제일",
            "/월",
            "매월",
            "월간",
            "/month",
            "monthly",
            "next billing",
            "next payment",
            "recurring",
            "자동 갱신",
        )
    )
    management_control = any(
        marker in surface
        for marker in (
            "에서 관리",
            "manage in google",
            "manage on google",
        )
    )
    return bool(plan_identity and (recurring_state or management_control))


def _target_requires_specific_terminal_identity(target_definition) -> bool:
    if target_definition is None:
        return False
    return bool(
        target_definition.terminal
        or target_definition.node_kind in {
            "action_entry",
            "destination",
            "state_change",
        }
    )


def _selected_generic_navigation_identity(
    *,
    candidate: UniversalNavigationCandidate,
    element,
    function_ids: tuple[str, ...],
) -> bool:
    """Keep selected global/account/content tabs out of terminal synthesis."""

    if element is None or not element.selected:
        return False
    role = str(element.role).lower()
    if role in {
        "bottomnavigationitem",
        "menuitem",
        "navigationitem",
        "tab",
    }:
        return True
    if any(
        function_id.startswith(("account.", "content.", "navigation."))
        or function_id in {"account_entry", "subscription.list"}
        for function_id in function_ids
    ):
        return True
    return _plain_phrase(candidate.label) in {
        "+",
        "shorts",
        "구독",
        "내 페이지",
        "나",
        "마이페이지",
        "재생목록",
        "홈",
        "home",
        "library",
        "my page",
        "playlists",
        "subscriptions",
        "you",
    }


def _goal_targets_settings_surface(target_function: str, goal_text: str) -> bool:
    """Return whether the requested destination is a preferences surface."""

    goal = _plain_phrase(goal_text)
    return bool(
        target_function == "settings.root"
        or target_function.startswith("settings.")
        or target_function.endswith((".settings", "_settings"))
        or any(
            marker in goal
            for marker in (
                "설정",
                "환경설정",
                "settings",
                "preferences",
            )
        )
    )


def _target_is_notification_preferences(target_function: str) -> bool:
    """Separate notification preferences from an activity/inbox destination."""

    return bool(
        target_function in {
            "notification.settings",
            "notification.email",
            "notification.sms",
            "notification.quiet_hours",
            "android.app.notifications",
            "android.notification.channels",
            "marketing.settings",
        }
        or target_function.endswith("notification_settings")
    )


def _looks_like_notification_preferences_detour(
    label: str,
    *,
    target_function: str,
) -> bool:
    """Reject account-page commerce branches for in-app notification goals.

    Dense account pages commonly place an active membership card, wallet, and
    payment-method management next to the settings control.  Those controls
    can also receive a broad ``account.entry`` match, but that does not make
    them progress toward notification preferences.  A label that explicitly
    mentions notifications is retained because rows such as ``구독 알림`` or
    ``결제 알림`` can be genuine notification categories.

    The guard deliberately applies only to the in-app canonical destination;
    Android/system notification routes retain their separate planner policy.
    """

    if target_function != "notification.settings":
        return False
    value = _plain_phrase(label)
    if any(
        marker in value
        for marker in (
            "알림",
            "수신",
            "notification",
            "notifications",
            "alert",
            "alerts",
            "push",
        )
    ):
        return False
    if any(
        marker in value
        for marker in (
            "결제수단",
            "결제 관리",
            "결제 내역",
            "청구 관리",
            "구독",
            "멤버십",
            "요금제",
            "클럽 이용 중",
            "payment method",
            "manage payment",
            "billing",
            "subscription",
            "membership",
            "active club",
            "current plan",
        )
    ):
        return True
    tokens = set(value.split())
    return bool(
        value.endswith("페이")
        or tokens
        & {
            "payment",
            "payments",
            "wallet",
            "pay",
            "plan",
            "plans",
        }
    )


def _looks_like_neutral_notification_settings_gateway(label: str) -> bool:
    """Allow only neutral account/menu/settings fallbacks for this target."""

    value = _plain_phrase(label)
    return any(
        marker in value
        for marker in (
            "설정",
            "환경설정",
            "계정",
            "마이페이지",
            "내 페이지",
            "프로필",
            "메뉴",
            "더보기",
            "settings",
            "preferences",
            "account",
            "my page",
            "profile",
            "menu",
            "more",
        )
    )


def _looks_like_notification_inbox_control(
    label: str,
    *,
    role: str,
    view_id: str | None,
    target_function: str,
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Detect a bare toolbar bell/activity tab for notification-setting goals.

    Accessibility trees commonly expose both a notification inbox bell and a
    notification-preferences row as ``Notifications``.  A bare notification
    label rendered as an icon or navigation tab is the inbox/activity surface;
    descriptive rows such as ``Notification settings`` or ``Push
    notifications`` remain eligible.
    """

    if not _target_is_notification_preferences(target_function):
        return False
    value = _plain_phrase(label)
    explicit_inbox_label = bool(
        value in {
            "알림함",
            "새 알림",
            "활동",
            "업데이트",
            "notification center",
            "new notifications",
            "activity",
            "updates",
        }
    )
    if explicit_inbox_label and not _screen_is_notification_preferences_surface(request):
        return True
    if value not in {
        "알림",
        "notification",
        "notifications",
        "alert",
        "alerts",
    }:
        return False
    role_value = role.lower()
    if role_value in {
        "icon",
        "image",
        "imagebutton",
        "bottomnavigationitem",
        "navigationitem",
        "tab",
    }:
        return True
    # Android accessibility nodes may omit a resource id.  Treat that as an
    # empty id instead of failing the whole observation on a valid settings
    # row such as YouTube's bare ``알림`` control.
    resource = str(view_id or "").lower()
    return bool(
        role_value == "button"
        and not _screen_is_notification_preferences_surface(request)
        and any(
            marker in resource
            for marker in (
                "toolbar",
                "menu_item",
                "notification_bell",
                "notification_icon",
                "notification_inbox",
                "activity_feed",
            )
        )
    )


def _screen_is_notification_preferences_surface(
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Require editable preference evidence for an ambiguous Notifications title."""

    title = _plain_phrase(request.screen.window_title)
    visible_labels = [
        _plain_phrase(element.text or element.content_description or "")
        for element in request.screen.elements
        if element.visible and element.enabled and not element.password
    ]
    explicit_markers = (
        "알림 설정",
        "알림 환경설정",
        "notification settings",
        "notification preferences",
        "push notification settings",
    )
    explicit_title = any(marker in title for marker in explicit_markers)
    explicit_label = any(
        any(marker in label for marker in explicit_markers)
        for label in visible_labels
    )
    notification_heading = bool(
        title in {"알림", "notification", "notifications", "alerts"}
        or any(
            label in {"알림", "notification", "notifications", "alerts"}
            or (
                len(label) <= 80
                and any(marker in label for marker in (" 알림", "알림 ", " notification", " notifications"))
            )
            for label in visible_labels
        )
    )
    editable_controls = [
        element
        for element in request.screen.elements
        if element.visible
        and element.enabled
        and (
            element.checkable
            or element.role.lower() in {"switch", "checkbox", "radio"}
        )
    ]
    notification_evidence = sum(
        1
        for label in set(visible_labels)
        if any(
            marker in label
            for marker in (
                "알림",
                "수신",
                "notification",
                "notifications",
                "notify",
                "push",
            )
        )
    )
    # An explicit title can represent a read-only category picker, whereas a
    # bare ``Notifications`` title also names an inbox and therefore requires
    # at least one editable preference control.  Some Android apps expose the
    # toolbar's back description (for example ``위로 이동``) as the window
    # title; in that case the visible heading plus multiple notification rows
    # and switches is the authoritative destination evidence.
    return bool(
        explicit_title
        or explicit_label
        or (
            editable_controls
            and notification_heading
            and notification_evidence >= 2
        )
    )


def _screen_is_notification_inbox_surface(
    request: UniversalNavigationObserveRequest,
    *,
    target_function: str,
) -> bool:
    """Recognize read-only notification activity so exploration backs out."""

    if (
        not _target_is_notification_preferences(target_function)
        or _screen_is_notification_preferences_surface(request)
    ):
        return False
    title = _plain_phrase(request.screen.window_title)
    title_is_inbox = title in {
        "알림",
        "알림함",
        "활동",
        "notification",
        "notifications",
        "notification center",
        "activity",
        "updates",
    }
    labels = {
        _plain_phrase(element.text or element.content_description or "")
        for element in request.screen.elements
        if element.visible and element.enabled
    }
    inbox_filters = {
        "전체",
        "댓글",
        "멘션",
        "좋아요",
        "all",
        "comments",
        "mentions",
        "likes",
    }
    filter_count = len(labels & inbox_filters)
    has_preference_gateway = any(
        any(
            marker in label
            for marker in (
                "알림 설정",
                "수신 설정",
                "notification settings",
                "notification preferences",
                "manage notifications",
            )
        )
        for label in labels
    )
    return bool(
        (title_is_inbox and filter_count >= 1 and not has_preference_gateway)
        or (filter_count >= 2 and not has_preference_gateway)
    )


def _selected_state_has_target_identity(
    *,
    target_function: str,
    candidate_label: str,
    target_match,
) -> bool:
    """Require direct target evidence before selected state implies arrival.

    Being checked or selected only describes UI state.  It must not allow an
    unrelated tab, playlist, filter, or account choice to borrow the requested
    function from the surrounding screen after a backtrack.
    """

    if target_match is None or target_match.score < 0.50:
        return False
    if (
        _terminal_cues_for_function(target_function) is not None
        and not _has_required_terminal_cue(target_function, candidate_label)
    ):
        return False
    return bool(
        target_match.alias_score >= 0.60
        or target_match.concept_score >= 0.28
        or target_match.score >= 0.72
    )


def _is_explicit_settings_gateway(label: str) -> bool:
    normalized = " ".join(label.lower().split())
    exact = {
        "설정",
        "환경 설정",
        "환경설정",
        "앱 설정",
        "설정 및 개인정보",
        "settings",
        "preferences",
        "app settings",
        "general settings",
        "settings and privacy",
        "user settings",
    }
    if normalized in exact:
        return True
    # Short OCR labels often differ by one Hangul syllable (for example
    # ``환경설젱``).  Accept a close compact reading only for the reviewed
    # settings gateway aliases; long free-form text is intentionally excluded
    # so a descriptive paragraph cannot become an automatic navigation row.
    compact = "".join(character for character in normalized if character.isalnum())
    if not (3 <= len(compact) <= 8):
        return False
    return any(
        len(compact_alias := "".join(character for character in alias if character.isalnum()))
        == len(compact)
        and text_similarity(compact, compact_alias) >= 0.74
        for alias in ("환경설정", "앱설정", "settings")
    )


def _looks_like_account_or_settings_hub(
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Recognize a dense account/preferences menu without app-specific names."""

    visible = " ".join(
        [request.screen.window_title]
        + [
            element.text or element.content_description or ""
            for element in request.screen.elements
            if element.visible and not element.password
        ]
    )
    text = _plain_phrase(visible)
    account_context = any(
        marker in text
        for marker in (
            "마이",
            "내 계정",
            "계정",
            "프로필",
            "account",
            "profile",
            "my page",
            "preferences",
        )
    )
    menu_families = (
        ("고객센터", "도움말", "support", "help center"),
        ("주문내역", "구매내역", "order history", "purchase history"),
        ("멤버십", "구독", "membership", "subscription"),
        ("개인정보", "보안", "privacy", "security"),
        ("결제", "payment", "billing"),
        ("설정", "settings"),
    )
    family_count = sum(any(marker in text for marker in family) for family in menu_families)
    return bool(account_context and family_count >= 1)


def _unnamed_navigation_hypothesis_score(
    *,
    element,
    request: UniversalNavigationObserveRequest,
    settings_hub: bool,
    account_hub: bool = False,
) -> float:
    """Rank an unnamed control structurally without claiming visual recognition."""

    if (
        (not settings_hub and not account_hub)
        or element is None
        or not element.bounds
        or len(element.bounds) != 4
    ):
        return 0.41
    max_right = max(
        (
            item.bounds[2]
            for item in request.screen.elements
            if item.bounds and len(item.bounds) == 4
        ),
        default=max(1, element.bounds[2]),
    )
    max_bottom = max(
        (
            item.bounds[3]
            for item in request.screen.elements
            if item.bounds and len(item.bounds) == 4
        ),
        default=max(1, element.bounds[3]),
    )
    left, top, right, bottom = element.bounds
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    if account_hub:
        if center_y < max_bottom * 0.72:
            return 0.36
        horizontal_ratio = max(0.0, min(1.0, center_x / max(1, max_right)))
        # Custom-drawn media apps often omit accessibility labels from their
        # persistent bottom tabs.  The trailing tab is conventionally the
        # account/profile surface (Netflix: ``My Netflix``).  This hypothesis
        # is scoped to the reviewed package and a paid-plan goal, and ordinary
        # transition reconciliation/backtracking remains in force.
        return min(0.91, 0.62 + 0.29 * horizontal_ratio)
    if center_y > max_bottom * 0.25:
        return 0.41
    horizontal_ratio = max(0.0, min(1.0, center_x / max(1, max_right)))
    # A top-bar trailing icon is a common reversible preferences gateway.  The
    # score remains below an explicit semantic settings label and is used only
    # when no named safe candidate exists.  If it is wrong, the normal
    # backtracking/frontier limits still apply.
    return min(0.69, 0.48 + 0.21 * horizontal_ratio)


def _baemin_profile_edit_gateway_score(
    label: str,
    *,
    element,
    request: UniversalNavigationObserveRequest,
) -> float:
    """Identify Baemin's OCR-backed nickname/pencil profile doorway.

    The reviewed Compose screen exposes the nickname row as a non-clickable
    button and the pencil without a label. OCR therefore provides the only
    executable coordinate candidate. Keep the inference package/call-site
    scoped and require the central upper profile-header geometry so promo,
    survey, membership, and trailing ``꾸미기`` controls cannot match.
    """

    if element is None or not element.bounds or len(element.bounds) != 4:
        return 0.0
    value = _plain_phrase(label)
    if not value or any(
        marker in value
        for marker in (
            "마이배민",
            "배민클럽",
            "꾸미기",
            "쿠폰",
            "포인트",
            "선물함",
            "결제수단",
            "고객센터",
            "환경설정",
            "주문 경험",
            "survey",
            "settings",
        )
    ):
        return 0.0
    max_right = max(
        (
            item.bounds[2]
            for item in request.screen.elements
            if item.bounds and len(item.bounds) == 4
        ),
        default=max(1, element.bounds[2]),
    )
    max_bottom = max(
        (
            item.bounds[3]
            for item in request.screen.elements
            if item.bounds and len(item.bounds) == 4
        ),
        default=max(1, element.bounds[3]),
    )
    left, top, right, bottom = element.bounds
    center_x_ratio = ((left + right) / 2) / max(1, max_right)
    center_y_ratio = ((top + bottom) / 2) / max(1, max_bottom)
    if not (0.25 <= center_x_ratio <= 0.72 and 0.22 <= center_y_ratio <= 0.34):
        return 0.0
    ocr_backed = element.view_id == "exitguide:ocr"
    short_profile_identity = len(value) <= 32 and len(value.split()) <= 4
    if not (ocr_backed or short_profile_identity):
        return 0.0
    return 1.18 if ocr_backed else 1.08


def _baemin_my_page_surface_visible(
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Detect the Baemin account surface without trusting its window title.

    Baemin's Compose hierarchy frequently reports the survey banner as the
    window title.  The actual ``마이배민`` heading remains visible near the top,
    while the identically named bottom tab sits at the bottom of every root
    screen.  Geometry distinguishes the heading from that global tab.
    """

    max_bottom = max(
        (
            element.bounds[3]
            for element in request.screen.elements
            if element.bounds and len(element.bounds) == 4
        ),
        default=1,
    )
    for element in request.screen.elements:
        if not element.visible or not element.bounds or len(element.bounds) != 4:
            continue
        value = _plain_phrase(element.text or element.content_description or "")
        if value not in {"마이배민", "my baemin"}:
            continue
        _left, top, _right, bottom = element.bounds
        if ((top + bottom) / 2) / max(1, max_bottom) <= 0.22:
            return True
    return False


def _baemin_profile_edit_surface_visible(
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Recognize Baemin's profile WebView from its visible page heading."""

    for element in request.screen.elements:
        if not element.visible or element.password:
            continue
        value = _plain_phrase(element.text or element.content_description or "")
        if "내 정보 수정" in value:
            return True
    return False


def _baemin_withdrawal_control_materially_visible(
    *,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
) -> bool:
    """Require more than a clipped sliver of Baemin's final withdrawal row."""

    elements_by_id = {element.id: element for element in request.screen.elements}
    max_bottom = max(
        (
            element.bounds[3]
            for element in request.screen.elements
            if element.bounds and len(element.bounds) == 4
        ),
        default=1,
    )
    minimum_height = max(24, round(max_bottom * 0.01))
    for candidate in candidates:
        if "탈퇴" not in _plain_phrase(candidate.label):
            continue
        element = elements_by_id.get(candidate.element_id)
        if element is None or not element.visible or not element.bounds or len(element.bounds) != 4:
            continue
        _left, top, _right, bottom = element.bounds
        height = max(0, bottom - top)
        center_y_ratio = ((top + bottom) / 2) / max(1, max_bottom)
        if height >= minimum_height and center_y_ratio <= 0.95:
            return True
    return False


def _terminal_cues_for_function(target_function: str) -> tuple[str, ...] | None:
    required_cues = {
        "account.delete.entry": (
            "탈퇴",
            "계정 삭제",
            "계정 폐쇄",
            "계정 비활성화",
            "delete account",
            "delete your account",
            "delete your google account",
            "account deletion",
            "deactivation or deletion",
            "deactivate or delete account",
            "deactivate your account",
            "close account",
        ),
        "privacy.delete_data": (
            "데이터 삭제",
            "기록 삭제",
            "개인정보 삭제",
            "기록 지우기",
            "delete data",
            "erase data",
        ),
        "privacy.consent": ("동의", "consent", "agreement"),
        "auth.signup.email": ("이메일", "email"),
        "auth.signup.phone": ("휴대폰", "전화번호", "phone", "mobile"),
        "auth.signup.social": ("구글", "애플", "카카오", "소셜", "google", "apple", "social"),
        "legal.privacy_policy": (
            "처리방침",
            "개인정보 정책",
            "보호정책",
            "프라이버시 정책",
            "privacy policy",
            "privacy notice",
        ),
        "subscription.manage": (
            "구독 관리",
            "멤버십 관리",
            "멤버십 세부",
            "프리미엄 관리",
            "구매 항목 및 멤버십",
            "구독 및 멤버십 관리",
            "play에서 관리",
            "google play에서 관리",
            "manage subscription",
            "manage membership",
            "manage your plan",
            "manage in google play",
            "membership details",
        ),
        "subscription.change": (
            "요금제 변경",
            "구독 변경",
            "멤버십 변경",
            "플랜 변경",
            "사용 가능한 요금제",
            "change plan",
            "switch plan",
            "available plans",
        ),
        "content.history": (
            "기록",
            "시청 기록",
            "시청 활동",
            "검색 기록",
            "활동 기록",
            "최근 본",
            "watch history",
            "viewing activity",
            "viewing history",
            "search history",
            "activity history",
        ),
        "settings.playback": (
            "재생",
            "자동 재생",
            "재생 설정",
            "동영상 설정",
            "autoplay",
            "playback",
            "video preferences",
        ),
        "notification.settings": (
            "알림",
            "알림 설정",
            "알림 및 혜택",
            "푸시 알림",
            "notification",
            "notification settings",
            "push notifications",
        ),
        "data.download": (
            "데이터 다운로드",
            "데이터 사본",
            "내 정보 내려받기",
            "정보 내보내기",
            "download your data",
            "download my data",
            "download an archive",
            "request data archive",
            "export data",
        ),
        "refund.entry": ("환불", "결제 취소", "구매 취소", "refund"),
        "order.cancel.entry": ("주문 취소", "구매 취소", "배송 전 취소", "취소 요청", "cancel order"),
        "insurance.contract.list": ("보험계약", "계약조회", "내 보험", "보유계약", "한번에 조회 마이페이지", "my교보", "my policies", "policy inquiry"),
        "insurance.contract.change": ("보험계약 변경", "계약 변경", "계약자 변경", "change policy"),
        "insurance.contract.cancel.entry": ("보험계약 해지", "계약 해지", "장기보험 해지", "보험 해약", "청약철회", "cancel policy", "policy cancellation"),
        "insurance.claim.entry": ("보험금 청구", "보험금청구", "실손 청구", "file a claim", "insurance claim"),
        "insurance.claim.status": ("처리현황", "진행상황", "보상 진행", "청구 결과", "보상내역", "claim status", "claim results"),
        "insurance.claim.documents": ("청구서류", "필요서류", "구비서류", "claim documents"),
        "insurance.premium.payment": ("보험료 납입", "보험료납입", "보험료 납부", "보험료납부", "pay premium", "premium payment"),
        "insurance.certificate.issue": ("증명서 발급", "증명서발급", "증명서 발행", "제증명", "확인서 발급", "issue certificate"),
        "insurance.policy.documents": ("보험증권", "policy document", "insurance policy document"),
        "insurance.policy.terms": ("보험약관", "보험 약관", "상품약관", "policy wording", "policy terms"),
        "insurance.surrender_value": ("해지환급금", "해약환급금", "surrender value"),
        "insurance.loan.entry": ("보험계약대출", "계약대출", "policy loan", "insurance loan"),
        "insurance.accident.report": ("사고접수", "사고 접수", "accident report", "report accident"),
        "insurance.emergency.roadside": ("긴급출동", "고장출동", "출동 요청", "roadside assistance", "breakdown service"),
        "insurance.branch.find": ("지점찾기", "지점 찾기", "고객창구", "find branch", "branch locator"),
        "insurance.coverage.analysis": ("보장분석", "보장 분석", "coverage analysis"),
        "health_insurance.eligibility": ("자격조회", "자격 조회", "자격득실", "eligibility"),
        "health_insurance.screening": ("건강검진", "검진대상", "검진 결과", "health screening"),
        "health_insurance.refund": ("환급금 조회", "미지급환급금", "건강보험 환급금", "unclaimed refund"),
        "support.chat": (
            "상담 연결 대기",
            "상담 가능",
            "상담원이 연결",
            "대기 시간",
            "waiting for an agent",
            "agent connected",
            "chat ready",
        ),
    }
    return required_cues.get(target_function)


def _requires_explicit_terminal_cue(target_function: str) -> bool:
    # Support chat has a distinct entry control and a distinct connected/waiting
    # state. Notification-preference goals must also retain notification
    # identity: a generic ``Settings`` gateway is progress, not the requested
    # destination. Other functions accept reviewed semantic paraphrases, with
    # destructive action words enforced through semantic terminal concepts.
    return bool(
        target_function == "support.chat"
        or (
            _target_is_notification_preferences(target_function)
            and _terminal_cues_for_function(target_function) is not None
        )
    )


def _has_required_terminal_cue(target_function: str, label: str) -> bool:
    normalized = " ".join(label.lower().split())
    cues = _terminal_cues_for_function(target_function)
    return cues is None or any(cue in normalized for cue in cues)


def _satisfies_semantic_terminal_concepts(
    catalog: NavigationFunctionCatalog,
    target_function: str,
    label: str,
) -> bool:
    definition = catalog.function(target_function)
    if definition is None or not definition.semantic_terminal_concepts:
        return True
    return frozenset(definition.semantic_terminal_concepts).issubset(
        catalog.semantic_concepts_for_text(label)
    )


def _looks_like_support_chat_entry(label: str) -> bool:
    normalized = " ".join(label.lower().split())
    if _has_required_terminal_cue("support.chat", normalized):
        return False
    return any(
        cue in normalized
        for cue in (
            "상담원",
            "상담 채팅",
            "실시간 상담",
            "live chat",
            "chat with an agent",
            "talk to an agent",
        )
    )


def _path_has_subscription_specific_progress(state: ExplorationState) -> bool:
    """Return whether exploration already entered the subscription branch."""

    subscription_function_ids = {
        "active_subscription",
        "billing.manage",
        "billing_management",
        "subscription.detail",
        "subscription.list",
        "subscription.manage",
    }
    for step in state.path:
        function_ids = {
            str(function_id)
            for function_id in step.get("function_ids", [])
            if function_id
        }
        if any(
            function_id.startswith("subscription.")
            or function_id in subscription_function_ids
            for function_id in function_ids
        ):
            return True
        label = _plain_phrase(str(step.get("label", "")))
        if any(
            marker in label
            for marker in (
                "구매 항목 및 멤버십",
                "구독 및 멤버십",
                "멤버십 관리",
                "구독 관리",
                "purchases and memberships",
                "subscriptions and memberships",
                "manage membership",
                "manage subscription",
            )
        ):
            return True
    return False


def _is_reliable_subscription_progress(
    label: str,
    function_ids: tuple[str, ...],
    *,
    state: ExplorationState,
) -> bool:
    normalized = " ".join(label.lower().split())
    if _looks_like_creator_audience_metric(label):
        return False
    if any(
        token in normalized
        for token in ("가게", "특가", "할인", "쿠폰", "0원", "혜택가", "무료", "추천 상품", "주문 시")
    ):
        return False
    generic_gateway = any(
        function_id in COMMON_GATEWAY_FUNCTIONS
        or function_id in {"account_entry", "android.settings.root"}
        or function_id.startswith("navigation.")
        for function_id in function_ids
    )
    subscription_functions = {
        "billing.manage",
        "billing_management",
        "subscription.manage",
        "subscription.list",
        "subscription.detail",
        "active_subscription",
    }
    subscription_specific = any(
        function_id in subscription_functions for function_id in function_ids
    )
    if generic_gateway:
        if _path_has_subscription_specific_progress(state):
            # Once a subscription-specific screen has been reached, a broad
            # catalog fuzzy match must not make My page, Settings, Home, or a
            # global tab look subscription-specific.  Only an explicit label
            # below is allowed to keep progressing from that point.
            if not any(
                token in normalized
                for token in (
                    "이용 중",
                    "이용중",
                    "현재 이용",
                    "구독",
                    "멤버십",
                    "이용권",
                    "정기 결제",
                    "결제 관리",
                    "subscription",
                    "membership",
                    "billing",
                )
            ):
                return False
        else:
            # A cold-start account/menu/settings gateway is valid progress even
            # when the broad ontology also assigns it a weak subscription tag.
            # Treating the fuzzy tag as authoritative used to discard entries
            # such as ``마이배민`` before the planner could evaluate them.
            return True
    if not subscription_specific:
        return False
    if normalized in {"배민클럽", "마이배민클럽"}:
        return True
    return any(
        token in normalized
        for token in (
            "이용 중",
            "이용중",
            "이용즉",
            "현재 이용",
            "구독",
            "멤버십",
            "이용권",
            "정기 결제",
            "결제 관리",
            "구독 관리",
            "멤버십 관리",
            "subscription",
            "membership",
            "manage subscription",
            "manage membership",
            "billing management",
            "active",
            "google play",
        )
    )


def _subscription_detail_needs_bounded_reobserve(
    *,
    target_function: str,
    request: UniversalNavigationObserveRequest,
    state: ExplorationState,
    latest_attempt: dict[str, object] | None,
) -> bool:
    """Wait once when a just-opened paid-plan detail has not populated yet.

    Some apps expose only their persistent navigation chrome for the first
    accessibility snapshot after opening a web-backed membership detail.  A
    single no-op observation is safer than immediately abandoning a correct
    branch.  The latest-attempt guard makes this strictly one-shot even when
    OCR-only changes produce a different screen fingerprint.
    """

    if target_function != "subscription.cancel.entry" or not state.path:
        return False
    if latest_attempt is not None and latest_attempt.get("command") == "wait":
        return False
    step = next(
        (
            item
            for item in reversed(state.path)
            if item.get("kind") != "scroll" and not bool(item.get("pending"))
        ),
        None,
    )
    if step is None:
        return False
    if str(step.get("expected_to_screen_fingerprint") or "") != state.current_screen_fingerprint:
        return False
    if latest_attempt is not None and latest_attempt.get("command") == "click":
        attempted_label = _plain_phrase(str(latest_attempt.get("label", "")))
        if attempted_label and attempted_label != _plain_phrase(str(step.get("label", ""))):
            return False
    label = _plain_phrase(str(step.get("label", "")))
    if label in {
        "구매 항목 및 멤버십",
        "멤버십 및 채널",
        "구독 및 멤버십",
        "purchases and memberships",
        "subscriptions and memberships",
        "memberships and channels",
    }:
        return False
    plan_specific = any(
        marker in label
        for marker in (
            "프리미엄",
            "premium",
            "배민클럽",
            "개인 멤버십",
            "유료 멤버십",
            "이용 중",
            "이용중",
            "현재 이용",
            "paid membership",
            "subscription plan",
            "membership plan",
            "active subscription",
            "active membership",
        )
    )
    netflix_account_webview = bool(
        request.app_package == "com.netflix.mediaclient"
        and _goal_requests_paid_subscription_management(request.goal_text)
        and label in {"계정", "account"}
    )
    if (
        not (plan_specific or netflix_account_webview)
        or not _path_has_subscription_specific_progress(state)
    ):
        return False

    # Do not wait once an explicit user-owned destination is already exposed.
    visible_labels = [
        element.text or element.content_description or ""
        for element in request.screen.elements
        if element.visible and not element.password
    ]
    return not any(
        _has_explicit_cancellation_cue(value)
        or _is_reviewed_external_subscription_management_handoff(value, request)
        for value in visible_labels
        if value
    )


def _subscription_destination_requires_page_scan(
    *,
    target_function: str,
    request: UniversalNavigationObserveRequest,
) -> bool:
    if target_function != "subscription.cancel.entry":
        return False
    visible_labels = [
        element.text or element.content_description or ""
        for element in request.screen.elements
        if element.visible and not element.password
    ]
    if any(
        _has_explicit_cancellation_cue(value)
        or _is_reviewed_external_subscription_management_handoff(value, request)
        for value in visible_labels
        if value
    ):
        return False
    screen_text = _plain_phrase(
        " ".join([request.screen.window_title] + visible_labels)
    )
    has_subscription_context = any(
        marker in screen_text
        for marker in (
            "구독",
            "멤버십",
            "멤버쉽",
            "클럽",
            "subscription",
            "membership",
            "plan",
        )
    )
    has_active_detail_context = any(
        marker in screen_text
        for marker in (
            "이용 중",
            "이용중",
            "현재 이용",
            "다음 결제",
            "갱신",
            "active membership",
            "active subscription",
            "current plan",
            "next billing",
            "renews",
        )
    )
    return has_subscription_context and has_active_detail_context


def _baemin_profile_detail_needs_bounded_reobserve(
    *,
    state: ExplorationState,
    latest_attempt: dict[str, object] | None,
) -> bool:
    """Wait once for Baemin's just-opened profile WebView to populate."""

    if not state.path:
        return False
    if latest_attempt is not None and latest_attempt.get("command") == "wait":
        return False
    step = next(
        (
            item
            for item in reversed(state.path)
            if item.get("kind") != "scroll" and not bool(item.get("pending"))
        ),
        None,
    )
    if step is None:
        return False
    if str(step.get("expected_to_screen_fingerprint") or "") != state.current_screen_fingerprint:
        return False
    return "account.profile.edit" in {
        str(function_id) for function_id in step.get("function_ids", [])
    }


def _screen_has_explicit_late_terminal_evidence(
    target_function: str,
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Permit an over-budget read only when a safe terminal may be visible."""

    if target_function != "subscription.cancel.entry":
        return False
    return any(
        _has_explicit_cancellation_cue(value)
        or _is_reviewed_external_subscription_management_handoff(value, request)
        for value in (
            element.text or element.content_description or ""
            for element in request.screen.elements
            if element.visible and not element.password
        )
        if value
    )


def _scroll_attempt_count(state: ExplorationState, screen_fingerprint: str) -> int:
    return sum(
        1
        for step in state.path
        if step.get("kind") == "scroll"
        and step.get("from_screen_fingerprint") == screen_fingerprint
    )


def _total_scroll_attempt_count(state: ExplorationState) -> int:
    return sum(1 for step in state.path if step.get("kind") == "scroll")


def _looks_like_expired_session_screen(request: UniversalNavigationObserveRequest) -> bool:
    text = _plain_phrase(
        " ".join(
            filter(
                None,
                [request.screen.window_title]
                + [
                    element.text or element.content_description or ""
                    for element in request.screen.elements
                    if element.visible and not element.password
                ],
            )
        )
    )
    return any(
        marker in text
        for marker in (
            "세션이 만료",
            "세션 만료",
            "로그인이 만료",
            "인증이 만료",
            "session expired",
            "session has expired",
            "sign in again",
            "authentication required",
        )
    )


def _looks_like_reauthentication_candidate(label: str) -> bool:
    normalized = _plain_phrase(label)
    return any(
        marker in normalized
        for marker in (
            "다시 로그인",
            "로그인 계속",
            "계정 확인",
            "본인 확인",
            "재인증",
            "open account verification",
            "verify account",
            "account verification",
            "continue sign in",
            "sign in again",
            "log in again",
        )
    )


def _looks_like_new_account_candidate(label: str) -> bool:
    normalized = _plain_phrase(label)
    return any(
        marker in normalized
        for marker in (
            "새 계정",
            "다른 계정",
            "계정 만들기",
            "회원가입",
            "create account",
            "create a different account",
            "different account",
            "new account",
            "sign up",
            "register",
        )
    )


def _looks_like_intermediate_process_label(label: str) -> bool:
    """Return True for navigation labels that lead toward a final action."""

    normalized = _plain_phrase(label)
    return any(
        marker in normalized
        for marker in (
            "과정",
            "절차 안내",
            "설정 메뉴",
            "관리 화면",
            "옵션",
            "목록",
            "상세",
            "flow",
            "process",
            "steps",
            "options",
            "settings menu",
            "management screen",
            "details",
            "list",
        )
    )


def _recovery_screen_requires_back(
    request: UniversalNavigationObserveRequest,
    *,
    target_function: str,
    state: ExplorationState,
) -> bool:
    """Recognize screens where Back is safer than guessing another control.

    The rule uses generic UI state evidence only: explicit connection/error
    dead ends, unsafe browser interstitials, redirect loops, exhausted lists,
    or a user's request to dismiss a temporary input/overlay.  It never infers
    a state-changing action from the goal.
    """

    visible_labels = [
        element.text or element.content_description or ""
        for element in request.screen.elements
        if element.visible and not element.password
    ]
    title = _plain_phrase(request.screen.window_title)
    screen_text = _plain_phrase(" ".join([request.screen.window_title] + visible_labels))
    goal = _plain_phrase(request.goal_text)

    activity = _plain_phrase(request.screen.activity_name)
    external_auxiliary_surface = bool(
        "customtab" in activity
        or "browser" in activity
        or title in {"링크 공유", "공유", "share link", "share"}
    )
    if external_auxiliary_surface and any(
        _looks_like_goal_irrelevant_auxiliary_link(
            label,
            goal_text=request.goal_text,
            target_function=target_function,
        )
        for label in [request.screen.window_title, *visible_labels]
        if label
    ):
        # If a stale/manual transition already opened a share sheet, support
        # page, or legal document, recover immediately.  Do not continue
        # clicking within another app merely because its text mentions the
        # product named in the user's original goal.
        return True

    feedback_overlay = _looks_like_transient_feedback_overlay(request)
    in_app_message_overlay = _looks_like_transient_in_app_message_overlay(request)
    visible_settings_gateway = any(
        element.visible
        and element.enabled
        and _is_explicit_settings_gateway(
            element.text or element.content_description or ""
        )
        for element in request.screen.elements
    )
    if (
        feedback_overlay
        and not in_app_message_overlay
        and _looks_like_clickable_feedback_card(request)
        and (
            visible_settings_gateway
            or _looks_like_account_or_settings_hub(request)
        )
    ):
        # A clickable satisfaction card embedded in an account page is not a
        # blocking modal. Keep exploring the visible settings gateway instead
        # of backing out of the account screen itself.
        return False
    transient_overlay = bool(feedback_overlay or in_app_message_overlay)
    if transient_overlay:
        # Prefer the overlay's own reversible close affordance. Android Back
        # can finish the host Activity for HTML in-app messages on some apps.
        if any(
            element.visible
            and element.enabled
            and _is_safe_transient_overlay_dismiss_label(
                element.text or element.content_description or ""
            )
            for element in request.screen.elements
        ):
            return False
        return True

    # A radio/checkbox destination is an actionable state screen, not a dead
    # branch.  Backtracking here would discard the very choice the user asked
    # to inspect and can create loops in Android settings.
    if any(
        element.visible and element.enabled and element.checkable
        for element in request.screen.elements
    ):
        return False

    explicit_return = any(
        marker in goal
        for marker in (
            "이전 화면으로",
            "뒤로 가",
            "돌아가",
            "돌아와",
            "이전 화면",
            "맨 아래까지",
            "끝까지 왔",
            "get me back",
            "go back",
            "return to",
            "back to",
            "end of the list",
        )
    )
    dismisses_temporary_ui = bool(
        any(marker in goal for marker in ("닫고", "숨기", "dismiss", "hide", "close"))
        and any(
            marker in goal
            for marker in (
                "키보드",
                "입력",
                "선택창",
                "팝업",
                "오버레이",
                "keyboard",
                "dialog",
                "popup",
                "sheet",
                "overlay",
            )
        )
    )
    temporary_surface_request = bool(
        any(
            marker in goal
            for marker in (
                "열린 속도 선택창을 닫",
                "키보드가 결과를 가",
                "입력을 닫",
                "선택창을 닫",
                "sheet",
                "keyboard is covering",
                "close the picker",
            )
        )
        and any(
            marker in screen_text
            for marker in (
                "재생 속도",
                "키보드 완료",
                "음성 입력",
                "speed",
                "keyboard",
            )
        )
    )
    if state.back_count == 0 and (
        explicit_return or dismisses_temporary_ui or temporary_surface_request
    ):
        return True

    hard_dead_end_markers = (
        "일시적인 연결 문제",
        "잠시 문제가 생겼",
        "오류 코드 503",
        "페이지를 찾을 수 없음",
        "연결이 비공개로 설정되어 있지 않습니다",
        "안전하지 않은 연결",
        "더 이상 항목이 없습니다",
        "page not found",
        "error code 503",
        "server error",
        "connection is not private",
        "your connection is not private",
        "too many redirects",
        "redirected 5 times",
        "third-party cookies are blocked",
        "sign-in could not continue",
    )
    if any(marker in screen_text for marker in hard_dead_end_markers):
        return True

    visible_values = {_plain_phrase(label) for label in visible_labels if label}
    if (
        target_function.startswith(("android.", "android_"))
        and bool(visible_values & {"allow", "허용"})
        and bool(visible_values & {"don't allow", "do not allow", "허용 안 함"})
        and bool(visible_values & {"back", "뒤로"})
        and title not in {"android settings", "android 설정", "설정"}
    ):
        return True
    if (
        bool(visible_values & {"back", "뒤로"})
        and any(
            marker in screen_text
            for marker in (
                "오프라인 상태에서는",
                "인터넷 연결 없이는",
                "cannot while offline",
                "unavailable offline",
            )
        )
    ):
        return True

    # Captive portals are unrelated to in-app feature navigation. Network and
    # connectivity goals remain eligible to interact with them.
    if any(marker in screen_text for marker in ("네트워크에 로그인", "network login")):
        if not any(token in target_function for token in ("network", "wifi", "connectivity")):
            return True

    # A blank embedded browser with only a reload affordance is a dead end.
    readable = [label for label in visible_labels if _plain_phrase(label)]
    if title in {"웹페이지", "webpage", "web page"} and len(readable) <= 1:
        if not readable or any(
            marker in _plain_phrase(readable[0])
            for marker in ("새로고침", "reload", "refresh")
        ):
            return True
    if title in {"웹페이지", "webpage", "web page"}:
        meaningful_controls = [
            element
            for element in request.screen.elements
            if element.visible
            and element.enabled
            and element.clickable
            and not any(
                marker in _plain_phrase(element.text or element.content_description or "")
                for marker in (
                    "웹 콘텐츠 영역",
                    "빈 웹 콘텐츠",
                    "새로고침",
                    "web content area",
                    "blank web content",
                    "reload",
                    "refresh",
                )
            )
        ]
        if not meaningful_controls:
            return True

    # When the user explicitly asks to switch authentication methods after an
    # invalid-code message, choosing Back is safer than retrying or locking the
    # account.
    auth_method_switch = bool(
        any(marker in goal for marker in ("바꾸", "전환", "switch", "instead"))
        and any(marker in screen_text for marker in ("코드가 올바르지", "invalid code", "incorrect code"))
    )
    return auth_method_switch


def _looks_like_transient_feedback_overlay(
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Recognize an unsolicited satisfaction prompt without eating a form.

    Apps often expose the underlying account page together with a modal whose
    title is a short experience question.  Treating that mixed tree as an
    ordinary page lets unrelated global frontier items beat the obscured
    settings control.  These prompts are safe to dismiss with Back, but an
    explicit review/feedback form and a user-requested feedback task must stay
    in the normal planner and user-boundary flow.
    """

    goal = _plain_phrase(request.goal_text)
    if any(
        marker in goal
        for marker in (
            "만족도",
            "설문",
            "피드백",
            "평가",
            "리뷰",
            "후기",
            "survey",
            "feedback",
            "rate the",
            "rate my",
            "write a review",
            "leave a review",
        )
    ):
        return False

    title = _plain_phrase(request.screen.window_title)
    visible_labels = [
        _plain_phrase(element.text or element.content_description or "")
        for element in request.screen.elements
        if element.visible and element.enabled and not element.password
    ]
    screen_text = _plain_phrase(" ".join([title, *visible_labels]))
    question_prompt = any(
        marker in screen_text
        for marker in (
            "어떠셨나요",
            "어땠나요",
            "만족하셨나요",
            "마음에 드시나요",
            "평가해 주세요",
            "의견을 들려주세요",
            "how was your",
            "how did you like",
            "are you enjoying",
            "rate your experience",
            "rate your order",
            "tell us what you think",
            "quick survey",
            "feedback survey",
            "would you rate",
        )
    )
    if not question_prompt:
        return False

    # WebView/modals often keep the ordinary account page as the window title
    # and expose the survey question only as a child label. A question mixed
    # with stable account/settings navigation is strong overlay evidence even
    # when the SDK container was truncated from the accessibility snapshot.
    question_is_window_title = any(
        marker in title
        for marker in (
            "어떠셨나요",
            "어땠나요",
            "만족하셨나요",
            "마음에 드시나요",
            "평가해 주세요",
            "how was your",
            "how did you like",
            "are you enjoying",
            "rate your experience",
            "rate your order",
        )
    )
    mixed_account_surface = any(
        marker in screen_text
        for marker in (
            "환경설정",
            "고객센터",
            "계정 설정",
            "account settings",
            "customer center",
            "help center",
        )
    )
    if not (question_is_window_title or mixed_account_surface):
        return False

    explicit_form = bool(
        any(
            element.visible
            and element.enabled
            and element.role.lower()
            in {
                "input",
                "text_field",
                "textfield",
                "edittext",
                "textbox",
            }
            for element in request.screen.elements
        )
        or any(
            marker in screen_text
            for marker in (
                "리뷰 작성",
                "후기 작성",
                "설문 작성",
                "피드백 작성",
                "리뷰 제출",
                "후기 제출",
                "설문 제출",
                "피드백 보내기",
                "작성 완료",
                "write a review",
                "review form",
                "survey form",
                "feedback form",
                "submit review",
                "submit survey",
                "send feedback",
                "post review",
                "publish review",
            )
        )
    )
    return not explicit_form


def _looks_like_clickable_feedback_card(
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Distinguish an embedded survey card from a touch-blocking modal.

    Some apps expose the survey question only as the window title while the
    underlying account page retains several ordinary clickable controls.  A
    page with that stable navigation structure and no dialog/WebView marker
    is an embedded card even when the question node itself is not clickable.
    """

    question_markers = (
        "어떠셨나요",
        "어땠나요",
        "만족하셨나요",
        "마음에 드시나요",
        "평가해 주세요",
        "how was your",
        "how did you like",
        "are you enjoying",
        "rate your experience",
        "rate your order",
    )
    if any(
        element.visible
        and element.enabled
        and element.clickable
        and any(
            marker
            in _plain_phrase(element.text or element.content_description or "")
            for marker in question_markers
        )
        for element in request.screen.elements
    ):
        return True

    modal_roles = {"dialog", "webview", "popup", "sheet"}
    if any(
        element.visible
        and (
            element.role.casefold() in modal_roles
            or any(
                marker in (element.view_id or "").casefold()
                for marker in ("inappmessage", "in_app_message", "modal", "dialog")
            )
        )
        for element in request.screen.elements
    ):
        return False
    stable_controls = [
        element
        for element in request.screen.elements
        if element.visible
        and element.enabled
        and element.clickable
        and not _is_safe_transient_overlay_dismiss_label(
            element.text or element.content_description or ""
        )
        and not any(
            marker
            in _plain_phrase(element.text or element.content_description or "")
            for marker in question_markers
        )
    ]
    return len(stable_controls) >= 2 and _looks_like_account_or_settings_hub(request)


def _looks_like_transient_in_app_message_overlay(
    request: UniversalNavigationObserveRequest,
) -> bool:
    """Recognize a full-screen SDK message obscuring the app underneath.

    In-app messaging SDKs can leave the underlying accessibility tree visible
    while a clickable HTML/WebView layer intercepts every touch.  Without this
    structural check the explorer repeatedly selects valid controls behind the
    layer.  Android Back is reversible here and dismisses the transient layer.

    The rule stays narrow: a known in-app-message resource marker must cover
    most of the visible screen, and a goal explicitly asking for that content
    is not dismissed.
    """

    goal = _plain_phrase(request.goal_text)
    if any(
        marker in goal
        for marker in (
            "혜택",
            "쿠폰",
            "프로모션",
            "이벤트",
            "광고",
            "팝업 내용",
            "인앱 메시지",
            "offer",
            "promotion",
            "coupon",
            "deal",
            "event banner",
            "in app message",
            "in-app message",
        )
    ):
        return False

    bounded = [
        element
        for element in request.screen.elements
        if element.visible and element.bounds and len(element.bounds) == 4
    ]
    if not bounded:
        return False

    min_left = min(element.bounds[0] for element in bounded)
    min_top = min(element.bounds[1] for element in bounded)
    max_right = max(element.bounds[2] for element in bounded)
    max_bottom = max(element.bounds[3] for element in bounded)
    screen_width = max(1, max_right - min_left)
    screen_height = max(1, max_bottom - min_top)

    resource_markers = (
        "braze_inappmessage",
        "braze_in_app_message",
        "firebase_inappmessaging",
        "firebase_in_app_messaging",
    )
    for element in bounded:
        view_id = (element.view_id or "").casefold().replace("-", "_")
        if not any(marker in view_id for marker in resource_markers):
            continue
        left, top, right, bottom = element.bounds
        width_ratio = max(0, right - left) / screen_width
        height_ratio = max(0, bottom - top) / screen_height
        if width_ratio >= 0.72 and height_ratio >= 0.72:
            return True
    return False


def _looks_like_infinite_feed(request: UniversalNavigationObserveRequest) -> bool:
    """Distinguish a content feed from a finite settings/menu list.

    A feed changes its screen fingerprint after every scroll, so a per-screen
    limit alone never converges. Repeated post actions plus a tall scrollable
    surface provide a package-independent signal for timelines such as X.
    """

    tall_scrollable = any(
        element.visible
        and element.enabled
        and element.scrollable
        and element.bounds
        and len(element.bounds) == 4
        and (element.bounds[3] - element.bounds[1]) >= 900
        for element in request.screen.elements
    )
    if not tall_scrollable:
        return False
    visible_text = _plain_phrase(
        " ".join(
            filter(
                None,
                [request.screen.window_title]
                + [
                    element.text or element.content_description or ""
                    for element in request.screen.elements
                    if element.visible and not element.password
                ],
            )
        )
    )
    feed_signals = (
        "피드",
        "타임라인",
        "추천",
        "팔로잉",
        "답글",
        "재게시",
        "마음에 들어요",
        "공유하기",
        "게시 옵션",
        "for you",
        "following",
        "timeline",
        "reply",
        "repost",
        "like",
        "share",
        "post options",
    )
    signal_count = sum(1 for token in feed_signals if token in visible_text)
    return signal_count >= 2


def _plain_phrase(value: str) -> str:
    without_formatting = "".join(
        character for character in value.lower() if unicodedata.category(character) != "Cf"
    )
    return " ".join(without_formatting.split())


def _same_as_current_screen(candidate_label: str, request: UniversalNavigationObserveRequest) -> bool:
    raw_label = " ".join(candidate_label.lower().split())
    if raw_label.startswith(("ut ", "u+ ", "u+")) and any(character.isdigit() for character in raw_label[:16]):
        return True
    candidate = "".join(character.lower() for character in candidate_label if character.isalnum())
    if not candidate:
        return False
    titles = [request.screen.window_title]
    elements_by_id = {element.id: element for element in request.screen.elements}
    max_bottom = max(
        (element.bounds[3] for element in request.screen.elements if element.bounds and len(element.bounds) == 4),
        default=2400,
    )
    for element in request.screen.elements:
        if (
            not element.visible
            or element.clickable
            or element.password
            or _is_owned_by_clickable_ancestor(element, elements_by_id)
            or not element.bounds
            or len(element.bounds) != 4
            or element.bounds[1] > max_bottom * 0.25
        ):
            continue
        titles.append(element.text or element.content_description or "")
    for title in titles:
        normalized_title = "".join(character.lower() for character in title if character.isalnum())
        if not normalized_title:
            continue
        if candidate == normalized_title:
            return True
        if len(candidate) >= 4 and candidate in normalized_title:
            return True
        if normalized_title and candidate.endswith(normalized_title):
            prefix = candidate[: -len(normalized_title)]
            if len(prefix) <= 18 and any(character.isdigit() for character in prefix):
                return True
    return False


def _is_owned_by_clickable_ancestor(element, elements_by_id: dict[str, object]) -> bool:
    """Do not confuse an action's accessibility child with a page heading.

    Android frequently exposes an icon button as a blank clickable container
    whose non-clickable child carries the readable ``contentDescription``.
    A top-bar child such as ``환경설정`` is therefore the button's label, not
    evidence that the current page is already the settings page.  Walk the
    bounded ancestor chain so nested wrappers are handled without relying on
    an app package, resource id, or absolute coordinate.
    """

    parent_id = getattr(element, "parent_id", None)
    visited: set[str] = set()
    while parent_id and parent_id not in visited and len(visited) < 24:
        visited.add(parent_id)
        parent = elements_by_id.get(parent_id)
        if parent is None:
            return False
        if bool(getattr(parent, "clickable", False)):
            return True
        parent_id = getattr(parent, "parent_id", None)
    return False


def _exploration_budget_stopped_response(
    *,
    request: UniversalNavigationObserveRequest,
    repository: UniversalNavigationGraphRepository,
    candidates: list[UniversalNavigationCandidate],
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
    state: ExplorationState,
    elapsed: float,
    warnings: list[str],
) -> UniversalNavigationObserveResponse:
    failure_reason = (
        "exploration_timeout"
        if elapsed >= state.timeout_seconds
        else "action_budget_exhausted"
    )
    return _stopped_response(
        request=request,
        observation=observation,
        graph_update=graph_update,
        candidates=candidates,
        state=repository.update_exploration(
            state.exploration_id,
            status="stopped",
            clear_pending=True,
        ),
        failure_reason=failure_reason,
        reason="안전 탐색의 시간 또는 동작 한도에 도달했습니다.",
        warnings=warnings,
    )


def _issue_reobserve(
    *,
    request: UniversalNavigationObserveRequest,
    repository: UniversalNavigationGraphRepository,
    candidates: list[UniversalNavigationCandidate],
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
    state: ExplorationState,
    warnings: list[str],
    selected_label: str = "구독 상세 불러오는 중",
    reason: str = "방금 연 유료 구독 상세의 관리 항목이 아직 접근성 트리에 표시되지 않아 한 번만 재확인합니다.",
) -> UniversalNavigationObserveResponse:
    last_step = next(
        (
            item
            for item in reversed(state.path)
            if item.get("kind") != "scroll" and not bool(item.get("pending"))
        ),
        {},
    )
    repository.record_exploration_attempt(
        exploration_id=state.exploration_id,
        screen_fingerprint=observation.screen_fingerprint,
        action_id=f"reobserve:{last_step.get('element_key', observation.screen_fingerprint)}",
        element_key_value=str(last_step.get("element_key", "")),
        label=str(last_step.get("label", "")),
        function_ids=[
            str(value)
            for value in last_step.get("function_ids", [])
            if value
        ],
        command="wait",
        outcome="waiting_for_detail_content",
        to_screen_fingerprint=observation.screen_fingerprint,
    )
    state = repository.update_exploration(
        state.exploration_id,
        current_screen_fingerprint=observation.screen_fingerprint,
        clear_pending=True,
    )
    return UniversalNavigationObserveResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        status="guided",
        screen_fingerprint=observation.screen_fingerprint,
        goal_interpretation=state.target_function,
        decision_mode="function_graph_exploration",
        phase="exploring",
        candidates=candidates,
        recommendation=None,
        graph_update=graph_update,
        automation=UniversalNavigationAutomation(
            action="none",
            safe_to_execute=True,
            selected_label=selected_label,
            reason=reason,
            action_count=state.action_count,
            action_limit=state.max_actions,
            elapsed_seconds=_elapsed_seconds(state.started_at),
            timeout_seconds=state.timeout_seconds,
        ),
        warnings=warnings,
    )


def _issue_scroll(
    *,
    request: UniversalNavigationObserveRequest,
    repository: UniversalNavigationGraphRepository,
    candidates: list[UniversalNavigationCandidate],
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
    state: ExplorationState,
    warnings: list[str],
) -> UniversalNavigationObserveResponse:
    scrollable = next(
        (element for element in request.screen.elements if element.visible and element.enabled and element.scrollable),
        None,
    )
    step = {
        "kind": "scroll",
        "ordinal": len(state.path),
        "from_screen_fingerprint": observation.screen_fingerprint,
        "element_id": None if scrollable is None else scrollable.id,
        "pending": True,
    }
    pending = {
        "kind": "scroll",
        "from_screen_fingerprint": observation.screen_fingerprint,
        "element_id": None if scrollable is None else scrollable.id,
    }
    state = repository.update_exploration(
        state.exploration_id,
        current_screen_fingerprint=observation.screen_fingerprint,
        action_count=state.action_count + 1,
        path=list(state.path) + [step],
        pending=pending,
    )
    return UniversalNavigationObserveResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        status="guided",
        screen_fingerprint=observation.screen_fingerprint,
        goal_interpretation=state.target_function,
        decision_mode="function_graph_exploration",
        phase="exploring",
        candidates=candidates,
        recommendation=None,
        graph_update=graph_update,
        automation=UniversalNavigationAutomation(
            action="scroll_forward",
            safe_to_execute=True,
            selected_element_id=None if scrollable is None else scrollable.id,
            selected_label="아래로 스크롤",
            reason="현재 화면에 적합한 메뉴가 없어 보이지 않는 메뉴를 확인합니다.",
            action_count=state.action_count,
            action_limit=state.max_actions,
            elapsed_seconds=_elapsed_seconds(state.started_at),
            timeout_seconds=state.timeout_seconds,
        ),
        warnings=warnings,
    )


def _issue_back(
    *,
    request: UniversalNavigationObserveRequest,
    repository: UniversalNavigationGraphRepository,
    candidates: list[UniversalNavigationCandidate],
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
    state: ExplorationState,
    route: StoredRoute | None,
    warnings: list[str],
    final_return: bool,
    preserve_parent_branch_for_retry: bool = False,
) -> UniversalNavigationObserveResponse:
    path = list(state.path)
    while path and path[-1].get("kind") == "scroll":
        path.pop()
    backtracked_step: dict[str, object] | None = None
    if path:
        backtracked_step = dict(path.pop())
    transient_retry_released = False
    if (
        preserve_parent_branch_for_retry
        and backtracked_step is not None
        and backtracked_step.get("element_key")
    ):
        transient_retry_released = repository.release_transient_retry_once(
            exploration_id=state.exploration_id,
            screen_fingerprint=str(
                backtracked_step.get("from_screen_fingerprint", "")
            ),
            action_id=str(backtracked_step.get("action_id", "")),
            element_key_value=str(backtracked_step.get("element_key", "")),
            label=str(backtracked_step.get("label", "")),
            function_ids=[
                str(value)
                for value in backtracked_step.get("function_ids", [])
                if value
            ],
        )
    if (
        backtracked_step is not None
        and backtracked_step.get("element_key")
        and not transient_retry_released
    ):
        repository.record_exploration_attempt(
            exploration_id=state.exploration_id,
            screen_fingerprint=observation.screen_fingerprint,
            action_id=(
                f"backtrack:{state.back_count + 1}:"
                f"{backtracked_step.get('action_id', backtracked_step.get('element_key', ''))}"
            ),
            element_key_value=str(backtracked_step.get("element_key", "")),
            label=str(backtracked_step.get("label", "")),
            function_ids=[
                str(value)
                for value in backtracked_step.get("function_ids", [])
                if value
            ],
            command="backtrack",
            outcome="backtracking",
            to_screen_fingerprint=observation.screen_fingerprint,
        )
    pending = {
        "kind": "back",
        "from_screen_fingerprint": observation.screen_fingerprint,
    }
    state = repository.update_exploration(
        state.exploration_id,
        status="returning_to_start" if final_return else "exploring",
        current_screen_fingerprint=observation.screen_fingerprint,
        back_count=state.back_count + 1,
        path=path,
        pending=pending,
    )
    return UniversalNavigationObserveResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        status="guided",
        screen_fingerprint=observation.screen_fingerprint,
        goal_interpretation=state.target_function,
        decision_mode="function_graph_exploration",
        phase="returning_to_start" if final_return else "exploring",
        candidates=candidates,
        recommendation=None,
        graph_update=graph_update,
        automation=UniversalNavigationAutomation(
            action="back",
            safe_to_execute=True,
            reason=(
                "발견한 경로를 보존한 채 시작 화면으로 복귀합니다."
                if final_return
                else "탐색이 끝난 분기에서 부모 화면으로 되돌아갑니다."
            ),
            action_count=state.action_count,
            action_limit=state.max_actions,
            elapsed_seconds=_elapsed_seconds(state.started_at),
            timeout_seconds=state.timeout_seconds,
        ),
        discovered_route=None if route is None else route.response_model(),
        warnings=warnings,
    )


def _verified_route_response(
    *,
    request: UniversalNavigationObserveRequest,
    repository: UniversalNavigationGraphRepository,
    candidates: list[UniversalNavigationCandidate],
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
    state: ExplorationState,
    route: StoredRoute,
    step: dict[str, object] | None,
    warnings: list[str],
) -> UniversalNavigationObserveResponse | None:
    """Execute one reversible low-risk step from a verified candidate route.

    The route remains provisional. Every step is rebound to the live
    accessibility candidate and the resulting screen is checked on the next
    observation. Any mismatch returns ``None`` so the caller invalidates the
    candidate and continues with the ordinary explorer in the same request.
    """

    if not step:
        terminal_step = next(
            (
                item
                for item in route.steps
                if bool(item.get("terminal"))
                and repository.screens_semantically_match(
                    str(item.get("from_screen_fingerprint") or ""),
                    observation.screen_fingerprint,
                )
            ),
            None,
        )
        terminal_is_live = bool(
            terminal_step is not None
            and any(
                candidate.element_key == terminal_step.get("element_key")
                for candidate in candidates
            )
        )
        if (
            observation.screen_fingerprint != route.destination_screen_fingerprint
            and not terminal_is_live
        ):
            return None
        repository.update_exploration(
            state.exploration_id,
            status="completed",
            current_screen_fingerprint=observation.screen_fingerprint,
            destination_screen_fingerprint=observation.screen_fingerprint,
            clear_pending=True,
            route_id=route.route_id,
        )
        repository.mark_goal_completed(request.session_id, request.goal_text)
        return _manual_route_response(
            request=request,
            repository=repository,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            route=route,
            step=None,
            warnings=warnings + ["검증 후보 경로의 목적지 화면을 다시 확인했습니다."],
        )
    if bool(step.get("terminal")):
        return None
    expected_to = str(step.get("expected_to_screen_fingerprint") or "")
    if not expected_to:
        return None
    if str(step.get("kind") or "click") == "back":
        pending_step = {
            "ordinal": len(state.path),
            "kind": "back",
            "from_screen_fingerprint": observation.screen_fingerprint,
            "element_key": "",
            "label": "뒤로",
            "function_ids": [str(value) for value in step.get("function_ids", [])],
            "role": "navigation",
            "risk_level": "low",
            "expected_to_screen_fingerprint": expected_to,
            "terminal": False,
            "reversible": True,
            "confidence": float(step.get("confidence", route.confidence)),
            "action_id": "verified-route-back",
            "element_id": "android:back",
            "pending": True,
            "source": "verified_route",
        }
        pending = {
            "kind": "back",
            "source": "verified_route",
            "route_id": route.route_id,
            "from_screen_fingerprint": observation.screen_fingerprint,
            "expected_to_screen_fingerprint": expected_to,
            "element_id": "android:back",
            "element_key": "",
            "action_id": "verified-route-back",
            "label": "뒤로",
            "function_ids": [str(value) for value in step.get("function_ids", [])],
            "mismatch_observations": 0,
        }
        state = repository.update_exploration(
            state.exploration_id,
            status="route_reusing",
            current_screen_fingerprint=observation.screen_fingerprint,
            action_count=state.action_count + 1,
            back_count=state.back_count + 1,
            path=list(state.path) + [pending_step],
            pending=pending,
            route_id=route.route_id,
        )
        return UniversalNavigationObserveResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            status="guided",
            screen_fingerprint=observation.screen_fingerprint,
            goal_interpretation=route.target_function,
            decision_mode="route_cache",
            phase="exploring",
            candidates=candidates,
            recommendation=None,
            graph_update=graph_update,
            automation=UniversalNavigationAutomation(
                action="back",
                safe_to_execute=True,
                selected_element_id=None,
                selected_element_key=None,
                selected_label="뒤로",
                reason="검증 후보 경로에 기록된 되돌릴 수 있는 화면 복구 단계입니다.",
                action_count=state.action_count,
                action_limit=state.max_actions,
                elapsed_seconds=_elapsed_seconds(state.started_at),
                timeout_seconds=state.timeout_seconds,
            ),
            discovered_route=route.response_model(),
            warnings=warnings,
        )
    feedback_overlay = _looks_like_transient_feedback_overlay(request)
    in_app_message_overlay = _looks_like_transient_in_app_message_overlay(request)
    embedded_static_feedback_card = bool(
        feedback_overlay
        and not in_app_message_overlay
        and _looks_like_clickable_feedback_card(request)
        and _looks_like_account_or_settings_hub(request)
    )
    if (feedback_overlay or in_app_message_overlay) and not embedded_static_feedback_card:
        return None
    selected = next(
        (candidate for candidate in candidates if candidate.element_key == step.get("element_key")),
        None,
    )
    if selected is None:
        return None
    element = next(
        (item for item in request.screen.elements if item.id == selected.element_id),
        None,
    )
    action = observation.actions_by_element_id.get(selected.element_id)
    expected_role = str(step.get("role") or "").strip().casefold()
    if (
        element is None
        or action is None
        or not element.visible
        or not element.enabled
        or not element.clickable
        or element.checkable
        or element.password
        or element.selected
        or selected.risk_level != "low"
        or action.risk_level != "low"
        or str(step.get("risk_level") or "low") != "low"
        or _looks_like_final_state_change_action(selected.label)
        or (
            expected_role
            and expected_role not in {selected.role.casefold(), element.role.casefold()}
        )
    ):
        return None
    if (
        _same_as_current_screen(selected.label, request)
        or _looks_like_promotional_or_auxiliary_candidate(
            selected.label,
            allow_help=_goal_requests_help(request.goal_text),
        )
        or _looks_like_notification_inbox_control(
            selected.label,
            role=element.role,
            view_id=element.view_id,
            target_function=route.target_function,
            request=request,
        )
        or _looks_like_notification_preferences_detour(
            selected.label,
            target_function=route.target_function,
        )
        or (
            _looks_like_goal_irrelevant_auxiliary_link(
                selected.label,
                goal_text=request.goal_text,
                target_function=route.target_function,
            )
            and not (
                route.target_function == "subscription.cancel.entry"
                and _is_reviewed_external_subscription_management_handoff(
                    selected.label,
                    request,
                )
            )
        )
        or (
            _looks_like_content_discovery_surface(request)
            and _looks_like_feed_interaction_candidate(selected.label)
        )
        or _looks_like_paid_subscription_content_detour(
            selected.label,
            request=request,
            target_function=route.target_function,
        )
    ):
        # A trusted route is still only a hint against the live UI.  Reapply
        # the same semantic detour guards used by cold exploration so stale or
        # mislabeled gold cannot make route_cache open an inbox, promotion,
        # feed item, or unrelated support link.  Returning ``None`` causes the
        # caller to invalidate the route and continue safely in-session.
        return None
    if (
        route.target_function == "subscription.cancel.entry"
        and not _is_reliable_subscription_progress(
            selected.label,
            tuple(str(value) for value in step.get("function_ids", [])),
            state=state,
        )
    ):
        return None

    recommendation_id = _recommendation_id(
        request.session_id,
        observation.screen_fingerprint,
        selected.element_key,
    )
    confidence = max(0.0, min(1.0, float(step.get("confidence", route.confidence))))
    repository.record_recommendation(
        recommendation_id=recommendation_id,
        session_id=request.session_id,
        app_package=request.app_package,
        app_version=request.app_version,
        locale=request.locale,
        goal_text=request.goal_text,
        goal_interpretation=route.target_function,
        target_function=route.target_function,
        decision_mode="route_cache",
        screen_fingerprint=observation.screen_fingerprint,
        action_id=action.action_id,
        confidence=confidence,
    )
    pending_step = {
        "ordinal": len(state.path),
        "from_screen_fingerprint": observation.screen_fingerprint,
        "element_key": selected.element_key,
        "label": selected.label,
        "function_ids": [str(value) for value in step.get("function_ids", [])],
        "role": selected.role,
        "risk_level": selected.risk_level,
        "expected_to_screen_fingerprint": expected_to,
        "terminal": False,
        "reversible": True,
        "confidence": confidence,
        "action_id": action.action_id,
        "element_id": selected.element_id,
        "pending": True,
        "source": "verified_route",
    }
    pending = {
        "kind": "click",
        "source": "verified_route",
        "route_id": route.route_id,
        "from_screen_fingerprint": observation.screen_fingerprint,
        "expected_to_screen_fingerprint": expected_to,
        "element_id": selected.element_id,
        "element_key": selected.element_key,
        "action_id": action.action_id,
        "label": selected.label,
        "function_ids": [str(value) for value in step.get("function_ids", [])],
        "mismatch_observations": 0,
    }
    state = repository.update_exploration(
        state.exploration_id,
        status="route_reusing",
        current_screen_fingerprint=observation.screen_fingerprint,
        action_count=state.action_count + 1,
        path=list(state.path) + [pending_step],
        pending=pending,
        route_id=route.route_id,
    )
    recommendation = UniversalNavigationRecommendation(
        recommendation_id=recommendation_id,
        selected_element_id=selected.element_id,
        selected_element_key=selected.element_key,
        selected_label=selected.label,
        target_function=route.target_function,
        instruction=f"검증된 경로의 ‘{selected.label}’ 메뉴를 확인합니다.",
        reason="앱·버전·목적·화면·버튼 의미가 일치한 저위험 검증 후보 단계입니다.",
        expected_next_screen="검증 후보 경로에 기록된 다음 의미 화면",
        confidence=confidence,
        risk_level="low",
        requires_user_confirmation=False,
    )
    return UniversalNavigationObserveResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        status="guided",
        screen_fingerprint=observation.screen_fingerprint,
        goal_interpretation=route.target_function,
        decision_mode="route_cache",
        phase="exploring",
        candidates=candidates,
        recommendation=recommendation,
        graph_update=graph_update,
        automation=UniversalNavigationAutomation(
            action="click",
            safe_to_execute=True,
            selected_element_id=selected.element_id,
            selected_element_key=selected.element_key,
            selected_label=selected.label,
            reason="검증 후보 경로의 저위험 중간 메뉴이며 다음 화면을 재검증합니다.",
            action_count=state.action_count,
            action_limit=state.max_actions,
            elapsed_seconds=_elapsed_seconds(state.started_at),
            timeout_seconds=state.timeout_seconds,
        ),
        discovered_route=route.response_model(),
        warnings=warnings,
    )


def _manual_route_response(
    *,
    request: UniversalNavigationObserveRequest,
    repository: UniversalNavigationGraphRepository,
    candidates: list[UniversalNavigationCandidate],
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
    route: StoredRoute,
    step: dict[str, object] | None,
    warnings: list[str],
) -> UniversalNavigationObserveResponse:
    if not step:
        terminal_step = next(
            (
                item
                for item in route.steps
                if bool(item.get("terminal"))
                and repository.screens_semantically_match(
                    str(item.get("from_screen_fingerprint") or ""),
                    observation.screen_fingerprint,
                )
            ),
            None,
        )
        terminal_candidate = None
        if terminal_step is not None:
            terminal_candidate = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.element_key == terminal_step.get("element_key")
                ),
                None,
            )
        terminal_recommendation = None
        if terminal_candidate is not None:
            terminal_recommendation = UniversalNavigationRecommendation(
                recommendation_id=_recommendation_id(
                    request.session_id,
                    observation.screen_fingerprint,
                    terminal_candidate.element_key,
                ),
                selected_element_id=terminal_candidate.element_id,
                selected_element_key=terminal_candidate.element_key,
                selected_label=terminal_candidate.label,
                target_function=route.target_function,
                instruction=(
                    f"‘{terminal_candidate.label}’ 기능이 있는 최종 화면에 도착했습니다. "
                    "실제 상태 변경은 사용자가 직접 수행합니다."
                ),
                reason="저장된 경로의 최종 목적지를 현재 화면에서 다시 확인했습니다.",
                expected_next_screen="",
                confidence=float(terminal_step.get("confidence", route.confidence)),
                risk_level=terminal_candidate.risk_level,
                requires_user_confirmation=True,
            )
        return UniversalNavigationObserveResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            status="goal_completed",
            screen_fingerprint=observation.screen_fingerprint,
            goal_interpretation=route.target_function,
            decision_mode="route_cache",
            phase="destination_reached",
            candidates=candidates,
            recommendation=terminal_recommendation,
            graph_update=graph_update,
            automation=UniversalNavigationAutomation(
                action="stop",
                safe_to_execute=False,
                selected_element_id=(
                    None if terminal_candidate is None else terminal_candidate.element_id
                ),
                selected_element_key=(
                    None if terminal_candidate is None else terminal_candidate.element_key
                ),
                selected_label=None if terminal_candidate is None else terminal_candidate.label,
                reason="목적 기능 화면에 도착했으므로 자동 조작은 비활성화됐습니다.",
            ),
            discovered_route=route.response_model(),
            warnings=warnings,
        )
    selected = next(
        (candidate for candidate in candidates if candidate.element_key == step.get("element_key")),
        None,
    )
    recommendation_id = _recommendation_id(
        request.session_id,
        observation.screen_fingerprint,
        str(step.get("element_key", "")),
    )
    if selected is None:
        recommendation = UniversalNavigationRecommendation(
            recommendation_id=recommendation_id,
            selected_element_id=None,
            selected_element_key=str(step.get("element_key", "")) or None,
            selected_label=str(step.get("label", "")) or None,
            target_function=route.target_function,
            instruction="저장된 다음 메뉴가 현재 화면에 없습니다. 뒤로 가서 시작 화면을 맞추거나 경로를 다시 탐색해 주세요.",
            reason="앱 업데이트 또는 화면 상태 변화로 저장 경로와 현재 UI가 일치하지 않습니다.",
            expected_next_screen="",
            confidence=0.0,
            risk_level="low",
            requires_user_confirmation=False,
        )
        status = "needs_user_input"
    else:
        recommendation = UniversalNavigationRecommendation(
            recommendation_id=recommendation_id,
            selected_element_id=selected.element_id,
            selected_element_key=selected.element_key,
            selected_label=selected.label,
            target_function=route.target_function,
            instruction=f"‘{selected.label}’ 메뉴를 직접 눌러 주세요.",
            reason="탐색으로 확인해 저장한 기능 그래프 경로의 다음 단계입니다.",
            expected_next_screen="저장된 다음 기능 화면",
            confidence=float(step.get("confidence", route.confidence)),
            risk_level=selected.risk_level,
            requires_user_confirmation=bool(step.get("terminal")) or selected.risk_level != "low",
        )
        status = "guided"
        action = observation.actions_by_element_id.get(selected.element_id)
        repository.record_recommendation(
            recommendation_id=recommendation_id,
            session_id=request.session_id,
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            goal_text=request.goal_text,
            goal_interpretation=route.target_function,
            target_function=route.target_function,
            decision_mode="route_cache",
            screen_fingerprint=observation.screen_fingerprint,
            action_id=None if action is None else action.action_id,
            confidence=recommendation.confidence,
        )
    return UniversalNavigationObserveResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        status=status,
        screen_fingerprint=observation.screen_fingerprint,
        goal_interpretation=route.target_function,
        decision_mode="route_cache",
        phase="guiding",
        candidates=candidates,
        recommendation=recommendation,
        graph_update=graph_update,
        automation=UniversalNavigationAutomation(
            action="none",
            safe_to_execute=False,
            reason="경로 안내 단계에서는 모든 버튼을 사용자가 직접 누릅니다.",
        ),
        discovered_route=route.response_model(),
        warnings=warnings,
    )


def _destination_reached_response(
    *,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
    route: StoredRoute,
    state: ExplorationState,
    terminal: TerminalCandidate | None,
    warnings: list[str],
) -> UniversalNavigationObserveResponse:
    recommendation = None
    if terminal is not None:
        recommendation = UniversalNavigationRecommendation(
            recommendation_id=_recommendation_id(
                request.session_id,
                observation.screen_fingerprint,
                terminal.candidate.element_key,
            ),
            selected_element_id=terminal.candidate.element_id,
            selected_element_key=terminal.candidate.element_key,
            selected_label=terminal.candidate.label,
            target_function=route.target_function,
            instruction=(
                f"‘{terminal.candidate.label}’ 기능이 있는 최종 화면에 도착했습니다. "
                "실제 해지나 상태 변경은 사용자가 직접 수행합니다."
            ),
            reason="목적 기능이 있는 화면을 확인했으므로 자동 탐색을 종료합니다.",
            expected_next_screen="",
            confidence=terminal.confidence,
            risk_level=terminal.candidate.risk_level,
            requires_user_confirmation=True,
        )
    return UniversalNavigationObserveResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        status="goal_completed",
        screen_fingerprint=observation.screen_fingerprint,
        goal_interpretation=route.target_function,
        decision_mode="function_graph_exploration",
        phase="destination_reached",
        candidates=candidates,
        recommendation=recommendation,
        graph_update=graph_update,
        automation=UniversalNavigationAutomation(
            action="stop",
            safe_to_execute=False,
            selected_element_id=None if terminal is None else terminal.candidate.element_id,
            selected_element_key=None if terminal is None else terminal.candidate.element_key,
            selected_label=None if terminal is None else terminal.candidate.label,
            reason="최종 목적지에 도달해 자동 탐색을 종료합니다.",
            action_count=state.action_count,
            action_limit=state.max_actions,
            elapsed_seconds=_elapsed_seconds(state.started_at),
            timeout_seconds=state.timeout_seconds,
        ),
        discovered_route=route.response_model(),
        warnings=warnings,
    )


def _stopped_response(
    *,
    request: UniversalNavigationObserveRequest,
    observation: ObservationResult,
    graph_update: UniversalNavigationGraphUpdate,
    candidates: list[UniversalNavigationCandidate],
    state: ExplorationState,
    failure_reason: str,
    reason: str,
    warnings: list[str],
) -> UniversalNavigationObserveResponse:
    return UniversalNavigationObserveResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        status="needs_user_input",
        screen_fingerprint=observation.screen_fingerprint,
        goal_interpretation=state.target_function,
        decision_mode="function_graph_exploration",
        phase="stopped",
        candidates=candidates,
        recommendation=None,
        graph_update=graph_update,
        automation=UniversalNavigationAutomation(
            action="stop",
            safe_to_execute=False,
            reason=reason,
            action_count=state.action_count,
            action_limit=state.max_actions,
            elapsed_seconds=_elapsed_seconds(state.started_at),
            timeout_seconds=state.timeout_seconds,
        ),
        failure_reason=failure_reason,
        warnings=warnings + [reason],
    )


def _step_for_screen(route: StoredRoute, screen_fingerprint: str) -> dict[str, object] | None:
    return next(
        (dict(step) for step in route.steps if step.get("from_screen_fingerprint") == screen_fingerprint),
        None,
    )


def _renumber_steps(steps: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for ordinal, source in enumerate(steps):
        step = {
            key: value
            for key, value in source.items()
            if key
            in {
                "from_screen_fingerprint",
                "element_key",
                "label",
                "function_ids",
                "expected_to_screen_fingerprint",
                "terminal",
                "confidence",
            }
        }
        step["ordinal"] = ordinal
        normalized.append(step)
    return normalized


def _route_confidence(steps: list[dict[str, object]]) -> float:
    values = [float(step.get("confidence", 0.5)) for step in steps]
    if not values:
        return 0.62
    return round(max(0.45, min(values) * 0.70 + sum(values) / len(values) * 0.30), 4)


def _recommendation_id(session_id: str, screen_fingerprint: str, element_key: str) -> str:
    payload = f"{session_id}|{screen_fingerprint}|{element_key}"
    return "ur_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _elapsed_seconds(started_at: str) -> float:
    try:
        started = datetime.fromisoformat(started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return round(max(0.0, (datetime.now(timezone.utc) - started).total_seconds()), 3)
    except ValueError:
        return 0.0
