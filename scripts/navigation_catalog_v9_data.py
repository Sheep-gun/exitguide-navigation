from __future__ import annotations

"""Reviewed v9 cross-domain ontology for universal Android navigation.

The source pack is deliberately app agnostic: it models role, asset, lifecycle,
state, and safety semantics without package names, resource IDs, coordinates,
screenshots, or recorded paths.  Every consequential destination stops before
the final action and leaves the final press to the user.
"""

import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse

from navigation_catalog_v8_data import (
    CATALOG_V8_DESCRIPTION,
    CATALOG_V8_VERSION,
    F,
    G,
    FeatureSeed,
    GroupSeed,
    _build_feature as _v8_build_feature,
    _build_intent as _v8_build_intent,
    _build_root as _v8_build_root,
    _cue_key,
    _pre_v8_payload,
    _rule_signature,
    _runtime_pattern_key,
    merge_with_base as merge_v8_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
CATALOG_V9_VERSION = "9.0.0"
COLLECTED_ON = "2026-07-30"
CATALOG_V9_DESCRIPTION = (
    "ExitGuide cross-app function ontology v9: app-agnostic destinations for "
    "code collaboration, community events, crowdfunding, public EV charging, "
    "nutrition, translation, commercial fleets, hospitality hosts, workplace "
    "access, and agriculture; every consequential final press remains user-owned."
)


def _source(publisher: str, title: str, url: str) -> dict[str, object]:
    return {
        "publisher": publisher,
        "title": title,
        "url": url,
        "collected_on": COLLECTED_ON,
        "evidence_level": "official_primary",
        "verified_status": 200,
        "verification_method": "official first-party page reviewed in the v9 coverage audit",
    }


OFFICIAL_SOURCES: dict[str, dict[str, object]] = {
    "github_mobile": _source(
        "GitHub Docs", "GitHub Mobile",
        "https://docs.github.com/en/get-started/using-github/github-mobile?apiVersion=2022-11-28",
    ),
    "github_notifications": _source(
        "GitHub Docs", "Configuring notifications",
        "https://docs.github.com/en/subscriptions-and-notifications/get-started/configuring-notifications",
    ),
    "meetup_organizers": _source(
        "Meetup Help", "FAQs about the Meetup for Organizers app",
        "https://help.meetup.com/hc/en-us/articles/4481764411405-FAQs-about-the-Meetup-for-Organizers-app",
    ),
    "meetup_attendees": _source(
        "Meetup Help", "Manage attendees and track attendance",
        "https://help.meetup.com/hc/en-us/articles/9389668230541-Manage-attendees-and-track-attendance-for-your-Meetup-event",
    ),
    "gofundme_create": _source(
        "GoFundMe Help", "Creating a fundraiser from start to finish",
        "https://support.gofundme.com/hc/en-us/articles/360001992627-Creating-a-GoFundMe-from-start-to-finish",
    ),
    "gofundme_beneficiary": _source(
        "GoFundMe Help", "Invite a beneficiary to receive funds",
        "https://support.gofundme.com/hc/en-us/articles/204993267-How-to-invite-a-beneficiary-to-receive-funds",
    ),
    "chargepoint_customer_guide": _source(
        "ChargePoint", "Customer Experience User Guide",
        "https://docs.chargepoint.com/ref-docs-sec/content/pdfs/7-misc/cust-exp/cp-cust-exp-ug.pdf",
    ),
    "chargepoint_cloud_plan": _source(
        "ChargePoint", "Essential Cloud Plan",
        "https://docs.chargepoint.com/ref-docs-sec/content/pdfs/7-misc/cp_essential_cloud_plan.pdf",
    ),
    "myfitnesspal_diary": _source(
        "MyFitnessPal Support", "Add a food to the food diary",
        "https://support.myfitnesspal.com/hc/en-us/articles/360032274592-How-do-I-add-a-food-to-my-food-diary",
    ),
    "myfitnesspal_barcode": _source(
        "MyFitnessPal Support", "Use the barcode scanner to log foods",
        "https://support.myfitnesspal.com/hc/en-us/articles/360032624771-How-do-I-use-the-barcode-scanner-to-log-foods",
    ),
    "translate_android": _source(
        "Google Translate Help", "Translate on Android",
        "https://support.google.com/translate/answer/6350850?co=GENIE.Platform%3DAndroid&hl=en",
    ),
    "translate_tap": _source(
        "Google Translate Help", "Tap to Translate",
        "https://support.google.com/translate/answer/6350658?hl=en",
    ),
    "translate_offline": _source(
        "Google Translate Help", "Download languages for offline use",
        "https://support.google.com/translate/answer/6142473?co=GENIE.Platform%3DAndroid&hl=en",
    ),
    "samsara_driver": _source(
        "Samsara Knowledge Base", "Get started with the Driver App",
        "https://kb.samsara.com/hc/en-us/articles/4423183155341-Get-Started-with-the-Samsara-Driver-App",
    ),
    "samsara_settings": _source(
        "Samsara Knowledge Base", "Driver App and device settings",
        "https://kb.samsara.com/hc/en-us/articles/360059559832-Samsara-Driver-App-and-Device-Settings",
    ),
    "samsara_certify": _source(
        "Samsara Knowledge Base", "Certify your logs",
        "https://kb.samsara.com/hc/en-us/articles/12018137810573-Certify-Your-Logs",
    ),
    "airbnb_host_calendar": _source(
        "Airbnb Help", "Host calendar",
        "https://www.airbnb.com/help/article/447",
    ),
    "airbnb_booking_request": _source(
        "Airbnb Help", "Respond to a request to book",
        "https://www.airbnb.com/help/article/28",
    ),
    "airbnb_cohost": _source(
        "Airbnb Help", "Co-host permissions",
        "https://www.airbnb.com/help/article/1534",
    ),
    "envoy_mobile": _source(
        "Envoy Help", "Using the mobile app",
        "https://envoy.help/en/articles/6960299-using-the-envoy-app-mobile",
    ),
    "envoy_invites": _source(
        "Envoy Help", "Registration with invites",
        "https://envoy.help/en/articles/3444425-about-registration-with-invites",
    ),
    "envoy_visitor_log": _source(
        "Envoy Help", "Using the visitor log",
        "https://envoy.help/en/articles/3444480-using-the-visitor-log",
    ),
    "deere_operations_center": _source(
        "John Deere", "Operations Center",
        "https://www.deere.com/en/technology-products/precision-ag-technology/operations-center/welcome/",
    ),
    "deere_work_planner": _source(
        "John Deere", "Work Planner",
        "https://www.deere.com/en/technology-products/precision-ag-technology/operations-center/work-planner/",
    ),
    "deere_harvest": _source(
        "John Deere", "Operations Center harvest",
        "https://www.deere.com/en/technology-products/precision-ag-technology/operations-center/harvest/",
    ),
}


FeatureRow = tuple[str, str, str, str, str, str]


def _feature_rows(
    rows: Sequence[FeatureRow], *, sources: str, negative: str,
) -> tuple[FeatureSeed, ...]:
    """Expand compact reviewed rows into rich, domain-anchored semantics."""

    result: list[FeatureSeed] = []
    for key, name_ko, name_en, alternate_ko, alternate_en, mode in rows:
        ko_aliases = "|".join((
            alternate_ko,
            f"{name_ko} 화면",
            f"{name_ko} 세부",
            f"{name_ko} 작업",
        ))
        en_aliases = "|".join((
            alternate_en,
            f"{name_en} screen",
            f"{name_en} details",
            f"{name_en} workflow",
        ))
        positive = "|".join((name_ko, alternate_ko, name_en, alternate_en))
        result.append(F(
            key, name_ko, name_en, ko_aliases, en_aliases,
            positive, negative, mode, sources=sources,
        ))
    return tuple(result)


CODE_REPOSITORY_ROWS: tuple[FeatureRow, ...] = (
    ("account_switch", "코드 저장소 계정 전환", "Code repository account switch", "개발 조직 계정 바꾸기", "switch development organization account", "sensitive"),
    ("repository_search", "코드 저장소 검색", "Code repository search", "프로젝트 저장소 찾기", "find a project repository", "view"),
    ("code_search", "저장소 코드 검색", "Repository code search", "소스 코드 문자열 찾기", "find source code text", "sensitive"),
    ("repository_tree", "저장소 파일 트리", "Repository file tree", "브랜치 폴더 구조 보기", "browse branch folder structure", "sensitive"),
    ("file_view", "저장소 파일 보기", "Repository file view", "소스 파일 내용 열기", "open source file contents", "sensitive"),
    ("commit_history", "저장소 커밋 기록", "Repository commit history", "코드 변경 이력 보기", "review code change history", "sensitive"),
    ("issue_list", "저장소 이슈 목록", "Repository issue list", "개발 문제 목록 보기", "review development issue list", "sensitive"),
    ("issue_detail", "저장소 이슈 상세", "Repository issue detail", "개발 문제 대화 열기", "open development issue discussion", "sensitive"),
    ("issue_create", "저장소 이슈 생성", "Create repository issue", "새 개발 문제 등록", "submit a new development issue", "submit"),
    ("issue_comment", "저장소 이슈 댓글", "Repository issue comment", "개발 문제에 답글 쓰기", "reply to a development issue", "submit"),
    ("issue_close_reopen", "저장소 이슈 종료·재개", "Close or reopen repository issue", "개발 문제 상태 전환", "change development issue lifecycle", "submit"),
    ("pull_request_list", "코드 변경 요청 목록", "Code pull request list", "병합 요청 목록 보기", "review merge request list", "sensitive"),
    ("pull_request_detail", "코드 변경 요청 상세", "Code pull request detail", "병합 요청 대화 열기", "open merge request details", "sensitive"),
    ("diff_review", "코드 변경 차이 검토", "Code diff review", "변경 줄 비교하기", "inspect changed code lines", "sensitive"),
    ("review_comment", "코드 검토 댓글", "Code review comment", "변경 줄에 검토 의견 남기기", "leave feedback on changed code", "submit"),
    ("review_submit", "코드 검토 결과 제출", "Submit code review decision", "승인 또는 변경 요청 제출", "submit approval or change request", "submit"),
    ("merge_pull_request", "코드 변경 병합", "Merge code pull request", "검토된 코드 합치기", "merge reviewed code changes", "submit"),
    ("notification_triage", "코드 협업 알림 정리", "Code collaboration notification triage", "개발 알림 완료·보관·구독 해제", "mark save or unsubscribe development notifications", "submit"),
)

COMMUNITY_MEETUP_ROWS: tuple[FeatureRow, ...] = (
    ("group_discovery", "커뮤니티 모임 그룹 탐색", "Community meetup group discovery", "관심사 지역 모임 찾기", "find a local interest group", "view"),
    ("group_join_request", "커뮤니티 그룹 가입 요청", "Community group join request", "관심사 모임 참여 신청", "request membership in an interest group", "submit"),
    ("group_leave", "커뮤니티 그룹 탈퇴", "Leave community meetup group", "관심사 모임 나가기", "leave an interest community", "submit"),
    ("event_discovery", "커뮤니티 행사 탐색", "Community event discovery", "주변 모임 행사 찾기", "find nearby meetup events", "view"),
    ("event_detail", "커뮤니티 행사 상세", "Community event detail", "모임 일정과 장소 보기", "review meetup time and venue", "view"),
    ("event_rsvp", "커뮤니티 행사 참석 응답", "Community event RSVP", "모임 참석·불참 선택", "choose going or not going", "submit"),
    ("event_waitlist", "커뮤니티 행사 대기열", "Community event waitlist", "정원 찬 모임 대기 신청", "join a full event waitlist", "submit"),
    ("event_fee", "커뮤니티 행사 참가비", "Community event fee", "모임 참가 결제", "pay a meetup participation fee", "submit"),
    ("attendee_list", "커뮤니티 행사 참가자 목록", "Community event attendee list", "모임 참석자와 대기자 보기", "review attendees and waitlisted people", "sensitive"),
    ("event_check_in", "커뮤니티 행사 체크인", "Community event check-in", "모임 현장 출석 처리", "record meetup attendance", "submit"),
    ("group_discussion", "커뮤니티 그룹 토론", "Community group discussion", "모임 게시판에 글 남기기", "post in a meetup discussion", "submit"),
    ("organizer_create_event", "주최자 커뮤니티 행사 생성", "Organizer community event creation", "새 모임 행사 만들기", "create a new meetup event", "submit"),
    ("organizer_edit_event", "주최자 커뮤니티 행사 편집", "Organizer community event editing", "모임 일정 내용 수정", "edit meetup event details", "submit"),
    ("organizer_publish_event", "주최자 커뮤니티 행사 공개", "Organizer community event publishing", "작성한 모임 게시", "publish a prepared meetup event", "submit"),
    ("organizer_venue", "주최자 커뮤니티 행사 장소", "Organizer community event venue", "모임 개최 장소 설정", "set the meetup event venue", "submit"),
    ("organizer_member_requests", "주최자 그룹 가입 요청 관리", "Organizer group membership requests", "모임 가입 신청 승인·거절", "approve or deny group join requests", "submit"),
    ("organizer_member_moderation", "주최자 그룹 구성원 관리", "Organizer community member moderation", "모임 구성원 경고·제거", "moderate or remove group members", "submit"),
    ("organizer_group_settings", "주최자 커뮤니티 그룹 설정", "Organizer community group settings", "모임 공개 범위와 규칙 변경", "change group visibility and rules", "submit"),
)

CROWDFUNDING_ROWS: tuple[FeatureRow, ...] = (
    ("fundraiser_discovery", "크라우드펀딩 모금 탐색", "Crowdfunding fundraiser discovery", "기부할 모금 캠페인 찾기", "find a fundraising campaign to support", "view"),
    ("fundraiser_detail", "크라우드펀딩 모금 상세", "Crowdfunding fundraiser detail", "모금 목표와 사연 보기", "review fundraiser goal and story", "view"),
    ("donation_amount", "크라우드펀딩 기부 금액", "Crowdfunding donation amount", "후원 금액과 통화 선택", "choose contribution amount and currency", "submit"),
    ("recurring_donation", "크라우드펀딩 정기 기부", "Recurring crowdfunding donation", "반복 후원 주기 설정", "set a recurring fundraiser contribution", "submit"),
    ("anonymous_donation", "크라우드펀딩 익명 기부", "Anonymous crowdfunding donation", "후원자 이름 숨김 선택", "hide donor identity on a fundraiser", "submit"),
    ("donation_checkout", "크라우드펀딩 기부 결제", "Crowdfunding donation checkout", "모금 후원 최종 결제", "complete fundraiser contribution checkout", "submit"),
    ("donation_receipt", "크라우드펀딩 기부 영수증", "Crowdfunding donation receipt", "후원 결제 증빙 보기", "review fundraiser payment receipt", "sensitive"),
    ("donation_history", "크라우드펀딩 기부 내역", "Crowdfunding donation history", "과거 모금 후원 기록", "review past fundraiser contributions", "sensitive"),
    ("share_fundraiser", "크라우드펀딩 모금 공유", "Share crowdfunding fundraiser", "모금 캠페인 링크 보내기", "send a fundraiser campaign link", "submit"),
    ("create_fundraiser", "크라우드펀딩 모금 생성", "Create crowdfunding fundraiser", "새 모금 캠페인 만들기", "start a new fundraising campaign", "submit"),
    ("edit_story_media", "크라우드펀딩 사연·미디어 편집", "Edit crowdfunding story and media", "모금 설명과 사진 수정", "update fundraiser story and photos", "submit"),
    ("publish_fundraiser", "크라우드펀딩 모금 공개", "Publish crowdfunding fundraiser", "작성한 모금 캠페인 게시", "publish a prepared fundraising campaign", "submit"),
    ("post_update", "크라우드펀딩 모금 소식 게시", "Post crowdfunding fundraiser update", "후원자에게 진행 소식 알리기", "publish progress news to donors", "submit"),
    ("donor_thank_you", "크라우드펀딩 후원자 감사", "Crowdfunding donor thank-you", "기부자에게 감사 메시지 보내기", "send a thank-you message to donors", "submit"),
    ("beneficiary_invite", "크라우드펀딩 수혜자 초대", "Crowdfunding beneficiary invitation", "모금 수령인에게 초대 전송", "invite a fundraiser beneficiary", "submit"),
    ("beneficiary_accept", "크라우드펀딩 수혜자 수락", "Crowdfunding beneficiary acceptance", "모금 수령 권한 인수", "accept fundraiser beneficiary ownership", "submit"),
    ("transfer_setup", "크라우드펀딩 모금 이체 설정", "Crowdfunding fundraiser transfer setup", "수혜 계좌와 출금 정보 설정", "configure beneficiary bank transfer", "submit"),
    ("transfer_status", "크라우드펀딩 모금 이체 상태", "Crowdfunding fundraiser transfer status", "수혜금 지급 진행 보기", "review beneficiary payout progress", "sensitive"),
)

EV_CHARGING_ROWS: tuple[FeatureRow, ...] = (
    ("station_map", "공용 전기차 충전소 지도", "Public EV charging station map", "주변 공용 충전기 지도 보기", "browse nearby public chargers on a map", "view"),
    ("station_search", "공용 전기차 충전소 검색", "Public EV charging station search", "주소로 공용 충전기 찾기", "find a public charger by location", "view"),
    ("connector_filter", "공용 충전 커넥터 필터", "Public charging connector filter", "차량 규격에 맞는 플러그 찾기", "filter chargers by vehicle connector", "view"),
    ("station_availability", "공용 충전소 가용 상태", "Public charging station availability", "사용 가능한 충전기 확인", "check available public charge points", "view"),
    ("station_detail", "공용 전기차 충전소 상세", "Public EV charging station detail", "충전소 ID와 편의시설 보기", "review charger identifier and amenities", "view"),
    ("pricing_idle_fee", "공용 충전 요금·유휴 수수료", "Public charging price and idle fee", "충전 단가와 점유 수수료 확인", "review charging tariff and occupancy fee", "sensitive"),
    ("station_photos", "공용 충전소 사진", "Public charging station photos", "충전기 위치 사진 보기", "view photos locating a public charger", "view"),
    ("favorite_station", "공용 충전소 즐겨찾기", "Favorite public charging station", "자주 쓰는 충전소 저장", "save a frequently used charger", "submit"),
    ("waitlist_notify", "공용 충전 대기 알림", "Public charging waitlist notification", "충전기 비면 알림 신청", "request notice when a charger frees up", "submit"),
    ("reserve_charger", "공용 충전기 예약", "Reserve public EV charger", "충전 시간과 포트 예약", "reserve a charge point and time", "submit"),
    ("start_session", "공용 전기차 충전 시작", "Start public EV charging session", "연결된 충전기 세션 시작", "start the connected public charger session", "submit"),
    ("live_session", "공용 전기차 충전 진행", "Live public EV charging session", "충전량과 비용 진행 보기", "review live energy and cost progress", "sensitive"),
    ("stop_session", "공용 전기차 충전 중단", "Stop public EV charging session", "진행 중 충전 세션 종료", "end the active public charging session", "submit"),
    ("payment_methods", "공용 충전 결제수단", "Public charging payment methods", "충전 카드와 결제 정보 변경", "change charging card and billing method", "submit"),
    ("charging_history", "공용 전기차 충전 내역", "Public EV charging history", "과거 충전 세션과 비용 보기", "review past charging sessions and costs", "sensitive"),
    ("receipt_download", "공용 충전 영수증 다운로드", "Public charging receipt download", "충전 결제 증빙 받기", "download public charging payment proof", "sensitive"),
    ("roaming_networks", "공용 충전 로밍 네트워크", "Public charging roaming networks", "연동 충전 사업자 범위 확인", "review interoperable charging networks", "sensitive"),
    ("report_station_issue", "공용 충전소 문제 신고", "Report public charging station issue", "고장난 충전기 문제 제출", "submit a faulty charger report", "submit"),
)

NUTRITION_ROWS: tuple[FeatureRow, ...] = (
    ("food_search", "영양 식품 검색", "Nutrition food search", "식단에 기록할 음식 찾기", "find food to add to a meal diary", "view"),
    ("barcode_scan", "영양 식품 바코드 스캔", "Nutrition food barcode scan", "포장 식품 코드로 영양 찾기", "scan packaged food for nutrition", "sensitive"),
    ("meal_scan", "영양 식사 사진 스캔", "Nutrition meal photo scan", "음식 사진으로 식단 인식", "identify a meal from a photo", "sensitive"),
    ("voice_log", "영양 식사 음성 기록", "Nutrition meal voice log", "말로 먹은 음식 입력", "dictate food eaten into a diary", "sensitive"),
    ("serving_adjust", "영양 제공량 조정", "Nutrition serving adjustment", "음식 분량과 단위 변경", "change food portion and unit", "submit"),
    ("food_log", "영양 음식 기록", "Nutrition food logging", "식사 구분에 음식 추가", "add food to a selected meal", "submit"),
    ("water_log", "영양 수분 기록", "Nutrition water logging", "마신 물 양 추가", "add consumed water amount", "submit"),
    ("food_diary", "영양 식단 일지", "Nutrition food diary", "날짜별 음식 기록 보기", "review dated meal records", "sensitive"),
    ("macro_dashboard", "영양소 대시보드", "Nutrition macro dashboard", "탄수화물 단백질 지방 요약", "review carbohydrate protein and fat totals", "sensitive"),
    ("nutrient_goals", "영양소 목표 설정", "Nutrition nutrient goals", "칼로리와 영양 목표 변경", "change calorie and nutrient targets", "submit"),
    ("recipe_create", "영양 레시피 생성", "Create nutrition recipe", "재료와 분량으로 조리법 만들기", "create a recipe from ingredients and servings", "submit"),
    ("recipe_edit", "영양 레시피 편집", "Edit nutrition recipe", "저장한 조리법 재료 수정", "update ingredients in a saved recipe", "submit"),
    ("saved_meal", "영양 저장 식사", "Saved nutrition meal", "반복 식단 묶음 저장", "save a reusable meal combination", "submit"),
    ("meal_plan", "영양 식사 계획", "Nutrition meal plan", "날짜별 식단 구성", "plan meals by date", "submit"),
    ("grocery_list", "영양 식단 장보기 목록", "Nutrition meal grocery list", "식사 계획에서 재료 목록 만들기", "create ingredients list from meal plan", "submit"),
    ("fasting_window", "영양 단식 시간창", "Nutrition fasting window", "공복 시작과 종료 설정", "set fasting start and end time", "submit"),
    ("progress_report", "영양 진행 보고서", "Nutrition progress report", "섭취와 목표 추세 보기", "review intake and goal trends", "sensitive"),
    ("export_nutrition_data", "영양 데이터 내보내기", "Export nutrition data", "식단과 영양 기록 파일 받기", "export meal and nutrient records", "submit"),
)

TRANSLATION_ROWS: tuple[FeatureRow, ...] = (
    ("language_pair", "번역 출발어·도착어", "Translation source and target languages", "번역 언어 방향 선택", "choose translation language direction", "view"),
    ("text_translate", "텍스트 번역", "Text translation", "입력한 문장을 다른 언어로 변환", "translate typed text into another language", "sensitive"),
    ("camera_instant_translate", "카메라 즉시 번역", "Instant camera translation", "카메라 글자를 실시간 번역", "translate visible camera text instantly", "sensitive"),
    ("image_import_translate", "가져온 이미지 번역", "Imported image translation", "사진 파일 속 글자 번역", "translate text in an imported image", "sensitive"),
    ("speech_translate", "음성 번역", "Speech translation", "말한 내용을 다른 언어로 번역", "translate spoken content", "sensitive"),
    ("conversation_mode", "대화 통역 모드", "Conversation interpreting mode", "두 언어 대화를 번갈아 통역", "interpret a two-language conversation", "sensitive"),
    ("live_transcription", "번역 실시간 받아쓰기", "Translation live transcription", "말을 연속 자막과 번역으로 표시", "show continuous speech transcript and translation", "sensitive"),
    ("handwriting_input", "번역 손글씨 입력", "Translation handwriting input", "손으로 쓴 문자를 번역", "translate handwritten characters", "sensitive"),
    ("pronunciation_playback", "번역 발음 재생", "Translation pronunciation playback", "번역 결과 소리 듣기", "listen to translated result pronunciation", "view"),
    ("copy_result", "번역 결과 복사", "Copy translation result", "번역문을 클립보드에 넣기", "copy translated text to clipboard", "submit"),
    ("share_result", "번역 결과 공유", "Share translation result", "번역문을 다른 대상에게 보내기", "send translated text to another destination", "submit"),
    ("phrasebook", "번역 표현 모음", "Translation phrasebook", "저장한 번역 문구 보기", "review saved translated phrases", "sensitive"),
    ("translation_history", "번역 기록", "Translation history", "과거 번역 입력과 결과 보기", "review past translation inputs and results", "sensitive"),
    ("offline_language_download", "번역 오프라인 언어 다운로드", "Translation offline language download", "인터넷 없이 쓸 언어 받기", "download a language for offline translation", "submit"),
    ("offline_language_update_remove", "번역 오프라인 언어 갱신·삭제", "Update or remove offline translation language", "받아둔 언어 팩 관리", "manage a downloaded translation language pack", "submit"),
    ("tap_to_translate_overlay", "다른 앱 위 번역 오버레이", "Translation overlay over another app", "복사한 글자 번역 아이콘 켜기", "enable floating translation for copied text", "submit"),
)

FLEET_ROWS: tuple[FeatureRow, ...] = (
    ("fleet_select", "상용 운송 차량대 선택", "Commercial fleet selection", "소속 운송 차량대 바꾸기", "switch assigned transport fleet", "sensitive"),
    ("vehicle_select", "상용 운행 차량 선택", "Commercial vehicle selection", "근무에 사용할 차량 지정", "select vehicle for the duty period", "submit"),
    ("trailer_select", "상용 운행 트레일러 선택", "Commercial trailer selection", "운송 작업 트레일러 지정", "select trailer for the route", "submit"),
    ("driver_profile", "상용 운전자 프로필", "Commercial driver profile", "운전자 면허와 소속 정보 보기", "review driver identity and carrier details", "sensitive"),
    ("duty_status", "상용 운전자 근무 상태", "Commercial driver duty status", "운전·근무·휴식 상태 변경", "change driving on-duty or rest status", "submit"),
    ("hos_clock", "상용 운전자 운행시간 시계", "Commercial driver hours-of-service clock", "남은 운전·근무 시간 보기", "review remaining driving and duty time", "sensitive"),
    ("hos_violations", "상용 운전자 운행시간 위반", "Commercial driver hours violations", "규정 위반과 임박 경고 확인", "review compliance violations and warnings", "sensitive"),
    ("daily_log", "상용 운전자 일일 운행 기록", "Commercial driver daily log", "근무 상태와 운행 이력 보기", "review daily duty and driving history", "sensitive"),
    ("edit_hos_log", "상용 운전자 운행 기록 편집", "Edit commercial driver duty log", "허용된 근무 기록 수정", "edit an eligible duty record", "submit"),
    ("certify_hos_logs", "상용 운전자 운행 기록 인증", "Certify commercial driver logs", "법정 일일 기록 서명·제출", "sign and submit regulated daily logs", "submit"),
    ("roadside_inspection", "상용 운전자 도로 검사 모드", "Commercial roadside inspection mode", "검사관에게 운행 기록 제시", "present duty records for roadside inspection", "submit"),
    ("pretrip_dvir", "상용 차량 운행 전 점검", "Commercial pre-trip vehicle inspection", "출발 전 차량 상태 보고", "submit a pre-trip vehicle condition report", "submit"),
    ("posttrip_dvir", "상용 차량 운행 후 점검", "Commercial post-trip vehicle inspection", "운행 종료 차량 상태 보고", "submit a post-trip vehicle condition report", "submit"),
    ("defect_report", "상용 차량 결함 보고", "Commercial vehicle defect report", "안전 결함과 조치 필요 제출", "submit a safety defect and needed repair", "submit"),
    ("route_assignments", "상용 운전자 배정 경로", "Commercial driver route assignments", "회사 배차 정류장 목록 보기", "review dispatched stops and route", "sensitive"),
    ("route_start", "상용 운송 경로 시작", "Start commercial transport route", "배정된 운송 작업 출발 처리", "start an assigned commercial route", "submit"),
    ("stop_arrival_departure", "상용 운송 정류장 도착·출발", "Commercial stop arrival and departure", "배차 지점 상태 기록", "record arrival or departure at a dispatched stop", "submit"),
    ("dispatch_messages", "상용 운송 배차 메시지", "Commercial dispatch messages", "배차 담당자에게 업무 메시지 보내기", "send an operational message to dispatch", "submit"),
    ("driver_documents_forms", "상용 운전자 문서·양식", "Commercial driver documents and forms", "운송 업무 서류 작성·제출", "complete and submit transport forms", "submit"),
    ("proof_of_delivery", "상용 운송 인도 증빙", "Commercial proof of delivery", "수령 서명·사진·완료 기록 제출", "submit signature photo or delivery completion proof", "submit"),
)

HOSPITALITY_HOST_ROWS: tuple[FeatureRow, ...] = (
    ("listing_switch", "숙소 호스트 매물 전환", "Hospitality host listing switch", "관리할 숙소 바꾸기", "switch the lodging listing being managed", "sensitive"),
    ("listing_editor", "숙소 호스트 매물 편집", "Hospitality host listing editor", "숙소 설명과 기본 정보 수정", "edit lodging description and core details", "submit"),
    ("listing_photos", "숙소 호스트 매물 사진", "Hospitality host listing photos", "숙소 사진 추가·순서 변경", "add or reorder lodging photos", "submit"),
    ("amenities_rules", "숙소 호스트 편의시설·규칙", "Hospitality host amenities and rules", "숙소 시설과 이용 규칙 수정", "change lodging amenities and house rules", "submit"),
    ("host_calendar", "숙소 호스트 예약 달력", "Hospitality host reservation calendar", "숙소 가용일과 예약 보기", "review listing availability and bookings", "sensitive"),
    ("block_unblock_dates", "숙소 호스트 날짜 차단·해제", "Hospitality host block or unblock dates", "예약 가능한 날짜 상태 변경", "change dates between available and blocked", "submit"),
    ("nightly_price", "숙소 호스트 1박 가격", "Hospitality host nightly price", "숙박 날짜별 요금 변경", "change nightly lodging price", "submit"),
    ("discounts_fees", "숙소 호스트 할인·수수료", "Hospitality host discounts and fees", "숙박 할인과 추가 요금 설정", "set lodging discounts and extra charges", "submit"),
    ("availability_settings", "숙소 호스트 예약 가능 설정", "Hospitality host availability settings", "최소 숙박과 예약 기간 변경", "change minimum stay and booking window", "submit"),
    ("inquiry_requests", "숙소 호스트 문의·예약 요청", "Hospitality host inquiries and requests", "게스트 문의와 대기 요청 보기", "review guest inquiries and pending requests", "sensitive"),
    ("reservation_detail", "숙소 호스트 예약 상세", "Hospitality host reservation detail", "게스트와 숙박 일정 보기", "review guest and stay details", "sensitive"),
    ("accept_decline_request", "숙소 호스트 예약 수락·거절", "Hospitality host accept or decline request", "게스트 예약 요청 결정", "decide a guest booking request", "submit"),
    ("guest_messages", "숙소 호스트 게스트 메시지", "Hospitality host guest messages", "숙박객에게 답장 보내기", "send a reply to a lodging guest", "submit"),
    ("quick_scheduled_reply", "숙소 호스트 빠른·예약 답장", "Hospitality host quick or scheduled reply", "미리 만든 게스트 메시지 발송", "send a prepared or timed guest message", "submit"),
    ("checkin_guide", "숙소 호스트 체크인 안내", "Hospitality host check-in guide", "입실 방법과 출입 정보 수정", "edit guest arrival and access instructions", "submit"),
    ("reservation_modify", "숙소 호스트 예약 변경", "Hospitality host reservation modification", "숙박 날짜·인원·금액 조정", "change reservation dates guests or price", "submit"),
    ("host_cancel_reservation", "숙소 호스트 예약 취소", "Hospitality host reservation cancellation", "호스트가 확정 숙박 취소", "cancel a confirmed stay as host", "submit"),
    ("guest_review", "숙소 호스트 게스트 후기", "Hospitality host guest review", "숙박객 평가와 후기 제출", "submit a review of a lodging guest", "submit"),
    ("earnings_payouts", "숙소 호스트 수익·정산", "Hospitality host earnings and payouts", "숙박 수입과 지급 상태 보기", "review hosting income and payout status", "sensitive"),
    ("cohost_access", "숙소 공동 호스트 권한", "Hospitality co-host access", "공동 관리자의 숙소 권한 변경", "change another host's listing permissions", "submit"),
)

WORKPLACE_ACCESS_ROWS: tuple[FeatureRow, ...] = (
    ("location_switch", "사업장 출입 위치 전환", "Workplace access location switch", "근무 지점 바꾸기", "switch active workplace location", "sensitive"),
    ("workplace_pass", "사업장 출입 패스", "Workplace access pass", "직원 모바일 출입증 보기", "view employee mobile credential", "sensitive"),
    ("door_unlock", "사업장 출입문 잠금 해제", "Workplace door unlock", "권한 있는 업무 공간 문 열기", "unlock an authorized workplace door", "submit"),
    ("desk_booking", "사업장 좌석 예약", "Workplace desk booking", "근무할 책상과 시간 예약", "reserve a workplace desk and time", "submit"),
    ("room_booking", "사업장 회의실 예약", "Workplace room booking", "업무 공간 방과 시간 예약", "reserve a workplace room and time", "submit"),
    ("workplace_schedule", "사업장 근무 일정", "Workplace attendance schedule", "출근 예정 위치와 날짜 보기", "review planned workplace location and date", "sensitive"),
    ("visitor_invite", "사업장 방문자 초대", "Workplace visitor invitation", "외부 방문객에게 등록 초대", "invite an external visitor to register", "submit"),
    ("visitor_edit_invite", "사업장 방문자 초대 편집", "Edit workplace visitor invitation", "방문 날짜와 호스트 수정", "change visitor date and host", "submit"),
    ("visitor_preregistration", "사업장 방문자 사전등록", "Workplace visitor preregistration", "방문 전에 신원 정보 제출", "submit visitor identity before arrival", "submit"),
    ("visitor_qr", "사업장 방문자 QR", "Workplace visitor QR", "방문 접수용 코드 보기", "view code for visitor reception", "sensitive"),
    ("visitor_log", "사업장 방문 기록", "Workplace visitor log", "방문자 출입 이력 보기", "review visitor entry history", "sensitive"),
    ("visitor_detail", "사업장 방문자 상세", "Workplace visitor detail", "방문 신원과 호스트 정보 보기", "review visitor identity and host", "sensitive"),
    ("visitor_approve_deny", "사업장 방문 승인·거절", "Approve or deny workplace visitor", "보안 담당자가 방문 허용 결정", "security decision on visitor access", "submit"),
    ("visitor_sign_in", "사업장 방문자 입실", "Workplace visitor sign-in", "방문객 도착과 출입 시작 기록", "record visitor arrival and entry", "submit"),
    ("visitor_sign_out", "사업장 방문자 퇴실", "Workplace visitor sign-out", "방문객 퇴장과 출입 종료 기록", "record visitor departure and exit", "submit"),
    ("badge_reprint", "사업장 방문 배지 재출력", "Workplace visitor badge reprint", "방문자 출입 배지 다시 발급", "issue another visitor access badge", "submit"),
    ("emergency_roll_call", "사업장 비상 재실 확인", "Workplace emergency roll call", "비상 시 현재 인원 보기", "review people present during emergency", "sensitive"),
    ("report_access_issue", "사업장 출입 문제 신고", "Report workplace access issue", "출입증이나 문 오류 제출", "submit a credential or door access problem", "submit"),
)

AGRICULTURE_ROWS: tuple[FeatureRow, ...] = (
    ("organization_farm_switch", "농장 조직 전환", "Agriculture farm organization switch", "관리할 농장 계정 바꾸기", "switch the farm organization being managed", "sensitive"),
    ("field_map", "농업 필지 지도", "Agriculture field map", "농장 구획과 위치 보기", "review farm parcels and locations", "sensitive"),
    ("field_boundary", "농업 필지 경계", "Agriculture field boundary", "재배 구획 경계 생성·수정", "create or edit a crop field boundary", "submit"),
    ("crop_season", "농업 작물·재배 시즌", "Agriculture crop and season", "필지 작물과 재배 연도 설정", "set field crop and growing season", "submit"),
    ("machine_map", "농업 기계 지도", "Agriculture machine map", "농기계 위치와 이동 보기", "review agricultural machine locations", "sensitive"),
    ("machine_detail", "농업 기계 상세", "Agriculture machine detail", "농기계 상태와 작업 정보 보기", "review machine state and operation", "sensitive"),
    ("diagnostic_alert", "농업 기계 진단 경보", "Agriculture machine diagnostic alert", "농기계 오류와 진단 코드 확인", "review machinery fault and diagnostic code", "sensitive"),
    ("implement_status", "농업 작업기 상태", "Agriculture implement status", "연결된 농작업 장비 보기", "review attached farming implement", "sensitive"),
    ("work_plan_list", "농업 작업 계획 목록", "Agriculture work plan list", "필지별 예정 작업 보기", "review planned field operations", "sensitive"),
    ("work_plan_create_edit", "농업 작업 계획 생성·편집", "Create or edit agriculture work plan", "필지 작업과 자재 계획 수정", "prepare field operation and input plan", "submit"),
    ("work_plan_send_machine", "농업 작업 계획 기계 전송", "Send agriculture work plan to machine", "필지 지시를 농기계로 보내기", "transmit field instructions to machinery", "submit"),
    ("input_products", "농업 투입 자재", "Agriculture input products", "종자·비료·약제 정보 설정", "set seed fertilizer or treatment product", "submit"),
    ("tank_mix", "농업 탱크 혼합", "Agriculture tank mix", "살포 자재 혼합비 구성", "configure agricultural spray mixture", "submit"),
    ("scouting_note", "농업 필지 관찰 기록", "Agriculture scouting note", "작물 상태와 병해충 메모", "record crop condition or pest observation", "submit"),
    ("field_flag", "농업 필지 표식", "Agriculture field flag", "현장 관심 위치 표시", "mark a location of interest in a field", "submit"),
    ("planting_record", "농업 파종 기록", "Agriculture planting record", "필지 파종 작업 결과 보기", "review completed field planting operation", "sensitive"),
    ("application_record", "농업 살포 기록", "Agriculture application record", "비료·약제 적용 이력 보기", "review fertilizer or treatment application history", "sensitive"),
    ("harvest_record", "농업 수확 기록", "Agriculture harvest record", "필지 수확 작업 결과 보기", "review completed field harvest operation", "sensitive"),
    ("yield_map", "농업 수확량 지도", "Agriculture yield map", "필지별 생산량 분석 보기", "review production yield by field area", "sensitive"),
    ("farm_data_share_export", "농장 데이터 공유·내보내기", "Share or export agriculture data", "농장 작업 기록을 외부에 제공", "share farm operation records externally", "submit"),
)


GROUPS: tuple[GroupSeed, ...] = (
    G(
        "code_repository", "코드 저장소 협업", "Code repository collaboration", "code_collaboration",
        "코드 저장소|브랜치|커밋|이슈|변경 요청|코드 검토",
        "code repository|branch|commit|issue|pull request|code review",
        "일반 파일 보관함|업무 할 일|장애 경보", "generic file storage|general task|incident alert",
        "work.hub", "github_mobile|github_notifications",
        *_feature_rows(
            CODE_REPOSITORY_ROWS,
            sources="github_mobile|github_notifications",
            negative="일반 문서 파일|업무 댓글|장애 알림|generic document file|task comment|incident notification",
        ),
    ),
    G(
        "community_meetup", "커뮤니티·모임 운영", "Community and meetup organizing", "community_events",
        "관심사 모임|지역 그룹|참가자|주최자|참석 응답|대기열",
        "interest meetup|local group|attendee|organizer|RSVP|waitlist",
        "좌석 티켓 구매|스포츠 선수단|업무 회의", "seat ticket purchase|sports roster|work meeting",
        "event_ticket.hub", "meetup_organizers|meetup_attendees",
        *_feature_rows(
            COMMUNITY_MEETUP_ROWS,
            sources="meetup_organizers|meetup_attendees",
            negative="좌석 지정 행사|팀 경기|회사 회의|ticketed seating event|team game|company meeting",
        ),
    ),
    G(
        "crowdfunding_donations", "크라우드펀딩·금전 기부", "Crowdfunding and monetary donations", "fundraising_service",
        "모금 캠페인|기부자|후원 금액|수혜자|모금 이체|후원 영수증",
        "fundraiser campaign|donor|donation amount|beneficiary|fund transfer|donation receipt",
        "장기 기증|창작자 멤버십|일반 은행 송금", "organ donation|creator membership|ordinary bank transfer",
        "finance.longtail.hub", "gofundme_create|gofundme_beneficiary",
        *_feature_rows(
            CROWDFUNDING_ROWS,
            sources="gofundme_create|gofundme_beneficiary",
            negative="장기 기증 의사|크리에이터 구독|개인 계좌 송금|organ donation consent|creator subscription|personal bank transfer",
        ),
    ),
    G(
        "public_ev_charging", "공용 전기차 충전", "Public electric-vehicle charging", "public_charging_network",
        "공용 충전소|충전 커넥터|충전 요금|유휴 수수료|충전 세션|충전 로밍",
        "public charging station|charging connector|tariff|idle fee|charging session|roaming network",
        "가정용 충전 예약|차량 배터리|주유소", "home charging schedule|vehicle battery|fuel station",
        "automotive_vehicle.hub", "chargepoint_customer_guide|chargepoint_cloud_plan",
        *_feature_rows(
            EV_CHARGING_ROWS,
            sources="chargepoint_customer_guide|chargepoint_cloud_plan",
            negative="소유 차량 배터리|가정 충전기|연료 주유|owned vehicle battery|home charger|fuel purchase",
        ),
    ),
    G(
        "nutrition_meal", "영양·식단·레시피", "Nutrition, meals, and recipes", "nutrition_service",
        "음식|제공량|식단 일지|영양소|레시피|단식 시간",
        "food|serving|meal diary|nutrient|recipe|fasting window",
        "식료품 주문|증상 기록|의학 진단", "grocery order|symptom journal|medical diagnosis",
        "wellbeing.hub", "myfitnesspal_diary|myfitnesspal_barcode",
        *_feature_rows(
            NUTRITION_ROWS,
            sources="myfitnesspal_diary|myfitnesspal_barcode",
            negative="상점 장바구니|질병 증상|치료 조언|store shopping cart|disease symptom|treatment advice",
        ),
    ),
    G(
        "language_translation", "언어 번역·통역", "Language translation and interpreting", "translation_service",
        "출발 언어|도착 언어|텍스트 번역|카메라 번역|음성 통역|번역 기록",
        "source language|target language|text translation|camera translation|speech interpreting|translation history",
        "언어 수업|자막 접근성|문서 편집", "language lesson|caption accessibility|document editing",
        "education.hub", "translate_android|translate_tap|translate_offline",
        *_feature_rows(
            TRANSLATION_ROWS,
            sources="translate_android|translate_tap|translate_offline",
            negative="언어 퀴즈|미디어 자막|원문 문서 수정|language quiz|media caption|source document edit",
        ),
    ),
    G(
        "fleet_driver_compliance", "상용 차량대·운전자 규정", "Commercial fleet and driver compliance", "commercial_transport",
        "상용 차량대|운전자|트레일러|운행시간|운행 기록|차량 점검",
        "commercial fleet|driver|trailer|hours of service|duty log|vehicle inspection",
        "개인 차량|배달 고객 추적|플랫폼 일감 제안", "personal vehicle|customer parcel tracking|gig offer",
        "automotive_vehicle.hub", "samsara_driver|samsara_settings|samsara_certify",
        *_feature_rows(
            FLEET_ROWS,
            sources="samsara_driver|samsara_settings|samsara_certify",
            negative="개인 자동차 설정|고객 배송 조회|일회성 플랫폼 배차|personal car settings|customer delivery tracking|gig dispatch offer",
        ),
    ),
    G(
        "hospitality_host", "숙소 호스트 운영", "Hospitality host operations", "lodging_host_service",
        "숙소 호스트|매물|예약 달력|게스트 요청|숙박 가격|공동 호스트",
        "lodging host|listing|reservation calendar|guest request|nightly price|co-host",
        "숙박객 검색|여행자 예약|호텔 체크인", "guest lodging search|traveler booking|hotel check-in",
        "lodging.hub", "airbnb_host_calendar|airbnb_booking_request|airbnb_cohost",
        *_feature_rows(
            HOSPITALITY_HOST_ROWS,
            sources="airbnb_host_calendar|airbnb_booking_request|airbnb_cohost",
            negative="투숙객 숙소 탐색|여행 예약 결제|게스트 환불|guest property search|traveler reservation payment|guest refund",
        ),
    ),
    G(
        "workplace_access", "사업장 출입·방문자", "Workplace access and visitor management", "physical_workplace_security",
        "사업장|직원 출입증|방문자|호스트|출입 배지|재실 인원",
        "workplace|employee credential|visitor|host|access badge|occupancy",
        "개인 주택 문|소프트웨어 권한|일반 회의 일정", "personal home door|software permission|general meeting schedule",
        "smarthome.hub", "envoy_mobile|envoy_invites|envoy_visitor_log",
        *_feature_rows(
            WORKPLACE_ACCESS_ROWS,
            sources="envoy_mobile|envoy_invites|envoy_visitor_log",
            negative="스마트홈 잠금|온라인 계정 권한|일반 캘린더|smart-home lock|online account permission|general calendar",
        ),
    ),
    G(
        "agriculture_ops", "농장·농업 운영", "Agriculture and farm operations", "agriculture_operations",
        "농장 조직|필지|작물 시즌|농기계|작업 계획|수확량",
        "farm organization|field|crop season|agricultural machine|work plan|yield",
        "개인 차량|건설 현장|정원 관리", "personal vehicle|construction site|garden care",
        "field_construction_ops.hub", "deere_operations_center|deere_work_planner|deere_harvest",
        *_feature_rows(
            AGRICULTURE_ROWS,
            sources="deere_operations_center|deere_work_planner|deere_harvest",
            negative="개인 자동차|건설 작업지시|가정 원예|personal automobile|construction work order|home gardening",
        ),
    ),
)


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["legacy_tags"] = [
        "v9_cross_domain" if value == "v8_operational_workflow" else value
        for value in result.get("legacy_tags", [])
    ]
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    return _retag_function(_v8_build_root(group))


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v8_build_feature(group, seed))
    if bool(result["state_changing"]) or result["risk_level"] == "high":
        result["automation_policy"] = "never_auto"
        result["stop_policy"] = "before_action"
        risk_cues = copy.deepcopy(result["risk_cues"])
        risk_cues["user_boundary"] = [
            "최종 실행 버튼은 사용자가 직접 누름",
            "the user must press the final action button",
        ]
        result["risk_cues"] = risk_cues
    return result


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v8_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v8_", "v9_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v8_", "v9_", 1)
        for key in tuple(rule):
            if key.startswith("v8_"):
                rule[f"v9_{key[3:]}"] = rule.pop(key)
    return result


