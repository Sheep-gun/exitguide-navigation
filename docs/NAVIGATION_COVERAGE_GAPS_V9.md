# Navigation ontology coverage gap audit — v9

감사 기준일: 2026-07-30
감사 대상: `fixtures/navigation/function-catalog.v1.json`의 canonical v7과 `scripts/navigation_catalog_v8_data.py`의 구현 예정 v8
감사 목적: 특정 앱 이름·패키지·좌표·녹화 경로 없이, 처음 보는 Android 앱에서 재사용할 수 있는 다음 기능 목적지 묶음을 정한다.

> 상태(2026-07-30): v8은 canonical에 반영됐으며, 이 문서는 그 다음 v9 구현 범위를 고정한 설계 감사다.

## 결론

canonical v7은 89개 도메인, 1,046개 기능, 930개 intent를 가진다. v8은 여기에 서로 충돌하지 않는 8개 도메인, 146개 기능(허브 8개 + terminal 138개), 138개 intent를 더하므로, v8 반영 직후 예상 기준선은 **97개 도메인, 1,192개 기능, 1,068개 intent**다.

v9은 아래 10개 도메인을 다음 팩으로 권장한다. 제안 규모는 정확히 **194개 기능(허브 10개 + terminal 184개), 184개 intent**다. 모두 반영되면 예상 누계는 **107개 도메인, 1,386개 기능, 1,252개 intent**가 된다.

| 우선순위 | 도메인 ID | terminal | 허브 포함 기능 | intent | 핵심 역할 |
|---:|---|---:|---:|---:|---|
| 1 | `code_repository` | 18 | 19 | 18 | 개발 협업자 |
| 2 | `community_meetup` | 18 | 19 | 18 | 참가자·주최자 |
| 3 | `crowdfunding_donations` | 18 | 19 | 18 | 기부자·모금자·수혜자 |
| 4 | `public_ev_charging` | 18 | 19 | 18 | 공용 충전 이용자 |
| 5 | `nutrition_meal` | 18 | 19 | 18 | 식단 기록 사용자 |
| 6 | `language_translation` | 16 | 17 | 16 | 번역 사용자 |
| 7 | `fleet_driver_compliance` | 20 | 21 | 20 | 상용 운전자 |
| 8 | `hospitality_host` | 20 | 21 | 20 | 숙소 호스트 |
| 9 | `workplace_access` | 18 | 19 | 18 | 직원·방문객·보안 담당자 |
| 10 | `agriculture_ops` | 20 | 21 | 20 | 농장 운영자·작업자 |
| **합계** | **10개** | **184** | **194** | **184** | |

선정 기준은 (1) Android에서 실제로 반복되는 목적지인가, (2) v1~v8의 자산·역할·상태 기계로 정확히 표현하기 어려운가, (3) 처음 보는 앱의 텍스트·아이콘·접근성 트리만으로도 일반화할 가치가 큰가, (4) 잘못 안내했을 때의 피해를 명확한 중단 규칙으로 통제할 수 있는가다. canonical과 v8에서 새 도메인 ID는 모두 부재하며, 현재 카탈로그의 `repository`, `meetup`, `fundraiser`, `nutrition`, `translation`, `fleet`, `visitor`, `farm`, `agriculture` 관련 독립 목적지는 사실상 비어 있다. `charging`, `driver`, `host`, `donation`이라는 단어가 일부 존재하지만 아래에서 설명하는 역할과 자산은 다르다.

## v9 제안 팩 상세

아래 목록은 구현 시 사용할 terminal key의 고정 제안이다. 괄호의 `V`는 조회·탐색, `S`는 민감정보 조회, `C`는 외부 상태 변경 또는 제출을 뜻한다. `C`는 모두 `terminal=true`, `automation_policy=never_auto`, `stop_policy=before_action`이어야 한다. 결제·법적 기록·물리적 출입·차량 운행·기계 전송과 관련된 `S`도 최종 진입 전에 사용자 확인을 요구한다.

### 1. Code repository collaboration (`code_repository`) — 18 terminal

제안 terminal:

