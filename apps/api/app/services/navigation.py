import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.resource_paths import get_resource_root
from app.schemas import (
    DarkPatternInspectRequest,
    DarkPatternScreenElement,
    NavigationGuideRequest,
    NavigationGuideResponse,
    NavigationRecovery,
    NavigationRouteCatalog,
    NavigationRouteSummary,
    NavigationScreenElement,
    NavigationTermsEvidence,
    NavigationTermsHint,
)
from app.services.dark_pattern import inspect_dark_pattern
from app.services.terms_corpus import search_terms_corpus


ROOT = get_resource_root()
NAVIGATION_ROUTES_PATH = ROOT / "fixtures" / "navigation" / "routes.json"
MAX_RETRY_COUNT = 2
MATCH_THRESHOLD = 2.5
ELEMENT_MATCH_THRESHOLD = 0.62
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")

GOAL_KEYWORDS = {
    "cancel_subscription": (
        "구독 해지",
        "구독해지",
        "멤버십 해지",
        "자동결제 해제",
        "자동 결제 해제",
        "자동결제",
        "cancel subscription",
    ),
    "delete_account": ("회원 탈퇴", "회원탈퇴", "계정 삭제", "계정삭제", "delete account"),
    "marketing_opt_out": ("마케팅 알림 끄", "광고 알림 끄", "수신 동의 철회", "마케팅 동의 철회", "opt out"),
}


def load_navigation_route_catalog() -> NavigationRouteCatalog:
    payload = _load_payload()
    routes = [
        NavigationRouteSummary(
            route_id=route["route_id"],
            service_name=route["service_name"],
            app_package=route["app_package"],
            platform=route["platform"],
            locale=route["locale"],
            goal_id=route["goal_id"],
            route_version=route["route_version"],
            state_count=len(route["states"]),
            status=route["status"],
            source_file=route["source_file"],
        )
        for route in payload["routes"]
    ]
    return NavigationRouteCatalog(
        description=payload["description"],
        route_count=len(routes),
        routes=routes,
    )


def guide_navigation(request: NavigationGuideRequest) -> NavigationGuideResponse:
    goal_id = _resolve_goal_id(request.goal_id, request.goal_text)
    dark_pattern = inspect_dark_pattern(_dark_pattern_request(request, goal_id))
    route = _find_route(
        app_package=request.app_package,
        platform=request.platform,
        locale=request.locale,
        goal_id=goal_id,
    )
    if route is None:
        return NavigationGuideResponse(
            request_id=request.request_id,
            goal_id=goal_id,
            instruction="이 앱과 목적에 대해 검증된 모범 경로가 아직 없습니다.",
            confidence=0.0,
            navigation_state="route_not_found",
            dark_pattern=dark_pattern,
            status="route_not_found",
        )

    if request.session.retry_count >= MAX_RETRY_COUNT:
        return _needs_review_response(
            request=request,
            route=route,
            goal_id=goal_id,
            dark_pattern=dark_pattern,
            instruction="두 번의 안내가 맞지 않아 추측을 중단했습니다. 이 화면은 경로 검수가 필요합니다.",
        )

    matched_state, state_score = _match_state(
        route["states"],
        request.screen_elements,
        request.session.last_confirmed_state_id,
    )
    if matched_state is None:
        return _recovery_response(request=request, route=route, goal_id=goal_id, dark_pattern=dark_pattern)

    navigation_state = _navigation_state(route, matched_state, request.session.last_confirmed_state_id)
    confidence = _state_confidence(matched_state, state_score)

    if matched_state["terminal"]:
        return NavigationGuideResponse(
            request_id=request.request_id,
            route_id=route["route_id"],
            route_version=route["route_version"],
            goal_id=goal_id,
            current_step=matched_state["step"],
            current_state_id=matched_state["state_id"],
            instruction=matched_state["instruction"],
            warning=matched_state["warning"],
            confidence=confidence,
            navigation_state="completed",
            terms_hint=_build_terms_hint(matched_state.get("terms_query")),
            dark_pattern=dark_pattern,
            source_files=[route["source_file"]],
            status="goal_completed",
        )

    if matched_state.get("target_meaning") in set(request.session.failed_candidate_meanings):
        return _needs_review_response(
            request=request,
            route=route,
            goal_id=goal_id,
            dark_pattern=dark_pattern,
            instruction="이미 실패한 동작 의미를 다시 추천하지 않습니다. 이 화면의 대체 경로를 검수해야 합니다.",
            state=matched_state,
        )

    target = _select_target_element(
        request.screen_elements,
        matched_state["target_labels"],
        set(request.session.failed_element_ids),
    )
    if target is None:
        recovery = matched_state["recovery"]
        if not recovery["safe"]:
            return _needs_review_response(
                request=request,
                route=route,
                goal_id=goal_id,
                dark_pattern=dark_pattern,
                instruction="현재 화면은 찾았지만 안전하게 안내할 버튼을 확인하지 못했습니다.",
                state=matched_state,
            )
        return NavigationGuideResponse(
            request_id=request.request_id,
            route_id=route["route_id"],
            route_version=route["route_version"],
            goal_id=goal_id,
            current_step=matched_state["step"],
            current_state_id=matched_state["state_id"],
            instruction="이 화면에서 검증된 버튼을 찾지 못했습니다. 이전 화면으로 한 번 돌아가 주세요.",
            warning=matched_state["warning"],
            requires_user_confirmation=True,
            confidence=max(0.3, confidence - 0.25),
            navigation_state="recovery_required",
            recovery=_recovery_model(recovery),
            dark_pattern=dark_pattern,
            source_files=[route["source_file"]],
            status="guided",
        )

    target_label = _element_label(target)
    return NavigationGuideResponse(
        request_id=request.request_id,
        route_id=route["route_id"],
        route_version=route["route_version"],
        goal_id=goal_id,
        current_step=matched_state["step"],
        current_state_id=matched_state["state_id"],
        target_element_id=target.id,
        target_label=target_label,
        instruction=matched_state["instruction"].format(target=target_label),
        warning=matched_state["warning"],
        requires_user_confirmation=matched_state["requires_user_confirmation"],
        confidence=confidence,
        navigation_state=navigation_state,
        terms_hint=_build_terms_hint(matched_state.get("terms_query")),
        dark_pattern=dark_pattern,
        source_files=[route["source_file"]],
        status="guided",
    )


