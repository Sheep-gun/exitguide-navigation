from __future__ import annotations

"""Materialize the broad v2-v16 navigation ontology into the reviewable catalog.

This migration is deliberately deterministic and idempotent.  The JSON catalog
remains the runtime source of truth; this file makes the large, hand-reviewed
expansion auditable without hiding it in a generated binary database.
"""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from navigation_catalog_v3_data import V3_FUNCTIONS, V3_INTENTS, validate_v3_data
from navigation_catalog_v4_data import V4_FUNCTIONS, V4_INTENTS, merge_with_base as merge_v4_with_base
from navigation_catalog_v5_data import V5_FUNCTIONS, V5_INTENTS, merge_with_base as merge_v5_with_base
from navigation_catalog_v6_data import V6_FUNCTIONS, V6_INTENTS, merge_with_base as merge_v6_with_base
from navigation_catalog_v7_data import V7_FUNCTIONS, V7_INTENTS, merge_with_base as merge_v7_with_base
from navigation_catalog_v8_data import V8_FUNCTIONS, V8_INTENTS, merge_with_base as merge_v8_with_base
from navigation_catalog_v9_data import V9_FUNCTIONS, V9_INTENTS, merge_with_base as merge_v9_with_base
from navigation_catalog_v10_data import V10_FUNCTIONS, V10_INTENTS, merge_with_base as merge_v10_with_base
from navigation_catalog_v11_data import V11_FUNCTIONS, V11_INTENTS, merge_with_base as merge_v11_with_base
from navigation_catalog_v12_data import (
    V12_FUNCTIONS,
    V12_INTENTS,
    merge_with_base as merge_v12_with_base,
)
from navigation_catalog_v13_data import (
    V13_FUNCTIONS,
    V13_INTENTS,
    merge_with_base as merge_v13_with_base,
)
from navigation_catalog_v14_data import (
    V14_FUNCTIONS,
    V14_INTENTS,
    merge_with_base as merge_v14_with_base,
)
from navigation_catalog_v15_data import (
    V15_FUNCTIONS,
    V15_INTENTS,
    merge_with_base as merge_v15_with_base,
)
from navigation_catalog_v16_data import (
    CATALOG_V16_DESCRIPTION,
    CATALOG_V16_VERSION,
    V16_FUNCTIONS,
    V16_INTENTS,
    merge_equivalence_with_v16,
    merge_with_base as merge_v16_with_base,
    project_equivalence_to_v15,
)
from navigation_alias_context_overrides import apply_alias_context_overrides, strip_alias_context_overrides


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"


