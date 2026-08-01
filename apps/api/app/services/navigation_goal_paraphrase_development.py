from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from app.services.navigation_function_catalog import (
    NEVER_AUTO_STOP_POLICIES,
    NavigationFunctionCatalog,
    _normalize,
)


_GENERIC_UI_ROLES = frozenset(
    {
        "button",
        "heading",
        "image",
        "image_button",
        "link",
        "menu",
        "menuitem",
        "switch",
        "tab",
        "text",
        "textbox",
    }
)
_LOCALES = ("ko", "en")
_KOREAN_REWRITES = (
    ("비행기 모드", "모든 무선 연결을 한꺼번에 끄는 방식"),
    ("펀치 항목", "준공 전 보완 목록"),
    ("숙소 호스트 게스트 메시지", "숙박 제공 담당자가 투숙객과 주고받는 연락 내용"),
    ("게스트 메시지", "투숙객과 주고받는 연락 내용"),
    ("저수위 추세", "저장 수면 높이의 시간 변화"),
    ("허가 시설제원", "승인된 방송 설비의 기술 수치"),
    ("회원가입", "새 이용 자격 마련"),
    ("회원탈퇴", "이용 관계 종료"),
    ("자동결제", "주기적 금액 지불"),
    ("구독해지", "정기 이용 관계 종료"),
    ("구독 해지", "정기 이용 관계 종료"),
    ("개인정보", "개인 관련 자료"),
    ("비밀번호", "접근 암호"),
    ("인증서", "신원 증명 문서"),
    ("회원", "이용 자격"),
    ("가입", "새 자격 마련"),
    ("탈퇴", "이용 관계 끝내기"),
    ("삭제", "없애기"),
    ("제거", "걷어내기"),
    ("해지", "이용 관계 종료"),
    ("취소", "철회하기"),
    ("변경", "다르게 바꾸기"),
    ("수정", "내용 바로잡기"),
    ("편집", "내용 다듬기"),
    ("설정", "작동 방식 구성"),
    ("관리", "운영하여 다루기"),
    ("등록", "목록에 올리기"),
    ("신청", "처리를 요청하기"),
    ("제출", "검토 대상으로 넘기기"),
    ("승인", "허가 판단 내리기"),
    ("거절", "받아들이지 않기"),
    ("반려", "보완 대상으로 돌려보내기"),
    ("확인", "내용 살펴보기"),
    ("조회", "내역 살펴보기"),
    ("보기", "내용 살피기"),
    ("검색", "조건으로 찾아내기"),
    ("발급", "증명 문서 받아두기"),
    ("다운로드", "기기에 내려받기"),
    ("업로드", "서비스로 올려보내기"),
    ("저장", "계속 쓰도록 보관하기"),
    ("공유", "다른 주체와 나누기"),
    ("결제", "금액 지불 처리"),
    ("납부", "금액을 치르기"),
    ("환불", "지불 금액 돌려받기"),
    ("송금", "금액을 다른 곳으로 보내기"),
    ("이체", "계좌 사이 금액 옮기기"),
    ("예약", "이용 일정을 잡기"),
    ("주문", "상품 제공을 요청하기"),
    ("청구", "급부 또는 금액을 요구하기"),
    ("신고", "담당 체계에 알리기"),
    ("보고", "처리 내역을 전달하기"),
    ("기록", "이력으로 남기기"),
    ("생성", "새 항목 마련하기"),
    ("추가", "새 항목 더하기"),
    ("초기화", "처음 조건으로 되돌리기"),
    ("잠금", "접근하지 못하게 보호하기"),
    ("차단", "접근 흐름 막기"),
    ("허용", "이용할 수 있게 두기"),
    ("동의", "조건을 받아들이기"),
    ("철회", "이전 의사 거두기"),
    ("재개", "중단된 흐름 이어가기"),
    ("중지", "진행을 멈추기"),
    ("일시정지", "잠시 멈춘 상태로 두기"),
    ("시작", "절차에 착수하기"),
    ("종료", "절차를 마치기"),
    ("열기", "해당 영역에 닿기"),
    ("진입", "해당 영역에 닿기"),
    ("상태", "현재 조건"),
    ("내역", "이전 처리 자료"),
    ("알림", "새 소식 전달 방식"),
    ("계정", "사용자 식별 단위"),
    ("보험", "보장 계약"),
    ("문서", "기록 자료"),
    ("데이터", "저장 자료"),
)
_ENGLISH_REWRITES = {
    "accept": "consent to",
    "access": "reachability",
    "account": "user identity",
    "accounts": "user-held financial relationships",
    "acknowledge": "take responsibility for",
    "activate": "make operational",
    "add": "bring in",
    "admin": "oversight",
    "administration": "oversight",
    "adjudicate": "reach a determination on",
    "adjust": "recalibrate",
    "alert": "attention notice",
    "alerts": "attention notices",
    "alternative": "substitute choice",
    "analysis": "structured assessment",
    "allow": "permit use of",
    "app": "service interface",
    "application": "submitted request",
    "article": "governed object",
    "approval": "authorization decision",
    "approve": "authorize",
    "archive": "retain as a closed record",
    "assign": "place under responsibility",
    "assignment": "allocated task",
    "assessment": "structured evaluation",
    "authentication": "identity proofing",
    "automatic": "without repeated manual input",
    "autofill": "form completion assistance",
    "autoplay": "media start without a separate prompt",
    "backup": "protective copy",
    "balance": "remaining amount",
    "battery": "energy reserve",
    "beneficiary": "entitled recipient",
    "berth": "vessel docking position",
    "billing": "charge administration",
    "block": "prevent access to",
    "booking": "scheduled use",
    "bookmarks": "retained web locations",
    "browser": "web viewer",
    "budget": "spending allocation",
    "cache": "temporary retained material",
    "calendar": "date schedule",
    "calling": "voice communication",
    "cancel": "discontinue",
    "cancellation": "discontinuation",
    "card": "payment credential",
    "care": "service recipient support",
    "case": "managed matter",
    "cast": "send media to another display",
    "center": "assistance area",
    "certificate": "proof document",
    "chart": "care record",
    "change": "make different",
    "check": "verify condition of",
    "claim": "benefit request",
    "clinician": "care practitioner",
    "clock": "time reference",
    "close": "conclude",
    "comments": "participant responses",
    "classification": "category determination",
    "clarification": "resolution of uncertainty",
    "confirm": "verify and retain",
    "consent": "permission decision",
    "contact": "reach assistance staff",
    "contacts": "known correspondents",
    "content": "published material",
    "control": "governance adjustment",
    "controls": "governance adjustments",
    "coverage": "protection scope",
    "capture": "digitize as evidence",
    "create": "establish",
    "data": "stored information",
    "decision": "determination",
    "delete": "remove permanently",
    "deletion": "permanent removal",
    "delivery": "arrival service",
    "dangerous": "regulated hazardous",
    "deposit": "funds placed on account",
    "detail": "specific information",
    "details": "specific information",
    "disable": "make unavailable",
    "discovery": "candidate finding",
    "dispatch": "work allocation and sending",
    "distribution": "allocation among recipients",
    "documents": "record materials",
    "duty": "assigned responsibility period",
    "download": "save a local copy of",
    "edit": "revise",
    "eligibility": "qualification condition",
    "equipment": "operating unit",
    "emergency": "urgent event",
    "enable": "make available",
    "entry": "starting point",
    "estate": "decedent property matter",
    "event": "scheduled occurrence",
    "exception": "departure from the ordinary rule",
    "export": "take a portable copy of",
    "eccn": "export-control category code",
    "fare": "travel charge",
    "file": "submit formally",
    "files": "stored items",
    "filters": "selection criteria",
    "financial": "money-related",
    "flight": "air journey",
    "follow": "receive continuing updates from",
    "forwarding": "redirection to another destination",
    "freeze": "hold inactive",
    "groups": "organized collections",
    "goods": "cargo items",
    "help": "assistance",
    "history": "prior activity record",
    "handover": "change of custody",
    "home": "service recipient residence",
    "hold": "reserve for later",
    "hospital": "care facility",
    "human": "person-related",
    "hunt": "proactive search",
    "inquiry": "information lookup",
    "inbox": "received-items area",
    "inspect": "examine",
    "inspection": "structured examination",
    "insurance": "coverage contract",
    "intake": "initial receipt and classification",
    "inventory": "on-hand item register",
    "issue": "produce for use",
    "item": "governed article",
    "jobs": "work opportunities",
    "join": "become a participant in",
    "lab": "testing facility",
    "leave": "absence period",
    "library": "borrowable collection",
    "list": "collection overview",
    "location": "place information",
    "lodging": "temporary stay",
    "log": "retain an activity trace",
    "lock": "protect from access",
    "login": "identity session entry",
    "manage": "administer",
    "management": "administration",
    "map": "spatial overview",
    "manifest": "cargo declaration",
    "marketplace": "multi-seller exchange",
    "media": "audio-visual material",
    "medical": "care-related",
    "medication": "prescribed treatment item",
    "membership": "participation entitlement",
    "message": "communication item",
    "mindfulness": "attention practice",
    "mobile": "handheld-service",
    "music": "audio program",
    "network": "connected system",
    "navigation": "route guidance",
    "news": "current-affairs material",
    "note": "written observation",
    "notification": "attention delivery",
    "notifications": "attention deliveries",
    "offer": "proposed terms",
    "open": "reach",
    "operations": "operational work",
    "order": "request provision of",
    "oversight": "supervisory review",
    "package": "shipment item",
    "parental": "guardian-related",
    "patient": "care recipient",
    "pickup": "collection stop",
    "pause": "hold temporarily",
    "pay": "settle the amount for",
    "payment": "amount settlement",
    "payments": "amount settlements",
    "permit": "formal authorization",
    "personal": "individual-related",
    "plan": "planned arrangement",
    "playback": "media reproduction",
    "playlist": "ordered audio collection",
    "postal": "mail-network",
    "prescriber": "ordering clinician",
    "preferences": "chosen operating behavior",
    "presale": "early purchase window",
    "prescription": "medication order",
    "prescriptions": "medication orders",
    "privacy": "personal-information protection",
    "profile": "personal service record",
    "property": "owned or managed premises",
    "queue": "ordered work line",
    "record": "retain as evidence",
    "receipt": "proof of a completed transaction",
    "receivable": "incoming customer amount",
    "related": "associated",
    "records": "retained evidence items",
    "recover": "restore access to",
    "remote": "away from the local site",
    "refund": "return paid value",
    "register": "enroll",
    "registration": "enrollment",
    "reject": "decline",
    "release": "make available after review",
    "remove": "take away",
    "renew": "extend validity of",
    "report": "communicate formally",
    "request": "ask for processing of",
    "reset": "restore an initial condition for",
    "research": "systematic study",
    "restore": "bring back from retained material",
    "results": "observed findings",
    "resume": "continue after interruption",
    "review": "examine for a decision",
    "roadside": "at the side of a traveled road",
    "rollout": "staged introduction",
    "save": "retain for later use",
    "saved": "retained for later use",
    "sales": "customer acquisition",
    "scan": "read machine-readable information from",
    "screen": "interface view",
    "search": "locate by criteria",
    "settings": "operating preferences",
    "share": "make available to another party",
    "shopping": "retail selection",
    "signup": "new-user enrollment",
    "serial": "manufacturer identifier",
    "speed": "operating rate",
    "status": "current condition",
    "stop": "bring to an end",
    "storage": "retained capacity",
    "store": "retain in a repository",
    "submit": "hand over for review",
    "summary": "concise overview",
    "support": "assistance function",
    "subjects": "participating persons",
    "substitution": "replacement choice",
    "subscription": "recurring service relationship",
    "switch": "move to another option",
    "tab": "page session",
    "table": "structured row collection",
    "tax": "public levy",
    "team": "collaborating group",
    "ticket": "admission or travel entitlement",
    "time": "clock period",
    "timezone": "regional clock offset",
    "topics": "subject categories",
    "track": "observe progress of",
    "tracking": "progress observation",
    "translation": "language conversion",
    "transfer": "move between responsible parties",
    "transit": "public transport journey",
    "rail": "railway transport",
    "uninstall": "remove installed software",
    "unlock": "restore access to",
    "update": "bring information up to date",
    "upload": "send a copy into the service",
    "usage": "consumption pattern",
    "value": "assessed worth",
    "verify": "establish validity of",
    "vehicle": "transport unit",
    "vessel": "watercraft",
    "visit": "scheduled in-person encounter",
    "view": "inspect",
    "voicemail": "recorded voice inbox",
    "wishlist": "saved-interest collection",
    "zone": "regional area",
    "withdraw": "take back",
}


