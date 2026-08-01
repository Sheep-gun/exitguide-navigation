from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


REDACTED = "[REDACTED]"

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(
    r"(?<!\d)(?:"
    r"(?:\+?82[- .]?)?(?:0?(?:1[016789]|2|3[1-3]|4[1-4]|5[1-5]|6[1-4]|70))[- .]?\d{3,4}[- .]?\d{4}"
    r"|(?:1[2-9]\d{2})[- .]?\d{4}"
    r")(?!\d)"
)
_RESIDENT_ID = re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)")
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_ACCOUNT_HANDLE = re.compile(r"(?<![\w@])@[A-Za-z0-9_][A-Za-z0-9._]{1,29}(?![\w.])")
_KOREAN_ROAD_ADDRESS = re.compile(
    r"(?:[가-힣]{2,}(?:특별시|광역시|특별자치시|도|특별자치도)\s*)?"
    r"(?:[가-힣]{1,}(?:시|군|구)\s*)?"
    r"[가-힣0-9·.]{1,20}(?:로|길)\s*\d{1,4}(?:-\d{1,4})?"
)
_KOREAN_LOT_ADDRESS = re.compile(
    r"(?:[가-힣]{1,}(?:시|군|구)\s+)?[가-힣0-9·.]{1,20}(?:읍|면|동|리|가)\s+"
    r"(?:산\s*)?\d{1,4}(?:-\d{1,4})?"
)
_PERSONAL_NAME = re.compile(
    r"(?:이름|성명|예금주|수령인|받는\s*사람|피보험자|계약자|name)\s*[:：]?\s*"
    r"(?!(?:없(?:는|음)|미상)(?:\s|$)|(?:unknown|unavailable|missing|none|not\s+available)(?:\s|$))"
    r"(?:[가-힣]{2,5}|[A-Za-z][A-Za-z .'-]{1,50})",
    re.IGNORECASE,
)
_HONORIFIC_NAME = re.compile(r"(?<![가-힣])([가-힣]{2,5})\s*님(?![가-힣])")
_CURRENCY = re.compile(
    r"(?:[₩$€¥]\s*\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s*(?:원|KRW|USD|달러))",
    re.IGNORECASE,
)

_SECRET_PATTERNS = (
    re.compile(r"\bflp_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:sk|pk)_[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}\b"),
    re.compile(
        r"(?i)(?:api[_ -]?key|secret|access[_ -]?token|authorization)[\"']?\s*[=:]\s*[\"']?"
        r"(?:bearer\s+)?[A-Za-z0-9_./+~=-]{12,}"
    ),
)

_USERNAME_CONTEXT = (
    "사용자 이름",
    "사용자명",
    "계정 아이디",
    "회원 아이디",
    "로그인 아이디",
    "username",
    "user name",
    "account id",
)
_ADDRESS_CONTEXT = (
    "배송지",
    "배송 주소",
    "배달 주소",
    "현재 위치",
    "받는 곳",
    "도로명 주소",
    "지번 주소",
    "상세 주소",
    "shipping address",
    "delivery address",
    "current location",
)
_BALANCE_CONTEXT = (
    "잔액",
    "보유 금액",
    "보유금액",
    "출금 가능",
    "계좌 잔액",
    "청구 금액",
    "청구금액",
    "보험료",
    "balance",
    "available amount",
    "amount due",
)
_ORDER_CONTEXT = (
    "주문번호",
    "주문 번호",
    "주문 내역",
    "구매 내역",
    "배송 조회",
    "예약번호",
    "예약 번호",
    "order number",
    "order history",
    "purchase history",
    "booking number",
)
_INSURANCE_CONTEXT = (
    "보험 계약",
    "보험계약",
    "증권번호",
    "증권 번호",
    "계약번호",
    "계약 번호",
    "피보험자",
    "보험금",
    "청구 내역",
    "보상 내역",
    "insurance policy",
    "policy number",
    "claim number",
    "claim history",
)
_INSURANCE_IDENTIFIER_VALUE = re.compile(
    r"(?:증권\s*번호|계약\s*번호|policy\s*number|claim\s*number)"
    r"\s*[:：]?\s*[A-Za-z0-9][A-Za-z0-9._/-]{2,}",
    re.IGNORECASE,
)
_INSURANCE_AMOUNT_VALUE = re.compile(
    r"(?:보험료|보험금|청구\s*금액|보상\s*금액|premium|claim\s*amount)\s*[:：]?\s*"
    r"(?:[₩$€¥]\s*\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s*(?:원|KRW|USD|달러))",
    re.IGNORECASE,
)
_AUTH_CONTEXT = (
    "비밀번호",
    "인증번호",
    "일회용 비밀번호",
    "보안코드",
    "생체인증",
    "지문인증",
    "얼굴인증",
    "password",
    "passcode",
    "verification code",
    "one-time password",
    "otp",
    "biometric",
    "fingerprint",
    "face recognition",
)

_STRUCTURAL_FIELD_NAMES = frozenset(
    {
        "id",
        "record_id",
        "run_id",
        "screen_id",
        "element_id",
        "ui_element_id",
        "parent_id",
        "view_id",
        "transition_id",
        "goal_id",
        "failure_id",
        "metric_id",
        "api_ms",
        "annotation_id",
        "request_id",
        "session_id",
        "recommendation_id",
        "completed_task_ids",
        "fingerprint",
        "screen_fingerprint",
        "screen_signature",
        "sha256",
        "content_sha256",
        "resource_id",
        "resource_ids",
        "resource_ids_json",
        "element_key",
        "bounds",
        "bounds_json",
        "coordinates",
        "coordinates_json",
        "accessibility_tree_path",
        "screenshot_path",
        "tree_path",
        "artifact_path",
        "inventory_snapshot_path",
    }
)
_SEMANTIC_INTENT_FIELDS = frozenset(
    {
        "goal",
        "goal_text",
        "user_goal",
        "normalized_goal",
        "intent",
        "intent_text",
        "semantic_intent",
        "target_function",
        "target_function_id",
        "semantic_function_id",
        "function_name",
        "purpose",
        "purpose_text",
    }
)
_GENERIC_HONORIFICS = frozenset({"고객", "회원", "사용자", "여러분", "사장", "선생"})


