"""Pure, shared safety classification for physical-device auto actions.

The collector uses this module immediately before dispatching an action.  The
corpus validator imports the same *rules* but recomputes the decision from the
persisted transition and source element instead of trusting collector flags.
No function in this module performs I/O or retains the labels it evaluates.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Mapping


ACTION_GUARD_POLICY_VERSION = "egl-real-device-auto-action.v1"
ACTION_GUARD_EVALUATION_PHASE = "pre_execution"

_PLAIN_FINAL_ACTIONS = frozenset(
    {
        "해지",
        "해지하기",
        "탈퇴",
        "탈퇴하기",
        "삭제",
        "삭제하기",
        "비활성화",
        "결제",
        "결제하기",
        "구매",
        "구매하기",
        "제출",
        "제출하기",
        "신청",
        "신청하기",
        "청구",
        "청구하기",
        "취소",
        "취소하기",
        "환불",
        "환불하기",
        "송금",
        "이체",
        "출금",
        "동의",
        "동의하기",
        "철회",
        "철회하기",
        "발급",
        "발급하기",
        "pay",
        "pay now",
        "buy",
        "buy now",
        "purchase",
        "purchase now",
        "submit",
        "apply",
        "claim",
        "cancel",
        "confirm",
        "refund",
        "delete",
        "withdraw",
        "transfer",
        "send",
        "agree",
        "accept",
        "revoke",
        "issue",
    }
)

_FINAL_ACTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:회원|계정|프로필|개인정보|데이터).{0,12}(?:탈퇴|삭제|비활성화)(?:하기|확정|완료|요청|신청)?$",
        r"(?:구독|멤버십|무료\s*체험|요금제|플랜).{0,12}(?:해지|취소|종료)(?:하기|확정|완료|요청|신청)?$",
        r"(?:자동\s*결제|자동\s*갱신).{0,12}(?:해제|중지|끄기|취소)(?:하기|확정|완료)?$",
        r"(?:결제|구매|주문|예약|신청|청구|송금|이체|출금)(?:\s*(?:하기|확정|완료|제출|실행|보내기|요청))$",
        r"(?:삭제|탈퇴|해지|취소|환불|제출|동의|철회|발급|청구)(?:\s*(?:하기|확정|완료|신청|요청))$",
        r"^(?:pay|buy|purchase|place order|order|book|reserve|submit|send|transfer|withdraw)(?:\s+now)?$",
        r"^(?:delete|close|deactivate|remove)(?:\s+my)?\s+(?:account|profile|data)(?:\s+now)?$",
        r"^(?:cancel|end|terminate)(?:\s+my)?\s+(?:subscription|membership|trial|plan)(?:\s+now)?$",
        r"^(?:turn off|disable|cancel)\s+(?:auto[ -]?(?:pay|payment|renew|renewal))(?:\s+now)?$",
        r"^confirm\s+(?:payment|purchase|order|booking|reservation|deletion|cancellation|withdrawal|transfer|submission)$",
        r"^(?:request|confirm)\s+(?:a\s+)?(?:refund|cancellation|deletion|withdrawal)$",
        r"^(?:agree|accept|consent|revoke consent)(?:\s+and\s+continue)?$",
    )
)

_SAFE_KOREAN_TERMS = (
    "메뉴",
    "설정",
    "관리",
    "조회",
    "내역",
    "안내",
    "도움말",
    "고객센터",
    "마이페이지",
    # Exact branded profile gateway. Do not broaden this to every ``마이*``
    # label because that could admit consequential MyData controls.
    "마이배민",
    "내 페이지",
    "프로필",
    "계정",
    "개인정보",
    "알림",
    "보안",
    "구독",
    "멤버십",
    "더보기",
    "전체",
)

_SAFE_ENGLISH_TERMS = (
    "settings",
    "setting",
    "manage",
    "management",
    "details",
    "history",
    "help",
    "support",
    "profile",
    "account",
    "privacy",
    "notifications",
    "security",
    "subscriptions",
    "subscription",
    "membership",
    "more",
    "menu",
)

_SAFE_RESOURCE_TERMS = frozenset(
    {
        "menu",
        "setting",
        "settings",
        "profile",
        "account",
        "mypage",
        "my_page",
        "navigation",
        "drawer",
        "more",
        "help",
        "support",
        "history",
        "manage",
        "management",
        "privacy",
        "security",
        "subscription",
        "membership",
    }
)

# Accessibility nodes frequently expose an empty human-facing label while the
# Android resource ID still names the control.  These machine tokens are
# transient pre-dispatch evidence only; they must never be treated as a safe
# menu merely because the same ID also contains ``account`` or
# ``subscription``.
_FINAL_RESOURCE_TOKENS = frozenset(
    {
        "accept",
        "agree",
        "apply",
        "buy",
        "cancel",
        "claim",
        "confirm",
        "deactivate",
        "delete",
        "issue",
        "logout",
        "pay",
        "purchase",
        "refund",
        "remove",
        "revoke",
        "send",
        "signout",
        "submit",
        "terminate",
        "transfer",
        "unsubscribe",
        "withdraw",
        "withdrawal",
    }
)


def _resource_tokens(resource_id: object) -> set[str]:
    # Split camelCase before case-folding, then retain both compound and atomic
    # underscore tokens (e.g. ``delete_account`` and ``delete``).
    raw = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(resource_id or ""))
    resource = normalize_action_text(raw)
    tokens = {token for token in re.split(r"[^a-z0-9_]+", resource) if token}
    expanded = set(tokens)
    for token in tokens:
        expanded.update(part for part in token.split("_") if part)
    return expanded


def is_final_or_consequential_resource_id(resource_id: object) -> bool:
    """Classify an unnamed Android resource as a user-owned action."""

    tokens = _resource_tokens(resource_id)
    if tokens & _FINAL_RESOURCE_TOKENS:
        return True
    # ``close`` alone often means dismissing a harmless sheet.  It becomes a
    # terminal action only when the same resource identifies owned data.
    if "close" in tokens and tokens & {"account", "profile", "data"}:
        return True
    if "end" in tokens and tokens & {"subscription", "membership", "trial", "plan"}:
        return True
    if "disable" in tokens and tokens & {
        "auto",
        "autopay",
        "renew",
        "renewal",
        "subscription",
    }:
        return True
    if tokens & {"optout", "opt_out"} or {"opt", "out"}.issubset(tokens):
        return True
    # A bare payment execution resource is consequential, while explicit
    # management/history surfaces remain navigational.
    if "payment" in tokens and not tokens & {
        "details",
        "history",
        "manage",
        "management",
        "method",
        "methods",
        "setting",
        "settings",
    }:
        return True
    return False


def normalize_action_text(value: object) -> str:
    """Return a stable comparison form without mutating or persisting input."""

    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" \t\r\n.!?:;·•|/\\[](){}<>'\"")


def is_final_or_consequential_label(*labels: object) -> bool:
    """Classify a human-facing label conservatively as a user-owned action."""

    for label in labels:
        value = normalize_action_text(label)
        if not value:
            continue
        if value in _PLAIN_FINAL_ACTIONS:
            return True
        if any(pattern.search(value) for pattern in _FINAL_ACTION_PATTERNS):
            return True
    return False


def _contains_english_token(text: str, token: str) -> bool:
    escaped = re.escape(token).replace(r"\ ", r"[\s_-]+")
    return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text))


def is_safe_menu_or_settings_action(
    *,
    selected_label: object = "",
    element_labels: Iterable[object] = (),
    resource_id: object = "",
) -> bool:
    """Return whether evidence identifies an intermediate menu/settings hop.

    This result does not override :func:`is_final_or_consequential_label`.
    Callers must reject final/consequential actions even when their label also
    contains a word such as ``account`` or ``subscription``.
    """

    labels = (selected_label, *tuple(element_labels))
    for raw in labels:
        value = normalize_action_text(raw)
        if not value:
            continue
        if any(term in value for term in _SAFE_KOREAN_TERMS):
            return True
        if any(_contains_english_token(value, term) for term in _SAFE_ENGLISH_TERMS):
            return True

    resource = normalize_action_text(resource_id)
    if resource:
        expanded = _resource_tokens(resource_id)
        if expanded & _SAFE_RESOURCE_TERMS:
            return True
        if any(term in resource for term in ("my_page", "account_settings", "subscription_settings")):
            return True
    return False


@dataclass(frozen=True)
class AutoActionGuardDecision:
    action_type: str
    allowed: bool
    computed_final_or_consequential: bool
    safe_menu_match: bool
    reason: str

    def evidence(self) -> dict[str, object]:
        """Return label-free, pre-execution evidence suitable for persistence."""

        return {
            "policy_version": ACTION_GUARD_POLICY_VERSION,
            "evaluation_phase": ACTION_GUARD_EVALUATION_PHASE,
            "action_type": self.action_type,
            "allowed": self.allowed,
            "computed_final_or_consequential": self.computed_final_or_consequential,
            "safe_menu_match": self.safe_menu_match,
            "reason": self.reason,
        }


def evaluate_auto_action_guard(
    action_type: object,
    *,
    selected_label: object = "",
    element_labels: Iterable[object] = (),
    resource_id: object = "",
) -> AutoActionGuardDecision:
    """Evaluate one action using only its pre-dispatch structural evidence."""

    action = normalize_action_text(action_type).replace(" ", "_")
    labels = tuple(element_labels)
    final = is_final_or_consequential_label(
        selected_label, *labels
    ) or is_final_or_consequential_resource_id(resource_id)
    safe_menu = is_safe_menu_or_settings_action(
        selected_label=selected_label,
        element_labels=labels,
        resource_id=resource_id,
    )
    if action == "click":
        if final:
            return AutoActionGuardDecision(
                action, False, True, safe_menu, "final_or_consequential_action"
            )
        if not safe_menu:
            return AutoActionGuardDecision(
                action, False, False, False, "not_a_safe_menu_or_setting"
            )
        return AutoActionGuardDecision(
            action, True, False, True, "physical_safe_menu_navigation"
        )
    if action == "scroll_forward":
        return AutoActionGuardDecision(
            action, True, False, False, "physical_bounded_menu_scroll"
        )
    if action == "back":
        return AutoActionGuardDecision(
            action, True, False, False, "physical_bounded_back_navigation"
        )
    return AutoActionGuardDecision(
        action or "none", False, final, safe_menu, "unsupported_auto_action"
    )


def guard_evidence_matches(
    evidence: object,
    decision: AutoActionGuardDecision,
) -> bool:
    """Strictly compare persisted evidence with a recomputed decision."""

    expected = decision.evidence()
    if not isinstance(evidence, Mapping) or set(evidence) != set(expected):
        return False
    for key, expected_value in expected.items():
        actual = evidence.get(key)
        if isinstance(expected_value, bool):
            if type(actual) is not bool or actual is not expected_value:
                return False
        elif type(actual) is not type(expected_value) or actual != expected_value:
            return False
    return True
