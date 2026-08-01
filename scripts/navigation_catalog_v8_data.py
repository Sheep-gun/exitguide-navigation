from __future__ import annotations

"""Reviewed v8 operational-workflow ontology for universal navigation.

This layer models semantic destinations for eight high-value professional
domains.  It intentionally contains no application identity, Android package,
resource ID, coordinate, screenshot, or recorded path.  Consequential actions
always stop before the final control and remain owned by the user.
"""

import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse

from navigation_catalog_v7_data import (
    CATALOG_V7_DESCRIPTION,
    CATALOG_V7_VERSION,
    F,
    G,
    FeatureSeed,
    GroupSeed,
    _build_feature as _v7_build_feature,
    _build_intent as _v7_build_intent,
    _build_root as _v7_build_root,
    _cue_key,
    _runtime_pattern_key,
    _rule_signature,
    _pre_v7_payload,
    merge_with_base as merge_v7_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
CATALOG_V8_VERSION = "8.0.0"
COLLECTED_ON = "2026-07-30"
CATALOG_V8_DESCRIPTION = (
    "ExitGuide cross-app function ontology v8: app-agnostic destinations for "
    "credential vaults, business accounting, CRM sales, support-agent workspaces, "
    "merchant POS and inventory, field operations, gig-worker dispatch, and "
    "incident on-call response; every consequential final click remains user-owned."
)


def _source(publisher: str, title: str, url: str) -> dict[str, object]:
    return {
        "publisher": publisher,
        "title": title,
        "url": url,
        "collected_on": COLLECTED_ON,
        "evidence_level": "official_primary",
        "verified_status": 200,
        "verification_method": "official first-party page reviewed in the v8 coverage audit",
    }


OFFICIAL_SOURCES: dict[str, dict[str, object]] = {
    "bitwarden_app_settings": _source(
        "Bitwarden", "App settings", "https://bitwarden.com/help/app-settings/"
    ),
    "google_authenticator_android": _source(
        "Google Account Help", "Get verification codes with Google Authenticator",
        "https://support.google.com/accounts/answer/1066447?co=GENIE.Platform%3DAndroid",
    ),
    "quickbooks_mobile": _source(
        "Intuit QuickBooks", "Get work done in the QuickBooks mobile app and web",
        "https://quickbooks.intuit.com/learn-support/en-us/help-article/compare-products/get-done-quickbooks-mobile-app-web/L9YN5gwQw_US_en_US",
    ),
    "xero_mobile": _source(
        "Xero Central", "Xero for mobile",
        "https://central.xero.com/s/article/Xero-for-mobile-US",
    ),
    "salesforce_mobile_records": _source(
        "Salesforce Help", "View records in the Salesforce mobile app",
        "https://help.salesforce.com/s/articleView?id=sales.sales_mobile_app_view_records.htm&language=en_US&type=5",
    ),
    "salesforce_lead_conversion": _source(
        "Salesforce Help", "Convert leads in Salesforce Mobile",
        "https://help.salesforce.com/s/articleView?id=000387247&language=en_US&type=1",
    ),
    "zendesk_mobile_overview": _source(
        "Zendesk Support", "About the Zendesk Support mobile app",
        "https://support.zendesk.com/hc/en-us/articles/4408846407066-About-the-Zendesk-Support-mobile-app",
    ),
    "zendesk_mobile_tickets": _source(
        "Zendesk Support", "Working with tickets in the Support mobile app",
        "https://support.zendesk.com/hc/en-us/articles/4408825697434-Working-with-tickets-in-the-Support-mobile-app",
    ),
    "square_inventory": _source(
        "Square Support", "View, receive, and adjust inventory",
        "https://squareup.com/help/us/en/article/6110-manage-inventory-with-the-retail-pos-app",
    ),
    "square_inventory_counts": _source(
        "Square Support", "Conduct full inventory counts",
        "https://squareup.com/help/us/en/article/8249-conduct-full-inventory-counts-with-square-for-retail",
    ),
    "procore_android_guide": _source(
        "Procore Support", "Android app user guide",
        "https://support.procore.com/procore-mobile-android/user-guide",
    ),
    "procore_android_punch": _source(
        "Procore Support", "Punch List for Android",
        "https://support.procore.com/procore-mobile-android/user-guide/punch-list-android",
    ),
    "uber_driver_earnings": _source(
        "Uber Help", "Where can I see my trip earnings?",
        "https://help.uber.com/driving-and-delivering/article/where-can-i-see-my-trip-earnings?nodeId=9fbc207b-2837-4428-8133-2d2df7b3b17d",
    ),
    "uber_driver_upfront": _source(
        "Uber Help", "Understand the calculation of prices",
        "https://help.uber.com/en/driving-and-delivering/article/understand-the-calculation-of-prices?nodeId=470cd474-831c-4e01-8e5a-3032ca39bab1",
    ),
    "pagerduty_mobile": _source(
        "PagerDuty Support", "Mobile App",
        "https://support.pagerduty.com/main/docs/mobile-app",
    ),
    "pagerduty_mobile_settings": _source(
        "PagerDuty Support", "Mobile App Settings",
        "https://support.pagerduty.com/main/docs/mobile-app-settings",
    ),
}


FeatureRow = tuple[str, str, str, str, str, str]


def _feature_rows(
    rows: Sequence[FeatureRow], *, sources: str, negative: str,
) -> tuple[FeatureSeed, ...]:
    """Expand compact reviewed rows into rich bilingual semantic seeds."""

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
        result.append(
            F(
                key,
                name_ko,
                name_en,
                ko_aliases,
                en_aliases,
                positive,
                negative,
                mode,
                sources=sources,
            )
        )
    return tuple(result)


CREDENTIAL_ROWS: tuple[FeatureRow, ...] = (
    ("stored_logins", "저장된 로그인", "Stored logins", "보관된 자격 증명", "saved credentials", "sensitive"),
    ("vault_search", "보관함 검색", "Vault search", "로그인 항목 찾기", "find a login item", "sensitive"),
    ("add_credential", "로그인 항목 추가", "Add login item", "새 자격 증명 저장", "save a new credential", "submit"),
    ("edit_credential", "로그인 항목 편집", "Edit login item", "저장 정보 수정", "update saved credential", "submit"),
    ("password_generator", "비밀번호 생성기", "Password generator", "강한 암호 만들기", "create strong password", "sensitive"),
    ("autofill_settings", "자동완성 설정", "Autofill settings", "로그인 자동 입력", "login autofill", "change"),
    ("authenticator_codes", "인증 코드", "Authenticator codes", "일회용 코드 보기", "view one-time codes", "sensitive"),
    ("import_codes", "인증 코드 가져오기", "Import authenticator codes", "인증기 데이터 가져오기", "import verification codes", "submit"),
    ("export_codes", "인증 코드 내보내기", "Export authenticator codes", "인증기 데이터 이전", "transfer verification codes", "submit"),
    ("secure_notes", "보안 메모", "Secure notes", "암호화 메모 보기", "view encrypted notes", "sensitive"),
    ("payment_cards", "보관된 결제 카드", "Stored payment cards", "카드 보관함", "payment card vault", "sensitive"),
    ("identities", "보관된 신원 정보", "Stored identities", "주소와 신원 항목", "identity and address items", "sensitive"),
    ("organize_items", "보관함 항목 정리", "Organize vault items", "폴더와 컬렉션 정리", "organize folders and collections", "change"),
    ("lock_vault", "보관함 잠금", "Lock vault", "비밀 보관함 닫기", "secure the credential vault", "submit"),
    ("emergency_access", "긴급 접근", "Emergency access", "신뢰 연락처 접근", "trusted contact access", "submit"),
    ("security_report", "보안 보고서", "Vault security report", "노출 암호 점검", "credential exposure report", "sensitive"),
    ("password_health", "비밀번호 상태 점검", "Password health", "재사용 암호 확인", "reused password review", "sensitive"),
)

ACCOUNTING_ROWS: tuple[FeatureRow, ...] = (
    ("company_switch", "사업체 전환", "Switch business", "회사 장부 바꾸기", "change company books", "sensitive"),
    ("dashboard", "사업 재무 대시보드", "Business finance dashboard", "회사 재무 요약", "company finance overview", "sensitive"),
    ("customers", "회계 고객 목록", "Accounting customers", "거래처 고객 관리", "manage billing customers", "sensitive"),
    ("vendors", "공급업체 목록", "Vendors", "매입 거래처 관리", "manage suppliers", "sensitive"),
    ("estimate_create", "견적 작성", "Create estimate", "고객 견적서 만들기", "prepare customer estimate", "change"),
    ("invoice_create", "송장 작성", "Create invoice", "매출 청구서 만들기", "prepare sales invoice", "change"),
    ("invoice_send", "송장 발송", "Send invoice", "고객에게 청구 전송", "deliver invoice to customer", "submit"),
    ("record_payment", "결제 기록", "Record payment", "수금 내역 반영", "post customer payment", "submit"),
    ("expenses", "사업 비용", "Business expenses", "회사 지출 내역", "company expense records", "sensitive"),
    ("receipt_capture", "영수증 촬영", "Receipt capture", "비용 증빙 스캔", "scan expense receipt", "submit"),
    ("bills", "매입 청구서", "Vendor bills", "지급 예정 비용", "bills to pay", "sensitive"),
    ("bank_transactions", "사업 계좌 거래", "Business bank transactions", "연결 계좌 내역", "connected bank activity", "sensitive"),
    ("reconcile", "은행 조정", "Bank reconciliation", "장부와 거래 맞추기", "match books to bank", "submit"),
    ("accounts_receivable", "미수금", "Accounts receivable", "미납 송장 확인", "outstanding invoices", "sensitive"),
    ("profit_loss", "손익 보고서", "Profit and loss report", "사업 손익 보기", "business income statement", "sensitive"),
    ("cash_flow", "현금 흐름", "Cash flow report", "사업 자금 흐름", "business cash movement", "sensitive"),
    ("tax_summary", "세금 요약", "Business tax summary", "판매세와 부가세 요약", "sales tax summary", "sensitive"),
    ("accountant_access", "회계 담당자 접근", "Accountant access", "장부 사용자 권한", "bookkeeping user access", "submit"),
    ("payment_links", "결제 링크", "Payment links", "고객 수금 링크", "customer payment link", "submit"),
)

CRM_ROWS: tuple[FeatureRow, ...] = (
    ("leads", "영업 리드 목록", "Sales leads", "잠재 고객 찾기", "find prospective customers", "sensitive"),
    ("lead_create", "리드 생성", "Create lead", "새 잠재 고객 입력", "add a prospect", "change"),
    ("lead_convert", "리드 전환", "Convert lead", "잠재 고객 자격 전환", "qualify and convert prospect", "submit"),
    ("contacts", "영업 연락처", "Sales contacts", "고객 담당자 찾기", "find customer contacts", "sensitive"),
    ("accounts", "고객 계정", "Customer accounts", "회사 고객 기록", "company customer records", "sensitive"),
    ("opportunities", "영업 기회 목록", "Sales opportunities", "거래 기회 찾기", "find sales deals", "sensitive"),
    ("opportunity_create", "영업 기회 생성", "Create opportunity", "새 거래 기회 열기", "open a sales opportunity", "change"),
    ("pipeline_stage", "파이프라인 단계", "Pipeline stage", "거래 단계 변경", "change deal stage", "submit"),
    ("value_close_date", "기회 금액과 마감일", "Opportunity value and close date", "거래 가치와 예정일", "deal value and target date", "submit"),
    ("activity_timeline", "영업 활동 기록", "Sales activity timeline", "고객 접촉 이력", "customer engagement history", "sensitive"),
    ("log_activity", "영업 활동 등록", "Log sales activity", "통화와 미팅 기록", "record call or meeting", "submit"),
    ("contact_customer", "영업 고객 연락", "Contact sales customer", "고객에게 통화나 메일", "call or email customer", "submit"),
    ("follow_up_task", "영업 후속 작업", "Sales follow-up task", "고객 후속 일정", "customer follow-up reminder", "change"),
    ("quote_review", "영업 견적 검토", "Review sales quote", "거래 제안서 확인", "review deal proposal", "sensitive"),
    ("quote_send", "영업 견적 발송", "Send sales quote", "고객에게 제안서 전송", "send proposal to customer", "submit"),
    ("approval_request", "영업 승인 요청", "Request sales approval", "할인과 거래 승인", "request deal approval", "submit"),
    ("forecast_territory", "영업 예측과 구역", "Sales forecast and territory", "매출 전망 확인", "review revenue forecast", "sensitive"),
)

SUPPORT_AGENT_ROWS: tuple[FeatureRow, ...] = (
    ("ticket_queues", "상담 티켓 대기열", "Support ticket queues", "상담 업무 보기", "open agent work queue", "sensitive"),
    ("ticket_search", "상담 티켓 검색", "Search support tickets", "문의 번호 찾기", "find a customer case", "sensitive"),
    ("ticket_detail", "상담 티켓 상세", "Support ticket detail", "고객 문의 내용", "customer case details", "sensitive"),
    ("requester_profile", "문의자 프로필", "Requester profile", "상담 고객 정보", "support requester details", "sensitive"),
    ("self_assign", "티켓 직접 할당", "Assign ticket to self", "내 상담으로 가져오기", "take ownership of ticket", "submit"),
    ("reassign", "상담 티켓 재할당", "Reassign support ticket", "다른 상담자에게 전달", "transfer case to another agent", "submit"),
    ("public_reply", "고객 공개 답변", "Public customer reply", "문의자에게 답장", "reply to requester", "submit"),
    ("internal_note", "상담 내부 메모", "Internal support note", "상담자 전용 기록", "agent-only ticket note", "submit"),
    ("apply_macro", "상담 매크로 적용", "Apply support macro", "미리 만든 답변 적용", "apply saved response workflow", "submit"),
    ("ticket_status", "티켓 상태 변경", "Change ticket status", "상담 처리 상태", "update case lifecycle", "submit"),
    ("ticket_priority", "티켓 우선순위", "Ticket priority", "상담 긴급도 변경", "change case urgency", "submit"),
    ("followers_cc", "티켓 참조자", "Ticket followers and CC", "상담 참조인 추가", "add case followers", "submit"),
    ("merge_tickets", "상담 티켓 병합", "Merge support tickets", "중복 문의 합치기", "combine duplicate cases", "submit"),
    ("spam_delete", "스팸 티켓 처리", "Spam or delete ticket", "악성 문의 제거", "remove spam case", "submit"),
    ("sla_notifications", "상담 SLA와 알림", "Support SLA and notifications", "응답 기한 확인", "review response deadline", "sensitive"),
)

POS_ROWS: tuple[FeatureRow, ...] = (
    ("item_search", "판매 상품 검색", "Merchant item search", "SKU 상품 찾기", "find item or SKU", "view"),
    ("barcode_scan", "상품 바코드 스캔", "Product barcode scan", "스캔으로 상품 찾기", "scan to find item", "sensitive"),
    ("item_edit", "판매 상품 편집", "Edit merchant item", "상품 정보 수정", "update catalog item", "submit"),
    ("variants_modifiers", "상품 옵션과 변형", "Item variants and modifiers", "사이즈와 추가 옵션", "size and add-on options", "submit"),
    ("pricing_tax", "가격과 세금 설정", "Price and tax settings", "판매가와 세율", "item price and tax rate", "submit"),
    ("stock_levels", "재고 수량", "Inventory levels", "매장 재고 보기", "view store stock", "sensitive"),
    ("receive_stock", "재고 입고", "Receive inventory", "납품 수량 반영", "record received stock", "submit"),
    ("adjust_stock", "재고 조정", "Adjust inventory", "수량 증감 반영", "change stock quantity", "submit"),
    ("inventory_count", "재고 실사", "Inventory count", "매장 수량 확정", "conduct stock count", "submit"),
    ("low_stock_alert", "재고 부족 알림", "Low-stock alerts", "품절 임박 경고", "inventory shortage alert", "change"),
    ("vendors_orders", "공급업체와 발주", "Vendors and purchase orders", "매입 주문 관리", "manage supplier orders", "submit"),
    ("cart", "판매 장바구니", "Merchant sale cart", "계산 상품 목록", "checkout item list", "change"),
    ("discount", "판매 할인 적용", "Apply sale discount", "장바구니 할인", "discount current sale", "submit"),
    ("take_payment", "판매 결제", "Take customer payment", "고객 결제 수단", "charge customer tender", "submit"),
    ("receipt", "판매 영수증", "Sale receipt", "고객 영수증 보기", "customer purchase receipt", "sensitive"),
    ("refund", "판매 환불", "Merchant refund", "결제 취소와 반환", "refund a completed sale", "submit"),
    ("cash_drawer", "현금 서랍", "Cash drawer", "금전함 열기", "open register drawer", "submit"),
    ("register_close", "판매대 마감", "Close register", "교대 정산 마감", "close point-of-sale shift", "submit"),
    ("daily_sales", "일일 매출 보고서", "Daily sales report", "오늘 판매 요약", "today's merchant sales", "sensitive"),
)

FIELD_ROWS: tuple[FeatureRow, ...] = (
    ("project_site_switch", "현장 프로젝트 전환", "Switch project site", "작업 현장 바꾸기", "change active job site", "sensitive"),
    ("work_orders", "현장 작업지시", "Field work orders", "배정 작업 보기", "view assigned field jobs", "sensitive"),
    ("dispatch_schedule", "현장 배차와 일정", "Field dispatch schedule", "기사 작업 일정", "field crew schedule", "sensitive"),
    ("job_checkin", "현장 작업 체크인", "Job-site check-in", "작업지 도착 기록", "record arrival at job", "submit"),
    ("timecard", "현장 근무시간표", "Field timecard", "작업 시간 제출", "submit field hours", "submit"),
    ("drawings_specs", "도면과 시방서", "Drawings and specifications", "현장 설계 문서", "field plans and specs", "sensitive"),
    ("rfi", "현장 정보 요청", "Request for information", "RFI 작성과 검토", "create or review RFI", "submit"),
    ("submittals", "현장 서브미털", "Construction submittals", "자재 승인 문서", "material approval package", "submit"),
    ("daily_log", "현장 일일 기록", "Field daily log", "공사일보 작성", "record daily site activity", "submit"),
    ("photos_attachments", "현장 사진과 첨부", "Field photos and attachments", "작업 증빙 업로드", "upload job evidence", "submit"),
    ("inspections", "현장 검사", "Field inspections", "점검표 작성", "complete site inspection", "submit"),
    ("safety_observations", "현장 안전 관찰", "Safety observations", "위험 요소 기록", "record site hazard", "submit"),
    ("incident_report", "현장 사고 보고", "Field incident report", "안전 사고 제출", "submit site incident", "submit"),
    ("punch_items", "펀치 항목", "Punch items", "미완료 보수 목록", "construction deficiency list", "submit"),
    ("materials", "현장 자재", "Field materials", "작업 자재 수량", "job material inventory", "sensitive"),
    ("equipment", "현장 장비", "Field equipment", "작업 장비 상태", "job equipment status", "sensitive"),
    ("customer_signature", "고객 현장 서명", "Customer job signature", "작업 인수 서명", "customer acceptance signature", "submit"),
    ("complete_job", "현장 작업 완료", "Complete field job", "작업지시 마감", "close assigned job", "submit"),
    ("offline_sync", "현장 오프라인 동기화", "Field offline sync", "오프라인 기록 전송", "sync offline job data", "submit"),
)

GIG_ROWS: tuple[FeatureRow, ...] = (
    ("availability", "기사 온라인 상태", "Worker availability", "운행 온라인과 오프라인", "go online or offline", "change"),
    ("service_type", "수행 서비스 유형", "Worker service type", "승객과 배달 유형", "ride or delivery mode", "change"),
    ("offer_card", "배차 제안", "Dispatch offer", "예상 수익 제안", "upfront work offer", "sensitive"),
    ("offer_response", "배차 수락 또는 거절", "Accept or decline offer", "제안 응답", "respond to dispatch offer", "submit"),
    ("pickup_navigation", "픽업 길찾기", "Pickup navigation", "승객이나 주문 픽업 경로", "route to pickup", "sensitive"),
    ("contact_customer", "승객·고객 연락", "Contact rider or customer", "배차 고객 통화", "message dispatch customer", "submit"),
    ("arrive_wait", "도착과 대기", "Arrive and wait", "픽업 도착 알림", "mark arrival and wait", "submit"),
    ("confirm_pickup", "픽업 확인", "Confirm pickup", "승객 탑승이나 주문 수령", "confirm rider or order pickup", "submit"),
    ("multi_stop", "다중 경유지", "Multiple stops", "추가 정차 지점", "manage trip stops", "sensitive"),
    ("dropoff_proof", "도착 완료와 증빙", "Drop-off and proof", "배달 사진 제출", "submit completion proof", "submit"),
    ("cancellation", "배차 취소 사유", "Dispatch cancellation", "운행이나 주문 취소", "cancel assigned work", "submit"),
    ("safety_help", "기사 안전 지원", "Worker safety help", "운행 중 안전 도구", "in-trip safety support", "submit"),
    ("ratings", "기사 평점", "Worker ratings", "고객 평가 보기", "view service ratings", "sensitive"),
    ("trip_history", "운행·배달 내역", "Work trip history", "완료 작업 기록", "completed dispatch history", "sensitive"),
    ("earnings", "기사 수익", "Worker earnings", "운행별 수입", "trip earnings details", "sensitive"),
    ("incentives", "기사 인센티브", "Worker incentives", "보너스 진행 상황", "bonus progress", "sensitive"),
    ("cash_out", "수익 즉시 출금", "Instant cash-out", "기사 수익 인출", "withdraw worker earnings", "submit"),
)

INCIDENT_ROWS: tuple[FeatureRow, ...] = (
    ("incident_queue", "장애 대기열", "Incident queue", "발생 장애 목록", "open incidents list", "sensitive"),
    ("urgency_sort", "장애 긴급도 정렬", "Incident urgency sort", "우선순위별 장애", "sort incidents by priority", "sensitive"),
    ("detail_timeline", "장애 상세와 타임라인", "Incident detail and timeline", "경보 진행 기록", "alert event history", "sensitive"),
    ("acknowledge", "장애 인지", "Acknowledge incident", "대응 인수 확인", "accept incident ownership", "submit"),
    ("snooze", "장애 알림 일시정지", "Snooze incident", "경보 다시 알림", "defer incident alert", "submit"),
    ("reassign", "장애 재할당", "Reassign incident", "다른 당직자에게 전달", "transfer incident owner", "submit"),
    ("escalate", "장애 에스컬레이션", "Escalate incident", "상위 대응 단계 호출", "raise response level", "submit"),
    ("add_responder", "장애 대응자 추가", "Add incident responder", "추가 담당자 호출", "invite another responder", "submit"),
    ("conference_bridge", "장애 회의 연결", "Incident conference bridge", "대응 회의 참여", "join response conference", "submit"),
    ("status_update", "장애 상태 공지", "Incident status update", "서비스 장애 업데이트", "publish incident update", "submit"),
    ("runbook", "장애 런북 실행", "Incident runbook", "대응 절차 워크플로", "launch response workflow", "submit"),
    ("related_incidents", "관련 장애", "Related incidents", "유사 경보 묶음", "linked incident alerts", "sensitive"),
    ("resolve", "장애 해결 처리", "Resolve incident", "장애 종료 확정", "mark incident resolved", "submit"),
    ("resolved_history", "해결된 장애 기록", "Resolved incident history", "과거 대응 내역", "past incident responses", "sensitive"),
    ("oncall_service_status", "당직 일정과 서비스 상태", "On-call schedule and service status", "현재 당직자 확인", "current on-call and service health", "sensitive"),
)


GROUPS: tuple[GroupSeed, ...] = (
    G(
        "credential_vault", "자격 증명 보관함", "Credential vault and authenticator", "credential_service",
        "비밀번호|자격 증명|로그인|보관함|인증 코드|자동완성",
        "password|credential|login|vault|authenticator code|autofill",
        "계정 보안 설정|브라우저 저장 암호", "account security settings|browser password manager",
        "account.security", "bitwarden_app_settings|google_authenticator_android",
        *_feature_rows(
            CREDENTIAL_ROWS,
            sources="bitwarden_app_settings|google_authenticator_android",
            negative="계정 자체 보안 설정|브라우저 로그인|account security settings|browser login storage",
        ),
    ),
    G(
        "business_accounting", "사업 회계·청구", "Business accounting and invoicing", "business_finance",
        "사업체|장부|송장|비용|고객|공급업체",
        "business|books|invoice|expense|customer|vendor",
        "개인 금융|급여 셀프서비스", "personal finance|employee payroll",
        "finance.longtail.hub", "quickbooks_mobile|xero_mobile",
        *_feature_rows(
            ACCOUNTING_ROWS,
            sources="quickbooks_mobile|xero_mobile",
            negative="개인 청구서|급여 명세|personal bill|employee payslip",
        ),
    ),
    G(
        "crm_sales", "CRM 영업 파이프라인", "CRM sales pipeline", "sales_workspace",
        "리드|고객 계정|영업 기회|파이프라인|견적|매출 예측",
        "lead|customer account|opportunity|pipeline|quote|sales forecast",
        "고객센터 티켓|일반 업무 채널", "support ticket|general work channel",
        "work.hub", "salesforce_mobile_records|salesforce_lead_conversion",
        *_feature_rows(
            CRM_ROWS,
            sources="salesforce_mobile_records|salesforce_lead_conversion",
            negative="고객 문의 티켓|일반 연락처|support request|personal contact",
        ),
    ),
    G(
        "customer_support_agent", "고객지원 상담자 업무공간", "Customer-support agent workspace", "support_workspace",
        "상담자|티켓|문의자|대기열|SLA|고객 답변",
        "support agent|ticket|requester|queue|SLA|customer reply",
        "고객 도움말 요청|일반 메시지", "customer help request|general messaging",
        "support.help", "zendesk_mobile_overview|zendesk_mobile_tickets",
        *_feature_rows(
            SUPPORT_AGENT_ROWS,
            sources="zendesk_mobile_overview|zendesk_mobile_tickets",
            negative="고객용 도움말|일반 채팅|customer self-service help|general chat",
        ),
    ),
    G(
        "merchant_pos_inventory", "매장 POS·재고", "Merchant POS and inventory", "merchant_operations",
        "매장|판매대|상품|SKU|재고|결제",
        "merchant|point of sale|item|SKU|inventory|payment",
        "소비자 장바구니|개인 판매 목록", "consumer cart|personal marketplace listing",
        "shopping_logistics.hub", "square_inventory|square_inventory_counts",
        *_feature_rows(
            POS_ROWS,
            sources="square_inventory|square_inventory_counts",
            negative="소비자 주문|개인 중고 판매|consumer order|personal resale",
        ),
    ),
    G(
        "field_construction_ops", "현장 서비스·건설 운영", "Field service and construction operations", "field_operations",
        "현장|프로젝트|작업지시|도면|검사|펀치",
        "job site|project|work order|drawing|inspection|punch",
        "고객 홈서비스 예약|일반 할 일", "customer home-service booking|general task",
        "home_services.hub", "procore_android_guide|procore_android_punch",
        *_feature_rows(
            FIELD_ROWS,
            sources="procore_android_guide|procore_android_punch",
            negative="고객 수리 예약|개인 작업 목록|customer repair booking|personal task list",
        ),
    ),
    G(
        "gig_worker_dispatch", "플랫폼 노동자 배차", "Gig-worker offer and dispatch", "worker_dispatch",
        "기사|배달원|배차|픽업 업무|운행|수익",
        "driver|courier|dispatch|pickup work|trip|earnings",
        "승객 호출|고객 주문 추적", "rider request|customer order tracking",
        "ride_hailing.hub", "uber_driver_earnings|uber_driver_upfront",
        *_feature_rows(
            GIG_ROWS,
            sources="uber_driver_earnings|uber_driver_upfront",
            negative="승객용 호출|고객 배달 주문|rider booking|customer delivery order",
        ),
    ),
    G(
        "incident_oncall", "장애 대응·당직", "Incident response and on-call", "incident_operations",
        "장애|경보|당직|에스컬레이션|대응자|서비스 상태",
        "incident|alert|on-call|escalation|responder|service status",
        "개인 안전 경보|일반 업무 작업", "personal safety alert|general work task",
        "safety.hub", "pagerduty_mobile|pagerduty_mobile_settings",
        *_feature_rows(
            INCIDENT_ROWS,
            sources="pagerduty_mobile|pagerduty_mobile_settings",
            negative="개인 긴급 알림|일반 팀 작업|personal emergency|general team task",
        ),
    ),
)


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["legacy_tags"] = [
        "v8_operational_workflow" if value == "v7_long_tail" else value
        for value in result.get("legacy_tags", [])
    ]
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    return _retag_function(_v7_build_root(group))


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v7_build_feature(group, seed))
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
    result = copy.deepcopy(_v7_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v7_", "v8_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v7_", "v8_", 1)
        for key in tuple(rule):
            if key.startswith("v7_"):
                rule[f"v8_{key[3:]}"] = rule.pop(key)
    return result


V8_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V8_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
REQUIRED_FUNCTIONS = frozenset({
    "credential_vault.emergency_access",
    "credential_vault.export_codes",
    "business_accounting.invoice_send",
    "business_accounting.reconcile",
    "crm_sales.lead_convert",
    "crm_sales.quote_send",
    "customer_support_agent.public_reply",
    "customer_support_agent.merge_tickets",
    "merchant_pos_inventory.take_payment",
    "merchant_pos_inventory.refund",
    "field_construction_ops.incident_report",
    "field_construction_ops.customer_signature",
    "gig_worker_dispatch.offer_response",
    "gig_worker_dispatch.cash_out",
    "incident_oncall.acknowledge",
    "incident_oncall.resolve",
})


class V8CatalogValidationError(ValueError):
    """Raised when v8 cannot be merged without semantic or safety drift."""


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _pre_v8_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V8_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V8_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", [])
        if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", [])
        if str(item["intent_id"]) not in intent_ids
    ]
    result.pop("official_sources_v8", None)
    result["catalog_version"] = CATALOG_V7_VERSION
    result["description"] = CATALOG_V7_DESCRIPTION
    return result


