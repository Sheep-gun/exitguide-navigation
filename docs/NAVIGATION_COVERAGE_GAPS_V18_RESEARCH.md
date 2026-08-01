# Navigation coverage gap research — V18

Status: research backlog only; this file is not canonical catalog input.  V18 may
only be implemented after the V16 isolated evaluation and V17 validation have
finished.  Candidate IDs below must be rejected if a terminal-level comparison
shows that an existing function already owns the same role, asset, state and
jurisdiction.

## Prospective baseline

If V16 and V17 are accepted without further changes, the physical catalog will
contain 203 domains, 3,358 functions and 3,128 intents.  A larger count is not a
quality target by itself.  V18 should improve common first-seen-app coverage and
must preserve these invariants:

If all twelve researched domains survive terminal-level duplicate review and
each contributes twenty terminals plus one fail-closed hub, the isolated V18
projection is 215 domains, 3,610 functions and 3,368 intents.  Relative to the
current canonical V15 that is +36 domains, +744 physical functions and +708
intents; none of those counts is promotion evidence without independent routing
and safety results.

- one governed asset and lifecycle state per terminal;
- bilingual display names, aliases and independently worded goals;
- direct official lifecycle evidence, not search-result snippets or generic home
  pages;
- explicit role, jurisdiction and provider boundaries;
- view/status destinations separated from submit, pay, publish, appeal, trade,
  cancel and ownership-changing actions;
- all consequential actions use `automation_policy=never_auto` and
  `stop_policy=before_action`;
- missing role, asset, state or jurisdiction fails closed to the domain hub;
- the same word in adjacent domains is represented as a negative collision, not
  duplicated as an unrestricted alias.

### 한국어 범위·안전 경계 요약

V18의 한국어 메타데이터는 영문 명칭을 그대로 음역하는 수준이 아니라,
사용자 역할과 대상 자산, 현재 상태, 서비스 제공자와 관할 범위를 함께
표현해야 한다. 각 영역의 핵심 경계는 다음과 같다.

- 디지털 광고 캠페인 운영은 광고주 계정·캠페인·소재·예산·청구 자산을
  다루며, 캠페인 금융 신고나 일반 소셜 게시 기능과 구분한다.
- 소비자 기기 보증·수리는 개인 소유 기기의 일련번호·보증상태·수리요청·
  견적·교체·반송 흐름을 다루며 기업 자산정비와 구분한다.
- 대학 입학 지원은 예비 지원자의 학교 탐색·지원서·서류·결정 조회를
  다루며 입학사정 담당자의 합격처리 기능으로 연결하지 않는다.
- 소셜 계정·콘텐츠 이의제기는 계정 제한·콘텐츠 삭제·신고·재심 상태를
  다루며 운영자 제재 도구와 구분하고 최종 이의제기는 사용자가 누른다.
- 소비자 채권추심 대응은 본인의 채무·추심 통지·검증·분쟁·연락 제한을
  다루며 채권자의 회수 업무나 임의 상환 약속을 생성하지 않는다.
- 렌터카 이용은 예약·운전자·차량 인수·연장·연료·손상·반납·영수증을
  다루며 결제·계약 변경·사고 신고는 행동 직전에 중단한다.
- 항공권 발권 후 승객 서비스는 문서 준비·특별지원·유료 수하물·추적·
  운항차질·재예약·크레딧·환불·비용보상을 다루며 기존 일반 여행 기능과
  중복되는 체크인·좌석·탑승권은 명시적으로 인계한다.
- 가정용 인터넷·TV 서비스는 설치·게이트웨이·장애·이전·해지·장비반납을
  다루며 이동통신 요금제나 통신사 현장기사 업무와 구분한다.
- 소비자 제품 리콜 구제는 공식 리콜 식별·대상 제품 확인·수리·교환·환불·
  회수 상태를 다루며 리콜 해당 여부를 근거 없이 단정하지 않는다.
