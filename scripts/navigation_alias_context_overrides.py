from __future__ import annotations

"""Deterministic context guards for ambiguous, exact UI labels.

This module deliberately changes only ``positive_context`` and
``negative_context``.  It does not rename functions, add aliases, copy goal
sentences, or encode an app/package/coordinate.  The development fixture made
from this module is catalog-derived and tuning-allowed; it is not evidence of
unseen-app accuracy.
"""

import copy
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Mapping, Sequence


OVERRIDE_VERSION = "1.1.0"
FIXTURE_VERSION = "1.0.0"

# Product names are poor disambiguators: a reusable navigation ontology should
# recognize the surrounding UI meaning, not memorize which app emitted it.
_BRAND_MARKERS = {
    "youtube", "netflix", "spotify", "instagram", "facebook", "twitter",
    "tiktok", "kakao", "naver", "coupang", "baemin", "배민", "배달의민족",
    "제주항공", "google", "apple", "samsung", "삼성", "toss", "토스",
    "airbnb", "doordash", "uber", "lyft", "github", "slack", "zoom",
}
_GENERIC_CONTEXTS = {
    "menu", "main menu", "settings", "setting", "options", "option",
    "account", "profile", "home", "more", "service", "services", "관리",
    "메뉴", "설정", "계정", "프로필", "홈", "더보기", "서비스", "전체 메뉴",
}
_COORDINATE_RE = re.compile(
    r"(?:\bx\s*[=:]\s*\d+|\by\s*[=:]\s*\d+|\b\d+\s*[,x]\s*\d+\b|\b(?:top|bottom|left|right)\s*\d+\b)",
    flags=re.IGNORECASE,
)

# A few legacy owners expose only a generic or alias-identical context.  These
# are short, app-independent screen descriptions authored from the function's
# UI consequence.  They are context evidence, not alternate button labels.
_FALLBACK_POSITIVE_CONTEXTS: dict[tuple[str, str], str] = {
    ("shopping.cart", "ko"): "담아 둔 상품의 수량과 배송 전 주문 금액",
    ("account.profile", "ko"): "이름과 연락처를 확인하는 사용자 기본 신원 영역",
    ("privacy.consent", "ko"): "개인정보 수집 목적과 선택 항목별 허용 상태",
    ("onboarding.complete", "ko"): "초기 설정 항목을 모두 검토한 뒤 서비스 이용 준비 완료",
    ("tax.hub", "ko"): "신고 납부 환급 내역을 모아 보는 세무 업무 영역",
}

