# Navigation ontology coverage gap audit — v8

감사 기준일: 2026-07-30
대상: `fixtures/navigation/function-catalog.v1.json`의 canonical v6와 `scripts/navigation_catalog_v7_data.py`의 v7 확장안
관점: 앱별 좌표·패키지·녹화 경로가 아닌, 처음 보는 Android 앱에도 재사용할 수 있는 **범용 기능 목적지 온톨로지**

> 구현 상태(2026-07-30): 이 감사에서 제안한 8개 영역은 catalog v8에 반영됐다. 현재 canonical 기준선은 97개 영역·1,192개 기능·1,068개 목적이다. 아래 v6/v7 수치는 다음 팩을 고르던 당시의 감사 스냅샷으로 보존한다.

## 감사 결론

현재 canonical v6는 918개 기능, 810개 intent, 81개 도메인을 포함한다. 작성 중인 v7 모듈은 다음 8개 도메인에 128개 기능(도메인 허브 8개 + 목적지 120개)과 120개 intent를 추가하도록 설계되어 있다.

- `dating_discovery`
- `digital_library`
- `beauty_wellness_booking`
- `childcare_family_portal`
- `esign_notary`
- `creator_monetization`
- `crypto_assets`
- `sports_team`

따라서 이 문서에서는 위 89개 기존·예약 도메인을 다시 만들지 않는다. 그 이후에도 남는 공백 가운데 사용 빈도, 다른 도메인과의 의미적 분리 가능성, Android에서의 실제 탐색 가치, 공식 문서 근거, 오동작 시 피해를 함께 평가했다.

v8에서 먼저 구현할 8개 도메인은 아래와 같다. 예상 규모는 **146개 기능(허브 8개 + 목적지 약 138개)** 이다.

| 순위 | 권장 도메인 ID | 우선순위 | 예상 기능 수 | 선택 이유 |
|---:|---|---|---:|---|
| 1 | `credential_vault` | P0 | 18 | 로그인 보조 앱의 핵심인데 현재 `security.*`는 계정 보안 설정만 다룬다. 비밀값 노출 방지라는 독립 안전 정책도 필요하다. |
| 2 | `business_accounting` | P0 | 20 | 개인 금융과 다른 사업 장부·청구·비용 처리의 모바일 수요가 크고 기능 어휘가 명확하다. |
| 3 | `crm_sales` | P0 | 18 | 고객·리드·기회·파이프라인은 범용 업무 협업의 task/channel 모델로 표현할 수 없다. |
| 4 | `customer_support_agent` | P0 | 16 | 기존 `support.*`는 최종사용자 도움말이고, 상담원 티켓 처리 상태기계는 별도다. |
| 5 | `merchant_pos_inventory` | P0 | 20 | 결제·환불·재고 확정 등 고빈도이면서 피해 가능성이 큰 판매자 업무를 안전하게 안내할 필요가 있다. |
| 6 | `field_construction_ops` | P0 | 20 | 현장 작업지시·점검·도면·RFI·펀치리스트는 일반 task와 다른 상태·권한·증빙 구조를 가진다. |
| 7 | `gig_worker_dispatch` | P0 | 18 | 승객/주문자 앱과 달리 기사·배달원의 제안 수락부터 완료 증빙·정산까지를 다룬다. |
| 8 | `incident_oncall` | P0 | 16 | 모바일에서 긴급성이 높고, acknowledge/resolve 오안내의 조직적 피해가 커서 명시적 온톨로지가 필요하다. |

## 공백 상세

아래의 기능 수는 구현 전 설계 목표다. 각 숫자는 도메인 허브 1개를 포함한다. `submit`, `send`, `approve`, `accept`, `pay`, `refund`, `unlock`, `publish`, `resolve` 등 외부 상태를 바꾸는 목적지는 모두 `automation_policy=never_auto`, `stop_policy=before_action`으로 두고 **최종 클릭은 사용자 소유**로 유지한다.

### 1. Credential vault and authenticator (`credential_vault`) — P0, 18개