- 학교·가족 등록은 보호자 관점의 학생 등록·주소·서류·급식·교통·출결·
  기록 요청을 다루며 교직원 행정 승인 기능으로 이동하지 않는다.
- 온라인 마켓플레이스 판매자 운영은 검증된 사업 판매자의 상점·상품목록·
  주문·배송·지급·성과 자산을 다루며 개인 중고물품 판매와 구분한다.
- 플랫폼 노동자 계정·수입은 배달·운송 종사자의 가입·신원검증·가용상태·
  수입·지급·세금서류·계정 이의제기를 다루며 배차 수락을 자동화하지 않는다.

모든 변경·제출·지급·게시·취소·이의제기·소유권 이전은 최종 버튼 직전에
멈추고 사용자가 직접 누른다. 역할·대상 기록·상태·제공자·관할 가운데
하나라도 불명확하면 개별 기능을 추측하지 않고 해당 영역 허브에서 안전하게
중단한다.

### Known canonical collision audit

A 2026-07-30 terminal-level scan found three important ownership boundaries that
the V18 layer must enforce before accepting any feature:

- canonical `travel.checkin`, `travel.boarding_pass`, `travel.seat`,
  `travel.baggage`, `travel.booking.change`, `travel.booking.cancel.entry` and
  `travel.flight_status` already own the generic passenger states.  V18 may add
  airline-specific missing states such as document readiness, special assistance,
  paid-bag addition, baggage tracking, disruption choice, rebooking, travel
  credit, refund eligibility/status and reimbursement, but it must hand off to or
  explicitly model equivalence with the existing terminals rather than create a
  second unrestricted destination.
- canonical `higher_education_student_admin.applicant_queue` and
  `higher_education_student_admin.applicant_admit` belong to registrar and
  authorised institutional staff.  Applicant-facing discovery, preparation,
  submission and decision viewing require a prospective-applicant role gate and
  must never route an applicant to the operator-side admission action.
- canonical `marketplace.create_listing`, `marketplace.edit_listing` and
  `marketplace.mark_sold` describe one-off consumer/used-item sales.  A V18
  business seller function is valid only when storefront, catalog, business
  order, fulfilment, payout or seller-performance cues are present.

The scan also confirmed that campaign-finance campaign records are not digital
advertising campaigns, and that mobile `telecom` service does not own residential
gateway, installation, move, cancellation or equipment-return states.  Those
terms still require cross-domain negatives because the surface words overlap.

## Evidence-ready high-frequency gaps

### 1. Digital advertising campaign operations (`digital_ad_campaign_ops`)

Distinct asset: advertiser account → campaign → ad group/ad set → creative →
audience → conversion → budget/billing.  This is not app-store release,
campaign-finance compliance, CRM sales, creator monetization or ordinary social
posting.

Required lifecycle coverage: account access and roles, campaign list/status,
objective/type selection, budget and bid review, audience/targeting review,
creative review, conversion goal, policy/approval status, performance view,
pause/resume, publish, billing profile, transaction/invoice view and account
access removal.  Publish, budget application, billing mutation and access changes
are consequential actions.

Direct official evidence opened 2026-07-30:

- https://support.google.com/google-ads/answer/13359357?hl=en
- https://support.google.com/google-ads/answer/6324971?hl=en
- https://support.google.com/google-ads/answer/6127167?hl=en
- https://support.google.com/google-ads/answer/6372672?hl=en-AUI
- https://support.google.com/google-ads/answer/7058605?hl=en
- https://www.linkedin.com/help/lms/answer/a425731
- https://www.linkedin.com/help/lms/answer/a9519149

Korean companion evidence (keep provider vocabulary jurisdiction-scoped):

- https://gfa.naver.com/
- https://help.naver.com/service/19459/contents/21263?lang=ko

### 2. Consumer device warranty and repair (`consumer_device_warranty_repair`)

