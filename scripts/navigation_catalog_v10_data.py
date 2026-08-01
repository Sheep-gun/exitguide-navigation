from __future__ import annotations

"""Reviewed v10 operational ontology for universal Android navigation.

The layer is intentionally app independent.  Runtime matching data contains
roles, assets, lifecycle states, and safety boundaries, but never packages,
resource IDs, coordinates, screenshots, or recorded paths.  All 218 terminal
destinations are sensitive or consequential and therefore stop before the
final control; the user always owns the final press.
"""

import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse

from navigation_catalog_v9_data import (
    CATALOG_V9_DESCRIPTION,
    CATALOG_V9_VERSION,
    F,
    G,
    FeatureSeed,
    GroupSeed,
    _build_feature as _v9_build_feature,
    _build_intent as _v9_build_intent,
    _build_root as _v9_build_root,
    _cue_key,
    _pre_v9_payload,
    _rule_signature,
    _runtime_pattern_key,
    merge_with_base as merge_v9_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
CATALOG_V10_VERSION = "10.0.0"
COLLECTED_ON = "2026-07-30"
CATALOG_V10_DESCRIPTION = (
    "ExitGuide cross-app function ontology v10: app-agnostic operational "
    "destinations for property, warehouse, maintenance, manufacturing, "
    "laboratory, classroom, legal, restaurant, caregiving, home energy, "
    "genealogy, and procurement workflows; every final press remains user-owned."
)


def _source(publisher: str, title: str, url: str) -> dict[str, object]:
    return {
        "publisher": publisher,
        "title": title,
        "url": url,
        "collected_on": COLLECTED_ON,
        "evidence_level": "official_primary",
        "verified_status": 200,
        "verification_method": "official first-party page reviewed in the v10 coverage audit",
    }


OFFICIAL_SOURCES: dict[str, dict[str, object]] = {
    "doorloop_help": _source(
        "DoorLoop", "Help Center", "https://support.doorloop.com/en/",
    ),
    "propertyware_maintenance": _source(
        "Propertyware", "Rental property maintenance mobile app",
        "https://www.propertyware.com/rental-property-maintenance-mobile-app/",
    ),
    "propertyware_inspections": _source(
        "Propertyware", "Property inspection software",
        "https://www.propertyware.com/property-inspection-software/",
    ),
    "odoo_barcode_receipts": _source(
        "Odoo", "Barcode receipts and deliveries",
        "https://www.odoo.com/documentation/master/applications/inventory_and_mrp/barcode/operations/receipts_deliveries.html",
    ),
    "odoo_barcode_setup": _source(
        "Odoo", "Product and location barcodes",
        "https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/barcode/setup/software.html",
    ),
    "maximo_mobile": _source(
        "IBM", "Maximo Mobile overview",
        "https://www.ibm.com/docs/en/masv-and-l/maximo-manage/cd?topic=overview-maximo-mobile",
    ),
    "maximo_data_flow": _source(
        "IBM", "Maximo Mobile authentication and data flow",
        "https://www.ibm.com/docs/en/masv-and-l/maximo-manage/cd?topic=mobile-maximo-authentication-data-flow",
    ),
    "odoo_work_orders": _source(
        "Odoo", "Manufacturing orders and work orders",
        "https://www.odoo.com/documentation/master/applications/inventory_and_mrp/manufacturing/basic_setup/manufacturing_work_orders.html",
    ),
    "odoo_quality_points": _source(
        "Odoo", "Quality control points",
        "https://www.odoo.com/documentation/master/applications/inventory_and_mrp/quality/quality_management/quality_control_points.html",
    ),
    "benchling_inventory": _source(
        "Benchling", "Create and track samples with Inventory",
        "https://help.benchling.com/hc/en-us/articles/39943809066637-Create-and-track-samples-with-the-Inventory",
    ),
    "benchling_reviews": _source(
        "Benchling", "Notebook review processes",
        "https://help.benchling.com/hc/en-us/articles/9684260674189-Add-auditors-for-Notebook-reviews",
    ),
    "classroom_mobile": _source(
        "Google Classroom Help", "Mobile app FAQ",
        "https://support.google.com/edu/classroom/answer/6118390?hl=en",
    ),
    "classroom_assignments": _source(
        "Google Classroom Help", "Assignment workflow",
        "https://support.google.com/edu/classroom/answer/6020260?hl=en",
    ),
    "clio_mobile": _source(
        "Clio", "Mobile app", "https://help.clio.com/hc/en-150/sections/9036135114395-Mobile-App",
    ),
    "clio_conflicts": _source(
        "Clio", "Conflict checks",
        "https://help.clio.com/hc/en-150/articles/35286010477979-Conflict-Checks-in-Clio-Manage-and-Clio-Grow",
    ),
    "clio_filing": _source(
        "Clio", "File and serve documents and court forms",
        "https://help.clio.com/hc/en-us/articles/35405304545819-File-and-Serve-Documents-and-Court-Forms",
    ),
    "toast_kitchen": _source(
        "Toast", "Kitchen display system",
        "https://support.toasttab.com/en/article/Get-Started-With-the-Kitchen-Display-System?lang=en_US",
    ),
    "toast_void": _source(
        "Toast", "Voiding items, payments, and checks",
        "https://support.toasttab.com/en/article/Voiding-Items-Payments-and-Checks",
    ),
    "toast_split": _source(
        "Toast", "Splitting checks by item",
        "https://support.toasttab.com/en/article/Splitting-Checks-by-Item-1492811097734",
    ),
    "toast_86": _source(
        "Toast", "Marking an item unavailable",
        "https://support.toasttab.com/en/article/86-an-Item",
    ),
    "circlecare": _source(
        "CircleCare", "Family caregiving coordination", "https://circlecare.app/",
    ),
    "lotsa_helping_hands": _source(
        "Lotsa Helping Hands", "Care community coordination", "https://lotsahelpinghands.com/",
    ),
    "lotsa_tasks": _source(
        "Lotsa Helping Hands", "Activities and tasks",
        "https://www.lotsahelpinghands.com/help/pe_activities.html",
    ),
    "energy_mobile": _source(
        "Tesla Energy", "Mobile app for home energy",
        "https://www.tesla.com/support/energy/powerwall/mobile-app/tesla-app-for-energy",
    ),
    "energy_advanced": _source(
        "Tesla Energy", "Advanced energy settings",
        "https://www.tesla.com/support/energy/powerwall/mobile-app/advanced-settings",
    ),
    "enphase_monitoring": _source(
        "Enphase", "Monitor home energy usage",
        "https://enphase.com/learn/home-energy/explore-your-system/monitor-your-energy-usage",
    ),
    "family_tree_mobile": _source(
        "FamilySearch", "Family Tree mobile app",
        "https://www.familysearch.org/en/mobile-apps/family-tree-app",
    ),
    "family_tree_hints": _source(
        "FamilySearch", "Attach record hints in Family Tree",
        "https://www.familysearch.org/en/help/helpcenter/article/how-do-i-attach-record-hints-in-family-tree",
    ),
    "family_tree_memories": _source(
        "FamilySearch", "Preserve family stories with Memories",
        "https://www.familysearch.org/en/help/helpcenter/article/how-do-i-use-familysearch-memories-to-preserve-my-ancestors-life-stories",
    ),
    "ariba_requisitions": _source(
        "SAP", "Mobile requisitions",
        "https://help.sap.com/docs/ARIBA_SHOP_MOB/ab43f274ca6c4acea94aa612efb5c489/529344bfa0d14b6fb83c793955d05895.html?locale=en-US&state=PRODUCTION&version=SHIP",
    ),
    "ariba_mobile_guide": _source(
        "SAP", "Procurement Mobile guide",
        "https://help.sap.com/doc/a98d048991094230a1416d8a17b2c688/2508/en-US/ProcurementMobile_1.pdf",
    ),
    "oracle_procurement": _source(
        "Oracle", "Procurement lifecycle",
        "https://docs.oracle.com/cd/E56614_01/procurementop_gs/OAPRC.pdf",
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
        result.append(F(
            key, name_ko, name_en, ko_aliases, en_aliases,
            positive, negative, mode, sources=sources,
        ))
    return tuple(result)


PROPERTY_ROWS: tuple[FeatureRow, ...] = (
    ("portfolio_switch", "임대 포트폴리오 전환", "Rental portfolio switch", "관리 포트폴리오 바꾸기", "switch managed property portfolio", "sensitive"),
    ("property_unit_search", "임대 부동산·세대 검색", "Rental property and unit search", "관리 건물과 세대 찾기", "find a managed building or unit", "sensitive"),
    ("tenant_owner_directory", "세입자·소유주 명부", "Tenant and owner directory", "임대 관계자 연락처 찾기", "find rental stakeholder contacts", "sensitive"),
    ("rental_application_queue", "임대 신청 대기열", "Rental application queue", "입주 신청 검토 목록", "review pending tenancy applications", "sensitive"),
    ("screening_report", "임대 신청 심사 보고서", "Rental applicant screening report", "신청자 신원·임대 심사 보기", "review applicant tenancy screening", "sensitive"),
    ("application_decision", "임대 신청 승인·거절", "Rental application decision", "입주 신청 결과 확정", "decide a tenancy application", "submit"),
    ("lease_draft_edit", "임대차 계약 초안 편집", "Lease draft editing", "세대 임대 계약서 준비", "prepare a unit lease agreement", "submit"),
    ("lease_send_signature", "임대차 계약 서명 발송", "Send lease for signature", "임대 계약 서명 요청 보내기", "send a lease signature request", "submit"),
    ("move_in_inspection", "입주 점검 기록", "Move-in inspection record", "세대 입주 상태 점검", "record unit condition at move-in", "submit"),
    ("rent_ledger", "임대료 원장", "Rent ledger", "세입자 임대료 잔액 보기", "review tenant rent balance", "sensitive"),
    ("delinquency_notice", "임대료 연체 통지", "Rent delinquency notice", "미납 임대료 안내 발송", "send overdue rent notice", "submit"),
    ("maintenance_request_queue", "임대 수리 요청 대기열", "Rental maintenance request queue", "세입자 수리 요청 목록", "review tenant repair requests", "sensitive"),
    ("work_order_dispatch", "임대 수리 작업지시 배차", "Rental work order dispatch", "세대 수리 기사에게 작업 보내기", "dispatch a unit repair work order", "submit"),
    ("vendor_assignment", "임대 수리 업체 배정", "Rental maintenance vendor assignment", "세대 작업에 외주 업체 지정", "assign a vendor to unit maintenance", "submit"),
    ("security_deposit_ledger", "임대 보증금 원장", "Security deposit ledger", "세입자 보증금 보관 내역", "review tenant deposit custody", "sensitive"),
    ("renewal_offer", "임대차 갱신 제안", "Lease renewal offer", "세입자에게 갱신 조건 보내기", "send lease renewal terms", "submit"),
    ("record_notice_to_vacate", "퇴거 예정 통지 기록", "Record notice to vacate", "세입자 퇴거 의사 등록", "record tenant move-out notice", "submit"),
    ("move_out_inspection", "퇴거 점검 기록", "Move-out inspection record", "세대 퇴거 상태 점검", "record unit condition at move-out", "submit"),
    ("owner_statement", "임대 소유주 정산서", "Property owner statement", "소유주 수입·비용 명세 보기", "review owner income and expense statement", "sensitive"),
    ("owner_distribution", "임대 소유주 배분금", "Property owner distribution", "소유주 정산금 지급 확정", "confirm owner fund distribution", "submit"),
)

WAREHOUSE_ROWS: tuple[FeatureRow, ...] = (
    ("site_zone_switch", "창고·구역 전환", "Warehouse and zone switch", "작업 창고 위치 바꾸기", "switch warehouse work location", "sensitive"),
    ("inbound_receipt_queue", "입고 예정 대기열", "Inbound receipt queue", "도착 예정 납품 목록", "review expected inbound deliveries", "sensitive"),
    ("barcode_item_location_scan", "품목·위치 바코드 스캔", "Item and location barcode scan", "상품과 보관 위치 식별", "identify stock and storage location", "sensitive"),
    ("receive_goods", "창고 물품 입고 확정", "Receive warehouse goods", "납품 수량 입고 처리", "confirm inbound goods quantity", "submit"),
    ("lot_serial_capture", "로트·일련번호 등록", "Lot and serial capture", "입고 추적 번호 기록", "record inbound traceability identifiers", "submit"),
    ("quality_hold_quarantine", "재고 품질 보류·격리", "Inventory quality hold and quarantine", "문제 재고를 격리 상태로 변경", "place suspect inventory in quarantine", "submit"),
    ("putaway_confirm", "창고 적치 확정", "Warehouse putaway confirmation", "입고품 보관 위치 확정", "confirm received stock storage bin", "submit"),
    ("inventory_lookup", "창고 재고 조회", "Warehouse inventory lookup", "품목별 가용 수량 찾기", "find available stock by item", "sensitive"),
    ("bin_transfer", "창고 빈 간 재고 이동", "Warehouse bin transfer", "출발·도착 위치로 재고 옮기기", "move stock between source and destination bins", "submit"),
    ("cycle_count", "창고 순환 실사", "Warehouse cycle count", "보관 위치 실수량 확정", "confirm physical quantity at a bin", "submit"),
    ("inventory_adjustment", "창고 재고 조정", "Warehouse inventory adjustment", "장부 수량 증감 반영", "adjust recorded stock quantity", "submit"),
    ("replenishment_task", "피킹 위치 보충 작업", "Picking location replenishment", "예비 재고를 피킹 빈으로 보충", "replenish a picking bin from reserve stock", "submit"),
    ("wave_release", "출고 피킹 웨이브 해제", "Fulfillment wave release", "주문 묶음을 피킹 작업으로 공개", "release an order wave for picking", "submit"),
    ("pick_task", "창고 피킹 작업", "Warehouse pick task", "출고 주문 품목 위치 보기", "review items and bins for an outbound pick", "sensitive"),
    ("pick_confirm", "창고 피킹 확정", "Warehouse pick confirmation", "주문 품목 수집 완료 기록", "confirm picked order quantity", "submit"),
    ("pack_order", "출고 주문 포장", "Pack fulfillment order", "피킹 주문을 포장 완료 처리", "confirm packing of a picked order", "submit"),
    ("shipping_label", "출고 운송 라벨", "Outbound shipping label", "포장 주문 배송 라벨 발행", "issue a carrier label for a package", "submit"),
    ("carrier_handoff", "운송사 인계 확정", "Carrier handoff confirmation", "출고 화물을 운송사에 전달", "confirm shipment handoff to carrier", "submit"),
    ("return_receipt", "반품 입고 확정", "Returned goods receipt", "반송 상품 수량과 상태 기록", "record returned item quantity and condition", "submit"),
    ("fulfillment_exception", "출고 예외 처리", "Fulfillment exception handling", "부족·파손·오배송 문제 기록", "resolve shortage damage or mispick exception", "submit"),
)

MAINTENANCE_ROWS: tuple[FeatureRow, ...] = (
    ("site_location_switch", "설비 사업장·위치 전환", "Asset site and location switch", "정비 대상 사업장 바꾸기", "switch maintenance site or location", "sensitive"),
    ("asset_search", "정비 자산 검색", "Maintenance asset search", "설비 번호로 장비 찾기", "find equipment by asset identifier", "sensitive"),
    ("asset_detail", "정비 자산 상세", "Maintenance asset detail", "설비 상태와 이력 보기", "review equipment status and history", "sensitive"),
    ("service_request_create", "설비 서비스 요청 생성", "Create asset service request", "장비 고장·정비 요청 등록", "submit an equipment maintenance request", "submit"),
    ("work_order_queue", "설비 작업지시 대기열", "Asset work order queue", "담당 정비 작업 목록", "review assigned maintenance jobs", "sensitive"),
    ("work_order_detail", "설비 작업지시 상세", "Asset work order detail", "정비 범위와 안전 조건 보기", "review maintenance scope and safety conditions", "sensitive"),
    ("work_order_accept_assign", "설비 작업지시 수락·배정", "Accept or assign asset work order", "정비 작업 담당자 확정", "confirm maintenance job ownership", "submit"),
    ("work_order_start_pause", "설비 작업 시작·일시정지", "Start or pause asset work order", "정비 진행 상태 전환", "change maintenance work progress", "submit"),
    ("inspection_checklist", "설비 검사 체크리스트", "Asset inspection checklist", "필수 점검 결과 제출", "submit required equipment inspection results", "submit"),
    ("preventive_schedule", "설비 예방정비 일정", "Preventive maintenance schedule", "예정된 장비 점검 보기", "review scheduled equipment maintenance", "sensitive"),
    ("meter_reading", "설비 계기값 기록", "Asset meter reading", "장비 누적 계측값 입력", "record equipment meter value", "submit"),
    ("parts_reservation", "정비 부품 예약", "Maintenance parts reservation", "작업지시에 부품 할당", "reserve parts for a work order", "submit"),
    ("labor_time_log", "정비 작업시간 기록", "Maintenance labor time log", "작업지시 실제 공수 입력", "record actual labor for a work order", "submit"),
    ("failure_downtime_report", "설비 고장·정지시간 보고", "Asset failure and downtime report", "장비 고장 원인과 중단시간 기록", "record equipment failure and downtime", "submit"),
    ("photo_attachment", "정비 현장 사진 첨부", "Maintenance photo attachment", "작업지시에 설비 사진 등록", "attach equipment evidence to a work order", "submit"),
    ("work_order_approval", "설비 작업지시 승인", "Asset work order approval", "정비 결과 검토·승인", "approve maintenance work results", "submit"),
    ("work_order_complete_close", "설비 작업지시 완료·종결", "Complete or close asset work order", "정비 작업 최종 종료", "finalize a completed maintenance job", "submit"),
    ("offline_sync", "정비 오프라인 동기화", "Maintenance offline synchronization", "현장 기록 서버 전송", "synchronize offline maintenance records", "submit"),
)

MANUFACTURING_ROWS: tuple[FeatureRow, ...] = (
    ("plant_workcenter_switch", "공장·작업장 전환", "Plant and work-center switch", "생산 대상 라인 바꾸기", "switch production plant or work center", "sensitive"),
    ("production_order_queue", "생산 주문 대기열", "Production order queue", "작업장 제조 지시 목록", "review manufacturing orders at a work center", "sensitive"),
    ("production_order_detail", "생산 주문 상세", "Production order detail", "제조 수량과 공정 보기", "review manufacturing quantity and operations", "sensitive"),
    ("bill_of_materials", "생산 자재명세서", "Manufacturing bill of materials", "제품 구성 부품 보기", "review product component requirements", "sensitive"),
    ("material_availability", "생산 자재 가용성", "Production material availability", "제조 부품 준비 상태 보기", "review component readiness for production", "sensitive"),
    ("lot_serial_traceability", "생산 로트·일련 추적", "Production lot and serial traceability", "제조 배치 계보 보기", "review manufacturing batch genealogy", "sensitive"),
    ("operation_start_pause", "생산 공정 시작·일시정지", "Start or pause production operation", "작업장 공정 상태 전환", "change work-center operation status", "submit"),
    ("material_issue_consume", "생산 자재 투입·소비", "Issue or consume production material", "제조 주문에 부품 사용 기록", "record component consumption for production", "submit"),
    ("production_quantity_report", "생산 수량 실적 보고", "Production quantity report", "양품 제조 수량 입력", "record completed manufacturing quantity", "submit"),
    ("scrap_record", "생산 폐기 기록", "Production scrap record", "불량 자재·제품 폐기량 입력", "record scrapped material or product", "submit"),
    ("downtime_reason", "생산 중단 사유", "Production downtime reason", "작업장 정지 원인 기록", "record work-center downtime cause", "submit"),
    ("quality_check_queue", "생산 품질검사 대기열", "Manufacturing quality check queue", "검사 예정 제품·공정 목록", "review pending product and operation checks", "sensitive"),
    ("quality_measurement", "생산 품질 측정", "Manufacturing quality measurement", "검사값과 허용오차 입력", "record inspection value and tolerance", "submit"),
    ("pass_fail_disposition", "생산 합격·불합격 판정", "Manufacturing pass or fail disposition", "검사 결과 상태 확정", "confirm manufacturing inspection outcome", "submit"),
    ("nonconformance_create", "생산 부적합 생성", "Create manufacturing nonconformance", "품질 결함 사건 등록", "submit a product quality defect", "submit"),
    ("deviation_review", "생산 일탈 검토", "Manufacturing deviation review", "공정 편차와 승인 상태 보기", "review process deviation and approval state", "sensitive"),
    ("corrective_action", "생산 시정조치", "Manufacturing corrective action", "부적합 개선 작업 등록", "record corrective work for a nonconformance", "submit"),
    ("rework_release", "생산 재작업 해제", "Manufacturing rework release", "보류 제품을 재작업으로 전환", "release held product for rework", "submit"),
    ("batch_release_approval", "생산 배치 출하 승인", "Manufacturing batch release approval", "검사 완료 배치 사용 허가", "approve a completed batch for release", "submit"),
    ("production_order_complete", "생산 주문 완료", "Complete production order", "제조 지시 최종 종결", "finalize a manufacturing order", "submit"),
)


LABORATORY_ROWS: tuple[FeatureRow, ...] = (
    ("organization_project_switch", "연구 조직·프로젝트 전환", "Research organization and project switch", "실험 작업공간 바꾸기", "switch laboratory workspace or project", "sensitive"),
    ("notebook_entry_search", "연구노트 항목 검색", "Research notebook entry search", "실험 기록 찾기", "find an experiment notebook record", "sensitive"),
    ("protocol_view", "실험 프로토콜 보기", "Laboratory protocol view", "연구 절차와 단계 확인", "review research procedure and steps", "sensitive"),
    ("experiment_create_edit", "실험 생성·편집", "Create or edit experiment", "연구 실행 계획 작성", "prepare a laboratory experiment run", "submit"),
    ("experiment_run_status", "실험 실행 상태", "Experiment run status", "실험 시작·완료 상태 기록", "record laboratory run lifecycle", "submit"),
    ("entity_registry_search", "연구 개체 등록부 검색", "Research entity registry search", "등록된 생물·화학 개체 찾기", "find a registered research entity", "sensitive"),
    ("sample_container_scan", "연구 시료·용기 스캔", "Research sample and container scan", "바코드로 시료 위치 식별", "identify a sample container by barcode", "sensitive"),
    ("sample_transfer", "연구 시료 이동", "Research sample transfer", "시료를 새 용기·위치로 옮기기", "transfer a sample to another container or location", "submit"),
    ("freezer_box_plate_map", "냉동고·박스·플레이트 지도", "Freezer box and plate map", "시료 보관 위치 격자 보기", "review sample storage position map", "sensitive"),
    ("reagent_inventory", "연구 시약 재고", "Laboratory reagent inventory", "시약 잔량과 만료 상태 보기", "review reagent quantity and expiry", "sensitive"),
    ("instrument_booking", "연구 장비 예약", "Laboratory instrument booking", "분석 장비 사용 시간 확정", "reserve research instrument time", "submit"),
    ("workflow_task_queue", "연구 워크플로 작업 대기열", "Research workflow task queue", "담당 실험 작업 목록", "review assigned laboratory workflow tasks", "sensitive"),
    ("observation_result_record", "연구 관찰·결과 기록", "Research observation and result record", "실험 측정값과 단위 입력", "record experiment observation and units", "submit"),
    ("deviation_event", "연구 일탈 사건", "Research deviation event", "프로토콜 이탈 내용 등록", "record a protocol deviation", "submit"),
    ("entry_submit_review", "연구노트 검토 제출", "Submit research entry for review", "실험 기록을 검토 단계로 보내기", "send a notebook entry to review", "submit"),
    ("entry_approve_reject", "연구노트 승인·거절", "Approve or reject research entry", "검토자가 실험 기록 판정", "decide a reviewed notebook entry", "submit"),
    ("audit_trail", "연구 감사 추적", "Research audit trail", "실험 기록 변경 이력 보기", "review research record change history", "sensitive"),
    ("research_data_export", "연구 데이터 내보내기", "Research data export", "프로젝트 실험 결과 외부 반출", "export project experiment records", "submit"),
)

CLASSROOM_ROWS: tuple[FeatureRow, ...] = (
    ("class_switch", "교사용 수업 전환", "Instructor class switch", "관리할 강좌 바꾸기", "switch the course being taught", "sensitive"),
    ("roster", "교사용 수강생 명단", "Instructor class roster", "강좌 학생 목록 보기", "review enrolled student list", "sensitive"),
    ("student_profile", "교사용 학생 프로필", "Instructor student profile", "수강생 학습 정보 보기", "review a learner profile in class", "sensitive"),
    ("announcement_create_post", "수업 공지 작성·게시", "Create and post class announcement", "강좌 대상 알림 공개", "publish an announcement to a class", "submit"),
    ("class_material_create_post", "수업 자료 작성·게시", "Create and post class material", "강좌 학습 자료 배포", "publish learning material to a course", "submit"),
    ("assignment_create_edit", "교사용 과제 생성·편집", "Create or edit instructor assignment", "수강생 과제 내용 작성", "prepare coursework for students", "submit"),
    ("assignment_schedule_publish", "과제 예약·배포", "Schedule or publish assignment", "과제 공개 시각과 대상 확정", "schedule coursework release to a class", "submit"),
    ("rubric_create_edit", "채점표 생성·편집", "Create or edit grading rubric", "과제 평가 기준 작성", "prepare assignment grading criteria", "submit"),
    ("submission_queue", "교사용 제출물 대기열", "Instructor submission queue", "채점할 학생 과제 목록", "review student work awaiting grading", "sensitive"),
    ("submission_detail", "교사용 제출물 상세", "Instructor submission detail", "학생 과제 내용과 이력 보기", "review submitted student work and history", "sensitive"),
    ("grade_feedback_draft", "점수·피드백 초안", "Grade and feedback draft", "학생 평가 결과 작성", "prepare assessment and feedback for a student", "submit"),
    ("return_submission", "학생 제출물 반환", "Return student submission", "채점한 과제를 학생에게 돌려주기", "return assessed work to the learner", "submit"),
    ("quiz_question_create", "퀴즈 문항 생성", "Create quiz question", "수업 평가 문제 작성", "author an assessment question", "submit"),
    ("attendance_roll_call", "수업 출석 처리", "Class attendance roll call", "학생 출석·결석 기록", "record learner attendance status", "submit"),
    ("discussion_moderation", "수업 토론 관리", "Class discussion moderation", "강좌 게시글 숨김·삭제", "moderate a course discussion", "submit"),
    ("due_date_extension", "과제 마감 연장", "Assignment due-date extension", "학생별 제출 기한 변경", "change coursework deadline for a learner", "submit"),
    ("guardian_message", "학생 보호자 메시지", "Student guardian message", "보호자에게 학습 연락 보내기", "send a course message to a guardian", "submit"),
    ("course_analytics", "교사용 강좌 분석", "Instructor course analytics", "수강생 완료·성취 현황 보기", "review class completion and performance", "sensitive"),
)

LEGAL_ROWS: tuple[FeatureRow, ...] = (
    ("firm_account_switch", "법률 사무소 계정 전환", "Legal firm account switch", "업무 법인·사무소 바꾸기", "switch legal practice workspace", "sensitive"),
    ("matter_search", "법률 사건 검색", "Legal matter search", "의뢰인 사건 번호 찾기", "find a client matter by reference", "sensitive"),
    ("matter_detail", "법률 사건 상세", "Legal matter detail", "사건 당사자와 진행 상태 보기", "review matter parties and lifecycle", "sensitive"),
    ("client_intake_review", "법률 의뢰 접수 검토", "Legal client intake review", "신규 의뢰 정보 확인", "review prospective client intake", "sensitive"),
    ("conflict_check", "법률 이해충돌 확인", "Legal conflict check", "의뢰인·상대방 충돌 검색", "search client and adverse-party conflicts", "sensitive"),
    ("task_deadline_calendar", "법률 업무·기한 달력", "Legal task and deadline calendar", "사건별 법정 기한 보기", "review matter tasks and court deadlines", "sensitive"),
    ("time_entry", "법률 업무시간 기록", "Legal time entry", "사건에 청구 가능 시간 입력", "record billable time to a matter", "submit"),
    ("expense_entry", "법률 사건 비용 기록", "Legal matter expense entry", "사건 관련 지출 입력", "record an expense against a matter", "submit"),
    ("matter_note", "법률 사건 메모", "Legal matter note", "의뢰 사건 내부 기록 추가", "add a privileged internal matter note", "submit"),
    ("document_bundle", "법률 사건 문서 묶음", "Legal matter document bundle", "제출·송달할 사건 파일 보기", "review a matter filing document set", "sensitive"),
    ("secure_client_message", "법률 의뢰인 보안 메시지", "Secure legal client message", "의뢰인에게 기밀 연락 보내기", "send privileged communication to a client", "submit"),
    ("trust_account_ledger", "법률 신탁계좌 원장", "Legal trust account ledger", "의뢰인 예치금 잔액 보기", "review client trust fund balance", "sensitive"),
    ("invoice_draft", "법률 청구서 초안", "Legal invoice draft", "사건 시간·비용 청구 준비", "prepare a matter billing statement", "submit"),
    ("invoice_send", "법률 청구서 발송", "Send legal invoice", "의뢰인에게 사건 청구 전송", "deliver a matter invoice to a client", "submit"),
    ("court_filing_prepare", "법원 제출 준비", "Prepare court filing", "사건 서류와 수수료 검토", "prepare case documents and filing fee", "submit"),
    ("court_filing_submit", "법원 전자 제출", "Submit court filing", "사건 서류를 법원에 접수", "file case documents with a court", "submit"),
    ("settlement_authority_approval", "합의 권한 승인", "Settlement authority approval", "사건 합의 한도와 권한 확정", "approve matter settlement authority", "submit"),
    ("matter_close", "법률 사건 종결", "Close legal matter", "의뢰 사건 최종 종료", "finalize and close a client matter", "submit"),
)

RESTAURANT_ROWS: tuple[FeatureRow, ...] = (
    ("location_shift_switch", "식당 지점·근무조 전환", "Restaurant location and shift switch", "서비스 지점과 영업 시간대 바꾸기", "switch restaurant site and service period", "sensitive"),
    ("floor_table_map", "식당 좌석·테이블 지도", "Restaurant floor and table map", "홀 테이블 상태 보기", "review dining-room table status", "sensitive"),
    ("reservation_book", "식당 예약 장부", "Restaurant reservation book", "예약 손님과 시간 보기", "review booked parties and times", "sensitive"),
    ("waitlist_manage", "식당 대기열 관리", "Restaurant waitlist management", "대기 손님 등록·알림", "manage waiting parties and notifications", "submit"),
    ("table_seat_guest", "식당 손님 착석 처리", "Seat restaurant guest", "대기 팀을 테이블에 배정", "assign a waiting party to a table", "submit"),
    ("open_check_create", "식당 주문 계산서 열기", "Create restaurant open check", "테이블 새 주문서 생성", "open a new dining check for a table", "submit"),
    ("order_item_modifier", "식당 주문 품목·옵션", "Restaurant order item and modifier", "메뉴와 알레르기 옵션 입력", "record menu item and dietary modifier", "submit"),
    ("course_fire_hold", "식당 코스 조리·보류", "Fire or hold restaurant course", "코스 조리 시점 전환", "change kitchen timing for a course", "submit"),
    ("kitchen_ticket_queue", "주방 주문표 대기열", "Kitchen ticket queue", "조리 순서와 준비 상태 보기", "review kitchen preparation queue", "sensitive"),
    ("kitchen_ticket_bump_recall", "주방 주문표 완료·복구", "Bump or recall kitchen ticket", "조리표 완료 처리·되돌리기", "complete or restore a kitchen ticket", "submit"),
    ("item_86_restore", "식당 품절·판매복구", "Mark restaurant item unavailable or restore", "메뉴 판매 중지·재개", "disable or restore menu item availability", "submit"),
    ("transfer_table_check", "식당 테이블·계산서 이동", "Transfer restaurant table or check", "열린 주문을 다른 테이블로 옮기기", "move an open check to another table", "submit"),
    ("split_merge_check", "식당 계산서 분할·병합", "Split or merge restaurant check", "손님별 결제서를 나누거나 합치기", "divide or combine dining checks", "submit"),
    ("comp_discount", "식당 서비스 보상·할인", "Restaurant comp or discount", "주문 금액 감면 적용", "apply an authorized dining adjustment", "submit"),
    ("void_item_check", "식당 품목·계산서 취소", "Void restaurant item or check", "잘못된 주문·결제서 무효화", "void an incorrect order item or check", "submit"),
    ("take_payment", "식당 결제 수취", "Take restaurant payment", "계산서 결제수단 승인", "capture payment for a dining check", "submit"),
    ("tip_adjust", "식당 팁 조정", "Restaurant tip adjustment", "결제 후 팁 금액 반영", "adjust gratuity on a captured payment", "submit"),
    ("shift_review_close", "식당 근무조 검토·마감", "Review and close restaurant shift", "영업조 정산 최종 종료", "finalize restaurant service-period totals", "submit"),
)


CAREGIVING_ROWS: tuple[FeatureRow, ...] = (
    ("care_recipient_switch", "돌봄 대상자 전환", "Care recipient switch", "관리할 가족 돌봄 프로필 바꾸기", "switch the person receiving coordinated care", "sensitive"),
    ("care_circle_members", "돌봄 공동체 구성원", "Care circle members", "가족·보호자·봉사자 목록 보기", "review family caregiver and volunteer members", "sensitive"),
    ("invite_caregiver", "돌봄 제공자 초대", "Invite caregiver", "가족 돌봄 공동체에 구성원 추가", "invite a person into a care circle", "submit"),
    ("care_calendar", "돌봄 일정 달력", "Care coordination calendar", "진료·약·돌봄 작업 일정 보기", "review appointments medication and care tasks", "sensitive"),
    ("appointment_create_edit", "돌봄 일정 생성·편집", "Create or edit care appointment", "대상자 진료·방문 일정 변경", "schedule a recipient appointment or visit", "submit"),
    ("medication_list", "돌봄 대상자 약 목록", "Care recipient medication list", "가족 복용약과 지시 보기", "review recipient medicines and instructions", "sensitive"),
    ("medication_schedule_edit", "돌봄 약 복용 일정 편집", "Edit caregiving medication schedule", "대상자 약 알림 시간 변경", "change recipient medication reminder time", "submit"),
    ("dose_confirmation", "돌봄 약 복용 확인", "Caregiving dose confirmation", "대상자 복용·건너뜀 상태 기록", "record recipient dose taken or skipped", "submit"),
    ("symptom_vitals_log", "돌봄 증상·활력 기록", "Caregiving symptom and vital log", "대상자 상태·측정값 입력", "record recipient symptom or vital measurement", "submit"),
    ("care_task_create_assign", "돌봄 작업 생성·배정", "Create and assign care task", "가족 돌봄 할 일 담당 지정", "assign a caregiving responsibility", "submit"),
    ("care_task_claim_complete", "돌봄 작업 맡기·완료", "Claim or complete care task", "봉사 요청을 맡거나 끝내기", "claim or finish a care request", "submit"),
    ("meal_ride_request", "돌봄 식사·이동 요청", "Care meal or ride request", "대상자 식사·교통 도움 모집", "request meal or transportation assistance", "submit"),
    ("emergency_information", "돌봄 응급 정보", "Care recipient emergency information", "대상자 응급 연락·주의사항 보기", "review recipient emergency contacts and cautions", "sensitive"),
    ("care_contacts", "돌봄 연락처", "Care coordination contacts", "의료진·가족 연락처 보기", "review provider and family contacts", "sensitive"),
    ("care_note_update", "돌봄 기록 업데이트", "Update caregiving note", "대상자 상태 공유 메모 작성", "write a shared recipient care note", "submit"),
    ("document_vault", "돌봄 문서 보관함", "Care document vault", "보험·지시서·기록 문서 보기", "review recipient insurance or directive documents", "sensitive"),
    ("share_access_permissions", "돌봄 공유 권한", "Care sharing permissions", "구성원별 대상자 정보 접근 변경", "change member access to care information", "submit"),
    ("activity_feed", "돌봄 활동 기록", "Care activity feed", "구성원 작업·복용 확인 이력 보기", "review care task and adherence history", "sensitive"),
)

HOME_ENERGY_ROWS: tuple[FeatureRow, ...] = (
    ("energy_site_switch", "주택 에너지 사이트 전환", "Home energy site switch", "관리할 전력 시스템 바꾸기", "switch the managed household energy system", "sensitive"),
    ("live_energy_flow", "실시간 주택 전력 흐름", "Live home energy flow", "태양광·배터리·전력망 흐름 보기", "review live solar battery and grid flow", "sensitive"),
    ("solar_generation", "주택 태양광 발전", "Home solar generation", "현재 태양광 생산량 보기", "review current household solar production", "sensitive"),
    ("home_consumption", "주택 전력 소비", "Home energy consumption", "현재 가정 부하 사용량 보기", "review current household electrical load", "sensitive"),
    ("grid_import_export", "전력망 수입·송전", "Grid import and export", "전력 구매·판매 흐름 보기", "review household grid draw and feed-in", "sensitive"),
    ("battery_state", "주택 배터리 상태", "Home battery state", "충전량과 충방전 상태 보기", "review home storage charge and power state", "sensitive"),
    ("energy_history", "주택 에너지 이력", "Home energy history", "기간별 생산·소비 기록 보기", "review historical household energy activity", "sensitive"),
    ("backup_reserve", "주택 배터리 예비율", "Home battery backup reserve", "정전 대비 잔량 기준 변경", "change stored energy reserved for outage", "submit"),
    ("operating_mode", "주택 에너지 운전 모드", "Home energy operating mode", "자급·시간대·백업 정책 변경", "change household energy operating policy", "submit"),
    ("utility_rate_plan", "주택 전기요금제", "Home utility rate plan", "시간대별 전력 단가 설정", "configure household electricity tariff", "submit"),
    ("grid_charging_setting", "전력망 배터리 충전 설정", "Grid battery charging setting", "계통 전기로 저장장치 충전 허용", "allow home storage charging from grid", "submit"),
    ("energy_export_setting", "주택 전력 송전 설정", "Home energy export setting", "태양광·배터리 계통 판매 변경", "change household power export behavior", "submit"),
    ("storm_watch_status", "폭풍 대비 전력 상태", "Storm-watch energy status", "기상 대비 배터리 충전 보기", "review weather-triggered home backup state", "sensitive"),
    ("off_grid_test", "주택 독립운전 시험", "Home off-grid test", "전력망 분리 백업 시험 시작", "start household islanding backup test", "submit"),
    ("charge_on_solar", "태양광 차량 충전", "Vehicle charging from home solar", "잉여 태양광으로 차량 충전 설정", "configure vehicle charging from excess solar", "submit"),
    ("outage_event_history", "주택 정전 사건 이력", "Home outage event history", "백업 전환과 복구 기록 보기", "review household outage and restoration history", "sensitive"),
)

GENEALOGY_ROWS: tuple[FeatureRow, ...] = (
    ("tree_switch", "가계도 전환", "Family tree switch", "연구할 가족 계보 바꾸기", "switch the family history tree", "sensitive"),
    ("pedigree_view", "가계도 계보 보기", "Family pedigree view", "조상·후손 관계도 열기", "review ancestor and descendant chart", "sensitive"),
    ("person_profile", "가계도 인물 프로필", "Family tree person profile", "계보 인물의 생애 정보 보기", "review a genealogical person record", "sensitive"),
    ("relative_search", "가계도 친족 검색", "Genealogical relative lookup", "계보에서 가족 인물 찾기", "find a relative in ancestry records", "sensitive"),
    ("historical_record_search", "가계도 역사 기록 검색", "Genealogy historical record search", "인물 관련 문서 자료 찾기", "find historical evidence for a person", "sensitive"),
    ("record_hint_review", "가계도 기록 힌트 검토", "Genealogy record hint review", "인물과 후보 자료 비교", "compare a person with suggested historical evidence", "sensitive"),
    ("record_attach_reject", "가계도 기록 연결·거절", "Attach or reject genealogy record", "역사 자료를 인물에 연결·제외", "accept or dismiss a person record hint", "submit"),
    ("source_citation_create", "가계도 출처 인용 생성", "Create genealogy source citation", "인물 사실에 근거 자료 추가", "add evidence citation to a family fact", "submit"),
    ("person_create_edit", "가계도 인물 생성·편집", "Create or edit family tree person", "계보 인물의 생애 정보 변경", "change a genealogical person record", "submit"),
    ("relationship_edit", "가계도 관계 편집", "Edit family tree relationship", "부모·배우자·자녀 연결 변경", "change parent spouse or child relationship", "submit"),
    ("possible_duplicate_review", "가계도 중복 인물 검토", "Review possible duplicate person", "두 계보 인물 기록 비교", "compare potential duplicate family records", "sensitive"),
    ("person_merge", "가계도 인물 병합", "Merge family tree person", "중복 계보 인물 하나로 합치기", "combine duplicate genealogical records", "submit"),
    ("memory_upload_tag", "가계도 추억 업로드·태그", "Upload and tag family memory", "가족 사진·문서를 인물에 연결", "attach a family photo or document to a person", "submit"),
    ("dna_match_list", "가계도 DNA 일치 목록", "Genealogy DNA match list", "유전적 친족 후보 보기", "review genetic relationship candidates", "sensitive"),
    ("tree_privacy_settings", "가계도 공개 범위", "Family tree privacy settings", "생존 인물과 계보 공유 설정 변경", "change visibility of living people and family tree", "submit"),
    ("tree_export_download", "가계도 내보내기", "Family tree export", "계보 인물·관계 데이터 다운로드", "export genealogical people and relationships", "submit"),
)

PROCUREMENT_ROWS: tuple[FeatureRow, ...] = (
    ("organization_cost_center_switch", "구매 조직·원가부서 전환", "Procurement organization and cost-center switch", "구매 책임 조직 바꾸기", "switch purchasing organization and cost center", "sensitive"),
    ("catalog_item_search", "구매 카탈로그 품목 검색", "Procurement catalog item search", "조달 가능한 상품·서비스 찾기", "find an approved product or service", "sensitive"),
    ("supplier_search", "구매 공급업체 검색", "Procurement supplier search", "승인된 납품업체 찾기", "find an approved purchasing supplier", "sensitive"),
    ("purchase_requisition_create", "구매 요청서 생성", "Create purchase requisition", "품목·서비스 조달 요청 작성", "prepare a product or service purchase request", "submit"),
    ("requisition_submit", "구매 요청서 제출", "Submit purchase requisition", "조달 요청을 승인 절차로 보내기", "send a purchase request for approval", "submit"),
    ("approval_inbox", "구매 승인 대기함", "Procurement approval inbox", "검토할 조달 요청 목록", "review purchasing requests awaiting decision", "sensitive"),
    ("requisition_approve_reject", "구매 요청 승인·거절", "Approve or reject purchase requisition", "원가부서 조달 요청 판정", "decide a cost-center purchase request", "submit"),
    ("request_for_quote_create", "구매 견적요청 생성", "Create procurement request for quote", "공급업체에 가격 제안 요청", "invite suppliers to quote a requirement", "submit"),
    ("supplier_quote_compare", "공급업체 견적 비교", "Supplier quote comparison", "가격·조건·납기 제안 비교", "review supplier price terms and delivery", "sensitive"),
    ("supplier_award", "구매 공급업체 선정", "Procurement supplier award", "견적 수주 업체 확정", "award a sourcing event to a supplier", "submit"),
    ("purchase_order_detail", "구매 주문서 상세", "Purchase order detail", "발주 품목·금액·납기 보기", "review ordered items amount and delivery", "sensitive"),
    ("purchase_order_change", "구매 주문서 변경", "Purchase order change", "발주 수량·가격·납기 수정", "change order quantity price or delivery", "submit"),
    ("goods_receipt_match", "구매 물품 수령 확인", "Procurement goods receipt match", "발주서와 입고 수량 대조", "confirm delivered goods against purchase order", "submit"),
    ("service_entry_confirm", "구매 용역 수행 확인", "Procurement service entry confirmation", "발주한 서비스 완료 승인", "confirm delivery of a purchased service", "submit"),
    ("invoice_three_way_match", "구매 송장 삼자 대조", "Procurement invoice three-way match", "발주·수령·청구 일치 상태 보기", "review order receipt and supplier invoice match", "sensitive"),
    ("invoice_exception_resolve", "구매 송장 예외 해결", "Resolve procurement invoice exception", "수량·가격 불일치 처리", "resolve supplier billing discrepancy", "submit"),
    ("supplier_onboarding", "구매 공급업체 등록", "Procurement supplier onboarding", "신규 납품업체 정보·자격 제출", "submit new supplier identity and qualification", "submit"),
    ("supplier_risk_documents", "공급업체 위험 문서", "Supplier risk documents", "보험·규정·심사 자료 보기", "review supplier insurance compliance and screening", "sensitive"),
)


GROUPS: tuple[GroupSeed, ...] = (
    G(
        "property_management_ops", "임대 부동산 운영", "Rental property operations", "rental_property_operations",
        "임대 관리자|임대 세대|세입자|임대차 계약|수리 작업지시|소유주 정산",
        "property manager|rental unit|tenant|lease lifecycle|maintenance work order|owner accounting",
        "입주자 숙소 검색|여행객 예약|개인 청구서", "tenant lodging search|traveler reservation|personal invoice",
        "property.hub", "doorloop_help|propertyware_maintenance|propertyware_inspections",
        *_feature_rows(
            PROPERTY_ROWS,
            sources="doorloop_help|propertyware_maintenance|propertyware_inspections",
            negative="입주 희망자 검색|단기 숙소 예약|일반 거래처 송장|traveler property search|short-stay booking|generic customer invoice",
        ),
    ),
    G(
        "warehouse_fulfillment_ops", "창고 주문이행 운영", "Warehouse fulfillment operations", "warehouse_fulfillment",
        "창고 작업자|보관 위치|재고 품목|입고 수명주기|피킹 작업|출고 화물",
        "warehouse worker|storage bin|stock item|receipt lifecycle|picking task|outbound shipment",
        "소매 계산대|고객 배송조회|회계 영수증", "retail checkout|customer parcel tracking|accounting receipt",
        "merchant_pos_inventory.hub", "odoo_barcode_receipts|odoo_barcode_setup",
        *_feature_rows(
            WAREHOUSE_ROWS,
            sources="odoo_barcode_receipts|odoo_barcode_setup",
            negative="매장 판매 장바구니|택배 수취인 추적|비용 영수증|store sales cart|parcel recipient tracking|expense receipt",
        ),
    ),
    G(
        "maintenance_asset_ops", "설비·자산 정비 운영", "Maintenance and asset operations", "maintenance_asset_operations",
        "정비 기술자|장기 추적 설비|서비스 요청|예방정비|정비 작업지시|검사 체크리스트",
        "maintenance technician|tracked equipment|service request|preventive maintenance|asset work order|inspection checklist",
        "건설 프로젝트|창고 부품 이동|가정 수리 예약", "construction project|warehouse stock movement|home repair booking",
        "field_construction_ops.hub", "maximo_mobile|maximo_data_flow",
        *_feature_rows(
            MAINTENANCE_ROWS,
            sources="maximo_mobile|maximo_data_flow",
            negative="건설 도면·RFI|판매 재고 이동|소비자 수리 기사 예약|construction drawing and RFI|retail inventory transfer|consumer repair appointment",
        ),
    ),
    G(
        "manufacturing_quality_ops", "제조·품질 운영", "Manufacturing and quality operations", "manufacturing_quality_operations",
        "생산 작업자|제조 주문|작업장 공정|자재명세|생산 배치|품질 판정",
        "production operator|manufacturing order|work-center operation|bill of materials|production batch|quality disposition",
        "창고 보관 재고|설비 정비|상품 반품", "warehouse stored stock|asset maintenance|commerce return",
        "warehouse_fulfillment_ops.hub", "odoo_work_orders|odoo_quality_points",
        *_feature_rows(
            MANUFACTURING_ROWS,
            sources="odoo_work_orders|odoo_quality_points",
            negative="창고 로트 이동|설비 고장 수리|소매 상품 폐기|warehouse lot movement|equipment repair|retail item disposal",
        ),
    ),
    G(
        "laboratory_research_ops", "연구실·실험 운영", "Laboratory and research operations", "laboratory_research_operations",
        "연구자|연구 프로젝트|실험 프로토콜|연구 시료|실험 장비|연구노트 검토",
        "researcher|research project|experiment protocol|research sample|laboratory instrument|notebook review",
        "의료 환자 검체|상업 창고 재고|일반 문서 편집", "clinical patient specimen|commercial warehouse stock|generic document editing",
        "documents.hub", "benchling_inventory|benchling_reviews",
        *_feature_rows(
            LABORATORY_ROWS,
            sources="benchling_inventory|benchling_reviews",
            negative="환자 임상 검사|상품 물류 용기|일반 파일 승인|patient clinical test|commercial logistics container|generic file approval",
        ),
    ),
    G(
        "classroom_instructor_ops", "교사용 수업 운영", "Classroom instructor operations", "classroom_instruction_operations",
        "교사|강좌|수강생 명단|교사용 과제|학생 제출물|채점·반환",
        "teacher|course|student roster|instructor assignment|student submission|grading and return",
        "학생 과제 제출|일반 콘텐츠 게시|상거래 반품", "student assignment submission|general content publishing|commerce return",
        "education.hub", "classroom_mobile|classroom_assignments",
        *_feature_rows(
            CLASSROOM_ROWS,
            sources="classroom_mobile|classroom_assignments",
            negative="학습자 과제 소비|소셜 게시물|상품 반환|learner coursework consumption|social post|product return",
        ),
    ),
    G(
        "legal_practice_ops", "법률 실무 운영", "Legal practice operations", "legal_practice_operations",
        "변호사|의뢰인 사건|상대 당사자|법정 기한|신탁계좌|법원 제출",
        "attorney|client matter|adverse party|court deadline|trust account|court filing",
        "앱 이용약관|고객지원 티켓|일반 문서 파일", "application terms|support ticket|generic document file",
        "documents.hub", "clio_mobile|clio_conflicts|clio_filing",
        *_feature_rows(
            LEGAL_ROWS,
            sources="clio_mobile|clio_conflicts|clio_filing",
            negative="개인정보 약관|고객 문의 사건|일반 파일 공유|privacy terms|customer support case|generic file sharing",
        ),
    ),
    G(
        "restaurant_service_ops", "식당 서비스 운영", "Restaurant service operations", "restaurant_service_operations",
        "식당 호스트|홀 테이블|손님 계산서|메뉴 코스|주방 주문표|근무조 마감",
        "restaurant host|dining table|guest check|menu course|kitchen ticket|service shift close",
        "손님 음식 주문|일반 소매 결제|식당 방문 예약", "guest food ordering|generic retail payment|diner reservation booking",
        "food_order.hub", "toast_kitchen|toast_void|toast_split|toast_86",
        *_feature_rows(
            RESTAURANT_ROWS,
            sources="toast_kitchen|toast_void|toast_split|toast_86",
            negative="배달 주문 장바구니|소매 상품 환불|소비자 식당 예약|delivery order cart|retail product refund|consumer restaurant booking",
        ),
    ),
    G(
        "family_caregiving", "가족 돌봄 조정", "Family caregiving coordination", "family_care_coordination",
        "돌봄 대상자|가족 보호자|돌봄 공동체|복용 일정|돌봄 작업|응급 정보",
        "care recipient|family caregiver|care circle|medication schedule|care task|emergency information",
        "본인 건강 기록|병원 법적 대리|보육원 포털", "personal health log|hospital legal proxy|childcare portal",
        "wellbeing.hub", "circlecare|lotsa_helping_hands|lotsa_tasks",
        *_feature_rows(
            CAREGIVING_ROWS,
            sources="circlecare|lotsa_helping_hands|lotsa_tasks",
            negative="본인 운동·증상 기록|의료진 환자 주문|아동 등하원|self fitness and symptom log|provider clinical order|child pickup and drop-off",
        ),
    ),
    G(
        "home_energy_management", "주택 에너지 관리", "Home energy management", "home_energy_management",
        "에너지 시스템 소유자|주택 부하|태양광 설비|가정 배터리|전력망 송수전|정전 백업",
        "energy system owner|household load|solar array|home battery|grid import export|outage backup",
        "전기요금 청구|일반 스마트홈 기기|공용 차량 충전", "utility billing|generic smart-home device|public vehicle charging",
        "utilities.hub", "energy_mobile|energy_advanced|enphase_monitoring",
        *_feature_rows(
            HOME_ENERGY_ROWS,
            sources="energy_mobile|energy_advanced|enphase_monitoring",
            negative="전력회사 계정 청구|가정 조명 자동화|공용 충전 세션|utility account bill|home lighting automation|public charger session",
        ),
    ),
    G(
        "genealogy_family_history", "가계도·가족사 연구", "Genealogy and family history", "genealogy_family_history",
        "가족사 연구자|가계도|계보 인물|역사 기록|출처 인용|유전적 일치",
        "family historian|family tree|genealogical person|historical record|source citation|DNA match",
        "주소록 연락처|소셜 프로필|사진 앨범", "contact directory|social profile|photo album",
        "family_store.hub", "family_tree_mobile|family_tree_hints|family_tree_memories",
        *_feature_rows(
            GENEALOGY_ROWS,
            sources="family_tree_mobile|family_tree_hints|family_tree_memories",
            negative="계정 가족 구성원|데이트 상대 매칭|일반 사진 태그|account family member|dating match|generic photo tag",
        ),
    ),
    G(
        "procurement_supplier_ops", "구매·공급업체 운영", "Procurement and supplier operations", "procurement_supplier_operations",
        "구매 요청자|원가부서 승인자|조달 담당자|공급업체|구매 주문서|삼자 대조",
        "purchase requester|cost-center approver|procurement buyer|supplier|purchase order|three-way match",
        "일반 회계 청구서|창고 입고 실행|소비자 상품 주문", "generic accounting bill|warehouse receiving execution|consumer product order",
        "business_accounting.hub", "ariba_requisitions|ariba_mobile_guide|oracle_procurement",
        *_feature_rows(
            PROCUREMENT_ROWS,
            sources="ariba_requisitions|ariba_mobile_guide|oracle_procurement",
            negative="회계 거래처 장부|창고 피킹 작업|개인 쇼핑 결제|accounting vendor ledger|warehouse picking task|personal shopping checkout",
        ),
    ),
)


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["legacy_tags"] = [
        "v10_reviewed_operations" if value == "v9_cross_domain" else value
        for value in result.get("legacy_tags", [])
    ]
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    return _retag_function(_v9_build_root(group))


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v9_build_feature(group, seed))
    # All v10 terminals are sensitive (S) or consequential (C).  Both classes
    # are user-owned final destinations and must stop before opening/committing.
    result["automation_policy"] = "never_auto"
    result["stop_policy"] = "before_action"
    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues["user_boundary"] = [
        "최종 목적지 버튼은 사용자가 직접 누름",
        "the user must press the final destination button",
    ]
    result["risk_cues"] = risk_cues
    return result


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v9_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v9_", "v10_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v9_", "v10_", 1)
        for key in tuple(rule):
            if key.startswith("v9_"):
                rule[f"v10_{key[3:]}"] = rule.pop(key)
    return result


V10_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V10_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
REQUIRED_FUNCTIONS = frozenset({
    "property_management_ops.application_decision",
    "property_management_ops.owner_distribution",
    "warehouse_fulfillment_ops.quality_hold_quarantine",
    "warehouse_fulfillment_ops.carrier_handoff",
    "maintenance_asset_ops.work_order_complete_close",
    "maintenance_asset_ops.offline_sync",
    "manufacturing_quality_ops.pass_fail_disposition",
    "manufacturing_quality_ops.batch_release_approval",
    "laboratory_research_ops.sample_transfer",
    "laboratory_research_ops.entry_approve_reject",
    "classroom_instructor_ops.grade_feedback_draft",
    "classroom_instructor_ops.guardian_message",
    "legal_practice_ops.court_filing_submit",
    "legal_practice_ops.settlement_authority_approval",
    "restaurant_service_ops.take_payment",
    "restaurant_service_ops.void_item_check",
    "family_caregiving.dose_confirmation",
    "family_caregiving.share_access_permissions",
    "home_energy_management.off_grid_test",
    "home_energy_management.energy_export_setting",
    "genealogy_family_history.person_merge",
    "genealogy_family_history.tree_privacy_settings",
    "procurement_supplier_ops.supplier_award",
    "procurement_supplier_ops.invoice_exception_resolve",
})


class V10CatalogValidationError(ValueError):
    """Raised when v10 cannot be merged without semantic or safety drift."""


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _pre_v10_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V10_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V10_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", [])
        if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", [])
        if str(item["intent_id"]) not in intent_ids
    ]
    result.pop("official_sources_v10", None)
    result["catalog_version"] = CATALOG_V9_VERSION
    result["description"] = CATALOG_V9_DESCRIPTION
    return result


def _ensure_v9(payload: Mapping[str, object]) -> dict[str, object]:
    """Rebuild a clean reviewed v9 layer, discarding derived runtime guards."""

    return merge_v9_with_base(_pre_v9_payload(_pre_v10_payload(payload)))


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Load a clean v9 base whether canonical storage is at v8, v9, or v10."""

    return _ensure_v9(json.loads(path.read_text(encoding="utf-8")))


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V10_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V10_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    if not present_functions and not present_intents and "official_sources_v10" not in payload:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V10CatalogValidationError("partial v10 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V10CatalogValidationError("v10 collides with a different function or intent definition")
    if payload.get("official_sources_v10") != OFFICIAL_SOURCES:
        raise V10CatalogValidationError("v10 official evidence registry differs")
    if payload.get("catalog_version") != CATALOG_V10_VERSION or payload.get("description") != CATALOG_V10_DESCRIPTION:
        raise V10CatalogValidationError("v10 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def validate_v10_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate exact reviewed scope, evidence, safety, and collision freedom."""

    errors: list[str] = []
    function_ids = [str(item["function_id"]) for item in V10_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V10_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V10_FUNCTIONS if bool(item["terminal"])}
    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v10 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v10 intent IDs: {sorted(duplicates)}")
    if len(REQUIRED_DOMAINS) != 12:
        errors.append("v10 must contain exactly twelve reviewed priority domains")
    domain_terminal_counts = Counter(
        str(item["domain"]) for item in V10_FUNCTIONS if bool(item["terminal"])
    )
    expected_domain_counts = {
        "classroom_instructor_ops": 18,
        "family_caregiving": 18,
        "genealogy_family_history": 16,
        "home_energy_management": 16,
        "laboratory_research_ops": 18,
        "legal_practice_ops": 18,
        "maintenance_asset_ops": 18,
        "manufacturing_quality_ops": 20,
        "procurement_supplier_ops": 18,
        "property_management_ops": 20,
        "restaurant_service_ops": 18,
        "warehouse_fulfillment_ops": 20,
    }
    if dict(sorted(domain_terminal_counts.items())) != expected_domain_counts:
        errors.append(
            "v10 domain terminal counts differ from the reviewed 218-destination pack: "
            f"{dict(sorted(domain_terminal_counts.items()))}"
        )
    if len(V10_FUNCTIONS) != 230 or len(terminal_ids) != 218 or len(V10_INTENTS) != 218:
        errors.append("v10 requires exactly 12 hubs, 218 terminals, and 218 intents")
    if missing := REQUIRED_FUNCTIONS - set(function_ids):
        errors.append(f"missing required v10 functions: {sorted(missing)}")

    sensitive_count = sum(
        bool(item["terminal"]) and not bool(item["state_changing"])
        for item in V10_FUNCTIONS
    )
    consequential_count = sum(bool(item["state_changing"]) for item in V10_FUNCTIONS)
    if sensitive_count != 88 or consequential_count != 130:
        errors.append(
            f"v10 requires exactly 88 sensitive reads and 130 state changes; "
            f"got S={sensitive_count}, C={consequential_count}"
        )

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
    if len(OFFICIAL_SOURCES) < 24:
        errors.append("v10 requires at least twenty-four official-primary sources")

    known_sources = set(OFFICIAL_SOURCES)
    used_sources: set[str] = set()
    forbidden_keys = {
        "x", "y", "bounds", "coordinate", "coordinates", "package",
        "package_name", "resource_id", "screenshot_hash", "screen_path", "recorded_path",
    }
    for function in V10_FUNCTIONS:
        function_id = str(function["function_id"])
        aliases = function["aliases"]
        if len(aliases["ko-KR"]) < 8 or len(aliases["en-US"]) < 8:  # type: ignore[index]
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if len(function["positive_context"]) < 6 or len(function["negative_context"]) < 6:
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

        if function["terminal"]:
            if function["automation_policy"] != "never_auto" or function["stop_policy"] != "before_action":
                errors.append(f"{function_id}: unsafe final-destination boundary")
            boundary = " ".join(function["risk_cues"].get("user_boundary", []))  # type: ignore[union-attr]
            if "사용자" not in boundary or "user" not in boundary.casefold() or "press" not in boundary.casefold():
                errors.append(f"{function_id}: explicit user-owned final press is missing")
        elif function["automation_policy"] != "safe_navigation" or function["stop_policy"] != "continue":
            errors.append(f"{function_id}: hub must remain navigation-only")
    if used_sources != known_sources:
        errors.append(f"orphan official sources: {sorted(known_sources - used_sources)}")

    intent_terminals = [str(item["terminal_function"]) for item in V10_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v10 requires exactly one intent per terminal function")
    terminal_by_id = {str(item["function_id"]): item for item in V10_FUNCTIONS}
    for intent in V10_INTENTS:
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
        if intent["desired_state"] != "user_confirmation_required":
            errors.append(f"{intent_id}: terminal intent lacks user confirmation")
        if intent["terminal_condition"]["stop_policy"] != "stop_before_action":  # type: ignore[index]
            errors.append(f"{intent_id}: terminal route does not stop before action")
        if terminal["automation_policy"] != "never_auto":
            errors.append(f"{intent_id}: terminal is not fail-closed")
        for rule in intent["goal_rules"]:
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v10_"):
                errors.append(f"{intent_id}: malformed semantic rule")
            for key in ("v10_discriminative_keys", "v10_negative_context_keys", "v10_positive_context_keys"):
                values = list(rule.get(key, []))
                if values != sorted(dict.fromkeys(values)):
                    errors.append(f"{intent_id}: nondeterministic {key}")

    materialized = False
    if base_payload is not None:
        materialized = _materialization_state(base_payload)
        pre_v10 = _ensure_v9(base_payload)
        base_function_ids = {str(item["function_id"]) for item in pre_v10.get("functions", [])}
        base_intent_ids = {str(item["intent_id"]) for item in pre_v10.get("intents", [])}
        if collisions := sorted(set(function_ids).intersection(base_function_ids)):
            errors.append(f"v10 function IDs collide with v1-v9: {collisions[:12]}")
        if collisions := sorted(set(intent_ids).intersection(base_intent_ids)):
            errors.append(f"v10 intent IDs collide with v1-v9: {collisions[:12]}")

        pattern_owners: dict[str, set[str]] = {}
        for intent in [*pre_v10.get("intents", []), *V10_INTENTS]:
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
            for intent in pre_v10.get("intents", [])
            for rule in intent.get("goal_rules", [])
            if _rule_signature(rule)
        }
        v10_rule_owners: dict[tuple[str, ...], set[str]] = {}
        for intent in V10_INTENTS:
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if signature in base_rule_signatures:
                    errors.append(f"{intent['intent_id']}: goal rule collides with v1-v9")
                v10_rule_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
        shared_rules = {
            signature: sorted(owners) for signature, owners in v10_rule_owners.items()
            if len(owners) > 1
        }
        if shared_rules:
            errors.append(f"v10 goal-rule collisions: {list(shared_rules.items())[:8]}")

    semantic_payload = copy.deepcopy({"functions": V10_FUNCTIONS, "intents": V10_INTENTS})
    for function in semantic_payload["functions"]:
        function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = (
        "com.", "package name", "resource-id", "screen coordinate", "recorded path",
        "doorloop", "propertyware", "odoo", "maximo", "benchling", "google classroom",
        "clio", "toast", "circlecare", "lotsa helping hands", "tesla", "enphase",
        "familysearch", "sap ariba", "oracle procurement",
    )
    if any(
        re.search(rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])", semantic_text)
        for value in forbidden_fragments
    ):
        errors.append("v10 runtime semantics contain an app identity or recorded UI path")

    if errors:
        raise V10CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V10_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V10_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_terminal_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES),
        "aliases": sum(len(values) for item in V10_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V10_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V10_INTENTS),
        "compositional_goal_rules": sum(
            1 for item in V10_INTENTS for rule in item["goal_rules"]
            if rule["rule_kind"] in {"v10_compositional_domain", "v10_consequence_context"}
        ),
        "sensitive_reads": sensitive_count,
        "state_changing": consequential_count,
        "high_risk": sum(item["risk_level"] == "high" for item in V10_FUNCTIONS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, idempotent, fail-closed v9+v10 catalog copy."""

    validate_v10_data(base_payload)
    if _materialization_state(base_payload):
        return copy.deepcopy(dict(base_payload))
    merged = _ensure_v9(base_payload)
    merged["catalog_version"] = CATALOG_V10_VERSION
    merged["description"] = CATALOG_V10_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V10_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V10_INTENTS)]
    merged["official_sources_v10"] = copy.deepcopy(OFFICIAL_SOURCES)
    return merged


def main() -> int:
    print(json.dumps(validate_v10_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
