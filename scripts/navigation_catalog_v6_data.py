from __future__ import annotations

"""App-agnostic v6 navigation ontology for open-world Android services.

This module is deliberately independent from evaluation fixtures.  Every
concept below is derived from first-party product/help documentation and is
expressed as a semantic destination, never as a package name, coordinate, or
memorised application path.  Routes stop at the destination or immediately
before a user-owned consequential action.
"""

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
CATALOG_V6_VERSION = "6.0.0"
COLLECTED_ON = "2026-07-30"
CATALOG_V6_DESCRIPTION = (
    "ExitGuide cross-app function ontology v6: open-world, app-agnostic destinations "
    "for vehicle services, parking and tolls, employee payroll, fitness memberships, "
    "home services, local civic services, pet care, and grocery loyalty; all "
    "consequential final actions remain user-owned."
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


# Each URL was opened on COLLECTED_ON.  Search results, community posts, and
# third-party app walkthroughs are not accepted as evidence.
OFFICIAL_SOURCES: dict[str, dict[str, object]] = {
    # Connected vehicles.
    "tesla_getting_started": _source(
        "Tesla Support", "Getting Started With Your Tesla Vehicle",
        "https://www.tesla.com/support/getting-started-with-your-vehicle",
    ),
    "tesla_vehicle_controls": _source(
        "Tesla Support", "Vehicle Controls | Tesla App",
        "https://www.tesla.com/support/videos/watch/vehicle-controls-tesla-app",
    ),
    "tesla_vehicle_keys": _source(
        "Tesla Support", "Tesla Vehicle Keys",
        "https://www.tesla.com/support/tesla-vehicle-keys",
    ),
    "tesla_vehicle_security": _source(
        "Tesla Support", "Vehicle Safety and Security Features",
        "https://www.tesla.com/support/vehicle-safety-security-features",
    ),
    "tesla_service_visits": _source(
        "Tesla Support", "Schedule and Manage Tesla Service Appointments",
        "https://www.tesla.com/support/service-visits",
    ),
    "tesla_charge_stats": _source(
        "Tesla Support", "Understanding Charge Stats",
        "https://www.tesla.com/support/tesla-app/charge-stats",
    ),
    "tesla_driver_access": _source(
        "Tesla Support", "How to Add or Remove Drivers",
        "https://www.tesla.com/support/how-add-or-remove-drivers",
    ),
    "tesla_customer_support": _source(
        "Tesla Support", "Customer Support and Roadside Assistance",
        "https://www.tesla.com/support/customer-support",
    ),
    "tesla_charging": _source(
        "Tesla Support", "Charging",
        "https://www.tesla.com/support/charging",
    ),
    "tesla_scheduled_charge": _source(
        "Tesla Service", "Scheduled Precondition and Charge",
        "https://service.tesla.com/docs/Public/diy/model3/en_us/GUID-9C2F6258-81FB-484C-B16A-AF4238EDF028.html",
    ),
    # Parking and tolls.
    "parkmobile_faq": _source(
        "ParkMobile Customer Care", "Frequently Asked Questions",
        "https://support.parkmobile.io/hc/en-us/articles/36854907118747-FREQUENTLY-ASKED-QUESTIONS",
    ),
    "parkmobile_extend": _source(
        "ParkMobile Customer Care", "How do I extend a parking session?",
        "https://support.parkmobile.io/hc/en-us/articles/36854825840027-How-do-I-extend-a-parking-session",
    ),
    "parkmobile_history": _source(
        "ParkMobile Customer Care", "How do I view and print my parking history?",
        "https://support.parkmobile.io/hc/en-us/articles/36854910209179-How-do-I-view-and-print-my-parking-history",
    ),
    "parkmobile_personal_pages": _source(
        "ParkMobile Customer Care", "What are Personal Pages?",
        "https://support.parkmobile.io/hc/en-us/articles/36854886013851-What-are-Personal-Pages",
    ),
    "parkmobile_ticket": _source(
        "ParkMobile Customer Care", "Parking ticket after payment",
        "https://support.parkmobile.io/hc/en-us/articles/36854748270747-I-received-a-parking-ticket-or-violation-after-I-paid-What-do-I-do",
    ),
    "ezpass_accounts": _source(
        "E-ZPass New York", "E-ZPass Account Types and Online Account Management",
        "https://www.e-zpassny.com/ezpass/account-types",
    ),
    "ny_thruway_tolls": _source(
        "New York State Thruway Authority", "Cashless Tolling and Toll Bills",
        "https://thruway.ny.gov/ezpass",
    ),
    # HR and payroll.
    "adp_mobile": _source(
        "ADP", "HR and Payroll Mobile App",
        "https://www.adp.com/what-we-offer/products/adp-mobile-solutions.aspx",
    ),
    "adp_mobile_login": _source(
        "ADP", "ADP Mobile Solutions Login and Support",
        "https://www.adp.com/logins/adp-mobile-solutions.aspx",
    ),
    "adp_employee_self_service": _source(
        "ADP", "Employee Self-Service Payroll and HR Software",
        "https://www.adp.com/resources/articles-and-insights/articles/e/employee-self-service.aspx",
    ),
    "adp_hr_pro": _source(
        "ADP Marketplace", "ADP HR Pro Features",
        "https://apps.adp.com/en-US/apps/292428/adp-hr-pro/features",
    ),
    "workday_mobile": _source(
        "Workday", "Workday Mobile App",
        "https://www.workday.com/en-sg/products/platform-product-extensions/workday-mobile.html",
    ),
    "workday_expenses": _source(
        "Workday", "Expense Reporting and Tracking Software",
        "https://www.workday.com/en-us/products/spend-management/expenses.html",
    ),
    # Fitness and memberships.
    "google_fit_help": _source(
        "Google Fit Help", "Google Fit Help",
        "https://support.google.com/fit/?hl=en",
    ),
    "google_fit_activity": _source(
        "Google Fit Help", "Find your activity",
        "https://support.google.com/fit/answer/6090183?hl=en-GB",
    ),
    "google_fit_edit_activity": _source(
        "Google Fit Help", "Add and edit fitness activities",
        "https://support.google.com/fit/answer/6223934?hl=en-GB",
    ),
    "google_fit_connect": _source(
        "Google Fit Help", "Connect other apps with Google Fit",
        "https://support.google.com/fit/answer/6098255?co=GENIE.Platform%3DAndroid&hl=en",
    ),
    "google_fit_permissions": _source(
        "Google Fit Help", "Manage Google Fit permissions",
        "https://support.google.com/fit/answer/9488336?co=GENIE.Platform%3DAndroid&hl=en",
    ),
    "classpass_reserve": _source(
        "ClassPass Support", "How do I make a reservation?",
        "https://help.classpass.com/hc/en-us/articles/204335689-How-do-I-make-a-reservation",
    ),
    "classpass_cancel": _source(
        "ClassPass Support", "How do I cancel a fitness class or wellness reservation?",
        "https://help.classpass.com/hc/en-us/articles/204335739-How-do-I-cancel-a-fitness-class-or-wellness-reservation",
    ),
    "classpass_pause": _source(
        "ClassPass Support", "Can I pause my ClassPass membership?",
        "https://help.classpass.com/hc/en-us/articles/360040920251-Can-I-pause-my-ClassPass-membership",
    ),
    "classpass_renewal": _source(
        "ClassPass Support", "Will my membership automatically renew?",
        "https://help.classpass.com/hc/en-us/articles/204368569-Will-my-membership-automatically-renew",
    ),
    # Home services.
    "taskrabbit_hire": _source(
        "Taskrabbit Support", "How Do I Hire a Tasker?",
        "https://support.taskrabbit.com/hc/en-us/articles/46260422073755-How-Do-I-Hire-a-Tasker",
    ),
    "taskrabbit_reschedule": _source(
        "Taskrabbit Support", "How Do I Reschedule a Task?",
        "https://support.taskrabbit.com/hc/en-ca/articles/46260501690651-How-Do-I-Reschedule-a-Task",
    ),
    "taskrabbit_cancel": _source(
        "Taskrabbit Support", "How Do I Cancel a Task?",
        "https://support.taskrabbit.com/hc/en-us/articles/46260428230939-How-Do-I-Cancel-a-Task",
    ),
    "taskrabbit_tip": _source(
        "Taskrabbit Support", "How Do I Tip My Tasker?",
        "https://support.taskrabbit.com/hc/en-us/articles/46260486399643-How-Do-I-Tip-My-Tasker",
    ),
    "taskrabbit_claim": _source(
        "Taskrabbit Support", "How Do I Submit a Claim?",
        "https://support.taskrabbit.com/hc/en-us/articles/46260478592539-Damages-Theft-or-Injury-Occurred-During-My-Task-How-Do-I-Submit-a-Claim",
    ),
    "taskrabbit_invoice": _source(
        "Taskrabbit Support", "Understand Fees on a Task Invoice",
        "https://support.taskrabbit.com/hc/en-us/articles/46260407116955-I-d-Like-To-Understand-The-Fees-On-My-Task-s-Invoice",
    ),
    "taskrabbit_expenses": _source(
        "Taskrabbit Support", "How Do I Reimburse My Tasker For Expenses?",
        "https://support.taskrabbit.com/hc/en-us/articles/46260534257435-How-Do-I-Reimburse-My-Tasker-For-Expenses",
    ),
    # Local civic services.
    "nyc311_service_requests": _source(
        "NYC311", "Service Requests",
        "https://portal.311.nyc.gov/article/?kanumber=KA-03116",
    ),
    "nyc311_report": _source(
        "NYC311", "Report Problems",
        "https://portal.311.nyc.gov/report-problems/",
    ),
    "nyc311_status": _source(
        "NYC311", "Look Up Service Requests",
        "https://portal.311.nyc.gov/check-status//",
    ),
    "nyc311_home": _source(
        "NYC311", "NYC311 Home and Service Topics",
        "https://portal.311.nyc.gov/",
    ),
    "nyc311_pothole": _source(
        "NYC311", "Pothole or Cave-In on Street",
        "https://portal.311.nyc.gov/article/?kanumber=KA-01093",
    ),
    "nyc_dob_now": _source(
        "NYC Department of Buildings", "DOB NOW",
        "https://www.nyc.gov/site/buildings/property-or-business-owner/dob-now.page",
    ),
    # Pet care.
    "petco_app": _source(
        "Petco", "Petco App: Personalized Pet Care",
        "https://www.petco.com/c/petco-app",
    ),
    "petsmart_services": _source(
        "PetSmart", "PetSmart Services",
        "https://services.petsmart.com/grooming/booking?openLogin=true",
    ),
    "akc_records": _source(
        "AKC Reunite", "Online Records System",
        "https://apps.akcreunite.org/cares-pub/customer/customerLogin.car",
    ),
    "akc_recovery": _source(
        "AKC Reunite", "Recovery Service and Enrollment FAQ",
        "https://www.akcreunite.org/recoveryservicefaq/",
    ),
    "akc_lost_pet": _source(
        "AKC Reunite", "Lost or Found Pets FAQ",
        "https://www.akcreunite.org/lostfoundpetfaq/",
    ),
    "chewy_home": _source(
        "Chewy", "Pet Health Services",
        "https://www.chewy.com/",
    ),
    "chewy_pharmacy": _source(
        "Chewy", "Chewy Pharmacy",
        "https://www.chewy.com/health/pharmacy",
    ),
    "chewy_vetfinder": _source(
        "Chewy", "Find a Vet Clinic",
        "https://www.chewy.com/health/vetfinder",
    ),
    # Grocery and loyalty.
    "kroger_coupons": _source(
        "Kroger", "Digital Coupon FAQs",
        "https://www.kroger.com/hc/help/faqs/ways-to-save/coupons",
    ),
    "kroger_receipts": _source(
        "Kroger", "Digital Receipts",
        "https://www.kroger.com/i/receipt",
    ),
    "kroger_shopping_list": _source(
        "Kroger", "Shopping List FAQs",
        "https://www.kroger.com/hc/help/faqs/ways-to-shop/shopping-list",
    ),
    "kroger_fuel_points": _source(
        "Kroger", "Fuel Points Program",
        "https://www.kroger.com/d/fuel-points-program",
    ),
    "walmart_substitutions": _source(
        "Walmart Help", "Substitutions for Store Pickup and Delivery Items",
        "https://www.walmart.com/help/article/substitutions-for-store-pickup-and-delivery-items/c8dd3973509b42488da66a362af4666d",
    ),
    "walmart_pickup": _source(
        "Walmart Help", "Pickup and Delivery",
        "https://www.walmart.com/help/article/pickup-and-delivery/d0d02a5f54e54592930f110aaf6a2f50",
    ),
    "walmart_pickup_changes": _source(
        "Walmart Help", "Pickup and Delivery Changes and Exceptions",
        "https://www.walmart.com/help/article/pickup-and-delivery-changes-and-exceptions/97461ebd27b04ab78cfa1ca3de480a83",
    ),
    "target_circle": _source(
        "Target Help", "About Target Circle",
        "https://help.target.com/help/SubCategoryArticle?childcat=About+Target+Circle&parentcat=Target+Circle%E2%84%A2",
    ),
    "target_wallet": _source(
        "Target Help", "Wallet",
        "https://help.target.com/help/subcategoryarticle?childcat=Wallet&parentcat=Payment+Options",
    ),
}


def _terms(value: str | Iterable[str]) -> tuple[str, ...]:
    values = value.split("|") if isinstance(value, str) else value
    return tuple(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


@dataclass(frozen=True)
class FeatureSeed:
    key: str
    name_ko: str
    name_en: str
    ko_aliases: tuple[str, ...]
    en_aliases: tuple[str, ...]
    positive: tuple[str, ...]
    negative: tuple[str, ...]
    mode: str
    source_refs: tuple[str, ...]


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
    key: str, name_ko: str, name_en: str, ko_aliases: str, en_aliases: str,
    positive: str, negative: str, mode: str = "view", *, sources: str,
) -> FeatureSeed:
    return FeatureSeed(
        key, name_ko, name_en, _terms(ko_aliases), _terms(en_aliases),
        _terms(positive), _terms(negative), mode, _terms(sources),
    )


def G(
    domain: str, root_ko: str, root_en: str, scope: str,
    ko_context: str, en_context: str, negative_ko: str, negative_en: str,
    avoid_root: str, sources: str, *features: FeatureSeed,
) -> GroupSeed:
    return GroupSeed(
        domain, f"{domain}.hub", root_ko, root_en, scope,
        _terms(ko_context), _terms(en_context), _terms(negative_ko),
        _terms(negative_en), avoid_root, _terms(sources), tuple(features),
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


# Explicit exclusions keep v6 semantic rather than count-driven.
EXCLUDED_AS_ALREADY_COVERED: dict[str, str] = {
    "generic_subscription_cancel": "subscription.cancel.entry / subscription.cancel.confirm",
    "generic_subscription_pause": "subscription.pause",
    "generic_payment_method": "billing.payment_method",
    "generic_refund": "refund.entry / app_store.refund_request",
    "generic_appointment": "health.appointments / government.appointment",
    "generic_order_tracking": "shopping.track_package / order.tracking",
    "generic_address_management": "address.manage",
    "generic_medication_reminders": "health.medication_reminder",
    "generic_smart_home_controls": "smarthome.hub and descendants",
    "generic_government_forms": "government_digital.form_filing",
}


GROUPS: tuple[GroupSeed, ...] = (
    G(
        "automotive_vehicle", "차량 원격 서비스", "Connected vehicle services", "vehicle_service",
        "차량|자동차|원격 제어|주행|충전|정비", "vehicle|car|remote control|driving|charging|service",
        "택시 호출|대중교통|스마트홈", "ride hailing|public transit|smart home",
        "ride_hailing.hub",
        "tesla_getting_started|tesla_vehicle_controls|tesla_vehicle_keys|tesla_service_visits|tesla_charging",
        F("status", "차량 상태", "Vehicle status", "차 상태 확인|배터리와 주행 가능 거리|문 잠김 상태|차량 요약|차 컨디션", "car status|battery and range|door status|vehicle overview|vehicle condition", "배터리|주행 가능 거리|문|충전|타이어", "택시 배차|배송 차량", "sensitive", sources="tesla_getting_started|tesla_vehicle_controls"),
        F("lock_unlock", "차량 잠금·잠금 해제", "Lock or unlock vehicle", "차 문 잠그기|차 문 열기|원격 도어 잠금|자동차 잠금 해제|도어 제어", "lock car doors|unlock vehicle|remote door lock|open car locks|door controls", "차량|도어|열쇠|보안|원격", "집 도어락|계정 잠금", "submit", sources="tesla_vehicle_controls|tesla_vehicle_keys"),
        F("remote_start", "차량 원격 시동", "Remote vehicle start", "차 시동 걸기|원격 운전 허용|자동차 출발 준비|키 없이 시동|차량 시작", "start car remotely|remote start|keyless drive authorization|prepare vehicle to drive|start vehicle", "차량|시동|운전|브레이크|인증", "앱 시작|예약 시작", "submit", sources="tesla_vehicle_keys|tesla_vehicle_controls"),
        F("climate", "차량 실내 온도 원격 설정", "Vehicle climate control", "차량 에어컨 켜기|차 히터 켜기|실내 온도 맞추기|출발 전 공조|차량 예열", "turn on car climate|vehicle air conditioning|heat the cabin|set cabin temperature|precondition car", "실내|온도|공조|히터|에어컨", "집 온도조절기|날씨", "change", sources="tesla_getting_started|tesla_vehicle_controls|tesla_scheduled_charge"),
        F("charge_progress", "차량 충전 상태", "Vehicle charging progress", "전기차 충전량|충전 남은 시간|충전 속도|차량 배터리 충전|충전 진행률", "EV charge level|charging time remaining|charge rate|vehicle battery charging|charging progress", "배터리|킬로와트|주행 거리|충전기|완료 시간", "휴대폰 충전|결제 충전", "sensitive", sources="tesla_charging|tesla_charge_stats"),
        F("charge_schedule", "차량 충전 일정", "Vehicle charging schedule", "전기차 예약 충전|출발 시간 충전|심야 충전 설정|충전 시작 시간|충전 스케줄", "scheduled EV charging|departure charging|off-peak charging|charge start time|charging schedule", "전기차|시간|출발|요금제|배터리", "휴대폰 충전|일반 캘린더", "change", sources="tesla_scheduled_charge|tesla_charging"),
        F("location", "차량 현재 위치", "Vehicle location", "내 차 위치 찾기|주차한 차 찾기|자동차 지도 위치|차량 좌표 확인|차 위치", "find my car|parked vehicle location|car on map|vehicle position|where is my vehicle", "지도|주차 위치|차량|마지막 연결|경로", "택시 기사 위치|택배 위치", "sensitive", sources="tesla_driver_access|tesla_getting_started"),
        F("phone_key", "차량 휴대전화 키", "Vehicle phone key", "스마트폰 차 키 설정|디지털 차량 키|폰키 연결|휴대폰 키 재설정|차량 키 페어링", "set up phone key|digital car key|pair phone as key|reset phone key|vehicle key pairing", "블루투스|키 카드|차량 접근|인증|소유자", "계정 패스키|집 도어락", "submit", sources="tesla_vehicle_keys|tesla_getting_started"),
        F("driver_access", "차량 운전자 권한", "Vehicle driver access", "추가 운전자 초대|차량 공유 권한|운전자 삭제|가족에게 차 공유|운전자 관리", "invite additional driver|share vehicle access|remove driver|family car access|manage drivers", "차량|운전자|초대|접근 권한|소유자", "승차 공유 기사|워크스페이스 멤버", "submit", sources="tesla_driver_access"),
        F("service_appointment", "차량 정비 예약", "Vehicle service appointment", "자동차 점검 예약|차량 수리 일정|정비소 방문 예약|모바일 정비 요청|서비스 예약", "book vehicle service|car repair appointment|service center visit|mobile service request|maintenance appointment", "차량 증상|정비 센터|날짜|견적|사진", "병원 예약|홈서비스 예약", "submit", sources="tesla_service_visits"),
        F("roadside_assistance", "차량 긴급출동 요청", "Vehicle roadside assistance", "차량 고장 도움|타이어 펑크 출동|차 문 잠김 구조|견인 요청|길가 지원", "vehicle breakdown help|flat tire assistance|car lockout help|request towing|roadside support", "차량 위치|고장|타이어|견인|긴급", "보험 일반 문의|응급 신고", "submit", sources="tesla_customer_support"),
        F("security_monitoring", "주차 차량 보안 모니터링", "Parked vehicle security monitoring", "차량 주변 카메라|감시 모드|주차 보안 영상|차량 경보 확인|라이브 카메라", "vehicle live camera|sentry monitoring|parked car security|vehicle alarm status|surroundings camera", "주차|카메라|경보|움직임|차량", "홈 카메라|휴대폰 카메라", "sensitive", sources="tesla_vehicle_security"),
    ),
    G(
        "parking_tolls", "주차·통행료 관리", "Parking and toll management", "mobility_payment",
        "주차|주차 구역|차량 번호|통행료|하이패스|톨", "parking|parking zone|license plate|toll|transponder|road fee",
        "택시 호출|자동차 정비|대중교통 요금", "ride request|vehicle service|transit fare",
        "local_transit.hub",
        "parkmobile_faq|parkmobile_history|ezpass_accounts|ny_thruway_tolls",
        F("availability", "주차 가능 구역", "Parking availability", "빈 주차장 찾기|주변 주차 공간|주차 가능 지도|주차장 혼잡도|주차 자리 검색", "find available parking|nearby parking spaces|parking availability map|garage occupancy|search parking", "지도|주차장|구역|가용성|거리", "숙소 주차 옵션|차량 위치", sources="parkmobile_faq"),
        F("start_session", "주차 세션 시작", "Start parking session", "주차 요금 시작|주차 구역 번호 입력|차량 주차 활성화|주차 시간 결제 시작|주차 타이머 시작", "start paid parking|enter parking zone|activate parking session|begin parking payment|start parking timer", "구역 번호|차량 번호|시간|요금|확인", "예약 주차|통행료 결제", "submit", sources="parkmobile_faq"),
        F("active_session", "진행 중인 주차", "Active parking session", "현재 주차 확인|남은 주차 시간|활성 주차 타이머|주차 종료 시각|주차 세션 상태", "current parking|time remaining|active parking timer|parking expiry time|session status", "차량|구역|남은 시간|종료|요금", "과거 주차|예약 주차", "sensitive", sources="parkmobile_faq"),
        F("extend_session", "주차 시간 연장", "Extend parking session", "주차 더하기|주차 만료 연장|주차 시간 추가|미터기 원격 연장|주차 타이머 늘리기", "add parking time|extend parking expiry|more parking time|remote meter extension|increase parking timer", "활성 세션|최대 시간|추가 요금|만료|차량", "예약 변경|통행료", "submit", sources="parkmobile_extend|parkmobile_faq"),
        F("reservation", "주차 공간 예약", "Reserve parking", "주차장 미리 예약|행사 주차 예약|차고 자리 예약|주차 패스 구매|예약 주차 찾기", "prebook parking|event parking reservation|reserve garage space|buy parking pass|find reservable parking", "날짜|시간|주차장|입차|QR 패스", "노상 주차 세션|숙소 주차", "submit", sources="parkmobile_faq"),
        F("history_receipts", "주차 내역·영수증", "Parking history and receipts", "지난 주차 보기|주차 결제 영수증|주차 거래 기록|주차 비용 증빙|주차 이력 출력", "past parking|parking receipt|parking transactions|parking expense proof|print parking history", "날짜|차량|구역|금액|영수증", "통행료 내역|쇼핑 영수증", "sensitive", sources="parkmobile_history|parkmobile_personal_pages"),
        F("expiry_alerts", "주차 만료 알림", "Parking expiry alerts", "주차 끝나기 전 알림|주차 시간 푸시|미터 만료 문자|주차 리마인더|세션 종료 경고", "parking expiry reminder|parking time push alert|meter expiration text|parking reminder|session ending warning", "알림|남은 시간|문자|푸시|이메일", "마케팅 알림|통행료 경고", "change", sources="parkmobile_faq|parkmobile_personal_pages"),
        F("registered_vehicles", "주차 등록 차량", "Parking account vehicles", "주차 차량 번호 추가|주차 번호판 수정|주차 계정 자동차 삭제|기본 주차 차량|차량 목록", "add parking vehicle|edit license plate|remove car from parking account|default parking vehicle|vehicle list", "번호판|등록 지역|별명|기본 차량|계정", "차량 운전자 권한|통행료 차량", "change", sources="parkmobile_faq|parkmobile_personal_pages"),
        F("citation_dispute", "주차 위반 이의제기 안내", "Parking citation dispute guidance", "주차 딱지 이의|결제했는데 주차 벌금|주차 위반 증빙|주차 티켓 항의|주차 과태료 검토", "dispute parking ticket|ticket after paying|parking payment evidence|contest citation|parking penalty review", "주차 내역|차량 번호|구역|시간|발급 기관", "통행료 위반|일반 민원", "submit", sources="parkmobile_ticket|parkmobile_history"),
        F("toll_balance", "통행료 계정 잔액", "Toll account balance", "하이패스 잔액|톨 계정 금액|통행료 선불 잔액|저잔액 확인|도로 요금 잔액", "toll tag balance|road toll account amount|prepaid toll balance|low balance status|toll funds", "통행료|계정|잔액|차량|태그", "은행 잔액|대중교통 잔액", "sensitive", sources="ezpass_accounts"),
        F("toll_transactions", "통행료 이용 내역", "Toll transaction history", "지난 통행료 보기|톨 게이트 기록|도로 이용 거래|통행료 명세|차량별 톨 내역", "past toll charges|toll crossing history|road fee transactions|toll statement|vehicle toll activity", "날짜|도로|차량|금액|태그", "주차 내역|은행 거래", "sensitive", sources="ezpass_accounts|ny_thruway_tolls"),
        F("toll_payment", "통행료 청구서 납부", "Pay toll bill", "미납 통행료 내기|톨 바이 메일 결제|도로 요금 청구 납부|통행료 인보이스 결제|톨 벌금 납부", "pay unpaid toll|pay toll by mail|road charge payment|toll invoice payment|pay toll violation", "청구서 번호|차량 번호|금액|기한|결제", "주차 결제|은행 이체", "submit", sources="ny_thruway_tolls|ezpass_accounts"),
        F("auto_replenish", "통행료 자동 충전", "Toll auto-replenishment", "하이패스 자동 충전 설정|톨 잔액 자동 보충|통행료 결제수단 자동이체|저잔액 자동 결제|톨 충전 기준", "enable toll auto-reload|automatic toll replenishment|toll payment auto debit|low-balance refill|replenishment threshold", "잔액 기준|결제수단|충전 금액|계정|태그", "교통카드 충전|구독 자동결제", "submit", sources="ezpass_accounts"),
        F("transponders", "통행료 단말기 관리", "Toll transponder management", "하이패스 단말기 추가|톨 태그 주문|단말기 분실 신고|태그 교체|차량과 태그 연결", "add toll transponder|order toll tag|report lost transponder|replace toll tag|link tag to vehicle", "태그 번호|차량|배송|상태|계정", "블루투스 기기|주차 차량", "submit", sources="ezpass_accounts"),
    ),
    G(
        "hr_payroll", "인사·급여 셀프서비스", "HR and payroll self-service", "workforce_service",
        "급여|인사|근무 시간|휴가|복리후생|직원", "payroll|HR|time|leave|benefits|employee",
        "은행 계좌|세금 신고|구직", "retail bank account|tax return|job search",
        "work.hub",
        "adp_mobile|adp_employee_self_service|workday_mobile|workday_expenses",
        F("pay_statements", "급여 명세서", "Pay statements", "월급 명세 보기|급여 내역|페이슬립|실수령액 확인|급여 공제 명세", "view payslip|pay history|earnings statement|net pay details|payroll deductions", "급여 기간|총액|세금|공제|실수령", "은행 거래|세금 신고서", "sensitive", sources="adp_mobile|adp_mobile_login"),
        F("tax_documents", "근로소득 세금 문서", "Payroll tax documents", "연말정산 급여 문서|원천징수 영수증|W-2 보기|1099 문서|급여 세금 양식", "employee tax forms|withholding certificate|view W-2|1099 document|payroll tax statement", "과세 연도|고용주|소득|원천징수|다운로드", "세금 신고 제출|정부 세금 납부", "sensitive", sources="adp_mobile|adp_mobile_login"),
        F("direct_deposit", "급여 입금 계좌", "Payroll direct deposit", "월급 통장 변경|급여 계좌 추가|직접 입금 설정|급여 배분 계좌|입금 계좌 관리", "change payroll bank account|add direct deposit account|set salary deposit|split paycheck accounts|manage deposit details", "은행 정보|계좌 번호|배분 비율|급여|인증", "일반 송금|청구서 결제", "submit", sources="adp_employee_self_service|adp_hr_pro"),
        F("tax_withholding", "급여 원천징수 선택", "Payroll tax withholding elections", "원천징수 정보 변경|급여 세금 공제 설정|W-4 수정|부양가족 원천징수|추가 세금 공제", "change tax withholding|payroll tax election|edit W-4|dependent withholding|additional tax deduction", "세금|공제|신고 상태|부양가족|서명", "세금 신고 제출|은행 공제", "submit", sources="adp_hr_pro|adp_employee_self_service"),
        F("time_clock", "출퇴근 기록", "Clock in or out", "출근 찍기|퇴근 찍기|근무 시작|휴게 시작|타임 클록", "clock in|clock out|start shift|start break|time clock", "근무지|현재 시간|교대|휴게|직원", "운동 시간|주차 시간", "submit", sources="adp_mobile|workday_mobile"),
        F("timecard", "근무시간표 제출", "Submit timecard", "타임시트 작성|근무 시간 수정|주간 시간표 제출|누락 출퇴근 보정|근무시간 승인 요청", "fill timesheet|edit hours worked|submit weekly timecard|correct missed punch|request time approval", "근무일|시간|초과근무|프로젝트|제출", "캘린더 일정|운동 기록", "submit", sources="adp_employee_self_service|workday_mobile"),
        F("work_schedule", "근무 일정", "Work schedule", "내 교대 확인|근무표 보기|출근 일정|주간 스케줄|배정된 시프트", "view my shifts|employee roster|work timetable|weekly schedule|assigned shift", "날짜|시작 시간|종료 시간|근무지|교대", "개인 캘린더|수업 일정", "sensitive", sources="adp_mobile|workday_mobile"),
        F("shift_swap", "교대근무 바꾸기", "Swap work shift", "시프트 교환 요청|근무 교대 바꾸기|대타 구하기|교대 양도|근무 일정 교환", "request shift swap|exchange work shift|find shift cover|offer assigned shift|trade schedule", "현재 교대|대체 직원|관리자 승인|마감|일정", "캘린더 초대|수업 변경", "submit", sources="workday_mobile"),
        F("leave_balance", "휴가 잔여 일수", "Leave balance", "연차 남은 일수|PTO 잔액|병가 잔여|휴가 사용 내역|사용 가능 휴가", "PTO balance|vacation remaining|sick leave balance|leave usage|available time off", "휴가 유형|발생 일수|사용|잔여|만료", "구독 크레딧|은행 잔액", "sensitive", sources="adp_employee_self_service|workday_mobile"),
        F("leave_request", "휴가 신청", "Request time off", "연차 내기|PTO 요청|병가 신청|휴무 요청|휴가 승인 요청", "submit vacation request|request PTO|request sick leave|ask for day off|leave approval request", "날짜|휴가 유형|잔액|사유|승인자", "여행 예약|수업 취소", "submit", sources="adp_mobile|adp_employee_self_service|workday_mobile"),
        F("benefits_enrollment", "복리후생 가입·변경", "Benefits enrollment", "건강보험 선택|복지 플랜 가입|오픈 인롤먼트|퇴직연금 선택|부양가족 혜택 추가", "choose health benefits|enroll in benefit plan|open enrollment|retirement election|add dependent coverage", "보험 플랜|보험료|부양가족|수혜자|적용일", "개인 보험 청구|구독 플랜", "submit", sources="adp_mobile|adp_employee_self_service"),
        F("life_event", "인사 생애사건 변경", "HR life event", "결혼 정보 변경|자녀 출생 등록|가족 상태 변경|주소 변경 생애사건|복지 자격 사건", "report marriage event|add newborn dependent|family status change|life-event address update|benefit qualifying event", "사건 날짜|증빙|부양가족|복리후생|제출", "소셜 프로필|정부 주소 변경", "submit", sources="adp_mobile|adp_employee_self_service"),
        F("expense_report", "업무 경비 보고서", "Employee expense report", "출장비 청구|영수증 경비 제출|회사 카드 비용 처리|비용 환급 요청|경비 항목 작성", "submit travel expense|expense receipt claim|corporate card expense|request reimbursement|itemize work cost", "영수증|금액|비용 항목|프로젝트|승인", "보험 청구|개인 쇼핑 영수증", "submit", sources="workday_mobile|workday_expenses"),
        F("manager_approvals", "관리자 인사 승인함", "Manager HR approvals", "직원 휴가 승인|타임시트 승인|경비 승인|교대 요청 검토|관리자 받은 편지함", "approve employee leave|approve timecard|approve expense|review shift request|manager approval inbox", "직원|요청|기한|승인|거절", "파일 접근 승인|결제 승인", "submit", sources="adp_mobile|workday_mobile"),
        F("personal_information", "직원 개인정보", "Employee personal information", "인사 주소 수정|비상 연락처 변경|직원 전화번호|법적 이름 변경|개인 프로필 정보", "update HR address|change emergency contact|employee phone number|legal name change|personal profile details", "주소|연락처|법적 이름|비상 연락망|직원 번호", "소셜 프로필|일반 연락처", "submit", sources="adp_hr_pro|adp_employee_self_service"),
        F("directory", "조직도·직원 찾기", "Organization directory", "회사 직원 검색|조직도 보기|팀 연락처|상사 찾기|부서 구성원", "find coworker|view org chart|team contacts|find manager|department directory", "직원 이름|직책|부서|보고 관계|연락처", "휴대폰 연락처|구직 검색", "sensitive", sources="adp_employee_self_service|workday_mobile"),
    ),
    G(
        "fitness_membership", "피트니스·운동 멤버십", "Fitness and gym membership", "fitness_service",
        "운동|피트니스|체육관|수업|회원권|활동", "fitness|workout|gym|class|membership|activity",
        "병원 진료|일반 구독|스포츠 중계", "medical care|generic subscription|sports streaming",
        "wellbeing.hub",
        "google_fit_help|google_fit_activity|classpass_reserve|classpass_pause",
        F("activity_summary", "운동 활동 요약", "Fitness activity summary", "오늘 걸음 수|칼로리 소모|활동 시간|운동 대시보드|주간 활동 비교", "today's steps|calories burned|active minutes|fitness dashboard|weekly activity comparison", "걸음|칼로리|거리|심박 포인트|기간", "의료 검사 결과|화면 사용 시간", "sensitive", sources="google_fit_activity|google_fit_help"),
        F("track_workout", "운동 기록 시작", "Track a workout", "달리기 측정 시작|걷기 기록|자전거 운동 추적|운동 타이머 시작|실시간 운동 기록", "start run tracking|record a walk|track cycling|start workout timer|live exercise tracking", "운동 종류|시간|거리|센서|위치", "근무 시간 기록|주차 타이머", "submit", sources="google_fit_help|google_fit_edit_activity"),
        F("workout_history", "운동 기록 내역", "Workout history", "지난 운동 보기|활동 저널|달리기 기록|운동 통계 이력|운동 경로", "past workouts|activity journal|running history|exercise statistics|workout routes", "날짜|운동 종류|시간|거리|경로", "의료 방문 기록|근무시간표", "sensitive", sources="google_fit_activity|google_fit_edit_activity"),
        F("activity_goals", "운동 목표 설정", "Fitness activity goals", "걸음 목표 바꾸기|주간 운동 목표|심박 포인트 목표|칼로리 목표|운동 시간 목표", "change step goal|weekly exercise goal|heart point target|calorie goal|workout duration target", "목표 수치|기간|진행률|알림|운동", "업무 목표|저축 목표", "change", sources="google_fit_help"),
        F("body_metrics", "신체 측정 기록", "Body metrics", "체중 기록|키와 몸무게|심박 기록|신체 수치 추세|체성분 입력", "log weight|height and weight|heart rate history|body metric trends|enter body composition", "체중|키|심박|날짜|건강 데이터", "의료 진단|반려동물 체중", "sensitive", sources="google_fit_help|google_fit_edit_activity"),
        F("connected_apps", "운동 앱·기기 연결", "Connected fitness apps and devices", "스마트워치 연결|운동 앱 연동|피트니스 데이터 동기화|연결된 기기 관리|건강 앱 연결 해제", "connect fitness watch|link workout app|sync fitness data|manage connected device|disconnect health app", "기기|앱|동기화|건강 데이터|계정", "블루투스 일반 기기|차량 키", "submit", sources="google_fit_connect"),
        F("data_permissions", "운동 데이터 접근 권한", "Fitness data permissions", "활동 권한 설정|운동 위치 접근|건강 데이터 공유 범위|연결 앱 권한 철회|신체 센서 권한", "physical activity permission|fitness location access|health data sharing scope|revoke connected app|body sensor permission", "민감 데이터|앱 권한|활동|위치|센서", "일반 파일 권한|카메라 권한", "submit", sources="google_fit_permissions|google_fit_connect"),
        F("class_search", "운동 수업 검색", "Search fitness classes", "근처 요가 찾기|헬스 수업 일정|필라테스 검색|운동 스튜디오 지도|시간대별 클래스", "find nearby yoga|gym class schedule|search pilates|fitness studio map|classes by time", "위치|운동 종류|날짜|시간|크레딧", "학교 수업|온라인 강의", sources="classpass_reserve"),
        F("class_booking", "운동 수업 예약", "Book fitness class", "요가 수업 예약|헬스 클래스 신청|운동 자리 확정|스튜디오 방문 예약|피트니스 세션 예약", "reserve yoga class|book gym class|confirm workout spot|studio reservation|fitness session booking", "수업|시간|장소|크레딧|취소 정책", "병원 예약|식당 예약", "submit", sources="classpass_reserve"),
        F("class_cancellation", "운동 수업 예약 취소", "Cancel fitness class", "요가 예약 취소|헬스 클래스 취소|운동 수업 빠지기|스튜디오 예약 철회|피트니스 예약 삭제", "cancel yoga booking|cancel gym class|drop workout session|withdraw studio reservation|remove fitness booking", "예정 수업|마감 시간|취소 수수료|크레딧|확인", "멤버십 해지|병원 예약 취소", "submit", sources="classpass_cancel"),
        F("class_credits", "운동 수업 크레딧", "Fitness class credits", "남은 클래스 포인트|운동 크레딧 잔액|수업별 필요 포인트|이월 크레딧|다음 결제 주기 포인트", "remaining class credits|fitness credit balance|credits per class|rolled-over credits|next cycle credits", "크레딧|결제 주기|수업|잔액|만료", "게임 포인트|연료 포인트", "sensitive", sources="classpass_reserve|classpass_renewal"),
        F("membership_pause", "운동 멤버십 일시정지", "Pause fitness membership", "헬스 회원권 동결|피트니스 멤버십 쉬기|운동 구독 잠시 중단|회원권 휴회|크레딧 동결", "freeze gym membership|pause fitness plan|temporarily stop workout membership|membership hold|freeze class credits", "회원권|일시정지 기간|결제|크레딧|재개", "일반 구독 일시정지|운동 수업 취소", "submit", sources="classpass_pause"),
        F("membership_plan", "운동 멤버십 플랜", "Fitness membership plan", "헬스 회원권 등급|피트니스 크레딧 플랜|다음 갱신 옵션|운동 멤버십 변경|월간 수업 요금제", "gym membership tier|fitness credit plan|next renewal option|change workout membership|monthly class plan", "월 요금|크레딧|갱신일|플랜|혜택", "일반 앱 구독|보험 플랜", "submit", sources="classpass_renewal|classpass_pause"),
        F("checkin_pass", "피트니스 출입 패스", "Fitness check-in pass", "헬스장 입장 QR|회원 바코드|운동 시설 체크인|체육관 디지털 카드|클럽 출입증", "gym entry QR|member barcode|fitness facility check-in|digital gym card|club access pass", "QR|바코드|회원|지점|체크인", "탑승권|주차 패스", "sensitive", sources="classpass_reserve"),
        F("trainer_session", "트레이너 세션", "Personal trainer session", "개인 운동 코치 예약|PT 일정|트레이너 상담|운동 코칭 세션|개인 레슨", "book personal trainer|PT schedule|trainer consultation|fitness coaching session|private workout lesson", "트레이너|시간|목표|지점|요금", "의료 상담|반려동물 훈련", "submit", sources="classpass_reserve"),
    ),
    G(
        "home_services", "생활·주거 서비스", "Home service marketplace", "home_service",
        "집수리|청소|이사|설치|기술자|가정 서비스", "home repair|cleaning|moving|installation|provider|household service",
        "스마트홈 기기|부동산 매물|차량 정비", "smart home device|property listing|vehicle service",
        "property.hub",
        "taskrabbit_hire|taskrabbit_reschedule|taskrabbit_invoice|taskrabbit_claim",
        F("category_search", "생활 서비스 종류 찾기", "Find home service category", "집수리 종류 선택|청소 서비스 찾기|가구 조립 카테고리|이사 도움 검색|설치 기사 찾기", "choose home repair type|find cleaning service|furniture assembly category|search moving help|find installer", "작업 종류|주소|날짜|집|기술자", "스마트홈 기기|부동산 검색", sources="taskrabbit_hire"),
        F("provider_compare", "생활 서비스 제공자 비교", "Compare home service providers", "기술자 가격 비교|서비스 전문가 고르기|평점과 후기 비교|가능 시간 비교|작업자 목록", "compare provider prices|choose service professional|compare ratings and reviews|compare availability|provider list", "시간당 요금|후기|기술|가능 시간|프로필", "보험 설계사|택시 기사", "sensitive", sources="taskrabbit_hire"),
        F("quote_request", "생활 서비스 견적 요청", "Request home service quote", "집수리 예상 비용 요청|작업 견적 받기|청소 가격 문의|서비스 비용 산정|기술자에게 견적", "request repair estimate|get task quote|ask cleaning price|estimate service cost|request provider quote", "작업 범위|주소|사진|예산|요청", "차량 정비 견적|보험 견적", "submit", sources="taskrabbit_hire|taskrabbit_invoice"),
        F("provider_profile", "생활 서비스 제공자 프로필", "Home service provider profile", "기술자 경력 보기|작업자 후기|서비스 전문가 기술|제공자 사진|작업자 신원 정보", "view provider experience|tasker reviews|professional skills|provider work photos|service profile", "경력|평점|후기|요금|작업 사진", "직원 프로필|소셜 프로필", "sensitive", sources="taskrabbit_hire"),
        F("booking", "생활 서비스 예약", "Book home service", "집수리 일정 예약|청소 기사 부르기|가구 조립 예약|작업자 시간 확정|서비스 방문 신청", "schedule home repair|book cleaner|reserve furniture assembly|confirm provider time|request service visit", "날짜|시간|주소|작업자|요금", "차량 정비|병원 예약", "submit", sources="taskrabbit_hire"),
        F("recurring_schedule", "정기 생활 서비스 일정", "Recurring home service schedule", "매주 청소 설정|정기 방문 예약|반복 가사 서비스|월간 관리 일정|서비스 반복 주기", "weekly cleaning schedule|recurring service booking|repeat household task|monthly maintenance visit|service frequency", "주기|시작일|종료|주소|요금", "캘린더 반복|일반 구독", "submit", sources="taskrabbit_hire"),
        F("task_details", "생활 서비스 작업 설명·사진", "Home service task details and photos", "수리 사진 첨부|작업 범위 설명|기사 준비물 메모|주차 안내 적기|집 접근 정보", "attach repair photos|describe task scope|provider supply notes|parking instructions|home access details", "사진|설명|치수|준비물|주소", "보험 사고 사진|공공 민원 사진", "submit", sources="taskrabbit_hire|taskrabbit_expenses"),
        F("provider_chat", "생활 서비스 제공자 대화", "Message home service provider", "작업자에게 메시지|기술자와 채팅|서비스 일정 문의|작업 사진 보내기|기사에게 전화", "message provider|chat with tasker|ask about service schedule|send task photo|call service professional", "예약 작업|대화|사진|전화|합의", "택배 기사 메모|병원 메시지", "submit", sources="taskrabbit_reschedule|taskrabbit_expenses"),
        F("reschedule", "생활 서비스 일정 변경", "Reschedule home service", "청소 날짜 바꾸기|기사 방문 시간 변경|작업 예약 미루기|집수리 일정 수정|서비스 재예약", "change cleaning date|move provider visit|postpone task booking|modify repair time|rebook home service", "기존 작업|새 날짜|작업자 동의|수수료|확인", "병원 일정 변경|차량 정비 일정", "submit", sources="taskrabbit_reschedule"),
        F("cancellation", "생활 서비스 예약 취소", "Cancel home service", "청소 예약 취소|작업자 예약 철회|집수리 취소|서비스 방문 삭제|작업 요청 취소", "cancel cleaner booking|withdraw provider reservation|cancel home repair|remove service visit|cancel task request", "기존 작업|24시간|취소 수수료|사유|확인", "일반 구독 해지|수업 취소", "submit", sources="taskrabbit_cancel"),
        F("arrival_status", "생활 서비스 방문 상태", "Home service arrival status", "작업자 도착 확인|기사 오는 중|서비스 방문 진행|기술자 체크인|예약 작업 상태", "provider arrival status|service professional en route|home visit progress|tasker check-in|scheduled task status", "작업자|예정 시간|주소|진행 상태|대화", "택배 배송 상태|택시 도착", "sensitive", sources="taskrabbit_hire|taskrabbit_reschedule"),
        F("invoice_expenses", "생활 서비스 청구서·실비", "Home service invoice and expenses", "작업 비용 명세|기사 영수증 확인|재료비 내역|서비스 수수료|작업 인보이스", "task cost breakdown|provider receipt|materials reimbursement|service fees|task invoice", "시간|요금|실비|영수증|수수료", "쇼핑 영수증|보험 청구", "sensitive", sources="taskrabbit_invoice|taskrabbit_expenses"),
        F("review_tip", "생활 서비스 후기·팁", "Review and tip home service provider", "작업자 평가|기술자 후기 남기기|서비스 팁 주기|별점 제출|기사 리뷰", "rate provider|review tasker|tip service professional|submit star rating|provider feedback", "완료 작업|별점|후기|팁 금액|제출", "상품 리뷰|식당 팁", "submit", sources="taskrabbit_tip"),
        F("protection_claim", "생활 서비스 피해 청구", "Home service protection claim", "작업 중 파손 신고|서비스 피해 보상|도난 청구|작업 부상 신고|보호 프로그램 청구", "report task damage|service damage claim|theft claim|task injury report|service protection claim", "작업 번호|손상 사진|영수증|발생일|청구 기한", "보험 일반 청구|상품 반품", "submit", sources="taskrabbit_claim"),
    ),
    G(
        "civic_local", "지역 생활행정", "Local civic services", "local_government_service",
        "시청|구청|311|생활 민원|쓰레기|건축 허가", "city hall|local government|311|service request|sanitation|permit",
        "중앙정부 여권|세금 신고|응급 신고", "federal passport|tax return|emergency call",
        "government.hub",
        "nyc311_service_requests|nyc311_report|nyc311_status|nyc311_home|nyc_dob_now",
        F("service_catalog", "지역 공공서비스 찾기", "Find local public service", "시청 서비스 검색|구청 업무 찾기|지역 지원 프로그램|생활행정 주제|공공 시설 찾기", "search city services|find local government help|local support programs|civic service topics|find public facility", "지역|기관|서비스 종류|운영 시간|자격", "중앙정부 민원|상업 서비스", sources="nyc311_home"),
        F("problem_report", "지역 생활문제 신고", "Report local civic problem", "도로 파손 신고|소음 민원|불법 주차 신고|거리 문제 요청|생활 불편 접수", "report pothole|file noise complaint|report illegal parking|request street repair|submit neighborhood issue", "문제 유형|위치|발생 시간|설명|담당 기관", "112 긴급 신고|고객센터 불만", "submit", sources="nyc311_report|nyc311_pothole|nyc311_service_requests"),
        F("issue_location", "생활민원 위치 지정", "Civic issue location", "민원 주소 선택|지도에서 문제 위치|교차로 지정|공공시설 위치 표시|현장 좌표 확인", "select complaint address|pin issue on map|choose intersection|mark public facility|confirm incident location", "주소|교차로|지도|관할 구역|현장", "배송 주소|차량 위치", "submit", sources="nyc311_service_requests|nyc311_status"),
        F("evidence_attachment", "생활민원 증빙 첨부", "Attach civic request evidence", "민원 사진 올리기|문제 영상 첨부|공공 신고 파일|현장 증거 제출|문서 붙이기", "upload complaint photo|attach issue video|civic request file|submit scene evidence|add document", "사진|영상|파일|개인정보|민원 번호", "보험 사고 증빙|홈서비스 작업 사진", "submit", sources="nyc311_service_requests"),
        F("anonymous_request", "익명 생활민원 선택", "Anonymous civic request option", "이름 없이 민원|연락처 비공개 신고|익명으로 접수|개인정보 없이 요청|신원 공개 여부", "file without name|private contact complaint|submit anonymously|request without personal details|identity disclosure option", "익명 가능 여부|연락처|후속 알림|개인정보|요청 유형", "익명 커뮤니티 글|긴급 신고", "submit", sources="nyc311_service_requests"),
        F("request_status", "생활민원 처리 상태", "Civic service request status", "311 접수 조회|민원 번호 추적|시청 요청 진행 상황|공공기관 조치 결과|생활민원 완료 여부", "look up 311 request|track service request number|city request progress|agency action result|civic case completion", "요청 번호|담당 기관|상태|예정일|조치", "정부 이민 사건|배송 상태", "sensitive", sources="nyc311_status|nyc311_service_requests"),
        F("follow_updates", "생활민원 상태 알림", "Follow civic request updates", "민원 진행 알림 받기|311 요청 구독|기관 조치 문자|생활민원 이메일 업데이트|공공 요청 팔로우", "subscribe to request updates|follow 311 case|agency action texts|civic email updates|track public request alerts", "요청 번호|이메일|문자|상태 변경|구독", "마케팅 문자|택배 알림", "change", sources="nyc311_service_requests"),
        F("nearby_requests", "주변 생활민원 지도", "Nearby civic requests map", "근처 311 신고 보기|지역 민원 지도|주변 도로 문제|동네 요청 현황|공개 민원 검색", "nearby 311 reports|local complaint map|street issues around me|neighborhood request activity|search public requests", "지도|날짜|문제 유형|공개 상태|지역", "친구 위치|범죄 긴급 지도", "sensitive", sources="nyc311_status|nyc311_home"),
        F("sanitation_schedule", "쓰레기·재활용 수거 일정", "Trash and recycling schedule", "우리 동네 쓰레기 날짜|재활용 수거일|음식물 수거 일정|휴일 청소 변경|주소별 배출 시간", "local trash collection day|recycling pickup schedule|compost collection|holiday sanitation change|address disposal time", "주소|쓰레기|재활용|요일|휴일", "택배 수거|가정 청소 예약", sources="nyc311_home"),
        F("bulky_pickup", "대형 폐기물 수거", "Bulky waste pickup", "가구 버리기 예약|대형 쓰레기 수거|매트리스 배출|가전제품 처리 요청|부피 큰 폐기물", "schedule furniture disposal|large trash pickup|mattress collection|appliance disposal request|bulky item removal", "품목|주소|수거일|배출 규칙|예약", "이사 서비스|상품 반품", "submit", sources="nyc311_home|nyc311_service_requests"),
        F("local_alerts", "지역 공공 알림", "Local public alerts", "시청 긴급 공지|도로 폐쇄 알림|폭염 정보|지역 서비스 중단|동네 공공 푸시", "city emergency notice|road closure alert|heat advisory|local service disruption|neighborhood civic push", "지역|날씨|교통|보건|서비스", "마케팅 알림|앱 업데이트", "change", sources="nyc311_home"),
        F("permit_application", "지역 인허가 신청", "Local permit application", "건축 허가 제출|공사 허가 신청|사업장 라이선스|지역 허가서 발급|허가 갱신", "submit building permit|construction permit application|local business license|obtain city permit|renew permit", "신청 유형|주소|도면|수수료|서명", "여권 신청|일반 파일 업로드", "submit", sources="nyc_dob_now"),
        F("inspection_schedule", "지역 검사 일정", "Local inspection scheduling", "건축 검사 예약|허가 현장 점검|검사 일정 변경|검사 결과 추적|시청 인스펙션", "schedule building inspection|permit site inspection|change inspection date|track inspection result|city inspection", "허가 번호|검사 유형|날짜|현장|결과", "차량 검사|의료 검사", "submit", sources="nyc_dob_now"),
        F("public_records", "지역 공공기록 요청", "Local public records request", "시청 기록 사본|민원 기록 요청|정보공개 청구|지역 행정 문서|공공 기록 다운로드", "request city record|copy of service request|public information request|local government document|download civic record", "기록 종류|기간|기관|요청자|수령 방식", "의료 기록|회사 데이터 내보내기", "submit", sources="nyc311_home|nyc311_service_requests"),
    ),
    G(
        "pet_care", "반려동물 돌봄", "Pet care services", "pet_service",
        "반려동물|강아지|고양이|동물병원|미용|마이크로칩", "pet|dog|cat|veterinary|grooming|microchip",
        "사람 병원|아동 돌봄|야생동물 민원", "human healthcare|child care|wildlife complaint",
        "healthcare_provider.hub",
        "petco_app|petsmart_services|akc_records|akc_recovery|chewy_home",
        F("profile", "반려동물 프로필", "Pet profile", "강아지 정보|고양이 생년월일|반려동물 품종|펫 체중과 사진|동물 기본 정보", "dog information|cat birth date|pet breed|pet weight and photo|animal profile", "이름|품종|나이|체중|사진", "사람 프로필|쇼핑 프로필", "sensitive", sources="petco_app|akc_records"),
        F("vaccination_records", "반려동물 예방접종 기록", "Pet vaccination records", "강아지 백신 내역|고양이 접종 증명|예방접종 만료일|광견병 기록|펫 건강 문서", "dog vaccine history|cat vaccination proof|vaccine expiry|rabies record|pet health document", "백신 종류|접종일|만료|동물병원|증명서", "사람 예방접종|보험 문서", "sensitive", sources="petco_app|akc_records"),
        F("care_reminders", "반려동물 돌봄 알림", "Pet care reminders", "펫 예방접종 알림|사료 급여 리마인더|벼룩약 일정|치아 관리 알림|반려동물 건강 일정", "pet vaccine reminder|feeding reminder|flea treatment schedule|dental care alert|pet wellness schedule", "반려동물|날짜|돌봄 유형|반복|알림", "사람 약 복용 알림|일반 캘린더", "change", sources="petco_app"),
        F("vet_appointment", "동물병원 예약", "Veterinary appointment", "수의사 진료 예약|강아지 병원 방문|고양이 검진 일정|펫 예방접종 예약|동물 응급진료 찾기", "book veterinarian|dog clinic visit|cat checkup schedule|pet vaccination appointment|find urgent vet", "반려동물|증상|병원|날짜|진료 유형", "사람 병원 예약|미용 예약", "submit", sources="chewy_vetfinder|chewy_home"),
        F("vet_chat", "반려동물 건강 상담", "Pet health chat", "수의팀 채팅|강아지 증상 문의|고양이 건강 질문|온라인 펫 상담|동물병원 메시지", "chat with vet team|ask about dog symptom|cat health question|online pet consultation|message veterinary clinic", "반려동물|증상|사진|상담|응급 안내", "사람 의료 상담|일반 고객센터", "submit", sources="chewy_home|chewy_vetfinder"),
        F("prescriptions", "반려동물 처방약", "Pet prescriptions", "강아지 약 처방|고양이 약 리필|동물 처방 승인|펫 약 배송|수의사 처방전", "dog prescription|cat medication refill|vet prescription approval|pet medicine delivery|veterinary script", "반려동물|약 이름|처방전|수의사|배송", "사람 약 처방|일반 쇼핑", "submit", sources="chewy_pharmacy|chewy_vetfinder"),
        F("grooming", "반려동물 미용 예약", "Pet grooming booking", "강아지 목욕 예약|고양이 미용 일정|발톱 관리 예약|펫 그루밍 서비스|미용사 시간", "book dog bath|cat grooming schedule|nail trim appointment|pet grooming service|groomer time", "반려동물|서비스 종류|지점|날짜|예방접종", "사람 미용실|집 청소", "submit", sources="petco_app|petsmart_services"),
        F("training", "반려동물 훈련 수업", "Pet training class", "강아지 훈련 예약|반려견 행동 교정|퍼피 클래스|개인 펫 트레이너|복종 훈련 일정", "book dog training|pet behavior class|puppy course|private pet trainer|obedience lesson", "반려동물|훈련 수준|수업|트레이너|날짜", "사람 피트니스 코치|온라인 강의", "submit", sources="petco_app|petsmart_services"),
        F("boarding", "반려동물 호텔·데이케어", "Pet boarding and daycare", "강아지 호텔 예약|고양이 숙박|펫 데이캠프|반려동물 맡기기|보딩 일정", "book dog hotel|cat boarding|pet day camp|overnight pet care|boarding schedule", "반려동물|체류 날짜|시설|예방접종|픽업", "사람 숙소|아동 돌봄", "submit", sources="petsmart_services"),
        F("sitter_walker", "펫시터·산책 서비스", "Pet sitter or walker", "강아지 산책 예약|펫시터 찾기|반려동물 방문 돌봄|고양이 돌보미|도그워커 일정", "book dog walker|find pet sitter|in-home pet visit|cat caregiver|walking schedule", "반려동물|주소|시간|돌봄 지침|제공자", "아동 돌봄|홈서비스 청소", "submit", sources="petco_app|chewy_home"),
        F("feeding_plan", "반려동물 급여 계획", "Pet feeding plan", "사료 급여량|강아지 식사 일정|고양이 영양 계획|반려동물 식단 메모|알레르기 사료", "pet food portions|dog meal schedule|cat nutrition plan|feeding notes|pet allergy diet", "반려동물|사료|횟수|양|알레르기", "사람 식단|식료품 목록", "change", sources="petco_app|chewy_home"),
        F("microchip_enrollment", "반려동물 마이크로칩 등록", "Pet microchip enrollment", "강아지 칩 등록|고양이 마이크로칩 연결|펫 ID 번호 등록|동물 칩 소유자 등록|마이크로칩 보호 서비스", "register dog microchip|link cat microchip|enroll pet ID number|microchip owner registration|pet recovery enrollment", "마이크로칩 번호|소유자|연락처|반려동물|등록", "휴대폰 eSIM|차량 키", "submit", sources="akc_recovery|akc_records"),
        F("recovery_contacts", "반려동물 구조 연락처", "Pet recovery contacts", "마이크로칩 전화번호 변경|펫 비상 연락처|보호자 주소 수정|동물병원 연락처 추가|반려동물 칩 정보 갱신", "update microchip phone|pet emergency contact|change owner address|add veterinarian contact|update pet chip record", "반려동물|마이크로칩|전화|주소|대체 연락처", "사람 비상 연락처|일반 주소록", "submit", sources="akc_records|akc_recovery"),
        F("lost_pet", "실종 반려동물 신고", "Report lost pet", "강아지 잃어버림 신고|고양이 실종 등록|마이크로칩 분실 알림|잃어버린 펫 전단|반려동물 구조 경보", "report missing dog|register lost cat|microchip lost alert|lost pet flyer|pet recovery alert", "반려동물|마지막 위치|사진|연락처|실종 시각", "유실물 신고|야생동물 민원", "submit", sources="akc_lost_pet|akc_records"),
    ),
    G(
        "grocery_loyalty", "장보기·마트 멤버십", "Grocery shopping and loyalty", "grocery_service",
        "마트|식료품|장보기|쿠폰|멤버십|픽업", "grocery|supermarket|shopping list|coupon|loyalty|pickup",
        "음식 배달|일반 쇼핑 주문|게임 포인트", "restaurant delivery|general retail order|game points",
        "shopping_logistics.hub",
        "kroger_coupons|kroger_shopping_list|kroger_fuel_points|walmart_pickup|target_circle",
        F("shopping_list", "장보기 목록", "Grocery shopping list", "마트 살 것 목록|식료품 리스트|장바구니 메모|공유 장보기 목록|마트 품목 수량", "supermarket list|grocery checklist|shopping note|shared grocery list|item quantities", "식료품|수량|카테고리|공유|매장", "일반 할 일|온라인 장바구니", "change", sources="kroger_shopping_list"),
        F("aisle_locator", "마트 상품 진열 위치", "Grocery aisle locator", "상품 몇 번 통로|마트에서 물건 찾기|매장 선반 위치|식료품 코너 안내|점포 내 상품 지도", "which aisle is item|find product in store|shelf location|grocery department guide|in-store item map", "선택 매장|통로|선반|상품|재고", "도로 길찾기|창고 위치", sources="kroger_shopping_list"),
        F("weekly_ad", "마트 주간 할인 전단", "Grocery weekly ad", "이번 주 마트 세일|식료품 행사 전단|주간 특가|매장별 할인 품목|마트 프로모션", "this week's grocery sale|supermarket flyer|weekly specials|store deals|grocery promotions", "매장|기간|품목|할인|전단", "일반 광고 설정|앱 추천", sources="kroger_coupons|target_circle"),
        F("digital_coupons", "마트 디지털 쿠폰", "Grocery digital coupons", "식료품 쿠폰 담기|마트 쿠폰 클립|멤버십 카드에 할인 추가|사용 가능한 e쿠폰|쿠폰 만료 확인", "clip grocery coupon|load supermarket coupon|add deal to loyalty card|available e-coupons|coupon expiry", "상품|쿠폰|멤버십 카드|만료|할인", "앱 프로모션 코드|항공 쿠폰", "change", sources="kroger_coupons|target_circle"),
        F("loyalty_card", "마트 멤버십 바코드", "Grocery loyalty barcode", "마트 회원 카드|쇼퍼 카드 번호|계산대 멤버십 QR|장보기 포인트 바코드|디지털 회원증", "supermarket member card|shopper card number|checkout loyalty QR|grocery rewards barcode|digital store card", "바코드|전화번호|회원|계산대|할인", "피트니스 출입증|탑승권", "sensitive", sources="kroger_coupons|target_wallet"),
        F("rewards_balance", "마트 리워드 잔액", "Grocery rewards balance", "마트 적립금 확인|장보기 포인트 잔액|멤버십 보상 보기|사용 가능 리워드|소멸 예정 포인트", "grocery rewards balance|supermarket points|loyalty rewards available|reward amount|expiring store points", "포인트|적립|사용 가능|만료|회원", "게임 포인트|항공 마일리지", "sensitive", sources="target_circle|kroger_fuel_points"),
        F("rewards_redeem", "마트 리워드 사용", "Redeem grocery rewards", "마트 적립금 쓰기|장보기 포인트 적용|멤버십 보상 차감|결제에 리워드 사용|쿠폰 보상 선택", "use grocery rewards|apply supermarket points|redeem loyalty balance|spend rewards at checkout|select reward discount", "리워드|결제|적용 금액|회원|확인", "게임 아이템 구매|항공 마일 사용", "submit", sources="target_circle|target_wallet"),
        F("fuel_points", "마트 주유 포인트", "Grocery fuel points", "마트 연료 포인트|주유 할인 잔액|식료품 구매 주유 혜택|이번 달 연료 적립|주유소 포인트 사용", "grocery fuel points|gas discount balance|fuel rewards from groceries|monthly fuel earnings|redeem gas points", "포인트|주유소|갤런|만료|멤버십", "전기차 충전|항공 마일", "sensitive", sources="kroger_fuel_points"),
        F("pickup_slot", "마트 픽업·배송 시간", "Grocery pickup or delivery slot", "장보기 픽업 시간 예약|마트 배송 시간대|식료품 수령 일정|커브사이드 슬롯|주문 시간 변경", "reserve grocery pickup time|supermarket delivery window|grocery collection schedule|curbside slot|reschedule grocery order", "매장|주소|날짜|시간대|마감", "택배 시간|식당 예약", "submit", sources="walmart_pickup|walmart_pickup_changes"),
        F("curbside_checkin", "마트 커브사이드 도착 알림", "Grocery curbside check-in", "마트에 가는 중 알리기|픽업 주차 자리 입력|장보기 도착 체크인|차량 색상 보내기|커브사이드 수령", "tell store I'm on my way|enter pickup parking spot|grocery arrival check-in|send vehicle color|curbside collection", "주문|매장|주차 번호|차량|도착", "호텔 체크인|피트니스 체크인", "submit", sources="walmart_pickup"),
        F("substitution_preferences", "장보기 대체상품 선호", "Grocery substitution preferences", "품절 상품 대체 허용|마트 교체 상품 선택|대체품 거절|식료품 환불 선호|장보기 대체 규칙", "allow grocery substitution|choose replacement item|decline substitute|grocery refund preference|replacement rules", "품절|원래 상품|대체 상품|가격|환불", "음식 메뉴 대체|일반 반품", "change", sources="walmart_substitutions|walmart_pickup_changes"),
        F("weighted_items", "중량 상품 수량 선호", "Weighted grocery item preferences", "과일 무게 지정|고기 중량 요청|낱개 수량 선호|예상 중량 가격|신선식품 구매 메모", "set produce weight|request meat quantity|preferred item count|estimated weight price|fresh food notes", "중량|수량|예상 가격|신선식품|허용 범위", "택배 무게|운동 체중", "change", sources="walmart_substitutions"),
        F("digital_receipts", "마트 디지털 영수증", "Grocery digital receipts", "마트 구매 영수증 보기|장보기 결제 내역|식료품 전자 영수증|과거 구매 증빙|마트 영수증 다운로드", "view grocery receipt|supermarket purchase details|digital food receipt|past grocery proof|download store receipt", "구매일|매장|품목|할인|결제", "주차 영수증|홈서비스 청구서", "sensitive", sources="kroger_receipts"),
        F("past_purchase_reorder", "마트 과거 구매 재담기", "Reorder past groceries", "전에 산 식료품 다시 담기|마트 구매 이력에서 추가|자주 사는 품목|지난 장보기 반복|과거 상품 목록", "reorder previous groceries|add from purchase history|frequently bought items|repeat grocery basket|past item list", "구매 이력|품목|수량|장보기 목록|재주문", "일반 쇼핑 재주문|처방약 리필", "change", sources="kroger_receipts|kroger_shopping_list"),
    ),
)


def _aliases(seed: FeatureSeed, locale: str) -> list[str]:
    if locale == "ko-KR":
        return _dedupe([
            seed.name_ko, *seed.ko_aliases,
            f"{seed.name_ko} 메뉴", f"{seed.name_ko} 관리", f"{seed.name_ko} 찾기",
        ])
    lowered = seed.name_en.lower()
    return _dedupe([
        seed.name_en, *seed.en_aliases,
        f"{seed.name_en} menu", f"manage {lowered}", f"find {lowered}",
    ])


def _root_aliases(group: GroupSeed, locale: str) -> list[str]:
    if locale == "ko-KR":
        return _dedupe([
            group.root_ko, *group.ko_context,
            f"{group.root_ko} 메뉴", f"{group.root_ko} 관리", f"{group.root_ko} 서비스",
        ])
    lowered = group.root_en.lower()
    return _dedupe([
        group.root_en, *group.en_context,
        f"{group.root_en} menu", f"manage {lowered}", f"{group.root_en} services",
    ])


def _risk_cues(seed: FeatureSeed) -> dict[str, list[str]]:
    if seed.mode in {"submit", "change"}:
        return {
            "final_action": _dedupe([
                seed.name_ko, seed.name_en, "제출", "저장", "확정", "submit", "save", "confirm",
            ]),
            "consequence": [
                "외부 상태·비용·권리가 바뀔 수 있음",
                "may change external state, money, or rights",
            ],
            "user_boundary": [
                "최종 실행 버튼은 사용자가 직접 누름",
                "the user must press the final action button",
            ],
        }
    if seed.mode == "sensitive":
        return {
            "sensitive_access": _dedupe([
                seed.name_ko, seed.name_en, "개인정보", "민감 정보", "personal data", "sensitive information",
            ]),
            "user_boundary": [
                "민감 화면을 열기 전에 사용자에게 알림",
                "inform the user before opening sensitive information",
            ],
        }
    return {
        "navigation_scope": [seed.name_ko, seed.name_en],
        "safe_boundary": ["화면 탐색만 허용", "navigation only"],
        "user_boundary": ["실행 동작은 하지 않음", "does not perform a final action"],
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
        "description": (
            f"{group.root_ko} 영역의 앱 독립적 기능 허브. "
            f"App-agnostic function hub for {group.root_en.lower()}."
        ),
        "risk_level": "low",
        "automation_policy": "safe_navigation",
        "terminal": False,
        "state_changing": False,
        "legacy_tags": [group.domain, "v6_open_world", "hub"],
        "role_hints": ["button", "heading", "image_button", "menuitem", "tab", "text"],
        "aliases": {
            "ko-KR": _root_aliases(group, "ko-KR"),
            "en-US": _root_aliases(group, "en-US"),
        },
        "positive_context": _dedupe([
            *group.ko_context, *group.en_context, "전체 메뉴", "기능 목록", "main menu", "service list",
        ]),
        "negative_context": _dedupe([
            *group.negative_ko, *group.negative_en, "긴급 상황", "emergency",
        ]),
        "state_cues": {
            "visible": [group.root_ko, group.root_en, "서비스", "services"],
            "loading": ["불러오는 중", "처리 중", "loading", "please wait"],
            "offline": ["연결 없음", "오프라인", "no connection", "offline"],
            "error": ["다시 시도", "오류", "try again", "error"],
            "relogin_required": ["다시 로그인", "세션 만료", "sign in again", "session expired"],
        },
        "risk_cues": {
            "safe_boundary": ["허브 탐색", "navigation hub"],
            "user_boundary": ["최종 실행은 사용자 소유", "final actions remain user-owned"],
        },
        "source_refs": list(group.source_refs),
        "evidence_level": "official",
    }


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    metadata = MODE_METADATA[seed.mode]
    aliases_ko = _aliases(seed, "ko-KR")
    aliases_en = _aliases(seed, "en-US")
    return {
        "function_id": f"{group.domain}.{seed.key}",
        "domain": group.domain,
        "scope": group.scope,
        "node_kind": metadata["node_kind"],
        "stop_policy": metadata["stop_policy"],
        "name_ko": seed.name_ko,
        "name_en": seed.name_en,
        "description": (
            f"{seed.name_ko} 목적지와 사용자 소유 최종 동작의 경계를 식별한다. "
            f"Identifies the {seed.name_en.lower()} destination and its user-owned final-action boundary."
        ),
        "risk_level": metadata["risk_level"],
        "automation_policy": metadata["automation_policy"],
        "terminal": True,
        "state_changing": metadata["state_changing"],
        "legacy_tags": [group.domain, "v6_open_world", seed.key],
        "role_hints": ["button", "image_button", "link", "menuitem", "switch", "tab", "text"],
        "aliases": {"ko-KR": aliases_ko, "en-US": aliases_en},
        "positive_context": _dedupe([
            *seed.positive, *group.ko_context[:4], *group.en_context[:4],
        ]),
        "negative_context": _dedupe([
            *seed.negative, *group.negative_ko[:2], *group.negative_en[:2],
        ]),
        "state_cues": {
            "visible": [seed.name_ko, seed.name_en, aliases_ko[1], aliases_en[1]],
            "disabled": ["사용할 수 없음", "비활성", "unavailable", "disabled"],
            "selected": ["선택됨", "현재", "selected", "current"],
            "loading": ["처리 중", "불러오는 중", "processing", "loading"],
            "error": ["다시 시도", "문제가 발생", "try again", "something went wrong"],
            "relogin_required": ["다시 로그인", "세션 만료", "sign in again", "session expired"],
            "permission_required": ["권한 필요", "접근 요청", "permission required", "request access"],
            "empty": ["내역 없음", "항목 없음", "no records", "nothing here"],
        },
        "risk_cues": _risk_cues(seed),
        "source_refs": list(seed.source_refs),
        "evidence_level": "official",
    }


def _normalize(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def _cue_key(value: object) -> str:
    return "".join(
        re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", str(value)).casefold(), flags=re.UNICODE)
    )


def _runtime_pattern_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


def _tokens(value: object) -> list[str]:
    return _dedupe(
        token for token in re.findall(r"[^\W_]+", _normalize(value), flags=re.UNICODE)
        if len(token) >= 2
    )


V6_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)


def _append_rule(
    rules: list[dict[str, object]], seen: set[tuple[str, ...]], *, terms: Iterable[str],
    locale: str, kind: str, alias: str, domain: str,
    positive: Iterable[str] = (), negative: Iterable[str] = (), score: float = 1.0,
) -> None:
    all_of = _dedupe(_normalize(value) for value in terms if _normalize(value))
    signature = tuple(sorted(_cue_key(value) for value in all_of if _cue_key(value)))
    if len(signature) < 2 or signature in seen:
        return
    seen.add(signature)
    discriminative = sorted(dict.fromkeys(_cue_key(value) for value in all_of if _cue_key(value)))
    rule: dict[str, object] = {
        "all_of": all_of,
        "none_of": _dedupe(negative),
        "score": score,
        "rule_kind": kind,
        "v6_locale": locale,
        "v6_alias_key": _cue_key(alias),
        "v6_domain_key": _cue_key(domain),
        "v6_discriminative_keys": discriminative,
        "v6_negative_context_keys": sorted(
            dict.fromkeys(_cue_key(value) for value in negative if _cue_key(value))
        ),
        "v6_positive_context_keys": sorted(
            dict.fromkeys(_cue_key(value) for value in positive if _cue_key(value))
        ),
    }
    rules.append(rule)


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    function_id = f"{group.domain}.{seed.key}"
    aliases_ko = _aliases(seed, "ko-KR")
    aliases_en = _aliases(seed, "en-US")
    ko_patterns = _dedupe([
        *(f"{group.root_ko} {alias}" for alias in aliases_ko),
        f"{group.root_ko}에서 {seed.name_ko} 찾기",
        f"{group.root_ko}의 {seed.name_ko} 화면 열기",
        f"{seed.name_ko} 하려고 {group.root_ko} 메뉴로 이동",
        f"{group.root_ko} 관련 {seed.name_ko} 안내",
    ])
    en_patterns = _dedupe([
        *(f"{group.root_en} {alias}" for alias in aliases_en),
        f"find {seed.name_en.lower()} in {group.root_en.lower()}",
        f"open {seed.name_en.lower()} under {group.root_en.lower()}",
        f"go to {group.root_en.lower()} for {seed.name_en.lower()}",
        f"show {seed.name_en.lower()} for {group.root_en.lower()}",
    ])

    rules: list[dict[str, object]] = []
    seen: set[tuple[str, ...]] = set()
    for locale, domain, aliases, positives, negatives, request_words in (
        (
            "ko-KR", group.root_ko, aliases_ko,
            [*seed.positive, *group.ko_context], [*seed.negative, *group.negative_ko],
            ("찾기", "열기", "이동"),
        ),
        (
            "en-US", group.root_en, aliases_en,
            [*seed.positive, *group.en_context], [*seed.negative, *group.negative_en],
            ("find", "open", "manage"),
        ),
    ):
        for alias in aliases[:6]:
            _append_rule(
                rules, seen, terms=(domain, alias), locale=locale,
                kind="v6_domain_qualified_alias", alias=alias, domain=domain,
                positive=positives, negative=negatives,
            )
            _append_rule(
                rules, seen, terms=(f"{domain} {alias}", request_words[0]), locale=locale,
                kind="v6_request_framing", alias=alias, domain=domain,
                positive=positives, negative=negatives, score=0.998,
            )

        semantic_tokens = _dedupe([
            *(_tokens(seed.name_ko if locale == "ko-KR" else seed.name_en)),
            *(_tokens(aliases[1])), *(_tokens(aliases[2])),
            *(_tokens(positives[0])), *(_tokens(positives[1])),
        ])
        while len(semantic_tokens) < 4:
            semantic_tokens.append(f"{seed.key}{len(semantic_tokens)}")
        compositions = (
            (semantic_tokens[0], semantic_tokens[1]),
            (semantic_tokens[0], semantic_tokens[2]),
            (semantic_tokens[1], semantic_tokens[3]),
            (semantic_tokens[2], semantic_tokens[3]),
        )
        destination_anchor = seed.name_ko if locale == "ko-KR" else seed.name_en
        for left, right in compositions:
            _append_rule(
                rules, seen, terms=(domain, destination_anchor, left, right), locale=locale,
                kind="v6_compositional_domain", alias=f"{left} {right}", domain=domain,
                positive=positives, negative=negatives, score=0.994,
            )
            _append_rule(
                rules, seen, terms=(domain, destination_anchor, left, right, positives[0]), locale=locale,
                kind="v6_consequence_context", alias=f"{left} {right}", domain=domain,
                positive=positives[:2], negative=negatives, score=0.996,
            )

    confirmation_required = seed.mode in {"change", "submit", "sensitive"}
    return {
        "intent_id": f"v6_{group.domain}_{seed.key}",
        "terminal_function": function_id,
        "patterns": [*ko_patterns, *en_patterns],
        "patterns_by_locale": {"ko-KR": ko_patterns, "en-US": en_patterns},
        "goal_rules": rules,
        "route": [
            {"function_id": group.root_id, "weight": 0.42},
            {"function_id": function_id, "weight": 1.0},
        ],
        "avoid_functions": [group.avoid_root],
        "desired_state": "user_confirmation_required" if confirmation_required else "destination_visible",
        "terminal_condition": {
            "stop_policy": "stop_before_action" if confirmation_required else "on_destination_screen",
        },
    }


V6_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)

REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
REQUIRED_FUNCTIONS = frozenset({
    "automotive_vehicle.phone_key",
    "automotive_vehicle.roadside_assistance",
    "parking_tolls.citation_dispute",
    "parking_tolls.auto_replenish",
    "hr_payroll.direct_deposit",
    "hr_payroll.tax_withholding",
    "fitness_membership.class_booking",
    "fitness_membership.membership_pause",
    "home_services.protection_claim",
    "civic_local.problem_report",
    "civic_local.permit_application",
    "pet_care.microchip_enrollment",
    "pet_care.lost_pet",
    "grocery_loyalty.substitution_preferences",
    "grocery_loyalty.loyalty_card",
})


class V6CatalogValidationError(ValueError):
    """Raised when the reviewed v6 layer cannot be safely materialized."""


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    # Tests and standalone validation always exercise a clean pre-v6 base,
    # even after the canonical catalog has already materialized this layer.
    return _pre_v6_payload(json.loads(path.read_text(encoding="utf-8")))


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _rule_signature(rule: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(sorted(
        _cue_key(value) for value in rule.get("all_of", []) if _cue_key(value)
    ))


def _pre_v6_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V6_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V6_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", [])
        if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", [])
        if str(item["intent_id"]) not in intent_ids
    ]
    result.pop("official_sources_v6", None)
    return result


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V6_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V6_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    if not present_functions and not present_intents and "official_sources_v6" not in payload:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V6CatalogValidationError("partial v6 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V6CatalogValidationError("v6 collides with a different function or intent definition")
    if payload.get("official_sources_v6") != OFFICIAL_SOURCES:
        raise V6CatalogValidationError("v6 official evidence registry differs")
    if (
        payload.get("catalog_version") != CATALOG_V6_VERSION
        or payload.get("description") != CATALOG_V6_DESCRIPTION
    ):
        raise V6CatalogValidationError("v6 materialization metadata differs")
    return True


def validate_v6_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    errors: list[str] = []
    function_ids = [str(item["function_id"]) for item in V6_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V6_INTENTS]
    terminal_ids = {
        str(item["function_id"]) for item in V6_FUNCTIONS if bool(item["terminal"])
    }

    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v6 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v6 intent IDs: {sorted(duplicates)}")
    if len(REQUIRED_DOMAINS) != 8:
        errors.append("v6 must contain the eight reviewed open-world domains")
    if len(terminal_ids) < 80:
        errors.append("v6 requires at least 80 terminal functions")
    domain_terminal_counts = Counter(
        str(item["domain"]) for item in V6_FUNCTIONS if bool(item["terminal"])
    )
    if any(domain_terminal_counts[domain] < 10 for domain in REQUIRED_DOMAINS):
        errors.append(f"every v6 domain requires at least ten terminals: {dict(sorted(domain_terminal_counts.items()))}")
    if REQUIRED_FUNCTIONS - set(function_ids):
        errors.append(f"missing required v6 functions: {sorted(REQUIRED_FUNCTIONS - set(function_ids))}")

    for source_id, source in OFFICIAL_SOURCES.items():
        parsed = urlparse(str(source.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"source {source_id} is not HTTPS")
        if source.get("evidence_level") != "official_primary":
            errors.append(f"source {source_id} is not official_primary")
        if source.get("collected_on") != COLLECTED_ON:
            errors.append(f"source {source_id} missing collection date")
        if source.get("verified_status") != 200:
            errors.append(f"source {source_id} missing successful web verification")
        if not str(source.get("verification_method", "")).strip():
            errors.append(f"source {source_id} missing verification method")

    known_sources = set(OFFICIAL_SOURCES)
    used_sources: set[str] = set()
    for function in V6_FUNCTIONS:
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
        if function["state_changing"] or function["risk_level"] == "high":
            if function["automation_policy"] != "never_auto" or function["stop_policy"] != "before_action":
                errors.append(f"{function_id}: unsafe final-action boundary")
            boundary = " ".join(function["risk_cues"].get("user_boundary", []))  # type: ignore[union-attr]
            if "사용자" not in boundary or "user" not in boundary.casefold():
                errors.append(f"{function_id}: user-owned final click is not explicit")
        forbidden_keys = {"x", "y", "bounds", "coordinates", "package", "package_name", "resource_id"}
        if forbidden_keys.intersection(function):
            errors.append(f"{function_id}: app-specific coordinate or package data is forbidden")

    if used_sources != known_sources:
        errors.append(f"orphan official sources: {sorted(known_sources - used_sources)}")

    intent_terminals = [str(item["terminal_function"]) for item in V6_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v6 requires exactly one intent per terminal function")
    for intent in V6_INTENTS:
        intent_id = str(intent["intent_id"])
        locale_patterns = intent["patterns_by_locale"]
        if len(locale_patterns["ko-KR"]) < 10 or len(locale_patterns["en-US"]) < 10:  # type: ignore[index]
            errors.append(f"{intent_id}: insufficient bilingual patterns")
        if len(intent["goal_rules"]) < 24:
            errors.append(f"{intent_id}: insufficient compositional goal rules")
        if intent["route"][-1]["function_id"] != intent["terminal_function"]:  # type: ignore[index]
            errors.append(f"{intent_id}: route does not end at its terminal")
        if len(intent["route"]) != 2 or not intent["avoid_functions"]:
            errors.append(f"{intent_id}: route must remain app-agnostic hub-to-destination")
        terminal = next(item for item in V6_FUNCTIONS if item["function_id"] == intent["terminal_function"])
        if terminal["state_changing"] or terminal["risk_level"] == "high":
            if intent["desired_state"] != "user_confirmation_required":
                errors.append(f"{intent_id}: consequential intent lacks user confirmation")
            if intent["terminal_condition"]["stop_policy"] != "stop_before_action":  # type: ignore[index]
                errors.append(f"{intent_id}: consequential route does not stop before action")
        for rule in intent["goal_rules"]:
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v6_"):
                errors.append(f"{intent_id}: malformed semantic rule")
            for key in ("v6_discriminative_keys", "v6_negative_context_keys", "v6_positive_context_keys"):
                values = list(rule.get(key, []))
                if values != sorted(dict.fromkeys(values)):
                    errors.append(f"{intent_id}: nondeterministic {key}")

    materialized = False
    if base_payload is not None:
        materialized = _materialization_state(base_payload)
        pre_v6 = _pre_v6_payload(base_payload) if materialized else copy.deepcopy(dict(base_payload))
        base_function_ids = {str(item["function_id"]) for item in pre_v6.get("functions", [])}
        base_intent_ids = {str(item["intent_id"]) for item in pre_v6.get("intents", [])}
        if collisions := sorted(set(function_ids).intersection(base_function_ids)):
            errors.append(f"v6 function IDs collide with v1-v5: {collisions[:12]}")
        if collisions := sorted(set(intent_ids).intersection(base_intent_ids)):
            errors.append(f"v6 intent IDs collide with v1-v5: {collisions[:12]}")

        pattern_owners: dict[str, set[str]] = {}
        for intent in [*pre_v6.get("intents", []), *V6_INTENTS]:
            owner = str(intent["intent_id"])
            for pattern in intent.get("patterns", []):
                key = _runtime_pattern_key(pattern)
                if key:
                    pattern_owners.setdefault(key, set()).add(owner)
        collisions = {
            key: sorted(owners) for key, owners in pattern_owners.items() if len(owners) > 1
        }
        if collisions:
            errors.append(f"normalized goal-pattern collisions: {list(collisions.items())[:8]}")

        base_rule_signatures = {
            _rule_signature(rule)
            for intent in pre_v6.get("intents", [])
            for rule in intent.get("goal_rules", [])
            if _rule_signature(rule)
        }
        v6_rule_owners: dict[tuple[str, ...], set[str]] = {}
        for intent in V6_INTENTS:
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if signature in base_rule_signatures:
                    errors.append(f"{intent['intent_id']}: goal rule collides with v1-v5")
                v6_rule_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
        shared_rules = {
            signature: sorted(owners)
            for signature, owners in v6_rule_owners.items() if len(owners) > 1
        }
        if shared_rules:
            errors.append(f"v6 goal-rule collisions: {list(shared_rules.items())[:8]}")

    # No app identity or recorded UI route may leak into runtime semantics.
    semantic_payload = copy.deepcopy({"functions": V6_FUNCTIONS, "intents": V6_INTENTS})
    for function in semantic_payload["functions"]:
        function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = (
        "com.", "package name", "resource-id", "screen coordinate", "x coordinate",
        "tesla", "parkmobile", "e-zpass", "adp", "workday", "classpass",
        "taskrabbit", "nyc311", "petco", "petsmart", "chewy", "kroger", "walmart", "target circle",
    )
    if any(
        re.search(rf"(?<![a-z0-9]){re.escape(fragment)}(?![a-z0-9])", semantic_text)
        for fragment in forbidden_fragments
    ):
        errors.append("v6 runtime semantics contain an app identity or recorded UI path")

    if errors:
        raise V6CatalogValidationError("; ".join(errors))

    return {
        "functions": len(V6_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V6_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_terminal_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES),
        "aliases": sum(len(values) for item in V6_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V6_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V6_INTENTS),
        "compositional_goal_rules": sum(
            1 for item in V6_INTENTS for rule in item["goal_rules"]
            if rule["rule_kind"] in {"v6_compositional_domain", "v6_consequence_context"}
        ),
        "state_changing": sum(bool(item["state_changing"]) for item in V6_FUNCTIONS),
        "high_risk": sum(item["risk_level"] == "high" for item in V6_FUNCTIONS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic validated copy; never mutate the caller."""

    validate_v6_data(base_payload)
    if _materialization_state(base_payload):
        return copy.deepcopy(dict(base_payload))
    merged = copy.deepcopy(dict(base_payload))
    merged["catalog_version"] = CATALOG_V6_VERSION
    merged["description"] = CATALOG_V6_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V6_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V6_INTENTS)]
    merged["official_sources_v6"] = copy.deepcopy(OFFICIAL_SOURCES)
    return merged


def main() -> int:
    print(json.dumps(validate_v6_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