Distinct asset: personally owned device → serial/IMEI → coverage → diagnosed
issue → service request/RMA → shipment/walk-in visit → inspection/estimate →
repair/replacement → return.  This is not vehicle maintenance, home-service
booking, enterprise asset maintenance, app troubleshooting or product returns.

Required lifecycle coverage: product registration, device lookup, warranty
eligibility, damage/issue classification, service option comparison, repair
estimate, service-center lookup, appointment/mail-in request, data-backup/reset
preparation, shipping label, repair status, estimate approval/decline,
replacement choice, proof-of-purchase correction and repair history.  Repair
submission, estimate approval, device reset and replacement acceptance require a
user final action.

Direct official evidence opened 2026-07-30:

- https://www.samsung.com/us/support/
- https://www.samsung.com/us/support/service/
- https://support.google.com/store/answer/13516446?hl=en
- https://support.google.com/pixelphone/answer/6160400?hl=en
- https://support.google.com/pixelphone/answer/9218411?hl=en
- https://support.google.com/pixelphone/answer/9105064?hl=en

Korean companion evidence:

- https://www.samsungsvc.co.kr/reserve/searchCenter

### 3. Higher-education admissions (`higher_education_admissions`)

Distinct asset: prospective applicant → institution/program list → application
requirements → applicant profile → recommender/supporting documents → fee/waiver
→ submission → decision.  This ends where the existing post-enrolment
`higher_education_student_admin` domain begins and must not absorb V17 student
financial-aid case handling.

Required lifecycle coverage: applicant type, college/program search, saved list,
requirements/deadlines, profile sections, activities, coursework, essay and
supplements, recommender invitation/assignment, FERPA authorization, transcript
status, fee waiver, preview, submission, checklist, application status, missing
item notice, decision view, wait-list response and enrollment-deposit handoff.
Invitation, authorization, payment, submission, wait-list response and deposit
are consequential actions.

Direct official evidence opened 2026-07-30:

- https://www.commonapp.org/apply/first-year-students/
- https://www.commonapp.org/mobile/
- https://www.commonapp.org/apply/student-guides-and-resources/
- https://www.commonapp.org/counselors-and-recommenders/recommender-guide/
- https://www.commonapp.org/static/b96ac19f1b082d294afc77aa6a386e01/Resource_FY_HowFYWorks_ENG_2025.10.24.pdf
- https://content.commonapp.org/Files/ReqGrid.pdf

Korean companion evidence (Korean application-limit and status vocabulary must
not leak into Common App routing):

- https://www.adiga.kr/uve/faq/conseFaqView.do?ansBbsId=97315&menuId=PCUVEFAQ1000
- https://ipsi.kopo.ac.kr/index.do

### 4. Social-platform enforcement and appeals (`social_platform_account_appeals`)

Distinct asset: platform account or authored content → enforcement notice →
restriction/strike/removal → evidence/identity challenge → appeal → decision →
restoration or data/deactivation route.  This is not reporting another user,
generic account recovery, community-organizer moderation or ordinary posting.

Required lifecycle coverage: account status, violation history, content-removal
notice, reach label, feature restriction, locked-account verification,
suspension status, appeal eligibility, appeal evidence, appeal submission,
appeal status/result, copyright counter path, impersonation/authenticity route,
restricted-account data request and deactivation after enforcement.  Identity
evidence, counter-notice, appeal and deactivation are always user-final.

Direct official evidence opened 2026-07-30:

- https://help.x.com/en/managing-your-account/suspended-x-accounts
- https://help.x.com/en/managing-your-account/locked-and-limited-accounts
- https://help.x.com/en/rules-and-policies/enforcement-options
- https://help.x.com/en/forms/account-access/appeals/redirect
- https://help.x.com/en/rules-and-policies/copyright-policy
- https://support.tiktok.com/en/safety-hc/account-and-user-safety/content-violations-and-bans
- https://support.tiktok.com/en/safety-hc/account-and-user-safety/underage-appeals-on-tiktok

Korean companion evidence (provider-localized routes are retained separately;
a regulator article is not a substitute for an in-app route):

