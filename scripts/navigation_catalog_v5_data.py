from __future__ import annotations

"""Production v5 ontology materialization for high-value Android services.

The merge is deterministic from reviewed v5 ontology vocabulary and the
pre-v5 catalog.  Cross-generation filtering prevents new unqualified cues
from taking ownership of earlier intents while retaining bilingual,
request-framed generalization for genuinely distinctive destinations.

The concepts are app-agnostic.  They describe destinations and user-owned
action boundaries, never screen coordinates or a memorised app path.
"""

import copy
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from itertools import combinations, product
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
CATALOG_V5_VERSION = "5.0.0"
COLLECTED_ON = "2026-07-30"
CATALOG_V5_DESCRIPTION = (
    "ExitGuide cross-app function ontology v5: general Android and application navigation, "
    "state-aware and user-confirmed action boundaries, plus independently validated service "
    "semantics for ordering, reservations, lodging, flights, tickets, ride hailing, banking, "
    "digital government, healthcare, workspace administration, and parcel delivery."
)


# Every entry is a first-party publisher page checked on COLLECTED_ON.  Search
# results, community posts, app-review sites, and secondary summaries are not
# accepted as ontology evidence.
OFFICIAL_SOURCES: dict[str, dict[str, object]] = {
    "doordash_consumer_start": {
        "publisher": "DoorDash Help Center", "title": "Get Started with DoorDash",
        "url": "https://help.doordash.com/en-us/consumers/category/get-started-with-doordash",
    },
    "doordash_group_order": {
        "publisher": "DoorDash Help Center", "title": "What is a group order and how can I create one?",
        "url": "https://help.doordash.com/consumers/s/article/What-is-a-group-order-and-how-can-I-create-one",
    },
    "doordash_group_checkout": {
        "publisher": "DoorDash Help Center", "title": "Group Order AutoCheckout",
        "url": "https://help.doordash.com/en-ca/business/article/group-order-auto-checkout",
    },
    "doordash_substitutions": {
        "publisher": "DoorDash Help Center", "title": "Customer substitution preferences",
        "url": "https://help.doordash.com/en-us/consumers/article/what-are-customer-substitution-preferences",
    },
    "doordash_schedule": {
        "publisher": "DoorDash Help Center", "title": "Schedule a delivery in advance",
        "url": "https://help.doordash.com/consumers/s/article/Can-I-schedule-a-delivery-in-advance",
    },
    "doordash_instructions": {
        "publisher": "DoorDash Help Center", "title": "Special instructions for an order",
        "url": "https://help.doordash.com/consumers/s/article/Can-I-specify-special-instructions-for-my-order",
    },
    "doordash_taxes": {
        "publisher": "DoorDash Help Center", "title": "How taxes are calculated",
        "url": "https://help.doordash.com/consumers/s/article/How-are-taxes-calculated",
    },
    "doordash_order_help": {
        "publisher": "DoorDash Help Center", "title": "Where is my order?",
        "url": "https://help.doordash.com/en-us/consumers/article/customer-where-is-my-order",
    },
    "ubereats_allergies": {
        "publisher": "Uber Help", "title": "Add or remove allergy instructions",
        "url": "https://help.uber.com/am/ubereats/restaurants/article/how-can-i-add-or-remove-allergy-instructions?nodeId=8b473a3d-8341-4369-9287-7febe2fe0b7b",
    },
    "opentable_terms": {
        "publisher": "OpenTable", "title": "OpenTable Terms of Use",
        "url": "https://www.opentable.com/c/legal/terms-and-conditions/",
    },
    "opentable_notify": {
        "publisher": "OpenTable", "title": "Find the reservation you want with Notify Me",
        "url": "https://www.opentable.com/blog/notify-me/",
    },
    "opentable_privacy": {
        "publisher": "OpenTable", "title": "OpenTable Privacy Policy",
        "url": "https://www.opentable.com/c/legal/privacy-policy/",
    },
    "airbnb_search": {
        "publisher": "Airbnb Help Center", "title": "Using search filters",
        "url": "https://www.airbnb.com/help/article/479",
    },
    "airbnb_change": {
        "publisher": "Airbnb Help Center", "title": "How to change a home reservation during a trip",
        "url": "https://www.airbnb.com/help/article/1363",
    },
    "airbnb_cancel": {
        "publisher": "Airbnb Help Center", "title": "Cancel your home reservation as a guest",
        "url": "https://www.airbnb.com/help/article/169",
    },
    "airbnb_checkin": {
        "publisher": "Airbnb Help Center", "title": "How to check in to your home reservation",
        "url": "https://www.airbnb.com/help/article/41",
    },
    "airbnb_accessibility": {
        "publisher": "Airbnb Help Center", "title": "Search for listings with accessibility features",
        "url": "https://www.airbnb.com/help/article/3138",
    },
    "google_flights_search": {
        "publisher": "Google Travel Help", "title": "Find plane tickets on Google Flights",
        "url": "https://support.google.com/travel/answer/2475306?co=GENIE.Platform%3DAndroid&hl=en",
    },
    "google_flights_fares": {
        "publisher": "Google Travel Help", "title": "How to find the best fares with Google Flights",
        "url": "https://support.google.com/travel/answer/7664728?hl=en",
    },
    "google_flights_track": {
        "publisher": "Google Travel Help", "title": "Track flights and prices",
        "url": "https://support.google.com/travel/answer/6235879?co=GENIE.Platform%3DAndroid&hl=en",
    },
    "ticketmaster_help": {
        "publisher": "Ticketmaster Help", "title": "Ticketmaster Help Center",
        "url": "https://help.ticketmaster.com/hc/en-us/",
    },
    "uber_request": {
        "publisher": "Uber Help", "title": "How to request a ride or get a price estimate",
        "url": "https://help.uber.com/riders/article/how-to-request-a-ride--get-a-price-estimate?nodeId=67f41961-e0aa-4670-af32-58be02c7c492",
    },
    "uber_multistop": {
        "publisher": "Uber Help", "title": "Request a ride with multiple stops",
        "url": "https://help.uber.com/riders/article/%E9%A0%90%E7%B4%84%E5%89%8D%E5%BE%80%E5%A4%9A%E5%80%8B%E7%9B%AE%E7%9A%84%E5%9C%B0%E7%9A%84%E8%A1%8C%E7%A8%8B?nodeId=26f09874-91e9-4fe1-9537-ec680a47ecbe",
    },
    "uber_reserve": {
        "publisher": "Uber Help", "title": "What is Uber Reserve?",
        "url": "https://help.uber.com/riders/article/hva-er-uber-reserve?nodeId=ccb9a8da-9e44-4038-921f-0360bbabc518",
    },
    "uber_pickup_preferences": {
        "publisher": "Uber Help", "title": "Pickup Preferences",
        "url": "https://help.uber.com/en/riders/article/pickup-preferences?nodeId=d5c348be-59f0-4fa6-91c2-e8ce57906662&partner=crm&pcid=bloc_9f10093b-60fb-428e-ba97-1c1069cc5821&pcn=crm_au_nz_r_em_pickup_preferences_03162026_a_w&pscn=crm_apac_r_em_UBRg04wrp4tf51tyalnasgr&sl_id=3nqoc",
    },
    "uber_business_profile": {
        "publisher": "Uber Help", "title": "Creating a business ride profile",
        "url": "https://help.uber.com/riders/article/creating-a-business-ride-profile/?nodeId=ca5a9884-4e4f-4649-82dd-1561c3db7e70",
    },
    "uber_wait_fee": {
        "publisher": "Uber Help", "title": "Wait time fees and refunds",
        "url": "https://help.uber.com/riders/article/your-trip-details?nodeId=469f1786-1543-4c83-abbf-ddccb7826fc2",
    },
    "uber_saved_places": {
        "publisher": "Uber Help", "title": "How to Add or Remove Saved Places",
        "url": "https://help.uber.com/en/riders/article/so-f%C3%BCgst-du-gespeicherte-orte-hinzu-bzw-entfernst-sie?nodeId=92f13cb2-bab2-4c88-a19e-9d52533496c3",
    },
    "uber_accessible_vehicle": {
        "publisher": "Uber Help", "title": "What is WAV?",
        "url": "https://help.uber.com/riders/article/qu%C3%A9-es%C2%A0wav?nodeId=51c47a81-67c7-4286-91f5-79c6bc78f6a7",
    },
    "uber_verify_ride": {
        "publisher": "Uber Help", "title": "What's Verify my Ride?",
        "url": "https://help.uber.com/sw/riders/article/whats-a-pin?nodeId=2ddbb5e8-0dd3-4048-b9ee-f6b5e5311e25",
    },
    "uber_expense_memo": {
        "publisher": "Uber Help", "title": "How to use expense memos",
        "url": "https://help.uber.com/en/riders/article/onkostenmemos-gebruiken?nodeId=b5184ede-6169-4f44-82ad-2b0dbe48699b",
    },
    "boa_mobile_features": {
        "publisher": "Bank of America", "title": "Mobile and Online Banking Features",
        "url": "https://www.bankofamerica.com/online-banking/mobile-and-online-banking-features/",
    },
    "boa_check_deposit": {
        "publisher": "Bank of America", "title": "Deposit a check with the Mobile Banking app",
        "url": "https://info.bankofamerica.com/en/digital-banking/mobile-check-deposit",
    },
    "boa_account_access": {
        "publisher": "Bank of America", "title": "Access your accounts",
        "url": "https://www.bankofamerica.com/deposits/access-your-accounts/",
    },
    "boa_debit_card_faq": {
        "publisher": "Bank of America", "title": "Debit Card FAQs",
        "url": "https://www.bankofamerica.com/deposits/debit-card-faqs/",
    },
    "boa_direct_deposit": {
        "publisher": "Bank of America", "title": "Set up direct deposit",
        "url": "https://info.bankofamerica.com/en/digital-banking/direct-deposit",
    },
    "chase_wire": {
        "publisher": "Chase", "title": "Wire Transfer FAQs",
        "url": "https://www.chase.com/digital/wire-transfer/faqs",
    },
    "chase_payment_safety": {
        "publisher": "Chase", "title": "Payment choices matter",
        "url": "https://www.chase.com/digital/resources/privacy-security/security/payment-choices",
    },
    "login_gov_auth": {
        "publisher": "Login.gov", "title": "Add or change an authentication method",
        "url": "https://www.login.gov/help/manage-your-account/add-or-change-your-authentication-method/",
    },
    "login_gov_identity": {
        "publisher": "Login.gov", "title": "How to verify your identity",
        "url": "https://www.login.gov/help/verify-your-identity/overview/",
    },
    "passport_apply": {
        "publisher": "U.S. Department of State", "title": "Apply for a Passport",
        "url": "https://travel.state.gov/en/passports/apply.html",
    },
    "passport_renew": {
        "publisher": "U.S. Department of State", "title": "Renew Your Passport Online",
        "url": "https://travel.state.gov/en/passports/renew-replace/online.html",
    },
    "passport_status": {
        "publisher": "U.S. Department of State", "title": "After You Apply for Your Passport",
        "url": "https://travel.state.gov/en/passports/after-you-apply.html",
    },
    "uscis_case": {
        "publisher": "U.S. Citizenship and Immigration Services", "title": "Case Status Online",
        "url": "https://egov.uscis.gov/",
    },
    "uscis_appointment": {
        "publisher": "U.S. Citizenship and Immigration Services", "title": "Appointment Request Overview",
        "url": "https://my.uscis.gov/accounts/appointment_request/overview",
    },
    "uscis_file_online": {
        "publisher": "U.S. Citizenship and Immigration Services", "title": "File Online",
        "url": "https://www.uscis.gov/file-online",
    },
    "uscis_fee_calculator": {
        "publisher": "U.S. Citizenship and Immigration Services", "title": "Fee Calculator",
        "url": "https://www.uscis.gov/feecalculator?form=i-90",
    },
    "nhs_app_help": {
        "publisher": "National Health Service", "title": "Help with using the NHS App",
        "url": "https://www.nhs.uk/nhs-app/help/",
    },
    "nhs_appointments": {
        "publisher": "National Health Service", "title": "Help with appointments in the NHS App",
        "url": "https://www.nhs.uk/nhs-app/help/appointments/",
    },
    "nhs_messages": {
        "publisher": "National Health Service", "title": "Messages in the NHS App",
        "url": "https://www.nhs.uk/nhs-app/help/messages/",
    },
    "nhs_records": {
        "publisher": "National Health Service", "title": "GP health record",
        "url": "https://www.nhs.uk/nhs-app/help/health-records-in-the-nhs-app/gp-health-record/",
    },
    "nhs_family_access": {
        "publisher": "National Health Service", "title": "Family and carer access",
        "url": "https://www.nhs.uk/nhs-app/help/profile/family-and-carer-access/",
    },
    "nhs_pharmacy": {
        "publisher": "National Health Service", "title": "Nominating a pharmacy",
        "url": "https://www.nhs.uk/nhs-app/help/prescriptions/nominating-a-pharmacy/",
    },
    "nhs_organ_donation": {
        "publisher": "National Health Service", "title": "Organ donation",
        "url": "https://www.nhs.uk/nhs-app/help/profile/organ-donation/",
    },
    "nhs_fit_note": {
        "publisher": "National Health Service", "title": "Getting a fit note",
        "url": "https://www.nhs.uk/nhs-services/gps/getting-a-fit-note/",
    },
    "nhs_app_terms": {
        "publisher": "National Health Service", "title": "NHS App terms of use",
        "url": "https://www.nhs.uk/nhs-app/about/privacy-legal-information/nhs-app-terms-of-use/",
    },
    "va_manage_health": {
        "publisher": "U.S. Department of Veterans Affairs", "title": "Manage Your Health Care With My HealtheVet",
        "url": "https://www.va.gov/health-care/manage-health/",
    },
    "slack_retention": {
        "publisher": "Slack", "title": "Customize data retention in Slack",
        "url": "https://slack.com/help/articles/203457187-Customize-data-retention-in-Slack",
    },
    "slack_export": {
        "publisher": "Slack", "title": "How to read Slack data exports",
        "url": "https://slack.com/help/articles/220556107-How-to-read-Slack-data-exports",
    },
    "slack_import": {
        "publisher": "Slack", "title": "Import data from one Slack workspace to another",
        "url": "https://slack.com/help/articles/217872578-Import-data-from-one-Slack-workspace-to-another",
    },
    "slack_channels": {
        "publisher": "Slack", "title": "Archive or delete a channel",
        "url": "https://slack.com/help/articles/213185307-Archive-or-delete-a-channel",
    },
    "drive_share": {
        "publisher": "Google Drive Help", "title": "Share files from Google Drive",
        "url": "https://support.google.com/drive/answer/2494822?hl=en",
    },
    "drive_shared_drives": {
        "publisher": "Google Drive Help", "title": "Store and share files with shared drives",
        "url": "https://support.google.com/drive/answer/7286514?hl=en",
    },
    "drive_access": {
        "publisher": "Google Drive Help", "title": "Learn more about access to Google files",
        "url": "https://support.google.com/drive/answer/16722399?hl=en",
    },
    "ups_change_delivery": {
        "publisher": "UPS", "title": "Change a Delivery",
        "url": "https://www.ups.com/us/en/track/change-delivery",
    },
    "ups_my_choice": {
        "publisher": "UPS", "title": "View All Shipments With UPS My Choice",
        "url": "https://www.ups.com/us/en/track/ups-my-choice",
    },
    "ups_tracking": {
        "publisher": "UPS", "title": "UPS Tracking Support",
        "url": "https://www.ups.com/us/en/support/tracking-support",
    },
    "ups_intercept": {
        "publisher": "UPS", "title": "Changing a Delivery with UPS Delivery Intercept",
        "url": "https://www.ups.com/us/en/support/tracking-support/change-delivery-options/delivery-intercept",
    },
}

for _source in OFFICIAL_SOURCES.values():
    _source.update(
        collected_on=COLLECTED_ON,
        evidence_level="official_primary",
        verified_status=200,
        verification_method="official page opened with web reader",
    )


def _terms(value: str | Iterable[str]) -> tuple[str, ...]:
    values = value.split("|") if isinstance(value, str) else value
    return tuple(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


@dataclass(frozen=True)
class FeatureSeed:
    function_id: str
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
    function_id: str,
    name_ko: str,
    name_en: str,
    ko_aliases: str,
    en_aliases: str,
    positive: str,
    negative: str,
    mode: str = "view",
    *,
    sources: str,
) -> FeatureSeed:
    return FeatureSeed(
        function_id, name_ko, name_en, _terms(ko_aliases), _terms(en_aliases),
        _terms(positive), _terms(negative), mode, _terms(sources),
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
        domain, root_id, root_ko, root_en, scope, _terms(ko_context), _terms(en_context),
        _terms(negative_ko), _terms(negative_en), avoid_root, _terms(sources), tuple(features),
    )


MODE_METADATA: dict[str, dict[str, object]] = {
    "view": {
        "risk_level": "low", "automation_policy": "safe_navigation",
        "state_changing": False, "node_kind": "destination", "stop_policy": "on_destination_screen",
    },
    "sensitive": {
        "risk_level": "high", "automation_policy": "never_auto",
        "state_changing": False, "node_kind": "sensitive_destination", "stop_policy": "before_action",
    },
    "change": {
        "risk_level": "medium", "automation_policy": "never_auto",
        "state_changing": True, "node_kind": "state_change", "stop_policy": "before_action",
    },
    "submit": {
        "risk_level": "high", "automation_policy": "never_auto",
        "state_changing": True, "node_kind": "external_action", "stop_policy": "before_action",
    },
}


# Deliberately excluded because the current v4 catalog already owns the
# semantic destination.  Keeping this review ledger is as important as adding
# new rows: it prevents apparent "coverage" from becoming duplicate concepts.
EXCLUDED_AS_ALREADY_COVERED: dict[str, str] = {
    "generic_order_tracking": "shopping.track_package",
    "generic_order_cancel": "shopping.cancel_order",
    "generic_refund_request": "app_store.refund_request / refund.entry",
    "generic_account_balance_history": "finance.transactions",
    "generic_card_freeze": "finance.card.freeze",
    "generic_recurring_transfer": "finance.recurring_transfer",
    "generic_medical_appointments": "health.appointments",
    "generic_lab_results": "digital_health.lab_results / health.lab_results",
    "generic_cloud_link_share": "cloud.link_share",
    "generic_workspace_members_roles": "work.members / work.roles",
    "generic_flight_checkin": "travel.checkin",
    "generic_boarding_pass": "travel.boarding_pass",
}


