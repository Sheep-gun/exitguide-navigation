from __future__ import annotations

"""Reviewed v7 long-tail ontology for app-agnostic Android navigation.

The layer deliberately stores semantic destinations instead of package names,
coordinates, screenshots, or recorded app paths.  All source evidence is
first-party product/help documentation opened on the collection date.  Any
consequential action remains user-owned and the agent stops before the final
button.
"""

import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlparse

from navigation_catalog_v6_data import (
    F,
    G,
    FeatureSeed,
    GroupSeed,
    _build_feature as _v6_build_feature,
    _build_intent as _v6_build_intent,
    _build_root as _v6_build_root,
    _cue_key,
    _runtime_pattern_key,
    _rule_signature,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
CATALOG_V7_VERSION = "7.0.0"
COLLECTED_ON = "2026-07-30"
CATALOG_V7_DESCRIPTION = (
    "ExitGuide cross-app function ontology v7: app-agnostic long-tail destinations "
    "for dating safety, digital libraries, beauty and wellness booking, childcare "
    "family portals, electronic signature, creator monetization, crypto assets, "
    "and sports-team coordination; final actions remain user-owned."
)


def _source(publisher: str, title: str, url: str) -> dict[str, object]:
    return {
        "publisher": publisher,
        "title": title,
        "url": url,
        "collected_on": COLLECTED_ON,
        "evidence_level": "official_primary",
        "verified_status": 200,
        "verification_method": "official page opened with web reader",
    }


OFFICIAL_SOURCES: dict[str, dict[str, object]] = {
    # Dating discovery and safety.
    "tinder_discovery": _source("Tinder Help", "Discovery Settings", "https://www.help.tinder.com/hc/en-us/articles/115003340963-Discovery-Settings"),
    "tinder_unmatch": _source("Tinder Help", "Unmatching someone", "https://www.help.tinder.com/hc/en-us/articles/115003360106-Unmatching-someone"),
    "tinder_photo_verify": _source("Tinder Help", "Photo Verification", "https://www.help.tinder.com/hc/en-us/articles/360034941812-Photo-Verification"),
    "tinder_id_verify": _source("Tinder Help", "ID + Photo Verification", "https://www.help.tinder.com/hc/en-us/articles/19868368795917-ID-Photo-Verification"),
    "tinder_safety": _source("Tinder Safety Center", "How to Unmatch", "https://policies.tinder.com/web/safety-center/tools/unmatch/intl/en/"),
    # Digital libraries and reading.
    "libby_navigation": _source("Libby Help", "Navigating the app", "https://help.libbyapp.com/en-us/6011.htm"),
    "libby_getting_started": _source("Libby Help", "Getting started with Libby", "https://help.libbyapp.com/en-us/6103.htm"),
    "libby_borrow": _source("Libby Help", "Borrowing, renewing, and returning", "https://help.libbyapp.com/en-us/categories/borrowing-renewing-returning.htm"),
    "libby_holds": _source("Libby Help", "Acting on an available hold", "https://help.libbyapp.com/en-us/6198.htm"),
    "libby_cards": _source("Libby Help", "Switching between cards from the same library", "https://help.libbyapp.com/en-us/6000.htm"),
    "libby_reset": _source("Libby Help", "When should I sign out of Libby?", "https://help.libbyapp.com/en-us/6004.htm"),
    "libby_downloads": _source("Libby Help", "Managing your download settings", "https://help.libbyapp.com/en-us/6005.htm"),
    "libby_content_controls": _source("Libby Help", "Getting started with content controls", "https://help.libbyapp.com/en-us/6315.htm"),
    # Beauty and wellness appointment systems.
    "fresha_calendar": _source("Fresha Help Center", "Calendar and schedule", "https://www.fresha.com/help-center/knowledge-base/calendar"),
    "fresha_reschedule": _source("Fresha Help Center", "Reschedule appointments", "https://www.fresha.com/help-center/knowledge-base/calendar/28-reschedule-appointments"),
    "fresha_online_booking": _source("Fresha Help Center", "Manage online bookings settings", "https://www.fresha.com/help-center/knowledge-base/calendar/22-manage-online-bookings-settings"),
    # Childcare family portals.
    "brightwheel_guardian": _source("Brightwheel Help Center", "Overview for parents, family, and approved pickups", "https://help.mybrightwheel.com/en/articles/2165917-overview-of-how-to-use-brightwheel-as-a-parent-family-or-approved-pickup"),
    "brightwheel_checkin": _source("Brightwheel Help Center", "Locate and edit your check-in code", "https://help.mybrightwheel.com/en/articles/942420-locate-and-edit-your-check-in-code"),
    "brightwheel_messages": _source("Brightwheel Help Center", "Message your childcare provider", "https://help.mybrightwheel.com/en/articles/8436983-message-your-childcare-provider"),
    "brightwheel_payments": _source("Brightwheel Help Center", "How payments in brightwheel work", "https://help.mybrightwheel.com/en/articles/5599079-how-payments-in-brightwheel-work"),
    "brightwheel_home": _source("Brightwheel Help Center", "Brightwheel Help Center", "https://help.mybrightwheel.com/en/"),
    # Electronic signatures and agreement management.
    "adobe_sign_start": _source("Adobe Acrobat Sign", "User get started guide", "https://helpx.adobe.com/sign/using/get-started-guide.html"),
    "adobe_sign_manage": _source("Adobe Acrobat Sign", "Manage, track, and change agreements", "https://helpx.adobe.com/sign/using/manage-documents-sent-for-signature.html"),
    "adobe_sign_request": _source("Adobe Acrobat Sign", "Request signatures from others", "https://helpx.adobe.com/in/sign/using/sending/request-signatures-from-others.html"),
    "adobe_sign_cancel": _source("Adobe Acrobat Sign", "Cancel an agreement", "https://helpx.adobe.com/in/sign/using/manage/cancel.html"),
    "adobe_sign_audit": _source("Adobe Acrobat Sign", "Download the audit report for an agreement", "https://helpx.adobe.com/sign/using/sign-download-audit-report.html"),
    "docusign_training": _source("Docusign University", "Customer training catalog", "https://support.docusign.com/resource/DSU_Customer_Training_Catalog"),
    # Creator memberships and monetization.
    "patreon_tiers": _source("Patreon Help Center", "Set up paid tiers and benefits", "https://support.patreon.com/hc/en-us/articles/203913559-How-to-set-up-paid-tiers-and-benefits"),
    "patreon_payouts": _source("Patreon Help Center", "Paying out your earnings", "https://support.patreon.com/hc/en-us/articles/203913499-Paying-out-your-earnings"),
    "patreon_billing": _source("Patreon Help Center", "How membership billing works", "https://support.patreon.com/hc/en-us/articles/360002355991-How-membership-billing-works"),
    "patreon_navigation": _source("Patreon Help Center", "Navigate the Patreon app as a creator", "https://support.patreon.com/hc/en-us/articles/19500560370189-Navigate-the-Patreon-app-as-a-creator"),
    "patreon_gifting": _source("Patreon Help Center", "Gifting memberships to your fans", "https://support.patreon.com/hc/en-us/articles/31345065123597-Gifting-memberships-to-your-fans-creator-to-fan-gifts"),
    # Crypto assets and account safety.
    "coinbase_buy": _source("Coinbase Help", "Buy crypto", "https://help.coinbase.com/en/coinbase/trading-and-funding/buying-selling-or-converting-crypto/how-do-i-buy-digital-currency"),
    "coinbase_recurring": _source("Coinbase Help", "Recurring buys", "https://help.coinbase.com/en/coinbase/trading-and-funding/buying-selling-or-converting-crypto/how-can-i-create-or-cancel-a-recurring-transaction"),
    "coinbase_security": _source("Coinbase Help", "Make your account more secure", "https://help.coinbase.com/en/coinbase/privacy-and-security/data-privacy/how-can-i-make-my-account-more-secure"),
    "coinbase_send_receive": _source("Coinbase Help", "Send and receive crypto", "https://help.coinbase.com/en/coinbase/trading-and-funding/sending-or-receiving-cryptocurrency/send-receive-crypto-eu"),
    "coinbase_privacy": _source("Coinbase Help", "Privacy and security", "https://help.coinbase.com/en/coinbase/privacy-and-security"),
    "coinbase_available_services": _source("Coinbase Help", "Available transaction types", "https://help.coinbase.com/en/coinbase/trading-and-funding/depositing-or-withdrawing-fiat-money/available-services"),
    "coinbase_staking": _source("Coinbase Help", "Stake or unstake crypto", "https://help.coinbase.com/en/coinbase/coinbase-staking/staking/stake-unstake"),
    "coinbase_transactions": _source("Coinbase Help", "View transaction history", "https://help.coinbase.com/en/coinbase/getting-started/getting-started-with-coinbase/transaction-history"),
    "coinbase_fraud": _source("Coinbase Help", "Fraud and suspicious activity", "https://help.coinbase.com/en/coinbase/fraud-suspicious-activity"),
    # Amateur and youth sports coordination.
    "teamsnap_help": _source("TeamSnap", "TeamSnap ONE Help Center", "https://help.teamsnap.com/"),
    "teamsnap_features": _source("TeamSnap", "Team management app features", "https://www.teamsnap.com/teams/features"),
    "teamsnap_mobile": _source("TeamSnap", "TeamSnap mobile apps", "https://www.teamsnap.com/mobile"),
    "teamsnap_payments": _source("TeamSnap", "Team payment tracking", "https://www.teamsnap.com/teams/features/payments"),
    "teamsnap_subscription": _source("TeamSnap ONE Help", "Manage your TeamSnap subscription", "https://help.teamsnap.com/article/2113-how-to-manage-your-teamsnap-subscription"),
}


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["legacy_tags"] = [
        "v7_long_tail" if value == "v6_open_world" else value
        for value in result.get("legacy_tags", [])
    ]
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    return _retag_function(_v6_build_root(group))


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    return _retag_function(_v6_build_feature(group, seed))


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v6_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v6_", "v7_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v6_", "v7_", 1)
        for key in tuple(rule):
            if key.startswith("v6_"):
                rule[f"v7_{key[3:]}"] = rule.pop(key)
    return result


GROUPS: tuple[GroupSeed, ...] = (
    G(
        "dating_discovery", "데이트 매칭·안전", "Dating discovery and safety", "dating_service",
        "데이트|매칭|소개팅|프로필|관심 상대|만남", "dating|match|discovery|profile|potential date|meet people",
        "일반 메신저|주소록|업무 채팅", "general messaging|contacts|work chat",
        "messaging.hub",
        "tinder_discovery|tinder_unmatch|tinder_photo_verify|tinder_id_verify|tinder_safety",
        F("profile_edit", "데이트 프로필 편집", "Edit dating profile", "소개글 수정|프로필 사진 변경|관심사 편집|직업 정보 수정|데이트 자기소개", "edit bio|change profile photos|update interests|edit job details|dating introduction", "프로필|자기소개", "회사 프로필|주소록", "change", sources="tinder_discovery|tinder_photo_verify"),
        F("discovery_preferences", "매칭 검색 조건", "Discovery preferences", "희망 나이 범위|검색 거리 설정|성별 선호|관심 대상 설정|매칭 조건", "age range preference|distance preference|gender preference|who I want to see|match filters", "검색 조건|추천 상대", "상품 검색 필터|지도 반경", "change", sources="tinder_discovery"),
        F("discovery_visibility", "프로필 노출 설정", "Discovery visibility", "새 상대에게 숨기기|매칭 추천 끄기|프로필 공개 중지|디스커버리 비활성화|데이트 노출", "hide from new people|turn off discovery|pause profile visibility|stop match recommendations|dating visibility", "프로필 노출|새로운 매칭", "온라인 상태 숨기기|광고 개인화", "change", sources="tinder_discovery"),
        F("matches", "매칭 상대 목록", "Match list", "매치한 사람 보기|서로 좋아요한 상대|연결된 상대 목록|데이트 매치|새 매칭 확인", "view matches|mutual likes|connected people|dating matches|new match list", "매칭|상대 목록", "주소록 친구|팀 구성원", "sensitive", sources="tinder_unmatch|tinder_safety"),
        F("conversation", "매칭 대화", "Match conversation", "매치 채팅 열기|데이트 상대 메시지|연결된 사람과 대화|매칭 받은편지함|소개팅 채팅", "open match chat|message a date|conversation with match|dating inbox|matched person messages", "매칭|대화", "고객센터 채팅|업무 채널", "sensitive", sources="tinder_unmatch|tinder_safety"),
        F("unmatch", "매칭 해제", "Unmatch a person", "매치 끊기|연결 취소|상대와 매칭 종료|대화 상대 제거|소개팅 매칭 삭제", "remove match|end match|disconnect a person|unmatch conversation|delete dating connection", "영구 해제|매칭 관계", "채팅방 나가기|팔로우 취소", "submit", sources="tinder_unmatch|tinder_safety"),
        F("block_profile", "데이트 프로필 차단", "Block dating profile", "상대 차단|다시 보지 않기|프로필 숨김 차단|연락 못하게 하기|매칭 대상 제외", "block person|hide profile permanently|prevent contact|block a match|exclude dating profile", "차단|안전", "광고 차단|팝업 차단", "submit", sources="tinder_unmatch|tinder_safety"),
        F("report_profile", "데이트 프로필 신고", "Report dating profile", "부적절한 상대 신고|가짜 프로필 신고|괴롭힘 신고|매치 신고|안전팀에 알리기", "report inappropriate person|report fake profile|report harassment|report match|notify safety team", "신고 사유|신뢰와 안전", "콘텐츠 오류 신고|앱 버그 신고", "submit", sources="tinder_unmatch|tinder_safety"),
        F("photo_verification", "프로필 사진 인증", "Dating photo verification", "셀피 인증|얼굴 영상 인증|사진 본인 확인|파란 체크 인증|프로필 실물 인증", "selfie verification|video face check|verify profile photos|blue check verification|prove photo identity", "얼굴|프로필 사진", "결제 신원 인증|문서 서명", "submit", sources="tinder_photo_verify"),
        F("identity_verification", "데이트 신분 인증", "Dating identity verification", "신분증과 사진 인증|나이 확인|ID 인증 배지|정부 발급 신분증 제출|본인 확인", "ID and photo verification|verify age|identity badge|submit government ID|dating identity check", "신분증|얼굴 정보", "은행 실명 인증|전자서명", "submit", sources="tinder_id_verify"),
        F("safety_center", "데이트 안전 센터", "Dating safety center", "안전 수칙 보기|만남 전 주의사항|데이트 보호 도구|신뢰와 안전 도움말|위험 대응 안내", "dating safety tips|meeting precautions|safety tools|trust and safety help|unsafe date guidance", "만남 안전|보호", "기기 보안 설정|차량 안전", "view", sources="tinder_safety|tinder_id_verify"),
        F("date_safety_share", "데이트 일정 안전 공유", "Share date safety plan", "만남 정보 공유|데이트 장소 보내기|친구에게 일정 알리기|안전 연락처에 공유|만남 계획 전달", "share date details|send meeting place|tell a friend about date|share with safety contact|date plan sharing", "만남 일정|신뢰 연락처", "캘린더 초대|실시간 위치 일반 공유", "submit", sources="tinder_safety"),
        F("read_receipts", "매칭 읽음 표시", "Match read receipts", "대화 읽음 여부|메시지 확인 표시|읽음 기능 설정|채팅 수신 확인|매치 메시지 상태", "message read status|seen indicator|read receipt setting|chat delivery confirmation|match message status", "매칭 채팅|읽음", "이메일 수신 확인|택배 배송 상태", "change", sources="tinder_unmatch"),
        F("distance_location", "매칭 위치·거리", "Dating location and distance", "현재 지역 변경|매칭 거리 확인|데이트 위치 설정|여행 지역 검색|주변 상대 범위", "change dating location|match distance|dating region|travel discovery location|nearby people radius", "위치|거리", "차량 위치|택배 위치", "sensitive", sources="tinder_discovery"),
        F("privacy_controls", "데이트 개인정보 설정", "Dating privacy controls", "연락처 차단 설정|프로필 정보 공개 범위|활동 상태 숨기기|개인정보 선택|데이트 데이터 설정", "block contacts setting|profile privacy|hide activity status|privacy choices|dating data controls", "개인정보|노출", "브라우저 쿠키|광고 설정", "change", sources="tinder_discovery|tinder_id_verify"),
    ),
    G(
        "digital_library", "전자도서관·독서", "Digital library and reading", "library_service",
        "전자책|오디오북|도서관|대출|책장|독서", "ebook|audiobook|library|loan|shelf|reading",
        "서점 구매|문서 편집|음악 스트리밍", "bookstore purchase|document editing|music streaming",
        "documents.hub",
        "libby_navigation|libby_getting_started|libby_borrow|libby_holds|libby_cards|libby_reset|libby_downloads|libby_content_controls",
        F("catalog_search", "도서관 자료 검색", "Library catalog search", "전자책 찾기|오디오북 검색|작가로 책 찾기|도서관 소장 자료|제목 검색", "find ebook|search audiobooks|search by author|library catalog|title search", "도서관 검색|책", "웹 문서 검색|쇼핑 상품 검색", "view", sources="libby_navigation|libby_getting_started"),
        F("library_browse", "도서관 컬렉션 둘러보기", "Browse library collection", "도서관 추천 목록|신간 도서 보기|장르별 책|큐레이션 목록|도서관 캠페인", "library recommendations|new titles|browse by genre|curated lists|library guides", "컬렉션|도서관", "상점 카탈로그|사진 앨범", "view", sources="libby_navigation|libby_getting_started"),
        F("library_cards", "도서관 카드 관리", "Manage library cards", "도서관 카드 추가|대출증 바꾸기|카드 번호 관리|다른 도서관 연결|활성 카드 선택", "add library card|switch borrowing card|manage card number|connect another library|select active card", "도서관 카드|PIN", "결제 카드|교통 카드", "submit", sources="libby_cards|libby_getting_started"),
        F("borrow_title", "전자책 대출", "Borrow a library title", "책 빌리기|오디오북 대출|대출 기간 선택|전자책 체크아웃|도서관 자료 빌림", "borrow book|check out audiobook|choose loan period|ebook checkout|library loan", "대출|기간", "유료 책 구매|기기 대여", "submit", sources="libby_borrow|libby_getting_started"),
        F("loans_shelf", "대출 중인 책", "Current library loans", "내 대출 목록|책장 대출 탭|반납 예정 책|빌린 오디오북|대출 만료일", "my loans|shelf loans|books due soon|borrowed audiobooks|loan due date", "책장|대출", "금융 대출|렌터카", "sensitive", sources="libby_navigation|libby_getting_started|libby_borrow"),
        F("renew_loan", "도서 대출 연장", "Renew library loan", "책 대출 갱신|반납일 연장|오디오북 재대출|대출 기간 늘리기|전자책 연장", "renew book loan|extend due date|renew audiobook|increase loan period|ebook renewal", "만료일|대출", "구독 갱신|계약 연장", "submit", sources="libby_borrow"),
        F("return_early", "도서 조기 반납", "Return library title early", "책 미리 반납|전자책 반환|오디오북 조기 반납|대출 종료|책장에서 반납", "return book early|return ebook|early audiobook return|end library loan|return from shelf", "반납|대출 종료", "상품 반품|렌터카 반납", "submit", sources="libby_borrow|libby_getting_started"),
        F("place_hold", "도서 예약 걸기", "Place library hold", "대출 예약|책 대기열 신청|인기 도서 예약|오디오북 보류 요청|이용 가능 알림 신청", "place hold|join book waitlist|reserve popular title|hold audiobook|notify when available", "예약|대기열", "숙소 예약|식당 대기", "submit", sources="libby_holds|libby_getting_started"),
        F("hold_status", "도서 예약 순번", "Library hold status", "대기 순서 보기|예약 예상 날짜|책 대기열 위치|보류 자료 상태|이용 가능까지 시간", "hold queue position|estimated availability|place in book line|hold status|time until available", "대기열|예약 자료", "식당 대기 순번|고객센터 대기", "sensitive", sources="libby_holds"),
        F("suspend_hold", "도서 예약 일시정지", "Suspend library hold", "예약 보류|대기 순번 유지|책 나중에 받기|예약 전달 연기|보류 해제 일정", "suspend hold|keep queue position|deliver title later|delay hold|schedule hold resume", "예약|일시정지", "구독 일시정지|다운로드 중지", "change", sources="libby_holds"),
        F("cancel_hold", "도서 예약 취소", "Cancel library hold", "책 예약 삭제|대기열 나가기|보류 자료 취소|대출 예약 철회|예약 목록 제거", "cancel book hold|leave waitlist|remove held title|withdraw loan reservation|delete hold", "예약 취소|대기열", "호텔 예약 취소|구독 취소", "submit", sources="libby_holds"),
        F("offline_downloads", "독서 오프라인 다운로드", "Reading offline downloads", "전자책 자동 다운로드|와이파이에서만 받기|오디오북 오프라인 저장|다운로드 크기 제한|대출 자료 저장", "automatic ebook downloads|download on Wi-Fi only|offline audiobook|download size limit|save borrowed title", "다운로드|오프라인", "사진 백업|앱 설치", "change", sources="libby_downloads|libby_getting_started"),
        F("reading_preferences", "독서 화면 설정", "Reading preferences", "글자 크기 변경|배경색 설정|오디오북 속도|독서 테마|페이지 넘김 설정", "change font size|reader background|audiobook speed|reading theme|page turn settings", "독서 화면|재생", "시스템 글꼴|음악 속도", "change", sources="libby_navigation|libby_getting_started"),
        F("content_controls", "도서 콘텐츠 제한", "Library content controls", "성인 자료 숨기기|어린이 독서 모드|대출 가능 연령 설정|표지 이미지 제한|청소년 콘텐츠 필터", "hide mature titles|kids reading mode|audience loan controls|hide cover images|young adult filter", "독서 대상|콘텐츠 제한", "앱 사용 시간|영상 자녀 보호", "change", sources="libby_content_controls"),
        F("tags_history", "독서 태그·이력", "Reading tags and timeline", "나중에 읽을 책|책 태그 목록|대출 기록 보기|독서 타임라인|저장한 제목", "books for later|title tags|borrowing history|reading timeline|saved titles", "태그|독서 기록", "브라우저 기록|쇼핑 찜 목록", "sensitive", sources="libby_navigation|libby_reset"),
    ),
    G(
        "beauty_wellness_booking", "뷰티·웰니스 예약", "Beauty and wellness booking", "appointment_marketplace",
        "미용실|네일|마사지|스파|뷰티 예약|웰니스", "salon|nails|massage|spa|beauty booking|wellness",
        "병원 진료|식당 예약|차량 정비", "medical appointment|restaurant reservation|vehicle service",
        "fitness_membership.hub",
        "fresha_calendar|fresha_reschedule|fresha_online_booking",
        F("service_search", "뷰티 서비스 검색", "Beauty service search", "헤어 시술 찾기|네일 서비스 검색|마사지 종류|스파 메뉴|근처 뷰티 예약", "find hair service|search nail treatment|massage type|spa menu|nearby beauty booking", "서비스 종류|뷰티", "병원 진료과|식당 메뉴", "view", sources="fresha_online_booking"),
        F("provider_profile", "뷰티 전문가 프로필", "Beauty professional profile", "스타일리스트 보기|테라피스트 정보|네일 아티스트 경력|담당자 리뷰|서비스 제공자 소개", "view stylist|therapist profile|nail artist experience|professional reviews|service provider bio", "전문가|리뷰", "의사 프로필|배달 기사", "view", sources="fresha_calendar|fresha_online_booking"),
        F("availability", "뷰티 예약 가능 시간", "Beauty appointment availability", "빈 시간 찾기|시술 가능 날짜|스타일리스트 일정|스파 타임 슬롯|당일 예약 가능", "find open time|treatment availability|stylist schedule|spa time slot|same-day opening", "일정|가능 시간", "병원 예약 시간|회의실", "view", sources="fresha_calendar|fresha_online_booking"),
        F("book_appointment", "뷰티 예약 확정", "Book beauty appointment", "미용실 예약하기|네일 예약|마사지 시간 선택|스파 예약 제출|시술 예약", "book salon|book nail appointment|select massage time|confirm spa booking|reserve treatment", "서비스|날짜|담당자", "진료 예약|식당 예약", "submit", sources="fresha_calendar|fresha_online_booking"),
        F("upcoming_appointments", "예정된 뷰티 예약", "Upcoming beauty appointments", "내 미용실 예약|다음 시술 일정|예약 확인서|예정 마사지|뷰티 예약 목록", "my salon bookings|next treatment|booking confirmation|upcoming massage|beauty appointment list", "예약 목록|시술", "병원 일정|항공 일정", "sensitive", sources="fresha_calendar"),
        F("reschedule", "뷰티 예약 변경", "Reschedule beauty appointment", "시술 시간 바꾸기|미용실 날짜 변경|담당자 일정 이동|마사지 예약 미루기|예약 시간 재선택", "change treatment time|move salon date|reschedule professional|postpone massage|choose new booking time", "기존 예약|새 시간", "병원 일정 변경|배송 변경", "submit", sources="fresha_reschedule"),
        F("cancel_booking", "뷰티 예약 취소", "Cancel beauty appointment", "미용실 예약 취소|네일 예약 삭제|마사지 취소|시술 일정 철회|스파 예약 종료", "cancel salon booking|delete nail appointment|cancel massage|withdraw treatment booking|cancel spa visit", "취소 정책|예약", "구독 취소|식당 취소", "submit", sources="fresha_calendar|fresha_online_booking"),
        F("waitlist", "뷰티 예약 대기 목록", "Beauty appointment waitlist", "빈자리 대기 신청|취소 자리 알림|시술 대기열|선호 시간 등록|예약 대기 삭제", "join cancellation waitlist|opening alert|treatment waitlist|preferred time request|remove waitlist entry", "대기 목록|빈 시간", "도서 예약|식당 대기", "submit", sources="fresha_calendar"),
        F("repeat_booking", "반복 뷰티 예약", "Repeat beauty appointments", "정기 네일 예약|매주 마사지|반복 시술 일정|다음 방문 자동 예약|연속 예약", "recurring nail booking|weekly massage|repeat treatment schedule|automatic next visit|appointment series", "반복 일정|시술", "구독 결제|반복 회의", "submit", sources="fresha_calendar"),
        F("group_booking", "그룹 뷰티 예약", "Group beauty booking", "여러 명 스파 예약|동시 시술 예약|그룹 마사지|파티 뷰티 일정|복수 고객 예약", "spa booking for group|simultaneous treatments|group massage|beauty party schedule|multi-client appointment", "그룹|인원", "단체 식당 예약|팀 회의", "submit", sources="fresha_calendar"),
        F("intake_forms", "뷰티 사전 문진", "Beauty intake forms", "시술 전 질문지|알레르기 정보 제출|건강 상태 작성|고객 동의서|뷰티 상담 양식", "pre-treatment questionnaire|submit allergy info|health intake|client consent form|beauty consultation form", "시술 정보|민감 정보", "병원 진료 문진|보험 청구", "submit", sources="fresha_calendar|fresha_online_booking"),
        F("booking_policy", "뷰티 예약 정책", "Beauty booking policy", "취소 수수료 확인|예약 변경 마감|노쇼 정책|선결제 조건|시술 주의사항", "cancellation fee policy|reschedule deadline|no-show policy|deposit terms|treatment booking rules", "정책|수수료", "구독 약관|항공 환불 규정", "view", sources="fresha_online_booking"),
        F("deposit_payment", "뷰티 예약 보증금", "Beauty booking deposit", "시술 예약금 결제|카드 보증|선결제 금액|예약 보증금 확인|결제 정책 동의", "pay treatment deposit|card guarantee|upfront payment|booking deposit amount|accept payment policy", "예약금|결제", "병원 본인부담금|쇼핑 결제", "submit", sources="fresha_online_booking|fresha_reschedule"),
        F("appointment_reminders", "뷰티 예약 알림", "Beauty appointment reminders", "시술 전 알림|예약 문자 설정|방문 리마인더|미용실 푸시 알림|일정 알림 끄기", "treatment reminder|booking text alerts|visit reminder|salon push notification|turn off appointment alerts", "예약|알림", "약 복용 알림|배송 알림", "change", sources="fresha_online_booking|fresha_calendar"),
        F("checkout_tip", "뷰티 시술 결제·팁", "Beauty checkout and tip", "시술비 결제|스타일리스트 팁|마사지 결제 완료|영수증 확인|뷰티 체크아웃", "pay treatment bill|tip stylist|complete massage payment|view salon receipt|beauty checkout", "시술 완료|결제", "식당 결제|배달 팁", "submit", sources="fresha_calendar"),
    ),
    G(
        "childcare_family_portal", "보육·가족 포털", "Childcare family portal", "childcare_service",
        "어린이집|보육원|아이 등하원|보호자|유아 활동|가족", "childcare|daycare|child check-in|guardian|daily child activity|family",
        "학교 성적|병원 소아과|가족 구독", "school grades|pediatric clinic|family subscription",
        "education.hub",
        "brightwheel_guardian|brightwheel_checkin|brightwheel_messages|brightwheel_payments|brightwheel_home",
        F("child_profile", "아이 프로필", "Child profile", "자녀 정보 보기|반 정보|생일과 알레르기|아이 사진|학생 기본 정보", "view child information|classroom details|birthday and allergies|child photo|student profile", "아이|보호자", "성인 프로필|학교 성적", "sensitive", sources="brightwheel_guardian|brightwheel_home"),
        F("daily_feed", "아이 일일 활동", "Child daily activity feed", "오늘 아이 활동|식사 기록|낮잠 시간|기저귀 기록|어린이집 사진", "child activity today|meal log|nap time|diaper log|daycare photos", "일일 기록|아이", "소셜 피드|운동 기록", "sensitive", sources="brightwheel_guardian|brightwheel_home"),
        F("checkin_code", "등하원 확인 코드", "Childcare check-in code", "보호자 네 자리 코드|등원 코드 보기|픽업 PIN 변경|체크인 암호|출석 확인 번호", "guardian four-digit code|view drop-off code|change pickup PIN|check-in passcode|attendance code", "보호자 코드|등하원", "기기 잠금 PIN|결제 비밀번호", "sensitive", sources="brightwheel_checkin"),
        F("child_checkin", "아이 등원 처리", "Check child in", "어린이집 등원|아이 체크인|등원 시간 기록|드롭오프 확인|보호자 서명 등원", "daycare drop-off|check child in|record arrival time|confirm dropoff|guardian arrival signature", "아이|도착|보호자", "항공 체크인|직원 출근", "submit", sources="brightwheel_guardian|brightwheel_checkin"),
        F("child_checkout", "아이 하원 처리", "Check child out", "어린이집 하원|아이 체크아웃|픽업 시간 기록|데려감 확인|보호자 서명 하원", "daycare pickup|check child out|record pickup time|confirm collection|guardian pickup signature", "아이|픽업|보호자", "호텔 체크아웃|직원 퇴근", "submit", sources="brightwheel_guardian|brightwheel_checkin"),
        F("approved_pickups", "승인된 아이 픽업자", "Approved child pickups", "하원 가능 사람 추가|픽업 보호자 관리|아이 데려갈 가족|승인 픽업 삭제|대리 하원 권한", "add approved pickup|manage pickup guardian|family allowed to collect|remove pickup person|delegate child pickup", "아이|픽업 권한", "택배 수령인|차량 운전자", "submit", sources="brightwheel_guardian"),
        F("family_contacts", "아이 가족 연락처", "Child family contacts", "자녀 가족 구성원 추가|보호자 전화번호|가족 앱 접근|공동 보호자 관리|아이 연락망", "add child family member|guardian phone|family app access|manage co-guardian|child contact list", "가족|접근 권한", "일반 주소록|팀 로스터", "submit", sources="brightwheel_guardian"),
        F("emergency_contacts", "아이 비상 연락처", "Child emergency contacts", "어린이집 긴급 연락처|아이 비상 보호자|응급 전화번호|가족 외 연락처|비상 연락망 수정", "daycare emergency contact|child emergency guardian|emergency phone|non-family contact|edit emergency list", "아이|비상", "일반 주소록|보험 긴급출동", "submit", sources="brightwheel_guardian"),
        F("provider_messages", "보육기관 메시지", "Message childcare provider", "선생님에게 메시지|어린이집 문의|관리자에게 비공개 대화|아이 관련 채팅|보육원 답장", "message teacher|ask daycare|private admin thread|childcare chat|reply to provider", "아이|교사|관리자", "학교 단체 채팅|고객센터", "submit", sources="brightwheel_messages"),
        F("billing_balance", "보육료 잔액·청구서", "Childcare balance and invoices", "어린이집 청구서|미납 보육료|아이 결제 잔액|납부 예정 금액|보육비 거래", "daycare invoice|unpaid tuition|child billing balance|amount due|childcare transactions", "아이|청구|납부", "학교 성적|일반 카드 잔액", "sensitive", sources="brightwheel_payments"),
        F("invoice_payment", "보육료 납부", "Pay childcare invoice", "어린이집 비용 결제|보육료 송금|아이 청구서 납부|열린 인보이스 결제|보육비 일부 납부", "pay daycare fee|pay tuition|settle child invoice|pay open invoices|partial childcare payment", "아이|결제|청구서", "학교 급식 결제|쇼핑 결제", "submit", sources="brightwheel_payments"),
        F("autopay", "보육료 자동납부", "Childcare autopay", "어린이집 자동결제 등록|보육료 자동이체|청구일 카드 결제|자동납부 해제|결제 수단 변경", "enroll daycare autopay|automatic tuition debit|charge card on due date|disable autopay|change childcare payment method", "보육료|자동 결제", "구독 자동결제|공과금 자동납부", "submit", sources="brightwheel_payments"),
        F("attendance_history", "아이 등하원 이력", "Child attendance history", "어린이집 출석 기록|과거 등원 시간|하원 내역|결석 날짜|보호자 픽업 기록", "daycare attendance log|past arrival times|pickup history|absence dates|guardian collection record", "아이|출석|시간", "직원 근태|학교 성적", "sensitive", sources="brightwheel_guardian|brightwheel_checkin"),
        F("health_medication", "아이 건강·투약 정보", "Child health and medication", "아이 알레르기 정보|투약 지시|건강 기록|어린이집 약 요청|의료 주의사항", "child allergy information|medication instructions|health record|daycare medicine request|medical care notes", "아이|건강|약", "성인 처방전|건강 보험", "sensitive", sources="brightwheel_guardian|brightwheel_home"),
        F("incident_report", "아이 사고·관찰 기록", "Child incident report", "어린이집 사고 보고서|다친 기록 보기|행동 관찰|보호자 확인 서명|사건 알림", "daycare incident report|view injury record|behavior observation|guardian acknowledgment|child event alert", "아이|사고|확인", "보험 사고 접수|앱 오류", "sensitive", sources="brightwheel_guardian|brightwheel_home"),
    ),
    G(
        "esign_notary", "전자서명·계약 문서", "Electronic signature and agreements", "agreement_service",
        "전자서명|서명 요청|계약서|협약|서명자|감사 보고서", "electronic signature|signature request|agreement|contract|signer|audit report",
        "일반 문서 편집|신분증 스캔|법률 상담", "general document editing|ID scanning|legal advice",
        "documents.hub",
        "adobe_sign_start|adobe_sign_manage|adobe_sign_request|adobe_sign_cancel|adobe_sign_audit|docusign_training",
        F("waiting_to_sign", "서명 대기 문서", "Documents waiting for signature", "내 서명 필요|서명 요청 받은 문서|처리 대기 계약서|검토 및 서명|수신 협약", "needs my signature|received signature request|agreement awaiting action|review and sign|incoming contract", "서명 대기|수신 문서", "일반 받은편지함|문서 초안", "sensitive", sources="adobe_sign_start|docusign_training"),
        F("review_document", "서명 전 문서 검토", "Review agreement before signing", "계약 내용 읽기|서명 문서 열기|조항 검토|첨부 파일 확인|협약 미리보기", "read contract|open signature document|review clauses|inspect attachments|preview agreement", "계약 문서|검토", "문서 편집|약관 요약", "sensitive", sources="adobe_sign_start|adobe_sign_manage"),
        F("required_fields", "서명 필수 항목", "Required signing fields", "입력할 칸 찾기|다음 필수 필드|이니셜 위치|날짜 입력란|누락된 서명 칸", "find fields to complete|next required field|initial field|date field|missing signature field", "필수 필드|문서", "회원가입 양식|검색 필터", "change", sources="adobe_sign_start"),
        F("apply_signature", "전자서명 완료", "Apply electronic signature", "문서에 서명하기|서명 적용|계약 동의 서명|클릭하여 서명|전자서명 제출", "sign document|apply signature|sign agreement consent|click to sign|submit electronic signature", "서명|법적 동의", "프로필 서명|이메일 서명", "submit", sources="adobe_sign_start|docusign_training"),
        F("decline_signing", "서명 거절", "Decline to sign", "계약 서명 거부|문서 승인하지 않기|서명 요청 반려|거절 사유 입력|협약 거부", "decline agreement|refuse document approval|reject signature request|enter decline reason|do not sign contract", "서명 요청|거절", "초대 거절|예약 거절", "submit", sources="adobe_sign_start|docusign_training"),
        F("request_signatures", "서명 요청 보내기", "Request signatures", "계약서 서명 받기|문서 업로드 후 전송|서명자에게 보내기|전자서명 요청 생성|협약 발송", "send contract for signature|upload and send document|send to signer|create e-sign request|dispatch agreement", "문서|수신자|서명", "파일 공유|이메일 첨부", "submit", sources="adobe_sign_request|docusign_training"),
        F("recipient_routing", "서명자 순서·역할", "Signer routing and roles", "서명 순서 설정|승인자 추가|참조 수신자|동시 서명|수신자 역할 지정", "set signing order|add approver|add carbon copy|parallel signing|assign recipient role", "수신자|순서|역할", "이메일 수신자|배송 경로", "submit", sources="adobe_sign_request|adobe_sign_start"),
        F("send_reminder", "서명 알림 보내기", "Send signing reminder", "미서명자 재알림|계약 리마인더|서명 요청 다시 보내기|기한 알림|수신자 독촉", "remind unsigned recipient|agreement reminder|resend signature request|deadline alert|nudge signer", "서명자|미완료", "일반 캘린더 알림|결제 독촉", "submit", sources="adobe_sign_manage|docusign_training"),
        F("replace_recipient", "서명자 교체", "Replace agreement recipient", "잘못된 이메일 수정|현재 서명자 변경|대체 수신자 추가|계약 수신인 교체|서명 담당 변경", "fix signer email|change current signer|add alternate recipient|replace agreement recipient|change signing assignee", "진행 중 계약|수신자", "이메일 연락처 편집|배송 수령인", "submit", sources="adobe_sign_manage|docusign_training"),
        F("modify_agreement", "발송 계약 수정", "Modify sent agreement", "계약 파일 교체|서명 필드 수정|발송 문서 정정|만료일 변경|계약 내용 업데이트", "replace agreement file|edit signature fields|correct sent document|change expiration date|update agreement", "진행 중 문서|수정", "로컬 파일 편집|완료 계약", "submit", sources="adobe_sign_manage|docusign_training"),
        F("cancel_agreement", "전자서명 계약 취소", "Cancel signature agreement", "진행 중 계약 중단|서명 요청 무효화|협약 취소|계약 발송 철회|서명 절차 종료", "stop in-progress agreement|void signature request|cancel contract|withdraw sent agreement|end signing process", "취소|되돌릴 수 없음", "구독 취소|예약 취소", "submit", sources="adobe_sign_cancel|adobe_sign_manage|docusign_training"),
        F("agreement_status", "전자서명 진행 상태", "Agreement status tracking", "누가 서명했는지|계약 진행률|서명 대기자|완료된 협약|문서 만료 상태", "who has signed|agreement progress|pending signer|completed contract|document expiration status", "계약 상태|수신자", "배송 추적|승인 결재", "sensitive", sources="adobe_sign_manage|docusign_training"),
        F("download_signed", "서명 완료 문서 다운로드", "Download signed agreement", "완료 계약 PDF|서명본 저장|협약 파일 받기|개별 문서 다운로드|서명 증명서 포함", "completed contract PDF|save signed copy|download agreement|download individual files|include completion certificate", "서명 완료|PDF", "일반 파일 다운로드|영수증", "sensitive", sources="adobe_sign_manage|adobe_sign_start"),
        F("audit_report", "서명 감사 보고서", "Signature audit report", "계약 이력 PDF|서명 이벤트 기록|감사 추적 다운로드|수신자 활동 이력|완료 증명 보고서", "agreement history PDF|signature event log|download audit trail|recipient activity history|completion evidence report", "감사|서명 이력", "보안 로그인 기록|회계 감사", "sensitive", sources="adobe_sign_audit|adobe_sign_manage"),
        F("templates", "전자서명 템플릿", "Signature agreement templates", "반복 계약 양식|서명 필드 템플릿|문서 라이브러리|협약 서식 만들기|저장된 워크플로", "recurring contract template|signature field template|document library|create agreement form|saved signing workflow", "템플릿|서명 요청", "문서 서식|이메일 템플릿", "change", sources="adobe_sign_request|docusign_training"),
    ),
    G(
        "creator_monetization", "크리에이터 수익화", "Creator monetization", "creator_service",
        "크리에이터|멤버십|후원자|유료 콘텐츠|수익|정산", "creator|membership|patron|paid content|earnings|payout",
        "일반 구독자|급여|온라인 쇼핑", "generic subscription|payroll|online shopping",
        "work.hub",
        "patreon_tiers|patreon_payouts|patreon_billing|patreon_navigation|patreon_gifting",
        F("dashboard", "크리에이터 대시보드", "Creator dashboard", "창작자 홈|멤버 현황|최근 참여|수익 요약|크리에이터 스튜디오", "creator home|member overview|recent engagement|earnings summary|creator studio", "크리에이터|지표", "일반 홈 피드|광고 대시보드", "sensitive", sources="patreon_navigation|patreon_payouts"),
        F("publish_post", "유료 콘텐츠 게시", "Publish creator post", "멤버 전용 글 올리기|새 창작물 게시|유료 포스트 발행|콘텐츠 업로드|후원자에게 공개", "publish member post|create new work|release paid post|upload creator content|share with patrons", "게시물|공개 대상", "소셜 일반 게시|상품 등록", "submit", sources="patreon_navigation|patreon_billing"),
        F("post_audience", "콘텐츠 공개 대상", "Creator post audience", "유료 멤버만 보기|특정 등급 공개|전체 팬 공개|무료 멤버 공개|콘텐츠 접근 설정", "paid members only|selected tiers|all fans|free members|content access setting", "콘텐츠|멤버 등급", "광고 대상|가족 공유", "change", sources="patreon_tiers|patreon_navigation"),
        F("membership_tiers", "크리에이터 멤버십 등급", "Creator membership tiers", "후원 등급 만들기|월 가격 설정|멤버십 이름 수정|등급 인원 제한|유료 티어 공개", "create support tier|set monthly price|edit membership name|limit tier members|publish paid tier", "등급|가격|혜택", "일반 구독 요금제|게임 랭크", "submit", sources="patreon_tiers|patreon_billing"),
        F("tier_benefits", "멤버십 혜택 관리", "Membership benefit delivery", "등급별 혜택 추가|배송 주소 수집|커뮤니티 역할 연결|후원자 리워드|혜택 이행 목록", "add tier benefits|collect shipping address|link community role|patron reward|benefit fulfillment list", "멤버십|혜택", "직원 복리후생|카드 혜택", "change", sources="patreon_tiers"),
        F("member_directory", "유료 멤버 목록", "Paid member directory", "후원자 목록|멤버 상태 보기|신규 가입자|등급별 회원|결제 실패 멤버", "patron list|member status|new supporters|members by tier|declined payment members", "멤버|결제 상태", "주소록|팀 로스터", "sensitive", sources="patreon_navigation|patreon_billing"),
        F("earnings_insights", "크리에이터 수익 분석", "Creator earnings insights", "월별 수익 보기|멤버십 매출|수수료 내역|콘텐츠별 수익|정산 분석", "monthly creator revenue|membership sales|fee breakdown|earnings by content|payout analytics", "수익|수수료", "급여 명세|투자 수익", "sensitive", sources="patreon_payouts|patreon_billing"),
        F("payout_balance", "크리에이터 정산 잔액", "Creator payout balance", "출금 가능 금액|대기 중 수익|정산 예정액|창작자 잔액|지급 보류", "available payout amount|pending earnings|scheduled payout|creator balance|payout hold", "정산|잔액", "은행 잔액|포인트", "sensitive", sources="patreon_payouts"),
        F("payout_method", "크리에이터 정산 수단", "Creator payout method", "정산 계좌 추가|페이팔 연결|출금 정보 변경|지급 통화 설정|정산 방식 관리", "add payout bank|connect PayPal|change withdrawal details|set payout currency|manage payout method", "정산|계좌", "일반 결제 카드|급여 계좌", "submit", sources="patreon_payouts"),
        F("withdraw_earnings", "크리에이터 수익 출금", "Withdraw creator earnings", "창작자 잔액 인출|정산금 받기|수익 지급 요청|출금 금액 확인|정산 확정", "withdraw creator balance|receive payout|request earnings payment|review withdrawal amount|confirm creator payout", "출금|수수료|정산", "은행 이체|가상자산 출금", "submit", sources="patreon_payouts"),
        F("auto_payout", "크리에이터 자동 정산", "Creator automatic payout", "매월 자동 출금|정산 자동이체 켜기|자동 지급 해제|지급일 설정|정산 스케줄", "monthly auto withdrawal|enable automatic payout|disable auto payout|payout day|creator payout schedule", "정산|자동", "구독 자동결제|급여 자동입금", "submit", sources="patreon_payouts"),
        F("billing_model", "멤버십 청구 방식", "Creator membership billing model", "가입일 기준 결제|월초 청구|게시물당 과금|연간 멤버십|청구 모델 전환", "subscription-date billing|first-of-month charge|per-creation billing|annual membership|switch billing model", "멤버십|청구", "공과금 청구|급여 주기", "submit", sources="patreon_billing"),
        F("discount_offers", "크리에이터 할인·무료체험", "Creator discounts and trials", "멤버십 할인 코드|무료 체험 설정|한정 할인|연간 요금 할인|가입 프로모션", "membership discount code|free trial setting|limited offer|annual plan discount|join promotion", "멤버십|할인", "쇼핑 쿠폰|통신 요금 할인", "submit", sources="patreon_tiers|patreon_billing"),
        F("gift_membership", "멤버십 선물", "Gift creator membership", "팬에게 무료 멤버십|선물 링크 만들기|등급 체험권|후원권 선물|멤버십 선물 기간", "gift free membership|create gift link|tier trial gift|give supporter access|membership gift duration", "선물|등급|기간", "상품권|앱 선물", "submit", sources="patreon_gifting|patreon_tiers"),
        F("community_messages", "크리에이터 커뮤니티 대화", "Creator community messages", "후원자 채팅|멤버 댓글 답장|신규 멤버 메시지|크리에이터 받은편지함|커뮤니티 알림", "patron chat|reply to member comments|message new member|creator inbox|community notification", "멤버|대화", "일반 메신저|고객센터", "submit", sources="patreon_navigation"),
    ),
    G(
        "crypto_assets", "가상자산·암호화폐", "Crypto assets and transfers", "crypto_service",
        "가상자산|암호화폐|코인|토큰|지갑|블록체인", "crypto|cryptocurrency|coin|token|wallet|blockchain",
        "주식|일반 은행|게임 코인", "stocks|retail bank|game currency",
        "retail_banking.hub",
        "coinbase_buy|coinbase_recurring|coinbase_security|coinbase_send_receive|coinbase_privacy|coinbase_available_services|coinbase_staking|coinbase_transactions|coinbase_fraud",
        F("portfolio_balance", "가상자산 포트폴리오", "Crypto portfolio balance", "보유 코인 잔액|토큰 평가액|가상자산 자산 현황|암호화폐 포트폴리오|현금 잔고", "coin holdings balance|token value|digital asset overview|crypto portfolio|cash balance", "자산|잔액|가격", "은행 예금|게임 포인트", "sensitive", sources="coinbase_buy|coinbase_privacy"),
        F("asset_detail", "가상자산 상세", "Crypto asset detail", "코인 가격 차트|토큰 보유량|가상자산 정보|암호화폐 시세|자산 거래 버튼", "coin price chart|token holding|digital asset information|crypto market price|asset trade actions", "자산|시세", "주식 종목|게임 아이템", "sensitive", sources="coinbase_buy"),
        F("buy_crypto", "가상자산 구매", "Buy crypto", "코인 사기|암호화폐 매수|토큰 구매|가상자산 주문|코인 결제 수단 선택", "buy coin|purchase cryptocurrency|buy token|digital asset order|select crypto payment method", "자산|금액|주문", "주식 매수|쇼핑 결제", "submit", sources="coinbase_buy"),
        F("sell_crypto", "가상자산 매도", "Sell crypto", "코인 팔기|암호화폐 현금화|토큰 매도|가상자산 판매 주문|현금 잔액으로 전환", "sell coin|cash out crypto|sell token|digital asset sale order|convert to cash balance", "자산|수량|매도", "주식 매도|중고 판매", "submit", sources="coinbase_buy|coinbase_available_services"),
        F("convert_swap", "가상자산 교환", "Convert or swap crypto", "코인 바꾸기|토큰 스왑|암호화폐 간 전환|자산 교환 비율|가상자산 변환", "convert coins|token swap|crypto-to-crypto exchange|asset conversion rate|swap digital asset", "보내는 자산|받는 자산", "환전|포인트 전환", "submit", sources="coinbase_available_services"),
        F("send_crypto", "가상자산 보내기", "Send crypto", "외부 지갑으로 전송|코인 출금|암호화폐 송금|수신 주소 입력|네트워크 선택", "send to external wallet|withdraw coin|transfer cryptocurrency|enter recipient address|choose crypto network", "수신 주소|네트워크|수수료", "은행 송금|메시지 보내기", "submit", sources="coinbase_send_receive|coinbase_security"),
        F("receive_crypto", "가상자산 받기 주소", "Receive crypto address", "코인 입금 주소|QR로 암호화폐 받기|지갑 주소 복사|토큰 수신 네트워크|입금 메모 확인", "crypto deposit address|receive coin QR|copy wallet address|token receive network|deposit memo", "공개 주소|네트워크", "개인 키|은행 계좌번호", "sensitive", sources="coinbase_send_receive|coinbase_security"),
        F("recurring_buy", "가상자산 정기 구매", "Recurring crypto buy", "매주 코인 자동 매수|월간 암호화폐 구매|정기 주문 만들기|코인 구매 주기|자동 매수 설정", "weekly coin purchase|monthly crypto buy|create recurring order|crypto purchase frequency|set automatic buy", "주기|금액|결제 수단", "주식 적립식|구독 결제", "submit", sources="coinbase_recurring"),
        F("cancel_recurring", "가상자산 정기 구매 취소", "Cancel recurring crypto buy", "코인 자동 매수 해제|정기 주문 삭제|암호화폐 구매 중단|열린 자동 주문 취소|반복 매수 종료", "disable crypto auto-buy|delete recurring order|stop scheduled crypto purchase|cancel open automatic order|end recurring buy", "정기 주문|취소", "구독 취소|자동이체 해제", "submit", sources="coinbase_recurring"),
        F("staking_rewards", "가상자산 스테이킹 보상", "Crypto staking rewards", "코인 보상 내역|스테이킹 수익|토큰 리워드|예상 연 수익률|보상 지급 기록", "coin reward history|staking earnings|token rewards|estimated annual yield|reward payouts", "스테이킹|보상", "카드 포인트|게임 보상", "sensitive", sources="coinbase_staking"),
        F("stake_asset", "가상자산 스테이킹", "Stake crypto asset", "코인 예치|토큰 스테이킹 시작|보상 프로그램 참여|가상자산 잠금|스테이킹 조건 동의", "stake coin|start token staking|join reward program|lock digital asset|accept staking terms", "자산|잠금|보상", "은행 예금|멤버십 가입", "submit", sources="coinbase_staking"),
        F("unstake_asset", "가상자산 언스테이킹", "Unstake crypto asset", "코인 예치 해제|스테이킹 종료|토큰 잠금 풀기|출금 대기 시작|보상 자산 회수", "unstake coin|end staking|unlock token|start unstaking wait|withdraw staked asset", "자산|대기 기간", "예금 해지|구독 해지", "submit", sources="coinbase_staking"),
        F("transaction_history", "가상자산 거래 내역", "Crypto transaction history", "코인 매수 매도 기록|암호화폐 송수신 내역|토큰 거래 명세|블록체인 전송 상태|가상자산 영수증", "crypto buy and sell history|coin transfer history|token statement|blockchain transaction status|digital asset receipt", "거래|자산|시간", "은행 거래 내역|쇼핑 주문", "sensitive", sources="coinbase_transactions|coinbase_recurring|coinbase_send_receive"),
        F("address_allowlist", "가상자산 주소 허용 목록", "Crypto address allowlist", "신뢰 지갑 주소 추가|출금 화이트리스트|주소록 별칭|새 주소 대기 기간|허용 주소만 전송", "add trusted wallet address|withdrawal allowlist|address nickname|new address hold|send only to approved addresses", "주소|보안|출금", "연락처 즐겨찾기|이메일 허용 목록", "submit", sources="coinbase_security"),
        F("account_lock", "가상자산 계정 잠금", "Lock compromised crypto account", "해킹 의심 계정 잠그기|무단 거래 신고|로그인 세션 제거|기기 접근 취소|암호화폐 계정 보호", "lock compromised account|report unauthorized transaction|remove login session|revoke device access|secure crypto account", "계정 보안|무단 접근", "기기 화면 잠금|카드 분실", "submit", sources="coinbase_security|coinbase_privacy|coinbase_fraud"),
    ),
    G(
        "sports_team", "스포츠 팀 운영", "Sports team coordination", "team_sports_service",
        "스포츠 팀|선수|코치|경기|훈련|로스터", "sports team|player|coach|game|practice|roster",
        "프로 스포츠 중계|헬스장|업무 팀", "professional sports streaming|gym membership|work team",
        "fitness_membership.hub",
        "teamsnap_help|teamsnap_features|teamsnap_mobile|teamsnap_payments|teamsnap_subscription",
        F("schedule", "팀 경기·훈련 일정", "Team game and practice schedule", "팀 캘린더|경기 일정 보기|훈련 시간|원정 경기 날짜|스포츠 행사 목록", "team calendar|game schedule|practice time|away game date|sports event list", "팀|일정|장소", "프로 경기 중계표|업무 캘린더", "view", sources="teamsnap_features|teamsnap_help"),
        F("event_details", "팀 행사 상세", "Team event details", "경기장 주소|훈련 준비물|집합 시간|상대 팀 정보|행사 메모", "game field address|practice equipment|arrival time|opponent details|event notes", "팀 행사|장소", "콘서트 티켓|일반 지도", "view", sources="teamsnap_features|teamsnap_mobile"),
        F("availability_rsvp", "팀 참석 가능 여부", "Player availability RSVP", "경기 참석 응답|훈련 가능 여부|선수 출전 응답|불참 사유|행사 RSVP", "game attendance response|practice availability|player participation|absence reason|event RSVP", "선수|행사|응답", "회의 참석|식당 예약", "submit", sources="teamsnap_features|teamsnap_help"),
        F("roster", "팀 선수 명단", "Team roster", "선수 목록|코치 연락처|등번호 보기|보호자 정보|팀 구성원 프로필", "player list|coach contact|jersey number|guardian information|team member profile", "팀|구성원", "주소록|직원 명단", "sensitive", sources="teamsnap_features|teamsnap_help"),
        F("lineup", "경기 라인업", "Game lineup", "선발 선수 확인|포지션 배치|교체 명단|출전 순서|경기 로테이션", "starting players|position assignment|substitute list|batting order|game rotation", "경기|선수|포지션", "음악 재생목록|업무 당번", "sensitive", sources="teamsnap_features|teamsnap_help"),
        F("team_chat", "스포츠 팀 채팅", "Sports team chat", "선수단 대화|코치 메시지|보호자 채팅|팀 그룹 메시지|경기 관련 답장", "team conversation|coach message|parent chat|sports group message|reply about game", "팀|대화", "업무 채팅|일반 메신저", "submit", sources="teamsnap_mobile|teamsnap_help"),
        F("announcements", "팀 공지", "Team announcements", "경기 취소 공지|훈련 변경 알림|팀 전체 방송|코치 발표|긴급 일정 안내", "game cancellation notice|practice change alert|team broadcast|coach announcement|urgent schedule update", "팀|공지", "일반 푸시 알림|학교 공지", "submit", sources="teamsnap_mobile|teamsnap_features"),
        F("assignments", "팀 역할·준비 담당", "Team assignments", "간식 담당|차량 운전 배정|장비 준비 역할|자원봉사 신청|경기 당번", "snack duty|carpool driver assignment|equipment responsibility|volunteer signup|game-day duty", "팀|담당|행사", "업무 프로젝트 배정|보육 픽업", "change", sources="teamsnap_features|teamsnap_help"),
        F("attendance_checkin", "팀 행사 체크인", "Team event check-in", "경기 도착 확인|훈련 출석 처리|선수 체크인|현장 참가 확인|행사 입장 기록", "game arrival check|practice attendance|player check-in|on-site participation|event entry record", "선수|도착|행사", "항공 체크인|직원 출근", "submit", sources="teamsnap_mobile|teamsnap_help"),
        F("live_scores", "팀 경기 실시간 점수", "Live team scores", "현재 경기 점수|실시간 경기 업데이트|이닝별 결과|득점 알림|경기 진행 상황", "current game score|live game update|inning result|scoring alert|match progress", "경기|점수", "프로 스포츠 스트리밍|게임 랭킹", "view", sources="teamsnap_mobile|teamsnap_features"),
        F("player_statistics", "선수·팀 통계", "Player and team statistics", "선수 기록 보기|팀 시즌 성적|경기별 통계|득점 순위|출전 기록", "player stats|team season record|game statistics|scoring leaders|appearance history", "팀|선수|기록", "건강 운동 기록|프로 리그", "sensitive", sources="teamsnap_features|teamsnap_help"),
        F("team_invoices", "팀 회비 청구서", "Team fee invoices", "선수 회비 내역|미납 팀 비용|시즌 청구서|대회 참가비|팀 결제 잔액", "player fee statement|unpaid team cost|season invoice|tournament fee|team payment balance", "팀|청구|회비", "보육료|구독료", "sensitive", sources="teamsnap_payments|teamsnap_mobile"),
        F("pay_team_fee", "팀 회비 납부", "Pay team fee", "선수 등록비 결제|팀 회비 내기|대회 참가비 납부|스포츠 청구서 결제|시즌 비용 지급", "pay player registration fee|pay team dues|pay tournament charge|settle sports invoice|pay season cost", "팀|결제|회비", "헬스장 회비|학교 급식비", "submit", sources="teamsnap_payments|teamsnap_mobile"),
        F("registration", "스포츠 팀 등록", "Sports team registration", "시즌 참가 신청|선수 등록 양식|팀 초대 수락|리그 가입|보호자 동의 제출", "season signup|player registration form|accept team invitation|join league|submit guardian consent", "팀|시즌|선수", "헬스장 가입|학교 입학", "submit", sources="teamsnap_help|teamsnap_features"),
        F("live_stream", "팀 경기 라이브 방송", "Team game live stream", "경기 방송 시작|팀 생중계 보기|카메라 스트리밍|경기 영상 공유|라이브 링크", "start game broadcast|watch team livestream|camera streaming|share game video|live match link", "팀|경기|영상", "프로 스포츠 중계|영상 통화", "submit", sources="teamsnap_help|teamsnap_mobile"),
    ),
)


V7_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V7_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
REQUIRED_FUNCTIONS = frozenset({
    "dating_discovery.report_profile",
    "dating_discovery.identity_verification",
    "digital_library.borrow_title",
    "digital_library.content_controls",
    "beauty_wellness_booking.booking_policy",
    "beauty_wellness_booking.deposit_payment",
    "childcare_family_portal.approved_pickups",
    "childcare_family_portal.health_medication",
    "esign_notary.apply_signature",
    "esign_notary.audit_report",
    "creator_monetization.withdraw_earnings",
    "creator_monetization.membership_tiers",
    "crypto_assets.send_crypto",
    "crypto_assets.address_allowlist",
    "sports_team.availability_rsvp",
    "sports_team.pay_team_fee",
})


class V7CatalogValidationError(ValueError):
    """Raised when the reviewed v7 layer cannot be safely materialized."""


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    # Keep layer tests stable after v7 is promoted to the canonical catalog.
    return _pre_v7_payload(json.loads(path.read_text(encoding="utf-8")))


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _pre_v7_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V7_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V7_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", [])
        if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", [])
        if str(item["intent_id"]) not in intent_ids
    ]
    result.pop("official_sources_v7", None)
    return result


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V7_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V7_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    if not present_functions and not present_intents and "official_sources_v7" not in payload:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V7CatalogValidationError("partial v7 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V7CatalogValidationError("v7 collides with a different function or intent definition")
    if payload.get("official_sources_v7") != OFFICIAL_SOURCES:
        raise V7CatalogValidationError("v7 official evidence registry differs")
    if payload.get("catalog_version") != CATALOG_V7_VERSION or payload.get("description") != CATALOG_V7_DESCRIPTION:
        raise V7CatalogValidationError("v7 materialization metadata differs")
    return True


def validate_v7_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    errors: list[str] = []
    function_ids = [str(item["function_id"]) for item in V7_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V7_INTENTS]
    terminal_ids = {
        str(item["function_id"]) for item in V7_FUNCTIONS if bool(item["terminal"])
    }
    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v7 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v7 intent IDs: {sorted(duplicates)}")
    if len(REQUIRED_DOMAINS) != 8:
        errors.append("v7 must contain exactly eight reviewed long-tail domains")
    domain_terminal_counts = Counter(
        str(item["domain"]) for item in V7_FUNCTIONS if bool(item["terminal"])
    )
    if any(domain_terminal_counts[domain] < 14 for domain in REQUIRED_DOMAINS):
        errors.append(f"every v7 domain requires at least fourteen terminals: {dict(sorted(domain_terminal_counts.items()))}")
    if len(terminal_ids) < 112:
        errors.append("v7 requires at least 112 terminal functions")
    if missing := REQUIRED_FUNCTIONS - set(function_ids):
        errors.append(f"missing required v7 functions: {sorted(missing)}")

    for source_id, source in OFFICIAL_SOURCES.items():
        parsed = urlparse(str(source.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"source {source_id} is not HTTPS")
        if source.get("evidence_level") != "official_primary":
            errors.append(f"source {source_id} is not official_primary")
        if source.get("collected_on") != COLLECTED_ON:
            errors.append(f"source {source_id} missing collection date")
        if source.get("verified_status") != 200 or not str(source.get("verification_method", "")).strip():
            errors.append(f"source {source_id} missing successful verification metadata")

    known_sources = set(OFFICIAL_SOURCES)
    used_sources: set[str] = set()
    forbidden_keys = {"x", "y", "bounds", "coordinates", "package", "package_name", "resource_id"}
    for function in V7_FUNCTIONS:
        function_id = str(function["function_id"])
        aliases = function["aliases"]
        if len(aliases["ko-KR"]) < 8 or len(aliases["en-US"]) < 8:  # type: ignore[index]
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if len(function["positive_context"]) < 6 or len(function["negative_context"]) < 4:
            errors.append(f"{function_id}: insufficient positive/negative context")
        if len(function["role_hints"]) < 5 or not function["state_cues"] or not function["risk_cues"]:
            errors.append(f"{function_id}: incomplete role/state/risk semantics")
        refs = {str(value) for value in function["source_refs"]}
        used_sources.update(refs)
        if not refs or not refs <= known_sources:
            errors.append(f"{function_id}: invalid official source refs")
        if function["evidence_level"] != "official":
            errors.append(f"{function_id}: evidence level must be official")
        if forbidden_keys.intersection(function):
            errors.append(f"{function_id}: app-specific coordinate or package data is forbidden")
        if function["state_changing"] or function["risk_level"] == "high":
            if function["automation_policy"] != "never_auto" or function["stop_policy"] != "before_action":
                errors.append(f"{function_id}: unsafe final-action boundary")
            boundary = " ".join(function["risk_cues"].get("user_boundary", []))  # type: ignore[union-attr]
            if "사용자" not in boundary or "user" not in boundary.casefold():
                errors.append(f"{function_id}: user-owned final click is not explicit")
    if used_sources != known_sources:
        errors.append(f"orphan official sources: {sorted(known_sources - used_sources)}")

    intent_terminals = [str(item["terminal_function"]) for item in V7_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v7 requires exactly one intent per terminal function")
    for intent in V7_INTENTS:
        intent_id = str(intent["intent_id"])
        localized = intent["patterns_by_locale"]
        if len(localized["ko-KR"]) < 10 or len(localized["en-US"]) < 10:  # type: ignore[index]
            errors.append(f"{intent_id}: insufficient bilingual patterns")
        if len(intent["goal_rules"]) < 24:
            errors.append(f"{intent_id}: insufficient compositional goal rules")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != intent["terminal_function"]:  # type: ignore[index]
            errors.append(f"{intent_id}: invalid app-agnostic hub-to-destination route")
        if not intent["avoid_functions"]:
            errors.append(f"{intent_id}: missing disambiguation avoid function")
        terminal = next(item for item in V7_FUNCTIONS if item["function_id"] == intent["terminal_function"])
        if terminal["state_changing"] or terminal["risk_level"] == "high":
            if intent["desired_state"] != "user_confirmation_required":
                errors.append(f"{intent_id}: consequential intent lacks user confirmation")
            if intent["terminal_condition"]["stop_policy"] != "stop_before_action":  # type: ignore[index]
                errors.append(f"{intent_id}: consequential route does not stop before action")
        for rule in intent["goal_rules"]:
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v7_"):
                errors.append(f"{intent_id}: malformed semantic rule")
            for key in ("v7_discriminative_keys", "v7_negative_context_keys", "v7_positive_context_keys"):
                values = list(rule.get(key, []))
                if values != sorted(dict.fromkeys(values)):
                    errors.append(f"{intent_id}: nondeterministic {key}")

    materialized = False
    if base_payload is not None:
        materialized = _materialization_state(base_payload)
        pre_v7 = _pre_v7_payload(base_payload) if materialized else copy.deepcopy(dict(base_payload))
        base_function_ids = {str(item["function_id"]) for item in pre_v7.get("functions", [])}
        base_intent_ids = {str(item["intent_id"]) for item in pre_v7.get("intents", [])}
        if collisions := sorted(set(function_ids).intersection(base_function_ids)):
            errors.append(f"v7 function IDs collide with v1-v6: {collisions[:12]}")
        if collisions := sorted(set(intent_ids).intersection(base_intent_ids)):
            errors.append(f"v7 intent IDs collide with v1-v6: {collisions[:12]}")
        pattern_owners: dict[str, set[str]] = {}
        for intent in [*pre_v7.get("intents", []), *V7_INTENTS]:
            owner = str(intent["intent_id"])
            for pattern in intent.get("patterns", []):
                key = _runtime_pattern_key(pattern)
                if key:
                    pattern_owners.setdefault(key, set()).add(owner)
        pattern_collisions = {key: sorted(owners) for key, owners in pattern_owners.items() if len(owners) > 1}
        if pattern_collisions:
            errors.append(f"normalized goal-pattern collisions: {list(pattern_collisions.items())[:8]}")
        base_rule_signatures = {
            _rule_signature(rule)
            for intent in pre_v7.get("intents", [])
            for rule in intent.get("goal_rules", [])
            if _rule_signature(rule)
        }
        v7_rule_owners: dict[tuple[str, ...], set[str]] = {}
        for intent in V7_INTENTS:
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if signature in base_rule_signatures:
                    errors.append(f"{intent['intent_id']}: goal rule collides with v1-v6")
                v7_rule_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
        shared_rules = {signature: sorted(owners) for signature, owners in v7_rule_owners.items() if len(owners) > 1}
        if shared_rules:
            errors.append(f"v7 goal-rule collisions: {list(shared_rules.items())[:8]}")

    semantic_payload = copy.deepcopy({"functions": V7_FUNCTIONS, "intents": V7_INTENTS})
    for function in semantic_payload["functions"]:
        function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = (
        "com.", "package name", "resource-id", "screen coordinate", "x coordinate",
        "tinder", "libby", "fresha", "brightwheel", "docusign", "adobe",
        "patreon", "coinbase", "teamsnap",
    )
    if any(re.search(rf"(?<![a-z0-9]){re.escape(fragment)}(?![a-z0-9])", semantic_text) for fragment in forbidden_fragments):
        errors.append("v7 runtime semantics contain an app identity or recorded UI path")

    if errors:
        raise V7CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V7_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V7_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_terminal_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES),
        "aliases": sum(len(values) for item in V7_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V7_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V7_INTENTS),
        "compositional_goal_rules": sum(
            1 for item in V7_INTENTS for rule in item["goal_rules"]
            if rule["rule_kind"] in {"v7_compositional_domain", "v7_consequence_context"}
        ),
        "state_changing": sum(bool(item["state_changing"]) for item in V7_FUNCTIONS),
        "high_risk": sum(item["risk_level"] == "high" for item in V7_FUNCTIONS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic validated copy without mutating the caller."""

    validate_v7_data(base_payload)
    if _materialization_state(base_payload):
        return copy.deepcopy(dict(base_payload))
    merged = copy.deepcopy(dict(base_payload))
    merged["catalog_version"] = CATALOG_V7_VERSION
    merged["description"] = CATALOG_V7_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V7_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V7_INTENTS)]
    merged["official_sources_v7"] = copy.deepcopy(OFFICIAL_SOURCES)
    return merged


def main() -> int:
    print(json.dumps(validate_v7_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