- https://help.x.com/ko/managing-your-account/suspended-x-accounts
- https://help.x.com/ko/managing-your-account/locked-and-limited-accounts
- https://help.x.com/ko/forms/account-access/appeals/redirect
- https://support.tiktok.com/ko/safety-hc/account-and-user-safety
- https://support.tiktok.com/ko-KR/safety-hc/account-and-user-safety/content-levels-on-tiktok-posts

### 5. Consumer debt-collection response (`consumer_debt_collection_services`)

Distinct asset: claimed consumer debt → validation notice → creditor/itemization
→ dispute/verification → communication preference → settlement/payment proposal
→ complaint or litigation handoff.  This is not credit-report-file correction,
ordinary loan servicing, estate debt administration or collector-side casework.

Required lifecycle coverage: collector identity, validation notice, current
amount/itemization, original-creditor request, validation deadline, debt
recognition choice, dispute drafting/submission, verification status, contact
channel/frequency, stop-contact request, payment-plan offer, settlement offer,
payment record, complaint submission, lawsuit notice and legal-help handoff.
Dispute, contact restriction, settlement, payment and complaint submission must
stop for the user; the agent must never characterize a debt as legally valid.

Direct official evidence opened 2026-07-30:

- https://www.consumerfinance.gov/consumer-tools/debt-collection/
- https://www.consumerfinance.gov/rules-policy/regulations/1006/34/
- https://www.consumerfinance.gov/rules-policy/regulations/1006/38/
- https://www.consumerfinance.gov/ask-cfpb/what-information-does-a-debt-collector-have-to-give-me-about-the-debt-en-331/
- https://www.consumerfinance.gov/ask-cfpb/can-a-debt-collector-still-collect-a-debt-after-ive-disputed-it-en-338/
- https://www.consumerfinance.gov/consumer-tools/debt-collection/know-your-rights-when-a-debt-collector-calls/
- https://www.ftc.gov/legal-library/browse/rules/fair-debt-collection-practices-act-text

Korean companion evidence (Korean statutory rights and debt-adjustment paths are
separate jurisdictional branches):

- https://law.go.kr/LSW/lsInfoP.do?ancYnChk=0&lsId=010910
- https://www.crss.or.kr/

### 6. Rental-vehicle trip services (`rental_vehicle_trip_services`)

Distinct asset: consumer rental reservation → driver/vehicle/rate/protection →
pickup → active rental → extension/incident → return → receipt/charge dispute.
This is not ride hailing, personally owned connected vehicles, fleet compliance
or property rental.

Required lifecycle coverage: location/date search, vehicle class, rate and
protection review, driver requirements, reservation, reservation lookup,
modify/cancel, online check-in, pickup instructions, rental agreement, active
rental, extend rental, roadside help, accident/damage report, return location,
fuel/charging terms, return confirmation, receipt, deposit release and billing
question.  Booking, modification, cancellation, extension, protection choice and
damage submission are user-final.

Direct official evidence opened 2026-07-30:

- https://www.enterprise.com/en/reserve/view-modify-cancel.html
- https://www.enterprise.com/en/car-rental-faqs/us-reservations/change-cancel-reservation.html
- https://www.enterprise.com/en/reserve/receipts.html
- https://www.hertz.com/pr/es/reservation/extend
- https://www5.hertz.com/rentacar/misc/index.jsp?targetPage=USContactUs.jsp
- https://www.avis.com/en/reservation/view-modify-cancel

Korean companion evidence:

- https://m.lotterentacar.net/hp/kor/reservation/shortInfo/pay.do
- https://www.lotterentacar.net/hp/kor/cs/faq/list.do?faqGroup=C

### 7. Airline passenger trip management (`airline_passenger_trip_management`)

Distinct asset: ticketed passenger itinerary → trip details → seats/extras →
travel documents → check-in → boarding pass/baggage → disruption/rebooking →
refund/reimbursement.  This is not flight discovery, airline crew operations,
airport airside operations or cargo handling.

