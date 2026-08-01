from __future__ import annotations

"""Independent v4 ontology for broad everyday Android navigation.

The module deliberately contains reusable function concepts rather than app
coordinates, benchmark sentences, or screenshots.  It can be reviewed and
validated on its own, then merged with the materialized v3 catalog without
mutating either input.  Re-merging an identical v4 payload is idempotent.

Safety invariant: every state-changing or high-risk destination is
``never_auto`` and stops before the user-owned final click.
"""

import argparse
import copy
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
CATALOG_V4_VERSION = "4.0.0-broad-services"
VERIFIED_ON = "2026-07-30"


# These pages were checked directly from their publishers on VERIFIED_ON.
# The registry is evidence metadata, not a recipe for app-specific clicking.
OFFICIAL_SOURCES: dict[str, dict[str, str | int]] = {
    "chrome_tabs": {
        "publisher": "Google Chrome Help",
        "title": "Manage tabs in Chrome",
        "url": "https://support.google.com/chrome/answer/2391819",
        "verified_status": 200,
    },
    "chrome_sync": {
        "publisher": "Google Chrome Help",
        "title": "Get bookmarks, passwords, and more on all your devices",
        "url": "https://support.google.com/chrome/answer/165139",
        "verified_status": 200,
    },
    "chrome_bookmarks": {
        "publisher": "Google Chrome Help",
        "title": "Create, find and edit bookmarks in Chrome",
        "url": "https://support.google.com/chrome/answer/188842",
        "verified_status": 200,
    },
    "chrome_history": {
        "publisher": "Google Chrome Help",
        "title": "Check or delete your Chrome browsing history",
        "url": "https://support.google.com/chrome/answer/95589",
        "verified_status": 200,
    },
    "chrome_downloads": {
        "publisher": "Google Chrome Help",
        "title": "Download a file",
        "url": "https://support.google.com/chrome/answer/95759",
        "verified_status": 200,
    },
    "chrome_site_permissions": {
        "publisher": "Google Chrome Help",
        "title": "Change site settings permissions",
        "url": "https://support.google.com/chrome/answer/114662",
        "verified_status": 200,
    },
    "chrome_passwords": {
        "publisher": "Google Chrome Help",
        "title": "Manage passwords in Chrome",
        "url": "https://support.google.com/chrome/answer/95606",
        "verified_status": 200,
    },
    "chrome_autofill": {
        "publisher": "Google Chrome Help",
        "title": "Fill out forms automatically in Chrome",
        "url": "https://support.google.com/chrome/answer/142893",
        "verified_status": 200,
    },
    "chrome_translate": {
        "publisher": "Google Chrome Help",
        "title": "Translate pages and change Chrome languages",
        "url": "https://support.google.com/chrome/answer/173424",
        "verified_status": 200,
    },
    "chrome_search": {
        "publisher": "Google Chrome Help",
        "title": "Set default search engine and site search shortcuts",
        "url": "https://support.google.com/chrome/answer/95426",
        "verified_status": 200,
    },
    "chrome_incognito": {
        "publisher": "Google Chrome Help",
        "title": "Browse in Incognito mode",
        "url": "https://support.google.com/chrome/answer/95464",
        "verified_status": 200,
    },
    "messages_conversations": {
        "publisher": "Google Messages Help",
        "title": "Archive, delete and read conversations in Google Messages",
        "url": "https://support.google.com/messages/answer/7028817",
        "verified_status": 200,
    },
    "messages_spam": {
        "publisher": "Google Messages Help",
        "title": "Report spam in Google Messages",
        "url": "https://support.google.com/messages/answer/9061432",
        "verified_status": 200,
    },
    "messages_pairing": {
        "publisher": "Google Messages Help",
        "title": "Check messages on a computer or Android tablet",
        "url": "https://support.google.com/messages/answer/7611075",
        "verified_status": 200,
    },
    "phone_blocking": {
        "publisher": "Phone app Help",
        "title": "Block or unblock a phone number",
        "url": "https://support.google.com/phoneapp/answer/6325463",
        "verified_status": 200,
    },
    "phone_spam": {
        "publisher": "Phone app Help",
        "title": "Use caller ID and spam protection",
        "url": "https://support.google.com/phoneapp/answer/3459196",
        "verified_status": 200,
    },
    "play_updates": {
        "publisher": "Google Play Help",
        "title": "How to update apps on Android",
        "url": "https://support.google.com/googleplay/answer/113412",
        "verified_status": 200,
    },
    "play_beta": {
        "publisher": "Google Play Help",
        "title": "Try new Android apps before their official release",
        "url": "https://support.google.com/googleplay/answer/7003180",
        "verified_status": 200,
    },
    "play_refunds": {
        "publisher": "Google Play Help",
        "title": "Learn about Google Play refund policies",
        "url": "https://support.google.com/googleplay/answer/2479637",
        "verified_status": 200,
    },
    "play_budget": {
        "publisher": "Google Play Help",
        "title": "Set a budget for Google Play expenses",
        "url": "https://support.google.com/googleplay/answer/9281767",
        "verified_status": 200,
    },
    "play_subscriptions": {
        "publisher": "Google Play Help",
        "title": "Cancel, pause, or change a subscription on Google Play",
        "url": "https://support.google.com/googleplay/answer/7018481",
        "verified_status": 200,
    },
    "play_family_payment": {
        "publisher": "Google Play Help",
        "title": "Use a family payment method on Google Play",
        "url": "https://support.google.com/googleplay/answer/6294544",
        "verified_status": 200,
    },
    "play_purchase_approval": {
        "publisher": "Google Play Help",
        "title": "Purchase approvals on Google Play",
        "url": "https://support.google.com/googleplay/answer/7039872",
        "verified_status": 200,
    },
    "play_parental_controls": {
        "publisher": "Google Play Help",
        "title": "Set up content restrictions on Google Play",
        "url": "https://support.google.com/googleplay/answer/1075738",
        "verified_status": 200,
    },
    "android_backup": {
        "publisher": "Android Help",
        "title": "Back up or restore data on an Android device",
        "url": "https://support.google.com/android/answer/2819582",
        "verified_status": 200,
    },
    "android_quick_share": {
        "publisher": "Android Help",
        "title": "Use Quick Share on an Android device",
        "url": "https://support.google.com/android/answer/9286773",
        "verified_status": 200,
    },
    "android_cast": {
        "publisher": "Google Streaming Help",
        "title": "Cast media from Google Cast-enabled apps",
        "url": "https://support.google.com/chromecast/answer/3006709",
        "verified_status": 200,
    },
    "android_usb": {
        "publisher": "Android Help",
        "title": "Transfer files between a computer and Android device",
        "url": "https://support.google.com/android/answer/9064445",
        "verified_status": 200,
    },
    "android_nfc": {
        "publisher": "Android Developers",
        "title": "Near field communication overview",
        "url": "https://developer.android.com/develop/connectivity/nfc",
        "verified_status": 200,
    },
    "android_data_saver": {
        "publisher": "Android Developers",
        "title": "Optimize network data usage",
        "url": "https://developer.android.com/training/basics/network-ops/data-saver",
        "verified_status": 200,
    },
    "android_app_languages": {
        "publisher": "Android Developers",
        "title": "Per-app language preferences",
        "url": "https://developer.android.com/guide/topics/resources/app-languages",
        "verified_status": 200,
    },
    "android_emergency": {
        "publisher": "Android Help",
        "title": "Get help during an emergency with an Android phone",
        "url": "https://support.google.com/android/answer/9319337",
        "verified_status": 200,
    },
    "android_safety_services": {
        "publisher": "Android Help",
        "title": "Google Play services for safety and emergency",
        "url": "https://support.google.com/android/answer/12464968",
        "verified_status": 200,
    },
    "maps_transit": {
        "publisher": "Google Maps Help",
        "title": "Get train and bus departures",
        "url": "https://support.google.com/maps/answer/6142130",
        "verified_status": 200,
    },
    "google_weather": {
        "publisher": "Google Search Help",
        "title": "How Google Weather works",
        "url": "https://support.google.com/websearch/answer/13687874",
        "verified_status": 200,
    },
    "google_news": {
        "publisher": "Google News Help",
        "title": "Manage Google News notifications",
        "url": "https://support.google.com/googlenews/answer/9005590",
        "verified_status": 200,
    },
    "usps_informed_delivery": {
        "publisher": "United States Postal Service",
        "title": "Informed Delivery mail and package notifications",
        "url": "https://www.usps.com/manage/informed-delivery.htm",
        "verified_status": 200,
    },
    "usps_package_intercept": {
        "publisher": "United States Postal Service",
        "title": "Package Intercept",
        "url": "https://www.usps.com/manage/package-intercept.htm",
        "verified_status": 200,
    },
    "ftc_delivery_disputes": {
        "publisher": "US Federal Trade Commission",
        "title": "What to do about goods that never arrived",
        "url": "https://consumer.ftc.gov/articles/what-do-if-youre-billed-things-you-never-got-or-you-get-unordered-products",
        "verified_status": 200,
    },
    "usajobs_profile": {
        "publisher": "USAJOBS",
        "title": "How to create a profile",
        "url": "https://help.usajobs.gov/how-to/account/profile",
        "verified_status": 200,
    },
    "usajobs_saved_search": {
        "publisher": "USAJOBS",
        "title": "How to save a job search",
        "url": "https://help.usajobs.gov/how-to/search/save",
        "verified_status": 200,
    },
    "usagov_rental_assistance": {
        "publisher": "USAGov",
        "title": "Rental assistance",
        "url": "https://www.usa.gov/rental-housing-programs",
        "verified_status": 200,
    },
    "usagov_utility_help": {
        "publisher": "USAGov",
        "title": "Help with utility bills",
        "url": "https://www.usa.gov/help-with-utility-bills",
        "verified_status": 200,
    },
}

for _source in OFFICIAL_SOURCES.values():
    _source["verified_on"] = VERIFIED_ON


