"""Deterministic goal-candidate inference for validated physical-device runs.

This module deliberately works one stage *after* collection and corpus
validation.  It consumes only privacy-attested, redacted Accessibility
semantics supplied by the caller.  Metadata-only observations can establish a
boundary, but can never contribute words, labels, or inferred functions.

The output is research-only shadow data.  It does not mutate the frozen V15
catalog and it cannot promote a V16--V20, V21, or V22+ catalog.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence


PROVENANCE = "real_device_observation_candidate"
REVIEW_STATUS = "unreviewed_candidate"
ROUTE_LIFECYCLE = "shadow"
CANONICAL_VERSION = "15.0.0"
SENSITIVE_LOCAL_POLICY_VERSION = "egl-sensitive-local-navigation.v1"

APPLICABILITY_STATES = frozenset(
    {"applicable", "not_applicable", "authentication_boundary", "unverified"}
)

# On a package whose inventory record carries any sensitivity category, goal
# inference is constrained to menu scopes that cannot reveal transactional or
# user-content data.  Final actions remain user-owned even in these scopes.
SENSITIVE_SAFE_FAMILIES = frozenset(
    {
        "signup",
        "login",
        "logout",
        "account_deletion",
        "subscription_manage",
        "subscription_change",
        "subscription_cancel",
        "free_trial_cancel",
        "autopay_off",
        "marketing_notifications_off",
        "optional_consent_withdrawal",
        "privacy_settings",
        "data_download_delete",
        "customer_support",
        "security_settings",
        "insurance_contract_lookup",
        "insurance_contract_change",
        "insurance_contract_cancel",
        "insurance_claim",
        "insurance_premium_lookup",
        "insurance_refund_lookup",
    }
)

# A sensitive insurance screen is useful as a destination candidate, but the
# destination itself can disclose contracts, claims, premiums, or personal
# identity.  Even lookup families that are navigation-only in the general
# manifest become user boundaries in this local-only scope.
SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES = frozenset(
    {
        "insurance_contract_lookup",
        "insurance_contract_change",
        "insurance_contract_cancel",
        "insurance_claim",
        "insurance_premium_lookup",
        "insurance_refund_lookup",
    }
)

# Signup and public help can remain reachable before authentication.  The
# login family itself is recorded as ``authentication_boundary`` when only a
# structural boundary (and no verified-redacted login label) was observed.
AUTH_PUBLIC_FAMILIES = frozenset({"signup", "customer_support"})

# Only families whose destination inherently acts on an existing account or
# protected record inherit a structural authentication boundary without a
# family-specific label.  A login wall observed somewhere in a mixed run is
# not evidence that every other family in the manifest is authentication
# gated.
AUTHENTICATION_GATED_FAMILIES = frozenset(
    {
        "logout",
        "account_deletion",
        "subscription_manage",
        "subscription_change",
        "subscription_cancel",
        "free_trial_cancel",
        "autopay_off",
        "payment_methods",
        "order_cancel_refund",
        "marketing_notifications_off",
        "optional_consent_withdrawal",
        "privacy_settings",
        "data_download_delete",
        "security_settings",
        "insurance_contract_lookup",
        "insurance_contract_change",
        "insurance_contract_cancel",
        "insurance_claim",
        "insurance_premium_lookup",
        "insurance_refund_lookup",
        "flight_booking_lookup",
        "flight_booking_cancel",
        "telecom_billing_lookup",
    }
)

# These families can be positively identified on the authentication surface
# itself.  Signup/help links are public controls, while a direct login label
# is stronger evidence than a structural boundary alone.
AUTH_SURFACE_APPLICABLE_FAMILIES = AUTH_PUBLIC_FAMILIES | frozenset({"login"})

GOAL_CANDIDATE_POLICY_VERSION = "egl-real-device-goal-candidates.v2"
GOAL_CANDIDATE_POLICY_DESCRIPTOR = {
    "policy_version": GOAL_CANDIDATE_POLICY_VERSION,
    "applicability_threshold": "0.7000",
    "authentication_boundary_sources": (
        "screen_login_state_boundary",
        "password_element",
        "sensitive_element",
        "edit_text_element",
    ),
    "privacy_redacted_element_policy": "semantic_exclusion_not_authentication",
    "authentication_gated_families": tuple(sorted(AUTHENTICATION_GATED_FAMILIES)),
    "authentication_surface_applicable_families": tuple(
        sorted(AUTH_SURFACE_APPLICABLE_FAMILIES)
    ),
    "candidate_provenance": PROVENANCE,
    "review_status": REVIEW_STATUS,
    "route_lifecycle": ROUTE_LIFECYCLE,
    "serving_allowed": False,
    "unsafe_action_auto_click_allowed": False,
    "final_action_auto_click_allowed": False,
}
GOAL_CANDIDATE_POLICY_SHA256 = hashlib.sha256(
    json.dumps(
        GOAL_CANDIDATE_POLICY_DESCRIPTOR,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
).hexdigest()


def goal_candidate_policy_attestation() -> dict[str, str]:
    """Return the immutable policy identity persisted across every lineage."""

    return {
        "version": GOAL_CANDIDATE_POLICY_VERSION,
        "sha256": GOAL_CANDIDATE_POLICY_SHA256,
    }

SUBSCRIPTION_CHAIN = (
    "subscription_manage",
    "subscription_change",
    "autopay_off",
    "subscription_cancel",
    "free_trial_cancel",
)

# Stable tie-break only.  Scores and explicit evidence still decide the normal
# ordering; this table makes equal-score output reproducible.
BASE_PRIORITY = {
    family_id: index
    for index, family_id in enumerate(
        (
            *SUBSCRIPTION_CHAIN,
            "signup",
            "login",
            "logout",
            "account_deletion",
            "payment_methods",
            "order_cancel_refund",
            "marketing_notifications_off",
            "optional_consent_withdrawal",
            "privacy_settings",
            "data_download_delete",
            "customer_support",
            "security_settings",
            "insurance_contract_lookup",
            "insurance_contract_change",
            "insurance_contract_cancel",
            "insurance_claim",
            "insurance_premium_lookup",
            "insurance_refund_lookup",
            "flight_booking_lookup",
            "flight_booking_cancel",
            "public_document_issuance",
            "telecom_billing_lookup",
        ),
        1,
    )
}


@dataclass(frozen=True)
class Signal:
    signal_id: str
    phrases: tuple[str, ...]
    weight: float = 1.0


@dataclass(frozen=True)
class GoalFamily:
    family_id: str
    terminal_policy: str
    signals: tuple[Signal, ...]
    negative_signals: tuple[Signal, ...] = ()


@dataclass(frozen=True)
class SemanticValue:
    """A privacy-attested semantic value from a verified-redacted screen."""

    value: str
    screen_id: str
    element_id: str | None = None
    field: str = ""


@dataclass(frozen=True)
class LocalSignalEvidence:
    """Label-free signal attestation emitted by the local sensitive policy."""

    family_id: str
    signal_ids: tuple[str, ...]
    screen_id: str
    element_id: str
    semantic_commitment_sha256: str
    policy_version: str = SENSITIVE_LOCAL_POLICY_VERSION
    source_metric_id: str = ""
    source_event_sequence: int = 0
    source_metric_payload_sha256: str = ""
    action_guard_sha256: str = ""
    terminal_policy: str = ""
    control_bucket: str = ""
    auto_navigation_allowed: bool = False


@dataclass(frozen=True)
class AppEvidence:
    app_package: str
    version_name: str | None
    version_code: str | None
    version_key: str
    sensitivity_categories: tuple[str, ...]
    semantic_values: tuple[SemanticValue, ...]
    verified_redacted_screen_ids: tuple[str, ...]
    metadata_only_screen_ids: tuple[str, ...]
    authentication_boundary_screen_ids: tuple[str, ...]
    local_signal_evidence: tuple[LocalSignalEvidence, ...] = ()


HermesReranker = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _signals(*items: tuple[str, Sequence[str], float] | tuple[str, Sequence[str]]) -> tuple[Signal, ...]:
    result: list[Signal] = []
    for item in items:
        signal_id = item[0]
        phrases = tuple(str(value) for value in item[1])
        weight = float(item[2]) if len(item) == 3 else 1.0
        result.append(Signal(signal_id, phrases, weight))
    return tuple(result)


# The phrases are conservative menu labels, not open-ended app/category
# guesses.  A family is applicable only after a direct redacted-UI match.
FAMILY_SIGNALS: dict[str, tuple[Signal, ...]] = {
    "signup": _signals(
        ("signup.direct", ("회원가입", "가입하기", "계정 만들기", "sign up", "create account", "register")),
    ),
    "login": _signals(
        ("login.direct", ("로그인", "sign in", "log in")),
    ),
    "logout": _signals(
        ("logout.direct", ("로그아웃", "sign out", "log out")),
    ),
    "account_deletion": _signals(
        ("account.delete", ("회원탈퇴", "계정 삭제", "계정 비활성화", "delete account", "close account", "deactivate account")),
    ),
    "subscription_manage": _signals(
        ("subscription.manage", ("구독 관리", "멤버십 관리", "정기 결제 관리", "manage subscription", "manage membership")),
        ("subscription.entry", ("구독 및 결제", "멤버십", "subscriptions", "membership", "premium"), 0.72),
    ),
    "subscription_change": _signals(
        ("subscription.change", ("구독 변경", "요금제 변경", "플랜 변경", "멤버십 변경", "change plan", "change subscription")),
    ),
    "subscription_cancel": _signals(
        ("subscription.cancel", ("구독 해지", "멤버십 해지", "구독 취소", "cancel subscription", "cancel membership", "end subscription")),
    ),
    "free_trial_cancel": _signals(
        ("trial.cancel", ("무료 체험 취소", "무료체험 취소", "체험 해지", "cancel free trial", "end trial")),
    ),
    "autopay_off": _signals(
        ("autopay.off", ("자동결제 해제", "자동 결제 해제", "자동 갱신 끄기", "정기 결제 해제", "turn off auto renew", "disable autopay", "stop automatic renewal")),
    ),
    "payment_methods": _signals(
        ("payment.methods", ("결제수단 관리", "결제 수단 관리", "결제 방법", "payment methods", "manage payment")),
    ),
    "order_cancel_refund": _signals(
        ("order.cancel_refund", ("주문 취소", "취소 환불", "반품 환불", "환불 신청", "cancel order", "request refund", "returns and refunds")),
    ),
    "marketing_notifications_off": _signals(
        ("marketing.off", ("마케팅 알림", "광고 알림", "혜택 알림", "프로모션 알림", "marketing notifications", "promotional messages", "ad notifications")),
    ),
    "optional_consent_withdrawal": _signals(
        ("consent.withdraw", ("선택 동의 철회", "동의 철회", "선택 정보 동의", "withdraw consent", "optional consent")),
    ),
    "privacy_settings": _signals(
        ("privacy.settings", ("개인정보 설정", "개인 정보 설정", "개인정보 보호", "privacy settings", "privacy controls")),
    ),
    "data_download_delete": _signals(
        ("data.download_delete", ("데이터 다운로드", "데이터 삭제", "내 정보 다운로드", "download your data", "delete your data", "data export")),
    ),
    "customer_support": _signals(
        ("support.entry", ("고객센터", "고객 지원", "문의하기", "도움말", "customer support", "help center", "contact us")),
    ),
    "security_settings": _signals(
        ("security.settings", ("보안 설정", "로그인 및 보안", "계정 보안", "security settings", "login and security", "account security")),
    ),
    "insurance_contract_lookup": _signals(
        ("insurance.contract_lookup", ("보험 계약 조회", "계약 조회", "내 보험 조회", "policy lookup", "view policy", "insurance contracts")),
    ),
    "insurance_contract_change": _signals(
        ("insurance.contract_change", ("보험 계약 변경", "계약 변경", "change policy", "policy changes")),
    ),
    "insurance_contract_cancel": _signals(
        ("insurance.contract_cancel", ("보험 계약 해지", "계약 해지", "cancel policy", "terminate policy")),
    ),
    "insurance_claim": _signals(
        ("insurance.claim", ("보험금 청구", "사고 접수", "claim insurance", "file a claim", "insurance claim")),
    ),
    "insurance_premium_lookup": _signals(
        ("insurance.premium", ("보험료 조회", "납입 보험료", "premium lookup", "insurance premium")),
    ),
    "insurance_refund_lookup": _signals(
        ("insurance.refund", ("환급금 조회", "보험 환급금", "refund lookup", "insurance refund")),
    ),
    "flight_booking_lookup": _signals(
        ("flight.booking_lookup", ("항공권 예약 조회", "예약 조회", "나의 예약", "my bookings", "view booking", "manage booking")),
    ),
    "flight_booking_cancel": _signals(
        ("flight.booking_cancel", ("항공권 예약 취소", "예약 취소", "cancel booking", "cancel flight")),
    ),
    "public_document_issuance": _signals(
        ("public.document", ("민원 서류 발급", "증명서 발급", "전자증명서", "issue certificate", "public document")),
    ),
    "telecom_billing_lookup": _signals(
        ("telecom.billing", ("통신요금 조회", "요금 조회", "이번 달 요금", "mobile bill", "billing details")),
    ),
}

FAMILY_NEGATIVE_SIGNALS: dict[str, tuple[Signal, ...]] = {
    family_id: _signals(
        ("subscription.none", ("활성 구독 없음", "구독 내역이 없습니다", "no active subscription", "not subscribed")),
    )
    for family_id in SUBSCRIPTION_CHAIN
}
FAMILY_NEGATIVE_SIGNALS.update(
    {
        "order_cancel_refund": _signals(
            ("order.none", ("주문 내역이 없습니다", "no orders", "no order history")),
        ),
        "flight_booking_lookup": _signals(
            ("booking.none", ("예약 내역이 없습니다", "no bookings", "no upcoming trips")),
        ),
        "flight_booking_cancel": _signals(
            ("booking.none", ("예약 내역이 없습니다", "no bookings", "no upcoming trips")),
        ),
        "insurance_contract_lookup": _signals(
            ("policy.none", ("보험 계약이 없습니다", "보유 계약 없음", "no policies", "no insurance contracts")),
        ),
        "insurance_contract_change": _signals(
            ("policy.none", ("보험 계약이 없습니다", "보유 계약 없음", "no policies", "no insurance contracts")),
        ),
        "insurance_contract_cancel": _signals(
            ("policy.none", ("보험 계약이 없습니다", "보유 계약 없음", "no policies", "no insurance contracts")),
        ),
    }
)


def normalize_semantics(value: object) -> str:
    text = unicodedata.normalize("NFKC", "" if value is None else str(value)).casefold()
    text = re.sub(r"[_./:#-]+", " ", text)
    return " ".join(text.split())


def canonical_sha256(value: object) -> str:
    """Hash a label-free evidence object using the artifact JSON contract."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def local_signal_evidence_ref(row: LocalSignalEvidence) -> dict[str, Any]:
    """Return the exact source-event reference carried by one candidate."""

    return {
        "source_metric_id": row.source_metric_id,
        "source_event_sequence": row.source_event_sequence,
        "source_metric_payload_sha256": row.source_metric_payload_sha256,
        "source_screen_id": row.screen_id,
        "source_element_id": row.element_id,
        "policy_version": row.policy_version,
        "family_id": row.family_id,
        "signal_ids": list(row.signal_ids),
        "semantic_commitment_sha256": row.semantic_commitment_sha256,
        "action_guard_sha256": row.action_guard_sha256,
        "terminal_policy": row.terminal_policy,
        "control_bucket": row.control_bucket,
        "auto_navigation_allowed": row.auto_navigation_allowed,
    }