# These owners are especially close to another ontology node (for example a
# refund entry versus a pre-shipment order cancellation).  A consequence-rich
# screen phrase is more realistic and more discriminative than a generic word
# such as "payment", "SMS", or "profile".
_PREFERRED_POSITIVE_CONTEXTS: dict[tuple[str, str], str] = {
    ("commerce.cart", "ko"): "담아 둔 상품 수량과 주문 예상 금액 확인",
    ("commerce.cart", "en"): "items saved for checkout with quantities and order subtotal",
    ("refund.entry", "ko"): "결제 완료된 주문의 환불 사유와 반환 예정 금액",
    ("refund.entry", "en"): "refund reason and expected repayment for a completed purchase",
    ("insurance.contract.list", "ko"): "피보험자 계약번호 보험기간 납입 상태 목록",
    ("insurance.contract.list", "en"): "policyholder contract numbers coverage periods and payment status",
    ("billing.manage", "ko"): "결제 수단 영수증 구매 내역을 한곳에서 관리",
    ("billing.manage", "en"): "payment methods receipts and purchase history management",
    ("subscription.manage", "ko"): "갱신일 요금제 멤버십 이용 상태 관리",
    ("subscription.manage", "en"): "renewal date plan and active membership status",
    ("security.two_factor", "ko"): "인증 앱 복구 코드 보안 키를 이용한 추가 보호 설정",
    ("security.two_factor", "en"): "authenticator recovery codes and security key protection",
    ("communication.conversation.archive", "ko"): "대화를 삭제하지 않고 받은편지함에서 숨겨 보관",
    ("communication.conversation.archive", "en"): "hide a conversation from the inbox without deleting its messages",
    ("shopping.cancel_order", "ko"): "배송 시작 전 주문 상태와 취소 가능 여부 확인",
    ("shopping.cancel_order", "en"): "order status and cancellation eligibility before shipment",
    ("delivery.instructions", "ko"): "배달 기사에게 전달할 공동현관 출입과 문 앞 요청",
    ("delivery.instructions", "en"): "entrance access and doorstep notes for the delivery courier",
    ("messaging.delete", "ko"): "선택한 채팅 기록을 지우기 전 삭제 범위 확인",
    ("messaging.delete", "en"): "review the deletion scope for the selected chat history",
    ("hr_payroll.tax_documents", "ko"): "고용주가 발급한 과세연도 소득 원천징수 서류",
    ("hr_payroll.tax_documents", "en"): "employer issued tax year income and withholding documents",
    ("account.profile", "ko"): "이름 연락처 사진 등 현재 사용자 신원 정보 확인",
    ("account.profile", "en"): "current user identity details including name contact and photo",
    ("account.personal_info", "ko"): "생년월일 주소 연락처 등 계정 소유자 기본 정보",
    ("account.personal_info", "en"): "account owner details including birth date address and contact",
    ("privacy.consent", "ko"): "개인정보 수집 목적과 선택 항목별 허용 상태",
    ("privacy.consent", "en"): "permission status for each optional personal data purpose",
    ("healthcare_provider.hub", "ko"): "병원 진료 의뢰와 환자 임상 기록 업무 모음",
    ("healthcare_provider.hub", "en"): "hospital referrals patient portal and clinical record services",
    ("marketplace.favorites", "ko"): "판매자 상품의 가격 변동과 판매 상태를 저장해 확인",
    ("marketplace.favorites", "en"): "saved seller listings with price changes and sale status",
    ("media.quality", "ko"): "재생 데이터 사용량에 따른 영상 해상도 선택",
    ("media.quality", "en"): "video playback resolution based on streaming data usage",
    ("restaurant_booking.cancel", "ko"): "식당 좌석 인원과 기존 예약의 취소 조건 확인",
    ("restaurant_booking.cancel", "en"): "cancellation terms for an existing restaurant table reservation",
    ("family_store.purchase_approval", "ko"): "가족 그룹의 앱 콘텐츠 구매 요청 가격과 승인자 확인",
    ("family_store.purchase_approval", "en"): "price and approver for a child content purchase request in the family group",
    ("messaging.archive", "ko"): "문자 대화 목록을 삭제하지 않고 보관함으로 이동",
    ("messaging.archive", "en"): "move a text conversation to the archive without deleting it",
    ("shopping_logistics.hub", "ko"): "주문 장바구니 배송 반품을 모아 보는 쇼핑 기능",
    ("shopping_logistics.hub", "en"): "shopping area for orders carts shipping and returns",
    ("calls.hub", "ko"): "발신 수신 통화 기록과 전화번호 기능 모음",
    ("calls.hub", "en"): "phone calls dialed received numbers and call history",
    ("health.medications", "ko"): "처방받은 약 이름 복용 용량과 일정 목록",
    ("health.medications", "en"): "prescribed medicine names dosages and medication schedule",
    ("tax.documents", "ko"): "공공기관에서 발급하는 소득 증명과 세무 민원 서류",
    ("tax.documents", "en"): "public authority income certificates and tax filing documents",
    ("maps.incognito", "ko"): "장소 검색과 이동 경로 위치 기록을 남기지 않는 지도 탐색",
    ("maps.incognito", "en"): "map place and route searches without saving location history",
    ("safety.check_in", "ko"): "지정 종료 시간까지 응답이 없으면 선택한 사람에게 위치 알림",
    ("safety.check_in", "en"): "notify chosen contacts with a location when a personal check-in expires",
    ("subscription.cancel.confirm", "ko"): "혜택 종료일과 다음 결제 중단을 검토하는 최종 확인 단계",
    ("subscription.cancel.confirm", "en"): "final review of benefit end date and stopped future billing",
    ("safety.sos", "ko"): "현재 위치와 긴급 메시지를 지정한 연락처에 즉시 전송",
    ("safety.sos", "en"): "send current location and an emergency message to chosen contacts",
    ("restaurant_booking.waitlist_status", "ko"): "식당 대기 순번과 예상 입장 시간을 실시간 확인",
    ("restaurant_booking.waitlist_status", "en"): "live restaurant queue position and estimated table time",
    ("android.settings.root", "ko"): "휴대전화 시스템의 연결 화면 표시 소리 보안 설정 모음",
    ("android.settings.root", "en"): "device system settings for connections display sound and security",
    ("communication.conversation.search", "ko"): "현재 대화방에서 메시지 내용과 보낸 사람을 검색",
    ("communication.conversation.search", "en"): "search message text and senders inside the current conversation",
    ("health.lab_results", "ko"): "검사일 수치 기준 범위와 의료진 판독 결과 확인",
    ("health.lab_results", "en"): "test date values reference ranges and clinician interpretation",
    ("files.browser", "ko"): "기기와 클라우드 폴더에서 최근 문서 파일을 탐색",
    ("files.browser", "en"): "browse recent documents across device and cloud folders",
}

