from __future__ import annotations

"""Research-isolated V18 candidate catalog.

This module appends twelve evidence-backed consumer and operator domains to an
exact in-memory V17 payload.  It never writes the physical catalog.  Every
terminal is a sensitive/view or consequential destination, remains
``never_auto``, stops before the destination action, and leaves the final press
to the user.
"""

import copy
import hashlib
import json
import posixpath
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from navigation_catalog_v10_data import (
    F,
    G,
    FeatureSeed,
    GroupSeed,
    _build_feature as _v10_build_feature,
    _build_intent as _v10_build_intent,
    _build_root as _v10_build_root,
    _runtime_pattern_key,
)
from navigation_catalog_v17_data import (
    CATALOG_V17_DESCRIPTION,
    CATALOG_V17_VERSION,
    V17_FUNCTIONS,
    V17_INTENTS,
    load_base_catalog as load_v16_source_base,
    merge_with_base as merge_v17_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DESIGN_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V18_RESEARCH.md"
SOURCE_DOCUMENT_SHA256 = {
    DESIGN_SOURCE_RELATIVE_PATH: "cca4aac49ad2811dfb1d55e059628c7261723becec6fd27536a648fddf9f5c13",
}
SOURCE_DOCUMENT_METADATA = {
    path: {"path": path, "algorithm": "sha256", "sha256": digest}
    for path, digest in SOURCE_DOCUMENT_SHA256.items()
}

CATALOG_V18_VERSION = "18.0.0"
COLLECTED_ON = "2026-07-30"
RETRIEVED_AT = "2026-07-30T00:00:00+09:00"
CATALOG_V18_DESCRIPTION = (
    "ExitGuide research-isolated V18 ontology for advertising, device repair, "
    "admissions, platform appeals, debt response, rental vehicles, airline "
    "post-ticket servicing, home connectivity, recalls, school-family records, "
    "marketplace seller operations, and gig-worker account earnings; every "
    "terminal press remains user-owned."
)

BASELINE_COUNTS = {"domains": 203, "functions": 3358, "intents": 3128}
PROJECTED_COUNTS = {
    "domains": 215,
    "physical_functions": 3610,
    "physical_terminal_functions": 3368,
    "physical_intents": 3368,
}


class V18CatalogValidationError(ValueError):
    """Raised when the V18 candidate cannot be proven complete and isolated."""


@dataclass(frozen=True)
class ReviewedFeature:
    key: str
    classification: str
    name_ko: str
    name_en: str
    goal_ko: str
    goal_en: str
    purpose_ko: str
    purpose_en: str
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    jurisdiction_guard: str
    safety_boundary: str
    source_tags: tuple[str, ...]


@dataclass(frozen=True)
class FeatureRow:
    key: str
    classification: str
    name_ko: str
    name_en: str
    goal_ko: str
    goal_en: str
    purpose_ko: str
    purpose_en: str
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    source_tags: tuple[str, ...]


@dataclass(frozen=True)
class DomainSpec:
    domain: str
    root_ko: str
    root_en: str
    jurisdiction: str
    boundary: str
    avoid_root: str
    collision_terms: tuple[str, ...]
    nearest_existing_domains: tuple[str, ...]
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    features: tuple[ReviewedFeature, ...]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _terms(value: str) -> tuple[str, ...]:
    return _dedupe(value.split("|"))


def R(
    key: str,
    classification: str,
    name_ko: str,
    name_en: str,
    goal_ko: str,
    goal_en: str,
    purpose_ko: str,
    purpose_en: str,
    roles: str,
    assets: str,
    states: str,
    source_tags: str,
) -> FeatureRow:
    """Declare one reviewed terminal; goals and purposes are never synthesized."""

    if classification not in {"S", "C"}:
        raise V18CatalogValidationError(f"{key}: classification must be S or C")
    return FeatureRow(
        key,
        classification,
        name_ko,
        name_en,
        goal_ko,
        goal_en,
        purpose_ko,
        purpose_en,
        _terms(roles),
        _terms(assets),
        _terms(states),
        _terms(source_tags),
    )


def D(
    domain: str,
    root_ko: str,
    root_en: str,
    jurisdiction: str,
    boundary: str,
    avoid_root: str,
    collision_terms: str,
    nearest_existing_domains: str,
    roles: str,
    assets: str,
    states: str,
    rows: tuple[FeatureRow, ...],
) -> DomainSpec:
    if len(rows) != 20:
        raise V18CatalogValidationError(f"{domain}: exactly 20 reviewed terminals are required")
    features = tuple(
        ReviewedFeature(
            key=row.key,
            classification=row.classification,
            name_ko=row.name_ko,
            name_en=row.name_en,
            goal_ko=row.goal_ko,
            goal_en=row.goal_en,
            purpose_ko=row.purpose_ko,
            purpose_en=row.purpose_en,
            roles=row.roles,
            assets=row.assets,
            states=row.states,
            jurisdiction_guard=jurisdiction,
            safety_boundary=(
                f"{row.name_en}: {boundary}; verify the explicit role, governed asset, "
                f"lifecycle state, provider, and jurisdiction; stop before the final "
                f"{'sensitive disclosure' if row.classification == 'S' else 'submission or state change'}"
            ),
            source_tags=row.source_tags,
        )
        for row in rows
    )
    return DomainSpec(
        domain,
        root_ko,
        root_en,
        jurisdiction,
        boundary,
        avoid_root,
        _terms(collision_terms),
        _terms(nearest_existing_domains),
        _terms(roles),
        _terms(assets),
        _terms(states),
        features,
    )


# This tuple is the normative bilingual V18 domain/terminal table.  Names,
# representative goals, and purposes are authored here before aliases/patterns.
REVIEWED_DOMAINS: tuple[DomainSpec, ...] = (
    D(
        "digital_ad_campaign_ops",
        "디지털 광고 캠페인 운영",
        "Digital advertising campaign operations",
        "identified advertising provider, advertiser account, billing country, and campaign market",
        "do not cross into app-store releases, political campaign compliance, CRM sales, creator monetization, or ordinary social posting",
        "marketing.settings",
        "campaign|audience|creative|conversion|billing",
        "marketing|campaign_finance_compliance|crm_sales|creator_monetization|app_store_release_management",
        "advertiser account owner|advertiser campaign manager|advertiser analyst|advertiser billing administrator",
        "advertiser account|campaign|ad group or ad set|creative|audience|conversion goal|budget and billing record",
        "draft|eligible|under review|approved|active|paused|limited|ended|billing attention",
        (
            R("account_role_access", "S", "광고 계정 역할 및 접근 권한", "Advertiser account role access", "광고주 계정에서 내 역할과 접근 범위를 확인하고 싶어", "I need to inspect my role and access scope on the advertiser account", "권한을 바꾸지 않고 광고 계정의 사용자 역할과 허용 범위를 검토", "Review advertiser role scope without changing account access", "advertiser account owner|advertiser campaign manager", "advertiser account role record", "invited|active|restricted", "access"),
            R("campaign_portfolio_status", "S", "캠페인 목록 및 게재 상태", "Campaign portfolio and delivery status", "이 광고주 계정의 캠페인별 게재 상태를 보고 싶어", "Show the delivery state of campaigns in this advertiser account", "캠페인별 초안·활성·일시중지 상태를 변경 없이 비교", "Compare draft, active, and paused campaign states without mutation", "advertiser campaign manager|advertiser analyst", "campaign portfolio", "draft|active|paused|ended", "campaign"),
            R("campaign_objective_review", "S", "캠페인 목표 및 유형 검토", "Campaign objective and type review", "게시 전 캠페인의 목표와 유형을 다시 확인하고 싶어", "I want to review the campaign objective and type before publication", "선택된 광고 목표와 캠페인 유형이 계정 목적에 맞는지 열람", "Inspect the selected advertising objective and campaign type", "advertiser campaign manager", "campaign objective configuration", "selected|editable|locked after launch", "campaign"),
            R("budget_bid_review", "S", "예산 및 입찰 설정 검토", "Budget and bid setting review", "적용하지 않고 광고 예산과 입찰 설정을 확인하고 싶어", "Let me inspect the advertising budget and bid settings without applying them", "현재 예산 한도와 입찰 전략을 읽기 전용으로 검토", "Review current budget limits and bidding strategy as read-only data", "advertiser campaign manager|advertiser billing administrator", "campaign budget and bid record", "draft|scheduled|active", "budget"),
            R("audience_targeting_review", "S", "잠재고객 및 타기팅 검토", "Audience and targeting review", "이 광고 세트가 대상으로 삼는 잠재고객을 확인하고 싶어", "I need to see which audience this ad set targets", "지역·인구통계·관심사 조건을 수정 없이 점검", "Inspect geography, demographic, and interest targeting without edits", "advertiser campaign manager|advertiser analyst", "audience targeting definition", "estimated|saved|applied", "audience"),
            R("creative_asset_review", "S", "광고 소재 검토", "Advertising creative review", "제출 전에 광고 문구와 이미지를 확인하고 싶어", "I want to inspect the advertising copy and media before submission", "캠페인에 연결된 소재 버전과 랜딩 대상을 열람", "Review creative versions and their linked landing destinations", "advertiser campaign manager|advertiser creative editor", "advertising creative asset", "draft|under review|approved|rejected", "creative"),
            R("conversion_goal_review", "S", "전환 목표 검토", "Conversion goal review", "캠페인이 측정하는 전환 목표를 확인하고 싶어", "Show the conversion goal measured by this campaign", "선택된 전환 이벤트와 측정 상태를 변경 없이 검토", "Inspect the selected conversion event and measurement state", "advertiser campaign manager|advertiser analyst", "conversion goal and event", "configured|unverified|recording", "conversion"),
            R("policy_approval_status", "S", "광고 정책 및 승인 상태", "Advertising policy approval status", "광고가 심사 중인지 승인 또는 제한되었는지 보고 싶어", "Tell me whether the ad is under review, approved, or limited", "정책 심사 결과와 제한 사유를 상태 화면에서 확인", "View policy review outcomes and restriction reasons", "advertiser campaign manager|advertiser policy reviewer", "ad policy review record", "under review|approved|limited|rejected", "policy"),
            R("delivery_performance_view", "S", "광고 게재 성과 보기", "Advertising delivery performance view", "이 캠페인의 노출과 클릭 및 전환 성과를 보고 싶어", "I want to view impressions, clicks, and conversions for this campaign", "기간별 광고 성과 지표를 수정 없이 분석", "Analyze time-bounded campaign delivery metrics without changes", "advertiser analyst|advertiser campaign manager", "campaign performance report", "collecting|available|delayed", "performance"),
            R("invoice_transaction_view", "S", "광고 거래 및 청구서 보기", "Advertising transactions and invoices", "광고 계정의 결제 거래와 청구서를 확인하고 싶어", "Show transactions and invoices for the advertising account", "광고비 거래 내역과 발행된 청구 문서를 읽기 전용으로 열람", "View advertising charges and issued invoices without billing mutation", "advertiser billing administrator|advertiser account owner", "advertising transaction and invoice", "pending|posted|paid|failed", "billing"),
            R("campaign_pause_request", "C", "캠페인 일시중지", "Campaign pause request", "이 캠페인을 일시중지하는 화면까지 안내해 줘", "Take me to the control for pausing this campaign", "활성 캠페인의 게재 중지 대상을 확인하고 사용자가 최종 중지", "Present the active campaign pause control for the user's final action", "advertiser campaign manager", "active campaign", "active|pause eligible|awaiting confirmation", "campaign"),
            R("campaign_resume_request", "C", "캠페인 게재 재개", "Campaign resume request", "중지된 캠페인의 게재를 다시 시작하는 곳을 찾아줘", "Find the control to resume delivery for the paused campaign", "중지 상태와 재개 자격을 확인한 뒤 사용자가 게재를 재개", "Verify paused state and let the user finally resume delivery", "advertiser campaign manager", "paused campaign", "paused|resume eligible|awaiting confirmation", "campaign"),
            R("campaign_publish", "C", "캠페인 게시", "Campaign publication", "검토한 캠페인을 게시하는 마지막 화면으로 이동해 줘", "Navigate to the final screen for publishing the reviewed campaign", "목표·예산·소재·정책 상태를 검토한 캠페인을 사용자가 직접 게시", "Let the user publish a reviewed campaign after configuration checks", "advertiser campaign manager", "reviewed campaign draft", "draft|publish eligible|awaiting confirmation", "campaign|policy"),
            R("budget_bid_apply", "C", "예산 및 입찰 변경 적용", "Budget and bid change application", "새 광고 예산과 입찰 값을 적용하는 곳으로 안내해 줘", "Guide me to apply the new advertising budget and bid values", "비용 영향이 있는 예산·입찰 변경을 사용자가 최종 적용", "Leave final application of cost-affecting budget and bid changes to the user", "advertiser campaign manager|advertiser billing administrator", "campaign budget and bid configuration", "edited|validation passed|awaiting confirmation", "budget"),
            R("audience_targeting_apply", "C", "잠재고객 타기팅 변경 적용", "Audience targeting change application", "수정한 타기팅 조건을 적용할 화면을 열어 줘", "Open the screen to apply the edited audience targeting", "도달 범위를 바꾸는 타기팅 수정을 사용자가 확인 후 적용", "Have the user confirm targeting changes that alter campaign reach", "advertiser campaign manager", "audience targeting configuration", "edited|estimated|awaiting confirmation", "audience"),
            R("creative_submit_review", "C", "광고 소재 심사 제출", "Creative review submission", "완성한 광고 소재를 정책 심사에 제출하려고 해", "I want to submit the completed creative for policy review", "광고 소재와 연결 대상을 확인한 후 사용자가 심사를 요청", "Let the user request policy review after inspecting creative and destination", "advertiser creative editor|advertiser campaign manager", "completed advertising creative", "draft|submission ready|awaiting confirmation", "creative|policy"),
            R("conversion_goal_apply", "C", "전환 목표 변경 적용", "Conversion goal change application", "선택한 전환 목표를 이 캠페인에 적용하고 싶어", "I want to apply the selected conversion goal to this campaign", "성과 최적화에 영향을 주는 전환 목표 변경을 사용자가 적용", "Leave final application of the optimization goal change to the user", "advertiser campaign manager|advertiser analyst", "campaign conversion configuration", "selected|compatible|awaiting confirmation", "conversion"),
            R("billing_profile_update", "C", "광고 결제 프로필 변경", "Advertising billing profile update", "광고 계정의 결제 프로필을 변경하는 곳으로 가고 싶어", "Take me to update the advertising account billing profile", "청구 국가·결제 수단 등 비용 정보를 사용자가 직접 변경", "Let the user finally change cost-bearing billing profile details", "advertiser billing administrator|advertiser account owner", "advertising billing profile", "verified|editable|awaiting confirmation", "billing"),
            R("account_access_invitation", "C", "광고 계정 사용자 초대", "Advertiser account access invitation", "새 팀원을 광고 계정 역할로 초대하려고 해", "I want to invite a teammate into an advertiser account role", "초대 대상과 역할 범위를 확인하고 사용자가 접근 권한을 부여", "Have the user grant scoped advertiser access after reviewing invitee and role", "advertiser account owner", "advertiser account invitation", "draft|role selected|awaiting confirmation", "access"),
            R("account_access_removal", "C", "광고 계정 접근 권한 제거", "Advertiser account access removal", "이 사용자의 광고 계정 접근 권한을 제거하는 곳을 열어 줘", "Open the control to remove this user's advertiser account access", "정확한 사용자와 영향 범위를 확인한 후 계정 소유자가 접근을 제거", "Require the account owner to confirm the exact user before removing access", "advertiser account owner", "advertiser account membership", "active|removal eligible|awaiting confirmation", "access"),
        ),
    ),
    D(
        "consumer_device_warranty_repair",
        "소비자 기기 보증 및 수리",
        "Consumer device warranty and repair",
        "identified device maker or authorized service provider, device serial or IMEI, purchase region, and coverage terms",
        "do not treat vehicle service, home-service booking, enterprise asset maintenance, app troubleshooting, or ordinary merchandise returns as this device case",
        "support.help",
        "device|coverage|service|estimate|replacement",
        "automotive_vehicle|home_services|maintenance_asset_ops|support|refund",
        "device owner|authorized device user|authorized repair intake agent",
        "personally owned device|serial or IMEI|coverage record|diagnosed issue|service request|inspection estimate|repair or replacement",
        "unregistered|registered|covered|not covered|diagnosis pending|in transit|inspecting|estimate pending|repairing|completed",
        (
            R("product_registration", "C", "기기 제품 등록", "Device product registration", "내 기기를 제조사 계정에 등록하는 화면으로 가고 싶어", "Take me to register my device with the manufacturer account", "소유 기기와 일련번호를 확인한 뒤 사용자가 보증 서비스용 등록을 완료", "Let the owner register the identified serial for warranty service", "device owner|authorized device user", "personally owned device registration", "unregistered|registration ready|awaiting confirmation", "registration"),
            R("device_serial_lookup", "S", "기기 일련번호 조회", "Device serial or IMEI lookup", "수리할 기기의 일련번호나 IMEI 기록을 찾고 싶어", "I need to find the serial or IMEI record for the device being serviced", "수리 대상 기기의 고유 식별자와 모델을 변경 없이 확인", "Inspect the service device identifier and model without mutation", "device owner|authorized repair intake agent", "device serial or IMEI record", "recognized|not found|multiple matches", "lookup"),
            R("warranty_eligibility", "S", "보증 적용 자격 확인", "Warranty coverage eligibility", "이 기기가 현재 보증 수리 대상인지 확인하고 싶어", "Check whether this device is currently eligible for warranty service", "구매 지역과 보증 기간에 따른 적용 여부를 정보로 검토", "Review coverage eligibility under purchase-region and term rules", "device owner|authorized device user", "device warranty coverage record", "active|expired|exception review", "coverage"),
            R("damage_issue_classification", "C", "손상 및 문제 유형 분류", "Damage and issue classification", "기기의 손상이나 고장 유형을 수리 요청에 기록하려고 해", "I want to record the device damage or fault category for service", "진단을 확정하지 않고 사용자가 관찰한 증상과 손상 유형을 제출", "Let the user submit observed symptoms without claiming a diagnosis", "device owner|authorized device user", "reported device issue", "unclassified|category selected|awaiting confirmation", "diagnosis"),
            R("service_option_comparison", "S", "수리 서비스 방식 비교", "Repair service option comparison", "방문 수리와 배송 수리 및 교체 옵션을 비교하고 싶어", "Compare walk-in, mail-in, and replacement service options", "기기와 지역에 제공되는 서비스 방식·기간·비용 정보를 비교", "Compare available service modes, timing, and indicative cost", "device owner|authorized device user", "device service option set", "available|limited by region|unavailable", "service"),
            R("repair_estimate_preview", "S", "수리 예상 비용 보기", "Repair estimate preview", "신청 전에 예상 수리 비용 범위를 보고 싶어", "Show the estimated repair cost range before I request service", "검사 전 안내되는 예상 비용을 확정 견적으로 오인하지 않고 열람", "View a pre-inspection cost range without treating it as a final estimate", "device owner|authorized device user", "preliminary repair estimate", "indicative|inspection required|coverage dependent", "estimate"),
            R("service_center_lookup", "S", "공식 서비스 센터 찾기", "Authorized service center lookup", "내 지역에서 이 기기를 수리하는 공식 센터를 찾고 싶어", "Find an authorized center that services this device in my area", "기기 모델과 서비스 지역에 맞는 공식 방문 지점을 조회", "Locate provider-authorized walk-in service for the model and region", "device owner|authorized device user", "authorized service-center directory", "open|appointment required|model unsupported", "service"),
            R("service_appointment_request", "C", "수리 방문 예약", "Repair appointment request", "선택한 서비스 센터에 수리 방문을 예약하려고 해", "I want to book a repair visit at the selected service center", "센터·기기·시간을 확인한 뒤 사용자가 방문 요청을 제출", "Have the user submit the visit after confirming center, device, and time", "device owner|authorized device user", "walk-in repair appointment", "slot selected|request ready|awaiting confirmation", "service"),
            R("mail_in_service_request", "C", "배송 수리 신청", "Mail-in repair request", "이 기기의 배송 수리 요청을 제출하는 곳으로 안내해 줘", "Guide me to submit a mail-in repair request for this device", "수거 주소와 기기 정보를 검토하고 사용자가 RMA 또는 배송 수리를 요청", "Let the user request mail-in service after reviewing device and pickup data", "device owner|authorized device user", "mail-in service request or RMA", "eligible|address verified|awaiting confirmation", "service|shipping"),
            R("backup_readiness", "S", "수리 전 데이터 백업 준비", "Pre-repair data backup readiness", "기기를 맡기기 전에 백업해야 할 항목을 확인하고 싶어", "Show what should be backed up before the device is handed over", "수리 전 데이터 보호 준비사항을 열람하되 백업 완료를 추정하지 않음", "Review data-protection preparation without assuming a backup succeeded", "device owner|authorized device user", "device backup readiness checklist", "not reviewed|incomplete|owner confirmed", "preparation"),
            R("device_reset_authorization", "C", "수리 전 기기 초기화", "Pre-repair device reset authorization", "수리 전 초기화를 시작하는 마지막 화면으로 이동해 줘", "Take me to the final control for resetting the device before repair", "데이터 삭제 영향을 경고하고 소유자가 직접 초기화를 승인", "Warn about data loss and leave reset authorization to the device owner", "device owner", "personally owned device data", "backup owner-confirmed|reset ready|awaiting confirmation", "preparation"),
            R("shipping_label_request", "C", "수리 배송 라벨 요청", "Repair shipping label request", "배송 수리용 라벨을 발급받는 곳을 열어 줘", "Open the control to request a shipping label for this repair", "정확한 RMA와 반송 주소를 확인한 뒤 사용자가 라벨 생성을 요청", "Let the user request a label after verifying RMA and return address", "device owner|authorized device user", "repair return shipping label", "RMA active|address confirmed|awaiting confirmation", "shipping"),
            R("repair_status", "S", "기기 수리 진행 상태", "Device repair status", "접수한 기기가 검사 중인지 수리 중인지 확인하고 싶어", "Check whether my submitted device is being inspected or repaired", "서비스 요청의 접수·검사·부품·수리 상태를 변경 없이 조회", "View intake, inspection, parts, and repair stages without changes", "device owner|authorized device user", "device service request", "received|inspecting|parts pending|repairing|completed", "status"),
            R("inspection_result", "S", "수리 검사 결과 보기", "Repair inspection result", "서비스 센터가 기록한 기기 검사 결과를 보고 싶어", "I want to view the inspection result recorded by the service center", "진단된 손상과 보증 적용 판단을 승인 동작과 분리해 열람", "View diagnosed damage and coverage findings separately from approval", "device owner|authorized device user", "repair inspection finding", "inspection complete|estimate issued|exception noted", "estimate"),
            R("estimate_approval", "C", "수리 견적 승인", "Repair estimate approval", "검사 후 제시된 수리 견적을 승인하는 곳으로 가고 싶어", "Take me to approve the repair estimate issued after inspection", "기기·비용·수리 범위를 확인하고 사용자가 유상 수리를 승인", "Require the user to confirm device, price, and scope before approval", "device owner", "final repair estimate", "issued|approval eligible|awaiting confirmation", "estimate"),
            R("estimate_decline", "C", "수리 견적 거절", "Repair estimate decline", "제시된 수리 견적을 거절하는 화면을 열어 줘", "Open the screen to decline the issued repair estimate", "반환 또는 폐기 영향까지 확인한 뒤 사용자가 견적을 거절", "Let the user decline after reviewing return or disposal consequences", "device owner", "final repair estimate", "issued|decline eligible|awaiting confirmation", "estimate"),
            R("replacement_choice", "C", "교체 기기 선택 수락", "Replacement device choice", "수리 대신 제안된 교체 옵션을 선택하려고 해", "I want to select the replacement option offered instead of repair", "교체 모델·비용·소유권 조건을 검토하고 사용자가 선택을 수락", "Have the user accept a replacement after reviewing model, cost, and ownership terms", "device owner", "repair replacement offer", "offered|choice selected|awaiting confirmation", "replacement"),
            R("proof_of_purchase_correction", "C", "구매 증빙 수정 제출", "Proof-of-purchase correction", "보증 확인에 필요한 구매 증빙을 수정해서 제출하고 싶어", "I need to correct and submit proof of purchase for coverage review", "정확한 기기와 구매 기록에 보정 증빙을 사용자가 제출", "Let the user submit corrected evidence for the identified device purchase", "device owner|authorized device user", "device proof-of-purchase record", "missing|rejected|correction ready", "coverage"),
            R("repair_history", "S", "기기 수리 이력", "Device repair history", "이 기기에 완료된 이전 수리 기록을 확인하고 싶어", "Show prior completed repair records for this device", "현재 소유 기기의 서비스 이력과 교체 기록을 읽기 전용으로 열람", "View repair and replacement history for the identified device", "device owner|authorized device user", "device repair history", "available|restricted|no records", "history"),
            R("return_delivery_status", "S", "수리 기기 반환 배송 상태", "Repaired device return status", "수리되거나 교체된 기기의 반환 배송 상태를 보고 싶어", "Track the return shipment of the repaired or replacement device", "완료된 서비스 건의 반환 운송과 인도 상태를 조회", "View return transit and delivery state for the completed service case", "device owner|authorized device user", "repaired-device return shipment", "label created|in transit|delivered|exception", "shipping|status"),
        ),
    ),
    D(
        "higher_education_admissions",
        "고등교육 입학 지원",
        "Higher-education admissions",
        "identified prospective applicant, application provider, institution, program, entry term, and admissions jurisdiction",
        "prospective-applicant records only; never route institutional admissions queues, enrolled-student administration, or student-aid case handling here",
        "higher_education_student_admin.hub",
        "application|program|transcript|decision|deposit",
        "higher_education_student_admin|student_financial_aid_services|education|classroom_instructor_ops|special_education_program_admin",
        "prospective applicant|applicant-authorized recommender|applicant counselor",
        "prospective application|institution and program list|applicant profile|supporting document|submission|admissions decision",
        "researching|draft|awaiting recommender|ready for review|submitted|incomplete|decided|wait-listed|deposit handoff",
        (
            R("applicant_profile_type", "C", "지원자 유형 및 프로필", "Applicant type and profile", "내 지원자 유형과 기본 프로필 섹션을 입력하고 싶어", "I want to complete my applicant type and core profile sections", "예비 지원자가 본인 유형과 기본 신상 정보를 직접 저장", "Let the prospective applicant save their own type and core profile", "prospective applicant", "prospective applicant profile", "draft|required fields complete|awaiting confirmation", "profile"),
            R("institution_program_search", "S", "대학 및 전공 프로그램 찾기", "Institution and program search", "지원할 대학과 전공 프로그램을 찾아 비교하고 싶어", "I need to search and compare institutions and programs for my application", "지원 가능 기관·프로그램과 입학 학기를 변경 없이 탐색", "Explore eligible institutions, programs, and entry terms without applying", "prospective applicant|applicant counselor", "institution and program directory", "open|deadline passed|not accepting", "search"),
            R("saved_institution_list", "C", "지원 대학 저장 목록", "Saved institution list", "관심 있는 대학과 프로그램을 내 지원 목록에 저장하고 싶어", "I want to save selected institutions and programs to my application list", "예비 지원자가 지원 검토 대상을 개인 목록에 추가하거나 제거", "Let the applicant maintain a personal list of prospective applications", "prospective applicant", "saved institution and program list", "not saved|saved|limit reached", "search"),
            R("requirements_deadlines", "S", "지원 요건 및 마감일", "Application requirements and deadlines", "선택한 대학의 제출 요건과 마감일을 확인하고 싶어", "Show the requirements and deadlines for the selected institution", "기관·프로그램·학기별 필수 항목과 일정을 읽기 전용으로 확인", "Review required items and dates scoped to institution, program, and term", "prospective applicant|applicant counselor", "institution application requirement set", "current|changed|deadline passed", "requirements"),
            R("activities_section", "C", "활동 경력 섹션 작성", "Applicant activities section", "입학 지원서의 활동 경력 섹션을 작성하려고 해", "I want to complete the activities section of my admission application", "예비 지원자가 본인의 활동 기록을 검토하고 직접 저장", "Let the applicant review and save their own activity record", "prospective applicant", "application activities record", "blank|draft|complete", "application"),
            R("coursework_section", "C", "교과 이수 내역 작성", "Applicant coursework section", "지원서에 내 교과 이수 내역을 입력하고 싶어", "I need to enter my coursework in the admission application", "성적표 상태와 구분되는 지원자 입력 교과 내역을 직접 저장", "Save applicant-entered coursework separately from official transcript status", "prospective applicant", "application coursework record", "blank|draft|complete", "application"),
            R("personal_essay", "C", "개인 에세이 작성", "Personal essay section", "내 입학 지원 에세이를 작성하거나 수정하고 싶어", "I want to draft or revise my personal admission essay", "제출 전 예비 지원자가 에세이 원문을 직접 저장", "Let the prospective applicant save their essay before submission", "prospective applicant", "personal application essay", "blank|draft|complete|locked after submission", "essay"),
            R("institution_supplements", "C", "대학별 추가 문항", "Institution-specific supplements", "선택한 대학의 추가 질문에 답하고 싶어", "I want to answer the supplemental questions for the selected institution", "특정 기관·프로그램에만 적용되는 추가 답변을 지원자가 저장", "Save applicant responses scoped to one institution and program", "prospective applicant", "institution-specific supplement response", "not started|draft|complete", "supplement"),
            R("recommender_invitation", "C", "추천인 초대", "Recommender invitation", "이 지원서에 추천인을 초대하는 화면을 열어 줘", "Open the screen to invite a recommender to this application", "추천인 이메일과 역할을 확인한 뒤 지원자가 초대를 전송", "Have the applicant send the invitation after confirming recommender and role", "prospective applicant", "application recommender invitation", "draft|ready to send|awaiting confirmation", "recommender"),
            R("recommender_assignment", "C", "추천서 대학 배정", "Recommender assignment", "초대한 추천인을 특정 대학 지원서에 배정하고 싶어", "I want to assign an invited recommender to a specific institution application", "기존 추천인을 정확한 기관 지원 건에 사용자가 연결", "Let the applicant link an existing recommender to the correct application", "prospective applicant", "recommender-to-application assignment", "unassigned|eligible|awaiting confirmation", "recommender"),
            R("ferpa_authorization", "C", "FERPA 권한 포기 및 동의", "FERPA authorization and waiver", "추천서 관련 FERPA 동의와 권리 포기를 직접 선택하려고 해", "I need to make my own FERPA authorization and waiver choice", "법적 의미를 대신 판단하지 않고 지원자가 동의 선택을 최종 확인", "Present the choice without legal interpretation and require applicant confirmation", "prospective applicant", "FERPA authorization record", "not answered|choice selected|awaiting signature", "recommender|authorization"),
            R("transcript_status", "S", "성적표 접수 상태", "Transcript receipt status", "대학별로 내 성적표가 접수되었는지 확인하고 싶어", "Check whether my transcript has been received for each application", "공식 성적표의 요청·발송·접수 상태를 지원자 입력 교과와 분리해 조회", "View official transcript delivery separately from self-reported coursework", "prospective applicant|applicant counselor", "official transcript delivery record", "requested|sent|received|missing", "transcript"),
            R("fee_waiver_request", "C", "지원 수수료 면제 요청", "Application fee waiver request", "지원 수수료 면제 자격을 확인하고 요청을 제출하고 싶어", "I want to review eligibility and submit an application fee waiver request", "면제 기준을 안내하고 예비 지원자가 요청 또는 증빙을 최종 제출", "Let the applicant finally submit the waiver request or evidence", "prospective applicant", "application fee waiver request", "not requested|eligible|evidence ready|awaiting confirmation", "fee"),
            R("application_preview", "S", "지원서 제출 전 미리보기", "Pre-submission application preview", "제출하기 전에 대학에 전달될 지원서 전체를 보고 싶어", "Show the complete application as the institution will receive it", "제출 동작과 분리해 지원 항목·문서·선택을 읽기 전용으로 검토", "Review application fields, documents, and choices separately from submit", "prospective applicant", "rendered application preview", "incomplete|preview available|validation warning", "submission"),
            R("application_submission", "C", "입학 지원서 제출", "Admission application submission", "검토를 마친 지원서를 선택한 대학에 제출하려고 해", "I want to submit the reviewed application to the selected institution", "기관·프로그램·학기·비용을 확인하고 지원자가 최종 제출", "Require the applicant to confirm institution, program, term, and fee before submit", "prospective applicant", "completed institution application", "ready|fee resolved|awaiting confirmation", "submission"),
            R("submission_checklist_status", "S", "제출 후 지원 체크리스트", "Post-submission application checklist", "제출한 지원서의 필수 항목 체크리스트를 확인하고 싶어", "Show the required-item checklist for my submitted application", "제출 건별 완료·대기·누락 항목을 변경 없이 조회", "View completed, pending, and missing items for one submitted application", "prospective applicant", "submitted application checklist", "complete|pending|incomplete", "status"),
            R("missing_item_notice", "S", "지원 서류 누락 안내", "Missing application item notice", "대학이 누락되었다고 표시한 서류가 무엇인지 보고 싶어", "Tell me which item the institution marked as missing", "기관이 발행한 누락 통지와 해당 지원 건을 읽기 전용으로 확인", "Inspect the institution-issued notice for the exact application", "prospective applicant|applicant counselor", "missing-item notice", "open|resolved|deadline approaching", "status"),
            R("admission_decision_view", "S", "입학 결정 보기", "Admission decision view", "내 지원서에 공개된 입학 결정을 확인하고 싶어", "I want to view the admission decision released for my application", "정확한 기관·프로그램의 공개된 결정을 응답 동작과 분리해 열람", "View the released decision separately from any applicant response", "prospective applicant", "released admission decision", "not released|released|viewed", "decision"),
            R("waitlist_response", "C", "대기자 명단 응답", "Wait-list response", "대기자 명단 제안을 수락하거나 거절하는 화면으로 가고 싶어", "Take me to accept or decline the wait-list offer", "기관과 응답 기한을 확인한 뒤 지원자가 대기 의사를 최종 제출", "Require the applicant to confirm institution and deadline before responding", "prospective applicant", "admission wait-list offer", "offered|response due|awaiting confirmation", "decision"),
            R("enrollment_deposit_handoff", "C", "등록 예치금 납부 인계", "Enrollment deposit handoff", "합격한 대학의 공식 등록 예치금 단계로 이동하고 싶어", "Take me to the official enrollment-deposit step for the admitted institution", "입학 결정과 기관을 확인하고 결제 소유자에게 안전하게 인계하며 자동 결제하지 않음", "Verify the admission and institution, then hand off without paying automatically", "prospective applicant|authorized payer", "admitted-offer enrollment deposit", "admitted|deposit due|handoff ready", "decision|deposit"),
        ),
    ),
    D(
        "social_platform_account_appeals",
        "소셜 플랫폼 제재 및 이의제기",
        "Social-platform enforcement and appeals",
        "identified social platform, account owner, authored content, enforcement notice, provider region, and appeal lane",
        "do not route reports about another user, generic sign-in recovery, community moderation, or ordinary content publishing into an owner enforcement appeal",
        "account.entry",
        "account|violation|restriction|appeal|copyright",
        "account|authentication|privacy|content|community_meetup",
        "platform account owner|authored-content owner|authorized account representative",
        "platform account|authored content|enforcement notice|restriction or strike|identity evidence|appeal|restoration or deactivation record",
        "clear|notice issued|content removed|limited|locked|suspended|appeal eligible|under review|restored|denied|deactivated",
        (
            R("account_status", "S", "플랫폼 계정 제재 상태", "Platform account enforcement status", "내 소셜 계정에 현재 적용된 제재 상태를 확인하고 싶어", "Show the current enforcement state applied to my social account", "계정 소유자가 활성·제한·잠금·정지 상태를 변경 없이 확인", "Let the owner inspect active, limited, locked, or suspended state", "platform account owner|authorized account representative", "platform account enforcement record", "clear|limited|locked|suspended", "status"),
            R("violation_history", "S", "계정 위반 및 경고 이력", "Account violation and warning history", "내 계정에 기록된 위반과 경고 이력을 보고 싶어", "I want to view violations and warnings recorded on my account", "계정별 정책 위반·경고·스트라이크 기록을 읽기 전용으로 열람", "View policy violations, warnings, and strikes without mutation", "platform account owner|authorized account representative", "account violation history", "open|expired|resolved|active strike", "enforcement"),
            R("content_removal_notice", "S", "콘텐츠 삭제 통지", "Content removal notice", "내 게시물이 삭제된 이유와 적용 정책을 확인하고 싶어", "Show why my authored post was removed and which policy applied", "작성자 소유 콘텐츠의 삭제 통지와 이의 가능 기한을 확인", "Inspect the removal notice and appeal deadline for authored content", "authored-content owner|platform account owner", "authored-content removal notice", "issued|viewed|appeal window open|expired", "content"),
            R("reach_label_status", "S", "콘텐츠 도달 제한 라벨", "Content reach restriction label", "내 콘텐츠에 노출 제한 라벨이 붙었는지 확인하고 싶어", "Check whether a reach restriction label applies to my content", "삭제와 구분하여 추천·노출 제한의 사유와 상태를 열람", "View recommendation or reach limits separately from removal", "authored-content owner|platform account owner", "authored-content reach label", "none|limited|reviewable|expired", "content"),
            R("feature_restriction_status", "S", "계정 기능 제한 상태", "Account feature restriction status", "내 계정에서 제한된 기능과 해제 예정일을 보고 싶어", "Show which account features are restricted and when review is due", "게시·메시지·수익화 등 기능별 제한을 계정 정지와 분리해 조회", "Inspect per-feature restrictions separately from suspension", "platform account owner|authorized account representative", "account feature restriction", "active|temporary|review pending|lifted", "restriction"),
            R("identity_challenge_requirements", "S", "잠금 계정 본인확인 요건", "Locked-account identity challenge requirements", "잠긴 계정을 확인하려면 어떤 본인확인이 필요한지 알고 싶어", "Tell me what identity challenge is required for my locked account", "공식 제공자가 요구하는 증빙 유형과 제출 범위를 사전에 검토", "Review provider-required evidence types before any disclosure", "platform account owner", "locked-account identity challenge", "required|incomplete|accepted|failed", "identity"),
            R("locked_account_verification", "C", "잠금 계정 본인확인 제출", "Locked-account verification submission", "잠긴 계정의 본인확인 자료를 제출하는 곳으로 안내해 줘", "Guide me to submit identity evidence for my locked account", "민감한 신원 자료 범위를 확인하고 계정 소유자가 직접 제출", "Require the account owner to submit sensitive identity evidence personally", "platform account owner", "locked-account identity evidence", "challenge open|evidence ready|awaiting confirmation", "identity"),
            R("suspension_status", "S", "계정 정지 상태 및 사유", "Account suspension status and reason", "내 계정이 정지된 사유와 현재 상태를 확인하고 싶어", "I need to inspect the reason and current state of my account suspension", "제공자 제재 통지의 사유·기간·이의 경로를 읽기 전용으로 확인", "View provider-stated reason, duration, and appeal route", "platform account owner|authorized account representative", "account suspension notice", "suspended|temporary|permanent|review pending", "suspension"),
            R("appeal_eligibility", "S", "제재 이의제기 자격", "Enforcement appeal eligibility", "이 계정 제재가 이의제기 가능한지 확인하고 싶어", "Check whether this account enforcement action is eligible for appeal", "정확한 통지·기한·제공자 경로에 따른 이의 가능 상태를 조회", "Inspect appeal availability for the exact notice, deadline, and provider", "platform account owner|authored-content owner", "enforcement appeal eligibility record", "eligible|not eligible|deadline passed|already appealed", "appeal"),
            R("appeal_evidence", "C", "제재 이의 증빙 제출", "Enforcement appeal evidence submission", "계정 제재 이의에 필요한 설명과 증빙을 제출하려고 해", "I want to submit explanation and evidence for my enforcement appeal", "계정 또는 작성 콘텐츠와 연결된 이의 자료를 소유자가 직접 제출", "Let the owner submit appeal evidence tied to the exact account or content", "platform account owner|authored-content owner", "enforcement appeal evidence", "draft|attachment ready|awaiting confirmation", "appeal"),
            R("appeal_submission", "C", "계정 제재 이의제기 제출", "Account enforcement appeal submission", "검토한 계정 제재 이의제기를 최종 제출하고 싶어", "I want to submit the reviewed appeal against my account enforcement", "대상 통지와 진술을 확인한 뒤 사용자가 공식 제공자에게 이의를 제출", "Require the user to confirm notice and statement before official submission", "platform account owner|authorized account representative", "account enforcement appeal", "eligible|reviewed|awaiting confirmation", "appeal"),
            R("appeal_status", "S", "제재 이의제기 진행 상태", "Enforcement appeal status", "제출한 제재 이의가 검토 중인지 확인하고 싶어", "Check whether my submitted enforcement appeal is under review", "제공자별 이의 접수·검토·추가자료 상태를 변경 없이 조회", "View provider-scoped receipt, review, and evidence-request states", "platform account owner|authored-content owner", "submitted enforcement appeal", "received|under review|more information required|closed", "appeal"),
            R("appeal_result", "S", "제재 이의제기 결정", "Enforcement appeal result", "내 제재 이의제기의 최종 결정과 복구 범위를 보고 싶어", "Show the final appeal decision and any restoration scope", "승인·기각·부분 복구 결정을 후속 동작과 분리해 열람", "View upheld, denied, or partial-restoration result separately from action", "platform account owner|authored-content owner", "appeal decision record", "upheld|denied|partially restored|closed", "appeal"),
            R("copyright_counter_notice", "C", "저작권 삭제 반론 통지", "Copyright counter-notice path", "내 콘텐츠의 저작권 삭제에 반론 통지를 제출하려고 해", "I want to submit a counter-notice for copyright removal of my content", "법적 진술의 의미를 대신 판단하지 않고 작성자가 직접 반론을 제출", "Present the official counter path without legal judgment and require user submission", "authored-content owner", "copyright removal counter-notice", "eligible|statement ready|awaiting confirmation", "copyright"),
            R("authenticity_route", "C", "사칭 및 진정성 검토 경로", "Impersonation and authenticity review route", "내 계정의 사칭 또는 진정성 문제를 검토 요청하려고 해", "I want to request review of an impersonation or authenticity issue affecting my account", "다른 사용자를 일반 신고하는 대신 소유 계정의 진정성 이의를 제출", "Submit an owner-account authenticity challenge, not a report about another user", "platform account owner", "owner-account authenticity challenge", "challenge available|evidence ready|awaiting confirmation", "identity"),
            R("underage_appeal_evidence", "C", "연령 제재 이의 증빙", "Age-enforcement appeal evidence", "연령 제한 제재에 필요한 나이 증빙을 직접 제출하고 싶어", "I need to submit age evidence for an age-enforcement appeal", "제공자별 연령 이의 경로에서 민감한 증빙을 사용자가 직접 제공", "Require personal submission of sensitive evidence in the provider's age appeal lane", "platform account owner|authorized guardian", "age-enforcement identity evidence", "appeal open|evidence selected|awaiting confirmation", "age"),
            R("restricted_data_request", "C", "제한 계정 데이터 요청", "Restricted-account data request", "제한된 계정에서 내 데이터 사본을 요청하고 싶어", "I want to request a copy of my data from the restricted account", "계정 소유권과 제공자 경로를 확인한 뒤 사용자가 데이터 요청을 제출", "Let the owner submit a provider-scoped data request after identity checks", "platform account owner", "restricted-account data archive request", "available|identity required|awaiting confirmation", "data"),
            R("remediation_steps", "S", "계정 제재 해소 조치", "Account enforcement remediation steps", "계정 제한을 해소하기 위해 제공자가 요구한 조치를 보고 싶어", "Show the remediation steps required by the provider for my account restriction", "제공자가 명시한 교육·수정·대기 요건을 추정 없이 확인", "View provider-stated training, correction, or waiting requirements", "platform account owner|authorized account representative", "account remediation requirement", "not started|in progress|complete|not offered", "restriction"),
            R("restoration_status", "S", "계정 및 콘텐츠 복구 상태", "Account and content restoration status", "이의 결정 뒤 계정이나 콘텐츠가 복구되었는지 확인하고 싶어", "Check whether my account or authored content was restored after the decision", "결정 결과와 실제 접근·콘텐츠 복구 상태를 별도로 조회", "Inspect actual access or content restoration separately from the decision", "platform account owner|authored-content owner", "post-appeal restoration record", "pending|partially restored|restored|not restored", "status"),
            R("post_enforcement_deactivation", "C", "제재 후 계정 비활성화", "Post-enforcement account deactivation", "제재 중인 내 계정을 비활성화하는 마지막 화면으로 가고 싶어", "Take me to the final deactivation control for my enforced account", "데이터 접근과 복구 가능성 영향을 확인하고 소유자가 직접 비활성화", "Require owner confirmation after explaining data-access and restoration effects", "platform account owner", "enforced platform account", "deactivation available|impact reviewed|awaiting confirmation", "deactivation"),
        ),
    ),
    D(
        "consumer_debt_collection_services",
        "소비자 채권추심 대응",
        "Consumer debt-collection response",
        "identified consumer, collector, claimed debt, governing U.S. state or Korean statutory branch, notice date, and response channel",
        "never declare a debt legally valid and do not merge credit-file disputes, ordinary loan servicing, estate administration, or collector-side casework",
        "finance.accounts",
        "debt|validation|dispute|contact|settlement",
        "consumer_credit_reporting_services|mortgage_origination_servicing_ops|retail_banking|estate_probate_administration|legal",
        "consumer recipient|consumer-authorized advocate|consumer counsel",
        "claimed consumer debt|validation notice|creditor itemization|dispute|communication restriction|settlement or payment proposal|complaint or lawsuit notice",
        "notice received|validation window open|disputed|verification pending|verified by collector|offer pending|paid record|complaint submitted|litigation handoff",
        (
            R("collector_identity", "S", "추심업체 신원 확인", "Debt collector identity", "연락한 추심업체의 이름과 공식 연락처를 확인하고 싶어", "I need to verify the identity and official contact details of the collector", "채무 유효성을 판단하지 않고 통지에 표시된 추심 주체를 확인", "Identify the collector shown on the notice without validating the debt", "consumer recipient|consumer-authorized advocate", "collector identity record", "identified|information incomplete|unverified contact", "notice"),
            R("validation_notice", "S", "채무 확인 통지 보기", "Debt validation notice", "받은 채무 확인 통지의 필수 내용을 보고 싶어", "Show the required information in the debt validation notice I received", "채권자·금액·권리·기한 정보를 법적 결론 없이 열람", "Review creditor, amount, rights, and dates without a legal conclusion", "consumer recipient|consumer-authorized advocate", "debt validation notice", "received|incomplete|window open|expired", "notice"),
            R("amount_itemization", "S", "추심 금액 세부내역", "Claimed debt amount itemization", "현재 요구 금액의 원금과 이자 및 수수료 내역을 확인하고 싶어", "I want to inspect principal, interest, fees, and payments in the claimed amount", "추심 통지의 금액 구성과 기준일을 변경 없이 검토", "Review the notice-date amount breakdown without accepting liability", "consumer recipient|consumer-authorized advocate", "claimed debt itemization", "itemized|incomplete|changed since notice", "notice"),
            R("original_creditor_request", "C", "원채권자 정보 요청", "Original creditor information request", "원래 채권자 정보를 공식적으로 요청하려고 해", "I want to request information about the original creditor", "정확한 추심 건과 응답 기한을 확인하고 소비자가 요청을 제출", "Let the consumer submit the request for the exact collection matter", "consumer recipient|consumer-authorized advocate", "original-creditor information request", "available|draft|awaiting confirmation", "validation"),
            R("validation_deadline", "S", "채무 확인 및 이의 기한", "Debt validation and dispute deadline", "이 통지에 대응할 수 있는 날짜와 기한을 확인하고 싶어", "Show the response and dispute dates associated with this notice", "통지일과 관할 규칙에 따른 표시 기한을 법률 자문 없이 안내", "Display notice-based dates without presenting legal advice", "consumer recipient|consumer-authorized advocate", "validation response deadline", "open|approaching|passed|uncertain", "validation"),
            R("debt_position_record", "C", "채무 인정 여부 선택 기록", "Consumer debt position record", "이 채무를 인정하는지 여부를 내가 직접 선택하는 화면을 열어 줘", "Open the screen where I make my own choice about recognizing the claimed debt", "에이전트가 유효성을 판단하지 않고 소비자의 선택만 최종 기록", "Record only the consumer's choice; never characterize legal validity", "consumer recipient", "consumer position on claimed debt", "unanswered|choice selected|awaiting confirmation", "validation"),
            R("dispute_draft", "S", "채무 이의제기 초안 검토", "Debt dispute draft review", "제출 전에 채무 이의제기 초안을 검토하고 싶어", "I want to review my debt dispute draft before submission", "추심 건·진술·증빙을 제출 동작과 분리해 읽기 전용으로 확인", "Review matter, statement, and evidence separately from submission", "consumer recipient|consumer-authorized advocate", "consumer debt dispute draft", "draft|incomplete|ready", "dispute"),
            R("dispute_submission", "C", "채무 이의제기 제출", "Debt dispute submission", "검토한 채무 이의제기를 추심업체에 제출하려고 해", "I want to submit the reviewed dispute to the collector", "정확한 채무·추심업체·기한을 확인하고 소비자가 이의를 제출", "Require consumer confirmation of debt, collector, and deadline before submit", "consumer recipient|consumer-authorized advocate", "consumer debt dispute", "ready|channel selected|awaiting confirmation", "dispute"),
            R("verification_status", "S", "채무 검증 진행 상태", "Debt verification status", "이의를 낸 뒤 추심업체의 검증 상태를 확인하고 싶어", "Check the collector's verification state after my dispute", "검증 요청의 접수·보류·응답 상태를 법적 유효성 판단 없이 조회", "View receipt, pause, and response states without judging legal validity", "consumer recipient|consumer-authorized advocate", "disputed-debt verification record", "requested|collection paused|response received|unresolved", "dispute"),
            R("contact_channel_preferences", "C", "추심 연락 채널 설정", "Collector contact channel preferences", "추심 연락을 받을 채널을 내가 선택하고 싶어", "I want to choose which contact channels the collector may use", "관할 규칙과 제공 옵션 범위에서 소비자가 연락 채널을 지정", "Let the consumer set available channels within the applicable rules", "consumer recipient", "debt-collection communication preference", "current|edited|awaiting confirmation", "contact"),
            R("contact_frequency_request", "C", "추심 연락 빈도 제한 요청", "Collector contact frequency request", "추심 연락 빈도를 제한해 달라는 요청을 제출하고 싶어", "I want to submit a request limiting collection contact frequency", "법적 효과를 보장하지 않고 소비자가 빈도 요청을 공식 채널로 제출", "Submit the consumer's frequency request without promising legal effect", "consumer recipient|consumer-authorized advocate", "collection contact-frequency request", "draft|channel verified|awaiting confirmation", "contact"),
            R("stop_contact_request", "C", "추심 연락 중단 요청", "Debt collection stop-contact request", "추심업체에 연락 중단 요청을 보내는 곳으로 안내해 줘", "Guide me to send a stop-contact request to the collector", "소송 통지 등 예외 가능성을 알리고 소비자가 요청을 최종 제출", "Explain possible notice exceptions and require consumer submission", "consumer recipient|consumer-authorized advocate", "collection stop-contact request", "draft|delivery method selected|awaiting confirmation", "contact"),
            R("payment_plan_offer", "S", "추심 분할상환 제안 보기", "Collection payment-plan offer", "추심업체가 제안한 분할상환 조건을 확인하고 싶어", "Show the payment-plan terms offered by the collector", "금액·회차·기한을 수락 또는 결제 동작과 분리해 열람", "Review amount, installments, and dates separately from acceptance", "consumer recipient|consumer-authorized advocate", "collector payment-plan offer", "offered|expires|withdrawn", "offer"),
            R("settlement_offer", "S", "추심 합의 제안 보기", "Debt settlement offer", "추심업체가 제시한 합의 금액과 조건을 보고 싶어", "I want to view the settlement amount and conditions offered by the collector", "세금·법률 효과를 단정하지 않고 공식 제안 내용을 열람", "View the official offer without asserting tax or legal consequences", "consumer recipient|consumer-authorized advocate", "collector settlement offer", "offered|expires|withdrawn", "offer"),
            R("offer_response", "C", "상환 또는 합의 제안 응답", "Payment or settlement offer response", "제시된 상환 또는 합의 조건에 응답하는 화면으로 가고 싶어", "Take me to respond to the offered payment or settlement terms", "조건·채권자·금액을 확인하고 소비자가 수락 또는 거절을 제출", "Require the consumer to confirm terms, creditor, and amount before responding", "consumer recipient", "collection offer response", "offer open|response selected|awaiting confirmation", "offer"),
            R("collection_payment", "C", "추심 채무 결제", "Collection debt payment", "이 추심 건의 결제를 최종 확인하는 곳으로 안내해 줘", "Guide me to the final payment confirmation for this collection matter", "추심 주체·금액·결제 수단을 검증하고 사용자가 직접 결제", "Verify collector, amount, and method and leave payment to the consumer", "consumer recipient|authorized payer", "collection payment instruction", "amount confirmed|method selected|awaiting confirmation", "payment"),
            R("payment_record", "S", "추심 결제 기록", "Collection payment record", "이 추심 건에 기록된 이전 결제를 확인하고 싶어", "Show prior payments recorded for this collection matter", "영수증·처리일·잔액 표시를 추가 결제와 분리해 열람", "View receipt, posting date, and displayed balance separately from payment", "consumer recipient|consumer-authorized advocate", "collection payment history", "pending|posted|reversed|disputed", "payment"),
            R("complaint_submission", "C", "채권추심 민원 제출", "Debt collection complaint submission", "추심 행위에 대한 공식 민원을 제출하려고 해", "I want to submit an official complaint about collection conduct", "기관·업체·사실관계를 확인하고 소비자가 민원을 최종 제출", "Require the consumer to confirm agency, company, and facts before submit", "consumer recipient|consumer-authorized advocate", "debt-collection complaint", "draft|evidence ready|awaiting confirmation", "complaint"),
            R("lawsuit_notice", "S", "추심 소송 통지 보기", "Debt collection lawsuit notice", "받은 추심 소송 통지의 사건과 기한을 확인하고 싶어", "I need to inspect the case and dates on a debt collection lawsuit notice", "법률 판단 없이 통지의 법원·사건번호·표시 기한을 정확히 열람", "Display court, case number, and stated dates without legal judgment", "consumer recipient|consumer counsel", "debt-collection lawsuit notice", "served|response date shown|judgment entered|uncertain", "legal"),
            R("legal_help_handoff", "S", "채권추심 법률지원 연결", "Debt collection legal-help handoff", "이 추심 또는 소송 건에 맞는 공식 법률지원 경로를 찾고 싶어", "Find an official legal-help route for this collection or lawsuit matter", "관할과 사건 상태를 바탕으로 외부 법률지원 목적지만 안내", "Route to jurisdiction-appropriate legal help without providing legal advice", "consumer recipient|consumer-authorized advocate", "official debt legal-help directory", "available|eligibility unknown|urgent deadline", "legal"),
        ),
    ),
    D(
        "rental_vehicle_trip_services",
        "렌터카 여행 서비스",
        "Rental-vehicle trip services",
        "identified rental provider, consumer renter, reservation, pickup country, driver eligibility, and active rental agreement",
        "do not route ride hailing, privately owned connected vehicles, fleet compliance, or property rental through a consumer vehicle reservation",
        "travel.bookings",
        "rental|driver|protection|return|receipt",
        "ride_hailing_extended|automotive_vehicle|fleet_driver_compliance|travel|mobility_delivery",
        "consumer renter|authorized additional driver|reservation payer",
        "consumer rental reservation|driver|vehicle class|rate and protection|rental agreement|active rental|return closeout",
        "searching|held|confirmed|checked in|picked up|active|extended|incident open|returned|charge pending|closed",
        (
            R("location_date_search", "S", "렌터카 지점 및 날짜 검색", "Rental location and date search", "차량을 빌릴 지점과 날짜에 가능한 렌터카를 찾고 싶어", "Find rental availability for my pickup location and dates", "예약을 만들지 않고 지점·대여기간별 이용 가능 범위를 조회", "Search location and date availability without creating a reservation", "consumer renter|reservation payer", "rental availability query", "available|limited|sold out", "search"),
            R("vehicle_class_review", "S", "렌터카 등급 비교", "Rental vehicle class review", "이 예약에 가능한 차량 등급과 특징을 비교하고 싶어", "Compare vehicle classes and features available for this rental", "특정 실차 배정을 보장하지 않고 등급별 좌석·적재·동력 정보를 비교", "Compare class attributes without promising a specific vehicle", "consumer renter|authorized additional driver", "rental vehicle class offering", "available|on request|unavailable", "reservation"),
            R("rate_terms_review", "S", "렌터카 요금 조건 검토", "Rental rate terms review", "예약 전 기본 요금과 세금 및 주행 조건을 확인하고 싶어", "Show the base rate, taxes, and mileage terms before booking", "결제 동작과 분리해 날짜·지점별 요금 조건을 읽기 전용으로 검토", "Review date-and-location rate terms separately from booking", "consumer renter|reservation payer", "rental rate quote", "quoted|expires|changed", "reservation"),
            R("protection_selection", "C", "렌터카 보호상품 선택", "Rental protection selection", "이 렌탈에 적용할 보호상품을 내가 직접 선택하고 싶어", "I want to make my own protection-product choice for this rental", "보장 범위를 단정하지 않고 선택과 거절을 사용자가 최종 확인", "Present provider terms without coverage advice and require the renter's choice", "consumer renter|reservation payer", "rental protection choice", "not selected|option selected|awaiting confirmation", "protection"),
            R("driver_requirements", "S", "렌터카 운전자 요건", "Rental driver requirements", "픽업 지점에서 필요한 나이와 면허 및 결제 요건을 확인하고 싶어", "Show age, license, and payment requirements for the pickup location", "지점 관할과 운전자 유형에 따른 제공자 요건을 정보로 열람", "Review provider requirements scoped to location and driver type", "consumer renter|authorized additional driver", "rental driver eligibility requirement", "eligible|document needed|restriction applies", "driver"),
            R("reservation_booking", "C", "렌터카 예약 확정", "Rental reservation booking", "선택한 차량 등급과 요금으로 예약을 확정하는 곳으로 가고 싶어", "Take me to confirm the selected rental class and rate", "지점·날짜·운전자·요금·보호 선택을 검토하고 사용자가 예약", "Require final renter review of location, dates, driver, price, and protection", "consumer renter|reservation payer", "consumer rental reservation", "quote valid|details complete|awaiting confirmation", "reservation"),
            R("reservation_lookup", "S", "렌터카 예약 조회", "Rental reservation lookup", "확정된 렌터카 예약의 번호와 세부정보를 보고 싶어", "Show the number and details of my confirmed rental reservation", "예약자와 확인번호에 맞는 지점·시간·등급을 변경 없이 조회", "View location, time, and class for the identified reservation", "consumer renter|reservation payer", "confirmed rental reservation", "confirmed|modified|cancelled", "reservation"),
            R("reservation_modification", "C", "렌터카 예약 변경", "Rental reservation modification", "기존 렌터카 예약의 날짜나 지점을 변경하고 싶어", "I want to change dates or location on my existing rental reservation", "변경 요금과 이용 가능성을 확인하고 사용자가 예약 수정을 확정", "Have the renter confirm availability and revised price before modification", "consumer renter|reservation payer", "confirmed rental reservation", "change eligible|repriced|awaiting confirmation", "reservation"),
            R("reservation_cancellation", "C", "렌터카 예약 취소", "Rental reservation cancellation", "이 렌터카 예약을 취소하는 마지막 화면을 열어 줘", "Open the final cancellation screen for this rental reservation", "정확한 예약과 취소 조건을 확인하고 사용자가 직접 취소", "Require the renter to confirm the reservation and terms before cancellation", "consumer renter|reservation payer", "confirmed rental reservation", "cancel eligible|fee shown|awaiting confirmation", "reservation"),
            R("online_checkin", "C", "렌터카 온라인 체크인", "Rental online check-in", "픽업 전에 운전자 정보를 제출하고 온라인 체크인을 완료하고 싶어", "I want to submit driver details and complete rental online check-in", "면허·운전자·예약 정보를 검토하고 사용자가 픽업 준비 제출", "Let the renter submit pickup preparation after reviewing driver details", "consumer renter|authorized additional driver", "rental online check-in record", "available|details ready|awaiting confirmation", "pickup"),
            R("pickup_instructions", "S", "렌터카 픽업 안내", "Rental pickup instructions", "예약 차량을 어디서 어떻게 인수하는지 확인하고 싶어", "Show where and how to collect the reserved rental vehicle", "지점·영업시간·셔틀·필요 문서를 예약에 맞춰 조회", "View reservation-scoped location, hours, shuttle, and document instructions", "consumer renter|authorized additional driver", "rental pickup instruction", "available|after-hours|counter required", "pickup"),
            R("rental_agreement", "S", "렌터카 계약서 보기", "Rental agreement view", "인수한 차량의 렌탈 계약 조건을 확인하고 싶어", "I want to inspect the agreement terms for the vehicle I picked up", "계약 번호·운전자·차량·반납 조건을 변경 동작과 분리해 열람", "Review agreement, driver, vehicle, and return terms without mutation", "consumer renter|authorized additional driver", "executed rental agreement", "active|amended|closed", "active"),
            R("active_rental_status", "S", "이용 중 렌터카 상태", "Active rental status", "현재 이용 중인 렌탈의 반납 시각과 계약 상태를 보고 싶어", "Show return time and agreement state for my active rental", "활성 계약의 차량·기간·현재 상태를 변경 없이 확인", "Inspect vehicle, rental period, and current active state", "consumer renter|authorized additional driver", "active consumer rental", "active|extension pending|return due|incident hold", "active"),
            R("rental_extension", "C", "렌터카 대여 연장", "Rental extension request", "현재 렌터카의 반납 시간을 연장하는 화면으로 가고 싶어", "Take me to request more time on my active rental", "이용 가능성·추가요금·새 반납시각을 확인하고 사용자가 연장", "Require renter confirmation of availability, price, and new return time", "consumer renter|reservation payer", "active rental period", "extension eligible|repriced|awaiting confirmation", "active"),
            R("roadside_help", "S", "렌터카 긴급출동 연결", "Rental roadside assistance", "이용 중인 렌터카의 공식 긴급출동 연락 경로를 찾고 싶어", "Find the provider's official roadside-help route for my active rental", "안전한 위치 확보를 우선 안내하고 정확한 계약의 지원 채널을 표시", "Prioritize immediate safety and show the channel for the exact agreement", "consumer renter|authorized additional driver", "active-rental roadside support route", "available|location needed|emergency services required", "incident"),
            R("accident_damage_report", "C", "렌터카 사고 및 손상 신고", "Rental accident and damage report", "이 렌터카의 사고나 손상을 제공자에게 신고하려고 해", "I want to report an accident or damage involving this rental vehicle", "긴급 상황은 현지 구조기관으로 분리하고 사용자가 계약별 사고 보고 제출", "Separate emergencies and require the renter to submit the agreement-scoped report", "consumer renter|authorized additional driver", "rental accident or damage report", "safe to report|evidence ready|awaiting confirmation", "incident"),
            R("return_instructions", "S", "렌터카 반납 위치 및 연료 안내", "Rental return location and fuel terms", "렌터카 반납 장소와 연료 또는 충전 조건을 확인하고 싶어", "Show the return location and fuel or charging terms for this rental", "계약별 반납 지점·시간·연료 또는 충전 기준을 조회", "View agreement-scoped return place, time, and energy terms", "consumer renter|authorized additional driver", "rental return instruction", "return due|after-hours option|different-location restriction", "return"),
            R("return_confirmation", "S", "렌터카 반납 확인", "Rental return confirmation", "반납한 차량이 제공자에게 접수되었는지 확인하고 싶어", "Check whether the provider recorded my rental vehicle as returned", "반납 시각·주행·연료·검사 대기 상태를 추가 동작 없이 조회", "View return time, mileage, energy, and inspection-pending state", "consumer renter|reservation payer", "rental return closeout record", "returned|inspection pending|closed|exception", "return"),
            R("receipt_deposit_status", "S", "렌터카 영수증 및 보증금 상태", "Rental receipt and deposit status", "최종 영수증과 카드 보증금 해제 상태를 확인하고 싶어", "Show my final rental receipt and card-deposit release state", "하나의 반납 정산 기록에서 청구 내역과 승인 보류 해제를 열람", "View charges and authorization-hold release in the rental closeout record", "consumer renter|reservation payer", "rental closeout settlement", "receipt issued|deposit pending|released|adjusted", "receipt"),
            R("billing_question", "C", "렌터카 청구 문의 제출", "Rental billing question submission", "렌터카 영수증의 특정 청구에 대해 문의를 제출하고 싶어", "I want to submit a question about a specific charge on my rental receipt", "환불을 자동 요구하지 않고 계약·영수증·청구 항목을 지정해 사용자가 문의", "Let the renter submit a question tied to the exact agreement and charge", "consumer renter|reservation payer", "rental billing inquiry", "charge selected|statement ready|awaiting confirmation", "receipt"),
        ),
    ),
    D(
        "airline_passenger_trip_management",
        "항공 승객 여행 관리",
        "Airline passenger trip management",
        "identified ticketed passenger, airline, ticket number, itinerary, operating jurisdiction, and post-ticket service state",
        "exclude generic flight discovery, existing travel check-in, boarding-pass, seat, basic baggage, booking-change, booking-cancel, and flight-status terminals; exclude crew, airport, and cargo operations",
        "travel.bookings",
        "ticket|document|baggage|disruption|refund",
        "travel|air_travel_planning|airline_crew_operations|airport_airside_operations|air_traffic_control_ops",
        "ticketed passenger|passenger-authorized trip manager|authorized payer",
        "ticketed itinerary|passenger detail|fare rule|travel document readiness|special assistance|paid baggage|disrupted journey|refund or reimbursement case",
        "ticketed|document check pending|assistance requested|bag paid|bag delayed|disrupted|rebook eligible|refund eligible|refund pending|case closed",
        (
            R("ticket_receipt", "S", "항공권 번호 및 영수증", "Air ticket number and receipt", "발권된 여행의 항공권 번호와 영수증을 확인하고 싶어", "Show the ticket number and receipt for my issued itinerary", "예약 변경 화면과 분리해 승객별 발권 및 결제 기록을 열람", "View passenger ticketing and receipt records separately from booking changes", "ticketed passenger|authorized payer", "issued passenger ticket receipt", "issued|exchanged|voided|refunded", "ticket"),
            R("fare_rule_review", "S", "발권 운임 규정 검토", "Ticketed fare rule review", "내 항공권의 변경과 취소 및 환불 규정을 확인하고 싶어", "I need to review change, cancellation, and refund rules for my ticket", "실제 변경·취소 동작 없이 발권 운임의 조건과 제한을 조회", "Inspect ticketed fare conditions without executing a booking action", "ticketed passenger|passenger-authorized trip manager", "ticketed fare-rule record", "applicable|restricted|carrier review required", "ticket"),
            R("passenger_detail_correction", "C", "발권 승객 정보 정정 요청", "Ticketed passenger detail correction", "발권된 여행의 승객 정보 정정을 요청하려고 해", "I want to request correction of passenger details on an issued ticket", "명의 이전과 구분해 허용된 철자·문서정보 정정을 사용자가 요청", "Distinguish corrections from transfer and require the passenger's request", "ticketed passenger|passenger-authorized trip manager", "ticketed passenger identity detail", "correction eligible|documents ready|awaiting confirmation", "passenger"),
            R("travel_document_readiness", "S", "여행 서류 준비 상태", "Travel-document readiness", "이 여정에 필요한 여권과 비자 등 서류 준비 상태를 확인하고 싶어", "Check document readiness for the passport, visa, or entry rules on this itinerary", "노선·국적·환승 조건의 항공사 안내를 확인하되 입국 허가를 보장하지 않음", "Review airline guidance without guaranteeing immigration admissibility", "ticketed passenger|passenger-authorized trip manager", "itinerary travel-document checklist", "not reviewed|information needed|ready by passenger attestation", "document"),
            R("assistance_option_review", "S", "특별지원 옵션 검토", "Special-assistance option review", "이 여정에서 요청할 수 있는 이동 및 탑승 지원을 보고 싶어", "Show mobility and boarding assistance available for this itinerary", "승객 필요와 공항·운항편에 따른 지원 유형 및 사전 기한을 열람", "View assistance types and lead times scoped to passenger and flight", "ticketed passenger|passenger-authorized trip manager", "itinerary special-assistance option set", "available|advance notice required|carrier confirmation needed", "assistance"),
            R("assistance_request", "C", "항공 특별지원 요청", "Airline special-assistance request", "선택한 항공편에 특별지원을 요청하는 화면으로 가고 싶어", "Take me to request special assistance for the selected flight", "민감한 필요 정보 범위를 확인하고 승객 또는 권한자가 지원을 요청", "Require passenger-authorized submission of scoped assistance needs", "ticketed passenger|passenger-authorized trip manager", "passenger special-assistance request", "eligible|need selected|awaiting confirmation", "assistance"),
            R("paid_baggage_eligibility", "S", "유료 수하물 추가 가능 여부", "Paid baggage addition eligibility", "내 항공권에 추가 수하물을 구매할 수 있는지 확인하고 싶어", "Check whether paid baggage can be added to my ticket", "기존 무료 허용량 보기와 구분해 노선별 유료 추가 조건을 조회", "Inspect paid-addition terms separately from the existing allowance view", "ticketed passenger|authorized payer", "ticketed-itinerary paid-baggage offer", "available|sales closed|airport only", "baggage"),
            R("paid_baggage_addition", "C", "유료 수하물 추가", "Paid baggage addition", "이 항공권에 선택한 추가 수하물을 결제하려고 해", "I want to pay for the selected additional baggage on this ticket", "노선·승객·개수·가격을 확인하고 사용자가 추가 수하물을 구매", "Require user confirmation of route, passenger, quantity, and price", "ticketed passenger|authorized payer", "paid baggage ancillary order", "offer valid|quantity selected|awaiting confirmation", "baggage"),
            R("baggage_tracker", "S", "위탁 수하물 추적", "Checked-baggage tracker", "맡긴 수하물이 현재 어디에 있는지 추적하고 싶어", "Track the current handling state of my checked bag", "태그 번호와 운항편에 연결된 인수·탑재·도착 상태를 조회", "View acceptance, loading, and arrival state tied to bag tag and flight", "ticketed passenger|passenger-authorized trip manager", "checked-baggage tracking record", "accepted|loaded|arrived|delivery pending|unknown", "baggage"),
            R("mishandled_baggage_report", "C", "지연 및 파손 수하물 신고", "Mishandled baggage report", "도착하지 않았거나 파손된 수하물을 신고하려고 해", "I want to report a delayed, missing, or damaged checked bag", "태그·항공편·수하물 상태를 확인하고 승객이 공식 보고서를 제출", "Have the passenger submit the report after verifying tag, flight, and condition", "ticketed passenger|passenger-authorized trip manager", "mishandled-baggage report", "reportable|details ready|awaiting confirmation", "baggage"),
            R("same_day_change_eligibility", "S", "당일 항공편 변경 자격", "Same-day flight-change eligibility", "내 발권 항공권이 당일 변경 대상인지 확인하고 싶어", "Check whether my issued ticket is eligible for a same-day change", "기존 예약변경 terminal로 실행을 넘기기 전에 운임·노선별 자격만 조회", "Inspect eligibility before handing execution to the existing booking-change owner", "ticketed passenger|passenger-authorized trip manager", "same-day change eligibility record", "eligible|standby only|not eligible|window closed", "disruption"),
            R("schedule_change_notice", "S", "항공사 일정 변경 통지", "Airline schedule-change notice", "항공사가 보낸 일정 변경 내용과 영향 구간을 보고 싶어", "Show the carrier-issued schedule change and affected itinerary segment", "일반 운항 상태와 구분해 발권 여정에 발행된 변경 통지를 열람", "View a ticket-specific carrier notice separately from generic flight status", "ticketed passenger|passenger-authorized trip manager", "ticketed-itinerary schedule-change notice", "issued|acknowledged|options offered", "disruption"),
            R("disruption_options", "S", "운항중단 대응 옵션", "Flight disruption options", "취소나 큰 지연 뒤 항공사가 제시한 선택지를 보고 싶어", "Show the carrier options offered after cancellation or major delay", "영향받은 발권 여정에 제공된 재예약·크레딧·환불 선택을 비교", "Compare rebooking, credit, and refund options for the disrupted ticket", "ticketed passenger|passenger-authorized trip manager", "disrupted-itinerary option set", "options pending|offered|expired", "disruption"),
            R("disrupted_itinerary_rebook", "C", "운항중단 여정 재예약", "Disrupted-itinerary rebooking", "운항중단으로 제시된 대체 항공편을 선택해 재예약하려고 해", "I want to select and confirm a replacement flight for my disrupted itinerary", "일반 예약변경과 구분해 항공사가 제시한 대체편을 승객이 확정", "Require passenger confirmation of a carrier-offered disruption replacement", "ticketed passenger|passenger-authorized trip manager", "disrupted-itinerary rebooking offer", "offered|selection held|awaiting confirmation", "disruption"),
            R("travel_credit_balance", "S", "항공 여행 크레딧", "Airline travel-credit balance", "취소 또는 변경으로 받은 여행 크레딧의 금액과 만료일을 보고 싶어", "Show the amount and expiry of my airline travel credit", "발행 사유·사용 가능 승객·잔액·만료를 결제와 분리해 조회", "View owner, balance, origin, and expiry separately from redemption", "ticketed passenger|authorized payer", "airline travel-credit record", "active|partially used|expired|restricted", "credit"),
            R("refund_eligibility", "S", "항공권 환불 자격", "Air ticket refund eligibility", "내 발권 여정이 환불 요청 대상인지 확인하고 싶어", "Check whether my issued itinerary is eligible for a refund request", "운임 규정·운항중단·사용 구간을 기준으로 표시된 자격을 정보로 검토", "Review displayed eligibility from fare, disruption, and usage state", "ticketed passenger|authorized payer", "ticket refund eligibility record", "eligible|partially eligible|not eligible|manual review", "refund"),
            R("refund_request", "C", "항공권 환불 요청", "Air ticket refund request", "환불 가능한 항공권의 환불 요청을 제출하려고 해", "I want to submit a refund request for the eligible ticket", "승객·항공권·환불 대상 구간·수단을 확인하고 사용자가 요청", "Require user confirmation of passenger, ticket, segments, and method", "ticketed passenger|authorized payer", "air ticket refund request", "eligible|amount shown|awaiting confirmation", "refund"),
            R("refund_status", "S", "항공권 환불 처리 상태", "Air ticket refund status", "제출한 항공권 환불 요청의 처리 상태를 확인하고 싶어", "Check the processing state of my submitted ticket refund", "요청 접수·심사·지급·거절 상태와 지급 수단을 조회", "View receipt, review, payment, or denial state and destination method", "ticketed passenger|authorized payer", "submitted ticket refund case", "received|under review|approved|paid|denied", "refund"),
            R("expense_reimbursement_claim", "C", "운항중단 비용 보상 청구", "Disruption expense reimbursement claim", "운항중단으로 발생한 적격 비용의 보상을 청구하려고 해", "I want to claim reimbursement for eligible disruption expenses", "관할 권리를 단정하지 않고 영수증과 항공사 기준에 따라 승객이 청구", "Let the passenger submit receipts under carrier rules without legal conclusions", "ticketed passenger|authorized payer", "disruption expense reimbursement claim", "expense documented|claim ready|awaiting confirmation", "reimbursement"),
            R("passenger_complaint", "C", "항공 승객 민원 제출", "Airline passenger complaint", "이 발권 여정의 서비스 문제에 대해 공식 민원을 제출하고 싶어", "I want to submit an official complaint about service on this ticketed trip", "항공사·항공권·구간·사실관계를 확인하고 승객이 민원을 제출", "Require the passenger to confirm carrier, ticket, segment, and facts", "ticketed passenger|passenger-authorized trip manager", "ticketed-journey passenger complaint", "draft|evidence ready|awaiting confirmation", "complaint"),
        ),
    ),
    D(
        "home_internet_tv_service",
        "가정용 인터넷 및 TV 서비스",
        "Home internet and television service",
        "identified residential provider, service address, account holder, active line, equipment inventory, and contract jurisdiction",
        "do not route mobile SIM, generic utility billing, standalone streaming subscriptions, or technician-side field work into this residential-line lifecycle",
        "telecom.hub",
        "address|plan|outage|cancellation|equipment return",
        "telecom|android_connectivity|utilities|subscription|telecom_field_service_ops",
        "residential account holder|account-authorized household member|authorized payer",
        "residential service address|internet or TV plan|installation appointment|provider equipment|active line|diagnostic case|bill and contract|service closeout",
        "serviceable|ordered|installation pending|active|outage|diagnosing|appointment pending|suspended|move pending|cancelling|return pending|closed",
        (
            R("address_serviceability", "S", "서비스 주소 설치 가능 조회", "Service-address availability", "우리 집 주소에 인터넷이나 TV 설치가 가능한지 확인하고 싶어", "Check whether internet or TV service is available at my home address", "주거 주소와 제공자 망에 따른 설치 가능 범위를 주문 없이 조회", "Inspect provider serviceability for the residence without ordering", "residential account holder|account-authorized household member", "residential serviceability record", "serviceable|limited|not serviceable|manual check", "order"),
            R("plan_speed_review", "S", "인터넷 및 TV 요금제 비교", "Internet and TV plan review", "내 주소에서 가능한 속도와 TV 요금제를 비교하고 싶어", "Compare internet speeds and TV plans available at my address", "주소별 속도 등급·채널·계약 조건을 변경 없이 검토", "Review address-scoped speed, channel, and contract options", "residential account holder|authorized payer", "residential plan offering", "available|promotion active|contract required", "order"),
            R("service_order", "C", "가정용 통신 서비스 주문", "Residential service order", "선택한 인터넷 또는 TV 서비스를 우리 집에 주문하려고 해", "I want to order the selected internet or TV service for my home", "주소·요금제·계약·설치비를 확인하고 계정 소유자가 주문", "Require the account holder to confirm address, plan, term, and fees", "residential account holder|authorized payer", "residential internet or TV order", "serviceable|plan selected|awaiting confirmation", "order"),
            R("order_status", "S", "인터넷 및 TV 주문 상태", "Residential service order status", "신청한 인터넷 또는 TV 주문의 진행 상태를 보고 싶어", "Show the status of my submitted home internet or TV order", "주소 검증·장비 배송·설치 대기 상태를 변경 없이 조회", "View address validation, equipment shipment, and install-pending state", "residential account holder|account-authorized household member", "submitted residential service order", "received|address review|equipment shipped|installation pending", "order"),
            R("installation_schedule", "C", "통신 설치 일정 변경", "Service installation scheduling", "인터넷 설치 방문 일정을 예약하거나 변경하고 싶어", "I want to schedule or reschedule my home-service installation visit", "서비스 주소·방문창·변경 영향을 확인하고 사용자가 일정을 확정", "Require user confirmation of address, window, and rescheduling effects", "residential account holder|account-authorized household member", "residential installation appointment", "slot available|selected|awaiting confirmation", "installation"),
            R("equipment_activation", "C", "게이트웨이 및 셋톱박스 활성화", "Gateway and set-top activation", "배송된 라우터나 셋톱박스를 내 회선에 활성화하려고 해", "I want to activate the delivered gateway or set-top box on my line", "장비 일련번호와 정확한 주거 회선을 확인하고 사용자가 활성화", "Require the user to match equipment serial to the exact residential line", "residential account holder|account-authorized household member", "provider gateway or set-top equipment", "delivered|connected|activation ready", "equipment"),
            R("wifi_credentials_update", "C", "와이파이 이름 및 비밀번호 변경", "Wi-Fi name and password update", "집 와이파이 이름이나 비밀번호를 변경하는 곳을 열어 줘", "Open the control to change my home Wi-Fi name or password", "영향받는 연결 기기를 알리고 권한 있는 사용자가 자격증명을 변경", "Warn about affected devices and require authorized user confirmation", "residential account holder|account-authorized household member", "residential Wi-Fi credential", "active|edited|awaiting confirmation", "equipment"),
            R("connected_device_view", "S", "홈 네트워크 연결 기기 보기", "Home network connected-device view", "우리 집 라우터에 연결된 기기 목록을 보고 싶어", "Show devices currently connected to my home gateway", "주거 계정 권한을 확인하고 기기 목록을 차단 동작 없이 열람", "Verify household authorization and view devices without blocking them", "residential account holder|account-authorized household member", "home gateway connected-device inventory", "online|offline|unknown device", "diagnostic"),
            R("outage_status", "S", "가정용 통신 장애 상태", "Residential service outage status", "우리 주소의 인터넷이나 TV 장애가 신고되었는지 확인하고 싶어", "Check whether an internet or TV outage is reported for my address", "주소별 장애·예상 복구 정보를 취소 화면과 명확히 분리해 조회", "View address outage state distinctly from any cancellation route", "residential account holder|account-authorized household member", "residential service outage record", "no outage|investigating|repairing|resolved", "outage"),
            R("guided_diagnostics", "S", "인터넷 속도 측정 및 진단 안내", "Speed test and guided home-service diagnostics", "내 회선의 속도를 측정하고 장비의 공식 진단 절차를 실행할 곳을 찾고 싶어", "Find the provider speed test and guided diagnostics for my line and equipment", "측정 맥락과 회선·게이트웨이·셋톱 상태를 확인하되 해지로 라우팅하지 않음", "Inspect test context, line, and equipment without confusing diagnostics with cancellation", "residential account holder|account-authorized household member", "residential line diagnostic session", "ready|testing|result available|issue found|no issue found", "diagnostic"),
            R("technician_appointment", "C", "통신 장애 기사 방문 예약", "Service technician appointment", "진단 후 집에 방문할 기사를 예약하려고 해", "I want to book a technician visit after diagnostics", "진단 건·주소·비용·방문창을 확인하고 사용자가 방문을 요청", "Require confirmation of case, address, fee, and visit window", "residential account holder|account-authorized household member", "residential repair appointment", "diagnostic complete|slot selected|awaiting confirmation", "installation|diagnostic"),
            R("bill_contract_review", "S", "통신 요금 및 계약기간 보기", "Service bill and contract-term review", "현재 인터넷 또는 TV 청구서와 계약기간을 확인하고 싶어", "Show my current home-service bill and contract term", "청구 항목·프로모션 종료·약정 기간을 변경 동작 없이 열람", "View charges, promotion expiry, and service term without mutation", "residential account holder|authorized payer", "residential service bill and contract", "current|past due|promotion ending|term complete", "billing"),
            R("plan_addon_change", "C", "인터넷 및 TV 요금제 변경", "Internet and TV plan or add-on change", "현재 요금제나 TV 부가서비스를 변경하려고 해", "I want to change my current internet plan or TV add-ons", "새 가격·속도·채널·약정 영향을 확인하고 계정 소유자가 변경", "Require account-holder confirmation of price, service, and term effects", "residential account holder|authorized payer", "active residential plan configuration", "change eligible|repriced|awaiting confirmation", "billing"),
            R("temporary_suspension", "C", "가정용 통신 일시정지", "Residential service temporary suspension", "우리 집 인터넷 또는 TV를 일정 기간 일시정지하고 싶어", "I want to temporarily suspend home internet or TV service", "정지 기간·요금·복구 조건을 확인하고 사용자가 일시정지를 요청", "Have the user confirm duration, charges, and restoration terms", "residential account holder|authorized payer", "active residential service line", "suspension eligible|dates selected|awaiting confirmation", "move_cancel"),
            R("service_move", "C", "인터넷 및 TV 이전 설치", "Residential service move", "현재 서비스를 새 집 주소로 이전하고 싶어", "I want to move my existing home service to a new address", "기존·신규 주소와 설치 가능성·중단 기간을 확인하고 사용자가 이전 요청", "Require confirmation of both addresses, availability, and interruption", "residential account holder|authorized payer", "residential service move order", "new address serviceable|date selected|awaiting confirmation", "move_cancel"),
            R("cancellation_request", "C", "가정용 통신 해지 요청", "Residential service cancellation request", "인터넷 또는 TV 회선 해지를 요청하는 마지막 화면으로 가고 싶어", "Take me to the final request screen for cancelling my home service", "장애·진단과 분리하고 회선·종료일·장비 반환 영향을 확인 후 사용자가 해지", "Separate from outage diagnostics and require user confirmation of line, date, and returns", "residential account holder|authorized payer", "active residential service cancellation", "cancel eligible|impact shown|awaiting confirmation", "move_cancel"),
            R("cancellation_closeout", "S", "해지 상태 및 최종 청구", "Cancellation status and final bill", "해지 요청의 처리 상태와 최종 청구서를 확인하고 싶어", "Show my cancellation state and final home-service bill", "하나의 서비스 종료 기록에서 종료일·최종요금·반환 의무를 열람", "View termination date, final charges, and return duty in one closeout record", "residential account holder|authorized payer", "residential service closeout record", "request received|scheduled|terminated|final bill issued", "move_cancel|billing"),
            R("equipment_return_method", "C", "통신 장비 반환 방식 선택", "Provider equipment return-method selection", "해지 후 라우터나 셋톱박스를 반환할 방식을 선택하고 싶어", "I want to select how to return the gateway or set-top box after cancellation", "반환 대상 일련번호·기한·방법을 확인하고 사용자가 반환 방식을 제출", "Require user confirmation of equipment, deadline, and method", "residential account holder|account-authorized household member", "provider-equipment return request", "return required|method selected|awaiting confirmation", "return"),
            R("return_label_location", "S", "장비 반환 라벨 및 장소", "Equipment return label and location", "통신 장비 반환 라벨이나 공식 반납 장소를 찾고 싶어", "Find the return label or authorized drop-off location for provider equipment", "정확한 계정·장비에 발급된 라벨과 제공자 지정 장소를 조회", "View the label and provider-authorized location for the exact equipment", "residential account holder|account-authorized household member", "provider equipment return instruction", "label available|drop-off selected|deadline approaching", "return"),
            R("equipment_return_confirmation", "S", "통신 장비 반환 확인", "Provider equipment return confirmation", "반납한 라우터나 셋톱박스가 처리되었는지 확인하고 싶어", "Check whether my returned gateway or set-top box was processed", "운송·수령·일련번호 매칭·반환 완료 상태를 추가 제출 없이 조회", "View transit, receipt, serial match, and completion without resubmission", "residential account holder|account-authorized household member", "provider equipment return record", "in transit|received|matched|completed|exception", "return"),
        ),
    ),
    D(
        "consumer_product_recall_remedies",
        "소비자 제품 리콜 구제",
        "Consumer product recall remedies",
        "identified consumer-owned product, regulator or manufacturer, model or VIN, lot or date code, recall jurisdiction, and corrective-action status",
        "do not treat an ordinary return, warranty repair, medical diagnosis, manufacturer recall administration, or regulator enforcement case as a consumer remedy",
        "safety.hub",
        "recall|model|hazard|remedy|incident",
        "commerce|refund|automotive_vehicle|medical_device_regulatory_ops|food_manufacturing_recall_ops",
        "consumer product owner|authorized household member|registered vehicle owner",
        "consumer-owned product|model serial or VIN|affected lot|official recall|hazard guidance|repair replacement refund or disposal remedy|remedy request",
        "not searched|match found|no exact match|unrepaired|stop-use|registered|request pending|remedy in progress|completed",
        (
            R("product_category_search", "S", "제품 리콜 분류 검색", "Product recall category search", "내가 가진 제품 종류의 공식 리콜을 찾아보고 싶어", "Search official recalls for the category of product I own", "넓은 분류 검색 결과를 개별 제품 안전 판정으로 오인하지 않고 조회", "Search broadly without treating an empty result as proof of safety", "consumer product owner|authorized household member", "official recall category index", "matches available|no broad match|filters needed", "search"),
            R("model_serial_vin_lookup", "S", "모델·일련번호·VIN 리콜 조회", "Model serial or VIN recall lookup", "내 제품의 모델이나 일련번호 또는 VIN으로 리콜을 확인하고 싶어", "Check recalls using my product model, serial, or VIN", "정확한 식별자를 공식 제공자 조회에 적용해 대상 여부를 확인", "Use the exact identifier in an official provider lookup", "consumer product owner|registered vehicle owner", "product model serial or VIN", "matched|not matched|identifier invalid|manual confirmation needed", "lookup"),
            R("unrepaired_recall_status", "S", "미수리 리콜 상태", "Unrepaired recall status", "내 제품에 아직 완료되지 않은 리콜 조치가 있는지 보고 싶어", "Show whether an open recall remedy remains incomplete for my product", "제품 식별자별 미완료·완료·부품대기 상태를 변경 없이 조회", "View open, completed, or parts-pending state for the identifier", "consumer product owner|registered vehicle owner", "product recall remedy status", "open|parts pending|scheduled|completed", "lookup"),
            R("lot_date_code_check", "S", "리콜 로트 및 날짜코드 확인", "Affected lot and date-code check", "포장에 적힌 로트나 날짜코드가 리콜 범위인지 확인하고 싶어", "Check whether the lot or date code on my product falls in the recall", "공식 공지의 제조기간·로트 범위와 소비자 제품 코드를 대조", "Compare the consumer's code to the official affected range", "consumer product owner|authorized household member", "product lot or date-code identifier", "within range|outside range|code unreadable|manual check", "lookup"),
            R("hazard_severity", "S", "리콜 위험 및 위해 내용", "Recall hazard and severity", "이 리콜이 설명하는 위험과 심각도를 확인하고 싶어", "Show the hazard and severity described in the official recall", "진단을 내리지 않고 규제기관 또는 제조사가 발표한 위해 내용을 열람", "View regulator or manufacturer hazard statements without diagnosis", "consumer product owner|authorized household member", "official recall hazard notice", "warning|serious injury risk|fire risk|other stated hazard", "hazard"),
            R("stop_use_guidance", "S", "즉시 사용중지 및 보관 안내", "Immediate stop-use and storage guidance", "리콜 제품을 지금 어떻게 사용 중지하고 보관해야 하는지 알고 싶어", "Show official stop-use and safe-storage guidance for the recalled product", "공식 즉시조치 문구를 표시하고 임의의 안전 사용법을 추론하지 않음", "Present official immediate-action guidance without inventing safe use", "consumer product owner|authorized household member", "recall immediate-action guidance", "stop use|unplug|store away|provider-specific direction", "hazard"),
            R("owner_registration", "C", "리콜 소유자 등록", "Recall owner registration", "이 제품의 리콜 소유자로 내 연락처를 등록하려고 해", "I want to register my contact details as the owner of this recalled product", "제품 식별자와 연락 범위를 확인하고 사용자가 알림·구제용 등록을 제출", "Require the owner to submit scoped contact and product identifiers", "consumer product owner|registered vehicle owner", "recall owner registration", "eligible|details complete|awaiting confirmation", "alerts"),
            R("recall_alert_subscription", "C", "제품 리콜 알림 신청", "Product recall alert subscription", "이 제품 또는 분류의 새 리콜 알림을 신청하고 싶어", "I want to subscribe to new recall alerts for this product or category", "알림 범위와 연락 채널을 확인하고 사용자가 구독을 최종 신청", "Let the user confirm alert scope and channel before subscribing", "consumer product owner|authorized household member", "recall alert subscription", "not subscribed|scope selected|awaiting confirmation", "alerts"),
            R("remedy_type", "S", "리콜 구제 유형 확인", "Recall remedy type", "이 리콜이 수리와 교체 또는 환불 중 무엇을 제공하는지 보고 싶어", "Show whether this recall offers repair, replacement, refund, or another remedy", "공식 리콜별 제공 구제와 자격 조건을 신청 동작과 분리해 열람", "View recall-specific remedy and eligibility separately from submission", "consumer product owner|registered vehicle owner", "official recall remedy offering", "repair|replacement|refund|disposal|provider review", "remedy"),
            R("service_location_lookup", "S", "리콜 수리처 찾기", "Recall service location lookup", "내 리콜 제품을 조치하는 공식 판매점이나 서비스센터를 찾고 싶어", "Find an authorized dealer or service center for my recalled product", "제품·리콜·지역에 맞는 공식 조치 지점을 조회", "Locate an official remedy site scoped to product, recall, and region", "consumer product owner|registered vehicle owner", "authorized recall service directory", "available|appointment required|mobile service offered", "repair"),
            R("repair_appointment", "C", "리콜 수리 예약", "Recall repair appointment", "공식 서비스센터에 리콜 수리를 예약하려고 해", "I want to schedule recall repair at an authorized service location", "제품 식별자·리콜·지점·시간을 확인하고 사용자가 예약", "Require owner confirmation of identifier, recall, site, and time", "consumer product owner|registered vehicle owner", "recall repair appointment", "remedy open|slot selected|awaiting confirmation", "repair"),
            R("replacement_request", "C", "리콜 교체 요청", "Recall replacement request", "리콜 대상 제품의 공식 교체를 요청하려고 해", "I want to request the official replacement remedy for my recalled product", "대상 제품과 교체 조건·반송 의무를 확인하고 소유자가 요청", "Require owner confirmation of product, terms, and return duty", "consumer product owner", "recall replacement request", "eligible|choice reviewed|awaiting confirmation", "replacement"),
            R("refund_request", "C", "리콜 환불 요청", "Recall refund request", "리콜 대상 제품의 공식 환불 구제를 신청하려고 해", "I want to request the official refund remedy for my recalled product", "리콜 번호·제품·환불 방식과 소유권 영향을 확인하고 사용자가 요청", "Require confirmation of recall, product, refund method, and ownership effect", "consumer product owner|authorized payer", "recall refund request", "eligible|amount or method shown|awaiting confirmation", "refund"),
            R("return_shipping_instructions", "S", "리콜 제품 배송 및 반송 안내", "Recall return-shipping instructions", "리콜 제품을 어디로 어떻게 보내야 하는지 확인하고 싶어", "Show where and how to ship the recalled product for its remedy", "공식 포장·라벨·운송 제한과 반송 주소를 제품별로 조회", "View product-specific packaging, label, carrier, and address directions", "consumer product owner|authorized household member", "recall return-shipping instruction", "label available|special handling|required drop-off", "replacement|refund"),
            R("proof_exception_request", "C", "구매 증빙 예외 요청", "Recall proof-of-purchase exception", "영수증이 없는 리콜 제품의 증빙 예외를 요청하고 싶어", "I want to request a proof-of-purchase exception for a recalled product without a receipt", "공식 예외 경로에서 제품 식별과 대체 증빙을 소유자가 제출", "Let the owner submit identifier and alternate evidence in the official exception path", "consumer product owner", "recall proof exception request", "exception offered|evidence ready|awaiting confirmation", "remedy"),
            R("remedy_request_status", "S", "리콜 구제 요청 상태", "Recall remedy request status", "제출한 리콜 수리나 교체 또는 환불 요청 상태를 보고 싶어", "Show the status of my submitted recall repair, replacement, or refund request", "요청 접수·검증·배송·예약 상태를 변경 없이 확인", "View receipt, validation, shipment, or appointment state", "consumer product owner|registered vehicle owner", "submitted recall remedy case", "received|verification pending|scheduled|shipped|exception", "status"),
            R("remedy_completion", "S", "리콜 조치 완료 확인", "Recall remedy completion", "내 제품의 리콜 조치가 완료로 기록되었는지 확인하고 싶어", "Check whether the recall remedy is recorded as complete for my product", "식별자별 수리·교체·환불 완료 기록을 미수리 상태와 대조", "Verify identifier-scoped completion against the prior open-recall state", "consumer product owner|registered vehicle owner", "recall remedy completion record", "completed|not completed|record update pending", "status"),
            R("unsafe_product_incident", "C", "위해 제품 사고 신고", "Unsafe-product incident report", "이 제품과 관련된 사고나 위해를 공식 기관에 신고하려고 해", "I want to report an incident or injury involving this product to the official authority", "응급 대응과 분리하고 제품·사건·피해 사실을 사용자가 직접 제출", "Separate emergency response and require user submission of product and incident facts", "consumer product owner|affected consumer|authorized household member", "unsafe-product incident report", "safe to report|details ready|awaiting confirmation", "incident"),
            R("disposal_guidance", "S", "리콜 제품 폐기 안내", "Recalled-product disposal guidance", "반송할 수 없는 리콜 제품의 공식 폐기 방법을 확인하고 싶어", "Show official disposal directions for a recalled product that cannot be returned", "일반 폐기 조언 대신 제품·위험별 공식 처리 지침을 열람", "View product- and hazard-specific official directions instead of generic advice", "consumer product owner|authorized household member", "recall disposal instruction", "available|special handling|local authority referral", "disposal"),
            R("inconclusive_lookup", "S", "리콜 조회 불확실 결과", "Inconclusive recall lookup", "검색 결과가 없거나 식별자가 맞지 않을 때 다음 공식 확인 방법을 알고 싶어", "Show the official next check when a recall search is empty or the identifier does not match", "빈 검색을 안전 판정으로 바꾸지 않고 제조사·규제기관 수동 확인 경로를 표시", "Never infer safety from no result; show official manual-verification routes", "consumer product owner|registered vehicle owner", "inconclusive recall search result", "no broad match|identifier invalid|manual verification required", "search"),
        ),
    ),
    D(
        "school_family_enrollment",
        "학교 가족 등록 및 기록",
        "School-family enrolment and records",
        "identified guardian-linked student, residential school jurisdiction, academic year, grade, family portal, and enrollment or records case",
        "do not route higher-education admissions, instructor administration, childcare booking, special-education casework, or school-operator SIS work here",
        "education.hub",
        "student|school|registration|attendance|transfer",
        "higher_education_student_admin|education|classroom_instructor_ops|childcare_family_portal|special_education_program_admin",
        "student guardian|eligible adult student|guardian-authorized family member",
        "guardian-linked student|zoned-school eligibility|registration checklist|placement record|family-facing attendance and academic record|transfer or records request",
        "eligibility unknown|account unlinked|registration draft|documents pending|placed|wait-listed|enrolled|attendance posted|transfer pending|records ready",
        (
            R("zoned_school_lookup", "S", "거주지 배정 학교 찾기", "Zoned-school lookup", "우리 집 주소에 배정된 학교를 찾고 싶어", "Find the school zoned for my residential address", "교육청·학년도·주소 기준의 배정 학교를 등록 없이 조회", "Look up the zoned school by district, year, and address without registration", "student guardian|eligible adult student", "residential zoned-school record", "match found|boundary review|no match|manual help needed", "enrollment"),
            R("enrollment_path_eligibility", "S", "학년 및 신규·재학생 등록 경로", "Grade and enrollment-path eligibility", "학생의 학년과 신규 또는 재학생 등록 경로를 확인하고 싶어", "Check the grade and new- or returning-student path for this student", "학생 생년·학년도·현재 재학 상태에 따른 등록 경로를 정보로 검토", "Review the enrollment path from age, year, and current status", "student guardian|eligible adult student", "student enrollment-path eligibility", "new student|returning student|grade eligible|manual review", "enrollment"),
            R("guardian_account", "C", "보호자 학교 계정 생성", "Guardian school-account creation", "학교 가족 포털의 보호자 계정을 만들고 싶어", "I want to create a guardian account for the school family portal", "보호자 본인이 신원과 연락처를 확인하고 가족 계정을 생성", "Require the guardian to confirm identity and contact details", "student guardian", "guardian family-portal account", "not created|details ready|awaiting confirmation", "account"),
            R("student_link", "C", "보호자 계정에 학생 연결", "Guardian-to-student account linking", "내 보호자 계정에 이 학생을 연결하려고 해", "I want to link this student to my guardian account", "보호 관계와 학생 식별을 확인한 뒤 사용자가 계정 연결을 제출", "Require relationship and student verification before account linking", "student guardian", "guardian-to-student relationship link", "unlinked|verification ready|awaiting confirmation", "account"),
            R("school_program_list", "S", "학교 및 프로그램 선택 목록", "School and program choice list", "학생이 지원할 수 있는 학교와 프로그램 목록을 보고 싶어", "Show schools and programs this student may choose", "학년·주소·교육청 기준의 선택 가능 항목을 신청 동작 없이 조회", "View eligible choices by grade, address, and district without applying", "student guardian|eligible adult student", "student school-and-program choice set", "eligible|priority applies|not eligible", "enrollment"),
            R("registration_checklist", "S", "학생 등록 준비 체크리스트", "Student registration checklist", "학교 등록에 필요한 서류와 단계를 확인하고 싶어", "Show the documents and steps required for school registration", "학생·학년·교육청별 신원·거주·예방접종 요건을 읽기 전용으로 검토", "Review identity, residency, and immunization requirements", "student guardian|eligible adult student", "student registration checklist", "not started|items pending|complete", "registration"),
            R("document_status", "S", "등록 서류 접수 상태", "Registration document status", "제출한 신원과 거주 및 예방접종 서류 상태를 보고 싶어", "Show receipt status for submitted identity, residency, and immunization documents", "서류별 접수·검토·반려·만료 상태를 추가 제출과 분리해 조회", "View per-document receipt, review, rejection, and expiry states", "student guardian|eligible adult student", "student registration document record", "missing|received|under review|rejected|accepted", "registration"),
            R("registration_submission", "C", "학생 입학 등록 제출", "Student enrollment registration submission", "검토한 학생 등록 신청서를 학교에 제출하려고 해", "I want to submit the reviewed school enrollment registration", "학생·보호자·학교·학년도·서류를 확인하고 사용자가 최종 제출", "Require confirmation of student, guardian, school, year, and documents", "student guardian|eligible adult student", "student school-registration application", "complete|school selected|awaiting confirmation", "registration"),
            R("registration_completion", "S", "학교 등록 완료 상태", "School registration completion status", "학생의 학교 등록이 완료되었는지 확인하고 싶어", "Check whether this student's school registration is complete", "신청 접수·학교 확인·등록 완료를 배치 제안과 분리해 조회", "View receipt, school verification, and completion separately from placement", "student guardian|eligible adult student", "student registration case", "submitted|school review|completed|action required", "status"),
            R("placement_waitlist_status", "S", "학교 배치 및 대기자 상태", "School placement and wait-list status", "학생의 학교 배치 제안이나 대기 순번을 확인하고 싶어", "Show this student's placement offer or wait-list state", "학생·학년도·프로그램별 배치 또는 대기 상태를 응답과 분리해 열람", "View year- and program-scoped placement separately from response", "student guardian|eligible adult student", "student placement record", "offered|wait-listed|no offer|expired", "placement"),
            R("waitlist_offer_response", "C", "학교 배치 및 대기 제안 응답", "School placement or wait-list response", "학교 배치 또는 대기자 제안에 응답하려고 해", "I want to respond to the school placement or wait-list offer", "학생·학교·프로그램·기한을 확인하고 보호자가 수락 또는 거절", "Require guardian confirmation of student, school, program, and deadline", "student guardian|eligible adult student", "student placement response", "offer open|choice selected|awaiting confirmation", "placement"),
            R("family_contact_update", "C", "학생 가족 연락처 변경", "Student family-contact update", "학교 기록의 보호자 연락처나 주소를 변경하고 싶어", "I want to update guardian contact details or address in the school record", "정확한 학생 기록과 변경 범위를 확인하고 권한 있는 사용자가 수정", "Require authorized confirmation of student record and fields", "student guardian|eligible adult student", "student family-contact record", "verified|edited|awaiting confirmation", "records"),
            R("attendance_view", "S", "학생 출결 보기", "Student attendance view", "이 학생의 날짜별 출석과 지각 기록을 확인하고 싶어", "Show daily attendance and lateness records for this student", "보호자 연결과 학년을 확인하고 가족용 출결 기록을 읽기 전용으로 열람", "Verify guardian link and year before viewing family-facing attendance", "student guardian|eligible adult student", "student attendance record", "present|absent|late|pending update", "attendance"),
            R("absence_notice_correction", "C", "결석 알림 및 출결 정정 요청", "Absence notice or attendance correction request", "학생의 결석을 알리거나 잘못된 출결 기록 정정을 요청하고 싶어", "I want to report an absence or request correction of an attendance entry", "학생·날짜·요청 유형과 설명을 확인하고 보호자가 제출", "Require guardian confirmation of student, date, request type, and statement", "student guardian|eligible adult student", "student attendance notice or correction", "date selected|statement ready|awaiting confirmation", "attendance"),
            R("grades_schedule_view", "S", "학생 성적 및 시간표 보기", "Student grades and schedule view", "가족 포털에서 학생의 성적과 현재 시간표를 보고 싶어", "Show this student's family-facing grades and current schedule", "교육청이 하나의 학업 기록 화면으로 제공하는 성적·수업 배치를 조회", "View grades and class placement in the district's family academic record", "student guardian|eligible adult student", "student family academic record", "current|provisional|term closed|restricted", "records"),
            R("transfer_eligibility", "S", "학생 전학 자격 확인", "Student transfer eligibility", "이 학생이 전학 신청 대상인지 확인하고 싶어", "Check whether this student is eligible for a school transfer", "전학 유형·거주지·학년·사유별 표시 자격을 법적 보장 없이 검토", "Review displayed eligibility by transfer type, address, grade, and reason", "student guardian|eligible adult student", "student transfer eligibility record", "eligible|not eligible|exception review|required counseling", "transfer"),
            R("transfer_document_checklist", "S", "전학 서류 체크리스트", "Student transfer document checklist", "전학 요청에 필요한 재학과 거주 서류를 확인하고 싶어", "Show the enrollment and residency documents needed for a transfer request", "교육청·전학 유형별 필수 서류와 발급 상태를 제출 없이 조회", "Review district- and type-specific transfer documents without submit", "student guardian|eligible adult student", "student transfer document checklist", "items missing|ready|document expired", "transfer"),
            R("transfer_request", "C", "학생 전학 요청 제출", "Student transfer request", "준비된 서류로 학생 전학 요청을 제출하려고 해", "I want to submit this student's transfer request with the prepared documents", "학생·현재 학교·요청 학교·사유·서류를 확인하고 보호자가 제출", "Require guardian confirmation of student, schools, reason, and documents", "student guardian|eligible adult student", "student school-transfer request", "eligible|documents ready|awaiting confirmation", "transfer"),
            R("transfer_status", "S", "학생 전학 처리 상태", "Student transfer request status", "제출한 전학 요청의 검토와 결정 상태를 확인하고 싶어", "Check the review and decision state of my submitted transfer request", "접수·서류검토·배치검토·승인·거절 상태를 변경 없이 조회", "View receipt, document review, placement review, approval, or denial", "student guardian|eligible adult student", "submitted student transfer case", "received|under review|approved|denied|more information needed", "transfer"),
            R("student_record_request", "C", "학생 기록 및 성적표 요청", "Student record or transcript request", "이 학생의 공식 기록이나 성적표 사본을 요청하고 싶어", "I want to request an official student record or transcript copy", "요청자 권한·학생·기록 종류·수령 방식을 확인하고 사용자가 제출", "Require confirmation of authority, student, record type, and delivery", "student guardian|eligible adult student", "official student-record request", "authorized|record selected|awaiting confirmation", "records"),
        ),
    ),
    D(
        "online_marketplace_seller_ops",
        "온라인 마켓플레이스 판매자 운영",
        "Online marketplace seller operations",
        "identified verified business seller, provider storefront, marketplace listing, buyer order, fulfilment record, payout account, and seller jurisdiction",
        "business storefront operations only; exclude consumer purchases, one-off used-item listings, generic POS inventory, direct-site administration, CRM, and warehouse-operator work",
        "marketplace.hub",
        "store|listing|order|refund|payout",
        "marketplace|merchant_pos_inventory|commerce|crm_sales|warehouse_fulfillment_ops",
        "verified business seller owner|storefront manager|seller order operator|seller finance administrator",
        "verified marketplace storefront|business catalog listing|sellable inventory|buyer order|fulfilment|return or dispute case|seller payment account|seller standing",
        "verification pending|store active|listing draft|published|order pending|fulfilling|delivered|return open|payout pending|restricted",
        (
            R("seller_verification", "C", "사업자 판매자 등록 및 인증", "Business seller registration and verification", "사업자 판매자 계정을 등록하고 인증 자료를 제출하려고 해", "I want to register a business seller account and submit verification", "사업 주체·마켓·관할·신원 자료를 확인하고 판매자 소유자가 제출", "Require the seller owner to confirm entity, market, jurisdiction, and evidence", "verified business seller owner", "business seller identity application", "draft|evidence ready|awaiting confirmation", "onboarding"),
            R("storefront_configuration", "C", "스토어 프로필 및 판매정책 설정", "Storefront profile and selling-policy configuration", "내 마켓플레이스 스토어 프로필과 배송·반품 정책을 설정하고 싶어", "I want to configure my marketplace storefront profile, shipping, and return policies", "사업 스토어의 공개 정보와 주문 정책을 소유자가 최종 저장", "Require the store owner to save public profile and order policies", "verified business seller owner|storefront manager", "business storefront configuration", "draft|edited|awaiting confirmation", "store"),
            R("seller_role_access", "C", "판매자 스토어 사용자 권한", "Seller storefront role access", "직원에게 판매자 스토어 역할을 부여하거나 제거하려고 해", "I want to grant or remove a staff role on the seller storefront", "정확한 직원·역할·권한 범위를 확인하고 소유자가 접근을 변경", "Require owner confirmation of staff identity, role, and scope", "verified business seller owner", "business storefront membership", "active|role edited|awaiting confirmation", "access"),
            R("catalog_listing_view", "S", "사업자 상품 목록 보기", "Business catalog listing view", "내 스토어의 게시·초안·비활성 상품 목록을 보고 싶어", "Show published, draft, and inactive business listings in my store", "일회성 중고 물품과 구분해 검증된 스토어 카탈로그 상태를 조회", "View verified-store catalog state separately from one-off resale listings", "verified business seller owner|storefront manager", "business storefront catalog", "draft|published|out of stock|inactive", "listing"),
            R("listing_draft_edit", "C", "사업자 상품 초안 작성 및 수정", "Business listing draft editing", "스토어 상품의 설명과 분류 및 변형 초안을 수정하고 싶어", "I want to edit title, category, description, and variation draft for a store listing", "게시 동작과 분리해 사업자 카탈로그 초안을 권한자가 저장", "Save a business catalog draft separately from publication", "verified business seller owner|storefront manager", "business catalog listing draft", "new draft|editable|validation warning", "listing"),
            R("listing_publish", "C", "사업자 상품 게시", "Business marketplace listing publication", "검토한 스토어 상품을 마켓플레이스에 게시하려고 해", "I want to publish the reviewed business listing to the marketplace", "가격·재고·정책·상품 정보를 확인하고 판매자가 최종 게시", "Require seller confirmation of product, price, stock, and policies", "verified business seller owner|storefront manager", "reviewed business listing", "publish eligible|reviewed|awaiting confirmation", "listing"),
            R("listing_deactivate", "C", "사업자 상품 비활성화", "Business listing deactivation", "스토어의 게시 상품을 판매 중지 상태로 바꾸고 싶어", "I want to deactivate a published business listing in my storefront", "미처리 주문과 재활성화 영향을 확인하고 판매자가 비활성화", "Require seller confirmation of open-order and reactivation effects", "verified business seller owner|storefront manager", "published business listing", "active|deactivation eligible|awaiting confirmation", "listing"),
            R("variation_inventory_update", "C", "상품 변형 및 재고 변경", "Listing variation and inventory update", "상품 옵션별 판매 재고 수량을 변경하고 싶어", "I want to update sellable inventory for each listing variation", "정확한 SKU·창고가 아닌 마켓 판매 수량·옵션을 판매자가 변경", "Update marketplace sellable quantity and variation for the exact SKU", "verified business seller owner|storefront manager", "marketplace listing inventory", "in stock|low stock|edited|awaiting confirmation", "inventory"),
            R("listing_price_update", "C", "마켓 상품 가격 변경", "Marketplace listing price update", "스토어 상품의 판매 가격을 변경하는 화면을 열어 줘", "Open the control to change the selling price of a storefront listing", "통화·마켓·프로모션 영향을 확인하고 판매자가 가격을 적용", "Require seller confirmation of currency, market, and promotion effects", "verified business seller owner|storefront manager", "marketplace listing price", "current|edited|awaiting confirmation", "inventory"),
            R("seller_order_view", "S", "판매자 주문 목록 및 상세", "Seller order list and detail", "내 스토어의 신규 주문과 구매자별 상세를 보고 싶어", "Show new orders and buyer-level details for my storefront", "소비자 구매 화면과 구분해 사업 판매자의 주문 처리 기록을 조회", "View business seller order records separately from consumer purchases", "verified business seller owner|seller order operator", "business storefront buyer order", "new|accepted|cancel requested|fulfilling|delivered", "order"),
            R("order_accept", "C", "판매자 주문 수락", "Seller order acceptance", "새 구매자 주문을 판매자가 수락하는 곳으로 가고 싶어", "Take me to accept a new buyer order as the seller", "재고·배송기한·주문 항목을 확인하고 판매자가 주문을 수락", "Require seller confirmation of stock, deadline, and line items", "verified business seller owner|seller order operator", "new buyer order", "new|accept eligible|awaiting confirmation", "order"),
            R("order_cancel", "C", "판매자 주문 취소", "Seller-side order cancellation", "판매자 사유로 이 구매자 주문을 취소하려고 해", "I want to cancel this buyer order from the seller side", "환불·재고·판매자 지표 영향을 확인하고 판매자가 취소", "Require seller confirmation of refund, inventory, and performance effects", "verified business seller owner|seller order operator", "accepted buyer order", "cancel eligible|reason selected|awaiting confirmation", "order"),
            R("fulfilment_confirmation", "C", "포장·발송 및 추적 확정", "Order fulfilment and tracking confirmation", "포장한 주문의 배송 라벨과 추적번호를 확정하고 싶어", "I want to confirm shipment, label, and tracking for the packed order", "정확한 주문·운송사·추적번호를 확인하고 판매자가 발송 처리", "Require seller confirmation of order, carrier, and tracking before dispatch", "seller order operator|verified business seller owner", "buyer order fulfilment record", "picked|packed|label ready|awaiting shipment confirmation", "fulfilment"),
            R("delivery_exception", "S", "판매 주문 배송 예외", "Seller-order delivery exception", "판매한 주문의 지연이나 주소 또는 반송 예외를 확인하고 싶어", "Show delay, address, or return-to-sender exceptions for a sold order", "주문별 운송 예외와 필요한 판매자 조치를 변경 없이 조회", "View shipment exception and required seller follow-up without mutation", "seller order operator|storefront manager", "seller-order delivery exception", "delayed|address issue|returned|carrier investigation", "fulfilment"),
            R("return_refund_case", "S", "구매자 반품 및 환불 요청", "Buyer return and refund case", "구매자가 연 반품 또는 환불 요청의 사유와 상태를 보고 싶어", "Show reason and status for the buyer's return or refund request", "주문·상품·기한·증빙을 실제 환불 동작과 분리해 검토", "Review order, item, deadline, and evidence separately from refund", "verified business seller owner|seller order operator", "buyer return or refund case", "opened|evidence pending|return in transit|decision due", "return"),
            R("refund_issue", "C", "판매자 환불 처리", "Seller refund issuance", "이 구매자 주문에 환불을 발행하는 마지막 화면으로 가고 싶어", "Take me to the final control for issuing a refund on this buyer order", "주문·금액·사유·반품 상태를 확인하고 판매자가 환불", "Require seller confirmation of order, amount, reason, and return state", "verified business seller owner|seller finance administrator", "buyer-order refund instruction", "refund eligible|amount selected|awaiting confirmation", "return"),
            R("seller_dispute_case", "S", "판매자 분쟁 및 케이스 보기", "Seller dispute and case view", "구매자 또는 플랫폼이 연 판매 분쟁의 상태를 확인하고 싶어", "Show the state of a buyer or platform dispute affecting my store", "정확한 주문·증빙·기한·플랫폼 판단을 항소 제출과 분리해 열람", "View order, evidence, deadline, and platform decision separately from appeal", "verified business seller owner|storefront manager", "marketplace seller dispute case", "open|evidence requested|decided|appeal eligible", "dispute"),
            R("seller_appeal", "C", "판매자 결정 이의제기", "Seller decision appeal", "판매 분쟁이나 정책 결정에 판매자 이의를 제출하려고 해", "I want to submit a seller appeal against a dispute or policy decision", "결정·스토어·증빙·기한을 확인하고 판매자가 이의를 최종 제출", "Require seller confirmation of decision, store, evidence, and deadline", "verified business seller owner|storefront manager", "seller decision appeal", "eligible|statement ready|awaiting confirmation", "dispute"),
            R("seller_payment_account", "S", "판매자 지급 및 정산 계정", "Seller payment and settlement account", "판매대금 잔액과 입금 계좌 상태 및 수수료·세금 명세를 보고 싶어", "Show payout balance, bank status, fees, and tax statements in my seller payment account", "하나의 제공자 결제계정에서 지급 예정·보류·비용·명세 상태를 조회", "View payout, hold, fee, and statement state in the provider payment account", "verified business seller owner|seller finance administrator", "marketplace seller payment account", "available|payout pending|bank unverified|statement issued", "payout"),
            R("seller_standing_analytics", "S", "판매자 성과 및 계정 제한", "Seller performance and account standing", "스토어 매출 성과와 서비스 지표 및 정책 제한을 확인하고 싶어", "Show sales performance, service metrics, and policy standing for my store", "검증된 스토어의 분석·등급·위반·제한 상태를 일반 판매 목록과 분리해 조회", "View verified-store analytics, level, violations, and restrictions", "verified business seller owner|storefront manager", "marketplace seller standing record", "healthy|below standard|warning|restricted|appeal eligible", "performance"),
        ),
    ),
    D(
        "gig_worker_account_earnings",
        "긱 워커 계정 및 수입",
        "Gig-worker account and earnings",
        "identified independent worker, platform provider, work region, eligibility record, payout country, and worker-account standing",
        "worker-account and money states only; exclude consumer ordering, fleet-employer administration, and offer discovery, acceptance, or active dispatch execution",
        "gig_worker_dispatch.hub",
        "worker|document|earnings|payout|appeal",
        "gig_worker_dispatch|hr_payroll|fleet_driver_compliance|jobs|ride_hailing_extended",
        "independent platform worker|worker-authorized payout owner|worker account owner",
        "independent worker account|eligibility and onboarding record|required document|vehicle or equipment profile|completed-job ledger|earnings and payout record|worker standing and appeal",
        "signup draft|eligibility review|background pending|documents expiring|activation pending|active|payout failed|warning|held|deactivated|appealed|closed",
        (
            R("worker_signup", "C", "긱 워커 가입 신청", "Gig-worker signup", "독립 작업자 계정 가입 신청을 제출하려고 해", "I want to submit signup for an independent platform-worker account", "제공자·지역·작업자 신원과 계약 형태를 확인하고 본인이 신청", "Require the worker to confirm provider, region, identity, and relationship", "independent platform worker|worker account owner", "independent worker signup application", "draft|requirements reviewed|awaiting confirmation", "onboarding"),
            R("eligibility_region", "S", "작업 자격 및 활동 지역", "Worker eligibility and region", "내가 이 지역에서 작업자 계정을 만들 자격이 있는지 확인하고 싶어", "Check whether I am eligible to work through this provider in my region", "고용관계나 법적 지위를 판단하지 않고 제공자별 표시 요건을 조회", "Review provider-stated requirements without employment-law conclusions", "independent platform worker|worker account owner", "provider worker-region eligibility", "eligible|wait-listed|not available|manual review", "onboarding"),
            R("identity_verification", "C", "작업자 본인확인 제출", "Worker identity verification", "작업자 계정의 본인확인 자료를 제출하려고 해", "I want to submit identity evidence for my worker account", "민감한 신원 자료와 제공 범위를 확인하고 작업자가 직접 제출", "Require the worker to submit scoped sensitive identity evidence", "independent platform worker|worker account owner", "worker identity-verification evidence", "required|evidence ready|awaiting confirmation", "onboarding"),
            R("onboarding_activation_status", "S", "배경조회·교육·활성화 상태", "Background, training, and activation status", "배경조회와 필수 교육 및 계정 활성화 진행 상태를 보고 싶어", "Show my background-check, required-training, and activation progress", "하나의 제공자 온보딩 케이스에서 각 단계 상태를 변경 없이 조회", "View provider onboarding stages without claiming employment clearance", "independent platform worker|worker account owner", "worker onboarding case", "background pending|training due|reviewing|active|rejected", "onboarding"),
            R("required_document_list", "S", "작업자 필수 서류 목록", "Worker required-document list", "내 지역과 작업 유형에 필요한 서류와 만료일을 확인하고 싶어", "Show documents and expiry requirements for my region and work type", "제공자별 면허·보험·허가·신원 서류 요건을 업로드와 분리해 검토", "Review provider document requirements separately from upload", "independent platform worker|worker account owner", "worker required-document checklist", "missing|valid|expiring|expired", "documents"),
            R("document_upload_renewal", "C", "작업자 서류 업로드 및 갱신", "Worker document upload and renewal", "만료 예정인 작업자 서류를 새 파일로 제출하려고 해", "I want to upload or renew an expiring worker document", "서류 종류·지역·만료일·민감정보 범위를 확인하고 작업자가 제출", "Require confirmation of type, region, expiry, and sensitive scope", "independent platform worker|worker account owner", "worker eligibility document", "missing|expiring|replacement ready|awaiting confirmation", "documents"),
            R("vehicle_equipment_profile", "C", "작업 차량 및 장비 등록", "Worker vehicle and equipment profile", "작업에 사용할 차량이나 장비 정보를 등록하거나 변경하고 싶어", "I want to register or update vehicle or equipment used for platform work", "소유·보험·지역 요건과 정확한 자산을 확인하고 작업자가 변경", "Require the worker to confirm asset, ownership, insurance, and region", "independent platform worker|worker account owner", "worker vehicle or equipment profile", "unregistered|verified|edited|awaiting confirmation", "documents"),
            R("availability_preference", "C", "작업 가능 시간 선호 설정", "Worker availability preference", "작업 제안 수신을 위한 가능 시간과 지역 선호를 설정하고 싶어", "I want to set time and region preferences for receiving work opportunities", "개별 제안 수락이나 배차 실행과 분리해 계정 선호를 작업자가 저장", "Save account preferences separately from offer acceptance or dispatch", "independent platform worker|worker account owner", "worker availability preference", "unset|edited|awaiting confirmation", "account"),
            R("completed_job_history", "S", "완료 작업 이력", "Completed-job history", "내 계정에서 완료된 작업과 취소 기록을 확인하고 싶어", "Show completed and cancelled jobs recorded on my worker account", "제안 발견·수락·활성 배차와 분리해 완료 후 작업 기록을 조회", "View post-completion history separately from live offer and dispatch", "independent platform worker|worker account owner", "worker completed-job ledger", "completed|cancelled|adjusted|under review", "earnings"),
            R("earnings_ledger_statement", "S", "작업 수입 명세 및 내역", "Worker earnings ledger and statement", "기간별 작업 수입 요약과 상세 명세를 보고 싶어", "Show my period earnings summary, details, and statement", "세무 또는 고용 조언 없이 제공자 수입 원장을 읽기 전용으로 열람", "View the provider earnings ledger without tax or employment advice", "independent platform worker|worker account owner", "worker earnings ledger", "provisional|posted|statement issued|adjusted", "earnings"),
            R("adjustment_tip_incentive", "S", "운임 조정·팁·인센티브", "Fare adjustments, tips, and incentives", "작업별 운임 조정과 팁 및 인센티브 반영 내역을 확인하고 싶어", "Show fare adjustments, tips, and incentives applied to my jobs", "완료 작업에 연결된 추가·차감 항목과 계산 근거 표시를 조회", "View additional and deducted items tied to completed jobs", "independent platform worker|worker account owner", "worker earnings adjustment record", "pending|posted|reversed|disputed", "earnings"),
            R("payout_tax_profile", "C", "지급 계좌 및 세금정보 변경", "Worker payout-bank and tax profile", "수입 지급 계좌나 제공자 세금정보를 변경하고 싶어", "I want to update the payout bank or provider tax profile for my worker account", "금융·세금 식별정보 범위를 확인하고 계정 소유자가 직접 변경", "Require the account owner to personally change sensitive bank or tax identifiers", "worker account owner|worker-authorized payout owner", "worker payout and tax profile", "verified|edited|awaiting confirmation", "payout"),
            R("payout_method_cashout", "C", "지급 방식·일정 및 현금화", "Worker payout method, schedule, and cash-out", "수입 지급 방식과 일정을 선택하거나 즉시 출금을 요청하고 싶어", "I want to choose payout method and schedule or request cash-out", "수수료·금액·계좌·도착 예상일을 확인하고 작업자가 지급을 요청", "Require worker confirmation of fee, amount, account, and arrival estimate", "worker account owner|worker-authorized payout owner", "worker payout instruction", "balance available|method selected|awaiting confirmation", "payout"),
            R("failed_payout", "S", "작업 수입 지급 실패", "Worker failed-payout status", "지급이 실패하거나 반송된 이유와 다음 조치를 확인하고 싶어", "Show why my worker payout failed or was returned and what the provider requests", "지급 건·계좌 상태·오류 사유를 변경 없이 조회하고 세무 조언을 하지 않음", "View payout, account state, and provider error without tax advice", "worker account owner|worker-authorized payout owner", "worker payout failure record", "failed|returned|bank review|required update", "payout"),
            R("worker_standing", "S", "작업자 평점·경고 및 보류", "Worker rating, warning, and hold status", "내 평점과 피드백 및 계정 경고나 임시 보류 상태를 보고 싶어", "Show ratings, feedback, warnings, or temporary holds on my worker account", "하나의 제공자 작업자 상태 기록에서 품질 지표와 제재 전 상태를 조회", "View quality and pre-deactivation standing in the provider worker record", "independent platform worker|worker account owner", "worker account standing record", "good standing|warning|temporary hold|reviewing", "standing"),
            R("deactivation_reason", "S", "작업자 계정 비활성화 사유", "Worker account deactivation reason", "내 작업자 계정이 비활성화된 공식 사유를 확인하고 싶어", "Show the provider-stated reason my worker account was deactivated", "제공자 통지·적용일·이의 가능성을 법률 판단 없이 열람", "View provider notice, effective date, and appeal availability without legal judgment", "independent platform worker|worker account owner", "worker deactivation notice", "deactivated|temporary|permanent|appeal offered", "deactivation"),
            R("remediation_submission", "C", "작업자 계정 시정조치 제출", "Worker-account remediation submission", "계정 복구를 위해 요구된 교육이나 서류를 제출하려고 해", "I want to submit required training or documents for account remediation", "제공자가 명시한 조치와 자료 범위를 확인하고 작업자가 제출", "Require worker submission only for provider-stated remediation", "independent platform worker|worker account owner", "worker account remediation record", "offered|requirements complete|awaiting confirmation", "deactivation"),
            R("deactivation_appeal", "C", "작업자 비활성화 이의제기", "Worker deactivation appeal", "비활성화 결정에 설명과 증빙을 포함해 이의를 제출하려고 해", "I want to appeal deactivation with my statement and evidence", "자격·기한·결정·증빙을 확인하고 작업자가 공식 이의를 제출", "Require worker confirmation of eligibility, deadline, decision, and evidence", "independent platform worker|worker account owner", "worker deactivation appeal", "eligible|statement ready|awaiting confirmation", "appeal"),
            R("appeal_status_decision", "S", "작업자 이의 상태 및 결정", "Worker appeal status and decision", "제출한 비활성화 이의의 검토 상태와 결정을 확인하고 싶어", "Show review status and decision for my submitted deactivation appeal", "접수·추가자료·검토·복구·기각 상태를 추가 제출과 분리해 조회", "View receipt, evidence request, review, restoration, or denial", "independent platform worker|worker account owner", "submitted worker deactivation appeal", "received|under review|evidence requested|restored|denied", "appeal"),
            R("worker_account_exit", "C", "긱 워커 계정 탈퇴", "Gig-worker account exit", "작업자 계정을 종료하는 마지막 화면으로 이동해 줘", "Take me to the final control for exiting my worker account", "미지급 수입·세금 문서·진행 중 이의 영향을 확인하고 소유자가 탈퇴", "Require owner confirmation after reviewing unpaid earnings, documents, and appeals", "worker account owner", "independent worker account", "exit available|impact reviewed|awaiting confirmation", "exit"),
        ),
    ),
)

REVIEWED_BY_DOMAIN = {item.domain: item for item in REVIEWED_DOMAINS}
REVIEWED_FEATURE_BY_ID = {
    f"{domain.domain}.{feature.key}": feature
    for domain in REVIEWED_DOMAINS
    for feature in domain.features
}


KOREAN_DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "digital_ad_campaign_ops": _terms("네이버 검색광고|광고 계정|캠페인 관리|광고비 결제"),
    "consumer_device_warranty_repair": _terms("삼성전자서비스|서비스센터 찾기|휴대폰 수리|수리 진행상태"),
    "higher_education_admissions": _terms("대입정보포털 어디가|대학 입학원서|원서 접수상태|지원 횟수"),
    "social_platform_account_appeals": _terms("계정 정지|계정 잠김|이의제기|콘텐츠 제재"),
    "consumer_debt_collection_services": _terms("채권추심|채무 확인|추심 연락 제한|신용회복위원회"),
    "rental_vehicle_trip_services": _terms("롯데렌터카|단기렌터카 예약|대여 연장|렌터카 반납"),
    "airline_passenger_trip_management": _terms("대한항공 예약|여행 서류|수하물 추적|항공권 환불"),
    "home_internet_tv_service": _terms("B world 인터넷|가정용 인터넷|인터넷 이전 설치|장비 반납"),
    "consumer_product_recall_remedies": _terms("제품안전정보센터|제품 리콜|리콜 조치|위해제품 신고"),
    "school_family_enrollment": _terms("나이스 학부모서비스|학교 배정|학생 전학|학생생활기록"),
    "online_marketplace_seller_ops": _terms("스마트스토어 판매자센터|상품관리|판매관리|정산관리"),
    "gig_worker_account_earnings": _terms("배민커넥트|배달 정산|라이더 계정|작업자 수입"),
}


