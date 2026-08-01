from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from app.schemas import UniversalNavigationCandidate, UniversalNavigationObserveRequest
from app.services.android_control_index import AndroidControlEvidence, functional_tags, search_terms
from app.services.navigation_function_catalog import (
    GOAL_GOVERNANCE_BLOCKED_INTENT,
    NavigationFunctionCatalog,
    get_navigation_function_catalog,
)
from app.services.universal_navigation_graph import sanitize_text


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


@dataclass(frozen=True)
class GoalPlan:
    intent: str
    preferred_functions: tuple[tuple[str, float], ...]
    avoid_functions: tuple[str, ...] = ()
    terminal_function: str = ""
    confidence: float = 0.0

    def prompt_payload(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "preferred_functions": [tag for tag, _ in self.preferred_functions],
            "avoid_functions": list(self.avoid_functions),
            "terminal_function": self.terminal_function,
            "intent_confidence": self.confidence,
        }


@dataclass(frozen=True)
class CandidateContext:
    element_id: str
    position: str
    parent_label: str
    nearby_text: str
    function_tags: tuple[str, ...]
    function_matches: tuple[tuple[str, float], ...]
    demonstration_support: float
    semantic_score: float

    def prompt_payload(self, candidate: UniversalNavigationCandidate) -> dict[str, object]:
        return {
            **candidate.model_dump(),
            "screen_position": self.position,
            "parent_label": self.parent_label,
            "nearby_text": self.nearby_text,
            "inferred_functions": list(self.function_tags),
            "function_match_scores": {key: round(score, 4) for key, score in self.function_matches},
            "android_control_support": round(self.demonstration_support, 4),
            "independent_semantic_score": round(self.semantic_score, 4),
        }