Required lifecycle coverage: find trip, itinerary and fare rules, passenger
details, seat map/change/upgrade, baggage allowance/addition, special assistance,
travel-document readiness, check-in, boarding pass, baggage tracker, same-day
change, disruption options, rebook, cancel, travel credit, refund eligibility,
refund status, reimbursement and complaint.  Purchase, paid seat/bag, check-in,
rebook, cancel and refund requests are user-final.

Direct official evidence opened 2026-07-30:

- https://www.delta.com/us/en/need-help/overview
- https://www.delta.com/us/en/need-help/support-flights
- https://www.delta.com/us/en/need-help/support-seats
- https://www.delta.com/us/en/check-in-security/overview
- https://www.aa.com/reservation/view/find-your-reservation
- https://www.aa.com/i18n/travel-info/travel-tools/mobile-and-app.jsp

Korean companion evidence:

- https://www.koreanair.com/contents/plan-your-travel/check-in/self-check-in/online-check-in
- https://www.koreanair.com/contents/booking/reservation-guide/how-to-book/booking-guide

### 8. Home internet and television service (`home_internet_tv_service`)

Distinct asset: residential service address -> internet/TV plan -> installation
appointment -> provider gateway/router/set-top equipment -> active line -> outage
or diagnostic case -> bill/contract -> move, cancellation and equipment return.
This is not mobile SIM/roaming, generic utility billing, streaming-subscription
management or technician-side telecom field work.

Required lifecycle coverage: address/serviceability check, plan and speed tier,
order status, installation/reschedule, equipment activation, Wi-Fi name/password,
connected-device view, speed test, outage status, guided diagnostics, technician
appointment, bill and contract term, plan/add-on change, temporary suspension,
service move, cancellation request/status, final bill, return-method selection,
return label/location and equipment-return confirmation.  Ordering, rescheduling,
plan mutation, move, cancellation and equipment-return submission are user-final;
an outage or diagnostic screen must never be mistaken for cancellation.

Direct official evidence opened 2026-07-30:

- https://www.att.com/support/how-to/internet/equipment-return/
- https://www.att.com/support/how-to/cancellation-policy-internet/
- https://www.att.com/help/moving/
- https://www.xfinity.com/support/articles/move-services-faqs
- https://www.xfinity.com/support/articles/transferring-service-to-a-new-location/
- https://www.xfinity.com/support/articles/returning-your-equipment