@dataclass(frozen=True)
class SourceSeed:
    source_id: str
    domain: str
    publisher: str
    title: str
    canonical_url: str
    jurisdiction: str
    lifecycle_tags: tuple[str, ...]


def _source_rows(
    domain: str,
    prefix: str,
    rows: tuple[tuple[str, str, str, str, str], ...],
) -> tuple[SourceSeed, ...]:
    return tuple(
        SourceSeed(
            source_id=f"v18_{prefix}_{index:02d}",
            domain=domain,
            publisher=publisher,
            title=title,
            canonical_url=url,
            jurisdiction=jurisdiction,
            lifecycle_tags=_terms(tags),
        )
        for index, (publisher, title, url, jurisdiction, tags) in enumerate(rows, start=1)
    )


SOURCE_SEEDS: tuple[SourceSeed, ...] = (
    *_source_rows(
        "digital_ad_campaign_ops", "ads", (
            ("Google Ads Help", "Google Ads campaign creation guidance", "https://support.google.com/google-ads/answer/13359357?hl=en", "GLOBAL", "campaign|creative|audience"),
            ("Google Ads Help", "Google Ads budget guidance", "https://support.google.com/google-ads/answer/6324971?hl=en", "GLOBAL", "budget|campaign"),
            ("Google Ads Help", "Google Ads conversion guidance", "https://support.google.com/google-ads/answer/6127167?hl=en", "GLOBAL", "conversion|performance"),
            ("Google Ads Help", "Google Ads policy review guidance", "https://support.google.com/google-ads/answer/6372672?hl=en-AUI", "GLOBAL", "policy|creative"),
            ("Google Ads Help", "Google Ads billing guidance", "https://support.google.com/google-ads/answer/7058605?hl=en", "GLOBAL", "billing|access"),
            ("LinkedIn Marketing Solutions Help", "LinkedIn Campaign Manager account guidance", "https://www.linkedin.com/help/lms/answer/a425731", "GLOBAL", "access|campaign|performance"),
            ("LinkedIn Marketing Solutions Help", "LinkedIn campaign lifecycle guidance", "https://www.linkedin.com/help/lms/answer/a9519149", "GLOBAL", "campaign|audience|creative|budget"),
            ("NAVER Search Ads", "NAVER Search Ads advertiser service", "https://gfa.naver.com/", "KR", "all"),
            ("NAVER Help", "NAVER advertising account help", "https://help.naver.com/service/19459/contents/21263?lang=ko", "KR", "access|campaign|billing"),
        ),
    ),
    *_source_rows(
        "consumer_device_warranty_repair", "repair", (
            ("Samsung Support", "Samsung consumer support", "https://www.samsung.com/us/support/", "US", "all"),
            ("Samsung Support", "Samsung service and repair", "https://www.samsung.com/us/support/service/", "US", "service|status|estimate|replacement"),
            ("Google Store Help", "Google Store repair process", "https://support.google.com/store/answer/13516446?hl=en", "GLOBAL", "service|shipping|status"),
            ("Google Pixel Help", "Pixel warranty and repair guidance", "https://support.google.com/pixelphone/answer/6160400?hl=en", "GLOBAL", "coverage|service|estimate"),
            ("Google Pixel Help", "Pixel repair preparation", "https://support.google.com/pixelphone/answer/9218411?hl=en", "GLOBAL", "preparation|service"),
            ("Google Pixel Help", "Pixel repair and replacement status", "https://support.google.com/pixelphone/answer/9105064?hl=en", "GLOBAL", "status|replacement|shipping"),
            ("Samsung Electronics Service", "Samsung service-center search", "https://www.samsungsvc.co.kr/reserve/searchCenter", "KR", "service|registration|lookup"),
        ),
    ),
    *_source_rows(
        "higher_education_admissions", "admit", (
            ("Common App", "First-year applicant guidance", "https://www.commonapp.org/apply/first-year-students/", "US", "all"),
            ("Common App", "Common App mobile service", "https://www.commonapp.org/mobile/", "US", "profile|application|status"),
            ("Common App", "Student guides and resources", "https://www.commonapp.org/apply/student-guides-and-resources/", "US", "requirements|essay|supplement|submission|decision"),
            ("Common App", "Recommender guide", "https://www.commonapp.org/counselors-and-recommenders/recommender-guide/", "US", "recommender|authorization|transcript"),
            ("Common App", "How the first-year application works", "https://www.commonapp.org/static/b96ac19f1b082d294afc77aa6a386e01/Resource_FY_HowFYWorks_ENG_2025.10.24.pdf", "US", "profile|application|submission|status"),
            ("Common App", "Application requirements grid", "https://content.commonapp.org/Files/ReqGrid.pdf", "US", "requirements|fee|transcript|supplement"),
            ("Korean Council for University Education", "Korean admissions FAQ", "https://www.adiga.kr/uve/faq/conseFaqView.do?ansBbsId=97315&menuId=PCUVEFAQ1000", "KR", "requirements|submission|status"),
            ("Korea Polytechnics Admissions", "Korea Polytechnics applicant portal", "https://ipsi.kopo.ac.kr/index.do", "KR", "search|application|submission|decision|deposit"),
        ),
    ),
    *_source_rows(
        "social_platform_account_appeals", "appeal", (
            ("X Help", "Suspended X accounts", "https://help.x.com/en/managing-your-account/suspended-x-accounts", "GLOBAL", "suspension|appeal|status"),
            ("X Help", "Locked and limited X accounts", "https://help.x.com/en/managing-your-account/locked-and-limited-accounts", "GLOBAL", "status|identity|restriction"),
            ("X Help", "X enforcement options", "https://help.x.com/en/rules-and-policies/enforcement-options", "GLOBAL", "enforcement|content|restriction"),
            ("X Help", "X account-access appeal form", "https://help.x.com/en/forms/account-access/appeals/redirect", "GLOBAL", "appeal|identity"),
            ("X Help", "X copyright policy and counter process", "https://help.x.com/en/rules-and-policies/copyright-policy", "GLOBAL", "copyright|content"),
            ("TikTok Support", "TikTok content violations and bans", "https://support.tiktok.com/en/safety-hc/account-and-user-safety/content-violations-and-bans", "GLOBAL", "all"),
            ("TikTok Support", "TikTok underage appeals", "https://support.tiktok.com/en/safety-hc/account-and-user-safety/underage-appeals-on-tiktok", "GLOBAL", "age|identity|appeal"),
            ("X Help Korea", "정지된 X 계정", "https://help.x.com/ko/managing-your-account/suspended-x-accounts", "KR", "suspension|appeal|status"),
            ("X Help Korea", "잠기거나 제한된 X 계정", "https://help.x.com/ko/managing-your-account/locked-and-limited-accounts", "KR", "identity|restriction|status"),
            ("X Help Korea", "X 계정 접근 이의제기", "https://help.x.com/ko/forms/account-access/appeals/redirect", "KR", "appeal|identity"),
            ("TikTok Support Korea", "TikTok 계정 및 사용자 안전", "https://support.tiktok.com/ko/safety-hc/account-and-user-safety", "KR", "all"),
            ("TikTok Support Korea", "TikTok 게시물 콘텐츠 수준", "https://support.tiktok.com/ko-KR/safety-hc/account-and-user-safety/content-levels-on-tiktok-posts", "KR", "content|restriction"),
        ),
    ),
    *_source_rows(
        "consumer_debt_collection_services", "debt", (
            ("Consumer Financial Protection Bureau", "Debt collection consumer tools", "https://www.consumerfinance.gov/consumer-tools/debt-collection/", "US", "all"),
            ("Consumer Financial Protection Bureau", "Regulation F validation notice rule", "https://www.consumerfinance.gov/rules-policy/regulations/1006/34/", "US", "notice|validation|dispute"),
            ("Consumer Financial Protection Bureau", "Regulation F disputes and requests rule", "https://www.consumerfinance.gov/rules-policy/regulations/1006/38/", "US", "dispute|validation|contact"),
            ("Consumer Financial Protection Bureau", "Debt collector required information", "https://www.consumerfinance.gov/ask-cfpb/what-information-does-a-debt-collector-have-to-give-me-about-the-debt-en-331/", "US", "notice|validation"),
            ("Consumer Financial Protection Bureau", "Collection after a dispute", "https://www.consumerfinance.gov/ask-cfpb/can-a-debt-collector-still-collect-a-debt-after-ive-disputed-it-en-338/", "US", "dispute|payment|offer"),
            ("Consumer Financial Protection Bureau", "Rights when a debt collector calls", "https://www.consumerfinance.gov/consumer-tools/debt-collection/know-your-rights-when-a-debt-collector-calls/", "US", "contact|complaint|legal"),
            ("Federal Trade Commission", "Fair Debt Collection Practices Act text", "https://www.ftc.gov/legal-library/browse/rules/fair-debt-collection-practices-act-text", "US", "notice|contact|complaint|legal"),
            ("Korea Ministry of Government Legislation", "채권의 공정한 추심에 관한 법률", "https://law.go.kr/LSW/lsInfoP.do?ancYnChk=0&lsId=010910", "KR", "notice|contact|complaint|legal"),
            ("Credit Counseling and Recovery Service", "신용회복위원회 채무조정 서비스", "https://www.crss.or.kr/", "KR", "offer|payment|legal"),
        ),
    ),
    *_source_rows(
        "rental_vehicle_trip_services", "rental", (
            ("Enterprise Rent-A-Car", "View, modify, or cancel a reservation", "https://www.enterprise.com/en/reserve/view-modify-cancel.html", "US", "reservation|search"),
            ("Enterprise Rent-A-Car", "Change or cancel a reservation", "https://www.enterprise.com/en/car-rental-faqs/us-reservations/change-cancel-reservation.html", "US", "reservation"),
            ("Enterprise Rent-A-Car", "Rental receipts", "https://www.enterprise.com/en/reserve/receipts.html", "US", "receipt|return"),
            ("Hertz", "Extend a rental", "https://www.hertz.com/pr/es/reservation/extend", "GLOBAL", "active"),
            ("Hertz", "Hertz contact and roadside routes", "https://www5.hertz.com/rentacar/misc/index.jsp?targetPage=USContactUs.jsp", "US", "incident|receipt|active"),
            ("Avis", "View, modify, or cancel a reservation", "https://www.avis.com/en/reservation/view-modify-cancel", "US", "all"),
            ("LOTTE Rent-a-Car", "단기 렌터카 예약 및 결제 안내", "https://m.lotterentacar.net/hp/kor/reservation/shortInfo/pay.do", "KR", "reservation|protection|driver|pickup"),
            ("LOTTE Rent-a-Car", "롯데렌터카 고객 FAQ", "https://www.lotterentacar.net/hp/kor/cs/faq/list.do?faqGroup=C", "KR", "all"),
        ),
    ),
    *_source_rows(
        "airline_passenger_trip_management", "air", (
            ("Delta Air Lines", "Delta help overview", "https://www.delta.com/us/en/need-help/overview", "US", "all"),
            ("Delta Air Lines", "Delta flight support", "https://www.delta.com/us/en/need-help/support-flights", "US", "disruption|refund|reimbursement|complaint"),
            ("Delta Air Lines", "Delta seat and ancillary support", "https://www.delta.com/us/en/need-help/support-seats", "US", "passenger|assistance|ticket"),
            ("Delta Air Lines", "Delta check-in and travel-readiness overview", "https://www.delta.com/us/en/check-in-security/overview", "US", "document|baggage|assistance"),
            ("American Airlines", "Find a ticketed reservation", "https://www.aa.com/reservation/view/find-your-reservation", "US", "ticket|passenger|disruption"),
            ("American Airlines", "American Airlines mobile travel tools", "https://www.aa.com/i18n/travel-info/travel-tools/mobile-and-app.jsp", "US", "baggage|disruption|ticket"),
            ("Korean Air", "대한항공 온라인 체크인 및 여행 준비", "https://www.koreanair.com/contents/plan-your-travel/check-in/self-check-in/online-check-in", "KR", "document|passenger|baggage"),
            ("Korean Air", "대한항공 예약 및 발권 안내", "https://www.koreanair.com/contents/booking/reservation-guide/how-to-book/booking-guide", "KR", "ticket|refund|credit|disruption"),
        ),
    ),
    *_source_rows(
        "home_internet_tv_service", "home_net", (
            ("AT&T", "AT&T equipment return", "https://www.att.com/support/how-to/internet/equipment-return/", "US", "return"),
            ("AT&T", "AT&T internet cancellation policy", "https://www.att.com/support/how-to/cancellation-policy-internet/", "US", "move_cancel|billing"),
            ("AT&T", "AT&T moving service", "https://www.att.com/help/moving/", "US", "move_cancel|installation|order"),
            ("Xfinity", "Xfinity move services FAQ", "https://www.xfinity.com/support/articles/move-services-faqs", "US", "move_cancel|order"),
            ("Xfinity", "Transfer service to a new location", "https://www.xfinity.com/support/articles/transferring-service-to-a-new-location/", "US", "move_cancel|installation"),
            ("Xfinity", "Return Xfinity equipment", "https://www.xfinity.com/support/articles/returning-your-equipment", "US", "return"),
            ("SK Broadband", "B world customer FAQ", "https://www.bworld.co.kr/m/customer/faq/faq.do?menu_id=C01080000", "KR", "all"),
            ("SK Broadband", "신규 인터넷 설치 안내", "https://blog.bworld.co.kr/2026/02/10/new-home-internet-installation-guide/", "KR", "order|installation|equipment"),
            ("SK Broadband", "B world 인터넷 요금 안내", "https://www.bworld.co.kr/product/internet/charge.do?menu_id=P02010200", "KR", "order|billing"),
        ),
    ),
    *_source_rows(
        "consumer_product_recall_remedies", "recall", (
            ("U.S. Consumer Product Safety Commission", "CPSC recalls", "https://www.cpsc.gov/Recalls", "US", "all"),
            ("U.S. Consumer Product Safety Commission", "CPSC safety data", "https://www.cpsc.gov/Data", "US", "search|lookup|incident"),
            ("U.S. Consumer Product Safety Commission", "Report, Search, Protect", "https://www.cpsc.gov/content/Report-Search-Protect-0", "US", "search|alerts|incident"),
            ("U.S. Food and Drug Administration", "FDA recalls and safety alerts", "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts", "US", "search|hazard|remedy"),
            ("U.S. Food and Drug Administration", "FDA recall definitions", "https://www.fda.gov/safety/industry-guidance-recalls/recalls-background-and-definitions", "US", "hazard|remedy"),
            ("National Highway Traffic Safety Administration", "NHTSA vehicle recall lookup", "https://www.nhtsa.gov/recalls", "US", "lookup|repair|status"),
            ("Safety Korea", "제품안전정보센터 리콜 목록", "https://www.safetykorea.kr/recall/fRecallBoard", "KR", "search|lookup|hazard"),
            ("Safety Korea", "제품 리콜 절차 및 조치", "https://www.safetykorea.kr/recall/recallProc02", "KR", "remedy|repair|replacement|refund|disposal"),
            ("Safety Korea", "제품안전 홍보 및 알림", "https://www.safetykorea.kr/news/promote", "KR", "alerts|hazard|incident"),
        ),
    ),
    *_source_rows(
        "school_family_enrollment", "school", (
            ("New York City Public Schools", "How to enroll grade by grade", "https://www.schools.nyc.gov/enrollment/enroll-grade-by-grade/how-to-enroll-one-pager", "US-NY", "enrollment|registration"),
            ("New York City Public Schools", "Family Welcome Centers", "https://www.schools.nyc.gov/enrollment/enrollment-help/family-welcome-centers", "US-NY", "enrollment|placement|transfer"),
            ("New York City Public Schools", "Transfer registration checklist", "https://www.schools.nyc.gov/enrollment/enrollment-help/transfers/registration-checklist", "US-NY", "transfer|registration"),
            ("New York City Public Schools", "NYCSA mobile application", "https://www.schools.nyc.gov/learning/student-journey/nyc-schools-account/nycsa-mobile-application", "US-NY", "account|records|status"),
            ("New York City Public Schools", "Student attendance", "https://www.schools.nyc.gov/school-life/school-environment/attendance", "US-NY", "attendance"),
            ("New York City Public Schools", "Request student records and transcripts", "https://www.schools.nyc.gov/learning/student-journey/student-records-and-transcripts/requesting-student-records-and-transcripts", "US-NY", "records"),
            ("NEIS Parent Service", "나이스 학부모서비스", "https://parents.neis.go.kr/", "KR", "all"),
            ("Seoul Metropolitan Office of Education", "서울시교육청 전학 안내", "https://jbedu.sen.go.kr/CMS/entrance/entrance03/entrance0304/index.html", "KR", "transfer|enrollment"),
            ("Seoul Metropolitan Office of Education", "학생 기록 민원 안내", "https://sbgbedu.sen.go.kr/CMS/civilapp/civilapp08/civilapp0803/civilapp080302/index.html", "KR", "records|transfer"),
        ),
    ),
    *_source_rows(
        "online_marketplace_seller_ops", "seller", (
            ("eBay", "eBay selling help", "https://www.ebay.com/help/selling", "GLOBAL", "all"),
            ("eBay", "eBay Seller Hub", "https://www.ebay.com/help/Selling/Selling_Tools/Seller_Hub?id=4095", "GLOBAL", "store|listing|order|fulfilment|payout"),
            ("eBay", "eBay seller levels and performance standards", "https://www.ebay.com/help/selling/selling/seller-levels-performance-standards?id=4080", "GLOBAL", "performance|dispute"),
            ("eBay", "eBay seller performance policy", "https://www.ebay.com/help/policies/selling-policies/seller-performance-standards?id=4347", "GLOBAL", "performance|dispute"),
            ("eBay", "eBay service metrics", "https://www.ebay.com/help/selling/selling/monitor-service-metrics?id=4785", "GLOBAL", "performance|return|fulfilment"),
            ("Etsy Help", "Etsy shop dashboard", "https://help.etsy.com/hc/en-us/articles/360000343908-How-to-Use-Your-Dashboard-to-Manage-Your-Shop", "GLOBAL", "store|listing|order|performance"),
            ("Etsy Help", "Etsy post-sale order handling", "https://help.etsy.com/hc/en-us/articles/115015710308-What-to-Do-After-You-Sell-an-Item", "GLOBAL", "order|fulfilment|return"),
            ("Etsy Help", "Etsy payment account", "https://help.etsy.com/hc/en-us/articles/115015747228-How-to-Manage-Your-Payment-Account", "GLOBAL", "payout|refund"),
            ("NAVER SmartStore", "스마트스토어 판매자센터", "https://sell.smartstore.naver.com/", "KR", "all"),
            ("NAVER SmartStore Help", "스마트스토어 상품관리 도움말", "https://help.sell.smartstore.naver.com/faq/list.help?rootCategoryId=525", "KR", "listing|inventory"),
            ("NAVER SmartStore Help", "스마트스토어 판매관리 도움말", "https://help.sell.smartstore.naver.com/faq/list.help?categoryId=527", "KR", "order|fulfilment|return"),
            ("NAVER SmartStore Help", "스마트스토어 정산관리 도움말", "https://help.sell.smartstore.naver.com/faq/list.help?categoryId=11085", "KR", "payout|refund"),
            ("NAVER SmartStore", "스마트스토어 판매자 운영정책", "https://safety.smartstore.naver.com/main/rules/safety/credit", "KR", "performance|dispute"),
        ),
    ),
    *_source_rows(
        "gig_worker_account_earnings", "gig", (
            ("Lyft Help", "How to see driver earnings", "https://help.lyft.com/hc/en-us/driver/articles/115013078888-How-to-see-your-earnings", "US", "earnings|payout"),
            ("Lyft Help", "How driver pay works", "https://help.lyft.com/hc/en-us/driver/articles/115013080008-How-driver-pay-works", "US", "earnings|payout"),
            ("Lyft Help", "Lyft driver account guidance", "https://help.lyft.com/hc/en-us/driver/articles/115012926307", "US", "onboarding|documents|account"),
            ("Lyft Help", "Driver and passenger ratings", "https://help.lyft.com/hc/en-us/all/articles/115013079948-Driver-and-passenger-ratings", "US", "standing"),
            ("Lyft Help", "Driver deactivations", "https://help.lyft.com/hc/en-us/all/articles/7366276697-Deactivations", "US", "deactivation|appeal"),
            ("DoorDash Dasher Help", "Dasher earnings statements", "https://help.doordash.com/en-us/dashers/article/dasher-earnings-statements", "US", "earnings|payout"),
            ("DoorDash Dasher Help", "Appeal Dasher account deactivation", "https://help.doordash.com/en-us/dashers/article/how-to-appeal-dasher-account-deactivations", "US", "deactivation|appeal"),
            ("Uber Help", "Appeal a driver account deactivation", "https://help.uber.com/driving-and-delivering/article/appeal-process-my-account-has-been-deactivated?nodeId=423f363a-71b2-4557-92e3-92246b35e5e3", "GLOBAL", "deactivation|appeal"),
            ("Baemin Connect", "배민커넥트 작업자 가입 및 정산 안내", "https://join.baeminconnect.com/", "KR", "all"),
        ),
    ),
)