1. `account_switch` (S)
2. `repository_search` (V)
3. `code_search` (S)
4. `repository_tree` (S)
5. `file_view` (S)
6. `commit_history` (S)
7. `issue_list` (S)
8. `issue_detail` (S)
9. `issue_create` (C)
10. `issue_comment` (C)
11. `issue_close_reopen` (C)
12. `pull_request_list` (S)
13. `pull_request_detail` (S)
14. `diff_review` (S)
15. `review_comment` (C)
16. `review_submit` (C; approve/request changes를 상태 cue로 분리)
17. `merge_pull_request` (C)
18. `notification_triage` (C; done/save/unsubscribe를 분리)

중복 방지: `documents_cloud`의 파일 조회가 아니라 repository/branch/commit/issue/PR 객체를 가진다. `work_collaboration`의 일반 task/comment가 아니라 코드 변경 수명주기다. `incident_oncall`의 alert acknowledge와 GitHub notification done도 서로 다른 상태 변경이다.

공식 근거: [GitHub Mobile](https://docs.github.com/en/get-started/using-github/github-mobile?apiVersion=2022-11-28)은 Android에서 repository·code 검색, issue/PR 검토와 협업을 명시하고, [GitHub notification configuration](https://docs.github.com/en/subscriptions-and-notifications/get-started/configuring-notifications)은 mobile inbox의 done/save/unsubscribe·repository watch 흐름을 설명한다.

안전 경계: private repository 이름, 코드, diff, 조직 정보는 민감정보다. comment/review/close/merge는 조직 상태와 공개 기록을 바꾸므로 절대 자동 실행하지 않는다. `Approve`, `Request changes`, `Merge`는 동일한 PR 화면에서도 결과가 반대이므로 한 alias로 합치지 않는다.

### 2. Community and meetup organizing (`community_meetup`) — 18 terminal

제안 terminal:

1. `group_discovery` (V)
2. `group_join_request` (C)
3. `group_leave` (C)
4. `event_discovery` (V)
5. `event_detail` (V)
6. `event_rsvp` (C)
7. `event_waitlist` (C)
8. `event_fee` (C)
9. `attendee_list` (S)
10. `event_check_in` (C)
11. `group_discussion` (C)
12. `organizer_create_event` (C)
13. `organizer_edit_event` (C)
14. `organizer_publish_event` (C)
15. `organizer_venue` (C)
16. `organizer_member_requests` (C)
17. `organizer_member_moderation` (C)
18. `organizer_group_settings` (C)

중복 방지: `event_ticketing`은 좌석·티켓 구매/전송 중심이고, `sports_team`은 roster·경기 일정 중심이다. 이 도메인은 지속되는 지역·관심사 group, membership, RSVP/waitlist, organizer 권한을 소유한다. 참가자와 주최자 역할을 intent context에서 반드시 분리한다.

공식 근거: [Meetup for Organizers app FAQ](https://help.meetup.com/hc/en-us/articles/4481764411405-FAQs-about-the-Meetup-for-Organizers-app)는 group settings, venue, event fee 등 organizer 기능을 설명하며, [Meetup attendee management](https://help.meetup.com/hc/en-us/articles/9389668230541-Manage-attendees-and-track-attendance-for-your-Meetup-event)은 Android organizer app의 attendee/waitlist/check-in 상태를 명시한다.

안전 경계: join/leave/RSVP/payment/publish/member approval/removal은 모두 사용자 최종 클릭이다. attendee 이름·결제 여부·출석은 민감정보다. `Going`, `Not going`, `Waitlist`, `Checked in`, `Absent`를 독립 state cue로 둔다.

### 3. Crowdfunding and donations (`crowdfunding_donations`) — 18 terminal

제안 terminal:

1. `fundraiser_discovery` (V)
2. `fundraiser_detail` (V)
3. `donation_amount` (C)
4. `recurring_donation` (C)
5. `anonymous_donation` (C)
6. `donation_checkout` (C)
7. `donation_receipt` (S)
8. `donation_history` (S)
9. `share_fundraiser` (C)
10. `create_fundraiser` (C)
11. `edit_story_media` (C)
12. `publish_fundraiser` (C)
13. `post_update` (C)
14. `donor_thank_you` (C)
15. `beneficiary_invite` (C)
16. `beneficiary_accept` (C)
17. `transfer_setup` (C)
18. `transfer_status` (S)

중복 방지: `creator_monetization`은 콘텐츠 membership/tier/payout이고, `finance`는 계좌 송금이다. 이 도메인은 fundraiser campaign, donor, organizer, beneficiary, donation, fundraiser transfer라는 자산과 역할을 가진다. `healthcare_provider.organ_donation`의 장기기증 의사표시와 금전 donation은 강한 negative context로 분리한다.

공식 근거: [Creating a GoFundMe from start to finish](https://support.gofundme.com/hc/en-us/articles/360001992627-Creating-a-GoFundMe-from-start-to-finish)는 fundraiser 생성과 beneficiary 선택 흐름을, [GoFundMe beneficiary invitation](https://support.gofundme.com/hc/en-us/articles/204993267-How-to-invite-a-beneficiary-to-receive-funds)은 invitation·acceptance·bank transfer 소유권 변경을 설명한다.

안전 경계: donation checkout, recurring 설정, fundraiser publish, beneficiary invite/accept, bank transfer setup은 모두 금전·신원 상태 변경이다. 금액·통화·반복 여부·수혜자 이름·계좌 귀속을 확인한 화면에서 멈춘다. 모금 사기나 낯선 수혜자 초대 위험을 경고하되 사실 판정은 하지 않는다.

### 4. Public EV charging networks (`public_ev_charging`) — 18 terminal

제안 terminal:

1. `station_map` (V)
2. `station_search` (V)
3. `connector_filter` (V)
4. `station_availability` (V)
5. `station_detail` (V)
6. `pricing_idle_fee` (S)
7. `station_photos` (V)
8. `favorite_station` (C)
9. `waitlist_notify` (C)
10. `reserve_charger` (C)
11. `start_session` (C)
12. `live_session` (S)
13. `stop_session` (C)
14. `payment_methods` (C)
15. `charging_history` (S)
16. `receipt_download` (S)
17. `roaming_networks` (S)
18. `report_station_issue` (C)

중복 방지: `automotive_vehicle.charge_progress`와 `.charge_schedule`은 사용자가 소유한 차량/가정용 충전기의 배터리·예약 상태다. 이 도메인은 공용 station, connector, network, tariff, idle fee, session, roaming을 소유한다.

공식 근거: ChargePoint의 [Customer Experience User Guide](https://docs.chargepoint.com/ref-docs-sec/content/pdfs/7-misc/cust-exp/cp-cust-exp-ug.pdf)와 [ChargePoint Essential Cloud Plan](https://docs.chargepoint.com/ref-docs-sec/content/pdfs/7-misc/cp_essential_cloud_plan.pdf)은 mobile app에서 가용 충전기 탐색, session 시작·업데이트, station 사진·문제 신고를 제공한다고 설명한다.

안전 경계: connector 규격, station ID, 요금, idle fee, 연결 차량을 확인하기 전에는 session을 시작하거나 중단하지 않는다. 주행 중 조작을 금지하고 정차 상태가 확인되지 않으면 안내를 보류한다. 결제수단·예약·session start/stop은 사용자 소유다.

### 5. Nutrition, recipes, and meal planning (`nutrition_meal`) — 18 terminal

제안 terminal:

1. `food_search` (V)
2. `barcode_scan` (S)
3. `meal_scan` (S)
4. `voice_log` (S)
5. `serving_adjust` (C)
6. `food_log` (C)
7. `water_log` (C)
8. `food_diary` (S)
9. `macro_dashboard` (S)
10. `nutrient_goals` (C)
11. `recipe_create` (C)
12. `recipe_edit` (C)
13. `saved_meal` (C)
14. `meal_plan` (C)
15. `grocery_list` (C)
16. `fasting_window` (C)
17. `progress_report` (S)
18. `export_nutrition_data` (C)

중복 방지: `grocery_loyalty`는 상점 주문·쿠폰·포인트이고, `wellbeing_health`는 증상·수면·기분·주기다. 이 도메인은 food item, serving, meal, recipe, diary, macro/micronutrient, fasting window를 소유한다.

공식 근거: [MyFitnessPal food diary](https://support.myfitnesspal.com/hc/en-us/articles/360032274592-How-do-I-add-a-food-to-my-food-diary)는 Android의 food search, serving, meal, diary 기록을, [MyFitnessPal barcode scanner](https://support.myfitnesspal.com/hc/en-us/articles/360032624771-How-do-I-use-the-barcode-scanner-to-log-foods)는 camera permission, barcode result, 최종 confirm 흐름을 설명한다.

안전 경계: 식사·체중·영양 목표는 건강 관련 민감정보다. 잘못된 barcode 결과를 자동 확정하지 않고 음식명·1회 제공량·수량·식사 구분을 사용자에게 보여준다. 의학적 진단이나 치료 권고로 확장하지 않는다.

### 6. Translation and interpreting (`language_translation`) — 16 terminal

제안 terminal:

1. `language_pair` (V)
2. `text_translate` (S)
3. `camera_instant_translate` (S)
4. `image_import_translate` (S)
5. `speech_translate` (S)
6. `conversation_mode` (S)
7. `live_transcription` (S)
8. `handwriting_input` (S)
9. `pronunciation_playback` (V)
10. `copy_result` (C)
11. `share_result` (C)
12. `phrasebook` (S)
13. `translation_history` (S)
14. `offline_language_download` (C)
15. `offline_language_update_remove` (C)
16. `tap_to_translate_overlay` (C)

중복 방지: `education`의 language lesson/quiz가 아니라 source-target language pair와 text/image/speech 입력 modality를 가진 즉시 번역 작업이다. `accessibility`의 caption과 번역 결과도 목적이 다르다.

공식 근거: [Google Translate for Android](https://support.google.com/translate/answer/6350850?co=GENIE.Platform%3DAndroid&hl=en)은 text, handwriting, photo, speech 번역을, [Tap to Translate](https://support.google.com/translate/answer/6350658?hl=en)는 다른 앱 위 floating icon과 overlay permission을, [offline language download](https://support.google.com/translate/answer/6142473?co=GENIE.Platform%3DAndroid&hl=en)는 download/update/remove 상태를 설명한다.

안전 경계: clipboard, camera, microphone, imported image에는 비밀번호·문서·대화가 포함될 수 있다. 입력이 외부 서버로 전송될 수 있음을 표시하고 share/copy/history delete/overlay permission은 사용자 소유로 둔다. source와 target language가 뒤집힌 경우를 독립 contrastive fixture로 만든다.

### 7. Commercial fleet and driver compliance (`fleet_driver_compliance`) — 20 terminal

제안 terminal:

1. `fleet_select` (S)
2. `vehicle_select` (C)
3. `trailer_select` (C)
4. `driver_profile` (S)
5. `duty_status` (C)
6. `hos_clock` (S)
7. `hos_violations` (S)
8. `daily_log` (S)
9. `edit_hos_log` (C)
10. `certify_hos_logs` (C)
11. `roadside_inspection` (C)
12. `pretrip_dvir` (C)
13. `posttrip_dvir` (C)
14. `defect_report` (C)
15. `route_assignments` (S)
16. `route_start` (C)
17. `stop_arrival_departure` (C)
18. `dispatch_messages` (C)
19. `driver_documents_forms` (C)
20. `proof_of_delivery` (C)

중복 방지: `automotive_vehicle`은 개인 connected car, `parcel_courier`는 고객의 배송 추적, v8 `gig_worker_dispatch`는 gig offer/earnings다. 이 도메인은 fleet ID, commercial vehicle/trailer, HOS/ELD, DVIR, 규제 기록과 회사 dispatch를 소유한다.

공식 근거: [Samsara Driver App overview](https://kb.samsara.com/hc/en-us/articles/4423183155341-Get-Started-with-the-Samsara-Driver-App)는 HOS, DVIR, routes, dispatch messaging을, [Samsara Driver App settings](https://kb.samsara.com/hc/en-us/articles/360059559832-Samsara-Driver-App-and-Device-Settings)는 vehicle/trailer selection, route, form, document 기능을, [Certify Your Logs](https://kb.samsara.com/hc/en-us/articles/12018137810573-Certify-Your-Logs)는 `Certify and Submit`의 법적 기록 경계를 설명한다.

안전 경계: 차량이 움직이는 동안에는 어떤 탐색·스크롤·클릭도 수행하지 않는다. duty status, log edit/certify, DVIR, defect, route start/arrival/departure, document proof는 규제·고용 기록이므로 사용자 최종 클릭만 허용한다. 자동 기록된 drive time을 수정 가능한 것으로 안내하지 않는다.

### 8. Hospitality host operations (`hospitality_host`) — 20 terminal

제안 terminal:

1. `listing_switch` (S)
2. `listing_editor` (C)
3. `listing_photos` (C)
4. `amenities_rules` (C)
5. `host_calendar` (S)
6. `block_unblock_dates` (C)
7. `nightly_price` (C)
8. `discounts_fees` (C)
9. `availability_settings` (C)
10. `inquiry_requests` (S)
11. `reservation_detail` (S)
12. `accept_decline_request` (C)
13. `guest_messages` (C)
14. `quick_scheduled_reply` (C)
15. `checkin_guide` (C)
16. `reservation_modify` (C)
17. `host_cancel_reservation` (C)
18. `guest_review` (C)
19. `earnings_payouts` (S)
20. `cohost_access` (C)

중복 방지: `lodging_stays`는 숙박객의 검색·예약·체크인·환불 흐름이다. 이 도메인은 host 역할의 listing, availability calendar, incoming request, guest communication, payout, co-host 권한을 소유한다. `lodging.host_message`는 guest→host이고 여기의 `guest_messages`는 host→guest다.

공식 근거: [Airbnb host calendar](https://www.airbnb.com/help/article/447)은 Android에서 날짜 선택과 available/blocked 상태를, [Respond to a request to book](https://www.airbnb.com/help/article/28)은 24시간 내 accept/decline과 calendar 영향을, [co-host permissions](https://www.airbnb.com/help/article/1534)은 listing, price, reservation, guest message, payout 권한을 설명한다.

안전 경계: 가격·수수료·예약 수락/거절/취소·guest message·review·payout·co-host 권한은 사용자 소유다. 취소는 fee, calendar block, payout 손실을 초래할 수 있으므로 결과 요약을 먼저 보여준다. guest와 host 역할을 화면 문맥 없이 추정하지 않는다.

### 9. Workplace access and visitor management (`workplace_access`) — 18 terminal

제안 terminal:

1. `location_switch` (S)
2. `workplace_pass` (S)
3. `door_unlock` (C)
4. `desk_booking` (C)
5. `room_booking` (C)
6. `workplace_schedule` (S)
7. `visitor_invite` (C)
8. `visitor_edit_invite` (C)
9. `visitor_preregistration` (C)
10. `visitor_qr` (S)
11. `visitor_log` (S)
12. `visitor_detail` (S)
13. `visitor_approve_deny` (C)
14. `visitor_sign_in` (C)
15. `visitor_sign_out` (C)
16. `badge_reprint` (C)
17. `emergency_roll_call` (S)
18. `report_access_issue` (C)

중복 방지: `smart_home`의 개인용 door lock, `workspace_administration`의 SaaS user/permission, `calendar`의 일반 meeting room과 다르다. 이 도메인은 물리적 workplace/location, employee credential, visitor/host, badge, occupancy와 출입 상태를 소유한다.

공식 근거: [Envoy mobile app](https://envoy.help/en/articles/6960299-using-the-envoy-app-mobile)은 location 전환, employee profile, passport, auto check-in을, [registration with invites](https://envoy.help/en/articles/3444425-about-registration-with-invites)는 mobile visitor invite, QR registration, approve/deny를, [visitor log](https://envoy.help/en/articles/3444480-using-the-visitor-log)는 mobile visitor detail, sign-out, filter와 민감 필드를 설명한다.

안전 경계: door unlock, visitor approval/denial, sign-in/out, badge reprint는 물리 보안 상태 변경이다. 위치, 방문자 신원, 사진, ID check, 방문 기록, 현재 재실 여부는 민감정보다. 권한이 없거나 credential이 잠겨 있으면 대체 버튼을 추측하지 않고 종료한다.

### 10. Agriculture and farm operations (`agriculture_ops`) — 20 terminal

제안 terminal:

1. `organization_farm_switch` (S)
2. `field_map` (S)
3. `field_boundary` (C)
4. `crop_season` (C)
5. `machine_map` (S)
6. `machine_detail` (S)
7. `diagnostic_alert` (S)
8. `implement_status` (S)
9. `work_plan_list` (S)
10. `work_plan_create_edit` (C)
11. `work_plan_send_machine` (C)
12. `input_products` (C)
13. `tank_mix` (C)
14. `scouting_note` (C)
15. `field_flag` (C)
16. `planting_record` (S)
17. `application_record` (S)
18. `harvest_record` (S)
19. `yield_map` (S)
20. `farm_data_share_export` (C)

중복 방지: `automotive_vehicle`은 개인 차량, v8 `field_construction_ops`는 건설 site/work order다. 이 도메인은 farm organization, field boundary, crop season, machine/implement, agronomic product, planting/application/harvest operation, yield를 소유한다.

공식 근거: [John Deere Operations Center welcome](https://www.deere.com/en/technology-products/precision-ag-technology/operations-center/welcome/)은 mobile에서 equipment, land, field, boundary, flag와 작업 데이터를, [Work Planner](https://www.deere.com/en/technology-products/precision-ag-technology/operations-center/work-planner/)는 mobile work plan 생성·수정·기계 전송을, [Operations Center harvest](https://www.deere.com/en/technology-products/precision-ag-technology/operations-center/harvest/)는 machine/field/yield 분석과 data sharing을 설명한다.

안전 경계: boundary, crop season, work plan, product/tank mix, machine transmission, data share는 생산·장비·화학물질·권한 상태에 영향을 준다. agent는 실제 기계를 원격 조작하지 않으며, 전송 대상 organization/field/machine/product를 모두 확인한 뒤 최종 버튼 전에 멈춘다.

## 가장 위험한 교차 도메인 충돌

v9은 단순 alias 수를 늘리는 것보다 아래 충돌을 contrastive context로 먼저 해결해야 한다.

| 모호한 표면어 | 반드시 분리할 의미 |
|---|---|
| `review` / `검토` | PR review, guest review, fundraising update review, HOS log review |
| `merge` / `병합` | pull request merge와 support ticket merge(v8) |
| `issue` / `문제` | code issue, charger issue report, physical access issue, machine diagnostic |
| `history` / `기록` | commit, donation, charging, translation, food diary, HOS, visitor, harvest |
| `transfer` / `전송` | fundraiser bank transfer, translation share, work plan→machine, farm data share |
| `check-in` | meetup attendance, lodging guest check-in, workplace visitor sign-in, field job check-in(v8) |
| `host` | lodging host, meetup event host, workplace visitor host, network host(배제) |
| `log` | food diary, HOS legal log, visitor log, application/harvest record, app debug log(배제) |
| `route` | fleet dispatch route, gig trip(v8), map navigation, code repository route(배제) |
| `station` | EV charger, transit station, radio station, workstation(배제) |
| `field` | database form field, farm parcel, construction field, sports field |
| `approve` | PR review, member request, visitor access, beneficiary invitation acceptance |

각 충돌 그룹은 동일 locale의 positive probe와 최소 2개의 다른 역할·자산 negative probe를 가져야 한다. 표면어 하나만 일치할 때 terminal로 확정하지 말고, `role + asset + lifecycle state` 중 최소 두 축이 확인될 때만 높은 신뢰도를 부여한다.

## 구현·검증 계약

### 데이터 계약

- 앱 이름, package name, resource ID, 좌표, screenshot hash, 녹화 경로를 function/intent semantics에 넣지 않는다.
- 184개 terminal 각각에 `ko-KR`/`en-US` alias, positive/negative context, role hints, visible/unavailable state cue, risk cue, 공식 source ref를 둔다.
- 허브 10개는 탐색용이며 terminal이 아니다. 최종 목적지 184개만 intent를 가진다.
- `C` 전부와 금전·법적 기록·물리 출입·운행·기계 전송 관련 `S`는 `never_auto + before_action`으로 고정한다.
- unavailable/disabled/permission/subscription/role mismatch가 보이면 다른 위험 버튼을 대신 고르지 않고 fail-closed한다.
- 실제 비밀번호, repository 코드, 은행·기부·영양·위치·방문자·HOS·농장 데이터는 fixture나 telemetry에 저장하지 않는다.

### 정확한 검증 규모

1. **ontology 단위검사:** 10 domains, 194 functions, 184 intents를 정확히 검증한다.
2. **개발 semantic matrix:** intent당 4 probes — 한국어 positive 1, 영어 positive 1, 역할 반전 1, 동음이의/negative 1 — 총 **736 probes**를 둔다.
3. **독립 frozen fixture:** catalog에서 자동 생성하지 않은 **184 scenarios**를 둔다. 한국어 92, 영어 92로 균등 분할하고 총 step은 최소 736으로 한다.
4. **안전 gate:** 모든 state-changing/high-risk terminal에서 자동 click 0건, 최종 action은 `stop/no_click` 100%를 요구한다.
5. **충돌 gate:** 위 12개 표면어 충돌군을 각각 최소 8 probes로 구성한 **96-probe alias collision suite**를 별도로 둔다.
6. **회귀 gate:** v1~v8의 모든 independent fixture, catalog quality, deterministic materialization, idempotence, resolver latency를 그대로 통과해야 한다.
7. **출처 gate:** 도메인당 서로 다른 공식 문서 최소 2개, 총 **20개 이상의 official-primary source**를 registry에 등록하고 URL·publisher·수집일·검증 상태를 고정한다.

## 구현 순서

1. 10개 허브와 184개 terminal의 ID·역할·자산·상태 기계를 먼저 동결한다.
2. 공식 source registry와 source ref를 작성한다.
3. terminal별 한국어·영어 alias보다 먼저 role inversion, homonym, unavailable 문맥을 작성한다.
4. safety contract와 final-click 소유권을 코드 수준 invariant로 적용한다.
5. 736-probe 개발 matrix로 의미 충돌을 교정한다.
6. catalog와 독립적으로 작성한 184-scenario fixture를 마지막에 한 번 평가하고, 해당 실패 label을 다시 학습 데이터로 사용하지 않는다.
7. 실패를 고칠 때는 특정 앱명·화면 좌표를 추가하지 말고, role/asset/state context와 충돌 규칙을 일반화한다.

## 감사 한계와 다음 단계

이 문서는 v9 구현 계획이며, 구현 완료 증거가 아니다. 공식 문서는 기능의 존재와 상태 전이를 입증하지만 모든 Android 앱이 동일한 라벨을 사용한다는 뜻은 아니다. 또한 지역, 요금제, 조직 권한, 기기 상태에 따라 기능이 숨겨질 수 있다. 따라서 source 기반 ontology를 추가한 뒤에도 frozen independent fixture와 실제 기기 검증은 별도로 필요하다.

v9 이후에는 새 도메인을 무작정 늘리기보다, 실제 실패 로그에서 아직 소유자가 없는 `role + asset + lifecycle` 조합을 집계해 다음 팩을 선정해야 한다. 특히 의료 전문가 업무, 제조 품질관리, 창고 피킹, 학교 교직원 행정, 법률 사건관리처럼 책임과 권한이 큰 영역은 충분한 공식 근거와 안전 fixture를 확보한 뒤 별도 팩으로 다루는 것이 타당하다.