GROUPS: tuple[GroupSeed, ...] = (
    G(
        "food_ordering", "food_order.hub", "음식 주문", "Food ordering", "commerce_service",
        "음식|배달|포장|식당 메뉴|주문 장바구니", "food|delivery|pickup|restaurant menu|meal order",
        "숙소 예약|항공권|택배 배송", "lodging reservation|flight ticket|parcel shipment",
        "restaurant_booking.hub", "doordash_consumer_start|doordash_group_order|doordash_group_checkout",
        F("food_order.menu", "식당 메뉴 보기", "Restaurant menu", "메뉴판|음식 목록|메뉴 둘러보기|판매 메뉴", "browse menu|food menu|menu items|restaurant catalog", "카테고리|가격|품절|옵션", "장바구니 결제|예약 좌석", sources="doordash_consumer_start"),
        F("food_order.dietary_filters", "식단 조건 필터", "Dietary filters", "알레르기 필터|채식 메뉴|비건 옵션|식단 조건", "allergy filter|vegetarian options|vegan menu|dietary needs", "알레르기|채식|할랄|글루텐", "검색어 삭제|주소 필터", sources="ubereats_allergies"),
        F("food_order.item_customize", "메뉴 옵션 선택", "Customize menu item", "토핑 선택|맵기 선택|사이즈 변경|메뉴 커스텀", "choose toppings|item options|change size|customize dish", "추가 옵션|제외 재료|수량|가격 변경", "배송 요청사항|결제 수단", "change", sources="doordash_instructions|ubereats_allergies"),
        F("food_order.substitution_preferences", "품절 대체 설정", "Substitution preferences", "대체 상품|품절 시 처리|대체 허용|환불 선호", "replacement preference|out of stock choice|allow substitute|refund preference", "품절|대체|환불|연락", "메뉴 토핑|주소 변경", "change", sources="doordash_substitutions"),
        F("food_order.fulfillment", "배달·포장 방식", "Delivery or pickup", "배달 선택|포장 주문|직접 수령|픽업 전환", "choose delivery|pickup order|collect myself|fulfillment method", "배달 시간|픽업 시간|매장 수령", "택배 수령|호텔 체크인", "change", sources="doordash_consumer_start"),
        F("food_order.schedule", "주문 시간 예약", "Schedule food order", "예약 배달|나중에 주문|배달 시간 선택|사전 주문", "scheduled delivery|order later|choose delivery time|preorder food", "날짜|시간|예약 가능|도착 예정", "승차 예약|식당 좌석 예약", "change", sources="doordash_schedule"),
        F("food_order.group_create", "단체 주문 만들기", "Create group order", "그룹 주문|함께 주문|단체 장바구니|공동 주문", "group order|order together|shared cart|team meal order", "초대 링크|참여자|마감 시간|장바구니", "단체 채팅|회의 초대", "submit", sources="doordash_group_order|doordash_group_checkout"),
        F("food_order.group_invite", "단체 주문 초대", "Invite to group order", "주문 링크 공유|참여자 초대|그룹 주문 보내기|동료 초대", "share order link|invite participants|send group order|invite coworkers", "초대 링크|참여자|주문 마감", "문서 공유|일정 초대", "submit", sources="doordash_group_order"),
        F("food_order.group_budget", "단체 주문 예산", "Group order budget", "1인 예산|사람별 한도|그룹 주문 금액 제한|식사 예산", "per-person budget|participant limit|group order cap|meal allowance", "예산 금액|회사 결제|한도 초과", "앱 스토어 예산|데이터 한도", "change", sources="doordash_group_checkout"),
        F("food_order.fee_breakdown", "주문 요금 상세", "Food order fee breakdown", "배달비 보기|서비스 수수료|세금 내역|최종 금액 상세", "delivery fee|service fee|tax breakdown|order total details", "소계|세금|배달비|팁|수수료", "은행 수수료|항공 수하물 요금", sources="doordash_taxes"),
        F("food_order.live_support", "진행 중 주문 도움", "Live food order support", "배달 문제 신고|주문 도움|실시간 상담|음식 주문 문제", "delivery issue|order help|live support|problem with food order", "진행 중 주문|누락|오배송|상담", "택배 분실|승차 요금 이의", "submit", sources="doordash_order_help"),
    ),
    G(
        "restaurant_booking", "restaurant_booking.hub", "식당 예약", "Restaurant reservations", "reservation_service",
        "식당|테이블|좌석|예약 시간|대기 명단", "restaurant|table|party size|reservation time|waitlist",
        "음식 배달|호텔 객실|병원 진료", "food delivery|hotel room|medical visit",
        "food_order.hub", "opentable_terms|opentable_notify|opentable_privacy",
        F("restaurant_booking.availability", "예약 가능 시간 찾기", "Find table availability", "빈 테이블|예약 시간 검색|자리 있는 식당|가능한 시간", "available tables|reservation times|open slots|find availability", "날짜|시간|인원|식당", "진료 시간|항공편 시간", sources="opentable_terms"),
        F("restaurant_booking.filters", "식당 예약 필터", "Restaurant reservation filters", "음식 종류|가격대|지역 필터|좌석 조건", "cuisine filter|price range|neighborhood filter|seating preference", "요리 종류|거리|평점|예약 가능", "숙소 편의시설|비행 경유", sources="opentable_terms"),
        F("restaurant_booking.table_options", "테이블 옵션", "Table options", "실내 좌석|야외 좌석|바 좌석|테이블 유형", "indoor seating|outdoor table|bar seating|table type", "좌석 종류|인원|특별 요청", "항공 좌석|공연 좌석", sources="opentable_terms"),
        F("restaurant_booking.create", "식당 예약 확정", "Book restaurant table", "테이블 예약|식당 예약하기|좌석 예약 확정|예약 제출", "reserve table|book restaurant|confirm dining reservation|submit booking", "날짜|시간|인원|예약 확인", "음식 주문|호텔 예약", "submit", sources="opentable_terms"),
        F("restaurant_booking.modify", "식당 예약 변경", "Modify restaurant reservation", "예약 시간 변경|인원 수정|테이블 예약 수정|식사 일정 변경", "change reservation time|edit party size|modify booking|update dining reservation", "기존 예약|날짜|시간|인원", "호텔 일정 변경|진료 예약 변경", "submit", sources="opentable_terms"),
        F("restaurant_booking.cancel", "식당 예약 취소", "Cancel restaurant reservation", "테이블 예약 취소|식사 예약 삭제|예약 철회|노쇼 방지 취소", "cancel table|cancel dining booking|remove reservation|avoid no-show", "기존 예약|취소 확인|정책", "호텔 취소|항공 취소", "submit", sources="opentable_terms"),
        F("restaurant_booking.waitlist_join", "식당 대기 등록", "Join restaurant waitlist", "웨이팅 등록|대기 명단 참가|현장 대기|줄서기", "join waitlist|restaurant queue|add me to wait list|virtual line", "예상 대기|순번|인원|호출", "병원 대기 명단|티켓 대기열", "submit", sources="opentable_terms"),
        F("restaurant_booking.waitlist_status", "식당 대기 순번", "Restaurant waitlist status", "웨이팅 확인|내 대기 상태|남은 대기 시간|줄 순서", "waitlist position|queue status|estimated wait|place in line", "현재 순번|예상 시간|호출 상태", "택배 위치|진료 의뢰 상태", "sensitive", sources="opentable_terms"),
        F("restaurant_booking.availability_alert", "빈자리 알림", "Table availability alert", "예약 자리 알림|Notify Me|취소석 알림|테이블 열림 알림", "notify me|table alert|cancellation opening|availability notification", "원하는 날짜|시간|인원|푸시 알림", "항공 가격 알림|택배 알림", "change", sources="opentable_notify"),
        F("restaurant_booking.message", "식당에 예약 메시지", "Message restaurant about reservation", "식당 문의|예약 요청사항|레스토랑 메시지|기념일 요청", "message restaurant|booking request|reservation note|special occasion request", "예약 번호|요청 내용|식당 응답", "호스트 메시지|의료진 메시지", "submit", sources="opentable_privacy"),
        F("restaurant_booking.rewards", "식당 예약 리워드", "Dining reservation rewards", "다이닝 포인트|예약 보상|리워드 잔액|식사 포인트", "dining points|reservation rewards|reward balance|meal points", "적립|사용 가능|예약 내역", "항공 마일리지|카드 포인트", "sensitive", sources="opentable_terms"),
    ),
    G(
        "lodging_stays", "lodging.hub", "숙소", "Lodging stays", "travel_reservation",
        "호텔|숙소|객실|체크인 날짜|게스트", "hotel|home stay|room|check-in dates|guests",
        "부동산 임대|항공편|식당 테이블", "property lease|flight|restaurant table",
        "air_travel_planning.hub", "airbnb_search|airbnb_change|airbnb_cancel|airbnb_checkin|airbnb_accessibility",
        F("lodging.search", "숙소 검색", "Search lodging", "호텔 찾기|숙박 검색|머물 곳 찾기|객실 검색", "find hotel|search stays|find a place to stay|room search", "목적지|날짜|게스트|객실", "부동산 매물|식당 찾기", sources="airbnb_search"),
        F("lodging.filters", "숙소 검색 필터", "Lodging search filters", "가격 필터|객실 유형|편의시설 필터|무료 취소 조건", "price filter|property type|amenities filter|free cancellation", "가격|침실|편의시설|예약 옵션", "항공 운임|식당 음식 종류", sources="airbnb_search"),
        F("lodging.map", "숙소 지도", "Lodging map", "지도에서 숙소|호텔 위치 보기|주변 숙소 지도|지역별 객실", "stays on map|hotel locations|nearby lodging map|rooms by area", "동네|거리|지도 핀|목적지", "대중교통 지도|부동산 지도", sources="airbnb_search"),
        F("lodging.wishlist", "숙소 위시리스트", "Lodging wishlist", "찜한 숙소|저장한 호텔|여행 숙소 목록|객실 즐겨찾기", "saved stays|favorite hotels|trip wishlist|bookmarked rooms", "저장|목록|공유|숙소", "쇼핑 찜|앱 위시리스트", "change", sources="airbnb_search"),
        F("lodging.listing_details", "숙소 상세", "Lodging details", "객실 설명|숙소 편의시설|하우스 규칙|총 가격", "room details|property amenities|house rules|total stay price", "사진|후기|편의시설|규칙|가격", "부동산 계약|항공편 상세", sources="airbnb_search"),
        F("lodging.reserve", "숙소 예약 요청", "Reserve lodging", "객실 예약|숙박 예약 확정|숙소 예약 제출|호텔 부킹", "book room|confirm stay|submit lodging reservation|hotel booking", "날짜|게스트|결제|예약 정책", "식당 예약|항공 예약", "submit", sources="airbnb_search"),
        F("lodging.trip_details", "숙박 예약 상세", "Stay reservation details", "내 숙소 예약|여행 상세|호텔 예약 번호|숙박 일정", "my stay booking|trip details|hotel confirmation|lodging itinerary", "예약 번호|주소|날짜|게스트", "항공 예약 상세|부동산 임대", "sensitive", sources="airbnb_checkin"),
        F("lodging.change_dates", "숙박 일정 변경", "Change stay dates", "체크인 날짜 변경|숙박 연장|체크아웃 수정|예약 날짜 바꾸기", "change check-in date|extend stay|update checkout|modify stay dates", "기존 예약|새 날짜|추가 요금|호스트 승인", "항공편 변경|식당 시간 변경", "submit", sources="airbnb_change"),
        F("lodging.cancel", "숙소 예약 취소", "Cancel lodging reservation", "호텔 취소|숙박 예약 철회|여행 숙소 취소|객실 예약 삭제", "cancel hotel|cancel stay|withdraw lodging booking|remove room reservation", "취소 정책|예상 환불|예약 확인", "항공 취소|식당 취소", "submit", sources="airbnb_cancel"),
        F("lodging.checkin_instructions", "숙소 체크인 안내", "Lodging check-in instructions", "입실 방법|도어락 코드|열쇠 수령|숙소 들어가는 법", "entry instructions|door code|key pickup|how to get inside", "정확한 주소|출입 코드|주차|와이파이", "항공 체크인|사무실 출입", "sensitive", sources="airbnb_checkin"),
        F("lodging.host_message", "숙소 호스트 메시지", "Message lodging host", "호스트에게 문의|체크인 질문|숙소 주인 연락|예약 메시지", "message host|ask about check-in|contact property host|stay conversation", "예약|질문|응답|연락", "식당 메시지|의료진 메시지", "submit", sources="airbnb_checkin"),
        F("lodging.accessibility_filter", "접근성 숙소 필터", "Accessible lodging filter", "무단차 숙소|휠체어 접근 객실|장애인 주차|접근성 편의시설", "step-free stay|wheelchair accessible room|accessible parking|accessibility amenities", "출입구|침실|욕실|주차", "앱 접근성 설정|대중교통 접근성", sources="airbnb_accessibility"),
        F("lodging.refund_preview", "숙소 취소 환불 예상", "Lodging refund preview", "취소 전 환불액|호텔 환불 계산|예상 환불 상세|취소 수수료 보기", "refund before cancellation|hotel refund estimate|refund breakdown|cancellation charge preview", "취소 정책|환불액|수수료|결제 수단", "쇼핑 반품 환불|앱 환불", "sensitive", sources="airbnb_cancel"),
    ),
    G(
        "air_travel_planning", "air_travel_planning.hub", "항공편 찾기", "Flight discovery", "travel_search",
        "항공권|비행기|출발 공항|도착 공항|운임", "flight|airfare|departure airport|arrival airport|fare",
        "이미 예약한 비행|공항 체크인|기차", "booked flight|airport check-in|train",
        "lodging.hub", "google_flights_search|google_flights_fares|google_flights_track",
        F("flight_search.itinerary", "항공편 검색", "Search flights", "비행기표 찾기|항공권 검색|왕복 항공편|다구간 비행", "find flights|search airfare|round trip flight|multi-city flight", "출발지|도착지|날짜|승객", "예약 조회|비행 상태", sources="google_flights_search"),
        F("flight_search.fare_filters", "항공편 조건 필터", "Flight search filters", "직항 필터|항공사 선택|시간대 필터|좌석 등급", "nonstop filter|choose airline|time filter|cabin class", "경유 횟수|항공사|시간|등급", "호텔 편의시설|식당 필터", sources="google_flights_search"),
        F("flight_search.flexible_dates", "항공 유연한 날짜", "Flexible flight dates", "저렴한 날짜|날짜별 항공료|여행 날짜 비교|달력 운임", "cheapest dates|airfare calendar|compare travel dates|date grid", "달력|최저 가격|전후 날짜", "예약 날짜 변경|식당 예약 시간", sources="google_flights_search|google_flights_fares"),
        F("flight_search.price_graph", "항공 가격 그래프", "Flight price graph", "운임 추세|날짜별 가격 차트|항공료 그래프|가격 변화 보기", "fare trends|price chart by date|airfare graph|price history", "월|주|가격 추세|기간", "투자 차트|공과금 사용량", sources="google_flights_fares"),
        F("flight_search.alternative_airports", "대체 공항 비교", "Alternative airports", "근처 공항|다른 출발 공항|공항별 요금|주변 공항", "nearby airports|alternate departure airport|airport fare comparison|other airports", "공항|거리|운임|이동", "대체 숙소|택배 픽업 지점", sources="google_flights_fares"),
        F("flight_search.bag_fee_filter", "수하물 요금 포함 검색", "Bag fee flight filter", "가방 요금 반영|수하물 비용 필터|위탁 수하물 포함 가격|기내 가방 요금", "include bag fees|baggage cost filter|checked bag price|carry-on fee", "가방 개수|수하물 요금|총 운임", "예약 수하물 관리|배송비", sources="google_flights_search"),
        F("flight_search.price_track", "항공 가격 추적", "Track flight price", "항공료 알림 켜기|운임 추적|가격 하락 알림|노선 가격 저장", "flight price alert|track airfare|fare drop notification|save route price", "노선|날짜|알림|가격 변화", "식당 빈자리 알림|주가 알림", "change", sources="google_flights_track"),
        F("flight_search.tracked_flights", "추적 중인 항공편", "Tracked flight prices", "저장한 항공 가격|추적 노선|가격 알림 목록|관심 항공편", "saved flight prices|tracked routes|fare alerts list|watched flights", "노선|현재 가격|변동|알림", "이미 예약한 항공편|항공 상태", sources="google_flights_track"),
        F("flight_search.emissions", "항공편 배출량 비교", "Flight emissions comparison", "탄소 배출 비교|비행 배출량|친환경 항공편|CO2 정보", "carbon comparison|flight emissions|lower-emission flight|CO2 information", "배출량|일반 대비|항공편", "차량 연비|가정 에너지", sources="google_flights_search"),
        F("flight_search.booking_link", "항공권 예약처 선택", "Choose flight booking provider", "항공사에서 예약|여행사 링크|예약 옵션|판매처 선택", "book with airline|travel agency link|booking option|choose provider", "항공사|여행사|최종 가격|외부 이동", "이미 예약한 항공 변경|호텔 예약", "sensitive", sources="google_flights_search|google_flights_fares"),
        F("flight_search.self_transfer_warning", "자가 환승 확인", "Self-transfer flight warning", "별도 발권|수하물 다시 부치기|자가 환승 안내|공항 이동 경고", "separate tickets|recheck baggage|self-transfer notice|airport change warning", "별도 티켓|수하물|공항 변경|연결 위험", "일반 경유|대중교통 환승", sources="google_flights_fares"),
    ),
    G(
        "event_ticketing", "event_ticket.hub", "공연·행사 티켓", "Event tickets", "ticketing_service",
        "공연|콘서트|경기|행사|티켓|공연장", "concert|sports event|show|event|ticket|venue",
        "항공권|대중교통 승차권|식당 예약", "flight ticket|transit fare|restaurant reservation",
        "restaurant_booking.hub", "ticketmaster_help",
        F("event_ticket.search", "행사 검색", "Search events", "공연 찾기|콘서트 검색|경기 일정|행사 둘러보기", "find events|concert search|sports schedule|browse shows", "아티스트|팀|도시|날짜|장르", "항공편 검색|식당 검색", sources="ticketmaster_help"),
        F("event_ticket.venue_info", "공연장 정보", "Venue information", "공연장 위치|입장 규칙|시설 안내|행사장 정보", "venue location|entry rules|venue facilities|event location details", "주소|입장 시간|가방 정책|시설", "숙소 위치|공항 정보", sources="ticketmaster_help"),
        F("event_ticket.seat_map", "좌석 배치도", "Event seat map", "공연 좌석도|구역 보기|무대 위치|좌석 선택 지도", "concert seating chart|sections|stage location|seat selection map", "구역|열|좌석|무대|가격", "항공 좌석|식당 테이블", sources="ticketmaster_help"),
        F("event_ticket.accessible_seats", "접근성 좌석", "Accessible event seats", "휠체어 좌석|동반자 좌석|장애인 관람석|접근 가능한 티켓", "wheelchair seats|companion seating|accessible section|accessible tickets", "휠체어|동반자|시야|접근성", "항공 특별 지원|숙소 접근성", sources="ticketmaster_help"),
        F("event_ticket.presale", "티켓 선예매", "Ticket presale", "팬클럽 선예매|사전 판매|예매 코드|얼리 액세스", "fan presale|advance sale|presale code|early access", "코드|시작 시간|대상|티켓", "앱 사전 등록|상품 예약 판매", "sensitive", sources="ticketmaster_help"),
        F("event_ticket.purchase", "행사 티켓 구매", "Purchase event tickets", "공연 예매 확정|티켓 결제|좌석 구매|행사 예약", "confirm ticket order|buy tickets|purchase seats|book event", "좌석|수량|가격|수수료|결제", "항공권 예약처|대중교통 충전", "submit", sources="ticketmaster_help"),
        F("event_ticket.mobile_entry", "모바일 입장권", "Mobile event ticket", "휴대폰 티켓|입장 바코드|모바일 QR|내 티켓 열기", "phone ticket|entry barcode|mobile QR|open my tickets", "회전 바코드|행사|좌석|입장", "탑승권|처방전 바코드", "sensitive", sources="ticketmaster_help"),
        F("event_ticket.wallet_add", "티켓 지갑에 추가", "Add ticket to wallet", "모바일 지갑 저장|티켓 오프라인 저장|월렛에 추가|입장권 보관", "save to mobile wallet|store ticket offline|add to wallet|keep entry pass", "티켓|지갑|오프라인|입장", "결제 카드 추가|정부 인증서 지갑", "change", sources="ticketmaster_help"),
        F("event_ticket.transfer", "티켓 양도", "Transfer event ticket", "입장권 보내기|티켓 전달|친구에게 양도|티켓 이전", "send ticket|transfer admission|give ticket to friend|ticket handoff", "받는 사람|티켓 선택|전송 확인", "송금|파일 공유", "submit", sources="ticketmaster_help"),
        F("event_ticket.transfer_accept", "양도 티켓 받기", "Accept ticket transfer", "받은 티켓 수락|입장권 이전 받기|양도 초대 승인|티켓 클레임", "accept transferred ticket|receive admission|claim ticket transfer|accept invite", "보낸 사람|행사|수락|내 티켓", "파일 접근 승인|예약 초대", "submit", sources="ticketmaster_help"),
        F("event_ticket.resale", "티켓 재판매 등록", "List ticket for resale", "티켓 팔기|공식 재판매|입장권 판매 등록|리셀 가격", "sell tickets|official resale|list admission|resale price", "판매 가능|가격|지급 수단|등록", "중고 상품 등록|항공권 환불", "submit", sources="ticketmaster_help"),
        F("event_ticket.refund", "행사 티켓 환불", "Event ticket refund", "공연 취소 환불|티켓 환불 요청|행사 환불|예매 취소 금액", "cancelled event refund|ticket refund request|event refund|booking cancellation amount", "행사 상태|주문|환불 가능|결제", "앱 환불|숙소 환불", "submit", sources="ticketmaster_help"),
        F("event_ticket.updates", "행사 변경 알림", "Event updates", "공연 일정 변경|행사 취소 알림|공연장 업데이트|입장 시간 변경", "show schedule change|event cancellation alert|venue update|door time change", "행사|새 일정|취소|공연장", "항공 상태|대중교통 장애", sources="ticketmaster_help"),
    ),
    G(
        "ride_hailing_extended", "ride_hailing.hub", "차량 호출 상세", "Ride-hailing controls", "mobility_service",
        "택시 호출|승차|픽업|기사|차량 옵션", "ride request|pickup|driver|car option|rider",
        "음식 배달|대중교통|렌터카", "food delivery|public transit|car rental",
        "local_transit.hub", "uber_request|uber_multistop|uber_reserve|uber_pickup_preferences|uber_business_profile|uber_wait_fee",
        F("ride_hailing.pickup_pin", "승차 위치 조정", "Adjust pickup pin", "픽업 핀 옮기기|차 타는 곳 변경|승차 지점 확인|출발 위치 지정", "move pickup pin|change pickup spot|confirm pickup location|set departure point", "지도 핀|주소|승차 지점|기사", "배송 주소|숙소 위치", "change", sources="uber_request"),
        F("ride_hailing.vehicle_options", "호출 차량 옵션", "Ride vehicle options", "차량 종류|택시 등급|승차 인원|예상 요금 비교", "car types|ride tiers|passenger capacity|compare estimated fare", "차량|좌석|요금|도착 시간", "렌터카|항공 좌석 등급", sources="uber_request"),
        F("ride_hailing.schedule", "차량 예약 호출", "Schedule a ride", "택시 예약|나중에 승차|픽업 시간 예약|사전 호출", "reserve ride|ride later|schedule pickup|book car in advance", "날짜|시간|픽업|목적지|예약 요금", "음식 예약 배달|식당 예약", "submit", sources="uber_reserve"),
        F("ride_hailing.multiple_stops", "경유지 추가", "Add ride stops", "택시 경유|여러 목적지|중간 정차 추가|경유 순서", "add ride stop|multiple destinations|extra stop|reorder stops", "경유지|목적지|예상 요금|대기 시간", "항공 다구간|대중교통 환승", "change", sources="uber_multistop"),
        F("ride_hailing.saved_places", "승차 즐겨찾는 장소", "Saved ride places", "집 주소 저장|회사 위치|자주 가는 곳|승차 장소 즐겨찾기", "save home address|work location|favorite places|saved ride destination", "집|회사|주소|바로가기", "숙소 위시리스트|지도 저장 목록", "change", sources="uber_saved_places"),
        F("ride_hailing.pickup_preferences", "픽업 접근성 선호", "Ride pickup preferences", "기사 도착 신호|경적 요청|차량 불빛|보행 보조기 안내", "driver arrival signal|honk preference|flash lights|mobility aid note", "연락 방법|식별 방법|접근성|픽업", "배달 요청사항|차량 유형", "change", sources="uber_pickup_preferences"),
        F("ride_hailing.accessible_vehicle", "접근성 차량 찾기", "Accessible ride option", "휠체어 차량|승하차 보조|접근 가능한 택시|WAV", "wheelchair vehicle|boarding assistance|accessible car|WAV ride", "휠체어|보조|차량 옵션|추가 시간", "항공 접근성 좌석|대중교통 접근성", sources="uber_accessible_vehicle"),
        F("ride_hailing.rider_pin", "승차 PIN 확인", "Rider PIN verification", "기사에게 PIN|승차 확인 코드|차량 탑승 인증|안전 핀", "give driver PIN|ride verification code|verify vehicle pickup|safety pin", "PIN|기사|차량|승차 시작", "SIM PIN|카드 PIN", "sensitive", sources="uber_verify_ride"),
        F("ride_hailing.business_profile", "업무용 승차 프로필", "Business ride profile", "회사 택시 프로필|업무 경비 승차|법인 결제 승차|출장 프로필", "company ride profile|business travel ride|corporate payment ride|work trip profile", "업무 이메일|회사 카드|영수증|경비", "개인 승차|은행 계정", "change", sources="uber_business_profile"),
        F("ride_hailing.expense_code", "승차 경비 코드", "Ride expense code", "프로젝트 코드|비용 센터|택시 경비 메모|업무 목적", "project code|cost center|ride expense memo|business purpose", "업무 프로필|코드|영수증|정책", "프로모션 코드|배송 코드", "change", sources="uber_expense_memo|uber_business_profile"),
        F("ride_hailing.wait_fee_dispute", "승차 대기 요금 이의", "Dispute ride wait-time fee", "택시 대기비 환불|잘못된 대기 요금|승차 수수료 이의|추가 시간 요금 신고", "wait fee refund|incorrect waiting charge|ride fee dispute|extra time charge issue", "여행 내역|요금|접근성 추가 시간|환불", "음식 배달 문제|카드 거래 이의", "submit", sources="uber_wait_fee"),
    ),
    G(
        "retail_banking", "retail_banking.hub", "모바일 은행 업무", "Retail banking", "financial_service",
        "은행 계좌|체크카드|수표|송금|입금", "bank account|debit card|check|wire|deposit",
        "투자 주문|보험 계약|공과금", "investment order|insurance policy|utility bill",
        "government_digital.hub", "boa_mobile_features|boa_check_deposit|chase_wire|chase_payment_safety",
        F("retail_banking.balances", "계좌 잔액", "Bank account balances", "통장 잔액|사용 가능 금액|예금 잔고|계좌별 금액", "checking balance|available funds|deposit balance|account amounts", "계좌|현재 잔액|사용 가능|보류", "거래 내역|투자 포트폴리오", "sensitive", sources="boa_mobile_features"),
        F("retail_banking.mobile_check_deposit", "모바일 수표 입금", "Mobile check deposit", "수표 사진 입금|체크 입금|모바일 디파짓|수표 촬영", "deposit check by photo|check deposit|mobile deposit|capture check", "앞면|뒷면|입금 계좌|금액|제출", "현금 이체|문서 스캔", "submit", sources="boa_check_deposit"),
        F("retail_banking.deposit_status", "수표 입금 상태", "Check deposit status", "입금 처리 중|수표 승인 확인|모바일 입금 내역|입금 보류", "deposit processing|check approval status|mobile deposit history|deposit hold", "수표|접수|처리|가용 일자", "송금 상태|환불 상태", "sensitive", sources="boa_check_deposit"),
        F("retail_banking.wire_recipient", "전신 송금 수취인", "Wire transfer recipient", "해외 송금 받는 사람|송금 대상 추가|수취 은행|SWIFT 수취인", "wire beneficiary|add wire recipient|recipient bank|SWIFT payee", "이름|은행|계좌|SWIFT|국가", "일반 연락처|티켓 양도", "submit", sources="chase_wire|chase_payment_safety"),
        F("retail_banking.wire_send", "전신 송금 보내기", "Send wire transfer", "해외 송금 실행|와이어 전송|국내 전신 송금|고액 송금", "send international wire|make wire transfer|domestic wire|high-value transfer", "수취인|금액|수수료|환율|확인", "일반 계좌 이체|청구서 납부", "submit", sources="chase_wire|chase_payment_safety"),
        F("retail_banking.wire_status", "전신 송금 상태", "Wire transfer status", "와이어 처리 확인|해외 송금 추적|송금 활동|전신 송금 내역", "wire processing status|track international transfer|wire activity|wire history", "보낸 날짜|상태|수취인|금액", "택배 추적|항공 상태", "sensitive", sources="chase_wire"),
        F("retail_banking.card_pin", "체크카드 PIN 관리", "Debit card PIN", "카드 비밀번호 변경|ATM PIN|체크카드 핀 설정|핀 재설정", "change card PIN|ATM PIN|debit PIN settings|reset pin", "체크카드|PIN|본인 확인|ATM", "SIM PIN|승차 PIN", "submit", sources="boa_account_access|boa_debit_card_faq"),
        F("retail_banking.card_limits", "카드 사용 한도", "Card spending limits", "체크카드 한도|ATM 출금 한도|일일 결제 제한|카드 한도 변경", "debit card limit|ATM withdrawal limit|daily purchase limit|change card limit", "일일 한도|ATM|결제|변경", "데이터 한도|예산 알림", "submit", sources="boa_account_access|boa_debit_card_faq"),
        F("retail_banking.card_replace", "은행 카드 교체", "Replace bank card", "손상 카드 재발급|만료 카드 교체|새 체크카드|카드 배송", "replace damaged card|expired card replacement|new debit card|card delivery", "카드|교체 사유|배송 주소|확인", "카드 잠금|결제수단 삭제", "submit", sources="boa_debit_card_faq"),
        F("retail_banking.transaction_dispute", "은행 거래 이의", "Dispute bank transaction", "모르는 결제 신고|승인하지 않은 거래|체크카드 이의 제기|사기 거래", "report unknown charge|unauthorized transaction|debit dispute|fraudulent payment", "거래 선택|사유|증빙|제출", "승차 요금 이의|청구서 분쟁", "submit", sources="chase_payment_safety|boa_mobile_features"),
        F("retail_banking.direct_deposit", "급여 자동 입금 정보", "Direct deposit details", "급여 계좌 정보|라우팅 번호|자동 입금 설정|고용주 제출 정보", "payroll account details|routing number|set up direct deposit|employer deposit form", "계좌 번호|라우팅|고용주|양식", "자동이체 결제|전신 송금", "sensitive", sources="boa_direct_deposit"),
        F("retail_banking.check_order", "은행 수표 주문", "Order bank checks", "수표책 신청|새 수표 주문|입금표 주문|수표 배송 상태", "order checkbook|new checks|deposit tickets|check order status", "계좌|수표 디자인|배송|비용", "모바일 수표 입금|음식 주문", "submit", sources="boa_mobile_features"),
    ),
    G(
        "government_digital", "government_digital.hub", "정부 온라인 서비스", "Digital government services", "public_service",
        "정부 계정|신원 확인|여권|이민 사건|민원", "government account|identity verification|passport|immigration case|public service",
        "은행 계정|회사 워크스페이스|병원 기록", "bank account|company workspace|medical record",
        "retail_banking.hub", "login_gov_auth|passport_renew|passport_status|uscis_case|uscis_appointment",
        F("government_digital.identity_verify", "정부 계정 신원 확인", "Government identity verification", "공공서비스 본인 확인|신분증 인증|정부 계정 인증|온라인 신원 검증", "public service identity proofing|verify ID|government account verification|online identity check", "신분증|사회보장번호|주소|셀카|확인", "은행 KYC|앱 로그인", "submit", sources="login_gov_identity"),
        F("government_digital.auth_methods", "정부 계정 인증 수단", "Government account authentication methods", "보안 키 추가|인증 앱|백업 코드|공공 계정 2단계 인증", "add security key|authenticator app|backup codes|government account MFA", "인증 수단|보안 키|전화|백업", "일반 앱 2단계 인증|생체 잠금", "change", sources="login_gov_auth"),
        F("government_digital.passport_apply", "여권 신규 신청", "Apply for passport", "첫 여권 신청|성인 여권 발급|여권 신청 준비|여권 서류 제출", "first passport|adult passport application|prepare passport application|submit passport documents", "자격|사진|서류|수수료|제출", "여권 갱신|비자 신청", "submit", sources="passport_apply"),
        F("government_digital.passport_renew", "여권 온라인 갱신", "Renew passport online", "여권 재발급|만료 여권 갱신|온라인 여권 신청|여권 연장", "passport renewal|renew expired passport|online passport application|extend passport", "갱신 자격|사진|수수료|기존 여권", "여권 신규|운전면허 갱신", "submit", sources="passport_renew"),
        F("government_digital.passport_status", "여권 신청 상태", "Passport application status", "여권 처리 조회|여권 배송 확인|신청 진행 상황|여권 승인 여부", "passport processing|passport delivery status|application progress|passport approval", "접수|처리|승인|우편 발송", "이민 사건 상태|택배 상태", "sensitive", sources="passport_status"),
        F("government_digital.passport_records", "여권 기록 사본", "Passport record copies", "과거 여권 신청 기록|여권 문서 사본|여권 기록 요청|생명 사건 기록", "past passport application record|passport document copy|request passport records|life event record", "본인|자녀|권한|사본 요청", "현재 여권 상태|의료 기록", "submit", sources="passport_status"),
        F("government_digital.immigration_case", "이민 사건 상태", "Immigration case status", "USCIS 케이스 조회|접수 번호 상태|이민 신청 진행|체류 사건 확인", "USCIS case status|receipt number status|immigration application progress|petition tracking", "접수 번호|현재 단계|결정|통지", "여권 상태|법원 사건", "sensitive", sources="uscis_case"),
        F("government_digital.processing_times", "정부 신청 처리 시간", "Government case processing times", "이민 처리 기간|공공 신청 예상 시간|사무소별 처리|케이스 대기 시간", "immigration processing time|public application estimate|office processing time|case wait time", "양식|사무소|날짜|예상", "식당 대기 시간|택배 도착 시간", sources="uscis_case|uscis_appointment"),
        F("government_digital.address_change", "정부 사건 주소 변경", "Change address for government case", "USCIS 주소 변경|공공 기록 주소 수정|이민 우편 주소|사건 연락처 변경", "USCIS address change|update public record address|immigration mailing address|case contact update", "사건|새 주소|우편|제출", "배송 주소 변경|은행 주소", "submit", sources="uscis_case|uscis_appointment"),
        F("government_digital.case_inquiry", "정부 사건 문의", "Submit government case inquiry", "이민 사건 질문|통지 오류 문의|지연 신고|공공 신청 도움 요청", "immigration case question|notice error inquiry|delay request|public application help", "사건 번호|문의 유형|설명|제출", "일반 고객센터|보험 청구", "submit", sources="uscis_case"),
        F("government_digital.office_appointment", "정부 사무소 방문 예약", "Government office appointment", "이민 사무소 예약|공공기관 방문|대면 민원 예약|긴급 문서 약속", "immigration office appointment|public office visit|in-person service booking|urgent document appointment", "서비스 유형|사무소|날짜|접근성", "병원 예약|식당 예약", "submit", sources="uscis_appointment"),
        F("government_digital.form_filing", "정부 양식 온라인 제출", "File government form online", "이민 양식 제출|공공 신청서 작성|전자 민원 접수|정부 서류 업로드", "file immigration form|public application|electronic petition|upload government documents", "양식|증빙|서명|수수료|제출", "세금 신고|보험 청구", "submit", sources="uscis_file_online"),
        F("government_digital.fee_calculator", "정부 신청 수수료 계산", "Government filing fee calculator", "이민 양식 비용|공공 신청 수수료|접수 비용 계산|정부 요금 확인", "immigration form fee|public application charge|filing cost calculator|government fee", "양식 종류|신청자|수수료|면제", "배송비|항공 운임", sources="uscis_fee_calculator|passport_renew"),
    ),
    G(
        "healthcare_provider", "healthcare_provider.hub", "의료기관 서비스", "Healthcare provider services", "health_service",
        "병원|의료기관|진료 의뢰|건강 기록|환자 포털", "hospital|health provider|referral|clinical record|patient portal",
        "보험 보장|약국 주문|운동 기록", "insurance coverage|pharmacy order|fitness tracking",
        "digital_health.hub", "nhs_app_help|nhs_appointments|nhs_messages|nhs_records|va_manage_health",
        F("healthcare_provider.appointment_notes", "진료 기록 메모", "Appointment notes", "의사 진료 노트|방문 기록|상담 내용|과거 진료 요약", "clinician appointment notes|visit record|consultation notes|past visit summary", "진료 날짜|의료진|메모|후속 조치", "새 진료 예약|검사 결과", "sensitive", sources="nhs_appointments|nhs_records"),
        F("healthcare_provider.referral_status", "진료 의뢰 상태", "Medical referral status", "병원 리퍼럴|전문의 의뢰|진료 의뢰 진행|의뢰서 확인", "hospital referral|specialist referral|referral progress|referral details", "의뢰 기관|전문의|상태|다음 단계", "보험 청구 상태|처방 상태", "sensitive", sources="nhs_appointments"),
        F("healthcare_provider.waiting_lists", "병원 대기 명단", "Healthcare waiting lists", "진료 대기 순서|수술 대기|병원 웨이팅|예상 대기", "appointment waitlist|surgery waiting list|hospital queue|estimated wait", "서비스|의료기관|대기 상태|예상", "식당 웨이팅|고객센터 대기", "sensitive", sources="nhs_appointments"),
        F("healthcare_provider.hospital_documents", "병원 문서", "Hospital documents", "병원 편지|진료 의뢰서|검사 문서|의료 파일 다운로드", "hospital letters|referral document|clinical documents|download medical file", "문서 날짜|의료기관|다운로드|민감 정보", "보험 문서|정부 양식", "sensitive", sources="nhs_app_help|nhs_records"),
        F("healthcare_provider.test_trends", "검사 결과 추세", "Clinical test trends", "혈액 검사 그래프|수치 변화|검사 이력 비교|참고 범위", "blood test graph|result changes|compare test history|reference range", "검사명|날짜|수치|참고 범위", "투자 가격 그래프|공과금 사용량", "sensitive", sources="nhs_records"),
        F("healthcare_provider.allergies", "알레르기·이상 반응 기록", "Allergies and adverse reactions", "의료 알레르기|약물 반응|건강 상태 알레르기|이상 반응", "medical allergies|drug reaction|health condition allergy|adverse reaction", "알레르기 항목|반응|기록 날짜|의료진", "음식 알레르기 필터|앱 권한", "sensitive", sources="nhs_app_help|nhs_records"),
        F("healthcare_provider.care_plan", "개인 진료 계획", "Personal care plan", "치료 계획|케어 플랜|건강 관리 계획|의료 목표", "treatment plan|care plan|health management plan|clinical goals", "진단|목표|담당 팀|다음 단계", "보험 플랜|운동 계획", "sensitive", sources="nhs_app_terms"),
        F("healthcare_provider.proxy_access", "가족·보호자 의료 접근", "Family and carer health access", "자녀 건강 관리|보호자 계정|대리 의료 서비스|가족 환자 전환", "manage child's health|carer account|proxy health access|switch family patient", "대상 환자|권한|관계|민감 기록", "가족 결제|워크스페이스 게스트", "submit", sources="nhs_family_access"),
        F("healthcare_provider.online_consultation", "온라인 의료 상담 요청", "Online medical consultation", "의사에게 건강 문제 문의|비대면 증상 상담|GP 질문|의료 조언 요청", "ask provider about health problem|online symptom consultation|GP question|request clinical advice", "증상|긴급도|사진|의료기관|제출", "긴급 신고|일반 고객센터", "submit", sources="nhs_appointments|nhs_messages"),
        F("healthcare_provider.questionnaire", "의료 사전 문진", "Medical questionnaire", "병원 설문|진료 전 질문|증상 양식|환자 문진표", "hospital questionnaire|pre-visit questions|symptom form|patient intake form", "증상|약물|병력|서명|제출", "교육 퀴즈|고객 설문", "submit", sources="nhs_app_terms|va_manage_health"),
        F("healthcare_provider.secure_inbox", "의료기관 보안 메시지함", "Secure healthcare inbox", "병원 메시지|의료진 답변|환자 포털 받은편지함|진료 알림", "hospital messages|care team reply|patient portal inbox|clinical notification", "의료기관|보낸 사람|날짜|민감 내용", "일반 이메일|보험 알림", "sensitive", sources="nhs_messages|va_manage_health"),
        F("healthcare_provider.pharmacy_nomination", "처방 수령 약국 지정", "Choose prescription pharmacy", "기본 약국 선택|처방전 보낼 약국|약국 변경|수령처 지정", "choose default pharmacy|send prescription to pharmacy|change nominated pharmacy|pickup pharmacy", "약국|주소|처방|선택 확인", "일반 약국 검색|배송 주소", "change", sources="nhs_pharmacy"),
        F("healthcare_provider.fit_note", "진단서·근무 확인서 요청", "Request medical fit note", "병가 진단서|업무 가능 확인서|의사 소견서 요청|근무용 의료 문서", "sick note|fit note|doctor letter request|work medical certificate", "기간|고용주|건강 문제|요청", "보험 증명서|정부 인증서", "submit", sources="nhs_fit_note"),
        F("healthcare_provider.organ_donation", "장기 기증 결정", "Organ donation decision", "장기 기증 등록|기증 의사 변경|기증 선택 확인|장기 기증 철회", "register organ donation|change donation choice|confirm donation decision|withdraw donation preference", "기증 선택|대리 결정자|확인|법적 영향", "혈액 기증 예약|마케팅 동의", "submit", sources="nhs_organ_donation"),
    ),
    G(
        "workspace_administration", "workspace_admin.hub", "워크스페이스 관리", "Workspace administration", "organization_admin",
        "회사 워크스페이스|조직 관리자|채널|보존 정책|공유 드라이브", "workspace|organization admin|channel|retention policy|shared drive",
        "개인 채팅|일반 파일 보기|기기 설정", "personal chat|ordinary file view|device settings",
        "documents.hub", "slack_retention|slack_export|slack_import|slack_channels|drive_share|drive_shared_drives|drive_access",
        F("workspace_admin.data_retention", "워크스페이스 데이터 보존", "Workspace data retention", "조직 보존 정책|데이터 유지 기간|메시지 파일 보존|삭제 주기", "organization retention policy|data lifetime|message and file retention|deletion schedule", "기간|영구 삭제|조직 정책|확인", "기기 저장 공간|브라우저 기록 삭제", "submit", sources="slack_retention"),
        F("workspace_admin.message_retention", "채널 메시지 보존", "Channel message retention", "대화 보존 기간|메시지 자동 삭제|채널 기록 유지|DM 보존", "conversation retention|auto-delete messages|channel history lifetime|DM retention", "채널 유형|기간|편집 기록|삭제", "알림 기록|이메일 보관", "submit", sources="slack_retention"),
        F("workspace_admin.file_retention", "워크스페이스 파일 보존", "Workspace file retention", "파일 자동 삭제|업로드 보존 기간|삭제 파일 유지|조직 파일 기록", "auto-delete files|upload retention|keep deleted files|workspace file history", "파일|기간|삭제|내보내기", "클라우드 휴지통|사진 백업", "submit", sources="slack_retention"),
        F("workspace_admin.data_export", "워크스페이스 데이터 내보내기", "Export workspace data", "조직 기록 다운로드|채널 JSON 내보내기|대화 백업|워크스페이스 ZIP", "download workspace history|export channel JSON|conversation backup|workspace ZIP", "채널|DM|멤버|기간|내보내기", "연락처 내보내기|의료 기록 다운로드", "submit", sources="slack_export"),
        F("workspace_admin.data_import", "워크스페이스 데이터 가져오기", "Import workspace data", "다른 워크스페이스 병합|채널 가져오기|멤버 메시지 이전|조직 마이그레이션", "merge workspaces|import channels|migrate members and messages|organization migration", "원본|대상|채널 매핑|멤버|실행", "연락처 가져오기|기기 복원", "submit", sources="slack_import"),
        F("workspace_admin.guests", "워크스페이스 게스트", "Workspace guest access", "외부 게스트 관리|단일 채널 게스트|게스트 만료|협력사 계정", "external guest management|single-channel guest|guest expiration|partner account", "게스트|허용 채널|만료|권한", "일반 멤버 역할|가족 계정", "submit", sources="slack_import|drive_share"),
        F("workspace_admin.external_collaboration", "외부 조직 협업", "External organization collaboration", "외부 도메인 공유|파트너 채널|방문자 공유|조직 밖 협업", "external domain sharing|partner channel|visitor sharing|outside organization collaboration", "외부 배지|도메인|권한|만료", "공개 링크|개인 메시지", "submit", sources="drive_share|drive_access"),
        F("workspace_admin.channel_archive", "채널 보관", "Archive workspace channel", "업무 채널 닫기|채널 아카이브|대화방 보관|프로젝트 채널 종료", "close work channel|archive channel|retain conversation|end project channel", "채널|검색 가능|새 메시지 차단|확인", "채팅 보관|이메일 보관", "submit", sources="slack_channels"),
        F("workspace_admin.channel_delete", "채널 영구 삭제", "Delete workspace channel", "업무 채널 삭제|채널 기록 영구 제거|대화방 완전 삭제|관리자 채널 삭제", "delete work channel|permanently remove channel history|erase conversation channel|admin channel deletion", "채널|영구 삭제|메시지 기록|관리자", "채널 보관|개인 채팅 삭제", "submit", sources="slack_channels"),
        F("workspace_admin.shared_drives", "공유 드라이브 관리", "Manage shared drives", "팀 드라이브|조직 파일 공간|공유 드라이브 만들기|부서 드라이브", "team drive|organization file space|create shared drive|department drive", "드라이브|조직 소유|파일|멤버", "내 드라이브|링크 공유", "submit", sources="drive_shared_drives"),
        F("workspace_admin.shared_drive_members", "공유 드라이브 멤버 권한", "Shared drive member permissions", "드라이브 관리자|콘텐츠 관리자|기여자|공유 드라이브 역할", "drive manager|content manager|contributor|shared drive role", "멤버|역할|파일 이동|삭제 권한", "워크스페이스 일반 역할|파일 단일 공유", "submit", sources="drive_shared_drives"),
        F("workspace_admin.file_access_requests", "파일 접근 요청 관리", "Manage file access requests", "문서 권한 요청|액세스 승인|파일 접근 거절|대기 중 공유 요청", "document permission request|approve access|deny file access|pending share request", "요청자|파일|권한 수준|승인|거절", "정부 신청 승인|티켓 양도", "submit", sources="drive_share|drive_access"),
        F("workspace_admin.sharing_restrictions", "조직 파일 공유 제한", "Organization sharing restrictions", "다운로드 금지|외부 공유 차단|편집자 공유 제한|복사 인쇄 제한", "disable download|block external sharing|limit editor resharing|prevent copy and print", "뷰어|댓글|편집|다운로드|외부", "브라우저 사이트 권한|앱 권한", "submit", sources="drive_share"),
    ),
    G(
        "parcel_courier", "parcel_courier.hub", "택배 수령 관리", "Parcel delivery management", "logistics_service",
        "택배|소포|배송 기사|수령 일정|운송장", "parcel|package|courier|delivery schedule|tracking number",
        "음식 배달|쇼핑 주문 자체|이사 서비스", "food delivery|store order itself|moving service",
        "shopping_logistics.hub", "ups_change_delivery|ups_my_choice|ups_tracking|ups_intercept",
        F("parcel_courier.delivery_calendar", "택배 배송 달력", "Package delivery calendar", "예정 소포 목록|오는 택배 달력|과거 배송|여러 주소 배송 일정", "incoming package list|delivery calendar|past shipments|multi-address schedule", "예정|과거|주소|날짜|소포", "식당 예약 달력|업무 일정", "sensitive", sources="ups_my_choice"),
        F("parcel_courier.delivery_window", "택배 배송 시간대", "Package delivery window", "2시간 배송 창|도착 시간 선택|예상 배달 시간|배송 시간 요청", "two-hour delivery window|choose arrival time|estimated delivery time|request delivery slot", "날짜|시간 범위|요금|확정", "음식 예약 배달|승차 예약", "submit", sources="ups_my_choice"),
        F("parcel_courier.proof_photo", "택배 배송 사진", "Proof of delivery photo", "문 앞 사진|배달 완료 사진|소포 놓은 위치|배송 증거", "doorstep photo|delivery confirmation image|package location photo|proof of delivery", "사진|배송 주소|완료 시간|놓은 장소", "신분증 사진|수표 사진", "sensitive", sources="ups_my_choice|ups_tracking"),
        F("parcel_courier.alerts", "택배 배송 알림", "Package delivery alerts", "소포 상태 푸시|배송 예정 알림|택배 문자|도착 통지", "package status notification|delivery alert|shipment text|arrival notice", "출발|배송 중|도착|예외", "쇼핑 프로모션|항공 가격 알림", "change", sources="ups_my_choice|ups_tracking"),
        F("parcel_courier.hold", "택배 보관 요청", "Hold package delivery", "휴가 중 배송 보류|소포 보관|나중에 배달|픽업 지점 보관", "vacation hold|keep package|deliver later|hold for pickup", "소포|기간|보관 장소|수령", "우편 보관 외 일반|주문 취소", "submit", sources="ups_change_delivery|ups_my_choice"),
        F("parcel_courier.reroute", "택배 배송지 변경", "Reroute package", "다른 주소로 택배|이웃에게 배송|소포 우회|배송 위치 변경", "send package to another address|deliver to neighbor|redirect parcel|change delivery location", "현재 주소|새 주소|수수료|제한", "쇼핑 주문 주소 변경|이사 주소", "submit", sources="ups_change_delivery|ups_my_choice"),
        F("parcel_courier.reschedule", "택배 배송일 변경", "Reschedule package delivery", "소포 날짜 변경|다른 날 배달|배송 일정 수정|택배 도착일 선택", "change package date|deliver another day|update delivery schedule|choose arrival date", "현재 날짜|새 날짜|가능 여부|요금", "숙박 날짜 변경|승차 예약", "submit", sources="ups_change_delivery|ups_my_choice"),
        F("parcel_courier.access_point", "택배 픽업 지점", "Package pickup location", "편의점 수령|UPS Access Point|소포 찾을 곳|택배 보관소", "parcel shop pickup|UPS Access Point|package collection point|courier locker", "지점|영업 시간|보관 기한|신분증", "음식 픽업|약국 수령", "submit", sources="ups_change_delivery|ups_my_choice"),
        F("parcel_courier.driver_instructions", "택배 기사 요청사항", "Package driver instructions", "문 앞에 두기|경비실 배송|택배 놓는 곳|배달 메모", "leave at door|deliver to reception|package drop location|courier note", "출입|장소|기사|주소", "음식 배달 요청사항|숙소 체크인", "submit", sources="ups_my_choice"),
        F("parcel_courier.release", "택배 서명 면제", "Authorize package release", "서명 없이 배송|소포 릴리스|부재중 수령 승인|택배 인수 허가", "release without signature|authorize delivery|approve unattended drop|package release", "고가 소포|서명|책임|주소", "전자 서명|문서 승인", "submit", sources="ups_my_choice"),
        F("parcel_courier.intercept", "발송 택배 가로채기", "Intercept sent package", "보낸 소포 회수|배송 중지|발송인 주소 변경|택배 반환 요청", "recall sent parcel|stop shipment|sender reroute|return package to sender", "발송인|배송 전|반환|새 주소|수수료", "수령 택배 변경|쇼핑 주문 취소", "submit", sources="ups_intercept"),
        F("parcel_courier.customs_fees", "택배 관세·수입료", "Package customs and import fees", "수입 관세 납부|통관 비용|택배 세금|세관 보류", "pay import duty|customs charge|parcel tax|customs hold", "운송장|관세|세금|통관|결제", "쇼핑 세금|항공 수하물 요금", "submit", sources="ups_tracking"),
        F("parcel_courier.missing_claim", "분실 택배 조사", "Missing package claim", "배달 완료인데 없음|소포 분실 신고|택배 못 찾음|배송 조사 시작", "delivered but missing|report lost parcel|cannot find package|start delivery investigation", "운송장|배송 사진|주소|신고 기한", "음식 누락|카드 분실", "submit", sources="ups_tracking"),
        F("parcel_courier.damage_claim", "파손 택배 청구", "Damaged package claim", "소포 파손 신고|택배 손상 배상|깨진 상품 배송|손상 증빙 제출", "report damaged parcel|courier damage claim|broken item delivery|submit damage evidence", "운송장|사진|포장|가액|신고", "쇼핑 반품|보험 사고 청구", "submit", sources="ups_tracking"),
    ),
)