Korean companion evidence (provider-specific account menus remain scoped to the
provider; cancellation penalties are informational, not a reason to block the
user's route):

- https://www.bworld.co.kr/m/customer/faq/faq.do?menu_id=C01080000
- https://blog.bworld.co.kr/2026/02/10/new-home-internet-installation-guide/
- https://www.bworld.co.kr/product/internet/charge.do?menu_id=P02010200

### 9. Consumer product recall remedies (`consumer_product_recall_remedies`)

Distinct asset: consumer-owned product -> make/model/serial or VIN -> applicable
recall/corrective action -> hazard and stop-use guidance -> repair, replacement,
refund or disposal remedy -> claim/appointment/shipment -> completion status.
This is not an ordinary return, device warranty repair, adverse-event diagnosis,
manufacturer-side recall administration or a regulator enforcement case.

Required lifecycle coverage: product/category search, model/serial/VIN lookup,
unrepaired-recall status, affected-lot or date-code check, hazard severity,
immediate stop-use/storage guidance, owner registration and alerts, remedy type,
dealer/service-center lookup, repair appointment, replacement/refund request,
shipping/return instructions, proof-of-purchase exception, request status,
remedy completion and unsafe-product incident report.  Incident reports, owner
registration, appointments and remedy submissions are user-final; the agent must
not infer that a product is safe merely because a broad keyword search is empty.

Direct official evidence opened 2026-07-30:

- https://www.cpsc.gov/Recalls
- https://www.cpsc.gov/Data
- https://www.cpsc.gov/content/Report-Search-Protect-0
- https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts
- https://www.fda.gov/safety/industry-guidance-recalls/recalls-background-and-definitions
- https://www.nhtsa.gov/recalls

Korean companion evidence (Korean recall orders, corrective remedies and model
lookup are a separate jurisdictional vocabulary branch):

- https://www.safetykorea.kr/recall/fRecallBoard
- https://www.safetykorea.kr/recall/recallProc02
- https://www.safetykorea.kr/news/promote

### 10. School-family enrolment and records (`school_family_enrollment`)

Distinct asset: guardian-linked student -> residential/zoned-school eligibility
-> school/program choice -> registration documents -> placement/enrolment ->
attendance and family-facing records -> transfer or records request.  This is not
higher-education admissions, instructor administration, childcare booking,
special-education case management or school-operator student-information work.

Required lifecycle coverage: find zoned school, grade/year eligibility, new or
returning student path, guardian account, link/add student, school/program list,
registration checklist, identity/residency and immunisation document status,
application/registration, placement or offer, wait-list status/response, school
registration completion, contact-information update, attendance view, absence
notice/correction request, grades/schedule view, transfer eligibility, transfer
documents/request/status and transcript or student-record request.  Account
linking, document submission, registration, offer response, contact mutation,
absence correction, transfer and records submission are user-final.

Direct official evidence opened 2026-07-30:

- https://www.schools.nyc.gov/enrollment/enroll-grade-by-grade/how-to-enroll-one-pager
- https://www.schools.nyc.gov/enrollment/enrollment-help/family-welcome-centers
- https://www.schools.nyc.gov/enrollment/enrollment-help/transfers/registration-checklist
- https://www.schools.nyc.gov/learning/student-journey/nyc-schools-account/nycsa-mobile-application
- https://www.schools.nyc.gov/school-life/school-environment/attendance
- https://www.schools.nyc.gov/learning/student-journey/student-records-and-transcripts/requesting-student-records-and-transcripts

Korean companion evidence (NEIS viewing and education-office transfer workflows
are separate provider and jurisdiction branches):

- https://parents.neis.go.kr/
- https://jbedu.sen.go.kr/CMS/entrance/entrance03/entrance0304/index.html
- https://sbgbedu.sen.go.kr/CMS/civilapp/civilapp08/civilapp0803/civilapp080302/index.html

### 11. Online marketplace seller operations (`online_marketplace_seller_ops`)

Distinct asset: marketplace seller identity -> shop/storefront -> catalog/listing
-> inventory -> buyer order -> fulfilment -> return/refund/dispute -> payout and
seller-performance record.  This is not a consumer purchase, a one-off used-item
listing, generic POS inventory, direct-to-consumer site administration, CRM or
warehouse-operator work.

Required lifecycle coverage: seller registration/verification, store profile,
user/role access, catalog/listing list, create/edit/deactivate listing, variation
and inventory, pricing, shipping/return policy, order list/detail, accept or
cancel order, pick/pack/ship, label and tracking, delivery exception, buyer
message, return/refund request, dispute/case, seller appeal, payout balance,
deposit/bank status, fees/tax statement, sales analytics, performance metrics,
policy violation and account restriction.  Registration, publishing, price or
stock mutation, order cancellation, fulfilment confirmation, refund, dispute,
bank mutation and appeal are always user-final.

Direct official evidence opened 2026-07-30:

- https://www.ebay.com/help/selling
- https://www.ebay.com/help/Selling/Selling_Tools/Seller_Hub?id=4095
- https://www.ebay.com/help/selling/selling/seller-levels-performance-standards?id=4080
- https://www.ebay.com/help/policies/selling-policies/seller-performance-standards?id=4347
- https://www.ebay.com/help/selling/selling/monitor-service-metrics?id=4785
- https://help.etsy.com/hc/en-us/articles/360000343908-How-to-Use-Your-Dashboard-to-Manage-Your-Shop
- https://help.etsy.com/hc/en-us/articles/115015710308-What-to-Do-After-You-Sell-an-Item
- https://help.etsy.com/hc/en-us/articles/115015747228-How-to-Manage-Your-Payment-Account

Korean companion evidence (SmartStore menu aliases must remain provider-scoped):

- https://sell.smartstore.naver.com/
- https://help.sell.smartstore.naver.com/faq/list.help?rootCategoryId=525
- https://help.sell.smartstore.naver.com/faq/list.help?categoryId=527
- https://help.sell.smartstore.naver.com/faq/list.help?categoryId=11085
- https://safety.smartstore.naver.com/main/rules/safety/credit

### 12. Gig-worker account and earnings (`gig_worker_account_earnings`)

Distinct asset: independent worker account -> identity/eligibility/vehicle or
equipment documents -> work availability -> completed jobs -> earnings and
incentives -> payout/tax record -> quality rating -> restriction/deactivation and
appeal.  Offer discovery, acceptance and active dispatch execution remain owned
by the existing offer/dispatch domain; this domain owns worker-account and money
states, not consumer ordering or fleet-employer workforce administration.

Required lifecycle coverage: worker signup, eligibility and region, identity,
background-check status, required-document list/upload/expiry, vehicle/equipment,
training/onboarding, account activation, availability preference, completed-job
history, earnings summary/detail, fare or adjustment review, tips/incentives,
earnings statement, bank/tax information, payout method/schedule, failed payout,
rating/feedback, account warning, temporary hold, deactivation reason,
remediation, appeal eligibility, appeal evidence/submission/status/decision and
account exit.  Signup, document upload, bank/tax mutation, cash-out, remediation,
appeal and account exit are user-final; earnings information must not be treated
as tax or employment-law advice.

Direct official evidence opened 2026-07-30:

- https://help.lyft.com/hc/en-us/driver/articles/115013078888-How-to-see-your-earnings
- https://help.lyft.com/hc/en-us/driver/articles/115013080008-How-driver-pay-works
- https://help.lyft.com/hc/en-us/driver/articles/115012926307
- https://help.lyft.com/hc/en-us/all/articles/115013079948-Driver-and-passenger-ratings
- https://help.lyft.com/hc/en-us/all/articles/7366276697-Deactivations
- https://help.doordash.com/en-us/dashers/article/dasher-earnings-statements
- https://help.doordash.com/en-us/dashers/article/how-to-appeal-dasher-account-deactivations
- https://help.uber.com/driving-and-delivering/article/appeal-process-my-account-has-been-deactivated?nodeId=423f363a-71b2-4557-92e3-92246b35e5e3

Korean companion evidence (the public provider page covers onboarding, region,
equipment, bank account and settlement; in-app-only states require provider-
scoped aliases and must not be inferred from third-party blogs):

- https://join.baeminconnect.com/

Health-insurance member journeys and subscription billing are recorded as
existing-domain refinement candidates rather than new domains: the canonical
catalog already contains health-insurance certificate/eligibility/premium/refund
and insurance claim/contract paths, plus generic subscription management,
change, cancellation and automatic-payment functions.  V18 must add missing
states to those owners instead of creating parallel destinations.

## Required next gates

1. Extract all canonical plus V16/V17 function IDs and compare candidate
   role/asset/state tuples, not just domain names.
2. Require at least five direct official lifecycle sources and one Korean
   official companion source per accepted domain; jurisdiction-specific terms
   must remain isolated.
3. Write the normative bilingual domain/terminal table before aliases or intent
   patterns.
4. Create development-only collision probes against the five nearest existing
   domains for every accepted domain.
5. Have a separate author create sealed goal and stateful fixtures without
   reading aliases, intent patterns or runtime implementation.
6. Measure routability, safe-stop behavior, cross-domain false positives,
   deterministic materialization and time-to-confirmed-destination before any
   canonical promotion.