# Fuzzy/concept matches outside the exact collision set observed in the fixed
# development probes.  Each pair is a genuine neighboring UI meaning, not an
# app identity: the owner context is valid negative evidence for the neighbor.
_ADDITIONAL_CONTEXT_COMPETITORS: dict[str, tuple[str, ...]] = {
    "family_store.purchase_approval": (
        "family_store.hub",
        "parental.purchase_approval",
        "refund.entry",
    ),
    "shopping.cancel_order": ("order.cancel.entry", "refund.entry"),
    "messaging.archive": ("communication.conversation.archive",),
    "security.two_factor": ("auth.two_factor",),
    "safety.check_in": ("android_safety.safety_check",),
    "account.personal_info": ("civic_local.anonymous_request",),
    "account.profile": (
        "civic_local.anonymous_request",
        "consent.required",
        "legal.signup_terms",
    ),
    "shopping_logistics.hub": ("mobility.hub", "order.cancel.entry"),
    "calls.hub": ("calls.block_number", "contacts.hub"),
    "health.medications": ("digital_health.prescriptions",),
    "tax.documents": ("hr_payroll.tax_documents",),
    "marketplace.favorites": ("commerce.wishlist",),
    "maps.incognito": ("browser.incognito",),
    "commerce.cart": ("shopping.cart",),
    "subscription.cancel.confirm": ("subscription.cancel.entry",),
    "safety.sos": ("android_safety.sos",),
    "restaurant_booking.waitlist_status": ("healthcare_provider.waiting_lists",),
    "android.settings.root": ("android.connectivity.hub",),
    "communication.conversation.search": ("messaging.search",),
    "health.lab_results": ("health.records", "digital_health.lab_results"),
    "privacy.consent": ("consent.optional",),
    "files.browser": ("documents.hub",),
}


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return " ".join(
        "".join(character if (character.isalpha() or character.isdigit()) else " " for character in text).split()
    )


def _compact_normalized(value: object) -> str:
    return normalize_text(value).replace(" ", "")


def _same_normalized_phrase(left: object, right: object) -> bool:
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    return bool(
        left_normalized
        and right_normalized
        and (
            left_normalized == right_normalized
            or _compact_normalized(left_normalized)
            == _compact_normalized(right_normalized)
        )
    )


def _contexts_overlap(left: object, right: object) -> bool:
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    if not left_normalized or not right_normalized:
        return False
    if (
        left_normalized == right_normalized
        or left_normalized in right_normalized
        or right_normalized in left_normalized
    ):
        return True
    left_compact = _compact_normalized(left_normalized)
    right_compact = _compact_normalized(right_normalized)
    return (
        left_compact == right_compact
        or left_compact in right_compact
        or right_compact in left_compact
    )