def _ensure_v7(payload: Mapping[str, object]) -> dict[str, object]:
    # Canonical storage may carry derived alias-context guards on v7 records.
    # Rebuild those records from the reviewed v7 source pack before validating
    # v8, rather than treating derived runtime enrichment as source drift.
    return merge_v7_with_base(_pre_v7_payload(_pre_v8_payload(payload)))


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Load a clean v7 base whether canonical storage is at v6, v7, or v8."""

    return _ensure_v7(json.loads(path.read_text(encoding="utf-8")))


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V8_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V8_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    if not present_functions and not present_intents and "official_sources_v8" not in payload:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V8CatalogValidationError("partial v8 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V8CatalogValidationError("v8 collides with a different function or intent definition")
    if payload.get("official_sources_v8") != OFFICIAL_SOURCES:
        raise V8CatalogValidationError("v8 official evidence registry differs")
    if payload.get("catalog_version") != CATALOG_V8_VERSION or payload.get("description") != CATALOG_V8_DESCRIPTION:
        raise V8CatalogValidationError("v8 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def validate_v8_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    errors: list[str] = []
    function_ids = [str(item["function_id"]) for item in V8_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V8_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V8_FUNCTIONS if bool(item["terminal"])}
    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v8 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v8 intent IDs: {sorted(duplicates)}")
    if len(REQUIRED_DOMAINS) != 8:
        errors.append("v8 must contain exactly eight reviewed priority domains")
    domain_terminal_counts = Counter(
        str(item["domain"]) for item in V8_FUNCTIONS if bool(item["terminal"])
    )
    if any(domain_terminal_counts[domain] < 14 for domain in REQUIRED_DOMAINS):
        errors.append(f"every v8 domain requires at least fourteen terminals: {dict(sorted(domain_terminal_counts.items()))}")
    if len(terminal_ids) < 112:
        errors.append("v8 requires at least 112 terminal functions plus domain hubs")
    if missing := REQUIRED_FUNCTIONS - set(function_ids):
        errors.append(f"missing required v8 functions: {sorted(missing)}")

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
    forbidden_keys = {"x", "y", "bounds", "coordinate", "coordinates", "package", "package_name", "resource_id"}
    for function in V8_FUNCTIONS:
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
            errors.append(f"{function_id}: app-specific package, resource, or coordinate data is forbidden")
        consequential = bool(function["state_changing"]) or function["risk_level"] == "high"
        if consequential:
            if function["automation_policy"] != "never_auto" or function["stop_policy"] != "before_action":
                errors.append(f"{function_id}: unsafe final-action boundary")
            boundary = " ".join(function["risk_cues"].get("user_boundary", []))  # type: ignore[union-attr]
            if "사용자" not in boundary or "user" not in boundary.casefold() or "press" not in boundary.casefold():
                errors.append(f"{function_id}: explicit user-owned final click is missing")
        elif function["terminal"]:
            if function["automation_policy"] != "safe_navigation":
                errors.append(f"{function_id}: read-only terminal must remain safe navigation")
        else:
            if function["automation_policy"] != "safe_navigation" or function["stop_policy"] != "continue":
                errors.append(f"{function_id}: hub must remain navigation-only")
    if used_sources != known_sources:
        errors.append(f"orphan official sources: {sorted(known_sources - used_sources)}")

    intent_terminals = [str(item["terminal_function"]) for item in V8_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v8 requires exactly one intent per terminal function")
    terminal_by_id = {str(item["function_id"]): item for item in V8_FUNCTIONS}
    for intent in V8_INTENTS:
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
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v8_"):
                errors.append(f"{intent_id}: malformed semantic rule")
            for key in ("v8_discriminative_keys", "v8_negative_context_keys", "v8_positive_context_keys"):
                values = list(rule.get(key, []))
                if values != sorted(dict.fromkeys(values)):
                    errors.append(f"{intent_id}: nondeterministic {key}")

    materialized = False
    if base_payload is not None:
        materialized = _materialization_state(base_payload)
        pre_v8 = _ensure_v7(base_payload)
        base_function_ids = {str(item["function_id"]) for item in pre_v8.get("functions", [])}
        base_intent_ids = {str(item["intent_id"]) for item in pre_v8.get("intents", [])}
        if collisions := sorted(set(function_ids).intersection(base_function_ids)):
            errors.append(f"v8 function IDs collide with v1-v7: {collisions[:12]}")
        if collisions := sorted(set(intent_ids).intersection(base_intent_ids)):
            errors.append(f"v8 intent IDs collide with v1-v7: {collisions[:12]}")
        pattern_owners: dict[str, set[str]] = {}
        for intent in [*pre_v8.get("intents", []), *V8_INTENTS]:
            owner = str(intent["intent_id"])
            for pattern in intent.get("patterns", []):
                key = _runtime_pattern_key(pattern)
                if key:
                    pattern_owners.setdefault(key, set()).add(owner)
        collisions = {key: sorted(owners) for key, owners in pattern_owners.items() if len(owners) > 1}
        if collisions:
            errors.append(f"normalized goal-pattern collisions: {list(collisions.items())[:8]}")
        base_rule_signatures = {
            _rule_signature(rule)
            for intent in pre_v8.get("intents", [])
            for rule in intent.get("goal_rules", [])
            if _rule_signature(rule)
        }
        v8_rule_owners: dict[tuple[str, ...], set[str]] = {}
        for intent in V8_INTENTS:
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if signature in base_rule_signatures:
                    errors.append(f"{intent['intent_id']}: goal rule collides with v1-v7")
                v8_rule_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
        shared_rules = {signature: sorted(owners) for signature, owners in v8_rule_owners.items() if len(owners) > 1}
        if shared_rules:
            errors.append(f"v8 goal-rule collisions: {list(shared_rules.items())[:8]}")

    semantic_payload = copy.deepcopy({"functions": V8_FUNCTIONS, "intents": V8_INTENTS})
    for function in semantic_payload["functions"]:
        function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = (
        "com.", "package name", "resource-id", "screen coordinate", "x coordinate",
        "bitwarden", "google authenticator", "quickbooks", "xero", "salesforce",
        "zendesk", "square", "procore", "uber", "pagerduty",
    )
    if any(re.search(rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])", semantic_text) for value in forbidden_fragments):
        errors.append("v8 runtime semantics contain an app identity or recorded UI path")

    if errors:
        raise V8CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V8_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V8_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_terminal_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES),
        "aliases": sum(len(values) for item in V8_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V8_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V8_INTENTS),
        "compositional_goal_rules": sum(
            1 for item in V8_INTENTS for rule in item["goal_rules"]
            if rule["rule_kind"] in {"v8_compositional_domain", "v8_consequence_context"}
        ),
        "state_changing": sum(bool(item["state_changing"]) for item in V8_FUNCTIONS),
        "high_risk": sum(item["risk_level"] == "high" for item in V8_FUNCTIONS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, idempotent, fail-closed v7+v8 catalog copy."""

    validate_v8_data(base_payload)
    if _materialization_state(base_payload):
        return copy.deepcopy(dict(base_payload))
    merged = _ensure_v7(base_payload)
    merged["catalog_version"] = CATALOG_V8_VERSION
    merged["description"] = CATALOG_V8_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V8_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V8_INTENTS)]
    merged["official_sources_v8"] = copy.deepcopy(OFFICIAL_SOURCES)
    return merged


def main() -> int:
    print(json.dumps(validate_v8_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
