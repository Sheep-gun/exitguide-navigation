# Navigation ontology coverage gap audit — v10

감사 기준일: 2026-07-30
감사 기준선: v9 반영 후 예상 canonical **107개 도메인, 1,386개 기능, 1,252개 intent**
감사 목적: 특정 앱 이름·패키지·좌표·녹화 경로 없이, 처음 보는 Android 앱에서 재사용할 수 있으면서 v1~v9의 역할·자산·상태 기계와 겹치지 않는 다음 기능 목적지를 고정한다.

> 이 문서는 source-level 설계 감사다. catalog, 코드, 테스트, 독립·sealed fixture는 수정하거나 정답 분석에 사용하지 않았다. 아래 항목은 구현 완료 증거가 아니라 v10 후보 팩의 정확한 계약이다.

## 결론

v10은 아래 12개 도메인을 권장한다. 제안 규모는 정확히 **230개 기능(허브 12개 + terminal 218개), 218개 intent**다. 전부 반영되면 예상 누계는 **119개 도메인, 1,616개 기능, 1,470개 intent**가 된다.

| 우선순위 | 도메인 ID | terminal | 허브 포함 기능 | intent | 핵심 역할 |
|---:|---|---:|---:|---:|---|
| 1 | `property_management_ops` | 20 | 21 | 20 | 임대 관리자·소유주 회계 담당자 |
| 2 | `warehouse_fulfillment_ops` | 20 | 21 | 20 | 입고·피킹·포장·출고 작업자 |
| 3 | `maintenance_asset_ops` | 18 | 19 | 18 | 설비 기술자·검사자·감독자 |
| 4 | `manufacturing_quality_ops` | 20 | 21 | 20 | 생산 작업자·품질 검사자·승인자 |
| 5 | `laboratory_research_ops` | 18 | 19 | 18 | 연구자·실험실 기술자·검토자 |
| 6 | `classroom_instructor_ops` | 18 | 19 | 18 | 교사·조교·교과 관리자 |
| 7 | `legal_practice_ops` | 18 | 19 | 18 | 변호사·법무 보조·청구 담당자 |
| 8 | `restaurant_service_ops` | 18 | 19 | 18 | 호스트·서버·주방·매니저 |
| 9 | `family_caregiving` | 18 | 19 | 18 | 돌봄 대상자·가족 보호자·봉사자 |
| 10 | `home_energy_management` | 16 | 17 | 16 | 주택 에너지 시스템 소유자 |
| 11 | `genealogy_family_history` | 16 | 17 | 16 | 가계도 소유자·연구자·협업자 |
| 12 | `procurement_supplier_ops` | 18 | 19 | 18 | 요청자·승인자·구매자·검수자 |
| **합계** | **12개** | **218** | **230** | **218** | |

선정 기준은 다음과 같다.

1. Android 또는 모바일·태블릿 화면에서 반복적으로 수행되는 실제 목적지인가.
2. v1~v9의 기존 역할·자산·상태 기계만으로 표현하면 오안내 위험이 큰가.
3. 앱 이름 없이 접근성 텍스트, 아이콘, 폼 라벨, 상태 badge만으로 일반화할 가치가 큰가.
4. 잘못된 클릭이 금전·법률·건강·물리 자산·조직 기록에 미치는 영향을 명확한 중단 규칙으로 통제할 수 있는가.
5. 기존 도메인의 단순 동의어가 아니라 독립된 수명주기 객체를 소유하는가.

아래 표기의 `S`는 민감하거나 조직 내부인 조회 목적지, `C`는 외부 상태 변경·기록·제출 목적지다. 모든 `C`는 `terminal=true`, `automation_policy=never_auto`, `stop_policy=before_action`으로 고정하고 최종 클릭을 사용자에게 남긴다. `S`는 명시적 사용자 목적과 현재 역할이 확인된 경우에만 탐색하며, terminal 도달 시 내용을 외부 telemetry에 남기지 않고 종료한다.

## v10 제안 팩 상세

### 1. Property management operations (`property_management_ops`) — 20 terminal

제안 terminal:

1. `portfolio_switch` (S)
2. `property_unit_search` (S)
3. `tenant_owner_directory` (S)
4. `rental_application_queue` (S)
5. `screening_report` (S)
6. `application_decision` (C)
7. `lease_draft_edit` (C)
8. `lease_send_signature` (C)
9. `move_in_inspection` (C)
10. `rent_ledger` (S)
11. `delinquency_notice` (C)
12. `maintenance_request_queue` (S)
13. `work_order_dispatch` (C)
14. `vendor_assignment` (C)
15. `security_deposit_ledger` (S)
16. `renewal_offer` (C)
17. `record_notice_to_vacate` (C)
18. `move_out_inspection` (C)
19. `owner_statement` (S)
20. `owner_distribution` (C)

역할·자산·상태: property manager, leasing agent, maintenance coordinator, owner-accounting 역할을 분리한다. 핵심 자산은 portfolio, property, unit, applicant, tenant, owner, lease, inspection, maintenance request, work order, deposit, distribution이다. 주요 상태는 vacant/occupied/turnover, application pending/screened/approved/denied, lease draft/sent/signed/expiring, work order open/dispatched/completed, ledger current/delinquent다.