def _aliases(seed: FeatureSeed, locale: str) -> list[str]:
    if locale == "ko-KR":
        return _dedupe([
            seed.name_ko, *seed.ko_aliases,
            f"{seed.name_ko} 메뉴", f"{seed.name_ko} 관리", f"{seed.name_ko} 찾기",
        ])
    return _dedupe([
        seed.name_en, *seed.en_aliases,
        f"{seed.name_en} menu", f"manage {seed.name_en.lower()}", f"find {seed.name_en.lower()}",
    ])


def _risk_cues(seed: FeatureSeed) -> dict[str, list[str]]:
    if seed.mode == "submit":
        return {
            "final_action": [seed.name_ko, seed.name_en, "제출", "확정", "submit", "confirm"],
            "consequence": ["외부 상태 변경", "비용 또는 권리 영향", "changes external state", "may affect money or rights"],
            "user_boundary": ["최종 버튼은 사용자가 직접 누름", "final action requires the user's click"],
        }
    if seed.mode == "change":
        return {
            "setting_change": [seed.name_ko, seed.name_en, "변경", "저장", "change", "save"],
            "user_boundary": ["변경 저장 전 사용자 확인", "user confirmation before saving"],
        }
    if seed.mode == "sensitive":
        return {
            "sensitive_access": [seed.name_ko, seed.name_en, "개인정보", "민감 정보", "personal data", "sensitive information"],
            "user_boundary": ["민감 화면 열기 전 사용자 확인", "confirm before opening sensitive data"],
        }
    return {
        "navigation_scope": [seed.name_ko, seed.name_en],
        "safe_boundary": ["화면 탐색만 허용", "navigation only"],
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
        "description": f"{group.root_ko} 기능을 탐색하는 범용 허브. General hub for {group.root_en.lower()}.",
        "risk_level": "low",
        "automation_policy": "safe_navigation",
        "terminal": False,
        "state_changing": False,
        "legacy_tags": [group.domain, "v5_service_gaps", "hub"],
        "role_hints": ["button", "menuitem", "tab", "heading", "image_button"],
        "aliases": {
            "ko-KR": _dedupe([group.root_ko, *group.ko_context, f"{group.root_ko} 메뉴", f"{group.root_ko} 관리"]),
            "en-US": _dedupe([group.root_en, *group.en_context, f"{group.root_en} menu", f"manage {group.root_en.lower()}"]),
        },
        "positive_context": _dedupe([*group.ko_context, *group.en_context, "전체 메뉴", "main menu"]),
        "negative_context": _dedupe([*group.negative_ko, *group.negative_en]),
        "state_cues": {
            "visible": [group.root_ko, group.root_en],
            "loading": ["불러오는 중", "로딩", "loading", "please wait"],
            "offline": ["연결 없음", "오프라인", "no connection", "offline"],
            "error": ["다시 시도", "오류", "try again", "error"],
        },
        "risk_cues": {"safe_boundary": ["허브 탐색", "navigation hub"]},
        "source_refs": list(group.source_refs),
        "evidence_level": "official",
    }


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    metadata = MODE_METADATA[seed.mode]
    aliases_ko = _aliases(seed, "ko-KR")
    aliases_en = _aliases(seed, "en-US")
    return {
        "function_id": seed.function_id,
        "domain": group.domain,
        "scope": group.scope,
        "node_kind": metadata["node_kind"],
        "stop_policy": metadata["stop_policy"],
        "name_ko": seed.name_ko,
        "name_en": seed.name_en,
        "description": (
            f"{seed.name_ko} 목적지 또는 사용자 소유 최종 동작의 경계를 식별한다. "
            f"Identifies the {seed.name_en.lower()} destination or user-owned action boundary."
        ),
        "risk_level": metadata["risk_level"],
        "automation_policy": metadata["automation_policy"],
        "terminal": True,
        "state_changing": metadata["state_changing"],
        "legacy_tags": [group.domain, "v5_service_gaps", seed.function_id.rsplit(".", 1)[-1]],
        "role_hints": ["button", "menuitem", "tab", "text", "switch", "image_button", "link"],
        "aliases": {"ko-KR": aliases_ko, "en-US": aliases_en},
        "positive_context": _dedupe([*seed.positive, *group.ko_context[:3], *group.en_context[:3]]),
        "negative_context": _dedupe([*seed.negative, *group.negative_ko[:2], *group.negative_en[:2]]),
        "state_cues": {
            "visible": [seed.name_ko, seed.name_en, aliases_ko[1], aliases_en[1]],
            "disabled": ["사용할 수 없음", "비활성", "unavailable", "disabled"],
            "selected": ["선택됨", "현재", "selected", "current"],
            "loading": ["처리 중", "불러오는 중", "processing", "loading"],
            "error": ["다시 시도", "문제가 발생", "try again", "something went wrong"],
            "relogin_required": ["다시 로그인", "세션 만료", "sign in again", "session expired"],
            "permission_required": ["권한 필요", "접근 요청", "permission required", "request access"],
        },
        "risk_cues": _risk_cues(seed),
        "source_refs": list(seed.source_refs),
        "evidence_level": "official",
    }