def infer_goal_plan(
    goal_text: str,
    catalog: NavigationFunctionCatalog | None = None,
) -> GoalPlan:
    resolved_catalog = catalog or get_navigation_function_catalog()
    catalog_plan = resolved_catalog.plan_goal(goal_text)
    goal = sanitize_text(goal_text).lower()
    # A reviewed fail-closed decision is a safety boundary, not a weak
    # semantic suggestion.  In particular, regulated actions whose ordinary
    # names contain "notification" (device-shortage notification, recall
    # notification, construction notification) must not be rewritten into
    # the consumer app-notification settings intent below.
    if catalog_plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT:
        return GoalPlan(
            intent=catalog_plan.intent,
            preferred_functions=catalog_plan.preferred_functions,
            avoid_functions=catalog_plan.avoid_functions,
            terminal_function=catalog_plan.terminal_function,
            confidence=catalog_plan.confidence,
        )
    if (
        _is_in_app_notification_settings_goal(goal)
        and resolved_catalog.function("notification.settings") is not None
        and not _catalog_has_more_specific_in_app_notification_intent(catalog_plan.intent)
    ):
        return _in_app_notification_settings_plan(resolved_catalog)
    if (
        _contains_any(goal, ("주문", "구매", "배송", "order", "purchase"))
        and _contains_any(goal, ("취소", "철회", "cancel", "withdraw"))
        and resolved_catalog.function("order.cancel.entry") is not None
    ):
        return GoalPlan(
            intent="order_cancellation",
            preferred_functions=(
                ("account.entry", 0.45),
                ("order.list", 0.72),
                ("order.cancel.entry", 1.0),
            ),
            avoid_functions=("refund.entry",),
            terminal_function="order.cancel.entry",
            confidence=0.99,
        )
    if (
        _contains_any(goal, ("보험", "생명", "손보", "insurance"))
        and _contains_any(goal, ("계약", "contract", "policy"))
        and _contains_any(goal, ("조회", "확인", "목록", "view", "check", "list"))
        and resolved_catalog.function("insurance.contract.list") is not None
    ):
        return GoalPlan(
            intent="insurance_contract_inquiry",
            preferred_functions=(
                ("insurance.hub", 0.48),
                ("account.entry", 0.62),
                ("insurance.contract.list", 1.0),
            ),
            terminal_function="insurance.contract.list",
            confidence=0.99,
        )
    if (
        _contains_any(goal, ("계정", "회원", "account"))
        and _contains_any(goal, ("삭제", "탈퇴", "폐쇄", "delete", "close"))
        and resolved_catalog.function("account.delete.entry") is not None
    ):
        return GoalPlan(
            intent="account_deletion",
            preferred_functions=(
                ("account.entry", 0.48),
                ("navigation.more", 0.54),
                ("settings.root", 0.62),
                ("account.settings", 0.72),
                ("account.personal_info", 0.82),
                ("account.delete.entry", 1.0),
            ),
            terminal_function="account.delete.entry",
            confidence=0.99,
        )
    if catalog_plan.intent != "generic_navigation":
        expanded_weights: dict[str, float] = dict(catalog_plan.preferred_functions)
        for function_id, weight in catalog_plan.preferred_functions:
            definition = resolved_catalog.function(function_id)
            if definition is None:
                continue
            for legacy_tag in definition.legacy_tags:
                # Broad legacy tags (for example ``privacy``) are fallback
                # evidence only. Letting them inherit a terminal function's
                # full weight makes every privacy-looking sibling tie at the
                # top and hides the catalog's precise function match.
                expanded_weights[legacy_tag] = max(
                    expanded_weights.get(legacy_tag, 0.0),
                    min(0.58, weight * 0.72),
                )
        return GoalPlan(
            intent=catalog_plan.intent,
            preferred_functions=tuple(expanded_weights.items()),
            avoid_functions=catalog_plan.avoid_functions,
            terminal_function=catalog_plan.terminal_function,
            confidence=catalog_plan.confidence,
        )
    cancellation = _contains_any(goal, ("해지", "취소", "자동결제", "비활성화", "cancel", "unsubscribe", "deactivate"))
    subscription = _contains_any(goal, ("구독", "멤버십", "프리미엄", "subscription", "membership", "premium"))
    recurring_payment = _contains_any(goal, ("자동결제", "자동 갱신", "auto renew", "recurring payment"))
    if cancellation and (subscription or recurring_payment):
        return GoalPlan(
            intent="subscription_cancellation",
            preferred_functions=(
                ("cancellation", 0.98),
                ("active_subscription", 0.94),
                ("billing_management", 0.84),
                ("account_entry", 0.68),
                ("settings", 0.54),
            ),
            avoid_functions=("content_subscriptions",),
        )
    account_deletion = (
        _contains_any(goal, ("회원 탈퇴", "계정 삭제", "delete account", "close account"))
        or (_contains_any(goal, ("계정", "account")) and _contains_any(goal, ("삭제", "지우", "delete", "remove")))
    )
    if account_deletion:
        return GoalPlan(
            intent="account_deletion",
            preferred_functions=(
                ("account_deletion", 0.99),
                ("account_entry", 0.72),
                ("privacy", 0.66),
                ("settings", 0.56),
            ),
        )
    if _contains_any(goal, ("마케팅", "광고 알림", "홍보", "marketing", "promotional")):
        return GoalPlan(
            intent="marketing_notification_control",
            preferred_functions=(
                ("marketing_control", 0.99),
                ("notifications", 0.84),
                ("settings", 0.66),
                ("account_entry", 0.50),
            ),
        )
    if _contains_any(goal, ("환불", "결제 취소", "refund")):
        return GoalPlan(
            intent="refund",
            preferred_functions=(
                ("refund", 0.99),
                ("purchase_history", 0.94),
                ("billing_management", 0.84),
                ("support", 0.60),
                ("account_entry", 0.48),
            ),
        )
    if _contains_any(goal, ("알림", "notification", "push")):
        return GoalPlan(
            intent="notification_control",
            preferred_functions=(("notifications", 0.94), ("settings", 0.68), ("account_entry", 0.50)),
        )
    if _contains_any(goal, ("개인정보", "내 데이터", "privacy", "personal data")):
        return GoalPlan(
            intent="privacy_control",
            preferred_functions=(("privacy", 0.94), ("settings", 0.66), ("account_entry", 0.54)),
        )
    return GoalPlan(
        intent="generic_navigation",
        preferred_functions=(("settings", 0.45), ("account_entry", 0.40), ("support", 0.34)),
    )