def _canonical_payload_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def strip_alias_context_overrides(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only contexts recorded as derived by the previous override run.

    The materializer rebuilds later ontology generations from reviewed source
    packs.  Removing the recorded derived values first prevents a previous run
    from becoming implicit source data and makes repeated materialization byte
    stable.  Metadata from the legacy 1.0.0 schema did not contain an addition
    ledger; it is safely discarded once during migration.
    """

    result = copy.deepcopy(dict(payload))
    metadata = result.get("alias_context_overrides", {})
    additions = metadata.get("context_additions", []) if isinstance(metadata, Mapping) else []
    if additions and not isinstance(additions, list):
        raise ValueError("alias context_additions must be a list")
    functions = _function_map(result)
    for entry in additions:
        if not isinstance(entry, Mapping):
            raise ValueError("alias context addition entry must be an object")
        function_id = str(entry.get("function_id", "")).strip()
        function = functions.get(function_id)
        if function is None:
            # A later source pack may intentionally remove a function.  Its
            # now-orphaned derived record must not block reconstruction.
            continue
        for field in ("positive_context", "negative_context"):
            raw_removals = entry.get(field, [])
            if not isinstance(raw_removals, list):
                raise ValueError(f"alias {field} additions must be a list")
            removals = {str(value) for value in raw_removals}
            if removals:
                function[field] = [
                    value
                    for value in _string_list(function.get(field, []))
                    if value not in removals
                ]
    result.pop("alias_context_overrides", None)
    return result


def apply_alias_context_overrides(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with owner-specific contrastive context guards applied.

    For every exact same-locale alias collision, a reviewed positive context of
    each owner becomes negative evidence for the *other* owners of the same UI
    label.  The evidence already describes the surrounding screen semantics;
    this operation merely makes its contrastive meaning explicit.
    """

    result = copy.deepcopy(dict(payload))
    existing_metadata = result.get("alias_context_overrides", {})
    if isinstance(existing_metadata, Mapping) and str(existing_metadata.get("version", "")) == OVERRIDE_VERSION:
        return result
    source_catalog_sha256 = _canonical_payload_sha256(result)
    functions = _function_map(result)
    groups, _raw_aliases = _collision_groups(functions)
    selected = _selected_positive_contexts(functions, groups)
    context_additions: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"positive_context": [], "negative_context": []}
    )

    added_positive = 0
    for (_locale, _normalized_alias, expected_function), context in sorted(selected.items()):
        positive = _string_list(functions[expected_function].get("positive_context", []))
        if normalize_text(context) in {normalize_text(value) for value in positive}:
            continue
        positive.append(context)
        functions[expected_function]["positive_context"] = positive
        context_additions[expected_function]["positive_context"].append(context)
        added_positive += 1

    # A normalized label can be declared under multiple locale tags, including
    # a locale in which it is not itself a collision.  Treat every exact or
    # strongly similar owner as confusable so a locale fallback cannot win a
    # saturated-score tie.
    aliases_by_function = {
        function_id: tuple(
            normalize_text(value)
            for _locale, values in _mapping_lists(function.get("aliases", {}))
            for value in values
            if normalize_text(value)
        )
        for function_id, function in functions.items()
    }
    confusable_by_alias = {
        normalized_alias: {
            function_id
            for function_id, aliases in aliases_by_function.items()
            if any(_aliases_confusable(normalized_alias, alias) for alias in aliases)
        }
        for normalized_alias in {key[1] for key, _owners in groups}
    }
    protected_contexts: dict[str, set[str]] = {
        function_id: {
            normalize_text(value)
            for value in _string_list(function.get("positive_context", []))
            if normalize_text(value)
        }
        for function_id, function in functions.items()
    }
    for (_locale, _normalized_alias, function_id), context in selected.items():
        protected_contexts[function_id].update(
            normalize_text(value) for value in _guard_phrases(context) if normalize_text(value)
        )

    added_negative = 0
    guarded_owner_pairs = 0
    for (locale, normalized_alias), owners in groups:
        for expected_function in owners:
            context = selected.get((locale, normalized_alias, expected_function), "")
            if not context:
                continue
            confusable_functions = (
                confusable_by_alias[normalized_alias]
                | set(_ADDITIONAL_CONTEXT_COMPETITORS.get(expected_function, ()))
            ) - {expected_function}
            guard_phrases = _guard_phrases(context)
            positive = _string_list(functions[expected_function].get("positive_context", []))
            existing_positive = {normalize_text(value) for value in positive}
            for guard in guard_phrases:
                if normalize_text(guard) not in existing_positive:
                    positive.append(guard)
                    existing_positive.add(normalize_text(guard))
                    context_additions[expected_function]["positive_context"].append(guard)
                    added_positive += 1
            functions[expected_function]["positive_context"] = positive
            for competing_function in sorted(confusable_functions):
                negative = _string_list(functions[competing_function].get("negative_context", []))
                existing_negative = {normalize_text(value) for value in negative}
                own_aliases = set(aliases_by_function.get(competing_function, ()))
                for guard in guard_phrases:
                    normalized_guard = normalize_text(guard)
                    if normalized_guard in existing_negative:
                        continue
                    # A context guard must never negate the competing
                    # function's own reviewed UI label.  Exact labels are the
                    # strongest screen evidence; treating one as negative can
                    # make a longer, consequential sibling label win (for
                    # example ``Assignment`` over ``Submit assignment``).
                    if any(
                        _same_normalized_phrase(normalized_guard, alias)
                        for alias in own_aliases
                    ):
                        continue
                    force_context_guard = competing_function in set(
                        _ADDITIONAL_CONTEXT_COMPETITORS.get(expected_function, ())
                    )
                    if not force_context_guard and any(
                        _contexts_overlap(normalized_guard, protected)
                        for protected in protected_contexts.get(competing_function, set())
                    ):
                        continue
                    negative.append(guard)
                    existing_negative.add(normalized_guard)
                    context_additions[competing_function]["negative_context"].append(guard)
                    added_negative += 1
                functions[competing_function]["negative_context"] = negative
            guarded_owner_pairs += 1

    result["alias_context_overrides"] = {
        "version": OVERRIDE_VERSION,
        "source_catalog_sha256": source_catalog_sha256,
        "strategy": "exact-alias-owner contrast using app-agnostic surrounding UI context",
        "collision_group_count": len(groups),
        "guarded_owner_pair_count": guarded_owner_pairs,
        "positive_context_addition_count": added_positive,
        "negative_context_addition_count": added_negative,
        "context_additions": [
            {
                "function_id": function_id,
                "positive_context": sorted(set(fields["positive_context"]), key=normalize_text),
                "negative_context": sorted(set(fields["negative_context"]), key=normalize_text),
            }
            for function_id, fields in sorted(context_additions.items())
            if fields["positive_context"] or fields["negative_context"]
        ],
        "constraints": {
            "aliases_added": 0,
            "goal_sentences_copied": 0,
            "app_names_added": 0,
            "coordinates_added": 0,
        },
    }
    return result