def sensitive_evidence_attestation(
    rows: Sequence[LocalSignalEvidence],
) -> dict[str, Any]:
    """Build a deterministic root over every persisted local signal event."""

    refs = sorted(
        (local_signal_evidence_ref(row) for row in rows),
        key=lambda value: (
            int(value["source_event_sequence"]),
            str(value["source_metric_id"]),
            str(value["family_id"]),
            str(value["source_element_id"]),
        ),
    )
    event_refs = [
        {
            "source_metric_id": value["source_metric_id"],
            "source_event_sequence": value["source_event_sequence"],
            "source_metric_payload_sha256": value[
                "source_metric_payload_sha256"
            ],
        }
        for value in refs
    ]
    return {
        "schema_version": 1,
        "policy_version": SENSITIVE_LOCAL_POLICY_VERSION,
        "source_event_count": len(refs),
        "ordered_event_refs": event_refs,
        "evidence_root_sha256": canonical_sha256(refs),
        "external_api_transfer_count": 0,
        "human_text_persisted": False,
    }


def family_definitions(manifest: Mapping[str, Any]) -> tuple[GoalFamily, ...]:
    """Load governed family IDs/policies without trusting manifest labels."""

    rows: list[Mapping[str, Any]] = []
    for field in ("required_goal_families", "supplemental_goal_families"):
        values = manifest.get(field, [])
        if not isinstance(values, list):
            raise ValueError(f"{field} must be a list")
        for value in values:
            if not isinstance(value, Mapping):
                raise ValueError(f"{field} entries must be objects")
            rows.append(value)
    if not rows:
        raise ValueError("goal family manifest is empty")

    result: list[GoalFamily] = []
    seen: set[str] = set()
    allowed_policies = {
        "navigation_only",
        "user_boundary",
        "user_final_action",
        "mixed_user_owned",
    }
    for row in rows:
        family_id = str(row.get("family_id") or "").strip()
        terminal_policy = str(row.get("terminal_policy") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", family_id):
            raise ValueError("goal family id is invalid")
        if family_id in seen:
            raise ValueError("goal family ids must be unique")
        if terminal_policy not in allowed_policies:
            raise ValueError(f"unsupported terminal policy for {family_id}")
        signals = FAMILY_SIGNALS.get(family_id)
        if not signals:
            raise ValueError(f"no deterministic signal policy for {family_id}")
        seen.add(family_id)
        result.append(
            GoalFamily(
                family_id=family_id,
                terminal_policy=terminal_policy,
                signals=signals,
                negative_signals=FAMILY_NEGATIVE_SIGNALS.get(family_id, ()),
            )
        )
    return tuple(result)


def _match_signals(
    signals: Iterable[Signal], semantic_values: Sequence[SemanticValue]
) -> tuple[float, list[str], list[str], list[str]]:
    matched: list[tuple[Signal, SemanticValue]] = []
    for signal in signals:
        normalized_phrases = tuple(normalize_semantics(value) for value in signal.phrases)
        for semantic in semantic_values:
            normalized_value = normalize_semantics(semantic.value)
            if normalized_value and any(phrase and phrase in normalized_value for phrase in normalized_phrases):
                matched.append((signal, semantic))
                break
    if not matched:
        return 0.0, [], [], []
    unique_signals = {item[0].signal_id: item[0] for item in matched}
    score = min(1.0, max(signal.weight for signal in unique_signals.values()) + 0.03 * (len(unique_signals) - 1))
    screen_ids = sorted({item[1].screen_id for item in matched})
    element_ids = sorted({item[1].element_id for item in matched if item[1].element_id})
    return (
        round(score, 4),
        sorted(unique_signals),
        screen_ids,
        element_ids,
    )


def _match_local_signal_evidence(
    family: GoalFamily,
    evidence: AppEvidence,
    *,
    included_screen_ids: frozenset[str] | None = None,
) -> tuple[float, list[str], list[str], list[str], int]:
    rows = [
        row
        for row in evidence.local_signal_evidence
        if row.family_id == family.family_id
        and (
            included_screen_ids is None
            or row.screen_id in included_screen_ids
        )
    ]
    if not rows:
        return 0.0, [], [], [], 0
    if not evidence.sensitivity_categories:
        raise ValueError("local sensitive signal evidence requires a sensitive app")
    allowed = {signal.signal_id: signal for signal in family.signals}
    matched_ids: set[str] = set()
    screen_ids: set[str] = set()
    element_ids: set[str] = set()
    score = 0.0
    metadata_screen_ids = set(evidence.metadata_only_screen_ids)
    for row in rows:
        expected_terminal = (
            "user_boundary"
            if family.family_id in SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES
            else "manifest_governed"
        )
        if (
            row.policy_version != SENSITIVE_LOCAL_POLICY_VERSION
            or not row.signal_ids
            or any(signal_id not in allowed for signal_id in row.signal_ids)
            or row.screen_id not in metadata_screen_ids
            or not re.fullmatch(r"adb_[0-9a-f]{8,64}", row.element_id)
            or not re.fullmatch(r"[0-9a-f]{64}", row.semantic_commitment_sha256)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:+|/-]{0,299}", row.source_metric_id)
            or type(row.source_event_sequence) is not int
            or row.source_event_sequence < 1
            or not re.fullmatch(r"[0-9a-f]{64}", row.source_metric_payload_sha256)
            or not re.fullmatch(r"[0-9a-f]{64}", row.action_guard_sha256)
            or row.terminal_policy != expected_terminal
            or row.control_bucket
            not in {"clickable", "checkable", "password", "text_field"}
            or type(row.auto_navigation_allowed) is not bool
        ):
            raise ValueError("invalid local sensitive signal evidence")
        matched_ids.update(row.signal_ids)
        screen_ids.add(row.screen_id)
        element_ids.add(row.element_id)
        score = max(score, max(allowed[value].weight for value in row.signal_ids))
    return (
        round(min(1.0, score), 4),
        sorted(matched_ids),
        sorted(screen_ids),
        sorted(element_ids),
        len(rows),
    )