def _normalize_field_name(field_name: str, path: str) -> str:
    candidate = (field_name or path.rsplit(".", 1)[-1]).strip().casefold()
    if candidate.endswith("[]"):
        candidate = candidate[:-2]
    return candidate


def is_structural_context(*, field_name: str = "", path: str = "") -> bool:
    field = _normalize_field_name(field_name, path)
    path_components = tuple(
        component
        for component in re.split(r"[.\[\]]+", (path or "").strip().casefold())
        if component
    )

    def structural_name(value: str) -> bool:
        return (
            value in _STRUCTURAL_FIELD_NAMES
            or value.endswith("_id")
            or value.endswith("_ids")
            or value.endswith("_path")
            or value.endswith("_key")
            or value.endswith("_ms")
            or value.endswith("_sha256")
            or value.endswith("_fingerprint")
            or value.endswith("_signature")
        )

    return structural_name(field) or any(structural_name(component) for component in path_components)


def is_semantic_intent_context(*, field_name: str = "", path: str = "") -> bool:
    field = _normalize_field_name(field_name, path)
    return field in _SEMANTIC_INTENT_FIELDS or field.endswith("_goal") or field.endswith("_intent")


def _luhn_valid(value: str) -> bool:
    digits = [int(character) for character in re.sub(r"\D", "", value)]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


@dataclass(frozen=True)
class PrivacyFinding:
    categories: tuple[str, ...]
    metadata_only: bool

    @property
    def safe_for_semantic_export(self) -> bool:
        return not self.metadata_only


def classify_human_text(
    text: object,
    *,
    field_name: str = "",
    path: str = "",
    structural: bool | None = None,
) -> PrivacyFinding:
    """Classify human-facing text without returning matched source values.

    Structural identifiers are exempt from numeric/handle heuristics, but
    embedded credentials remain blocked in every context.
    """

    value = "" if text is None else str(text)
    if not value:
        return PrivacyFinding((), False)

    categories: set[str] = set()
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        categories.add("secret")

    structural_context = is_structural_context(field_name=field_name, path=path) if structural is None else structural
    if structural_context:
        return PrivacyFinding(tuple(sorted(categories)), bool(categories))

    lowered = value.casefold()
    semantic_intent = is_semantic_intent_context(field_name=field_name, path=path)
    if _EMAIL.search(value):
        categories.add("email")
    if _PHONE.search(value):
        categories.add("phone")
    if _RESIDENT_ID.search(value):
        categories.add("korean_resident_id")
    if any(_luhn_valid(match.group()) for match in _CARD_CANDIDATE.finditer(value)):
        categories.add("payment_card")
    if _ACCOUNT_HANDLE.search(value) and not _EMAIL.search(value):
        categories.add("account_handle")
    if not semantic_intent and any(term in lowered for term in _USERNAME_CONTEXT):
        categories.add("account_identifier_context")
    if _KOREAN_ROAD_ADDRESS.search(value) or _KOREAN_LOT_ADDRESS.search(value):
        categories.add("postal_address")
    if not semantic_intent and any(term in lowered for term in _ADDRESS_CONTEXT):
        categories.add("location_or_address_context")
    if not semantic_intent and _PERSONAL_NAME.search(value):
        categories.add("personal_name")
    if not semantic_intent:
        for match in _HONORIFIC_NAME.finditer(value):
            if match.group(1) not in _GENERIC_HONORIFICS:
                categories.add("personal_name")
                break
    if not semantic_intent and _CURRENCY.search(value) and any(term in lowered for term in _BALANCE_CONTEXT):
        categories.add("financial_balance")
    if not semantic_intent and any(term in lowered for term in _ORDER_CONTEXT):
        categories.add("order_or_booking_data")
    # Generic navigation labels such as "보험 계약 조회" and "보험금 청구"
    # describe a feature, not a person's insurance data.  Require evidence of
    # an actual policy/claim identifier, insured person, amount, or history
    # value before classifying the text as private.
    if not semantic_intent and (
        _INSURANCE_IDENTIFIER_VALUE.search(value)
        or _INSURANCE_AMOUNT_VALUE.search(value)
        or (_PERSONAL_NAME.search(value) and "보험" in value)
    ):
        categories.add("insurance_data")
    if not semantic_intent and any(term in lowered for term in _AUTH_CONTEXT):
        categories.add("authentication_data")

    return PrivacyFinding(tuple(sorted(categories)), bool(categories))


def classify_human_values(
    values: Iterable[tuple[str, str, object]],
) -> PrivacyFinding:
    """Classify ``(field_name, path, value)`` triples as one screen/document."""

    categories: set[str] = set()
    for field_name, path, value in values:
        finding = classify_human_text(value, field_name=field_name, path=path)
        categories.update(finding.categories)
    return PrivacyFinding(tuple(sorted(categories)), bool(categories))


def redact_if_sensitive(
    text: object,
    *,
    field_name: str = "",
    path: str = "",
    structural: bool | None = None,
) -> str:
    finding = classify_human_text(
        text,
        field_name=field_name,
        path=path,
        structural=structural,
    )
    return REDACTED if finding.metadata_only else ("" if text is None else str(text))