V9_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V9_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
REQUIRED_FUNCTIONS = frozenset({
    "code_repository.merge_pull_request",
    "code_repository.review_submit",
    "community_meetup.event_rsvp",
    "community_meetup.organizer_member_moderation",
    "crowdfunding_donations.donation_checkout",
    "crowdfunding_donations.transfer_setup",
    "public_ev_charging.start_session",
    "public_ev_charging.stop_session",
    "nutrition_meal.food_log",
    "nutrition_meal.export_nutrition_data",
    "language_translation.share_result",
    "language_translation.tap_to_translate_overlay",
    "fleet_driver_compliance.certify_hos_logs",
    "fleet_driver_compliance.proof_of_delivery",
    "hospitality_host.host_cancel_reservation",
    "hospitality_host.cohost_access",
    "workplace_access.door_unlock",
    "workplace_access.visitor_approve_deny",
    "agriculture_ops.work_plan_send_machine",
    "agriculture_ops.farm_data_share_export",
})


class V9CatalogValidationError(ValueError):
    """Raised when v9 cannot be merged without semantic or safety drift."""


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _pre_v9_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V9_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V9_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", [])
        if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", [])
        if str(item["intent_id"]) not in intent_ids
    ]
    result.pop("official_sources_v9", None)
    result["catalog_version"] = CATALOG_V8_VERSION
    result["description"] = CATALOG_V8_DESCRIPTION
    return result