PUBLISHER_ALLOWLIST = frozenset(seed.publisher for seed in SOURCE_SEEDS)


def normalize_official_url(value: str) -> str:
    parts = urlsplit(value.strip())
    scheme = parts.scheme.casefold()
    host = (parts.hostname or "").casefold()
    if scheme != "https" or not host:
        raise V18CatalogValidationError(f"invalid official source URL: {value}")
    port = parts.port
    netloc = host if port is None or port == 443 else f"{host}:{port}"
    path = posixpath.normpath(parts.path or "/")
    if not path.startswith("/"):
        path = f"/{path}"
    if parts.path.endswith("/") and not path.endswith("/"):
        path = f"{path}/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def _source_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_official_sources() -> tuple[
    dict[str, dict[str, object]],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
]:
    sources: dict[str, dict[str, object]] = {}
    terminal_sources: dict[str, list[str]] = defaultdict(list)
    domain_sources: dict[str, list[str]] = defaultdict(list)
    for seed in SOURCE_SEEDS:
        domain = REVIEWED_BY_DOMAIN[seed.domain]
        terminal_ids = [
            f"{seed.domain}.{feature.key}"
            for feature in domain.features
            if "all" in seed.lifecycle_tags or set(seed.lifecycle_tags).intersection(feature.source_tags)
        ]
        record: dict[str, object] = {
            "source_id": seed.source_id,
            "publisher": seed.publisher,
            "provider_scope": seed.publisher,
            "title": seed.title,
            "canonical_url": seed.canonical_url,
            "normalized_url": normalize_official_url(seed.canonical_url),
            "final_url": seed.canonical_url,
            "retrieved_at": RETRIEVED_AT,
            "collected_on": COLLECTED_ON,
            "evidence_level": "official_primary",
            "verification_status": "accepted",
            "verification_method": "direct official lifecycle URL opened and recorded in the V18 research document",
            "http_status": 200,
            "verified_status": 200,
            "jurisdiction": seed.jurisdiction,
            "domains": [seed.domain],
            "lifecycle_tags": list(seed.lifecycle_tags),
            "terminal_ids": terminal_ids,
            "source_documents": [DESIGN_SOURCE_RELATIVE_PATH],
        }
        record["source_record_sha256"] = _source_digest(record)
        sources[seed.source_id] = record
        domain_sources[seed.domain].append(seed.source_id)
        for terminal_id in terminal_ids:
            terminal_sources[terminal_id].append(seed.source_id)
    return (
        sources,
        {key: _dedupe(values) for key, values in terminal_sources.items()},
        {key: _dedupe(values) for key, values in domain_sources.items()},
    )