def _normalized_phrase(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def _goal_cue_key(value: object) -> str:
    """Return the runtime-compatible punctuation-insensitive cue key."""

    return "".join(
        re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", str(value)).casefold(), flags=re.UNICODE)
    )


def _runtime_goal_key(value: object) -> str:
    """Mirror runtime pattern normalization, including common Korean particles."""

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


def _specific_goal_terms(domain_phrase: str, feature_phrase: str) -> list[str]:
    """Build a deterministic high-specificity domain/feature conjunction."""

    values = [_normalized_phrase(domain_phrase), _normalized_phrase(feature_phrase)]
    for phrase in (domain_phrase, feature_phrase):
        values.extend(
            _normalized_phrase(token)
            for token in re.split(r"[\s/·&+_\-]+", phrase)
            if token.strip()
        )
    return _dedupe(values)


def _semantic_aliases(seed: FeatureSeed, locale: str) -> list[str]:
    if locale == "ko-KR":
        return _dedupe([seed.name_ko, *seed.ko_aliases])
    return _dedupe([seed.name_en, *seed.en_aliases])


V5_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)


def _v5_alias_owners() -> dict[str, frozenset[str]]:
    owners: dict[str, set[str]] = {}
    for function in V5_FUNCTIONS:
        if not bool(function["terminal"]):
            continue
        for aliases in function["aliases"].values():  # type: ignore[union-attr]
            for alias in aliases:
                if key := _goal_cue_key(alias):
                    owners.setdefault(key, set()).add(str(function["function_id"]))
    return {key: frozenset(function_ids) for key, function_ids in owners.items()}