def _stable_id(value: Mapping[str, Any], length: int = 24) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _candidate_sort_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    state_order = {
        "applicable": 0,
        "authentication_boundary": 1,
        "not_applicable": 2,
        "unverified": 3,
    }
    family_id = str(candidate["family_id"])
    return (
        state_order[str(candidate["applicability_state"])],
        -float(candidate["confidence"]),
        BASE_PRIORITY.get(family_id, 10_000),
        family_id,
    )


def deterministic_candidates(
    evidence: AppEvidence,
    families: Sequence[GoalFamily],
) -> list[dict[str, Any]]:
    """Create one applicability record per governed goal family."""

    auth_screen_ids = frozenset(evidence.authentication_boundary_screen_ids)
    auth_boundary = bool(auth_screen_ids)
    non_boundary_semantics = tuple(
        value
        for value in evidence.semantic_values
        if value.screen_id not in auth_screen_ids
    )
    boundary_semantics = tuple(
        value
        for value in evidence.semantic_values
        if value.screen_id in auth_screen_ids
    )
    non_boundary_screen_ids = frozenset(
        set(evidence.verified_redacted_screen_ids)
        | set(evidence.metadata_only_screen_ids)
    ) - auth_screen_ids
    sensitive = bool(evidence.sensitivity_categories)
    candidates: list[dict[str, Any]] = []
    for family in families:
        semantic_score, semantic_signal_ids, semantic_screen_ids, semantic_element_ids = _match_signals(
            family.signals, non_boundary_semantics
        )
        (
            local_score,
            local_signal_ids,
            local_screen_ids,
            local_element_ids,
            local_evidence_count,
        ) = _match_local_signal_evidence(
            family,
            evidence,
            included_screen_ids=non_boundary_screen_ids,
        )
        (
            boundary_semantic_score,
            boundary_semantic_signal_ids,
            boundary_semantic_screen_ids,
            boundary_semantic_element_ids,
        ) = _match_signals(family.signals, boundary_semantics)
        (
            boundary_local_score,
            boundary_local_signal_ids,
            boundary_local_screen_ids,
            boundary_local_element_ids,
            boundary_local_evidence_count,
        ) = _match_local_signal_evidence(
            family,
            evidence,
            included_screen_ids=auth_screen_ids,
        )
        non_boundary_local_rows = sorted(
            (
                row
                for row in evidence.local_signal_evidence
                if row.family_id == family.family_id
                and row.screen_id in non_boundary_screen_ids
            ),
            key=lambda row: (
                row.source_event_sequence,
                row.source_metric_id,
                row.element_id,
            ),
        )
        boundary_local_rows = sorted(
            (
                row
                for row in evidence.local_signal_evidence
                if row.family_id == family.family_id
                and row.screen_id in auth_screen_ids
            ),
            key=lambda row: (
                row.source_event_sequence,
                row.source_metric_id,
                row.element_id,
            ),
        )
        local_refs = [
            local_signal_evidence_ref(row) for row in non_boundary_local_rows
        ]
        score = max(semantic_score, local_score)
        signal_ids = sorted(set(semantic_signal_ids) | set(local_signal_ids))
        screen_ids = sorted(set(semantic_screen_ids) | set(local_screen_ids))
        element_ids = sorted(set(semantic_element_ids) | set(local_element_ids))
        selected_semantic_score = semantic_score
        selected_local_score = local_score
        selected_local_evidence_count = local_evidence_count
        boundary_score = max(boundary_semantic_score, boundary_local_score)
        boundary_signal_ids = sorted(
            set(boundary_semantic_signal_ids) | set(boundary_local_signal_ids)
        )
        boundary_screen_ids = sorted(
            set(boundary_semantic_screen_ids) | set(boundary_local_screen_ids)
        )
        boundary_element_ids = sorted(
            set(boundary_semantic_element_ids) | set(boundary_local_element_ids)
        )
        if family.family_id in AUTH_SURFACE_APPLICABLE_FAMILIES:
            score = max(score, boundary_score)
            signal_ids = sorted(set(signal_ids) | set(boundary_signal_ids))
            screen_ids = sorted(set(screen_ids) | set(boundary_screen_ids))
            element_ids = sorted(set(element_ids) | set(boundary_element_ids))
            local_refs.extend(
                local_signal_evidence_ref(row) for row in boundary_local_rows
            )
            selected_semantic_score = max(
                selected_semantic_score, boundary_semantic_score
            )
            selected_local_score = max(selected_local_score, boundary_local_score)
            selected_local_evidence_count += boundary_local_evidence_count
        negative_score, negative_ids, negative_screen_ids, _ = _match_signals(
            family.negative_signals, non_boundary_semantics
        )
        restriction_reason: str | None = None
        if sensitive and family.family_id not in SENSITIVE_SAFE_FAMILIES:
            state = "unverified"
            confidence = 0.0
            signal_ids = []
            screen_ids = []
            element_ids = []
            restriction_reason = "sensitive_scope_forbidden"
            local_refs = []
        elif score >= 0.7:
            state = "applicable"
            confidence = score
        elif negative_score >= 0.7:
            state = "not_applicable"
            confidence = negative_score
            signal_ids = negative_ids
            screen_ids = negative_screen_ids
            element_ids = []
        elif auth_boundary and (
            boundary_score >= 0.7
            or family.family_id in AUTHENTICATION_GATED_FAMILIES
            or family.family_id == "login"
        ):
            state = "authentication_boundary"
            confidence = 1.0
            restriction_reason = "authentication_required"
            if boundary_score >= 0.7:
                signal_ids = boundary_signal_ids
                screen_ids = boundary_screen_ids
                element_ids = boundary_element_ids
                local_refs = [
                    local_signal_evidence_ref(row) for row in boundary_local_rows
                ]
                selected_semantic_score = boundary_semantic_score
                selected_local_score = boundary_local_score
                selected_local_evidence_count = boundary_local_evidence_count
        else:
            state = "unverified"
            confidence = 0.0
            restriction_reason = (
                "metadata_only_no_semantic_inference"
                if evidence.metadata_only_screen_ids and not evidence.verified_redacted_screen_ids
                else "insufficient_verified_redacted_evidence"
            )

        effective_terminal_policy = (
            "user_boundary"
            if sensitive
            and family.family_id in SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES
            else family.terminal_policy
        )
        final_user_owned = effective_terminal_policy in {
            "user_boundary",
            "user_final_action",
            "mixed_user_owned",
        }
        candidate = {
            "candidate_id": "goal_"
            + _stable_id(
                {
                    "package": evidence.app_package,
                    "version_key": evidence.version_key,
                    "family_id": family.family_id,
                }
            ),
            "family_id": family.family_id,
            "applicability_state": state,
            "confidence": round(confidence, 4),
            "terminal_policy": effective_terminal_policy,
            "terminal_action_owner": "user" if final_user_owned else "navigation_only",
            "final_action_auto_click_allowed": False,
            "unsafe_action_auto_click_allowed": False,
            "evidence_signal_ids": signal_ids,
            "source_screen_ids": screen_ids,
            "source_element_ids": element_ids,
            "local_signal_evidence_count": selected_local_evidence_count,
            "sensitive_evidence_refs": local_refs,
            "evidence_source_mode": (
                "verified_redacted_and_sensitive_local_signal_ids"
                if selected_semantic_score > 0.0 and selected_local_score > 0.0
                else "sensitive_local_signal_ids"
                if selected_local_score > 0.0
                else "verified_redacted_semantics"
                if selected_semantic_score > 0.0
                else "none"
            ),
            "restriction_reason_code": restriction_reason,
            "provenance": PROVENANCE,
            "review_status": REVIEW_STATUS,
            "route_lifecycle": ROUTE_LIFECYCLE,
            "serving_allowed": False,
            "human_review_required": True,
        }
        if candidate["applicability_state"] not in APPLICABILITY_STATES:
            raise AssertionError("invalid applicability state")
        candidates.append(candidate)
    candidates.sort(key=_candidate_sort_key)
    for index, candidate in enumerate(candidates, 1):
        candidate["rank"] = index
    return candidates


