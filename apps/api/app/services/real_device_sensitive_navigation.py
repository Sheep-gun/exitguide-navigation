"""Local-only navigation decisions for privacy-heightened Android apps.

Financial, health, conversation, property, and personal-content apps must not
send their screen semantics to an external model.  This module uses transient
Accessibility labels only to identify low-risk menu/settings hops, returns no
human text, and delegates the final action gate to the shared physical safety
classifier.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.services.real_device_action_safety import (
    AutoActionGuardDecision,
    evaluate_auto_action_guard,
    normalize_action_text,
)
from app.services.real_device_goal_candidates import (
    FAMILY_SIGNALS,
    SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES,
    SENSITIVE_SAFE_FAMILIES,
)


LOCAL_POLICY_VERSION = "egl-sensitive-local-navigation.v1"
NEUTRAL_DISCOVERY_FAMILY = "neutral_safe_gateway_discovery"
PERSISTED_GUARD_LABEL_BUCKET = "metadata safe menu gateway"

_GATEWAY_SIGNAL_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gateway.settings", ("설정", "settings", "setting")),
    ("gateway.menu", ("메뉴", "전체", "더보기", "menu", "more")),
    ("gateway.profile", ("마이", "내 페이지", "프로필", "profile", "my page")),
    ("gateway.account", ("계정", "account")),
    ("gateway.support", ("고객센터", "도움말", "support", "help")),
    # Baemin uses an app-branded profile/account gateway. Keep this exact;
    # accepting every ``마이*`` label would also admit unsafe MyData actions.
    ("gateway.profile", ("마이배민",)),
)

_RESOURCE_GATEWAY_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("resource.settings", ("settings", "setting")),
    ("resource.menu", ("menu", "drawer", "more", "navigation")),
    ("resource.profile", ("profile", "mypage", "my_page")),
    ("resource.account", ("account",)),
    ("resource.support", ("support", "help")),
)

# Labels are evaluated only in transient memory.  Only the returned enum is
# persisted by the collector.  Terms deliberately target content surfaces,
# not ordinary menu entries such as "보험 계약 조회".
_BOUNDARY_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "conversation_content_boundary",
        (
            "메시지 본문",
            "대화 내용",
            "채팅 내용",
            "최근 메시지",
            "message preview",
            "conversation preview",
            "chat history",
        ),
    ),
    (
        "financial_content_boundary",
        (
            "잔액",
            "보유 자산",
            "계좌번호",
            "거래내역",
            "입출금 내역",
            "송금하기",
            "이체하기",
            "매수",
            "매도",
            "balance",
            "portfolio",
            "account number",
            "transaction history",
            "transfer money",
        ),
    ),
    (
        "location_listing_content_boundary",
        (
            "관심 매물",
            "문의 내역",
            "매물 주소",
            "현재 위치",
            "property address",
            "saved listing",
            "inquiry history",
            "current location",
        ),
    ),
    (
        "health_insurance_content_boundary",
        (
            "계약자",
            "피보험자",
            "증권번호",
            "계약번호",
            "보장내용",
            "보험료 납입내역",
            "보험금 청구내역",
            "사고번호",
            "진료내역",
            "건강검진 결과",
            "진단명",
            "policy holder",
            "policy number",
            "claim history",
            "medical history",
            "diagnosis",
        ),
    ),
)


@dataclass(frozen=True)
class SensitiveLocalDecision:
    action: str
    element_id: str | None
    reason: str
    candidate_count: int
    score_bucket: str | None
    action_guard: AutoActionGuardDecision | None
    goal_family_id: str
    terminal_policy: str
    matched_signal_ids: tuple[str, ...] = ()
    semantic_commitment_sha256: str | None = None
    boundary_kind: str | None = None

    @property
    def allowed(self) -> bool:
        return self.action == "click" and self.action_guard is not None and self.action_guard.allowed

    def evidence(self) -> dict[str, Any]:
        """Label-free evidence safe for a metadata-only corpus."""

        return {
            "policy_version": LOCAL_POLICY_VERSION,
            "decision_source": "deterministic_local_transient_accessibility",
            "action": self.action,
            "reason": self.reason,
            "candidate_count": self.candidate_count,
            "score_bucket": self.score_bucket,
            "goal_family_id": self.goal_family_id,
            "terminal_policy": self.terminal_policy,
            "matched_signal_ids": list(self.matched_signal_ids),
            "selected_element_id": self.element_id,
            "semantic_commitment_sha256": self.semantic_commitment_sha256,
            "boundary_kind": self.boundary_kind,
            "persisted_guard_label_bucket": (
                PERSISTED_GUARD_LABEL_BUCKET if self.allowed else None
            ),
            "external_api_transfer_count": 0,
            "human_text_persisted": False,
            "action_guard": self.action_guard.evidence() if self.action_guard else None,
        }


@dataclass(frozen=True)
class SensitiveLocalGoalSignalEvidence:
    family_id: str
    matched_signal_ids: tuple[str, ...]
    element_id: str
    semantic_commitment_sha256: str
    terminal_policy: str
    control_bucket: str
    auto_navigation_allowed: bool
    action_guard: AutoActionGuardDecision

    def evidence(self) -> dict[str, Any]:
        return {
            "policy_version": LOCAL_POLICY_VERSION,
            "decision_source": "deterministic_local_transient_accessibility",
            "family_id": self.family_id,
            "matched_signal_ids": list(self.matched_signal_ids),
            "selected_element_id": self.element_id,
            "semantic_commitment_sha256": self.semantic_commitment_sha256,
            "terminal_policy": self.terminal_policy,
            "control_bucket": self.control_bucket,
            "auto_navigation_allowed": self.auto_navigation_allowed,
            "action_guard": self.action_guard.evidence(),
            "external_api_transfer_count": 0,
            "human_text_persisted": False,
        }


def _value(element: object, name: str, default: Any = None) -> Any:
    if isinstance(element, Mapping):
        return element.get(name, default)
    return getattr(element, name, default)


def _labels(element: object) -> tuple[str, ...]:
    values = (
        _value(element, "label", ""),
        _value(element, "text", ""),
        _value(element, "content_description", ""),
        _value(element, "inferred_label", ""),
    )
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _sensitive_action_guard(
    labels: tuple[str, ...], resource_id: str
) -> AutoActionGuardDecision:
    return evaluate_auto_action_guard(
        "click",
        selected_label=labels[0] if labels else "",
        element_labels=labels,
        resource_id=resource_id,
    )


def _hard_control_bucket(element: object, class_name: str) -> str:
    role = str(_value(element, "role", "") or "").casefold()
    if _value(element, "password", False) is True:
        return "password"
    if "edittext" in class_name or role == "text_field":
        return "text_field"
    if (
        _value(element, "checkable", False) is True
        or any(token in class_name for token in ("switch", "toggle", "checkbox"))
        or role in {"switch", "toggle", "checkbox"}
    ):
        return "checkable"
    return "clickable"


def _goal_signal_score(
    family_id: str, normalized_labels: Iterable[str]
) -> tuple[float, tuple[str, ...]]:
    score = 0.0
    signal_ids: set[str] = set()
    labels = tuple(normalized_labels)
    for signal in FAMILY_SIGNALS.get(family_id, ()):
        for phrase in signal.phrases:
            needle = normalize_action_text(phrase)
            if needle and any(needle in label for label in labels):
                score = max(score, 100.0 * signal.weight)
                signal_ids.add(signal.signal_id)
    return score, tuple(sorted(signal_ids))


def _gateway_score(
    normalized_labels: Iterable[str], resource_id: str
) -> tuple[float, tuple[str, ...]]:
    labels = tuple(normalized_labels)
    score = 0.0
    signal_ids: set[str] = set()
    for signal_id, terms in _GATEWAY_SIGNAL_TERMS:
        if any(
            (needle := normalize_action_text(term))
            and any(needle in label for label in labels)
            for term in terms
        ):
            score = max(score, 55.0)
            signal_ids.add(signal_id)
    resource = normalize_action_text(resource_id)
    for signal_id, tokens in _RESOURCE_GATEWAY_SIGNALS:
        if any(token in resource for token in tokens):
            score = max(score, 62.0)
            signal_ids.add(signal_id)
    return score, tuple(sorted(signal_ids))


def _score_bucket(score: float) -> str:
    if score >= 95.0:
        return "direct_goal_signal"
    if score >= 60.0:
        return "structural_gateway"
    return "generic_safe_gateway"


def _semantic_commitment(
    *,
    element_id: str,
    goal_family_id: str,
    normalized_labels: Iterable[str],
    resource_id: str,
    matched_signal_ids: Iterable[str],
) -> str:
    payload = json.dumps(
        {
            "element_id": element_id,
            "goal_family_id": goal_family_id,
            "labels": sorted(set(normalized_labels)),
            "resource_id": normalize_action_text(resource_id),
            "matched_signal_ids": sorted(set(matched_signal_ids)),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_sensitive_surface_boundary(elements: Iterable[object]) -> str | None:
    """Classify private/auth surfaces without returning their source text."""

    normalized_values: list[str] = []
    for element in elements:
        class_name = str(_value(element, "class_name", "") or "").casefold()
        role = str(_value(element, "role", "") or "").casefold()
        if (
            _value(element, "password", False) is True
            or "edittext" in class_name
            or role == "text_field"
        ):
            return "authentication_or_input_boundary"
        normalized_values.extend(
            value
            for value in (normalize_action_text(raw) for raw in _labels(element))
            if value
        )
    for boundary, terms in _BOUNDARY_TERMS:
        if any(
            (needle := normalize_action_text(term))
            and any(needle in value for value in normalized_values)
            for term in terms
        ):
            return boundary
    return None


def collect_sensitive_local_goal_signal_evidence(
    elements: Iterable[object],
) -> tuple[SensitiveLocalGoalSignalEvidence, ...]:
    """Extract governed family signal IDs without retaining their source text."""

    found: list[SensitiveLocalGoalSignalEvidence] = []
    for element in elements:
        element_id = str(
            _value(element, "element_id", _value(element, "id", "")) or ""
        ).strip()
        if (
            not element_id
            or _value(element, "clickable", False) is not True
            or _value(element, "enabled", False) is not True
            or _value(element, "visible", False) is not True
            or not _value(element, "bounds", None)
        ):
            continue
        labels = _labels(element)
        normalized_labels = tuple(normalize_action_text(value) for value in labels)
        resource_id = str(_value(element, "resource_id", "") or "")
        class_name = str(_value(element, "class_name", "") or "").casefold()
        control_bucket = _hard_control_bucket(element, class_name)
        guard = _sensitive_action_guard(labels, resource_id)
        for family_id in sorted(SENSITIVE_SAFE_FAMILIES):
            score, signal_ids = _goal_signal_score(family_id, normalized_labels)
            if score <= 0.0 or not signal_ids:
                continue
            terminal_policy = (
                "user_boundary"
                if family_id in SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES
                else "manifest_governed"
            )
            commitment = _semantic_commitment(
                element_id=element_id,
                goal_family_id=family_id,
                normalized_labels=normalized_labels,
                resource_id=resource_id,
                matched_signal_ids=signal_ids,
            )
            found.append(
                SensitiveLocalGoalSignalEvidence(
                    family_id=family_id,
                    matched_signal_ids=signal_ids,
                    element_id=element_id,
                    semantic_commitment_sha256=commitment,
                    terminal_policy=terminal_policy,
                    control_bucket=control_bucket,
                    auto_navigation_allowed=bool(
                        guard.allowed and control_bucket == "clickable"
                    ),
                    action_guard=guard,
                )
            )
    found.sort(key=lambda value: (value.family_id, value.element_id))
    return tuple(found)


def choose_sensitive_local_menu_action(
    elements: Iterable[object],
    *,
    goal_family_id: str,
) -> SensitiveLocalDecision:
    """Choose one safe local click without returning or retaining UI text."""

    family_id = str(goal_family_id or "").strip()
    neutral_discovery = not family_id or family_id == NEUTRAL_DISCOVERY_FAMILY
    effective_family_id = NEUTRAL_DISCOVERY_FAMILY if neutral_discovery else family_id
    terminal_policy = (
        "user_boundary"
        if family_id in SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES
        else "navigation_only"
    )
    if not neutral_discovery and family_id not in SENSITIVE_SAFE_FAMILIES:
        return SensitiveLocalDecision(
            action="stop",
            element_id=None,
            reason="goal_family_not_allowed_in_sensitive_scope",
            candidate_count=0,
            score_bucket=None,
            action_guard=None,
            goal_family_id=effective_family_id,
            terminal_policy=terminal_policy,
        )

    candidates: list[
        tuple[
            float,
            str,
            AutoActionGuardDecision,
            tuple[str, ...],
            str,
        ]
    ] = []
    direct_boundaries: list[
        tuple[
            float,
            str,
            AutoActionGuardDecision,
            tuple[str, ...],
            str,
        ]
    ] = []
    for element in elements:
        element_id = str(_value(element, "element_id", _value(element, "id", "")) or "").strip()
        labels = _labels(element)
        resource_id = str(_value(element, "resource_id", "") or "")
        class_name = str(_value(element, "class_name", "") or "").casefold()
        if (
            not element_id
            or _value(element, "clickable", False) is not True
            or _value(element, "enabled", False) is not True
            or _value(element, "visible", False) is not True
            or not _value(element, "bounds", None)
        ):
            continue
        normalized_labels = tuple(normalize_action_text(value) for value in labels)
        goal_score, goal_signal_ids = (
            (0.0, ())
            if neutral_discovery
            else _goal_signal_score(family_id, normalized_labels)
        )
        gateway_score, gateway_signal_ids = _gateway_score(
            normalized_labels, resource_id
        )
        score = max(goal_score, gateway_score)
        if score <= 0.0:
            continue
        matched_signal_ids = tuple(
            sorted(
                set(goal_signal_ids if goal_score >= gateway_score else ())
                | set(gateway_signal_ids if gateway_score >= goal_score else ())
            )
        )
        guard = _sensitive_action_guard(labels, resource_id)
        commitment = _semantic_commitment(
            element_id=element_id,
            goal_family_id=effective_family_id,
            normalized_labels=normalized_labels,
            resource_id=resource_id,
            matched_signal_ids=matched_signal_ids,
        )
        direct_goal_match = goal_score > 0.0 and goal_score >= gateway_score
        hard_control_boundary = (
            _hard_control_bucket(element, class_name) != "clickable"
        )
        if direct_goal_match and (hard_control_boundary or not guard.allowed):
            direct_boundaries.append(
                (
                    score,
                    element_id,
                    guard,
                    matched_signal_ids,
                    commitment,
                )
            )
            continue
        if hard_control_boundary:
            continue
        if not guard.allowed:
            continue
        candidates.append(
            (score, element_id, guard, matched_signal_ids, commitment)
        )

    if not candidates:
        if direct_boundaries:
            direct_boundaries.sort(key=lambda item: (-item[0], item[1]))
            score, element_id, guard, signal_ids, commitment = direct_boundaries[0]
            return SensitiveLocalDecision(
                action="stop",
                element_id=element_id,
                reason="sensitive_goal_entry_user_boundary",
                candidate_count=len(direct_boundaries),
                score_bucket=_score_bucket(score),
                action_guard=guard,
                goal_family_id=effective_family_id,
                terminal_policy="user_boundary",
                matched_signal_ids=signal_ids,
                semantic_commitment_sha256=commitment,
                boundary_kind="sensitive_goal_entry_user_boundary",
            )
        return SensitiveLocalDecision(
            action="stop",
            element_id=None,
            reason="no_safe_local_menu_candidate",
            candidate_count=0,
            score_bucket=None,
            action_guard=None,
            goal_family_id=effective_family_id,
            terminal_policy=terminal_policy,
        )
    candidates.sort(key=lambda item: (-item[0], item[1]))
    score, element_id, guard, signal_ids, commitment = candidates[0]
    return SensitiveLocalDecision(
        action="click",
        element_id=element_id,
        reason="safe_local_menu_candidate",
        candidate_count=len(candidates),
        score_bucket=_score_bucket(score),
        action_guard=guard,
        goal_family_id=effective_family_id,
        terminal_policy=terminal_policy,
        matched_signal_ids=signal_ids,
        semantic_commitment_sha256=commitment,
    )