OFFICIAL_SOURCES, DOMAIN_TERMINAL_SOURCE_IDS, DOMAIN_SOURCE_IDS = _build_official_sources()
EXPECTED_SOURCE_DISTRIBUTION = {
    domain: len(DOMAIN_SOURCE_IDS[domain]) for domain in sorted(DOMAIN_SOURCE_IDS)
}
KOREAN_TERMINAL_IDS = frozenset(
    terminal_id
    for source in OFFICIAL_SOURCES.values()
    if source["jurisdiction"] == "KR"
    for terminal_id in source["terminal_ids"]
)


def _words(value: str) -> str:
    return " ".join(part for part in value.replace("-", "_").split("_") if part)


def _ko_aliases(domain: DomainSpec, feature: ReviewedFeature) -> tuple[str, ...]:
    provider_terms = (
        KOREAN_DOMAIN_TERMS[domain.domain]
        if f"{domain.domain}.{feature.key}" in KOREAN_TERMINAL_IDS
        else ()
    )
    aliases = _dedupe(
        (
            feature.name_ko,
            f"{feature.name_ko} 보기",
            f"{feature.name_ko} 확인",
            f"{feature.name_ko} 화면",
            f"{feature.name_ko} 메뉴",
            f"{feature.name_ko} 상태",
            f"{feature.name_ko} 상세",
            f"{feature.name_ko} 기록",
            f"{feature.name_ko} 항목",
            f"{domain.root_ko} {feature.name_ko}",
            *provider_terms,
        )
    )
    return tuple(value for value in aliases if re.search(r"[\uac00-\ud7a3]", value))