@dataclass(frozen=True)
class CatalogDerivedParaphraseCase:
    """A bilingual, development-only goal composed from catalog metadata."""

    case_id: str
    locale: str
    family: str
    generation: str
    domain: str
    goal_text: str
    intent_id: str
    raw_terminal_function: str
    canonical_terminal_function: str
    risk_level: str
    state_changing: bool
    automation_policy: str
    stop_policy: str
    role: str
    asset: str
    state: str
    action: str
    outcome: str
    maximum_source_phrase_fraction: float
    short_source_overlap_count: int
    goal_rule_action_overlap_count: int


def validate_paraphrase_development_policy(payload: Mapping[str, object]) -> None:
    required_flags = {
        "catalog_derived": True,
        "tuning_allowed": True,
        "independent_accuracy_evidence": False,
    }
    for key, expected in required_flags.items():
        if payload.get(key) is not expected:
            raise ValueError(f"paraphrase policy requires {key}={expected!r}")
    if str(payload.get("split", "")) != "development":
        raise ValueError("paraphrase policy must use split=development")
    if payload.get("frozen") is not False:
        raise ValueError("paraphrase development policy must remain non-frozen")

    expected = payload.get("catalog_expectations")
    if not isinstance(expected, Mapping):
        raise ValueError("catalog_expectations must be an object")
    exact_intents = int(expected.get("exact_intents", 0))
    exact_cases = int(expected.get("exact_cases", 0))
    if exact_intents <= 0 or exact_cases != exact_intents * 2:
        raise ValueError("catalog expectations must declare two cases per intent")
    if tuple(payload.get("locales", ())) != _LOCALES:
        raise ValueError("paraphrase policy locales must be exactly ['ko', 'en']")

    family_order = payload.get("family_order")
    templates = payload.get("templates")
    if not isinstance(family_order, list) or len(family_order) < 8:
        raise ValueError("at least eight ordered template families are required")
    if len(set(map(str, family_order))) != len(family_order):
        raise ValueError("template family names must be unique")
    if not isinstance(templates, Mapping) or set(map(str, family_order)) != set(templates):
        raise ValueError("templates must exactly match family_order")
    placeholders = {"role", "asset", "state", "action", "outcome", "safety"}
    for family in family_order:
        localized = templates.get(str(family))
        if not isinstance(localized, Mapping) or set(localized) != set(_LOCALES):
            raise ValueError(f"family {family} must define Korean and English templates")
        for locale, template in localized.items():
            text = str(template)
            missing = [value for value in placeholders if "{" + value + "}" not in text]
            if missing:
                raise ValueError(f"family {family}/{locale} lacks placeholders {missing}")

    anti_copy = payload.get("anti_copy_policy")
    if not isinstance(anti_copy, Mapping):
        raise ValueError("anti_copy_policy must be an object")
    required_anti_copy = {
        "normalization": "navigation_function_catalog._normalize",
        "reject_exact_alias_or_pattern": True,
        "reject_normalized_source_substring_at_or_above_minimum": True,
        "reject_partial_wrapper_at_or_above_minimum": True,
        "short_source_terms_are_reported_not_rejected": True,
    }
    for key, expected_value in required_anti_copy.items():
        if anti_copy.get(key) != expected_value:
            raise ValueError(f"anti-copy policy requires {key}={expected_value!r}")
    if int(anti_copy.get("minimum_normalized_phrase_length", 0)) < 4:
        raise ValueError("anti-copy protected phrases must include four-character labels")
    if float(anti_copy.get("maximum_source_phrase_fraction", 1.0)) > 0.34:
        raise ValueError("anti-copy maximum source phrase fraction is too permissive")
    gates = payload.get("diagnostic_gates")
    if not isinstance(gates, Mapping):
        raise ValueError("diagnostic_gates must be an object")
    required_gates = {
        "minimum_correct",
        "maximum_generic",
        "maximum_wrong",
        "maximum_short_source_overlap_cases",
        "maximum_goal_rule_action_overlap_cases",
        "maximum_expected_boundary_mismatch_cases",
        "maximum_safety_violations",
    }
    if set(gates) != required_gates or any(int(gates[key]) < 0 for key in gates):
        raise ValueError("diagnostic_gates must contain non-negative reviewed bounds")