def _ensure_v8(payload: Mapping[str, object]) -> dict[str, object]:
    """Rebuild a clean reviewed v8 layer, discarding derived runtime guards."""

    return merge_v8_with_base(_pre_v8_payload(_pre_v9_payload(payload)))


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Load a clean v8 base whether canonical storage is at v7, v8, or v9."""

    return _ensure_v8(json.loads(path.read_text(encoding="utf-8")))


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V9_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V9_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    if not present_functions and not present_intents and "official_sources_v9" not in payload:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V9CatalogValidationError("partial v9 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V9CatalogValidationError("v9 collides with a different function or intent definition")
    if payload.get("official_sources_v9") != OFFICIAL_SOURCES:
        raise V9CatalogValidationError("v9 official evidence registry differs")
    if payload.get("catalog_version") != CATALOG_V9_VERSION or payload.get("description") != CATALOG_V9_DESCRIPTION:
        raise V9CatalogValidationError("v9 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def validate_v9_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate exact reviewed scope, evidence, safety, and collision freedom."""

    errors: list[str] = []
    function_ids = [str(item["function_id"]) for item in V9_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V9_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V9_FUNCTIONS if bool(item["terminal"])}
    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v9 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v9 intent IDs: {sorted(duplicates)}")
    if len(REQUIRED_DOMAINS) != 10:
        errors.append("v9 must contain exactly ten reviewed priority domains")
    domain_terminal_counts = Counter(
        str(item["domain"]) for item in V9_FUNCTIONS if bool(item["terminal"])
    )
    expected_domain_counts = {
        "agriculture_ops": 20,
        "code_repository": 18,
        "community_meetup": 18,
        "crowdfunding_donations": 18,
        "fleet_driver_compliance": 20,
        "hospitality_host": 20,
        "language_translation": 16,
        "nutrition_meal": 18,
        "public_ev_charging": 18,
        "workplace_access": 18,
    }
    if dict(sorted(domain_terminal_counts.items())) != expected_domain_counts:
        errors.append(
            "v9 domain terminal counts differ from the reviewed 184-destination pack: "
            f"{dict(sorted(domain_terminal_counts.items()))}"
        )
    if len(V9_FUNCTIONS) != 194 or len(terminal_ids) != 184 or len(V9_INTENTS) != 184:
        errors.append("v9 requires exactly 10 hubs, 184 terminals, and 184 intents")
    if missing := REQUIRED_FUNCTIONS - set(function_ids):
        errors.append(f"missing required v9 functions: {sorted(missing)}")

    for source_id, source in OFFICIAL_SOURCES.items():
        parsed = urlparse(str(source.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"source {source_id} is not an absolute HTTPS URL")
        if not str(source.get("publisher", "")).strip() or not str(source.get("title", "")).strip():
            errors.append(f"source {source_id} lacks publisher or title")
        if source.get("evidence_level") != "official_primary":
            errors.append(f"source {source_id} is not official_primary")
        if source.get("collected_on") != COLLECTED_ON:
            errors.append(f"source {source_id} lacks collection date")
        if source.get("verified_status") != 200 or not str(source.get("verification_method", "")).strip():
            errors.append(f"source {source_id} lacks verification metadata")

    known_sources = set(OFFICIAL_SOURCES)
    used_sources: set[str] = set()
    forbidden_keys = {
        "x", "y", "bounds", "coordinate", "coordinates", "package",
        "package_name", "resource_id", "screen_path", "recorded_path",
    }
    for function in V9_FUNCTIONS:
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
        if _contains_forbidden_key(function, forbidden_keys):
            errors.append(f"{function_id}: app-specific package, resource, coordinate, or path data is forbidden")

        consequential = bool(function["state_changing"]) or function["risk_level"] == "high"
        if consequential:
            if function["automation_policy"] != "never_auto" or function["stop_policy"] != "before_action":
                errors.append(f"{function_id}: unsafe final-action boundary")
            boundary = " ".join(function["risk_cues"].get("user_boundary", []))  # type: ignore[union-attr]
            if "사용자" not in boundary or "user" not in boundary.casefold() or "press" not in boundary.casefold():
                errors.append(f"{function_id}: explicit user-owned final press is missing")
        elif function["terminal"]:
            if function["automation_policy"] != "safe_navigation":
                errors.append(f"{function_id}: read-only terminal must remain safe navigation")
        elif function["automation_policy"] != "safe_navigation" or function["stop_policy"] != "continue":
            errors.append(f"{function_id}: hub must remain navigation-only")
    if used_sources != known_sources:
        errors.append(f"orphan official sources: {sorted(known_sources - used_sources)}")

    intent_terminals = [str(item["terminal_function"]) for item in V9_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v9 requires exactly one intent per terminal function")
    terminal_by_id = {str(item["function_id"]): item for item in V9_FUNCTIONS}
    for intent in V9_INTENTS:
        intent_id = str(intent["intent_id"])
        localized = intent["patterns_by_locale"]
        if len(localized["ko-KR"]) < 10 or len(localized["en-US"]) < 10:  # type: ignore[index]
            errors.append(f"{intent_id}: insufficient bilingual patterns")
        if len(intent["goal_rules"]) < 24:
            errors.append(f"{intent_id}: insufficient compositional rules")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != intent["terminal_function"]:  # type: ignore[index]
            errors.append(f"{intent_id}: invalid hub-to-destination route")
        if not intent["avoid_functions"]:
            errors.append(f"{intent_id}: missing contrastive avoid function")
        terminal = terminal_by_id[str(intent["terminal_function"])]
        if bool(terminal["state_changing"]) or terminal["risk_level"] == "high":
            if intent["desired_state"] != "user_confirmation_required":
                errors.append(f"{intent_id}: consequential intent lacks user confirmation")
            if intent["terminal_condition"]["stop_policy"] != "stop_before_action":  # type: ignore[index]
                errors.append(f"{intent_id}: consequential route does not stop before action")
        for rule in intent["goal_rules"]:
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v9_"):
                errors.append(f"{intent_id}: malformed semantic rule")
            for key in ("v9_discriminative_keys", "v9_negative_context_keys", "v9_positive_context_keys"):
                values = list(rule.get(key, []))
                if values != sorted(dict.fromkeys(values)):
                    errors.append(f"{intent_id}: nondeterministic {key}")

    materialized = False
    if base_payload is not None:
        materialized = _materialization_state(base_payload)
        pre_v9 = _ensure_v8(base_payload)
        base_function_ids = {str(item["function_id"]) for item in pre_v9.get("functions", [])}
        base_intent_ids = {str(item["intent_id"]) for item in pre_v9.get("intents", [])}
        if collisions := sorted(set(function_ids).intersection(base_function_ids)):
            errors.append(f"v9 function IDs collide with v1-v8: {collisions[:12]}")
        if collisions := sorted(set(intent_ids).intersection(base_intent_ids)):
            errors.append(f"v9 intent IDs collide with v1-v8: {collisions[:12]}")

        pattern_owners: dict[str, set[str]] = {}
        for intent in [*pre_v9.get("intents", []), *V9_INTENTS]:
            owner = str(intent["intent_id"])
            for pattern in intent.get("patterns", []):
                key = _runtime_pattern_key(pattern)
                if key:
                    pattern_owners.setdefault(key, set()).add(owner)
        pattern_collisions = {
            key: sorted(owners) for key, owners in pattern_owners.items() if len(owners) > 1
        }
        if pattern_collisions:
            errors.append(f"normalized goal-pattern collisions: {list(pattern_collisions.items())[:8]}")

        base_rule_signatures = {
            _rule_signature(rule)
            for intent in pre_v9.get("intents", [])
            for rule in intent.get("goal_rules", [])
            if _rule_signature(rule)
        }
        v9_rule_owners: dict[tuple[str, ...], set[str]] = {}
        for intent in V9_INTENTS:
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if signature in base_rule_signatures:
                    errors.append(f"{intent['intent_id']}: goal rule collides with v1-v8")
                v9_rule_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
        shared_rules = {
            signature: sorted(owners) for signature, owners in v9_rule_owners.items()
            if len(owners) > 1
        }
        if shared_rules:
            errors.append(f"v9 goal-rule collisions: {list(shared_rules.items())[:8]}")

    semantic_payload = copy.deepcopy({"functions": V9_FUNCTIONS, "intents": V9_INTENTS})
    for function in semantic_payload["functions"]:
        function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = (
        "com.", "package name", "resource-id", "screen coordinate", "recorded path",
        "github", "gofundme", "chargepoint", "myfitnesspal",
        "google translate", "samsara", "airbnb", "envoy", "john deere",
    )
    if any(
        re.search(rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])", semantic_text)
        for value in forbidden_fragments
    ):
        errors.append("v9 runtime semantics contain an app identity or recorded UI path")

    if errors:
        raise V9CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V9_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V9_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_terminal_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES),
        "aliases": sum(len(values) for item in V9_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V9_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V9_INTENTS),
        "compositional_goal_rules": sum(
            1 for item in V9_INTENTS for rule in item["goal_rules"]
            if rule["rule_kind"] in {"v9_compositional_domain", "v9_consequence_context"}
        ),
        "state_changing": sum(bool(item["state_changing"]) for item in V9_FUNCTIONS),
        "high_risk": sum(item["risk_level"] == "high" for item in V9_FUNCTIONS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, idempotent, fail-closed v8+v9 catalog copy."""

    validate_v9_data(base_payload)
    if _materialization_state(base_payload):
        return copy.deepcopy(dict(base_payload))
    merged = _ensure_v8(base_payload)
    merged["catalog_version"] = CATALOG_V9_VERSION
    merged["description"] = CATALOG_V9_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V9_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V9_INTENTS)]
    merged["official_sources_v9"] = copy.deepcopy(OFFICIAL_SOURCES)
    return merged


def main() -> int:
    print(json.dumps(validate_v9_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