def _en_aliases(domain: DomainSpec, feature: ReviewedFeature) -> tuple[str, ...]:
    lower = feature.name_en.lower()
    return _dedupe(
        (
            feature.name_en,
            f"view {lower}",
            f"check {lower}",
            f"open {lower}",
            f"find {lower}",
            f"manage {lower}",
            f"{lower} details",
            f"{lower} status",
            f"{lower} screen",
            f"{domain.root_en}: {feature.name_en}",
        )
    )


def _feature_seed(domain: DomainSpec, feature: ReviewedFeature) -> FeatureSeed:
    function_id = f"{domain.domain}.{feature.key}"
    positive = _dedupe(
        (
            feature.goal_ko,
            feature.goal_en,
            feature.purpose_ko,
            feature.purpose_en,
            *feature.roles,
            *feature.assets,
            *feature.states,
            feature.jurisdiction_guard,
        )
    )
    negative = _dedupe(
        (
            "역할 불일치",
            "다른 사람 또는 다른 기록",
            "다른 생명주기 상태",
            "관할 또는 제공자 불명확",
            "권한 거부",
            "오프라인 또는 오래된 정보",
            "wrong role",
            "different person or record",
            "wrong lifecycle state",
            "missing jurisdiction or provider",
            "permission denied",
            "offline or stale data",
            *domain.collision_terms,
            *domain.nearest_existing_domains,
        )
    )
    return F(
        feature.key,
        feature.name_ko,
        feature.name_en,
        "|".join(_ko_aliases(domain, feature)),
        "|".join(_en_aliases(domain, feature)),
        "|".join(positive),
        "|".join(negative),
        "sensitive" if feature.classification == "S" else "submit",
        sources="|".join(DOMAIN_TERMINAL_SOURCE_IDS.get(function_id, ())),
    )