V5_ALIAS_OWNERS = _v5_alias_owners()


def _purpose_concepts(ko: str, en: str) -> dict[str, tuple[tuple[str, ...], ...]]:
    """Declare short, reusable consequence concepts, never benchmark prose.

    Each locale contains a conjunction of two to four independently useful
    semantic atoms.  The atoms deliberately describe the object and outcome
    (for example ``photographs + both sides + cheque``), rather than copying a
    UI label or an authored request sentence.  This lets the same rule survive
    politeness, word-order, and framing changes while remaining reviewable.
    """

    return {"ko-KR": (_terms(ko),), "en-US": (_terms(en),)}


# Purpose/consequence vocabulary for every v5 terminal.  Button aliases answer
# "what is the control called?"; these conjunctions answer "what result does
# the user mean?".  Keeping this as reviewed ontology data (instead of loading
# a benchmark at runtime) makes the production catalog deterministic and keeps
# evaluation provenance auditable.
V5_PURPOSE_CONCEPTS: dict[str, dict[str, tuple[tuple[str, ...], ...]]] = {
    "food_order.menu": _purpose_concepts("가격|재료|파는지", "dishes|prices|offers"),
    "food_order.dietary_filters": _purpose_concepts("식물성|안 되는 재료", "allergens|animal products|avoid"),
    "food_order.item_customize": _purpose_concepts("맵기|추가 재료|조절", "heat level|extras|adjust"),
    "food_order.substitution_preferences": _purpose_concepts("재료가 떨어|돌려받", "unavailable grocery|credited back"),
    "food_order.fulfillment": _purpose_concepts("집에서 받|매장에 가서", "brought to my address|collecting it in person"),
    "food_order.schedule": _purpose_concepts("저녁 여섯|도착|미리", "meal arrive|six|rather than"),
    "food_order.group_create": _purpose_concepts("여러 동료|각자 먹을 것|한 번에 정산", "shared basket|coworkers|own meals"),
    "food_order.group_invite": _purpose_concepts("참여할 주소|보내|동료", "send coworkers|shared meal|selections"),
    "food_order.group_budget": _purpose_concepts("사람마다|상한|회사", "cap|each coworker|lunch funds"),
    "food_order.fee_breakdown": _purpose_concepts("청구 예정액|음식값|항목별", "taxes|platform charges|total exceed"),
    "food_order.live_support": _purpose_concepts("도착 예정|담당자|이동이 멈", "human assistance|promised arrival|stopped moving"),
    "restaurant_booking.availability": _purpose_concepts("토요일 저녁|두 사람|시각", "Saturday evening|two diners|times"),
    "restaurant_booking.filters": _purpose_concepts("채식|조용|삼만 원", "cuisine|neighborhood|spend"),
    "restaurant_booking.table_options": _purpose_concepts("실내|바깥|자리", "inside|outdoors|counter"),
    "restaurant_booking.create": _purpose_concepts("자리|확보|토요일 저녁", "secure seats|chosen place|time"),
    "restaurant_booking.modify": _purpose_concepts("이미 잡|시각|참석 인원", "revise|existing dining commitment|how many people"),
    "restaurant_booking.cancel": _purpose_concepts("자리|놓아주|갈 수 없", "give up the seats|dinner plans|fell through"),
    "restaurant_booking.waitlist_join": _purpose_concepts("만석|내 차례|받아 두", "virtual queue|occupied|my party"),
    "restaurant_booking.waitlist_status": _purpose_concepts("몇 팀|언제 불|앞에", "parties are ahead|when|called"),
    "restaurant_booking.availability_alert": _purpose_concepts("취소가 생기|소식|원하는 저녁", "diner releases|preferred time|be told"),
    "restaurant_booking.message": _purpose_concepts("케이크|유아 의자|묻", "birthday cake|high chair|ask"),
    "restaurant_booking.rewards": _purpose_concepts("지난 외식|혜택|다음 방문", "benefit value|prior meals|next visit"),
    "lodging.search": _purpose_concepts("출장 날짜|밤을 보낼|후보", "places|sleep|travel dates"),
    "lodging.filters": _purpose_concepts("반려동물|주방|비용 조건", "kitchen|pet acceptance|spending ceiling"),
    "lodging.map": _purpose_concepts("행사장|지하철|위치", "conference site|transit|relative"),
    "lodging.wishlist": _purpose_concepts("후보|모아 두|다시 비교", "promising places|together|later decision"),
    "lodging.listing_details": _purpose_concepts("규칙|포함 시설|총 지불액", "property includes|visitors must obey|full amount"),
    "lodging.reserve": _purpose_concepts("머물 권리|확보|지정한 날짜", "secure|selected property|travel dates"),
    "lodging.trip_details": _purpose_concepts("확인 번호|주소|날짜", "confirmation number|address|dates"),
    "lodging.change_dates": _purpose_concepts("하루 더|나가는 날|늦추", "extend|existing stay|departure"),
    "lodging.cancel": _purpose_concepts("잠자리|포기|여행이 무산", "release|property|trip is no longer"),
    "lodging.checkin_instructions": _purpose_concepts("건물에 들어|열쇠|도착", "enter the building|obtain the key|arrive"),
    "lodging.host_message": _purpose_concepts("제공한 사람|늦은 도착|묻", "person providing the property|late arrival|ask"),
    "lodging.accessibility_filter": _purpose_concepts("휠체어|계단 없이|욕실", "wheelchair|step-free|bathroom"),
    "lodging.refund_preview": _purpose_concepts("돌려받|잃는지|잠자리", "recover|forfeit|property"),
    "flight_search.itinerary": _purpose_concepts("서울|파리|운항 조합", "fly|Seoul|Paris"),
    "flight_search.fare_filters": _purpose_concepts("탑승 칸|경유 횟수|수하물", "cabin|stops|bags"),
    "flight_search.flexible_dates": _purpose_concepts("출발일|앞뒤|저렴", "departure days|shifting|cost"),
    "flight_search.price_graph": _purpose_concepts("날짜별 비용|오르내|한 달", "rises|falls|month"),
    "flight_search.alternative_airports": _purpose_concepts("먼 공항|비용|도심", "departure and arrival airports|cheaper|nearby"),
    "flight_search.bag_fee_filter": _purpose_concepts("짐 한 개|맡기는 비용|실제 지출", "checked bag|amount due|included"),
    "flight_search.price_track": _purpose_concepts("금액이 내려|소식|노선", "notified|quoted amount|drops"),
    "flight_search.tracked_flights": _purpose_concepts("예전에|가격 변화|노선들", "routes|fares|previously"),
    "flight_search.emissions": _purpose_concepts("기후 영향|운항|비교", "climate impact|ways to fly|compare"),
    "flight_search.booking_link": _purpose_concepts("항공사|중개업체|진행", "airline|agency|complete payment"),
    "flight_search.self_transfer_warning": _purpose_concepts("구간 표|따로|짐을 다시", "independently issued legs|collecting bags|changing airports"),
    "event_ticket.search": _purpose_concepts("공연|경기|주말", "concerts|games|weekend"),
    "event_ticket.venue_info": _purpose_concepts("입구|주차장|반입 금지", "entrance|parking|bag rules"),
    "event_ticket.seat_map": _purpose_concepts("무대|출입구|관람 구역", "seating section|stage|exits"),
    "event_ticket.accessible_seats": _purpose_concepts("휠체어|동행인|함께 앉", "wheelchair user|companion|sit together"),
    "event_ticket.presale": _purpose_concepts("일반 판매|코드|먼저", "eligibility code|sales|everyone else"),
    "event_ticket.purchase": _purpose_concepts("입장 권리|사고|금액", "pay|admission|performance"),
    "event_ticket.mobile_entry": _purpose_concepts("직원|휴대전화|입장 증표", "scannable credential|phone|gate"),
    "event_ticket.wallet_add": _purpose_concepts("네트워크|카드 보관함|입장 증표", "payment passes|offline access|admission credential"),
    "event_ticket.transfer": _purpose_concepts("친구 명의|넘기|입장 권리", "send|admission entitlement|friend"),
    "event_ticket.transfer_accept": _purpose_concepts("내 계정|받아들이|친구", "claim|sent to my account|admission entitlement"),
    "event_ticket.resale": _purpose_concepts("다른 구매자|내놓|입장 권리", "offer|another buyer|marketplace"),
    "event_ticket.refund": _purpose_concepts("행사가 취소|비용|돌려받", "recover the money|organizer called off|admission"),
    "event_ticket.updates": _purpose_concepts("시간|장소|바뀌", "organizer moved|time|location"),
    "ride_hailing.pickup_pin": _purpose_concepts("반대편 도로|타는 지점|옮기", "meeting point|side of the street|move"),
    "ride_hailing.vehicle_options": _purpose_concepts("인원수|짐의 양|차 종류", "car categories|party|luggage"),
    "ride_hailing.schedule": _purpose_concepts("내일 새벽|차가 미리|시각", "car|arrive tomorrow|specified time"),
    "ride_hailing.multiple_stops": _purpose_concepts("중간 목적지|친구를 태운|공항", "friend's address|origin|final destination"),
    "ride_hailing.saved_places": _purpose_concepts("집과 회사|기억|다음 호출", "remember|home and office|future journeys"),
    "ride_hailing.pickup_preferences": _purpose_concepts("문자로 연락|승차에 시간|기사", "text communication|extra boarding time|meets me"),
    "ride_hailing.accessible_vehicle": _purpose_concepts("휠체어|접지 않고|차종", "vehicle|remain in my wheelchair|carrying me"),
    "ride_hailing.rider_pin": _purpose_concepts("숫자 코드|탑승 전|기사", "short code|entering the car|correct vehicle"),
    "ride_hailing.business_profile": _purpose_concepts("출장 이동|개인 기록|회사", "work journeys|company billing|personal"),
    "ride_hailing.expense_code": _purpose_concepts("회계팀|프로젝트|분류 값", "project reference|accounting|classify"),
    "ride_hailing.wait_fee_dispute": _purpose_concepts("기사|도착하기|대기 비용|부당", "challenge a charge|before the car reached|time attributed"),
    "retail_banking.balances": _purpose_concepts("은행 계좌|쓸 수 있는 돈|처리 중", "money|currently available|bank accounts"),
    "retail_banking.mobile_check_deposit": _purpose_concepts("앞뒤|촬영|종이 지급 증서", "photographs|both sides|paper cheque"),
    "retail_banking.deposit_status": _purpose_concepts("사진으로 보낸 수표|승인|돈을 쓸", "photographed cheque|accepted|funds become usable"),
    "retail_banking.wire_recipient": _purpose_concepts("받을 사람|은행 정보|신원", "new beneficiary|bank-to-bank|verify"),
    "retail_banking.wire_send": _purpose_concepts("큰 금액|수취 은행|실제 전송", "large sum|beneficiary|final authorization"),
    "retail_banking.wire_status": _purpose_concepts("이미 보낸|접수|도착", "previously authorized|pending|completed"),
    "retail_banking.card_pin": _purpose_concepts("현금 인출|비밀 숫자|바꾸", "secret digits|ATM transaction|replace"),
    "retail_banking.card_limits": _purpose_concepts("하루|최대 금액|낮추", "reduce|card|single day"),
    "retail_banking.card_replace": _purpose_concepts("금이 가|새 실물 카드|발급", "new physical card|cracked|obtain"),
    "retail_banking.transaction_dispute": _purpose_concepts("승인하지 않은|출금|조사", "debit|did not authorize|investigate"),
    "retail_banking.direct_deposit": _purpose_concepts("회사 급여|고용주|번호", "employer|pay wages|routing"),
    "retail_banking.check_order": _purpose_concepts("종이 지급 증서|묶음|우편", "booklet|paper cheques|mail"),
    "government_digital.identity_verify": _purpose_concepts("신분증|얼굴|본인", "identification|biometric|prove"),
    "government_digital.auth_methods": _purpose_concepts("보안 키|인증 앱|추가", "hardware key|authenticator|enter"),
    "government_digital.passport_apply": _purpose_concepts("처음 발급|해외여행용 신분 문서", "first|international travel identity document|obtain"),
    "government_digital.passport_renew": _purpose_concepts("만료|다시 유효|인터넷", "expiring|extend the validity|website"),
    "government_digital.passport_status": _purpose_concepts("심사|제작|어디까지", "submitted|review|production"),
    "government_digital.passport_records": _purpose_concepts("과거|발급|공식 사본", "official copy|historical|issuance records"),
    "government_digital.immigration_case": _purpose_concepts("접수 번호|체류|심사", "receipt number|immigration|pending"),
    "government_digital.processing_times": _purpose_concepts("정부 신청|기간|예상", "months|public-agency submission|takes"),
    "government_digital.address_change": _purpose_concepts("우편물|새 집|관청", "agency|correspondence|new home"),
    "government_digital.case_inquiry": _purpose_concepts("처리 기간을 넘|관청|답변", "ask the agency|exceeded|decision time"),
    "government_digital.office_appointment": _purpose_concepts("공무원|대면|시간", "in person|officer|arrange a time"),
    "government_digital.form_filing": _purpose_concepts("정부 양식|증빙|인터넷", "completed public-agency form|evidence|online portal"),
    "government_digital.fee_calculator": _purpose_concepts("내야 할 비용|조건별|계산", "calculate|amount due|public-agency submission"),
    "healthcare_provider.appointment_notes": _purpose_concepts("지난 진료|의료진이 적|후속 지시", "clinician recorded|previous visit|recommended"),
    "healthcare_provider.referral_status": _purpose_concepts("전문의|의뢰|접수", "request for specialist care|received|assigned"),
    "healthcare_provider.waiting_lists": _purpose_concepts("치료 차례|명단|내 위치", "patients awaiting|procedure|place"),
    "healthcare_provider.hospital_documents": _purpose_concepts("퇴원 안내|진료 서류|병원", "discharge letters|documents|medical facility"),
    "healthcare_provider.test_trends": _purpose_concepts("같은 검사|여러 날짜|변", "same clinical measurement|several dates|changed"),
    "healthcare_provider.allergies": _purpose_concepts("약물|과민 반응|피해야", "substances|medicines|harmful reactions"),
    "healthcare_provider.care_plan": _purpose_concepts("치료 목표|다음 조치|계획", "agreed goals|next actions|treatment"),
    "healthcare_provider.proxy_access": _purpose_concepts("부모님 동의|대신 의료|연결", "authorized access|elderly parent|consent"),
    "healthcare_provider.online_consultation": _purpose_concepts("새로 생긴 증상|비대면 답변|의료진", "new symptoms|remotely|clinician"),
    "healthcare_provider.questionnaire": _purpose_concepts("진료 전에|증상|병력", "clinician's questions|symptoms and history|before the visit"),
    "healthcare_provider.secure_inbox": _purpose_concepts("민감한 안내|보호된 공간|의료기관", "confidential correspondence|protected account|care provider"),
    "healthcare_provider.pharmacy_nomination": _purpose_concepts("반복 처방약|기본 약국|정하", "chemist|routinely receive|prescriptions"),
    "healthcare_provider.fit_note": _purpose_concepts("근무하지 못|회사에 증명|의료 문서", "evidence|illness|ability to work"),
    "healthcare_provider.organ_donation": _purpose_concepts("사망 후|장기|등록하거나 철회", "organs|after death|final decision"),
    "workspace_admin.data_retention": _purpose_concepts("조직의 대화와 파일|얼마 동안|규칙", "organization-wide lifetime|conversations|uploads"),
    "workspace_admin.message_retention": _purpose_concepts("특정 채널|오래된 대화|기간 뒤", "old conversations|one team discussion area|chosen period"),
    "workspace_admin.file_retention": _purpose_concepts("올린 파일|기간이 지나|자동", "uploaded files|automatically|age"),
    "workspace_admin.data_export": _purpose_concepts("감사 목적|대화 기록|묶음", "downloadable archive|conversations|audit"),
    "workspace_admin.data_import": _purpose_concepts("다른 협업 공간|채널|구성원 기록", "bring channels|member identities|another collaboration service"),
    "workspace_admin.guests": _purpose_concepts("협력업체|한 채널만|정해진 기간", "contractor|only one project discussion|expiry date"),
    "workspace_admin.external_collaboration": _purpose_concepts("다른 회사|공동 프로젝트|조직 계정", "two companies|work together|same project conversation"),
    "workspace_admin.channel_archive": _purpose_concepts("끝난 프로젝트|새 글|기록을 남", "finished project conversation|new activity|history"),
    "workspace_admin.channel_delete": _purpose_concepts("오래된 업무 대화방|되돌릴 수 없|없애", "erase|obsolete work conversation|permanently"),
    "workspace_admin.shared_drives": _purpose_concepts("부서가 소유|공동 파일 공간|만들", "file space|owned by the department|create"),
    "workspace_admin.shared_drive_members": _purpose_concepts("부서 파일 공간|사람마다|관리 범위", "assign different abilities|department-owned file space|people"),
    "workspace_admin.file_access_requests": _purpose_concepts("문서를 보겠다고 요청|대기 목록|허용", "pending requests|cannot yet read a document|decide"),
    "workspace_admin.sharing_restrictions": _purpose_concepts("조직 밖|복사|인쇄|다운로드", "outsiders|downloading|printing|copying"),
    "parcel_courier.delivery_calendar": _purpose_concepts("여러 주소|지난 도착|날짜순", "parcels|already arrived|arranged by date"),
    "parcel_courier.delivery_window": _purpose_concepts("오늘|두 시간|받을", "narrow period|today|receive the shipment"),
    "parcel_courier.proof_photo": _purpose_concepts("기사가 찍은 이미지|어디 놓", "carrier employee's image|where|left"),
    "parcel_courier.alerts": _purpose_concepts("운송 단계|바뀌|휴대전화", "phone updates|shipment changes stage|destination"),
    "parcel_courier.hold": _purpose_concepts("휴가 동안|돌아올 때까지|맡아", "carrier keep|until I return|vacation"),
    "parcel_courier.reroute": _purpose_concepts("이미 오고 있는|이웃 주소|집 대신", "in-transit shipment|neighbor's address|instead of my home"),
    "parcel_courier.reschedule": _purpose_concepts("오늘 대신|금요일|물건이 오", "move the arrival|today to Friday|home"),
    "parcel_courier.access_point": _purpose_concepts("보관함|취급점|직접", "staffed shop|secure locker|instead of home"),
    "parcel_courier.driver_instructions": _purpose_concepts("공동현관|경비실|설명", "tell the carrier employee|enter the building|where inside"),
    "parcel_courier.release": _purpose_concepts("부재중|서명 없이|책임", "unattended drop|nobody can sign|liability"),
    "parcel_courier.intercept": _purpose_concepts("이미 보낸|잘못된 곳|되돌리", "recall a shipment|destination is wrong|sent"),
    "parcel_courier.customs_fees": _purpose_concepts("해외|세관|내야 할 금액", "border charges|international shipment|preventing"),
    "parcel_courier.missing_claim": _purpose_concepts("도착 완료|물건이 없어|조사", "investigation|shipment arrived|cannot locate"),
    "parcel_courier.damage_claim": _purpose_concepts("깨져|사진과 영수증|배상", "compensation|photographs and receipts|broken"),
}

