from __future__ import annotations

import json
import hashlib
import math
import re
import sqlite3
import unicodedata
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from functools import lru_cache
from heapq import nlargest
from pathlib import Path
from threading import Lock
from typing import Callable, Iterable, Iterator, Mapping, Sequence

from app.config import Settings, get_settings
from app.resource_paths import get_resource_root
from app.services.navigation_goal_char_retrieval import (
    CharRetrievalResult,
    get_navigation_goal_char_retriever,
    navigation_goal_char_retrieval_stats,
)
from app.services.universal_navigation_graph import sanitize_text


ROOT = get_resource_root()
DEFAULT_CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DEFAULT_EQUIVALENCE_FILENAME = "function-equivalence.v1.json"
DEFAULT_DATABASE_PATH = ROOT / ".artifacts" / "navigation-function-catalog.sqlite"
CATALOG_SCHEMA_VERSION = "6"
DEFAULT_SCOPE = "cross_app"
NEVER_AUTO_STOP_POLICIES = frozenset(
    {"before_action", "before_activation", "user_confirmation", "user_only", "stop_before_action"}
)
# The final branch of ``_phrase_similarity`` is a SequenceMatcher ratio
# multiplied by this value.  A distinct, non-containing pair is therefore
# strictly below the bound.  Once an exact/containment/rule match reaches the
# bound, running SequenceMatcher for every catalog pattern cannot change the
# winner (including the existing deterministic tie-breaks).
GOAL_FUZZY_SCORE_UPPER_BOUND = 0.72
GOAL_CONCRETE_SCORE_FLOOR = 0.34
# A barely passing edit-distance match is not enough evidence for a regulated
# or otherwise user-owned final action.  Keep this deliberately narrow: it
# only reopens the 0.34..0.36 ambiguity band for high-risk fuzzy winners, while
# reviewed rules, contained phrases, and stronger fuzzy matches stay intact.
GOAL_HIGH_RISK_FUZZY_REVIEW_FLOOR = 0.36
# Exhaustive SequenceMatcher across every pattern is both the slowest path and
# weak evidence for long, sentence-like goals with no exact/rule anchor.  Such
# prose is handled more accurately by the sparse semantic and bounded
# character retrievers.  Short typo-style commands still retain legacy fuzzy
# matching.
GOAL_LONG_PROSE_FUZZY_SKIP_LENGTH = 80
GOAL_SEMANTIC_RERANK_LIMIT = 12
# Reviewed conjunctions remain deterministic evidence, but a short/common
# conjunction can occur incidentally in the context clause of a much longer
# request.  Only this narrow long-prose ambiguity band is reopened.  Exact
# goals and simple reviewed wrappers never enter the challenge path.
GOAL_RULE_CHALLENGE_MIN_LENGTH = 72
GOAL_RULE_CHALLENGE_MIN_MARGIN = 0.045
GOAL_RULE_CHALLENGE_MIN_DIMENSIONS = 2
CANDIDATE_MATCH_SCORE_FLOOR = 0.18
CANDIDATE_STATE_SCORE_MAX = 0.024
GOAL_GENERIC_ROLE_HINTS = frozenset(
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

# Regulated V16 destinations carry an explicit fail-closed boundary.  These
# phrases describe evidence that the user is *not* allowed to proceed to a
# concrete terminal (wrong role/record, unavailable permission, stale state,
# or a hold).  They are intentionally consequence-level and app-independent.
# A matching, unambiguous V16 domain is routed only to its non-terminal hub;
# the user-owned final action is never inferred from this negative evidence.
GOAL_GOVERNANCE_FAILURE_CUES = tuple(
    _cue.casefold()
    for _cue in (
        "wrong role",
        "role not authorized",
        "unauthorized role",
        "other professional role",
        "access denied",
        "not authorized",
        "isn't authorized",
        "is not authorized",
        "unauthorised",
        "insufficient permission",
        "insufficient permissions",
        "different governed asset",
        "wrong asset",
        "wrong person or record",
        "wrong record",
        "record mismatch",
        "different lifecycle state",
        "invalid lifecycle state",
        "state mismatch",
        "missing jurisdiction",
        "wrong jurisdiction",
        "jurisdiction mismatch",
        "jurisdiction hold",
        "permission denied",
        "unavailable permission",
        "disabled control",
        "button is disabled",
        "control is disabled",
        "disabled button",
        "currently unavailable",
        "unavailable control",
        "action unavailable",
        "feature unavailable",
        "service unavailable",
        "system is offline",
        "system is loading",
        "system error",
        "relogin required",
        "currently offline",
        "offline data",
        "offline or stale data",
        "data is stale",
        "stale data",
        "legal hold",
        "safety hold",
        "quality hold",
        "security hold",
        "interlock",
        "권한 없는 역할",
        "잘못된 역할",
        "다른 전문 역할",
        "다른 관리 자산",
        "다른 사람 또는 기록",
        "잘못된 기록",
        "기록 불일치",
        "다른 생명주기 상태",
        "상태 불일치",
        "권한 거부",
        "권한 부족",
        "접근 거부",
        "허가되지 않음",
        "버튼이 비활성",
        "비활성 버튼",
        "컨트롤 비활성",
        "사용 불가",
        "관할 누락",
        "잘못된 관할",
        "관할 불일치",
        "오프라인 상태",
        "시스템 로딩 중",
        "시스템 오류",
        "재로그인 필요",
        "오래된 데이터",
        "법적 보류",
        "안전 보류",
        "품질 보류",
        "보안 보류",
    )
)
GOAL_GOVERNANCE_CATALOG_TAG = "v16_role_governed_operations"
GOAL_GOVERNANCE_BLOCKED_INTENT = "governance_fail_closed"
GOAL_GOVERNANCE_UNSCOPED_FAILURE_CUES = (
    "wrong role",
    "role not authorized",
    "unauthorized role",
    "other professional role",
    "access denied",
    "not authorized",
    "isn't authorized",
    "is not authorized",
    "unauthorised",
    "insufficient permission",
    "insufficient permissions",
    "different governed asset",
    "wrong asset",
    "wrong person or record",
    "wrong record",
    "record mismatch",
    "invalid lifecycle state",
    "state mismatch",
    "missing jurisdiction",
    "wrong jurisdiction",
    "jurisdiction mismatch",
    "jurisdiction hold",
    "permission denied",
    "unavailable permission",
    "legal hold",
    "safety hold",
    "quality hold",
    "security hold",
    "권한 없는 역할",
    "잘못된 역할",
    "다른 전문 역할",
    "다른 관리 자산",
    "다른 사람 또는 기록",
    "잘못된 기록",
    "기록 불일치",
    "다른 생명주기 상태",
    "상태 불일치",
    "권한 거부",
    "권한 부족",
    "접근 거부",
    "허가되지 않음",
    "관할 누락",
    "잘못된 관할",
    "관할 불일치",
    "법적 보류",
    "안전 보류",
    "품질 보류",
    "보안 보류",
)

# Compact, app-independent equivalence classes for consequence-level goals.
# These do not name packages, products, coordinates, or intent IDs.  They
# bridge ordinary user wording to the reviewed function vocabulary and extend
# (rather than replace) the JSON catalog's semantic_lexicon.
GOAL_SEMANTIC_EQUIVALENTS: Mapping[str, tuple[str, ...]] = {
    "visitor": ("visitor", "guest", "outside guest", "방문자", "방문객", "손님", "외부인"),
    "workplace": ("workplace", "office", "company building", "work site", "사업장", "직장", "회사 건물", "사무실"),
    "invite": ("invite", "invitation", "pre-register", "preregister", "초대", "사전 등록", "미리 등록"),
    "physical_access": ("enter a building", "building access", "door access", "entry pass", "출입", "입장", "건물에 들어", "출입증"),
    "donation": ("donation", "donate", "fundraiser support", "contribution", "기부", "후원", "모금 지원"),
    "recurring": ("repeat", "repeating", "every month", "each month", "regularly", "매달", "매월", "되풀이", "주기적으로"),
    "charging": ("electric vehicle charging", "ev charging", "charger", "plugged in", "전기차 충전", "충전기", "충전소"),
    "idle_fee": ("idle fee", "overstay fee", "stays plugged in after charging", "after charging is done", "after charging has completed", "after charging completes", "충전 완료 후", "충전이 끝난 뒤", "충전이 끝난 후", "충전 후 계속 연결", "점유 요금", "추가 점유 금액", "추가 주차 요금"),
    "nutrition": ("nutrition", "diet", "food intake", "영양", "식단", "섭취"),
    "nutrient_goal": ("nutrient target", "nutrition goal", "configure daily nutrients", "macro target", "protein carbohydrate fat", "protein carbs fat", "macronutrient", "영양소 목표", "영양 목표를 정", "탄수화물 단백질 지방", "매크로 목표"),
    "agriculture": ("agriculture", "farm", "crop field", "농업", "농장", "농지", "작물 밭"),
    "field_application": ("pesticide treatment", "fertilizer application", "chemical application", "spray record", "농약 살포", "비료 살포", "방제 기록", "약제 처리"),
    "record_action": ("record an activity", "log what happened", "activity record", "application record", "작업 기록", "작업 내역", "내역을 남기", "실행 기록"),
    "waitlist": ("waitlist", "waiting list", "join the queue", "대기 명단", "대기열", "순번 대기"),
    "full_capacity": ("sold out", "already full", "no spots left", "정원 마감", "자리가 다 찬", "빈자리 없음"),
    "repository": ("source repository", "code repository", "project source", "코드 저장소", "소스 저장소", "프로젝트 소스"),
    "issue_ticket": ("repository issue", "software issue", "issue ticket", "bug ticket", "engineering work item", "work item", "source defect", "저장소 이슈", "소프트웨어 결함", "이슈 티켓", "버그 티켓", "개발 작업 항목", "작업 항목"),
    "create_action": ("create", "create new", "open a new", "register a new", "생성", "작성", "새로 만들", "신규 등록", "새 항목 추가"),
    "invoice": ("invoice", "bill a customer", "customer bill", "청구서", "거래처 청구", "고객 청구"),
    "invoice_draft": ("draft invoice", "create invoice", "new customer invoice", "청구서 작성", "새 고객 청구서", "매출 청구 작성"),
    "lead": ("sales lead", "prospect", "potential customer", "영업 리드", "잠재 고객", "영업 후보"),
    "convert": ("convert", "promote into", "turn into an account", "전환", "정식 고객으로", "계정으로 바꾸"),
    "stock": ("inventory stock", "stock level", "on hand quantity", "재고", "보유 수량", "상품 수량"),
    "quantity_correction": ("adjust inventory", "adjust stock", "adjust quantity", "correct stock", "increase or decrease inventory", "재고 조정", "수량 조정", "재고 바로잡", "수량 늘리거나 줄"),
    "inspection": ("inspection", "inspect", "site inspection", "checklist inspection", "check against drawings", "검사", "검사하고", "현장 점검", "검측"),
    "delivery_proof": ("proof of delivery", "drop-off photo", "delivery evidence", "배송 완료 증빙", "배달 인증", "인도 사진"),
    "incident": ("incident", "service outage event", "operational alert", "장애", "사고 대응", "운영 경보"),
    "acknowledge": ("acknowledge", "take ownership", "confirm receipt", "saw the alert", "take the incident", "인지", "접수 확인", "담당 수락", "경보를 확인", "대응을 맡"),
    "offline_language": ("offline language", "translate without internet", "language pack", "오프라인 언어", "인터넷 없이 번역", "언어 팩"),
    # Route guidance is expressed with several modality words that do not
    # necessarily contain the literal label "start navigation".  Keep two
    # consequence-level concepts so a high-risk fuzzy winner is admitted only
    # when both the guidance action and an explicit start request are present.
    # These phrases are app-independent vocabulary, not copied user goals.
    "route_guidance": (
        "start navigation", "begin guidance", "route guidance",
        "turn-by-turn guidance", "turn by turn guidance", "turn directions",
        "voice-guided directions", "spoken directions", "경로 안내 시작",
        "회전 안내", "음성 길안내", "길 안내",
    ),
    "route_guidance_start": (
        "start navigation", "begin guidance", "begin spoken", "start spoken",
        "start turn-by-turn", "begin turn-by-turn", "내비게이션 시작",
        "안내 시작", "음성 안내 시작", "길안내 시작",
    ),
    "blocked_dates": ("block or unblock dates", "block dates", "unavailable nights", "close calendar dates", "close selected nights", "예약 불가 날짜", "날짜 막기", "숙박 불가일", "숙박일을 막"),
    "vaccination": ("vaccination", "immunization", "vaccine record", "예방 접종", "백신 기록", "접종 내역"),
    "pet": ("pet", "companion animal", "my dog", "my cat", "반려동물", "우리 강아지", "우리 고양이"),
    "library_hold": ("library hold", "reserve a borrowed title", "queue for a book", "도서 예약", "대출 예약", "책 대기 신청"),
    "hold_request": ("place library hold", "place hold", "hold request", "place me in the queue", "request the next copy", "borrowing queue", "join the borrowing queue", "도서 대기", "예약 신청", "대기 순번 잡", "대출 대기 신청", "반납되면 받"),
    "delivery_window": ("delivery window", "arrival time slot", "package time range", "배송 시간대", "도착 시간 범위", "택배 수령 시간"),
    "parking_extension": ("extend parking", "add parking time", "keep the meter running", "more parking time", "running longer", "주차 연장", "주차 시간 추가", "주차 종료 늦추", "주차 시간을 더", "종료 시각에 시간"),
    "prescription_refill": ("refill medicine", "renew prescription", "more of my medication", "처방약 재조제", "약 다시 받기", "처방 갱신"),
    "private_photos": ("locked photos", "private photo folder", "protected picture", "protected pictures", "잠긴 사진", "비공개 사진함", "사진 보안 폴더", "보호된 사진"),
    "smart_home": ("smart home", "home device", "smart lock", "house automation", "스마트홈", "집 기기", "스마트 잠금"),
    "guest_access": ("guest access", "temporary access", "visitor permission", "게스트 접근", "임시 출입", "방문자 권한"),
    "esim": ("esim", "embedded sim", "digital sim", "이심", "전자 심", "디지털 심"),
    "install_new": ("install new", "set up a new", "add a new", "new line setup", "새로 설치", "새 회선 추가", "새 항목을 기기에 추가"),
    "utility_outage": ("utility outage", "outage status", "power outage", "water outage", "service interruption", "electricity interruption", "restoration time", "공급 중단 상태", "정전", "단수", "공급 중단", "복구 시각"),
    "severe_weather": ("severe weather", "storm warning", "dangerous weather", "기상 특보", "폭풍 경보", "위험 기상"),
    "shared_calendar": ("shared calendar", "team calendar", "another person's calendar", "calendars colleagues maintain", "공유 달력", "팀 캘린더", "다른 사람 일정표", "동료들이 함께 관리"),
    "receipt_download": ("download receipt", "save payment proof", "receipt file", "영수증 다운로드", "결제 증빙 저장", "영수증 파일"),
    "security_report": ("security report", "security assessment", "compromised password", "credential exposure", "exposed credential", "reused password", "보안 보고서", "보안 진단", "유출된 암호", "재사용 암호", "계정 정보 노출"),
    "customer_reply": ("public reply", "reply to requester", "reply to customer", "customer can read", "public support response", "send customer answer", "고객에게 답변", "고객이 읽는 답변", "공개 상담 답변", "문의 답장"),
    "refund": ("money back", "return the payment", "reverse a charge", "돈을 돌려받", "결제 되돌리", "환급"),
    "history": ("past activity", "previous records", "earlier transactions", "지난 활동", "이전 기록", "과거 내역"),
    "export": ("export", "take data out", "save a data copy", "내보내기", "데이터 반출", "자료 사본 저장"),
    "report_problem": ("report a problem", "file an issue", "tell support about a fault", "문제 신고", "오류 제보", "고장 알리기"),
}


class CatalogValidationError(ValueError):
    """Raised before a catalog payload is allowed to replace the runtime index."""


@dataclass(frozen=True)
class FunctionAlias:
    locale: str
    phrase: str
    normalized: str


@dataclass(frozen=True)
class FunctionDefinition:
    function_id: str
    domain: str
    name_ko: str
    name_en: str
    description: str
    risk_level: str
    automation_policy: str
    terminal: bool
    state_changing: bool
    legacy_tags: tuple[str, ...]
    scope: str = DEFAULT_SCOPE
    node_kind: str = "navigation"
    stop_policy: str = "continue"
    role_hints: tuple[str, ...] = ()
    asset_cues: tuple[str, ...] = ()
    state_cues: tuple[str, ...] = ()
    risk_cues: tuple[str, ...] = ()
    semantic_concepts: tuple[str, ...] = ()
    semantic_terminal_concepts: tuple[str, ...] = ()
    aliases: tuple[FunctionAlias, ...] = ()
    raw_function_id: str = ""
    canonical_function_id: str = ""


@dataclass(frozen=True)
class FunctionMatch:
    function_id: str
    score: float
    alias_score: float
    context_score: float
    matched_aliases: tuple[str, ...]
    negative_evidence: tuple[str, ...]
    risk_level: str
    automation_policy: str
    terminal: bool
    state_changing: bool
    matched_alias_locales: tuple[str, ...] = ()
    locale_score: float = 0.0
    state_score: float = 0.0
    role_score: float = 0.0
    state_evidence: tuple[str, ...] = ()
    concept_score: float = 0.0
    matched_concepts: tuple[str, ...] = ()
    matched_function_id: str = ""
    canonical_function_id: str = ""


@dataclass(frozen=True, slots=True)
class _CompiledStateCue:
    """Catalog-owned state cue normalized once at catalog load time."""

    canonical: str
    key: str
    normalized_phrase: str = ""
    text_evidence: str = ""


@dataclass(frozen=True, slots=True)
class _AliasRankingFeature:
    """Immutable alias metadata for lossless SequenceMatcher pruning."""

    alias: FunctionAlias
    ordinal: int
    length: int
    character_masks: Mapping[str, int]


@dataclass(frozen=True)
class CatalogGoalPlan:
    intent: str
    terminal_function: str
    preferred_functions: tuple[tuple[str, float], ...]
    avoid_functions: tuple[str, ...]
    confidence: float
    raw_terminal_function: str = ""
    canonical_terminal_function: str = ""


@dataclass(frozen=True)
class GoalRuleDefinition:
    """A semantic goal rule with an optional intent-internal destination."""

    score: float
    terms: tuple[str, ...]
    terminal_function: str = ""
    phrases: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoalPatternDefinition:
    """Precompiled data used by the lossless fuzzy branch-and-bound pass."""

    intent_id: str
    intent_ordinal: int
    pattern_index: int
    normalized: str
    length: int
    character_counts: tuple[tuple[str, int], ...]
    character_masks: Mapping[str, int]
    trigram_count: int


@dataclass(frozen=True)
class GoalSemanticCandidate:
    """One intent destination represented by catalog-owned semantic evidence."""

    intent_id: str
    intent_ordinal: int
    terminal_function: str
    destination_ordinal: int


@dataclass(frozen=True)
class GoalSemanticMatch:
    """A conservative fallback match for wording outside reviewed patterns."""

    intent_id: str
    terminal_function: str
    score: float
    evidence_count: int
    runner_up_score: float


@dataclass(frozen=True)
class _GoalRuleChallenge:
    """Deterministic disposition for one weak reviewed-rule winner."""

    disposition: str
    match: GoalSemanticMatch | None = None


class _ContextPhraseIndex:
    """Lossless substring index for reviewed positive/negative context cues.

    Each phrase of length three or greater is stored under its globally rarest
    trigram.  A text containing that phrase must contain the selected trigram,
    so the posting list is an exact superset of the possible matches.  One- and
    two-character phrases use the complete phrase as their anchor.  ``hits``
    always performs the original final ``phrase in text`` verification and
    emits evidence in the original per-function order; the index changes only
    how impossible phrases are skipped.
    """

    def __init__(
        self,
        contexts: Mapping[str, tuple[tuple[str, str], ...]],
    ) -> None:
        self._contexts = contexts
        trigram_frequency: Counter[str] = Counter()
        phrase_trigrams: dict[tuple[str, int], frozenset[str]] = {}
        for function_id, pairs in contexts.items():
            for phrase_index, (normalized, _original) in enumerate(pairs):
                if len(normalized) < 3:
                    continue
                trigrams = frozenset(
                    normalized[offset : offset + 3]
                    for offset in range(len(normalized) - 2)
                )
                phrase_trigrams[(function_id, phrase_index)] = trigrams
                trigram_frequency.update(trigrams)

        postings: dict[str, dict[str, int]] = {}
        for function_id, pairs in contexts.items():
            for phrase_index, (normalized, _original) in enumerate(pairs):
                if not normalized:
                    continue
                if len(normalized) < 3:
                    anchor = normalized
                else:
                    anchor = min(
                        phrase_trigrams[(function_id, phrase_index)],
                        key=lambda trigram: (trigram_frequency[trigram], trigram),
                    )
                by_function = postings.setdefault(anchor, {})
                by_function[function_id] = (
                    by_function.get(function_id, 0) | (1 << phrase_index)
                )
        self._postings = {
            anchor: tuple(by_function.items())
            for anchor, by_function in postings.items()
        }

    def hits(self, normalized_text: str) -> Mapping[str, tuple[str, ...]]:
        """Return exactly the evidence produced by exhaustive substring scans."""

        if not normalized_text:
            return {}
        candidate_masks: dict[str, int] = {}
        for width in (1, 2, 3):
            if len(normalized_text) < width:
                continue
            anchors = {
                normalized_text[offset : offset + width]
                for offset in range(len(normalized_text) - width + 1)
            }
            for anchor in anchors:
                for function_id, phrase_mask in self._postings.get(anchor, ()):
                    candidate_masks[function_id] = (
                        candidate_masks.get(function_id, 0) | phrase_mask
                    )

        matches: dict[str, tuple[str, ...]] = {}
        for function_id, phrase_mask in candidate_masks.items():
            pairs = self._contexts[function_id]
            evidence: list[str] = []
            while phrase_mask:
                lowest_bit = phrase_mask & -phrase_mask
                phrase_index = lowest_bit.bit_length() - 1
                normalized, original = pairs[phrase_index]
                if normalized and normalized in normalized_text:
                    evidence.append(original)
                phrase_mask ^= lowest_bit
            if evidence:
                matches[function_id] = tuple(evidence)
        return matches


class NavigationFunctionCatalog:
    """Versioned cross-app function ontology backed by SQLite.

    The JSON file is reviewable source data. SQLite is the fast runtime index.
    It stores exact aliases and contextual evidence separately so a short label
    such as ``구독`` can mean either a content feed or billing management.
    """

    def __init__(
        self,
        database_path: Path,
        catalog_path: Path = DEFAULT_CATALOG_PATH,
        equivalence_path: Path | None = None,
    ) -> None:
        self.database_path = database_path
        self.catalog_path = catalog_path
        self.equivalence_path = (
            equivalence_path
            if equivalence_path is not None
            else catalog_path.with_name(DEFAULT_EQUIVALENCE_FILENAME)
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._import_if_needed()
        self._reload_cache()
        self._governance_hubs = tuple(
            definition
            for definition in self._functions.values()
            if definition.node_kind == "hub"
            and GOAL_GOVERNANCE_CATALOG_TAG in definition.legacy_tags
        )
        self._load_equivalence()

    @property
    def version(self) -> str:
        return self._version

    def stats(self) -> dict[str, object]:
        with self._connection() as connection:
            values = connection.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM navigation_functions) AS function_count,
                  (SELECT COUNT(*) FROM navigation_aliases) AS alias_count,
                  (SELECT COUNT(*) FROM navigation_contexts) AS context_count,
                  (SELECT COUNT(*) FROM navigation_function_role_hints) AS role_hint_count,
                  (SELECT COUNT(*) FROM navigation_function_asset_cues) AS asset_cue_count,
                  (SELECT COUNT(*) FROM navigation_function_state_cues) AS state_cue_count,
                  (SELECT COUNT(*) FROM navigation_function_risk_cues) AS risk_cue_count,
                  (SELECT COUNT(*) FROM navigation_function_semantic_concepts) AS semantic_concept_count,
                  (SELECT COUNT(*) FROM navigation_function_semantic_terminal_concepts) AS semantic_terminal_concept_count,
                  (SELECT COUNT(*) FROM navigation_semantic_lexicon) AS semantic_lexicon_phrase_count,
                  (SELECT COUNT(*) FROM navigation_intents) AS intent_count,
                  (SELECT COUNT(*) FROM navigation_intent_goal_rules) AS goal_rule_count,
                  (SELECT COUNT(*) FROM navigation_function_edges) AS edge_count
                """
            ).fetchone()
        char_stats = self.goal_char_retrieval_stats()
        runtime = char_stats.get("runtime")
        return {
            "catalog_version": self.version,
            # Backwards-compatible revision field: it now represents every
            # reviewable source that changes logical runtime behavior.
            "catalog_sha256": self._sha256,
            "physical_catalog_sha256": self._catalog_sha256,
            "catalog_fingerprint": self._sha256,
            "equivalence_sha256": self._equivalence_sha256,
            "equivalence_class_count": len(self._canonical_members),
            "equivalence_alias_count": len(self._alias_to_canonical),
            "physical_function_count": int(values["function_count"]),
            "logical_function_count": len(self._canonical_functions),
            "physical_intent_count": int(values["intent_count"]),
            "logical_intent_count": self._logical_intent_count,
            "physical_default_terminal_count": len(set(self._intent_terminal.values())),
            "logical_default_terminal_count": len(
                {self.canonical_function_id(value) for value in self._intent_terminal.values()}
            ),
            **dict(values),
            "goal_char_retrieval_initialized": bool(char_stats["initialized"]),
            "goal_char_retrieval_build_count": int(char_stats["build_count"]),
            "goal_char_retrieval_query_count": (
                int(runtime["query_count"])
                if isinstance(runtime, Mapping)
                else 0
            ),
            "goal_char_retrieval_admitted_count": (
                int(runtime["admitted_count"])
                if isinstance(runtime, Mapping)
                else 0
            ),
        }

    def goal_char_retrieval_stats(self) -> dict[str, object]:
        """Observe the optional lazy fallback without constructing it."""

        return navigation_goal_char_retrieval_stats(
            self.catalog_path,
            catalog_fingerprint=self._sha256,
        )

    def function(self, function_id: str) -> FunctionDefinition | None:
        """Return the conservative logical definition for a raw or canonical ID."""

        return self.canonical_function(function_id)

    def raw_function(self, function_id: str) -> FunctionDefinition | None:
        """Return the physical catalog row without equivalence projection."""

        return self._functions.get(function_id)

    def canonical_function_id(self, function_id: str) -> str:
        """Project a physical ID to its reviewed canonical ID."""

        return self._alias_to_canonical.get(function_id, function_id)

    def canonical_function(self, function_id: str) -> FunctionDefinition | None:
        """Return a class-level definition with the strict composite safety envelope."""

        return self._canonical_functions.get(self.canonical_function_id(function_id))

    def validate(self) -> None:
        """Revalidate the reviewable JSON source without changing SQLite."""

        validate_catalog_payload(json.loads(self.catalog_path.read_text(encoding="utf-8")))
        if self.equivalence_path.exists():
            validate_equivalence_payload(
                json.loads(self.equivalence_path.read_text(encoding="utf-8")),
                self._functions,
            )

    def plan_goal(self, goal_text: str) -> CatalogGoalPlan:
        normalized_goal = _normalize(goal_text)
        cache_key = _goal_cache_key(goal_text)
        cached = self._goal_plan_cache.get(cache_key)
        if cached is not None:
            return cached
        best_intent, best_score, best_key, best_rule = self._best_goal_match(
            normalized_goal,
            include_fuzzy=False,
        )
        # Exact/wrapper patterns (key class 2) remain authoritative.  A
        # satisfied reviewed rule (key class 1) is also preserved unless it is
        # shallow incidental evidence inside a long, structured V16 request.
        reviewed_winner = best_key[1] >= 1
        rule_challenge = self._challenge_weak_reviewed_rule(
            goal_text=goal_text,
            normalized_goal=normalized_goal,
            best_intent=best_intent,
            best_key=best_key,
            best_rule=best_rule,
        )
        rule_challenge_failed_closed = False
        if rule_challenge is not None:
            if rule_challenge.disposition == "replace" and rule_challenge.match is not None:
                semantic_match = rule_challenge.match
                best_intent = semantic_match.intent_id
                best_score = semantic_match.score
                default_terminal = self._intent_terminal.get(best_intent, "")
                best_rule = (
                    GoalRuleDefinition(
                        score=best_score,
                        terms=(),
                        terminal_function=semantic_match.terminal_function,
                    )
                    if semantic_match.terminal_function != default_terminal
                    else None
                )
                # The admitted ensemble is now the authoritative reviewed
                # decision for the remainder of this call.  It must not be
                # reopened by the generic fallback chain below.
                reviewed_winner = True
                best_key = (best_score, 1, semantic_match.evidence_count, 0, 0)
            elif rule_challenge.disposition == "generic":
                reviewed_winner = False
                rule_challenge_failed_closed = True
                best_intent = "generic_navigation"
                best_score = GOAL_CONCRETE_SCORE_FLOOR - 0.000001
                best_key = (best_score, 0, 0, 0, 0)
                best_rule = None
        if (
            not rule_challenge_failed_closed
            and not reviewed_winner
            and best_score < GOAL_FUZZY_SCORE_UPPER_BOUND
            and _should_run_exhaustive_goal_fuzzy(normalized_goal, best_score)
        ):
            # Unseen or heavily misspelled goals retain the exact legacy
            # SequenceMatcher winner.  A chain of mathematically safe upper
            # bounds merely avoids evaluating pairs that cannot equal or beat
            # the current winner; this is retrieval-free branch-and-bound,
            # not approximate nearest-neighbour search.
            best_intent, best_score, best_key, best_rule = self._best_fuzzy_goal_match(
                normalized_goal,
                baseline=(best_intent, best_score, best_key, best_rule),
            )
        # Preserve reviewed and sufficiently strong legacy decisions.  A
        # barely passing fuzzy winner that points at a high-risk destination
        # is deliberately reopened: V13's much larger vocabulary exposed
        # unrelated long goals that crossed the old 0.34 boundary by only a
        # few thousandths.  Rich semantic/character evidence may rescue it;
        # otherwise it fails closed to generic navigation.
        fallback_required = (
            not rule_challenge_failed_closed
            and self._goal_match_requires_fallback(
                best_intent=best_intent,
                best_score=best_score,
                best_key=best_key,
                reviewed_winner=reviewed_winner,
            )
        )
        if fallback_required:
            semantic_match = self._best_semantic_goal_match(goal_text)
            if semantic_match is not None:
                best_intent = semantic_match.intent_id
                best_score = semantic_match.score
                default_terminal = self._intent_terminal.get(best_intent, "")
                best_rule = (
                    GoalRuleDefinition(
                        score=best_score,
                        terms=(),
                        terminal_function=semantic_match.terminal_function,
                    )
                    if semantic_match.terminal_function != default_terminal
                    else None
                )
                fallback_required = False
        # Only an unresolved result may consult the bounded character/word
        # retriever. Reviewed rules, strong fuzzy winners, and admitted
        # semantic destinations are immutable and never enter this branch.
        if fallback_required:
            char_result = self._best_char_goal_match(goal_text)
            if char_result is not None:
                candidate = char_result.candidates[0]
                best_intent = candidate.intent_id
                # TF-IDF cosine values are not calibrated to the reviewed
                # matcher scale.  Map an admitted result just above the
                # concrete threshold while retaining score/margin ordering.
                best_score = min(
                    0.72,
                    0.36
                    + 0.50 * char_result.best_score
                    + 0.20 * char_result.best_margin,
                )
                default_terminal = self._intent_terminal.get(best_intent, "")
                best_rule = (
                    GoalRuleDefinition(
                        score=best_score,
                        terms=(),
                        terminal_function=candidate.terminal_function,
                    )
                    if candidate.terminal_function != default_terminal
                    else None
                )
                fallback_required = False
        # The expanded role/state/clause ensemble is deliberately last.  It
        # can rescue only a result that every pre-existing resolver stage left
        # unresolved, preserving all established non-generic winners.
        if fallback_required:
            semantic_match = self._best_enriched_semantic_goal_match(goal_text)
            if semantic_match is not None:
                best_intent = semantic_match.intent_id
                best_score = semantic_match.score
                default_terminal = self._intent_terminal.get(best_intent, "")
                best_rule = (
                    GoalRuleDefinition(
                        score=best_score,
                        terms=(),
                        terminal_function=semantic_match.terminal_function,
                    )
                    if semantic_match.terminal_function != default_terminal
                    else None
                )
                fallback_required = False
        if fallback_required:
            # `_goal_plan_from_match` uses the concrete floor as its final
            # fail-closed boundary.  Demote only the unresolved ambiguity-band
            # winner; ordinary below-floor results were already generic.
            best_intent = "generic_navigation"
            best_score = min(best_score, GOAL_CONCRETE_SCORE_FLOOR - 0.000001)
            best_rule = None
        result = self._goal_plan_from_match(
            best_intent=best_intent,
            best_score=best_score,
            best_rule=best_rule,
        )
        result = self._apply_governance_fail_closed_boundary(
            normalized_goal=normalized_goal,
            result=result,
        )
        _bounded_cache_store(self._goal_plan_cache, cache_key, result)
        return result

    def _apply_governance_fail_closed_boundary(
        self,
        *,
        normalized_goal: str,
        result: CatalogGoalPlan,
    ) -> CatalogGoalPlan:
        """Route negative governance evidence to one unambiguous V16 hub.

        Intent matching is optimized for positive user goals.  A phrase such
        as ``wrong role`` can therefore resemble an unrelated concrete
        destination after the intended high-risk rule rejects it.  V16's
        reviewed safety contract says that these cases stop at the domain hub.
        We enforce that contract only when a domain-specific hub alias is
        present (or the already-selected terminal belongs to that domain), so
        a generic phrase cannot manufacture a cross-domain route.
        """

        if not any(_normalize(cue) in normalized_goal for cue in GOAL_GOVERNANCE_FAILURE_CUES):
            return result

        ranked_hubs: list[tuple[int, str]] = []
        governed_hub_present = bool(self._governance_hubs)
        for definition in self._governance_hubs:
            # Hub aliases also contain shared role names (for example
            # ``compliance officer``).  Only the reviewed bilingual domain
            # names are strong enough to select a hub; shared roles must not
            # redirect one regulated domain into another.
            domain_names = {
                _normalize(definition.name_ko),
                _normalize(definition.name_en),
            }
            specificity = max(
                (
                    len(name)
                    for name in domain_names
                    if len(name) >= 8 and name in normalized_goal
                ),
                default=0,
            )
            if specificity:
                ranked_hubs.append((specificity, definition.function_id))

        selected_definition = self._functions.get(result.terminal_function)
        if (
            not ranked_hubs
            and selected_definition is not None
            and selected_definition.terminal
            and GOAL_GOVERNANCE_CATALOG_TAG in selected_definition.legacy_tags
        ):
            inferred_hub = f"{selected_definition.domain}.hub"
            if inferred_hub in self._functions:
                ranked_hubs.append((1, inferred_hub))

        if not ranked_hubs:
            if governed_hub_present and any(
                _normalize(cue) in normalized_goal
                for cue in GOAL_GOVERNANCE_UNSCOPED_FAILURE_CUES
            ):
                return CatalogGoalPlan(
                    intent=GOAL_GOVERNANCE_BLOCKED_INTENT,
                    terminal_function="",
                    preferred_functions=(),
                    avoid_functions=tuple(
                        dict.fromkeys(
                            (
                                *result.avoid_functions,
                                *(value for value in (result.terminal_function,) if value),
                            )
                        )
                    ),
                    confidence=max(result.confidence, 0.99),
                )
            return result
        # Any two explicit regulated domains are ambiguous, even when one
        # name happens to be longer.  Name length is evidence strength, not
        # permission to choose between conflicting governance boundaries.
        best_hubs = {function_id for _specificity, function_id in ranked_hubs}
        if len(best_hubs) != 1:
            return CatalogGoalPlan(
                intent=GOAL_GOVERNANCE_BLOCKED_INTENT,
                terminal_function="",
                preferred_functions=(),
                avoid_functions=tuple(
                    dict.fromkeys(
                        (
                            *result.avoid_functions,
                            *(value for value in (result.terminal_function,) if value),
                        )
                    )
                ),
                confidence=max(result.confidence, 0.99),
            )

        raw_hub = next(iter(best_hubs))
        hub = self.canonical_function_id(raw_hub)
        avoided = tuple(
            dict.fromkeys(
                (
                    *result.avoid_functions,
                    *(value for value in (result.terminal_function,) if value and value != hub),
                )
            )
        )
        return CatalogGoalPlan(
            intent=GOAL_GOVERNANCE_BLOCKED_INTENT,
            terminal_function=hub,
            preferred_functions=((hub, 1.0),),
            avoid_functions=avoided,
            confidence=max(result.confidence, 0.99),
            raw_terminal_function=raw_hub,
            canonical_terminal_function=hub,
        )

    def apply_governance_evidence_boundary(
        self,
        *,
        result: CatalogGoalPlan,
        evidence_text: str,
    ) -> CatalogGoalPlan:
        """Apply the same V16 boundary to current-screen evidence.

        User goals normally describe the desired positive action; denial,
        disabled, stale, hold, role, and jurisdiction evidence usually lives
        on the current Android screen.  Keeping this operation explicit lets
        API consumers combine both channels before any cache or model action.
        """

        return self._apply_governance_fail_closed_boundary(
            normalized_goal=_normalize(evidence_text),
            result=result,
        )

    def _best_char_goal_match(self, goal_text: str) -> CharRetrievalResult | None:
        """Return an admitted catalog-compatible final fallback, or fail closed."""

        return self._char_goal_match(goal_text, require_admission=True)

    def _char_goal_match(
        self,
        goal_text: str,
        *,
        require_admission: bool,
    ) -> CharRetrievalResult | None:
        """Return a validated character candidate set for fallback or rerank."""

        try:
            result = get_navigation_goal_char_retriever(
                self.catalog_path,
                catalog_fingerprint=self._sha256,
            ).retrieve(goal_text, limit=5)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            return None
        if (
            result.negated
            or not result.candidates
            or (require_admission and not result.admitted)
        ):
            return None
        candidate = result.candidates[0]
        if candidate.intent_id not in self._intent_terminal:
            return None
        allowed_terminals = {
            self._intent_terminal[candidate.intent_id],
            *(
                rule.terminal_function
                for rule in self._intent_goal_rules.get(candidate.intent_id, ())
                if rule.terminal_function
            ),
        }
        if (
            candidate.terminal_function not in allowed_terminals
            or candidate.terminal_function not in self._functions
        ):
            return None
        return result

    def _goal_match_requires_fallback(
        self,
        *,
        best_intent: str,
        best_score: float,
        best_key: tuple[float, int, int, int, int],
        reviewed_winner: bool,
    ) -> bool:
        """Identify unresolved or weak high-risk fuzzy goal decisions."""

        if reviewed_winner:
            return False
        if best_score < GOAL_CONCRETE_SCORE_FLOOR:
            return True
        if best_key[1] != 0 or best_score >= GOAL_HIGH_RISK_FUZZY_REVIEW_FLOOR:
            return False
        terminal = self._intent_terminal.get(best_intent, "")
        definition = self._functions.get(terminal)
        return bool(
            definition is not None
            and (
                definition.risk_level == "high"
                or definition.automation_policy == "never_auto"
            )
        )

    def _challenge_weak_reviewed_rule(
        self,
        *,
        goal_text: str,
        normalized_goal: str,
        best_intent: str,
        best_key: tuple[float, int, int, int, int],
        best_rule: GoalRuleDefinition | None,
    ) -> _GoalRuleChallenge | None:
        """Reopen only a shallow V16 rule embedded in long composite prose.

        A reviewed conjunction is normally authoritative.  The exception is a
        long request in which a structured purpose clause supplies
        substantially richer evidence for a sibling destination.  Three
        independently compiled retrieval views
        are available: the base semantic index, bounded character/word TF-IDF
        tie-break, and the role/asset/state/jurisdiction-enriched semantic
        index.  A replacement
        needs the enriched winner plus another resolver, a sibling margin, and
        at least two catalog metadata dimensions.  Conflicting strong evidence
        fails closed to generic navigation rather than guessing.
        """

        if best_key[1] != 1 or best_rule is None:
            return None
        raw_terminal = best_rule.terminal_function or self._intent_terminal.get(
            best_intent, ""
        )
        current = self._functions.get(raw_terminal)
        if (
            current is None
            or GOAL_GOVERNANCE_CATALOG_TAG not in current.legacy_tags
            or len(normalized_goal) < GOAL_RULE_CHALLENGE_MIN_LENGTH
        ):
            return None

        stages = _goal_semantic_query_stages(goal_text)
        # A high-precision purpose marker is mandatory.  Mere length or a small
        # coverage ratio is not enough to reopen reviewed collision probes.
        if not stages:
            return None
        # Exact and simple wrapper patterns are key class 2 and returned above.
        # For a class-1 rule, an explicit purpose marker is stronger structural
        # evidence than raw character coverage: Korean domain/function names
        # can legitimately occupy most of the context clause even though the
        # marker declares a different desired destination.
        focused_goal = stages[0] if stages else _goal_semantic_focus_text(goal_text)
        if not focused_goal or _goal_contains_negation(focused_goal):
            return _GoalRuleChallenge("generic")
        # A purpose marker tells us which clause is authoritative; it does not
        # resolve an explicit choice *inside* that clause.  In particular,
        # ``either A or B`` may give both siblings rich role/asset/state
        # evidence and let the semantic reranker choose one by a tiny lexical
        # accident.  Keep that request on the safe hub until the user names a
        # single destination.
        if _goal_has_explicit_alternative(focused_goal):
            return _GoalRuleChallenge("generic")

        semantic = self._best_semantic_goal_match(focused_goal, challenge=True)
        enriched = self._best_enriched_semantic_goal_match(
            focused_goal,
            allow_unanchored=True,
            challenge=True,
        )
        metadata_matches = tuple(
            match
            # When a purpose marker exists, the context before/after that span
            # is explicitly non-authoritative.  Scoring the full sentence can
            # simply re-elect the incidental sibling label we are challenging.
            for stage in tuple(dict.fromkeys(stages or (focused_goal,)))
            if (
                match := self._best_metadata_goal_match(
                    stage,
                    domain=current.domain,
                )
            )
        )
        metadata_match = (
            max(
                metadata_matches,
                key=lambda item: (
                    item.score - item.runner_up_score,
                    item.score,
                    item.evidence_count,
                    item.intent_id,
                    item.terminal_function,
                ),
            )
            if metadata_matches
            else None
        )
        metadata_terminal = self.canonical_function_id(
            "" if metadata_match is None else metadata_match.terminal_function
        )
        metadata_dimensions = (
            frozenset()
            if metadata_match is None
            else self._goal_metadata_dimensions(
                focused_goal,
                metadata_match.terminal_function,
            )
        )
        metadata_strong = bool(
            metadata_match is not None
            and len(metadata_dimensions) >= 4
            and "domain" in metadata_dimensions
            and metadata_match.score - metadata_match.runner_up_score >= 0.07
        )
        semantic_hint = self.canonical_function_id(
            "" if semantic is None else semantic.terminal_function
        )
        enriched_hint = self.canonical_function_id(
            "" if enriched is None else enriched.terminal_function
        )
        # Character retrieval is the bounded tie-break view, not a mandatory
        # first-request index build.  Strong explicit metadata already supplies
        # the required independent evidence; ambiguous metadata with no
        # enriched candidate fails closed without paying the index cost.
        char_result = (
            self._char_goal_match(
                focused_goal,
                require_admission=False,
            )
            if (
                not metadata_strong
                and enriched is not None
                and (not semantic_hint or semantic_hint != enriched_hint)
            )
            else None
        )
        if enriched is None:
            enriched = metadata_match
        elif (
            metadata_match is not None
            and self.canonical_function_id(metadata_match.terminal_function)
            != self.canonical_function_id(enriched.terminal_function)
        ):
            # Two enriched views disagree inside one governed sibling family.
            # Let the independent base/character views arbitrate below; if
            # neither agrees, the normal admission check fails closed.
            semantic_terminal_hint = self.canonical_function_id(
                "" if semantic is None else semantic.terminal_function
            )
            char_terminal_hint = self.canonical_function_id(
                ""
                if char_result is None or not char_result.candidates
                else char_result.candidates[0].terminal_function
            )
            if metadata_strong or metadata_terminal in {
                semantic_terminal_hint,
                char_terminal_hint,
            }:
                enriched = metadata_match

        current_canonical = self.canonical_function_id(raw_terminal)

        def canonical(value: str) -> str:
            return self.canonical_function_id(value) if value else ""

        semantic_terminal = canonical(
            "" if semantic is None else semantic.terminal_function
        )
        char_terminal = canonical(
            ""
            if char_result is None or not char_result.candidates
            else char_result.candidates[0].terminal_function
        )
        enriched_terminal = canonical(
            "" if enriched is None else enriched.terminal_function
        )
        observed = tuple(
            value
            for value in (semantic_terminal, char_terminal, enriched_terminal)
            if value
        )
        if enriched is None or not enriched_terminal:
            if stages:
                # An explicit purpose clause was present but the metadata
                # ensemble could not separate a destination.  Do not let a
                # shallow label from the context clause win by default.
                return _GoalRuleChallenge("generic")
            return (
                _GoalRuleChallenge("generic")
                if any(value != current_canonical for value in observed)
                else _GoalRuleChallenge("preserve")
            )
        if enriched_terminal == current_canonical:
            metadata_confirms_current = bool(
                metadata_strong and metadata_terminal == current_canonical
            )
            return _GoalRuleChallenge(
                "preserve" if metadata_confirms_current else "generic"
            )

        support = 1
        support += int(semantic_terminal == enriched_terminal)
        char_support = bool(
            char_result is not None
            and char_result.candidates
            and char_terminal == enriched_terminal
            and char_result.candidates[0].evidence_count >= 10
            and char_result.candidates[0].word_evidence_count >= 3
            and char_result.candidates[0].margin >= 0.012
        )
        support += int(char_support)
        dimensions = self._goal_metadata_dimensions(
            focused_goal,
            enriched.terminal_function,
        )
        margin = enriched.score - enriched.runner_up_score
        challenger = self._functions.get(enriched.terminal_function)
        admitted = bool(
            challenger is not None
            and GOAL_GOVERNANCE_CATALOG_TAG in challenger.legacy_tags
            and (
                support >= 2
                or (
                    metadata_strong
                    and enriched_terminal == metadata_terminal
                )
            )
            and len(dimensions) >= GOAL_RULE_CHALLENGE_MIN_DIMENSIONS
            and "domain" in dimensions
            and enriched.evidence_count >= 4
            and margin >= GOAL_RULE_CHALLENGE_MIN_MARGIN
        )
        if admitted:
            return _GoalRuleChallenge("replace", enriched)
        return _GoalRuleChallenge("generic")

    def _goal_metadata_dimensions(
        self,
        goal_text: str,
        terminal_function: str,
    ) -> frozenset[str]:
        """Return independently matched destination-governance dimensions."""

        definition = self._functions.get(terminal_function)
        if definition is None:
            return frozenset()
        normalized_goal = _normalize(goal_text)

        def contains(values: Iterable[str], *, groups: frozenset[str] | None = None) -> bool:
            for raw_value in values:
                group, separator, _phrase = str(raw_value).partition(":")
                if groups is not None and (not separator or group not in groups):
                    continue
                phrase = _goal_metadata_phrase(str(raw_value))
                normalized_phrase = _normalize(phrase)
                if len(normalized_phrase) >= 4 and normalized_phrase in normalized_goal:
                    return True
            return False

        dimensions: set[str] = set()
        hub = self._functions.get(f"{definition.domain}.hub")
        domain_values = [definition.domain.replace("_", " ")]
        if hub is not None:
            domain_values.extend((hub.name_ko, hub.name_en))
        if contains(domain_values):
            dimensions.add("domain")
        if contains(
            value
            for value in definition.role_hints
            if value.casefold() not in GOAL_GENERIC_ROLE_HINTS
            and value.casefold() != "authorized responsible role"
        ):
            dimensions.add("role")
        if contains(definition.asset_cues):
            dimensions.add("asset")
        if contains(
            definition.state_cues,
            groups=frozenset({"lifecycle", "visible", "selected"}),
        ):
            dimensions.add("state")
        if contains(
            definition.state_cues,
            groups=frozenset({"jurisdiction"}),
        ):
            dimensions.add("jurisdiction")
        return frozenset(dimensions)

    def _best_metadata_goal_match(
        self,
        goal_text: str,
        *,
        domain: str,
    ) -> GoalSemanticMatch | None:
        """Rank governed siblings by explicit domain/role/asset/state evidence."""

        normalized_goal = _normalize(goal_text)
        if not normalized_goal or _goal_contains_negation(goal_text):
            return None

        def longest_match(values: Iterable[str]) -> int:
            return max(
                (
                    len(normalized)
                    for value in values
                    if (normalized := _normalize(_goal_metadata_phrase(str(value))))
                    and len(normalized) >= 4
                    and normalized in normalized_goal
                ),
                default=0,
            )

        ranked: list[tuple[float, int, int, int, str, str]] = []
        seen: set[str] = set()
        for candidate in self._goal_semantic_candidates:
            terminal = candidate.terminal_function
            if terminal in seen:
                continue
            seen.add(terminal)
            definition = self._functions.get(terminal)
            if (
                definition is None
                or definition.domain != domain
                or GOAL_GOVERNANCE_CATALOG_TAG not in definition.legacy_tags
            ):
                continue
            hub = self._functions.get(f"{domain}.hub")
            domain_values: list[str] = [domain.replace("_", " ")]
            if hub is not None:
                domain_values.extend((hub.name_ko, hub.name_en))
            domain_length = longest_match(domain_values)
            if not domain_length:
                continue
            role_length = longest_match(
                value
                for value in definition.role_hints
                if value.casefold() not in GOAL_GENERIC_ROLE_HINTS
                and value.casefold() != "authorized responsible role"
            )
            asset_length = longest_match(definition.asset_cues)
            state_length = longest_match(
                value
                for value in definition.state_cues
                if str(value).partition(":")[0]
                in {"lifecycle", "visible", "selected"}
            )
            jurisdiction_length = longest_match(
                value
                for value in definition.state_cues
                if str(value).partition(":")[0] == "jurisdiction"
            )
            anchor_length = longest_match(
                (
                    definition.name_ko,
                    definition.name_en,
                    definition.function_id.rsplit(".", 1)[-1].replace("_", " "),
                    *(alias.phrase for alias in definition.aliases),
                )
            )
            dimensions = sum(
                value > 0
                for value in (
                    domain_length,
                    role_length,
                    asset_length,
                    state_length,
                    jurisdiction_length,
                )
            )
            score = 3.0 + min(1.2, domain_length / 36.0)
            score += min(1.6, role_length / 20.0)
            score += min(2.2, asset_length / 16.0)
            score += min(1.4, state_length / 40.0)
            score += min(1.8, jurisdiction_length / 48.0)
            score += min(3.2, anchor_length / 9.0)
            ranked.append(
                (
                    score,
                    dimensions,
                    anchor_length,
                    -candidate.intent_ordinal,
                    terminal,
                    candidate.intent_id,
                )
            )
        if not ranked:
            return None
        alternative_request = bool(
            re.search(
                r"\b(?:either|or)\b|(?:또는|혹은|중\s*하나)",
                unicodedata.normalize("NFKC", sanitize_text(goal_text)).casefold(),
            )
        )
        if alternative_request and sum(item[2] >= 6 for item in ranked) >= 2:
            return None
        ranked.sort(reverse=True)
        best = ranked[0]
        runner_up_raw = ranked[1][0] if len(ranked) > 1 else 0.0
        raw_margin = best[0] - runner_up_raw
        if best[1] < 3 or best[2] < 6 or raw_margin < 0.75:
            return None
        normalized_score = min(0.94, 0.72 + 0.018 * best[1] + 0.0025 * best[2])
        normalized_margin = min(0.14, 0.045 + raw_margin / 24.0)
        return GoalSemanticMatch(
            intent_id=best[5],
            terminal_function=best[4],
            score=round(normalized_score, 6),
            evidence_count=best[1] + int(best[2] > 0),
            runner_up_score=round(max(0.0, normalized_score - normalized_margin), 6),
        )

    def _best_semantic_goal_match(
        self,
        goal_text: str,
        *,
        challenge: bool = False,
    ) -> GoalSemanticMatch | None:
        """Resolve unseen wording from function semantics, without app hints.

        Reviewed patterns and conjunction rules remain the primary resolver.
        This pass is a sparse lexical/concept ensemble over the destination
        function's names, aliases, descriptions, positive context, stable ID
        atoms, and semantic lexicon concepts.  Document-frequency weighting
        suppresses generic UI words automatically.  A minimum evidence and
        winner-margin contract makes ambiguous one-word requests fall back to
        the existing resolver instead of manufacturing confidence.
        """

        legacy_focus = _goal_semantic_focus_text(goal_text)
        return self._semantic_goal_match_for_text(
            legacy_focus,
            postings=self._goal_semantic_postings,
            rerank=False,
            challenge=challenge,
        )

    def _best_enriched_semantic_goal_match(
        self,
        goal_text: str,
        *,
        allow_unanchored: bool = False,
        challenge: bool = False,
    ) -> GoalSemanticMatch | None:
        """Use expanded catalog metadata only after legacy stages decline."""

        stages = _goal_semantic_query_stages(goal_text)
        if not stages and allow_unanchored:
            focused = _goal_semantic_focus_text(goal_text)
            if focused and not _goal_contains_negation(focused):
                stages = (focused,)
        if not stages:
            return None
        postings = self._ensure_goal_semantic_enriched_index()
        challenge_matches: list[GoalSemanticMatch] = []
        for focused_goal in stages:
            match = self._semantic_goal_match_for_text(
                focused_goal,
                postings=postings,
                rerank=True,
                challenge=challenge,
            )
            if match is not None:
                if not challenge:
                    return match
                challenge_matches.append(match)
        if not challenge_matches:
            return None
        return max(
            challenge_matches,
            key=lambda item: (
                item.score - item.runner_up_score,
                item.score,
                item.evidence_count,
                item.intent_id,
                item.terminal_function,
            ),
        )

    def _ensure_goal_semantic_enriched_index(
        self,
    ) -> Mapping[str, tuple[tuple[int, float, float], ...]]:
        """Lazily compile role/state/rule evidence for anchored prose only."""

        existing = self._goal_semantic_enriched_postings
        if existing is not None:
            return existing
        with self._goal_semantic_enriched_lock:
            existing = self._goal_semantic_enriched_postings
            if existing is not None:
                return existing
            enriched_profiles: list[dict[str, float]] = [
                {} for _candidate in self._goal_semantic_candidates
            ]
            for feature, values in self._goal_semantic_postings.items():
                for candidate_index, source_weight, _idf in values:
                    enriched_profiles[candidate_index][feature] = source_weight
            enriched_anchors: list[tuple[str, ...]] = []
            for candidate_index, candidate in enumerate(self._goal_semantic_candidates):
                definition = self._functions[candidate.terminal_function]
                weighted = enriched_profiles[candidate_index]
                anchors = list(self._goal_semantic_anchors[candidate_index])

                def add_text(value: str, source_weight: float) -> None:
                    for feature, intrinsic_weight in _goal_semantic_features(value).items():
                        if feature in self._goal_semantic_base_pruned_features:
                            continue
                        weighted[feature] = max(
                            weighted.get(feature, 0.0),
                            source_weight * intrinsic_weight,
                        )

                def add_anchor(value: str, source_weight: float) -> None:
                    phrase = " ".join(str(value).split())
                    if not phrase:
                        return
                    add_text(phrase, source_weight)
                    if 4 <= len(_normalize(phrase)) <= 96:
                        anchors.append(phrase)

                for phrase in self._intent_pattern_phrases.get(candidate.intent_id, ()):
                    add_anchor(phrase, 1.45)
                default_terminal = self._intent_terminal.get(candidate.intent_id, "")
                for rule in self._intent_goal_rules.get(candidate.intent_id, ()):
                    rule_terminal = rule.terminal_function or default_terminal
                    if rule_terminal != candidate.terminal_function:
                        continue
                    for phrase in rule.phrases:
                        add_anchor(phrase, 1.60)
                for role_hint in definition.role_hints:
                    if role_hint.casefold() not in GOAL_GENERIC_ROLE_HINTS:
                        add_anchor(role_hint, 1.45)
                for asset_cue in definition.asset_cues:
                    add_anchor(_goal_metadata_phrase(asset_cue), 1.40)
                for state_cue in definition.state_cues:
                    add_anchor(_goal_metadata_phrase(state_cue), 1.30)
                for risk_cue in definition.risk_cues:
                    add_text(_goal_metadata_phrase(risk_cue), 0.85)
                enriched_anchors.append(tuple(dict.fromkeys(anchors)))

            self._goal_semantic_anchors = tuple(enriched_anchors)
            existing = _compile_goal_semantic_postings(
                enriched_profiles,
                candidate_count=len(self._goal_semantic_candidates),
            )
            self._goal_semantic_enriched_postings = existing
            return existing

    def _semantic_goal_match_for_text(
        self,
        focused_goal: str,
        *,
        postings: Mapping[str, tuple[tuple[int, float, float], ...]],
        rerank: bool,
        challenge: bool = False,
    ) -> GoalSemanticMatch | None:
        """Score one conservative clause against catalog-derived candidates."""

        # If the conservative focus pass cannot remove a negated alternative,
        # do not guess.  Negation scope is structurally ambiguous and a wrong
        # concrete destination is worse than retaining generic navigation.
        if _goal_contains_negation(focused_goal):
            return None
        query_features = _goal_semantic_features(focused_goal)
        for concept in self._goal_concepts_for_text(_normalize(focused_goal)):
            query_features[f"c:{concept}"] = 1.80
        if not query_features:
            return None
        raw_scores: Counter[int] = Counter()
        evidence: dict[int, set[str]] = {}
        word_evidence: dict[int, set[str]] = {}
        concept_evidence: dict[int, set[str]] = {}
        strongest_word_idf: dict[int, float] = {}
        for feature, query_weight in query_features.items():
            for candidate_index, source_weight, idf in postings.get(
                feature, ()
            ):
                contribution = source_weight * query_weight * idf
                raw_scores[candidate_index] += contribution
                evidence.setdefault(candidate_index, set()).add(feature)
                if feature.startswith(("w:", "c:")):
                    word_evidence.setdefault(candidate_index, set()).add(feature)
                    if feature.startswith("c:"):
                        concept_evidence.setdefault(candidate_index, set()).add(feature)
                    strongest_word_idf[candidate_index] = max(
                        strongest_word_idf.get(candidate_index, 0.0), idf
                    )
        if not raw_scores:
            return None

        normalized_goal = _normalize(focused_goal)
        ranked: list[tuple[float, int, int, int, int]] = []
        for candidate_index, raw_score in raw_scores.items():
            distinct = evidence.get(candidate_index, set())
            lexical = word_evidence.get(candidate_index, set())
            rare_single = (
                len(lexical) == 1
                and strongest_word_idf.get(candidate_index, 0.0) >= 5.5
                and any(
                    len(feature.partition(":")[2]) >= 5
                    for feature in lexical
                )
            )
            has_composition = any(
                feature.startswith(("g2:", "g3:", "c:")) for feature in distinct
            )
            if len(lexical) < 2 and not (rare_single or has_composition):
                continue

            candidate = self._goal_semantic_candidates[candidate_index]
            for phrase in self._goal_semantic_negative_phrases.get(
                candidate.terminal_function, ()
            ):
                if phrase in normalized_goal:
                    raw_score -= 2.25
            if raw_score <= 0:
                continue

            # Saturating normalization keeps this score comparable with the
            # legacy 0..1 matcher.  Lexical breadth and a composed phrase earn
            # confidence, while character fragments alone never pass above.
            lexical_breadth = min(4, len(lexical))
            semantic_score = 0.30 + 0.48 * (raw_score / (raw_score + 11.0))
            semantic_score += 0.025 * max(0, lexical_breadth - 1)
            semantic_score += 0.025 if has_composition else 0.0
            candidate = self._goal_semantic_candidates[candidate_index]
            ranked.append(
                (
                    min(0.94, semantic_score),
                    len(distinct),
                    -candidate.intent_ordinal,
                    -candidate.destination_ordinal,
                    candidate_index,
                )
            )
        if not ranked:
            return None
        # The sparse pass retrieves candidates; a bounded second pass then
        # checks catalog phrases against the focused clause.  This is a
        # reranker, not a sentence lookup: anchors come only from canonical
        # names, aliases, patterns, rules, and positive metadata.  The cap
        # keeps long-prose latency independent of catalog growth.
        if rerank:
            ranked.sort(reverse=True)
            reranked: list[tuple[float, int, int, int, int]] = []
            rerank_indices = {
                item[4] for item in ranked[:GOAL_SEMANTIC_RERANK_LIMIT]
            }
            for item in ranked:
                score, breadth, intent_order, destination_order, candidate_index = item
                if candidate_index in rerank_indices:
                    score = min(
                        0.94,
                        score
                        + _goal_catalog_anchor_bonus(
                            focused_goal,
                            self._goal_semantic_anchors[candidate_index],
                        ),
                    )
                reranked.append(
                    (score, breadth, intent_order, destination_order, candidate_index)
                )
            ranked = reranked
        ranked.sort(reverse=True)
        # Repeated aliases or rules can make a one-concept candidate win by a
        # narrow raw-score margin.  Permit a nearby multi-concept challenger
        # only when it is also materially broader in both lexical and distinct
        # evidence.  This is deliberately asymmetric: an established
        # multi-concept winner is never displaced by this rule.
        initial_best = ranked[0]
        initial_best_index = initial_best[4]
        initial_concepts = concept_evidence.get(initial_best_index, set())
        if len(initial_concepts) <= 1:
            initial_words = word_evidence.get(initial_best_index, set())
            challengers = [
                item
                for item in ranked[1:GOAL_SEMANTIC_RERANK_LIMIT]
                if initial_best[0] - item[0] <= 0.015
                and len(concept_evidence.get(item[4], ())) >= 2
                and len(word_evidence.get(item[4], ())) >= len(initial_words) + 2
                and item[1] >= initial_best[1] + 2
            ]
            if challengers:
                promoted = max(
                    challengers,
                    key=lambda item: (
                        len(concept_evidence.get(item[4], ())),
                        len(word_evidence.get(item[4], ())),
                        item[1],
                        item[0],
                        item[2],
                        item[3],
                    ),
                )
                ranked.remove(promoted)
                # The promotion is a bounded composition rerank, so expose a
                # score that remains ordered ahead of the lexical runner-up.
                # This preserves the public best/runner-up score invariant.
                ranked.insert(
                    0,
                    (
                        min(0.94, initial_best[0] + 0.000001),
                        *promoted[1:],
                    ),
                )
        best = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        best_candidate_index = best[4]
        runner_up_candidate_index = ranked[1][4] if len(ranked) > 1 else -1
        best_concepts = concept_evidence.get(best_candidate_index, set())
        exclusive_concepts = {
            feature
            for feature in best_concepts.difference(
                concept_evidence.get(runner_up_candidate_index, set())
            )
            if feature.partition(":")[2] in GOAL_SEMANTIC_EQUIVALENTS
        }
        margin = best[0] - runner_up
        concept_dominant = bool(exclusive_concepts) and (
            len(best_concepts) >= 2 or margin >= 0.020
        )
        # This fallback may turn an otherwise generic result into a concrete
        # destination, so its admission threshold is intentionally much
        # stricter than ordinary ranking.  Require broad evidence, a high
        # absolute score, and a clear sibling margin.  Anything uncertain
        # remains generic and therefore cannot regress an established winner.
        if challenge:
            if (
                best[0] < 0.54
                or best[1] < 3
                or len(word_evidence.get(best_candidate_index, ())) < 2
                or (runner_up and margin < 0.012 and not concept_dominant)
            ):
                return None
        elif (
            best[0] < 0.79
            or best[1] < 4
            or len(word_evidence.get(best_candidate_index, ())) < 3
            or (runner_up and margin < 0.055 and not concept_dominant)
        ):
            return None
        candidate = self._goal_semantic_candidates[best_candidate_index]
        return GoalSemanticMatch(
            intent_id=candidate.intent_id,
            terminal_function=candidate.terminal_function,
            score=round(best[0], 6),
            evidence_count=best[1],
            runner_up_score=round(runner_up, 6),
        )

    def _best_goal_match(
        self,
        normalized_goal: str,
        *,
        include_fuzzy: bool,
    ) -> tuple[str, float, tuple[float, int, int, int, int], GoalRuleDefinition | None]:
        """Return the legacy winner while avoiding unnecessary fuzzy work.

        Intent and rule iteration order intentionally mirrors the original
        resolver.  The first equal key therefore remains the winner.  In the
        cheap pass, non-containing pattern pairs score zero; callers only
        accept that pass when its winner is mathematically above every score
        such an omitted pair can obtain.
        """

        best_intent = "generic_navigation"
        best_score = 0.0
        best_key = (0.0, 0, 0, 0, 0)
        best_rule: GoalRuleDefinition | None = None
        similarity = _phrase_similarity if include_fuzzy else _phrase_containment_similarity
        candidate_rule_indices = self._candidate_goal_rule_indices(normalized_goal)
        candidate_pattern_indices = (
            None if include_fuzzy else self._candidate_goal_pattern_indices(normalized_goal)
        )
        for intent_id, patterns, rules in self._goal_intent_matchers:
            score = 0.0
            dominant_pattern_length = 0
            selected_patterns = (
                patterns
                if candidate_pattern_indices is None
                else tuple(
                    patterns[index]
                    for index in candidate_pattern_indices.get(intent_id, ())
                )
            )
            for pattern in selected_patterns:
                score = max(score, similarity(normalized_goal, pattern))
                pattern_specificity = _reviewed_pattern_specificity(pattern)
                if (
                    pattern_specificity > dominant_pattern_length
                    and _is_wrapped_reviewed_pattern(normalized_goal, pattern)
                ):
                    dominant_pattern_length = pattern_specificity
            # An exact reviewed goal pattern is definitive.  Quality audit
            # rejects cross-intent exact-pattern collisions, so a broader
            # conjunction from a sibling intent must not override it merely
            # because rules otherwise outrank fuzzy/containment matches.
            # A contained pattern is also definitive when it occupies a
            # meaningful share of a short wrapper-style request ("please X",
            # "YouTube에서 X").  The coverage gate deliberately excludes
            # long situational prose where a short sibling label is merely
            # context, preserving compositional goal rules for those cases.
            if dominant_pattern_length:
                score = 1.0
                intent_key = (
                    score,
                    2,
                    dominant_pattern_length,
                    1,
                    dominant_pattern_length,
                )
            else:
                intent_key = (score, 2 if score >= 1.0 else 0, 0, 0, 0)
            intent_rule: GoalRuleDefinition | None = None
            for rule_index in candidate_rule_indices.get(intent_id, ()):
                rule = rules[rule_index]
                if rule.terms and all(term in normalized_goal for term in rule.terms):
                    # A conjunction is stronger evidence than a fuzzy phrase
                    # at the same score.  Prefer the longest reviewed semantic
                    # cue before counting fragments: one exact compound such
                    # as "device backup ... device data backup" is stronger
                    # than many overlapping tokens accidentally formed across
                    # a domain/feature word boundary.  Remaining ties use cue
                    # count and total evidence length deterministically.
                    rule_key = (
                        rule.score,
                        1,
                        max(len(term) for term in rule.terms),
                        len(rule.terms),
                        sum(len(term) for term in rule.terms),
                    )
                    if rule_key > intent_key:
                        score = rule.score
                        intent_key = rule_key
                        intent_rule = rule
            if intent_key > best_key:
                best_intent, best_score = intent_id, score
                best_key = intent_key
                best_rule = intent_rule
        return best_intent, best_score, best_key, best_rule

    def _best_fuzzy_goal_match(
        self,
        normalized_goal: str,
        *,
        baseline: tuple[
            str,
            float,
            tuple[float, int, int, int, int],
            GoalRuleDefinition | None,
        ],
    ) -> tuple[str, float, tuple[float, int, int, int, int], GoalRuleDefinition | None]:
        """Add only fuzzy pattern evidence to an exact containment/rule pass.

        ``SequenceMatcher.ratio`` is ``2 * M / (len(a) + len(b))``, where its
        ordered matching blocks form a common subsequence.  Therefore ``M``
        cannot exceed any of these progressively tighter quantities:

        * the shorter input length;
        * the multiset character intersection;
        * the exact longest-common-subsequence length.

        The final LCS bound is calculated with a bit-parallel algorithm.  We
        still call the legacy ``_phrase_similarity`` for every pair whose
        bound can challenge the current winner, so scores and deterministic
        tie behaviour are unchanged.  Sorting by the bound finds a strong
        winner early and makes the remaining exclusions substantially larger.
        """

        best_intent, best_score, best_key, best_rule = baseline
        best_ordinal = self._goal_intent_order.get(
            best_intent,
            len(self._goal_intent_order),
        )
        if not normalized_goal:
            return baseline

        # Exact and non-short containment relations were already evaluated in
        # the baseline pass.  The trigram index is a lossless superset, so only
        # those few candidates need a direct substring verification here.
        contained: dict[str, set[int]] = {}
        for intent_id, indices in self._candidate_goal_pattern_indices(
            normalized_goal
        ).items():
            patterns = self._intent_patterns.get(intent_id, ())
            for pattern_index in indices:
                pattern = patterns[pattern_index]
                if min(len(normalized_goal), len(pattern)) <= 2:
                    continue
                if pattern in normalized_goal or normalized_goal in pattern:
                    contained.setdefault(intent_id, set()).add(pattern_index)

        goal_length = len(normalized_goal)
        goal_counts = Counter(normalized_goal)
        goal_masks: dict[str, int] = {}
        for character_index, character in enumerate(normalized_goal):
            goal_masks[character] = goal_masks.get(character, 0) | (1 << character_index)
        # Seed the bound with a small set of high-overlap candidates.  This is
        # only an evaluation order: every non-seed pattern is still admitted
        # by the lossless bounds below, so trigram retrieval cannot alter the
        # result even for misspellings or scripts absent from the index.
        goal_trigrams = {
            normalized_goal[offset : offset + 3]
            for offset in range(max(0, goal_length - 2))
        }
        trigram_overlaps: Counter[tuple[str, int]] = Counter()
        for trigram in goal_trigrams:
            trigram_overlaps.update(self._goal_pattern_trigram_index.get(trigram, ()))

        def seed_rank(item: tuple[tuple[str, int], int]) -> tuple[float, int, int]:
            feature = self._goal_pattern_feature_refs[item[0]]
            denominator = max(1, len(goal_trigrams) + feature.trigram_count)
            return (
                (2.0 * item[1]) / denominator,
                item[1],
                -feature.intent_ordinal,
            )

        evaluated_refs: set[tuple[str, int]] = set()
        for reference, _overlap in nlargest(32, trigram_overlaps.items(), key=seed_rank):
            feature = self._goal_pattern_feature_refs[reference]
            if feature.pattern_index in contained.get(feature.intent_id, ()):
                continue
            score = _phrase_similarity(normalized_goal, feature.normalized)
            evaluated_refs.add(reference)
            intent_key = (score, 0, 0, 0, 0)
            if intent_key > best_key or (
                intent_key == best_key
                and best_intent != "generic_navigation"
                and feature.intent_ordinal < best_ordinal
            ):
                best_intent = feature.intent_id
                best_score = score
                best_key = intent_key
                best_rule = None
                best_ordinal = feature.intent_ordinal

        candidates: list[tuple[float, int, GoalPatternDefinition]] = []
        for feature in self._goal_pattern_features:
            if (feature.intent_id, feature.pattern_index) in evaluated_refs:
                continue
            if feature.pattern_index in contained.get(feature.intent_id, ()):
                continue
            denominator = goal_length + feature.length
            if denominator <= 0:
                continue
            multiplier = (
                0.25
                if min(goal_length, feature.length) <= 2
                else GOAL_FUZZY_SCORE_UPPER_BOUND
            )
            length_upper = (
                (2.0 * min(goal_length, feature.length) / denominator) * multiplier
            )
            if not _fuzzy_bound_can_challenge(
                length_upper,
                intent_ordinal=feature.intent_ordinal,
                best_key=best_key,
                best_ordinal=best_ordinal,
                best_intent=best_intent,
            ):
                continue
            character_matches = 0
            for character, count in feature.character_counts:
                goal_count = goal_counts.get(character, 0)
                if goal_count:
                    character_matches += count if count < goal_count else goal_count
            if not character_matches:
                continue
            character_upper = (
                (2.0 * character_matches / denominator) * multiplier
            )
            if not _fuzzy_bound_can_challenge(
                character_upper,
                intent_ordinal=feature.intent_ordinal,
                best_key=best_key,
                best_ordinal=best_ordinal,
                best_intent=best_intent,
            ):
                continue
            if feature.length < goal_length:
                lcs_matches = _bitset_lcs_length(feature.normalized, goal_masks)
            else:
                lcs_matches = _bitset_lcs_length(
                    normalized_goal,
                    feature.character_masks,
                )
            lcs_upper = (2.0 * lcs_matches / denominator) * multiplier
            if not _fuzzy_bound_can_challenge(
                lcs_upper,
                intent_ordinal=feature.intent_ordinal,
                best_key=best_key,
                best_ordinal=best_ordinal,
                best_intent=best_intent,
            ):
                continue
            candidates.append((lcs_upper, -feature.intent_ordinal, feature))

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        for upper_score, _negative_ordinal, feature in candidates:
            if not _fuzzy_bound_can_challenge(
                upper_score,
                intent_ordinal=feature.intent_ordinal,
                best_key=best_key,
                best_ordinal=best_ordinal,
                best_intent=best_intent,
            ):
                # Bounds are sorted descending, but an equal bound may still
                # matter for an earlier intent, so continue rather than break.
                continue
            score = _phrase_similarity(normalized_goal, feature.normalized)
            intent_key = (score, 0, 0, 0, 0)
            if intent_key > best_key or (
                intent_key == best_key
                and best_intent != "generic_navigation"
                and feature.intent_ordinal < best_ordinal
            ):
                best_intent = feature.intent_id
                best_score = score
                best_key = intent_key
                best_rule = None
                best_ordinal = feature.intent_ordinal
        return best_intent, best_score, best_key, best_rule

    def _candidate_goal_pattern_indices(self, normalized_goal: str) -> dict[str, tuple[int, ...]]:
        """Losslessly prune patterns for the non-fuzzy containment pass.

        Two strings of length at least three can contain one another only if
        they share a trigram. Every pattern is indexed by all its trigrams;
        short patterns are always checked. Goals shorter than three use the
        complete set because they may occur inside any longer phrase.
        """

        if len(normalized_goal) < 3:
            return self._all_goal_pattern_indices
        selected: dict[str, set[int]] = {}
        goal_trigrams = {
            normalized_goal[offset : offset + 3]
            for offset in range(len(normalized_goal) - 2)
        }
        # Pattern-in-goal: each pattern contributes one globally rare anchor;
        # if the pattern occurs, that anchor must occur in the goal.
        for trigram in goal_trigrams:
            for intent_id, pattern_index in self._goal_pattern_anchor_index.get(trigram, ()):
                selected.setdefault(intent_id, set()).add(pattern_index)
        # Goal-in-pattern: every goal trigram occurs in the containing pattern,
        # so looking up only the rarest goal trigram is sufficient and avoids
        # unioning large generic buckets such as "settings" or "menu".
        rarest_goal_trigram = min(
            goal_trigrams,
            key=lambda trigram: len(self._goal_pattern_trigram_index.get(trigram, ())),
        )
        for intent_id, pattern_index in self._goal_pattern_trigram_index.get(
            rarest_goal_trigram, ()
        ):
            selected.setdefault(intent_id, set()).add(pattern_index)
        for intent_id, pattern_index in self._goal_short_pattern_refs:
            selected.setdefault(intent_id, set()).add(pattern_index)
        return {
            intent_id: tuple(sorted(pattern_indices))
            for intent_id, pattern_indices in selected.items()
        }

    def _candidate_goal_rule_indices(self, normalized_goal: str) -> dict[str, tuple[int, ...]]:
        """Return every rule that can possibly satisfy substring matching.

        Each rule is indexed by a three-character slice of its longest term.
        If all rule terms occur in the goal, that slice must occur as well, so
        filtering cannot remove a valid rule.  Short-anchor rules are kept in
        an always-checked bucket.  The final ``all(term in goal)`` test and
        deterministic rule order remain unchanged; this is an exact inverted
        index, not an approximate retrieval stage.
        """

        selected: dict[str, set[int]] = {}
        if len(normalized_goal) >= 3:
            for offset in range(len(normalized_goal) - 2):
                anchor = normalized_goal[offset : offset + 3]
                for intent_id, rule_index in self._goal_rule_anchor_index.get(anchor, ()):
                    selected.setdefault(intent_id, set()).add(rule_index)
        for intent_id, rule_index in self._goal_short_rule_refs:
            selected.setdefault(intent_id, set()).add(rule_index)
        return {
            intent_id: tuple(sorted(rule_indices))
            for intent_id, rule_indices in selected.items()
        }

    def _goal_plan_from_match(
        self,
        *,
        best_intent: str,
        best_score: float,
        best_rule: GoalRuleDefinition | None,
    ) -> CatalogGoalPlan:
        if best_score < GOAL_CONCRETE_SCORE_FLOOR:
            generic = (
                ("settings.root", 0.45),
                ("account.entry", 0.40),
                ("navigation.menu", 0.36),
                ("support.help", 0.30),
            )
            result = CatalogGoalPlan(
                intent="generic_navigation",
                terminal_function="",
                preferred_functions=generic,
                avoid_functions=(),
                confidence=round(best_score, 4),
                raw_terminal_function="",
                canonical_terminal_function="",
            )
        else:
            raw_default_terminal = self._intent_terminal.get(best_intent, "")
            raw_terminal_function = (
                best_rule.terminal_function
                if best_rule is not None and best_rule.terminal_function
                else raw_default_terminal
            )
            raw_route = _route_with_terminal_override(
                self._intent_routes.get(best_intent, ()),
                default_terminal=raw_default_terminal,
                terminal_function=raw_terminal_function,
            )
            terminal_function = self.canonical_function_id(raw_terminal_function)
            preferred_functions = _canonicalize_route(
                raw_route,
                terminal_function=terminal_function,
                canonicalize=self.canonical_function_id,
            )
            avoids = tuple(
                dict.fromkeys(
                    canonical
                    for function_id in self._intent_avoid.get(best_intent, ())
                    if (canonical := self.canonical_function_id(function_id))
                    and canonical != terminal_function
                )
            )
            result = CatalogGoalPlan(
                intent=best_intent,
                terminal_function=terminal_function,
                preferred_functions=preferred_functions,
                avoid_functions=avoids,
                confidence=round(min(1.0, best_score), 4),
                raw_terminal_function=raw_terminal_function,
                canonical_terminal_function=terminal_function,
            )
        return result

    def match_candidate(
        self,
        *,
        label: str,
        parent_label: str = "",
        nearby_text: str = "",
        role: str = "unknown",
        position: str = "unknown",
        limit: int = 8,
        locale: str | None = None,
        enabled: bool | None = None,
        checkable: bool | None = None,
        checked: bool | None = None,
        selected: bool | None = None,
        allowed_function_ids: Iterable[str] | None = None,
    ) -> list[FunctionMatch]:
        label_value = _normalize(label)
        context_value = _normalize(" ".join((parent_label, nearby_text)))
        if not label_value:
            return []
        normalized_locale = _normalize_locale(locale)
        allowed_key = tuple(
            sorted(
                {
                    self.canonical_function_id(str(function_id))
                    for function_id in (allowed_function_ids or ())
                    if str(function_id)
                }
            )
        )
        cache_key = (
            label_value,
            context_value,
            _normalize_metadata_token(role),
            _normalize_metadata_token(position),
            max(1, int(limit)),
            normalized_locale,
            enabled,
            checkable,
            checked,
            selected,
            allowed_key,
        )
        cached = self._candidate_match_cache.get(cache_key)
        if cached is not None:
            return list(cached)
        candidate_state = _candidate_state_cues(
            enabled=enabled,
            checkable=checkable,
            checked=checked,
            selected=selected,
        )
        label_concepts = self._concepts_for_text(label_value)
        context_concepts = self._concepts_for_text(context_value)
        evidence_value = _normalize(" ".join((label, parent_label, nearby_text)))
        positive_hits_by_function = self._positive_context_index.hits(context_value)
        negative_hits_by_function = self._negative_context_index.hits(evidence_value)
        normalized_role = _normalize_metadata_token(role)
        action_role = role.lower() in {"button", "menu", "menuitem", "tab"}
        label_character_counts = Counter(label_value)
        matching_function_ids = tuple(
            function_id
            for function_id in self._functions
            if not allowed_key
            or self.canonical_function_id(function_id) in allowed_key
        )
        matching_function_id_set = frozenset(matching_function_ids)
        alias_bound_cache_key = (label_value, normalized_locale, allowed_key)
        alias_bounds_by_function = self._candidate_alias_bound_cache.get(
            alias_bound_cache_key
        )
        if alias_bounds_by_function is None:
            alias_bounds_by_function = {
                function_id: _alias_score_contribution_bound(
                    label_value,
                    normalized_locale,
                    features,
                    label_character_counts=label_character_counts,
                )
                for function_id, features in self._alias_ranking_features.items()
                if function_id in matching_function_id_set
            }
            _bounded_cache_store(
                self._candidate_alias_bound_cache,
                alias_bound_cache_key,
                alias_bounds_by_function,
                max_size=128,
            )
        candidate_bounds: list[tuple[float, bool, str]] = []
        for function_id in matching_function_ids:
            definition = self._functions[function_id]
            alias_contribution_bound, has_exact_alias = alias_bounds_by_function.get(
                function_id,
                (0.0, False),
            )
            positive_hits = positive_hits_by_function.get(function_id, ())
            raw_negative_hits = negative_hits_by_function.get(function_id, ())
            # An exact alias can shadow only a proper substring already
            # swallowed by that reviewed label. Use the less-negative branch
            # for the ceiling; exact scoring below recomputes the real branch.
            bound_negative_hits = _unshadowed_negative_context_hits(
                raw_negative_hits,
                positive_hits=positive_hits,
                exact_label=label_value if has_exact_alias else "",
            )
            context_score_bound = min(0.24, len(positive_hits) * 0.065) - min(
                0.55,
                len(bound_negative_hits) * 0.24,
            )
            normalized_role_hints = self._normalized_role_hints[function_id]
            role_score = (
                0.012
                if normalized_role and normalized_role in normalized_role_hints
                else 0.0
            )
            concept_score, _matched_concepts = _semantic_concept_score(
                label_concepts,
                definition.semantic_concepts,
                context_concepts=context_concepts,
            )
            position_score = 0.0
            if function_id == "content.subscriptions" and position == "bottom":
                position_score += 0.16
            if function_id == "subscription.manage" and position == "bottom":
                position_score -= 0.18
            score_upper_bound = (
                alias_contribution_bound
                + context_score_bound
                + CANDIDATE_STATE_SCORE_MAX
                + role_score
                + concept_score
            )
            if action_role:
                score_upper_bound += 0.015
            score_upper_bound += position_score
            if score_upper_bound < CANDIDATE_MATCH_SCORE_FLOOR:
                continue
            candidate_bounds.append((score_upper_bound, has_exact_alias, function_id))

        # Evaluate all possible exact-label functions first. The legacy exact
        # ceiling can clamp fuzzy matches, so it must be known before a top-k
        # stopping proof is allowed. Remaining rows are sorted by a proven
        # score ceiling, not by an approximate retrieval score.
        exact_bounds = sorted(
            (item for item in candidate_bounds if item[1]),
            key=lambda item: (-item[0], item[2]),
        )
        fuzzy_bounds = sorted(
            (item for item in candidate_bounds if not item[1]),
            key=lambda item: (-item[0], item[2]),
        )
        results: list[FunctionMatch] = []
        context_specificity: dict[str, int] = {}

        def evaluate_function(function_id: str) -> None:
            definition = self._functions[function_id]
            alias_pairs = _top_alias_pairs(
                label_value,
                normalized_locale,
                self._alias_ranking_features.get(function_id, ()),
                limit=1,
            )
            alias_score = alias_pairs[0][0] if alias_pairs else 0.0
            locale_score = alias_pairs[0][1] if alias_pairs else 0.0
            positive_hits = positive_hits_by_function.get(function_id, ())
            negative_hits = _unshadowed_negative_context_hits(
                negative_hits_by_function.get(function_id, ()),
                positive_hits=positive_hits,
                exact_label=label_value if alias_score >= 0.98 else "",
            )
            context_score = min(0.24, len(positive_hits) * 0.065) - min(0.55, len(negative_hits) * 0.24)
            normalized_role_hints = self._normalized_role_hints[function_id]
            role_score = 0.012 if normalized_role and normalized_role in normalized_role_hints else 0.0
            concept_score, matched_concepts = _semantic_concept_score(
                label_concepts,
                definition.semantic_concepts,
                context_concepts=context_concepts,
            )
            position_score = 0.0
            if function_id == "content.subscriptions" and position == "bottom":
                position_score += 0.16
            if function_id == "subscription.manage" and position == "bottom":
                position_score -= 0.18
            state_score, state_evidence = _state_cue_score(
                self._compiled_state_cues[function_id],
                candidate_state,
                evidence_text=evidence_value,
            )
            # Keep the legacy addition order byte-for-byte for stable rounded
            # scores and deterministic threshold behavior.
            score = (
                alias_score * 0.88
                + context_score
                + locale_score
                + state_score
                + role_score
                + concept_score
            )
            if action_role:
                score += 0.015
            score += position_score
            if score < CANDIDATE_MATCH_SCORE_FLOOR:
                return
            context_specificity[function_id] = max(
                (len(_normalize(phrase)) for phrase in positive_hits),
                default=0,
            )
            results.append(
                FunctionMatch(
                    function_id=function_id,
                    score=round(max(0.0, min(1.0, score)), 4),
                    alias_score=round(alias_score, 4),
                    context_score=round(context_score, 4),
                    # The exact top-three evidence is populated only for the
                    # final limited result set below.  Scoring and admission
                    # need just the exact top-one alias.
                    matched_aliases=(),
                    negative_evidence=negative_hits,
                    risk_level=definition.risk_level,
                    automation_policy=definition.automation_policy,
                    terminal=definition.terminal,
                    state_changing=definition.state_changing,
                    matched_alias_locales=(),
                    locale_score=round(locale_score, 4),
                    state_score=round(state_score, 4),
                    role_score=round(role_score, 4),
                    state_evidence=state_evidence,
                    concept_score=round(concept_score, 4),
                    matched_concepts=matched_concepts,
                    matched_function_id=function_id,
                    canonical_function_id=self.canonical_function_id(function_id),
                )
            )

        for _score_upper_bound, _has_exact_alias, function_id in exact_bounds:
            evaluate_function(function_id)

        logical_results = self._logical_candidate_results(results, context_specificity)
        requested_limit = max(1, limit)
        kth_score = (
            logical_results[requested_limit - 1].score
            if len(logical_results) >= requested_limit
            else None
        )
        admitted_since_rerank = 0
        for score_upper_bound, _has_exact_alias, function_id in fuzzy_bounds:
            # Scores are rounded to four decimals before final ordering. A
            # strict rounded inequality is therefore the exact stopping rule;
            # equality remains eligible so specificity and ID ties survive.
            if kth_score is not None and round(
                max(0.0, min(1.0, score_upper_bound)),
                4,
            ) < kth_score:
                break
            previous_count = len(results)
            evaluate_function(function_id)
            if len(results) != previous_count:
                admitted_since_rerank += 1
            # The kth score cannot decrease as more exactly evaluated rows are
            # added. Recomputing every 256 admissions tightens the safe lower
            # bound without the quadratic behavior of per-row projection.
            if (
                (
                    kth_score is None
                    and len(results) != previous_count
                    and len(results) >= requested_limit
                )
                or admitted_since_rerank >= 256
            ):
                logical_results = self._logical_candidate_results(
                    results,
                    context_specificity,
                )
                kth_score = (
                    logical_results[requested_limit - 1].score
                    if len(logical_results) >= requested_limit
                    else None
                )
                admitted_since_rerank = 0

        # A literal reviewed alias remains the strongest evidence channel when
        # the current context does not contradict it.  Compositional concepts
        # are a fallback for unseen paraphrases, not a way to replace exact UI
        # text.  Context can still overturn a negatively evidenced exact alias
        # (for example the content-feed label "구독" on a billing screen).
        exact_scores = [
            item.score
            for item in results
            if item.alias_score >= 0.98 and not item.negative_evidence
        ]
        if exact_scores and max(exact_scores) >= 0.75:
            exact_ceiling = max(exact_scores)
            results = [
                item
                if item.alias_score >= 0.98
                else replace(item, score=round(min(item.score, exact_ceiling - 0.01), 4))
                for item in results
            ]
        results.sort(
            key=lambda item: (
                -item.score,
                -context_specificity.get(item.matched_function_id or item.function_id, 0),
                item.function_id,
            )
        )
        # Score every physical member independently above, including its own
        # negative context and locale evidence.  Only now project to reviewed
        # classes, retaining the maximum-scoring member rather than summing
        # duplicated aliases.
        deduplicated: dict[str, FunctionMatch] = {}
        representative_specificity: dict[str, int] = {}
        for item in results:
            canonical = item.canonical_function_id or item.function_id
            if canonical in deduplicated:
                continue
            logical = self._canonical_functions[canonical]
            deduplicated[canonical] = replace(
                item,
                function_id=canonical,
                canonical_function_id=canonical,
                risk_level=logical.risk_level,
                automation_policy=logical.automation_policy,
                terminal=logical.terminal,
                state_changing=logical.state_changing,
            )
            representative_specificity[canonical] = context_specificity.get(
                item.matched_function_id or item.function_id,
                0,
            )
        logical_results = list(deduplicated.values())
        logical_results.sort(
            key=lambda item: (
                -item.score,
                -representative_specificity.get(item.function_id, 0),
                item.function_id,
            )
        )
        selected_results = tuple(
            self._with_top_alias_evidence(
                item,
                label_value=label_value,
                normalized_locale=normalized_locale,
            )
            for item in logical_results[: max(1, limit)]
        )
        _bounded_cache_store(self._candidate_match_cache, cache_key, selected_results)
        return list(selected_results)

    def _logical_candidate_results(
        self,
        results: list[FunctionMatch],
        context_specificity: Mapping[str, int],
    ) -> list[FunctionMatch]:
        """Project evaluated physical rows using the legacy final ordering.

        This side-effect-free form is also used to prove that the next
        unevaluated score ceiling cannot enter the requested top-k.
        """

        projected_results: list[FunctionMatch] = results
        exact_scores = [
            item.score
            for item in projected_results
            if item.alias_score >= 0.98 and not item.negative_evidence
        ]
        if exact_scores and max(exact_scores) >= 0.75:
            exact_ceiling = max(exact_scores)
            projected_results = [
                item
                if item.alias_score >= 0.98
                else replace(item, score=round(min(item.score, exact_ceiling - 0.01), 4))
                for item in projected_results
            ]
        projected_results = sorted(
            projected_results,
            key=lambda item: (
                -item.score,
                -context_specificity.get(item.matched_function_id or item.function_id, 0),
                item.function_id,
            ),
        )
        deduplicated: dict[str, FunctionMatch] = {}
        representative_specificity: dict[str, int] = {}
        for item in projected_results:
            canonical = item.canonical_function_id or item.function_id
            if canonical in deduplicated:
                continue
            logical = self._canonical_functions[canonical]
            deduplicated[canonical] = replace(
                item,
                function_id=canonical,
                canonical_function_id=canonical,
                risk_level=logical.risk_level,
                automation_policy=logical.automation_policy,
                terminal=logical.terminal,
                state_changing=logical.state_changing,
            )
            representative_specificity[canonical] = context_specificity.get(
                item.matched_function_id or item.function_id,
                0,
            )
        logical_results = list(deduplicated.values())
        logical_results.sort(
            key=lambda item: (
                -item.score,
                -representative_specificity.get(item.function_id, 0),
                item.function_id,
            )
        )
        return logical_results

    def _with_top_alias_evidence(
        self,
        item: FunctionMatch,
        *,
        label_value: str,
        normalized_locale: str,
    ) -> FunctionMatch:
        physical_function_id = item.matched_function_id or item.function_id
        alias_pairs = _top_alias_pairs(
            label_value,
            normalized_locale,
            self._alias_ranking_features.get(physical_function_id, ()),
            limit=3,
        )
        return replace(
            item,
            matched_aliases=tuple(
                alias.phrase
                for raw_score, _, alias in alias_pairs
                if raw_score > 0.35
            ),
            matched_alias_locales=tuple(
                alias.locale
                for raw_score, _, alias in alias_pairs
                if raw_score > 0.35
            ),
        )

    def _alias_pairs_for_label(
        self,
        label_value: str,
        normalized_locale: str,
    ) -> Mapping[str, tuple[tuple[float, float, FunctionAlias], ...]]:
        """Cache the context-independent alias ranking for a visible label.

        One UI label is commonly evaluated against several surrounding-screen
        contexts.  Alias similarity and locale affinity do not change between
        those calls, so recomputing and sorting every function's aliases was a
        large avoidable cost in the self-feedback bench and on real screens.
        The score formula and deterministic ordering are unchanged.
        """

        cache_key = (label_value, normalized_locale)
        cached = self._candidate_alias_pair_cache.get(cache_key)
        if cached is not None:
            return cached
        rankings = {
            function_id: _top_alias_pairs(
                label_value,
                normalized_locale,
                features,
                limit=1,
            )
            for function_id, features in self._alias_ranking_features.items()
        }
        _bounded_cache_store(
            self._candidate_alias_pair_cache,
            cache_key,
            rankings,
            max_size=16,
        )
        return rankings

    def terminal_screen_score(self, function_id: str, screen_text: str) -> float:
        if not function_id:
            return 0.0
        matches = self.match_candidate(label=screen_text, limit=8)
        canonical = self.canonical_function_id(function_id)
        return next((match.score for match in matches if match.function_id == canonical), 0.0)

    def search(self, query: str, limit: int = 20) -> list[dict[str, object]]:
        normalized = _normalize(query)
        rows: list[dict[str, object]] = []
        for function_id, definition in self._functions.items():
            alias_definitions = self._aliases.get(function_id, ())
            aliases = [alias.phrase for alias in alias_definitions]
            score = max(
                [_phrase_similarity(normalized, _normalize(value)) for value in aliases]
                + [_phrase_similarity(normalized, _normalize(definition.name_ko)), 0.0]
            )
            if normalized and score < 0.18:
                continue
            rows.append(
                {
                    "function_id": function_id,
                    "canonical_function_id": self.canonical_function_id(function_id),
                    "domain": definition.domain,
                    "name_ko": definition.name_ko,
                    "name_en": definition.name_en,
                    "description": definition.description,
                    "risk_level": definition.risk_level,
                    "automation_policy": definition.automation_policy,
                    "terminal": definition.terminal,
                    "state_changing": definition.state_changing,
                    "aliases": aliases,
                    "aliases_by_locale": {
                        locale: [alias.phrase for alias in alias_definitions if alias.locale == locale]
                        for locale in sorted({alias.locale for alias in alias_definitions})
                    },
                    "scope": definition.scope,
                    "node_kind": definition.node_kind,
                    "stop_policy": definition.stop_policy,
                    "role_hints": list(definition.role_hints),
                    "asset_cues": list(definition.asset_cues),
                    "state_cues": list(definition.state_cues),
                    "risk_cues": list(definition.risk_cues),
                    "semantic_concepts": list(definition.semantic_concepts),
                    "semantic_terminal_concepts": list(definition.semantic_terminal_concepts),
                    "score": round(score, 4),
                }
            )
        rows.sort(key=lambda item: (-float(item["score"]), str(item["function_id"])))
        return rows[: max(1, min(limit, 100))]

    def _import_if_needed(self) -> None:
        if not self.catalog_path.exists():
            raise RuntimeError(f"Navigation function catalog not found: {self.catalog_path}")
        raw_catalog = self.catalog_path.read_text(encoding="utf-8")
        payload = json.loads(raw_catalog)
        validate_catalog_payload(payload)
        version = str(payload["catalog_version"])
        catalog_sha256 = hashlib.sha256(raw_catalog.encode("utf-8")).hexdigest()
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT value FROM navigation_catalog_metadata WHERE key = 'catalog_version'"
            ).fetchone()
            existing_sha = connection.execute(
                "SELECT value FROM navigation_catalog_metadata WHERE key = 'catalog_sha256'"
            ).fetchone()
            existing_schema = connection.execute(
                "SELECT value FROM navigation_catalog_metadata WHERE key = 'catalog_schema_version'"
            ).fetchone()
            if (
                existing is not None
                and existing["value"] == version
                and existing_sha is not None
                and existing_sha["value"] == catalog_sha256
                and existing_schema is not None
                and existing_schema["value"] == CATALOG_SCHEMA_VERSION
            ):
                return
            self._replace_catalog(connection, payload, version, catalog_sha256)
            connection.commit()

    def _replace_catalog(
        self,
        connection: sqlite3.Connection,
        payload: dict,
        version: str,
        catalog_sha256: str,
    ) -> None:
        for table in (
            "navigation_function_edges",
            "navigation_intent_avoid",
            "navigation_intent_route",
            "navigation_intent_goal_rule_terms",
            "navigation_intent_goal_rules",
            "navigation_intent_patterns",
            "navigation_intents",
            "navigation_contexts",
            "navigation_aliases",
            "navigation_function_risk_cues",
            "navigation_function_semantic_concepts",
            "navigation_function_semantic_terminal_concepts",
            "navigation_semantic_lexicon",
            "navigation_function_state_cues",
            "navigation_function_asset_cues",
            "navigation_function_role_hints",
            "navigation_function_legacy_tags",
            "navigation_functions",
        ):
            connection.execute(f"DELETE FROM {table}")
        for item in payload.get("functions", []):
            function_id = str(item["function_id"])
            connection.execute(
                """
                INSERT INTO navigation_functions (
                  function_id, domain, name_ko, name_en, description, risk_level,
                  automation_policy, terminal, state_changing, scope, node_kind, stop_policy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    function_id,
                    str(item["domain"]),
                    str(item["name_ko"]),
                    str(item["name_en"]),
                    str(item["description"]),
                    str(item["risk_level"]),
                    str(item["automation_policy"]),
                    int(bool(item["terminal"])),
                    int(bool(item["state_changing"])),
                    _metadata_text(item, "scope", DEFAULT_SCOPE),
                    _metadata_text(item, "node_kind", _default_node_kind(item)),
                    _metadata_text(item, "stop_policy", _default_stop_policy(item)),
                ),
            )
            for alias in _iter_aliases(item.get("aliases", {})):
                connection.execute(
                    "INSERT INTO navigation_aliases (function_id, locale, phrase, normalized) VALUES (?, ?, ?, ?)",
                    (function_id, alias.locale, alias.phrase, alias.normalized),
                )
            for polarity, key in (("positive", "positive_context"), ("negative", "negative_context")):
                for phrase in item.get(key, []):
                    connection.execute(
                        "INSERT INTO navigation_contexts (function_id, polarity, phrase, normalized) VALUES (?, ?, ?, ?)",
                        (function_id, polarity, str(phrase), _normalize(str(phrase))),
                    )
            for tag in item.get("legacy_tags", []):
                connection.execute(
                    "INSERT INTO navigation_function_legacy_tags (function_id, tag) VALUES (?, ?)",
                    (function_id, str(tag)),
                )
            for table, key in (
                ("navigation_function_role_hints", "role_hints"),
                ("navigation_function_asset_cues", "asset_cues"),
                ("navigation_function_state_cues", "state_cues"),
                ("navigation_function_risk_cues", "risk_cues"),
            ):
                for value in _metadata_values(item.get(key, ())):
                    connection.execute(
                        f"INSERT INTO {table} (function_id, value) VALUES (?, ?)",
                        (function_id, value),
                    )
            for concept in _semantic_concept_values(item.get("semantic_concepts", ())):
                connection.execute(
                    "INSERT INTO navigation_function_semantic_concepts (function_id, concept) VALUES (?, ?)",
                    (function_id, concept),
                )
            for concept in _semantic_concept_values(item.get("semantic_terminal_concepts", ())):
                connection.execute(
                    "INSERT INTO navigation_function_semantic_terminal_concepts (function_id, concept) VALUES (?, ?)",
                    (function_id, concept),
                )
        for concept, locale, phrase in _iter_semantic_lexicon(payload.get("semantic_lexicon", {})):
            connection.execute(
                "INSERT INTO navigation_semantic_lexicon (concept, locale, phrase, normalized) VALUES (?, ?, ?, ?)",
                (concept, locale, phrase, _normalize(phrase)),
            )
        for intent in payload.get("intents", []):
            intent_id = str(intent["intent_id"])
            connection.execute(
                "INSERT INTO navigation_intents (intent_id, terminal_function) VALUES (?, ?)",
                (intent_id, str(intent.get("terminal_function", ""))),
            )
            for pattern in intent.get("patterns", []):
                connection.execute(
                    "INSERT INTO navigation_intent_patterns (intent_id, pattern, normalized) VALUES (?, ?, ?)",
                    (intent_id, str(pattern), _normalize(str(pattern))),
                )
            for rule_index, rule in enumerate(intent.get("goal_rules", [])):
                rule_id = f"{intent_id}:{rule_index}"
                connection.execute(
                    """
                    INSERT INTO navigation_intent_goal_rules (
                      intent_id, rule_id, score, terminal_function
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        intent_id,
                        rule_id,
                        float(rule.get("score", 0.9)),
                        str(rule.get("terminal_function", "")),
                    ),
                )
                for term in rule.get("all_of", []):
                    connection.execute(
                        "INSERT INTO navigation_intent_goal_rule_terms (intent_id, rule_id, term, normalized) VALUES (?, ?, ?, ?)",
                        (intent_id, rule_id, str(term), _normalize(str(term))),
                    )
            route = _expanded_intent_route(payload, intent)
            for ordinal, step in enumerate(route):
                connection.execute(
                    "INSERT INTO navigation_intent_route (intent_id, ordinal, function_id, weight) VALUES (?, ?, ?, ?)",
                    (intent_id, ordinal, str(step["function_id"]), float(step["weight"])),
                )
                if ordinal:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO navigation_function_edges (
                          intent_id, from_function, to_function, ordinal
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (intent_id, str(route[ordinal - 1]["function_id"]), str(step["function_id"]), ordinal),
                    )
            for function_id in intent.get("avoid_functions", []):
                connection.execute(
                    "INSERT INTO navigation_intent_avoid (intent_id, function_id) VALUES (?, ?)",
                    (intent_id, str(function_id)),
                )
        for rule_index, rule in enumerate(payload.get("supplemental_goal_rules", [])):
            intent_id = str(rule["intent_id"])
            rule_id = f"{intent_id}:supplemental:{rule_index}"
            connection.execute(
                """
                INSERT INTO navigation_intent_goal_rules (
                  intent_id, rule_id, score, terminal_function
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    intent_id,
                    rule_id,
                    float(rule.get("score", 0.9)),
                    str(rule.get("terminal_function", "")),
                ),
            )
            for term in rule.get("all_of", []):
                connection.execute(
                    "INSERT INTO navigation_intent_goal_rule_terms (intent_id, rule_id, term, normalized) VALUES (?, ?, ?, ?)",
                    (intent_id, rule_id, str(term), _normalize(str(term))),
                )
        connection.execute(
            "INSERT OR REPLACE INTO navigation_catalog_metadata (key, value) VALUES ('catalog_version', ?)",
            (version,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO navigation_catalog_metadata (key, value) VALUES ('catalog_sha256', ?)",
            (catalog_sha256,),
        )
        connection.execute(
            "INSERT OR REPLACE INTO navigation_catalog_metadata (key, value) VALUES ('catalog_schema_version', ?)",
            (CATALOG_SCHEMA_VERSION,),
        )

    def _reload_cache(self) -> None:
        with self._connection() as connection:
            metadata = connection.execute(
                "SELECT value FROM navigation_catalog_metadata WHERE key = 'catalog_version'"
            ).fetchone()
            self._version = "" if metadata is None else metadata["value"]
            sha = connection.execute(
                "SELECT value FROM navigation_catalog_metadata WHERE key = 'catalog_sha256'"
            ).fetchone()
            self._catalog_sha256 = "" if sha is None else sha["value"]
            self._sha256 = self._catalog_sha256
            functions = connection.execute("SELECT * FROM navigation_functions ORDER BY function_id").fetchall()
            legacy = connection.execute(
                "SELECT function_id, tag FROM navigation_function_legacy_tags ORDER BY function_id, tag"
            ).fetchall()
            legacy_by_function = _group_values(legacy, "function_id", "tag")
            role_hints = _group_values(
                connection.execute(
                    "SELECT function_id, value FROM navigation_function_role_hints ORDER BY function_id, value"
                ).fetchall(),
                "function_id",
                "value",
            )
            asset_cues = _group_values(
                connection.execute(
                    "SELECT function_id, value FROM navigation_function_asset_cues ORDER BY function_id, value"
                ).fetchall(),
                "function_id",
                "value",
            )
            state_cues = _group_values(
                connection.execute(
                    "SELECT function_id, value FROM navigation_function_state_cues ORDER BY function_id, value"
                ).fetchall(),
                "function_id",
                "value",
            )
            risk_cues = _group_values(
                connection.execute(
                    "SELECT function_id, value FROM navigation_function_risk_cues ORDER BY function_id, value"
                ).fetchall(),
                "function_id",
                "value",
            )
            semantic_concepts = _group_values(
                connection.execute(
                    "SELECT function_id, concept FROM navigation_function_semantic_concepts "
                    "ORDER BY function_id, concept"
                ).fetchall(),
                "function_id",
                "concept",
            )
            semantic_terminal_concepts = _group_values(
                connection.execute(
                    "SELECT function_id, concept FROM navigation_function_semantic_terminal_concepts "
                    "ORDER BY function_id, concept"
                ).fetchall(),
                "function_id",
                "concept",
            )
            aliases = connection.execute(
                "SELECT function_id, locale, phrase, normalized FROM navigation_aliases "
                "ORDER BY function_id, locale, phrase"
            ).fetchall()
            aliases_by_function = _group_aliases(aliases)
            self._functions = {
                row["function_id"]: FunctionDefinition(
                    function_id=row["function_id"],
                    domain=row["domain"],
                    name_ko=row["name_ko"],
                    name_en=row["name_en"],
                    description=row["description"],
                    risk_level=row["risk_level"],
                    automation_policy=row["automation_policy"],
                    terminal=bool(row["terminal"]),
                    state_changing=bool(row["state_changing"]),
                    legacy_tags=legacy_by_function.get(row["function_id"], ()),
                    scope=row["scope"],
                    node_kind=row["node_kind"],
                    stop_policy=row["stop_policy"],
                    role_hints=role_hints.get(row["function_id"], ()),
                    asset_cues=asset_cues.get(row["function_id"], ()),
                    state_cues=state_cues.get(row["function_id"], ()),
                    risk_cues=risk_cues.get(row["function_id"], ()),
                    semantic_concepts=semantic_concepts.get(row["function_id"], ()),
                    semantic_terminal_concepts=semantic_terminal_concepts.get(row["function_id"], ()),
                    aliases=aliases_by_function.get(row["function_id"], ()),
                    raw_function_id=row["function_id"],
                    canonical_function_id=row["function_id"],
                )
                for row in functions
            }
            # These values belong to the catalog, not the current screen.  The
            # V16 expansion made normalizing them inside every candidate x
            # function comparison dominate runtime, so compile them once per
            # reviewed catalog revision while preserving the score formula.
            self._normalized_role_hints = {
                function_id: frozenset(
                    _normalize_metadata_token(value)
                    for value in definition.role_hints
                )
                for function_id, definition in self._functions.items()
            }
            self._compiled_state_cues = {
                function_id: _compile_state_cues(definition.state_cues)
                for function_id, definition in self._functions.items()
            }
            self._aliases = aliases_by_function
            self._alias_ranking_features = {
                function_id: tuple(
                    _AliasRankingFeature(
                        alias=alias,
                        ordinal=ordinal,
                        length=len(alias.normalized),
                        character_masks=_character_masks(alias.normalized),
                    )
                    for ordinal, alias in enumerate(aliases_for_function)
                )
                for function_id, aliases_for_function in self._aliases.items()
            }
            contexts = connection.execute(
                "SELECT function_id, polarity, normalized, phrase FROM navigation_contexts"
            ).fetchall()
            self._positive_contexts = _group_pairs(
                [row for row in contexts if row["polarity"] == "positive"],
                "function_id",
                "normalized",
                "phrase",
            )
            self._negative_contexts = _group_pairs(
                [row for row in contexts if row["polarity"] == "negative"],
                "function_id",
                "normalized",
                "phrase",
            )
            self._positive_context_index = _ContextPhraseIndex(self._positive_contexts)
            self._negative_context_index = _ContextPhraseIndex(self._negative_contexts)
            pattern_rows = connection.execute(
                "SELECT intent_id, pattern, normalized FROM navigation_intent_patterns"
            ).fetchall()
            self._intent_patterns = _group_values(
                pattern_rows,
                "intent_id",
                "normalized",
            )
            self._intent_pattern_phrases = _group_values(
                pattern_rows,
                "intent_id",
                "pattern",
            )
            rule_terms: dict[tuple[str, str], list[str]] = {}
            rule_phrases: dict[tuple[str, str], list[str]] = {}
            for row in connection.execute(
                "SELECT intent_id, rule_id, term, normalized "
                "FROM navigation_intent_goal_rule_terms ORDER BY intent_id, rule_id"
            ).fetchall():
                key = (str(row["intent_id"]), str(row["rule_id"]))
                rule_terms.setdefault(key, []).append(str(row["normalized"]))
                rule_phrases.setdefault(key, []).append(str(row["term"]))
            goal_rules: dict[str, list[GoalRuleDefinition]] = {}
            for row in connection.execute(
                """
                SELECT intent_id, rule_id, score, terminal_function
                FROM navigation_intent_goal_rules
                ORDER BY intent_id, rule_id
                """
            ).fetchall():
                key = (str(row["intent_id"]), str(row["rule_id"]))
                goal_rules.setdefault(key[0], []).append(
                    GoalRuleDefinition(
                        score=float(row["score"]),
                        terms=tuple(rule_terms.get(key, [])),
                        terminal_function=str(row["terminal_function"]),
                        phrases=tuple(rule_phrases.get(key, [])),
                    )
                )
            self._intent_goal_rules = {key: tuple(value) for key, value in goal_rules.items()}
            # These are already normalized by the import layer.  Compile the
            # hot goal-resolution loop once per catalog reload instead of
            # rebuilding dictionary joins for every request.
            self._goal_intent_matchers = tuple(
                (
                    intent_id,
                    patterns,
                    self._intent_goal_rules.get(intent_id, ()),
                )
                for intent_id, patterns in self._intent_patterns.items()
            )
            self._goal_intent_order = {
                intent_id: ordinal
                for ordinal, (intent_id, _patterns, _rules) in enumerate(
                    self._goal_intent_matchers
                )
            }
            goal_pattern_features: list[GoalPatternDefinition] = []
            for intent_ordinal, (intent_id, patterns, _rules) in enumerate(
                self._goal_intent_matchers
            ):
                for pattern_index, pattern in enumerate(patterns):
                    character_masks: dict[str, int] = {}
                    for character_index, character in enumerate(pattern):
                        character_masks[character] = (
                            character_masks.get(character, 0)
                            | (1 << character_index)
                        )
                    goal_pattern_features.append(
                        GoalPatternDefinition(
                            intent_id=intent_id,
                            intent_ordinal=intent_ordinal,
                            pattern_index=pattern_index,
                            normalized=pattern,
                            length=len(pattern),
                            character_counts=tuple(Counter(pattern).items()),
                            character_masks=character_masks,
                            trigram_count=len(
                                {
                                    pattern[offset : offset + 3]
                                    for offset in range(max(0, len(pattern) - 2))
                                }
                            ),
                        )
                    )
            self._goal_pattern_features = tuple(goal_pattern_features)
            self._goal_pattern_feature_refs = {
                (feature.intent_id, feature.pattern_index): feature
                for feature in self._goal_pattern_features
            }
            pattern_trigram_index: dict[str, list[tuple[str, int]]] = {}
            short_pattern_refs: list[tuple[str, int]] = []
            all_pattern_indices: dict[str, tuple[int, ...]] = {}
            for intent_id, patterns, _rules in self._goal_intent_matchers:
                all_pattern_indices[intent_id] = tuple(range(len(patterns)))
                for pattern_index, pattern in enumerate(patterns):
                    if len(pattern) < 3:
                        short_pattern_refs.append((intent_id, pattern_index))
                        continue
                    trigrams = {
                        pattern[offset : offset + 3]
                        for offset in range(len(pattern) - 2)
                    }
                    for trigram in trigrams:
                        pattern_trigram_index.setdefault(trigram, []).append(
                            (intent_id, pattern_index)
                        )
            self._goal_pattern_trigram_index = {
                trigram: tuple(refs) for trigram, refs in pattern_trigram_index.items()
            }
            pattern_anchor_index: dict[str, list[tuple[str, int]]] = {}
            for intent_id, patterns, _rules in self._goal_intent_matchers:
                for pattern_index, pattern in enumerate(patterns):
                    if len(pattern) < 3:
                        continue
                    trigrams = {
                        pattern[offset : offset + 3]
                        for offset in range(len(pattern) - 2)
                    }
                    anchor = min(
                        trigrams,
                        key=lambda trigram: (
                            len(pattern_trigram_index.get(trigram, ())),
                            trigram,
                        ),
                    )
                    pattern_anchor_index.setdefault(anchor, []).append(
                        (intent_id, pattern_index)
                    )
            self._goal_pattern_anchor_index = {
                trigram: tuple(refs) for trigram, refs in pattern_anchor_index.items()
            }
            self._goal_short_pattern_refs = tuple(short_pattern_refs)
            self._all_goal_pattern_indices = all_pattern_indices
            rule_anchor_index: dict[str, list[tuple[str, int]]] = {}
            short_rule_refs: list[tuple[str, int]] = []
            rule_trigram_counts: dict[str, int] = {}
            indexed_rule_trigrams: list[tuple[str, int, frozenset[str]]] = []
            for intent_id, _patterns, rules in self._goal_intent_matchers:
                for rule_index, rule in enumerate(rules):
                    if not rule.terms:
                        continue
                    trigrams = frozenset(
                        term[offset : offset + 3]
                        for term in rule.terms
                        if len(term) >= 3
                        for offset in range(len(term) - 2)
                    )
                    if not trigrams:
                        short_rule_refs.append((intent_id, rule_index))
                        continue
                    indexed_rule_trigrams.append((intent_id, rule_index, trigrams))
                    for trigram in trigrams:
                        rule_trigram_counts[trigram] = rule_trigram_counts.get(trigram, 0) + 1
            for intent_id, rule_index, trigrams in indexed_rule_trigrams:
                # Any satisfied conjunction contains every trigram from every
                # term. Indexing by the globally rarest one keeps retrieval
                # exact while sharply reducing generic buckets.
                anchor = min(
                    trigrams,
                    key=lambda trigram: (rule_trigram_counts[trigram], trigram),
                )
                rule_anchor_index.setdefault(anchor, []).append((intent_id, rule_index))
            self._goal_rule_anchor_index = {
                anchor: tuple(refs) for anchor, refs in rule_anchor_index.items()
            }
            self._goal_short_rule_refs = tuple(short_rule_refs)
            self._intent_terminal = {
                row["intent_id"]: row["terminal_function"]
                for row in connection.execute("SELECT * FROM navigation_intents").fetchall()
            }
            routes: dict[str, list[tuple[str, float]]] = {}
            for row in connection.execute(
                "SELECT * FROM navigation_intent_route ORDER BY intent_id, ordinal"
            ).fetchall():
                routes.setdefault(row["intent_id"], []).append((row["function_id"], float(row["weight"])))
            self._intent_routes = {key: tuple(value) for key, value in routes.items()}
            self._intent_avoid = _group_values(
                connection.execute("SELECT intent_id, function_id FROM navigation_intent_avoid").fetchall(),
                "intent_id",
                "function_id",
            )
            lexicon_rows = connection.execute(
                "SELECT concept, locale, phrase, normalized FROM navigation_semantic_lexicon "
                "ORDER BY length(normalized) DESC, concept, locale, phrase"
            ).fetchall()
            self._semantic_lexicon = tuple(
                (str(row["concept"]), str(row["normalized"]))
                for row in lexicon_rows
                if str(row["normalized"])
            )
            self._goal_semantic_lexicon = tuple(
                dict.fromkeys(
                    (
                        *self._semantic_lexicon,
                        *(
                            (concept, _normalize(phrase))
                            for concept, phrases in GOAL_SEMANTIC_EQUIVALENTS.items()
                            for phrase in phrases
                            if _normalize(phrase)
                        ),
                    )
                )
            )
            self._compile_goal_semantic_index()
        # Goals and screen candidates recur across the stages of one route.
        # Catalog SHA changes create a fresh object, so cached results never
        # survive a source-data revision.
        self._goal_plan_cache: dict[str, CatalogGoalPlan] = {}
        self._candidate_match_cache: dict[tuple[object, ...], tuple[FunctionMatch, ...]] = {}
        self._candidate_alias_pair_cache: dict[
            tuple[str, str],
            Mapping[str, tuple[tuple[float, float, FunctionAlias], ...]],
        ] = {}
        self._candidate_alias_bound_cache: dict[
            tuple[object, ...],
            Mapping[str, tuple[float, bool]],
        ] = {}
        self._semantic_text_cache: dict[str, frozenset[str]] = {}

    def _load_equivalence(self) -> None:
        """Load the reviewable sibling map without rewriting physical SQLite rows."""

        self._alias_to_canonical: dict[str, str] = {}
        self._canonical_members: dict[str, tuple[str, ...]] = {}
        self._equivalence_sha256 = ""
        equivalence_payload: Mapping[str, object] = {}
        if self.equivalence_path.exists():
            raw_equivalence = self.equivalence_path.read_text(encoding="utf-8")
            loaded = json.loads(raw_equivalence)
            validate_equivalence_payload(loaded, self._functions)
            equivalence_payload = loaded
            self._equivalence_sha256 = hashlib.sha256(
                raw_equivalence.encode("utf-8")
            ).hexdigest()
            self._sha256 = hashlib.sha256(
                f"{self._catalog_sha256}:{self._equivalence_sha256}".encode("utf-8")
            ).hexdigest()

        class_payloads: dict[str, Mapping[str, object]] = {}
        for raw_class in equivalence_payload.get("classes", []):
            if not isinstance(raw_class, Mapping):
                continue
            canonical = str(raw_class["canonical_function_id"])
            members = (
                canonical,
                *(str(value) for value in raw_class.get("alias_function_ids", [])),
            )
            self._canonical_members[canonical] = members
            class_payloads[canonical] = raw_class
            for member in members[1:]:
                self._alias_to_canonical[member] = canonical

        self._functions = {
            function_id: replace(
                definition,
                raw_function_id=function_id,
                canonical_function_id=self.canonical_function_id(function_id),
            )
            for function_id, definition in self._functions.items()
        }
        self._canonical_functions = dict(self._functions)
        for canonical, members in self._canonical_members.items():
            base = self._functions[canonical]
            safety = class_payloads[canonical]["composite_safety"]
            member_definitions = [self._functions[member] for member in members]
            self._canonical_functions[canonical] = replace(
                base,
                risk_level=str(safety["risk_level"]),
                automation_policy=str(safety["automation_policy"]),
                state_changing=bool(safety["state_changing"]),
                stop_policy=str(safety["stop_policy"]),
                aliases=tuple(
                    dict.fromkeys(
                        alias
                        for definition in member_definitions
                        for alias in definition.aliases
                    )
                ),
                raw_function_id=canonical,
                canonical_function_id=canonical,
            )
            for alias in members[1:]:
                self._canonical_functions.pop(alias, None)

        physical_intents = len(self._intent_terminal)
        collapsed_intents = 0
        terminal_ids = set(self._intent_terminal.values())
        for members in self._canonical_members.values():
            represented = sum(member in terminal_ids for member in members)
            collapsed_intents += max(0, represented - 1)
        self._logical_intent_count = physical_intents - collapsed_intents

    def _compile_goal_semantic_index(self) -> None:
        """Compile catalog destination semantics into a sparse IDF index."""

        candidates: list[GoalSemanticCandidate] = []
        base_profile_features: list[dict[str, float]] = []
        semantic_anchors: list[tuple[str, ...]] = []
        negative_phrases: dict[str, tuple[str, ...]] = {}
        for intent_id, _patterns, rules in self._goal_intent_matchers:
            terminal_functions = [self._intent_terminal.get(intent_id, "")]
            terminal_functions.extend(
                rule.terminal_function
                for rule in rules
                if rule.terminal_function
                and rule.terminal_function not in terminal_functions
            )
            for destination_ordinal, terminal_function in enumerate(terminal_functions):
                definition = self._functions.get(terminal_function)
                if definition is None:
                    continue
                candidate = GoalSemanticCandidate(
                    intent_id=intent_id,
                    intent_ordinal=self._goal_intent_order[intent_id],
                    terminal_function=terminal_function,
                    destination_ordinal=destination_ordinal,
                )
                candidates.append(candidate)
                base_weighted: dict[str, float] = {}
                anchors: list[str] = []

                def add_text(
                    weighted: dict[str, float],
                    value: str,
                    source_weight: float,
                ) -> None:
                    for feature, intrinsic_weight in _goal_semantic_features(value).items():
                        weighted[feature] = max(
                            weighted.get(feature, 0.0),
                            source_weight * intrinsic_weight,
                        )

                def add_anchor(
                    weighted: dict[str, float],
                    value: str,
                    source_weight: float,
                ) -> None:
                    phrase = " ".join(str(value).split())
                    if not phrase:
                        return
                    add_text(weighted, phrase, source_weight)
                    if 4 <= len(_normalize(phrase)) <= 96:
                        anchors.append(phrase)

                add_anchor(base_weighted, definition.name_ko, 3.2)
                add_anchor(base_weighted, definition.name_en, 3.2)
                for alias in definition.aliases:
                    add_anchor(base_weighted, alias.phrase, 3.0)
                for _normalized, original in self._positive_contexts.get(
                    terminal_function, ()
                ):
                    add_anchor(base_weighted, original, 2.0)
                add_text(base_weighted, definition.description, 1.15)
                add_text(
                    base_weighted,
                    definition.function_id.replace(".", " ").replace("_", " "),
                    1.35,
                )
                add_text(
                    base_weighted,
                    definition.domain.replace("_", " "),
                    0.75,
                )

                semantic_text = " ".join(
                    (
                        definition.name_ko,
                        definition.name_en,
                        definition.description,
                        *(alias.phrase for alias in definition.aliases),
                    )
                )
                normalized_semantic_text = _normalize(semantic_text)
                inferred_concepts = {
                    concept
                    for concept, phrase in self._goal_semantic_lexicon
                    if phrase and phrase in normalized_semantic_text
                }
                for concept in (
                    *definition.semantic_concepts,
                    *definition.semantic_terminal_concepts,
                    *sorted(inferred_concepts),
                ):
                    base_weighted[f"c:{concept}"] = max(
                        base_weighted.get(f"c:{concept}", 0.0),
                        3.4,
                    )
                base_profile_features.append(base_weighted)

                semantic_anchors.append(tuple(dict.fromkeys(anchors)))

                if terminal_function not in negative_phrases:
                    negative_phrases[terminal_function] = tuple(
                        dict.fromkeys(
                            normalized
                            for normalized, _original in self._negative_contexts.get(
                                terminal_function, ()
                            )
                            if len(normalized) >= 4
                        )
                    )

        self._goal_semantic_candidates = tuple(candidates)
        self._goal_semantic_anchors = tuple(semantic_anchors)
        base_document_frequency: Counter[str] = Counter()
        for features in base_profile_features:
            base_document_frequency.update(features)
        candidate_count = max(1, len(candidates))
        self._goal_semantic_base_pruned_features = frozenset(
            feature
            for feature, frequency in base_document_frequency.items()
            if frequency / candidate_count > 0.42
        )
        self._goal_semantic_postings = _compile_goal_semantic_postings(
            base_profile_features,
            candidate_count=len(candidates),
            document_frequency=base_document_frequency,
        )
        self._goal_semantic_enriched_postings: (
            dict[str, tuple[tuple[int, float, float], ...]] | None
        ) = None
        self._goal_semantic_enriched_lock = Lock()
        self._goal_semantic_negative_phrases = negative_phrases

    def _goal_concepts_for_text(self, normalized_text: str) -> frozenset[str]:
        return frozenset(
            concept
            for concept, phrase in self._goal_semantic_lexicon
            if phrase and phrase in normalized_text
        )

    def _concepts_for_text(self, normalized_text: str) -> frozenset[str]:
        cached = self._semantic_text_cache.get(normalized_text)
        if cached is not None:
            return cached
        concepts = frozenset(
            concept
            for concept, phrase in self._semantic_lexicon
            if phrase and phrase in normalized_text
        )
        _bounded_cache_store(self._semantic_text_cache, normalized_text, concepts)
        return concepts

    def semantic_concepts_for_text(self, text: str) -> frozenset[str]:
        """Expose normalized semantic atoms for destination-policy checks."""

        return self._concepts_for_text(_normalize(text))

    def _ensure_schema(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS navigation_catalog_metadata (
                  key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS navigation_functions (
                  function_id TEXT PRIMARY KEY, domain TEXT NOT NULL, name_ko TEXT NOT NULL,
                  name_en TEXT NOT NULL, description TEXT NOT NULL, risk_level TEXT NOT NULL,
                  automation_policy TEXT NOT NULL, terminal INTEGER NOT NULL, state_changing INTEGER NOT NULL,
                  scope TEXT NOT NULL DEFAULT 'cross_app', node_kind TEXT NOT NULL DEFAULT 'navigation',
                  stop_policy TEXT NOT NULL DEFAULT 'continue'
                );
                CREATE TABLE IF NOT EXISTS navigation_aliases (
                  alias_id INTEGER PRIMARY KEY AUTOINCREMENT, function_id TEXT NOT NULL,
                  locale TEXT NOT NULL, phrase TEXT NOT NULL, normalized TEXT NOT NULL,
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_contexts (
                  context_id INTEGER PRIMARY KEY AUTOINCREMENT, function_id TEXT NOT NULL,
                  polarity TEXT NOT NULL, phrase TEXT NOT NULL, normalized TEXT NOT NULL,
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_function_legacy_tags (
                  function_id TEXT NOT NULL, tag TEXT NOT NULL, PRIMARY KEY(function_id, tag),
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_function_role_hints (
                  function_id TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(function_id, value),
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_function_asset_cues (
                  function_id TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(function_id, value),
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_function_state_cues (
                  function_id TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(function_id, value),
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_function_risk_cues (
                  function_id TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(function_id, value),
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_function_semantic_concepts (
                  function_id TEXT NOT NULL, concept TEXT NOT NULL, PRIMARY KEY(function_id, concept),
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_function_semantic_terminal_concepts (
                  function_id TEXT NOT NULL, concept TEXT NOT NULL, PRIMARY KEY(function_id, concept),
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_semantic_lexicon (
                  concept TEXT NOT NULL, locale TEXT NOT NULL, phrase TEXT NOT NULL, normalized TEXT NOT NULL,
                  PRIMARY KEY(concept, locale, phrase)
                );
                CREATE TABLE IF NOT EXISTS navigation_intents (
                  intent_id TEXT PRIMARY KEY, terminal_function TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS navigation_intent_patterns (
                  pattern_id INTEGER PRIMARY KEY AUTOINCREMENT, intent_id TEXT NOT NULL,
                  pattern TEXT NOT NULL, normalized TEXT NOT NULL,
                  FOREIGN KEY(intent_id) REFERENCES navigation_intents(intent_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_intent_goal_rules (
                  intent_id TEXT NOT NULL, rule_id TEXT NOT NULL, score REAL NOT NULL,
                  terminal_function TEXT NOT NULL DEFAULT '',
                  PRIMARY KEY(intent_id, rule_id),
                  FOREIGN KEY(intent_id) REFERENCES navigation_intents(intent_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_intent_goal_rule_terms (
                  intent_id TEXT NOT NULL, rule_id TEXT NOT NULL, term TEXT NOT NULL,
                  normalized TEXT NOT NULL, PRIMARY KEY(intent_id, rule_id, term),
                  FOREIGN KEY(intent_id, rule_id) REFERENCES navigation_intent_goal_rules(intent_id, rule_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_intent_route (
                  intent_id TEXT NOT NULL, ordinal INTEGER NOT NULL, function_id TEXT NOT NULL,
                  weight REAL NOT NULL, PRIMARY KEY(intent_id, ordinal),
                  FOREIGN KEY(intent_id) REFERENCES navigation_intents(intent_id) ON DELETE CASCADE,
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_intent_avoid (
                  intent_id TEXT NOT NULL, function_id TEXT NOT NULL, PRIMARY KEY(intent_id, function_id),
                  FOREIGN KEY(intent_id) REFERENCES navigation_intents(intent_id) ON DELETE CASCADE,
                  FOREIGN KEY(function_id) REFERENCES navigation_functions(function_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS navigation_function_edges (
                  intent_id TEXT NOT NULL, from_function TEXT NOT NULL, to_function TEXT NOT NULL,
                  ordinal INTEGER NOT NULL, PRIMARY KEY(intent_id, from_function, to_function)
                );
                CREATE INDEX IF NOT EXISTS idx_navigation_alias_normalized ON navigation_aliases(normalized);
                CREATE INDEX IF NOT EXISTS idx_navigation_context_normalized ON navigation_contexts(normalized, polarity);
                CREATE INDEX IF NOT EXISTS idx_navigation_semantic_lexicon_normalized ON navigation_semantic_lexicon(normalized);
                """
            )
            _ensure_sqlite_column(
                connection,
                "navigation_functions",
                "scope",
                "TEXT NOT NULL DEFAULT 'cross_app'",
            )
            _ensure_sqlite_column(
                connection,
                "navigation_functions",
                "node_kind",
                "TEXT NOT NULL DEFAULT 'navigation'",
            )
            _ensure_sqlite_column(
                connection,
                "navigation_functions",
                "stop_policy",
                "TEXT NOT NULL DEFAULT 'continue'",
            )
            _ensure_sqlite_column(
                connection,
                "navigation_intent_goal_rules",
                "terminal_function",
                "TEXT NOT NULL DEFAULT ''",
            )
            connection.commit()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
        finally:
            connection.close()


def _expanded_intent_route(payload: dict, intent: dict) -> list[dict[str, object]]:
    """Materialize reusable cross-app gateway rules into an intent route.

    App-specific routes remain learned by the graph repository. These gateway
    rules only describe common, low-risk entry points such as All menu, My page,
    and the combined Sign in / Sign up hub. Materializing them into SQLite keeps
    runtime ranking fast and makes the source rules reviewable in JSON.
    """

    route = [dict(step) for step in intent.get("route", [])]
    route_function_ids = {str(step["function_id"]) for step in route}
    prepended: list[dict[str, object]] = []
    for rule in payload.get("gateway_rules", []):
        triggers = {str(value) for value in rule.get("when_route_contains_any", [])}
        if triggers and not route_function_ids.intersection(triggers):
            continue
        prepended.extend(dict(step) for step in rule.get("prepend", []))

    merged: list[dict[str, object]] = []
    index_by_function: dict[str, int] = {}
    for step in [*prepended, *route]:
        function_id = str(step["function_id"])
        weight = float(step["weight"])
        existing_index = index_by_function.get(function_id)
        if existing_index is None:
            index_by_function[function_id] = len(merged)
            merged.append({"function_id": function_id, "weight": weight})
            continue
        merged[existing_index]["weight"] = max(float(merged[existing_index]["weight"]), weight)
    return merged


def get_navigation_function_catalog(settings: Settings | None = None) -> NavigationFunctionCatalog:
    settings = settings or get_settings()
    database_path = settings.navigation_function_db_path.strip()
    catalog_path = settings.navigation_function_catalog_path.strip()
    return _cached_catalog(
        str(Path(database_path).expanduser().resolve()) if database_path else str(DEFAULT_DATABASE_PATH),
        str(Path(catalog_path).expanduser().resolve()) if catalog_path else str(DEFAULT_CATALOG_PATH),
        _catalog_source_fingerprint(
            Path(catalog_path).expanduser().resolve() if catalog_path else DEFAULT_CATALOG_PATH
        ),
    )


@lru_cache(maxsize=8)
def _cached_catalog(
    database_path: str,
    catalog_path: str,
    _source_fingerprint: str = "",
) -> NavigationFunctionCatalog:
    return NavigationFunctionCatalog(Path(database_path), Path(catalog_path))


_CATALOG_SOURCE_FINGERPRINT_LOCK = Lock()


class _CatalogSourceChangedDuringRead(RuntimeError):
    pass


def _catalog_source_fingerprint(catalog_path: Path) -> str:
    """Fingerprint both reviewable sources for process-level catalog caching."""

    catalog_path = catalog_path.expanduser().resolve()
    equivalence_path = catalog_path.with_name(DEFAULT_EQUIVALENCE_FILENAME)
    for _attempt in range(3):
        with _CATALOG_SOURCE_FINGERPRINT_LOCK:
            catalog_signature = _catalog_source_stat_signature(catalog_path)
            equivalence_signature = _catalog_source_stat_signature(equivalence_path)
            try:
                fingerprint = _memoized_catalog_source_fingerprint(
                    str(catalog_path),
                    catalog_signature,
                    str(equivalence_path),
                    equivalence_signature,
                )
            except _CatalogSourceChangedDuringRead:
                continue
            if (
                _catalog_source_stat_signature(catalog_path) == catalog_signature
                and _catalog_source_stat_signature(equivalence_path)
                == equivalence_signature
            ):
                return fingerprint
    raise RuntimeError("Navigation catalog sources changed while being fingerprinted")


@lru_cache(maxsize=16)
def _memoized_catalog_source_fingerprint(
    catalog_path: str,
    catalog_signature: tuple[int, ...] | None,
    equivalence_path: str,
    equivalence_signature: tuple[int, ...] | None,
) -> str:
    digest = hashlib.sha256()
    resolved_catalog_path = Path(catalog_path)
    resolved_equivalence_path = Path(equivalence_path)
    if catalog_signature is not None:
        digest.update(
            _read_catalog_source_bytes(resolved_catalog_path, catalog_signature)
        )
    else:
        digest.update(f"missing:{catalog_path}".encode("utf-8"))
    if equivalence_signature is not None:
        digest.update(b"\0equivalence\0")
        digest.update(
            _read_catalog_source_bytes(
                resolved_equivalence_path,
                equivalence_signature,
            )
        )
    if (
        _catalog_source_stat_signature(resolved_catalog_path) != catalog_signature
        or _catalog_source_stat_signature(resolved_equivalence_path)
        != equivalence_signature
    ):
        raise _CatalogSourceChangedDuringRead
    return digest.hexdigest()


def _read_catalog_source_bytes(
    path: Path,
    expected_signature: tuple[int, ...],
) -> bytes:
    try:
        return path.read_bytes()
    except (FileNotFoundError, NotADirectoryError) as error:
        raise _CatalogSourceChangedDuringRead from error
    except OSError as error:
        if _catalog_source_stat_signature(path) != expected_signature:
            raise _CatalogSourceChangedDuringRead from error
        raise


def _catalog_source_stat_signature(path: Path) -> tuple[int, ...] | None:
    try:
        source_stat = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    return (
        int(source_stat.st_dev),
        int(source_stat.st_ino),
        int(source_stat.st_mode),
        int(source_stat.st_nlink),
        int(source_stat.st_size),
        int(source_stat.st_mtime_ns),
        int(source_stat.st_ctime_ns),
        int(getattr(source_stat, "st_birthtime_ns", 0)),
        int(getattr(source_stat, "st_file_attributes", 0)),
    )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", sanitize_text(value)).casefold()
    tokens = _unicode_tokens(normalized)
    return "".join(_strip_korean_particle(token) for token in tokens)


def _unshadowed_negative_context_hits(
    negative_hits: tuple[str, ...],
    *,
    positive_hits: tuple[str, ...],
    exact_label: str,
) -> tuple[str, ...]:
    """Discard only negative fragments swallowed by stronger exact evidence.

    Generated cross-domain guards intentionally contain short words such as
    ``inspection`` or ``close``.  A substring index also finds those words in
    a reviewed positive phrase (``required inspection item``) or in its exact
    alias (``closed``), which previously made a function penalize its own
    evidence.  A proper substring cannot negate the longer reviewed phrase;
    equal phrases and independent negative evidence remain untouched.
    """

    if not negative_hits:
        return ()
    anchors = tuple(
        value
        for value in (
            *(_normalize(hit) for hit in positive_hits),
            exact_label,
        )
        if value
    )
    if not anchors:
        return negative_hits
    retained: list[str] = []
    for hit in negative_hits:
        normalized = _normalize(hit)
        shadowed = bool(
            normalized
            and any(
                normalized != anchor and normalized in anchor
                for anchor in anchors
            )
        )
        if not shadowed:
            retained.append(hit)
    return tuple(retained)


def _goal_semantic_features(value: str) -> dict[str, float]:
    """Return reusable lexical features without retaining a user sentence.

    Word and short phrase features carry the score.  Korean character grams
    are low-weight morphology bridges (for example ``환불`` vs ``환불받기``),
    and can never qualify a candidate on their own.  English suffix variants
    provide the same small bridge for inflected verbs.  All returned features
    are app-agnostic and derived from the supplied text only.
    """

    normalized = unicodedata.normalize("NFKC", sanitize_text(value)).casefold()
    primary_tokens: list[str] = []
    features: dict[str, float] = {}
    for raw_token in _unicode_tokens(normalized):
        token = _strip_korean_particle(raw_token)
        if len(token) <= 1 and not token.isdigit():
            continue
        primary_tokens.append(token)
        features[f"w:{token}"] = max(features.get(f"w:{token}", 0.0), 1.0)
        for variant in _goal_semantic_token_variants(token):
            if variant != token:
                features[f"w:{variant}"] = max(
                    features.get(f"w:{variant}", 0.0), 0.72
                )
        if any("가" <= character <= "힣" for character in token):
            for width, weight in ((2, 0.18), (3, 0.27)):
                if len(token) < width + 1:
                    continue
                for offset in range(len(token) - width + 1):
                    gram = token[offset : offset + width]
                    features[f"h{width}:{gram}"] = max(
                        features.get(f"h{width}:{gram}", 0.0), weight
                    )
    for width, weight in ((2, 1.22), (3, 1.42)):
        if len(primary_tokens) < width:
            continue
        for offset in range(len(primary_tokens) - width + 1):
            gram = "|".join(primary_tokens[offset : offset + width])
            features[f"g{width}:{gram}"] = max(
                features.get(f"g{width}:{gram}", 0.0), weight
            )
    return features


def _goal_semantic_token_variants(token: str) -> tuple[str, ...]:
    variants = [token]
    if token.isascii() and token.isalpha():
        if len(token) >= 5 and token.endswith("ies"):
            variants.append(token[:-3] + "y")
        for suffix in ("ingly", "edly", "ing", "ed", "es", "s"):
            if token.endswith(suffix) and len(token) >= len(suffix) + 4:
                stem = token[: -len(suffix)]
                if suffix in {"ing", "ingly"} and len(stem) >= 3 and stem[-1:] == stem[-2:-1]:
                    stem = stem[:-1]
                variants.append(stem)
                break
    elif any("가" <= character <= "힣" for character in token):
        for suffix in (
            "하려고", "하고싶어", "하고싶어요", "해주세요", "해줘요", "해줘",
            "하기", "하는", "하려", "하고", "해서", "되었는지", "됐는지",
        ):
            if token.endswith(suffix) and len(token) >= len(suffix) + 2:
                variants.append(token[: -len(suffix)])
                break
    return tuple(dict.fromkeys(value for value in variants if len(value) >= 2))


def _goal_metadata_phrase(value: str) -> str:
    """Return the human phrase from flattened ``group:value`` metadata."""

    _group, separator, phrase = str(value).partition(":")
    return phrase.strip() if separator and phrase.strip() else str(value).strip()


def _compile_goal_semantic_postings(
    profiles: Sequence[Mapping[str, float]],
    *,
    candidate_count: int,
    document_frequency: Mapping[str, float] | None = None,
) -> dict[str, tuple[tuple[int, float, float], ...]]:
    """Compile deterministic IDF postings for one semantic evidence tier."""

    if document_frequency is None:
        counted: Counter[str] = Counter()
        for features in profiles:
            counted.update(features)
        document_frequency = counted
    bounded_candidate_count = max(1, candidate_count)
    postings: dict[str, list[tuple[int, float, float]]] = {}
    for candidate_index, features in enumerate(profiles):
        for feature, source_weight in features.items():
            frequency = float(document_frequency[feature])
            if frequency / bounded_candidate_count > 0.42:
                continue
            idf = math.log1p(bounded_candidate_count / frequency)
            postings.setdefault(feature, []).append(
                (candidate_index, source_weight, idf)
            )
    return {feature: tuple(values) for feature, values in postings.items()}


def _goal_catalog_anchor_bonus(value: str, anchors: tuple[str, ...]) -> float:
    """Bounded phrase evidence used only after sparse candidate retrieval."""

    normalized_value = _normalize(value)
    if not normalized_value or not anchors:
        return 0.0
    value_tokens = frozenset(
        token
        for token in _unicode_tokens(
            unicodedata.normalize("NFKC", sanitize_text(value)).casefold()
        )
        if len(token) >= 2
    )
    best = 0.0
    for anchor in anchors:
        normalized_anchor = _normalize(anchor)
        if len(normalized_anchor) < 4:
            continue
        if normalized_anchor == normalized_value:
            best = max(best, 0.070)
            continue
        if normalized_anchor in normalized_value:
            best = max(best, 0.025 + min(0.035, len(normalized_anchor) / 1200.0))
            continue
        anchor_tokens = frozenset(
            token
            for token in _unicode_tokens(
                unicodedata.normalize("NFKC", sanitize_text(anchor)).casefold()
            )
            if len(token) >= 2
        )
        overlap = value_tokens.intersection(anchor_tokens)
        if len(overlap) >= 2:
            recall = len(overlap) / max(1, len(anchor_tokens))
            best = max(best, min(0.035, 0.010 + 0.025 * recall))
        elif len(overlap) == 1 and len(next(iter(overlap))) >= 8:
            best = max(best, 0.012)
    return best


def _goal_contains_negation(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", sanitize_text(value)).casefold()
    tokens = set(_unicode_tokens(normalized))
    if tokens.intersection({"not", "without", "except", "instead", "never"}):
        return True
    return any(marker in normalized for marker in ("말고", "아니", "않", "제외", "빼고"))


def _goal_cache_key(value: str) -> str:
    """Preserve semantic token boundaries and punctuation in cache identity.

    Legacy matching still uses ``_normalize`` exactly as before.  The semantic
    focus pass, however, treats sentence and contrast punctuation as
    structure, so two requests that normalize to the same alphanumeric string
    must not share a cached plan.
    """

    text = unicodedata.normalize("NFKC", sanitize_text(value)).casefold()
    token_signature = "\x1e".join(_unicode_tokens(text))
    punctuation_signature = "".join(
        character
        for character in text
        if not character.isalnum() and not character.isspace()
    )
    return "\x1f".join((_normalize(text), token_signature, punctuation_signature))


def _goal_semantic_focus_text(value: str) -> str:
    """Remove clearly negated decoy clauses before semantic fallback scoring.

    This deliberately handles only high-precision contrast forms.  It never
    changes reviewed pattern/rule matching, and ambiguous negation remains in
    place so the fallback's conservative negative-context guard can decline.
    """

    text = " ".join(sanitize_text(value).split())
    if not text:
        return text
    # Korean contrast normally places the desired clause after the marker.
    for marker in ("아니라", "말고"):
        if marker in text:
            suffix = text.rsplit(marker, 1)[1].lstrip(" ,.;:-")
            if len(suffix) >= 8:
                text = suffix
                break

    # English contrast often isolates the rejected alternative in its own
    # sentence or in a leading comma/colon clause.
    sentences = [part.strip() for part in re.split(r"(?<=[.!?;])\s+", text) if part.strip()]
    if len(sentences) > 1:
        positive = [
            sentence
            for sentence in sentences
            if not _goal_contains_negation(sentence)
        ]
        if positive:
            text = " ".join(positive)
    # Korean often states the desired operation first and then protects a
    # sibling final action with "하되 ... 않다".  Keep only the desired clause;
    # unlike a bare unresolved negation, this grammatical boundary is
    # high-precision and preserves the user's explicit safety constraint.
    korean_trailing_contrast = re.search(
        r"(?:하되|하지만)\s*(?:아직\s+)?[^.!?;]{1,80}(?:않|아니)[^.!?;]*[.!?]?$",
        text,
    )
    if korean_trailing_contrast and korean_trailing_contrast.start() >= 8:
        text = text[: korean_trailing_contrast.start()].rstrip(" ,.;:-")
    leading_contrast = re.match(
        r"^(?:this is |i am |i'm |do )?(?:not|without|rather than|instead of)\b[^,:;.!?]*[,;:]\s*(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if leading_contrast and len(leading_contrast.group(1)) >= 12:
        text = leading_contrast.group(1)
    trailing_contrast = re.search(
        r"[,;:]?\s+\b(?:rather than|instead of|not)\b[^,;:.!?]*[.!?]?$",
        text,
        flags=re.IGNORECASE,
    )
    if trailing_contrast and trailing_contrast.start() >= 12:
        text = text[: trailing_contrast.start()].rstrip(" ,.;:-")
    return text


def _goal_semantic_query_stages(value: str) -> tuple[str, ...]:
    """Return high-precision anchor, focused-clause, then whole-query stages.

    Explicit goal/task markers are ordinary discourse structure rather than
    benchmark wording.  Only their following clause is promoted.  Ambiguous
    negation is never stripped here, so every stage retains the existing
    fail-closed contract.
    """

    text = " ".join(sanitize_text(value).split())
    if not text:
        return ()
    marker_patterns = (
        r"\bmy\s+(?:actual|real|primary|current|immediate)\s+"
        r"(?:goal|task|need|outcome)\s+(?:is|:)\s*(.+)$",
        r"\b(?:the\s+)?(?:immediate|actual|current|primary)\s+task"
        r"(?:\s+for\s+[^.!?;]{1,48})?\s+(?:is|:)\s*(.+)$",
        r"\bwhat\s+i\s+(?:actually\s+)?need(?:\s+(?:at\s+this\s+point|now))?"
        r"\s+(?:is|:)\s*(.+)$",
        r"\bthe\s+outcome\s+i\s+need(?:\s+at\s+this\s+point)?"
        r"\s+(?:is|:)\s*(.+)$",
        # Promote only the complement of an explicit declarative purpose,
        # destination, or outcome predicate.  The grammar contains no catalog
        # phrase and therefore applies uniformly across domains.
        r"\b(?:my|our|the)\s+"
        r"(?:(?:specific|operational|primary|intended)\s+)?"
        r"(?:purpose|destination|outcome)"
        r"(?:\s+(?:needed|required)(?:\s+(?:from|for)\s+[^.!?;,:]{1,48})?"
        r"|\s+(?:of|from|for)\s+[^.!?;,:]{1,48}"
        r"|\s+(?:i|we)\s+need\s+to\s+(?:complete|reach))?"
        r"\s+(?:is|:)\s*(?:to\s+(?:complete|reach)\s+)?(.+)$",
        r"(?:실제|현재|당장)\s*(?:목표|작업|목적)(?:은|는|이|가)?\s*[:：]?\s*(.+)$",
    )
    stages: list[str] = []
    for pattern in marker_patterns:
        matches = tuple(re.finditer(pattern, text, flags=re.IGNORECASE))
        if not matches:
            continue
        clause = re.split(
            # Preserve conjunctions inside provider, role, asset, state, and
            # jurisdiction lists.  Only sentence punctuation or an explicit
            # next-step imperative is a reliable boundary here.
            r"(?<=[.!?;])\s+|,\s+(?=(?:then|please|leave|stop|navigate|guide)\b)",
            matches[-1].group(1).strip(" ,.;:-"),
            maxsplit=1,
        )[0].strip(" ,.;:-")
        if len(_normalize(clause)) >= 4 and not _goal_contains_negation(clause):
            stages.append(clause)
            break

    # Enriched metadata is intentionally gated on an explicit discourse
    # anchor. Without one, ordinary situational prose retains the complete
    # legacy semantic/character outcome instead of guessing which clause is
    # primary.
    if not stages:
        return ()
    focused = _goal_semantic_focus_text(text)
    if focused and not _goal_contains_negation(focused):
        stages.append(focused)
    if text != focused and not _goal_contains_negation(text):
        stages.append(text)
    return tuple(dict.fromkeys(stages))


def _goal_has_explicit_alternative(value: str) -> bool:
    """Return whether one purpose clause asks us to choose between targets.

    The English form deliberately requires the paired ``either ... or``
    construction.  A bare ``or`` is common inside jurisdiction and lifecycle
    metadata and is therefore not enough to fail closed.  Korean alternatives
    use the corresponding paired or enumerating constructions.
    """

    text = unicodedata.normalize("NFKC", sanitize_text(value)).casefold()
    return bool(
        re.search(r"\beither\b[^.!?;]{0,240}\bor\b", text)
        or re.search(r"(?:둘\s*중|두\s*가지\s*중|중\s*(?:하나|하나를))", text)
        or re.search(r"(?:또는|혹은)[^.!?;]{1,160}(?:또는|혹은)", text)
    )


def _is_wrapped_reviewed_pattern(normalized_goal: str, pattern: str) -> bool:
    """Return whether a reviewed pattern occupies a simple request wrapper.

    This recognizes common app/politeness wrappers without promoting every
    substring in long situational prose.  The latter often names several
    sibling concepts and must remain available to semantic goal rules.
    """

    if not pattern:
        return False
    if normalized_goal == pattern:
        return True
    # Generic English request wrappers used naturally across apps.
    if normalized_goal in {
        "please" + pattern,
        "iwantto" + pattern,
        pattern + "menu",
    }:
        return True
    # Korean app prefix ("<app>에서 X") loses its particle during
    # normalization; cap the prefix so arbitrary narrative prose does not
    # masquerade as an app name.  Suffix wrappers retain stable wording.
    if normalized_goal.endswith(pattern):
        prefix_length = len(normalized_goal) - len(pattern)
        if 1 <= prefix_length <= 12:
            return True
    return normalized_goal in {
        pattern + "메뉴찾아줘",
        pattern + "하고싶어",
    }


def _reviewed_pattern_specificity(pattern: str) -> int:
    """Measure semantic content after removing generic request boilerplate."""

    value = pattern
    for prefix in ("please", "iwantto"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    for suffix in ("메뉴찾아줘", "하고싶어", "menu"):
        if value.endswith(suffix) and len(value) > len(suffix):
            value = value[:-len(suffix)]
            break
    return len(value)


def _route_with_terminal_override(
    route: tuple[tuple[str, float], ...],
    *,
    default_terminal: str,
    terminal_function: str,
) -> tuple[tuple[str, float], ...]:
    """Keep shared gateways while ending at the matched semantic subgoal."""

    if not terminal_function or terminal_function == default_terminal:
        return route
    rewritten = [
        (function_id, weight)
        for function_id, weight in route
        if function_id not in {default_terminal, terminal_function}
    ]
    rewritten.append((terminal_function, 1.0))
    return tuple(rewritten)


def _canonicalize_route(
    route: tuple[tuple[str, float], ...],
    *,
    terminal_function: str,
    canonicalize: Callable[[str], str],
) -> tuple[tuple[str, float], ...]:
    """Project a selected raw route, dedupe by max weight, and end at terminal."""

    order: list[str] = []
    weights: dict[str, float] = {}
    for raw_function_id, weight in route:
        function_id = canonicalize(raw_function_id)
        if function_id not in weights:
            order.append(function_id)
            weights[function_id] = float(weight)
        else:
            weights[function_id] = max(weights[function_id], float(weight))
    if terminal_function:
        terminal_weight = weights.get(terminal_function, 1.0)
        order = [function_id for function_id in order if function_id != terminal_function]
        weights[terminal_function] = terminal_weight
        order.append(terminal_function)
    return tuple((function_id, weights[function_id]) for function_id in order)


def _bounded_cache_store(cache: dict, key: object, value: object, *, max_size: int = 4096) -> None:
    """Keep hot semantic results without allowing an unbounded server cache."""

    if len(cache) >= max_size:
        cache.pop(next(iter(cache)))
    cache[key] = value


def _unicode_tokens(value: str) -> list[str]:
    """Tokenize every Unicode writing system without folding it to ASCII.

    NFKC normalizes width/compatibility variants while this tokenizer retains
    letters, numbers, and combining marks from Korean, CJK, Japanese, Latin,
    and other scripts. Punctuation and whitespace remain token boundaries.
    """

    tokens: list[str] = []
    current: list[str] = []
    for character in value:
        category = unicodedata.category(character)
        if character.isalnum() or (category.startswith("M") and current):
            current.append(character)
            continue
        if current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


@lru_cache(maxsize=64)
def _normalize_locale(locale: str | None) -> str:
    value = unicodedata.normalize("NFKC", str(locale or "")).casefold().replace("_", "-").strip()
    return value or "und"


@lru_cache(maxsize=256)
def _locale_affinity(requested_locale: str, alias_locale: str) -> float:
    if requested_locale == "und":
        return 0.0
    normalized_alias_locale = _normalize_locale(alias_locale)
    if normalized_alias_locale == requested_locale:
        return 0.026
    if normalized_alias_locale.split("-", 1)[0] == requested_locale.split("-", 1)[0]:
        return 0.018
    if normalized_alias_locale == "und":
        return 0.006
    # Other locales remain valid fallback evidence; they are not discarded.
    return 0.0


def _normalize_metadata_token(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value)).casefold().strip()


def _candidate_state_cues(
    *,
    enabled: bool | None,
    checkable: bool | None,
    checked: bool | None,
    selected: bool | None,
) -> frozenset[str]:
    values = {
        key: value
        for key, value in (
            ("enabled", enabled),
            ("checkable", checkable),
            ("checked", checked),
            ("selected", selected),
        )
        if value is not None
    }
    return frozenset(f"{key}:{str(value).lower()}" for key, value in values.items())


def _canonical_state_cue(value: object) -> str:
    normalized = _normalize_metadata_token(value).replace(" ", "")
    synonyms = {
        "enabled": "enabled:true",
        "disabled": "enabled:false",
        "checkable": "checkable:true",
        "not-checkable": "checkable:false",
        "non-checkable": "checkable:false",
        "checked": "checked:true",
        "unchecked": "checked:false",
        "selected": "selected:true",
        "unselected": "selected:false",
    }
    return synonyms.get(normalized, normalized)


def _compile_state_cues(function_cues: tuple[str, ...]) -> tuple[_CompiledStateCue, ...]:
    compiled: list[_CompiledStateCue] = []
    for raw_cue in function_cues:
        cue = _canonical_state_cue(raw_cue)
        normalized_phrase = ""
        text_evidence = ""
        if ":" in raw_cue:
            group, _, raw_phrase = raw_cue.partition(":")
            normalized_phrase = _normalize(raw_phrase)
            text_evidence = f"text:{group}:{raw_phrase}"
        compiled.append(
            _CompiledStateCue(
                canonical=cue,
                key=cue.partition(":")[0],
                normalized_phrase=normalized_phrase,
                text_evidence=text_evidence,
            )
        )
    return tuple(compiled)


def _state_cue_score(
    function_cues: tuple[_CompiledStateCue, ...],
    candidate_cues: frozenset[str],
    *,
    evidence_text: str = "",
) -> tuple[float, tuple[str, ...]]:
    if not function_cues or (not candidate_cues and not evidence_text):
        return 0.0, ()
    score = 0.0
    evidence: list[str] = []
    candidate_by_key = {cue.partition(":")[0]: cue for cue in candidate_cues if ":" in cue}
    for compiled in function_cues:
        if compiled.canonical in candidate_cues:
            score += 0.012
            evidence.append(compiled.canonical)
        elif compiled.key in candidate_by_key and ":" in compiled.canonical:
            score -= 0.008
            evidence.append(f"not:{compiled.canonical}")
        if compiled.normalized_phrase and compiled.normalized_phrase in evidence_text:
            score += 0.008
            evidence.append(compiled.text_evidence)
    return max(-0.024, min(0.024, score)), tuple(evidence)


def _strip_korean_particle(token: str) -> str:
    """Remove common Korean case particles while retaining semantic nouns."""

    if len(token) < 3 or not any("가" <= character <= "힣" for character in token):
        return token
    for particle in (
        "에게서", "으로부터", "한테서", "에서는", "에서도", "으로", "에서", "에게", "한테",
        "처럼", "보다", "까지", "부터", "은", "는", "이", "가", "을", "를", "에", "로", "와", "과", "도", "만",
    ):
        if token.endswith(particle) and len(token) > len(particle) + 1:
            return token[: -len(particle)]
    return token


def _character_masks(value: str) -> Mapping[str, int]:
    masks: dict[str, int] = {}
    for index, character in enumerate(value):
        masks[character] = masks.get(character, 0) | (1 << index)
    return masks


def _bitset_lcs_length(value: str, phrase_masks: Mapping[str, int]) -> int:
    """Return exact LCS length using one Python integer as the DP row.

    Every matching block selected by ``SequenceMatcher`` is an ordered common
    subsequence, so this value is a proven upper bound on its total match size.
    Pattern-side bit masks are compiled once when the catalog is loaded.
    """

    row = 0
    mask_for = phrase_masks.get
    for character in value:
        matches = mask_for(character, 0)
        combined = row | matches
        shifted = (row << 1) | 1
        row = combined & ~(combined - shifted)
    return row.bit_count()


def _fuzzy_bound_can_challenge(
    upper_score: float,
    *,
    intent_ordinal: int,
    best_key: tuple[float, int, int, int, int],
    best_ordinal: int,
    best_intent: str,
) -> bool:
    """Whether a fuzzy score upper bound can alter the legacy winner."""

    candidate_key = (upper_score, 0, 0, 0, 0)
    if candidate_key > best_key:
        return True
    # The original resolver retains the first intent on an equal key.  The
    # baseline pass may have found a later containment match before fuzzy
    # evidence is added, so an earlier fuzzy tie must remain eligible.
    return (
        candidate_key == best_key
        and best_intent != "generic_navigation"
        and intent_ordinal < best_ordinal
    )


def _phrase_similarity(normalized_value: str, normalized_phrase: str) -> float:
    if not normalized_value or not normalized_phrase:
        return 0.0
    if normalized_value == normalized_phrase:
        return 1.0
    # Do not let very short aliases such as English "me" match an unrelated
    # word such as "home" merely because they share two characters.
    if min(len(normalized_value), len(normalized_phrase)) <= 2:
        return SequenceMatcher(None, normalized_value, normalized_phrase).ratio() * 0.25
    if normalized_phrase in normalized_value:
        coverage = len(normalized_phrase) / max(1, len(normalized_value))
        return min(0.98, 0.78 + coverage * 0.20)
    if normalized_value in normalized_phrase:
        coverage = len(normalized_value) / max(1, len(normalized_phrase))
        return min(0.92, 0.68 + coverage * 0.20)
    return (
        SequenceMatcher(None, normalized_value, normalized_phrase).ratio()
        * GOAL_FUZZY_SCORE_UPPER_BOUND
    )


def _alias_score_contribution_bound(
    label_value: str,
    normalized_locale: str,
    features: tuple[_AliasRankingFeature, ...],
    *,
    label_character_counts: Mapping[str, int],
) -> tuple[float, bool]:
    """Bound ``alias_score * .88 + locale_score`` for one function.

    SequenceMatcher's matching blocks cannot consume more occurrences of any
    character than either input contains. The multiset intersection therefore
    bounds its ratio without executing edit-distance work. Exact and
    containment branches use their real score. Taking the maximum weighted
    contribution across aliases is also safe when locale affinity makes a
    different alias win the legacy ``alias_score + locale_score`` ordering.
    """

    if not features:
        return 0.0, False
    label_length = len(label_value)
    best_contribution = 0.0
    has_exact_alias = False
    for feature in features:
        alias_value = feature.alias.normalized
        alias_length = feature.length
        if not label_value or not alias_value:
            alias_upper_bound = 0.0
        elif label_value == alias_value:
            alias_upper_bound = 1.0
            has_exact_alias = True
        elif min(label_length, alias_length) <= 2:
            common_characters = _character_multiset_overlap(
                label_character_counts,
                feature.character_masks,
            )
            alias_upper_bound = (
                2.0
                * common_characters
                / max(1, label_length + alias_length)
                * 0.25
            )
        elif alias_value in label_value:
            coverage = alias_length / max(1, label_length)
            alias_upper_bound = min(0.98, 0.78 + coverage * 0.20)
        elif label_value in alias_value:
            coverage = label_length / max(1, alias_length)
            alias_upper_bound = min(0.92, 0.68 + coverage * 0.20)
        else:
            common_characters = _character_multiset_overlap(
                label_character_counts,
                feature.character_masks,
            )
            alias_upper_bound = (
                2.0
                * common_characters
                / max(1, label_length + alias_length)
                * GOAL_FUZZY_SCORE_UPPER_BOUND
            )
        contribution = alias_upper_bound * 0.88 + _locale_affinity(
            normalized_locale,
            feature.alias.locale,
        )
        best_contribution = max(best_contribution, contribution)
    return best_contribution, has_exact_alias


def _character_multiset_overlap(
    label_counts: Mapping[str, int],
    alias_masks: Mapping[str, int],
) -> int:
    """Return the exact character-multiset overlap with the shorter key scan."""

    common = 0
    if len(label_counts) <= len(alias_masks):
        mask_for = alias_masks.get
        for character, label_count in label_counts.items():
            alias_count = mask_for(character, 0).bit_count()
            common += label_count if label_count < alias_count else alias_count
        return common
    label_count_for = label_counts.get
    for character, mask in alias_masks.items():
        label_count = label_count_for(character, 0)
        alias_count = mask.bit_count()
        common += label_count if label_count < alias_count else alias_count
    return common


def _top_alias_pairs(
    label_value: str,
    normalized_locale: str,
    features: tuple[_AliasRankingFeature, ...],
    *,
    limit: int,
) -> tuple[tuple[float, float, FunctionAlias], ...]:
    """Return the exact legacy top aliases with lossless branch-and-bound.

    SequenceMatcher's total matching-block length cannot exceed the longest
    common subsequence of its two inputs.  A bit-parallel exact LCS therefore
    provides a proven ratio upper bound.  Exact and containment branches are
    calculated directly; edit-distance work is performed only while an alias
    can still outrank the current kth result.  No function or semantic fallback
    is ever removed from consideration.
    """

    if not features or limit <= 0:
        return ()
    label_length = len(label_value)
    bounded: list[
        tuple[float, float, str, int, float | None, _AliasRankingFeature]
    ] = []
    for feature in features:
        alias_value = feature.alias.normalized
        exact_score: float | None = None
        if not label_value or not alias_value:
            upper_score = 0.0
            exact_score = 0.0
        elif label_value == alias_value:
            upper_score = 1.0
            exact_score = 1.0
        elif min(label_length, feature.length) <= 2:
            common_characters = _bitset_lcs_length(
                label_value,
                feature.character_masks,
            )
            upper_score = (
                2.0
                * common_characters
                / max(1, label_length + feature.length)
                * 0.25
            )
        elif alias_value in label_value:
            coverage = feature.length / max(1, label_length)
            upper_score = min(0.98, 0.78 + coverage * 0.20)
            exact_score = upper_score
        elif label_value in alias_value:
            coverage = label_length / max(1, feature.length)
            upper_score = min(0.92, 0.68 + coverage * 0.20)
            exact_score = upper_score
        else:
            common_characters = _bitset_lcs_length(
                label_value,
                feature.character_masks,
            )
            upper_score = (
                2.0
                * common_characters
                / max(1, label_length + feature.length)
                * GOAL_FUZZY_SCORE_UPPER_BOUND
            )
        locale_score = _locale_affinity(normalized_locale, feature.alias.locale)
        bounded.append(
            (
                upper_score + locale_score,
                upper_score,
                feature.alias.phrase,
                -feature.ordinal,
                exact_score,
                feature,
            )
        )
    bounded.sort(key=lambda item: item[:4], reverse=True)

    ranked: list[tuple[float, float, str, int, float, FunctionAlias]] = []
    for upper_total, _upper_score, _phrase, _ordinal_key, exact_score, feature in bounded:
        if len(ranked) >= limit:
            kth_total = ranked[limit - 1][0]
            # The epsilon is deliberately one-sided and conservative: pruning
            # happens only when the mathematical upper bound is clearly below
            # the exact kth primary key.  Equal/tie-break cases are evaluated.
            if upper_total < kth_total - 1e-12:
                break
        alias_score = (
            exact_score
            if exact_score is not None
            else _phrase_similarity(label_value, feature.alias.normalized)
        )
        locale_score = _locale_affinity(normalized_locale, feature.alias.locale)
        ranked.append(
            (
                alias_score + locale_score,
                alias_score,
                feature.alias.phrase,
                -feature.ordinal,
                locale_score,
                feature.alias,
            )
        )
        ranked.sort(key=lambda item: item[:4], reverse=True)
        if len(ranked) > limit:
            ranked.pop()
    return tuple(
        (alias_score, locale_score, alias)
        for _total_score, alias_score, _phrase, _ordinal, locale_score, alias in ranked
    )


def _should_run_exhaustive_goal_fuzzy(
    normalized_goal: str,
    baseline_score: float,
) -> bool:
    """Keep exhaustive fuzzy work for short commands or anchored prose."""

    return not (
        baseline_score <= 0.0
        and len(normalized_goal) >= GOAL_LONG_PROSE_FUZZY_SKIP_LENGTH
    )


def _phrase_containment_similarity(normalized_value: str, normalized_phrase: str) -> float:
    """Score only exact and containment relations without edit distance.

    The returned values are byte-for-byte the corresponding branches of
    ``_phrase_similarity``.  A zero means that the exhaustive resolver must be
    used unless another match is at the proven fuzzy upper bound.
    """

    if not normalized_value or not normalized_phrase:
        return 0.0
    if normalized_value == normalized_phrase:
        return 1.0
    if min(len(normalized_value), len(normalized_phrase)) <= 2:
        # The legacy short-string guard deliberately uses SequenceMatcher even
        # for containment, so defer these rare cases to the exhaustive pass.
        return 0.0
    if normalized_phrase in normalized_value:
        coverage = len(normalized_phrase) / max(1, len(normalized_value))
        return min(0.98, 0.78 + coverage * 0.20)
    if normalized_value in normalized_phrase:
        coverage = len(normalized_value) / max(1, len(normalized_phrase))
        return min(0.92, 0.68 + coverage * 0.20)
    return 0.0


def _iter_aliases(raw_aliases: object) -> Iterator[FunctionAlias]:
    """Yield aliases from the current locale map and compatible future forms."""

    if isinstance(raw_aliases, Mapping):
        for raw_locale, raw_values in raw_aliases.items():
            locale = _normalize_locale(str(raw_locale))
            values = raw_values if isinstance(raw_values, (list, tuple)) else [raw_values]
            for value in values:
                phrase = str(value).strip()
                if phrase:
                    yield FunctionAlias(locale=locale, phrase=phrase, normalized=_normalize(phrase))
        return
    if isinstance(raw_aliases, (list, tuple)):
        for value in raw_aliases:
            if isinstance(value, Mapping):
                locale = _normalize_locale(str(value.get("locale", "und")))
                phrase = str(value.get("phrase", value.get("value", ""))).strip()
            else:
                locale = "und"
                phrase = str(value).strip()
            if phrase:
                yield FunctionAlias(locale=locale, phrase=phrase, normalized=_normalize(phrase))


def _metadata_values(raw_value: object) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    values: list[str] = []
    if isinstance(raw_value, Mapping):
        for raw_key, raw_item in raw_value.items():
            key = _normalize_metadata_token(raw_key)
            items = raw_item if isinstance(raw_item, (list, tuple, set)) else [raw_item]
            for item in items:
                if isinstance(item, bool):
                    value = f"{key}:{str(item).lower()}"
                else:
                    normalized_item = _normalize_metadata_token(item)
                    value = f"{key}:{normalized_item}" if normalized_item else ""
                if value:
                    values.append(value)
    else:
        items = raw_value if isinstance(raw_value, (list, tuple, set)) else [raw_value]
        values.extend(_normalize_metadata_token(item) for item in items if str(item).strip())
    return tuple(dict.fromkeys(value for value in values if value))


def _semantic_concept_values(raw_value: object) -> tuple[str, ...]:
    """Normalize function concept IDs while rejecting phrase-like metadata.

    Concepts are deliberately coarse reusable atoms (``account``, ``change``,
    ``history``), not benchmark sentences or labels.  Keeping this distinction
    explicit makes the ontology useful for unseen paraphrases without turning
    the independent benchmark into a lookup table.
    """

    items = raw_value if isinstance(raw_value, (list, tuple, set)) else [raw_value]
    values: list[str] = []
    for item in items:
        concept = _normalize_metadata_token(item).replace("-", "_").replace(" ", "_")
        if concept and re.fullmatch(r"[a-z0-9_]+", concept):
            values.append(concept)
    return tuple(dict.fromkeys(values))


def _iter_semantic_lexicon(raw_lexicon: object) -> Iterator[tuple[str, str, str]]:
    if not isinstance(raw_lexicon, Mapping):
        return
    for raw_concept, raw_locales in raw_lexicon.items():
        concepts = _semantic_concept_values([raw_concept])
        if not concepts or not isinstance(raw_locales, Mapping):
            continue
        concept = concepts[0]
        for raw_locale, raw_phrases in raw_locales.items():
            locale = _normalize_locale(str(raw_locale))
            phrases = raw_phrases if isinstance(raw_phrases, (list, tuple, set)) else [raw_phrases]
            for raw_phrase in phrases:
                phrase = str(raw_phrase).strip()
                if phrase:
                    yield concept, locale, phrase


def _semantic_concept_score(
    label_concepts: frozenset[str],
    function_concepts: tuple[str, ...],
    *,
    context_concepts: frozenset[str] = frozenset(),
) -> tuple[float, tuple[str, ...]]:
    """Return conservative compositional evidence for an unseen label.

    One shared atom is weak evidence: many menus contain words such as
    ``account`` or ``settings``.  Two or more atoms receive a much larger
    score because their conjunction identifies the function (for example
    ``email + change`` or ``refund + status``).  The cap prevents concepts
    from overpowering explicit negative context and safety metadata.
    """

    expected = frozenset(function_concepts)
    label_matched = frozenset(label_concepts.intersection(expected))
    if not label_matched:
        return 0.0, ()
    combined_matched = frozenset(label_matched.union(context_concepts.intersection(expected)))

    def score_for(matched: frozenset[str], observed: frozenset[str]) -> float:
        if len(matched) == 1:
            return 0.045
        recall = len(matched) / max(1, len(expected))
        precision = len(matched) / max(1, len(observed))
        return min(0.48, len(matched) * 0.12 + recall * 0.16 + precision * 0.06)

    label_score = score_for(label_matched, label_concepts)
    combined_score = score_for(combined_matched, label_concepts.union(context_concepts))
    # Screen/parent context may complete a compositional identity but cannot
    # contribute as strongly as text printed on the candidate itself.
    score = label_score + max(0.0, combined_score - label_score) * 0.75
    return min(0.48, score), tuple(sorted(combined_matched))


def _metadata_text(item: Mapping[str, object], key: str, default: str) -> str:
    value = _normalize_metadata_token(item.get(key, ""))
    return value or default


def _default_node_kind(item: Mapping[str, object]) -> str:
    return "destination" if bool(item.get("terminal")) else "navigation"


def _default_stop_policy(item: Mapping[str, object]) -> str:
    if bool(item.get("state_changing")) or str(item.get("risk_level", "")).casefold() == "high":
        return "before_activation"
    return "at_destination" if bool(item.get("terminal")) else "continue"


def validate_equivalence_payload(
    payload: object,
    functions: Mapping[str, FunctionDefinition],
) -> None:
    """Validate reviewed terminal classes and their conservative safety envelope."""

    if not isinstance(payload, Mapping):
        raise CatalogValidationError("equivalence payload must be a JSON object")
    errors: list[str] = []
    if str(payload.get("equivalence_kind", "")) != "true_equivalent":
        errors.append("equivalence_kind must be true_equivalent")
    raw_classes = payload.get("classes", [])
    if not isinstance(raw_classes, list):
        errors.append("classes must be a list")
        raw_classes = []

    integrity = payload.get("integrity")
    if integrity is not None and not isinstance(integrity, Mapping):
        errors.append("integrity must be an object")
    if isinstance(integrity, Mapping) and integrity.get("canonical_sha256"):
        document = dict(payload)
        document_integrity = dict(integrity)
        expected_hash = str(document_integrity.pop("canonical_sha256"))
        document["integrity"] = document_integrity
        actual_hash = hashlib.sha256(
            json.dumps(
                document,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            errors.append("integrity.canonical_sha256 does not match the equivalence document")

    membership: dict[str, str] = {}
    edges: dict[str, str] = {}
    risk_rank = {"low": 0, "medium": 1, "high": 2}
    automation_rank = {"safe_navigation": 0, "conditional": 1, "never_auto": 2}

    for index, raw_class in enumerate(raw_classes):
        location = f"classes[{index}]"
        if not isinstance(raw_class, Mapping):
            errors.append(f"{location} must be an object")
            continue
        canonical = str(raw_class.get("canonical_function_id", "")).strip()
        raw_aliases = raw_class.get("alias_function_ids", [])
        if not canonical:
            errors.append(f"{location}.canonical_function_id must not be empty")
        if not isinstance(raw_aliases, list) or not raw_aliases:
            errors.append(f"{location}.alias_function_ids must be a non-empty list")
            raw_aliases = []
        aliases = [str(value).strip() for value in raw_aliases]
        if any(not value for value in aliases):
            errors.append(f"{location}.alias_function_ids contains an empty ID")
        if len(set(aliases)) != len(aliases) or canonical in aliases:
            errors.append(f"{location} contains duplicate class members")
        if str(raw_class.get("classification", "")) != "true_equivalent":
            errors.append(f"{location}.classification must be true_equivalent")

        members = [canonical, *aliases]
        member_definitions: list[FunctionDefinition] = []
        for member in members:
            if member not in functions:
                errors.append(f"{location} references unknown function_id: {member or '<empty>'}")
                continue
            previous = membership.get(member)
            if previous is not None:
                errors.append(
                    f"{member} belongs to multiple equivalence classes: {previous}, {canonical}"
                )
            else:
                membership[member] = canonical
            member_definitions.append(functions[member])
        for alias in aliases:
            edges[alias] = canonical

        if member_definitions:
            if not all(definition.terminal for definition in member_definitions):
                errors.append(f"{location} may contain terminal functions only")
            if len({definition.terminal for definition in member_definitions}) != 1:
                errors.append(f"{location} mixes terminal and non-terminal functions")

        safety = raw_class.get("composite_safety")
        if not isinstance(safety, Mapping):
            errors.append(f"{location}.composite_safety must be an object")
            continue
        composite_risk = str(safety.get("risk_level", "")).casefold()
        composite_automation = str(safety.get("automation_policy", "")).casefold()
        composite_stop = str(safety.get("stop_policy", "")).casefold()
        composite_state = safety.get("state_changing")
        if composite_risk not in risk_rank:
            errors.append(f"{location}.composite_safety has invalid risk_level")
        if composite_automation not in automation_rank:
            errors.append(f"{location}.composite_safety has invalid automation_policy")
        if not isinstance(composite_state, bool):
            errors.append(f"{location}.composite_safety.state_changing must be boolean")
        if member_definitions:
            member_risk = max(risk_rank[definition.risk_level] for definition in member_definitions)
            member_automation = max(
                automation_rank.get(definition.automation_policy, 2)
                for definition in member_definitions
            )
            member_state = any(definition.state_changing for definition in member_definitions)
            member_requires_stop = any(
                definition.stop_policy in NEVER_AUTO_STOP_POLICIES
                for definition in member_definitions
            )
            if risk_rank.get(composite_risk, -1) < member_risk:
                errors.append(f"{location}.composite_safety weakens member risk_level")
            if automation_rank.get(composite_automation, -1) < member_automation:
                errors.append(f"{location}.composite_safety weakens member automation_policy")
            if isinstance(composite_state, bool) and composite_state != member_state:
                errors.append(
                    f"{location}.composite_safety.state_changing must equal the member OR"
                )
            if member_requires_stop and composite_stop not in NEVER_AUTO_STOP_POLICIES:
                errors.append(f"{location}.composite_safety weakens member stop_policy")
        if (
            composite_state is True or composite_risk == "high"
        ) and composite_automation != "never_auto":
            errors.append(f"{location}.composite_safety must preserve never_auto")
        if composite_state is True and composite_stop not in NEVER_AUTO_STOP_POLICIES:
            errors.append(f"{location}.composite_safety must stop before activation")

    # Detect cycles independently of disjointness so malformed future schemas
    # fail with a useful reason even if they introduce chained aliases.
    for start in edges:
        seen: set[str] = set()
        current = start
        while current in edges:
            if current in seen:
                errors.append(f"equivalence classes contain a cycle through {current}")
                break
            seen.add(current)
            current = edges[current]

    if errors:
        raise CatalogValidationError(
            "invalid navigation function equivalence:\n- " + "\n- ".join(errors)
        )


def validate_catalog_payload(payload: object) -> None:
    """Validate all safety and reference invariants before SQLite is mutated."""

    if not isinstance(payload, Mapping):
        raise CatalogValidationError("catalog payload must be a JSON object")
    errors: list[str] = []
    if not str(payload.get("catalog_version", "")).strip():
        errors.append("catalog_version must not be empty")

    raw_functions = payload.get("functions", [])
    raw_intents = payload.get("intents", [])
    if not isinstance(raw_functions, list):
        errors.append("functions must be a list")
        raw_functions = []
    if not isinstance(raw_intents, list):
        errors.append("intents must be a list")
        raw_intents = []

    raw_lexicon = payload.get("semantic_lexicon", {})
    if raw_lexicon and not isinstance(raw_lexicon, Mapping):
        errors.append("semantic_lexicon must be a concept-to-locale map")
        raw_lexicon = {}
    lexicon_concepts = {
        concept for concept, _locale, _phrase in _iter_semantic_lexicon(raw_lexicon)
    }
    for raw_concept, raw_locales in raw_lexicon.items():
        normalized_concepts = _semantic_concept_values([raw_concept])
        if not normalized_concepts:
            errors.append(f"semantic_lexicon has invalid concept id: {raw_concept!s}")
        if not isinstance(raw_locales, Mapping):
            errors.append(f"semantic_lexicon.{raw_concept!s} must be a locale map")
            continue
        for locale, values in raw_locales.items():
            entries = values if isinstance(values, (list, tuple, set)) else [values]
            if not str(locale).strip() or not entries or any(not str(value).strip() for value in entries):
                errors.append(f"semantic_lexicon.{raw_concept!s}.{locale!s} contains an empty phrase")

    function_ids: set[str] = set()
    for index, raw_item in enumerate(raw_functions):
        if not isinstance(raw_item, Mapping):
            errors.append(f"functions[{index}] must be an object")
            continue
        function_id = str(raw_item.get("function_id", "")).strip()
        if not function_id:
            errors.append(f"functions[{index}].function_id must not be empty")
            continue
        if function_id in function_ids:
            errors.append(f"duplicate function_id: {function_id}")
        function_ids.add(function_id)

        raw_aliases = raw_item.get("aliases")
        aliases = tuple(_iter_aliases(raw_aliases))
        if not aliases:
            errors.append(f"{function_id}: aliases must contain at least one non-empty phrase")
        if isinstance(raw_aliases, Mapping):
            for locale, values in raw_aliases.items():
                if not str(locale).strip():
                    errors.append(f"{function_id}: alias locale must not be empty")
                entries = values if isinstance(values, (list, tuple)) else [values]
                if not entries or any(not str(value).strip() for value in entries):
                    errors.append(f"{function_id}: aliases[{locale!s}] contains an empty phrase")
        elif isinstance(raw_aliases, (list, tuple)):
            for alias in raw_aliases:
                phrase = alias.get("phrase", alias.get("value", "")) if isinstance(alias, Mapping) else alias
                if not str(phrase).strip():
                    errors.append(f"{function_id}: aliases contains an empty phrase")
        else:
            errors.append(f"{function_id}: aliases must be a locale map or list")

        risk_level = str(raw_item.get("risk_level", "")).casefold()
        automation_policy = str(raw_item.get("automation_policy", "")).casefold()
        state_changing = bool(raw_item.get("state_changing"))
        stop_policy = _metadata_text(raw_item, "stop_policy", _default_stop_policy(raw_item))
        if state_changing and automation_policy != "never_auto":
            errors.append(f"{function_id}: state_changing functions must use never_auto")
        if risk_level == "high" and automation_policy != "never_auto":
            errors.append(f"{function_id}: high-risk functions must use never_auto")
        if state_changing and risk_level not in {"medium", "high"}:
            errors.append(f"{function_id}: state_changing functions must be medium or high risk")
        if state_changing and stop_policy not in NEVER_AUTO_STOP_POLICIES:
            errors.append(
                f"{function_id}: state-changing stop_policy must stop before activation"
            )
        for metadata_key in ("role_hints", "state_cues", "risk_cues"):
            raw_metadata = raw_item.get(metadata_key)
            if isinstance(raw_metadata, (list, tuple)) and any(
                not str(value).strip() for value in raw_metadata
            ):
                errors.append(f"{function_id}: {metadata_key} contains an empty value")
        concepts = _semantic_concept_values(raw_item.get("semantic_concepts", ()))
        for concept in concepts:
            if concept not in lexicon_concepts:
                errors.append(f"{function_id}: semantic concept has no lexicon entry: {concept}")
        terminal_concepts = _semantic_concept_values(
            raw_item.get("semantic_terminal_concepts", ())
        )
        for concept in terminal_concepts:
            if concept not in concepts:
                errors.append(
                    f"{function_id}: terminal concept is not declared in semantic_concepts: {concept}"
                )

    intent_ids: set[str] = set()
    referenced_functions: list[tuple[str, str]] = []
    for index, raw_intent in enumerate(raw_intents):
        if not isinstance(raw_intent, Mapping):
            errors.append(f"intents[{index}] must be an object")
            continue
        intent_id = str(raw_intent.get("intent_id", "")).strip()
        if not intent_id:
            errors.append(f"intents[{index}].intent_id must not be empty")
            continue
        if intent_id in intent_ids:
            errors.append(f"duplicate intent_id: {intent_id}")
        intent_ids.add(intent_id)
        terminal = str(raw_intent.get("terminal_function", "")).strip()
        if terminal:
            referenced_functions.append((f"intent {intent_id} terminal_function", terminal))
        for rule_index, raw_rule in enumerate(raw_intent.get("goal_rules", [])):
            if not isinstance(raw_rule, Mapping):
                errors.append(f"intent {intent_id} goal_rules[{rule_index}] must be an object")
                continue
            rule_terminal = str(raw_rule.get("terminal_function", "")).strip()
            if rule_terminal:
                referenced_functions.append(
                    (f"intent {intent_id} goal_rules[{rule_index}] terminal_function", rule_terminal)
                )
        for route_index, step in enumerate(raw_intent.get("route", [])):
            if isinstance(step, Mapping):
                referenced_functions.append(
                    (f"intent {intent_id} route[{route_index}]", str(step.get("function_id", "")).strip())
                )
            else:
                errors.append(f"intent {intent_id} route[{route_index}] must be an object")
        for function_id in raw_intent.get("avoid_functions", []):
            referenced_functions.append((f"intent {intent_id} avoid_functions", str(function_id).strip()))

    gateway_ids: set[str] = set()
    for index, raw_rule in enumerate(payload.get("gateway_rules", [])):
        if not isinstance(raw_rule, Mapping):
            errors.append(f"gateway_rules[{index}] must be an object")
            continue
        rule_id = str(raw_rule.get("rule_id", "")).strip()
        if not rule_id:
            errors.append(f"gateway_rules[{index}].rule_id must not be empty")
        elif rule_id in gateway_ids:
            errors.append(f"duplicate gateway rule_id: {rule_id}")
        gateway_ids.add(rule_id)
        for function_id in raw_rule.get("when_route_contains_any", []):
            referenced_functions.append((f"gateway rule {rule_id} trigger", str(function_id).strip()))
        for step_index, step in enumerate(raw_rule.get("prepend", [])):
            if isinstance(step, Mapping):
                referenced_functions.append(
                    (f"gateway rule {rule_id} prepend[{step_index}]", str(step.get("function_id", "")).strip())
                )
            else:
                errors.append(f"gateway rule {rule_id} prepend[{step_index}] must be an object")

    for index, raw_rule in enumerate(payload.get("supplemental_goal_rules", [])):
        location = f"supplemental_goal_rules[{index}]"
        if not isinstance(raw_rule, Mapping):
            errors.append(f"{location} must be an object")
            continue
        intent_id = str(raw_rule.get("intent_id", "")).strip()
        if not intent_id or intent_id not in intent_ids:
            errors.append(f"{location} references unknown intent_id: {intent_id or '<empty>'}")
        terms = raw_rule.get("all_of", [])
        if (
            not isinstance(terms, (list, tuple))
            or not terms
            or any(not str(term).strip() for term in terms)
        ):
            errors.append(f"{location}.all_of must contain non-empty cue terms")
        try:
            score = float(raw_rule.get("score", 0.9))
        except (TypeError, ValueError):
            errors.append(f"{location}.score must be numeric")
        else:
            if not 0.0 <= score <= 1.0:
                errors.append(f"{location}.score must be between 0 and 1")
        rule_terminal = str(raw_rule.get("terminal_function", "")).strip()
        if rule_terminal:
            referenced_functions.append((f"{location} terminal_function", rule_terminal))

    for location, function_id in referenced_functions:
        if not function_id or function_id not in function_ids:
            errors.append(f"{location} references unknown function_id: {function_id or '<empty>'}")
    if errors:
        raise CatalogValidationError("invalid navigation function catalog:\n- " + "\n- ".join(errors))


def _ensure_sqlite_column(
    connection: sqlite3.Connection, table: str, column: str, declaration: str
) -> None:
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _group_values(rows: Iterable[sqlite3.Row], key_name: str, value_name: str) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(str(row[key_name]), []).append(str(row[value_name]))
    return {key: tuple(value) for key, value in grouped.items()}


def _group_pairs(
    rows: Iterable[sqlite3.Row], key_name: str, normalized_name: str, original_name: str
) -> dict[str, tuple[tuple[str, str], ...]]:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        grouped.setdefault(str(row[key_name]), []).append(
            (str(row[normalized_name]), str(row[original_name]))
        )
    return {key: tuple(value) for key, value in grouped.items()}


def _group_aliases(rows: Iterable[sqlite3.Row]) -> dict[str, tuple[FunctionAlias, ...]]:
    grouped: dict[str, list[FunctionAlias]] = {}
    for row in rows:
        grouped.setdefault(str(row["function_id"]), []).append(
            FunctionAlias(
                locale=str(row["locale"]),
                phrase=str(row["phrase"]),
                normalized=str(row["normalized"]),
            )
        )
    return {key: tuple(values) for key, values in grouped.items()}