- 대표 목적: 저장된 로그인 찾기, 자격증명 추가·수정, 비밀번호 생성, Android 자동완성 설정, TOTP 코드 찾기, 인증 코드 가져오기·내보내기, 비밀 노트·카드·신원 항목 관리, vault 잠금, 긴급 접근, 보안 보고서 확인.
- 중복 방지: 기존 `security.password`, `security.two_factor`, `security.passkey`는 **특정 서비스 계정의 보안 설정**이다. 새 도메인은 여러 서비스의 비밀을 보관하는 **vault 자산과 authenticator 앱 자체**만 소유한다. Android의 일반 권한 화면도 `android_system`에 남긴다.
- 안전 경계: 비밀번호·TOTP·복구키를 플로팅 오버레이나 로그에 표시하지 않는다. 복사, 내보내기, 공유, 삭제, emergency access 승인, 자동완성 공급자 변경은 사용자 확인 직전에 멈춘다. 잠긴 vault는 우회하지 않고 생체/PIN 인증 화면에서 사용자에게 넘긴다.
- 공식 1차 문서 후보: [Bitwarden App settings](https://bitwarden.com/help/app-settings/), [Google Authenticator — Android](https://support.google.com/accounts/answer/1066447?co=GENIE.Platform%3DAndroid)

### 2. Business accounting, invoicing, and expenses (`business_accounting`) — P0, 20개

- 대표 목적: 사업체 전환, 대시보드, 고객·공급업체, 견적 작성, 송장 작성·발송, 결제 기록, 비용·영수증 촬영, bill 등록, 은행 거래 매칭·조정, 미수금 확인, 손익·현금흐름 보고서, 세금·회계사 접근.
- 중복 방지: `finance_long_tail`의 bill/loan/investment는 **개인 자금 사용자**의 목적이다. 새 도메인은 회사 원장, 회계기간, 거래 posting, customer/vendor 객체를 요구하는 **사업 회계 역할**만 다룬다. `hr_payroll`의 급여명세 조회와도 분리한다.
- 안전 경계: invoice 발송, 거래 posting/void, refund, payment link 발행, bank reconciliation 확정, 사용자·회계사 권한 변경은 사용자 소유다. 조회용 보고서와 초안 화면까지만 자동 탐색한다.
- 공식 1차 문서 후보: [QuickBooks mobile app and web capabilities](https://quickbooks.intuit.com/learn-support/en-us/help-article/compare-products/get-done-quickbooks-mobile-app-web/L9YN5gwQw_US_en_US), [Xero mobile apps](https://central.xero.com/s/article/Xero-for-mobile-US)

### 3. CRM and sales pipeline (`crm_sales`) — P0, 18개

- 대표 목적: lead·contact·account 찾기, 신규 lead 입력, lead 전환, opportunity 열기, 단계·금액·예정일 변경, 활동 기록, 통화·이메일 시작, follow-up task, quote 확인·발송, 승인 요청, territory·forecast 확인.
- 중복 방지: `work_collaboration`은 channel/meeting/task라는 **팀 협업 객체**를 다룬다. 새 도메인은 고객 계정, lead, opportunity, pipeline stage처럼 **매출 생애주기 객체**만 소유한다. 고객 문의 티켓은 다음 `customer_support_agent`에 둔다.
- 안전 경계: lead 전환, opportunity 단계 변경, quote 발송, 승인 요청, 고객에게 연락하기는 외부 상태 변경으로 취급한다. 전화번호·이메일·거래 금액은 민감 맥락으로 표시한다.
- 공식 1차 문서 후보: [Salesforce Mobile seller records](https://help.salesforce.com/s/articleView?id=sales.sales_mobile_app_view_records.htm&language=en_US&type=5), [Salesforce Mobile lead conversion](https://help.salesforce.com/s/articleView?id=000387247&language=en_US&type=1)

### 4. Customer-support agent workspace (`customer_support_agent`) — P0, 16개

- 대표 목적: ticket queue·view 열기, 검색·필터, ticket 상세, requester 프로필, 자신에게 할당, 다른 상담원에게 재할당, public reply, internal note, macro 적용, status·priority 변경, follower/CC, merge, spam·delete, SLA·notification 확인.
- 중복 방지: 기존 `support.help`, `support.chat`, `support.ticket`은 **서비스 고객이 도움을 요청하는 흐름**이다. 새 도메인은 권한을 가진 상담원의 queue와 ticket 상태기계만 다룬다. 일반 채팅은 `messaging`, 영업 고객은 `crm_sales`에 남긴다.
- 안전 경계: 답변 전송, internal/public 채널 선택, assign, status 변경, merge, spam, delete는 모두 사용자 소유다. 특히 public reply와 internal note를 강한 negative context로 상호 배제한다.
- 공식 1차 문서 후보: [Zendesk Support mobile app](https://support.zendesk.com/hc/en-us/articles/4408846407066-About-the-Zendesk-Support-mobile-app), [Working with tickets in the Support mobile app](https://support.zendesk.com/hc/en-us/articles/4408825697434-Working-with-tickets-in-the-Support-mobile-app)

### 5. Merchant POS and inventory (`merchant_pos_inventory`) — P0, 20개

- 대표 목적: item/SKU 검색, barcode scan, item·variant·modifier 편집, 가격·세율, 재고 조회, stock receive/adjust/count, low-stock alert, vendor·purchase order, cart, discount, 결제 수단, 영수증, refund, cash drawer, register close, 일매출 보고서.
- 중복 방지: `commerce`는 구매자의 cart/order/return, `marketplace`는 개인 판매 listing이다. 새 도메인은 **사업자·점원 역할**, 매장/location, 재고 원장, POS tender와 shift를 요구한다.
- 안전 경계: charge, refund, discount 확정, stock adjustment/count 승인, drawer open, register close, 가격·세금 저장은 사용자 소유다. 카메라 barcode 인식 결과도 SKU와 수량을 보여준 뒤 확정하게 한다.
- 공식 1차 문서 후보: [Square — view, receive, and adjust inventory](https://squareup.com/help/us/en/article/6110-manage-inventory-with-the-retail-pos-app), [Square — inventory counts](https://squareup.com/help/us/en/article/8249-conduct-full-inventory-counts-with-square-for-retail)

### 6. Field service and construction operations (`field_construction_ops`) — P0, 20개

- 대표 목적: project/site 전환, work order, dispatch·schedule, job check-in, timecard, drawing·spec, RFI, submittal, daily log, photo·attachment, inspection, incident·safety observation, punch item, material/equipment, customer signature, complete/close job, offline sync.
- 중복 방지: `home_services`는 소비자가 수리기사를 예약하는 흐름이고 `work_collaboration`은 일반 task다. 새 도메인은 **현장 위치·도면·작업지시·점검·증빙·승인**을 결합한 작업자/감독자 상태만 소유한다.
- 안전 경계: check-in/timecard 제출, inspection 승인·거절, RFI/submittal 발송, 안전사고 보고, 고객 서명, job close는 사용자 소유다. 역할 권한이 보이지 않으면 작업 가능 여부를 추측하지 않는다.
- 공식 1차 문서 후보: [Procore Android app user guide](https://support.procore.com/procore-mobile-android/user-guide), [Procore Punch List for Android](https://support.procore.com/procore-mobile-android/user-guide/punch-list-android)

### 7. Gig-worker offer and dispatch lifecycle (`gig_worker_dispatch`) — P0, 18개

- 대표 목적: go online/offline, service type, offer card·upfront pay, accept/decline, pickup navigation, rider/customer 연락, arrive/wait, pickup 확인, multi-stop, drop-off·proof, cancellation reason, safety help, ratings, trip history, earnings, incentives, instant cash-out.
- 중복 방지: `ride_hailing_extended`와 `mobility_delivery`는 **승객·주문자 역할**이다. 새 도메인은 기사·배달원의 availability, offer, proof, payout을 갖는 **공급자 역할**만 소유한다. 규제 HOS/DVIR은 `fleet_driver_compliance`로 분리한다.
- 안전 경계: online 전환, offer 수락·거절, 취소, pickup/drop-off 확인, proof 제출, 고객 연락, cash-out은 사용자 소유다. 운전 중에는 자동 터치하지 않고 음성/정차 상태 등 별도 안전 조건이 없으면 안내도 최소화한다.
- 공식 1차 문서 후보: [Uber Driver — viewing trip earnings](https://help.uber.com/driving-and-delivering/article/where-can-i-see-my-trip-earnings?nodeId=9fbc207b-2837-4428-8133-2d2df7b3b17d), [Uber Driver — upfront price model](https://help.uber.com/en/driving-and-delivering/article/understand-the-calculation-of-prices?nodeId=470cd474-831c-4e01-8e5a-3032ca39bab1)

### 8. Incident response and on-call operations (`incident_oncall`) — P0, 16개

- 대표 목적: open incident queue, urgency/priority sort, incident detail·timeline, acknowledge, snooze, reassign, escalate, add responder, conference bridge, status update, runbook/workflow, related incidents, resolve, resolved history, on-call shift·schedule, service status.
- 중복 방지: `safety`는 개인 긴급·사기·안전 기능이고 `work_collaboration`은 일반 업무 대화다. 새 도메인은 **서비스 장애 incident와 escalation policy/on-call 상태기계**만 소유한다.
- 안전 경계: acknowledge도 조직이 대응을 인수했다는 외부 상태 변경이므로 resolve와 동일하게 사용자 소유다. reassign, escalate, responder 추가, workflow 실행, status update, resolve도 자동 실행하지 않는다. 긴급성 때문에 신뢰도 문턱을 낮추지 않는다.
- 공식 1차 문서 후보: [PagerDuty Mobile App](https://support.pagerduty.com/main/docs/mobile-app), [PagerDuty Mobile App Settings](https://support.pagerduty.com/main/docs/mobile-app-settings)

## v8 이후의 다음 공백

다음 10개도 현재 v1~v7의 의미 공간에 충분히 포함되지 않는다. P0 8개가 안정화된 뒤 동일한 데이터 계약으로 확장한다.

### 9. Code repository collaboration (`code_repository`) — P1, 16개

- 대표 목적: repository·code 검색, issue/PR 열기, review thread, diff 보기, comment, approve/request changes, merge, notification triage, workflow run 상태, rerun/cancel, release 확인.
- 중복 방지: 일반 file/task 협업이 아니라 commit/branch/issue/PR/check라는 소프트웨어 변경 객체만 소유한다. `incident_oncall`의 운영 장애 대응과도 분리한다.
- 안전 경계: comment 전송, review 제출, merge, issue close, workflow rerun/cancel은 사용자 소유다.
- 공식 1차 문서 후보: [GitHub Mobile](https://docs.github.com/en/get-started/using-github/github-mobile?apiVersion=2022-11-28)

### 10. Community and meetup organizing (`community_meetup`) — P1, 18개

- 대표 목적: group 발견·가입·탈퇴, event RSVP·waitlist, attendee list, venue, organizer event 생성·편집, 공지, fee, check-in, member request 승인·거절, member moderation.
- 중복 방지: `event_ticketing`은 좌석·티켓 구매/전송이고, v7 `sports_team`은 팀 roster/schedule이다. 새 도메인은 지속되는 관심사 커뮤니티의 membership과 organizer 권한을 소유한다.
- 안전 경계: 가입·탈퇴, RSVP, 이벤트 게시, fee 설정, 회원 승인·제거는 사용자 소유다.
- 공식 1차 문서 후보: [Meetup for Organizers app setup](https://help.meetup.com/hc/en-us/articles/4424531081229-Setting-up-the-Meetup-for-Organizers-app), [Meetup organizer app FAQ](https://help.meetup.com/hc/en-us/articles/4481764411405-FAQs-about-the-Meetup-for-Organizers-app)

### 11. Donations and crowdfunding (`crowdfunding_donations`) — P1, 16개

- 대표 목적: fundraiser 검색·공유, 기부·반복기부, tip, 익명성·표시명, receipt, fundraiser 생성·편집·게시, update, donor message, beneficiary invite, identity/bank verification, transfer status.
- 중복 방지: v7 `creator_monetization`은 콘텐츠 멤버십·tier·payout이고, `finance`는 계좌 송금이다. 새 도메인은 공익/개인 모금 campaign, donor, beneficiary, donation을 소유한다.
- 안전 경계: 기부 결제, recurring donation, campaign publish, beneficiary 초대, 은행 연결, transfer setup은 사용자 소유다. 기부자·수혜자 신원 및 은행 문서는 민감 정보다.
- 공식 1차 문서 후보: [GoFundMe transfer setup](https://support.gofundme.com/hc/en-us/articles/360001992767-How-to-set-up-transfers), [GoFundMe beneficiary invitation](https://support.gofundme.com/hc/en-us/articles/204993267-How-to-invite-a-beneficiary-to-receive-funds)

### 12. Public EV charging networks (`public_ev_charging`) — P1, 16개

- 대표 목적: charger 지도·검색, connector/power 필터, availability, tariff·idle fee, station detail·사진·팁, waitlist/notify, reserve, start/stop session, live session, payment method, receipt/history, roaming, issue report.
- 중복 방지: `automotive_vehicle.charge_progress`와 `.charge_schedule`은 **차량 내부 배터리/충전 설정**이다. 새 도메인은 공용 충전소 사업자의 station, connector, session, tariff를 소유한다.
- 안전 경계: 예약, session 시작·중지, 결제수단 변경, 결제, issue 제출은 사용자 소유다. 충전기 ID와 실제 연결 차량을 확인한 뒤 경계에 도달해야 한다.
- 공식 1차 문서 후보: [ChargePoint Customer Experience User Guide](https://docs.chargepoint.com/ref-docs-sec/content/pdfs/7-misc/cust-exp/cp-cust-exp-ug.pdf)

### 13. Nutrition, recipes, and meal planning (`nutrition_meal`) — P1, 18개

- 대표 목적: food search, barcode/meal/voice scan, serving·meal 선택, food/water log, diary, macro·nutrient 목표, recipe 생성·수정, saved meal, meal plan, grocery list 연계, fasting window, report/export.
- 중복 방지: `grocery_loyalty`는 매장 shopping/rewards이고 `wellbeing_health`는 약·검사·증상·주기다. 새 도메인은 음식·영양소·recipe·meal diary만 소유한다.
- 안전 경계: 식사·체중·영양 목표는 건강 민감 데이터다. log/save/delete/share/export는 사용자 소유이며 의료 진단처럼 표현하지 않는다.
- 공식 1차 문서 후보: [MyFitnessPal — add food to diary](https://support.myfitnesspal.com/hc/en-us/articles/360032274592-How-do-I-add-a-food-to-my-food-diary), [MyFitnessPal — barcode scanner](https://support.myfitnesspal.com/hc/en-us/articles/360032624771-How-do-I-use-the-barcode-scanner-to-log-foods)

### 14. Translation and interpreting (`language_translation`) — P1, 15개

- 대표 목적: source/target language, text translation, camera/image translation, speech, bilingual conversation, transcription, handwriting, listen/copy/share, phrasebook/history, offline language download/update/remove, tap-to-translate overlay.
- 중복 방지: `education`의 course/lesson/quiz는 학습 관리다. 새 도메인은 입력 modality와 language pair를 갖는 즉시 번역 작업만 소유한다.
- 안전 경계: 클립보드·카메라·마이크 입력은 민감할 수 있으므로 외부 전송 여부를 표시한다. overlay 권한, 언어팩 다운로드/삭제, history 삭제, 번역 공유는 사용자 소유다.
- 공식 1차 문서 후보: [Google Translate Help](https://support.google.com/translate/?hl=en), [Google Translate — Tap to Translate on Android](https://support.google.com/translate/answer/6350658?hl=en), [Google Translate — offline languages](https://support.google.com/translate/answer/6142473?co=GENIE.Platform%3DAndroid&hl=en)

### 15. Commercial fleet and driver compliance (`fleet_driver_compliance`) — P1, 18개

- 대표 목적: vehicle/trailer 선택, duty status, HOS clock·violation, log review·certify·edit, DVIR/inspection, defect/photo, route assignment·start, dispatch message, document/form, fuel/receipt, proof of delivery, safety alert.
- 중복 방지: `automotive_vehicle`는 개인 connected car, `parcel_courier`는 소비자 배송 추적, `gig_worker_dispatch`는 단건 gig offer다. 새 도메인은 fleet ID, 상용차, 규제 HOS, DVIR과 회사 dispatch를 소유한다.
- 안전 경계: duty status, HOS edit/certify, DVIR 제출, defect 확인, route start, proof 제출은 법적·운영 기록이므로 사용자 소유다.
- 공식 1차 문서 후보: [Samsara Driver App getting started](https://kb.samsara.com/hc/en-us/articles/4423183155341-Get-Started-with-the-Samsara-Driver-App), [Samsara Driver App and device settings](https://kb.samsara.com/hc/en-us/articles/360059559832-Samsara-Driver-App-and-Device-Settings)

### 16. Hospitality host operations (`hospitality_host`) — P1, 18개

- 대표 목적: listing 전환·편집, photos/amenities/rules, host calendar, availability block/unblock, nightly price·discount, inquiry, reservation accept/decline, guest message, check-in guide, cancellation, review, payout·tax document, co-host access.
- 중복 방지: `lodging_stays`는 숙박객의 검색·예약·체크인 흐름이고 `property`는 장기 주거·임대 신청이다. 새 도메인은 숙소 공급자인 host의 listing, calendar, reservation, payout을 소유한다.
- 안전 경계: listing publish, calendar block, 가격 변경, 예약 수락·거절·취소, guest message, payout/co-host 변경은 사용자 소유다.
- 공식 1차 문서 후보: [Airbnb — updating the host calendar](https://www.airbnb.com/help/article/447)

### 17. Workplace access and visitor management (`workplace_access`) — P2, 16개

- 대표 목적: workplace/location 전환, employee pass, desk/room reservation, visitor invite·edit, guest registration/QR, visitor log, arrival notification, approve/deny visitor, badge, sign-in/out, emergency roll call, access issue.
- 중복 방지: `smart_home`은 가정용 lock/device이고 `workspace_administration`은 SaaS 데이터·공유 권한이다. 새 도메인은 물리적 사업장, visitor/host, 출입 credential과 occupancy를 소유한다.
- 안전 경계: 문 열기, 출입 승인·거절, visitor invite, badge 발급, 타인 sign-out은 물리 보안 상태 변경이므로 사용자 소유다. 위치·방문 기록은 민감 정보다.
- 공식 1차 문서 후보: [Envoy mobile app](https://envoy.help/en/articles/6960299-using-the-envoy-app-mobile), [Envoy visitor registration and invites](https://envoy.help/en/articles/3444425-about-registration-with-invites), [Envoy mobile visitor log](https://envoy.help/en/articles/3444480-using-the-visitor-log)

### 18. Agriculture and farm operations (`agriculture_ops`) — P2, 20개

- 대표 목적: organization/farm 전환, field/boundary, crop season, machine/implement status·location, diagnostic alert, work plan/order, dispatch to machine, input/tank mix, scouting note·flag, planting/application/harvest record, yield map, weather, data upload/export/share, team/dealer access.
- 중복 방지: `automotive_vehicle`은 개인 차량, `field_construction_ops`는 건설 site/work order다. 새 도메인은 field boundary, crop season, implement, agronomic operation과 yield라는 농업 자산을 소유한다.
- 안전 경계: boundary 수정, work plan 전송, 기계 원격 제어, input/application 기록, 데이터 삭제·공유, 팀·딜러 접근 권한 변경은 사용자 소유다. 실제 장비 제어를 단순 navigation으로 오인하지 않는다.
- 공식 1차 문서 후보: [John Deere Operations Center](https://www.deere.com/en/technology-products/precision-ag-technology/operations-center/), [John Deere Operations Center Work Planner](https://www.deere.com/en/technology-products/precision-ag-technology/operations-center/work-planner/)

## 구현 시 중복 방지 규칙

1. **행위자부터 분리한다.** `rider`와 `driver`, `guest`와 `host`, `customer`와 `support_agent`, `employee`와 `visitor`, `donor`와 `fundraiser_owner`를 intent의 positive context에 넣고 반대 역할은 negative context에 넣는다.
2. **자산 종류를 명시한다.** 개인 bill과 사업 invoice, 차량 배터리와 공용 charging session, 일반 task와 construction punch item, 채팅 message와 support ticket reply를 같은 alias만으로 판정하지 않는다.
3. **생애주기 상태를 저장한다.** draft/sent/paid/void, lead/qualified/converted, triggered/acknowledged/resolved, offered/accepted/picked-up/completed처럼 허용 가능한 다음 상태를 `state_cues`에 넣는다.
4. **역할·권한을 추측하지 않는다.** 버튼이 보이지 않으면 관리자 권한을 가정해 다른 위험 버튼을 고르지 않는다. unavailable/disabled/permission-required 상태로 종료한다.
5. **동음 alias는 contrastive fixture를 먼저 만든다.** `invoice`, `ticket`, `check-in`, `transfer`, `approve`, `close`, `report`, `history`, `balance`, `profile`은 도메인 단서가 없으면 단독 고신뢰 매칭을 금지한다.
6. **앱 고유 이름을 핵심 식별자로 쓰지 않는다.** 공식 제품 문서는 기능 존재를 증명하는 근거일 뿐이며 function ID, alias, route는 특정 패키지·좌표·화면 위치에 종속시키지 않는다.

## 공통 안전 계약

- 읽기 전용 hub/list/detail 탐색만 `safe_navigation` 후보가 될 수 있다.
- 외부 상태, 금전, 법적 기록, 권한, 물리 접근, 신원·비밀, 타인과의 통신을 바꾸는 모든 terminal은 `never_auto` + `before_action`이다.
- 최종 버튼은 agent가 누르지 않는다. 목적지 화면과 버튼명을 확인한 뒤 사용자가 직접 누른다.
- 비밀값·건강정보·아동정보·고객정보·위치·은행정보는 오버레이, 학습 로그, fixture 원문에 저장하지 않는다. fixture에는 합성·비식별 값만 쓴다.
- UI가 예상 상태와 다르거나 confidence가 낮거나 복수 후보가 충돌하면 fail-closed로 멈추고, 뒤로가기/다른 후보 선택을 사용자에게 요청한다.
- 운전 중·장비 동작 중에는 터치 탐색을 수행하지 않는다. motion/drive 상태를 신뢰성 있게 알 수 없으면 정차 후 재개하도록 한다.

## v8 완료를 주장하기 위한 증거

v8 구현은 기능 레코드 수만 늘었다고 완료가 아니다. 최소한 다음 증거가 모두 필요하다.

- 8개 P0 도메인의 모든 기능에 한국어/영어 alias, positive/negative context, role hints, state cues, risk cues, source refs가 존재한다.
- 모든 source ref가 이 문서의 공식 후보 페이지에서 실제 기능을 뒷받침하며, 수집일·publisher·URL·검증 상태가 registry에 저장된다.
- state-changing/high-risk 기능 100%가 `never_auto`, terminal, `before_action`을 만족한다.
- 각 목적지마다 최소 한국어 1개·영어 1개의 **catalog-derived가 아닌 frozen 독립 fixture**가 있고, 위험 terminal의 기대 행동은 `stop/no_click`이다.
- 역할 반전, 상태 반전, 동음 alias, unavailable/disabled, 로그인/권한 gateway, 목록 스크롤 종료, 잘못된 앱/도메인 화면을 포함한 다단계 복구 fixture가 있다.
- 기존 v1~v7 independent fixture와 catalog quality gate가 회귀 없이 통과한다.
- resolver 성능은 전체 catalog 크기 증가 후에도 별도 측정하며, 정확도를 희생한 alias 삭제로 속도를 맞추지 않는다.

이 감사는 v8의 다음 확장 순서를 정한 것이며, “가능한 모든 경우의 수”가 완성되었다는 증거는 아니다. P0 8개를 구현·검증한 뒤 P1/P2 목록과 새롭게 관찰된 실패 군집을 다시 감사해야 한다.