_COMPOSITIONAL_LIMIT_PER_KIND_LOCALE = 3
_EN_SEMANTIC_STOPWORDS = frozenset({
    "about", "account", "app", "application", "choose", "details", "find", "for", "from",
    "destination", "go", "help", "information", "manage", "menu", "need", "open", "option",
    "related", "screen", "service", "settings", "show", "the", "this", "use", "want", "with", "your",
})
_KO_SEMANTIC_STOPWORDS = frozenset({
    "관련", "관리", "메뉴", "목적", "보기", "서비스", "설정", "열기", "이동", "정보",
    "찾기", "화면", "확인",
})
_KO_PARTICLES = (
    "에게서", "으로부터", "한테서", "에서는", "에서도", "으로", "에서", "에게", "한테",
    "처럼", "보다", "까지", "부터", "은", "는", "이", "가", "을", "를", "에", "로", "와", "과", "도", "만",
)


def _looks_korean(value: object) -> bool:
    return any("가" <= character <= "힣" for character in str(value))


def _semantic_stem(token: str, locale: str) -> str:
    value = token.casefold()
    if locale == "ko-KR":
        for particle in _KO_PARTICLES:
            if value.endswith(particle) and len(value) > len(particle) + 1:
                value = value[: -len(particle)]
                break
        for suffix in ("하려고", "해주기", "시키기", "하기"):
            if value.endswith(suffix) and len(value) > len(suffix) + 1:
                value = value[: -len(suffix)]
                break
        if value.endswith("기") and len(value[:-1]) >= 2:
            value = value[:-1]
        return value
    if value.endswith("ies") and len(value) >= 6:
        return value[:-3] + "y"
    if value.endswith("ing") and len(value) >= 7:
        return value[:-3]
    if value.endswith("ied") and len(value) >= 6:
        return value[:-3] + "y"
    if value.endswith("ed") and len(value) >= 6:
        return value[:-2]
    if value.endswith("es") and len(value) >= 6:
        return value[:-2]
    if value.endswith("s") and len(value) >= 6:
        return value[:-1]
    return value


def _semantic_tokens(value: object, locale: str) -> list[str]:
    """Extract bounded inflection-tolerant terms from reviewed ontology text."""

    raw_tokens = re.findall(
        r"[가-힣]+" if locale == "ko-KR" else r"[a-z0-9]+",
        unicodedata.normalize("NFKC", str(value)).casefold(),
        flags=re.UNICODE,
    )
    stopwords = _KO_SEMANTIC_STOPWORDS if locale == "ko-KR" else _EN_SEMANTIC_STOPWORDS
    minimum_length = 2 if locale == "ko-KR" else 4
    return _dedupe(
        stem
        for token in raw_tokens
        if (stem := _semantic_stem(token, locale))
        and len(stem) >= minimum_length
        and stem not in stopwords
    )


def _v5_token_owners() -> dict[str, frozenset[str]]:
    owners: dict[str, set[str]] = {}
    for function in V5_FUNCTIONS:
        if not bool(function["terminal"]):
            continue
        function_id = str(function["function_id"])
        for locale in ("ko-KR", "en-US"):
            values = [function[f"name_{'ko' if locale == 'ko-KR' else 'en'}"]]
            values.extend(function["aliases"][locale])  # type: ignore[index]
            values.extend(
                value
                for value in function["positive_context"]  # type: ignore[union-attr]
                if _looks_korean(value) == (locale == "ko-KR")
            )
            for value in values:
                for token in _semantic_tokens(value, locale):
                    owners.setdefault(_goal_cue_key(token), set()).add(function_id)
            group = next(
                candidate
                for candidate in GROUPS
                if any(feature.function_id == function_id for feature in candidate.features)
            )
            domain_value = group.root_ko if locale == "ko-KR" else group.root_en
            for token in _semantic_tokens(domain_value, locale):
                owners.setdefault(_goal_cue_key(token), set()).add(function_id)
            for terms in V5_PURPOSE_CONCEPTS.get(function_id, {}).get(locale, ()):
                for term in terms:
                    for token in _semantic_tokens(term, locale):
                        owners.setdefault(_goal_cue_key(token), set()).add(function_id)
            if locale == "en-US":
                for source_id in function["source_refs"]:  # type: ignore[index]
                    source = OFFICIAL_SOURCES.get(str(source_id), {})
                    for token in _semantic_tokens(source.get("title", ""), locale):
                        owners.setdefault(_goal_cue_key(token), set()).add(function_id)
    return {key: frozenset(function_ids) for key, function_ids in owners.items()}


V5_TOKEN_OWNERS = _v5_token_owners()

# These labels are legitimate UI aliases, but outside their service domain
# they describe a common phrase or supporting datum rather than a unique
# destination.  Keep them for screen matching and domain-qualified rules;
# never promote them to an unqualified goal pattern/rule.
V5_DOMAIN_REQUIRED_ALIASES = frozenset({
    _goal_cue_key("notify me"),
    _goal_cue_key("reference range"),
})

# A mechanically shortened token such as ``auto`` does not say what is being
# automated.  In particular, it made an automatic device-backup request look
# like an automatic workspace-file deletion request.  Keep the full labels and
# domain-qualified rules, but never use these fragments in an unqualified
# cross-domain conjunction.
V5_COMPOSITIONAL_DOMAIN_REQUIRED_TOKENS = frozenset({
    _goal_cue_key("auto"),
})


def _requires_domain_qualification(value: object) -> bool:
    cue = _goal_cue_key(value)
    return (
        cue in V5_DOMAIN_REQUIRED_ALIASES
        or (cue.isascii() and cue.isalpha() and len(cue) <= 3)
    )


def _ranked_compositional_pairs(
    left_terms: Sequence[str],
    right_terms: Sequence[str],
    *,
    function_id: str,
    same_pool: bool = False,
) -> list[tuple[str, str]]:
    candidates = combinations(left_terms, 2) if same_pool else product(left_terms, right_terms)
    ranked: list[tuple[tuple[int, int, int, str, str], tuple[str, str]]] = []
    seen: set[tuple[str, str]] = set()
    for first, second in candidates:
        pair = tuple(sorted((_normalized_phrase(first), _normalized_phrase(second))))
        if (
            not all(pair)
            or pair[0] == pair[1]
            or pair in seen
            or pair[0] in pair[1]
            or pair[1] in pair[0]
            or any(
                _goal_cue_key(value) in V5_COMPOSITIONAL_DOMAIN_REQUIRED_TOKENS
                for value in pair
            )
        ):
            continue
        seen.add(pair)
        first_owners = V5_TOKEN_OWNERS.get(_goal_cue_key(pair[0]), frozenset())
        second_owners = V5_TOKEN_OWNERS.get(_goal_cue_key(pair[1]), frozenset())
        if first_owners.intersection(second_owners) != {function_id}:
            continue
        rank = (
            max(len(first_owners), len(second_owners)),
            len(first_owners) + len(second_owners),
            -(len(pair[0]) + len(pair[1])),
            pair[0],
            pair[1],
        )
        ranked.append((rank, pair))
    ranked.sort(key=lambda item: item[0])
    return [pair for _, pair in ranked]


def _append_rule(
    rules: list[dict[str, object]],
    seen: set[tuple[str, ...]],
    *,
    terms: Sequence[str],
    score: float,
    rule_kind: str,
    alias: str,
    domain: str = "",
    locale: str,
) -> None:
    normalized_terms = tuple(_dedupe(_normalized_phrase(term) for term in terms))
    if not all(normalized_terms) or normalized_terms in seen:
        return
    seen.add(normalized_terms)
    rule: dict[str, object] = {
        "all_of": list(normalized_terms),
        "score": score,
        "rule_kind": rule_kind,
        "v5_alias_key": _goal_cue_key(alias),
        "v5_locale": locale,
    }
    if domain:
        rule["v5_domain_key"] = _goal_cue_key(domain)
    rules.append(rule)


def _append_compositional_rules(
    rules: list[dict[str, object]],
    seen: set[tuple[str, ...]],
    *,
    pairs: Sequence[tuple[str, str]],
    rule_kind: str,
    source_phrase: str,
    source_aliases: Sequence[str],
    locale: str,
    domain: str = "",
    positive_context: Sequence[str] = (),
    negative_context: Sequence[str] = (),
    unqualified: bool,
    limit: int = _COMPOSITIONAL_LIMIT_PER_KIND_LOCALE,
    semantic_source: str = "reviewed_alias_and_context_ontology",
) -> None:
    added = 0
    positive_keys = {_goal_cue_key(value) for value in positive_context}
    for pair in pairs:
        if added >= limit:
            break
        before = len(rules)
        _append_rule(
            rules,
            seen,
            terms=pair,
            score=0.999 if unqualified else 0.998,
            rule_kind=rule_kind,
            alias=source_phrase,
            domain=domain,
            locale=locale,
        )
        if len(rules) == before:
            continue
        rules[-1]["v5_discriminative_keys"] = [_goal_cue_key(value) for value in pair]
        rules[-1]["v5_unqualified"] = unqualified
        rules[-1]["v5_source_token_count"] = len(
            _semantic_tokens(source_phrase, locale)
        )
        rules[-1]["v5_source_alias_keys"] = [_goal_cue_key(value) for value in source_aliases]
        # ``negative_context`` can be a set of derived tokens.  Persist it in a
        # stable order so repeated full-catalog materialization is byte-for-byte
        # deterministic across Python processes (hash randomization otherwise
        # shuffled this review metadata on every run).
        rules[-1]["v5_negative_context_keys"] = sorted(
            {_goal_cue_key(value) for value in negative_context if _goal_cue_key(value)}
        )
        rules[-1]["v5_semantic_source"] = semantic_source
        context_hits = [key for key in rules[-1]["v5_discriminative_keys"] if key in positive_keys]
        if context_hits:
            rules[-1]["v5_positive_context_keys"] = context_hits
        added += 1


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    ko_aliases = _aliases(seed, "ko-KR")
    en_aliases = _aliases(seed, "en-US")
    semantic_ko = _semantic_aliases(seed, "ko-KR")
    semantic_en = _semantic_aliases(seed, "en-US")
    distinctive_ko = [
        alias
        for alias in semantic_ko
        if len(V5_ALIAS_OWNERS.get(_goal_cue_key(alias), ())) == 1
        and not _requires_domain_qualification(alias)
    ]
    distinctive_en = [
        alias
        for alias in semantic_en
        if len(V5_ALIAS_OWNERS.get(_goal_cue_key(alias), ())) == 1
        and not _requires_domain_qualification(alias)
    ]
    ko_patterns = _dedupe([
        *distinctive_ko,
        *(f"{group.root_ko} {alias}" for alias in ko_aliases),
        f"{group.root_ko}에서 {seed.name_ko} 찾기",
        f"{group.root_ko}의 {seed.name_ko} 화면 열기",
        f"{seed.name_ko} 하려고 {group.root_ko} 메뉴로 이동",
    ])
    en_patterns = _dedupe([
        *distinctive_en,
        *(f"{group.root_en} {alias}" for alias in en_aliases),
        f"find {seed.name_en.lower()} in {group.root_en.lower()}",
        f"open the {seed.name_en.lower()} screen in {group.root_en.lower()}",
        f"go to {group.root_en.lower()} to {seed.name_en.lower()}",
    ])

    goal_rules: list[dict[str, object]] = []
    seen_rule_terms: set[tuple[str, ...]] = set()
    for locale, domain, aliases in (
        ("ko-KR", group.root_ko, semantic_ko),
        ("en-US", group.root_en, semantic_en),
    ):
        for alias in aliases:
            _append_rule(
                goal_rules,
                seen_rule_terms,
                terms=_specific_goal_terms(domain, alias),
                score=1.0,
                rule_kind="v5_domain_qualified_alias",
                alias=alias,
                domain=domain,
                locale=locale,
            )
            _append_rule(
                goal_rules,
                seen_rule_terms,
                terms=[f"{domain} {alias}"],
                score=1.0,
                rule_kind="v5_domain_phrase",
                alias=alias,
                domain=domain,
                locale=locale,
            )

            alias_key = _goal_cue_key(alias)
            if (
                len(V5_ALIAS_OWNERS.get(alias_key, ())) != 1
                or _requires_domain_qualification(alias)
            ):
                continue
            _append_rule(
                goal_rules,
                seen_rule_terms,
                terms=[alias],
                score=0.997,
                rule_kind="v5_distinctive_alias",
                alias=alias,
                locale=locale,
            )
            request_cues = ("찾", "열", "필요") if locale == "ko-KR" else (
                "find", "open", "need", "want", "show",
            )
            for request_cue in request_cues:
                _append_rule(
                    goal_rules,
                    seen_rule_terms,
                    terms=[alias, request_cue],
                    score=1.0,
                    rule_kind="v5_request_framing",
                    alias=alias,
                    locale=locale,
                )

    # Add bounded, order-independent semantic compositions.  These terms are
    # stems/tokens from reviewed aliases, positive context, and domain
    # metadata; negative-context tokens are excluded before pairing.  No rule
    # depends on a complete benchmark-like phrase.
    for locale, semantic_aliases, domain_values, negative_values, positive_values in (
        (
            "ko-KR",
            semantic_ko,
            [group.root_ko, *group.ko_context],
            [*seed.negative, *group.negative_ko],
            [*seed.positive, *group.ko_context],
        ),
        (
            "en-US",
            semantic_en,
            [group.root_en, *group.en_context],
            [*group.negative_en],
            [*group.en_context],
        ),
    ):
        negative_tokens = {
            token
            for value in negative_values
            for token in _semantic_tokens(value, locale)
        }
        alias_tokens = _dedupe(
            token
            for value in semantic_aliases
            for token in _semantic_tokens(value, locale)
            if token not in negative_tokens
        )
        positive_tokens = _dedupe(
            token
            for value in positive_values
            for token in _semantic_tokens(value, locale)
            if token not in negative_tokens
        )
        domain_tokens = _dedupe(
            token
            for value in domain_values
            for token in _semantic_tokens(value, locale)
            if token not in negative_tokens
        )

        def bounded(values: Sequence[str], limit: int) -> list[str]:
            return sorted(
                values,
                key=lambda value: (
                    len(V5_TOKEN_OWNERS.get(_goal_cue_key(value), ())),
                    -len(value),
                    value,
                ),
            )[:limit]

        alias_tokens = bounded(alias_tokens, 18)
        positive_tokens = bounded(positive_tokens, 12)
        domain_tokens = bounded(domain_tokens, 10)
        source_phrase = " | ".join(semantic_aliases)
        source_rules_start = len(goal_rules)
        _append_compositional_rules(
            goal_rules,
            seen_rule_terms,
            pairs=_ranked_compositional_pairs(
                alias_tokens,
                alias_tokens,
                function_id=seed.function_id,
                same_pool=True,
            ),
            rule_kind="v5_compositional_alias",
            source_phrase=source_phrase,
            source_aliases=semantic_aliases,
            locale=locale,
            negative_context=negative_tokens,
            unqualified=True,
        )
        _append_compositional_rules(
            goal_rules,
            seen_rule_terms,
            pairs=_ranked_compositional_pairs(
                alias_tokens,
                positive_tokens,
                function_id=seed.function_id,
            ),
            rule_kind="v5_consequence_context",
            source_phrase=source_phrase,
            source_aliases=semantic_aliases,
            locale=locale,
            positive_context=positive_tokens,
            negative_context=negative_tokens,
            unqualified=True,
        )
        _append_compositional_rules(
            goal_rules,
            seen_rule_terms,
            pairs=_ranked_compositional_pairs(
                alias_tokens,
                domain_tokens,
                function_id=seed.function_id,
            ),
            rule_kind="v5_compositional_domain",
            source_phrase=source_phrase,
            source_aliases=semantic_aliases,
            locale=locale,
            domain=group.root_ko if locale == "ko-KR" else group.root_en,
            negative_context=negative_tokens,
            unqualified=False,
        )

        # Four source-only paraphrase signatures per locale (with a validated
        # post-filter floor of two).  The
        # candidates come exclusively from first-party source titles (English)
        # and reviewed alias/context/domain metadata (both locales).  We scan
        # beyond the three primary compositions above, so these rules add new
        # lexical paths rather than duplicating an existing conjunction.
        official_title_tokens = _dedupe(
            token
            for source_id in seed.source_refs
            for token in _semantic_tokens(
                OFFICIAL_SOURCES.get(source_id, {}).get("title", ""),
                "en-US",
            )
            if locale == "en-US" and token not in negative_tokens
        )
        source_tokens = bounded(
            official_title_tokens if official_title_tokens else positive_tokens,
            18,
        )
        source_paraphrase_pairs = list(dict.fromkeys([
            *_ranked_compositional_pairs(
                source_tokens,
                positive_tokens,
                function_id=seed.function_id,
            ),
            *_ranked_compositional_pairs(
                positive_tokens,
                positive_tokens,
                function_id=seed.function_id,
                same_pool=True,
            ),
            *_ranked_compositional_pairs(
                alias_tokens,
                source_tokens,
                function_id=seed.function_id,
            ),
            *_ranked_compositional_pairs(
                positive_tokens,
                domain_tokens,
                function_id=seed.function_id,
            ),
        ]))
        _append_compositional_rules(
            goal_rules,
            seen_rule_terms,
            pairs=source_paraphrase_pairs,
            rule_kind="v5_source_paraphrase",
            source_phrase=" | ".join(
                str(OFFICIAL_SOURCES.get(source_id, {}).get("title", ""))
                for source_id in seed.source_refs
            ) or source_phrase,
            source_aliases=semantic_aliases,
            locale=locale,
            positive_context=positive_tokens,
            negative_context=negative_tokens,
            unqualified=True,
            limit=4,
            semantic_source="official_source_registry_and_reviewed_function_metadata",
        )
        source_rule_count = sum(
            rule.get("rule_kind") == "v5_source_paraphrase"
            and rule.get("v5_locale") == locale
            for rule in goal_rules
        )
        if source_rule_count < 4:
            for alias, context_token in product(
                semantic_aliases,
                [*positive_tokens, *domain_tokens, *source_tokens],
            ):
                if source_rule_count >= 4:
                    break
                before = len(goal_rules)
                _append_rule(
                    goal_rules,
                    seen_rule_terms,
                    terms=[alias, context_token],
                    score=0.998,
                    rule_kind="v5_source_paraphrase",
                    alias=alias,
                    locale=locale,
                )
                if len(goal_rules) == before:
                    continue
                discriminative_keys = _dedupe(
                    _goal_cue_key(token)
                    for value in (alias, context_token)
                    for token in _semantic_tokens(value, locale)
                    if _goal_cue_key(token)
                )
                if len(discriminative_keys) < 2:
                    goal_rules.pop()
                    continue
                goal_rules[-1]["v5_discriminative_keys"] = discriminative_keys
                goal_rules[-1]["v5_unqualified"] = True
                goal_rules[-1]["v5_source_token_count"] = len(discriminative_keys)
                goal_rules[-1]["v5_source_alias_keys"] = [_goal_cue_key(alias)]
                goal_rules[-1]["v5_negative_context_keys"] = sorted(
                    {
                        _goal_cue_key(value)
                        for value in negative_tokens
                        if _goal_cue_key(value) not in discriminative_keys
                    }
                )
                goal_rules[-1]["v5_semantic_source"] = (
                    "official_source_registry_and_reviewed_function_metadata"
                )
                source_rule_count += 1

        domain_anchor = group.root_ko if locale == "ko-KR" else group.root_en
        domain_anchor_key = _runtime_goal_key(domain_anchor)
        domain_discriminative_keys = [
            _goal_cue_key(token)
            for token in _semantic_tokens(domain_anchor, locale)
            if _goal_cue_key(token)
        ]
        for source_rule in goal_rules[source_rules_start:]:
            if source_rule.get("rule_kind") != "v5_source_paraphrase":
                continue
            if not any(
                _runtime_goal_key(value) == domain_anchor_key
                for value in source_rule["all_of"]
            ):
                source_rule["all_of"].append(domain_anchor)
            source_rule["v5_discriminative_keys"] = _dedupe([
                *source_rule["v5_discriminative_keys"],
                *domain_discriminative_keys,
            ])
            source_rule["v5_negative_context_keys"] = sorted(
                set(source_rule["v5_negative_context_keys"])
                - set(source_rule["v5_discriminative_keys"])
            )
            seen_rule_terms.add(
                tuple(_dedupe(_normalized_phrase(value) for value in source_rule["all_of"]))
            )

        # Preserve one high-specificity source anchor through cross-generation
        # and sibling shadow filtering.  It combines the reviewed terminal
        # label, a consequence/context atom, and the service domain; the full
        # label prevents a generic sibling pair from taking precedence.
        source_label = seed.name_ko if locale == "ko-KR" else seed.name_en
        source_anchor_count = 0
        for context_token in [*positive_tokens, *source_tokens, *domain_tokens]:
            if source_anchor_count >= 2:
                break
            if any(
                _runtime_goal_key(context_token) in _runtime_goal_key(value)
                for value in (source_label, domain_anchor)
            ):
                continue
            before = len(goal_rules)
            _append_rule(
                goal_rules,
                seen_rule_terms,
                terms=[source_label, context_token, domain_anchor],
                score=1.0,
                rule_kind="v5_source_paraphrase",
                alias=source_label,
                domain=domain_anchor,
                locale=locale,
            )
            if len(goal_rules) == before:
                continue
            discriminative_keys = _dedupe(
                _goal_cue_key(token)
                for value in (source_label, context_token, domain_anchor)
                for token in _semantic_tokens(value, locale)
                if _goal_cue_key(token) in V5_TOKEN_OWNERS
            )
            goal_rules[-1]["v5_discriminative_keys"] = discriminative_keys
            goal_rules[-1]["v5_unqualified"] = False
            goal_rules[-1]["v5_source_token_count"] = len(discriminative_keys)
            goal_rules[-1]["v5_source_alias_keys"] = [_goal_cue_key(source_label)]
            goal_rules[-1]["v5_negative_context_keys"] = sorted(
                set(_goal_cue_key(value) for value in negative_tokens if _goal_cue_key(value))
                - set(discriminative_keys)
            )
            goal_rules[-1]["v5_semantic_source"] = (
                "official_source_registry_and_reviewed_function_metadata"
            )
            goal_rules[-1]["v5_source_anchor"] = True
            goal_rules[-1]["v5_source_anchor_ordinal"] = source_anchor_count + 1
            source_anchor_count += 1

    # Purpose language frequently omits the destination's literal button
    # label ("a cheque photographed on both sides", "a wheelchair user and
    # companion sitting together").  Add one compact bilingual conjunction
    # from the reviewed consequence ontology.  These remain ordinary exact
    # semantic rules: no embedding, fixture lookup, or app-specific path is
    # consulted at runtime.
    for locale, concept_rules in V5_PURPOSE_CONCEPTS[seed.function_id].items():
        for terms in concept_rules:
            before = len(goal_rules)
            _append_rule(
                goal_rules,
                seen_rule_terms,
                terms=terms,
                score=1.0,
                rule_kind="v5_purpose_consequence",
                alias=seed.name_ko if locale == "ko-KR" else seed.name_en,
                locale=locale,
            )
            if len(goal_rules) == before:
                continue
            discriminative_keys = _dedupe(
                _goal_cue_key(token)
                for term in terms
                for token in _semantic_tokens(term, locale)
                if _goal_cue_key(token)
            )
            goal_rules[-1]["v5_discriminative_keys"] = discriminative_keys
            goal_rules[-1]["v5_unqualified"] = True
            goal_rules[-1]["v5_source_token_count"] = len(discriminative_keys)
            goal_rules[-1]["v5_source_alias_keys"] = []
            goal_rules[-1]["v5_negative_context_keys"] = []
            goal_rules[-1]["v5_semantic_source"] = "reviewed_purpose_consequence_ontology"

    confirmation_required = seed.mode in {"change", "submit", "sensitive"}
    return {
        "intent_id": "v5_" + seed.function_id.replace(".", "_"),
        "terminal_function": seed.function_id,
        "patterns": [*ko_patterns, *en_patterns],
        "patterns_by_locale": {"ko-KR": ko_patterns, "en-US": en_patterns},
        "goal_rules": goal_rules,
        "route": [
            {"function_id": group.root_id, "weight": 0.42},
            {"function_id": seed.function_id, "weight": 1.0},
        ],
        "avoid_functions": [group.avoid_root],
        "desired_state": "user_confirmation_required" if confirmation_required else "destination_visible",
        "terminal_condition": {
            "stop_policy": "stop_before_action" if confirmation_required else "on_destination_screen"
        },
    }