def build_development_fixture(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build fixed positive and contrastive-negative probes from pre-override data."""

    functions = _function_map(payload)
    groups, raw_aliases = _collision_groups(functions)
    selected = _selected_positive_contexts(functions, groups)
    cases: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for group_index, ((locale, normalized_alias), owners) in enumerate(groups, start=1):
        label = sorted(
            raw_aliases[(locale, normalized_alias)],
            key=lambda value: (len(value), value.casefold(), value),
        )[0]
        group_id = f"alias-{group_index:04d}"
        for expected_function in owners:
            context = selected.get((locale, normalized_alias, expected_function), "")
            if not context:
                unresolved.append(
                    {
                        "group_id": group_id,
                        "locale": locale,
                        "label": label,
                        "expected_function_id": expected_function,
                        "reason": "no_realistic_owner_unique_positive_context",
                    }
                )
                continue
            cases.append(
                _case(
                    case_id=f"{group_id}-positive-{_slug(expected_function)}",
                    probe_type="positive_context",
                    locale=locale,
                    label=label,
                    nearby_text=context,
                    expected_function=expected_function,
                    owners=owners,
                )
            )

        for rejected_function in owners:
            for expected_function in owners:
                if rejected_function == expected_function:
                    continue
                expected_context = selected.get((locale, normalized_alias, expected_function), "")
                rejected_context = _select_negative_context(
                    functions,
                    rejected_function=rejected_function,
                    expected_function=expected_function,
                    locale=locale,
                    label=label,
                )
                if not expected_context or not rejected_context:
                    continue
                cases.append(
                    _case(
                        case_id=(
                            f"{group_id}-negative-{_slug(rejected_function)}-to-"
                            f"{_slug(expected_function)}"
                        ),
                        probe_type="contrastive_negative",
                        locale=locale,
                        label=label,
                        nearby_text=f"{expected_context} {rejected_context}".strip(),
                        expected_function=expected_function,
                        rejected_function=rejected_function,
                        owners=owners,
                    )
                )

    return {
        "schema_version": 1,
        "fixture_version": FIXTURE_VERSION,
        "split": "development_alias_collisions_v1",
        "frozen": True,
        "catalog_derived": True,
        "independent_accuracy_claim": False,
        "tuning_allowed": True,
        "source_kind": "alias_collision_development",
        "description": (
            "Fixed development probes for exact same-locale UI-label collisions. "
            "This fixture is tuning-allowed and must not be reported as independent accuracy."
        ),
        "source_catalog": {
            "catalog_version": str(payload.get("catalog_version", "")),
            "canonical_sha256": _canonical_payload_sha256(payload),
        },
        "authoring_policy": {
            "input_snapshot": "canonical catalog before alias-context override application",
            "positive_probe": "exact label plus realistic owner-unique surrounding UI context",
            "negative_probe": "alternative-owner positive context plus rejected-owner negative context",
            "forbidden_shortcuts": ["app names", "screen coordinates", "copied goal sentences", "new aliases"],
        },
        "coverage_contract": {
            "collision_group_count": len(groups),
            "collision_owner_reference_count": sum(len(owners) for _key, owners in groups),
            "unresolved_owner_count": len(unresolved),
        },
        "unresolved_context_owners": unresolved,
        "cases": cases,
    }


def annotate_fixture_runtime_baseline(
    fixture: dict[str, Any],
    *,
    catalog_path: Path,
) -> dict[str, Any]:
    """Freeze actual pre-override top-1 results for every development probe."""

    api_root = Path(__file__).resolve().parents[1] / "apps" / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))
    from app.services.navigation_function_catalog import NavigationFunctionCatalog

    result = copy.deepcopy(fixture)
    raw_catalog = catalog_path.read_text(encoding="utf-8")
    correct = 0
    positive_correct = 0
    negative_correct = 0
    positive_total = 0
    negative_total = 0
    with TemporaryDirectory(prefix="egl-alias-development-baseline-") as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "catalog.sqlite",
            catalog_path,
        )
        catalog.validate()
        for case in result["cases"]:
            matches = catalog.match_candidate(
                label=str(case["label"]),
                nearby_text=str(case["nearby_text"]),
                role=str(case["role"]),
                locale=str(case["locale"]),
                limit=max(8, len(case["collision_function_ids"]) + 2),
            )
            actual = matches[0].function_id if matches else ""
            is_correct = actual == str(case["expected_function_id"])
            case["baseline_actual_function_id"] = actual
            case["baseline_correct"] = is_correct
            case["baseline_top_score"] = matches[0].score if matches else 0.0
            correct += int(is_correct)
            if case["probe_type"] == "positive_context":
                positive_total += 1
                positive_correct += int(is_correct)
            else:
                negative_total += 1
                negative_correct += int(is_correct)
    result["baseline"] = {
        "catalog_version": json.loads(raw_catalog)["catalog_version"],
        "catalog_sha256": hashlib.sha256(raw_catalog.encode("utf-8")).hexdigest(),
        "total": len(result["cases"]),
        "correct": correct,
        "accuracy": round(correct / max(1, len(result["cases"])), 6),
        "positive": {
            "total": positive_total,
            "correct": positive_correct,
            "accuracy": round(positive_correct / max(1, positive_total), 6),
        },
        "contrastive_negative": {
            "total": negative_total,
            "correct": negative_correct,
            "accuracy": round(negative_correct / max(1, negative_total), 6),
        },
    }
    return result


def evaluate_fixture_runtime(
    fixture: Mapping[str, Any],
    *,
    catalog_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate fixed probes with the production matcher (development only)."""

    api_root = Path(__file__).resolve().parents[1] / "apps" / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))
    from app.services.navigation_function_catalog import NavigationFunctionCatalog

    cases = list(fixture.get("cases", []))
    failures: list[dict[str, Any]] = []
    correct_by_type: dict[str, int] = defaultdict(int)
    total_by_type: dict[str, int] = defaultdict(int)
    with TemporaryDirectory(prefix="egl-alias-development-evaluation-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        catalog_path = temporary_root / "catalog.json"
        catalog_path.write_text(json.dumps(catalog_payload, ensure_ascii=False), encoding="utf-8")
        catalog = NavigationFunctionCatalog(temporary_root / "catalog.sqlite", catalog_path)
        catalog.validate()
        for case in cases:
            matches = catalog.match_candidate(
                label=str(case["label"]),
                nearby_text=str(case["nearby_text"]),
                role=str(case.get("role", "menuitem")),
                locale=str(case["locale"]),
                limit=max(8, len(case["collision_function_ids"]) + 2),
            )
            actual = matches[0].function_id if matches else ""
            probe_type = str(case["probe_type"])
            is_correct = actual == str(case["expected_function_id"])
            total_by_type[probe_type] += 1
            correct_by_type[probe_type] += int(is_correct)
            if not is_correct:
                failures.append(
                    {
                        "case_id": case["case_id"],
                        "probe_type": probe_type,
                        "locale": case["locale"],
                        "label": case["label"],
                        "nearby_text": case["nearby_text"],
                        "expected_function_id": case["expected_function_id"],
                        "actual_function_id": actual,
                        "collision_function_ids": case["collision_function_ids"],
                        "top_score": matches[0].score if matches else 0.0,
                    }
                )
    correct = sum(correct_by_type.values())
    return {
        "total": len(cases),
        "correct": correct,
        "accuracy": round(correct / max(1, len(cases)), 6),
        "by_probe_type": {
            probe_type: {
                "total": total_by_type[probe_type],
                "correct": correct_by_type[probe_type],
                "accuracy": round(correct_by_type[probe_type] / max(1, total_by_type[probe_type]), 6),
            }
            for probe_type in sorted(total_by_type)
        },
        "failure_count": len(failures),
        "failures": failures,
    }


def _case(
    *,
    case_id: str,
    probe_type: str,
    locale: str,
    label: str,
    nearby_text: str,
    expected_function: str,
    owners: Sequence[str],
    rejected_function: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case_id": case_id,
        "probe_type": probe_type,
        "locale": locale,
        "label": label,
        "nearby_text": nearby_text,
        "role": "menuitem",
        "expected_function_id": expected_function,
        "collision_function_ids": list(owners),
        "source_kind": "alias_collision_development",
        "tuning_allowed": True,
        "tags": ["catalog_derived", "context_disambiguation", "coordinate_free", "not_accuracy_evidence"],
    }
    if rejected_function:
        result["rejected_function_id"] = rejected_function
    return result


def _function_map(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_functions = payload.get("functions", [])
    if not isinstance(raw_functions, list):
        raise ValueError("functions must be a list")
    return {
        str(item["function_id"]): item
        for item in raw_functions
        if isinstance(item, dict) and str(item.get("function_id", "")).strip()
    }


def _collision_groups(
    functions: Mapping[str, Mapping[str, Any]],
) -> tuple[
    list[tuple[tuple[str, str], tuple[str, ...]]],
    dict[tuple[str, str], set[str]],
]:
    owners: dict[tuple[str, str], set[str]] = defaultdict(set)
    raw_aliases: dict[tuple[str, str], set[str]] = defaultdict(set)
    for function_id, function in functions.items():
        aliases = function.get("aliases", {})
        if not isinstance(aliases, Mapping):
            continue
        for raw_locale, raw_values in aliases.items():
            locale = str(raw_locale).casefold()
            values = raw_values if isinstance(raw_values, list) else []
            for raw_value in values:
                phrase = str(raw_value).strip()
                normalized = normalize_text(phrase)
                if not normalized:
                    continue
                key = (locale, normalized)
                owners[key].add(function_id)
                raw_aliases[key].add(phrase)
    groups = [
        (key, tuple(sorted(function_ids)))
        for key, function_ids in owners.items()
        if len(function_ids) >= 2
    ]
    groups.sort(key=lambda item: (-len(item[1]), item[0][0], item[0][1]))
    return groups, raw_aliases


def _selected_positive_contexts(
    functions: Mapping[str, Mapping[str, Any]],
    groups: Sequence[tuple[tuple[str, str], tuple[str, ...]]],
) -> dict[tuple[str, str, str], str]:
    result: dict[tuple[str, str, str], str] = {}
    all_aliases = {
        normalize_text(value)
        for function in functions.values()
        for _locale, values in _mapping_lists(function.get("aliases", {}))
        for value in values
        if normalize_text(value)
    }
    for (locale, normalized_alias), owners in groups:
        context_owners: dict[str, set[str]] = defaultdict(set)
        raw_context: dict[tuple[str, str], str] = {}
        for function_id in owners:
            for context in _string_list(functions[function_id].get("positive_context", [])):
                normalized = normalize_text(context)
                if normalized:
                    context_owners[normalized].add(function_id)
                    raw_context[(function_id, normalized)] = context
        for function_id in owners:
            own_negative = {
                normalize_text(value)
                for value in _string_list(functions[function_id].get("negative_context", []))
            }
            language = locale.split("-", 1)[0]
            preferred = _PREFERRED_POSITIVE_CONTEXTS.get((function_id, language), "")
            if preferred and normalize_text(preferred) != normalized_alias and _is_realistic_context(preferred):
                result[(locale, normalized_alias, function_id)] = preferred
                continue
            choices = [
                raw_context[(function_id, normalized)]
                for normalized, context_functions in context_owners.items()
                if context_functions == {function_id}
                and normalized not in all_aliases
                and normalized not in own_negative
                and normalized != normalized_alias
                and _is_realistic_context(raw_context[(function_id, normalized)])
            ]
            if not choices:
                # Some reviewed screen-context phrases also happen to be a
                # label elsewhere in the broad ontology.  They are still
                # valid here when they were already stored as this owner's
                # positive context; never synthesize them from an alias table.
                choices = [
                    raw_context[(function_id, normalized)]
                    for normalized, context_functions in context_owners.items()
                    if context_functions == {function_id}
                    and normalized not in own_negative
                    and normalized != normalized_alias
                    and _is_realistic_context(raw_context[(function_id, normalized)])
                ]
            if choices:
                result[(locale, normalized_alias, function_id)] = sorted(
                    set(choices),
                    key=lambda value: _context_sort_key(value, locale),
                )[0]
                continue
            fallback = _FALLBACK_POSITIVE_CONTEXTS.get((function_id, language), "")
            if fallback:
                result[(locale, normalized_alias, function_id)] = fallback
    return result


def _select_negative_context(
    functions: Mapping[str, Mapping[str, Any]],
    *,
    rejected_function: str,
    expected_function: str,
    locale: str,
    label: str,
) -> str:
    expected_negative = [
        normalize_text(value)
        for value in _string_list(functions[expected_function].get("negative_context", []))
    ]
    choices = []
    for context in _string_list(functions[rejected_function].get("negative_context", [])):
        normalized = normalize_text(context)
        if not normalized or normalized == normalize_text(label) or not _is_realistic_context(context):
            continue
        if any(normalized in other or other in normalized for other in expected_negative if other):
            continue
        choices.append(context)
    if not choices:
        return ""
    return sorted(set(choices), key=lambda value: _context_sort_key(value, locale))[0]


def _context_sort_key(value: str, locale: str) -> tuple[int, int, int, str, str]:
    normalized = normalize_text(value)
    language_penalty = 0 if _language_matches(value, locale) else 1
    generic_penalty = 1 if normalized in _GENERIC_CONTEXTS else 0
    # Prefer a compact phrase that looks like adjacent UI copy.  Overly long
    # prose is less likely to occur verbatim on a real screen.
    length_penalty = abs(len(normalized) - 18)
    return (language_penalty, generic_penalty, length_penalty, normalized, value)


def _language_matches(value: str, locale: str) -> bool:
    has_hangul = bool(re.search(r"[가-힣]", value))
    if locale.casefold().startswith("ko"):
        return has_hangul
    if locale.casefold().startswith("en"):
        return bool(re.search(r"[A-Za-z]", value)) and not has_hangul
    return True


def _is_realistic_context(value: str) -> bool:
    normalized = normalize_text(value)
    if len(normalized) < 3 or _COORDINATE_RE.search(value):
        return False
    return not any(marker in normalized for marker in _BRAND_MARKERS)


def _guard_phrases(value: str) -> tuple[str, ...]:
    """Return nested evidence present in ``value`` for stronger tie breaking."""

    normalized = normalize_text(value)
    tokens = normalized.split()
    candidates: list[str] = [value]
    # Use contiguous phrases rather than isolated generic words.  Every guard
    # is a literal substring of the authored UI context, so it is both strong
    # enough to break a clamped-score tie and meaningful on a real screen.
    for width in (3, 2):
        for index in range(max(0, len(tokens) - width + 1)):
            phrase = " ".join(tokens[index : index + width])
            if normalize_text(phrase) not in _GENERIC_CONTEXTS:
                candidates.append(phrase)
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = normalize_text(candidate)
        if not key or key in seen or not _is_realistic_context(candidate):
            continue
        seen.add(key)
        result.append(candidate)
        if len(result) == 4:
            break
    return tuple(result)


def _phrase_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if min(len(left), len(right)) <= 2:
        return SequenceMatcher(None, left, right).ratio() * 0.25
    if right in left:
        return min(0.98, 0.78 + len(right) / max(1, len(left)) * 0.20)
    if left in right:
        return min(0.92, 0.68 + len(left) / max(1, len(right)) * 0.20)
    return SequenceMatcher(None, left, right).ratio() * 0.76


@lru_cache(maxsize=None)
def _character_counts(value: str) -> Counter[str]:
    return Counter(value)


def _aliases_confusable(left: str, right: str) -> bool:
    """Exact ``_phrase_similarity >= .48`` decision with cheap upper bounds.

    The broad catalog contains millions of obviously unrelated alias pairs.
    SequenceMatcher's real-quick and quick-ratio bounds can reject those pairs
    without changing the eventual predicate; the expensive ratio is evaluated
    only when both mathematical upper bounds can still reach the threshold.
    """

    if not left or not right:
        return False
    if left == right:
        return True
    if min(len(left), len(right)) <= 2:
        return False
    if right in left or left in right:
        return True
    length_upper = 2.0 * min(len(left), len(right)) / (len(left) + len(right))
    if length_upper * 0.76 < 0.48:
        return False
    left_counts = _character_counts(left)
    right_counts = _character_counts(right)
    matches = sum(min(count, right_counts.get(character, 0)) for character, count in left_counts.items())
    quick_upper = 2.0 * matches / (len(left) + len(right))
    if quick_upper * 0.76 < 0.48:
        return False
    return SequenceMatcher(None, left, right).ratio() * 0.76 >= 0.48


def _mapping_lists(value: object) -> Iterable[tuple[str, list[object]]]:
    if not isinstance(value, Mapping):
        return ()
    return (
        (str(key), list(items))
        for key, items in value.items()
        if isinstance(items, list)
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog_path = root / "fixtures" / "navigation" / "function-catalog.v1.json"
    fixture_path = root / "fixtures" / "navigation" / "db-gym" / "development-alias-collisions.v1.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    fixture = build_development_fixture(payload)
    fixture = annotate_fixture_runtime_baseline(fixture, catalog_path=catalog_path)
    fixture_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "navigation alias development fixture "
        f"groups={fixture['coverage_contract']['collision_group_count']} "
        f"cases={len(fixture['cases'])} "
        f"unresolved={len(fixture['unresolved_context_owners'])} "
        f"baseline={fixture['baseline']['correct']}/{fixture['baseline']['total']}"
    )


if __name__ == "__main__":
    main()