def _terms(value: str | Iterable[str]) -> tuple[str, ...]:
    values = value.split("|") if isinstance(value, str) else value
    return tuple(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _dedupe_aliases(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = raw_value.strip()
        normalized = " ".join(value.casefold().split())
        if value and normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


@dataclass(frozen=True)
class FeatureSeed:
    function_id: str
    name_ko: str
    name_en: str
    ko_aliases: tuple[str, ...]
    en_aliases: tuple[str, ...]
    positive: tuple[str, ...]
    negative: tuple[str, ...]
    mode: str = "view"
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class GroupSeed:
    domain: str
    root_id: str
    root_ko: str
    root_en: str
    scope: str
    ko_context: tuple[str, ...]
    en_context: tuple[str, ...]
    negative_ko: tuple[str, ...]
    negative_en: tuple[str, ...]
    avoid_root: str
    source_refs: tuple[str, ...]
    features: tuple[FeatureSeed, ...]


def F(
    function_id: str,
    name_ko: str,
    name_en: str,
    ko_aliases: str,
    en_aliases: str,
    positive: str,
    negative: str,
    mode: str = "view",
    *,
    sources: str = "",
) -> FeatureSeed:
    return FeatureSeed(
        function_id=function_id,
        name_ko=name_ko,
        name_en=name_en,
        ko_aliases=_terms(ko_aliases),
        en_aliases=_terms(en_aliases),
        positive=_terms(positive),
        negative=_terms(negative),
        mode=mode,
        source_refs=_terms(sources),
    )


def G(
    domain: str,
    root_id: str,
    root_ko: str,
    root_en: str,
    scope: str,
    ko_context: str,
    en_context: str,
    negative_ko: str,
    negative_en: str,
    avoid_root: str,
    sources: str,
    *features: FeatureSeed,
) -> GroupSeed:
    return GroupSeed(
        domain=domain,
        root_id=root_id,
        root_ko=root_ko,
        root_en=root_en,
        scope=scope,
        ko_context=_terms(ko_context),
        en_context=_terms(en_context),
        negative_ko=_terms(negative_ko),
        negative_en=_terms(negative_en),
        avoid_root=avoid_root,
        source_refs=_terms(sources),
        features=tuple(features),
    )


MODE_METADATA: dict[str, dict[str, object]] = {
    "view": {
        "risk_level": "low", "automation_policy": "safe_navigation",
        "state_changing": False, "node_kind": "destination",
        "stop_policy": "on_destination_screen",
    },
    "sensitive": {
        "risk_level": "high", "automation_policy": "never_auto",
        "state_changing": False, "node_kind": "sensitive_destination",
        "stop_policy": "before_action",
    },
    "change": {
        "risk_level": "medium", "automation_policy": "never_auto",
        "state_changing": True, "node_kind": "state_change",
        "stop_policy": "before_action",
    },
    "submit": {
        "risk_level": "high", "automation_policy": "never_auto",
        "state_changing": True, "node_kind": "external_action",
        "stop_policy": "before_action",
    },
}


GROUPS: tuple[GroupSeed, ...] = (
    G(
        "browser_web", "browser.hub", "브라우저", "Browser", "web_session",
        "웹|인터넷|페이지|사이트", "web|internet|page|site",
        "문자 대화|전화 통화", "text conversation|phone call",
        "messaging.hub", "chrome_tabs|chrome_sync|chrome_bookmarks|chrome_history|chrome_downloads|chrome_site_permissions|chrome_passwords|chrome_autofill|chrome_translate|chrome_search|chrome_incognito",
        F("browser.tabs", "탭 목록", "Browser tabs", "열린 탭|탭 전환|탭 선택", "open tabs|switch tab|tab switcher", "열린 웹페이지|탭 개수", "앱 전환|최근 앱", sources="chrome_tabs"),
        F("browser.tab_groups", "탭 그룹", "Tab groups", "탭 묶기|그룹 탭|탭 모음", "group tabs|tab collection|tab groups", "여러 웹페이지|그룹 이름", "북마크 폴더|앱 그룹", "change", sources="chrome_tabs"),
        F("browser.bookmarks", "북마크", "Bookmarks", "즐겨찾기|저장한 페이지|웹 북마크", "favorites|saved pages|web bookmarks", "웹 주소|저장된 사이트", "읽기 목록|다운로드", sources="chrome_bookmarks"),
        F("browser.history", "방문 기록", "Browsing history", "검색 기록|웹 기록|최근 방문", "web history|recently visited|browsing activity", "날짜별 사이트|방문 페이지", "통화 기록|주문 내역", "sensitive", sources="chrome_history"),
        F("browser.clear_data", "인터넷 사용 기록 삭제", "Clear browsing data", "쿠키 삭제|캐시 삭제|방문 기록 지우기", "clear cookies|clear cache|delete browsing data", "기간 선택|쿠키와 사이트 데이터", "앱 캐시|파일 삭제", "submit", sources="chrome_history"),
        F("browser.downloads", "다운로드", "Browser downloads", "받은 파일|웹 다운로드|다운로드 목록", "downloaded files|browser downloads|download list", "파일 이름|다운로드 상태", "앱 설치|클라우드 파일", sources="chrome_downloads"),
        F("browser.site_permissions", "사이트 권한", "Site permissions", "웹사이트 권한|사이트 설정|웹 권한", "website permissions|site settings|web permissions", "카메라|마이크|위치|알림", "앱 권한|기기 관리자", "change", sources="chrome_site_permissions"),
        F("browser.password_manager", "비밀번호 관리자", "Password manager", "저장된 비밀번호|웹 암호|로그인 정보", "saved passwords|web passwords|login credentials", "사이트 계정|비밀번호 확인", "화면 잠금|SIM PIN", "sensitive", sources="chrome_passwords|chrome_sync"),
        F("browser.autofill_addresses", "주소 자동 완성", "Autofill addresses", "주소 저장|양식 주소|연락처 자동입력", "saved addresses|form addresses|address autofill", "이름|주소|전화번호", "배송지 목록|지도 주소", "change", sources="chrome_autofill"),
        F("browser.autofill_payments", "결제 수단 자동 완성", "Payment autofill", "카드 자동 입력|저장 카드|결제정보 자동완성", "saved cards|card autofill|payment autofill", "카드 번호|결제 양식", "스토어 결제수단|구독 결제", "sensitive", sources="chrome_autofill"),
        F("browser.translate", "페이지 번역", "Translate page", "웹 번역|이 페이지 번역|언어 번역", "translate website|translate this page|page language", "원문 언어|번역 언어", "앱 언어|자막 언어", sources="chrome_translate"),
        F("browser.reader_mode", "읽기 모드", "Reader mode", "간소화 보기|읽기용 보기|리더 보기", "simplified view|reading view|reader view", "본문|글꼴|방해 요소 제거", "화면 읽기|접근성 음성", sources="chrome_tabs"),
        F("browser.default_search", "기본 검색엔진", "Default search engine", "검색 제공업체|주소창 검색|기본 검색", "search provider|address bar search|default search", "검색엔진 목록|사이트 검색", "기본 브라우저|앱 검색", "change", sources="chrome_search"),
        F("browser.incognito", "시크릿 모드", "Incognito mode", "비공개 탭|익명 브라우징|시크릿 탭", "private tab|private browsing|incognito tab", "기록을 남기지 않는 탭|비공개 세션", "게스트 계정|VPN", "change", sources="chrome_incognito"),
        F("browser.desktop_site", "데스크톱 사이트", "Desktop site", "PC 버전|데스크톱 보기|웹 PC 화면", "desktop version|request desktop site|desktop view", "모바일 페이지|웹 레이아웃", "화면 회전|태블릿 모드", "change", sources="chrome_tabs"),
    ),
    G(
        "messaging", "messaging.hub", "메시지", "Messages", "communications",
        "문자|대화|채팅|메시지", "text|conversation|chat|message",
        "이메일|전화 설정", "email|call settings",
        "calls.hub", "messages_conversations|messages_spam|messages_pairing",
        F("messaging.archive", "대화 보관", "Archive conversation", "문자 보관|대화 숨기기|보관함으로 이동", "archive chat|hide conversation|move to archive", "대화 목록|보관함", "삭제|스팸 신고", "change", sources="messages_conversations"),
        F("messaging.unarchive", "대화 보관 해제", "Unarchive conversation", "보관함에서 복원|대화 다시 표시|문자 보관 취소", "restore archived chat|show conversation again|remove from archive", "보관된 대화|받은편지함", "백업 복원|삭제 취소", "change", sources="messages_conversations"),
        F("messaging.delete", "대화 삭제", "Delete conversation", "문자 지우기|채팅 삭제|메시지 스레드 삭제", "delete chat|erase conversation|remove message thread", "삭제 확인|대화 내용", "보관|읽음 처리", "submit", sources="messages_conversations"),
        F("messaging.mute", "대화 알림 끄기", "Mute conversation", "채팅방 음소거|문자 알림 끄기|대화 조용히", "mute chat|silence conversation|turn off chat alerts", "알림 기간|대화별 알림", "전체 알림|전화 벨소리", "change", sources="messages_conversations"),
        F("messaging.pin", "대화 고정", "Pin conversation", "채팅 상단 고정|문자 고정|대화 핀", "pin chat|keep conversation on top|pin thread", "대화 목록 상단|고정 아이콘", "홈 화면 고정|메시지 별표", "change", sources="messages_conversations"),
        F("messaging.mark_spam", "스팸 신고", "Report message spam", "문자 스팸 신고|대화 신고|스팸으로 차단", "report text spam|report conversation|mark as spam", "발신자|신고 및 차단", "보관|단순 삭제", "submit", sources="messages_spam"),
        F("messaging.block_sender", "메시지 발신자 차단", "Block message sender", "문자 번호 차단|채팅 상대 차단|메시지 수신 거부", "block text number|block chat sender|stop messages", "발신 번호|차단 확인", "알림 끄기|스팸함 보기", "submit", sources="messages_spam"),
        F("messaging.group_create", "그룹 대화 만들기", "Create group conversation", "단체 문자|새 그룹 채팅|여러 명 대화", "group text|new group chat|multi-person conversation", "참여자 선택|그룹 이름", "연락처 그룹|영상 회의", "submit", sources="messages_conversations"),
        F("messaging.group_members", "그룹 참여자 관리", "Manage group members", "채팅방 멤버|참여자 추가|그룹에서 나가기", "chat members|add participant|leave group", "그룹 정보|참여자 목록", "가족 그룹|연락처 목록", "submit", sources="messages_conversations"),
        F("messaging.rcs", "RCS 채팅 기능", "RCS chats", "채팅 기능|읽음 확인|입력 중 표시", "chat features|read receipts|typing indicators", "연결 상태|RCS|고급 메시징", "SMS 요금|일반 알림", "change", sources="messages_conversations"),
        F("messaging.device_pairing", "메시지 기기 페어링", "Message device pairing", "웹용 메시지|QR 기기 연결|컴퓨터에서 문자", "messages for web|pair with QR|text on computer", "QR 코드|연결된 기기", "블루투스 페어링|화면 미러링", "sensitive", sources="messages_pairing"),
        F("messaging.backup", "메시지 백업", "Message backup", "문자 백업|대화 저장|메시지 복원 준비", "back up texts|save conversations|message backup", "클라우드 백업|SMS 데이터", "채팅 보관|파일 내보내기", "change", sources="android_backup"),
        F("messaging.search", "메시지 검색", "Search messages", "대화 찾기|문자 내용 검색|채팅 검색", "find conversation|search text messages|chat search", "발신자|키워드|날짜", "웹 검색|연락처 검색", sources="messages_conversations"),
        F("messaging.notification_settings", "메시지 알림 설정", "Message notification settings", "문자 알림음|메시지 팝업|대화 알림", "message alerts|text notification sound|conversation notifications", "알림 카테고리|소리|진동", "전화 벨소리|전체 앱 알림", "change", sources="messages_conversations"),
    ),
    G(
        "calls", "calls.hub", "전화", "Calls", "communications",
        "통화|전화번호|발신|수신", "call|phone number|dial|caller",
        "문자 대화|영상 회의", "text chat|video meeting",
        "messaging.hub", "phone_blocking|phone_spam",
        F("calls.history", "통화 기록", "Call history", "최근 통화|발신 수신 기록|통화 내역", "recent calls|incoming outgoing log|call log", "전화번호|통화 시간|부재중", "웹 방문 기록|결제 내역", "sensitive", sources="phone_blocking"),
        F("calls.block_number", "전화번호 차단", "Block phone number", "수신 차단|발신자 차단|번호 블랙리스트", "block caller|block calls|blocked numbers", "전화번호|차단 확인", "문자 알림 끄기|스팸 표시", "submit", sources="phone_blocking"),
        F("calls.unblock_number", "전화번호 차단 해제", "Unblock phone number", "수신 차단 풀기|차단 번호 복원|번호 허용", "unblock caller|allow blocked number|remove call block", "차단 목록|허용 확인", "연락처 복원|스팸 신고 취소", "submit", sources="phone_blocking"),
        F("calls.caller_id_spam", "발신자 ID 및 스팸", "Caller ID and spam", "스팸 전화 감지|발신자 표시|스팸 보호", "spam call detection|caller identification|spam protection", "알 수 없는 번호|스팸 경고", "내 번호 표시|문자 스팸", "change", sources="phone_spam"),
        F("calls.settings", "통화 설정", "Call settings", "전화 앱 설정|수신 설정|발신 설정", "phone app settings|incoming call settings|outgoing call settings", "통화 계정|소리|응답", "기기 소리|메시지 알림", sources="phone_spam"),
        F("calls.voicemail", "음성사서함", "Voicemail", "보이스메일|음성 메시지|부재중 녹음", "voice mail|voice messages|missed call recording", "인사말|비밀번호|메시지", "통화 녹음|음성 메모", "sensitive", sources="phone_spam"),
        F("calls.wifi_calling", "Wi-Fi 통화", "Wi-Fi calling", "와이파이 콜|무선 인터넷 통화|Wi-Fi로 전화", "wifi calls|call over wireless|voice over wifi", "통신사|긴급 주소|연결", "인터넷 전화 앱|영상 통화", "change", sources="phone_spam"),
        F("calls.call_forwarding", "착신 전환", "Call forwarding", "전화 돌리기|다른 번호로 연결|수신 전환", "forward calls|redirect calls|send calls to another number", "전환 번호|조건|통신사", "메시지 전달|번호 변경", "submit", sources="phone_spam"),
        F("calls.recording", "통화 녹음", "Call recording", "전화 녹음|통화 자동 녹음|녹음된 통화", "record call|automatic call recording|recorded calls", "녹음 고지|법적 동의|저장", "음성 메모|화면 녹화", "submit", sources="phone_spam"),
    ),
    G(
        "app_store", "app_store.hub", "앱 스토어", "App store", "software_distribution",
        "앱|게임|설치|스토어", "app|game|install|store",
        "온라인 쇼핑|기기 설정", "online shopping|device settings",
        "marketplace.hub", "play_updates|play_beta|play_refunds|play_budget|play_subscriptions",
        F("app_store.updates", "앱 업데이트", "App updates", "업데이트 가능|모두 업데이트|앱 최신 버전", "updates available|update all|latest app version", "설치된 앱|새 버전", "시스템 업데이트|뉴스 새로고침", "change", sources="play_updates"),
        F("app_store.auto_update", "앱 자동 업데이트", "Automatic app updates", "자동 업뎃|Wi-Fi에서 업데이트|앱 자동갱신", "auto-update apps|update over wifi|automatic updates", "네트워크 환경|업데이트 방식", "구독 자동 갱신|OS 업데이트", "change", sources="play_updates"),
        F("app_store.library", "앱 라이브러리", "App library", "구매한 앱|설치했던 앱|내 앱 목록", "purchased apps|previously installed apps|my app library", "계정의 앱|설치되지 않음", "사진 보관함|도서관", sources="play_updates"),
        F("app_store.beta_join", "베타 프로그램 참여", "Join app beta", "테스터 참여|출시 전 버전|베타 신청", "become tester|pre-release version|join beta", "개발 중 앱|테스트 버전", "사전 등록|리뷰 작성", "submit", sources="play_beta"),
        F("app_store.beta_leave", "베타 프로그램 탈퇴", "Leave app beta", "테스터 나가기|정식 버전 복귀|베타 종료", "leave testing|return to stable|exit beta", "베타 앱|탈퇴 확인", "앱 제거|계정 탈퇴", "submit", sources="play_beta"),
        F("app_store.refund_request", "앱 구매 환불", "Request app refund", "구매 취소|결제 환불|앱 환불 신청", "cancel purchase|refund app payment|request refund", "주문 선택|환불 사유|제출", "구독 해지|배송 반품", "submit", sources="play_refunds"),
        F("app_store.budget", "스토어 예산", "Store budget", "월 지출 한도|구매 예산|비용 추적", "monthly spending limit|purchase budget|track expenses", "기간|예산 금액|사용액", "데이터 한도|가족 결제", "change", sources="play_budget"),
        F("app_store.subscriptions", "스토어 구독 관리", "Store subscriptions", "앱 구독 목록|정기 결제 관리|구독 변경", "app subscriptions|recurring payments|manage subscription", "다음 결제일|요금제|해지", "웹 구독|앱 구매", "sensitive", sources="play_subscriptions"),
        F("app_store.reviews", "앱 리뷰", "App reviews", "평점 작성|리뷰 수정|내 리뷰", "rate app|edit review|my reviews", "별점|후기|개발자 답변", "상품 리뷰|신고", "submit", sources="play_updates"),
        F("app_store.wishlist", "앱 위시리스트", "App wishlist", "찜한 앱|관심 앱|나중에 설치", "saved apps|favorite apps|install later", "저장 목록|앱 상세", "쇼핑 찜|사전 등록", "change", sources="play_updates"),
        F("app_store.preregister", "앱 사전 등록", "App pre-registration", "출시 알림 신청|게임 사전예약|출시 전 등록", "notify on release|pre-register game|register before launch", "출시 예정|자동 설치|알림", "베타 참여|예약 구매", "submit", sources="play_beta"),
        F("app_store.install_history", "앱 설치 기록", "App install history", "다운로드 기록|이전 앱|설치 내역", "download history|past apps|installation history", "계정|기기|설치 날짜", "브라우저 다운로드|구매 영수증", "sensitive", sources="play_updates"),
    ),
    G(
        "family_store", "family_store.hub", "가족 구매 관리", "Family purchase management", "family_account",
        "가족 그룹|자녀|구매 승인|보호자", "family group|child|purchase approval|guardian",
        "일반 결제|회사 계정", "personal payment|work account",
        "app_store.hub", "play_family_payment|play_purchase_approval|play_parental_controls|play_budget",
        F("family_store.payment_method", "가족 결제 수단", "Family payment method", "가족 카드|공용 결제|가족 구매 카드", "family card|shared payment|family purchase card", "가족 관리자|결제 수단", "개인 카드|브라우저 자동완성", "sensitive", sources="play_family_payment"),
        F("family_store.purchase_approval", "구매 승인", "Purchase approval", "자녀 구매 요청|보호자 승인|구매 허락", "child purchase request|guardian approval|approve purchase", "요청 목록|가격|승인자", "앱 권한|로그인 승인", "submit", sources="play_purchase_approval"),
        F("family_store.approval_rules", "구매 승인 규칙", "Purchase approval rules", "모든 콘텐츠 승인|인앱 구매 승인|승인 기준", "approve all content|in-app purchase approval|approval policy", "자녀 계정|콘텐츠 유형", "알림 설정|예산만 설정", "change", sources="play_purchase_approval"),
        F("family_store.parental_controls", "스토어 자녀 보호", "Store parental controls", "콘텐츠 제한|연령 제한|자녀 보호 기능", "content restriction|age rating limit|parental controls", "PIN|앱 게임 등급", "화면 시간|웹 사이트 권한", "change", sources="play_parental_controls"),
        F("family_store.content_rating", "콘텐츠 등급 제한", "Content rating limit", "연령별 앱 제한|게임 등급|부적절 콘텐츠", "age-based app limit|game rating|mature content", "앱 및 게임|영화|등급", "뉴스 관심사|추천 설정", "change", sources="play_parental_controls"),
        F("family_store.family_library", "가족 라이브러리", "Family library", "가족과 앱 공유|구매 콘텐츠 공유|가족 보관함", "share apps with family|shared purchases|family collection", "공유 가능 콘텐츠|가족 구성원", "앱 라이브러리|클라우드 공유", "change", sources="play_family_payment"),
        F("family_store.member_manage", "가족 구성원 관리", "Manage family members", "가족 초대|구성원 삭제|자녀 계정", "invite family|remove member|child account", "가족 그룹|관리자|초대", "채팅 참여자|연락처 그룹", "submit", sources="play_family_payment"),
        F("family_store.spending_activity", "가족 구매 내역", "Family purchase activity", "자녀 결제 내역|가족 지출|구매 기록", "child purchase history|family spending|purchase activity", "금액|구성원|날짜", "개인 주문|통화 기록", "sensitive", sources="play_budget|play_family_payment"),
        F("family_store.subscription_controls", "자녀 구독 관리", "Child subscription controls", "가족 구독|자녀 정기 결제|구독 승인", "family subscriptions|child recurring payment|subscription approval", "구독 앱|결제일|보호자", "개인 구독|앱 설치", "sensitive", sources="play_subscriptions|play_purchase_approval"),
    ),
    G(
        "android_backup", "android_backup.hub", "기기 백업 및 복원", "Device backup and restore", "device_data",
        "안드로이드|기기 데이터|백업|복원", "android|device data|backup|restore",
        "앱 보관|메시지 보관", "app archive|message archive",
        "android_connectivity.hub", "android_backup",
        F("android_backup.device_backup", "기기 데이터 백업", "Device data backup", "휴대폰 백업|자동 백업|클라우드 기기 백업", "phone backup|automatic backup|cloud device backup", "앱 데이터|통화 기록|설정|SMS", "파일 복사|사진만 백업", "change", sources="android_backup"),
        F("android_backup.backup_account", "백업 계정", "Backup account", "백업용 계정|클라우드 계정 선택|백업 저장 계정", "backup account|choose cloud account|backup destination account", "계정 이메일|저장공간|백업", "로그인 계정|결제 계정", "sensitive", sources="android_backup"),
        F("android_backup.restore_device", "기기 데이터 복원", "Restore device data", "휴대폰 복원|백업에서 가져오기|새 기기로 복구", "restore phone|recover from backup|restore to new device", "백업 선택|복원할 데이터|기기", "공장 초기화|파일 휴지통 복원", "submit", sources="android_backup"),
        F("android_backup.backup_details", "백업 세부정보", "Backup details", "백업된 항목|마지막 백업|백업 상태", "backed-up items|last backup|backup status", "앱|사진|SMS|시간", "저장공간 사용량|동기화 상태", "sensitive", sources="android_backup"),
        F("android_backup.manual_backup", "지금 백업", "Back up now", "수동 백업|즉시 백업|백업 시작", "manual backup|backup immediately|start backup", "현재 네트워크|배터리|백업 계정", "동기화|파일 다운로드", "submit", sources="android_backup"),
        F("android_backup.transfer_setup", "새 기기 데이터 전송", "New device transfer", "기기 간 복사|새 휴대폰 설정|데이터 옮기기", "copy between devices|set up new phone|move device data", "케이블|무선 전송|이전 기기", "eSIM 이전|파일 하나 전송", "submit", sources="android_backup|android_usb"),
        F("android_backup.delete_backup", "기기 백업 삭제", "Delete device backup", "클라우드 백업 지우기|백업본 삭제|이전 기기 백업 제거", "erase cloud backup|delete backup copy|remove old device backup", "기기 이름|백업 날짜|삭제 경고", "기기 초기화|앱 삭제", "submit", sources="android_backup"),
    ),
    G(
        "android_connectivity", "android_connectivity.hub", "연결 및 공유", "Connected devices and sharing", "device_system",
        "연결|무선|주변 기기|공유", "connectivity|wireless|nearby device|sharing",
        "계정 백업|웹 사이트", "account backup|website",
        "android_backup.hub", "android_quick_share|android_cast|android_usb|android_nfc|android_data_saver|android_app_languages",
        F("android_connectivity.quick_share", "Quick Share", "Quick Share", "빠른 공유|주변 공유|근처 기기로 보내기", "nearby share|share nearby|send to nearby device", "주변 기기 검색|공개 범위|파일", "인터넷 공유|위치 공유", "submit", sources="android_quick_share"),
        F("android_connectivity.quick_share_visibility", "Quick Share 공개 범위", "Quick Share visibility", "기기 공개 대상|주변 공유 공개|내 기기 표시", "device visibility|nearby visibility|who can discover device", "내 기기|연락처|모든 사용자", "블루투스 이름|위치 공개", "change", sources="android_quick_share"),
        F("android_connectivity.cast", "화면 및 미디어 전송", "Cast screen and media", "캐스트|TV로 보내기|화면 미러링", "cast|send to TV|screen mirroring", "사용 가능한 디스플레이|TV|미디어", "파일 전송|영상 통화", "submit", sources="android_cast"),
        F("android_connectivity.nfc", "NFC", "NFC", "근거리 통신|태그 인식|NFC 켜기", "near field communication|scan tag|turn on NFC", "비접촉 태그|결제 단말|연결", "블루투스|QR 스캔", "change", sources="android_nfc"),
        F("android_connectivity.contactless_payment", "비접촉 결제 기본 앱", "Default contactless payment", "NFC 결제 앱|탭 결제|기본 지갑", "NFC payment app|tap to pay|default wallet", "결제 서비스|기본 앱|잠금 해제", "스토어 결제|브라우저 카드", "sensitive", sources="android_nfc"),
        F("android_connectivity.usb_preferences", "USB 환경설정", "USB preferences", "USB 용도|파일 전송 모드|충전 전용", "USB use|file transfer mode|charge only", "연결된 컴퓨터|MTP|테더링", "무선 공유|케이블 백업", "change", sources="android_usb"),
        F("android_connectivity.default_apps", "기본 앱", "Default apps", "기본 브라우저|기본 전화 앱|링크 열기 앱", "default browser|default phone app|open links app", "앱 역할|기본으로 열기", "앱 제거|권한", "change", sources="android_app_languages"),
        F("android_connectivity.app_languages", "앱 언어", "App languages", "앱별 언어|개별 앱 언어|언어 선택", "per-app language|individual app language|choose app language", "설치된 앱|시스템 기본값|언어", "페이지 번역|자막 언어", "change", sources="android_app_languages"),
        F("android_connectivity.data_saver", "데이터 절약 모드", "Data Saver", "모바일 데이터 절약|백그라운드 데이터 제한|데이터 세이버", "mobile data saver|restrict background data|data saving mode", "제한 없는 앱|모바일 데이터|백그라운드", "배터리 절약|저장공간 정리", "change", sources="android_data_saver"),
        F("android_connectivity.unrestricted_data", "제한 없는 데이터 사용", "Unrestricted data access", "데이터 절약 예외|백그라운드 허용 앱|무제한 데이터 앱", "data saver exception|allow background data|unrestricted apps", "앱 목록|데이터 절약 중 허용", "배터리 최적화 예외|VPN", "change", sources="android_data_saver"),
        F("android_connectivity.airplane_mode", "비행기 모드", "Airplane mode", "항공 모드|모든 무선 연결 끄기|비행 모드", "flight mode|disable radios|airplane setting", "Wi-Fi|모바일 네트워크|블루투스", "방해 금지|로밍", "change", sources="android_data_saver"),
        F("android_connectivity.network_reset", "네트워크 설정 초기화", "Reset network settings", "Wi-Fi 블루투스 초기화|연결 설정 재설정|모바일 네트워크 리셋", "reset wifi bluetooth|reset connectivity|mobile network reset", "저장된 네트워크|페어링|경고", "공장 초기화|라우터 재부팅", "submit", sources="android_data_saver"),
    ),
    G(
        "android_safety", "android_safety.hub", "안전 및 긴급 상황", "Safety and emergency", "personal_safety",
        "긴급|재난|안전|구조", "emergency|disaster|safety|rescue",
        "일반 연락처|뉴스 알림", "regular contacts|news alerts",
        "android_connectivity.hub", "android_emergency|android_safety_services",
        F("android_safety.emergency_info", "긴급 정보", "Emergency information", "의료 정보|잠금화면 응급정보|비상 정보", "medical information|lock screen emergency info|emergency profile", "혈액형|알레르기|연락처", "건강 기록 전체|프로필 소개", "sensitive", sources="android_emergency"),
        F("android_safety.emergency_contacts", "긴급 연락처", "Emergency contacts", "비상 연락망|응급 연락 대상|ICE 연락처", "emergency people|ICE contacts|crisis contacts", "잠금화면|연락 대상|전화", "일반 즐겨찾기|그룹 채팅", "sensitive", sources="android_emergency"),
        F("android_safety.sos", "긴급 SOS", "Emergency SOS", "전원 버튼 긴급 호출|SOS 설정|응급 구조 요청", "power button emergency call|SOS settings|request emergency help", "긴급 서비스|카운트다운|공유", "일반 전화|안전 확인", "change", sources="android_emergency"),
        F("android_safety.earthquake_alerts", "지진 알림", "Earthquake alerts", "지진 경보|재난 진동 알림|지진 감지", "earthquake warning|seismic alert|quake detection", "지역|안전 안내|알림", "날씨 경보|뉴스 속보", "change", sources="android_safety_services"),
        F("android_safety.emergency_location", "긴급 위치 서비스", "Emergency Location Service", "ELS|구조기관 위치 전송|긴급전화 위치", "ELS|send location to responders|emergency call location", "긴급 통화|위치 정확도|구조", "일반 위치 공유|지도 기록", "change", sources="android_safety_services"),
        F("android_safety.crash_detection", "자동차 사고 감지", "Car crash detection", "충돌 감지|교통사고 자동 신고|사고 감지", "collision detection|automatic crash alert|detect car accident", "운전|긴급 연락|카운트다운", "낙상 감지|차량 블루투스", "change", sources="android_emergency"),
        F("android_safety.safety_check", "안전 확인", "Safety check", "안부 확인 예약|응답 없으면 알림|안전 타이머", "scheduled check-in|alert if no response|safety timer", "종료 시간|긴급 연락처|위치", "캘린더 일정|미리 알림", "submit", sources="android_emergency"),
        F("android_safety.crisis_alerts", "위기 알림", "Crisis alerts", "재난 정보|공공 안전 경보|위기 상황 알림", "disaster information|public safety alert|crisis notification", "지역 재난|공식 안내|지도", "뉴스 추천|날씨 일보", "change", sources="android_safety_services"),
    ),
    G(
        "local_transit", "local_transit.hub", "대중교통", "Public transit", "location",
        "버스|지하철|기차|정류장", "bus|subway|train|station",
        "택시 호출|항공편", "ride hail|flight",
        "weather_news.hub", "maps_transit",
        F("local_transit.departures", "실시간 출발 정보", "Live transit departures", "버스 도착|열차 출발|정류장 시간", "bus arrivals|train departures|stop times", "노선 번호|도착 예정|승강장", "택배 도착|항공 출발", sources="maps_transit"),
        F("local_transit.route_plan", "대중교통 경로", "Transit route planning", "버스 길찾기|지하철 경로|환승 안내", "bus directions|subway route|transfer directions", "출발지|목적지|환승", "자동차 경로|도보만", sources="maps_transit"),
        F("local_transit.nearby_stops", "주변 정류장", "Nearby transit stops", "가까운 버스정류장|주변 역|근처 승강장", "nearby bus stop|closest station|nearby platform", "현재 위치|거리|노선", "주변 상점|주차장", sources="maps_transit"),
        F("local_transit.saved_routes", "즐겨찾는 노선", "Saved transit routes", "자주 타는 버스|노선 즐겨찾기|통근 경로", "favorite bus|saved line|commute route", "집 회사|노선|정류장", "지도 장소 목록|여행 일정", "change", sources="maps_transit"),
        F("local_transit.service_alerts", "운행 알림", "Transit service alerts", "지연 알림|운행 중단|노선 변경", "delay alert|service disruption|route change", "노선 상태|공사|우회", "날씨 경보|배송 지연", sources="maps_transit"),
        F("local_transit.fare_card", "교통카드", "Transit fare card", "승차권 잔액|교통 패스|모바일 승차권", "fare balance|transit pass|mobile ticket", "잔액|유효기간|노선", "신용카드|항공 탑승권", "sensitive", sources="maps_transit"),
        F("local_transit.fare_topup", "교통카드 충전", "Top up transit card", "승차권 충전|교통 잔액 추가|패스 구매", "reload fare card|add transit balance|buy transit pass", "충전 금액|결제수단|카드", "휴대폰 요금 충전|기프트카드", "submit", sources="maps_transit"),
        F("local_transit.trip_history", "대중교통 이용 내역", "Transit trip history", "승하차 기록|교통카드 사용 내역|지난 이동", "tap history|fare usage history|past transit trips", "승차역|하차역|요금", "택시 이용 내역|위치 기록", "sensitive", sources="maps_transit"),
        F("local_transit.accessibility", "교통 접근성 경로", "Accessible transit routes", "휠체어 경로|엘리베이터 있는 역|저상버스", "wheelchair route|station elevator|accessible bus", "접근성 시설|환승|운행 정보", "앱 접근성|음성 안내", sources="maps_transit"),
    ),
    G(
        "weather_news", "weather_news.hub", "날씨 및 뉴스", "Weather and news", "local_information",
        "예보|기상|뉴스|속보", "forecast|weather|news|headline",
        "재난 설정|캘린더", "emergency settings|calendar",
        "local_transit.hub", "google_weather|google_news",
        F("weather.current", "현재 날씨", "Current weather", "지금 기온|현재 기상|오늘 날씨", "current temperature|weather now|today weather", "온도|강수|체감", "실내 온도|지역 뉴스", sources="google_weather"),
        F("weather.hourly", "시간별 예보", "Hourly forecast", "시간대별 날씨|몇 시 비|시간별 기온", "weather by hour|rain time|hourly temperature", "시간|강수확률|바람", "주간 예보|뉴스 시간", sources="google_weather"),
        F("weather.daily", "주간 예보", "Daily forecast", "일별 날씨|10일 예보|이번 주 기상", "daily weather|ten-day forecast|weekly forecast", "최고 최저|요일|강수", "시간별 예보|달력 일정", sources="google_weather"),
        F("weather.locations", "날씨 지역 관리", "Weather locations", "도시 추가|날씨 위치|지역 순서", "add weather city|forecast locations|reorder cities", "도시 검색|현재 위치|즐겨찾기", "지도 저장 장소|배송지", "change", sources="google_weather"),
        F("weather.severe_alerts", "기상 특보 알림", "Severe weather alerts", "폭염 경보|호우 알림|태풍 특보", "heat warning|heavy rain alert|storm warning", "지역|경보 등급|알림", "지진 알림|뉴스 속보", "change", sources="google_weather"),
        F("news.follow_topics", "뉴스 주제 팔로우", "Follow news topics", "관심 주제|뉴스 키워드 구독|분야 팔로우", "news interests|follow keyword|follow topic", "주제|언론사|추천", "소셜 팔로우|상품 알림", "change", sources="google_news"),
        F("news.local", "지역 뉴스", "Local news", "동네 소식|내 지역 뉴스|지역별 기사", "neighborhood news|news near me|regional stories", "지역 선택|언론사|기사", "날씨 지역|부동산 시세", sources="google_news"),
        F("news.notifications", "뉴스 알림", "News notifications", "속보 푸시|기사 알림|뉴스 알림 빈도", "breaking news push|story alerts|news notification frequency", "속보|주제|빈도", "재난 문자|메시지 알림", "change", sources="google_news"),
        F("news.hide_source", "뉴스 출처 숨기기", "Hide news source", "언론사 차단|이 출처 덜 보기|매체 숨기기", "block publisher|show fewer from source|hide outlet", "언론사|추천 피드|숨김", "발신자 차단|웹 사이트 권한", "change", sources="google_news"),
    ),
    G(
        "marketplace", "marketplace.hub", "중고 거래 및 마켓", "Marketplace", "commerce",
        "판매자|구매자|중고|거래", "seller|buyer|secondhand|listing",
        "앱 스토어|구독", "app store|subscription",
        "shopping_logistics.hub", "ftc_delivery_disputes",
        F("marketplace.search", "마켓 상품 검색", "Search marketplace", "중고 물건 찾기|매물 검색|판매글 검색", "find used item|search listings|marketplace search", "키워드|카테고리|지역", "앱 검색|구인 검색"),
        F("marketplace.filters", "마켓 검색 필터", "Marketplace filters", "가격 범위|거래 지역|상품 상태", "price range|local area|item condition", "정렬|거리|배송", "뉴스 필터|부동산 대출"),
        F("marketplace.saved_search", "마켓 검색 저장", "Save marketplace search", "검색 조건 저장|매물 알림|중고 키워드 알림", "save listing search|listing alert|used item keyword alert", "키워드|지역|알림", "구인 알림|부동산 알림", "change"),
        F("marketplace.favorites", "관심 상품", "Favorite listings", "중고 찜|저장한 매물|관심 목록", "saved listings|favorite items|watchlist", "상품 상태|가격 변동|판매 여부", "앱 위시리스트|부동산 찜"),
        F("marketplace.create_listing", "판매글 작성", "Create marketplace listing", "중고 판매 등록|매물 올리기|상품 판매", "list used item|post listing|sell item", "사진|가격|설명|거래 지역", "상품 리뷰|구인 이력서", "submit"),
        F("marketplace.edit_listing", "판매글 수정", "Edit marketplace listing", "매물 가격 변경|판매글 편집|상품 설명 수정", "change listing price|edit sale post|update item details", "내 판매글|가격|상태", "주문 변경|프로필 수정", "submit"),
        F("marketplace.mark_sold", "판매 완료 처리", "Mark listing sold", "거래 완료|판매됨 표시|매물 내리기", "mark transaction complete|show as sold|close listing", "판매글|구매자|완료", "주문 배송 완료|게시글 삭제", "submit"),
        F("marketplace.seller_chat", "판매자와 채팅", "Chat with seller", "구매 문의|판매자 메시지|거래 대화", "ask seller|message vendor|trade chat", "상품|가격|약속", "고객센터 채팅|그룹 메시지", "sensitive"),
        F("marketplace.report_listing", "거래 게시물 신고", "Report marketplace listing", "사기 매물 신고|판매자 신고|상품 신고", "report scam listing|report seller|flag item", "신고 사유|증거|제출", "배송 분쟁|스팸 문자", "submit", sources="ftc_delivery_disputes"),
    ),
    G(
        "shopping_logistics", "shopping_logistics.hub", "쇼핑 및 배송", "Shopping and delivery", "commerce",
        "주문|장바구니|배송|반품", "order|cart|shipping|return",
        "중고 거래|음식 배달", "marketplace|food delivery",
        "marketplace.hub", "usps_informed_delivery|usps_package_intercept|ftc_delivery_disputes",
        F("shopping.cart", "장바구니", "Shopping cart", "구매 목록|카트|담은 상품", "basket|cart items|items to buy", "수량|옵션|합계", "위시리스트|주문 내역"),
        F("shopping.saved_for_later", "나중에 구매", "Saved for later", "장바구니 보관|나중에 살 상품|구매 보류", "save cart item|buy later|deferred purchase", "상품|가격|재고", "관심 상품|예약 주문", "change"),
        F("shopping.orders", "주문 내역", "Order history", "구입 이력|지난 주문|온라인 주문", "purchases|past orders|online orders", "주문 번호|금액|상태", "앱 구매|중고 판매"),
        F("shopping.track_package", "택배 조회", "Track package", "배송 추적|송장 조회|택배 위치", "shipment tracking|tracking number|package location", "운송장|배송 단계|예정일", "음식 배달 위치|대중교통", sources="usps_informed_delivery"),
        F("shopping.delivery_notifications", "배송 알림", "Delivery notifications", "택배 도착 알림|배송 상태 푸시|우편 알림", "package arrival alert|shipping status push|mail notification", "출발|도착 예정|배달 완료", "음식 배달 알림|뉴스 알림", "change", sources="usps_informed_delivery"),
        F("shopping.change_delivery", "배송 옵션 변경", "Change delivery options", "배송지 변경|수령 장소|배송 날짜 변경", "change address|delivery location|reschedule delivery", "주문|주소|가능 시간", "기본 배송지|배달 요청사항", "submit", sources="usps_package_intercept"),
        F("shopping.cancel_order", "주문 취소", "Cancel order", "구매 취소|출고 전 취소|주문 철회", "cancel purchase|cancel before shipment|withdraw order", "주문 상태|환불 수단|취소 확인", "구독 해지|반품", "submit", sources="ftc_delivery_disputes"),
        F("shopping.return_item", "상품 반품", "Return item", "반품 신청|구매품 돌려보내기|반송", "request return|send item back|return purchase", "반품 사유|회수 방법|환불", "주문 취소|중고 신고", "submit", sources="ftc_delivery_disputes"),
        F("shopping.delivery_dispute", "미배송 분쟁", "Missing delivery dispute", "상품 못 받음|배송 완료 오배송|택배 분실", "item not received|delivered to wrong place|lost package", "주문 번호|증거|판매자 연락", "반품|음식 누락", "submit", sources="ftc_delivery_disputes"),
        F("shopping.invoices", "주문 영수증", "Order invoices", "구매 영수증|세금계산서|주문 증빙", "purchase receipt|order invoice|proof of purchase", "주문 번호|결제 금액|다운로드", "통신 청구서|급여 명세", "sensitive"),
    ),
    G(
        "pharmacy_telehealth", "digital_health.hub", "약국 및 비대면 진료", "Pharmacy and telehealth", "health_data",
        "처방|약|진료|의료진|돌봄", "prescription|medicine|medication|care|appointment|clinician",
        "보험 청구|운동 기록", "insurance claim|fitness log",
        "jobs.hub", "",
        F("digital_health.prescriptions", "처방전 목록", "Prescriptions", "내 처방|처방약|전자 처방전", "my prescriptions|prescribed medicine|electronic prescription", "약 이름|처방일|의료기관", "건강보조제|보험 서류", "sensitive"),
        F("digital_health.refill", "처방약 재조제", "Prescription refill", "약 재처방 요청|리필 신청|처방 갱신", "request medicine refill|refill prescription|renew medication", "남은 횟수|약국|의사 승인", "자동 배송|일반 재구매", "submit"),
        F("digital_health.pharmacy_search", "약국 찾기", "Find pharmacy", "주변 약국|당번 약국|처방 가능 약국", "nearby pharmacy|open pharmacy|prescription pharmacy", "위치|영업 시간|조제 가능", "병원 찾기|쇼핑 매장"),
        F("digital_health.pharmacy_transfer", "처방 약국 변경", "Transfer prescription", "다른 약국으로 옮기기|조제처 변경|처방 이전", "move to another pharmacy|change dispensing pharmacy|transfer prescription", "현재 약국|새 약국|처방", "배송지 변경|병원 변경", "submit"),
        F("digital_health.medication_delivery", "약 배송", "Medication delivery", "처방약 배송|약 배달|의약품 택배", "prescription delivery|medicine courier|drug shipment", "주소|수령 가능 시간|본인 확인", "일반 쇼핑 배송|음식 배달", "submit"),
        F("digital_health.telehealth_booking", "비대면 진료 예약", "Book telehealth visit", "화상 진료 예약|온라인 의사 예약|원격 상담", "book video visit|online doctor appointment|remote consultation", "의료진|시간|증상", "영상 회의|대면 예약", "submit"),
        F("digital_health.waiting_room", "온라인 진료 대기실", "Virtual waiting room", "진료 입장|화상 상담 대기|예약 진료 시작", "enter visit|wait for video consultation|start appointment", "예약 시간|카메라|마이크", "회의 대기실|고객센터 채팅", "sensitive"),
        F("digital_health.symptom_form", "진료 전 문진표", "Pre-visit symptom form", "증상 입력|의료 설문|사전 문진", "enter symptoms|medical questionnaire|pre-visit intake", "증상|병력|알레르기", "고객 설문|보험 청구", "submit"),
        F("digital_health.lab_results", "검사 결과", "Lab results", "혈액검사 결과|진단 검사|검사 수치", "blood test results|diagnostic tests|lab values", "검사일|기준 범위|의사 설명", "건강 앱 통계|보험 심사", "sensitive"),
        F("digital_health.visit_summary", "진료 기록 요약", "Visit summary", "진료 내역|의사 소견|방문 기록", "visit record|clinical notes|appointment summary", "진단|처방|추후 계획", "보험 이용 내역|일정 메모", "sensitive"),
        F("digital_health.message_clinician", "의료진에게 메시지", "Message clinician", "의사에게 문의|간호사 메시지|진료 후 질문", "ask doctor|message nurse|post-visit question", "의료진|환자 정보|본문", "약국 채팅|고객센터", "submit"),
        F("digital_health.consent", "원격진료 동의", "Telehealth consent", "비대면 진료 약관|의료정보 제공 동의|진료 동의서", "virtual care terms|health data consent|treatment consent", "개인정보|위험|서명", "마케팅 동의|앱 권한", "submit"),
    ),
    G(
        "jobs", "jobs.hub", "채용 및 구직", "Jobs and careers", "career_data",
        "채용|구직|이력서|지원", "job|career|resume|application",
        "부동산 매물|중고 판매", "property listing|marketplace sale",
        "property.hub", "usajobs_profile|usajobs_saved_search",
        F("jobs.search", "채용공고 검색", "Job search", "일자리 찾기|구인 공고|직무 검색", "find jobs|vacancy search|role search", "직무|회사|지역", "중고 검색|부동산 검색", sources="usajobs_saved_search"),
        F("jobs.filters", "채용 검색 필터", "Job search filters", "연봉 범위|경력 조건|근무 형태", "salary range|experience level|work type", "지역|재택|고용 형태", "상품 가격|주택 방 수", sources="usajobs_saved_search"),
        F("jobs.saved_search", "채용 검색 저장", "Save job search", "구직 알림|조건 저장|새 공고 알림", "job alert|save criteria|new vacancy notification", "검색 조건|알림 빈도|이메일", "중고 키워드 알림|뉴스 알림", "change", sources="usajobs_saved_search"),
        F("jobs.saved_jobs", "관심 채용공고", "Saved jobs", "찜한 공고|나중에 지원|저장한 일자리", "favorite vacancies|apply later|bookmarked jobs", "마감일|회사|직무", "지원 내역|앱 위시리스트", sources="usajobs_saved_search"),
        F("jobs.profile", "구직 프로필", "Job profile", "경력 프로필|인재 정보|지원자 프로필", "career profile|candidate information|applicant profile", "경력|학력|기술", "소셜 프로필|회사 프로필", "sensitive", sources="usajobs_profile"),
        F("jobs.resume", "이력서 관리", "Resume management", "CV 업로드|이력서 수정|경력기술서", "upload CV|edit resume|career document", "파일|공개 범위|최종 수정", "문서 편집|신분증 업로드", "sensitive", sources="usajobs_profile"),
        F("jobs.apply", "채용 지원", "Apply for job", "입사 지원|공고 지원하기|원서 제출", "submit application|apply to vacancy|job application", "이력서|자기소개서|질문", "관심 공고 저장|문의", "submit", sources="usajobs_profile"),
        F("jobs.applications", "지원 현황", "Job applications", "내 지원서|전형 상태|지원 내역", "my applications|hiring status|application history", "접수|검토|면접|결과", "저장 공고|보험 심사", "sensitive", sources="usajobs_profile"),
        F("jobs.withdraw", "입사 지원 철회", "Withdraw job application", "지원 취소|원서 철회|채용 지원 삭제", "cancel application|withdraw submission|remove candidacy", "지원서|철회 경고|확인", "공고 저장 해제|계정 탈퇴", "submit", sources="usajobs_profile"),
    ),
    G(
        "property", "property.hub", "부동산", "Property and housing", "location_finance",
        "주택|매물|임대|부동산", "home|listing|rent|property",
        "채용공고|중고 상품", "job listing|used item",
        "utilities.hub", "usagov_rental_assistance",
        F("property.search", "부동산 매물 검색", "Property search", "집 찾기|아파트 검색|임대 매물", "find home|apartment search|rental listing", "지역|가격|거래 유형", "구인 공고|중고 매물"),
        F("property.filters", "부동산 검색 조건", "Property filters", "방 개수|면적|보증금 필터", "bedroom count|floor area|deposit filter", "매매 임대|가격|주택 유형", "상품 상태|연봉 범위"),
        F("property.saved_search", "부동산 검색 저장", "Save property search", "새 매물 알림|지역 조건 저장|시세 알림", "new listing alert|save area criteria|price alert", "지역|가격|알림 빈도", "중고 알림|날씨 지역", "change"),
        F("property.favorites", "관심 부동산", "Favorite properties", "찜한 집|저장한 매물|관심 아파트", "saved homes|favorite listings|watched apartments", "가격 변동|거래 상태|메모", "중고 찜|지도 장소"),
        F("property.viewing", "매물 방문 예약", "Book property viewing", "집 보러가기|중개사 방문|모델하우스 예약", "schedule home tour|agent viewing|book showing", "날짜|시간|연락처", "의료 예약|정비 예약", "submit"),
        F("property.contact_agent", "중개사 문의", "Contact property agent", "부동산에 연락|매물 질문|중개인 채팅", "message realtor|ask about listing|contact broker", "매물|전화|메시지", "판매자 채팅|고객센터", "sensitive"),
        F("property.application", "임대 입주 신청", "Rental application", "세입자 지원|임대 신청서|입주 원서", "tenant application|lease application|apply to rent", "신원|소득|동의", "채용 지원|주택 찜", "submit", sources="usagov_rental_assistance"),
        F("property.lease_documents", "임대차 문서", "Lease documents", "계약서 보기|임대 계약|전자 서명 문서", "view lease|rental agreement|e-sign documents", "계약 기간|보증금|서명", "주문 영수증|보험 약관", "sensitive", sources="usagov_rental_assistance"),
        F("property.rent_payment", "임대료 납부", "Rent payment", "월세 내기|관리비 납부|임대 결제", "pay rent|monthly lease payment|housing payment", "금액|납부일|결제수단", "공과금|대출 조회", "submit", sources="usagov_rental_assistance"),
    ),
    G(
        "utilities", "utilities.hub", "공과금 및 생활 서비스", "Utilities and household services", "household_account",
        "전기|가스|수도|인터넷|요금", "electricity|gas|water|internet|utility bill",
        "임대료|쇼핑 주문", "rent|shopping order",
        "digital_health.hub", "usagov_utility_help",
        F("utilities.accounts", "생활요금 계정", "Utility accounts", "전기 고객번호|가스 계정|수도 계약", "electric account|gas account|water service account", "고객번호|서비스 주소|계약", "은행 계좌|통신 요금", "sensitive", sources="usagov_utility_help"),
        F("utilities.bill", "공과금 청구서", "Utility bill", "전기요금|가스요금|수도요금", "electric bill|gas bill|water bill", "사용 기간|청구 금액|납부일", "임대료|통신 청구", "sensitive", sources="usagov_utility_help"),
        F("utilities.usage", "에너지 사용량", "Utility usage", "전력 사용|가스 소비|수도 사용량", "electricity usage|gas consumption|water usage", "일별 사용량|요금 예상|비교", "모바일 데이터|저장공간", sources="usagov_utility_help"),
        F("utilities.autopay", "공과금 자동 납부", "Utility autopay", "전기 자동이체|가스 자동결제|요금 자동납부", "electric autopay|automatic gas payment|utility direct debit", "납부 계좌|결제일|한도", "구독 자동갱신|임대료", "change", sources="usagov_utility_help"),
        F("utilities.pay_bill", "공과금 납부", "Pay utility bill", "전기요금 내기|가스비 결제|수도요금 납부", "pay electricity|pay gas bill|pay water bill", "금액|결제수단|납부 확인", "자동 납부 설정|청구서 보기", "submit", sources="usagov_utility_help"),
        F("utilities.outage", "서비스 장애 조회", "Utility outage status", "정전 확인|가스 공급 중단|인터넷 장애", "power outage|gas interruption|internet outage", "주소|복구 예상|장애 지도", "앱 오류|배송 지연"),
        F("utilities.report_outage", "서비스 장애 신고", "Report utility outage", "정전 신고|누수 신고|인터넷 고장 접수", "report power outage|report leak|report internet fault", "서비스 주소|위험 여부|연락처", "앱 버그 신고|배송 분쟁", "submit"),
        F("utilities.move_service", "이사 서비스 이전", "Move utility service", "전기 전입 전출|가스 주소 변경|인터넷 이전 설치", "transfer electric service|change gas address|move internet service", "이전 주소|새 주소|이사일", "배송지 변경|eSIM 이전", "submit"),
        F("utilities.meter_reading", "계량기 검침 제출", "Submit meter reading", "전기 검침|가스 계량기 사진|수도 수치 입력", "electric meter reading|gas meter photo|water meter value", "계량기 번호|수치|사진", "건강 검사 결과|자동 사용량", "submit"),
        F("utilities.payment_assistance", "공과금 지원", "Utility payment assistance", "요금 감면|에너지 바우처|납부 유예", "bill discount|energy assistance|payment extension", "자격 조건|소득|신청", "환불|예산 알림", "sensitive", sources="usagov_utility_help"),
    ),
)


def _risk_cues(mode: str, name_ko: str, name_en: str) -> dict[str, list[str]]:
    if mode == "submit":
        return {
            "final_action": [name_ko, name_en, "제출", "확인", "submit", "confirm"],
            "consequence": ["외부 상태 변경", "최종 사용자 클릭 필요", "changes external state", "final user click required"],
        }
    if mode == "change":
        return {
            "setting_change": [name_ko, name_en, "켜기", "끄기", "변경", "enable", "disable", "change"],
            "confirmation": ["사용자가 직접 선택", "user confirmation required"],
        }
    if mode == "sensitive":
        return {
            "sensitive_access": [name_ko, name_en, "개인정보", "민감 정보", "personal data", "sensitive information"],
            "confirmation": ["열기 전 사용자 확인", "confirm before opening"],
        }
    return {
        "navigation_scope": [name_ko, name_en],
        "safe_boundary": ["화면 열기만 허용", "navigation only"],
    }


def _source_refs(group: GroupSeed, feature: FeatureSeed | None = None) -> list[str]:
    if feature is None:
        return list(group.source_refs)
    # Feature evidence is intentionally precise.  A group registry may cover
    # several sibling concepts, but it must not be attached to a function that
    # the referenced page does not actually document.
    return list(feature.source_refs)


def _build_root(group: GroupSeed) -> dict[str, object]:
    source_refs = _source_refs(group)
    return {
        "function_id": group.root_id,
        "domain": group.domain,
        "scope": group.scope,
        "node_kind": "hub",
        "stop_policy": "continue",
        "name_ko": group.root_ko,
        "name_en": group.root_en,
        "description": f"{group.root_ko} 기능을 찾기 위한 범용 허브. General hub for {group.root_en.lower()} functions.",
        "risk_level": "low",
        "automation_policy": "safe_navigation",
        "terminal": False,
        "state_changing": False,
        "legacy_tags": [group.domain, "v4_broad_services", "hub"],
        "role_hints": ["button", "menuitem", "tab", "heading"],
        "aliases": {
            "ko-KR": _dedupe_aliases([group.root_ko, *group.ko_context, f"{group.root_ko} 메뉴", f"{group.root_ko} 관리"]),
            "en-US": _dedupe_aliases([group.root_en, *group.en_context, f"{group.root_en} menu", f"manage {group.root_en.lower()}"]),
        },
        "positive_context": _dedupe([*group.ko_context, *group.en_context, "전체 메뉴", "main menu"]),
        "negative_context": _dedupe([*group.negative_ko, *group.negative_en]),
        "state_cues": {
            "visible": [group.root_ko, group.root_en],
            "loading": ["불러오는 중", "loading"],
        },
        "risk_cues": _risk_cues("view", group.root_ko, group.root_en),
        "source_refs": source_refs,
        "evidence_level": "official" if source_refs else "ontology_design",
    }


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    metadata = MODE_METADATA[seed.mode]
    aliases_ko = _dedupe_aliases([seed.name_ko, *seed.ko_aliases, f"{seed.name_ko} 설정", f"{seed.name_ko} 관리"])
    aliases_en = _dedupe_aliases([seed.name_en, *seed.en_aliases, f"{seed.name_en} settings", f"manage {seed.name_en.lower()}"])
    source_refs = _source_refs(group, seed)
    return {
        "function_id": seed.function_id,
        "domain": group.domain,
        "scope": group.scope,
        "node_kind": metadata["node_kind"],
        "stop_policy": metadata["stop_policy"],
        "name_ko": seed.name_ko,
        "name_en": seed.name_en,
        "description": (
            f"{seed.name_ko} 목적지 또는 사용자 소유의 최종 동작 경계를 식별한다. "
            f"Identifies the {seed.name_en.lower()} destination or user-owned action boundary."
        ),
        "risk_level": metadata["risk_level"],
        "automation_policy": metadata["automation_policy"],
        "terminal": True,
        "state_changing": metadata["state_changing"],
        "legacy_tags": [group.domain, "v4_broad_services", seed.function_id.rsplit(".", 1)[-1]],
        "role_hints": ["button", "menuitem", "tab", "text", "switch"],
        "aliases": {"ko-KR": aliases_ko, "en-US": aliases_en},
        "positive_context": _dedupe([*seed.positive, *group.ko_context[:2], *group.en_context[:2]]),
        "negative_context": _dedupe([*seed.negative, *group.negative_ko[:2], *group.negative_en[:2]]),
        "state_cues": {
            "visible": [seed.name_ko, seed.name_en, aliases_ko[1], aliases_en[1]],
            "disabled": ["사용할 수 없음", "비활성", "unavailable", "disabled"],
            "selected": ["선택됨", "현재", "selected", "current"],
        },
        "risk_cues": _risk_cues(seed.mode, seed.name_ko, seed.name_en),
        "source_refs": source_refs,
        "evidence_level": "official" if source_refs else "ontology_design",
    }


def _route(group: GroupSeed, seed: FeatureSeed) -> list[dict[str, object]]:
    return [
        {"function_id": group.root_id, "weight": 0.42},
        {"function_id": seed.function_id, "weight": 1.0},
    ]


def _specific_goal_terms(domain_phrase: str, feature_phrase: str) -> list[str]:
    """Build a high-specificity conjunction from a domain and feature cue.

    Full phrases preserve meaning, while their visible word parts make the
    deterministic tie-break prefer a domain-qualified destination over an
    older generic sibling that happens to share the short feature label.
    """

    values = [domain_phrase.casefold(), feature_phrase.casefold()]
    for phrase in (domain_phrase, feature_phrase):
        values.extend(
            token.casefold()
            for token in re.split(r"[\s/·&+_\-]+", phrase)
            if token.strip()
        )
    return _dedupe(values)


def _v4_alias_owner_counts() -> Counter[str]:
    """Count semantic owners of each reusable v4 function phrase.

    A phrase is safe as an unqualified goal cue only when it names one v4
    destination.  Shared UI wording (for example ``Favorite listings``) must
    retain a domain cue so marketplace and property navigation stay separate.
    Counts are based solely on reviewed ontology vocabulary; no benchmark
    sentence or expected answer is consulted.
    """

    owners: dict[str, set[str]] = {}
    for candidate_group in GROUPS:
        for candidate in candidate_group.features:
            for raw_phrase in (
                candidate.name_ko,
                candidate.name_en,
                *candidate.ko_aliases,
                *candidate.en_aliases,
            ):
                phrase = " ".join(raw_phrase.casefold().split())
                if phrase:
                    owners.setdefault(phrase, set()).add(candidate.function_id)
    return Counter({phrase: len(function_ids) for phrase, function_ids in owners.items()})


V4_ALIAS_OWNER_COUNTS = _v4_alias_owner_counts()
V4_FEATURE_ALIASES = frozenset(V4_ALIAS_OWNER_COUNTS)


def _goal_cue_key(value: object) -> str:
    """Approximate the runtime's punctuation-insensitive semantic key."""

    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


def _runtime_goal_key(value: object) -> str:
    """Mirror runtime goal normalization for cross-intent pattern ownership."""

    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    tokens = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    particles = (
        "에게서", "으로부터", "한테서", "에서는", "에서도", "으로", "에서", "에게", "한테",
        "처럼", "보다", "까지", "부터", "은", "는", "이", "가", "을", "를", "에", "로", "와", "과", "도", "만",
    )
    result: list[str] = []
    for token in tokens:
        if len(token) >= 3 and any("가" <= character <= "힣" for character in token):
            for particle in particles:
                if token.endswith(particle) and len(token) > len(particle) + 1:
                    token = token[: -len(particle)]
                    break
        result.append(token)
    return "".join(result)


def _base_goal_cues(payload: Mapping[str, object]) -> set[str]:
    """Collect reviewed pre-v4 vocabulary owned by another ontology layer."""

    cues: set[str] = set()
    for function in payload.get("functions", []):  # type: ignore[union-attr]
        aliases = function.get("aliases", {}) if isinstance(function, Mapping) else {}
        if isinstance(aliases, Mapping):
            for values in aliases.values():
                for value in values if isinstance(values, (list, tuple)) else (values,):
                    if key := _goal_cue_key(value):
                        cues.add(key)
    for intent in payload.get("intents", []):  # type: ignore[union-attr]
        if not isinstance(intent, Mapping):
            continue
        for pattern in intent.get("patterns", []):
            if key := _goal_cue_key(pattern):
                cues.add(key)
        for rule in intent.get("goal_rules", []):
            if not isinstance(rule, Mapping):
                continue
            for term in rule.get("all_of", []):
                if key := _goal_cue_key(term):
                    cues.add(key)
    return cues


def _has_explicit_action_cue(value: object) -> bool:
    """Return whether a phrase names a concrete operation, not just a noun."""

    key = _goal_cue_key(value)
    return any(
        cue in key
        for cue in (
            "끄기", "켜기", "해제", "취소", "삭제", "차단", "보관", "복원", "철회",
            "turnoff", "turnon", "mute", "unmute", "cancel", "delete", "block",
            "unblock", "archive", "unarchive", "restore", "withdraw",
        )
    )


def _is_sibling_feature_fragment(group: GroupSeed, seed: FeatureSeed, value: str) -> bool:
    """Detect group context words that actually describe a sibling feature."""

    cue = _goal_cue_key(value)
    if not cue:
        return False
    for sibling in group.features:
        if sibling.function_id == seed.function_id:
            continue
        for alias in (
            sibling.name_ko,
            sibling.name_en,
            *sibling.ko_aliases,
            *sibling.en_aliases,
        ):
            if cue in _goal_cue_key(alias):
                return True
    return False


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    ko_aliases = [seed.name_ko, *seed.ko_aliases]
    en_aliases = [seed.name_en, *seed.en_aliases]
    # Bare labels such as "방문 기록", "voicemail", or "cancel order"
    # legitimately occur in several domains.  Goal patterns are therefore
    # domain-qualified while function aliases remain faithful to short UI
    # labels for candidate matching.  This keeps semantically distinct
    # destinations separate without sacrificing screen recognition.
    ko_patterns = _dedupe([
        *(f"{group.root_ko} {alias}" for alias in ko_aliases),
        f"{group.root_ko}에서 {seed.name_ko} 찾기",
        f"{group.root_ko}에서 {seed.name_ko} 열기",
        f"{group.root_ko} {seed.name_ko} 메뉴로 이동",
    ])
    en_patterns = _dedupe([
        *(f"{group.root_en} {alias}" for alias in en_aliases),
        f"find {seed.name_en.lower()} in {group.root_en.lower()}",
        f"open {seed.name_en.lower()} in {group.root_en.lower()}",
        f"go to {group.root_en.lower()} {seed.name_en.lower()} settings",
    ])
    confirmation_required = seed.mode in {"change", "submit", "sensitive"}
    # A catch-all settings page is a legitimate destination, but it is weaker
    # evidence than an explicitly named child feature on the same request
    # (for example call forwarding mentioned alongside call settings).
    if seed.function_id.endswith(".orders"):
        qualified_score = 0.985
    elif seed.function_id.endswith(".settings"):
        qualified_score = 0.99
    else:
        qualified_score = 1.0
    specific_rules: list[dict[str, object]] = []
    seen_rule_terms: set[tuple[str, ...]] = set()
    for domain_phrase, aliases in (
        (group.root_ko, ko_aliases),
        (group.root_en, en_aliases),
    ):
        for alias in aliases:
            terms = tuple(_specific_goal_terms(domain_phrase, alias))
            if terms in seen_rule_terms:
                continue
            seen_rule_terms.add(terms)
            is_root = domain_phrase in {group.root_ko, group.root_en}
            contextual_score = qualified_score
            if not is_root and _is_sibling_feature_fragment(group, seed, domain_phrase):
                # A sibling action is contextual evidence, not a domain
                # qualifier.  Keep it useful but below a directly named
                # destination, e.g. "past orders ... return".
                contextual_score = min(contextual_score, 0.985)
            specific_rules.append({"all_of": list(terms), "score": contextual_score})
            # A separate contiguous rule resolves word-boundary collisions
            # without weakening the order-independent term rule above.  Keep
            # it separate: requiring the combined phrase in the same rule
            # would break natural wrappers such as "find FEATURE in DOMAIN".
            combined_terms = (f"{domain_phrase} {alias}".casefold(),)
            if combined_terms not in seen_rule_terms:
                seen_rule_terms.add(combined_terms)
                specific_rules.append({"all_of": list(combined_terms), "score": qualified_score})

    # Natural goals frequently name a distinctive result without repeating
    # the app-domain heading.  A globally unique v4 alias is sufficient
    # evidence in that case.  This is deliberately generated from ontology
    # vocabulary instead of copying independently authored evaluation prose.
    for alias in (*ko_aliases, *en_aliases):
        normalized_alias = " ".join(alias.casefold().split())
        terms = (normalized_alias,)
        cue_key = _goal_cue_key(normalized_alias)
        # Very short Latin abbreviations need word-boundary evidence; the
        # runtime intentionally removes whitespace, so an unqualified "ELS"
        # cue could otherwise appear accidentally across "cancel Spotify".
        short_latin = cue_key.isascii() and cue_key.isalpha() and len(cue_key) <= 3
        if V4_ALIAS_OWNER_COUNTS[normalized_alias] != 1 or terms in seen_rule_terms or short_latin:
            continue
        seen_rule_terms.add(terms)
        specific_rules.append(
            {
                "all_of": [normalized_alias],
                "score": qualified_score,
                "rule_kind": "v4_distinctive_alias",
            }
        )

    # Request framing is reusable evidence when the same noun appears both as
    # the desired destination and as incidental warning/context text.  It
    # lets "need Order history; I will confirm any return" prefer history,
    # while "past order's return menu" still prefers the return action.
    for alias in ko_aliases:
        for request_cue in ("필요",):
            terms = (alias.casefold(), request_cue)
            if terms not in seen_rule_terms:
                seen_rule_terms.add(terms)
                specific_rules.append({"all_of": list(terms), "score": 1.0})
    for alias in en_aliases:
        for request_cue in ("need", "want", "find", "open", "go to"):
            terms = (alias.casefold(), request_cue)
            if terms not in seen_rule_terms:
                seen_rule_terms.add(terms)
                specific_rules.append({"all_of": list(terms), "score": 1.0})

    # Ambiguous labels remain resolvable when any reviewed domain synonym is
    # present.  Generate the full cross-product rather than relying on one
    # arbitrarily selected context/alias pair.  At runtime punctuation and
    # whitespace are normalized, so phrases such as ``second-hand`` also
    # match the ontology's ``secondhand`` cue.
    for domain_phrase, aliases in (
        (group.root_ko, ko_aliases),
        (group.root_en, en_aliases),
        *(
            (context, ko_aliases)
            for context in group.ko_context
            if " ".join(context.casefold().split()) not in V4_FEATURE_ALIASES
        ),
        *(
            (context, en_aliases)
            for context in group.en_context
            if " ".join(context.casefold().split()) not in V4_FEATURE_ALIASES
        ),
    ):
        for alias in aliases:
            terms = tuple(_specific_goal_terms(domain_phrase, alias))
            if terms in seen_rule_terms:
                continue
            seen_rule_terms.add(terms)
            is_root = domain_phrase in {group.root_ko, group.root_en}
            contextual_score = qualified_score
            if not is_root and _is_sibling_feature_fragment(group, seed, domain_phrase):
                # Do not treat a sibling action such as "return" as proof
                # that the user wants the broad order-history destination.
                contextual_score = min(contextual_score, 0.997)
            specific_rules.append({"all_of": list(terms), "score": contextual_score})
    return {
        "intent_id": "v4_" + seed.function_id.replace(".", "_"),
        "terminal_function": seed.function_id,
        "patterns": [*ko_patterns, *en_patterns],
        "patterns_by_locale": {"ko-KR": ko_patterns, "en-US": en_patterns},
        "goal_rules": [
            *specific_rules,
            {"all_of": [group.ko_context[0], ko_aliases[1]], "score": 0.985},
            {"all_of": [group.en_context[0].casefold(), en_aliases[1].casefold()], "score": 0.985},
        ],
        "route": _route(group, seed),
        "avoid_functions": [group.avoid_root],
        "desired_state": "user_confirmation_required" if confirmation_required else "destination_visible",
        "terminal_condition": {
            "stop_policy": "stop_before_action" if confirmation_required else "on_destination_screen"
        },
    }


V4_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V4_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)


REQUIRED_DOMAINS = frozenset(
    {
        "browser_web", "messaging", "calls", "app_store", "family_store", "android_backup",
        "android_connectivity", "android_safety", "local_transit", "weather_news", "marketplace",
        "shopping_logistics", "pharmacy_telehealth", "jobs", "property", "utilities",
    }
)
REQUIRED_FUNCTIONS = frozenset(
    {
        "browser.tabs", "browser.tab_groups", "browser.bookmarks", "browser.history",
        "browser.downloads", "browser.site_permissions", "browser.password_manager",
        "browser.autofill_addresses", "browser.translate", "browser.reader_mode",
        "browser.default_search", "browser.incognito", "messaging.archive", "messaging.unarchive",
        "messaging.delete", "messaging.mute", "messaging.pin", "messaging.mark_spam",
        "messaging.block_sender", "messaging.group_create", "messaging.rcs",
        "messaging.device_pairing", "messaging.backup", "calls.settings", "app_store.updates",
        "app_store.library", "app_store.beta_join", "app_store.refund_request", "app_store.budget",
        "family_store.purchase_approval", "family_store.payment_method",
        "family_store.parental_controls", "android_backup.device_backup",
        "android_backup.restore_device", "android_connectivity.quick_share",
        "android_connectivity.cast", "android_connectivity.nfc", "android_connectivity.usb_preferences",
        "android_connectivity.default_apps", "android_connectivity.app_languages",
        "android_connectivity.data_saver", "android_safety.earthquake_alerts",
        "android_safety.emergency_location", "android_safety.emergency_info",
        "android_safety.crash_detection",
    }
)


class V4CatalogValidationError(ValueError):
    """Raised when v4 data is incomplete, unsafe, or collides with its base."""


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _normalized_alias(value: object) -> str:
    return " ".join(str(value).casefold().split())


def _materialized_v4_intents(base_payload: Mapping[str, object]) -> list[dict[str, object]]:
    """Apply deterministic cross-generation cue and pattern safeguards."""

    base_cues = _base_goal_cues(base_payload)
    base_pattern_keys = {
        _runtime_goal_key(pattern)
        for intent in base_payload.get("intents", [])  # type: ignore[union-attr]
        if isinstance(intent, Mapping)
        for pattern in intent.get("patterns", [])
        if _runtime_goal_key(pattern)
    }
    intents = copy.deepcopy(list(V4_INTENTS))
    for intent in intents:
        filtered_rules: list[dict[str, object]] = []
        for rule in intent.get("goal_rules", []):
            if not isinstance(rule, dict):
                continue
            if rule.get("rule_kind") == "v4_distinctive_alias":
                terms = list(rule.get("all_of", []))
                if (
                    len(terms) == 1
                    and _goal_cue_key(terms[0]) in base_cues
                    and not _has_explicit_action_cue(terms[0])
                ):
                    continue
            filtered_rules.append(rule)
        intent["goal_rules"] = filtered_rules

        retained_patterns = [
            pattern
            for pattern in intent.get("patterns", [])
            if _runtime_goal_key(pattern) not in base_pattern_keys
        ]
        intent["patterns"] = retained_patterns
        retained_keys = {_runtime_goal_key(pattern) for pattern in retained_patterns}
        patterns_by_locale = intent.get("patterns_by_locale", {})
        if isinstance(patterns_by_locale, dict):
            for locale, patterns in patterns_by_locale.items():
                patterns_by_locale[locale] = [
                    pattern for pattern in patterns if _runtime_goal_key(pattern) in retained_keys
                ]
    return intents


def _base_materialization_state(base_payload: Mapping[str, object]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    base_functions = {
        str(item.get("function_id", "")): item
        for item in base_payload.get("functions", [])  # type: ignore[union-attr]
        if isinstance(item, Mapping)
    }
    base_intents = {
        str(item.get("intent_id", "")): item
        for item in base_payload.get("intents", [])  # type: ignore[union-attr]
        if isinstance(item, Mapping)
    }
    expected_functions = {str(item["function_id"]): item for item in V4_FUNCTIONS}
    pre_v4_payload = copy.deepcopy(dict(base_payload))
    pre_v4_payload["functions"] = [
        item
        for item in base_payload.get("functions", [])  # type: ignore[union-attr]
        if not (isinstance(item, Mapping) and str(item.get("function_id", "")) in expected_functions)
    ]
    pre_v4_payload["intents"] = [
        item
        for item in base_payload.get("intents", [])  # type: ignore[union-attr]
        if not (isinstance(item, Mapping) and str(item.get("intent_id", "")).startswith("v4_"))
    ]
    expected_intents = {
        str(item["intent_id"]): item for item in _materialized_v4_intents(pre_v4_payload)
    }
    function_collisions = set(expected_functions).intersection(base_functions)
    intent_collisions = set(expected_intents).intersection(base_intents)
    if not function_collisions and not intent_collisions:
        return False, []
    complete = function_collisions == set(expected_functions) and intent_collisions == set(expected_intents)
    if not complete:
        errors.append("base catalog contains a partial v4 ID collision")
        return False, errors
    for function_id, expected in expected_functions.items():
        if base_functions[function_id] != expected:
            errors.append(f"v4 function collides with different base definition: {function_id}")
    for intent_id, expected in expected_intents.items():
        if base_intents[intent_id] != expected:
            errors.append(f"v4 intent collides with different base definition: {intent_id}")
    return not errors, errors


def validate_v4_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate completeness, collisions, references, evidence, and safety."""

    errors: list[str] = []
    function_ids = [str(item.get("function_id", "")) for item in V4_FUNCTIONS]
    intent_ids = [str(item.get("intent_id", "")) for item in V4_INTENTS]
    function_id_set = set(function_ids)
    intent_id_set = set(intent_ids)
    if len(V4_FUNCTIONS) < 120:
        errors.append(f"v4 must define at least 120 functions, got {len(V4_FUNCTIONS)}")
    if len(V4_INTENTS) < 105:
        errors.append(f"v4 must define at least 105 intents, got {len(V4_INTENTS)}")
    for value in sorted(_duplicates(function_ids)):
        errors.append(f"duplicate v4 function_id: {value}")
    for value in sorted(_duplicates(intent_ids)):
        errors.append(f"duplicate v4 intent_id: {value}")
    domains = {str(item.get("domain", "")) for item in V4_FUNCTIONS}
    if not REQUIRED_DOMAINS <= domains:
        errors.append("missing required v4 domains: " + ", ".join(sorted(REQUIRED_DOMAINS - domains)))
    if not REQUIRED_FUNCTIONS <= function_id_set:
        errors.append("missing required v4 concepts: " + ", ".join(sorted(REQUIRED_FUNCTIONS - function_id_set)))

    allowed_source_hosts = {
        "support.google.com", "developer.android.com", "www.usps.com", "consumer.ftc.gov",
        "help.usajobs.gov", "www.usa.gov",
    }
    source_urls: list[str] = []
    for source_id, source in OFFICIAL_SOURCES.items():
        missing = {"publisher", "title", "url", "verified_status", "verified_on"} - set(source)
        if missing:
            errors.append(f"official source {source_id}: missing {sorted(missing)}")
            continue
        url = str(source["url"])
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_source_hosts:
            errors.append(f"official source {source_id}: unapproved primary-source URL {url}")
        if int(source["verified_status"]) != 200:
            errors.append(f"official source {source_id}: source was not verified with HTTP 200")
        if str(source["verified_on"]) != VERIFIED_ON:
            errors.append(f"official source {source_id}: wrong verification date")
        source_urls.append(url)
    for url in sorted(_duplicates(source_urls)):
        errors.append(f"duplicate official source URL: {url}")

    required_fields = {
        "function_id", "domain", "scope", "node_kind", "stop_policy", "name_ko", "name_en",
        "description", "risk_level", "automation_policy", "terminal", "state_changing",
        "role_hints", "aliases", "positive_context", "negative_context", "state_cues", "risk_cues",
        "source_refs", "evidence_level",
    }
    never_auto_stops = {
        "before_action", "before_activation", "user_confirmation", "user_only", "stop_before_action"
    }
    alias_owners: dict[tuple[str, str, str], str] = {}
    referenced_source_ids: set[str] = set()
    forbidden_coordinate_keys = {"x", "y", "left", "top", "right", "bottom", "bounds", "coordinates", "coordinate"}
    for item in V4_FUNCTIONS:
        function_id = str(item.get("function_id", "<missing>"))
        missing_fields = sorted(required_fields - set(item))
        if missing_fields:
            errors.append(f"{function_id}: missing fields {missing_fields}")
        forbidden = forbidden_coordinate_keys.intersection(str(key).casefold() for key in item)
        if forbidden:
            errors.append(f"{function_id}: app coordinates are forbidden: {sorted(forbidden)}")
        if not str(item.get("scope", "")).strip() or not str(item.get("node_kind", "")).strip():
            errors.append(f"{function_id}: scope and node_kind are required")
        aliases = item.get("aliases", {})
        if not isinstance(aliases, Mapping):
            errors.append(f"{function_id}: aliases must be a locale map")
        else:
            for locale in ("ko-KR", "en-US"):
                values = aliases.get(locale, [])
                if not isinstance(values, list) or len(values) < 4 or any(not str(value).strip() for value in values):
                    errors.append(f"{function_id}: {locale} requires at least four non-empty aliases")
                    continue
                normalized_values = [_normalized_alias(value) for value in values]
                if len(normalized_values) != len(set(normalized_values)):
                    errors.append(f"{function_id}: duplicate normalized alias in {locale}")
                if bool(item.get("terminal")):
                    domain = str(item.get("domain", ""))
                    for normalized in normalized_values:
                        key = (domain, locale, normalized)
                        owner = alias_owners.get(key)
                        if owner is not None and owner != function_id:
                            errors.append(
                                f"terminal alias collision in {domain}/{locale}: {normalized!r} owned by {owner} and {function_id}"
                            )
                        alias_owners[key] = function_id
        for field in ("positive_context", "negative_context", "role_hints", "state_cues", "risk_cues"):
            if not item.get(field):
                errors.append(f"{function_id}: {field} must not be empty")
        positive = {_normalized_alias(value) for value in item.get("positive_context", [])}  # type: ignore[arg-type]
        negative = {_normalized_alias(value) for value in item.get("negative_context", [])}  # type: ignore[arg-type]
        overlap = positive.intersection(negative)
        if overlap:
            errors.append(f"{function_id}: positive/negative context collision {sorted(overlap)}")
        risk = str(item.get("risk_level", ""))
        policy = str(item.get("automation_policy", ""))
        changing = bool(item.get("state_changing"))
        stop_policy = str(item.get("stop_policy", ""))
        if risk not in {"low", "medium", "high"}:
            errors.append(f"{function_id}: invalid risk_level {risk!r}")
        if policy not in {"safe_navigation", "never_auto"}:
            errors.append(f"{function_id}: invalid automation_policy {policy!r}")
        if (changing or risk == "high") and policy != "never_auto":
            errors.append(f"{function_id}: changing/high-risk function must be never_auto")
        if (changing or risk == "high") and stop_policy not in never_auto_stops:
            errors.append(f"{function_id}: changing/high-risk function must stop before final click")
        if changing and risk not in {"medium", "high"}:
            errors.append(f"{function_id}: state-changing function must be medium/high risk")
        refs = item.get("source_refs", [])
        if not isinstance(refs, list):
            errors.append(f"{function_id}: source_refs must be a list")
            refs = []
        for source_id in refs:
            source_ref = str(source_id)
            if source_ref not in OFFICIAL_SOURCES:
                errors.append(f"{function_id}: unknown official source ref {source_ref}")
            referenced_source_ids.add(source_ref)
        evidence_level = str(item.get("evidence_level", ""))
        if refs and evidence_level != "official":
            errors.append(f"{function_id}: sourced functions must use official evidence_level")
        if not refs and evidence_level != "ontology_design":
            errors.append(f"{function_id}: unsourced functions must declare ontology_design")

    unused_sources = set(OFFICIAL_SOURCES).difference(referenced_source_ids)
    if unused_sources:
        errors.append("unused official source entries: " + ", ".join(sorted(unused_sources)))

    known_function_ids = set(function_id_set)
    materialized = False
    if base_payload is not None:
        materialized, collision_errors = _base_materialization_state(base_payload)
        errors.extend(collision_errors)
        base_function_ids = {
            str(item.get("function_id", ""))
            for item in base_payload.get("functions", [])  # type: ignore[union-attr]
            if isinstance(item, Mapping)
        }
        base_intent_ids = {
            str(item.get("intent_id", ""))
            for item in base_payload.get("intents", [])  # type: ignore[union-attr]
            if isinstance(item, Mapping)
        }
        if not materialized:
            for value in sorted(function_id_set.intersection(base_function_ids)):
                errors.append(f"v4 function collides with base catalog: {value}")
            for value in sorted(intent_id_set.intersection(base_intent_ids)):
                errors.append(f"v4 intent collides with base catalog: {value}")
        known_function_ids.update(base_function_ids)

    terminal_functions: set[str] = set()
    for intent in V4_INTENTS:
        intent_id = str(intent.get("intent_id", "<missing>"))
        terminal = str(intent.get("terminal_function", ""))
        terminal_functions.add(terminal)
        if terminal not in known_function_ids:
            errors.append(f"{intent_id}: unknown terminal_function {terminal}")
        locale_patterns = intent.get("patterns_by_locale", {})
        if not isinstance(locale_patterns, Mapping):
            errors.append(f"{intent_id}: patterns_by_locale must be a locale map")
        else:
            for locale in ("ko-KR", "en-US"):
                if len(locale_patterns.get(locale, [])) < 3:  # type: ignore[arg-type]
                    errors.append(f"{intent_id}: {locale} requires at least three patterns")
        rules = intent.get("goal_rules", [])
        if not isinstance(rules, list) or len(rules) < 4:
            errors.append(f"{intent_id}: requires at least four goal rules")
        else:
            for index, rule in enumerate(rules):
                if not isinstance(rule, Mapping) or not rule.get("all_of"):
                    errors.append(f"{intent_id}: goal_rules[{index}] must have all_of cues")
        route = intent.get("route", [])
        if not isinstance(route, list) or not route:
            errors.append(f"{intent_id}: route must not be empty")
        else:
            previous_weight = -1.0
            for index, step in enumerate(route):
                function_id = str(step.get("function_id", ""))
                weight = float(step.get("weight", 0.0))
                if function_id not in known_function_ids:
                    errors.append(f"{intent_id}: route[{index}] references {function_id}")
                if weight <= previous_weight:
                    errors.append(f"{intent_id}: route weights must be strictly increasing")
                previous_weight = weight
            if str(route[-1].get("function_id", "")) != terminal:
                errors.append(f"{intent_id}: route must end at terminal_function")
        avoid = intent.get("avoid_functions", [])
        if not isinstance(avoid, list) or not avoid:
            errors.append(f"{intent_id}: avoid_functions must not be empty")
        else:
            for function_id in avoid:
                if str(function_id) not in known_function_ids:
                    errors.append(f"{intent_id}: avoid_functions references {function_id}")

    expected_terminals = {
        str(item["function_id"]) for item in V4_FUNCTIONS if bool(item.get("terminal"))
    }
    if terminal_functions != expected_terminals:
        missing = expected_terminals - terminal_functions
        extras = terminal_functions - expected_terminals
        if missing:
            errors.append("terminal functions without intents: " + ", ".join(sorted(missing)))
        if extras:
            errors.append("intents targeting non-terminal functions: " + ", ".join(sorted(extras)))

    if errors:
        raise V4CatalogValidationError("invalid navigation catalog v4 data:\n- " + "\n- ".join(errors))

    functions_by_domain = Counter(str(item["domain"]) for item in V4_FUNCTIONS)
    risk_counts = Counter(str(item["risk_level"]) for item in V4_FUNCTIONS)
    sourced_functions = sum(bool(item["source_refs"]) for item in V4_FUNCTIONS)
    return {
        "catalog_version": CATALOG_V4_VERSION,
        "functions": len(V4_FUNCTIONS),
        "intents": len(V4_INTENTS),
        "domains": len(functions_by_domain),
        "official_sources": len(OFFICIAL_SOURCES),
        "sourced_functions": sourced_functions,
        "ontology_design_functions": len(V4_FUNCTIONS) - sourced_functions,
        "aliases": sum(len(values) for item in V4_FUNCTIONS for values in item["aliases"].values()),  # type: ignore[union-attr]
        "goal_patterns": sum(len(item["patterns"]) for item in V4_INTENTS),  # type: ignore[arg-type]
        "goal_rules": sum(len(item["goal_rules"]) for item in V4_INTENTS),  # type: ignore[arg-type]
        "route_steps": sum(len(item["route"]) for item in V4_INTENTS),  # type: ignore[arg-type]
        "state_changing": sum(bool(item["state_changing"]) for item in V4_FUNCTIONS),
        "high_risk": risk_counts.get("high", 0),
        "materialized": materialized,
        "functions_by_domain": dict(sorted(functions_by_domain.items())),
        "risk_counts": dict(sorted(risk_counts.items())),
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return an idempotent, validated, non-mutating v4 merge."""

    source_snapshot = copy.deepcopy(dict(base_payload))
    stats = validate_v4_data(base_payload)
    merged = copy.deepcopy(dict(base_payload))
    if stats["materialized"]:
        return merged
    merged["catalog_version"] = "4.0.0"
    marker = (
        "Broad-services v4 adds browser, messaging, store, Android safety, local-service, "
        "commerce, health, jobs, property, and utility functions."
    )
    description = str(merged.get("description", "")).rstrip()
    if marker not in description:
        description = f"{description} {marker}".strip()
    merged["description"] = description
    merged["functions"] = [*list(merged.get("functions", [])), *copy.deepcopy(list(V4_FUNCTIONS))]
    v4_intents = _materialized_v4_intents(base_payload)
    merged["intents"] = [*list(merged.get("intents", [])), *v4_intents]
    merged["official_sources_v4"] = copy.deepcopy(OFFICIAL_SOURCES)
    if dict(base_payload) != source_snapshot:
        raise AssertionError("merge_with_base mutated the source catalog")
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate independent ExitGuide navigation catalog v4 data")
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE_CATALOG)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    stats = validate_v4_data(load_base_catalog(args.base))
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(
            "navigation catalog v4 data valid: "
            f"functions={stats['functions']} intents={stats['intents']} domains={stats['domains']} "
            f"sources={stats['official_sources']} sourced={stats['sourced_functions']} "
            f"aliases={stats['aliases']} patterns={stats['goal_patterns']} rules={stats['goal_rules']} "
            f"routes={stats['route_steps']} changing={stats['state_changing']} high={stats['high_risk']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