def _is_in_app_notification_settings_goal(goal: str) -> bool:
    """Recognize app-owned notification preferences without stealing inbox/system goals."""

    if not _contains_any(goal, ("알림", "notification", "push")):
        return False
    if _contains_any(
        goal,
        (
            "안드로이드",
            "android",
            "운영체제",
            "시스템 설정",
            "system settings",
            "system notification",
            "휴대폰 설정",
            "기기 설정",
            "설정 앱",
            "앱 정보",
            "app info",
            "알림 권한",
            "notification permission",
            "알림 채널",
            "notification channel",
            "알림 카테고리",
            "notification category",
            "이 앱 알림",
            "앱별 알림",
        ),
    ):
        return False
    # The noun phrase itself is stronger than wrapper verbs such as
    # "열고 싶어" or an app-name prefix such as "배달의민족".
    if _contains_any(
        goal,
        (
            "알림 설정",
            "알림설정",
            "알림 수신 설정",
            "알림수신설정",
            "notification settings",
            "notification preferences",
            "push notification settings",
        ),
    ):
        return True
    if _contains_any(
        goal,
        (
            "알림함",
            "알림 목록",
            "알림 내역",
            "새 알림",
            "받은 알림",
            "놓친 알림",
            "알림 피드",
            "notification inbox",
            "notifications inbox",
            "notification feed",
            "notifications feed",
            "activity feed",
        ),
    ):
        return False
    return _contains_any(
        goal,
        (
            "끄",
            "켜",
            "바꾸",
            "변경",
            "관리",
            "해제",
            "차단",
            "받지 않",
            "안 받",
            "turn off",
            "disable",
            "enable",
            "manage",
            "change",
            "configure",
            "mute",
        ),
    )


def _catalog_has_more_specific_in_app_notification_intent(intent: str) -> bool:
    """Keep reviewed notification subtypes such as marketing/email/quiet hours."""

    return "notification" in intent and not intent.startswith("android_")


def _in_app_notification_settings_plan(catalog: NavigationFunctionCatalog) -> GoalPlan:
    preferred: dict[str, float] = {
        "account.entry": 0.48,
        "settings.root": 0.70,
        "account.profile": 0.66,
        "notification.settings": 1.0,
    }
    for function_id, weight in tuple(preferred.items()):
        definition = catalog.function(function_id)
        if definition is None:
            continue
        for legacy_tag in definition.legacy_tags:
            preferred[legacy_tag] = max(
                preferred.get(legacy_tag, 0.0),
                min(0.58, weight * 0.72),
            )
    return GoalPlan(
        intent="notification_control",
        preferred_functions=tuple(preferred.items()),
        avoid_functions=("notification.service",),
        terminal_function="notification.settings",
        confidence=0.99,
    )


def rank_candidates(
    *,
    goal_text: str,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
    demonstrations: list[AndroidControlEvidence],
    catalog: NavigationFunctionCatalog | None = None,
) -> list[tuple[float, UniversalNavigationCandidate, CandidateContext]]:
    catalog = catalog or get_navigation_function_catalog()
    plan = infer_goal_plan(goal_text, catalog)
    contexts = candidate_contexts(
        request=request,
        candidates=candidates,
        demonstrations=demonstrations,
        plan=plan,
        catalog=catalog,
    )
    ranked = [
        (contexts[candidate.element_id].semantic_score, candidate, contexts[candidate.element_id])
        for candidate in candidates
    ]
    ranked.sort(key=lambda item: (-item[0], item[1].label, item[1].element_id))
    return ranked