def _load_payload() -> dict[str, Any]:
    payload = json.loads(NAVIGATION_ROUTES_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(payload.get("routes"), list):
        raise ValueError("Navigation route fixture must contain a routes list.")
    return payload


def _resolve_goal_id(goal_id: str | None, goal_text: str | None) -> str | None:
    if goal_id:
        return goal_id.strip()
    normalized_goal = _normalize(goal_text or "")
    for candidate, keywords in GOAL_KEYWORDS.items():
        if any(_normalize(keyword) in normalized_goal for keyword in keywords):
            return candidate
    return None


def _find_route(app_package: str, platform: str, locale: str, goal_id: str | None) -> dict[str, Any] | None:
    for route in _load_payload()["routes"]:
        if (
            route["app_package"] == app_package
            and route["platform"] == platform
            and route["locale"].lower() == locale.lower()
            and route["goal_id"] == goal_id
        ):
            return route
    return None


def _match_state(
    states: list[dict[str, Any]],
    elements: list[NavigationScreenElement],
    last_state_id: str | None,
) -> tuple[dict[str, Any] | None, float]:
    labels = [_element_label(element) for element in elements if _element_label(element)]
    best_state: dict[str, Any] | None = None
    best_score = 0.0
    previous = next((state for state in states if state["state_id"] == last_state_id), None)
    expected_next_state_id = None if previous is None else previous.get("next_state_id")
    for state in states:
        anchor_score = sum(2.0 for anchor in state["anchors"] if _best_similarity(anchor, labels) >= 0.72)
        target_similarity = max(
            (_best_similarity(target_label, labels) for target_label in state["target_labels"]),
            default=0.0,
        )
        target_score = 3.0 * target_similarity if target_similarity >= ELEMENT_MATCH_THRESHOLD else 0.0
        terminal_bonus = 2.0 if state["terminal"] and anchor_score >= 2.0 else 0.0
        progress_bonus = 0.0
        if state["state_id"] == last_state_id:
            progress_bonus = 0.2
        elif state["state_id"] == expected_next_state_id:
            progress_bonus = 0.5
        score = anchor_score + target_score + terminal_bonus + progress_bonus
        if score > best_score:
            best_state = state
            best_score = score
    if best_score < MATCH_THRESHOLD:
        return None, best_score
    return best_state, best_score


def _select_target_element(
    elements: list[NavigationScreenElement],
    target_labels: list[str],
    failed_element_ids: set[str],
) -> NavigationScreenElement | None:
    best: tuple[float, NavigationScreenElement] | None = None
    for element in elements:
        if not element.clickable or element.id in failed_element_ids:
            continue
        label = _element_label(element)
        score = max((_similarity(label, target) for target in target_labels), default=0.0)
        if score < ELEMENT_MATCH_THRESHOLD:
            continue
        if best is None or score > best[0]:
            best = (score, element)
    return None if best is None else best[1]


def _navigation_state(route: dict[str, Any], state: dict[str, Any], last_state_id: str | None) -> str:
    if not last_state_id or state["state_id"] == last_state_id:
        return "on_route"
    previous = next((item for item in route["states"] if item["state_id"] == last_state_id), None)
    if previous and previous.get("next_state_id") == state["state_id"]:
        return "on_route"
    return "reanchored"


def _state_confidence(state: dict[str, Any], score: float) -> float:
    possible = max(1.0, len(state["anchors"]) * 2.0 + (3.0 if state["target_labels"] else 0.0) + (2.0 if state["terminal"] else 0.0))
    return round(min(0.97, 0.55 + 0.42 * min(1.0, score / possible)), 2)


def _recovery_response(
    request: NavigationGuideRequest,
    route: dict[str, Any],
    goal_id: str | None,
    dark_pattern,
) -> NavigationGuideResponse:
    last_state = next(
        (state for state in route["states"] if state["state_id"] == request.session.last_confirmed_state_id),
        None,
    )
    recovery = (last_state or route["states"][0])["recovery"]
    if not recovery["safe"]:
        return _needs_review_response(
            request=request,
            route=route,
            goal_id=goal_id,
            dark_pattern=dark_pattern,
            instruction="현재 화면을 검증 경로에 연결할 수 없어 안내를 중단했습니다.",
        )
    return NavigationGuideResponse(
        request_id=request.request_id,
        route_id=route["route_id"],
        route_version=route["route_version"],
        goal_id=goal_id,
        instruction="현재 화면은 확인된 경로와 다릅니다. 이전 화면으로 한 번 돌아가 주세요.",
        requires_user_confirmation=True,
        confidence=0.41,
        navigation_state="recovery_required",
        recovery=_recovery_model(recovery),
        dark_pattern=dark_pattern,
        source_files=[route["source_file"]],
        status="guided",
    )


def _needs_review_response(
    request: NavigationGuideRequest,
    route: dict[str, Any],
    goal_id: str | None,
    dark_pattern,
    instruction: str,
    state: dict[str, Any] | None = None,
) -> NavigationGuideResponse:
    return NavigationGuideResponse(
        request_id=request.request_id,
        route_id=route["route_id"],
        route_version=route["route_version"],
        goal_id=goal_id,
        current_step=None if state is None else state["step"],
        current_state_id=None if state is None else state["state_id"],
        instruction=instruction,
        requires_user_confirmation=True,
        confidence=0.2,
        navigation_state="needs_review",
        recovery=NavigationRecovery(type="stop", safe=True, retry_after_recovery=False),
        dark_pattern=dark_pattern,
        source_files=[route["source_file"]],
        status="needs_review",
    )


def _recovery_model(recovery: dict[str, Any]) -> NavigationRecovery:
    return NavigationRecovery(
        type=recovery["type"],
        safe=recovery["safe"],
        expected_previous_state_id=recovery.get("expected_previous_state_id"),
        retry_after_recovery=recovery["retry_after_recovery"],
    )


def _build_terms_hint(query: str | None) -> NavigationTermsHint | None:
    if not query:
        return None
    search = search_terms_corpus(query=query, top_k=2)
    if not search.results:
        return None
    evidence = [
        NavigationTermsEvidence(
            heading=result.chunk.heading,
            text=result.chunk.text,
            document_id=result.chunk.document_id,
        )
        for result in search.results
    ]
    return NavigationTermsHint(
        query=query,
        summary=evidence[0].text,
        evidence=evidence,
    )


def _dark_pattern_request(request: NavigationGuideRequest, goal_id: str | None) -> DarkPatternInspectRequest:
    interactive = [element for element in request.screen_elements if element.clickable]
    source_elements = interactive or request.screen_elements
    title_element = next(
        (element for element in request.screen_elements if element.role == "heading" or element.id == "screen-title"),
        None,
    )
    screen_title = _element_label(title_element) if title_element else request.app_package
    return DarkPatternInspectRequest(
        request_id=request.request_id,
        goal_id=goal_id,
        goal_text=request.goal_text,
        screen_title=screen_title,
        screen_text=" ".join(_element_label(element) for element in request.screen_elements if _element_label(element)),
        elements=[
            DarkPatternScreenElement(
                id=element.id,
                text=_element_label(element) or element.id,
                role=element.role,
                clickable=element.clickable,
                prominence=element.prominence,
                default_selected=element.default_selected,
                optional=element.optional,
                monetary_impact=element.monetary_impact,
            )
            for element in source_elements
        ],
    )


def _element_label(element: NavigationScreenElement) -> str:
    return (element.text or element.content_description or "").strip()


def _best_similarity(target: str, labels: list[str]) -> float:
    return max((_similarity(target, label) for label in labels), default=0.0)


def _similarity(left: str, right: str) -> float:
    normalized_left = _normalize(left)
    normalized_right = _normalize(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return 0.88
    left_tokens = set(TOKEN_PATTERN.findall(left.lower()))
    right_tokens = set(TOKEN_PATTERN.findall(right.lower()))
    token_score = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence_score = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    return max(token_score, sequence_score)


def _normalize(value: str) -> str:
    return "".join(TOKEN_PATTERN.findall(value.lower()))