충돌 위험: 기존 `property`는 입주 희망자·세입자의 검색, viewing, application, rent payment 흐름이고, `hospitality_host`는 단기 숙박 listing/reservation 흐름이다. `business_accounting`의 customer/vendor/invoice와 이름이 비슷해도 이 도메인은 반드시 property/unit/lease/tenant/owner 문맥을 요구한다. `field_construction_ops.work_orders`와 달리 임대 unit과 tenant request가 소유 객체다.

공식 근거: [DoorLoop Help Center](https://support.doorloop.com/en/)는 properties/units, leases/people, maintenance/work orders, accounting/owner statements를 별도 수명주기로 설명한다. [Propertyware mobile maintenance](https://www.propertyware.com/rental-property-maintenance-mobile-app/)와 [Propertyware mobile inspections](https://www.propertyware.com/property-inspection-software/)는 Android/iOS에서 inspection, work order, vendor, invoice 흐름을 제공한다.

안전 경계: screening 결과는 주거 차별과 신원정보 위험이 있으므로 agent가 승인·거절을 추천하거나 누르지 않는다. application decision, lease 발송, notice, fee·deposit 변경, vendor dispatch, renewal, distribution은 property/unit, 당사자, 금액, 효력일을 보여준 뒤 최종 버튼 전에 멈춘다.

### 2. Warehouse fulfillment operations (`warehouse_fulfillment_ops`) — 20 terminal

제안 terminal:

1. `site_zone_switch` (S)
2. `inbound_receipt_queue` (S)
3. `barcode_item_location_scan` (S)
4. `receive_goods` (C)
5. `lot_serial_capture` (C)
6. `quality_hold_quarantine` (C)
7. `putaway_confirm` (C)
8. `inventory_lookup` (S)
9. `bin_transfer` (C)
10. `cycle_count` (C)
11. `inventory_adjustment` (C)
12. `replenishment_task` (C)
13. `wave_release` (C)
14. `pick_task` (S)
15. `pick_confirm` (C)
16. `pack_order` (C)
17. `shipping_label` (C)
18. `carrier_handoff` (C)
19. `return_receipt` (C)
20. `fulfillment_exception` (C)

역할·자산·상태: receiver, putaway worker, picker, packer, inventory controller, supervisor 역할을 구분한다. 핵심 자산은 warehouse/site, zone/bin/location, SKU, lot, serial, container/package, receipt, transfer, wave, pick, shipment, return이다. 상태는 expected/received/held/put away, available/allocated, released/picked/packed/shipped, returned/damaged/quarantined다.

충돌 위험: `merchant_pos_inventory`는 매장 판매·가격·cash drawer 중심이고, `parcel_courier`는 수취인의 배송 추적 중심이다. `business_accounting.bills`의 receipt와 warehouse goods receipt를 분리한다. `scan`, `receive`, `transfer`, `release`, `return`은 site + stock object + order lifecycle 중 두 축 이상이 없으면 확정하지 않는다.

공식 근거: [Odoo barcode receipts and deliveries](https://www.odoo.com/documentation/master/applications/inventory_and_mrp/barcode/operations/receipts_deliveries.html)는 mobile scanner로 receipt, package, location, quantity, quality check, validation을 처리하는 흐름을 설명한다. [Odoo product and location barcodes](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/barcode/setup/software.html)는 product, packaging, location, lot/serial 식별을 구분한다.

안전 경계: quantity, UoM, lot/serial, source/destination bin, warehouse, order를 확인하기 전에는 재고를 이동·조정하지 않는다. receive, quarantine, putaway, transfer, count 확정, wave release, pick/pack/ship, return은 모두 사용자 최종 클릭이다. barcode가 여러 객체에 매칭되면 추측하지 않고 충돌 목록을 보여준다.

### 3. Maintenance and asset operations (`maintenance_asset_ops`) — 18 terminal

제안 terminal:

1. `site_location_switch` (S)
2. `asset_search` (S)
3. `asset_detail` (S)
4. `service_request_create` (C)
5. `work_order_queue` (S)
6. `work_order_detail` (S)
7. `work_order_accept_assign` (C)
8. `work_order_start_pause` (C)
9. `inspection_checklist` (C)
10. `preventive_schedule` (S)
11. `meter_reading` (C)
12. `parts_reservation` (C)
13. `labor_time_log` (C)
14. `failure_downtime_report` (C)
15. `photo_attachment` (C)
16. `work_order_approval` (C)
17. `work_order_complete_close` (C)
18. `offline_sync` (C)

역할·자산·상태: requester, technician, inspector, planner, supervisor 역할을 분리한다. 핵심 자산은 site, location, asset, meter, service request, work order, job plan, inspection, part reservation, labor actual, failure code다. 상태는 waiting approval/approved/scheduled/waiting material/in progress/paused/completed/closed와 inspection pending/in progress/completed다.

충돌 위험: `field_construction_ops`는 project/site의 도면·RFI·submittal·punch list를 소유하고, 이 도메인은 장기간 추적되는 asset + preventive/corrective work order를 소유한다. `warehouse_fulfillment_ops`의 parts stock은 이동·출고 객체이고, 여기서는 특정 work order의 planned/reserved/used material이다.

공식 근거: [IBM Maximo Mobile overview](https://www.ibm.com/docs/en/masv-and-l/maximo-manage/cd?topic=overview-maximo-mobile)는 technician, inspections, approvals, service requests, assets, meter readings, material/labor actuals를 설명한다. [Maximo Mobile authentication and data flow](https://www.ibm.com/docs/en/masv-and-l/maximo-manage/cd?topic=mobile-maximo-authentication-data-flow)는 offline local data와 복구 후 synchronization 상태를 구분한다.

안전 경계: asset/location 불일치, lockout/permit, 위험 경고, mandatory checklist가 보이면 우회하지 않는다. assign, status start/pause, inspection 완료, meter/labor/parts/failure 기록, approval, close, sync upload는 사용자 최종 클릭이다. offline 상태에서는 오래된 데이터일 수 있음을 표시하고 중복 제출을 막는다.

### 4. Manufacturing and quality operations (`manufacturing_quality_ops`) — 20 terminal

제안 terminal:

1. `plant_workcenter_switch` (S)
2. `production_order_queue` (S)
3. `production_order_detail` (S)
4. `bill_of_materials` (S)
5. `material_availability` (S)
6. `lot_serial_traceability` (S)
7. `operation_start_pause` (C)
8. `material_issue_consume` (C)
9. `production_quantity_report` (C)
10. `scrap_record` (C)
11. `downtime_reason` (C)
12. `quality_check_queue` (S)
13. `quality_measurement` (C)
14. `pass_fail_disposition` (C)
15. `nonconformance_create` (C)
16. `deviation_review` (S)
17. `corrective_action` (C)
18. `rework_release` (C)
19. `batch_release_approval` (C)
20. `production_order_complete` (C)

역할·자산·상태: operator, line lead, quality inspector, quality approver, production supervisor를 분리한다. 핵심 자산은 plant, work center, manufacturing/production order, operation/routing, BOM, component, batch/lot/serial, quality point/check, nonconformance, deviation, corrective action, rework다. 상태는 planned/released/in progress/paused/done, available/consumed/scrapped, pending/pass/fail/hold/rework/released다.

충돌 위험: `warehouse_fulfillment_ops`의 item·lot은 보관·이동 상태이고 여기의 lot은 생산 genealogy와 quality disposition을 가진다. `maintenance_asset_ops`의 downtime은 asset 수리 흐름이고 여기의 downtime은 생산 order/work center 성과 기록이다. `approve`, `release`, `complete`, `scrap`은 대상 객체를 확인하지 않으면 절대 후보를 합치지 않는다.

공식 근거: [Odoo manufacturing orders and work orders](https://www.odoo.com/documentation/master/applications/inventory_and_mrp/manufacturing/basic_setup/manufacturing_work_orders.html)는 start/done, component 이동, quality step, close production 상태를 설명한다. [Odoo quality control points](https://www.odoo.com/documentation/master/applications/inventory_and_mrp/quality/quality_management/quality_control_points.html)는 product·operation별 pass/fail, measure, worksheet와 failure 대응을 구분한다.

안전 경계: 생산 수량, UoM, batch/lot, consumed component, tolerance, disposition, rework 대상, release authority를 확인한다. start/pause, material consume, quantity/scrap/downtime 기록, pass/fail, nonconformance, corrective action, batch release, production close는 모두 사용자 소유다. safety interlock이나 품질 hold를 우회하는 대체 경로는 제시하지 않는다.

### 5. Laboratory research operations (`laboratory_research_ops`) — 18 terminal

제안 terminal:

1. `organization_project_switch` (S)
2. `notebook_entry_search` (S)
3. `protocol_view` (S)
4. `experiment_create_edit` (C)
5. `experiment_run_status` (C)
6. `entity_registry_search` (S)
7. `sample_container_scan` (S)
8. `sample_transfer` (C)
9. `freezer_box_plate_map` (S)
10. `reagent_inventory` (S)
11. `instrument_booking` (C)
12. `workflow_task_queue` (S)
13. `observation_result_record` (C)
14. `deviation_event` (C)
15. `entry_submit_review` (C)
16. `entry_approve_reject` (C)
17. `audit_trail` (S)
18. `research_data_export` (C)

역할·자산·상태: researcher, lab technician, inventory manager, instrument owner, reviewer/auditor 역할을 분리한다. 핵심 자산은 project/folder, notebook entry, protocol, experiment/run, registered entity, sample, container, box/plate/well, freezer/location, reagent, instrument, workflow task, result, review다. 상태는 draft/running/completed/submitted/approved/rejected/reopened, available/reserved/in use/consumed/disposed, stored/transferred다.

충돌 위험: `documents_cloud`의 문서 편집과 달리 notebook entry는 protocol/result/review audit를 가진다. `warehouse_fulfillment_ops`의 container/location은 상업 재고이고 여기서는 sample entity, concentration, volume, plate well, chain of custody가 핵심이다. 의료 환자 specimen 문맥은 `healthcare_provider`로 보내고 연구 sample과 합치지 않는다.

공식 근거: [Benchling Inventory](https://help.benchling.com/hc/en-us/articles/39943809066637-Create-and-track-samples-with-the-Inventory)는 sample, container, box, plate, location, barcode와 transfer를 설명한다. [Benchling review processes](https://help.benchling.com/hc/en-us/articles/9684260674189-Add-auditors-for-Notebook-reviews)는 entry/worksheet의 submit, staged review, approve, reopen, audit trail을 구분한다.

안전 경계: sample ID, container/position, quantity/concentration, project permission, instrument 시간, result 단위, reviewer authority를 확인한다. sample transfer, experiment status, result/deviation 기록, review submit/approve/reject, export는 사용자 최종 클릭이다. 생물안전·임상·규제 경고를 해석해 무시하거나 데이터 값을 생성하지 않는다.

### 6. Classroom instructor operations (`classroom_instructor_ops`) — 18 terminal

제안 terminal:

1. `class_switch` (S)
2. `roster` (S)
3. `student_profile` (S)
4. `announcement_create_post` (C)
5. `class_material_create_post` (C)
6. `assignment_create_edit` (C)
7. `assignment_schedule_publish` (C)
8. `rubric_create_edit` (C)
9. `submission_queue` (S)
10. `submission_detail` (S)
11. `grade_feedback_draft` (C)
12. `return_submission` (C)
13. `quiz_question_create` (C)
14. `attendance_roll_call` (C)
15. `discussion_moderation` (C)
16. `due_date_extension` (C)
17. `guardian_message` (C)
18. `course_analytics` (S)

역할·자산·상태: teacher, co-teacher, teaching assistant, course leader 역할을 학생·보호자 역할과 분리한다. 핵심 자산은 class/course, roster, student, announcement, material, assignment, rubric, submission, grade, quiz, attendance, discussion, guardian communication이다. 상태는 draft/scheduled/published, assigned/turned in/missing/late/graded/returned/resubmitted, present/absent/call later다.

충돌 위험: 기존 `education.assignment_submit`, `grades`, `courses`는 학습자의 소비·제출 흐름이다. 이 도메인은 instructor의 authoring, distribution, grading, return, moderation 권한을 소유한다. `return`은 commerce 환불이 아니라 submission 반환이며, `post`는 creator publication이나 social message가 아니라 특정 class 대상이다.

공식 근거: [Google Classroom mobile app FAQ](https://support.google.com/edu/classroom/answer/6118390?hl=en)는 모바일 교사의 class, announcement, comment, student contact, completion 조회를 설명한다. [Classroom assignment workflow](https://support.google.com/edu/classroom/answer/6020260?hl=en)는 assignment 생성·배포, submission 확인, grade/feedback, return 상태를 구분한다.

안전 경계: 학생 이름, 제출물, 점수, 출석, 보호자 연락은 민감정보다. publish/schedule, grade·feedback 기록, return, attendance, moderation, deadline 변경, guardian message는 class·student·audience·due date를 확인한 뒤 최종 클릭 전에 멈춘다. agent는 점수나 징계 결정을 생성하지 않는다.

### 7. Legal practice operations (`legal_practice_ops`) — 18 terminal

제안 terminal:

1. `firm_account_switch` (S)
2. `matter_search` (S)
3. `matter_detail` (S)
4. `client_intake_review` (S)
5. `conflict_check` (S)
6. `task_deadline_calendar` (S)
7. `time_entry` (C)
8. `expense_entry` (C)
9. `matter_note` (C)
10. `document_bundle` (S)
11. `secure_client_message` (C)
12. `trust_account_ledger` (S)
13. `invoice_draft` (C)
14. `invoice_send` (C)
15. `court_filing_prepare` (C)
16. `court_filing_submit` (C)
17. `settlement_authority_approval` (C)
18. `matter_close` (C)

역할·자산·상태: attorney, paralegal, legal assistant, billing clerk, trust administrator를 분리한다. 핵심 자산은 firm, client/contact, adverse party, matter/case, conflict report, deadline, activity, document bundle, trust ledger, invoice, court filing, settlement authority다. 상태는 intake/open/pending/closed, conflict clear/found/needs review, draft/reviewed/filed/accepted/rejected, unbilled/billed/paid다.

충돌 위험: 기존 `legal`은 terms/privacy/licenses 조회에 가깝고, `documents_cloud`와 `esign_notary`는 일반 문서·서명 흐름이다. 이 도메인은 client-matter privilege, adverse parties, court docket/filing, trust funds를 소유한다. `case`, `matter`, `file`, `serve`, `close`, `trust`는 일반 support ticket·파일·account security와 강하게 분리한다.

공식 근거: [Clio Mobile](https://help.clio.com/hc/en-150/sections/9036135114395-Mobile-App)은 matters, documents, communications, tasks, time/expense, billing을 구분한다. [Clio conflict checks](https://help.clio.com/hc/en-150/articles/35286010477979-Conflict-Checks-in-Clio-Manage-and-Clio-Grow)는 conflict lifecycle을, [Clio File](https://help.clio.com/hc/en-us/articles/35405304545819-File-and-Serve-Documents-and-Court-Forms)은 draft, review/pay, submit, accepted/rejected filing 상태를 설명한다.

안전 경계: attorney-client privileged data, adverse party, deadline, trust balance, settlement amount, filing document와 fee는 고위험 정보다. time/expense/note/message/invoice 기록, filing prepare/submit, settlement approval, matter close는 최종 클릭을 사용자에게 남긴다. 법률 판단, conflict 해소, filing code 선택, settlement 승인 여부를 agent가 결정하지 않는다.

### 8. Restaurant service operations (`restaurant_service_ops`) — 18 terminal

제안 terminal:

1. `location_shift_switch` (S)
2. `floor_table_map` (S)
3. `reservation_book` (S)
4. `waitlist_manage` (C)
5. `table_seat_guest` (C)
6. `open_check_create` (C)
7. `order_item_modifier` (C)
8. `course_fire_hold` (C)
9. `kitchen_ticket_queue` (S)
10. `kitchen_ticket_bump_recall` (C)
11. `item_86_restore` (C)
12. `transfer_table_check` (C)
13. `split_merge_check` (C)
14. `comp_discount` (C)
15. `void_item_check` (C)
16. `take_payment` (C)
17. `tip_adjust` (C)
18. `shift_review_close` (C)

역할·자산·상태: host, server, bartender, kitchen/prep, expediter, manager를 분리한다. 핵심 자산은 location, service period/shift, floor/table, party/reservation/waitlist entry, check, order item/modifier, course, kitchen ticket, payment/tip이다. 상태는 reserved/waiting/notified/seated, open/sent/held/fired/ready/served/paid/closed/voided다.

충돌 위험: `food_ordering`은 손님의 menu/cart/order 흐름이고, `restaurant_booking`은 손님의 예약 흐름이며, `merchant_pos_inventory`는 일반 retail cart/tender/refund다. 여기서는 table/party/check/course/kitchen ticket/shift라는 restaurant-specific lifecycle이 필수다. `close`, `fire`, `bump`, `86`, `comp`의 일반 영어 의미를 강한 negative context로 둔다.

공식 근거: [Toast Kitchen Display System](https://support.toasttab.com/en/article/Get-Started-With-the-Kitchen-Display-System?lang=en_US)은 fired ticket, prep station, expediter, queue 상태를 설명한다. [Toast void workflow](https://support.toasttab.com/en/article/Voiding-Items-Payments-and-Checks), [Toast split checks](https://support.toasttab.com/en/article/Splitting-Checks-by-Item-1492811097734), [Toast 86 item](https://support.toasttab.com/en/article/86-an-Item)은 check/payment/item state transitions와 권한 차이를 보여준다.

안전 경계: table/guest/check ownership, allergen/modifier, course timing, amount, payment method, tip, manager permission을 확인한다. seat, send/fire, bump, 86, transfer, split/merge, comp, void, payment, tip, shift close는 사용자 최종 클릭이다. 결제와 void/refund를 서로 대체하지 않으며 이미 closed/captured인 check에서 위험한 우회 경로를 제시하지 않는다.

### 9. Family caregiving coordination (`family_caregiving`) — 18 terminal

제안 terminal:

1. `care_recipient_switch` (S)
2. `care_circle_members` (S)
3. `invite_caregiver` (C)
4. `care_calendar` (S)
5. `appointment_create_edit` (C)
6. `medication_list` (S)
7. `medication_schedule_edit` (C)
8. `dose_confirmation` (C)
9. `symptom_vitals_log` (C)
10. `care_task_create_assign` (C)
11. `care_task_claim_complete` (C)
12. `meal_ride_request` (C)
13. `emergency_information` (S)
14. `care_contacts` (S)
15. `care_note_update` (C)
16. `document_vault` (S)
17. `share_access_permissions` (C)
18. `activity_feed` (S)

역할·자산·상태: care recipient, circle owner, family caregiver, paid caregiver, volunteer를 분리한다. 핵심 자산은 care circle, recipient profile, medication/dose, appointment, symptom/vital, care task, meal/ride request, emergency contact, care note, insurance/advance-directive document다. 상태는 invited/joined/revoked, scheduled/taken/skipped/missed, unassigned/claimed/completed/cancelled다.

충돌 위험: `wellbeing_health.medications`는 본인의 기록이고, `healthcare_provider.proxy_access`는 병원 계정의 법적 proxy 권한이다. `childcare_family_portal`은 child/provider attendance·pickup 흐름이다. 이 도메인은 여러 가족·봉사자가 한 care recipient의 task, schedule, adherence를 공유하는 lifecycle을 소유한다. `complete`가 약 복용, task 완료, appointment 완료 중 무엇인지 asset 문맥이 없으면 확정하지 않는다.

공식 근거: [CircleCare](https://circlecare.app/)는 family circle, medications, appointments, task ownership, emergency info, document storage를 설명한다. [Lotsa Helping Hands](https://lotsahelpinghands.com/)와 [Activities & Tasks](https://www.lotsahelpinghands.com/help/pe_activities.html)는 meal, ride, visit, childcare 요청의 unfilled/claimed 상태를 설명한다.

안전 경계: agent는 약 용량·복용 여부·증상 의미를 추론하거나 대신 확인하지 않는다. medication schedule, dose confirmation, symptom/vital log, task assignment/completion, caregiver invite, document/access sharing은 대상자와 행위자를 확인한 뒤 사용자 최종 클릭으로 남긴다. 응급 징후가 보이면 앱 탐색보다 지역 응급 서비스 안내를 우선하되 진단하지 않는다.

### 10. Home energy management (`home_energy_management`) — 16 terminal

제안 terminal:

1. `energy_site_switch` (S)
2. `live_energy_flow` (S)
3. `solar_generation` (S)
4. `home_consumption` (S)
5. `grid_import_export` (S)
6. `battery_state` (S)
7. `energy_history` (S)
8. `backup_reserve` (C)
9. `operating_mode` (C)
10. `utility_rate_plan` (C)
11. `grid_charging_setting` (C)
12. `energy_export_setting` (C)
13. `storm_watch_status` (S)
14. `off_grid_test` (C)
15. `charge_on_solar` (C)
16. `outage_event_history` (S)

역할·자산·상태: system owner, household member, installer 권한을 구분한다. 핵심 자산은 energy site, home load, solar array/inverter, battery, grid, vehicle/charger, utility tariff, outage event다. 상태는 producing/consuming/importing/exporting, charging/discharging/standby, on-grid/off-grid, backup/self-powered/time-based, storm watch active/inactive다.

충돌 위험: `utilities.usage/bill/outage`는 utility account의 청구·서비스 정보이고, `smart_home`은 일반 기기·자동화이며, `automotive_vehicle.charge_schedule`과 `public_ev_charging`은 차량·충전 session 중심이다. 이 도메인은 한 energy site 안의 solar + battery + home + grid power flow와 operating policy를 소유한다.

공식 근거: [Tesla App for Energy](https://www.tesla.com/support/energy/powerwall/mobile-app/tesla-app-for-energy)는 power flow, backup reserve, mode, rate plan, storm watch, off-grid, charge-on-solar를 설명한다. [Tesla advanced settings](https://www.tesla.com/support/energy/powerwall/mobile-app/advanced-settings)는 grid charging/export restriction과 utility permission을, [Enphase energy monitoring](https://enphase.com/learn/home-energy/explore-your-system/monitor-your-energy-usage)은 production/consumption/import/export/battery states를 구분한다.

안전 경계: site, battery charge, backup reserve, current outage, tariff, utility export permission을 확인한다. reserve/mode/rate plan/grid charging/export/off-grid/charge-on-solar 변경은 정전 대비와 비용·규제에 영향을 주므로 최종 클릭을 사용자에게 남긴다. active outage나 critical load 상태에서는 off-grid test를 제안하지 않는다.

### 11. Genealogy and family history (`genealogy_family_history`) — 16 terminal

제안 terminal:

1. `tree_switch` (S)
2. `pedigree_view` (S)
3. `person_profile` (S)
4. `relative_search` (S)
5. `historical_record_search` (S)
6. `record_hint_review` (S)
7. `record_attach_reject` (C)
8. `source_citation_create` (C)
9. `person_create_edit` (C)
10. `relationship_edit` (C)
11. `possible_duplicate_review` (S)
12. `person_merge` (C)
13. `memory_upload_tag` (C)
14. `dna_match_list` (S)
15. `tree_privacy_settings` (C)
16. `tree_export_download` (C)

역할·자산·상태: tree owner, family researcher, collaborator, DNA participant를 분리한다. 핵심 자산은 family tree, person, parent/spouse/child relationship, historical record, record hint, source citation, duplicate candidate, memory, DNA match, export다. 상태는 living/private/deceased/public, unverified/hinted/attached/rejected, possible duplicate/merged다.

충돌 위험: `contacts`, account family member, photo album, social profile과 달리 이 도메인의 person은 계보 관계와 historical source를 가진다. `merge`는 code PR나 support ticket가 아니라 two-person record merge다. `match`는 dating/commerce 검색 결과가 아니라 record hint 또는 DNA relationship 후보이며, 둘도 서로 분리한다.

공식 근거: [FamilySearch Family Tree app](https://www.familysearch.org/en/mobile-apps/family-tree-app)은 pedigree, person edit, historical records, hints, collaboration을 설명한다. [FamilySearch record hints](https://www.familysearch.org/en/help/helpcenter/article/how-do-i-attach-record-hints-in-family-tree)는 compare, attach, not-a-match, review-others 상태를, [FamilySearch Memories](https://www.familysearch.org/en/help/helpcenter/article/how-do-i-use-familysearch-memories-to-preserve-my-ancestors-life-stories)는 upload, tag, archive, privacy, share를 설명한다.

안전 경계: living person, relationship, DNA match, source image는 극도로 민감하다. attach/reject, create/edit person or relationship, merge, upload/tag, privacy, export는 모두 사용자 최종 클릭이다. agent는 친자관계·신원·민족·질병을 추론하지 않고, merge 전에 두 person의 이름·날짜·장소·관계를 비교하도록 요구한다.

### 12. Procurement and supplier operations (`procurement_supplier_ops`) — 18 terminal

제안 terminal:

1. `organization_cost_center_switch` (S)
2. `catalog_item_search` (S)
3. `supplier_search` (S)
4. `purchase_requisition_create` (C)
5. `requisition_submit` (C)
6. `approval_inbox` (S)
7. `requisition_approve_reject` (C)
8. `request_for_quote_create` (C)
9. `supplier_quote_compare` (S)
10. `supplier_award` (C)
11. `purchase_order_detail` (S)
12. `purchase_order_change` (C)
13. `goods_receipt_match` (C)
14. `service_entry_confirm` (C)
15. `invoice_three_way_match` (S)
16. `invoice_exception_resolve` (C)
17. `supplier_onboarding` (C)
18. `supplier_risk_documents` (S)

역할·자산·상태: requester, cost-center owner, approver, buyer, receiver, accounts-payable reviewer, supplier manager를 분리한다. 핵심 자산은 organization/cost center, catalog item, supplier, requisition, approval, RFQ, quote, award, purchase order, goods receipt, service entry, invoice match, supplier onboarding record다. 상태는 draft/submitted/approved/rejected, sourcing/open/quoted/awarded, ordered/partially received/received, matched/blocked/exception/resolved다.

충돌 위험: `business_accounting`의 vendor/bill/invoice는 회계 기록 중심이고, `warehouse_fulfillment_ops`의 receiving은 물리 입고 실행 중심이다. 이 도메인은 request→approval→sourcing→PO→receipt/service entry→invoice match라는 구매 책임 사슬을 소유한다. `approve`, `receive`, `match`, `award`, `change order`는 역할·문서 번호·금액 문맥 없이 합치지 않는다.

공식 근거: [SAP Ariba Mobile requisitions](https://help.sap.com/docs/ARIBA_SHOP_MOB/ab43f274ca6c4acea94aa612efb5c489/529344bfa0d14b6fb83c793955d05895.html?locale=en-US&state=PRODUCTION&version=SHIP)은 requisition list, price/quantity/status와 approval 역할을 설명한다. [SAP Ariba Procurement Mobile guide](https://help.sap.com/doc/a98d048991094230a1416d8a17b2c688/2508/en-US/ProcurementMobile_1.pdf)는 mobile approve/deny와 approval details를, [Oracle Procurement lifecycle](https://docs.oracle.com/cd/E56614_01/procurementop_gs/OAPRC.pdf)은 requisition, supplier order, receiving lifecycle을 설명한다.

안전 경계: legal entity, cost center, supplier, item/service, quantity/UoM, currency, tax, amount, delivery location, approver authority를 확인한다. submit, approve/reject, RFQ, award, PO change, receipt/service confirmation, exception resolution, supplier onboarding은 금전·계약·재고 상태를 바꾸므로 사용자 최종 클릭이다. 승인 한도나 segregation-of-duties 경고를 우회하지 않는다.

## 가장 위험한 교차 도메인 충돌

v10은 alias를 무작정 늘리기 전에 아래 표현을 role + asset + lifecycle state로 분리해야 한다.

| 모호한 표면어 | 반드시 분리할 의미 |
|---|---|
| `work order` / 작업지시 | 임대 maintenance, 설비 정비, 제조 operation, 건설 field work(v8) |
| `inspection` / 점검 | move-in/out unit, asset checklist, manufacturing quality, construction safety |
| `receive` / 입고·수신 | warehouse goods receipt, procurement receipt, legal message/document, restaurant order |
| `release` / 승인·해제 | manufacturing batch/rework, warehouse wave, payment hold, access/security |
| `approve` / 승인 | housing application, maintenance WO, quality batch, legal settlement, procurement requisition |
| `close` / 완료 | asset work order, production order, legal matter, restaurant check/shift, support ticket(v8) |
| `assign` / 배정 | vendor, technician, care task, classroom work, procurement approver |
| `record` / 기록 | production quantity, lab result, care vital, genealogy source, legal time entry |
| `screening` / 심사 | rental applicant, supplier risk, security scan, health screening |
| `return` / 반환 | warehouse return receipt, classroom submission return, commerce refund/return |
| `merge` / 병합 | genealogy person, restaurant check, pull request(v9), support ticket(v8) |
| `schedule` / 일정 | preventive maintenance, class assignment, care medication, home energy tariff |
| `profile` / 프로필 | tenant/owner, student, care recipient, genealogy person, account user |
| `export` / 내보내기 | research data, genealogy tree, home energy CSV, account privacy export |
| `hold` / 보류 | warehouse quarantine, manufacturing quality hold, restaurant course hold, legal trust hold |

각 충돌군은 동일 locale의 positive probe와 최소 3개의 다른 역할·자산 negative probe를 가져야 한다. 표면어 하나만 일치할 때 terminal을 확정하지 않는다. `role + asset + lifecycle state` 중 최소 두 축이 확인돼야 높은 신뢰도를 부여하고, 금전·법률·건강·물리 자산 관련 항목은 세 축이 모두 확인돼야 한다.

## 구현·검증 계약

### 데이터 계약

- 앱 이름, package name, resource ID, 좌표, screenshot hash, 녹화 경로를 function/intent runtime semantics에 넣지 않는다.
- 218개 terminal 각각에 `ko-KR`/`en-US` alias, positive/negative context, role hints, state cues, risk cues와 공식 source ref를 둔다.
- 허브 12개는 탐색용이며 terminal이 아니다. 218개 terminal만 각각 정확히 하나의 intent를 가진다.
- 위 terminal은 정확히 **민감 조회 `S` 88개, 상태 변경 `C` 130개**다. 130개 `C` 전부를 `never_auto + before_action`으로 고정한다.
- disabled/unavailable/permission/role mismatch/lock/approval limit/safety hold가 보이면 비슷한 위험 버튼으로 우회하지 않고 fail-closed한다.
- 실제 tenant, student, client, patient/care recipient, employee, sample, supplier, payment, DNA, legal filing, asset identifier를 fixture나 telemetry에 저장하지 않는다.
- 한 alias가 여러 도메인에 존재할 수는 있지만 alias-only 결정을 금지하고 role/asset/state guard를 필수화한다.

### 정확한 검증 규모

1. **ontology 단위검사:** 12 domains, 230 functions, 218 intents, `S=88`, `C=130`을 정확히 검증한다.
2. **개발 semantic matrix:** intent당 한국어 positive 1, 영어 positive 1, 역할 반전 1, 자산 동음이의 1의 **4 probes**, 총 **872 probes**를 둔다.
3. **독립 frozen fixture:** catalog에서 생성하지 않은 **218 scenarios**를 둔다. 한국어 109, 영어 109로 균등 분할하고 총 step은 최소 **872**로 한다.
4. **안전 gate:** 130개 `C`와 high-risk `S`에서 agent final click 0건, `stop/no_click` 100%, 잘못된 권한 우회 0건을 요구한다.
5. **충돌 gate:** 위 15개 표면어 충돌군을 각각 최소 8 probes로 구성한 **120-probe alias collision suite**를 별도로 둔다.
6. **상태 gate:** terminal당 unavailable/disabled/permission-denied/stale-or-offline 중 최소 2개를 포함해 총 **436개 이상의 recovery probes**를 둔다.
7. **회귀 gate:** v1~v9의 모든 independent fixture, quality score, deterministic materialization, idempotence, resolver latency와 안전 불변식을 그대로 통과해야 한다.
8. **출처 gate:** 도메인당 서로 다른 공식 문서 최소 2개, 총 **24개 이상의 official-primary source**를 registry에 등록하고 URL, publisher, 수집일, 검증 상태를 고정한다.

### 제안 품질 하한

- 각 terminal의 locale별 alias 최소 8개, positive context 최소 6개, negative context 최소 6개.
- 각 intent의 locale별 goal pattern 최소 10개, compositional rule 최소 24개.
- 동일 도메인 안에서 terminal 쌍마다 contrastive `avoid_functions` 최소 1개.
- 모든 고위험 terminal은 `user_boundary`에 한국어와 영어로 최종 클릭 소유권을 명시한다.
- role inversion fixture는 requester/approver, student/teacher, tenant/manager, patient/caregiver, operator/inspector처럼 권한이 반대인 쌍을 반드시 포함한다.
- sealed fixture 실패 label은 tuning 입력으로 재사용하지 않는다. 수정은 공식 근거, 개발 fixture, 일반화된 collision rule에서만 도출한다.

## 구현 순서

1. 12개 허브와 218개 terminal ID, 역할, 자산, 상태 기계를 먼저 동결한다.
2. 도메인별 source registry를 작성하고 official-primary evidence가 없는 terminal은 추가하지 않는다.
3. alias보다 먼저 role inversion, homonym, unavailable, stale/offline context를 작성한다.
4. 130개 `C`의 final-click ownership과 각 도메인의 고위험 `S` disclosure 경계를 invariant로 적용한다.
5. 872-probe 개발 matrix와 120-probe collision suite로 의미 충돌을 교정한다.
6. 기존 v1~v9 independent 회귀가 유지되는지 확인한 뒤 별도 작성한 218-scenario frozen fixture를 평가한다.
7. 실패를 수정할 때 특정 앱명·좌표·경로를 추가하지 말고 role/asset/state guard를 일반화한다.
8. 실제 기기 검증은 ontology·resolver·fixture gate가 모두 통과한 뒤 별도 단계로 수행한다.

## 감사 한계와 v11 후보

이 문서는 기능 존재와 의미 경계를 공식 자료로 확인한 설계 감사이며, 모든 Android 앱이 동일한 라벨과 화면 구조를 사용한다는 뜻은 아니다. 지역, 조직 권한, 요금제, 규제, device form factor, offline 상태에 따라 기능이 숨겨지거나 web-only일 수 있다. 따라서 source 기반 ontology를 구현한 뒤에도 독립 fixture와 실제 기기 검증이 필요하다.

v10 이후에도 남는 후보는 의료진용 clinical workflow, 약국 조제 업무, 보험사 adjuster workflow, 항공 승무·운항 업무, 통신 현장 technician, IT service management/CMDB, cybersecurity operations, 사회복지 case management, 장례·유산 집행, 해상·항만 물류다. 이들은 의료·규제·물리 안전·법적 권한이 특히 크므로, v10 회귀와 안전 경계가 안정된 뒤 별도 source audit로 다루는 편이 타당하다.