def _group_seed(domain: DomainSpec) -> GroupSeed:
    return G(
        domain.domain,
        domain.root_ko,
        domain.root_en,
        f"{domain.domain}_v18_researched_operations",
        "|".join(_dedupe((domain.root_ko, *domain.roles, *domain.assets, *KOREAN_DOMAIN_TERMS[domain.domain]))),
        "|".join(_dedupe((domain.root_en, *domain.roles, *domain.assets, *domain.states, domain.jurisdiction))),
        "|".join(_dedupe(("역할 불일치", "다른 기록", "생명주기 불명확", "관할 불명확", *domain.collision_terms))),
        "|".join(_dedupe(("wrong role", "different record", "unclear lifecycle", "missing jurisdiction", *domain.nearest_existing_domains))),
        domain.avoid_root,
        "|".join(DOMAIN_SOURCE_IDS[domain.domain]),
        *(_feature_seed(domain, feature) for feature in domain.features),
    )


GROUPS: tuple[GroupSeed, ...] = tuple(_group_seed(domain) for domain in REVIEWED_DOMAINS)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
EXPECTED_DOMAIN_COUNTS = {domain: 20 for domain in sorted(REQUIRED_DOMAINS)}
EXPECTED_DOMAIN_FUNCTION_COUNTS = {domain: 21 for domain in sorted(REQUIRED_DOMAINS)}
NEAREST_EXISTING_DOMAINS = {
    domain.domain: domain.nearest_existing_domains for domain in REVIEWED_DOMAINS
}


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    tags = [value for value in result.get("legacy_tags", []) if value != "v10_reviewed_operations"]
    result["legacy_tags"] = list(_dedupe((*tags, "v18_research_isolated_operations")))
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_root(group))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    ko_aliases = _dedupe(
        (
            domain.root_ko,
            f"{domain.root_ko} 보기",
            f"{domain.root_ko} 화면",
            f"{domain.root_ko} 메뉴",
            f"{domain.root_ko} 안내",
            f"{domain.root_ko} 서비스",
            f"{domain.root_ko} 항목",
            f"{domain.root_ko} 목록",
            f"{domain.root_ko} 도움",
            *KOREAN_DOMAIN_TERMS[group.domain],
        )
    )
    en_aliases = _dedupe(
        (
            domain.root_en,
            f"{domain.root_en} hub",
            f"{domain.root_en} menu",
            f"{domain.root_en} services",
            f"open {domain.root_en.lower()}",
            f"find {domain.root_en.lower()}",
            f"manage {domain.root_en.lower()}",
            f"{domain.root_en} help",
            f"{domain.root_en} destinations",
        )
    )
    result.update(
        {
            "aliases": {"ko-KR": list(ko_aliases), "en-US": list(en_aliases)},
            "automation_policy": "safe_navigation",
            "stop_policy": "continue",
            "risk_level": "low",
            "state_changing": False,
            "user_owned_final_press": False,
            "classification": "H",
            "fail_closed": True,
            "resolution_policy": "fail_closed",
            "requires_explicit_terminal_disambiguation": True,
            "jurisdiction_aliases": {
                "KR": list(KOREAN_DOMAIN_TERMS[group.domain]),
                "provider_scoped": [domain.jurisdiction],
            },
        }
    )
    result["role_hints"] = list(_dedupe((*domain.roles, "authorized domain participant")))
    result["asset_cues"] = list(_dedupe((*domain.assets, f"{domain.root_en} governed record")))
    result["state_cues"] = {
        "lifecycle": list(domain.states),
        "jurisdiction": [domain.jurisdiction, "provider and jurisdiction must be explicit"],
        "missing_dimension": ["missing role", "missing governed asset", "missing state", "missing jurisdiction"],
    }
    result["risk_cues"] = {
        "hub_boundary": [
            "역할·자산·상태·관할 중 하나라도 불명확하면 허브에서 중단",
            "stop on this hub when any role, asset, state, provider, or jurisdiction dimension is missing",
        ],
        "source_boundary": [domain.boundary],
        "collision_neighbors": list(domain.nearest_existing_domains),
    }
    result["source_refs"] = list(DOMAIN_SOURCE_IDS[group.domain])
    result["provider_scopes"] = sorted(
        {str(OFFICIAL_SOURCES[source_id]["provider_scope"]) for source_id in result["source_refs"]}
    )
    return result


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_feature(group, seed))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    feature = REVIEWED_FEATURE_BY_ID[f"{group.domain}.{seed.key}"]
    function_id = str(result["function_id"])
    result.update(
        {
            "aliases": {
                "ko-KR": list(_ko_aliases(domain, feature)),
                "en-US": list(_en_aliases(domain, feature)),
            },
            "automation_policy": "never_auto",
            "stop_policy": "before_action",
            "risk_level": "high",
            "state_changing": feature.classification == "C",
            "consequential": feature.classification == "C",
            "view_only": feature.classification == "S",
            "user_owned_final_press": True,
            "classification": feature.classification,
            "representative_goals": {"ko-KR": feature.goal_ko, "en-US": feature.goal_en},
            "purpose_by_locale": {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en},
            "jurisdiction_aliases": {
                "KR": list(KOREAN_DOMAIN_TERMS[group.domain]) if function_id in KOREAN_TERMINAL_IDS else [],
                "provider_scoped": [feature.jurisdiction_guard],
            },
            "semantic_scope": {
                "roles": list(feature.roles),
                "assets": list(feature.assets),
                "states": list(feature.states),
                "jurisdiction": feature.jurisdiction_guard,
                "safety_boundary": feature.safety_boundary,
            },
        }
    )
    result["role_hints"] = list(feature.roles)
    result["asset_cues"] = list(_dedupe((*feature.assets, feature.name_ko, feature.name_en, _words(feature.key))))
    result["state_cues"] = {
        "lifecycle": list(feature.states),
        "jurisdiction": [feature.jurisdiction_guard, "provider and jurisdiction must be explicit"],
        "wrong_role": ["역할 불일치", "권한 없는 사용자", "wrong role", "role not authorized"],
        "wrong_asset": ["다른 사람 또는 기록", "다른 자산", "wrong person or record", "different asset"],
        "wrong_state": ["다른 생명주기 상태", "현재 상태 불명확", "wrong lifecycle state", "state unclear"],
        "unavailable": ["비활성", "사용 불가", "권한 거부", "disabled", "unavailable", "permission denied"],
        "offline": ["오프라인", "오래된 정보", "offline", "stale data"],
        "hold": ["검토 대기", "법적 보류", "안전 보류", "pending review", "legal hold", "safety hold"],
    }
    result["risk_cues"] = {
        "classification": [
            "S: sensitive or permission-limited view"
            if feature.classification == "S"
            else "C: consequential state change"
        ],
        "role_asset_state_jurisdiction_gate": [
            "권한 역할·정확한 자산·현재 상태·제공자와 관할을 모두 확인",
            "verify authorized role, exact governed asset, current lifecycle state, provider, and jurisdiction",
            "all four routing dimensions are mandatory",
        ],
        "fail_closed": [
            "어느 차원이라도 없거나 충돌하면 도메인 허브에서 중단",
            "stop at the domain hub on any missing or conflicting dimension",
        ],
        "forbidden_terminal_actions": [
            "확인·승인·서명·제출·결제·변경·삭제 자동 실행 금지",
            "never auto-press confirm, approve, sign, submit, pay, publish, change, or delete",
        ],
        "blocked_final_channels": [
            "음성·키보드·딥링크·재시도·접근성 동작으로 최종 행동 우회 금지",
            "no final-action bypass through voice, keyboard, deep link, retry, or accessibility action",
        ],
        "user_boundary": [
            "최종 목적지 동작은 사용자가 직접 수행",
            "the user must perform the final destination action",
        ],
        "user_owned_final_press": ["true", "사용자 소유 최종 누름"],
        "source_boundary": [feature.safety_boundary],
        "collision_neighbors": list(domain.nearest_existing_domains),
    }
    result["source_refs"] = list(DOMAIN_TERMINAL_SOURCE_IDS[function_id])
    result["provider_scopes"] = sorted(
        {str(OFFICIAL_SOURCES[source_id]["provider_scope"]) for source_id in result["source_refs"]}
    )
    return result


