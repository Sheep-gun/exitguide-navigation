from __future__ import annotations

"""Reviewable long-tail navigation ontology for the v3 catalog expansion.

This module is intentionally independent from ``Expand-NavigationCatalog.py``.
It contains only general app-function concepts, never benchmark sentences or
app-specific screen coordinates.  A later materializer can merge ``V3_FUNCTIONS``
and ``V3_INTENTS`` into the runtime catalog after review.

Safety invariant: every state-changing or high-risk function is ``never_auto``
and stops before the final activation so the user performs the final click.
"""

import argparse
import copy
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
CATALOG_V3_VERSION = "3.0.0-long-tail"


def _terms(value: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        values = value.split("|")
    else:
        values = value
    return tuple(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


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
    via: tuple[str, ...] = ()


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
    via: str = "",
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
        via=_terms(via),
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
        features=tuple(features),
    )


# Modes encode the action boundary, not whether a menu can be discovered.
# ``change`` and ``submit`` always stop before the user-owned final click.
MODE_METADATA: dict[str, dict[str, object]] = {
    "view": {
        "risk_level": "low",
        "automation_policy": "safe_navigation",
        "state_changing": False,
        "node_kind": "destination",
        "stop_policy": "on_destination_screen",
    },
    "sensitive": {
        "risk_level": "high",
        "automation_policy": "never_auto",
        "state_changing": False,
        "node_kind": "destination",
        "stop_policy": "before_action",
    },
    "change": {
        "risk_level": "medium",
        "automation_policy": "never_auto",
        "state_changing": True,
        "node_kind": "state_change",
        "stop_policy": "before_action",
    },
    "submit": {
        "risk_level": "high",
        "automation_policy": "never_auto",
        "state_changing": True,
        "node_kind": "state_change",
        "stop_policy": "before_action",
    },
}


GROUPS: tuple[GroupSeed, ...] = (
    G(
        "email", "email.hub", "이메일", "Email", "in_app",
        "받은편지함|메일함|메시지", "inbox|mailbox|message",
        "문자 메시지|캘린더 일정", "text message|calendar event", "calendar.hub",
        F("email.archive", "메일 보관처리", "Archive email", "보관|아카이브|받은편지함에서 치우기", "archive|move to archive|remove from inbox", "메일 목록|보관함", "삭제|휴지통", "change"),
        F("email.swipe_actions", "메일 스와이프 동작", "Email swipe actions", "스와이프 설정|밀기 동작|좌우 밀기", "swipe actions|swipe settings|left and right swipe", "메일 일반 설정|동작 선택", "제스처 탐색|화면 넘기기", "change"),
        F("email.signature", "이메일 서명", "Email signature", "메일 서명|모바일 서명|서명 설정", "email signature|mobile signature|signature settings", "메일 작성 설정|발신 계정", "전자서명 인증서|문서 서명"),
        F("email.vacation_responder", "부재중 자동응답", "Vacation responder", "부재중 응답|휴가 자동응답|자동 회신", "vacation responder|out of office|automatic reply", "시작일|종료일|답장 내용", "일반 알림|자동 전달", "change"),
        F("email.sync", "이메일 동기화", "Email sync", "메일 동기화|동기화 주기|새 메일 가져오기", "email sync|sync frequency|fetch new mail", "계정 동기화|최근 동기화", "파일 백업|연락처 동기화", "change"),
        F("email.labels", "메일 라벨", "Email labels", "라벨 관리|메일 분류표|폴더 라벨", "email labels|manage labels|mail folders", "받은편지함 분류|라벨 색상", "주소록 그룹|캘린더 색상"),
        F("email.filters", "메일 필터", "Email filters", "필터 규칙|자동 분류|메일 규칙", "email filters|filter rules|mail rules", "보낸 사람|제목 조건|자동 보관", "검색 결과|스팸 차단", "change"),
        F("email.scheduled", "예약 발송 메일", "Scheduled email", "예약 발송|발송 예정|예약 메일", "scheduled email|send later|scheduled messages", "발송 시간|임시보관함", "캘린더 알림|정기 결제"),
        F("email.spam", "스팸 메일함", "Spam folder", "스팸함|정크 메일|원치 않는 메일", "spam folder|junk mail|unwanted email", "스팸 신고|차단된 발신자", "휴지통|보관함"),
        F("email.forwarding", "이메일 자동 전달", "Email forwarding", "자동 전달|메일 포워딩|전달 주소", "email forwarding|automatic forwarding|forwarding address", "전달 확인|수신 주소", "수동 전달|공유 링크", "change"),
        F("email.send", "이메일 보내기", "Send email", "보내기|메일 발송|메시지 전송", "send email|send message|deliver mail", "받는 사람|제목|본문", "임시저장|예약 발송", "submit"),
    ),
    G(
        "calendar", "calendar.hub", "캘린더", "Calendar", "in_app",
        "일정|달력|이벤트", "schedule|calendar|event",
        "이메일|할 일 목록", "email|task list", "email.hub",
        F("calendar.event.create", "일정 만들기", "Create calendar event", "새 일정|이벤트 추가|일정 생성", "create event|new event|add calendar event", "제목|날짜|시간", "할 일 추가|예약 조회", "submit"),
        F("calendar.event.edit", "일정 수정", "Edit calendar event", "일정 편집|이벤트 변경|시간 수정", "edit event|change event|update calendar event", "기존 일정|저장", "새 일정|일정 삭제", "submit"),
        F("calendar.event.delete", "일정 삭제", "Delete calendar event", "이벤트 삭제|일정 지우기|캘린더에서 제거", "delete event|remove event|erase calendar event", "삭제 확인|참석자 알림", "일정 숨기기|캘린더 삭제", "submit"),
        F("calendar.rsvp", "일정 참석 여부", "Event RSVP", "참석|불참|미정 응답", "rsvp|accept invitation|decline invitation|maybe", "초대받은 일정|응답", "설문 응답|예약 취소", "change"),
        F("calendar.notifications", "일정 알림", "Calendar notifications", "일정 알림|이벤트 알림|미리 알림", "calendar notifications|event alerts|reminders", "몇 분 전|이메일 알림|푸시", "앱 전체 알림|메일 알림", "change"),
        F("calendar.shared_calendars", "공유 캘린더", "Shared calendars", "캘린더 공유|공유 일정표|다른 사람 캘린더", "shared calendars|share calendar|other calendars", "공유 대상|보기 권한", "위치 공유|사진 앨범 공유", "sensitive"),
        F("calendar.timezone", "캘린더 시간대", "Calendar time zone", "시간대|표준 시간대|여행 시간대", "calendar time zone|time zone|travel time zone", "GMT|UTC|지역", "언어 설정|시계 알람", "change"),
        F("calendar.working_hours", "근무 시간", "Working hours", "근무 시간|업무 시간|근무 위치", "working hours|office hours|working location", "요일|시작 시간|종료 시간", "영업시간|스크린 타임", "change"),
        F("calendar.search", "일정 검색", "Search calendar", "일정 찾기|캘린더 검색|이벤트 검색", "search calendar|find event|calendar search", "제목|참석자|날짜", "메일 검색|장소 검색"),
        F("calendar.export", "캘린더 내보내기", "Export calendar", "일정 내보내기|ICS 내보내기|캘린더 백업", "export calendar|export ics|calendar backup", "ICS 파일|전체 일정", "연락처 내보내기|문서 PDF", "sensitive"),
    ),
    G(
        "contacts", "contacts.hub", "연락처", "Contacts", "personal_data",
        "주소록|전화번호|사람", "address book|phone number|people",
        "채팅방|메일함", "chat room|mailbox", "email.hub",
        F("contacts.create", "연락처 만들기", "Create contact", "새 연락처|연락처 추가|사람 저장", "create contact|add contact|save person", "이름|전화번호|이메일", "계정 추가|채팅 시작", "submit"),
        F("contacts.edit", "연락처 수정", "Edit contact", "연락처 편집|연락처 전화번호 변경|사람 정보 수정", "edit contact|update contact|change contact phone number", "기존 연락처|저장", "프로필 수정|계정 전화번호", "submit"),
        F("contacts.import", "연락처 가져오기", "Import contacts", "주소록 가져오기|VCF 가져오기|SIM 연락처 복사", "import contacts|import vcf|copy sim contacts", "VCF 파일|SIM 카드|계정", "메일 가져오기|사진 가져오기", "submit"),
        F("contacts.export", "연락처 내보내기", "Export contacts", "주소록 내보내기|VCF 저장|연락처 백업", "export contacts|save vcf|contact backup", "VCF 파일|저장 위치", "캘린더 내보내기|대화 내보내기", "sensitive"),
        F("contacts.merge_duplicates", "중복 연락처 병합", "Merge duplicate contacts", "연락처 중복 병합|같은 연락처 합치기|중복 연락처 정리", "merge duplicate contacts|combine contacts|clean duplicate contacts", "중복 후보|병합 결과", "계정 병합|파일 중복", "change"),
        F("contacts.blocked_numbers", "차단된 전화번호", "Blocked phone numbers", "차단 번호|수신 차단 목록|전화 차단", "blocked numbers|call blocking|blocked callers", "전화|문자|차단 해제", "차단된 사용자|스팸 메일"),
        F("contacts.emergency", "긴급 연락처", "Emergency contacts", "비상 연락처|긴급 연락망|응급 연락처", "emergency contacts|ice contacts|contact emergency people", "잠금 화면|의료 정보|가족", "일반 즐겨찾기|고객센터", "sensitive"),
        F("contacts.sync", "연락처 동기화", "Contact sync", "주소록 동기화|연락처 자동 동기화|계정 연락처", "contact sync|sync contacts|account contacts", "계정|최근 동기화|자동", "메일 동기화|사진 백업", "change"),
    ),
    G(
        "maps", "maps.hub", "지도", "Maps", "location",
        "장소|경로|현재 위치", "place|route|current location",
        "사진|연락처", "photos|contacts", "mobility.hub",
        F("maps.directions", "길찾기", "Directions", "경로 찾기|길 안내 경로|가는 방법", "directions|find route|get directions", "출발지|도착지|교통수단", "장소 저장|여행 예약"),
        F("maps.navigation", "내비게이션 시작", "Start navigation", "안내 시작|경로 안내 시작|내비 시작", "start navigation|navigate|begin guidance", "예상 시간|회전 안내|도착", "경로 미리보기|탐색 기록", "change"),
        F("maps.offline_maps", "오프라인 지도", "Offline maps", "지도 다운로드|오프라인 지역|다운로드 지도", "offline maps|download maps|offline areas", "다운로드 지역|저장 공간|업데이트", "콘텐츠 다운로드|클라우드 파일"),
        F("maps.saved_lists", "저장한 장소 목록", "Saved place lists", "저장 목록|즐겨찾는 장소|가고 싶은 곳", "saved lists|your lists|saved places|favorites|want to go", "장소 모음|별표|목록", "음악 재생목록|상품 찜"),
        F("maps.location_sharing", "실시간 위치 공유", "Location sharing", "지도 위치 공유|지도에서 내 위치 보내기|실시간 지도 위치", "maps location sharing|share live map location|real-time map location", "공유 시간|공유 상대|중지", "장소 링크 공유|주소 복사", "submit"),
        F("maps.trip_progress_sharing", "이동 경로 진행 공유", "Share trip progress", "이동 상황 공유|도착 예정 공유|경로 진행 공유", "share trip progress|share eta|share journey", "도착 예정 시간|현재 경로|공유 상대", "정적 위치 공유|차량 호출", "submit"),
        F("maps.incognito", "지도 시크릿 모드", "Maps incognito mode", "시크릿 모드|지도 기록 안 남기기|비공개 탐색", "incognito mode|private maps|pause map history", "검색 기록|위치 기록|프로필", "브라우저 시크릿|위치 공유", "change"),
        F("maps.location_history", "위치 기록", "Location history", "타임라인|방문 기록|위치 이력", "location history|timeline|visited places", "날짜|방문 장소|경로", "검색 기록|운행 기록", "sensitive"),
        F("maps.avoid_options", "경로 회피 옵션", "Route avoidance options", "톨게이트 피하기|고속도로 제외|페리 피하기", "avoid tolls|avoid highways|avoid ferries", "경로 옵션|통행료|도로", "콘텐츠 차단|광고 숨기기", "change"),
        F("maps.home_work", "집·직장 주소", "Home and work addresses", "집 주소|직장 주소|라벨 주소", "home address|work address|labeled places", "저장 장소|통근|주소", "배송 주소|청구지 주소", "sensitive"),
        F("maps.report_issue", "지도 정보 수정 제안", "Suggest map edit", "장소 수정|도로 문제 신고|지도 오류", "suggest an edit|report map issue|fix place information", "장소 정보|도로 폐쇄|제출", "사용자 신고|결제 분쟁", "submit"),
    ),
    G(
        "mobility_delivery", "mobility.hub", "이동·배달", "Mobility and delivery", "location",
        "호출|배달|이동|주문", "ride|delivery|mobility|order",
        "지도 저장 목록|항공 예약", "saved maps|flight booking", "maps.hub",
        F("mobility.ride_request", "차량 호출", "Request a ride", "택시 호출|차 부르기|승차 요청", "request a ride|hail a car|book taxi", "출발지|도착지|차량 종류", "길찾기|렌터카 예약", "submit"),
        F("mobility.fare_estimate", "예상 요금", "Fare estimate", "택시비 예상|호출 요금|예상 운임", "fare estimate|estimated price|ride cost", "거리|차량 종류|통행료", "확정 결제|배달비"),
        F("mobility.trip_history", "이용 기록", "Ride history", "탑승 내역|이동 기록|지난 호출", "ride history|past trips|trip receipts", "기사|운임|출발 도착", "위치 기록|항공 여정"),
        F("mobility.safety_center", "이동 안전 센터", "Ride safety center", "안전 센터|안심 기능|긴급 도움", "safety center|ride safety|emergency help", "긴급 연락처|차량 정보|위치", "고객센터|일반 도움말", "sensitive"),
        F("mobility.lost_item", "분실물 문의", "Report lost item", "차량 분실물|두고 내린 물건|기사에게 연락", "lost item|left item in car|contact driver", "탑승 기록|기사|연락", "배송 분실|계정 신고", "submit"),
        F("delivery.order_tracking", "배달 실시간 추적", "Live delivery tracking", "배달 위치|기사 위치|주문 추적", "live delivery tracking|courier location|track order", "도착 예정|지도|배달원", "택배 송장|차량 호출"),
        F("delivery.address", "배달 주소", "Delivery address", "배달지|배달 주소 관리|새 배달지", "delivery address|manage delivery addresses|add delivery address", "도로명|상세 주소|문 앞", "청구지 주소|집 직장 라벨", "change"),
        F("delivery.instructions", "배달 요청사항", "Delivery instructions", "문 앞에 두기|배달 메모|요청사항", "delivery instructions|drop-off note|courier note", "공동현관|문 앞|연락 방법", "음식 옵션|기사 신고", "change"),
        F("delivery.contact_courier", "배달원 연락", "Contact courier", "기사에게 전화|배달원 채팅|라이더 연락", "contact courier|call driver|message rider", "현재 주문|전화|채팅", "고객센터|판매자 문의", "sensitive"),
        F("delivery.tip", "배달 팁", "Courier tip", "기사 팁|감사 팁|배달원 팁", "courier tip|driver tip|add gratuity", "팁 금액|결제 수단|주문", "배달비|쿠폰", "submit"),
        F("delivery.issue", "배달 문제 신고", "Report delivery issue", "오배송 신고|음식 누락|배달 문제", "report delivery issue|missing item|wrong delivery", "주문 선택|사진|환불", "기사 분실물|사용자 신고", "submit"),
        F("delivery.reorder", "이전 주문 다시 주문", "Reorder", "재주문|같은 메뉴 다시|이전 주문 담기", "reorder|order again|repeat order", "주문 내역|장바구니|수량", "정기 주문|구독 갱신", "submit"),
    ),
    G(
        "telecom", "telecom.hub", "통신·SIM", "Mobile service and SIM", "device_service",
        "통신사|요금제|SIM|데이터", "carrier|mobile plan|sim|data",
        "앱 구독|와이파이 공유", "app subscription|wifi sharing", "android.connectivity.hub",
        F("telecom.data_plan", "모바일 요금제", "Mobile plan", "통신 요금제|데이터 플랜|월 요금제", "mobile plan|data plan|carrier plan", "기본료|데이터 제공량|약정", "앱 멤버십|인터넷 상품"),
        F("telecom.usage", "통신 사용량", "Mobile usage", "데이터 사용량|통화 사용량|잔여 데이터", "mobile usage|data allowance|remaining data", "이번 달|기가바이트|통화", "앱별 데이터|저장 공간"),
        F("telecom.bill", "통신 요금 청구서", "Mobile bill", "휴대폰 요금|통신 청구서|월별 요금", "mobile bill|carrier bill|monthly charges", "청구월|납부일|사용 내역", "신용카드 명세서|앱 결제"),
        F("telecom.autopay", "통신비 자동납부", "Mobile bill autopay", "통신비 자동이체|휴대폰 요금 자동납부|납부 수단", "mobile bill autopay|automatic carrier payment|billing autopay", "납부일|계좌|카드", "구독 자동 갱신|정기 송금", "change"),
        F("esim.install", "eSIM 설치", "Install eSIM", "이심 추가|eSIM 다운로드|요금제 추가", "install esim|add esim|download sim", "QR 코드|활성화 코드|통신사", "앱 설치|물리 SIM", "submit"),
        F("esim.transfer", "eSIM 이전", "Transfer eSIM", "이심 옮기기|새 기기로 eSIM 이전|SIM 전송", "transfer esim|move esim|transfer sim to new phone", "이전 기기|새 기기|통신사", "연락처 이전|파일 전송", "submit"),
        F("esim.remove", "eSIM 삭제", "Remove eSIM", "이심 삭제|모바일 요금제 제거|eSIM 지우기", "remove esim|delete esim|erase mobile plan", "서비스 중단|통신사|확인", "앱 삭제|계정 삭제", "submit"),
        F("roaming.settings", "데이터 로밍", "Data roaming", "로밍 설정|해외 데이터|데이터 로밍", "data roaming|roaming settings|international data", "해외|통신사|추가 요금", "국내 데이터|와이파이", "change"),
        F("roaming.pass", "로밍 패스", "Roaming pass", "해외 로밍 상품|로밍 이용권|여행 데이터", "roaming pass|international pass|travel data plan", "국가|기간|데이터", "항공 패스|관광 상품", "submit"),
        F("roaming.data_limit", "로밍 데이터 한도", "Roaming data limit", "해외 데이터 제한|로밍 사용 한도|요금 폭탄 방지", "roaming data limit|international data cap|roaming limit", "사용량|차단|한도", "앱 데이터 절약|스크린 타임", "change"),
        F("sim.pin", "SIM PIN", "SIM PIN", "유심 비밀번호|SIM 잠금|PIN 변경", "sim pin|sim lock|change pin", "PIN|PUK|재시작", "화면 잠금|앱 비밀번호", "change"),
        F("telecom.voicemail", "음성사서함", "Voicemail", "보이스메일|음성 메시지|음성사서함 설정", "voicemail|voice messages|voicemail settings", "인사말|비밀번호|알림", "음성 녹음|팟캐스트"),
    ),
    G(
        "documents_cloud", "documents.hub", "문서·클라우드", "Documents and cloud", "cloud_data",
        "문서|파일|클라우드|편집", "document|file|cloud|editor",
        "사진 갤러리|이메일", "photo gallery|email", "email.hub",
        F("documents.create", "새 문서", "Create document", "문서 만들기|새 파일|빈 문서", "create document|new file|blank document", "제목|템플릿|편집기", "폴더 만들기|게시물 작성", "change"),
        F("documents.scan", "문서 스캔", "Scan document", "카메라 스캔|종이 문서 촬영|PDF 스캔", "scan document|camera scan|scan to pdf", "카메라|자르기|페이지", "QR 스캔|사진 촬영"),
        F("documents.export_pdf", "PDF로 내보내기", "Export as PDF", "PDF 저장|PDF 변환|문서 내보내기", "export as pdf|save pdf|convert to pdf", "페이지|파일 형식|저장 위치", "인쇄|사진 내보내기", "change"),
        F("documents.version_history", "문서 버전 기록", "Document version history", "수정 기록|이전 버전|변경 내역", "version history|revision history|previous versions", "편집자|시간|복원", "활동 기록|백업 목록"),
        F("documents.sign", "문서 전자서명", "Sign document", "서명 추가|전자서명|문서에 사인", "sign document|electronic signature|add signature", "서명 위치|인증|완료", "이메일 서명|인증서 보기", "submit"),
        F("documents.comments", "문서 댓글", "Document comments", "문서 댓글 보기|검토 의견|문서 코멘트", "document comments|review document comments|document annotations", "답글|해결|멘션", "게시물 댓글|채팅"),
        F("documents.track_changes", "변경 내용 추적", "Track changes", "수정 제안|변경 추적|제안 모드", "track changes|suggesting mode|revision marks", "수락|거절|편집자", "버전 기록|자동 저장", "change"),
        F("cloud.sync", "클라우드 동기화", "Cloud sync", "파일 동기화|자동 동기화|클라우드 맞춤", "cloud sync|sync files|automatic synchronization", "최근 동기화|기기|충돌", "연락처 동기화|메일 동기화", "change"),
        F("cloud.storage", "클라우드 저장 공간", "Cloud storage usage", "클라우드 용량|클라우드 저장 공간 사용량|클라우드 용량 관리", "cloud storage|cloud storage usage|manage cloud space", "기가바이트|큰 파일|요금제", "기기 저장 공간|데이터 사용량"),
        F("cloud.offline", "오프라인 파일", "Offline files", "오프라인 사용|기기에 저장|인터넷 없이 열기", "offline files|available offline|download to device", "기기 공간|동기화|다운로드", "오프라인 지도|미디어 다운로드", "change"),
        F("cloud.shared_with_me", "나와 공유된 파일", "Shared with me", "공유받은 문서|나와 공유|받은 파일", "shared with me|shared documents|files others shared", "소유자|권한|최근 공유", "내 파일|공개 링크"),
        F("cloud.link_share", "파일 링크 공유", "Share file link", "공유 링크 만들기|링크로 보내기|공개 링크", "share file link|create sharing link|copy link", "접근 권한|만료|링크 복사", "첨부 파일|위치 공유", "submit"),
        F("cloud.link_revoke", "공유 링크 해제", "Revoke shared link", "링크 공유 중지|공개 링크 끄기|접근 차단", "revoke shared link|disable public link|stop link sharing", "공유 대상|접근 불가|확인", "파일 삭제|사용자 차단", "submit"),
        F("cloud.restore_version", "이전 문서 버전 복원", "Restore document version", "버전 복원|이전 상태로 되돌리기|수정 취소", "restore version|revert document|restore previous revision", "복원 시점|현재 변경|확인", "휴지통 복원|공장 초기화", "submit"),
    ),
    G(
        "education", "education.hub", "학습", "Learning", "in_app",
        "강의|과정|과제|성적", "course|lesson|assignment|grade",
        "업무 문서|게임", "work document|game", "documents.hub",
        F("education.courses", "수강 과정", "My courses", "내 강의|수강 목록|학습 과정", "my courses|course list|enrolled classes", "진도|강사|과정", "상품 구독|업무 프로젝트"),
        F("education.lesson", "강의 차시", "Lesson", "학습 차시|강의 보기|수업 콘텐츠", "lesson|class content|course unit", "동영상|자료|진도", "라이브 방송|게임 스테이지"),
        F("education.assignment", "과제", "Assignment", "숙제|제출 과제|학습 활동", "assignment|homework|course task", "마감일|첨부 파일|점수", "업무 할 일|설문"),
        F("education.assignment_submit", "과제 제출", "Submit assignment", "숙제 제출|과제 올리기|답안 제출", "submit assignment|turn in homework|upload answer", "첨부 파일|마감|제출 확인", "임시 저장|업무 파일 업로드", "submit", via="education.assignment"),
        F("education.grades", "성적", "Grades", "점수 확인|성적표|평가 결과", "grades|scores|assessment results", "과목|평균|피드백", "게임 점수|신용 점수", "sensitive"),
        F("education.certificate", "수료증", "Course certificate", "이수증|학습 수료증|과정 인증서", "course certificate|completion certificate|learning credential", "수료일|과정명|다운로드", "정부 증명서|보험 증권"),
        F("education.quiz", "퀴즈·시험", "Quiz and exam", "학습 퀴즈|시험 응시|평가 문제", "quiz|exam|take assessment", "제한 시간|문항|제출", "설문조사|게임 퀴즈", "submit"),
        F("education.playback", "강의 재생 설정", "Lesson playback settings", "강의 배속|화질|이어보기", "lesson playback|lecture speed|course video quality", "동영상|배속|진도", "음악 재생|일반 미디어 설정", "change"),
        F("education.captions", "강의 자막", "Lesson captions", "수업 자막|강의 번역|학습 캡션", "lesson captions|lecture subtitles|course translation", "언어|자막 크기|동영상", "기기 실시간 자막|영화 자막", "change"),
        F("education.offline", "오프라인 강의", "Offline lessons", "강의 다운로드|오프라인 수강|수업 저장", "offline lessons|download course|offline learning", "저장 공간|다운로드 품질|만료", "음악 다운로드|파일 오프라인", "change"),
        F("education.parent_dashboard", "학부모 학습 현황", "Parent learning dashboard", "자녀 학습 현황|학부모 페이지|아이 진도", "parent dashboard|child progress|guardian learning view", "자녀 계정|진도|성적", "교사 관리자|게임 보호자 설정", "sensitive"),
    ),
    G(
        "gaming_parental", "gaming.hub", "게임·보호자 설정", "Gaming and parental controls", "in_app",
        "게임|플레이|가족|자녀", "game|play|family|child",
        "학습 과정|업무 공간", "course|workspace", "education.hub",
        F("gaming.library", "게임 라이브러리", "Game library", "보유 게임|내 게임|설치 가능한 게임", "game library|owned games|my games", "설치|플레이 시간|구매", "앱 라이브러리|강의 목록"),
        F("gaming.cloud_saves", "게임 클라우드 저장", "Cloud game saves", "세이브 동기화|게임 저장 백업|클라우드 세이브", "cloud saves|sync game progress|save backup", "진행도|기기|동기화", "일반 파일 백업|문서 버전", "change"),
        F("gaming.crossplay", "크로스플레이", "Cross-platform play", "교차 플레이|다른 기기 사용자와 플레이|크로스 플랫폼", "crossplay|cross-platform play|play across devices", "멀티플레이|플랫폼|친구", "화면 공유|기기 동기화", "change"),
        F("gaming.voice_chat", "게임 음성 채팅", "Game voice chat", "보이스챗|게임 마이크|팀 음성", "game voice chat|team voice|gaming microphone", "마이크|팀원|음성 볼륨", "회의 음성|음성사서함", "change"),
        F("gaming.redeem_code", "게임 코드 등록", "Redeem game code", "쿠폰 코드|게임 키 등록|리딤 코드", "redeem game code|activate key|enter voucher", "코드|상품|계정", "프로모션 쿠폰|인증 코드", "submit"),
        F("gaming.purchase_history", "게임 구매 내역", "Game purchase history", "아이템 결제 내역|게임 구매 기록|콘텐츠 영수증", "game purchase history|item purchases|gaming receipts", "금액|날짜|환불", "일반 주문|구독 결제"),
        F("parental.child_account", "자녀 계정", "Child account", "아이 계정|어린이 프로필|자녀 추가", "child account|kids profile|add child", "나이|보호자|가족", "일반 보조 계정|게스트", "submit"),
        F("parental.screen_time", "자녀 사용 시간", "Child screen time", "아이 스크린 타임|게임 시간 제한|일일 한도", "child screen time|gaming time limit|daily limit", "요일|허용 시간|잠금", "내 웰빙 사용 시간|예약 시간", "change"),
        F("parental.content_rating", "연령별 콘텐츠 제한", "Content rating restriction", "연령 제한|등급 제한|부적절한 게임 차단", "content rating restriction|age filter|block mature games", "연령 등급|콘텐츠|자녀", "개인 추천|앱 등급 표시", "change"),
        F("parental.purchase_approval", "구매 승인", "Purchase approval", "결제 전 승인|자녀 구매 요청|보호자 승인", "purchase approval|ask to buy|parent approval", "구매 요청|보호자|결제", "업무 승인|앱 권한", "change"),
        F("parental.family_sharing", "가족 게임 공유", "Family game sharing", "게임 가족 공유|가족 라이브러리|구매 콘텐츠 공유", "family game sharing|family library|share purchases", "가족 구성원|라이브러리|기기", "파일 공유|사진 가족 앨범", "sensitive"),
        F("parental.communication_control", "자녀 소통 제한", "Child communication controls", "친구 추가 제한|채팅 제한|멀티플레이 제한", "child communication controls|chat restriction|friend request control", "친구|채팅|자녀", "알림 설정|연락처 차단", "change"),
    ),
    G(
        "government_tax", "government.hub", "정부·세금 서비스", "Government and tax services", "public_service",
        "민원|증명서|세금|공공 서비스", "civil service|certificate|tax|public service",
        "보험 증권|학습 수료증", "insurance policy|course certificate", "documents.hub",
        F("government.identity_login", "공공 서비스 본인인증", "Government identity verification", "공동인증 로그인|간편 인증|공공 로그인", "government sign in|digital identity|public service verification", "주민번호|인증서|휴대폰", "일반 앱 로그인|결제 인증", "sensitive"),
        F("government.certificate_search", "민원 증명서 찾기", "Find government certificate", "증명서 검색|민원 서류 찾기|발급 서비스 찾기", "find government certificate|search civil document|public record search", "발급 기관|증명서 종류|신청", "보험 서류|학교 수료증"),
        F("government.certificate_issue", "증명서 발급 신청", "Request government certificate", "민원 서류 발급|증명서 신청|전자문서 발급", "request certificate|issue public document|apply for record", "수령 방법|수수료|제출처", "증명서 조회|파일 다운로드", "submit", via="government.certificate_search"),
        F("government.certificate_wallet", "전자증명서 지갑", "Digital certificate wallet", "문서 지갑|전자문서함|발급 증명서", "digital certificate wallet|document wallet|issued records", "유효기간|제출|기관", "암호화폐 지갑|클라우드 파일", "sensitive"),
        F("government.benefits", "정부 지원금 조회", "Government benefits", "보조금 찾기|복지 혜택|지원 사업", "government benefits|find subsidies|public assistance", "자격 조건|신청 기간|가구", "쿠폰 혜택|보험 보장", "sensitive"),
        F("government.address_change", "전입 신고", "Report change of address", "주소 이전 신고|전입신고|거주지 변경", "report address change|moving registration|change residence", "이전 주소|새 주소|세대", "배달 주소|지도 집 주소", "submit"),
        F("government.fines", "과태료·범칙금 조회", "Government fines", "미납 과태료|교통 범칙금|벌금 조회", "government fines|traffic penalties|unpaid fine", "차량|납부 기한|금액", "통신 청구서|주차 요금", "sensitive"),
        F("tax.hub", "세금", "Taxes", "국세|지방세|세무", "taxes|revenue service|tax account", "신고|납부|환급", "보험료|통신비"),
        F("tax.return", "세금 신고", "File tax return", "소득 신고|연말정산 신고|세무 신고", "file tax return|income tax filing|submit tax return", "소득|공제|과세연도", "세금 문서 조회|환급 조회", "submit", via="tax.hub"),
        F("tax.payment", "세금 납부", "Pay tax", "국세 납부|지방세 결제|세금 내기", "pay tax|tax payment|pay revenue", "납부 금액|계좌|기한", "공과금 납부|보험료", "submit", via="tax.hub"),
        F("tax.refund_status", "세금 환급 상태", "Tax refund status", "환급금 조회|세금 환급 진행|국세 환급", "tax refund status|track tax refund|revenue refund", "처리 단계|환급 계좌|예정일", "쇼핑 환불|보험 환급"),
        F("tax.documents", "세금 증빙 문서", "Tax documents", "원천징수 영수증|소득 증명|세무 서류", "tax documents|income statement|withholding certificate", "과세연도|다운로드|발급", "카드 명세서|통신 청구서", "sensitive"),
        F("tax.deductions", "세액 공제 내역", "Tax deductions", "공제 항목|소득 공제|세금 감면", "tax deductions|tax credits|deductible items", "의료비|교육비|기부금", "쿠폰 할인|카드 혜택", "sensitive"),
        F("government.appointment", "공공기관 방문 예약", "Government office appointment", "민원실 예약|기관 방문 예약|상담 예약", "government appointment|office visit booking|civil service appointment", "기관|날짜|업무", "병원 예약|차량 예약", "submit"),
        F("government.petition", "민원·청원 제출", "Submit public petition", "국민신문고|민원 제기|행정 신고", "public petition|submit civil complaint|government grievance", "기관|내용|첨부", "앱 사용자 신고|고객센터 문의", "submit"),
    ),
    G(
        "smart_home", "smarthome.hub", "스마트홈", "Smart home", "physical_device",
        "집|기기|자동화|센서", "home|device|automation|sensor",
        "휴대폰 설정|게임", "phone settings|game", "android.connectivity.hub",
        F("smarthome.device_add", "스마트홈 기기 추가", "Add smart-home device", "기기 연결|새 장치|제품 등록", "add smart-home device|pair device|set up new device", "QR 코드|와이파이|블루투스", "eSIM 추가|계정 기기 목록", "submit"),
        F("smarthome.rooms", "방·공간 관리", "Rooms and spaces", "방 배정|공간 만들기|기기 위치", "rooms and spaces|assign room|device location", "거실|침실|기기", "채팅방|회의실", "change"),
        F("smarthome.automation", "스마트홈 자동화", "Smart-home automation", "루틴|자동 실행|조건 동작", "smart-home automation|routine|automatic action", "조건|시간|기기 동작", "업무 워크플로|자동 결제", "change"),
        F("smarthome.scene", "스마트홈 장면", "Smart-home scene", "스마트홈 장면|여러 기기 한번에|스마트홈 취침 장면", "smart-home scene|control multiple smart devices|home automation scene", "조명|온도|기기", "카메라 장면|게임 모드", "change"),
        F("smarthome.guest_access", "스마트홈 게스트 접근", "Smart-home guest access", "집 공유|임시 사용자|게스트 권한", "smart-home guest access|share home|temporary access", "초대|권한|만료", "파일 게스트 링크|게임 가족 공유", "submit"),
        F("smarthome.energy", "가정 에너지 사용량", "Home energy usage", "전력 사용량|에너지 대시보드|기기별 전기", "home energy usage|power dashboard|device electricity", "킬로와트시|기기|기간", "휴대폰 배터리|데이터 사용량"),
        F("smarthome.firmware", "기기 펌웨어 업데이트", "Device firmware update", "장치 업데이트|펌웨어 설치|기기 소프트웨어", "device firmware update|install firmware|device software", "버전|재시작|업데이트", "앱 업데이트|운영체제 업데이트", "submit"),
        F("smarthome.factory_reset", "스마트 기기 초기화", "Factory-reset smart device", "공장 초기화|기기 데이터 삭제|제품 재설정", "factory reset device|erase smart device|reset accessory", "연결 해제|데이터 삭제|재설정", "앱 설정 초기화|라우터 재시작", "submit"),
        F("smarthome.camera_privacy", "홈 카메라 개인정보 모드", "Home camera privacy mode", "카메라 끄기|사생활 모드|녹화 중지", "home camera privacy mode|disable camera|stop recording", "렌즈|녹화|재실", "휴대폰 카메라 권한|사진 숨김", "change"),
        F("smarthome.lock_codes", "스마트 도어록 암호", "Smart-lock access codes", "도어록 비밀번호|출입 코드|임시 암호", "smart-lock access code|door code|temporary pin", "사용자|만료|출입 기록", "SIM PIN|화면 잠금", "sensitive"),
        F("smarthome.sensor_alerts", "센서 알림", "Sensor alerts", "문 열림 알림|누수 감지|연기 경보", "sensor alerts|door alert|leak detection|smoke alarm", "센서|경보|알림 대상", "일반 앱 알림|날씨 경보", "change"),
        F("smarthome.device_remove", "스마트홈 기기 제거", "Remove smart-home device", "장치 삭제|집에서 기기 제거|연결 해제", "remove smart-home device|delete accessory|unlink device", "자동화 영향|연결 해제|초기화", "기기 전원 끄기|계정 로그아웃", "submit"),
    ),
    G(
        "photos_camera", "photos.hub", "사진·카메라", "Photos and camera", "media_library",
        "사진|동영상|카메라|앨범", "photo|video|camera|album",
        "문서 파일|지도 장소", "document file|map place", "documents.hub",
        F("photos.backup", "사진 백업", "Photo backup", "사진 자동 백업|갤러리 동기화|클라우드 사진", "photo backup|gallery sync|cloud photos", "계정|업로드 품질|와이파이", "문서 백업|연락처 동기화", "change"),
        F("photos.albums", "사진 앨범", "Photo albums", "앨범 목록|사진 모음|새 앨범", "photo albums|picture collections|new album", "사진 선택|앨범 이름|정렬", "음악 앨범|저장 장소 목록"),
        F("photos.shared_album", "공유 앨범", "Shared photo album", "사진 앨범 공유|가족 앨범|공동 앨범", "shared photo album|family album|collaborative album", "초대|공동 작업|링크", "파일 공유|게임 가족 공유", "submit"),
        F("photos.hidden", "숨긴 사진", "Hidden photos", "숨김 앨범|사진 숨기기|비공개 사진", "hidden photos|hide pictures|hidden album", "잠금|숨김 해제|앨범", "휴지통|보관처리", "sensitive"),
        F("photos.locked_folder", "잠긴 사진 폴더", "Locked photo folder", "보안 폴더|잠긴 폴더|인증 사진함", "locked photo folder|secure folder|private photo vault", "생체 인증|기기 저장|백업", "숨김 앨범|앱 잠금", "sensitive"),
        F("photos.memories", "사진 추억", "Photo memories", "지난 오늘|추억 모음|자동 하이라이트", "photo memories|on this day|automatic highlights", "날짜|사람|장소", "활동 기록|캘린더 일정"),
        F("photos.face_grouping", "얼굴별 사진 묶기", "Face grouping", "사람별 그룹|얼굴 인식|인물 분류", "face grouping|group similar faces|people recognition", "사람 이름|얼굴 모델|검색", "연락처 병합|사진 정렬", "sensitive"),
        F("photos.duplicates", "중복 사진 정리", "Clean duplicate photos", "중복 이미지|비슷한 사진|중복 사진 정리", "duplicate photos|similar pictures|clean duplicate photos", "용량 절약|선택|삭제", "연락처 중복|파일 버전", "change"),
        F("camera.resolution", "카메라 해상도", "Camera resolution", "사진 크기|동영상 화질|촬영 해상도", "camera resolution|photo size|video resolution", "메가픽셀|4K|프레임", "재생 화질|업로드 품질", "change"),
        F("camera.timer", "카메라 타이머", "Camera timer", "촬영 타이머|셀프 타이머|지연 촬영", "camera timer|self timer|delayed shutter", "3초|10초|셔터", "수면 타이머|일정 알림", "change"),
        F("camera.geotagging", "사진 위치 태그", "Photo geotagging", "위치 태그|촬영 장소 저장|사진 GPS", "photo geotagging|save location|camera gps", "위치 권한|메타데이터|사진", "지도 위치 공유|위치 기록", "change"),
        F("camera.raw", "RAW 촬영", "RAW capture", "원본 사진|RAW 저장|전문가 사진 형식", "raw capture|save raw|professional photo format", "DNG|저장 공간|후보정", "백업 원본 화질|문서 스캔", "change"),
        F("camera.qr_scan", "QR 코드 스캔", "Scan QR code", "큐알 인식|코드 스캔|카메라 QR", "scan qr code|qr scanner|camera code scan", "링크|코드|카메라", "문서 스캔|바코드 상품 검색"),
    ),
    G(
        "audio", "audio.hub", "음악·팟캐스트", "Music and podcasts", "media_playback",
        "음악|오디오|팟캐스트|재생", "music|audio|podcast|playback",
        "강의 영상|게임 음성", "lesson video|game voice", "education.hub",
        F("music.queue", "음악 재생 대기열", "Music queue", "재생 목록 순서|다음 곡|대기열", "music queue|up next|playback queue", "현재 곡|순서|셔플", "다운로드 목록|팟캐스트 새 에피소드"),
        F("music.playlist", "음악 플레이리스트", "Music playlist", "재생목록|노래 모음|새 플레이리스트", "music playlist|song collection|new playlist", "곡 추가|공개 범위|정렬", "사진 앨범|저장 장소 목록"),
        F("music.offline", "오프라인 음악", "Offline music", "노래 다운로드|오프라인 재생|저장한 음악", "offline music|download songs|saved music", "다운로드 품질|저장 공간|와이파이", "강의 다운로드|파일 오프라인", "change"),
        F("music.equalizer", "이퀄라이저", "Equalizer", "음향 효과|음악 EQ|저음 고음", "equalizer|music eq|audio effects|bass and treble", "프리셋|주파수|헤드폰", "음성 볼륨|마이크 설정", "change"),
        F("music.quality", "음악 음질", "Music audio quality", "스트리밍 음질|고음질|데이터 절약 음질", "music quality|streaming audio quality|lossless", "와이파이|모바일 데이터|다운로드", "영상 화질|녹음 품질", "change"),
        F("music.lyrics", "노래 가사", "Song lyrics", "가사 보기|동기화 가사|노래말", "song lyrics|view lyrics|synchronized lyrics", "현재 곡|언어|시간", "자막|문서 텍스트"),
        F("audio.sleep_timer", "오디오 수면 타이머", "Audio sleep timer", "음악 자동 종료|취침 타이머|재생 끄기", "audio sleep timer|stop playback timer|bedtime timer", "분|곡 종료|재생", "카메라 타이머|스크린 타임", "change"),
        F("podcast.subscriptions", "팟캐스트 구독", "Podcast subscriptions", "팔로우한 팟캐스트|프로그램 구독|쇼 목록", "podcast subscriptions|followed shows|podcast library", "새 에피소드|알림|프로그램", "유료 구독|콘텐츠 채널"),
        F("podcast.episodes", "팟캐스트 에피소드", "Podcast episodes", "회차 목록|새 에피소드|팟캐스트 재생", "podcast episodes|show episodes|new episodes", "재생 시간|다운로드|설명", "강의 차시|음성사서함"),
        F("podcast.speed", "팟캐스트 재생 속도", "Podcast playback speed", "팟캐스트 배속|말하기 속도|재생 배율", "podcast speed|playback rate|speaking speed", "0.5배|1.5배|2배", "강의 배속|영상 속도", "change"),
        F("podcast.trim_silence", "팟캐스트 무음 건너뛰기", "Trim podcast silence", "무음 제거|침묵 건너뛰기|공백 줄이기", "trim silence|skip silence|shorten pauses", "에피소드|재생 시간|음성", "광고 건너뛰기|노래 크로스페이드", "change"),
        F("podcast.auto_download", "팟캐스트 자동 다운로드", "Podcast auto-download", "새 회차 자동 저장|에피소드 자동 다운로드|오프라인 자동", "podcast auto-download|download new episodes|automatic episode download", "저장 개수|와이파이|삭제 정책", "메일 자동 전달|사진 백업", "change"),
        F("podcast.notifications", "팟캐스트 새 회차 알림", "Podcast episode notifications", "새 에피소드 알림|프로그램 알림|팟캐스트 푸시", "podcast notifications|new episode alerts|show notifications", "프로그램별|새 회차|푸시", "일정 알림|메일 알림", "change"),
    ),
    G(
        "work_collaboration", "work.hub", "업무 협업", "Work collaboration", "workspace",
        "업무 공간|팀|회의|프로젝트", "workspace|team|meeting|project",
        "개인 학습|게임 친구", "personal learning|game friends", "documents.hub",
        F("work.workspace_switch", "업무 공간 전환", "Switch workspace", "워크스페이스 바꾸기|조직 전환|팀 공간 선택", "switch workspace|change organization|select team space", "조직 이름|계정|팀", "계정 전환|채팅방 전환"),
        F("work.channels", "업무 채널", "Work channels", "팀 채널|대화 채널|프로젝트 방", "work channels|team channels|project rooms", "멤버|메시지|고정", "방송 채널|게임 음성"),
        F("work.meeting_create", "회의 만들기", "Create meeting", "새 회의|화상회의 예약|미팅 생성", "create meeting|schedule video call|new meeting", "참석자|시간|링크", "캘린더 개인 일정|정부 방문 예약", "submit"),
        F("work.meeting_join", "회의 참가", "Join meeting", "미팅 들어가기|회의 코드 입장|통화 참가", "join meeting|enter meeting|join call", "회의 코드|마이크|카메라", "게임 로비|라이브 방송", "change"),
        F("work.screen_share", "화면 공유", "Share screen", "내 화면 보여주기|프레젠테이션 공유|화면 발표", "share screen|present screen|screen presentation", "창 선택|전체 화면|참석자", "파일 공유|위치 공유", "submit"),
        F("work.recording", "회의 녹화", "Meeting recording", "녹화 시작|회의 기록 영상|회의 통화 녹화", "meeting recording|record meeting call|start meeting recording", "참석자 동의|저장 위치|녹화 표시", "카메라 촬영|음성 메모", "submit"),
        F("work.transcript", "회의 대화 기록", "Meeting transcript", "회의 자막 기록|전사본|발언 텍스트", "meeting transcript|call transcription|meeting text", "화자|시간|다운로드", "영상 자막|음성사서함", "sensitive"),
        F("work.tasks", "업무 할 일", "Work tasks", "작업 목록|프로젝트 할 일|담당 업무", "work tasks|project tasks|assigned work", "담당자|기한|상태", "학습 과제|개인 알림"),
        F("work.task_create", "업무 만들기", "Create work task", "새 작업|할 일 추가|프로젝트 태스크", "create work task|add task|new project task", "제목|담당자|기한", "캘린더 일정|학습 과제", "submit", via="work.tasks"),
        F("work.task_assign", "업무 담당자 지정", "Assign work task", "담당자 배정|작업 할당|책임자 지정", "assign work task|set assignee|delegate task", "팀원|작업|알림", "파일 권한|회의 초대", "submit", via="work.tasks"),
        F("work.task_due", "업무 마감일", "Task due date", "기한 변경|마감일 설정|작업 일정", "task due date|set deadline|change due date", "날짜|시간|알림", "캘린더 시간대|구독 갱신일", "change", via="work.tasks"),
        F("work.workflow", "업무 자동화", "Workflow automation", "워크플로|자동 규칙|조건부 작업", "workflow automation|automation rule|conditional task", "트리거|동작|조건", "스마트홈 루틴|메일 필터", "change"),
        F("work.integrations", "업무 앱 연동", "Workspace integrations", "외부 앱 연결|봇 추가|서비스 통합", "workspace integrations|connect app|add bot", "권한|조직|데이터 접근", "연결 계정|스마트 기기", "submit"),
        F("work.members", "조직 멤버 관리", "Workspace members", "팀원 관리|사용자 초대|조직 구성원", "workspace members|team members|invite users", "역할|이메일|활성 상태", "연락처|가족 구성원", "sensitive"),
        F("work.roles", "조직 역할·권한", "Workspace roles and permissions", "관리자 권한|멤버 역할|접근 수준", "workspace roles|admin permissions|member access", "소유자|관리자|게스트", "문서 공유 권한|앱 권한", "submit"),
        F("work.audit_log", "업무 감사 기록", "Workspace audit log", "관리자 활동 기록|보안 로그|조직 변경 이력", "workspace audit log|admin activity|security log", "사용자|시간|동작", "개인 활동 기록|로그인 기록", "sensitive"),
    ),
    G(
        "finance_long_tail", "finance.longtail.hub", "대출·투자·청구서", "Loans, investing, and bills", "financial",
        "대출|투자|청구서|금융", "loan|investment|bill|finance",
        "쇼핑 주문|보험 계약", "shopping order|insurance policy", "government.hub",
        F("loan.eligibility", "대출 자격 조회", "Loan eligibility", "대출 가능 여부|한도 조회|사전 심사", "loan eligibility|borrowing limit|prequalification", "소득|신용|예상 한도", "신용카드 한도|보험 대출", "sensitive"),
        F("loan.rate_quote", "대출 금리 견적", "Loan rate quote", "예상 이자율|대출 금리 비교|상환액 계산", "loan rate quote|estimated interest|loan payment estimate", "연이율|기간|원금", "예금 금리|환율"),
        F("loan.application", "대출 신청", "Submit loan application", "대출 접수|대출 신청서|자금 신청", "loan application|apply for loan|submit borrowing request", "금액|기간|소득 증빙", "한도 조회|상환 일정", "submit"),
        F("loan.repayment_schedule", "대출 상환 일정", "Loan repayment schedule", "납입 계획|원리금 일정|남은 회차", "loan repayment schedule|payment schedule|remaining installments", "원금|이자|납부일", "구독 결제일|정기 송금"),
        F("loan.early_repayment", "대출 중도상환", "Early loan repayment", "조기 상환|대출 미리 갚기|중도상환 신청", "early loan repayment|pay off loan|prepay loan", "상환 금액|수수료|계좌", "일반 이체|월 납부", "submit"),
        F("loan.refinance", "대출 갈아타기", "Loan refinance", "대환 대출|금리 갈아타기|대출 이전", "loan refinance|replace loan|switch lender", "기존 대출|새 금리|수수료", "요금제 변경|계좌 이전", "submit"),
        F("investment.portfolio", "투자 포트폴리오", "Investment portfolio", "보유 자산|투자 현황|수익률", "investment portfolio|holdings|investment performance", "평가 금액|수익률|종목", "은행 계좌|게임 아이템", "sensitive"),
        F("investment.order", "투자 주문", "Place investment order", "주식 주문|매수 매도|펀드 거래", "place investment order|buy stock|sell investment", "수량|가격|주문 유형", "상품 주문|환전 견적", "submit"),
        F("investment.recurring", "정기 투자", "Recurring investment", "자동 투자|매달 매수|적립식 투자", "recurring investment|automatic investing|scheduled purchase", "금액|주기|종목", "정기 송금|구독 결제", "change"),
        F("investment.dividends", "배당 내역", "Dividend history", "배당금|분배금|배당 지급", "dividend history|distribution payments|dividend income", "지급일|세금|종목", "이자 내역|환불 내역", "sensitive"),
        F("investment.tax_documents", "투자 세금 문서", "Investment tax documents", "투자 소득 증명|거래 세금 서류|연간 투자 보고서", "investment tax documents|capital gains statement|annual tax report", "과세연도|매매 손익|다운로드", "정부 세금 신고|은행 명세서", "sensitive"),
        F("investment.risk_profile", "투자 성향", "Investment risk profile", "위험 성향|투자자 설문|적합성 평가", "investment risk profile|investor questionnaire|suitability assessment", "목표|기간|손실 감내", "개인 추천 설정|건강 설문", "sensitive"),
        F("bills.list", "청구서 목록", "Bills", "납부할 요금|공과금 목록|미납 청구서", "bills|amounts due|unpaid invoices", "납부 기한|금액|기관", "쇼핑 영수증|세금 문서"),
        F("bills.payment", "청구서 납부", "Pay bill", "공과금 내기|요금 납부|청구 금액 결제", "pay bill|bill payment|settle invoice", "납부 금액|계좌|기한", "세금 납부|상품 결제", "submit", via="bills.list"),
        F("bills.reminder", "청구서 납부 알림", "Bill due reminder", "납부일 알림|공과금 리마인더|연체 방지", "bill due reminder|payment alert|invoice reminder", "기한|알림 시간|청구처", "일정 알림|약 복용 알림", "change"),
        F("bills.split", "청구 금액 나누기", "Split bill", "더치페이|비용 분담|청구서 나눔", "split bill|share expense|divide payment", "사람|금액|요청", "결제 수단 분할|할부", "submit"),
        F("bills.dispute", "청구 금액 이의 제기", "Dispute bill", "요금 오류 신고|청구서 이의|잘못된 금액", "dispute bill|challenge charge|billing error", "청구 항목|증빙|제출", "카드 부정 거래|환불 요청", "submit"),
        F("finance.credit_score", "신용 점수", "Credit score", "신용 등급|신용평점|신용 보고서", "credit score|credit rating|credit report", "변동 요인|조회일|기관", "게임 점수|학업 성적", "sensitive"),
    ),
    G(
        "safety", "safety.hub", "안전·신고·차단", "Safety, reporting, and blocking", "safety",
        "안전|신고|차단|긴급", "safety|report|block|emergency",
        "도움말 문서|알림 설정", "help article|notification setting", "wellbeing.hub",
        F("safety.sos", "긴급 SOS", "Emergency SOS", "긴급 구조 요청|비상 호출|SOS 실행", "emergency sos|call for help|urgent assistance", "긴급 번호|현재 위치|연락처", "일반 고객센터|안전 센터 안내", "submit"),
        F("safety.trusted_contacts", "안전 연락처", "Trusted safety contacts", "보호자 연락처|안심 친구|긴급 공유 대상", "trusted contacts|safety contacts|emergency sharing people", "위치|알림|연락처", "일반 즐겨찾기|업무 멤버", "sensitive"),
        F("safety.check_in", "안전 확인", "Safety check-in", "안전 체크|도착 확인|응답 없으면 알림", "safety check-in|arrival check|notify if no response", "종료 시간|연락처|위치", "일정 참석 응답|업무 출석", "submit"),
        F("safety.report_content", "콘텐츠 신고", "Report content", "게시물 신고|영상 신고|부적절한 콘텐츠", "report content|report post|flag video", "신고 사유|콘텐츠|제출", "관심 없음|댓글 삭제", "submit"),
        F("safety.report_user", "사용자 신고", "Report user", "계정 신고|사람 신고|악성 사용자", "report user|report account|flag person", "사용자|신고 사유|차단", "콘텐츠 신고|고객센터", "submit"),
        F("safety.block_user", "사용자 차단", "Block user", "계정 차단|이 사람 막기|연락 차단", "block user|block account|prevent contact", "메시지|프로필|해제", "전화번호 차단|콘텐츠 숨김", "submit"),
        F("safety.mute_user", "사용자 숨김", "Mute user", "뮤트|게시물 안 보기|알림 없이 숨기기", "mute user|hide posts|silence account", "피드|알림|해제", "완전 차단|대화 알림 끄기", "change"),
        F("safety.report_spam", "스팸 신고", "Report spam", "광고 메시지 신고|스팸 계정|원치 않는 연락", "report spam|flag junk|report unsolicited message", "메시지|발신자|차단", "메일 스팸함|마케팅 수신 거부", "submit"),
        F("safety.report_phishing", "피싱 신고", "Report phishing", "사기 링크 신고|피싱 메시지|가짜 사이트", "report phishing|scam link|fraudulent message", "링크|발신자|보안", "일반 스팸|지도 오류", "submit"),
        F("safety.report_fraud", "금융 사기 신고", "Report financial fraud", "부정 거래|도용 결제|금융 사기", "report financial fraud|fraudulent transaction|unauthorized charge", "거래 선택|카드 잠금|증빙", "청구서 이의|쇼핑 환불", "submit"),
        F("safety.harassment_controls", "괴롭힘 방지 설정", "Harassment controls", "모욕 필터|유해 댓글 차단|괴롭힘 보호", "harassment controls|abuse filter|toxic comment protection", "키워드|댓글|메시지", "콘텐츠 등급|일반 스팸 필터", "change"),
        F("safety.recovery_resources", "위기 지원 정보", "Crisis support resources", "위기 상담|긴급 지원 기관|안전 도움처", "crisis support|emergency resources|safety helplines", "전화|채팅|지역 기관", "일반 FAQ|보험 고객센터", "sensitive"),
    ),
    G(
        "wellbeing_health", "wellbeing.hub", "웰빙·건강", "Wellbeing and health", "health_data",
        "건강|웰빙|수면|복약", "health|wellbeing|sleep|medication",
        "게임 시간|업무 상태", "game time|work status", "safety.hub",
        F("wellbeing.screen_time", "내 화면 사용 시간", "Personal screen time", "앱 사용 시간|디지털 웰빙|휴대폰 사용량", "personal screen time|digital wellbeing|phone usage", "앱별 시간|잠금 해제|알림 수", "자녀 사용 시간|업무 근무 시간", "sensitive"),
        F("wellbeing.focus_mode", "집중 모드", "Focus mode", "방해 금지 앱|집중 시간|앱 일시중지", "focus mode|pause distracting apps|focus session", "앱 선택|일정|알림", "알림 방해 금지|업무 상태", "change"),
        F("wellbeing.bedtime", "취침 모드", "Bedtime mode", "수면 시간|취침 일정|잠잘 준비", "bedtime mode|sleep schedule|wind down", "취침|기상|화면 흑백", "오디오 수면 타이머|알람" , "change"),
        F("wellbeing.mindfulness", "마음챙김", "Mindfulness", "명상|호흡 운동|마음 안정", "mindfulness|meditation|breathing exercise", "시간|세션|연속 기록", "운동 기록|오디오 재생"),
        F("health.medications", "복약 목록", "Medications", "먹는 약|처방약 목록|약 관리", "medications|medicine list|prescriptions", "약 이름|용량|처방", "쇼핑 약 주문|보험 청구", "sensitive"),
        F("health.medication_reminder", "복약 알림", "Medication reminder", "약 먹을 시간|복용 알림|투약 일정", "medication reminder|dose alert|medicine schedule", "시간|용량|반복", "청구서 알림|일정 알림", "change"),
        F("health.log_dose", "복약 기록", "Log medication dose", "약 먹음 기록|복용 완료|투약 체크", "log medication dose|mark medicine taken|record dose", "복용 시각|건너뜀|용량", "습관 체크|과제 제출", "submit"),
        F("health.share_records", "건강 기록 공유", "Share health records", "의료 데이터 보내기|의사와 기록 공유|건강 정보 내보내기", "share health records|send medical data|share with doctor", "공유 대상|기간|기록 종류", "운동 성과 공유|문서 링크", "submit"),
        F("health.symptoms", "증상 기록", "Symptom tracking", "아픈 증상|몸 상태 기록|증상 일지", "symptom tracking|health symptoms|condition diary", "강도|시간|메모", "보험 사고 신고|고객 문의", "sensitive"),
        F("health.lab_results", "검사 결과", "Lab results", "혈액검사 결과|검진 수치|의료 검사", "lab results|test results|medical measurements", "검사일|수치|의료기관", "학업 시험 결과|기기 진단", "sensitive"),
        F("health.vaccinations", "예방접종 기록", "Vaccination records", "백신 이력|접종 증명|예방주사", "vaccination records|immunization history|vaccine certificate", "접종일|백신명|기관", "여행 백신 안내|정부 일반 증명서", "sensitive"),
        F("health.cycle_tracking", "생리 주기 기록", "Menstrual cycle tracking", "월경 기록|주기 예측|배란 추적", "menstrual cycle tracking|period log|ovulation tracking", "날짜|증상|예측", "캘린더 일정|운동 주기", "sensitive"),
        F("health.emergency_profile", "응급 의료 정보", "Emergency medical profile", "의료 ID|잠금 화면 건강 정보|응급 정보", "emergency medical profile|medical id|lock-screen health info", "혈액형|알레르기|긴급 연락처", "일반 프로필|연락처 카드", "sensitive"),
    ),
    G(
        "android_extended", "android.connectivity.hub", "Android 확장 설정", "Extended Android settings", "android_system",
        "Android|휴대전화 설정|시스템", "android|phone settings|system",
        "앱 내부 설정|웹 계정", "in-app settings|web account", "government.hub",
        F("android.notification_history", "알림 기록", "Notification history", "지난 알림|알림 내역|최근 알림 기록", "notification history|past notifications|recent alerts", "최근 24시간|앱별 알림|기록", "브라우저 기록|메시지 보관함", "sensitive"),
        F("android.privacy_dashboard", "개인정보 보호 대시보드", "Privacy dashboard", "권한 사용 기록|개인정보 대시보드|최근 권한 접근", "privacy dashboard|permission usage history|recent permission access", "카메라|마이크|위치|시간", "앱 개인정보 정책|계정 공개 범위", "sensitive"),
        F("android.restricted_settings", "제한된 설정 허용", "Allow restricted settings", "제한된 설정|보안상 제한|제한 설정 허용", "allow restricted settings|restricted settings|security restriction", "앱 정보|추가 확인|보안 위험", "자녀 콘텐츠 제한|일반 접근성 설정", "submit"),
        F("android.wifi", "Wi-Fi 설정", "Wi-Fi settings", "와이파이|무선 네트워크|인터넷 연결", "wi-fi settings|wireless network|internet connection", "네트워크 이름|신호|비밀번호", "모바일 데이터|블루투스"),
        F("android.bluetooth", "Bluetooth 설정", "Bluetooth settings", "블루투스|주변 기기|무선 액세서리", "bluetooth settings|nearby devices|wireless accessories", "페어링|기기 이름|연결", "와이파이|스마트홈 기기 목록"),
        F("android.hotspot", "모바일 핫스팟", "Mobile hotspot", "테더링|인터넷 공유|휴대폰 핫스팟", "mobile hotspot|tethering|share internet", "네트워크 이름|비밀번호|연결 기기", "위치 공유|파일 공유", "change"),
        F("android.vpn", "VPN 설정", "VPN settings", "가상 사설망|VPN 연결|보안 네트워크", "vpn settings|virtual private network|secure connection", "VPN 프로필|연결 상태|항상 사용", "와이파이 프록시|시크릿 모드", "change"),
        F("android.private_dns", "비공개 DNS", "Private DNS", "프라이빗 DNS|DNS 제공업체|보안 DNS", "private dns|dns provider|secure dns", "호스트 이름|자동|사용 안 함", "VPN|브라우저 DNS", "change"),
    ),
)


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _risk_cues(mode: str, name_ko: str, name_en: str) -> dict[str, list[str]]:
    if mode == "submit":
        return {
            "final_action": [name_ko, name_en, "제출", "확인", "submit", "confirm"],
            "consequence": ["외부 상태가 변경됨", "사용자 최종 클릭 필요", "changes external state", "final user click required"],
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


def _build_root(group: GroupSeed) -> dict[str, object]:
    return {
        "function_id": group.root_id,
        "domain": group.domain,
        "scope": group.scope,
        "node_kind": "hub",
        "stop_policy": "continue",
        "name_ko": group.root_ko,
        "name_en": group.root_en,
        "description": f"{group.root_ko} 기능을 찾기 위한 범용 허브 화면이다. General hub for {group.root_en.lower()} functions.",
        "risk_level": "low",
        "automation_policy": "safe_navigation",
        "terminal": False,
        "state_changing": False,
        "legacy_tags": [group.domain, "v3_long_tail", "hub"],
        "role_hints": ["button", "menuitem", "tab", "heading"],
        "aliases": {
            "ko-KR": _dedupe([group.root_ko, *group.ko_context, f"{group.root_ko} 메뉴", f"{group.root_ko} 관리"]),
            "en-US": _dedupe([group.root_en, *group.en_context, f"{group.root_en} menu", f"manage {group.root_en.lower()}"]),
        },
        "positive_context": _dedupe([*group.ko_context, *group.en_context, "전체 메뉴", "main menu"]),
        "negative_context": _dedupe([*group.negative_ko, *group.negative_en]),
        "state_cues": {
            "visible": [group.root_ko, group.root_en],
            "loading": ["불러오는 중", "loading"],
        },
        "risk_cues": _risk_cues("view", group.root_ko, group.root_en),
    }


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    metadata = MODE_METADATA[seed.mode]
    aliases_ko = _dedupe([seed.name_ko, *seed.ko_aliases, f"{seed.name_ko} 설정", f"{seed.name_ko} 관리"])
    aliases_en = _dedupe([seed.name_en, *seed.en_aliases, f"{seed.name_en} settings", f"manage {seed.name_en.lower()}"])
    return {
        "function_id": seed.function_id,
        "domain": group.domain,
        "scope": group.scope,
        "node_kind": metadata["node_kind"],
        "stop_policy": metadata["stop_policy"],
        "name_ko": seed.name_ko,
        "name_en": seed.name_en,
        "description": (
            f"{seed.name_ko} 메뉴 또는 최종 사용자 동작 경계를 식별한다. "
            f"Identifies the {seed.name_en.lower()} destination or user-owned action boundary."
        ),
        "risk_level": metadata["risk_level"],
        "automation_policy": metadata["automation_policy"],
        "terminal": True,
        "state_changing": metadata["state_changing"],
        "legacy_tags": [group.domain, "v3_long_tail", seed.function_id.rsplit(".", 1)[-1]],
        "role_hints": ["button", "menuitem", "tab", "text"],
        "aliases": {"ko-KR": aliases_ko, "en-US": aliases_en},
        "positive_context": _dedupe([*seed.positive, *group.ko_context[:2], *group.en_context[:2]]),
        "negative_context": _dedupe([*seed.negative, *group.negative_ko[:2], *group.negative_en[:2]]),
        "state_cues": {
            "visible": [seed.name_ko, seed.name_en, aliases_ko[1], aliases_en[1]],
            "unavailable": ["사용할 수 없음", "지원되지 않음", "unavailable", "not supported"],
        },
        "risk_cues": _risk_cues(seed.mode, seed.name_ko, seed.name_en),
    }


def _route(group: GroupSeed, seed: FeatureSeed) -> list[dict[str, object]]:
    ordered = [group.root_id, *seed.via, seed.function_id]
    ordered = list(dict.fromkeys(ordered))
    if len(ordered) == 1:
        return [{"function_id": ordered[0], "weight": 1.0}]
    return [
        {"function_id": function_id, "weight": round(0.28 + index * (0.72 / (len(ordered) - 1)), 3)}
        for index, function_id in enumerate(ordered)
    ]


_EXTRA_CONTEXT_GOAL_RULES: dict[str, list[dict[str, object]]] = {
    "cloud.link_share": [
        {"all_of": ["파일", "링크", "공유"], "score": 0.999},
        {"all_of": ["share", "file", "link"], "score": 0.999},
    ],
    "tax.refund_status": [
        {"all_of": ["세금", "환급", "상태"], "score": 0.9995},
        {"all_of": ["tax", "refund", "status"], "score": 0.9995},
    ],
}


# Natural requests rarely repeat the label shown in a settings screen.  These
# compact conjunctions bridge common paraphrases to the same reusable
# function concept.  Each entry deliberately uses only two to five independent
# semantic cues (never a complete benchmark utterance, screen title, app name,
# or case identifier).  Korean and English alternatives are kept together so
# the ontology remains useful outside the fixture that first exposed a gap.
_V3_PARAPHRASE_RULE_TERMS: dict[str, tuple[str, ...]] = {
    # Email and calendar
    "email.archive": (
        "받은편지함|지우지 않고|치우고",
        "remove|inbox|without deleting",
    ),
    "email.swipe_actions": (
        "좌우|밀기|메시지",
        "left|right|gesture|message",
    ),
    "email.signature": (
        "편지 끝|연락처|자동으로",
        "message ending|contact details|automatically",
        "signature|settings",
    ),
    "email.vacation_responder": (
        "부재중|자동|회신",
        "away|replying automatically|return",
    ),
    "email.sync": (
        "새 편지|여러 기기|늦게",
        "new mail|multiple devices|delayed",
    ),
    "email.labels": (
        "메시지|사용자 지정|표시|정리",
        "messages|custom marker|organize",
    ),
    "email.filters": (
        "특정 발신자|조건|자동 분류",
        "sender|conditions|automatically sort",
    ),
    "email.scheduled": (
        "메시지|나중에|보내기",
        "message|hold|tomorrow",
    ),
    "email.spam": (
        "수상한 편지|잘못 분류|확인",
        "suspicious mail|misclassified|review",
    ),
    "email.forwarding": (
        "수신 편지|다른 편지함|전달",
        "incoming message|another mailbox|route",
    ),
    "email.send": (
        "받는 사람|본문|전송 직전",
        "recipient|message body|before sending",
    ),
    "calendar.event.create": (
        "새 일정|참석자|저장 전",
        "new appointment|attendees|saving",
    ),
    "calendar.event.edit": (
        "기존 일정|시간|장소|고치는",
        "existing event|time|location|edit",
    ),
    "calendar.event.delete": (
        "일정|삭제|최종 경고",
        "final warning|removing|appointment",
    ),
    "calendar.rsvp": (
        "초대받은 회의|갈지|선택",
        "meeting invitation|attend|respond",
    ),
    "calendar.notifications": (
        "캘린더|미리|알림",
        "calendar|how far ahead|reminds",
    ),
    "calendar.shared_calendars": (
        "동료|공유한 달력|함께",
        "colleague|shared calendar|alongside",
    ),
    "calendar.timezone": (
        "여행 일정|현지|시간대",
        "travel events|local time zone|display",
    ),
    "calendar.working_hours": (
        "업무 가능 시간|쉬는 요일|캘린더",
        "working hours|days off|calendar",
    ),
    "calendar.search": (
        "예전 일정|참석자|찾기",
        "old appointment|attendee|find",
    ),
    "calendar.export": (
        "전체 일정|다른 서비스|파일",
        "entire calendar|another service|file",
    ),
    # Contacts and maps
    "contacts.create": (
        "빈 연락처|새 전화번호|추가",
        "blank person card|new phone number|add",
    ),
    "contacts.edit": (
        "저장된 사람|주소|번호|바로잡고",
        "saved contact|address|number|correct",
    ),
    "contacts.import": (
        "기기 파일|주소록|가져오기",
        "device file|address book|import",
    ),
    "contacts.export": (
        "주소록 사본|파일|내보낼",
        "address book copy|file|export",
    ),
    "contacts.merge_duplicates": (
        "같은 사람|반복 항목|합치기",
        "repeated entries|same person|combine",
    ),
    "contacts.blocked_numbers": (
        "번호 목록|실수로 막",
        "blocked numbers|list|mistakenly",
    ),
    "contacts.emergency": (
        "응급 상황|연락할 사람|확인",
        "emergency|people|contacted",
    ),
    "contacts.sync": (
        "휴대전화 주소록|사람 목록|맞춰지는",
        "phone contacts|service list|synchronize",
    ),
    "maps.directions": (
        "현재 위치|목적지|경로|안내 전",
        "route|destination|without starting guidance",
    ),
    "maps.navigation": (
        "현재 경로|실제 안내|전환",
        "current route|start guidance|button",
    ),
    "maps.offline_maps": (
        "지역|휴대전화|신호 없음|저장",
        "area|phone|no signal|save",
    ),
    "maps.saved_lists": (
        "나중에 갈 장소|여행별|묶음",
        "places to visit|trip lists|group",
    ),
    "maps.location_sharing": (
        "가족|내 위치|제한된 시간",
        "family member|where i am|limited time",
        "실시간|위치|공유",
        "maps|location|sharing",
    ),
    "maps.trip_progress_sharing": (
        "이동 중|도착 예상 시간|상대에게",
        "trip progress|estimated arrival|share",
    ),
    "maps.incognito": (
        "장소 탐색|검색 기록|남기지",
        "browse places|without adding|map activity",
    ),
    "maps.location_history": (
        "예전에 방문한|위치 기록|날짜별",
        "visited locations|history|by date",
    ),
    "maps.avoid_options": (
        "경로|유료 도로|페리|피하기",
        "avoid|toll roads|ferries|route",
    ),
    "maps.home_work": (
        "집|회사|저장된 주소",
        "home|work|saved addresses",
    ),
    "maps.report_issue": (
        "장소 위치|잘못|수정 제출",
        "place|wrong side|correction",
    ),
    # Mobility, delivery, and telecom
    "mobility.ride_request": (
        "목적지|탈 차량|부르는|최종 확인",
        "destination|request ride|final confirmation",
    ),
    "mobility.fare_estimate": (
        "차량|예상 비용|선택 전",
        "likely cost|ride|choose",
    ),
    "mobility.trip_history": (
        "이용한 차량|결제 내역|시간순",
        "past rides|payment history|chronological",
    ),
    "mobility.safety_center": (
        "차량 이동 중|응급|도구",
        "emergency tools|ride|in progress",
    ),
    "mobility.lost_item": (
        "차에 두고 내린|물건|기사",
        "left in car|item|driver",
    ),
    "delivery.order_tracking": (
        "배달원|지도|추적",
        "track|courier|map",
    ),
    "delivery.address": (
        "배달받을|기본 장소|아파트",
        "delivery|default place|new address",
    ),
    "delivery.instructions": (
        "배달원|메모|문 옆",
        "note|courier|side door",
    ),
    "delivery.contact_courier": (
        "배달원|전화|메시지",
        "courier|call|message",
    ),
    "delivery.tip": (
        "배달원|추가 금액|결제 승인",
        "extra amount|courier|payment",
    ),
    "delivery.issue": (
        "누락된 음식|문제|신고",
        "missing food|report|resolution",
    ),
    "delivery.reorder": (
        "지난번 음식|다시 주문|결제 전",
        "same meal|last time|before checkout",
    ),
    "telecom.data_plan": (
        "남은 데이터|통신 상품|조건",
        "remaining data|mobile plan|conditions",
    ),
    "telecom.usage": (
        "통화|문자|모바일 데이터|사용",
        "voice|text|mobile data|used",
    ),
    "telecom.bill": (
        "이번 달|휴대전화 요금|항목별 청구서",
        "monthly phone bill|itemized|charges",
    ),
    "telecom.autopay": (
        "통신 요금|자동 납부|관리",
        "automatic payment|carrier bill|manage",
        "통신비|자동이체",
    ),
    "esim.install": (
        "새 휴대전화|디지털 심|내려받기",
        "new phone|digital sim|download",
    ),
    "esim.transfer": (
        "디지털 심|다른 휴대전화|옮기기",
        "digital sim|another phone|move",
    ),
    "esim.remove": (
        "디지털 심|제거|경고",
        "digital sim|remove|warning",
    ),
    "roaming.settings": (
        "해외|셀룰러 데이터|작동",
        "cellular data|abroad|control",
    ),
    "roaming.pass": (
        "해외|통신 패스",
        "travel|data pass|allowance",
    ),
    "roaming.data_limit": (
        "로밍 데이터|한도|여행 예산",
        "roaming data|ceiling|travel budget",
    ),
    "sim.pin": (
        "유심|잠금 번호|설정",
        "sim|lock number|set",
    ),
    "telecom.voicemail": (
        "전화 못 받은|남긴 메시지|듣기",
        "callers left|messages|could not answer",
    ),
    # Documents and cloud storage
    "documents.create": (
        "빈 문서|제목|내용|준비",
        "blank document|title|content|prepare",
    ),
    "documents.scan": (
        "종이 영수증|카메라|디지털 문서",
        "paper receipt|camera|digital document",
    ),
    "documents.export_pdf": (
        "작성한 문서|읽기 전용|파일 형식",
        "written document|read-only|file format",
    ),
    "documents.version_history": (
        "이전 버전|누가 변경|문서",
        "earlier revision|who changed|document",
    ),
    "documents.sign": (
        "계약서|내 서명|최종 단계",
        "contract|my signature|final step",
    ),
    "documents.comments": (
        "문서|토론 메모|답글",
        "document|discussion notes|reply",
    ),
    "documents.track_changes": (
        "수정 흔적|편집 검토",
        "editing marks|review changes|visible",
    ),
    "cloud.sync": (
        "로컬 수정|온라인 드라이브|복사",
        "local edits|online drive|copied",
    ),
    "cloud.storage": (
        "클라우드|공간|많이 차지",
        "cloud|space|largest items",
    ),
    "cloud.offline": (
        "선택한 파일|네트워크 없음|사용 가능",
        "selected files|no network|available",
    ),
    "cloud.shared_with_me": (
        "다른 사람|나에게 보낸|문서",
        "documents|sent to me|other people",
    ),
    "cloud.link_share": (
        "동료|열 수 있는 링크|만들기",
        "link|colleague|can open",
    ),
    "cloud.link_revoke": (
        "공개 링크|더 이상|열 수 없게",
        "public link|no longer|open",
    ),
    "cloud.restore_version": (
        "문서|선택한 버전|되돌리기",
        "document|chosen revision|consequences",
    ),
    # Education and games
    "education.courses": (
        "등록한|학습 과정|한 화면",
        "enrolled|courses|one screen",
    ),
    "education.lesson": (
        "다음 강의|완료 처리 없이|열기",
        "next lesson|without marking|complete",
    ),
    "education.assignment": (
        "제출 기한|과제 설명|첨부물",
        "due date|assignment details|attachments",
    ),
    "education.assignment_submit": (
        "완성한 과제|업로드|최종 제출 전",
        "finished homework|upload|final submit",
        "과제|올리기",
    ),
    "education.grades": (
        "과목별 점수|선생님 피드백|확인",
        "course grades|teacher feedback|review",
    ),
    "education.certificate": (
        "과정 완료|증명|다운로드",
        "proof|finished the course|download",
    ),
    "education.quiz": (
        "시험 문제|규칙|제한 시간",
        "quiz|rules|time limit|before starting",
    ),
    "education.playback": (
        "강의 시청|재생 전|동작 조정",
        "lecture viewing|behavior|without playing",
    ),
    "education.captions": (
        "말소리|글로|표시 방식",
        "lecture speech|as text|display",
    ),
    "education.offline": (
        "선택한 강의|인터넷 없음|기기에 저장",
        "selected lessons|no internet|device",
    ),
    "education.parent_dashboard": (
        "자녀|수업|진도|확인",
        "child|classes|progress|review",
    ),
    "gaming.library": (
        "보유한 게임|전체 목록|실행 없이",
        "every title|own|without launching",
    ),
    "gaming.cloud_saves": (
        "기기 변경|이어|저장 상태",
        "change device|continue playing|save state",
    ),
    "gaming.crossplay": (
        "다른 콘솔|친구|같은 게임",
        "friends|another console platform|same match",
    ),
    "gaming.voice_chat": (
        "게임 중|음성 대화|누가 사용할",
        "in-game|voice chat|who can use",
    ),
    "gaming.redeem_code": (
        "선불 게임 키|등록|확인 전",
        "prepaid game key|apply|confirm redemption",
    ),
    "gaming.purchase_history": (
        "게임|추가 콘텐츠|결제 기록",
        "bought games|additional content|payment history",
    ),
    "parental.child_account": (
        "자녀|감독 프로필|등록 전",
        "supervised profile|child|enrollment",
    ),
    "parental.screen_time": (
        "자녀|하루|게임|시간",
        "child|daily|game time",
    ),
    "parental.content_rating": (
        "연령 등급|이상 게임|자녀 프로필|숨기기",
        "age rating|titles above|child profile|hide",
    ),
    "parental.purchase_approval": (
        "아이|구매 요청|승인|거절",
        "child|purchase request|approve|decline",
    ),
    "parental.family_sharing": (
        "가족 모두|사용 가능한 게임|확인",
        "games|everyone|household",
    ),
    "parental.communication_control": (
        "자녀|모르는 사람|대화",
        "child|strangers|communicate|restrict",
    ),
    # Government and tax
    "government.identity_login": (
        "공공 서비스|공식 신원|로그인",
        "official identity|public-service|account",
    ),
    "government.certificate_search": (
        "민원 서류|이름|발급 기관",
        "public document|name|issuing agency|search",
    ),
    "government.certificate_issue": (
        "공식 증명서|신청 단계|제출 전",
        "official certificate|application step|before filing",
    ),
    "government.certificate_wallet": (
        "발급받은|전자 문서|휴대전화 지갑",
        "issued digital document|phone wallet|view",
    ),
    "government.benefits": (
        "가구 조건|공공 지원|해당",
        "public assistance|household|fit",
    ),
    "government.address_change": (
        "이사한 주소|행정기관|제출",
        "moved address|government|report|before submit",
    ),
    "government.fines": (
        "미납|과태료|행정 처분",
        "unpaid|tickets|administrative penalties",
    ),
    "tax.hub": (
        "세금|신고|납부 문서|시작",
        "tax|filing|payment documents|start",
        "세금|신고|납부|홈",
    ),
    "tax.return": (
        "올해 세금|신고 준비|전송하지",
        "this year's|tax filing|not transmit",
    ),
    "tax.payment": (
        "납부할 세액|실제 결제",
        "tax due|payment method|before payment",
        "세금|내기",
    ),
    "tax.refund_status": (
        "세무 기관|돌려줄 돈|처리 여부",
        "revenue agency|money it owes|processed",
        "세금|환급|진행",
    ),
    "tax.documents": (
        "소득|원천징수|증빙 파일",
        "income|withholding|tax documents",
    ),
    "tax.deductions": (
        "지출|공제|반영 여부",
        "expenses|available deductions|counted",
        "세금|감면",
    ),
    "government.appointment": (
        "관공서|날짜|시간|예약",
        "public office|visit|date and time|appointment",
    ),
    "government.petition": (
        "관공서|공식 요청|작성|제출 없이",
        "public office|formal request|draft|without submitting",
    ),
    # Smart home and camera/photo library
    "smarthome.device_add": (
        "새 전구|제어 시스템|연결",
        "new light|home control|before connecting",
    ),
    "smarthome.rooms": (
        "연결된 기기|방 사이|이동",
        "connected devices|between rooms|move",
    ),
    "smarthome.automation": (
        "센서 조건|규칙",
        "sensor condition|device action|rule",
    ),
    "smarthome.scene": (
        "한 번 누르기|저녁|조명|온도",
        "one-tap|evening|lights|temperature",
    ),
    "smarthome.guest_access": (
        "방문객|제한된 기간|집 기기|제어",
        "guest|limited period|home devices|control",
    ),
    "smarthome.energy": (
        "연결된 기기|전기|이번 주|비교",
        "connected devices|electricity|this week|compare",
    ),
    "smarthome.firmware": (
        "스마트 기기|새 소프트웨어|변경 내용",
        "smart device|new software|release notes|before install",
    ),
    "smarthome.factory_reset": (
        "연결된 기기|원래 상태|지우기|승인 후",
        "connected device|original state|erase|approve",
    ),
    "smarthome.camera_privacy": (
        "집 카메라|촬영하지|사생활 보호",
        "home camera|not recording|privacy",
    ),
    "smarthome.lock_codes": (
        "문 출입|숫자 코드|유효",
        "door access|numeric codes|valid",
    ),
    "smarthome.sensor_alerts": (
        "문 열림|연기 감지|알림|언제",
        "door opening|smoke detection|alerts|when",
    ),
    "smarthome.device_remove": (
        "오래된 기기|가정|연결 해제|확인 전",
        "old device|household|detach|without confirming",
    ),
    "photos.backup": (
        "휴대전화 사진|온라인 사본",
        "phone photos|online copy|conditions",
    ),
    "photos.albums": (
        "사진|행사별|묶음|전체 목록 대신",
        "pictures|grouped|camera roll",
    ),
    "photos.shared_album": (
        "가족|함께 사진|공간",
        "family|add photos together|space|create",
        "사진|앨범|공유",
    ),
    "photos.hidden": (
        "일반 갤러리|제외한 사진|찾기",
        "images|removed|ordinary gallery view",
    ),
    "photos.locked_folder": (
        "민감한 사진|별도|잠금 공간",
        "sensitive photos|separate|locked space",
    ),
    "photos.memories": (
        "과거 같은 날짜|자동 생성|사진 모음",
        "this date|past years|automatically created collection",
    ),
    "photos.face_grouping": (
        "같은 사람|사진|잘못 묶였는지",
        "same person|photos|wrong grouping",
    ),
    "photos.duplicates": (
        "중복 사진|검토|삭제 전",
        "duplicate images|review",
    ),
    "camera.resolution": (
        "사진|선명하게|크기|비율",
        "photo|sharpness|size|ratio",
    ),
    "camera.timer": (
        "셔터|지연|단체 사진",
        "delay|shutter|group photo",
    ),
    "camera.geotagging": (
        "사진 파일|촬영 장소|기록",
        "photo file|capture location|recorded",
    ),
    "camera.raw": (
        "사진|미가공|나중에 편집",
        "unprocessed image|later editing|capture",
    ),
    "camera.qr_scan": (
        "카메라|사각 코드|주소",
        "camera|square code|link|scan",
    ),
    # Music and podcasts
    "music.queue": (
        "현재 노래|다음 재생|순서",
        "current song|reorder|play",
    ),
    "music.playlist": (
        "좋아하는 곡|재생 묶음|정리",
        "favorite songs|new playlist|organize",
    ),
    "music.offline": (
        "선택한 앨범|네트워크 없음|사용 가능",
        "selected albums|network connection|available",
    ),
    "music.equalizer": (
        "저음|고음|균형|조절",
        "bass|treble|balance|adjust",
    ),
    "music.quality": (
        "스트리밍|음질|데이터 사용|선택",
        "streams|sound detail|data use|choose",
    ),
    "music.lyrics": (
        "재생 중인 노래|문장|화면|따라",
        "current song|words|screen|follow",
    ),
    "audio.sleep_timer": (
        "잠든 후|오디오|자동 정지",
        "audio|automatically|fall asleep",
    ),
    "podcast.subscriptions": (
        "좋아하는 방송|모아|새 회차",
        "favorite shows|follow|new episodes",
    ),
    "podcast.episodes": (
        "팔로우한 방송|재생하지 않은|회차",
        "unplayed installments|programs i follow|show",
    ),
    "podcast.speed": (
        "느린 방송|빠르게",
        "slow show|faster|listen",
    ),
    "podcast.trim_silence": (
        "긴 무음|건너뛰기|말은 유지",
        "quiet gaps|skip|spoken words",
    ),
    "podcast.auto_download": (
        "새 회차|와이파이|받아",
        "new episode|wi-fi|download automatically",
    ),
    "podcast.notifications": (
        "구독한 방송|새 회차|알림|선택",
        "followed shows|new episode|notify|choose",
    ),
    # Collaboration and work management
    "work.workspace_switch": (
        "개인 공간|회사 공간|작업|유지",
        "personal workspace|company workspace|switch|keep work",
    ),
    "work.channels": (
        "팀 대화방|프로젝트 논의|찾기",
        "team room|project discussion|find",
    ),
    "work.meeting_create": (
        "새 화상 회의|시간|참석자|준비",
        "new video meeting|time|attendees|prepare",
    ),
    "work.meeting_join": (
        "기존 통화|초대|참가",
        "existing call|invite|enter",
    ),
    "work.screen_share": (
        "내 화면|참석자|공유 범위|확인",
        "my screen|participants|sharing scope|review",
    ),
    "work.recording": (
        "통화 녹화|동의|저장 정보",
        "record a call|consent|storage details",
    ),
    "work.transcript": (
        "지난 회의|누가|글 기록",
        "past meeting|who said|text record",
    ),
    "work.tasks": (
        "내게 할당|미완료 업무|팀",
        "unfinished work|assigned to me|team",
    ),
    "work.task_create": (
        "새 할 일|작성|저장 직전",
        "new task|compose|before saving",
    ),
    "work.task_assign": (
        "팀원|업무 담당|할당 전",
        "teammate|own a task|assignment",
    ),
    "work.task_due": (
        "업무|마감 날짜|수정",
        "task|due date|change",
    ),
    "work.workflow": (
        "상태 변경|업무 이동|자동 규칙",
        "status changes|moves work",
    ),
    "work.integrations": (
        "외부 업무 도구|조직 공간|연결|권한 검토",
        "external work tool|workspace|connect|permissions",
    ),
    "work.members": (
        "현재|작업 공간|모든 구성원",
        "everyone|currently belongs|workspace",
    ),
    "work.roles": (
        "팀 구성원|역할별|제한",
        "team members|by role|restrict abilities",
    ),
    "work.audit_log": (
        "관리자 변경|작업 공간|기록",
        "administrative changes|workspace|record",
    ),
    # Lending, investing, household bills
    "loan.eligibility": (
        "소득|빌릴 수|사전 확인",
        "income|eligible to borrow|pre-check",
    ),
    "loan.rate_quote": (
        "예상 이자율|비교|신청 없이",
        "estimated interest rate|compare|without applying",
    ),
    "loan.application": (
        "대출 신청서|입력 단계|접수 전",
        "loan application|input stage|before filing",
    ),
    "loan.repayment_schedule": (
        "향후 상환|남은 원금|일정",
        "future payment|remaining principal",
    ),
    "loan.early_repayment": (
        "남은 대출|예정보다 일찍|금액",
        "remaining loan|early|payoff amount",
    ),
    "loan.refinance": (
        "대출 잔액|다른 금융사|옮기기",
        "balance|different lender",
    ),
    "investment.portfolio": (
        "보유 자산|비중|오늘 변동",
        "owned assets|allocation|today change",
    ),
    "investment.order": (
        "매수 또는 매도|주문 준비|체결 금지",
        "buy or sell|request|never place",
    ),
    "investment.recurring": (
        "매달|같은 금액|계획",
        "monthly|same amount|investment plan",
    ),
    "investment.dividends": (
        "보유 회사|현금 분배|내역",
        "companies i own|cash distributions|review",
    ),
    "investment.tax_documents": (
        "투자 거래|연말|세금 자료",
        "investment trades|year-end|tax documents",
    ),
    "investment.risk_profile": (
        "시장 손실|감수|설문",
        "market loss|tolerate|questionnaire",
    ),
    "bills.list": (
        "납부 예정|항목|기한|한곳",
        "upcoming payments|items|deadlines|one place",
    ),
    "bills.payment": (
        "가정 청구서|검토|납부 승인 전",
        "household bill|review|before authorizing payment",
    ),
    "bills.reminder": (
        "청구 마감|날짜|정",
        "bill due|reminder date|change",
    ),
    "bills.split": (
        "공동 비용|여러 사람|나누기|청구 전",
        "shared expense|several people|divide|without requesting",
    ),
    "bills.dispute": (
        "청구 금액|잘못|이의 절차",
        "bill amount|wrong|dispute",
    ),
    "finance.credit_score": (
        "대출 점수|영향 요인|확인",
        "borrowing score|factors|view",
    ),
    # Safety, digital wellbeing, and health
    "safety.sos": (
        "위급할 때|구조 요청|실제 전송",
        "emergency|request help|before sending",
    ),
    "safety.trusted_contacts": (
        "응급 위치|받는 사람|확인",
        "emergency location|people who receive|review",
    ),
    "safety.check_in": (
        "약속한 시간|안전하다고|알리는",
        "scheduled time|safe|check in",
    ),
    "safety.report_content": (
        "유해 게시물|신고|전송 전",
        "harmful post|report|complaint",
    ),
    "safety.report_user": (
        "계정 자체|신고|사유 선택",
        "problem account|report user|reason",
    ),
    "safety.block_user": (
        "특정 계정|상호작용|막기|확인 후",
        "specific account|interacting|prevent|confirm",
    ),
    "safety.mute_user": (
        "특정 사용자|글만|조용히",
        "specific user|posts|silently hide",
    ),
    "safety.report_spam": (
        "원치 않는 메시지|링크 열지 않고|신고",
        "unsolicited message|without opening links|flag",
    ),
    "safety.report_phishing": (
        "개인정보|수상한 메시지|신고",
        "personal information|suspicious message|report",
    ),
    "safety.report_fraud": (
        "거래 요청|사기 의심|신고",
        "transaction request|scam|report",
    ),
    "safety.harassment_controls": (
        "괴롭히는|연락|보호 옵션",
        "repeated harassment|contact|protection options",
    ),
    "safety.recovery_resources": (
        "위기|회복 도움|자동 알림 없이",
        "crisis|recovery help|without notifying",
    ),
    "wellbeing.screen_time": (
        "오늘|앱|시간|많이",
        "today|apps|time spent|most",
    ),
    "wellbeing.focus_mode": (
        "업무 중|방해 앱|일시 중지",
        "while i work|distracting apps|temporarily silence",
    ),
    "wellbeing.bedtime": (
        "밤|화면|알림|줄어드는 시간",
        "night|screen|notifications|reduce",
    ),
    "wellbeing.mindfulness": (
        "짧은 호흡|안내 운동|시작 전",
        "short guided|breathing exercise|without starting",
    ),
    "health.medications": (
        "복용 중인 약|용량|목록",
        "current medications|dosage|list",
    ),
    "health.medication_reminder": (
        "처방약|복용|알림 시간",
        "prescription|take|remind",
    ),
    "health.log_dose": (
        "방금 먹은 약|시간|양|기록",
        "just took medicine|time|dose|record",
    ),
    "health.share_records": (
        "선택한 의료 기록|의료진|공유|승인 후",
        "selected medical records|clinician|share|approval",
    ),
    "health.symptoms": (
        "최근 몸 상태|불편한 증상|날짜별",
        "recent condition|symptoms|by date",
    ),
    "health.lab_results": (
        "혈액 검사|최신 수치|참고 범위",
        "blood|values|reference ranges",
    ),
    "health.vaccinations": (
        "예방접종|맞은|다음 권장 시기",
        "vaccinations received|next recommended|date",
    ),
    "health.cycle_tracking": (
        "월경 주기|예측|달력",
        "menstrual cycles|predictions|calendar",
    ),
    "health.emergency_profile": (
        "응급 상황|잠금 화면|의료 정보",
        "emergency|lock screen|medical information",
    ),
    # Extended Android settings
    "android.notification_history": (
        "오늘|지운 알림|다시 확인",
        "alerts|dismissed|earlier today",
    ),
    "android.privacy_dashboard": (
        "최근|카메라|마이크|사용한 앱",
        "recent|camera|microphone|apps used",
    ),
    "android.restricted_settings": (
        "외부 설치 앱|보호 옵션|경고|허용",
        "sideloaded app|protected option|warning|allow",
    ),
    "android.wifi": (
        "저장된 무선망|현재 연결|확인",
        "saved wireless networks|current connection|review",
    ),
    "android.bluetooth": (
        "주변|페어링된 액세서리|연결 제어",
        "nearby|paired accessories|connection controls",
    ),
    "android.hotspot": (
        "휴대전화 데이터|다른 기기",
        "phone data|other devices|share",
    ),
    "android.vpn": (
        "보안 터널|프로필|기기",
        "secure tunnel|profiles|device",
    ),
    "android.private_dns": (
        "자동 대신|이름 해석 서버|지정",
        "instead of automatic|name resolution server|specified",
    ),
}


# Consequence-oriented language from official productivity and Android help
# journeys.  These are deliberately short, reusable cue conjunctions rather
# than fixture sentences: users commonly describe the result they want
# ("keep it out of the inbox without deleting it", "let a friend follow my
# ETA") instead of repeating the visible menu label.  Every rule combines a
# domain/object cue with a distinguishing outcome so broad words such as
# ``message``, ``calendar``, ``location``, and ``settings`` never stand alone.
_V3_PRODUCTIVITY_SYSTEM_GOAL_RULE_TERMS: dict[str, tuple[str, ...]] = {
    "email.archive": (
        "받은편지함|지우지|치워",
        "inbox|without deleting|remove",
        "inbox|without deleting|mail",
    ),
    "email.swipe_actions": (
        "right swipe|archive|delet",
        "left swipe|mail|action",
    ),
    "email.signature": (
        "휴대폰|메일|서명",
        "mail ending|signature|phone",
        "mail|signature|phone",
    ),
    "email.vacation_responder": (
        "email|away|automatic",
        "email|away|know",
        "mail|out of office|reply",
    ),
    "email.sync": (
        "새 메일|자동|동기화",
        "new mail|automatically|sync",
    ),
    "email.labels": (
        "gmail label|sync|notification",
        "mail label|own notification|options",
    ),
    "email.filters": (
        "발신자|자동|라벨",
        "sender|automatically|label",
    ),
    "email.scheduled": (
        "messages|waiting|sent later",
        "mail|scheduled|review",
    ),
    "email.spam": (
        "스팸|분류한|메일",
        "mail|marked as spam|review",
    ),
    "email.forwarding": (
        "every new|mailbox|automatically",
        "incoming mail|second mailbox|route",
    ),
    "email.send": (
        "작성|메일|받는 사람|발송",
        "written mail|recipient|send",
    ),
    "calendar.event.create": (
        "appointment|calendar|put",
        "새 일정|날짜|달력|등록",
    ),
    "calendar.event.edit": (
        "등록한|회의|시작 시간|바꾸",
        "existing event|start time|change",
    ),
    "calendar.event.delete": (
        "remove|event|calendar",
        "일정|중복|삭제",
    ),
    "calendar.rsvp": (
        "초대받은|참석|답",
        "invited event|attend|respond",
    ),
    "calendar.notifications": (
        "calendar|warn|early|event",
        "calendar|warn|earlier|event",
        "일정|몇 분 전|알림|변경",
    ),
    "calendar.shared_calendars": (
        "공유|일정표|새 행사|캘린더",
        "shared calendar|new event|choose",
    ),
    "maps.directions": (
        "현재 위치|가는 길|예상 시간",
        "current location|directions|estimated time",
    ),
    "maps.offline_maps": (
        "인터넷|끊겨|지도|미리",
        "map|without internet|prepare",
    ),
    "maps.saved_lists": (
        "collection|restaurants|saved",
        "saved places|collection|open",
    ),
    "maps.location_sharing": (
        "가족|실시간 위치|시간|보여",
        "family|live location|limited time",
    ),
    "maps.trip_progress_sharing": (
        "friend|eta|navigating",
        "이동 중|도착 예정|공유",
    ),
    "maps.incognito": (
        "검색할 장소|기록|남지 않",
        "maps|search history|not saved",
        "maps|search history|without saving",
    ),
    "maps.location_history": (
        "maps|visited|timeline",
        "방문한 위치|타임라인|기록",
    ),
    "maps.avoid_options": (
        "자동차 경로|유료도로|피하",
        "route|avoid|toll road",
    ),
    "maps.report_issue": (
        "지도|도로 정보|수정 요청",
        "map|road information|correction",
    ),
    "android.notification_history": (
        "alert|dismissed|earlier today",
        "지운 알림|오늘|다시",
    ),
    "android.privacy_dashboard": (
        "최근|카메라 권한|사용한 앱",
        "recent|camera permission|apps used",
        "apps|recently used|camera permission",
    ),
    "android.bluetooth": (
        "system|nearby bluetooth|accessories",
        "주변|블루투스|액세서리",
    ),
    "android.hotspot": (
        "노트북|휴대전화 데이터|핫스팟",
        "laptop|phone data|hotspot",
    ),
    "android.vpn": (
        "android|vpn profiles|choose",
        "vpn|프로필|선택",
    ),
}


# These labels are valid candidate-screen aliases, but are too broad to be
# standalone user-goal patterns.  They remain in ``V3_FUNCTIONS.aliases`` for
# UI matching; only intent interpretation excludes them until another domain
# cue is present.  This keeps legacy canonical intents stable for genuinely
# ambiguous requests such as "delivery address" or "location sharing".
_V3_EXCLUDED_GOAL_PATTERNS: dict[str, frozenset[str]] = {
    "email.archive": frozenset({"보관"}),
    "calendar.rsvp": frozenset({"참석", "불참"}),
    "contacts.edit": frozenset({"change contact phone number"}),
    "contacts.sync": frozenset({"sync contacts", "연락처 자동 동기화"}),
    "maps.location_sharing": frozenset({"location sharing", "지도 위치 공유", "manage location sharing"}),
    "delivery.address": frozenset({"delivery address", "change delivery address"}),
    "delivery.order_tracking": frozenset({"track order"}),
    "education.assignment": frozenset({"숙제"}),
    "education.playback": frozenset({"course video quality", "lesson playback", "화질"}),
    "cloud.shared_with_me": frozenset({"files others shared"}),
    "esim.remove": frozenset({"erase mobile plan", "모바일 요금제 제거"}),
    "investment.tax_documents": frozenset({"거래 세금 서류"}),
    "smarthome.automation": frozenset({"루틴"}),
    "smarthome.factory_reset": frozenset({"기기 데이터 삭제"}),
    "safety.mute_user": frozenset({"뮤트"}),
    "tax.hub": frozenset({"국세", "세무"}),
    "wellbeing.mindfulness": frozenset({"명상"}),
    "work.roles": frozenset({"관리자 권한"}),
}


_V3_EXCLUDED_PRIMARY_GOAL_TERMS: dict[str, frozenset[str]] = {
    "delivery.address": frozenset({"배달 주소", "delivery address"}),
    "health.lab_results": frozenset({"검사 결과", "lab results"}),
    "loan.application": frozenset({"대출 신청", "loan application"}),
    "maps.location_sharing": frozenset({"실시간 위치 공유", "location sharing"}),
}


_V3_SUPPLEMENTAL_GOAL_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "calendar.rsvp": {
        "ko-KR": ("일정 초대 응답", "회의 참석 여부", "초대 수락 또는 거절"),
    },
    "delivery.address": {
        "en-US": ("manage delivery locations", "shipping destination address", "default drop-off location"),
    },
    "education.playback": {
        "en-US": ("lecture playback controls", "course player settings", "class video behavior"),
    },
    "tax.hub": {
        "ko-KR": ("세금 업무", "세무 업무 시작", "세금 신고 납부 홈"),
    },
}


def _paraphrase_goal_rules(function_id: str) -> list[dict[str, object]]:
    """Build deterministic high-confidence rules from reviewed cue groups."""

    established = _V3_PARAPHRASE_RULE_TERMS.get(function_id, ())
    productivity_system = _V3_PRODUCTIVITY_SYSTEM_GOAL_RULE_TERMS.get(function_id, ())
    rules = [
        {"all_of": list(_terms(rule)), "score": 0.9998}
        for rule in _dedupe(established)
    ]
    # These rules were reviewed specifically against cross-domain collisions
    # (for example Maps live-location sharing versus a generic privacy toggle),
    # so their richer result cues may tie at the resolver's maximum score.  The
    # existing longest-cue tie-break then selects the more specific domain
    # meaning without changing exact-pattern precedence.
    rules.extend(
        {"all_of": list(_terms(rule)), "score": 1.0}
        for rule in _dedupe(productivity_system)
        if rule not in established
    )
    return rules


def _reviewed_goal_patterns(
    values: Sequence[str],
    *,
    locale: str,
    excluded: frozenset[str] = frozenset(),
) -> list[str]:
    """Keep label-like patterns and avoid fuzzy command-wrapper collisions.

    Generic wrappers such as ``open <label>`` add no semantic evidence and can
    look deceptively similar to unrelated natural requests under edit-distance
    fallback.  Bare one-word English aliases are also omitted when richer
    phrases are available (for example, ``archive`` could mean a data export,
    a mail action, or a document collection).
    """

    excluded_folded = {value.casefold() for value in excluded}
    deduped = [value for value in _dedupe(values) if value.casefold() not in excluded_folded]
    if locale == "en-US":
        rich = [value for value in deduped if len(value.split()) >= 2]
        if len(rich) >= 3:
            return rich
    return deduped


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    ko_aliases = [seed.name_ko, *seed.ko_aliases]
    en_aliases = [seed.name_en, *seed.en_aliases]
    excluded_patterns = _V3_EXCLUDED_GOAL_PATTERNS.get(seed.function_id, frozenset())
    excluded_primary = {
        value.casefold()
        for value in _V3_EXCLUDED_PRIMARY_GOAL_TERMS.get(seed.function_id, frozenset())
    }
    supplemental = _V3_SUPPLEMENTAL_GOAL_PATTERNS.get(seed.function_id, {})
    ko_patterns = _dedupe(
        [
            *_reviewed_goal_patterns(
                [*ko_aliases, *supplemental.get("ko-KR", ())],
                locale="ko-KR",
                excluded=excluded_patterns,
            ),
            f"{group.root_ko} 영역 {seed.name_ko}",
            f"{group.root_ko} 메뉴 {seed.name_ko}",
            f"{group.root_ko} 설정 {seed.name_ko}",
        ]
    )
    en_patterns = _dedupe(
        [
            *_reviewed_goal_patterns(
                [*en_aliases, *supplemental.get("en-US", ())],
                locale="en-US",
                excluded=excluded_patterns,
            ),
            f"{seed.name_en} in {group.root_en}",
            f"{group.root_en} menu for {seed.name_en}",
            f"{group.root_en} settings for {seed.name_en}",
        ]
    )
    confirmation_required = seed.mode in {"change", "submit", "sensitive"}
    primary_rule_score = 0.995
    goal_rules = [
        *(
            []
            if seed.name_ko.casefold() in excluded_primary
            else [{"all_of": [seed.name_ko], "score": primary_rule_score}]
        ),
        *(
            []
            if seed.name_en.casefold() in excluded_primary
            else [{"all_of": [seed.name_en.casefold()], "score": primary_rule_score}]
        ),
        {"all_of": [group.root_ko, ko_aliases[1]], "score": 0.985},
        {"all_of": [group.root_en.casefold(), en_aliases[1].casefold()], "score": 0.985},
        *_EXTRA_CONTEXT_GOAL_RULES.get(seed.function_id, []),
        *_paraphrase_goal_rules(seed.function_id),
    ]
    return {
        "intent_id": "v3_" + seed.function_id.replace(".", "_"),
        "terminal_function": seed.function_id,
        "patterns": [*ko_patterns, *en_patterns],
        "patterns_by_locale": {"ko-KR": ko_patterns, "en-US": en_patterns},
        "goal_rules": goal_rules,
        "route": _route(group, seed),
        "avoid_functions": [group.avoid_root],
        "desired_state": "user_confirmation_required" if confirmation_required else "destination_visible",
        "terminal_condition": {
            "stop_policy": "stop_before_action" if confirmation_required else "on_destination_screen"
        },
    }


V3_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V3_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)