def _ambiguity_group(candidates: Sequence[Mapping[str, Any]]) -> list[str]:
    applicable = [item for item in candidates if item.get("applicability_state") == "applicable"]
    if len(applicable) < 2:
        return []
    top_score = float(applicable[0].get("confidence", 0.0))
    group = [
        str(item["family_id"])
        for item in applicable
        if top_score - float(item.get("confidence", 0.0)) <= 0.05
        and item.get("evidence_signal_ids")
    ]
    return group if len(group) >= 2 else []


def hermes_request(
    app_package: str,
    candidates: Sequence[Mapping[str, Any]],
    ambiguity_group: Sequence[str],
    semantic_values: Sequence[SemanticValue],
) -> dict[str, Any]:
    """Return a candidate-ID-only Hermes tool request.

    Only privacy-attested verified-redacted menu values relevant to the tied
    families are included.  K-EXAONE cannot invent families, change
    applicability, or see metadata-only content.
    """

    by_family = {str(item["family_id"]): item for item in candidates}
    summaries = [
        {
            "family_id": family_id,
            "confidence": by_family[family_id]["confidence"],
            "terminal_policy": by_family[family_id]["terminal_policy"],
            "evidence_signal_ids": list(by_family[family_id]["evidence_signal_ids"]),
            "subscription_chain_position": (
                SUBSCRIPTION_CHAIN.index(family_id) + 1
                if family_id in SUBSCRIPTION_CHAIN
                else None
            ),
        }
        for family_id in ambiguity_group
    ]
    relevant_phrases = tuple(
        normalize_semantics(phrase)
        for family_id in ambiguity_group
        for signal in FAMILY_SIGNALS.get(family_id, ())
        for phrase in signal.phrases
    )
    verified_redacted_menu_semantics: list[str] = []
    for semantic in semantic_values:
        normalized = normalize_semantics(semantic.value)
        if (
            normalized
            and any(phrase and phrase in normalized for phrase in relevant_phrases)
            and semantic.value not in verified_redacted_menu_semantics
        ):
            verified_redacted_menu_semantics.append(semantic.value[:500])
    verified_redacted_menu_semantics = verified_redacted_menu_semantics[:50]
    return {
        "format": "hermes_tool_call",
        "model_role": "K-EXAONE",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Reorder only the supplied tied goal family IDs. "
                    "Do not add, remove, or modify candidates."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "app_package": app_package,
                        "tied_candidates": summaries,
                        "verified_redacted_menu_semantics": verified_redacted_menu_semantics,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "rank_goal_candidates",
                    "description": "Order the supplied tied goal family IDs.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ordered_family_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            }
                        },
                        "required": ["ordered_family_ids"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "rank_goal_candidates"},
        },
    }