def candidate_contexts(
    *,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
    demonstrations: list[AndroidControlEvidence],
    plan: GoalPlan | None = None,
    catalog: NavigationFunctionCatalog | None = None,
    allowed_function_ids: Iterable[str] | None = None,
) -> dict[str, CandidateContext]:
    catalog = catalog or get_navigation_function_catalog()
    plan = plan or infer_goal_plan(request.goal_text, catalog)
    elements_by_id = {element.id: element for element in request.screen.elements}
    max_bottom = max(
        (element.bounds[3] for element in request.screen.elements if element.bounds and element.bounds[3] > 0),
        default=0,
    )
    contexts: dict[str, CandidateContext] = {}
    for candidate in candidates:
        element = elements_by_id.get(candidate.element_id)
        position = _position(element.bounds if element is not None else None, max_bottom=max_bottom)
        parent = elements_by_id.get(element.parent_id) if element is not None and element.parent_id else None
        parent_label = "" if parent is None else sanitize_text(parent.text or parent.content_description)
        nearby_text = _nearby_text(request, element)
        # Nearby labels describe the screen, not the candidate itself. Folding
        # them into the candidate tags makes every sibling look like every
        # other sibling (for example, both "Deactivate" and "Payment" become
        # cancellation actions). Use only the candidate and its owning parent.
        context_text = " ".join((candidate.label, parent_label))
        tags = functional_tags(context_text)
        catalog_matches = catalog.match_candidate(
            label=candidate.label,
            parent_label=parent_label,
            # Sibling labels are screen context, not evidence about this
            # candidate.  Passing them here lets an adjacent paid-membership
            # card suppress a content-feed tab, or lets a destructive sibling
            # leak action meaning into an otherwise safe menu.
            nearby_text="",
            role=candidate.role,
            position=position,
            locale=request.locale,
            enabled=(element.enabled if element is not None else None),
            checkable=(element.checkable if element is not None else None),
            checked=(element.checked if element is not None else None),
            selected=(element.selected if element is not None else None),
            allowed_function_ids=allowed_function_ids,
            # A large cross-domain catalog can place a valid route gateway
            # outside the first few fuzzy matches. Keep enough alternatives
            # for the explorer's safety and route filters to decide.
            limit=16,
        )
        function_scores = {
            match.function_id: match.score
            for match in catalog_matches
            if match.score >= 0.34
        }
        for match in catalog_matches:
            if match.score < 0.42:
                continue
            tags.add(match.function_id)
            definition = catalog.function(match.function_id)
            if definition is not None:
                tags.update(definition.legacy_tags)
        if _is_subscription_feed_label(candidate.label) and (
            position == "bottom" or _looks_like_home_navigation(nearby_text)
        ):
            tags.add("content_subscriptions")
            tags.discard("billing_management")
        support = demonstration_support(candidate.label, tags, demonstrations)
        score = semantic_candidate_score(
            goal_text=request.goal_text,
            label=candidate.label,
            role=candidate.role,
            risk_level=candidate.risk_level,
            tags=tags,
            plan=plan,
            demonstration_support_value=support,
            function_scores=function_scores,
        )
        contexts[candidate.element_id] = CandidateContext(
            element_id=candidate.element_id,
            position=position,
            parent_label=parent_label,
            nearby_text=nearby_text,
            function_tags=tuple(sorted(tags)),
            function_matches=tuple(sorted(function_scores.items())),
            demonstration_support=support,
            semantic_score=score,
        )
    return contexts