REQUIRED_OFFICIAL_EXAMPLES = frozenset(
    {
        "email.archive",
        "email.swipe_actions",
        "email.signature",
        "email.vacation_responder",
        "email.sync",
        "email.labels",
        "calendar.event.create",
        "calendar.event.edit",
        "calendar.event.delete",
        "calendar.rsvp",
        "calendar.notifications",
        "maps.directions",
        "maps.navigation",
        "maps.offline_maps",
        "maps.saved_lists",
        "maps.location_sharing",
        "maps.trip_progress_sharing",
        "maps.incognito",
        "android.notification_history",
        "android.privacy_dashboard",
        "android.restricted_settings",
    }
)


class V3CatalogValidationError(ValueError):
    """Raised when the independent v3 data cannot be safely merged."""


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def validate_v3_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate completeness, safety, uniqueness, and merge references."""

    errors: list[str] = []
    function_ids = [str(item.get("function_id", "")) for item in V3_FUNCTIONS]
    intent_ids = [str(item.get("intent_id", "")) for item in V3_INTENTS]
    function_id_set = set(function_ids)
    intent_id_set = set(intent_ids)
    if len(V3_FUNCTIONS) < 100:
        errors.append(f"v3 must define at least 100 functions, got {len(V3_FUNCTIONS)}")
    if len(V3_INTENTS) < 80:
        errors.append(f"v3 must define at least 80 intents, got {len(V3_INTENTS)}")
    for value in sorted(_duplicates(function_ids)):
        errors.append(f"duplicate v3 function_id: {value}")
    for value in sorted(_duplicates(intent_ids)):
        errors.append(f"duplicate v3 intent_id: {value}")
    missing_examples = sorted(REQUIRED_OFFICIAL_EXAMPLES - function_id_set)
    if missing_examples:
        errors.append("missing required official-route concepts: " + ", ".join(missing_examples))

    required_fields = {
        "function_id", "domain", "scope", "node_kind", "stop_policy", "name_ko", "name_en",
        "description", "risk_level", "automation_policy", "terminal", "state_changing",
        "role_hints", "aliases", "positive_context", "negative_context", "state_cues", "risk_cues",
    }
    never_auto_stops = {"before_action", "before_activation", "user_confirmation", "user_only", "stop_before_action"}
    for item in V3_FUNCTIONS:
        function_id = str(item.get("function_id", "<missing>"))
        missing_fields = sorted(required_fields - set(item))
        if missing_fields:
            errors.append(f"{function_id}: missing fields {missing_fields}")
        aliases = item.get("aliases", {})
        if not isinstance(aliases, Mapping):
            errors.append(f"{function_id}: aliases must be a locale map")
        else:
            for locale in ("ko-KR", "en-US"):
                values = aliases.get(locale, [])
                if not isinstance(values, list) or len(values) < 2 or any(not str(value).strip() for value in values):
                    errors.append(f"{function_id}: {locale} requires at least two non-empty aliases")
        for field in ("positive_context", "negative_context", "role_hints", "state_cues", "risk_cues"):
            value = item.get(field)
            if not value:
                errors.append(f"{function_id}: {field} must not be empty")
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

    known_function_ids = set(function_id_set)
    known_intent_ids: set[str] = set(intent_id_set)
    if base_payload is not None:
        base_function_ids = {str(item.get("function_id", "")) for item in base_payload.get("functions", [])}  # type: ignore[union-attr]
        base_intent_ids = {str(item.get("intent_id", "")) for item in base_payload.get("intents", [])}  # type: ignore[union-attr]
        for value in sorted(function_id_set & base_function_ids):
            errors.append(f"v3 function collides with base catalog: {value}")
        for value in sorted(intent_id_set & base_intent_ids):
            errors.append(f"v3 intent collides with base catalog: {value}")
        known_function_ids.update(base_function_ids)
        known_intent_ids.update(base_intent_ids)

    for intent in V3_INTENTS:
        intent_id = str(intent.get("intent_id", "<missing>"))
        terminal = str(intent.get("terminal_function", ""))
        if terminal not in known_function_ids:
            errors.append(f"{intent_id}: unknown terminal_function {terminal}")
        patterns_by_locale = intent.get("patterns_by_locale", {})
        if not isinstance(patterns_by_locale, Mapping):
            errors.append(f"{intent_id}: patterns_by_locale must be a locale map")
        else:
            for locale in ("ko-KR", "en-US"):
                if len(patterns_by_locale.get(locale, [])) < 3:  # type: ignore[arg-type]
                    errors.append(f"{intent_id}: {locale} requires at least three goal patterns")
        if len(intent.get("goal_rules", [])) < 4:  # type: ignore[arg-type]
            errors.append(f"{intent_id}: requires reusable ko/en goal rules")
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

    if errors:
        raise V3CatalogValidationError("invalid navigation catalog v3 data:\n- " + "\n- ".join(errors))

    functions_by_domain = Counter(str(item["domain"]) for item in V3_FUNCTIONS)
    risk_counts = Counter(str(item["risk_level"]) for item in V3_FUNCTIONS)
    return {
        "catalog_version": CATALOG_V3_VERSION,
        "functions": len(V3_FUNCTIONS),
        "intents": len(V3_INTENTS),
        "domains": len(functions_by_domain),
        "aliases": sum(len(values) for item in V3_FUNCTIONS for values in item["aliases"].values()),  # type: ignore[union-attr]
        "goal_patterns": sum(len(item["patterns"]) for item in V3_INTENTS),  # type: ignore[arg-type]
        "goal_rules": sum(len(item["goal_rules"]) for item in V3_INTENTS),  # type: ignore[arg-type]
        "route_steps": sum(len(item["route"]) for item in V3_INTENTS),  # type: ignore[arg-type]
        "state_changing": sum(bool(item["state_changing"]) for item in V3_FUNCTIONS),
        "high_risk": risk_counts.get("high", 0),
        "functions_by_domain": dict(sorted(functions_by_domain.items())),
        "risk_counts": dict(sorted(risk_counts.items())),
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a validated, non-mutating merge candidate for the materializer."""

    validate_v3_data(base_payload)
    merged = copy.deepcopy(dict(base_payload))
    merged["catalog_version"] = "3.0.0"
    merged["description"] = (
        str(merged.get("description", "")).rstrip()
        + " Long-tail v3 adds communication, mobility, telecom, productivity, public service, IoT, media, work, finance, safety, and health functions."
    ).strip()
    merged["functions"] = [*list(merged.get("functions", [])), *copy.deepcopy(list(V3_FUNCTIONS))]
    merged["intents"] = [*list(merged.get("intents", [])), *copy.deepcopy(list(V3_INTENTS))]
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the independent ExitGuide navigation catalog v3 data")
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE_CATALOG)
    parser.add_argument("--json", action="store_true", help="Print machine-readable statistics")
    args = parser.parse_args()
    stats = validate_v3_data(load_base_catalog(args.base))
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(
            "navigation catalog v3 data valid: "
            f"functions={stats['functions']} intents={stats['intents']} domains={stats['domains']} "
            f"aliases={stats['aliases']} patterns={stats['goal_patterns']} rules={stats['goal_rules']} "
            f"routes={stats['route_steps']} changing={stats['state_changing']} high={stats['high_risk']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