def _values(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split("|") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


def function(
    function_id: str,
    domain: str,
    name_ko: str,
    name_en: str,
    ko: str,
    en: str,
    positive: str,
    negative: str,
    *,
    risk: str = "low",
    policy: str = "safe_navigation",
    terminal: bool = True,
    changing: bool = False,
    scope: str = "in_app",
    node_kind: str = "destination",
    stop_policy: str = "on_destination_screen",
    tags: str = "",
    state_cues: dict[str, list[str]] | None = None,
    risk_cues: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    if changing and policy != "never_auto":
        raise ValueError(f"state-changing function must be never_auto: {function_id}")
    if risk == "high" and policy != "never_auto":
        raise ValueError(f"high-risk function must be never_auto: {function_id}")
    return {
        "function_id": function_id,
        "domain": domain,
        "scope": scope,
        "node_kind": node_kind,
        "stop_policy": stop_policy,
        "name_ko": name_ko,
        "name_en": name_en,
        "description": f"앱 또는 Android 설정에서 {name_ko} 기능의 목적 화면을 식별한다.",
        "risk_level": risk,
        "automation_policy": policy,
        "terminal": terminal,
        "state_changing": changing,
        "legacy_tags": _values(tags),
        "role_hints": ["button", "menuitem", "tab"],
        "aliases": {"ko-KR": _values(ko), "en-US": _values(en)},
        "positive_context": _values(positive),
        "negative_context": _values(negative),
        "state_cues": state_cues or {},
        "risk_cues": risk_cues or {},
    }


def intent(
    intent_id: str,
    terminal_function: str,
    patterns: str,
    route: str,
    *,
    rules: str = "",
    avoid: str = "",
    desired_state: str = "destination_visible",
) -> dict[str, object]:
    route_steps: list[dict[str, object]] = []
    for item in _values(route):
        function_id, weight = item.rsplit(":", 1)
        route_steps.append({"function_id": function_id, "weight": float(weight)})
    goal_rules = []
    for rule in _values(rules):
        goal_rules.append({"all_of": _values(rule.replace("+", "|")), "score": 0.99})
    return {
        "intent_id": intent_id,
        "terminal_function": terminal_function,
        "patterns": _values(patterns),
        "patterns_by_locale": {
            "ko-KR": [value for value in _values(patterns) if any("가" <= ch <= "힣" for ch in value)],
            "en-US": [value for value in _values(patterns) if not any("가" <= ch <= "힣" for ch in value)],
        },
        "goal_rules": goal_rules,
        "route": route_steps,
        "avoid_functions": _values(avoid),
        "desired_state": desired_state,
        "terminal_condition": {"stop_policy": "stop_before_action" if desired_state == "user_confirmation_required" else "on_destination_screen"},
    }


ON_OFF = {
    "on": ["사용", "켜짐", "허용됨", "On", "Enabled", "Allowed"],
    "off": ["사용 안 함", "꺼짐", "허용되지 않음", "Off", "Disabled", "Not allowed"],
}


DESTRUCTIVE_RISK = {
    "action": ["삭제", "제거", "중지", "해지", "delete", "remove", "stop", "cancel"],
    "consequence": ["되돌릴 수 없음", "데이터가 사라짐", "cannot be undone", "data will be removed"],
}


RISK_CUE_PATCHES: dict[str, dict[str, list[str]]] = {
    "account.delete.confirm": DESTRUCTIVE_RISK,
    "auth.login": {"credential": ["비밀번호", "인증", "password", "verification"], "session": ["로그인", "sign in"]},
    "auth.logout": {"session": ["현재 세션 종료", "다시 로그인", "end session", "sign in again"]},
    "auth.signup.confirm": {"external_submission": ["계정 생성", "가입 완료", "create account", "complete registration"]},
    "auth.guest": {"session": ["게스트 세션", "일부 기능 제한", "guest session", "limited features"]},
    "account.switch": {"session": ["활성 계정 변경", "다른 계정", "switch active account", "another account"]},
    "consent.required": {"legal_consent": ["필수 동의", "서비스 이용", "required consent", "use service"]},
    "consent.optional": {"legal_consent": ["선택 동의", "마케팅", "optional consent", "marketing"]},
    "consent.age": {"identity": ["연령 확인", "생년월일", "age verification", "date of birth"]},
    "consent.parental": {"legal_consent": ["법정대리인", "보호자 동의", "parental consent", "guardian"]},
    "onboarding.profile": {"personal_data": ["이름", "생년월일", "프로필", "name", "date of birth", "profile"]},
    "onboarding.permissions": {"sensitive_access": ["권한 허용", "위치", "연락처", "allow permission", "location", "contacts"]},
    "onboarding.interests": {"personalization": ["관심사", "추천", "interests", "recommendations"]},
    "subscription.cancel.confirm": {"recurring_charge": ["혜택 종료", "다음 결제 없음", "benefits end", "no next charge"]},
    "subscription.pause": {"recurring_charge": ["일시중지 기간", "다음 결제일", "pause period", "next billing date"]},
    "subscription.change": {"recurring_charge": ["요금제", "결제 금액", "plan", "billing amount"]},
    "notification.service": {"communication": ["서비스 알림", "푸시", "service alert", "push notification"]},
    "marketing.opt_out": {"legal_consent": ["수신 철회", "마케팅 동의", "withdraw", "marketing consent"]},
    "privacy.consent.withdraw": {"legal_consent": ["동의 철회", "처리 중지", "withdraw consent", "stop processing"]},
    "privacy.delete_data": {"personal_data": ["개인 데이터", "영구 삭제", "personal data", "permanently delete"]},
    "refund.confirm": {"money": ["환불 금액", "결제 수단", "refund amount", "payment method"], "external_submission": ["환불 요청", "submit refund"]},
    "order.cancel.confirm": {"money": ["취소 수수료", "환불 예정", "cancellation fee", "refund due"], "external_submission": ["주문 취소", "cancel order"]},
    "security.password": {"credential": ["현재 비밀번호", "새 비밀번호", "current password", "new password"]},
    "security.two_factor": {"credential": ["복구 코드", "인증 앱", "recovery code", "authenticator"]},
    "system.permission": {"sensitive_access": ["카메라", "마이크", "위치", "camera", "microphone", "location"]},
    "system.defaults": {"scope": ["모든 설정", "기본값", "all settings", "defaults"]},
    "android.app.background_usage": {"system_behavior": ["백그라운드 실행", "배터리", "background activity", "battery"]},
    "android.app.background_data": {"network_access": ["백그라운드 데이터", "모바일 데이터", "background data", "mobile data"]},
    "android.app.clear_defaults": {"scope": ["기본 연결", "지원 링크", "default links", "supported links"]},
    "files.restore": {"cloud_data": ["휴지통에서 복원", "원래 위치", "restore from trash", "original location"]},
}


# Reusable semantic atoms for compositional menu matching.  These are short
# cross-app concepts rather than benchmark labels: an unseen phrase such as
# "메일 주소 교체" can resolve through email + change, while a sibling such
# as "메일 알림" resolves through email + notification + receive.
SEMANTIC_LEXICON: dict[str, dict[str, list[str]]] = {
    "account": {"ko-KR": ["계정", "회원", "서비스 이용"], "en-US": ["account", "member profile"]},
    "email": {"ko-KR": ["이메일", "메일"], "en-US": ["email", "mail address"]},
    "phone": {"ko-KR": ["휴대폰", "전화번호", "연락처 번호", "본인 확인 번호"], "en-US": ["phone number", "mobile number", "contact number"]},
    "sms": {"ko-KR": ["문자", "SMS"], "en-US": ["sms", "text alert", "text message"]},
    "change": {"ko-KR": ["변경", "바꾸", "교체", "수정", "편집"], "en-US": ["change", "update", "replace", "edit"]},
    "signup": {"ko-KR": ["회원가입", "가입", "계정 만들", "새 계정", "새로 시작"], "en-US": ["sign up", "register", "create account", "new account", "start new"]},
    "notification": {"ko-KR": ["알림", "안내", "소식"], "en-US": ["notification", "alert", "news"]},
    "receive": {"ko-KR": ["수신", "받는", "받을"], "en-US": ["receive", "delivery", "delivered"]},
    "settings": {"ko-KR": ["설정", "관리", "제어", "환경"], "en-US": ["settings", "manage", "management", "controls", "preferences"]},
    "android_system": {"ko-KR": ["Android", "운영체제", "시스템", "휴대전화 설정", "폰 설정", "설치된 애플리케이션", "앱 정보 화면"], "en-US": ["android", "operating system", "system details", "phone settings", "installed applications", "app info screen"]},
    "storage": {"ko-KR": ["저장공간", "저장 공간", "용량", "스토리지"], "en-US": ["storage", "space usage", "disk space"]},
    "offline": {"ko-KR": ["오프라인", "내려받", "다운로드"], "en-US": ["offline", "downloaded", "downloads"]},
    "data_usage": {"ko-KR": ["데이터 사용", "통신량", "네트워크 사용", "모바일 데이터", "셀룰러"], "en-US": ["data usage", "bandwidth", "network usage", "mobile data", "cellular data"]},
    "saver": {"ko-KR": ["절약", "덜 쓰", "사용량 줄"], "en-US": ["data saver", "reduce usage", "limit data"]},
    "activity": {"ko-KR": ["활동", "이용 흔적", "검색 기록"], "en-US": ["activity", "usage activity", "search activity"]},
    "delete": {"ko-KR": ["삭제", "지우", "제거", "정리"], "en-US": ["delete", "erase", "remove", "clear"]},
    "permission": {"ko-KR": ["권한", "기능 접근", "접근 허용"], "en-US": ["permission", "feature access", "allow access"]},
    "onboarding": {"ko-KR": ["처음 시작", "사용 준비", "초기 설정"], "en-US": ["onboarding", "first-time setup", "get started"]},
    "content": {"ko-KR": ["콘텐츠", "게시물", "영상"], "en-US": ["content", "post", "video"]},
    "feed": {"ko-KR": ["피드", "새 영상 모음", "새 콘텐츠 모음"], "en-US": ["feed", "new videos", "new content"]},
    "channel": {"ko-KR": ["채널"], "en-US": ["channel", "following"]},
    "subscription": {"ko-KR": ["구독", "멤버십", "이용권"], "en-US": ["subscription", "membership", "plan"]},
    "paid": {"ko-KR": ["유료", "요금", "결제", "청구", "출금"], "en-US": ["paid", "charge", "charging", "billing", "payment"]},
    "recurring": {"ko-KR": ["정기", "반복", "자동 결제", "자동결제", "자동 갱신", "자동 연장", "이어지는"], "en-US": ["recurring", "automatic renewal", "auto-renew", "scheduled payment", "repeating"]},
    "cancel": {"ko-KR": ["해지", "취소", "종료", "철회", "중지"], "en-US": ["cancel", "terminate", "deactivate", "stop renewal", "close"]},
    "entry": {"ko-KR": ["절차", "시작", "진입", "신청"], "en-US": ["entry", "start", "request", "process"]},
    "status": {"ko-KR": ["상태", "진행", "추적", "처리 중"], "en-US": ["status", "progress", "track", "pending"]},
    "refund": {"ko-KR": ["환불", "반환", "돌려받", "환급"], "en-US": ["refund", "money back", "money return", "reimbursement"]},
    "order": {"ko-KR": ["주문", "구매", "상품"], "en-US": ["order", "purchase", "item"]},
    "shipping": {"ko-KR": ["발송", "배송"], "en-US": ["shipping", "dispatch", "shipment"]},
    "insurance": {"ko-KR": ["보험", "보험계약", "계약 종료"], "en-US": ["insurance", "policy", "policy surrender"]},
    "estimate": {"ko-KR": ["예상", "조회", "가정"], "en-US": ["estimate", "estimated", "expected", "preview"]},
    "value": {"ko-KR": ["금액", "반환금", "환급금"], "en-US": ["value", "amount", "cash value"]},
    "password": {"ko-KR": ["비밀번호", "암호", "접속 암호"], "en-US": ["password", "passcode"]},
    "security": {"ko-KR": ["보안", "본인 확인", "인증"], "en-US": ["security", "sign-in security", "authentication"]},
    "recovery": {"ko-KR": ["복구", "찾기", "잊어", "재설정"], "en-US": ["recover", "recovery", "forgot", "reset"]},
    "create": {"ko-KR": ["만들", "생성", "정하기"], "en-US": ["create", "set", "choose"]},
    "file": {"ko-KR": ["파일", "문서"], "en-US": ["file", "document"]},
    "share": {"ko-KR": ["공유", "전달", "보내기"], "en-US": ["share", "send", "access"]},
    "people": {"ko-KR": ["사람", "사용자", "접근 권한"], "en-US": ["people", "collaborator", "document access"]},
    "travel": {"ko-KR": ["여행", "항공", "여정"], "en-US": ["travel", "flight", "trip"]},
    "booking": {"ko-KR": ["예약", "일정", "여정"], "en-US": ["booking", "reservation", "itinerary"]},
    "list": {"ko-KR": ["목록", "모아보기", "대화함", "모든 채널"], "en-US": ["list", "all", "inbox"]},
    "health": {"ko-KR": ["진료", "병원", "의료", "검사", "건강"], "en-US": ["clinic", "doctor", "medical", "health", "test"]},
    "appointment": {"ko-KR": ["진료 예약", "방문 일정", "내원"], "en-US": ["appointment", "book a visit", "medical visit"]},
    "transfer": {"ko-KR": ["이체", "송금"], "en-US": ["transfer", "money transfer", "standing order"]},
    "history": {"ko-KR": ["기록", "내역", "이력", "이전에 본"], "en-US": ["history", "records", "previously viewed"]},
    "current": {"ko-KR": ["현재", "열린", "활성"], "en-US": ["current", "active", "open"]},
    "session": {"ko-KR": ["로그인", "세션", "접속"], "en-US": ["login", "sign-in", "session", "logged in"]},
    "captions": {"ko-KR": ["자막", "실시간 받아쓰기"], "en-US": ["captions", "caption", "transcription"]},
    "accessibility": {"ko-KR": ["접근성", "청각 지원", "전체 오디오"], "en-US": ["accessibility", "hearing", "all audio", "live transcription"]},
    "conversation": {"ko-KR": ["대화", "채팅", "메시지"], "en-US": ["conversation", "chat", "message"]},
    "inbox": {"ko-KR": ["대화함", "메시지함", "받은 메시지"], "en-US": ["inbox", "message list", "conversations"]},
    "compose": {"ko-KR": ["새 대화", "쓰기", "작성"], "en-US": ["compose", "new message", "write message"]},
    "trash": {"ko-KR": ["휴지통", "버린 파일", "최근 삭제"], "en-US": ["trash", "bin", "deleted files"]},
    "card": {"ko-KR": ["카드"], "en-US": ["card"]},
    "finance": {"ko-KR": ["금융", "발급 카드", "이용 한도", "거래", "카드 이용"], "en-US": ["finance", "issued card", "card security", "transaction", "card usage"]},
    "payment_method": {"ko-KR": ["결제 수단", "청구에 사용할 수단", "지불 방법"], "en-US": ["payment method", "billing method", "pay with"]},
    "benefit": {"ko-KR": ["혜택"], "en-US": ["benefit", "perks"]},
    "freeze": {"ko-KR": ["잠금", "사용 정지", "결제 차단"], "en-US": ["freeze", "lock", "block payments"]},
    "support": {"ko-KR": ["지원", "문의", "상담원", "운영팀", "고객센터", "도움"], "en-US": ["support", "contact", "help", "agent"]},
    "help_center": {"ko-KR": ["도움", "도움말", "문제 해결"], "en-US": ["help center", "help", "troubleshooting"]},
    "form": {"ko-KR": ["양식", "문의 양식", "연락처"], "en-US": ["form", "contact form", "request form"]},
    "profile": {"ko-KR": ["프로필", "회원정보"], "en-US": ["profile", "personal details"]},
    "privacy": {"ko-KR": ["개인정보", "공개 범위", "데이터 제어"], "en-US": ["privacy", "data control", "visibility"]},
    "playback": {"ko-KR": ["재생", "플레이어"], "en-US": ["playback", "player"]},
    "general": {"ko-KR": ["전반", "일반 환경"], "en-US": ["general", "overall preferences"]},
    "faq": {"ko-KR": ["자주 묻", "많이 묻", "문제 모음"], "en-US": ["faq", "frequently asked", "common questions", "help articles"]},
    "saved": {"ko-KR": ["저장", "보관", "나중에 볼"], "en-US": ["saved", "bookmark", "watch later"]},
    "wishlist": {"ko-KR": ["찜", "구매 후보", "관심 상품"], "en-US": ["wishlist", "wish list", "shopping favorites"]},
    "product": {"ko-KR": ["상품", "구매 후보"], "en-US": ["product", "shopping item"]},
    "receipt": {"ko-KR": ["영수증", "결제 증빙", "구매 증빙"], "en-US": ["receipt", "invoice", "proof of payment"]},
    "statement": {"ko-KR": ["명세서", "청구 내역서", "이용 대금"], "en-US": ["statement", "billing statement", "account statement"]},
    "monthly": {"ko-KR": ["월간", "월별", "이번 달"], "en-US": ["monthly", "this month"]},
    "marketing": {"ko-KR": ["마케팅", "광고성", "프로모션", "이벤트 혜택", "혜택 수신"], "en-US": ["marketing", "promotional", "advertising", "offers and promotions"]},
    "app_info": {"ko-KR": ["앱 정보", "애플리케이션 정보"], "en-US": ["app info", "application information", "about app"]},
    "in_app": {"ko-KR": ["일반", "버전", "만든 곳", "서비스 소개"], "en-US": ["general", "version", "about product", "made by"]},
    "two_factor": {"ko-KR": ["2단계", "이중 인증", "추가 인증"], "en-US": ["two-factor", "2fa", "second factor"]},
    "autoplay": {"ko-KR": ["자동 재생", "연속 재생"], "en-US": ["autoplay", "play automatically"]},
    "consent": {"ko-KR": ["동의", "약관 항목"], "en-US": ["consent", "agreement"]},
    "optional": {"ko-KR": ["선택", "필수가 아닌"], "en-US": ["optional", "not required"]},
}


SEMANTIC_CONCEPT_PATCHES: dict[str, list[str]] = {
    "notification.settings": ["notification", "receive", "settings"],
    "android.app.notifications": ["notification", "android_system", "settings"],
    "system.app_info": ["app_info", "in_app"],
    "android.app.info": ["app_info", "android_system"],
    "settings.storage": ["storage", "offline", "content"],
    "android.app.storage_cache": ["storage", "android_system"],
    "settings.data_usage": ["data_usage", "saver", "settings"],
    "android.app.data_usage": ["data_usage", "android_system"],
    "privacy.delete_data": ["privacy", "activity", "delete"],
    "android.app.clear_storage": ["storage", "android_system", "delete"],
    "onboarding.permissions": ["onboarding", "permission"],
    "android.permission.manage": ["permission", "android_system"],
    "content.subscriptions": ["content", "feed", "channel", "subscription"],
    "subscription.manage": ["subscription", "paid", "settings", "benefit"],
    "subscription.list": ["subscription", "paid", "list"],
    "subscription.cancel.entry": ["subscription", "cancel", "entry"],
    "subscription.renewal": ["subscription", "recurring"],
    "billing.autopay": ["paid", "recurring", "settings"],
    "refund.entry": ["refund", "entry", "order"],
    "billing.refund_status": ["refund", "status"],
    "order.cancel.entry": ["order", "shipping", "cancel", "entry"],
    "insurance.surrender_value": ["insurance", "cancel", "estimate", "value"],
    "account.email.change": ["account", "email", "change"],
    "auth.signup.email": ["signup", "email"],
    "notification.email": ["notification", "receive", "email"],
    "account.phone.change": ["account", "phone", "change"],
    "auth.signup.phone": ["signup", "phone"],
    "notification.sms": ["notification", "receive", "sms"],
    "security.password": ["password", "change", "security"],
    "security.password.reset": ["password", "recovery", "security"],
    "auth.password.create": ["signup", "password", "create"],
    "files.share": ["file", "share", "people"],
    "content.share": ["content", "share"],
    "travel.bookings": ["travel", "booking", "list"],
    "health.appointments": ["health", "appointment"],
    "finance.recurring_transfer": ["transfer", "recurring"],
    "travel.booking.cancel.entry": ["travel", "booking", "cancel", "entry"],
    "content.history": ["content", "history"],
    "billing.purchase_history": ["order", "paid", "history"],
    "finance.transactions": ["finance", "history"],
    "health.records": ["health", "history"],
    "account.sessions": ["session", "current"],
    "security.login_history": ["session", "history", "security"],
    "accessibility.captions": ["accessibility", "captions"],
    "account.delete.entry": ["account", "cancel", "entry"],
    "content.delete.entry": ["content", "delete", "entry"],
    "communication.conversation.delete": ["conversation", "delete"],
    "files.trash": ["file", "trash"],
    "finance.cards": ["finance", "card", "security"],
    "billing.payment_method": ["paid", "payment_method"],
    "finance.card.freeze": ["finance", "card", "freeze"],
    "support.chat": ["support", "conversation"],
    "communication.inbox": ["conversation", "inbox"],
    "support.contact": ["support", "form"],
    "communication.compose": ["conversation", "compose"],
    "account.profile.edit": ["profile", "change"],
    "privacy.settings": ["privacy", "settings"],
    "settings.playback": ["playback", "general", "settings"],
    "media.autoplay": ["playback", "autoplay"],
    "support.faq": ["support", "faq"],
    "content.saved": ["content", "saved"],
    "commerce.wishlist": ["product", "wishlist", "saved"],
    "billing.receipt": ["order", "paid", "receipt"],
    "finance.statements": ["finance", "statement", "monthly"],
    "marketing.settings": ["marketing", "notification", "settings"],
    "support.help": ["support", "help_center"],
    "auth.two_factor": ["security", "two_factor"],
    "consent.optional": ["consent", "optional"],
}


# Concepts that must be printed on the candidate itself before it can end a
# route.  Parent/screen context may help classify a menu, but cannot fabricate
# the action-defining word.  This prevents a privacy hub called "활동 데이터"
# from masquerading as "활동 기록 삭제", and a notification hub from
# masquerading as the marketing-preference destination.
SEMANTIC_TERMINAL_CONCEPT_PATCHES: dict[str, list[str]] = {
    "privacy.delete_data": ["delete"],
    "marketing.settings": ["marketing"],
    "order.cancel.entry": ["cancel"],
}


# Goal wording rarely repeats a menu label.  These rules connect common
# consequence- and context-based requests to an intent by requiring two to
# four independent semantic cues.  The cues are deliberately reusable stems
# (object + operation + scope/state), not copies of any benchmark sentence.
# Keeping them here makes the reviewable JSON a deterministic materialization
# and prevents evaluation fixtures from becoming a hidden runtime dependency.
GENERALIZED_GOAL_RULES: dict[str, list[tuple[tuple[str, ...], float]]] = {
    "account_login": [
        (("계정", "다시", "들어가"), 1.0),
        (("existing", "account", "enter"), 1.0),
    ],
    "account_switching": [
        (("profile", "other", "work"), 1.0),
        (("다른", "프로필", "전환"), 1.0),
    ],
    "activity_status_control": [
        (("접속 중", "다른 사람", "보이지"), 1.0),
        (("online status", "hide"), 1.0),
    ],
    "add_account": [
        (("remember", "one more", "account"), 1.0),
        (("계정", "하나 더", "연결"), 1.0),
    ],
    "edit_profile": [
        (("display name", "profile", "correct"), 1.0),
        (("프로필", "표시 이름", "수정"), 1.0),
    ],
    "change_email": [
        (("계정", "새 메일", "옮"), 1.0),
        (("account", "new email", "move"), 1.0),
    ],
    "change_phone_number": [
        (("인증번호", "휴대전화 번호", "바꾸"), 1.0),
        (("verification", "phone number", "change"), 1.0),
    ],
    "change_profile_photo": [
        (("replacing", "current", "avatar"), 1.0),
        (("프로필 사진", "새", "바꾸"), 1.0),
    ],
    "change_username": [
        (("표시되는", "사용자 이름", "바꾸"), 1.0),
        (("displayed", "username", "replace"), 1.0),
    ],
    "account_logout": [
        (("이 기기", "계정 연결", "끝"), 1.0),
        (("this device", "account session", "end"), 1.0),
    ],
    "account_deletion": [
        (("계정", "자료", "영구"), 1.0),
        (("계정", "마지막 경고", "멈"), 1.0),
        (("account", "permanent", "remove"), 1.0),
    ],
    "linked_accounts": [
        (("연결", "외부 로그인", "계정"), 1.0),
        (("linked", "external", "accounts"), 1.0),
    ],
    "password_reset": [
        (("cannot remember", "password", "new"), 1.0),
        (("로그인할 수 없", "계정", "되찾"), 1.0),
    ],
    "passkey_management": [
        (("비밀번호 대신", "지문", "로그인"), 1.0),
        (("passwordless", "fingerprint", "sign-in"), 1.0),
    ],
    "biometric_login_settings": [
        (("face", "fingerprint", "sign-in"), 1.0),
        (("얼굴", "지문", "로그인"), 1.0),
    ],
    "active_sessions": [
        (("모르는 휴대폰", "접속", "끊"), 1.0),
        (("devices", "currently", "account"), 1.0),
    ],
    "two_factor_verification": [
        (("another", "verification step", "signs in"), 1.0),
        (("로그인", "추가 인증", "단계"), 1.0),
    ],
    "security_settings": [
        (("로그인 보호", "인증 수단", "관리"), 1.0),
        (("sign-in protection", "authentication", "manage"), 1.0),
    ],
    "identity_verification": [
        (("새 계정", "휴대전화", "내 것"), 1.0),
        (("new account", "phone", "verify ownership"), 1.0),
    ],
    "guest_access": [
        (("browse", "without", "account"), 1.0),
        (("계정 없이", "둘러보"), 1.0),
    ],
    "social_registration": [
        (("creating account", "existing", "apple"), 1.0),
        (("기존", "소셜", "계정", "가입"), 1.0),
    ],
    "onboarding_profile_setup": [
        (("new member", "display name", "picture"), 1.0),
        (("신규 회원", "이름", "사진"), 1.0),
    ],
    "account_registration": [
        (("age declaration", "account creation"), 1.0),
        (("미성년", "보호자", "가입"), 1.0),
        (("optional", "topics", "first-time setup"), 1.0),
        (("새 계정", "확정", "마지막 버튼"), 1.0),
        (("initial account setup", "finished", "summary"), 1.0),
    ],
    "signup_required_consent": [
        (("agreement", "must", "new account"), 1.0),
        (("가입", "필수", "동의"), 1.0),
    ],
    "signup_terms_review": [
        (("가입하기 전", "계약 내용", "읽"), 1.0),
        (("before sign-up", "contract", "review"), 1.0),
    ],
    "onboarding_permission_setup": [
        (("가입 중", "기기 권한", "시스템"), 1.0),
        (("onboarding", "device permission", "system prompt"), 1.0),
    ],
    "android_app_notifications": [
        (("진동", "배너", "안 뜨"), 1.0),
        (("one app", "vibration", "banner"), 1.0),
    ],
    "android_notification_categories": [
        (("choose", "kinds of alerts", "app"), 1.0),
        (("앱", "알림 종류", "선택"), 1.0),
    ],
    "android_notification_access": [
        (("알림을 읽", "앱 권한", "확인"), 1.0),
        (("read notifications", "app access"), 1.0),
    ],
    "android_change_permission": [
        (("camera", "only while", "using"), 1.0),
        (("카메라", "사용 중에만", "허용"), 1.0),
    ],
    "android_enable_overlay": [
        (("다른 앱 위", "도우미 창", "띄"), 1.0),
        (("helper window", "over other apps"), 1.0),
    ],
    "android_enable_accessibility_service": [
        (("화면 메뉴", "읽", "보조 기능 권한"), 1.0),
        (("read screen", "accessibility service", "enable"), 1.0),
    ],
    "android_default_apps": [
        (("web links", "preferred browser", "asking"), 1.0),
        (("웹 링크", "선호 브라우저", "항상"), 1.0),
    ],
    "android_open_by_default": [
        (("웹 주소", "이 앱", "연결"), 1.0),
        (("web address", "this app", "open"), 1.0),
    ],
    "android_clear_defaults": [
        (("forget", "handles", "links automatically"), 1.0),
        (("링크", "자동", "연결", "잊"), 1.0),
    ],
    "android_open_settings": [
        (("phone", "main configuration", "not this app"), 1.0),
        (("휴대전화", "전체 설정", "앱 설정 아님"), 1.0),
    ],
    "android_manage_apps": [
        (("every installed", "application", "listed"), 1.0),
        (("설치된", "모든 앱", "목록"), 1.0),
    ],
    "android_permission_manager": [
        (("카메라", "위치 권한", "앱", "한곳"), 1.0),
        (("all apps", "permission", "overview"), 1.0),
    ],
    "android_special_access": [
        (("advanced access", "installed apps"), 1.0),
        (("설치 앱", "고급 접근", "제어"), 1.0),
    ],
    "android_app_battery": [
        (("앱", "배터리", "얼마나"), 1.0),
        (("app", "battery", "usage"), 1.0),
    ],
    "android_background_data": [
        (("mobile data", "not open", "stop"), 1.0),
        (("앱 닫", "모바일 데이터", "중지"), 1.0),
    ],
    "android_background_usage": [
        (("화면", "꺼", "계속 작동"), 1.0),
        (("screen off", "keep running", "app"), 1.0),
    ],
    "android_clear_app_cache": [
        (("로그인 정보", "남기", "임시 파일"), 1.0),
        (("keep login", "temporary files", "clear"), 1.0),
    ],
    "android_force_stop_app": [
        (("멈춘", "앱", "완전히 종료"), 1.0),
        (("frozen app", "force", "stop"), 1.0),
    ],
    "android_uninstall_app": [
        (("사용하지 않는", "게임", "제거 직전"), 1.0),
        (("unused app", "before uninstall"), 1.0),
    ],
    "shopping_cart": [
        (("담아 둔", "물건", "결제 전"), 1.0),
        (("items", "before checkout", "review"), 1.0),
    ],
    "order_details": [
        (("full record", "bought", "last week"), 1.0),
        (("구매", "상품", "상세 기록"), 1.0),
    ],
    "order_tracking": [
        (("택배", "어디쯤", "확인"), 1.0),
        (("package", "where", "track"), 1.0),
    ],
    "order_return": [
        (("delivered item", "not match", "send back"), 1.0),
        (("반품", "마지막 확인", "멈"), 1.0),
    ],
    "order_exchange": [
        (("사이즈", "다른", "바꾸"), 1.0),
        (("wrong size", "exchange", "item"), 1.0),
    ],
    "order_cancellation": [
        (("주문 취소", "마지막 버튼", "앞"), 1.0),
        (("order cancellation", "final control"), 1.0),
    ],
    "product_review": [
        (("산 물건", "사용 후기", "남기"), 1.0),
        (("purchased item", "review", "write"), 1.0),
    ],
    "coupon_management": [
        (("saved discounts", "promotion code"), 1.0),
        (("할인", "프로모션 코드", "입력"), 1.0),
    ],
    "compose_message": [
        (("연락처", "새 대화", "시작"), 1.0),
        (("contact", "new conversation", "start"), 1.0),
    ],
    "search_conversation": [
        (("대화 내 메시지 검색",), 1.0),
        (("대화 안에서 메시지 검색",), 1.0),
        (("search messages in a conversation",), 1.0),
        (("search messages within this conversation",), 1.0),
        (("대화", "메시지", "검색"), 1.0),
        (("conversation", "search", "messages"), 1.0),
        (("old conversation", "discussed", "receipt"), 1.0),
        (("예전 대화", "검색", "내용"), 1.0),
    ],
    "mute_conversation": [
        (("단체방", "알림", "조용"), 1.0),
        (("group chat", "notifications", "quiet"), 1.0),
    ],
    "archive_conversation": [
        (("채팅", "지우지", "받은 편지함"), 1.0),
        (("chat", "not delete", "inbox"), 1.0),
    ],
    "delete_conversation": [
        (("대화 기록", "목록", "지우"), 1.0),
        (("conversation record", "list", "remove"), 1.0),
    ],
    "blocked_users": [
        (("차단", "사람", "명단"), 1.0),
        (("blocked", "people", "list"), 1.0),
    ],
    "create_content": [
        (("사진", "짧은 글", "새 게시물"), 1.0),
        (("photo", "text", "new post"), 1.0),
    ],
    "upload_content": [
        (("adding", "new photo post", "not publish"), 1.0),
        (("새 사진 게시물", "추가", "게시 전"), 1.0),
    ],
    "edit_content": [
        (("올린", "게시글", "문장", "고치"), 1.0),
        (("existing post", "text", "edit"), 1.0),
    ],
    "view_drafts": [
        (("unfinished", "post", "continue editing"), 1.0),
        (("미완성", "게시물", "계속 편집"), 1.0),
    ],
    "delete_content": [
        (("올린", "게시물 하나", "지우"), 1.0),
        (("my post", "one", "delete"), 1.0),
    ],
    "view_comments": [
        (("게시물", "다른 사람", "반응", "펼쳐"), 1.0),
        (("post", "other people", "comments"), 1.0),
    ],
    "not_interested": [
        (("비슷한 영상", "추천", "덜"), 1.0),
        (("similar videos", "recommend", "less"), 1.0),
    ],
    "download_settings": [
        (("영상", "와이파이", "저장"), 1.0),
        (("video", "wi-fi only", "download"), 1.0),
    ],
    "downloaded_content": [
        (("movies", "saved", "offline viewing"), 1.0),
        (("저장된", "영화", "오프라인"), 1.0),
    ],
    "caption_settings": [
        (("외국어 영상", "자막", "자동"), 1.0),
        (("foreign language video", "captions", "automatic"), 1.0),
    ],
    "playback_quality": [
        (("streaming quality", "mobile data", "bandwidth"), 1.0),
        (("화질", "모바일 데이터", "사용량"), 1.0),
    ],
    "playback_speed": [
        (("lecture", "one and a half", "speed"), 1.0),
        (("강의", "배속", "재생"), 1.0),
    ],
    "appearance_change": [
        (("interface", "darker", "color scheme"), 1.0),
        (("화면", "어두운", "색상"), 1.0),
    ],
    "language_change": [
        (("표시 문자", "영어", "바꾸"), 1.0),
        (("display language", "english", "change"), 1.0),
    ],
    "travel_bookings": [
        (("예약번호 없이", "다음 비행", "일정"), 1.0),
        (("next flight", "itinerary", "without booking number"), 1.0),
    ],
    "travel_booking_details": [
        (("예약", "시간", "예약번호"), 1.0),
        (("reservation", "time", "booking number"), 1.0),
    ],
    "travel_checkin": [
        (("mobile check-in", "flight", "tomorrow"), 1.0),
        (("내일 비행", "모바일 체크인"), 1.0),
    ],
    "travel_boarding_pass": [
        (("mobile boarding pass", "airport security"), 1.0),
        (("모바일 탑승권", "공항 보안"), 1.0),
    ],
    "travel_booking_change": [
        (("출발일", "하루 뒤", "옮"), 1.0),
        (("departure date", "move", "one day"), 1.0),
    ],
    "travel_booking_cancellation": [
        (("탑승하지 않을", "항공편", "취소 절차"), 1.0),
        (("unused flight", "cancel", "process"), 1.0),
    ],
    "travel_baggage": [
        (("checked luggage", "added", "upcoming flight"), 1.0),
        (("위탁 수하물", "추가", "항공편"), 1.0),
    ],
    "travel_flight_status": [
        (("flight", "delayed", "changed gates"), 1.0),
        (("항공편", "지연", "게이트"), 1.0),
    ],
    "travel_seat_selection": [
        (("비행기", "좌석", "창가"), 1.0),
        (("flight", "seat", "window"), 1.0),
    ],
    "transaction_history": [
        (("last month", "outgoing", "transactions"), 1.0),
        (("지난달", "출금", "거래"), 1.0),
    ],
    "money_transfer": [
        (("친구 계좌", "돈", "보내"), 1.0),
        (("friend account", "send money"), 1.0),
    ],
    "recurring_transfer_management": [
        (("매달", "정해진 날", "이체"), 1.0),
        (("monthly", "scheduled", "transfer"), 1.0),
    ],
    "financial_accounts": [
        (("금융 앱", "등록된", "통장", "한 번에"), 1.0),
        (("registered", "bank accounts", "all"), 1.0),
    ],
    "freeze_card": [
        (("카드", "잠깐", "결제", "막"), 1.0),
        (("card", "temporarily", "block payments"), 1.0),
    ],
    "report_lost_card": [
        (("카드", "잃어버", "신고"), 1.0),
        (("lost card", "report"), 1.0),
    ],
    "financial_statements": [
        (("연말", "계좌 명세서", "pdf"), 1.0),
        (("year-end", "account statement", "pdf"), 1.0),
    ],
    "search_files": [
        (("stored files", "pdf", "name"), 1.0),
        (("저장 파일", "이름", "검색"), 1.0),
    ],
    "upload_file": [
        (("문서", "클라우드 폴더", "올리"), 1.0),
        (("document", "cloud folder", "upload"), 1.0),
    ],
    "share_file": [
        (("읽기만", "파일 링크", "팀원"), 1.0),
        (("read-only", "file link", "teammate"), 1.0),
    ],
    "restore_file": [
        (("휴지통", "원래 위치", "되돌"), 1.0),
        (("trash", "original location", "restore"), 1.0),
    ],
    "file_backup": [
        (("copies", "documents", "cloud storage"), 1.0),
        (("문서", "클라우드", "백업"), 1.0),
    ],
    "privacy_visibility": [
        (("모르는 사람", "프로필", "보이지"), 1.0),
        (("strangers", "profile", "hide"), 1.0),
    ],
    "read_receipts_control": [
        (("읽었다는 표시", "상대", "가지 않"), 1.0),
        (("read indicator", "other person", "hide"), 1.0),
    ],
    "contacts_sync_control": [
        (("주소록", "앱 서버", "맞추", "끄"), 1.0),
        (("contacts", "server", "sync", "off"), 1.0),
    ],
    "location_sharing_control": [
        (("가족", "실시간 위치", "중단"), 1.0),
        (("region", "location preference", "without changing"), 1.0),
    ],
    "personalization_control": [
        (("내 활동", "맞춤 추천", "광고", "제한"), 1.0),
        (("activity", "personalized", "ads", "limit"), 1.0),
    ],
    "tracking_control": [
        (("분석 목적", "행동", "기록", "제한"), 1.0),
        (("analytics", "behavior", "tracking", "limit"), 1.0),
    ],
    "consent_withdrawal": [
        (("optional data-sharing", "reviewed", "revoked"), 1.0),
        (("optional sharing", "final control", "revokes"), 1.0),
        (("선택", "정보 공유", "동의 철회"), 1.0),
    ],
    "privacy_policy_document": [
        (("회사", "개인정보", "다루", "문서"), 1.0),
        (("company", "personal information", "document"), 1.0),
    ],
    "data_download": [
        (("내 자료", "한 번에", "내려받을 파일"), 1.0),
        (("my data", "downloadable file", "request"), 1.0),
    ],
    "text_size": [
        (("글씨", "작", "크게"), 1.0),
        (("text", "too small", "larger"), 1.0),
    ],
    "high_contrast": [
        (("버튼 경계", "대비", "강"), 1.0),
        (("button edges", "contrast", "strong"), 1.0),
    ],
    "accessibility_captions": [
        (("자막 글씨", "노란색", "큰"), 1.0),
        (("captions", "yellow", "large"), 1.0),
    ],
    "accessibility_settings": [
        (("읽어 주기", "포커스 순서", "조절"), 1.0),
        (("screen reader", "focus order", "adjust"), 1.0),
    ],
    "support_faq": [
        (("상담 전", "자주 묻", "해결법"), 1.0),
        (("before contact", "frequent questions", "solution"), 1.0),
    ],
    "support_contact": [
        (("automated answers", "real support", "request"), 1.0),
        (("오류 내용", "개발팀", "보내"), 1.0),
        (("상담", "채팅 창", "안내"), 1.0),
    ],
    "medical_appointments": [
        (("medical appointment", "next week", "morning"), 1.0),
        (("진료 예약", "다음 주", "오전"), 1.0),
    ],
    "health_records": [
        (("건강검진", "결과표", "확인"), 1.0),
        (("health screening", "result", "record"), 1.0),
    ],
    "health_insurance_eligibility": [
        (("직장 건강보험", "자격", "유효"), 1.0),
        (("health insurance", "eligibility", "valid"), 1.0),
    ],
    "health_insurance_refund": [
        (("건강보험", "돌려받", "금액"), 1.0),
        (("health insurance", "refundable", "amount"), 1.0),
    ],
    "subscription_management": [
        (("결제 중", "이용권", "다음 결제일"), 1.0),
        (("current plan", "next billing date"), 1.0),
    ],
    "subscription_cancellation": [
        (("membership", "charging", "next month"), 1.0),
        (("멤버십 종료", "마지막 경고"), 1.0),
    ],
    "subscription_pause": [
        (("한 달", "이용권", "쉬"), 1.0),
        (("membership", "pause", "one month"), 1.0),
    ],
    "subscription_resume": [
        (("멈춰 둔", "멤버십", "다시 활성"), 1.0),
        (("paused membership", "reactivate"), 1.0),
    ],
    "automatic_renewal_control": [
        (("무료 체험", "유료 전환", "않"), 1.0),
        (("free trial", "paid", "not convert"), 1.0),
    ],
    "notification_control": [
        (("operational messages", "service", "switch"), 1.0),
        (("서비스 운영", "메시지", "제어"), 1.0),
    ],
    "marketing_notification_control": [
        (("광고성 메시지", "수신", "철회"), 1.0),
        (("promotional messages", "receive", "withdraw"), 1.0),
    ],
    "quiet_hours": [
        (("routine alerts", "every night", "eleven"), 1.0),
        (("매일 밤", "알림", "시간대"), 1.0),
    ],
    "refund": [
        (("refund", "last submission", "without activating"), 1.0),
        (("환불", "구매 건", "고르"), 1.0),
    ],
    "insurance_claim": [
        (("병원비", "실손", "접수"), 1.0),
        (("medical bill", "insurance", "claim"), 1.0),
    ],
    "insurance_claim_status": [
        (("insurance claim", "filed", "under review"), 1.0),
        (("보험금 청구", "처리 중", "확인"), 1.0),
    ],
    "insurance_roadside_assistance": [
        (("차", "멈", "긴급 견인"), 1.0),
        (("car stopped", "emergency towing"), 1.0),
    ],
    "insurance_accident_report": [
        (("insurer", "reporting", "car collision"), 1.0),
        (("보험사", "차 사고", "신고"), 1.0),
    ],
    "insurance_premium_payment": [
        (("밀린", "보험료", "납부"), 1.0),
        (("overdue", "insurance premium", "pay"), 1.0),
    ],
    "insurance_contract_change": [
        (("보험 계약", "납부 방법", "변경"), 1.0),
        (("insurance policy", "payment method", "change"), 1.0),
    ],
    "insurance_policy_terms": [
        (("coverage", "exclusions", "policy"), 1.0),
        (("보장 범위", "제외", "보험 약관"), 1.0),
    ],
    "insurance_contract_cancellation": [
        (("보험 계약", "해지 절차", "예상 환급액"), 1.0),
        (("insurance contract", "cancel", "estimated refund"), 1.0),
    ],
    "terms_document": [
        (("document", "rules", "using this service"), 1.0),
        (("서비스", "이용 규칙", "문서"), 1.0),
    ],
    "open_source_licenses": [
        (("외부 소프트웨어", "고지문", "앱"), 1.0),
        (("third-party software", "notices", "app"), 1.0),
    ],
    "address_management": [
        (("replace", "default parcel", "destination"), 1.0),
        (("기본 배송지", "교체"), 1.0),
    ],
    "reset_app_settings": [
        (("warning screen", "restores", "app preferences"), 1.0),
        (("앱 설정", "초기화", "경고"), 1.0),
    ],
    "storage_management": [
        (("temporary app files", "without removing"), 1.0),
        (("임시 앱 파일", "삭제 없이", "보기"), 1.0),
    ],
}


# Recovery wording adds transient UI state (offline, dialog, WebView, disabled
# controls) around the underlying purpose.  These rules anchor the enduring
# purpose while treating the transient state as supporting context.  They also
# cover a few morphology variants that are intentionally absent from the
# canonical menu-label patterns above.
RECOVERY_AND_EDGE_GOAL_RULES: dict[str, list[tuple[tuple[str, ...], float]]] = {
    "password_change": [
        (("비밀번호", "바꾸", "세션", "끝"), 1.0),
        (("change password", "session expired"), 1.0),
    ],
    "account_deletion": [
        (("업무용 계정", "탈퇴"), 1.0),
        (("계정 탈퇴", "마지막 확인", "삭제", "누르지"), 1.0),
    ],
    "two_factor_verification": [
        (("인증 앱 코드", "오류", "문자 인증"), 1.0),
        (("authenticator code", "error", "sms"), 1.0),
    ],
    "email_registration": [
        (("소셜 계정", "말고", "이메일", "가입"), 1.0),
        (("instead of social", "email", "sign up"), 1.0),
    ],
    "password_reset": [
        (("로그인 시도", "잠긴 계정", "복구"), 1.0),
        (("locked account", "recover", "login attempts"), 1.0),
    ],
    "account_login": [
        (("게스트", "내 계정", "이어", "저장"), 1.0),
        (("로그인", "사람인지 확인", "화면"), 1.0),
        (("guest", "continue", "my account"), 1.0),
    ],
    "biometric_login_settings": [
        (("지문 로그인", "기기", "사용할 수 없"), 1.0),
        (("fingerprint login", "device", "unavailable"), 1.0),
    ],
    "subscription_management": [
        (("오프라인", "이용권 관리"), 1.0),
        (("offline", "subscription management"), 1.0),
    ],
    "refund_status": [
        (("환불", "어디까지", "처리", "로딩"), 1.0),
        (("refund", "processing", "loading"), 1.0),
    ],
    "order_tracking": [
        (("배송 위치", "서버 오류"), 1.0),
        (("delivery location", "server error"), 1.0),
    ],
    "privacy_policy_document": [
        (("개인정보 처리방침", "연결 경고"), 1.0),
        (("privacy policy", "connection warning"), 1.0),
        (("쿠키 동의창", "개인정보 안내문"), 1.0),
    ],
    "subscription_cancellation": [
        (("해지 링크", "존재하지 않는 페이지"), 1.0),
        (("faq", "해지 메뉴", "돌아가"), 1.0),
        (("해지 버튼", "회색", "결제처"), 1.0),
        (("다음 결제 전", "구독 해지", "확인 단계", "마지막 선택"), 1.0),
    ],
    "data_download": [
        (("내 데이터 내려받기", "와이파이 로그인"), 1.0),
        (("data export", "browser download", "storage prompt"), 1.0),
    ],
    "notification_control": [
        (("알림 설정", "예전 값", "현재 설정"), 1.0),
        (("영상 피드", "넘기지", "알림 설정"), 1.0),
        (("프로필 편집", "저장하지", "알림 설정"), 1.0),
    ],
    "support_contact": [
        (("메시지", "아니라", "상담원", "실시간"), 1.0),
        (("상담 연결", "다시 시도"), 1.0),
        (("support connection", "try again"), 1.0),
    ],
    "android_change_permission": [
        (("사진", "찍을 때만", "카메라", "허용"), 1.0),
        (("대략적인 위치", "이 앱", "제공"), 1.0),
    ],
    "android_enable_overlay": [
        (("다른 앱 위", "안내 아이콘", "띄"), 1.0),
        (("guidance icon", "over other apps"), 1.0),
    ],
    "android_clear_app_cache": [
        (("로그인", "유지", "임시 캐시", "비우"), 1.0),
        (("keep login", "temporary cache", "clear"), 1.0),
    ],
    "android_default_apps": [
        (("링크", "기본 브라우저", "시스템 화면"), 1.0),
        (("links", "default browser", "system screen"), 1.0),
    ],
    "android_special_access": [
        (("외부 apk", "설치", "허용"), 1.0),
        (("external apk", "installation", "allow"), 1.0),
    ],
    "language_change": [
        (("뉴스 목록", "앱 언어 설정"), 1.0),
        (("news list", "app language"), 1.0),
    ],
    "accessibility_settings": [
        (("목록 아래쪽", "접근성 메뉴"), 1.0),
        (("below", "accessibility menu"), 1.0),
    ],
    "saved_content": [
        (("추천 목록", "아니라", "저장", "콘텐츠"), 1.0),
        (("not recommendations", "saved content"), 1.0),
    ],
    "onboarding_permission_setup": [
        (("처음 설정", "권한 설명", "시스템 권한"), 1.0),
        (("initial setup", "permission rationale", "system permission"), 1.0),
    ],
    "playback_settings": [
        (("속도 선택창", "닫", "재생 설정"), 1.0),
        (("speed dialog", "close", "playback settings"), 1.0),
    ],
    "delete_content": [
        (("글 삭제", "확인창", "내가 결정"), 1.0),
        (("사진", "지우는 메뉴", "이름 없는 아이콘"), 1.0),
    ],
    "appearance_change": [
        (("글씨 색", "테마", "설정"), 1.0),
        (("text color", "theme", "settings"), 1.0),
    ],
    "mute_conversation": [
        (("대화방", "알림만", "잠시 끄"), 1.0),
        (("conversation", "notification", "temporarily off"), 1.0),
    ],
    "account_registration": [
        (("가입 버튼", "비활성", "더 입력"), 1.0),
        (("sign-up button", "disabled", "missing input"), 1.0),
    ],
    "signup_optional_consent": [
        (("가입 중", "선택 마케팅 동의", "켜졌"), 1.0),
        (("optional marketing consent", "already on"), 1.0),
    ],
    "search_files": [
        (("tax statement", "every folder"), 1.0),
        (("세금 명세서", "모든 폴더"), 1.0),
    ],
    "billing_receipt": [
        (("receipt page", "redirecting", "billing"), 1.0),
        (("영수증 화면", "리디렉션", "결제"), 1.0),
    ],
    "payment_method_change": [
        (("payment-method", "not", "confirm", "charge"), 1.0),
        (("결제 수단", "청구", "확정하지"), 1.0),
    ],
    "upload_file": [
        (("claim document", "phone", "every file"), 1.0),
        (("청구 문서", "휴대폰", "모든 파일 권한"), 1.0),
    ],
    "linked_accounts": [
        (("linked-account", "third-party cookies", "native"), 1.0),
        (("연결 계정", "서드파티 쿠키", "앱 화면"), 1.0),
    ],
    "refund": [
        (("final refund review", "leave submission"), 1.0),
        (("환불 최종 검토", "제출하지"), 1.0),
    ],
    "money_transfer": [
        (("transfer review", "never send", "money"), 1.0),
        (("이체 검토", "자동 송금", "금지"), 1.0),
    ],
    "order_return": [
        (("delivered item", "not match", "send it back"), 1.0),
    ],
    "android_uninstall_app": [
        (("사용하지", "게임", "제거하기", "직전"), 1.0),
    ],
    "reset_app_settings": [
        (("warning screen", "restores", "preferences"), 1.0),
    ],
    "social_registration": [
        (("creating", "account", "apple identity"), 1.0),
    ],
}


# One broad intent may contain several safe stopping points.  The intent stays
# stable for analytics and graph reuse, while the matched semantic rule selects
# the precise destination.  This prevents, for example, a final refund review
# from being flattened to the generic refund entry screen.
GOAL_TERMINAL_OVERRIDES: dict[str, dict[tuple[str, ...], str]] = {
    "subscription_management": {
        ("채널", "새", "영상", "모음"): "content.subscriptions",
    },
    "account_registration": {
        ("신규", "계정", "처음", "암호"): "auth.password.create",
        ("age declaration", "account creation"): "consent.age",
        ("미성년", "보호자", "가입"): "consent.parental",
        ("optional", "topics", "first-time setup"): "onboarding.interests",
        ("새 계정", "확정", "마지막 버튼"): "auth.signup.confirm",
        ("initial account setup", "finished", "summary"): "onboarding.complete",
        ("가입 버튼", "비활성", "더 입력"): "consent.required",
    },
    "browse_files": {
        ("선택", "문서", "휴지통"): "files.trash",
    },
    "support_contact": {
        ("메시지", "아니라", "상담원", "실시간"): "support.chat",
        ("상담원", "실시간", "이야기"): "support.chat",
        ("앱", "오류", "운영팀", "문의"): "support.contact",
        ("automated answers", "real support", "request"): "support.contact",
        ("오류 내용", "개발팀", "보내"): "support.report",
        ("상담", "채팅 창", "안내"): "support.chat",
    },
    "two_factor_verification": {
        ("another", "verification step", "signs in"): "security.two_factor",
    },
    "create_content": {
        ("사진", "짧은 글", "새 게시물"): "content.upload",
    },
    "travel_bookings": {
        ("예약번호 없이", "다음 비행", "일정"): "travel.booking.detail",
    },
    "account_deletion": {
        ("계정", "마지막 경고", "멈"): "account.delete.confirm",
        ("계정 탈퇴", "마지막 확인", "삭제", "누르지"): "account.delete.confirm",
    },
    "subscription_cancellation": {
        ("멤버십 종료", "마지막 경고"): "subscription.cancel.confirm",
        ("다음 결제 전", "구독 해지", "확인 단계", "마지막 선택"): "subscription.cancel.confirm",
    },
    "notification_control": {
        ("operational messages", "service", "switch"): "notification.service",
    },
    "marketing_notification_control": {
        ("광고성 메시지", "수신", "철회"): "marketing.opt_out",
    },
    "consent_withdrawal": {
        ("optional sharing", "final control", "revokes"): "privacy.consent.withdraw",
    },
    "refund": {
        ("환불", "구매 건", "고르"): "refund.order_select",
        ("refund", "last submission", "without activating"): "refund.confirm",
        ("final refund review", "leave submission"): "refund.confirm",
    },
    "onboarding_permission_setup": {
        ("가입 중", "기기 권한", "시스템"): "system.permission",
    },
    "active_sessions": {
        ("devices", "currently", "account"): "account.devices",
    },
    "password_reset": {
        ("로그인할 수 없", "계정", "되찾"): "account.recovery",
    },
    "location_sharing_control": {
        ("region", "location preference", "without changing"): "settings.location",
    },
    "order_cancellation": {
        ("주문 취소", "마지막 버튼", "앞"): "order.cancel.confirm",
    },
    "storage_management": {
        ("temporary app files", "without removing"): "system.cache",
    },
    "order_return": {
        ("반품", "마지막 확인", "멈"): "order.return.confirm",
    },
    "account_login": {
        ("로그인", "사람인지 확인", "화면"): "auth.verification",
    },
}


FUNCTIONS: list[dict[str, object]] = [
    # Android system navigation is separate from in-app settings.  Hubs are
    # safe to navigate; all toggles and destructive actions stop for the user.
    function("android.settings.root", "android_system", "Android 설정", "Android Settings", "설정 앱|휴대전화 설정|기기 설정|시스템 설정", "Android settings|Phone settings|Device settings|System settings", "Android|휴대전화|기기", "앱 내부 설정|프로필 설정", terminal=False, scope="android_system", node_kind="hub", tags="settings"),
    function("android.apps.list", "android_system", "앱 목록", "Apps list", "앱|애플리케이션|앱 목록|앱 관리|모든 앱 보기", "Apps|Applications|App list|App management|See all apps", "설치된 앱|기본 앱|권한 관리자", "앱 마켓|추천 앱|콘텐츠 앱", terminal=False, scope="android_system", node_kind="hub", tags="apps_list"),
    function("android.app.info", "android_system", "앱 정보", "App info", "앱 정보|애플리케이션 정보|앱 세부정보|이 앱 정보", "App info|Application info|App details|About this app", "권한|알림|저장공간|배터리|기본으로 열기", "버전 정보|오픈소스|서비스 소개", terminal=False, scope="android_system", node_kind="hub", tags="app_info"),
    function("android.app.notifications", "android_system", "앱 알림", "App notifications", "앱 알림|이 앱의 알림|알림 허용|알림 관리", "App notifications|Notifications for this app|Allow notifications|Manage notifications", "알림 카테고리|배지|잠금 화면", "이메일 알림|마케팅 알림|문자 알림", scope="android_system", state_cues=ON_OFF, tags="notifications"),
    function("android.notification.channels", "android_system", "알림 카테고리", "Notification categories", "알림 카테고리|알림 채널|알림 유형|카테고리별 알림", "Notification categories|Notification channels|Notification types|Categories", "소리|진동|무음|배지", "이메일 수신|뉴스레터|메시지함", scope="android_system", state_cues=ON_OFF, tags="notifications"),
    function("android.permission.manager", "android_system", "권한 관리자", "Permission manager", "권한 관리자|개인정보 권한|권한 사용 현황|앱 권한 관리", "Permission manager|Privacy permissions|Permission usage|Manage app permissions", "카메라|마이크|위치|연락처", "약관 동의|마케팅 수신 동의", terminal=False, scope="android_system", node_kind="hub", tags="permissions"),
    function("android.permission.manage", "android_system", "앱 권한", "App permissions", "권한|앱 권한|이 앱의 권한|권한 관리", "Permissions|App permissions|Permissions for this app|Manage permissions", "허용됨|허용되지 않음|사용 중에만", "필수 약관|선택 동의|쿠키 동의", scope="android_system", state_cues=ON_OFF, tags="permissions"),
    function("android.permission.change", "android_system", "앱 권한 변경", "Change app permission", "권한 허용|권한 거부|허용 안 함|사용 중에만 허용|매번 묻기", "Allow permission|Deny permission|Don't allow|Allow only while using|Ask every time", "카메라|마이크|위치|사진|연락처", "약관 동의|마케팅 동의", risk="high", policy="never_auto", changing=True, scope="android_system", node_kind="state_change", stop_policy="stop_before_action", state_cues=ON_OFF, risk_cues={"sensitive_access": ["카메라", "마이크", "위치", "Camera", "Microphone", "Location"]}, tags="permissions"),
    function("android.permission.special_access", "android_system", "특별한 앱 접근", "Special app access", "특별한 앱 접근|특수 접근|기타 권한|특별 접근", "Special app access|Special access|Advanced permissions|Special permissions", "다른 앱 위에 표시|사용 정보 접근|알 수 없는 앱", "일반 권한|약관 동의", terminal=False, scope="android_system", node_kind="hub", tags="special_access"),
    function("android.permission.accessibility_service", "android_system", "접근성 서비스", "Accessibility service", "설치된 앱|접근성 서비스|설치된 서비스|접근성 앱", "Installed apps|Accessibility service|Downloaded apps|Accessibility apps", "접근성 설정|서비스 사용|전체 제어", "글자 크기|자막|색상 보정", risk="high", policy="never_auto", changing=True, scope="android_system", node_kind="state_change", stop_policy="before_action", state_cues=ON_OFF, risk_cues={"sensitive_access": ["화면 보기", "동작 수행", "view and control screen", "perform actions"]}, tags="accessibility_service"),
    function("android.permission.overlay", "android_system", "다른 앱 위에 표시", "Display over other apps", "다른 앱 위에 표시|다른 앱 위에 그리기|화면 오버레이|플로팅 창 권한", "Display over other apps|Draw over other apps|Screen overlay|Appear on top", "허용|다른 앱 사용 중", "화면 테마|팝업 알림", risk="high", policy="never_auto", changing=True, scope="android_system", node_kind="state_change", stop_policy="before_action", state_cues=ON_OFF, risk_cues={"sensitive_access": ["다른 앱 위", "on top of other apps"]}, tags="overlay_permission"),
    function("android.permission.notification_access", "android_system", "알림 접근", "Notification access", "알림 접근|알림 읽기 권한|기기 및 앱 알림|알림 리스너", "Notification access|Read notifications|Device and app notifications|Notification listener", "모든 알림 읽기|알림 제어", "앱 알림 켜기|알림 카테고리", risk="high", policy="never_auto", changing=True, scope="android_system", node_kind="state_change", stop_policy="before_action", state_cues=ON_OFF, risk_cues={"sensitive_access": ["알림 읽기", "개인정보", "read all notifications", "personal information"]}, tags="notification_access"),
    function("android.app.battery", "android_system", "앱 배터리 사용량", "App battery usage", "앱 배터리 사용량|배터리|배터리 사용|백그라운드 배터리", "App battery usage|Battery|Battery usage|Background battery", "최적화|제한됨|제한 없음", "배터리 잔량|절전 모드 전체", scope="android_system", state_cues={"selected": ["최적화됨", "제한됨", "제한 없음", "Optimized", "Restricted", "Unrestricted"]}, tags="battery"),
    function("android.app.background_usage", "android_system", "백그라운드 사용", "Background usage", "백그라운드 사용|백그라운드 활동|백그라운드 실행 허용|배터리 최적화", "Background usage|Background activity|Allow background activity|Battery optimization", "최적화됨|제한됨|제한 없음", "모바일 데이터|저장공간", risk="high", policy="never_auto", changing=True, scope="android_system", node_kind="state_change", stop_policy="before_action", state_cues=ON_OFF, tags="battery"),
    function("android.app.storage_cache", "android_system", "저장공간 및 캐시", "Storage and cache", "저장공간 및 캐시|저장공간|스토리지와 캐시|앱 저장공간", "Storage & cache|Storage and cache|App storage|Storage", "사용자 데이터|캐시|공간 사용", "클라우드 저장공간|다운로드 설정", scope="android_system", tags="storage"),
    function("android.app.clear_cache", "android_system", "캐시 삭제", "Clear cache", "캐시 삭제|캐시 지우기|임시 파일 삭제|캐시 비우기", "Clear cache|Delete cache|Remove temporary files|Empty cache", "임시 데이터|앱이 느림|공간 확보", "저장공간 삭제|모든 데이터 삭제|계정 삭제", risk="high", policy="never_auto", changing=True, scope="local_app_cache", node_kind="destructive_action", stop_policy="before_action", risk_cues={"scope": ["캐시", "임시 파일", "cache", "temporary files"]}, tags="clear_cache"),
    function("android.app.clear_storage", "android_system", "앱 저장공간 삭제", "Clear app storage", "저장공간 삭제|데이터 삭제|모든 데이터 삭제|앱 데이터 지우기", "Clear storage|Clear data|Clear all data|Erase app data", "계정 설정 파일|앱 초기화|영구 삭제", "캐시 삭제|임시 파일|다운로드만 삭제", risk="high", policy="never_auto", changing=True, scope="local_app_data", node_kind="destructive_action", stop_policy="before_action", risk_cues=DESTRUCTIVE_RISK, tags="clear_storage"),
    function("android.app.data_usage", "android_system", "모바일 데이터 및 Wi-Fi", "Mobile data and Wi-Fi", "모바일 데이터 및 Wi-Fi|데이터 사용량|모바일 데이터|네트워크 사용", "Mobile data & Wi-Fi|Data usage|Mobile data|Network usage", "백그라운드 데이터|무제한 데이터", "앱 내부 데이터 절약|다운로드 품질", scope="android_system", tags="data_usage"),
    function("android.app.background_data", "android_system", "백그라운드 데이터", "Background data", "백그라운드 데이터|데이터 사용 허용|무제한 데이터 사용|데이터 절약 예외", "Background data|Allow data usage|Unrestricted data usage|Data Saver exception", "모바일 데이터|Wi-Fi|데이터 절약", "배터리 백그라운드|다운로드 설정", risk="high", policy="never_auto", changing=True, scope="android_system", node_kind="state_change", stop_policy="before_action", state_cues=ON_OFF, tags="data_usage"),
    function("android.defaults.apps", "android_system", "기본 앱", "Default apps", "기본 앱|기본 애플리케이션|기본으로 사용할 앱|앱 기본값", "Default apps|Default applications|Choose default apps|App defaults", "브라우저 앱|전화 앱|SMS 앱|링크 열기", "앱 초기화|설정 초기화", terminal=False, scope="android_system", node_kind="hub", tags="defaults"),
    function("android.app.open_by_default", "android_system", "기본으로 열기", "Open by default", "기본으로 열기|지원 링크 열기|기본 링크|링크 처리", "Open by default|Open supported links|Supported links|Link handling", "지원되는 웹 주소|항상 열기", "브라우저 안에서 열기|새 창", scope="android_system", tags="defaults"),
    function("android.app.clear_defaults", "android_system", "기본 설정 삭제", "Clear defaults", "기본 설정 삭제|기본값 지우기|기본 연결 해제|기본 앱 해제", "Clear defaults|Clear default preferences|Remove defaults|Reset app defaults", "기본으로 열기|지원 링크", "모든 설정 초기화|데이터 삭제", risk="high", policy="never_auto", changing=True, scope="android_system", node_kind="state_change", stop_policy="before_action", tags="defaults"),
    function("android.app.uninstall", "android_system", "앱 제거", "Uninstall app", "제거|앱 제거|애플리케이션 삭제|설치 삭제", "Uninstall|Uninstall app|Remove application|Delete app", "앱과 데이터 제거|업데이트 제거", "계정 삭제|캐시 삭제|홈 화면에서 제거", risk="high", policy="never_auto", changing=True, scope="installed_app", node_kind="destructive_action", stop_policy="before_action", risk_cues=DESTRUCTIVE_RISK, tags="uninstall"),
    function("android.app.force_stop", "android_system", "강제 종료", "Force stop", "강제 종료|강제 중지|앱 중지|실행 종료", "Force stop|Force close|Stop app|End app", "앱이 오작동|다시 실행 전까지", "로그아웃|구독 중지|재생 중지", risk="high", policy="never_auto", changing=True, scope="running_app", node_kind="destructive_action", stop_policy="before_action", risk_cues={"consequence": ["앱이 제대로 작동하지 않을 수 있음", "app may misbehave"]}, tags="force_stop"),
]


INTENTS: list[dict[str, object]] = [
    intent("android_open_settings", "android.settings.root", "휴대전화 설정 열기|기기 설정으로 가기|Android 설정 열어줘|open phone settings|open Android settings", "android.settings.root:1.0", rules="설정+휴대전화|settings+phone"),
    intent("android_manage_apps", "android.apps.list", "설치된 앱 목록|앱 관리로 가기|모든 앱 보기|manage installed apps|see all apps", "android.settings.root:0.55|android.apps.list:1.0", rules="앱+목록|installed+apps"),
    intent("android_app_info", "android.app.info", "이 앱 정보 열기|애플리케이션 정보|앱 세부정보 보기|open app info|show application details", "android.settings.root:0.45|android.apps.list:0.7|android.app.info:1.0", rules="앱+정보|app+info", avoid="system.app_info"),
    intent("android_app_notifications", "android.app.notifications", "이 앱 알림 설정|앱 알림 관리|앱별 알림 켜기|manage this app notifications|app notification settings", "android.settings.root:0.42|android.apps.list:0.56|android.app.info:0.72|android.app.notifications:1.0", rules="앱+알림|app+notifications", avoid="notification.settings"),
    intent("android_notification_categories", "android.notification.channels", "알림 카테고리 설정|알림 채널별로 바꾸기|앱 알림 유형 관리|manage notification categories|notification channels", "android.settings.root:0.36|android.apps.list:0.5|android.app.info:0.68|android.app.notifications:0.84|android.notification.channels:1.0", rules="알림+카테고리|notification+channels"),
    intent("android_permission_manager", "android.permission.manager", "권한 관리자 열기|어떤 앱이 권한 쓰는지|앱 권한 전체 관리|open permission manager|manage app permissions", "android.settings.root:0.55|android.permission.manager:1.0", rules="권한+관리자|permission+manager", avoid="privacy.consent"),
    intent("android_app_permissions", "android.permission.manage", "이 앱 권한 보기|앱 권한 관리|카메라 마이크 권한 확인|view this app permissions|manage app permissions for this app", "android.settings.root:0.4|android.apps.list:0.55|android.app.info:0.76|android.permission.manage:1.0", rules="앱+권한|app+permissions", avoid="consent.required|consent.optional"),
    intent("android_change_permission", "android.permission.change", "이 앱 위치 권한 바꾸기|카메라 권한 허용하기|마이크 권한 끄기|change app permission|allow camera permission|deny location permission", "android.settings.root:0.34|android.apps.list:0.46|android.app.info:0.62|android.permission.manage:0.84|android.permission.change:1.0", rules="권한+바꾸|permission+change", avoid="consent.required|consent.optional", desired_state="user_confirmation_required"),
    intent("android_special_access", "android.permission.special_access", "특별한 앱 접근 열기|특수 권한 관리|고급 앱 권한|open special app access|manage special permissions", "android.settings.root:0.52|android.apps.list:0.62|android.permission.special_access:1.0", rules="특별+접근|special+access"),
    intent("android_enable_accessibility_service", "android.permission.accessibility_service", "접근성 서비스 켜기|설치된 접근성 앱 허용|ExitGuide 접근성 권한|enable accessibility service|allow accessibility app", "android.settings.root:0.38|settings.accessibility:0.58|android.permission.accessibility_service:1.0", rules="접근성+서비스|accessibility+service", desired_state="user_confirmation_required"),
    intent("android_enable_overlay", "android.permission.overlay", "다른 앱 위에 표시 허용|플로팅 창 권한 켜기|오버레이 권한|allow display over other apps|enable overlay permission", "android.settings.root:0.38|android.apps.list:0.44|android.permission.special_access:0.72|android.permission.overlay:1.0", rules="다른+앱+표시|overlay+permission", desired_state="user_confirmation_required"),
    intent("android_notification_access", "android.permission.notification_access", "알림 접근 권한 설정|알림 읽기 권한 켜기|알림 리스너 허용|manage notification access|enable notification listener", "android.settings.root:0.38|android.permission.special_access:0.7|android.permission.notification_access:1.0", rules="알림+접근|notification+access", desired_state="user_confirmation_required"),
    intent("android_app_battery", "android.app.battery", "이 앱 배터리 설정|앱 배터리 사용량|배터리 최적화 설정|app battery usage|battery optimization for this app", "android.settings.root:0.36|android.apps.list:0.5|android.app.info:0.72|android.app.battery:1.0", rules="앱+배터리|app+battery"),
    intent("android_background_usage", "android.app.background_usage", "백그라운드 실행 허용|이 앱 배터리 제한 해제|백그라운드 활동 끄기|allow background usage|restrict background activity", "android.settings.root:0.32|android.apps.list:0.46|android.app.info:0.64|android.app.battery:0.82|android.app.background_usage:1.0", rules="백그라운드+사용|background+usage", desired_state="user_confirmation_required"),
    intent("android_storage_cache", "android.app.storage_cache", "앱 저장공간 보기|저장공간 및 캐시|이 앱 용량 확인|view app storage and cache|app storage usage", "android.settings.root:0.34|android.apps.list:0.48|android.app.info:0.7|android.app.storage_cache:1.0", rules="저장공간+캐시|storage+cache"),
    intent("android_clear_app_cache", "android.app.clear_cache", "이 앱 캐시 지우기|캐시만 삭제|임시 파일 비우기|clear this app cache|delete cached files", "android.settings.root:0.3|android.apps.list:0.44|android.app.info:0.62|android.app.storage_cache:0.84|android.app.clear_cache:1.0", rules="캐시+지우|clear+cache", avoid="android.app.clear_storage|privacy.delete_data|account.delete.entry", desired_state="user_confirmation_required"),
    intent("android_clear_app_storage", "android.app.clear_storage", "이 앱 모든 데이터 삭제|앱 저장공간 지우기|앱을 초기 상태로 만들기|clear all app data|clear app storage", "android.settings.root:0.28|android.apps.list:0.4|android.app.info:0.58|android.app.storage_cache:0.8|android.app.clear_storage:1.0", rules="앱+데이터+삭제|clear+app+data", avoid="android.app.clear_cache|privacy.delete_data|account.delete.entry", desired_state="user_confirmation_required"),
    intent("android_app_data_usage", "android.app.data_usage", "이 앱 데이터 사용량|모바일 데이터 설정|앱 네트워크 사용 보기|view app data usage|mobile data settings for app", "android.settings.root:0.34|android.apps.list:0.48|android.app.info:0.68|android.app.data_usage:1.0", rules="앱+데이터+사용량|app+data+usage"),
    intent("android_background_data", "android.app.background_data", "백그라운드 데이터 끄기|데이터 절약 예외 허용|앱의 모바일 데이터 제한|disable background data|allow unrestricted data", "android.settings.root:0.3|android.apps.list:0.42|android.app.info:0.6|android.app.data_usage:0.82|android.app.background_data:1.0", rules="백그라운드+데이터|background+data", desired_state="user_confirmation_required"),
    intent("android_default_apps", "android.defaults.apps", "기본 앱 설정|기본 브라우저 바꾸기|기본 애플리케이션|manage default apps|change default browser", "android.settings.root:0.55|android.defaults.apps:1.0", rules="기본+앱|default+apps"),
    intent("android_open_by_default", "android.app.open_by_default", "이 앱 링크 기본으로 열기|지원 링크 설정|링크 연결 앱 바꾸기|open links by default|manage supported links", "android.settings.root:0.32|android.apps.list:0.45|android.app.info:0.64|android.app.open_by_default:1.0", rules="기본+열기|open+default"),
    intent("android_clear_defaults", "android.app.clear_defaults", "이 앱 기본값 지우기|기본 연결 해제|기본 앱 설정 삭제|clear app defaults|remove default preferences", "android.settings.root:0.28|android.apps.list:0.4|android.app.info:0.58|android.app.open_by_default:0.8|android.app.clear_defaults:1.0", rules="기본값+지우|clear+defaults", avoid="system.defaults|android.app.clear_storage", desired_state="user_confirmation_required"),
    intent("android_uninstall_app", "android.app.uninstall", "이 앱 제거|애플리케이션 삭제|앱 설치 삭제|uninstall this app|remove application", "android.settings.root:0.26|android.apps.list:0.4|android.app.info:0.66|android.app.uninstall:1.0", rules="앱+제거|uninstall+app", avoid="account.delete.entry|content.delete.entry", desired_state="user_confirmation_required"),
    intent("android_force_stop_app", "android.app.force_stop", "앱 강제 종료|실행 중인 앱 강제 중지|앱을 완전히 멈추기|force stop this app|force close application", "android.settings.root:0.26|android.apps.list:0.4|android.app.info:0.66|android.app.force_stop:1.0", rules="앱+강제+종료|force+stop+app", avoid="auth.logout|subscription.pause", desired_state="user_confirmation_required"),
]


FUNCTIONS.extend(
    [
        # Account/profile and security destinations shared by social, finance,
        # commerce, travel and productivity applications.
        function("account.profile.edit", "account", "프로필 수정", "Edit profile", "프로필 수정|내 정보 수정|프로필 편집|기본 정보 변경|회원정보 수정", "Edit profile|Edit personal details|Update profile|Change account details|Personal details", "이름|소개|생년월일|저장", "프로필 보기|계정 삭제|로그아웃", tags="profile_edit"),
        function("account.email.change", "account", "이메일 변경", "Change email", "이메일 변경|이메일 주소 수정|로그인 이메일 바꾸기|새 이메일 등록", "Change email|Update email address|Edit login email|New email address", "현재 이메일|새 이메일|이메일 인증", "이메일 알림|뉴스레터|이메일 회원가입", risk="medium", policy="never_auto", scope="account_identity", tags="email_change"),
        function("account.phone.change", "account", "휴대폰 번호 변경", "Change phone number", "휴대폰 번호 변경|전화번호 수정|연락처 번호 바꾸기|새 번호 등록", "Change phone number|Update mobile number|Edit contact number|New phone number", "현재 번호|새 번호|문자 인증", "SMS 알림|연락처 동기화|전화 걸기", risk="medium", policy="never_auto", scope="account_identity", tags="phone_change"),
        function("account.username.change", "account", "사용자 이름 변경", "Change username", "사용자 이름 변경|아이디 변경|닉네임 수정|핸들 바꾸기", "Change username|Edit user ID|Update nickname|Change handle", "현재 사용자 이름|사용 가능 여부|표시 이름", "비밀번호|계정 전환|로그인", risk="medium", policy="never_auto", scope="account_identity", tags="username_change"),
        function("account.avatar.change", "account", "프로필 사진 변경", "Change profile photo", "프로필 사진 변경|사진 수정|아바타 바꾸기|프로필 이미지 편집", "Change profile photo|Edit profile picture|Update avatar|Profile image", "카메라|갤러리|사진 선택", "배경화면|테마|게시물 사진", risk="medium", policy="never_auto", scope="account_profile", tags="avatar_change"),
        function("account.add", "account", "계정 추가", "Add account", "계정 추가|다른 계정 추가|새 계정 연결|계정 하나 더", "Add account|Add another account|Connect another account|New account", "계정 전환|로그인|프로필", "회원가입 완료|연결 계정 해제", tags="add_account"),
        function("security.password.reset", "security", "비밀번호 재설정", "Reset password", "비밀번호 재설정|비밀번호 찾기|암호를 잊음|새 비밀번호 받기", "Reset password|Forgot password|Recover password|Create new password", "인증 코드|이메일 링크|새 비밀번호", "비밀번호 변경 완료|로그인 비밀번호 입력", risk="medium", policy="never_auto", scope="credential", tags="password_reset"),
        function("security.passkey", "security", "패스키 관리", "Manage passkeys", "패스키|패스키 관리|패스키 추가|패스키 삭제", "Passkeys|Manage passkeys|Add passkey|Remove passkey", "생체 인증|보안 키|로그인 방법", "비밀번호 만들기|PIN 변경", risk="medium", policy="never_auto", scope="credential", tags="passkey"),
        function("security.biometric", "security", "생체 인증 설정", "Biometric authentication", "생체 인증|지문 로그인|얼굴 인식 로그인|생체 로그인", "Biometric authentication|Fingerprint sign-in|Face sign-in|Biometric login", "지문|얼굴|기기 잠금", "프로필 사진|카메라 권한", risk="medium", policy="never_auto", scope="credential", state_cues=ON_OFF, tags="biometric"),
        function("security.login_history", "security", "로그인 기록", "Login history", "로그인 기록|접속 기록|로그인 활동|최근 로그인", "Login history|Sign-in activity|Login activity|Recent sign-ins", "기기|위치|시간|세션", "이용 기록|시청 기록|구매 내역", tags="login_history"),

        # Common shopping and order flows.  Entry destinations are navigable;
        # submission and irreversible confirmation stay user-controlled.
        function("commerce.cart", "commerce", "장바구니", "Shopping cart", "장바구니|카트|쇼핑백|담은 상품", "Cart|Shopping cart|Bag|Basket|Items in cart", "상품|수량|결제하기", "저장한 항목|주문 내역|보관함", tags="cart"),
        function("commerce.wishlist", "commerce", "찜·위시리스트", "Wishlist", "찜|찜한 상품|위시리스트|관심 상품|좋아요한 상품", "Wishlist|Saved items|Favorites|Liked products|Wish list", "상품|저장됨|가격", "차단 목록|저장된 게시물|재생목록", tags="wishlist"),
        function("order.tracking", "commerce", "배송 조회", "Track order", "배송 조회|주문 추적|배송 현황|택배 위치|배달 상태", "Track order|Order tracking|Delivery status|Track package|Shipment status", "배송 중|도착 예정|운송장", "위치 공유|항공편 상태|라이브 방송", tags="order_tracking"),
        function("order.return.entry", "commerce", "반품 신청 진입", "Return order entry", "반품 신청|상품 반품|반품하기|반품 접수", "Return item|Start a return|Return order|Request return", "반품 사유|수거 방법|환불 수단", "주문 취소|교환 신청|계정 삭제", risk="medium", policy="never_auto", scope="order", node_kind="action_entry", stop_policy="on_destination_screen", tags="return"),
        function("order.return.confirm", "commerce", "반품 최종 제출", "Confirm return", "반품 신청 완료|반품 제출|반품 확정|반품 요청 보내기", "Confirm return|Submit return|Complete return request|Send return request", "환불 예정|수거 주소|최종 확인", "돌아가기|계속 쇼핑|반품 안내", risk="high", policy="never_auto", changing=True, scope="order", node_kind="destructive_action", stop_policy="before_action", risk_cues={"external_submission": ["신청", "제출", "submit", "request"]}, tags="return_confirm"),
        function("order.exchange.entry", "commerce", "교환 신청 진입", "Exchange order entry", "교환 신청|상품 교환|교환하기|교환 접수", "Exchange item|Start an exchange|Exchange order|Request exchange", "교환 사유|교환 옵션|수거 방법", "반품 신청|주문 취소|새로 구매", risk="medium", policy="never_auto", scope="order", node_kind="action_entry", stop_policy="on_destination_screen", tags="exchange"),

        # Messaging patterns deliberately distinguish content feeds from
        # conversation-level actions and account-level privacy controls.
        function("communication.inbox", "communication", "메시지함", "Inbox", "메시지|메시지함|받은 메시지|채팅 목록|대화 목록", "Messages|Inbox|Chats|Conversations|Direct messages", "안 읽음|새 메시지|대화", "알림 메시지|이메일 수신함|고객센터 채팅", tags="inbox"),
        function("communication.compose", "communication", "새 메시지 작성", "Compose message", "새 메시지|메시지 보내기|대화 시작|채팅 작성", "New message|Compose|Send a message|Start chat|Create conversation", "받는 사람|내용 입력|전송", "게시물 작성|고객센터 문의", risk="medium", policy="never_auto", scope="communication", tags="compose_message"),
        function("communication.conversation.search", "communication", "대화 검색", "Search conversations", "대화 검색|메시지 검색|채팅에서 찾기|메시지 내용 찾기", "Search conversations|Search messages|Find in chat|Conversation search", "검색어|대화 내용|결과", "앱 전체 검색|연락처 검색", tags="conversation_search"),
        function("communication.conversation.mute", "communication", "대화 알림 끄기", "Mute conversation", "대화 알림 끄기|채팅방 알림 끄기|대화 음소거|메시지 알림 숨기기", "Mute conversation|Mute chat|Turn off chat notifications|Silence messages", "기간|알림|음소거", "앱 전체 알림 끄기|사용자 차단|통화 음소거", risk="medium", policy="never_auto", scope="conversation", state_cues=ON_OFF, tags="mute_conversation"),
        function("communication.conversation.archive", "communication", "대화 보관", "Archive conversation", "대화 보관|채팅 보관|메시지 보관함으로|대화 숨기기", "Archive conversation|Archive chat|Move to archive|Hide conversation", "보관된 대화|받은편지함에서 제거", "대화 삭제|저장된 게시물", risk="medium", policy="never_auto", scope="conversation", tags="archive_conversation"),
        function("communication.conversation.delete", "communication", "대화 삭제", "Delete conversation", "대화 삭제|채팅 삭제|메시지 기록 삭제|대화 내용 지우기", "Delete conversation|Delete chat|Clear message history|Remove conversation", "모든 메시지|복구할 수 없음|기기에서 삭제", "대화 보관|메시지 요청 삭제|계정 삭제", risk="high", policy="never_auto", changing=True, scope="conversation", node_kind="destructive_action", stop_policy="before_action", risk_cues=DESTRUCTIVE_RISK, tags="delete_conversation"),

        # Creation and media controls cover icon-only plus/create/share menus,
        # while publishing and deletion remain explicit user actions.
        function("content.create", "content", "새 콘텐츠 만들기", "Create content", "만들기|새 게시물|작성|콘텐츠 만들기|플러스 버튼", "Create|New post|Compose|Create content|Plus button", "게시물|사진|동영상|스토리", "새 메시지|계정 만들기|결제 만들기", terminal=False, node_kind="hub", tags="create_content"),
        function("content.upload", "content", "콘텐츠 업로드", "Upload content", "업로드|사진 올리기|동영상 올리기|파일 게시|게시물 추가", "Upload|Upload photo|Upload video|Post file|Add post", "갤러리|카메라|파일 선택", "파일 백업|프로필 사진|영수증 첨부", risk="medium", policy="never_auto", scope="published_content", tags="upload_content"),
        function("content.drafts", "content", "임시 저장", "Drafts", "임시 저장|임시 보관함|작성 중|초안|게시물 초안", "Drafts|Saved drafts|In progress|Unpublished|Post drafts", "편집|게시|삭제", "다운로드|저장한 게시물|보관된 대화", tags="drafts"),
        function("content.edit", "content", "콘텐츠 수정", "Edit content", "수정|게시물 수정|콘텐츠 편집|내용 고치기", "Edit|Edit post|Edit content|Modify", "제목|설명|저장", "프로필 수정|주문 수정|설정 변경", risk="medium", policy="never_auto", scope="published_content", tags="edit_content"),
        function("content.delete.entry", "content", "콘텐츠 삭제 진입", "Delete content entry", "게시물 삭제|콘텐츠 삭제|사진 삭제|동영상 삭제", "Delete post|Delete content|Remove photo|Delete video", "더보기|관리|휴지통", "계정 삭제|대화 삭제|다운로드 삭제", risk="high", policy="never_auto", scope="published_content", node_kind="action_entry", stop_policy="before_action", risk_cues=DESTRUCTIVE_RISK, tags="delete_content"),
        function("content.share", "content", "콘텐츠 공유", "Share content", "공유|게시물 공유|링크 공유|다른 앱으로 보내기", "Share|Share post|Share link|Send to another app", "링크 복사|받는 사람|공유 대상", "데이터 공유 설정|가족 공유|위치 공유", risk="medium", policy="never_auto", scope="external_share", tags="share_content"),
        function("content.comments", "content", "댓글", "Comments", "댓글|댓글 보기|답글|의견", "Comments|View comments|Replies|Discussion", "댓글 작성|답글|정렬", "고객센터 문의|리뷰|메시지", tags="comments"),
        function("content.not_interested", "content", "관심 없음", "Not interested", "관심 없음|추천하지 않기|이런 콘텐츠 줄이기|숨기기", "Not interested|Show fewer|Don't recommend|Hide this content", "추천 피드|알고리즘|의견 보내기", "사용자 차단|게시물 삭제|팔로우 취소", risk="medium", policy="never_auto", scope="recommendation", tags="not_interested"),
        function("media.autoplay", "media", "자동 재생", "Autoplay", "자동 재생|다음 영상 자동 재생|연속 재생|미리보기 자동 재생", "Autoplay|Play next automatically|Continuous play|Autoplay previews", "재생 설정|Wi-Fi에서만|모바일 데이터", "자동 결제|자동 다운로드|자동 로그인", risk="medium", policy="never_auto", state_cues=ON_OFF, tags="autoplay"),
        function("media.captions", "media", "자막 설정", "Captions", "자막|캡션|자막 언어|CC 설정", "Captions|Subtitles|Caption language|CC settings", "언어|스타일|자동 생성", "알림 자막|사진 설명|댓글", tags="captions"),
        function("media.quality", "media", "재생 화질", "Playback quality", "화질|동영상 화질|재생 품질|스트리밍 품질", "Quality|Video quality|Playback quality|Streaming quality", "자동|고화질|데이터 절약", "다운로드 화질|카메라 화질|사진 품질", tags="media_quality"),
        function("media.speed", "media", "재생 속도", "Playback speed", "재생 속도|배속|영상 속도|속도 조절", "Playback speed|Speed|Video speed|Play rate", "0.5배|1배|1.5배|2배", "다운로드 속도|네트워크 속도|배송 속도", tags="playback_speed"),
    ]
)


INTENTS.extend(
    [
        intent("edit_profile", "account.profile.edit", "프로필 수정하고 싶어|내 정보 바꾸기|회원정보 편집|edit my profile|update personal details", "account.entry:0.56|account.profile:0.78|account.profile.edit:1.0", rules="프로필+수정|edit+profile", avoid="account.delete.entry"),
        intent("change_email", "account.email.change", "계정 이메일 변경|로그인 이메일 바꾸기|새 이메일 주소 등록|change account email|update login email", "account.entry:0.44|account.settings:0.6|account.personal_info:0.76|account.email.change:1.0", rules="이메일+변경|change+email", avoid="notification.email|auth.signup.email"),
        intent("change_phone_number", "account.phone.change", "휴대폰 번호 변경|계정 전화번호 바꾸기|새 번호 등록|change phone number|update mobile number", "account.entry:0.44|account.settings:0.6|account.personal_info:0.76|account.phone.change:1.0", rules="휴대폰+번호+변경|전화번호+바꾸|phone+number", avoid="notification.sms|auth.signup.phone"),
        intent("change_username", "account.username.change", "사용자 이름 변경|아이디 바꾸기|닉네임 수정|change username|update handle", "account.entry:0.44|account.profile:0.62|account.profile.edit:0.8|account.username.change:1.0", rules="사용자+이름+변경|change+username"),
        intent("change_profile_photo", "account.avatar.change", "프로필 사진 바꾸기|아바타 변경|내 사진 수정|change profile photo|update avatar", "account.entry:0.42|account.profile:0.62|account.profile.edit:0.78|account.avatar.change:1.0", rules="프로필+사진+변경|profile+photo"),
        intent("add_account", "account.add", "계정 추가|다른 계정 로그인|계정 하나 더 연결|add another account|connect a new account", "account.entry:0.58|account.switch:0.76|account.add:1.0", rules="계정+추가|add+account", avoid="auth.signup.confirm"),
        intent("password_reset", "security.password.reset", "비밀번호를 잊었어|비밀번호 찾기|암호 재설정|forgot my password|reset password", "auth.entry:0.44|auth.login.entry:0.62|account.recovery:0.78|security.password.reset:1.0", rules="비밀번호+찾기|reset+password", avoid="security.password|auth.password.create"),
        intent("passkey_management", "security.passkey", "패스키 관리|패스키 추가|패스키 삭제|manage passkeys|add a passkey", "account.entry:0.4|settings.root:0.52|account.security:0.72|security.passkey:1.0", rules="패스키+관리|manage+passkeys"),
        intent("biometric_login_settings", "security.biometric", "지문 로그인 켜기|얼굴 인식 로그인 설정|생체 인증 끄기|enable biometric login|fingerprint sign in settings", "account.entry:0.36|settings.root:0.48|account.security:0.68|security.biometric:1.0", rules="생체+인증|biometric+login", avoid="android.permission.manage"),
        intent("login_history", "security.login_history", "로그인 기록 확인|최근 접속 내역|누가 내 계정에 로그인했는지|view login history|recent sign-in activity", "account.entry:0.36|settings.root:0.46|account.security:0.66|security.login_history:1.0", rules="로그인+기록|login+history", avoid="content.history|billing.purchase_history"),
        intent("shopping_cart", "commerce.cart", "장바구니 열기|담은 상품 보기|카트로 가기|open shopping cart|view items in my basket", "navigation.menu:0.34|commerce.cart:1.0", rules="장바구니+보기|shopping+cart", avoid="content.saved"),
        intent("wishlist", "commerce.wishlist", "찜한 상품 보기|위시리스트 열기|관심 상품 목록|open my wishlist|view saved products", "account.entry:0.34|navigation.menu:0.42|commerce.wishlist:1.0", rules="찜+상품|wishlist", avoid="content.saved|privacy.blocked_users"),
        intent("order_tracking", "order.tracking", "배송 조회|내 주문 어디쯤 왔어|택배 위치 확인|track my order|check delivery status", "account.entry:0.32|order.list:0.54|order.detail:0.76|order.tracking:1.0", rules="배송+조회|track+order", avoid="travel.flight_status"),
        intent("order_return", "order.return.entry", "주문 반품하고 싶어|상품을 돌려보내고 싶어|반품 신청|return my order|start a product return", "account.entry:0.28|order.list:0.48|order.detail:0.7|order.return.entry:1.0", rules="주문+반품|return+order", avoid="order.cancel.entry|order.exchange.entry", desired_state="user_confirmation_required"),
        intent("order_exchange", "order.exchange.entry", "상품 교환하고 싶어|다른 사이즈로 교환|교환 신청|exchange my item|request an exchange", "account.entry:0.28|order.list:0.48|order.detail:0.7|order.exchange.entry:1.0", rules="상품+교환|exchange+item", avoid="order.return.entry|order.cancel.entry", desired_state="user_confirmation_required"),
        intent("message_inbox", "communication.inbox", "메시지함 열기|내 채팅 보기|받은 메시지|open messages|show my inbox", "navigation.menu:0.34|communication.inbox:1.0", rules="메시지함+열기|open+inbox"),
        intent("compose_message", "communication.compose", "새 메시지 보내기|대화 시작|누군가에게 채팅하기|send a new message|start a conversation", "navigation.menu:0.3|communication.inbox:0.62|communication.compose:1.0", rules="새+메시지|new+message", avoid="content.create|support.chat", desired_state="user_confirmation_required"),
        intent("search_conversation", "communication.conversation.search", "채팅 내용 검색|대화에서 메시지 찾기|대화 내 메시지 검색|search messages in a conversation|find text in chat", "communication.inbox:0.5|communication.conversation.search:1.0", rules="대화+검색|search+messages"),
        intent("mute_conversation", "communication.conversation.mute", "채팅방 알림 끄기|이 채팅방 알림 끄기|대화 음소거|메시지 알림 숨기기|mute this conversation|turn off chat notifications", "communication.inbox:0.42|navigation.more:0.58|communication.conversation.mute:1.0", rules="채팅방+알림|대화+알림+끄기|mute+conversation", avoid="notification.settings|privacy.blocked_users", desired_state="user_confirmation_required"),
        intent("archive_conversation", "communication.conversation.archive", "이 대화 보관|채팅을 보관함으로|대화 숨기기|archive this conversation|move chat to archive", "communication.inbox:0.42|navigation.more:0.58|communication.conversation.archive:1.0", rules="대화+보관|archive+conversation", avoid="communication.conversation.delete|content.saved", desired_state="user_confirmation_required"),
        intent("delete_conversation", "communication.conversation.delete", "대화 삭제|채팅 기록 지우기|메시지 전부 삭제|delete this conversation|clear chat history", "communication.inbox:0.38|navigation.more:0.54|communication.conversation.delete:1.0", rules="대화+삭제|delete+conversation", avoid="communication.conversation.archive|account.delete.entry", desired_state="user_confirmation_required"),
        intent("create_content", "content.create", "새 게시물 만들기|콘텐츠 작성|사진 올리기 시작|create a new post|make new content", "navigation.home:0.32|content.create:1.0", rules="새+게시물|create+post", avoid="communication.compose|auth.signup.entry"),
        intent("upload_content", "content.upload", "사진 업로드|동영상 올리기|파일 게시|upload a photo|post a video", "navigation.home:0.28|content.create:0.72|content.upload:1.0", rules="사진+업로드|upload+photo", avoid="files.upload|account.avatar.change", desired_state="user_confirmation_required"),
        intent("view_drafts", "content.drafts", "임시 저장한 글 보기|게시물 초안|작성 중인 콘텐츠|view my drafts|open saved drafts", "account.entry:0.3|content.create:0.5|content.drafts:1.0", rules="임시+저장+글|view+drafts", avoid="content.saved|files.backup"),
        intent("edit_content", "content.edit", "내 게시물 수정|올린 글 편집|콘텐츠 내용 바꾸기|edit my post|modify uploaded content", "account.entry:0.28|content.history:0.42|navigation.more:0.62|content.edit:1.0", rules="게시물+수정|edit+post", avoid="account.profile.edit", desired_state="user_confirmation_required"),
        intent("delete_content", "content.delete.entry", "내 게시물 삭제|올린 사진 지우기|콘텐츠 제거|delete my post|remove uploaded content", "account.entry:0.26|content.history:0.4|navigation.more:0.58|content.delete.entry:1.0", rules="게시물+삭제|delete+post", avoid="account.delete.entry|communication.conversation.delete", desired_state="user_confirmation_required"),
        intent("share_content", "content.share", "게시물 공유|이 링크 보내기|다른 앱으로 공유|share this post|send content to another app", "navigation.more:0.5|content.share:1.0", rules="게시물+공유|share+post", avoid="files.share|privacy.location_sharing", desired_state="user_confirmation_required"),
        intent("view_comments", "content.comments", "댓글 보기|게시물 답글 확인|의견 열기|view comments|open replies", "content.comments:1.0", rules="댓글+보기|view+comments", avoid="commerce.review|support.contact"),
        intent("not_interested", "content.not_interested", "이런 게시물 안 보고 싶어|관심 없음 표시|추천 줄이기|not interested in this content|show fewer posts like this", "navigation.more:0.56|content.not_interested:1.0", rules="관심+없음|not+interested", avoid="privacy.blocked_users|content.delete.entry", desired_state="user_confirmation_required"),
        intent("autoplay_settings", "media.autoplay", "자동 재생 끄기|다음 영상 자동 재생 켜기|미리보기 자동 재생 설정|turn off autoplay|enable continuous playback", "account.entry:0.28|settings.root:0.5|settings.playback:0.72|media.autoplay:1.0", rules="자동+재생|autoplay", avoid="billing.autopay", desired_state="user_confirmation_required"),
        intent("caption_settings", "media.captions", "자막 설정|캡션 언어 변경|CC 켜기|caption settings|change subtitle language", "settings.root:0.42|settings.playback:0.64|media.captions:1.0", rules="자막+설정|caption+settings", avoid="accessibility.captions"),
        intent("playback_quality", "media.quality", "영상 화질 바꾸기|재생 품질 설정|스트리밍 화질|change video quality|streaming quality settings", "settings.root:0.38|settings.playback:0.62|media.quality:1.0", rules="화질+변경|video+quality", avoid="settings.downloads"),
        intent("playback_speed", "media.speed", "재생 속도 바꾸기|두 배속으로 보기|영상 배속|change playback speed|play video at 2x", "navigation.more:0.4|settings.playback:0.58|media.speed:1.0", rules="재생+속도|playback+speed"),
    ]
)


FUNCTIONS.extend(
    [
        # Travel and transport flows use booking-centric terms that are very
        # different from generic account/order menus.
        function("travel.bookings", "travel", "예약 목록", "Bookings", "예약|내 예약|예약 목록|여행 일정|나의 여행", "Bookings|My bookings|Reservations|Trips|My travel", "예약번호|출발|도착|여정", "주문 내역|병원 예약|식당 예약", terminal=False, node_kind="hub", tags="bookings"),
        function("travel.booking.detail", "travel", "예약 상세", "Booking details", "예약 상세|여정 상세|예약 정보|항공권 상세", "Booking details|Trip details|Reservation details|Itinerary details", "예약번호|탑승객|출발 시간", "주문 상세|보험 계약 상세", tags="booking_detail"),
        function("travel.checkin", "travel", "체크인", "Check-in", "체크인|온라인 체크인|모바일 체크인|탑승 수속", "Check-in|Online check-in|Mobile check-in|Check in now", "출발 시간|탑승객|여권|좌석", "출석 체크|호텔 퇴실|로그인", risk="medium", policy="never_auto", scope="travel_booking", tags="checkin"),
        function("travel.boarding_pass", "travel", "탑승권", "Boarding pass", "탑승권|모바일 탑승권|보딩패스|QR 탑승권", "Boarding pass|Mobile boarding pass|Boarding card|Pass QR", "게이트|좌석|탑승 시간|QR", "승차권 구매|쿠폰|멤버십 카드", tags="boarding_pass"),
        function("travel.seat", "travel", "좌석 선택·변경", "Seat selection", "좌석 선택|좌석 변경|자리 지정|좌석 배정", "Seat selection|Change seat|Choose seat|Seat assignment", "좌석 배치도|창가|통로|추가 요금", "배송 좌석|영화 예매 좌석", risk="medium", policy="never_auto", scope="travel_booking", tags="seat_selection"),
        function("travel.baggage", "travel", "수하물 관리", "Baggage", "수하물|위탁 수하물|기내 수하물|짐 추가|수하물 구매", "Baggage|Checked baggage|Carry-on baggage|Add bags|Buy baggage", "무게|개수|추가 요금", "파일 저장공간|배송 물품", risk="medium", policy="never_auto", scope="travel_booking", tags="baggage"),
        function("travel.booking.change", "travel", "예약 변경", "Change booking", "예약 변경|여정 변경|항공편 변경|날짜 바꾸기", "Change booking|Modify trip|Change flight|Change travel date", "변경 수수료|새 일정|운임 차액", "예약 취소|좌석 변경|프로필 변경", risk="medium", policy="never_auto", scope="travel_booking", tags="booking_change"),
        function("travel.booking.cancel.entry", "travel", "예약 취소 진입", "Cancel booking entry", "예약 취소|여정 취소|항공권 취소|예약 철회", "Cancel booking|Cancel trip|Cancel flight|Cancel reservation", "환불 규정|취소 수수료|예약번호", "주문 취소|구독 해지|병원 예약 취소", risk="high", policy="never_auto", scope="travel_booking", node_kind="action_entry", stop_policy="before_action", risk_cues=DESTRUCTIVE_RISK, tags="booking_cancel"),
        function("travel.flight_status", "travel", "항공편 상태", "Flight status", "항공편 상태|출도착 조회|운항 정보|비행기 지연 확인", "Flight status|Arrivals and departures|Flight information|Delay status", "편명|공항|출발|도착|지연", "배송 상태|주문 추적|버스 도착", tags="flight_status"),

        # Finance functions stop before money movement, card state changes or
        # credential-impacting actions.  Read-only histories remain safe.
        function("finance.accounts", "finance", "금융 계좌 목록", "Financial accounts", "계좌|내 계좌|통장|보유 계좌|자산 목록", "Accounts|My accounts|Bank accounts|Account list|Assets", "잔액|계좌번호|입출금", "서비스 계정|연결 계정|소셜 계정", terminal=False, node_kind="hub", tags="financial_accounts"),
        function("finance.transactions", "finance", "거래 내역", "Transaction history", "거래 내역|입출금 내역|계좌 내역|이체 내역|사용 내역", "Transactions|Transaction history|Account activity|Transfers|Spending history", "금액|잔액|입금|출금", "구매 내역|시청 기록|로그인 기록", tags="transactions"),
        function("finance.transfer.entry", "finance", "송금·이체 진입", "Transfer money entry", "송금|이체|돈 보내기|계좌 이체|보내기", "Transfer|Send money|Bank transfer|Move money|Pay someone", "받는 사람|출금 계좌|금액", "메시지 보내기|파일 전송|포인트 선물", risk="medium", policy="never_auto", scope="financial_transaction", node_kind="action_entry", stop_policy="on_destination_screen", risk_cues={"money": ["금액", "잔액", "수수료", "amount", "balance", "fee"]}, tags="money_transfer"),
        function("finance.transfer.confirm", "finance", "송금·이체 최종 확인", "Confirm transfer", "이체하기|송금 완료|보내기 확인|이체 실행", "Confirm transfer|Send now|Complete transfer|Submit payment", "받는 분|금액|수수료|최종 확인", "취소|이전|내용 수정", risk="high", policy="never_auto", changing=True, scope="financial_transaction", node_kind="destructive_action", stop_policy="before_action", risk_cues={"money": ["금액", "출금", "amount", "debit"], "external_submission": ["이체", "송금", "transfer", "send"]}, tags="money_transfer_confirm"),
        function("finance.recurring_transfer", "finance", "자동 이체", "Recurring transfers", "자동 이체|정기 이체|예약 이체|자동 송금", "Recurring transfers|Scheduled transfer|Standing order|Automatic transfer", "주기|다음 이체일|금액|해지", "자동 결제|구독 갱신|보험료 납입", risk="medium", policy="never_auto", scope="financial_transaction", tags="recurring_transfer"),
        function("finance.cards", "finance", "카드 관리", "Manage cards", "카드|내 카드|카드 관리|보유 카드|결제 카드", "Cards|My cards|Manage cards|Card list|Payment cards", "카드번호|이용 한도|분실 신고", "프로필 카드|멤버십 카드|탑승권", terminal=False, node_kind="hub", tags="cards"),
        function("finance.card.freeze", "finance", "카드 일시 정지", "Freeze card", "카드 일시 정지|카드 잠금|사용 정지|결제 차단", "Freeze card|Lock card|Pause card|Block card payments", "분실|도난|사용 재개", "구독 일시중지|계정 잠금", risk="high", policy="never_auto", changing=True, scope="payment_card", node_kind="state_change", stop_policy="before_action", state_cues=ON_OFF, risk_cues={"money": ["결제", "카드 사용", "payments", "card use"]}, tags="freeze_card"),
        function("finance.card.lost", "finance", "카드 분실 신고", "Report lost card", "카드 분실 신고|도난 신고|카드를 잃어버림|분실 카드", "Report lost card|Card stolen|Lost my card|Lost or stolen", "재발급|즉시 정지|본인 확인", "일반 문의|거래 신고|앱 문제 신고", risk="high", policy="never_auto", changing=True, scope="payment_card", node_kind="destructive_action", stop_policy="before_action", risk_cues={"money": ["카드 정지", "재발급", "block card", "replacement"]}, tags="lost_card"),
        function("finance.statements", "finance", "명세서", "Statements", "명세서|거래 명세서|카드 명세서|월별 명세|이용 대금 명세서", "Statements|Account statement|Card statement|Monthly statement|Billing statement", "기간|청구 금액|PDF|이메일", "영수증|보험 증명서|급여 명세", tags="statements"),

        # Files and cloud productivity functions distinguish local deletion,
        # trash recovery, sync, and external sharing.
        function("files.browser", "files", "파일 목록", "Files", "파일|내 파일|파일 목록|문서|폴더", "Files|My files|File list|Documents|Folders", "최근 파일|공유됨|오프라인", "앱 데이터|다운로드 콘텐츠|첨부 파일 선택", terminal=False, node_kind="hub", tags="files"),
        function("files.search", "files", "파일 검색", "Search files", "파일 검색|문서 찾기|폴더 검색|내 파일에서 찾기", "Search files|Find document|Search folders|Find in files", "파일 이름|유형|수정일", "앱 검색|메시지 검색|웹 검색", tags="file_search"),
        function("files.upload", "files", "파일 업로드", "Upload files", "파일 업로드|문서 올리기|클라우드에 추가|파일 추가", "Upload files|Upload document|Add to cloud|Add file", "기기에서 선택|카메라|폴더", "게시물 업로드|프로필 사진|보험 서류 제출", risk="medium", policy="never_auto", scope="cloud_storage", tags="file_upload"),
        function("files.share", "files", "파일 공유", "Share files", "파일 공유|문서 공유|링크 보내기|공유 사용자 관리", "Share file|Share document|Send link|Manage access", "링크 공개|사용자 초대|권한", "게시물 공유|위치 공유|가족 공유", risk="medium", policy="never_auto", scope="cloud_access", tags="file_share"),
        function("files.trash", "files", "휴지통", "Trash", "휴지통|삭제된 파일|최근 삭제됨|버린 파일", "Trash|Deleted files|Recently deleted|Bin", "복원|영구 삭제|보관 기간", "캐시 삭제|메시지 보관함", terminal=False, node_kind="hub", tags="trash"),
        function("files.restore", "files", "파일 복원", "Restore file", "복원|파일 복구|휴지통에서 복원|되돌리기", "Restore|Recover file|Restore from trash|Undelete", "원래 위치|삭제된 파일", "계정 복구|구매 복원|백업 복원", risk="medium", policy="never_auto", changing=True, scope="cloud_storage", node_kind="state_change", stop_policy="before_action", tags="file_restore"),

        # Privacy/notification/accessibility destinations that occur across
        # social, commerce and communication apps.
        function("privacy.activity_status", "privacy", "활동 상태", "Activity status", "활동 상태|온라인 상태|접속 중 표시|마지막 접속", "Activity status|Online status|Show when active|Last seen", "온라인|최근 활동|다른 사람이 볼 수 있음", "이용 기록|로그인 기록|배송 상태", risk="medium", policy="never_auto", state_cues=ON_OFF, tags="activity_status"),
        function("privacy.read_receipts", "privacy", "읽음 표시", "Read receipts", "읽음 표시|읽음 확인|메시지 읽은 상태|읽음 알림", "Read receipts|Seen status|Message read status|Read confirmation", "메시지|상대방|확인", "영수증|결제 확인|알림 배지", risk="medium", policy="never_auto", state_cues=ON_OFF, tags="read_receipts"),
        function("privacy.contacts_sync", "privacy", "연락처 동기화", "Contact syncing", "연락처 동기화|주소록 업로드|친구 찾기 연락처|연락처 연결", "Sync contacts|Upload contacts|Find friends from contacts|Connect address book", "주소록|친구 추천|연락처 삭제", "전화번호 변경|배송 연락처|고객센터 전화", risk="high", policy="never_auto", changing=True, scope="contacts", node_kind="state_change", stop_policy="before_action", state_cues=ON_OFF, risk_cues={"sensitive_access": ["연락처 업로드", "주소록", "upload contacts", "address book"]}, tags="contacts_sync"),
        function("privacy.location_sharing", "privacy", "위치 공유", "Location sharing", "위치 공유|실시간 위치|내 위치 보내기|위치 공개", "Location sharing|Live location|Share my location|Location visibility", "공유 시간|받는 사람|정확한 위치", "위치 권한|지역 설정|매장 찾기", risk="high", policy="never_auto", changing=True, scope="precise_location", node_kind="state_change", stop_policy="before_action", state_cues=ON_OFF, risk_cues={"sensitive_access": ["실시간 위치", "정확한 위치", "live location", "precise location"]}, tags="location_sharing"),
        function("notification.quiet_hours", "notification", "방해 금지 시간", "Quiet hours", "방해 금지 시간|알림 휴식|조용한 시간|야간 알림 끄기", "Quiet hours|Do not disturb schedule|Notification pause|Mute at night", "시작 시간|종료 시간|요일", "기기 방해 금지|대화 음소거|알림 전체 끄기", risk="medium", policy="never_auto", state_cues=ON_OFF, tags="quiet_hours"),
        function("accessibility.text_size", "accessibility", "글자 크기", "Text size", "글자 크기|텍스트 크기|글꼴 크기|폰트 크기", "Text size|Font size|Larger text|Text scaling", "작게|기본|크게|미리보기", "자막 크기|화면 확대|이미지 크기", tags="text_size"),
        function("accessibility.high_contrast", "accessibility", "고대비 화면", "High contrast", "고대비|대비 높이기|고대비 텍스트|색상 대비", "High contrast|Increase contrast|High contrast text|Color contrast", "가독성|색상|어두운 테마", "화질|밝기|프로필 테마", risk="medium", policy="never_auto", state_cues=ON_OFF, tags="high_contrast"),

        function("support.faq", "support", "자주 묻는 질문", "Frequently asked questions", "자주 묻는 질문|FAQ|도움말 문서|문제 해결", "FAQ|Frequently asked questions|Help articles|Troubleshooting", "카테고리|검색|답변", "문의 보내기|문제 신고|커뮤니티 게시물", tags="faq"),
        function("notification.email", "notification", "이메일 알림", "Email notifications", "이메일 알림|메일 수신 설정|이메일로 알림|서비스 메일", "Email notifications|Email preferences|Notify by email|Service emails", "이메일 주소|공지|활동 알림", "계정 이메일 변경|이메일 회원가입|뉴스레터 구독", risk="medium", policy="never_auto", state_cues=ON_OFF, tags="email_notifications"),
        function("notification.sms", "notification", "문자 알림", "SMS notifications", "문자 알림|SMS 수신|문자로 알림|휴대폰 알림", "SMS notifications|Text alerts|Notify by SMS|Mobile alerts", "휴대폰 번호|문자 메시지|알림", "전화번호 변경|메시지함|인증 코드", risk="medium", policy="never_auto", state_cues=ON_OFF, tags="sms_notifications"),
        function("files.backup", "files", "파일 백업", "File backup", "파일 백업|문서 백업|클라우드 백업|자동 백업", "File backup|Document backup|Cloud backup|Automatic backup", "동기화|복원|백업 시간", "임시 저장|다운로드|앱 데이터 삭제", risk="medium", policy="never_auto", state_cues=ON_OFF, tags="file_backup"),
        function("commerce.review", "commerce", "상품 리뷰", "Product reviews", "상품 리뷰|구매 후기|리뷰 작성|별점", "Product reviews|Purchase review|Write a review|Rating", "구매 상품|별점|사진 후기", "게시물 댓글|앱 리뷰|문제 신고", risk="medium", policy="never_auto", scope="published_content", tags="product_review"),
        function("accessibility.captions", "accessibility", "접근성 자막", "Accessibility captions", "접근성 자막|실시간 자막|시스템 자막|청각 지원 자막", "Accessibility captions|Live Caption|System captions|Hearing captions", "청각 지원|언어|스타일", "영상 자막|댓글|사진 설명", risk="medium", policy="never_auto", state_cues=ON_OFF, tags="accessibility_captions"),
        function("subscription.resume", "subscription", "구독 재개", "Resume subscription", "구독 재개|멤버십 다시 시작|일시중지 해제|서비스 재개", "Resume subscription|Restart membership|Unpause subscription|Resume service", "일시중지됨|다음 결제일|혜택 재개", "새로 구독|요금제 변경|구독 취소", risk="high", policy="never_auto", changing=True, scope="recurring_charge", node_kind="state_change", stop_policy="before_action", state_cues={"paused": ["일시중지됨", "Paused"], "active": ["이용 중", "Active"]}, risk_cues={"money": ["다음 결제", "정기 결제", "next payment", "recurring charge"]}, tags="subscription_resume"),
        function("subscription.renewal", "subscription", "자동 갱신", "Automatic renewal", "자동 갱신|정기 갱신|다음 결제 자동|구독 갱신", "Automatic renewal|Auto-renew|Recurring renewal|Renew subscription", "다음 결제일|갱신 예정|결제 수단", "자동 재생|자동 다운로드|자동 이체", risk="high", policy="never_auto", changing=True, scope="recurring_charge", node_kind="state_change", stop_policy="before_action", state_cues=ON_OFF, risk_cues={"money": ["다음 결제", "자동 결제", "next payment", "recurring charge"]}, tags="auto_renewal"),
        function("billing.refund_status", "billing", "환불 상태", "Refund status", "환불 상태|환불 진행 상황|환불 내역|환불 처리 중", "Refund status|Refund progress|Refund history|Refund pending", "처리 중|완료|영업일|결제 수단", "환불 신청|주문 취소|보험금 청구 상태", tags="refund_status"),
        function("health.appointments", "health", "진료 예약", "Medical appointments", "진료 예약|병원 예약|예약 진료|내원 예약", "Medical appointments|Book a visit|Doctor appointment|Clinic booking", "날짜|의료진|진료과", "여행 예약|식당 예약|배달 예약", risk="medium", policy="never_auto", scope="health_data", tags="medical_appointment"),
        function("health.records", "health", "건강 기록", "Health records", "건강 기록|진료 기록|검사 결과|의료 기록", "Health records|Medical records|Test results|Clinical records", "진료일|검사|처방|민감 정보", "활동 기록|보험 청구 현황|운동 기록", risk="medium", policy="never_auto", scope="health_data", tags="health_records"),
    ]
)


INTENTS.extend(
    [
        intent("travel_bookings", "travel.bookings", "내 예약 보기|여행 일정 확인|예약 목록 열기|view my bookings|show my trips", "account.entry:0.3|navigation.menu:0.42|travel.bookings:1.0", rules="내+예약|my+bookings", avoid="order.list|health.appointments"),
        intent("travel_booking_details", "travel.booking.detail", "예약 상세 확인|항공권 정보 보기|내 여정 상세|view booking details|show itinerary details", "travel.bookings:0.62|travel.booking.detail:1.0", rules="예약+상세|booking+details", avoid="order.detail"),
        intent("travel_checkin", "travel.checkin", "온라인 체크인|탑승 수속하고 싶어|모바일 체크인|check in for my flight|online check-in", "travel.bookings:0.44|travel.booking.detail:0.66|travel.checkin:1.0", rules="온라인+체크인|flight+check-in", avoid="auth.login", desired_state="user_confirmation_required"),
        intent("travel_boarding_pass", "travel.boarding_pass", "탑승권 보여줘|모바일 보딩패스|QR 탑승권 열기|show boarding pass|open mobile boarding card", "travel.bookings:0.4|travel.booking.detail:0.58|travel.boarding_pass:1.0", rules="탑승권+보기|boarding+pass"),
        intent("travel_seat_selection", "travel.seat", "항공 좌석 변경|창가 자리 선택|좌석 지정|change my flight seat|select a seat", "travel.bookings:0.36|travel.booking.detail:0.56|travel.seat:1.0", rules="항공+좌석|flight+seat", desired_state="user_confirmation_required"),
        intent("travel_baggage", "travel.baggage", "수하물 추가|위탁 수하물 구매|짐 규정 확인|add checked baggage|manage my bags", "travel.bookings:0.34|travel.booking.detail:0.54|travel.baggage:1.0", rules="수하물+추가|add+baggage", desired_state="user_confirmation_required"),
        intent("travel_booking_change", "travel.booking.change", "항공편 날짜 변경|예약 일정 바꾸기|여정 변경|change flight date|modify my booking", "travel.bookings:0.3|travel.booking.detail:0.52|travel.booking.change:1.0", rules="예약+변경|change+booking", avoid="travel.booking.cancel.entry", desired_state="user_confirmation_required"),
        intent("travel_booking_cancellation", "travel.booking.cancel.entry", "항공권 취소|여행 예약 취소|여정 취소|cancel my flight|cancel travel booking", "travel.bookings:0.28|travel.booking.detail:0.5|travel.booking.cancel.entry:1.0", rules="예약+취소|cancel+booking", avoid="order.cancel.entry|subscription.cancel.entry", desired_state="user_confirmation_required"),
        intent("travel_flight_status", "travel.flight_status", "항공편 지연 확인|출도착 조회|비행기 운항 상태|check flight status|is my flight delayed", "navigation.search:0.36|travel.flight_status:1.0", rules="항공편+상태|flight+status", avoid="order.tracking"),
        intent("financial_accounts", "finance.accounts", "내 계좌 보기|보유 통장 목록|금융 자산 확인|show my bank accounts|view financial accounts", "navigation.menu:0.34|finance.accounts:1.0", rules="내+계좌|bank+accounts", avoid="account.linked_accounts"),
        intent("transaction_history", "finance.transactions", "입출금 내역 보기|계좌 거래 내역|최근 이체 확인|view transaction history|show account activity", "finance.accounts:0.56|finance.transactions:1.0", rules="거래+내역|transaction+history", avoid="billing.purchase_history|content.history"),
        intent("money_transfer", "finance.transfer.entry", "돈 보내기|계좌 이체|송금하고 싶어|send money|make a bank transfer", "finance.accounts:0.48|finance.transfer.entry:1.0", rules="돈+보내기|bank+transfer", avoid="communication.compose|content.share", desired_state="user_confirmation_required"),
        intent("recurring_transfer_management", "finance.recurring_transfer", "자동 이체 관리|정기 송금 해지|예약 이체 변경|manage recurring transfers|cancel a standing order", "finance.accounts:0.34|finance.transfer.entry:0.46|finance.recurring_transfer:1.0", rules="자동+이체|recurring+transfer", avoid="billing.autopay|subscription.manage", desired_state="user_confirmation_required"),
        intent("card_management", "finance.cards", "내 카드 관리|보유 카드 보기|결제 카드 설정|manage my bank cards|show my cards", "navigation.menu:0.34|finance.cards:1.0", rules="내+카드+관리|manage+cards"),
        intent("freeze_card", "finance.card.freeze", "카드 잠그기|카드 사용 일시 정지|결제 차단|freeze my card|temporarily lock card", "finance.cards:0.58|finance.card.freeze:1.0", rules="카드+정지|freeze+card", avoid="subscription.pause|account.security", desired_state="user_confirmation_required"),
        intent("report_lost_card", "finance.card.lost", "카드 분실 신고|도난당한 카드 정지|카드를 잃어버렸어|report lost card|my card was stolen", "finance.cards:0.54|finance.card.lost:1.0", rules="카드+분실|lost+card", avoid="support.report", desired_state="user_confirmation_required"),
        intent("financial_statements", "finance.statements", "월별 명세서 보기|카드 명세서 다운로드|계좌 명세|view monthly statement|download bank statement", "finance.accounts:0.4|finance.cards:0.42|finance.statements:1.0", rules="월별+명세서|monthly+statement", avoid="billing.receipt|insurance.certificate.issue"),
        intent("browse_files", "files.browser", "내 파일 열기|문서 목록 보기|클라우드 파일|open my files|browse documents", "navigation.menu:0.34|files.browser:1.0", rules="내+파일+열기|open+my+files|browse+documents", avoid="content.downloads"),
        intent("search_files", "files.search", "문서 파일 찾기|내 파일 검색|폴더에서 검색|search my files|find a document", "files.browser:0.54|files.search:1.0", rules="파일+검색|search+files", avoid="navigation.search|communication.conversation.search"),
        intent("upload_file", "files.upload", "클라우드에 파일 올리기|문서 업로드|새 파일 추가|upload a file|add document to cloud", "files.browser:0.48|content.create:0.38|files.upload:1.0", rules="파일+업로드|upload+file", avoid="content.upload|insurance.claim.documents", desired_state="user_confirmation_required"),
        intent("share_file", "files.share", "문서 공유|파일 링크 보내기|공유 권한 설정|share a file|send document link", "files.browser:0.42|navigation.more:0.56|files.share:1.0", rules="파일+공유|share+file", avoid="content.share|privacy.location_sharing", desired_state="user_confirmation_required"),
        intent("restore_file", "files.restore", "휴지통 파일 복원|삭제한 문서 되돌리기|파일 복구|restore deleted file|recover document from trash", "files.browser:0.34|files.trash:0.68|files.restore:1.0", rules="파일+복원|restore+file", avoid="account.recovery", desired_state="user_confirmation_required"),
        intent("activity_status_control", "privacy.activity_status", "온라인 상태 숨기기|활동 중 표시 끄기|마지막 접속 공개 안 함|hide my online status|turn off activity status", "account.entry:0.32|settings.root:0.46|privacy.settings:0.64|privacy.activity_status:1.0", rules="온라인+상태+끄기|activity+status", avoid="content.history|security.login_history", desired_state="user_confirmation_required"),
        intent("read_receipts_control", "privacy.read_receipts", "읽음 표시 끄기|메시지 읽은 상태 숨기기|읽음 확인 비활성화|turn off read receipts|hide seen status", "account.entry:0.3|settings.root:0.44|privacy.settings:0.62|privacy.read_receipts:1.0", rules="읽음+표시+끄기|read+receipts", avoid="billing.receipt", desired_state="user_confirmation_required"),
        intent("contacts_sync_control", "privacy.contacts_sync", "연락처 동기화 끄기|주소록 업로드 중지|연락처 기반 친구 찾기 해제|turn off contact syncing|stop uploading contacts", "account.entry:0.28|settings.root:0.42|privacy.settings:0.6|privacy.contacts_sync:1.0", rules="연락처+동기화|contact+sync", avoid="account.phone.change|android.permission.manage", desired_state="user_confirmation_required"),
        intent("location_sharing_control", "privacy.location_sharing", "실시간 위치 공유 중지|내 위치 보내기|위치 공개 설정|stop sharing live location|manage location sharing", "account.entry:0.26|settings.root:0.4|privacy.settings:0.58|privacy.location_sharing:1.0", rules="위치+공유|location+sharing", avoid="settings.location|android.permission.manage", desired_state="user_confirmation_required"),
        intent("quiet_hours", "notification.quiet_hours", "밤에는 알림 끄기|방해 금지 시간 설정|알림 휴식 예약|set notification quiet hours|mute notifications at night", "account.entry:0.28|settings.root:0.44|notification.settings:0.64|notification.quiet_hours:1.0", rules="알림+시간+끄기|quiet+hours", avoid="communication.conversation.mute"),
        intent("text_size", "accessibility.text_size", "글자 크게 보기|앱 글꼴 크기 변경|텍스트 크기 키우기|increase text size|change app font size", "account.entry:0.26|settings.root:0.46|settings.accessibility:0.7|accessibility.text_size:1.0", rules="글자+크기|text+size"),
        intent("high_contrast", "accessibility.high_contrast", "고대비 화면 켜기|글자 대비 높이기|색상 대비 설정|enable high contrast|increase color contrast", "account.entry:0.24|settings.root:0.44|settings.accessibility:0.68|accessibility.high_contrast:1.0", rules="고대비+화면|high+contrast", desired_state="user_confirmation_required"),
        intent("account_logout", "auth.logout", "로그아웃하고 싶어|이 계정에서 나가기|접속 종료|sign out of my account|log me out", "account.entry:0.46|account.settings:0.62|auth.logout:1.0", rules="계정+로그아웃|sign+out", avoid="account.delete.entry|android.app.force_stop", desired_state="user_confirmation_required"),
        intent("account_switching", "account.switch", "다른 계정으로 전환|계정 바꾸기|프로필 전환|switch accounts|change active account", "account.entry:0.58|account.switch:1.0", rules="계정+전환|switch+account", avoid="account.add|auth.logout"),
        intent("password_change", "security.password", "현재 비밀번호 변경|계정 암호 바꾸기|새 비밀번호 설정|change my password|update account password", "account.entry:0.34|settings.root:0.46|account.security:0.68|security.password:1.0", rules="비밀번호+변경|change+password", avoid="security.password.reset|auth.password.create", desired_state="user_confirmation_required"),
        intent("subscription_pause", "subscription.pause", "구독 일시중지|멤버십 잠시 멈추기|다음 달 쉬기|pause my subscription|temporarily pause membership", "account.entry:0.26|subscription.manage:0.5|subscription.list:0.66|subscription.detail:0.82|subscription.pause:1.0", rules="구독+일시중지|pause+subscription", avoid="subscription.cancel.entry|finance.card.freeze", desired_state="user_confirmation_required"),
        intent("subscription_resume", "subscription.resume", "구독 다시 시작|멤버십 재개|일시중지 해제|resume my subscription|restart membership", "account.entry:0.26|subscription.manage:0.5|subscription.list:0.66|subscription.detail:0.82|subscription.resume:1.0", rules="구독+재개|resume+subscription", avoid="auth.signup.entry", desired_state="user_confirmation_required"),
        intent("automatic_renewal_control", "subscription.renewal", "구독 자동 갱신 끄기|다음 결제 자동 갱신 해제|정기 갱신 설정|turn off auto-renewal|manage subscription renewal", "account.entry:0.24|subscription.manage:0.48|subscription.list:0.64|subscription.detail:0.8|subscription.renewal:1.0", rules="자동+갱신|auto+renewal", avoid="media.autoplay|finance.recurring_transfer", desired_state="user_confirmation_required"),
        intent("billing_receipt", "billing.receipt", "영수증 보기|결제 청구서 다운로드|구매 인보이스|view payment receipt|download invoice", "account.entry:0.3|billing.manage:0.52|billing.purchase_history:0.7|billing.receipt:1.0", rules="결제+영수증|payment+receipt", avoid="finance.statements|insurance.certificate.issue"),
        intent("coupon_management", "billing.promo", "쿠폰함 열기|프로모션 코드 등록|할인 쿠폰 보기|open my coupons|redeem promo code", "account.entry:0.28|billing.manage:0.46|billing.promo:1.0", rules="쿠폰+보기|promo+code", avoid="travel.boarding_pass"),
        intent("refund_status", "billing.refund_status", "환불 진행 상황|환불 완료됐는지 확인|내 환불 내역|check refund status|view refund progress", "account.entry:0.28|billing.manage:0.44|billing.purchase_history:0.62|billing.refund_status:1.0", rules="환불+상태|refund+status", avoid="refund.entry|insurance.claim.status"),
        intent("order_details", "order.detail", "주문 상세 보기|구매한 상품 정보|주문번호 확인|view order details|show purchase details", "account.entry:0.28|order.list:0.62|order.detail:1.0", rules="주문+상세|order+details", avoid="travel.booking.detail"),
        intent("downloaded_content", "content.downloads", "다운로드한 콘텐츠 보기|오프라인 저장 목록|받아둔 영상|view downloaded content|open offline downloads", "account.entry:0.26|navigation.menu:0.36|content.downloads:1.0", rules="다운로드+콘텐츠|downloaded+content", avoid="settings.downloads|files.browser"),
        intent("saved_content", "content.saved", "저장한 게시물 보기|보관한 콘텐츠|나중에 볼 목록|view saved content|open bookmarks", "account.entry:0.32|navigation.menu:0.4|content.saved:1.0", rules="저장한+게시물|saved+content", avoid="commerce.wishlist|files.trash"),
        intent("privacy_visibility", "privacy.visibility", "프로필 공개 범위 바꾸기|계정을 비공개로|누가 내 게시물을 보는지|change profile visibility|make account private", "account.entry:0.28|settings.root:0.42|privacy.settings:0.62|privacy.visibility:1.0", rules="공개+범위|profile+visibility", avoid="privacy.activity_status", desired_state="user_confirmation_required"),
        intent("open_source_licenses", "legal.licenses", "오픈소스 라이선스 보기|사용한 소프트웨어 고지|제3자 라이선스|view open source licenses|third-party notices", "account.entry:0.2|settings.root:0.38|system.app_info:0.58|legal.licenses:1.0", rules="오픈소스+라이선스|open+source+licenses", avoid="legal.terms"),
        intent("reset_app_settings", "system.defaults", "앱 설정 초기화|모든 설정 기본값으로|설정 리셋|reset app settings|restore default settings", "account.entry:0.24|settings.root:0.62|system.defaults:1.0", rules="설정+초기화|reset+settings", avoid="android.app.clear_storage|account.delete.entry", desired_state="user_confirmation_required"),
        intent("email_notification_control", "notification.email", "이메일 알림 끄기|서비스 메일 수신 설정|메일로 알림 받지 않기|turn off email notifications|manage email alerts", "account.entry:0.26|settings.root:0.42|notification.settings:0.62|notification.email:1.0", rules="이메일+알림|email+notifications", avoid="account.email.change|marketing.settings", desired_state="user_confirmation_required"),
        intent("sms_notification_control", "notification.sms", "문자 알림 끄기|SMS 수신 설정|휴대폰 문자로 알림 받지 않기|turn off SMS notifications|manage text alerts", "account.entry:0.26|settings.root:0.42|notification.settings:0.62|notification.sms:1.0", rules="문자+알림|SMS+notifications", avoid="account.phone.change|communication.inbox", desired_state="user_confirmation_required"),
        intent("file_backup", "files.backup", "파일 자동 백업 켜기|문서 클라우드 백업|내 파일 백업 설정|enable file backup|back up documents to cloud", "account.entry:0.24|settings.root:0.4|files.browser:0.56|files.backup:1.0", rules="파일+백업|file+backup", avoid="content.drafts|settings.downloads", desired_state="user_confirmation_required"),
        intent("product_review", "commerce.review", "구매 후기 작성|상품 리뷰 남기기|별점 주기|write a product review|rate my purchase", "account.entry:0.24|order.list:0.42|order.detail:0.62|commerce.review:1.0", rules="상품+리뷰|product+review", avoid="content.comments|support.report", desired_state="user_confirmation_required"),
        intent("accessibility_captions", "accessibility.captions", "실시간 자막 켜기|접근성 자막 설정|청각 지원 캡션|enable live captions|accessibility caption settings", "account.entry:0.2|settings.root:0.42|settings.accessibility:0.68|accessibility.captions:1.0", rules="접근성+자막|accessibility+captions", avoid="media.captions", desired_state="user_confirmation_required"),
        intent("support_faq", "support.faq", "자주 묻는 질문 보기|FAQ 열기|도움말 문서 검색|open frequently asked questions|view help articles", "navigation.menu:0.28|support.help:0.62|support.faq:1.0", rules="자주+묻는+질문|frequently+asked"),
        intent("medical_appointments", "health.appointments", "병원 진료 예약|의사 예약 잡기|내원 날짜 선택|book a medical appointment|schedule doctor visit", "navigation.menu:0.3|health.appointments:1.0", rules="진료+예약|medical+appointment", avoid="travel.bookings", desired_state="user_confirmation_required"),
        intent("health_records", "health.records", "진료 기록 보기|검사 결과 확인|내 건강 기록|view medical records|check test results", "account.entry:0.3|navigation.menu:0.4|health.records:1.0", rules="진료+기록|medical+records", avoid="content.history|insurance.claim.status"),
    ]
)


def _merge_by_id(existing: list[dict[str, object]], additions: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    result = [dict(item) for item in existing]
    index = {str(item[key]): position for position, item in enumerate(result)}
    for item in additions:
        item_id = str(item[key])
        if item_id in index:
            result[index[item_id]] = item
        else:
            index[item_id] = len(result)
            result.append(item)
    return result


def _refine_existing_intents(intents: list[dict[str, object]]) -> None:
    """Remove broad legacy examples now owned by a more precise v2 intent."""

    remove_patterns = {
        "playback_settings": {"자동 재생 끄기", "turn off autoplay", "기본 화질 변경", "재생 속도 설정", "video quality settings"},
        "accessibility_settings": {"자막 설정", "captions"},
        "security_settings": {"비밀번호 변경", "change password"},
        "payment_method_change": {"manage cards"},
        "app_information": {"앱 정보"},
        "android_permission_manager": {"manage app permissions"},
    }
    extra_rules = {
        "email_registration": [("이메일", "계정", "만들"), ("create", "email"), ("email", "registration")],
        "change_email": [("계정", "이메일", "변경"), ("change", "account", "email")],
        "phone_registration": [("phone", "registration"), ("휴대폰", "가입")],
        "guest_access": [("without", "signing"), ("가입", "없이")],
        "onboarding_permission_setup": [("initial", "permissions"), ("초기", "권한")],
        "download_settings": [("저장", "화질"), ("download", "quality")],
        "insurance_claim_status": [("보험금", "진행상황"), ("claim", "status")],
        "insurance_claim_documents": [("청구", "필요서류"), ("보험금", "필요한지"), ("claim", "documents")],
        "health_insurance_certificate": [("health", "premium", "certificate"), ("건강보험", "납부", "확인서")],
        "insurance_certificate_issue": [("premium", "payment", "certificate"), ("보험료", "납입", "증명서")],
        "health_insurance_premium_payment": [("건강보험", "보험료"), ("health", "premium")],
        "android_notification_categories": [("알림", "유형"), ("notification", "categories")],
        "android_permission_manager": [("권한", "전체", "관리"), ("어떤", "앱", "권한")],
        "android_change_permission": [("위치", "권한", "바꾸"), ("change", "permission")],
        "android_special_access": [("고급", "앱", "권한"), ("special", "access")],
        "android_background_usage": [("배터리", "제한", "해제"), ("background", "usage")],
        "android_clear_app_storage": [("앱", "모든", "데이터"), ("clear", "app", "data")],
        "android_open_by_default": [("링크", "기본", "열기"), ("open", "links", "default")],
        "android_clear_defaults": [("기본값", "지우"), ("기본", "앱", "설정", "삭제"), ("clear", "defaults")],
        "caption_settings": [("캡션", "언어"), ("subtitle", "language")],
        "transaction_history": [("계좌", "거래", "내역"), ("transaction", "history")],
        "recurring_transfer_management": [("예약", "이체"), ("recurring", "transfer")],
        "report_lost_card": [("도난", "카드"), ("lost", "card")],
        "search_files": [("파일", "검색"), ("search", "files")],
        "accessibility_captions": [("접근성", "자막"), ("accessibility", "captions")],
        "file_backup": [("파일", "백업"), ("file", "backup")],
        "share_file": [("파일", "링크", "공유"), ("share", "file")],
        "contacts_sync_control": [
            ("연락처", "동기화", "끄"),
            ("주소록", "업로드", "중지"),
            ("contact", "sync", "off"),
            ("turn", "off", "contact", "sync"),
            ("stop", "uploading", "contacts"),
        ],
        "location_sharing_control": [
            ("위치", "공유", "중지"),
            ("위치", "공유", "끄"),
            ("stop", "sharing", "location"),
            ("turn", "off", "location", "sharing"),
        ],
        "refund": [("환불",)],
        "refund_status": [("환불", "상태"), ("환불", "진행"), ("환불", "완료"), ("환불", "내역"), ("refund", "status")],
    }
    remove_goal_rules = {
        "email_registration": {("email", "account")},
        "health_insurance_certificate": {("premium", "certificate")},
    }
    rule_scores = {
        "refund": 0.80,
        "refund_status": 0.999,
        "change_email": 0.999,
        "android_clear_defaults": 0.999,
        "insurance_certificate_issue": 0.999,
        "health_insurance_certificate": 0.999,
        "contacts_sync_control": 1.0,
        "location_sharing_control": 1.0,
    }
    add_patterns = {
        "playback_settings": [
            "플레이어 설정",
            "동영상 재생 환경",
            "player preferences",
            "video playback controls",
        ]
    }
    # Natural goals frequently describe a consequence instead of repeating a
    # visible menu label (for example, "다음 달부터 돈이 빠져나가지 않게" rather
    # than "구독 해지").  These compact conjunctions model those reusable
    # semantic distinctions.  They intentionally avoid benchmark sentences,
    # screen labels, app names, and single broad keywords: each rule combines
    # the object, scope/state, and desired outcome needed to separate a close
    # sibling intent.
    semantic_disambiguation_rules: dict[str, list[tuple[tuple[str, ...], float]]] = {
        "notification_control": [
            (("서비스", "소식", "받"), 1.0),
            (("앱", "소식", "골라"), 1.0),
        ],
        "android_app_notifications": [
            (("android", "silence", "app"), 1.0),
            (("android", "pop", "one", "app"), 1.0),
            (("운영체제", "앱", "팝업"), 1.0),
        ],
        "storage_management": [
            (("내려받", "용량", "정리"), 1.0),
            (("오프라인", "용량", "관리"), 1.0),
        ],
        "android_storage_cache": [
            (("시스템", "공간", "확인"), 1.0),
            (("폰", "프로그램", "공간"), 1.0),
        ],
        "data_usage_settings": [
            (("앱", "통신량", "덜"), 1.0),
            (("앱", "자체", "데이터", "줄"), 1.0),
        ],
        "android_app_data_usage": [
            (("운영체제", "앱", "셀룰러"), 1.0),
            (("폰", "설정", "앱", "통신"), 1.0),
        ],
        "data_deletion": [
            (("회사", "보관", "활동", "지우"), 1.0),
            (("회사", "서버", "검색", "활동"), 1.0),
            (("서비스", "활동", "흔적", "지우"), 1.0),
        ],
        "android_clear_app_storage": [
            (("휴대전화", "로컬", "자료", "비우"), 1.0),
            (("앱", "로컬", "초기", "비우"), 1.0),
        ],
        "app_information": [
            (("서비스", "버전", "만든", "곳"), 1.0),
            (("앱", "안", "버전", "개발"), 1.0),
        ],
        "android_app_info": [
            (("운영체제", "권한", "배터리"), 1.0),
            (("설치", "프로그램", "시스템", "상세"), 1.0),
        ],
        "onboarding_permission_setup": [
            (("처음", "시작", "기능", "접근"), 1.0),
            (("초기", "기능", "접근", "확인"), 1.0),
        ],
        "android_app_permissions": [
            (("카메라", "연락처", "폰", "설정"), 1.0),
            (("앱", "접근", "시스템", "검토"), 1.0),
        ],
        "subscription_management": [
            (("채널", "새", "영상", "모음"), 1.0),
            (("paid", "plan", "charging", "month"), 1.0),
            (("유료", "멤버십", "혜택"), 1.0),
        ],
        "subscription_cancellation": [
            (("다음", "달", "요금", "빠져나가지"), 1.0),
            (("요금", "더", "나가지", "절차"), 1.0),
        ],
        "automatic_renewal_control": [
            (("멤버십", "기간", "끝", "이어"), 1.0),
            (("기간", "끝", "저절로"), 1.0),
        ],
        "automatic_payment_management": [
            (("반복", "출금", "확인"), 1.0),
            (("등록", "반복", "출금"), 1.0),
        ],
        "refund": [
            (("물건", "값", "돌려받", "신청"), 1.0),
            (("구매", "대금", "돌려받", "시작"), 1.0),
        ],
        "refund_status": [
            (("already", "asked", "money", "track"), 1.0),
            (("money", "back", "track", "now"), 1.0),
        ],
        "insurance_surrender_value": [
            (("보험", "끝", "예상", "금액"), 1.0),
            (("보험", "종료", "돌려받", "금액"), 1.0),
        ],
        "change_email": [
            (("계정", "메일", "교체"), 1.0),
            (("새", "메일", "계정", "식별"), 1.0),
        ],
        "email_registration": [
            (("새", "계정", "메일", "시작"), 1.0),
            (("소셜", "대신", "메일"), 1.0),
        ],
        "email_notification_control": [
            (("서비스", "안내", "메일", "조절"), 1.0),
            (("계정", "그대로", "메일", "오"), 1.0),
        ],
        "change_phone_number": [
            (("기존", "휴대폰", "새", "번호"), 1.0),
            (("로그인", "휴대폰", "번호", "바꾸"), 1.0),
        ],
        "phone_registration": [
            (("처음", "계정", "휴대폰", "인증"), 1.0),
            (("신규", "가입", "전화", "인증"), 1.0),
        ],
        "sms_notification_control": [
            (("안내", "문자", "오", "설정"), 1.0),
            (("계정", "그대로", "문자", "수신"), 1.0),
        ],
        "password_change": [
            (("현재", "암호", "알", "교체"), 1.0),
            (("기존", "비밀번호", "새", "바꾸"), 1.0),
        ],
        "password_reset": [
            (("기억나지", "로그인", "암호"), 1.0),
            (("로그인", "암호", "인증", "다시", "만들"), 1.0),
        ],
        "account_registration": [
            (("신규", "계정", "처음", "암호"), 1.0),
            (("가입", "절차", "암호", "정"), 1.0),
        ],
        "share_file": [
            (("coworker", "document", "cloud", "drive"), 1.0),
            (("초대", "접근", "권한", "부여"), 1.0),
        ],
        "share_content": [
            (("게시물", "친구", "링크", "보내"), 1.0),
            (("보고", "콘텐츠", "링크", "공유"), 1.0),
        ],
        "location_sharing_control": [
            (("대화", "상대", "움직", "위치"), 1.0),
            (("일정", "시간", "위치", "보여"), 1.0),
        ],
        "travel_bookings": [
            (("비행편", "예약번호", "일정"), 1.0),
            (("항공", "예약", "여정", "모아"), 1.0),
        ],
        "medical_appointments": [
            (("병원", "방문", "날짜"), 1.0),
            (("진료", "시간", "새로", "잡"), 1.0),
        ],
        "recurring_transfer_management": [
            (("매달", "계좌", "송금", "일정"), 1.0),
            (("같은", "날", "이체", "관리"), 1.0),
        ],
        "travel_booking_cancellation": [
            (("항공", "여정", "취소"), 1.0),
            (("비행", "예매", "취소"), 1.0),
        ],
        "activity_history": [
            (("예전", "재생", "영상", "목록"), 1.0),
            (("전에", "봤", "콘텐츠", "다시"), 1.0),
        ],
        "login_history": [
            (("언제", "기기", "접속"), 1.0),
            (("지난달", "접속", "시간순"), 1.0),
        ],
        "transaction_history": [
            (("계좌", "들어오", "나간", "돈"), 1.0),
            (("돈", "흐름", "날짜별"), 1.0),
        ],
        "purchase_history": [
            (("쇼핑", "결제", "물건", "찾"), 1.0),
            (("구매", "물건", "영수증", "모아"), 1.0),
        ],
        "health_records": [
            (("병원", "검사", "결과", "진료"), 1.0),
            (("과거", "진료", "내용", "모아"), 1.0),
        ],
        "active_sessions": [
            (("지금", "계정", "열려", "기기"), 1.0),
            (("현재", "로그인", "기기", "만"), 1.0),
        ],
        "caption_settings": [
            (("영상", "번역", "글", "언어"), 1.0),
            (("재생", "영상", "표시", "언어"), 1.0),
        ],
        "accessibility_captions": [
            (("speech", "device", "text", "not", "video"), 1.0),
            (("anything", "playing", "device", "text"), 1.0),
        ],
        "android_clear_app_cache": [
            (("임시", "파일", "운영체제", "비우"), 1.0),
            (("로그인", "남기", "임시", "파일"), 1.0),
        ],
        "account_deletion": [
            (("회원", "자격", "전체", "끝"), 1.0),
            (("서비스", "회원", "전부", "종료"), 1.0),
        ],
        "delete_content": [
            (("프로필", "유지", "게시글", "한"), 1.0),
            (("게시물", "한", "건", "없애"), 1.0),
        ],
        "delete_conversation": [
            (("채팅", "내역", "치우"), 1.0),
            (("채팅", "내역", "치울"), 1.0),
            (("계정", "아니", "대화", "기록", "지우"), 1.0),
        ],
        "browse_files": [
            (("선택", "문서", "휴지통"), 1.0),
            (("파일", "한", "개", "휴지통"), 1.0),
        ],
        "card_management": [
            (("bank", "card", "limits", "loss"), 1.0),
            (("은행", "카드", "한도", "분실"), 1.0),
        ],
        "payment_method_change": [
            (("서비스", "다음", "결제", "카드", "다른"), 1.0),
            (("구매", "사용", "결제", "수단", "바꾸"), 1.0),
        ],
        "freeze_card": [
            (("은행", "카드", "잠시", "결제", "불가"), 1.0),
            (("카드", "분실", "아니", "일시", "잠그"), 1.0),
        ],
        "support_contact": [
            (("상담원", "실시간", "이야기"), 1.0),
            (("앱", "오류", "운영팀", "문의"), 1.0),
            (("왼쪽", "목록", "도움말"), 1.0),
        ],
        "message_inbox": [
            (("다른", "이용자", "보낸", "대화"), 1.0),
            (("고객센터", "말고", "받은", "메시지"), 1.0),
        ],
        "compose_message": [
            (("친구", "새", "대화", "먼저"), 1.0),
            (("상담", "아니", "친구", "메시지"), 1.0),
        ],
        "two_factor_verification": [
            (("로그인", "문자", "추가", "확인", "번호"), 1.0),
            (("추가", "인증", "코드", "입력"), 1.0),
        ],
        "edit_profile": [
            (("이름", "소개", "고치"), 1.0),
            (("공개", "범위", "아니", "프로필", "수정"), 1.0),
        ],
        "privacy_control": [
            (("활동", "누구", "보이", "제한"), 1.0),
            (("이름", "수정", "아니", "공개", "제한"), 1.0),
        ],
        "autoplay_settings": [
            (("영상", "끝", "다음", "저절로", "시작"), 1.0),
            (("다음", "영상", "자동", "시작"), 1.0),
        ],
        "playback_settings": [
            (("재생", "품질", "속도", "전체"), 1.0),
            (("자동", "넘김", "아니", "재생", "환경"), 1.0),
        ],
        "support_faq": [
            (("자주", "문제", "해결", "글"), 1.0),
            (("연락", "전", "도움말", "문서"), 1.0),
        ],
        "saved_content": [
            (("나중", "보", "보관", "글", "영상"), 1.0),
            (("상품", "아니", "저장", "콘텐츠"), 1.0),
        ],
        "wishlist": [
            (("구매", "고민", "표시", "상품"), 1.0),
            (("읽", "글", "아니", "상품", "모아"), 1.0),
        ],
        "billing_receipt": [
            (("결제", "주문", "증빙", "문서"), 1.0),
            (("구매", "증빙", "내려받"), 1.0),
        ],
        "financial_statements": [
            (("이번", "달", "카드", "이용", "금액", "청구"), 1.0),
            (("카드", "합산", "청구", "문서"), 1.0),
        ],
        "marketing_notification_control": [
            (("광고성", "혜택", "소식", "그만"), 1.0),
            (("쿠폰", "아니", "광고", "받"), 1.0),
        ],
        "signup_optional_consent": [
            (("가입", "필요하지", "조항"), 1.0),
            (("가입", "선택", "조항", "읽"), 1.0),
        ],
    }
    for item in intents:
        intent_id = str(item.get("intent_id", ""))
        blocked = remove_patterns.get(intent_id)
        if not blocked:
            blocked = set()
        item["patterns"] = [value for value in item.get("patterns", []) if str(value) not in blocked]
        for value in add_patterns.get(intent_id, []):
            if value not in item["patterns"]:
                item["patterns"].append(value)
        existing_terms = {
            tuple(str(term) for term in rule.get("all_of", []))
            for rule in item.get("goal_rules", [])
        }
        rules = item.setdefault("goal_rules", [])
        blocked_rule_terms = remove_goal_rules.get(intent_id, set())
        rules[:] = [
            rule
            for rule in rules
            if tuple(str(term) for term in rule.get("all_of", [])) not in blocked_rule_terms
        ]
        target_score = rule_scores.get(intent_id, 0.995)
        for terms in extra_rules.get(intent_id, []):
            existing = next(
                (rule for rule in rules if tuple(str(term) for term in rule.get("all_of", [])) == terms),
                None,
            )
            if existing is not None:
                existing["score"] = target_score
                continue
            rules.append({"all_of": list(terms), "score": target_score})
        for terms, score in semantic_disambiguation_rules.get(intent_id, []):
            existing = next(
                (rule for rule in rules if tuple(str(term) for term in rule.get("all_of", [])) == terms),
                None,
            )
            if existing is not None:
                existing["score"] = score
                continue
            rules.append({"all_of": list(terms), "score": score})
        for rule_map in (GENERALIZED_GOAL_RULES, RECOVERY_AND_EDGE_GOAL_RULES):
            for terms, score in rule_map.get(intent_id, []):
                existing = next(
                    (rule for rule in rules if tuple(str(term) for term in rule.get("all_of", [])) == terms),
                    None,
                )
                if existing is not None:
                    existing["score"] = score
                    continue
                rules.append({"all_of": list(terms), "score": score})
        terminal_overrides = GOAL_TERMINAL_OVERRIDES.get(intent_id, {})
        for rule in rules:
            terms = tuple(str(term) for term in rule.get("all_of", []))
            terminal_function = terminal_overrides.get(terms, "")
            if terminal_function:
                rule["terminal_function"] = terminal_function
            else:
                rule.pop("terminal_function", None)


def _enrich_existing_functions(functions: list[dict[str, object]]) -> None:
    for item in functions:
        function_id = str(item.get("function_id", ""))
        changing = bool(item.get("state_changing", False))
        item.setdefault("scope", "in_app")
        item.setdefault("node_kind", "state_change" if changing else ("destination" if item.get("terminal") else "hub"))
        item.setdefault("stop_policy", "before_action" if changing else "on_destination_screen")
        if (changing or str(item.get("risk_level", "")) == "high") and str(item.get("stop_policy")) not in {
            "before_action",
            "before_activation",
            "stop_before_action",
            "user_confirmation",
            "user_only",
        }:
            item["stop_policy"] = "before_action"
        item.setdefault("role_hints", ["button", "menuitem", "tab"])
        if changing and not item.get("risk_cues"):
            item["risk_cues"] = RISK_CUE_PATCHES.get(
                function_id,
                {"consequence": ["사용자 상태가 변경됨", "changes user state"]},
            )
        concepts = SEMANTIC_CONCEPT_PATCHES.get(function_id)
        if concepts:
            item["semantic_concepts"] = list(dict.fromkeys(concepts))
        terminal_concepts = SEMANTIC_TERMINAL_CONCEPT_PATCHES.get(function_id)
        if terminal_concepts:
            item["semantic_terminal_concepts"] = list(dict.fromkeys(terminal_concepts))
        if function_id == "support.chat":
            # Opening the support conversation is reversible navigation.  The
            # actual message submission remains a separate user-controlled
            # action and is never auto-clicked.
            item["risk_level"] = "low"
            item["automation_policy"] = "safe_navigation"
            item["state_changing"] = False
            item["stop_policy"] = "on_destination_screen"


# Cross-generation semantic rules for official Android journeys.  These live
# in the materializer instead of a generation-specific pack because the
# underlying user language (one app's notification controls, backup contents,
# emergency information) spans the v2 Android ontology and v4 system packs.
# Keep the cues consequence-oriented and compositional; no frozen fixture
# sentence or case identifier belongs in production data.
PRODUCTIVITY_SYSTEM_GOAL_RULES: dict[str, tuple[tuple[str, ...], ...]] = {
    "android_app_notifications": (
        ("notification controls", "one", "app"),
        ("noisy", "app", "notification"),
        ("앱 하나", "알림", "제어"),
    ),
    "android_notification_categories": (
        ("메신저", "단체방", "알림 종류"),
        ("notification type", "one conversation", "app"),
        ("notification category", "specific", "app"),
    ),
    "android_change_permission": (
        ("camera permission", "app", "decide"),
        ("permission", "app", "decide its access"),
        ("앱", "카메라 권한", "허용 여부"),
    ),
    "v4_android_backup_device_backup": (
        ("phone", "backs up", "google account"),
        ("device backup", "google account", "control"),
        ("휴대전화", "구글 계정", "백업 여부"),
    ),
    "v4_android_backup_backup_account": (
        ("백업", "저장되는", "구글 계정", "다른 계정"),
        ("backup", "stored", "google account", "switch account"),
        ("switch", "google account", "backup", "stored"),
    ),
    "v4_android_backup_restore_device": (
        ("during setup", "earlier phone backup", "restore"),
        ("setup", "choose", "previous backup", "restore"),
        ("초기 설정", "이전 기기", "백업", "복원"),
    ),
    "v4_android_backup_backup_details": (
        ("백업되는 앱 데이터", "통화 기록", "자세히"),
        ("backup contents", "app data", "call history"),
        ("backup details", "data types", "review"),
    ),
    "v4_android_backup_manual_backup": (
        ("fresh phone backup", "now", "final upload"),
        ("back up now", "device", "confirm"),
        ("지금", "새 백업", "최종", "업로드"),
    ),
    "v4_android_backup_transfer_setup": (
        ("새 휴대전화", "초기 설정", "기존 기기", "자료를 옮"),
        ("new phone setup", "old device", "transfer data"),
    ),
    "v4_android_safety_emergency_info": (
        ("잠금 화면", "혈액형", "알레르기"),
        ("lock screen", "blood type", "allergy"),
        ("emergency information", "medical", "lock screen"),
    ),
    "v4_android_safety_emergency_contacts": (
        ("emergency", "listed", "contacted"),
        ("emergency contacts", "review", "listed"),
        ("긴급", "연락될 사람", "목록"),
    ),
    "v4_android_safety_sos": (
        ("긴급 상황", "전원 버튼", "구조 요청"),
        ("emergency", "power button", "sos"),
        ("power button", "call for help", "settings"),
        ("power button", "call for help", "emergency"),
    ),
    "v4_android_safety_safety_check": (
        ("혼자", "정해진 시간", "안전 여부"),
        ("safety check", "scheduled time", "check in"),
        ("walking alone", "timer", "safety"),
    ),
    "v4_android_safety_crisis_alerts": (
        ("safety app", "nearby", "public crises"),
        ("crisis alerts", "nearby", "safety"),
        ("주변", "재난", "위기 알림"),
    ),
}


def _set_productivity_system_goal_rules(payload: dict[str, object]) -> None:
    """Publish reviewed rules without mutating generation-owned intents.

    Supplemental rules are indexed by the runtime exactly like intent-local
    rules, but remain a separate source-data layer.  This lets v2 Android and
    v4 system intents share consequence language while preserving the v4
    pack's independently validated and idempotent definitions.
    """

    intents = payload.get("intents", [])
    if not isinstance(intents, list):
        raise ValueError("catalog intents must be a list")
    by_id = {str(item.get("intent_id", "")): item for item in intents}
    missing = set(PRODUCTIVITY_SYSTEM_GOAL_RULES).difference(by_id)
    if missing:
        raise ValueError(
            "productivity/system goal rules reference unknown intents: "
            + ", ".join(sorted(missing))
        )
    payload["supplemental_goal_rules"] = [
        {
            "intent_id": intent_id,
            "all_of": list(terms),
            "score": 1.0,
            "source_pack": "official_productivity_system",
        }
        for intent_id, cue_groups in PRODUCTIVITY_SYSTEM_GOAL_RULES.items()
        for terms in cue_groups
    ]


def _build_materialized_catalog(
    source_payload: dict[str, object],
    equivalence_payload: dict[str, object],
) -> dict[str, object]:
    # Reject partial/tampered V16 input before the normal source reconstruction
    # removes generation-owned IDs.  A fully materialized V16 pair is accepted
    # and then rebuilt from its exact V15 projection.
    source_equivalence_v15 = project_equivalence_to_v15(equivalence_payload)
    validation_source = strip_alias_context_overrides(source_payload)
    expected_v16_functions = {str(item["function_id"]) for item in V16_FUNCTIONS}
    expected_v16_intents = {str(item["intent_id"]) for item in V16_INTENTS}
    present_v16_functions = {
        str(item.get("function_id", ""))
        for item in validation_source.get("functions", [])
        if str(item.get("function_id", "")) in expected_v16_functions
    }
    present_v16_intents = {
        str(item.get("intent_id", ""))
        for item in validation_source.get("intents", [])
        if str(item.get("intent_id", "")) in expected_v16_intents
    }
    v16_metadata = {
        "official_sources_v16",
        "source_documents_v16",
        "semantic_equivalence_v16",
        "refinement_v16",
    }
    present_v16_metadata = v16_metadata.intersection(validation_source)
    has_any_v16 = bool(
        present_v16_functions or present_v16_intents or present_v16_metadata
    )
    has_complete_v16 = (
        present_v16_functions == expected_v16_functions
        and present_v16_intents == expected_v16_intents
        and present_v16_metadata == v16_metadata
    )
    if has_any_v16 and not has_complete_v16:
        raise ValueError("partial V16 materialization input")

    if has_complete_v16:
        merge_v16_with_base(validation_source, equivalence_payload)
        regenerated = apply_alias_context_overrides(validation_source)
        if regenerated != source_payload:
            raise ValueError("V16 alias-context override materialization differs")
        return regenerated

    payload = validation_source
    # Reconstruct the v3 base before every materialization so reviewed v4-v16
    # source changes replace, rather than silently preserve, older generated
    # definitions.  Later merges then restore each generation in order; v4's
    # cross-generation collision filtering must never depend on later data.
    v4_function_ids = {str(item["function_id"]) for item in V4_FUNCTIONS}
    v4_intent_ids = {str(item["intent_id"]) for item in V4_INTENTS}
    v5_function_ids = {str(item["function_id"]) for item in V5_FUNCTIONS}
    v5_intent_ids = {str(item["intent_id"]) for item in V5_INTENTS}
    v6_function_ids = {str(item["function_id"]) for item in V6_FUNCTIONS}
    v6_intent_ids = {str(item["intent_id"]) for item in V6_INTENTS}
    v7_function_ids = {str(item["function_id"]) for item in V7_FUNCTIONS}
    v7_intent_ids = {str(item["intent_id"]) for item in V7_INTENTS}
    v8_function_ids = {str(item["function_id"]) for item in V8_FUNCTIONS}
    v8_intent_ids = {str(item["intent_id"]) for item in V8_INTENTS}
    v9_function_ids = {str(item["function_id"]) for item in V9_FUNCTIONS}
    v9_intent_ids = {str(item["intent_id"]) for item in V9_INTENTS}
    v10_function_ids = {str(item["function_id"]) for item in V10_FUNCTIONS}
    v10_intent_ids = {str(item["intent_id"]) for item in V10_INTENTS}
    v11_function_ids = {str(item["function_id"]) for item in V11_FUNCTIONS}
    v11_intent_ids = {str(item["intent_id"]) for item in V11_INTENTS}
    v12_function_ids = {str(item["function_id"]) for item in V12_FUNCTIONS}
    v12_intent_ids = {str(item["intent_id"]) for item in V12_INTENTS}
    v13_function_ids = {str(item["function_id"]) for item in V13_FUNCTIONS}
    v13_intent_ids = {str(item["intent_id"]) for item in V13_INTENTS}
    v14_function_ids = {str(item["function_id"]) for item in V14_FUNCTIONS}
    v14_intent_ids = {str(item["intent_id"]) for item in V14_INTENTS}
    v15_function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    v15_intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}
    v16_function_ids = {str(item["function_id"]) for item in V16_FUNCTIONS}
    v16_intent_ids = {str(item["intent_id"]) for item in V16_INTENTS}
    payload["functions"] = [
        item
        for item in payload.get("functions", [])
        if str(item.get("function_id", ""))
        not in v4_function_ids | v5_function_ids | v6_function_ids | v7_function_ids | v8_function_ids | v9_function_ids | v10_function_ids | v11_function_ids | v12_function_ids | v13_function_ids | v14_function_ids | v15_function_ids | v16_function_ids
    ]
    payload["intents"] = [
        item
        for item in payload.get("intents", [])
        if str(item.get("intent_id", ""))
        not in v4_intent_ids | v5_intent_ids | v6_intent_ids | v7_intent_ids | v8_intent_ids | v9_intent_ids | v10_intent_ids | v11_intent_ids | v12_intent_ids | v13_intent_ids | v14_intent_ids | v15_intent_ids | v16_intent_ids
    ]
    payload.pop("official_sources_v4", None)
    payload.pop("official_sources_v5", None)
    payload.pop("official_sources_v6", None)
    payload.pop("official_sources_v7", None)
    payload.pop("official_sources_v8", None)
    payload.pop("official_sources_v9", None)
    payload.pop("official_sources_v10", None)
    payload.pop("official_sources_v11", None)
    payload.pop("official_sources_v12", None)
    payload.pop("source_document_v12", None)
    payload.pop("official_sources_v13", None)
    payload.pop("source_document_v13", None)
    payload.pop("official_sources_v14", None)
    payload.pop("source_document_v14", None)
    payload.pop("official_sources_v15", None)
    payload.pop("source_document_v15", None)
    payload.pop("semantic_equivalence_v15", None)
    payload.pop("official_sources_v16", None)
    payload.pop("source_documents_v16", None)
    payload.pop("semantic_equivalence_v16", None)
    payload.pop("refinement_v16", None)
    payload["catalog_version"] = "3.0.0"
    payload["description"] = (
        "ExitGuide cross-app function ontology v3: general application menus, Android system settings, "
        "state-aware destinations, user-confirmed high-risk actions, and long-tail communication, mobility, "
        "telecom, productivity, public-service, IoT, media, work, finance, safety, and health functions."
    )
    payload["semantic_lexicon"] = SEMANTIC_LEXICON
    payload["functions"] = _merge_by_id(payload.get("functions", []), FUNCTIONS, "function_id")
    _enrich_existing_functions(payload["functions"])
    payload["intents"] = _merge_by_id(payload.get("intents", []), INTENTS, "intent_id")
    _refine_existing_intents(payload["intents"])

    # Validate the independently reviewed v3 pack against the v2 materialized
    # base.  Filtering v3 IDs first keeps this migration deterministic and
    # idempotent when it is run against an already-materialized v3 catalog.
    v3_function_ids = {str(item["function_id"]) for item in V3_FUNCTIONS}
    v3_intent_ids = {str(item["intent_id"]) for item in V3_INTENTS}
    validation_base = dict(payload)
    validation_base["functions"] = [
        item for item in payload["functions"] if str(item.get("function_id", "")) not in v3_function_ids
    ]
    validation_base["intents"] = [
        item for item in payload["intents"] if str(item.get("intent_id", "")) not in v3_intent_ids
    ]
    validate_v3_data(validation_base)
    payload["functions"] = _merge_by_id(payload["functions"], list(V3_FUNCTIONS), "function_id")
    payload["intents"] = _merge_by_id(payload["intents"], list(V3_INTENTS), "intent_id")
    payload = merge_v4_with_base(payload)
    _set_productivity_system_goal_rules(payload)
    payload = merge_v5_with_base(payload)
    payload = merge_v6_with_base(payload)
    payload = merge_v7_with_base(payload)
    payload = merge_v8_with_base(payload)
    payload = merge_v9_with_base(payload)
    payload = merge_v10_with_base(payload)
    payload = merge_v11_with_base(payload)
    payload = merge_v12_with_base(payload)
    payload = merge_v13_with_base(payload)
    # V16 is the final append-only source merge and owns the final catalog
    # version/description. The generated collision overlay below may add only
    # derived contexts; the metadata guard ensures it cannot replace V15.
    payload = merge_v14_with_base(payload)
    payload = merge_v15_with_base(payload)
    payload = merge_v16_with_base(payload, source_equivalence_v15)
    payload = apply_alias_context_overrides(payload)
    if (
        payload.get("catalog_version") != CATALOG_V16_VERSION
        or payload.get("description") != CATALOG_V16_DESCRIPTION
    ):
        raise ValueError("V16 materialization metadata drifted after the final merge")

    return payload


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _temporary_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="wb",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(_json_bytes(payload))
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)


def _replace_pair_atomically(
    catalog_path: Path,
    catalog_payload: dict[str, object],
    equivalence_path: Path,
    equivalence_payload: dict[str, object],
) -> None:
    """Validate first, then replace both files with rollback on ordinary errors."""

    catalog_before = catalog_path.read_bytes()
    equivalence_before = equivalence_path.read_bytes()
    catalog_after = _json_bytes(catalog_payload)
    equivalence_after = _json_bytes(equivalence_payload)
    if catalog_before == catalog_after and equivalence_before == equivalence_after:
        return
    catalog_temp = _temporary_json(catalog_path, catalog_payload)
    equivalence_temp = _temporary_json(equivalence_path, equivalence_payload)
    try:
        os.replace(equivalence_temp, equivalence_path)
        os.replace(catalog_temp, catalog_path)
    except BaseException:
        rollback_catalog = catalog_path.with_name(f".{catalog_path.name}.rollback")
        rollback_equivalence = equivalence_path.with_name(
            f".{equivalence_path.name}.rollback"
        )
        rollback_catalog.write_bytes(catalog_before)
        rollback_equivalence.write_bytes(equivalence_before)
        os.replace(rollback_equivalence, equivalence_path)
        os.replace(rollback_catalog, catalog_path)
        raise
    finally:
        catalog_temp.unlink(missing_ok=True)
        equivalence_temp.unlink(missing_ok=True)


def materialize_catalog(
    catalog_path: Path = CATALOG_PATH,
    equivalence_path: Path | None = None,
) -> dict[str, object]:
    """Materialize and publish a coherent V16 catalog/equivalence pair."""

    catalog_path = Path(catalog_path).resolve()
    equivalence_path = (
        catalog_path.with_name("function-equivalence.v1.json")
        if equivalence_path is None
        else Path(equivalence_path).resolve()
    )
    source_payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    source_equivalence = json.loads(equivalence_path.read_text(encoding="utf-8"))
    payload = _build_materialized_catalog(source_payload, source_equivalence)
    equivalence_payload = merge_equivalence_with_v16(
        source_equivalence,
        payload,
    )
    _replace_pair_atomically(
        catalog_path,
        payload,
        equivalence_path,
        equivalence_payload,
    )
    return {
        "catalog_version": payload["catalog_version"],
        "functions": len(payload["functions"]),
        "intents": len(payload["intents"]),
        "catalog_path": str(catalog_path),
        "equivalence_path": str(equivalence_path),
    }


def main() -> None:
    result = materialize_catalog(CATALOG_PATH)

    print(
        f"catalog={result['catalog_path']} version={result['catalog_version']} "
        f"functions={result['functions']} intents={result['intents']}"
    )


if __name__ == "__main__":
    main()