def semantic_candidate_score(
    *,
    goal_text: str,
    label: str,
    role: str,
    risk_level: str,
    tags: set[str],
    plan: GoalPlan,
    demonstration_support_value: float,
    function_scores: dict[str, float] | None = None,
) -> float:
    lexical = text_similarity(goal_text, label)
    function_scores = function_scores or {}
    function_weight = max(
        (
            weight
            * (
                (match_score := function_scores.get(tag, 1.0 if tag in tags else 0.0))
                * (0.55 + 0.45 * match_score)
            )
            for tag, weight in plan.preferred_functions
        ),
        default=0.0,
    )
    avoid_score = max(
        (function_scores.get(tag, 1.0) for tag in plan.avoid_functions if tag in tags),
        default=0.0,
    )
    if avoid_score >= 0.76:
        return round(min(0.12, lexical * 0.10), 4)
    score = max(lexical * 0.46, function_weight)
    if demonstration_support_value:
        # Demonstrations strengthen evidence without flattening every strong
        # functional candidate to 1.0. Preserving the plan's ordering is what
        # keeps a direct "Deactivate" action ahead of a generic billing menu.
        score += demonstration_support_value * max(0.0, 1.0 - score) * 0.25
    if role.lower() in {"button", "menu", "menuitem", "tab", "switch"}:
        score += 0.025
    if risk_level == "medium" and not _goal_requests_state_change(goal_text):
        score -= 0.18
    if risk_level in {"high", "blocked"} and not _goal_requests_state_change(goal_text):
        score -= 0.35
    return round(max(0.0, min(1.0, score)), 4)


def demonstration_support(
    candidate_label: str,
    candidate_tags: set[str],
    demonstrations: Iterable[AndroidControlEvidence],
) -> float:
    candidate_terms = set(search_terms(candidate_label))
    best = 0.0
    for demonstration in demonstrations:
        action_text = " ".join((demonstration.step_instruction, demonstration.target_text))
        action_tags = functional_tags(action_text)
        tag_score = _set_overlap(candidate_tags, action_tags)
        lexical_score = _set_overlap(candidate_terms, set(search_terms(action_text)))
        support = demonstration.relevance * max(tag_score, lexical_score * 0.75)
        best = max(best, support)
    return round(min(1.0, best), 4)


def text_similarity(left: str, right: str) -> float:
    normalized_left = _normalize(left)
    normalized_right = _normalize(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return 0.9
    left_tokens = set(TOKEN_PATTERN.findall(left.lower()))
    right_tokens = set(TOKEN_PATTERN.findall(right.lower()))
    token_score = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return max(token_score, SequenceMatcher(None, normalized_left, normalized_right).ratio())


def _nearby_text(request: UniversalNavigationObserveRequest, target) -> str:
    if target is None:
        return ""
    labels: list[str] = []
    target_bounds = target.bounds
    for element in request.screen.elements:
        if element.id == target.id or not element.visible or element.password:
            continue
        label = sanitize_text(element.text or element.content_description)
        if not label:
            continue
        same_parent = target.parent_id is not None and element.parent_id == target.parent_id
        close = _bounds_distance(target_bounds, element.bounds) <= 260
        if same_parent or close:
            labels.append(label)
        if len(labels) >= 8:
            break
    return " | ".join(labels)[:600]


def _position(bounds: list[int] | None, *, max_bottom: int) -> str:
    if not bounds or max_bottom <= 0:
        return "unknown"
    center_y = (bounds[1] + bounds[3]) / 2
    ratio = center_y / max_bottom
    if ratio <= 0.25:
        return "top"
    if ratio >= 0.78:
        return "bottom"
    return "middle"


def _bounds_distance(left: list[int] | None, right: list[int] | None) -> float:
    if not left or not right:
        return float("inf")
    left_x, left_y = (left[0] + left[2]) / 2, (left[1] + left[3]) / 2
    right_x, right_y = (right[0] + right[2]) / 2, (right[1] + right[3]) / 2
    return ((left_x - right_x) ** 2 + (left_y - right_y) ** 2) ** 0.5


def _is_subscription_feed_label(label: str) -> bool:
    return _normalize(label) in {"구독", "subscriptions", "following"}


def _looks_like_home_navigation(value: str) -> bool:
    normalized = value.lower()
    markers = ("home", "shorts", "library", "홈", "내 페이지", "보관함")
    return sum(marker in normalized for marker in markers) >= 2


def _goal_requests_state_change(goal_text: str) -> bool:
    return _contains_any(
        goal_text.lower(),
        ("해지", "취소", "삭제", "탈퇴", "끄", "철회", "환불", "cancel", "delete", "disable", "refund"),
    )


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def _set_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def _normalize(value: str) -> str:
    return "".join(TOKEN_PATTERN.findall(value.lower()))