def _intent_patterns(domain: DomainSpec, feature: ReviewedFeature) -> dict[str, list[str]]:
    role_ko = "권한 있는 사용자"
    role_en = feature.roles[0]
    asset_en = feature.assets[0]
    state_en = feature.states[0]
    return {
        "ko-KR": list(
            _dedupe(
                (
                    feature.goal_ko,
                    f"{feature.name_ko} 목적지로 안내해 줘",
                    f"{domain.root_ko}에서 {feature.name_ko} 메뉴를 찾아줘",
                    f"{role_ko}로서 {feature.name_ko} 화면을 열고 싶어",
                    f"현재 기록 상태를 확인하고 {feature.name_ko} 위치로 이동해 줘",
                    f"제공자와 관할을 확인한 뒤 {feature.name_ko}을 찾아줘",
                )
            )
        ),
        "en-US": list(
            _dedupe(
                (
                    feature.goal_en,
                    f"Guide me to the {feature.name_en.lower()} destination",
                    f"Find {feature.name_en.lower()} within {domain.root_en.lower()}",
                    f"As {role_en}, open {feature.name_en.lower()}",
                    f"For {asset_en} in state {state_en}, locate {feature.name_en.lower()}",
                    f"After confirming provider and jurisdiction, take me to {feature.name_en.lower()}",
                )
            )
        ),
    }


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v10_build_intent(group, seed))
    result["intent_id"] = f"v18_{group.domain}_{seed.key}"
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v18_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v18_{key[4:]}"] = rule.pop(key)
    domain = REVIEWED_BY_DOMAIN[group.domain]
    feature = REVIEWED_FEATURE_BY_ID[f"{group.domain}.{seed.key}"]
    target = f"{group.domain}.{seed.key}"
    patterns_by_locale = _intent_patterns(domain, feature)
    result["patterns_by_locale"] = patterns_by_locale
    result["patterns"] = [*patterns_by_locale["ko-KR"], *patterns_by_locale["en-US"]]
    result["representative_goal_by_locale"] = {"ko-KR": feature.goal_ko, "en-US": feature.goal_en}
    result["purpose_by_locale"] = {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en}
    governance_terms = [feature.roles[0], feature.assets[0], feature.states[0], feature.jurisdiction_guard]
    result["goal_rules"].append(
        {
            "all_of": governance_terms,
            "none_of": [
                "wrong role",
                "different person or record",
                "wrong lifecycle state",
                "missing jurisdiction or provider",
                "offline or stale data",
            ],
            "score": 0.999,
            "rule_kind": "v18_role_asset_state_jurisdiction_gate",
            "v18_discriminative_keys": [
                key for key in (_runtime_pattern_key(value) for value in governance_terms) if key
            ],
            "v18_required_dimensions": ["authorized_role", "governed_asset", "lifecycle_state", "provider_jurisdiction"],
            "v18_required_dimension_count": 4,
        }
    )
    if target in KOREAN_TERMINAL_IDS:
        result["goal_rules"].append(
            {
                "all_of": [KOREAN_DOMAIN_TERMS[group.domain][0], feature.name_ko],
                "none_of": ["wrong jurisdiction", "다른 제공자"],
                "score": 0.999,
                "rule_kind": "v18_kr_provider_jurisdiction_gate",
                "v18_jurisdiction": "KR",
                "v18_discriminative_keys": [
                    _runtime_pattern_key(KOREAN_DOMAIN_TERMS[group.domain][0]),
                    _runtime_pattern_key(feature.name_ko),
                ],
            }
        )
    peers = [f"{group.domain}.{item.key}" for item in domain.features if item.key != seed.key]
    result["avoid_functions"] = list(
        _dedupe(
            (
                *peers[:3],
                *result.get("avoid_functions", []),
                domain.avoid_root,
                *domain.nearest_existing_domains,
            )
        )
    )
    result["desired_state"] = "user_confirmation_required"
    result["terminal_condition"] = {
        "stop_policy": "stop_before_action",
        "user_owned_final_press": True,
    }
    result["resolution_gate"] = {
        "dimensions": ["authorized_role", "governed_asset", "lifecycle_state", "provider_jurisdiction"],
        "required_dimensions": ["authorized_role", "governed_asset", "lifecycle_state", "provider_jurisdiction"],
        "minimum_positive_dimensions": 4,
        "on_missing_dimension": "fail_closed",
        "fail_closed_to": f"{group.domain}.hub",
    }
    return result


V18_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V18_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)


COLLISION_FAMILIES = tuple(
    (domain.domain, neighbor, domain.collision_terms[index % len(domain.collision_terms)])
    for domain in REVIEWED_DOMAINS
    for index, neighbor in enumerate(domain.nearest_existing_domains)
)