def _hermes_order(response: Mapping[str, Any]) -> list[str]:
    name: object = response.get("name")
    arguments: object = response.get("arguments")
    tool_calls = response.get("tool_calls")
    if isinstance(tool_calls, list) and len(tool_calls) == 1 and isinstance(tool_calls[0], Mapping):
        function = tool_calls[0].get("function")
        if isinstance(function, Mapping):
            name = function.get("name")
            arguments = function.get("arguments")
    if name != "rank_goal_candidates":
        raise ValueError("unexpected Hermes tool name")
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, Mapping):
        raise ValueError("Hermes tool arguments must be an object")
    ordered = arguments.get("ordered_family_ids")
    if not isinstance(ordered, list) or any(not isinstance(value, str) for value in ordered):
        raise ValueError("Hermes ordering must be a string list")
    return list(ordered)


def rank_with_optional_hermes(
    app_package: str,
    candidates: list[dict[str, Any]],
    reranker: HermesReranker | None,
    semantic_values: Sequence[SemanticValue] = (),
) -> dict[str, Any]:
    """Use K-EXAONE only for a genuine deterministic tie.

    Any absent, failing, or non-Hermes response preserves deterministic order
    and emits a stable fallback reason code (never an exception body).
    """

    group = _ambiguity_group(candidates)
    metric = {
        "eligible_ambiguity": bool(group),
        "ambiguity_candidate_count": len(group),
        "attempted": False,
        "used": False,
        "deterministic_fallback_used": False,
        "fallback_reason_code": "not_ambiguous",
        "raw_menu_semantics_sent": False,
        "verified_redacted_menu_semantics_sent_count": 0,
        "request_semantics": "candidate_ids_signal_ids_and_verified_redacted_menu_semantics",
    }
    if not group:
        return metric
    if reranker is None:
        metric.update(
            {
                "deterministic_fallback_used": True,
                "fallback_reason_code": "reranker_not_configured",
            }
        )
        return metric

    metric["attempted"] = True
    request = hermes_request(app_package, candidates, group, semantic_values)
    try:
        user_payload = json.loads(str(request["messages"][1]["content"]))
        metric["verified_redacted_menu_semantics_sent_count"] = len(
            user_payload.get("verified_redacted_menu_semantics", [])
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        metric.update(
            {
                "deterministic_fallback_used": True,
                "fallback_reason_code": "reranker_request_invalid",
            }
        )
        return metric
    try:
        response = reranker(request)
        if not isinstance(response, Mapping):
            raise ValueError("reranker response is not an object")
        ordered = _hermes_order(response)
        if len(ordered) != len(group) or set(ordered) != set(group):
            raise ValueError("reranker changed the candidate set")
    except Exception:
        metric.update(
            {
                "deterministic_fallback_used": True,
                "fallback_reason_code": "reranker_invalid_or_failed",
            }
        )
        return metric

    positions = {family_id: index for index, family_id in enumerate(ordered)}
    original_positions = {str(item["family_id"]): index for index, item in enumerate(candidates)}
    candidates.sort(
        key=lambda item: (
            0 if str(item["family_id"]) in positions else 1,
            positions.get(str(item["family_id"]), original_positions[str(item["family_id"])]),
            original_positions[str(item["family_id"])],
        )
    )
    for index, candidate in enumerate(candidates, 1):
        candidate["rank"] = index
    metric.update(
        {
            "used": True,
            "fallback_reason_code": None,
        }
    )
    return metric


def generate_app_candidate_set(
    evidence: AppEvidence,
    families: Sequence[GoalFamily],
    *,
    hermes_reranker: HermesReranker | None = None,
) -> dict[str, Any]:
    family_ids = {family.family_id for family in families}
    if any(
        row.family_id not in family_ids for row in evidence.local_signal_evidence
    ):
        raise ValueError("local sensitive signal family is outside the governed manifest")
    candidates = deterministic_candidates(evidence, families)
    if evidence.sensitivity_categories:
        # Sensitive apps never transfer even redacted menu semantics to an
        # external model.  Ordering remains deterministic and local.
        ambiguity_group = _ambiguity_group(candidates)
        reranker_metric = {
            "eligible_ambiguity": bool(ambiguity_group),
            "ambiguity_candidate_count": len(ambiguity_group),
            "attempted": False,
            "used": False,
            "deterministic_fallback_used": bool(ambiguity_group),
            "fallback_reason_code": "sensitive_local_only",
            "raw_menu_semantics_sent": False,
            "verified_redacted_menu_semantics_sent_count": 0,
            "request_semantics": "none_sensitive_local_only",
            "external_api_transfer_count": 0,
        }
    else:
        reranker_metric = rank_with_optional_hermes(
            evidence.app_package,
            candidates,
            hermes_reranker,
            evidence.semantic_values,
        )
    by_family = {str(item["family_id"]): item for item in candidates}
    subscription_chain = [
        {
            "position": position,
            "family_id": family_id,
            "applicability_state": by_family[family_id]["applicability_state"],
            "candidate_id": by_family[family_id]["candidate_id"],
        }
        for position, family_id in enumerate(SUBSCRIPTION_CHAIN, 1)
        if family_id in by_family
        and by_family[family_id]["applicability_state"] == "applicable"
    ]
    return {
        "app_package": evidence.app_package,
        "version_name": evidence.version_name,
        "version_code": evidence.version_code,
        "version_key": evidence.version_key,
        "sensitivity_categories": list(evidence.sensitivity_categories),
        "sensitive_scope_policy_applied": bool(evidence.sensitivity_categories),
        "sensitive_evidence_attestation": (
            sensitive_evidence_attestation(evidence.local_signal_evidence)
            if evidence.sensitivity_categories
            else None
        ),
        "evidence_summary": {
            "verified_redacted_screen_count": len(evidence.verified_redacted_screen_ids),
            "metadata_only_screen_count": len(evidence.metadata_only_screen_ids),
            "authentication_boundary_screen_count": len(
                evidence.authentication_boundary_screen_ids
            ),
            "verified_semantic_value_count": len(evidence.semantic_values),
            "metadata_only_semantics_used": 0,
            "sensitive_local_signal_evidence_count": len(
                evidence.local_signal_evidence
            ),
        },
        "goal_candidates": candidates,
        "subscription_chain": subscription_chain,
        "hermes_k_exaone": reranker_metric,
        "provenance": PROVENANCE,
        "review_status": REVIEW_STATUS,
        "route_lifecycle": ROUTE_LIFECYCLE,
        "serving_allowed": False,
        "human_review_required": True,
        "goal_candidate_policy": goal_candidate_policy_attestation(),
    }