V5_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)

REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
REQUIRED_FUNCTIONS = frozenset(
    {
        "food_order.group_create", "restaurant_booking.waitlist_join", "lodging.checkin_instructions",
        "flight_search.price_track", "event_ticket.mobile_entry", "ride_hailing.pickup_preferences",
        "retail_banking.mobile_check_deposit", "retail_banking.transaction_dispute",
        "government_digital.passport_renew", "government_digital.immigration_case",
        "healthcare_provider.referral_status", "healthcare_provider.proxy_access",
        "workspace_admin.data_retention", "workspace_admin.file_access_requests",
        "parcel_courier.intercept", "parcel_courier.missing_claim",
    }
)


class V5CatalogValidationError(ValueError):
    pass


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicate: set[str] = set()
    for value in values:
        if value in seen:
            duplicate.add(value)
        seen.add(value)
    return duplicate


def _normal_pattern(value: object) -> str:
    return _runtime_goal_key(value)


def _pre_v5_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Return the catalog prefix used to derive the v5 materialization."""

    v5_function_ids = {str(item["function_id"]) for item in V5_FUNCTIONS}
    v5_intent_ids = {str(item["intent_id"]) for item in V5_INTENTS}
    prefix = copy.deepcopy(dict(payload))
    prefix["functions"] = [
        item
        for item in payload.get("functions", [])  # type: ignore[union-attr]
        if not (isinstance(item, Mapping) and str(item.get("function_id", "")) in v5_function_ids)
    ]
    prefix["intents"] = [
        item
        for item in payload.get("intents", [])  # type: ignore[union-attr]
        if not (isinstance(item, Mapping) and str(item.get("intent_id", "")) in v5_intent_ids)
    ]
    prefix.pop("official_sources_v5", None)
    return prefix


def _base_goal_inventory(payload: Mapping[str, object]) -> tuple[set[str], set[str], set[tuple[str, ...]]]:
    """Collect pre-v5 cue, pattern, and rule ownership without test data."""

    cues: set[str] = set()
    pattern_keys: set[str] = set()
    rule_signatures: set[tuple[str, ...]] = set()
    for function in payload.get("functions", []):  # type: ignore[union-attr]
        if not isinstance(function, Mapping):
            continue
        for field in ("name_ko", "name_en"):
            if key := _goal_cue_key(function.get(field, "")):
                cues.add(key)
        aliases = function.get("aliases", {})
        if isinstance(aliases, Mapping):
            for values in aliases.values():
                for value in values if isinstance(values, (list, tuple)) else (values,):
                    if key := _goal_cue_key(value):
                        cues.add(key)
    for intent in payload.get("intents", []):  # type: ignore[union-attr]
        if not isinstance(intent, Mapping):
            continue
        for pattern in intent.get("patterns", []):
            if pattern_key := _runtime_goal_key(pattern):
                pattern_keys.add(pattern_key)
            if cue_key := _goal_cue_key(pattern):
                cues.add(cue_key)
        for rule in intent.get("goal_rules", []):
            if not isinstance(rule, Mapping):
                continue
            signature = tuple(
                sorted(
                    {
                        key
                        for term in rule.get("all_of", [])
                        if (key := _goal_cue_key(term))
                    }
                )
            )
            if signature:
                rule_signatures.add(signature)
            for key in signature:
                cues.add(key)
    return cues, pattern_keys, rule_signatures


def _base_compositional_token_owners(payload: Mapping[str, object]) -> dict[str, frozenset[str]]:
    """Map semantic stems to pre-v5 owners for conjunction-level filtering."""

    owners: dict[str, set[str]] = {}

    def add(owner: str, value: object, locale: str | None = None) -> None:
        selected_locale = locale or ("ko-KR" if _looks_korean(value) else "en-US")
        for token in _semantic_tokens(value, selected_locale):
            owners.setdefault(_goal_cue_key(token), set()).add(owner)

    for function in payload.get("functions", []):  # type: ignore[union-attr]
        if not isinstance(function, Mapping):
            continue
        owner = str(function.get("function_id", ""))
        add(owner, function.get("name_ko", ""), "ko-KR")
        add(owner, function.get("name_en", ""), "en-US")
        aliases = function.get("aliases", {})
        if isinstance(aliases, Mapping):
            for locale, values in aliases.items():
                normalized_locale = "ko-KR" if str(locale).lower().startswith("ko") else "en-US"
                for value in values if isinstance(values, (list, tuple)) else (values,):
                    add(owner, value, normalized_locale)
        for value in function.get("positive_context", []):
            add(owner, value)

    for intent in payload.get("intents", []):  # type: ignore[union-attr]
        if not isinstance(intent, Mapping):
            continue
        owner = str(intent.get("terminal_function") or intent.get("intent_id", ""))
        for pattern in intent.get("patterns", []):
            add(owner, pattern)
        for rule in intent.get("goal_rules", []):
            if isinstance(rule, Mapping):
                for term in rule.get("all_of", []):
                    add(owner, term)
    return {key: frozenset(values) for key, values in owners.items()}


def _rule_signature(rule: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                key
                for term in rule.get("all_of", [])  # type: ignore[union-attr]
                if (key := _goal_cue_key(term))
            }
        )
    )


def _materialized_v5_intents(pre_v5_payload: Mapping[str, object]) -> list[dict[str, object]]:
    """Filter raw v5 generalization against every pre-v5 semantic owner.

    Only ontology vocabulary is consulted.  Unqualified and request-framed
    aliases survive when the bilingual alias has one v5 owner and no pre-v5
    owner.  Domain-qualified rules may reuse a generic alias only when their
    domain anchor is exclusive to v5.  Exact rule signatures and normalized
    patterns owned by an earlier generation are always removed.
    """

    base_cues, base_pattern_keys, base_rule_signatures = _base_goal_inventory(pre_v5_payload)
    base_token_owners = _base_compositional_token_owners(pre_v5_payload)
    raw_intents = copy.deepcopy(list(V5_INTENTS))

    pattern_owners: dict[str, set[str]] = {}
    rule_owners: dict[tuple[str, ...], set[str]] = {}
    for intent in raw_intents:
        owner = str(intent["intent_id"])
        for pattern in intent.get("patterns", []):
            if key := _runtime_goal_key(pattern):
                pattern_owners.setdefault(key, set()).add(owner)
        for rule in intent.get("goal_rules", []):
            if isinstance(rule, Mapping) and (signature := _rule_signature(rule)):
                rule_owners.setdefault(signature, set()).add(owner)

    for intent in raw_intents:
        owner = str(intent["intent_id"])
        retained_rules: list[dict[str, object]] = []
        retained_signatures: set[tuple[str, ...]] = set()
        for raw_rule in intent.get("goal_rules", []):
            if not isinstance(raw_rule, dict):
                continue
            signature = _rule_signature(raw_rule)
            if (
                not signature
                or signature in retained_signatures
                or signature in base_rule_signatures
                or rule_owners.get(signature) != {owner}
            ):
                continue
            kind = str(raw_rule.get("rule_kind", ""))
            alias_key = str(raw_rule.get("v5_alias_key", ""))
            domain_key = str(raw_rule.get("v5_domain_key", ""))
            unique_alias = (
                bool(alias_key)
                and len(V5_ALIAS_OWNERS.get(alias_key, ())) == 1
                and alias_key not in base_cues
            )
            if kind in {"v5_distinctive_alias", "v5_request_framing"} and not unique_alias:
                continue
            if kind in {"v5_domain_qualified_alias", "v5_domain_phrase"}:
                # A domain-qualified rule is allowed to reuse a generic feature
                # label only when the domain itself is not already an earlier
                # ontology cue.  If both anchors are old, v5 has no new evidence.
                if alias_key in base_cues and (not domain_key or domain_key in base_cues):
                    continue
            if (
                kind.startswith("v5_compositional_")
                or kind in {
                    "v5_consequence_context",
                    "v5_purpose_consequence",
                    "v5_source_paraphrase",
                }
            ):
                discriminative_keys = tuple(
                    dict.fromkeys(str(value) for value in raw_rule.get("v5_discriminative_keys", []))
                )
                if len(discriminative_keys) < 2:
                    continue
                prior_owners: set[str] | None = None
                for key in discriminative_keys:
                    key_owners = set(base_token_owners.get(key, ()))
                    prior_owners = key_owners if prior_owners is None else prior_owners & key_owners
                if prior_owners:
                    continue
                if kind == "v5_consequence_context" and not raw_rule.get("v5_positive_context_keys"):
                    continue
            retained_signatures.add(signature)
            retained_rules.append(raw_rule)
        intent["goal_rules"] = retained_rules

        retained_patterns = [
            pattern
            for pattern in intent.get("patterns", [])
            if (
                (key := _runtime_goal_key(pattern))
                and key not in base_pattern_keys
                and pattern_owners.get(key) == {owner}
                and not (
                    len(V5_ALIAS_OWNERS.get(_goal_cue_key(pattern), ())) == 1
                    and _goal_cue_key(pattern) in base_cues
                )
            )
        ]
        intent["patterns"] = retained_patterns
        retained_pattern_keys = {_runtime_goal_key(pattern) for pattern in retained_patterns}
        patterns_by_locale = intent.get("patterns_by_locale", {})
        if isinstance(patterns_by_locale, dict):
            for locale, patterns in patterns_by_locale.items():
                patterns_by_locale[locale] = [
                    pattern
                    for pattern in patterns
                    if _runtime_goal_key(pattern) in retained_pattern_keys
                ]

    # A shorter stem can satisfy a longer sibling term (``save`` inside
    # ``saved``).  Remove a compositional rule when another owner would match
    # the same cue bag with equal-or-stronger runtime precedence.  This pass is
    # performed after base filtering so a discarded earlier-generation rule
    # cannot suppress a useful v5 composition.
    compositional_records: dict[str, list[tuple[str, dict[str, object], tuple[str, ...]]]] = {}
    for intent in raw_intents:
        owner = str(intent["intent_id"])
        for rule in intent["goal_rules"]:
            kind = str(rule.get("rule_kind", ""))
            if not (
                kind.startswith("v5_compositional_")
                or kind in {
                    "v5_consequence_context",
                    "v5_purpose_consequence",
                    "v5_source_paraphrase",
                }
            ):
                continue
            locale = str(rule.get("v5_locale", ""))
            terms = tuple(_runtime_goal_key(value) for value in rule["all_of"])
            compositional_records.setdefault(locale, []).append((owner, rule, terms))

    shadowed: set[tuple[str, tuple[str, ...]]] = set()
    for records in compositional_records.values():
        for owner, rule, terms in records:
            rule_key = (
                float(rule["score"]),
                max(len(term) for term in terms),
                len(terms),
                sum(len(term) for term in terms),
            )
            for other_owner, other_rule, other_terms in records:
                if other_owner == owner:
                    continue
                if not all(any(other in term for term in terms) for other in other_terms):
                    continue
                other_key = (
                    float(other_rule["score"]),
                    max(len(term) for term in other_terms),
                    len(other_terms),
                    sum(len(term) for term in other_terms),
                )
                if other_key >= rule_key:
                    shadowed.add((owner, _rule_signature(rule)))
                    break
    if shadowed:
        for intent in raw_intents:
            owner = str(intent["intent_id"])
            intent["goal_rules"] = [
                rule
                for rule in intent["goal_rules"]
                if (owner, _rule_signature(rule)) not in shadowed
            ]
    return raw_intents


def build_v5_compositional_probes(pre_v5_payload: Mapping[str, object]) -> list[dict[str, object]]:
    """Create bounded ontology-only drop/reorder/context perturbation probes."""

    probes: list[dict[str, object]] = []
    for intent in _materialized_v5_intents(pre_v5_payload):
        for locale in ("ko-KR", "en-US"):
            for kind in (
                "v5_compositional_alias",
                "v5_consequence_context",
                "v5_compositional_domain",
            ):
                rule = next(
                    (
                        candidate
                        for candidate in intent["goal_rules"]
                        if candidate.get("rule_kind") == kind
                        and candidate.get("v5_locale") == locale
                    ),
                    None,
                )
                if rule is None:
                    continue
                terms = [str(value) for value in rule["all_of"]]
                reordered = list(reversed(terms))
                if locale == "ko-KR":
                    goal = " 관련 ".join(f"{term}도" for term in reordered) + " 쪽으로"
                else:
                    goal = " related ".join(reordered) + " destination"
                normalized_goal = _runtime_goal_key(goal)
                if not all(_runtime_goal_key(term) in normalized_goal for term in terms):
                    raise V5CatalogValidationError(
                        f"generated probe lost a semantic cue for {intent['intent_id']}"
                    )
                source_token_count = int(rule.get("v5_source_token_count", len(terms)))
                probes.append(
                    {
                        "probe_id": (
                            f"{intent['intent_id']}::{locale}::{kind}"
                        ),
                        "intent_id": intent["intent_id"],
                        "terminal_function": intent["terminal_function"],
                        "locale": locale,
                        "rule_kind": kind,
                        "goal": goal,
                        "discriminative_cues": list(rule["v5_discriminative_keys"]),
                        "dropped_source_terms": max(0, source_token_count - len(terms)),
                        "reordered": reordered != terms,
                        "uses_positive_context": bool(rule.get("v5_positive_context_keys")),
                    }
                )
    return probes


def build_v5_purpose_probes(pre_v5_payload: Mapping[str, object]) -> list[dict[str, object]]:
    """Generate ontology-only word-order/framing probes for purpose rules.

    The source is the reviewed concept table above, not any authored fixture.
    Reversing the atoms and inserting neutral connective text verifies that a
    conjunction represents semantics rather than one memorised sentence.
    """

    probes: list[dict[str, object]] = []
    for intent in _materialized_v5_intents(pre_v5_payload):
        for rule in intent["goal_rules"]:
            if rule.get("rule_kind") != "v5_purpose_consequence":
                continue
            locale = str(rule["v5_locale"])
            terms = [str(value) for value in rule["all_of"]]
            reordered = list(reversed(terms))
            if locale == "ko-KR":
                goal = " 그리고 ".join(f"{term} 관련" for term in reordered) + " 결과를 찾고 싶어"
            else:
                goal = "I need an outcome involving " + ", then ".join(reordered)
            normalized_goal = _runtime_goal_key(goal)
            if not all(_runtime_goal_key(term) in normalized_goal for term in terms):
                raise V5CatalogValidationError(
                    f"generated purpose probe lost a semantic cue for {intent['intent_id']}"
                )
            probes.append(
                {
                    "probe_id": f"{intent['intent_id']}::{locale}::v5_purpose_consequence",
                    "intent_id": intent["intent_id"],
                    "terminal_function": intent["terminal_function"],
                    "locale": locale,
                    "rule_kind": "v5_purpose_consequence",
                    "goal": goal,
                    "discriminative_cues": list(rule["v5_discriminative_keys"]),
                    "reordered": reordered != terms,
                    "semantic_source": rule["v5_semantic_source"],
                }
            )
    return probes


def build_v5_source_paraphrase_probes(
    pre_v5_payload: Mapping[str, object],
) -> list[dict[str, object]]:
    """Build source-only bilingual probes with shared role/consequence frames."""

    frames = {
        "ko-KR": (
            "사용자가 결과를 검토한 뒤 직접 결정할 위치에서",
            "변경 전 영향을 확인하고 최종 선택은 남겨 둔 채",
        ),
        "en-US": (
            "with the outcome reviewed before the user decides",
            "while leaving final approval to the user before any change",
        ),
    }
    probes: list[dict[str, object]] = []
    per_terminal_locale: Counter[tuple[str, str]] = Counter()
    for intent in _materialized_v5_intents(pre_v5_payload):
        terminal = str(intent["terminal_function"])
        for rule in intent["goal_rules"]:
            if (
                rule.get("rule_kind") != "v5_source_paraphrase"
                or rule.get("v5_source_anchor") is not True
            ):
                continue
            locale = str(rule["v5_locale"])
            ordinal = per_terminal_locale[(terminal, locale)]
            per_terminal_locale[(terminal, locale)] += 1
            terms = [str(value) for value in rule["all_of"]]
            reordered = list(reversed(terms))
            frame = frames[locale][ordinal % len(frames[locale])]
            if locale == "ko-KR":
                goal = f"{frame} " + " 및 ".join(reordered) + " 목적지를 안내해 줘"
            else:
                goal = f"{frame}, guide me using " + " together with ".join(reordered)
            normalized_goal = _runtime_goal_key(goal)
            if not all(_runtime_goal_key(term) in normalized_goal for term in terms):
                raise V5CatalogValidationError(
                    f"generated source paraphrase probe lost a cue for {intent['intent_id']}"
                )
            probes.append(
                {
                    "probe_id": (
                        f"{intent['intent_id']}::{locale}::v5_source_paraphrase::{ordinal + 1}"
                    ),
                    "intent_id": intent["intent_id"],
                    "terminal_function": terminal,
                    "locale": locale,
                    "rule_kind": "v5_source_paraphrase",
                    "goal": goal,
                    "discriminative_cues": list(rule["v5_discriminative_keys"]),
                    "reordered": reordered != terms,
                    "semantic_source": rule["v5_semantic_source"],
                    "shared_frame": frame,
                }
            )
    return probes


def _materialization_state(base_payload: Mapping[str, object]) -> tuple[bool, list[str]]:
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
    expected_functions = {str(item["function_id"]): item for item in V5_FUNCTIONS}
    raw_intent_ids = {str(item["intent_id"]) for item in V5_INTENTS}
    function_collisions = set(expected_functions).intersection(base_functions)
    intent_collisions = raw_intent_ids.intersection(base_intents)
    present = [
        *(f"function:{value}" for value in sorted(function_collisions)),
        *(f"intent:{value}" for value in sorted(intent_collisions)),
    ]
    if not function_collisions and not intent_collisions:
        return False, []
    complete = (
        function_collisions == set(expected_functions)
        and intent_collisions == raw_intent_ids
    )
    if not complete:
        raise V5CatalogValidationError(f"partial v5 ID collision: {present[:12]}")

    pre_v5 = _pre_v5_payload(base_payload)
    expected_intents = {
        str(item["intent_id"]): item for item in _materialized_v5_intents(pre_v5)
    }
    differences = [
        *(function_id for function_id, expected in expected_functions.items() if base_functions[function_id] != expected),
        *(intent_id for intent_id, expected in expected_intents.items() if base_intents[intent_id] != expected),
    ]
    if base_payload.get("official_sources_v5") != OFFICIAL_SOURCES:
        differences.append("official_sources_v5")
    if base_payload.get("catalog_version") != CATALOG_V5_VERSION:
        differences.append("catalog_version")
    if base_payload.get("description") != CATALOG_V5_DESCRIPTION:
        differences.append("description")
    if differences:
        raise V5CatalogValidationError(
            f"v5 collides with a different v5 definition: {differences[:12]}"
        )
    return True, present


def validate_v5_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    function_ids = [str(item["function_id"]) for item in V5_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V5_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V5_FUNCTIONS if item["terminal"]}
    errors: list[str] = []

    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v5 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v5 intent IDs: {sorted(duplicates)}")
    if len(REQUIRED_DOMAINS) < 8:
        errors.append("v5 requires at least eight service domains")
    if len(terminal_ids) < 100:
        errors.append("v5 requires at least 100 terminal functions")
    if REQUIRED_FUNCTIONS - set(function_ids):
        errors.append(f"missing required v5 functions: {sorted(REQUIRED_FUNCTIONS - set(function_ids))}")

    for source_id, source in OFFICIAL_SOURCES.items():
        parsed = urlparse(str(source.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"source {source_id} is not HTTPS")
        if source.get("evidence_level") != "official_primary":
            errors.append(f"source {source_id} is not official_primary")
        if source.get("collected_on") != COLLECTED_ON:
            errors.append(f"source {source_id} missing collection date")
        if source.get("verified_status") != 200:
            errors.append(f"source {source_id} missing successful verification status")
        if not str(source.get("verification_method", "")).strip():
            errors.append(f"source {source_id} missing verification method")

    known_sources = set(OFFICIAL_SOURCES)
    safe_stops = {"before_action", "before_activation", "user_confirmation", "user_only", "stop_before_action"}
    for item in V5_FUNCTIONS:
        function_id = str(item["function_id"])
        aliases = item["aliases"]
        if len(aliases["ko-KR"]) < 6 or len(aliases["en-US"]) < 6:  # type: ignore[index]
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if not item["positive_context"] or not item["negative_context"]:
            errors.append(f"{function_id}: missing positive/negative context")
        if not item["role_hints"] or not item["state_cues"] or not item["risk_cues"]:
            errors.append(f"{function_id}: missing role/state/risk cues")
        refs = set(item["source_refs"])
        if not refs or not refs <= known_sources:
            errors.append(f"{function_id}: invalid or empty official source refs")
        if item["evidence_level"] != "official":
            errors.append(f"{function_id}: unexpected evidence level")
        if item["state_changing"] or item["risk_level"] == "high":
            if item["automation_policy"] != "never_auto" or item["stop_policy"] not in safe_stops:
                errors.append(f"{function_id}: unsafe action boundary")
        if {"x", "y", "bounds", "coordinates"} & set(item):
            errors.append(f"{function_id}: contains app coordinates")

    intent_terminals = {str(item["terminal_function"]) for item in V5_INTENTS}
    if intent_terminals != terminal_ids:
        errors.append("v5 intents must cover every terminal function exactly")
    for intent in V5_INTENTS:
        intent_id = str(intent["intent_id"])
        locale_patterns = intent["patterns_by_locale"]
        if len(locale_patterns["ko-KR"]) < 8 or len(locale_patterns["en-US"]) < 8:  # type: ignore[index]
            errors.append(f"{intent_id}: insufficient bilingual goal patterns")
        if len(intent["goal_rules"]) < 12:
            errors.append(f"{intent_id}: insufficient semantic goal rules")
        if intent["route"][-1]["function_id"] != intent["terminal_function"]:  # type: ignore[index]
            errors.append(f"{intent_id}: route does not end at terminal")
        if not intent["avoid_functions"]:
            errors.append(f"{intent_id}: missing negative route concept")
        for rule in intent["goal_rules"]:
            if not rule.get("all_of") or not str(rule.get("rule_kind", "")).startswith("v5_"):
                errors.append(f"{intent_id}: malformed ontology-derived goal rule")
            if not rule.get("v5_alias_key") or rule.get("v5_locale") not in {"ko-KR", "en-US"}:
                errors.append(f"{intent_id}: goal rule missing bilingual ownership metadata")
            kind = str(rule.get("rule_kind", ""))
            if (
                kind.startswith("v5_compositional_")
                or kind in {
                    "v5_consequence_context",
                    "v5_purpose_consequence",
                    "v5_source_paraphrase",
                }
            ):
                discriminative = list(dict.fromkeys(rule.get("v5_discriminative_keys", [])))
                if len(rule["all_of"]) < 2 or len(discriminative) < 2:
                    errors.append(f"{intent_id}: semantic conjunction needs two discriminative cues")
                if set(discriminative).intersection(rule.get("v5_negative_context_keys", [])):
                    errors.append(f"{intent_id}: semantic conjunction reused negative-context cue")
                if kind in {
                    "v5_compositional_alias",
                    "v5_consequence_context",
                    "v5_purpose_consequence",
                } and not rule.get("v5_unqualified"):
                    errors.append(f"{intent_id}: unqualified semantic rule missing safety marker")
                if kind == "v5_consequence_context" and not rule.get("v5_positive_context_keys"):
                    errors.append(f"{intent_id}: consequence rule lacks positive-context evidence")
                if kind == "v5_purpose_consequence":
                    if rule.get("v5_semantic_source") != "reviewed_purpose_consequence_ontology":
                        errors.append(f"{intent_id}: purpose rule lacks reviewed provenance")
                    if not (2 <= len(rule["all_of"]) <= 4):
                        errors.append(f"{intent_id}: purpose rule must use two to four atoms")
                if kind == "v5_source_paraphrase" and rule.get("v5_semantic_source") != (
                    "official_source_registry_and_reviewed_function_metadata"
                ):
                    errors.append(f"{intent_id}: source paraphrase lacks reviewed provenance")
        source_counts = Counter(
            str(rule.get("v5_locale", ""))
            for rule in intent["goal_rules"]
            if rule.get("rule_kind") == "v5_source_paraphrase"
        )
        if any(source_counts[locale] < 4 for locale in ("ko-KR", "en-US")):
            errors.append(f"{intent_id}: source paraphrase coverage must be at least four per locale")

    materialized = False
    effective_intents = list(V5_INTENTS)
    compositional_probes: list[dict[str, object]] = []
    purpose_probes: list[dict[str, object]] = []
    source_paraphrase_probes: list[dict[str, object]] = []
    if base_payload is not None:
        materialized, _ = _materialization_state(base_payload)
        pre_v5 = _pre_v5_payload(base_payload) if materialized else copy.deepcopy(dict(base_payload))
        effective_intents = _materialized_v5_intents(pre_v5)
        base_function_ids = {str(item["function_id"]) for item in pre_v5.get("functions", [])}  # type: ignore[index]
        base_intent_ids = {str(item["intent_id"]) for item in pre_v5.get("intents", [])}  # type: ignore[index]
        if not materialized:
            collisions = sorted(set(function_ids) & base_function_ids)
            collisions += sorted(set(intent_ids) & base_intent_ids)
            if collisions:
                errors.append(f"v5 IDs collide with current catalog: {collisions[:12]}")

        pattern_owners: dict[str, set[str]] = {}
        intents_to_check = list(pre_v5.get("intents", []))  # type: ignore[arg-type]
        intents_to_check.extend(effective_intents)
        for intent in intents_to_check:
            owner = str(intent["intent_id"])
            for pattern in intent.get("patterns", []):
                key = _normal_pattern(pattern)
                if key:
                    pattern_owners.setdefault(key, set()).add(owner)
        collisions = {key: owners for key, owners in pattern_owners.items() if len(owners) > 1}
        if collisions:
            sample = [(key, sorted(owners)) for key, owners in list(collisions.items())[:8]]
            errors.append(f"normalized goal-pattern collisions: {sample}")

        base_cues, _, base_rule_signatures = _base_goal_inventory(pre_v5)
        base_token_owners = _base_compositional_token_owners(pre_v5)
        effective_rule_owners: dict[tuple[str, ...], set[str]] = {}
        locale_rule_kinds: dict[str, set[tuple[str, str]]] = {}
        for intent in effective_intents:
            owner = str(intent["intent_id"])
            terminal = str(intent["terminal_function"])
            if any(len(intent["patterns_by_locale"][locale]) < 8 for locale in ("ko-KR", "en-US")):  # type: ignore[index]
                errors.append(f"{owner}: cross-generation filtering removed too many patterns")
            for pattern in intent["patterns"]:
                pattern_cue = _goal_cue_key(pattern)
                if len(V5_ALIAS_OWNERS.get(pattern_cue, ())) == 1 and pattern_cue in base_cues:
                    errors.append(f"{owner}: unsafe unqualified cross-generation pattern {pattern!r}")
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if not signature:
                    errors.append(f"{owner}: empty materialized goal rule")
                    continue
                effective_rule_owners.setdefault(signature, set()).add(owner)
                kind = str(rule.get("rule_kind", ""))
                locale = str(rule.get("v5_locale", ""))
                alias_key = str(rule.get("v5_alias_key", ""))
                locale_rule_kinds.setdefault(terminal, set()).add((locale, kind))
                if signature in base_rule_signatures:
                    errors.append(f"{owner}: reuses a pre-v5 goal-rule signature")
                if kind in {"v5_distinctive_alias", "v5_request_framing"}:
                    if len(V5_ALIAS_OWNERS.get(alias_key, ())) != 1 or alias_key in base_cues:
                        errors.append(f"{owner}: unsafe cross-generation alias rule {alias_key!r}")
                if (
                    kind.startswith("v5_compositional_")
                    or kind in {
                        "v5_consequence_context",
                        "v5_purpose_consequence",
                        "v5_source_paraphrase",
                    }
                ):
                    discriminative = tuple(
                        dict.fromkeys(str(value) for value in rule.get("v5_discriminative_keys", []))
                    )
                    if len(discriminative) < 2:
                        errors.append(f"{owner}: under-specified materialized semantic rule")
                    if set(discriminative).intersection(rule.get("v5_negative_context_keys", [])):
                        errors.append(f"{owner}: materialized rule contains negative-context cue")
                    prior_owners: set[str] | None = None
                    for key in discriminative:
                        owners = set(base_token_owners.get(key, ()))
                        prior_owners = owners if prior_owners is None else prior_owners & owners
                    if prior_owners:
                        errors.append(f"{owner}: semantic cues reuse pre-v5 owner {sorted(prior_owners)[:3]}")
        for intent in effective_intents:
            counts = Counter(
                (str(rule.get("v5_locale", "")), str(rule.get("rule_kind", "")))
                for rule in intent["goal_rules"]
                if str(rule.get("rule_kind", "")).startswith("v5_compositional_")
                or rule.get("rule_kind") == "v5_consequence_context"
            )
            if any(count > _COMPOSITIONAL_LIMIT_PER_KIND_LOCALE for count in counts.values()):
                errors.append(f"{intent['intent_id']}: compositional rule bound exceeded")
        shared_rules = {
            signature: owners
            for signature, owners in effective_rule_owners.items()
            if len(owners) > 1
        }
        if shared_rules:
            sample = [(signature, sorted(owners)) for signature, owners in list(shared_rules.items())[:8]]
            errors.append(f"materialized v5 goal-rule collisions: {sample}")
        for terminal in sorted(terminal_ids):
            owned = locale_rule_kinds.get(terminal, set())
            for locale in ("ko-KR", "en-US"):
                if (locale, "v5_distinctive_alias") not in owned:
                    errors.append(f"{terminal}: no globally unique {locale} alias rule remains")
                if (locale, "v5_request_framing") not in owned:
                    errors.append(f"{terminal}: no globally unique {locale} request-framing rule remains")
        compositional_probes = build_v5_compositional_probes(pre_v5)
        purpose_probes = build_v5_purpose_probes(pre_v5)
        source_paraphrase_probes = build_v5_source_paraphrase_probes(pre_v5)
        for locale in ("ko-KR", "en-US"):
            covered = {
                str(probe["terminal_function"])
                for probe in compositional_probes
                if probe["locale"] == locale
            }
            if covered != terminal_ids:
                errors.append(f"compositional probes do not cover every terminal in {locale}")
        if any(not probe["reordered"] or int(probe["dropped_source_terms"]) <= 0 for probe in compositional_probes):
            errors.append("compositional probes must drop and reorder ontology terms")
        if not any(probe["uses_positive_context"] for probe in compositional_probes):
            errors.append("compositional probes must exercise positive-context clues")
        if len(purpose_probes) < len(terminal_ids) * 2 - 1:
            errors.append("cross-generation filtering removed too many purpose rules")
        if any(not probe["reordered"] for probe in purpose_probes):
            errors.append("purpose probes must reorder reviewed semantic atoms")
        source_probe_counts = Counter(
            (str(probe["terminal_function"]), str(probe["locale"]))
            for probe in source_paraphrase_probes
        )
        for terminal in terminal_ids:
            for locale in ("ko-KR", "en-US"):
                if source_probe_counts[(terminal, locale)] < 2:
                    errors.append(
                        f"{terminal}: fewer than two source paraphrase probes in {locale}"
                    )
        if any(not probe["reordered"] for probe in source_paraphrase_probes):
            errors.append("source paraphrase probes must reorder reviewed atoms")

    if errors:
        raise V5CatalogValidationError("; ".join(errors))

    raw_compositional_rules = sum(
        1
        for intent in V5_INTENTS
        for rule in intent["goal_rules"]
        if str(rule.get("rule_kind", "")).startswith("v5_compositional_")
        or rule.get("rule_kind") == "v5_consequence_context"
    )
    materialized_compositional_rules = sum(
        1
        for intent in effective_intents
        for rule in intent["goal_rules"]
        if str(rule.get("rule_kind", "")).startswith("v5_compositional_")
        or rule.get("rule_kind") == "v5_consequence_context"
    )
    raw_purpose_rules = sum(
        1
        for intent in V5_INTENTS
        for rule in intent["goal_rules"]
        if rule.get("rule_kind") == "v5_purpose_consequence"
    )
    materialized_purpose_rules = sum(
        1
        for intent in effective_intents
        for rule in intent["goal_rules"]
        if rule.get("rule_kind") == "v5_purpose_consequence"
    )
    raw_source_paraphrase_rules = sum(
        1
        for intent in V5_INTENTS
        for rule in intent["goal_rules"]
        if rule.get("rule_kind") == "v5_source_paraphrase"
    )
    materialized_source_paraphrase_rules = sum(
        1
        for intent in effective_intents
        for rule in intent["goal_rules"]
        if rule.get("rule_kind") == "v5_source_paraphrase"
    )
    compositional_probe_count = len(compositional_probes)
    return {
        "functions": len(V5_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V5_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "official_sources": len(OFFICIAL_SOURCES),
        "aliases": sum(len(values) for item in V5_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in effective_intents),
        "raw_goal_patterns": sum(len(item["patterns"]) for item in V5_INTENTS),
        "materialized_goal_patterns": sum(len(item["patterns"]) for item in effective_intents),
        "goal_rules": sum(len(item["goal_rules"]) for item in effective_intents),
        "raw_goal_rules": sum(len(item["goal_rules"]) for item in V5_INTENTS),
        "materialized_goal_rules": sum(len(item["goal_rules"]) for item in effective_intents),
        "raw_compositional_rules": raw_compositional_rules,
        "materialized_compositional_rules": materialized_compositional_rules,
        "compositional_probes": compositional_probe_count,
        "raw_purpose_rules": raw_purpose_rules,
        "materialized_purpose_rules": materialized_purpose_rules,
        "purpose_probes": len(purpose_probes),
        "raw_source_paraphrase_rules": raw_source_paraphrase_rules,
        "materialized_source_paraphrase_rules": materialized_source_paraphrase_rules,
        "source_paraphrase_probes": len(source_paraphrase_probes),
        "state_changing": sum(bool(item["state_changing"]) for item in V5_FUNCTIONS),
        "high_risk": sum(item["risk_level"] == "high" for item in V5_FUNCTIONS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a validated copy; never mutate the caller's catalog."""

    validate_v5_data(base_payload)
    materialized, _ = _materialization_state(base_payload)
    merged = copy.deepcopy(dict(base_payload))
    if materialized:
        return merged

    merged["catalog_version"] = CATALOG_V5_VERSION
    merged["description"] = CATALOG_V5_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V5_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *_materialized_v5_intents(base_payload)]
    merged["official_sources_v5"] = copy.deepcopy(OFFICIAL_SOURCES)
    return merged


def main() -> int:
    base = load_base_catalog()
    stats = validate_v5_data(base)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