def build_collision_probes() -> tuple[dict[str, object], ...]:
    """Return bilingual fail-closed probes for five nearby existing domains each."""

    probes: list[dict[str, object]] = []
    for family_index, (domain, neighbor, token) in enumerate(COLLISION_FAMILIES):
        spec = REVIEWED_BY_DOMAIN[domain]
        for locale, text in (
            ("ko-KR", f"{spec.root_ko}에서 {token}이라는 말만 있고 역할·자산·상태·관할이 불명확해"),
            ("en-US", f"{token} is ambiguous between {domain} and {neighbor} with no role asset state or jurisdiction"),
        ):
            probes.append(
                {
                    "probe_id": f"v18_collision_{family_index:02d}_{locale}",
                    "locale": locale,
                    "text": text,
                    "expected_function": f"{domain}.hub",
                    "excluded_domain": neighbor,
                    "required_policy": "fail_closed",
                }
            )
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return two positive and four missing-dimension probes per terminal."""

    probes: list[dict[str, object]] = []
    for intent in V18_INTENTS:
        target = str(intent["terminal_function"])
        domain = target.split(".", 1)[0]
        for locale in ("ko-KR", "en-US"):
            probes.append(
                {
                    "kind": "positive",
                    "locale": locale,
                    "text": intent["patterns_by_locale"][locale][0],
                    "expected_function": target,
                }
            )
        for kind, text in (
            ("missing_role", "authorized role is missing"),
            ("missing_asset", "governed asset is missing"),
            ("missing_state", "lifecycle state is missing"),
            ("missing_jurisdiction", "provider and jurisdiction are missing"),
        ):
            probes.append(
                {
                    "kind": kind,
                    "locale": "en-US",
                    "text": f"{target} {text}",
                    "expected_function": f"{domain}.hub",
                    "excluded_function": target,
                }
            )
    return tuple(probes)


def build_state_permission_recovery_matrix() -> tuple[dict[str, object], ...]:
    """Return four terminal recovery interlocks per researched destination."""

    scenarios = (
        ("disabled", "disabled control interlock"),
        ("unavailable_offline", "currently unavailable offline stale data"),
        ("permission_denied", "permission denied for current provider role"),
        ("hold_or_changed_state", "legal safety or provider hold and state changed"),
    )
    probes: list[dict[str, object]] = []
    for function in V18_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text in scenarios:
            probes.append(
                {
                    "probe_id": f"v18_recovery_{len(probes):04d}",
                    "kind": kind,
                    "text": f"{function['name_en']} {text}",
                    "expected_function": f"{function['domain']}.hub",
                    "excluded_function": function["function_id"],
                    "required_policy": "never_auto",
                    "required_stop_policy": "before_action",
                    "required_user_owned_final_press": True,
                }
            )
    return tuple(probes)


def build_role_asset_isolation_matrix() -> tuple[dict[str, object], ...]:
    """Return wrong-role, wrong-asset, and wrong-state isolation probes."""

    scenarios = (
        ("wrong_role", "다른 역할 other unauthorized role"),
        ("wrong_asset", "다른 사람 또는 자산 different person or governed asset"),
        ("wrong_state", "다른 생명주기 상태 different lifecycle state"),
    )
    probes: list[dict[str, object]] = []
    for function in V18_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text in scenarios:
            probes.append(
                {
                    "probe_id": f"v18_isolation_{len(probes):04d}",
                    "kind": kind,
                    "text": f"{function['name_en']} {text}",
                    "expected_function": f"{function['domain']}.hub",
                    "excluded_function": function["function_id"],
                }
            )
    return tuple(probes)


def _verify_source_documents() -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        path = ROOT / relative_path
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        actual[relative_path] = digest
        if digest != expected:
            raise V18CatalogValidationError(
                f"V18 source SHA-256 differs for {relative_path}: expected {expected}, got {digest}"
            )
    return actual


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _layer_digest() -> str:
    payload = {
        "catalog_version": CATALOG_V18_VERSION,
        "reviewed_domains": [asdict(domain) for domain in REVIEWED_DOMAINS],
        "functions": V18_FUNCTIONS,
        "intents": V18_INTENTS,
        "official_sources": OFFICIAL_SOURCES,
        "source_documents": SOURCE_DOCUMENT_METADATA,
        "korean_domain_terms": KOREAN_DOMAIN_TERMS,
        "nearest_existing_domains": NEAREST_EXISTING_DOMAINS,
        "projected_counts": PROJECTED_COUNTS,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


DOCUMENT_DIGESTS = _verify_source_documents()
V18_LAYER_SHA256 = _layer_digest()
EXPECTED_V18_LAYER_SHA256 = "5037b41f24de175d9100a1bcc2c82efa438dfd00abeffaf9018282d797f37d99"
EXPECTED_CLASS_COUNTS = {"S": 126, "C": 114}


def _korean_metadata() -> dict[str, object]:
    return {
        "terms": {domain: list(terms) for domain, terms in sorted(KOREAN_DOMAIN_TERMS.items())},
        "terminal_ids": sorted(KOREAN_TERMINAL_IDS),
        "source_ids": sorted(
            source_id for source_id, source in OFFICIAL_SOURCES.items() if source["jurisdiction"] == "KR"
        ),
        "isolation": "provider- and jurisdiction-specific; Korean menu terms never relabel a non-Korean form",
    }


def _layer_integrity_metadata() -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "sha256": V18_LAYER_SHA256,
        "expected_sha256": EXPECTED_V18_LAYER_SHA256,
        "domains": 12,
        "functions": 252,
        "terminal_functions": 240,
        "intents": 240,
        "official_sources": len(OFFICIAL_SOURCES),
    }


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Return the exact prospective V17 payload, materialized only in memory."""

    return merge_v17_with_base(load_v16_source_base(path))


def _pre_v18_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V18_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V18_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids
    ]
    for key in (
        "official_sources_v18",
        "source_documents_v18",
        "korean_jurisdiction_v18",
        "nearest_domain_collisions_v18",
        "layer_integrity_v18",
    ):
        result.pop(key, None)
    result["catalog_version"] = CATALOG_V17_VERSION
    result["description"] = CATALOG_V17_DESCRIPTION
    return result


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V18_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V18_INTENTS}
    present_functions = {
        str(item["function_id"]): item
        for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item
        for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    metadata_keys = (
        "official_sources_v18",
        "source_documents_v18",
        "korean_jurisdiction_v18",
        "nearest_domain_collisions_v18",
        "layer_integrity_v18",
    )
    has_metadata = any(key in payload for key in metadata_keys)
    if not present_functions and not present_intents and not has_metadata:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V18CatalogValidationError("partial V18 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V18CatalogValidationError("V18 collides with a different function or intent definition")
    if payload.get("official_sources_v18") != OFFICIAL_SOURCES:
        raise V18CatalogValidationError("V18 official-source registry differs")
    if payload.get("source_documents_v18") != SOURCE_DOCUMENT_METADATA:
        raise V18CatalogValidationError("V18 source-document SHA registry differs")
    if payload.get("korean_jurisdiction_v18") != _korean_metadata():
        raise V18CatalogValidationError("V18 Korean-jurisdiction metadata differs")
    if payload.get("nearest_domain_collisions_v18") != {
        key: list(value) for key, value in sorted(NEAREST_EXISTING_DOMAINS.items())
    }:
        raise V18CatalogValidationError("V18 nearest-domain collision registry differs")
    if payload.get("layer_integrity_v18") != _layer_integrity_metadata():
        raise V18CatalogValidationError("V18 layer-integrity metadata differs")
    if payload.get("catalog_version") != CATALOG_V18_VERSION or payload.get("description") != CATALOG_V18_DESCRIPTION:
        raise V18CatalogValidationError("V18 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def _duplicates(values: Iterable[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def _research_direct_urls(source_text: str) -> set[str]:
    values = (match.rstrip(".,;") for match in re.findall(r"https://[^\s]+", source_text))
    return {normalize_official_url(value) for value in values}


def _dimension_keys(values: Iterable[object]) -> frozenset[str]:
    return frozenset(
        key
        for value in values
        for key in (_runtime_pattern_key(str(value)),)
        if key
    )


def _function_semantic_dimensions(function: Mapping[str, object]) -> tuple[
    frozenset[str], frozenset[str], frozenset[str], frozenset[str]
]:
    scope = function.get("semantic_scope", {})
    state_cues = function.get("state_cues", {})
    if not isinstance(scope, Mapping):
        scope = {}
    if not isinstance(state_cues, Mapping):
        state_cues = {}
    roles = scope.get("roles", function.get("role_hints", []))
    assets = scope.get("assets", function.get("asset_cues", []))
    states = scope.get("states", state_cues.get("lifecycle", []))
    jurisdiction = scope.get("jurisdiction", state_cues.get("jurisdiction", []))
    if isinstance(jurisdiction, str):
        jurisdiction = [jurisdiction]
    return (
        _dimension_keys(roles if isinstance(roles, (list, tuple)) else [roles]),
        _dimension_keys(assets if isinstance(assets, (list, tuple)) else [assets]),
        _dimension_keys(states if isinstance(states, (list, tuple)) else [states]),
        _dimension_keys(jurisdiction if isinstance(jurisdiction, (list, tuple)) else [jurisdiction]),
    )


def _has_four_dimension_overlap(
    left: tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]],
    right: tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]],
) -> bool:
    return all(a.intersection(b) for a, b in zip(left, right))


def validate_v18_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate scope, evidence, semantics, fail-closed policy, and V17 isolation."""

    base = load_base_catalog() if base_payload is None else copy.deepcopy(dict(base_payload))
    errors: list[str] = []
    source_path = ROOT / DESIGN_SOURCE_RELATIVE_PATH
    source_text = source_path.read_text(encoding="utf-8")
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"source SHA differs for {relative_path}: {actual}")
    if "\ufffd" in source_text or len(re.findall(r"[\uac00-\ud7a3]", source_text)) < 100:
        errors.append("V18 source document Unicode or Hangul gate differs")
    if V18_LAYER_SHA256 != EXPECTED_V18_LAYER_SHA256:
        errors.append(f"V18 layer SHA differs: {V18_LAYER_SHA256}")

    function_ids = [str(item["function_id"]) for item in V18_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V18_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V18_FUNCTIONS if item["terminal"]}
    domain_terminal_counts = Counter(str(item["domain"]) for item in V18_FUNCTIONS if item["terminal"])
    domain_function_counts = Counter(str(item["domain"]) for item in V18_FUNCTIONS)
    if _duplicates(function_ids) or _duplicates(intent_ids):
        errors.append("V18 contains duplicate function or intent IDs")
    if len(REQUIRED_DOMAINS) != 12 or len(V18_FUNCTIONS) != 252 or len(terminal_ids) != 240 or len(V18_INTENTS) != 240:
        errors.append("V18 requires 12 domains, 12 hubs, 240 terminals, 252 functions, and 240 intents")
    if dict(sorted(domain_terminal_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"V18 terminal counts differ: {dict(sorted(domain_terminal_counts.items()))}")
    if dict(sorted(domain_function_counts.items())) != EXPECTED_DOMAIN_FUNCTION_COUNTS:
        errors.append(f"V18 function counts differ: {dict(sorted(domain_function_counts.items()))}")
    if any(len(domain.nearest_existing_domains) != 5 for domain in REVIEWED_DOMAINS):
        errors.append("V18 requires five nearest existing-domain collisions per domain")

    sensitive = sum(
        bool(item["terminal"]) and item.get("classification") == "S" and item.get("view_only") is True
        and item.get("state_changing") is False
        for item in V18_FUNCTIONS
    )
    consequential = sum(
        bool(item["terminal"]) and item.get("classification") == "C" and item.get("consequential") is True
        and item.get("state_changing") is True
        for item in V18_FUNCTIONS
    )
    if {"S": sensitive, "C": consequential} != EXPECTED_CLASS_COUNTS:
        errors.append(f"V18 S/C counts differ: S={sensitive}, C={consequential}")

    forbidden = {
        "x", "y", "bounds", "coordinate", "coordinates", "package", "package_name",
        "resource_id", "screenshot_hash", "screen_path", "recorded_path", "fixed_ui_path",
        "pixel", "click_sequence", "selector", "xpath",
    }
    hangul = re.compile(r"[\uac00-\ud7a3]")
    functions_by_id = {str(item["function_id"]): item for item in V18_FUNCTIONS}
    reviewed_goals_ko: list[str] = []
    reviewed_goals_en: list[str] = []
    reviewed_purposes_ko: list[str] = []
    reviewed_purposes_en: list[str] = []
    reviewed_scope_signatures: list[tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]]] = []
    for function in V18_FUNCTIONS:
        function_id = str(function["function_id"])
        if _contains_forbidden_key(function, forbidden):
            errors.append(f"{function_id}: forbidden UI-specific key")
        if not function.get("source_refs") or set(function["source_refs"]) - set(OFFICIAL_SOURCES):
            errors.append(f"{function_id}: invalid official source references")
        if len(function["aliases"]["ko-KR"]) < 8 or len(function["aliases"]["en-US"]) < 8:
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if not hangul.search(str(function["name_ko"])) or any(
            not hangul.search(str(alias)) for alias in function["aliases"]["ko-KR"]
        ):
            errors.append(f"{function_id}: Korean name or alias lacks Hangul")
        if not function.get("role_hints") or not function.get("asset_cues") or not function.get("state_cues", {}).get("jurisdiction"):
            errors.append(f"{function_id}: missing role, asset, state, or jurisdiction semantics")
        if not function.get("provider_scopes"):
            errors.append(f"{function_id}: provider scope is empty")
        if function["terminal"]:
            feature = REVIEWED_FEATURE_BY_ID[function_id]
            reviewed_goals_ko.append(feature.goal_ko)
            reviewed_goals_en.append(feature.goal_en)
            reviewed_purposes_ko.append(feature.purpose_ko)
            reviewed_purposes_en.append(feature.purpose_en)
            reviewed_scope_signatures.append(_function_semantic_dimensions(function))
            if function.get("classification") != feature.classification:
                errors.append(f"{function_id}: classification differs")
            if function.get("name_ko") != feature.name_ko or function.get("name_en") != feature.name_en:
                errors.append(f"{function_id}: bilingual name differs")
            if function.get("representative_goals") != {"ko-KR": feature.goal_ko, "en-US": feature.goal_en}:
                errors.append(f"{function_id}: representative goal differs")
            if function.get("purpose_by_locale") != {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en}:
                errors.append(f"{function_id}: terminal purpose differs")
            if (
                not feature.roles
                or not feature.assets
                or not feature.states
                or not feature.jurisdiction_guard
                or not feature.safety_boundary
            ):
                errors.append(f"{function_id}: reviewed role/asset/state/jurisdiction/safety semantics are incomplete")
            if feature.goal_ko == feature.purpose_ko or feature.goal_en.casefold() == feature.purpose_en.casefold():
                errors.append(f"{function_id}: goal and purpose are not independent")
            if (
                function.get("automation_policy") != "never_auto"
                or function.get("stop_policy") != "before_action"
                or function.get("risk_level") != "high"
                or function.get("user_owned_final_press") is not True
                or not function.get("risk_cues", {}).get("source_boundary")
            ):
                errors.append(f"{function_id}: terminal safety boundary differs")
            if set(function["source_refs"]) != set(DOMAIN_TERMINAL_SOURCE_IDS.get(function_id, ())):
                errors.append(f"{function_id}: terminal source mapping differs")
        elif (
            function.get("node_kind") != "hub"
            or function.get("automation_policy") != "safe_navigation"
            or function.get("stop_policy") != "continue"
            or function.get("state_changing") is not False
            or function.get("user_owned_final_press") is not False
            or function.get("fail_closed") is not True
            or function.get("resolution_policy") != "fail_closed"
            or function.get("requires_explicit_terminal_disambiguation") is not True
        ):
            errors.append(f"{function_id}: hub fail-closed policy differs")
    for label, values in (
        ("Korean representative goals", reviewed_goals_ko),
        ("English representative goals", reviewed_goals_en),
        ("Korean purposes", reviewed_purposes_ko),
        ("English purposes", reviewed_purposes_en),
    ):
        if _duplicates(values):
            errors.append(f"V18 contains duplicate {label}")
    if _duplicates(repr(value) for value in reviewed_scope_signatures):
        errors.append("V18 contains duplicate role/asset/state/jurisdiction terminal scopes")

    for intent in V18_INTENTS:
        target = str(intent["terminal_function"])
        feature = REVIEWED_FEATURE_BY_ID[target]
        if str(intent["intent_id"]) != f"v18_{target.replace('.', '_')}":
            errors.append(f"{target}: intent ID differs")
        if intent["patterns_by_locale"]["ko-KR"][0] != feature.goal_ko or intent["patterns_by_locale"]["en-US"][0] != feature.goal_en:
            errors.append(f"{target}: representative patterns differ")
        if any(not hangul.search(str(pattern)) for pattern in intent["patterns_by_locale"]["ko-KR"]):
            errors.append(f"{target}: Korean goal pattern lacks Hangul")
        if len(intent["patterns_by_locale"]["ko-KR"]) < 5 or len(intent["patterns_by_locale"]["en-US"]) < 5:
            errors.append(f"{target}: insufficient independent bilingual patterns")
        if len(set(intent["patterns_by_locale"]["ko-KR"])) != len(intent["patterns_by_locale"]["ko-KR"]) or len(set(intent["patterns_by_locale"]["en-US"])) != len(intent["patterns_by_locale"]["en-US"]):
            errors.append(f"{target}: duplicate bilingual patterns")
        if not any(rule.get("rule_kind") == "v18_role_asset_state_jurisdiction_gate" for rule in intent["goal_rules"]):
            errors.append(f"{target}: missing four-dimension gate")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != target:
            errors.append(f"{target}: route differs")
        if intent.get("terminal_condition") != {"stop_policy": "stop_before_action", "user_owned_final_press": True}:
            errors.append(f"{target}: terminal condition differs")
        gate = intent.get("resolution_gate", {})
        if gate.get("minimum_positive_dimensions") != 4 or gate.get("on_missing_dimension") != "fail_closed" or gate.get("fail_closed_to") != f"{target.split('.', 1)[0]}.hub":
            errors.append(f"{target}: fail-closed resolution gate differs")
        if target not in functions_by_id:
            errors.append(f"{target}: intent target missing")

    normalized_urls: set[str] = set()
    mapped_terminal_union: set[str] = set()
    referenced_source_ids: set[str] = set()
    per_domain_jurisdiction: Counter[tuple[str, str]] = Counter()
    for source_id, source in OFFICIAL_SOURCES.items():
        normalized = normalize_official_url(str(source.get("canonical_url", "")))
        if normalized in normalized_urls:
            errors.append(f"duplicate normalized V18 source URL: {normalized}")
        normalized_urls.add(normalized)
        record_without_hash = {key: value for key, value in source.items() if key != "source_record_sha256"}
        mapped = {str(value) for value in source.get("terminal_ids", [])}
        domain = str(source.get("domains", [""])[0])
        jurisdiction = str(source.get("jurisdiction", ""))
        per_domain_jurisdiction[(domain, "KR" if jurisdiction == "KR" else "NON_KR")] += 1
        if source.get("source_id") != source_id or source.get("normalized_url") != normalized:
            errors.append(f"source identity differs: {source_id}")
        if (
            source.get("verification_status") != "accepted"
            or source.get("evidence_level") != "official_primary"
            or source.get("http_status") != 200
            or source.get("verified_status") != 200
            or source.get("final_url") != source.get("canonical_url")
            or source.get("publisher") not in PUBLISHER_ALLOWLIST
            or source.get("provider_scope") != source.get("publisher")
            or source.get("source_record_sha256") != _source_digest(record_without_hash)
        ):
            errors.append(f"source verification or provider metadata differs: {source_id}")
        if not mapped or not mapped <= terminal_ids:
            errors.append(f"source has empty or invalid terminal mapping: {source_id}")
        mapped_terminal_union.update(mapped)
        for terminal_id in mapped:
            referenced_source_ids.add(source_id)
            if source_id not in DOMAIN_TERMINAL_SOURCE_IDS.get(terminal_id, ()):
                errors.append(f"source reverse mapping differs: {source_id} -> {terminal_id}")
    if len(OFFICIAL_SOURCES) != 110:
        errors.append(f"V18 requires exactly 110 direct official sources; got {len(OFFICIAL_SOURCES)}")
    research_urls = _research_direct_urls(source_text)
    if normalized_urls != research_urls:
        errors.append(
            f"V18 official registry differs from research URLs: registry={len(normalized_urls)}, research={len(research_urls)}"
        )
    if mapped_terminal_union != terminal_ids or set(DOMAIN_TERMINAL_SOURCE_IDS) != terminal_ids:
        errors.append("V18 official source-to-terminal mapping is incomplete")
    if referenced_source_ids != set(OFFICIAL_SOURCES):
        errors.append("V18 official registry has orphan or missing source records")
    if set(DOMAIN_SOURCE_IDS) != REQUIRED_DOMAINS:
        errors.append("V18 domain source registry differs")
    for domain in REQUIRED_DOMAINS:
        if per_domain_jurisdiction[(domain, "NON_KR")] < 5 or per_domain_jurisdiction[(domain, "KR")] < 1:
            errors.append(f"{domain}: requires at least five non-Korean and one Korean official lifecycle source")
    for terminal_id in KOREAN_TERMINAL_IDS:
        function = functions_by_id[terminal_id]
        terms = KOREAN_DOMAIN_TERMS[str(function["domain"])]
        if not set(terms).intersection(function["aliases"]["ko-KR"]):
            errors.append(f"{terminal_id}: lacks Korean provider-scoped menu alias")

    semantic = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    if len(semantic) != 1440 or len(collisions) != 120 or len(recovery) != 960 or len(isolation) != 720:
        errors.append("V18 derived probe cardinality differs")

    try:
        materialized = _materialization_state(base)
    except V18CatalogValidationError as error:
        errors.append(str(error))
        materialized = False
    pre_v18 = _pre_v18_payload(base)
    if (
        pre_v18.get("catalog_version") != CATALOG_V17_VERSION
        or len(pre_v18.get("functions", [])) != BASELINE_COUNTS["functions"]
        or len(pre_v18.get("intents", [])) != BASELINE_COUNTS["intents"]
        or len({str(item["domain"]) for item in pre_v18.get("functions", [])}) != BASELINE_COUNTS["domains"]
    ):
        errors.append("V18 base must be the exact prospective 203-domain V17 payload")
    base_function_ids = {str(item["function_id"]) for item in pre_v18.get("functions", [])}
    base_intent_ids = {str(item["intent_id"]) for item in pre_v18.get("intents", [])}
    base_domains = {str(item["domain"]) for item in pre_v18.get("functions", [])}
    if set(function_ids).intersection(base_function_ids) or set(intent_ids).intersection(base_intent_ids) or REQUIRED_DOMAINS.intersection(base_domains):
        errors.append("V18 IDs or domains collide with the V17-composed baseline")
    nearest_domains = {
        neighbor for values in NEAREST_EXISTING_DOMAINS.values() for neighbor in values
    }
    if not nearest_domains <= base_domains:
        errors.append(
            f"V18 nearest-domain registry contains non-baseline domains: {sorted(nearest_domains - base_domains)}"
        )
    avoid_roots = {domain.avoid_root for domain in REVIEWED_DOMAINS}
    if not avoid_roots <= base_function_ids:
        errors.append(
            f"V18 collision handoffs contain non-baseline roots: {sorted(avoid_roots - base_function_ids)}"
        )
    expected_v17_functions = {str(item["function_id"]): item for item in V17_FUNCTIONS}
    expected_v17_intents = {str(item["intent_id"]): item for item in V17_INTENTS}
    present_v17_functions = {
        str(item["function_id"]): item
        for item in pre_v18.get("functions", [])
        if str(item["function_id"]) in expected_v17_functions
    }
    present_v17_intents = {
        str(item["intent_id"]): item
        for item in pre_v18.get("intents", [])
        if str(item["intent_id"]) in expected_v17_intents
    }
    if present_v17_functions != expected_v17_functions or present_v17_intents != expected_v17_intents:
        errors.append("prospective V17 layer differs before V18")

    base_terminal_dimensions = [
        (str(item["function_id"]), _function_semantic_dimensions(item))
        for item in pre_v18.get("functions", [])
        if item.get("terminal")
    ]
    for function in V18_FUNCTIONS:
        if not function["terminal"]:
            continue
        dimensions = _function_semantic_dimensions(function)
        collisions_found = [
            base_id for base_id, base_dimensions in base_terminal_dimensions
            if dimensions == base_dimensions or _has_four_dimension_overlap(dimensions, base_dimensions)
        ]
        if collisions_found:
            errors.append(
                f"{function['function_id']}: duplicates baseline role/asset/state/jurisdiction scope {collisions_found[:3]}"
            )

    if errors:
        raise V18CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V18_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V18_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_terminal_counts.items())),
        "domain_function_counts": dict(sorted(domain_function_counts.items())),
        "sensitive_reads": sensitive,
        "state_changing": consequential,
        "official_sources": len(OFFICIAL_SOURCES),
        "source_distribution": EXPECTED_SOURCE_DISTRIBUTION,
        "korean_sources": sum(source["jurisdiction"] == "KR" for source in OFFICIAL_SOURCES.values()),
        "source_documents": copy.deepcopy(DOCUMENT_DIGESTS),
        "source_orphans": len(set(OFFICIAL_SOURCES) - referenced_source_ids),
        "layer_sha256": V18_LAYER_SHA256,
        "aliases": sum(len(values) for item in V18_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V18_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V18_INTENTS),
        "semantic_probes": len(semantic),
        "collision_probes": len(collisions),
        "recovery_probes": len(recovery),
        "role_asset_probes": len(isolation),
        "projected_counts": copy.deepcopy(PROJECTED_COUNTS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, non-mutating, idempotent V17+V18 copy."""

    stats = validate_v18_data(base_payload)
    if stats["materialized"]:
        return copy.deepcopy(dict(base_payload))
    merged = _pre_v18_payload(base_payload)
    merged["catalog_version"] = CATALOG_V18_VERSION
    merged["description"] = CATALOG_V18_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V18_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V18_INTENTS)]
    merged["official_sources_v18"] = copy.deepcopy(OFFICIAL_SOURCES)
    merged["source_documents_v18"] = copy.deepcopy(SOURCE_DOCUMENT_METADATA)
    merged["korean_jurisdiction_v18"] = copy.deepcopy(_korean_metadata())
    merged["nearest_domain_collisions_v18"] = {
        key: list(value) for key, value in sorted(NEAREST_EXISTING_DOMAINS.items())
    }
    merged["layer_integrity_v18"] = copy.deepcopy(_layer_integrity_metadata())
    return merged


def main() -> int:
    print(json.dumps(validate_v18_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