def generate_catalog_derived_paraphrase_cases(
    *,
    catalog_payload: Mapping[str, object],
    equivalence_payload: Mapping[str, object],
    policy_payload: Mapping[str, object],
) -> tuple[CatalogDerivedParaphraseCase, ...]:
    """Generate exactly one Korean and one English case for every intent.

    The output never reads user/evaluation text.  Destination wording is
    composed from reviewed goal-rule fragments plus role, asset, lifecycle,
    and safety metadata.  A target alias or pattern may not survive as a
    normalized substring, which prevents an alias wrapped in boilerplate from
    masquerading as paraphrase evidence.
    """

    validate_paraphrase_development_policy(policy_payload)
    raw_functions = catalog_payload.get("functions")
    raw_intents = catalog_payload.get("intents")
    if not isinstance(raw_functions, list) or not isinstance(raw_intents, list):
        raise ValueError("catalog functions and intents must be lists")
    expected = policy_payload["catalog_expectations"]
    assert isinstance(expected, Mapping)
    if str(catalog_payload.get("catalog_version", "")) != str(expected["catalog_version"]):
        raise ValueError("paraphrase fixture is pinned to another catalog version")
    if len(raw_functions) != int(expected["exact_functions"]):
        raise ValueError("paraphrase fixture function count drifted")
    if len(raw_intents) != int(expected["exact_intents"]):
        raise ValueError("paraphrase fixture intent count drifted")

    functions = {
        str(item.get("function_id", "")): item
        for item in raw_functions
        if isinstance(item, Mapping) and str(item.get("function_id", ""))
    }
    if len(functions) != len(raw_functions):
        raise ValueError("function identifiers must be present and unique")
    canonical_ids = _equivalence_projection(equivalence_payload, functions)
    family_order = tuple(str(value) for value in policy_payload["family_order"])
    templates = policy_payload["templates"]
    anti_copy = policy_payload["anti_copy_policy"]
    assert isinstance(templates, Mapping) and isinstance(anti_copy, Mapping)
    minimum_phrase_length = int(anti_copy["minimum_normalized_phrase_length"])
    maximum_fraction = float(anti_copy["maximum_source_phrase_fraction"])
    cases: list[CatalogDerivedParaphraseCase] = []

    for ordinal, raw_intent in enumerate(raw_intents):
        if not isinstance(raw_intent, Mapping):
            raise ValueError(f"intent at ordinal {ordinal} must be an object")
        intent_id = str(raw_intent.get("intent_id", "")).strip()
        terminal = str(raw_intent.get("terminal_function", "")).strip()
        definition = functions.get(terminal)
        if not intent_id or definition is None:
            raise ValueError(f"intent {intent_id or ordinal} has no terminal definition")
        protected = normalized_source_phrases(
            raw_intent,
            definition,
            minimum_length=minimum_phrase_length,
        )
        for locale_index, locale in enumerate(_LOCALES):
            family = family_order[(ordinal + (len(family_order) // 2) * locale_index) % len(family_order)]
            salt = f"{intent_id}:{locale}:{ordinal}"
            role = _role_phrase(definition, locale, protected, salt)
            asset = _asset_phrase(definition, locale, protected, salt)
            state = _state_phrase(raw_intent, definition, locale, protected, salt)
            action = _action_phrase(raw_intent, definition, locale, protected, salt)
            outcome = _outcome_phrase(raw_intent, definition, locale, protected, salt)
            safety = _safety_phrase(definition, locale)
            localized = templates[family]
            assert isinstance(localized, Mapping)
            goal_text = str(localized[locale]).format_map(
                {
                    "role": role,
                    "asset": asset,
                    "state": state,
                    "action": action,
                    "outcome": outcome,
                    "safety": safety,
                }
            )
            normalized_goal = _normalize(goal_text)
            collisions = [value for value in protected if value in normalized_goal]
            if collisions:
                raise ValueError(
                    f"catalog phrase survived paraphrase composition: {intent_id}/{locale}"
                )
            all_sources = _all_normalized_source_phrases(raw_intent, definition)
            maximum_source_fraction = max(
                (len(value) / len(normalized_goal) for value in all_sources if value in normalized_goal),
                default=0.0,
            )
            if maximum_source_fraction > maximum_fraction:
                raise ValueError(
                    f"source phrase dominates paraphrase: {intent_id}/{locale}"
                )
            short_source_overlap_count = sum(
                1
                for value in all_sources
                if 0 < len(value) < minimum_phrase_length and value in normalized_goal
            )
            normalized_action = _normalize(action)
            goal_rule_action_overlap_count = sum(
                1
                for value in _normalized_goal_rule_terms(raw_intent)
                if len(value) >= minimum_phrase_length and value in normalized_action
            )
            cases.append(
                CatalogDerivedParaphraseCase(
                    case_id=f"paraphrase-{ordinal:04d}-{locale}",
                    locale=locale,
                    family=family,
                    generation=_intent_generation(intent_id),
                    domain=str(definition.get("domain", "")),
                    goal_text=goal_text,
                    intent_id=intent_id,
                    raw_terminal_function=terminal,
                    canonical_terminal_function=canonical_ids[terminal],
                    risk_level=str(definition.get("risk_level", "low")),
                    state_changing=bool(definition.get("state_changing", False)),
                    automation_policy=str(definition.get("automation_policy", "")),
                    stop_policy=str(definition.get("stop_policy", "")),
                    role=role,
                    asset=asset,
                    state=state,
                    action=action,
                    outcome=outcome,
                    maximum_source_phrase_fraction=maximum_source_fraction,
                    short_source_overlap_count=short_source_overlap_count,
                    goal_rule_action_overlap_count=goal_rule_action_overlap_count,
                )
            )

    exact_cases = int(expected["exact_cases"])
    if len(cases) != exact_cases:
        raise ValueError(f"expected {exact_cases} paraphrases, generated {len(cases)}")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("paraphrase case identifiers must be unique")
    if len({_normalize(case.goal_text) for case in cases}) != len(cases):
        raise ValueError("paraphrase goal texts must be normalization-unique")
    family_counts = Counter(case.family for case in cases)
    if max(family_counts.values()) - min(family_counts.values()) != 0:
        raise ValueError("template families must be exactly balanced")
    return tuple(cases)


def evaluate_catalog_derived_paraphrases(
    catalog: NavigationFunctionCatalog,
    cases: Iterable[CatalogDerivedParaphraseCase],
) -> dict[str, object]:
    """Evaluate only aggregate development diagnostics; omit failure payloads."""

    totals: Counter[str] = Counter()
    correct: Counter[str] = Counter()
    generic: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    locale_totals: Counter[str] = Counter()
    locale_correct: Counter[str] = Counter()
    locale_generic: Counter[str] = Counter()
    locale_wrong: Counter[str] = Counter()
    logical_terminal_correct = 0
    safety_violations = 0
    expected_boundary_mismatch_cases = 0
    short_source_overlap_cases = 0
    goal_rule_action_overlap_cases = 0
    for case in cases:
        short_source_overlap_cases += int(case.short_source_overlap_count > 0)
        goal_rule_action_overlap_cases += int(
            case.goal_rule_action_overlap_count > 0
        )
        plan = catalog.plan_goal(case.goal_text)
        totals[case.family] += 1
        locale_totals[case.locale] += 1
        if plan.intent == case.intent_id:
            correct[case.family] += 1
            locale_correct[case.locale] += 1
            if (
                plan.raw_terminal_function == case.raw_terminal_function
                and plan.terminal_function == case.canonical_terminal_function
            ):
                logical_terminal_correct += 1
        elif plan.intent == "generic_navigation":
            generic[case.family] += 1
            locale_generic[case.locale] += 1
        else:
            wrong[case.family] += 1
            locale_wrong[case.locale] += 1
        if plan.terminal_function:
            resolved = catalog.function(plan.terminal_function)
            if resolved is None:
                safety_violations += 1
            else:
                expected_strict_boundary = case.state_changing
                resolved_strict_boundary = resolved.state_changing
                expected_never_auto_boundary = (
                    case.risk_level == "high"
                    or case.automation_policy == "never_auto"
                )
                resolved_never_auto_boundary = (
                    resolved.risk_level == "high"
                    or resolved.automation_policy == "never_auto"
                )
                strict_stop_policies = {
                    "before_action",
                    "before_activation",
                    "user_confirmation",
                    "user_only",
                    "stop_before_action",
                }
                resolved_strict_valid = (
                    resolved.automation_policy == "never_auto"
                    and resolved.stop_policy in strict_stop_policies
                )
                resolved_never_auto_valid = (
                    resolved.automation_policy == "never_auto"
                    and resolved.stop_policy
                    in {*NEVER_AUTO_STOP_POLICIES, "on_destination_screen"}
                )
                if resolved_strict_boundary and not resolved_strict_valid:
                    safety_violations += 1
                elif resolved_never_auto_boundary and not resolved_never_auto_valid:
                    safety_violations += 1
                if expected_strict_boundary and not resolved_strict_valid:
                    expected_boundary_mismatch_cases += 1
                elif expected_never_auto_boundary and not resolved_never_auto_valid:
                    expected_boundary_mismatch_cases += 1

    families = {
        family: {
            "total": totals[family],
            "correct": correct[family],
            "generic": generic[family],
            "wrong": wrong[family],
        }
        for family in sorted(totals)
    }
    locales = {
        locale: {
            "total": locale_totals[locale],
            "correct": locale_correct[locale],
            "generic": locale_generic[locale],
            "wrong": locale_wrong[locale],
        }
        for locale in sorted(locale_totals)
    }
    total = sum(totals.values())
    total_correct = sum(correct.values())
    total_generic = sum(generic.values())
    total_wrong = sum(wrong.values())
    return {
        "catalog_derived": True,
        "tuning_allowed": True,
        "independent_accuracy_evidence": False,
        "total": total,
        "correct": total_correct,
        "generic": total_generic,
        "wrong": total_wrong,
        "logical_terminal_correct": logical_terminal_correct,
        "safety_violations": safety_violations,
        "expected_boundary_mismatch_cases": expected_boundary_mismatch_cases,
        "short_source_overlap_cases": short_source_overlap_cases,
        "goal_rule_action_overlap_cases": goal_rule_action_overlap_cases,
        "accuracy": round(total_correct / total, 6) if total else 0.0,
        "families": families,
        "locales": locales,
    }


def normalized_source_phrases(
    intent: Mapping[str, object],
    definition: Mapping[str, object],
    *,
    minimum_length: int = 4,
) -> frozenset[str]:
    return frozenset(
        value
        for value in _all_normalized_source_phrases(intent, definition)
        if len(value) >= minimum_length
    )


def _all_normalized_source_phrases(
    intent: Mapping[str, object], definition: Mapping[str, object]
) -> frozenset[str]:
    values: list[object] = list(intent.get("patterns", []))
    localized_patterns = intent.get("patterns_by_locale", {})
    if isinstance(localized_patterns, Mapping):
        for localized in localized_patterns.values():
            values.extend(localized if isinstance(localized, list) else [localized])
    representative = intent.get("representative_goal_by_locale", {})
    if isinstance(representative, Mapping):
        values.extend(representative.values())
    aliases = definition.get("aliases", {})
    if isinstance(aliases, Mapping):
        for localized in aliases.values():
            values.extend(localized if isinstance(localized, list) else [localized])
    values.extend((definition.get("name_ko", ""), definition.get("name_en", "")))
    return frozenset(
        normalized
        for raw_value in values
        if (normalized := _normalize(str(raw_value).strip()))
    )


def _normalized_goal_rule_terms(intent: Mapping[str, object]) -> frozenset[str]:
    values: list[object] = []
    for raw_rule in intent.get("goal_rules", []):
        if not isinstance(raw_rule, Mapping):
            continue
        raw_terms = raw_rule.get("all_of", [])
        values.extend(raw_terms if isinstance(raw_terms, list) else [raw_terms])
    return frozenset(
        normalized
        for value in values
        if (normalized := _normalize(str(value).strip()))
    )


def _equivalence_projection(
    payload: Mapping[str, object],
    functions: Mapping[str, Mapping[str, object]],
) -> dict[str, str]:
    projection = {function_id: function_id for function_id in functions}
    classes = payload.get("classes")
    if not isinstance(classes, list):
        raise ValueError("equivalence classes must be a list")
    for raw_class in classes:
        if not isinstance(raw_class, Mapping):
            raise ValueError("equivalence class must be an object")
        canonical = str(raw_class.get("canonical_function_id", ""))
        aliases = raw_class.get("alias_function_ids", [])
        if canonical not in functions or not isinstance(aliases, list):
            raise ValueError("equivalence class references an unknown canonical function")
        for alias in aliases:
            alias_id = str(alias)
            if alias_id not in functions or projection[alias_id] != alias_id:
                raise ValueError("equivalence alias is unknown or duplicated")
            projection[alias_id] = canonical
    return projection


def _role_phrase(
    definition: Mapping[str, object],
    locale: str,
    protected: frozenset[str],
    salt: str,
) -> str:
    raw_roles = definition.get("role_hints", [])
    candidates = [
        str(value).strip()
        for value in raw_roles
        if str(value).strip().casefold() not in _GENERIC_UI_ROLES
    ] if isinstance(raw_roles, list) else []
    if locale == "ko":
        rewritten = [f"{_rewrite_ko(value)} 권한을 맡은 사람" for value in candidates]
        rewritten.append("마지막 선택권을 가진 현재 이용자")
    else:
        rewritten = [f"the authorized {_rewrite_en(value)} practitioner" for value in candidates]
        rewritten.append("the current operator who owns the consequential choice")
    return _choose_clean(rewritten, protected, locale, salt, "role")


def _asset_phrase(
    definition: Mapping[str, object],
    locale: str,
    protected: frozenset[str],
    salt: str,
) -> str:
    raw_assets = definition.get("asset_cues", [])
    assets = [str(value).strip() for value in raw_assets if str(value).strip()] if isinstance(raw_assets, list) else []
    domain = str(definition.get("domain", "")).replace("_", " ")
    if locale == "ko":
        candidates = [f"{_rewrite_ko(value)}에 관련된 관리 자료" for value in assets]
        candidates.append(f"{_rewrite_ko(_rewrite_en(domain))} 범주의 관리 대상")
    else:
        candidates = [f"the governed record concerning {_rewrite_en(value)}" for value in assets]
        candidates.append(f"the governed work item in the {_rewrite_en(domain)} area")
    return _choose_clean(candidates, protected, locale, salt, "asset")


def _state_phrase(
    intent: Mapping[str, object],
    definition: Mapping[str, object],
    locale: str,
    protected: frozenset[str],
    salt: str,
) -> str:
    raw_states = definition.get("state_cues", {})
    candidates: list[str] = []
    group_order = ("lifecycle", "hold", "permission_required", "loading", "selected", "visible")
    if isinstance(raw_states, Mapping):
        for group in group_order:
            raw_values = raw_states.get(group, [])
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            for value in values:
                if not str(value).strip():
                    continue
                if locale == "ko":
                    candidates.append(f"{_rewrite_ko(str(value))} 조건에 머문 단계")
                else:
                    candidates.append(f"a stage characterized by {_rewrite_en(str(value))}")
    desired_state = str(intent.get("desired_state", "")).replace("_", " ").strip()
    if desired_state:
        if locale == "ko":
            candidates.append(f"{_rewrite_ko(_rewrite_en(desired_state))} 조건을 기다리는 단계")
        else:
            candidates.append(f"a stage awaiting {_rewrite_en(desired_state)}")
    if locale == "ko":
        candidates.append("결과 화면에 닿기 전의 검토 단계")
    else:
        candidates.append("an intermediate review stage before the intended consequence")
    return _choose_clean(candidates, protected, locale, salt, "state")


def _action_phrase(
    intent: Mapping[str, object],
    definition: Mapping[str, object],
    locale: str,
    protected: frozenset[str],
    salt: str,
) -> str:
    candidates: list[str] = []
    locale_rules: list[tuple[str, ...]] = []
    for raw_rule in intent.get("goal_rules", []):
        if not isinstance(raw_rule, Mapping):
            continue
        rule_terminal = str(raw_rule.get("terminal_function", ""))
        if rule_terminal and rule_terminal != str(intent.get("terminal_function", "")):
            continue
        raw_terms = raw_rule.get("all_of", [])
        if not isinstance(raw_terms, list):
            continue
        terms = tuple(str(value).strip() for value in raw_terms if str(value).strip())
        if terms and _fragment_locale(" ".join(terms)) == locale:
            locale_rules.append(terms)
    for terms in locale_rules[:20]:
        selected = tuple(reversed(terms[: min(3, len(terms))]))
        if locale == "ko":
            rewritten = [_rewrite_ko(value) for value in selected]
            if len(rewritten) >= 2:
                candidates.append(
                    f"{rewritten[0]} 조건을 고려하면서 {rewritten[1]} 쪽 결과를 성립시키는 처리"
                )
            else:
                candidates.append(f"{rewritten[0]} 의미를 실제 결과로 성립시키는 처리")
        else:
            rewritten = [_rewrite_en(value) for value in selected]
            if len(rewritten) >= 2:
                candidates.append(
                    f"bringing about {rewritten[0]} while satisfying the constraint around {rewritten[1]}"
                )
            else:
                candidates.append(f"bringing about the operational meaning of {rewritten[0]}")

    name = str(definition.get("name_ko" if locale == "ko" else "name_en", ""))
    function_words = str(definition.get("function_id", "")).replace(".", " ").replace("_", " ")
    if locale == "ko":
        candidates.extend(
            (
                f"{_rewrite_ko(name)}에 해당하는 결과를 갖추는 처리",
                f"{_rewrite_ko(_rewrite_en(function_words))} 의미의 결과를 갖추는 처리",
            )
        )
    else:
        candidates.extend(
            (
                f"bringing about the outcome described as {_rewrite_en(name)}",
                f"fulfilling the operational purpose of {_rewrite_en(function_words)}",
            )
        )
    return _choose_clean(candidates, protected, locale, salt, "action")


def _outcome_phrase(
    intent: Mapping[str, object],
    definition: Mapping[str, object],
    locale: str,
    protected: frozenset[str],
    salt: str,
) -> str:
    state_changing = bool(definition.get("state_changing", False))
    never_auto = str(definition.get("automation_policy", "")) == "never_auto"
    if locale == "ko":
        candidates = [
            "영향을 주는 조작 바로 앞의 검토 지점" if state_changing or never_auto else "관련 내용을 눈으로 검토할 수 있는 도착 지점",
            "내가 후속 선택을 판단할 수 있도록 필요한 조건이 드러난 상태",
        ]
    else:
        candidates = [
            "a review point immediately before any consequential control" if state_changing or never_auto else "a destination where the relevant information is available for inspection",
            "a condition in which I can judge the remaining choice myself",
        ]
    return _choose_clean(candidates, protected, locale, salt, "outcome")


def _safety_phrase(definition: Mapping[str, object], locale: str) -> str:
    protected_boundary = (
        bool(definition.get("state_changing", False))
        or str(definition.get("automation_policy", "")) == "never_auto"
        or str(definition.get("risk_level", "")) == "high"
    )
    if locale == "ko":
        return (
            "결과를 바꾸는 마지막 조작은 내가 직접 맡는다"
            if protected_boundary
            else "도착한 뒤의 선택은 내가 살펴보고 맡는다"
        )
    return (
        "the final consequential control remains exclusively mine"
        if protected_boundary
        else "I retain the choice that follows arrival"
    )


def _choose_clean(
    candidates: Sequence[str],
    protected: frozenset[str],
    locale: str,
    salt: str,
    dimension: str,
) -> str:
    for candidate in candidates:
        normalized = _normalize(candidate)
        if normalized and not any(value in normalized for value in protected):
            return candidate
    code = hashlib.sha256(f"{salt}:{dimension}".encode("utf-8")).hexdigest()[:10]
    if locale == "ko":
        return f"검토 분류 부호 {code}에 대응하는 {dimension} 조건"
    return f"the {dimension} condition indexed by review reference {code}"


def _rewrite_ko(value: str) -> str:
    rewritten = re.sub(r"[_/]+", " ", str(value)).strip()
    for source, replacement in _KOREAN_REWRITES:
        rewritten = rewritten.replace(source, replacement)
    if _fragment_locale(rewritten) == "en":
        rewritten = _rewrite_en(rewritten)
    return re.sub(r"\s+", " ", rewritten).strip()


def _rewrite_en(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9\s]+", str(value).replace("_", " "))
    rewritten = [_ENGLISH_REWRITES.get(word.casefold(), word.casefold()) for word in words]
    return re.sub(r"\s+", " ", " ".join(rewritten)).strip()


def _fragment_locale(value: str) -> str:
    if re.search(r"[\uac00-\ud7a3]", value):
        return "ko"
    return "en" if re.search(r"[A-Za-z]", value) else "unknown"


def _intent_generation(intent_id: str) -> str:
    match = re.match(r"^(v(?:[3-9]|1[0-5]))_", intent_id)
    return match.group(1) if match else "core"
