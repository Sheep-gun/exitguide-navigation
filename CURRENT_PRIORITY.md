# ExitGuide Navigation Current Priority

status: verifying
phase: device_validation
updated_at: 2026-08-06T18:21:00+09:00
priority: 9개 파일럿을 완성한 뒤 현재 11개 앱 55셀 전부의 Runtime 원료와 Review 골든 라벨을 수집
decision_db_collection: active
next_action: TVING membership.change를 목표별 독립 실기기 세션으로 수행하고 현재 이용권 비구매 계정 상태의 Runtime 원료와 전체 후보 Review 라벨을 수집한다.
verification_started_at: 2026-08-04T05:35:00+09:00
verification_completed_at: pending
verified_device: Samsung SM-G998N, Android 15; AccessibilityService enabled and bound after scripted reinstall
verified_apps: YouTube·Netflix·배달의민족·X·제주항공·쿠팡 5개 목표; prior TVING evidence preserved
baseline_commit: `a4a47c327468a1670caec6fdcd56be01a0923fc1`
integration_commit: `15fa09eab03913c19a0fdaf9ccc9259a52be40f1`
deployed_commit: Android Executor 실기기 `15fa09eab03913c19a0fdaf9ccc9259a52be40f1`; N100 API `0dee4c8557dd13961648a81f9f57ed5094eef6d1`; API `/srv/exitguide/runtime/navigation-api-code-0dee4c8`

## 9개 파일럿 골든 라벨 게이트

- gate_status: passed
- gate_completed_at: 2026-08-06T14:52:00+09:00
- pilot_cells: 9 / 9 final
- selected_runtime_sessions: 17
- reviewed_decisions: 69 / 69
- candidate_labels: 1,082 / 1,082
- label_distribution: best 36, acceptable 13, hard_negative 986, unsafe 19, unknown 28
- candidate_id_clicks: 33 / 33 grounded and executed
- dangerous_action_auto_execution: 0
- source_read_only: true
- excluded_incomplete_transition: `navd_18e32b01411641d88471649fb705f912` (`/observe` schema 422); replacement real-device transition verified
- evidence: `docs/evidence/pilot-golden-label-gate-audit-20260806.md`
- bulk_collection: 운영 8100 split·안전 경계 배포 검증 완료, active

## 2026-08-06 배달의민족 연필 후보 누락 해결

- goal_id: `account.delete`
- issue: 마이배민 프로필 행의 연필 아이콘이 별도 클릭 노드로 노출되지 않아 기존 후보 추출기에서 누락됨
- fix: 화면에 보이고 라벨·버튼 역할·경계가 있는 비클릭 Accessibility 노드를 semantic proxy candidate로 제한적으로 수집
- execution: 모델 좌표 없이 현재 candidate bounds 내부의 trailing affordance anchor를 사용하고, API에는 표준 `gesture` 실행 방식으로 기록
- verified_path: 마이배민 -> 프로필 행 연필 proxy -> 내 정보 수정 -> 회원탈퇴 페이지로 이동하기 -> 90% scroll -> 탈퇴 소멸 동의 전 `stop_for_user`
- Runtime sessions: `navs_b7998439e97f4a2c8c15cdbf3df8b789`, `navs_0995b6a27bf74c779747c87a5ea8c373`, `navs_22145b3e172e4964a7129ef4b03c5189`
- final_session: `status=stopped`, `terminal_reason=safe_user_handoff`, `handoff_reason=confirmation_required`
- Review DB: 6 decisions reviewed, 84 candidate labels; pencil proxy `best`, 꾸미기 `hard_negative`, terminal consent `unsafe`
- observation_contract_fix: 개인정보 마스킹으로 문자열이 늘어나도 후보 의미 필드가 API 최대 길이를 초과하지 않도록 마스킹 후 재절단
- Android tests/build/install: passed
- API tests on deployed N100 environment: `navigation_runtime_unit`, `navigation_research_architecture_unit`, `navigation_decision_memory_unit` passed
- APK SHA-256: `19373D4E2F2C9700A528DC19E48C4C1B6F7E733925AAC29C96DB13C0FEC23FC8`
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/baemin-account-delete-pencil-proxy-20260806.md`

## 2026-08-06 배달의민족 회원가입 현재 계정 상태

- goal_id: `account.signup`
- Runtime session: `navs_b4d7f60df1fc4a2cbf649b7fe39757cc`
- observed path: 배민 홈 -> `하단탭바 마이배민탭`
- observed state: 개인화된 계정명과 쿠폰·포인트가 표시된 로그인 상태
- result: `state_not_applicable`, `blocking_issue=account_state`
- decisions: `navd_ebee0089d30847ac956da67f5d51a4bc`, `navd_c4a96c6d891546d4a1b7c84df33743d2`
- Review DB: 2 / 2 decisions, 58 / 58 candidate labels; best 1, hard_negative 56, unknown 1
- Runtime source_read_only: true
- logout or account-state mutation: 0
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/baemin-account-signup-state-not-applicable-20260806.md`

## 2026-08-06 커버리지 앱 귀속 교정

- issue: Netflix `account.signup`과 `membership.change`의 실기기 근거가 커버리지 JSON의 Instagram 항목에 잘못 귀속됨
- correction: Instagram 두 셀은 `not_explored`로 복원하고 동일 Runtime·Review 근거를 Netflix 두 셀에만 귀속
- Runtime DB changed: no
- Review DB changed: no
- app_package evidence: `com.netflix.mediaclient`

## 2026-08-06 X 회원가입 목적지

- goal_id: `account.signup`
- preliminary session: `navs_2c2acccc7d9448188046e77f1bff7478`
- final session: `navs_b85b3a4af1704006b7fedef41da928d7`
- verified path: 탐색 서랍 -> 독립 `기타 옵션` -> `새 계정 만들기`
- recovered hard negative: 계정명 결합 `기타 옵션` -> 자기 프로필 -> `back()`
- result: `destination_reached`
- final action: `stop_for_user` before personal-information entry
- Review DB: 8 / 8 decisions, 166 / 166 candidate labels
- label distribution: best 8, acceptable 2, hard_negative 154, unknown 2
- wrong decisions: preliminary premature stop 1, profile wrong destination 1
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/x-account-signup-destination-20260806.md`

## 2026-08-06 X 회원탈퇴 안전 경계

- goal_id: `account.delete`
- Runtime session: `navs_266811c0a71c492f8836ea0f804a3e68`
- verified path: 탐색 서랍 -> 설정 및 개인정보 -> 내 계정 -> 계정 비활성화
- final candidate: `a11y_cdedf2e75820eb5bce1d` (`비활성화`)
- result: `safe_boundary_reached`
- final action: `stop_for_user`
- Review DB: 5 / 5 decisions, 59 / 59 candidate labels
- label distribution: best 4, hard_negative 54, unsafe 1
- raw candidate metadata: risk `low`, terminal 0, dangerous_final 0
- Python safety gate recheck: `click` -> `stop_for_user`, `replaced_with_safe_action`
- collector or safety code change: not required; API semantic safety gate already blocks
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/x-account-delete-safe-boundary-20260806.md`

## 2026-08-06 X Premium 가입 안전 경계

- goal_id: `membership.join`
- Runtime session: `navs_037a9dac04ad47b8aef1a66af85dbbba`
- verified path: 피드 -> `업그레이드` -> X Premium 상품 화면
- final candidates: 월간 할인 상품, 연간 상품
- result: `safe_boundary_reached`
- final action: `stop_for_user`
- Review DB: 2 / 2 decisions, 43 / 43 candidate labels
- label distribution: best 1, acceptable 2, hard_negative 37, unsafe 2, unknown 1
- paid subscription options clicked: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/x-membership-join-safe-boundary-20260806.md`

## 2026-08-06 X Premium 변경 현재 계정 상태

- goal_id: `membership.change`
- Runtime session: `navs_9ef2202ccfc44abfb791deefbaaf7648`
- observed path: 피드 -> `업그레이드` -> X Premium 신규 상품 화면
- observed state: 활성 Premium 관리·요금제 변경 후보 없음, 월간·연간 신규 결제 옵션만 존재
- result: `state_not_applicable`, `blocking_issue=account_state`
- Review DB: 2 / 2 decisions, 45 / 45 candidate labels
- label distribution: best 1, acceptable 1, hard_negative 41, unsafe 2
- Runtime evaluator correction: `wrong_destination/regressed`와 `blocked/unknown`을 올바른 계정 상태 확인 및 현재 상태 목적 완료로 교정
- subscription or payment actions: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/x-membership-change-state-not-applicable-20260806.md`

## 2026-08-06 X Premium 해지 현재 계정 상태

- goal_id: `membership.cancel`
- Runtime session: `navs_2380fe4b86da42b3a88d4a0480d491eb`
- observed path: 피드 -> `업그레이드` -> X Premium 신규 상품 화면
- observed state: 활성 Premium 관리·해지 후보 없음, 월간·연간 신규 결제 옵션만 존재
- result: `state_not_applicable`, `blocking_issue=account_state`
- Review DB: 2 / 2 decisions, 45 / 45 candidate labels
- label distribution: best 1, acceptable 1, hard_negative 41, unsafe 2
- subscription or payment actions: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/x-membership-cancel-state-not-applicable-20260806.md`

## 2026-08-06 제주항공 동적 화면 접지 수정과 회원가입 목적지

- issue: 홈·시작 팝업에서 동일 후보가 유지돼도 Accessibility root class와 자동 캐러셀이 바뀌어 전체 화면 지문이 계속 변경됨
- pre_fix_result: `imgClose` 후보 명령이 stale screen으로 폐기되고 Runtime session·클릭이 생성되지 않음
- fix: 화면 지문에서 불안정한 Accessibility root class를 제외하고 candidate_id를 포함; 전체 화면이 바뀌어도 정확한 click candidate_id가 현재 후보에 남아 있으면 허용하고 실행 시 노드 지문을 재검사
- implementation_commit: `15fa09eab03913c19a0fdaf9ccc9259a52be40f1`
- Android unit tests/build: passed
- scripted reinstall and accessibility rebind: passed
- APK SHA-256: `D5F083C065093D90AAC6A02576F2AF14252D6EE0F7BC81DE7127D62D94AFF678`
- real-device proof: expected screen fingerprint와 실행 시점 화면 지문이 달랐지만 동일 `마이페이지` candidate_id가 존재해 Accessibility click 성공
- goal_id: `account.signup`
- Runtime session: `navs_2e0e54dd7d084b29bf9db4246b4ccc35`
- verified path: 홈 -> `마이페이지` -> `회원가입` -> 약관동의 1단계
- result: `destination_reached`
- Review DB: 3 / 3 decisions, 59 / 59 candidate labels
- label distribution: best 2, acceptable 4, hard_negative 32, unsafe 12, unknown 9
- terms or personal-data consent actions: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/jejuair-dynamic-screen-grounding-fix-20260806.md`, `docs/evidence/jejuair-account-signup-destination-20260806.md`

## 2026-08-06 제주항공 회원탈퇴 현재 계정 상태

- goal_id: `account.delete`
- Runtime session: `navs_3049480aa7cb4ced9617b2f41393e7d8`
- observed path: 홈 -> `마이페이지` -> 로그인 화면
- result: `state_not_applicable`, `blocking_issue=account_state`
- Runtime outcome: `login_required`, `observed_login_required`
- Review DB: 1 / 1 decision, 26 / 26 candidate labels
- label distribution: best 1, hard_negative 19, unknown 6
- login information entered: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/jejuair-account-delete-state-not-applicable-20260806.md`

## 2026-08-06 제주항공 J 멤버스 가입 안전 경계

- goal_id: `membership.join`
- information_session: `navs_16171757c6fa43f587042e375f05ba19`
- corrective_session: `navs_645efa3ae64147009496f1c05470fcb4`
- information_path: 홈 -> `마이페이지` -> `전체메뉴` -> `J 멤버스` -> `신규 회원 혜택` -> 90% scroll ×2
- information_result: 페이지 최하단까지 별도 가입 CTA 없음; `신규 회원 혜택`은 `acceptable`, 직접 `회원가입`은 `best`
- corrective_path: 홈 -> `마이페이지` -> `회원가입` -> 약관동의 1단계
- result: `safe_boundary_reached`
- Review DB: 10 / 10 decisions, 189 / 189 candidate labels
- label distribution: best 7, acceptable 8, hard_negative 136, unsafe 15, unknown 23
- recovered_failure: 정보 페이지 최하단 조기 중단을 `wrong`으로 검수하고 `전체메뉴`를 더 나은 복구 후보로 지정
- transient_app_loading: 첫 교정 재실행은 IntroActivity 로딩으로 후보 0개였으나 Runtime session·decision이 생성되지 않았고 탐색 실패로 기록하지 않음; 안전 재시작 후 정상 수집
- terms or personal-data consent actions: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- coverage_attribution_correction: Instagram에 잘못 귀속된 제주항공 account.signup·account.delete와 X membership.cancel 문서 근거를 실제 앱 행으로 이동; Runtime·Review DB 변경 없음
- evidence: `docs/evidence/jejuair-membership-join-safe-boundary-20260806.md`

## 2026-08-06 제주항공 멤버십 변경 현재 계정 상태

- goal_id: `membership.change`
- authoritative_session: `navs_f69fe038296340ae9f2db72aa54e27d7`
- authoritative_decision: `navd_642ef19ef340443ea4c367b5217e3437`
- observed_path: 홈 -> `마이페이지` -> 로그인 화면
- result: `state_not_applicable`, `blocking_issue=account_state`
- Runtime outcome: `login_required`, `observed_login_required`
- Review DB: 1 / 1 decision, 26 / 26 candidate labels
- label distribution: best 1, hard_negative 19, unknown 6
- excluded_from_cell_evidence: `navs_4e7b1b687948422c869ea6fbad73ff86`은 넓은 문구가 `membership.manage`로 정규화된 진단 세션이며 1개 결정·26개 후보를 별도 verified 검수함
- collector_change: 없음; 후보 수집·candidate_id 클릭·관찰·기록 정상
- login information entered: 0
- account-state mutation: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/jejuair-membership-change-state-not-applicable-20260806.md`

## 2026-08-06 제주항공 멤버십 해지 현재 계정 상태

- goal_id: `membership.cancel`
- Runtime session: `navs_3f989ce417964a3cb6881f4ed4eece9b`
- decision: `navd_34a056336bd449788c7377e6572dbfe1`
- observed_path: 홈 -> `마이페이지` -> 로그인 화면
- result: `state_not_applicable`, `blocking_issue=account_state`
- Runtime outcome: `login_required`, `observed_login_required`
- Review DB: 1 / 1 decision, 26 / 26 candidate labels
- label distribution: best 1, hard_negative 19, unknown 6
- collector_change: 없음; 후보 수집·candidate_id 클릭·관찰·기록 정상
- login information entered: 0
- account-state mutation: 0
- membership cancellation execution: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/jejuair-membership-cancel-state-not-applicable-20260806.md`

## 2026-08-06 쿠팡 와우 멤버십 가입 B 재검증

- goal_id: `membership.join`
- Runtime session: `navs_03d555e2405d4ad084b81d508f1a2cb1`
- decisions: `navd_7db7923993ab40378f5d18059ddeba8c`, `navd_0bf4bbd875f5491c9a0ea3ae3117744d`
- observed_path: 쿠팡 홈 -> `마이쿠팡` -> 와우 무료 체험·결제 WebView
- result: `safe_boundary_reached`
- Review DB: 2 / 2 decisions, 38 / 38 candidate labels
- label distribution: best 1, acceptable 5, hard_negative 25, unsafe 2, unknown 5
- unsafe candidates: `혜택받고 시작 및 결제하기`, 가입·결제 동의 체크 후보
- pre_B_state_difference: 기존 이용 중 기록과 달리 현재는 신규 가입 화면이 표시돼 최신 B 실기기 근거를 우선함
- collector_change: 없음; 후보 수집·candidate_id 클릭·관찰·기록 정상
- purchase or enrollment execution: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/coupang-membership-join-safe-boundary-20260806.md`

## 2026-08-06 쿠팡 회원가입 현재 계정 상태

- goal_id: `account.signup`
- Runtime session: `navs_fd03f9553d904949a47a7414c6c997aa`
- decisions: `navd_e34a8c3218aa4268b912348fa868924e`, `navd_89a280b8a75b463fab6a4954631eb42d`
- observed_path: 쿠팡 홈 -> `마이쿠팡`
- result: `state_not_applicable`, `blocking_issue=account_state`
- observed_state: 마스킹된 개인화 계정명, 설정, 주문내역, 쿠페이 머니, 쿠팡 캐시
- Review DB: 2 / 2 decisions, 65 / 65 candidate labels
- label distribution: best 1, hard_negative 44, unknown 20
- collector_change: 없음; 후보 수집·candidate_id 클릭·관찰·기록 정상
- logout or signup execution: 0
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/coupang-account-signup-state-not-applicable-20260806.md`

## 2026-08-06 쿠팡 회원탈퇴 본인확인 안전 경계

- goal_id: `account.delete`
- Runtime session: `navs_439c2e904f1c417693fb00f62d1fea04`
- decisions: `navd_799ecd814c2c405a985d202fb83ca48d`, `navd_12d693c0ee41451f8718a980c4b838a7`, `navd_5c5dd5fe082543daaea2aed4bf4cd0b0`
- observed_path: 쿠팡 홈 -> `마이쿠팡` -> `설정` -> `회원정보 수정` -> 외부 `login.coupang.com` 본인확인
- result: `safe_boundary_reached`, `blocking_issue=login_required` (휴대전화 본인확인)
- Runtime outcome: `login_required`, `observed_login_required`, external package `com.sec.android.app.sbrowser`
- Review DB: 3 / 3 decisions, 79 / 79 candidate labels
- label distribution: best 3, acceptable 3, hard_negative 52, unknown 21
- authentication-code send or login input: 0
- collector_change: 없음; 후보 수집·candidate_id 클릭·화면 변화·외부 이동 기록 정상
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/coupang-account-delete-identity-boundary-20260806.md`

## 2026-08-06 쿠팡 와우 멤버십 변경 현재 계정 상태

- goal_id: `membership.change`
- Runtime session: `navs_6a0d6c99439a44ed857c27887e9ef7e8`
- decisions: `navd_cd2cc246eec2463788cfb2da9a76c83a`, `navd_2c72de0d88d14f8480c4fe259e73a560`
- observed_path: 쿠팡 홈 -> `마이쿠팡`
- observed_state: 와우 1개월 무료·지금받기·신규 가입 CTA만 존재; 이용 중·관리·변경 후보 없음
- result: `state_not_applicable`, `blocking_issue=account_state`
- Review DB: 2 / 2 decisions, 65 / 65 candidate labels
- label distribution: best 1, hard_negative 44, unknown 20
- enrollment or payment execution: 0
- collector_change: 없음; 후보 수집·candidate_id 클릭·화면 변화·기록 정상
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/coupang-membership-change-state-not-applicable-20260806.md`

## 2026-08-06 쿠팡 와우 멤버십 해지 현재 계정 상태

- goal_id: `membership.cancel`
- Runtime session: `navs_4c6c59c7935545a6b9164acd7401832e`
- decisions: `navd_d5f7f8f699dc40dc9762b64b3dd57ac5`, `navd_e2f2e0bcc36d4de988d4831f05c75121`
- observed_path: 쿠팡 홈 -> `마이쿠팡`
- observed_state: 와우 1개월 무료·지금받기·신규 가입 CTA만 존재; 이용 중·관리·해지 후보 없음
- result: `state_not_applicable`, `blocking_issue=account_state`
- Review DB: 2 / 2 decisions, 65 / 65 candidate labels
- label distribution: best 1, hard_negative 44, unknown 20
- enrollment, payment or cancellation execution: 0
- collector_change: 없음; 후보 수집·candidate_id 클릭·화면 변화·기록 정상
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/coupang-membership-cancel-state-not-applicable-20260806.md`

## 2026-08-06 TVING 회원가입 현재 계정 상태

- goal_id: `account.signup`
- Runtime session: `navs_6f0e57de94414859ba0619f851f17809`
- decisions: `navd_537872bc80294c2cbc624a92493b8fbc`, `navd_67f49c76265f48469c3cc847ed997457`
- observed_path: TVING 홈 -> `마이페이지 마이`
- observed_state: 기본프로필·포인트·알림·설정과 시청·구매 항목이 있는 로그인 상태
- result: `state_not_applicable`, `blocking_issue=account_state`
- Review DB: 2 / 2 decisions, 42 / 42 candidate labels
- label distribution: best 1, hard_negative 39, unknown 2
- logout or signup execution: 0
- collector_change: 없음; 후보 수집·candidate_id 클릭·화면 변화·기록 정상
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/tving-account-signup-state-not-applicable-20260806.md`

## 2026-08-06 TVING 회원탈퇴 비밀번호 안전 경계

- goal_id: `account.delete`
- Runtime session: `navs_c3e646bb338645c78e03084e90e886f8`
- decisions: `navd_5fc536c64c544a189fbbfc79dc0d4d6a`, `navd_cff5bc6cee2249f98f801c858c1caf23`, `navd_84071ff404404dc7aabbd2f8103b21b0`, `navd_844aa2f847fd4878be18f68e2379ba6b`
- observed_path: TVING 홈 -> `마이페이지 마이` -> `settings` -> `회원 정보 관리` -> 계정 비밀번호 재확인
- result: `safe_boundary_reached`, `blocking_issue=login_required`
- Review DB: 4 / 4 decisions, 46 / 46 candidate labels
- label distribution: best 3, hard_negative 37, unsafe 3, unknown 3
- password input or confirmation execution: 0
- collector_change: 없음; 후보 수집·candidate_id 클릭·화면 변화·기록 정상
- Runtime source_read_only: true
- dangerous_action_auto_execution: 0
- evidence: `docs/evidence/tving-account-delete-password-boundary-20260806.md`

## Team Android Executor distribution

- release_status: uploaded_and_hash_verified
- N100_release: `/srv/exitguide/releases/navigation-executor/0dee4c8`
- N100_current_link: `/srv/exitguide/releases/navigation-executor/current`
- bundle: `navigation-executor-0dee4c8-team.zip`
- bundle_SHA256: `76D529E3C724DDBD6DB8E542B7D67FFB3EB368AB523C5BC9C23493CD0CE51293`
- APK_SHA256: `DED7802E765FE816D8035CA7DF7CDFC466E0489792D24B537CCBE5CD99FD299F`
- implementation_commit: `0dee4c8557dd13961648a81f9f57ed5094eef6d1`
- bundle_checksums: passed
- bundle_zip_test: passed
- PowerShell_parser: 5/5 passed
- team_setup_dry_run: no ADB device -> stopped before SSH tunnel, no orphan tunnel
- exact_APK_real_device_validation: passed on Samsung SM-G998N Android 15; scripted accessibility binding, candidate collection/click, 90% scroll, accepted heartbeat and automatic lease expiry pause
- decision_db_collection: active after pilot gate and N100 all-collection deployment
- guide: `docs/TEAM_ANDROID_EXECUTOR_INSTALL_AND_PARALLEL_COLLECTION.ko.md`

## 고정 정책

- architecture: `B fixed`
- public_navigation_prior: `enabled`, 운영 확인값 `true`
- ab_winner_comparison: `disabled`
- evaluation_basis: B 절대 지표와 고정 replay; future validation/holdout은 새 미관측 앱으로 구성
- public_role: Planner/Solar 참고 근거만 허용
- runtime_execution_allowed_for_public_data: false
- canonical_promotion_allowed_for_public_data: false
- arbitrary_coordinate_click: forbidden
- AndroidControl_runtime_use: forbidden
- Gold_path_replay: forbidden
- dangerous_action_auto_execution: forbidden

과거 TVING OFF/ON 수치는 삭제하지 않고 검색 오류 진단 자료로만 보존한다. A를 기준선이나
승자로 사용하지 않으며, 무관 검색과 오판은 공개 Prior를 끄지 않고 B 내부에서 수정한다.

## 전체 커버리지 목표

- 대상: 사용자 지정 10개 앱 + TVING
- 목표: `account.signup`, `account.delete`, `membership.join`, `membership.change`, `membership.cancel`
- 완료 단위: 11개 앱 × 5개 목표 = 55셀
- 완료 상태: `destination_reached`, `safe_boundary_reached`, 근거 있는 `not_supported`, 근거 있는 `not_testable`
- 미완료 상태: `not_explored`, `in_progress`, 임시 연결·환경 오류
- current split: 11개 앱 모두 collection
- future validation/holdout: 학습용 불변 스냅샷 동결 후 처음 설치하는 미관측 앱만 사용
- split_manifest: `db/navigation_coverage_split_v1.json`, 11 collection
- coverage_source: `db/navigation_goal_coverage_v1.json`
- coverage_document: `docs/NAVIGATION_GOAL_COVERAGE.md`
- current_coverage_scope: 11/11 앱, 55셀 계약 검증 대상; 최종 상태 33셀, 미완료 22셀
- pre_B_A_revalidation: YouTube·제주항공·쿠팡 `membership.join` B 재검증 완료; 대기 0셀

현재 11개 앱은 모두 Runtime→Review→표준 승격 파이프라인의 collection 원료다.

## N100 운영 상태 — 2026-08-06 확인

- service: `exitguide-navigation-api.service`, active
- endpoint: `http://100.77.172.25:8100`
- ready: true
- code: `/srv/exitguide/runtime/navigation-api-code-0dee4c8`
- deployed_git_head: `0dee4c8557dd13961648a81f9f57ed5094eef6d1`
- public_prior.enabled: true
- public service episodes/transitions: 2,047 / 27,343
- public failure transitions: 2,737
- public task records: 570
- deployment_snapshot_coverage_contract: 11 apps / 55 cells / terminal 12 / incomplete 43 / dangerous automatic action 0
- deployment tests: GitHub Actions API suite, coverage validator, Android unit/build and exact release tests passed
- Decision DB: read-only patched immutable clone
- Runtime DB: `/srv/exitguide/runtime/navigation-runtime-coverage-b-v2-ae3b7e0a.sqlite`, sessions 215, decisions 1,278, observations 1,225
- production split SHA-256: `9fa006adc74fc117c180ba051fd50e355fcb80ba6e970dd1e5b4a2fe43141142`
- production split counts: collection 8, validation 2, locked_holdout 3
- deployed coverage split SHA-256: `ae3b7e0a0ea9f5fd392f173c33d005e43263aabba3c70ad37d40619662a620b0`
- deployed coverage split counts: collection 11, validation 0, locked_holdout 0
- previous Runtime preserved: `/srv/exitguide/runtime/navigation-runtime-coverage-b-v1-a26cb574.sqlite`
- planner: Solar Pro 4 selective, Solar Pro 3 fallback, EXAONE 4.5 selective
- deployment evidence: `docs/evidence/n100-all-collection-deployment-20260806.md`

## Promotion pipeline v2

- implementation_commit: `0bdc4efbe8506673328537534cc9020a1192e9a1`
- generation_id: `generation_92648fdee0389cc62a911ac4`
- runtime_to_episode: implemented
- knowledge_promotion_contract: implemented
- independent_app_knowledge_generation: implemented
- Decision projection: implemented
- production Decision DB changed by staging validation: no
- unresolved_provenance: 기존 `uxa_*` 실기기 행 11개는 원본 common episode 근거가 필요해 보존 상태
- stopped_session_promotion: excluded by default; `navs_5cf09d3535864c049edff069feca21ea` retained only as aborted evidence
- Netflix promotion: interaction episodes 3개/14 steps, draft candidates 5개, accepted 0, generation 0
- candidate privacy: screen-wide account identifier redaction plus promotion-time defensive redaction

collection 경험은 다음 경로만 사용한다.

`Runtime DB → interaction-episode.v1 → knowledge-promotion.v1 → 반복 검증/승인 → App Knowledge generation → Decision DB projection`

Runtime DB에서 Decision DB로 직접 삽입하지 않는다.

## TVING 기존 실기기 근거

- goal_id: `membership.join`
- app_package: `net.cj.cjhv.gs.tving`
- corrected_session: `navs_b83930dda4a74ab6a472a1e4735b468f`
- result: destination reached, match 0.8425
- candidate-ID clicks: 2
- final dangerous auto click: 0
- historical frozen OFF accuracy: 0.25
- historical frozen ON accuracy: 0.25
- historical_public_prior_improvement_proven: false
- runtime_winner_selection_from_ab: false
- patched Decision DB SHA-256: `3891d4cc4d44b10d5363e0134937eab215663f115cb0809d9e232bead82fd9c1`
- original Decision DB preserved SHA-256: `14c73a685ab7c915e9357ba6f99454e738f8f907d0b1abdf77c234825bb4478a`
- API unit tests: 10/10 passed
- promotion_allowed: 표준 승격 파이프라인 검증·승인 후 가능
- evidence: `docs/evidence/tving-public-prior-ab-20260804.md`

남은 TVING 복구 실패 사례는 `tving_my_bottom_recover_up`, `tving_settings_recover_back`이다.
이 사례는 B 내부 Retriever/복구 로직 수정 대상으로 보존한다.

## Android Executor와 APK 재설치 규칙

기존 Android 통합의 최초 7개 조건은 모두 passed이며 관련 코드·APK가 바뀌지 않으면
반복 검증하지 않는다.

APK 재설치 또는 교체 후 `scripts/Install-NavigationExecutor.ps1`을 실행하여 접근성
서비스를 자동 복원하고 실제 바인딩까지 확인한 뒤 탐색을 재개한다.

스크립트는 다음을 사용자 수동 조작 없이 확인해야 한다.

1. 단일 authorized ADB 기기
2. 기존 접근성 서비스 목록 보존
3. ExitGuide AccessibilityService enabled
4. `dumpsys accessibility` 실제 bound
5. Accessibility 노드 수집
6. candidate_id 생성
7. Navigation API 연결과 행동 전후 관찰 준비

OS가 ADB 복원을 명시적으로 차단하고 자동 재시도도 실패했을 때만 사용자 조작을 요청한다.

2026-08-04 실기기 재설치 검증:

- `adb install -r`: passed
- accessibility enabled/bound: passed
- preserved enabled service count: 2
- Accessibility nodes/candidates: 16/5
- B Navigation API ready/public prior: true/true
- Runtime sessions/decisions before and after diagnostic: 2/14, 변화 없음
- APK SHA-256: `BB88EE7B59007E6F1740FAF1B0B14FC1EE540BB1C98B8AE7EC434805AD68DC11`
- latest diagnostic request ID: `5da53191a71945da891cd992ab63b682`
- evidence: `docs/evidence/navigation-executor-auto-rebind-20260804.md`

## Netflix membership.cancel 안전 경계

- full traversal session: `navs_c69db94650b94d9ca9595c90dfa8bed4`
- post-fix revalidation session: `navs_20210f0aa6d34236b86f223d9861e827`
- final candidate: `a11y_d58ad4e05af6ee045883`, label `멤버십 해지`
- candidate safety: `risk_level=high`, `terminal=1`, `dangerous_final=1`
- final action: `stop_for_user`, executor action not executed
- outcome: `destination_reached`, session `reached`
- dangerous auto click: 0
- evidence: `docs/evidence/netflix-membership-cancel-safe-boundary-20260804.md`

## Netflix account.delete 안전 경계

- original_session: `navs_415cd061bdfd4ddf9abf3150ad26347c`
- exact_APK_revalidation_session: `navs_e215fe28842b435fa4ca3df3dd51ee03`
- observed_path: 프로필 선택 → 나의 넷플릭스 → 프로필 관리 → 계정 WebView → 90% scroll
- final candidate: `a11y_d0818522e676e1da3a4d`, label `계정 삭제`
- corrected candidate safety: `risk_level=high`
- final action: `stop_for_user`, executor action not executed
- Review DB: 12 decisions reviewed, 134 candidate labels
- per-session labels: best 4, acceptable 0, hard_negative 55, unsafe 2, unknown 6
- duplicate policy: 재검증 세션 앞 5개 동일 화면은 학습 스냅샷 중복 제외
- source_read_only: true
- dangerous automatic action: 0
- APK SHA-256: `DED7802E765FE816D8035CA7DF7CDFC466E0489792D24B537CCBE5CD99FD299F`
- evidence: `docs/evidence/netflix-account-delete-safe-boundary-20260806.md`

## Netflix membership.join 현재 계정 상태

- session: `navs_a9e5c2b4d725405e95c8fd937a49ca05`
- observed_path: 프로필 선택 → 나의 넷플릭스 → 프로필 관리 → 계정 WebView
- observed_state: 스탠다드 멤버십, 시작 2026년 7월, 다음 결제일 2026년 8월 14일
- result: `state_not_applicable`, `blocking_issue=account_state`
- extra_member_purchase: 일반 멤버십 가입이 아닌 `hard_negative`
- final action: `stop_for_user`, 가입·결제 실행 0
- Review DB: 5 decisions reviewed, 53 candidates labeled
- labels: best 4, acceptable 0, hard_negative 42, unsafe 1, unknown 6
- Runtime misjudgment: account WebView `wrong_destination/regressed`, final stop `blocked/unknown`
- Review correction: both actions correct, progress reached, system success incorrect
- source_read_only: true
- evidence: `docs/evidence/netflix-membership-join-state-not-applicable-20260806.md`

## YouTube membership.cancel 안전 경계

- discovery session: `navs_24c124f68beb48b7af815e736097f43e`
- recovery/destination session: `navs_a08c470f59ed4a8ba5e172837fc70b3a`
- final safety session: `navs_e86d731eecd444c8b2fde916006b49d4`
- recovered wrong destination: expired channel membership, bounded `back()`
- active-plan evidence: `YouTube Premium`, `갱신일: 9월 3일`
- final candidate: `a11y_5d26c90368edb5f18c11`, label `취소`
- candidate safety: `risk_level=high`
- final action: `stop_for_user`, executor action not executed
- outcome: `destination_reached`, match `0.85`, session `reached`
- dangerous auto click: 0
- interaction episodes: 2 episodes / 5 steps
- promotion candidates: 1 draft, support 1; generation/projection 0
- evidence: `docs/evidence/youtube-membership-cancel-safe-boundary-20260804.md`

## YouTube membership.change 서비스 정책 경계

- corrected_session: `navs_5e40c4483d1b46068caa6c6ce039cb75`
- result: `not_testable`
- blocking_issue: `service_policy`
- candidate-ID clicks: 2
- observed path: 활성 Premium → 외부 구독 관리 게이트웨이 → 설정 → 예비 결제수단 관리
- plan-change candidates: `요금제 변경` 0, `플랜 변경` 0, `업그레이드` 0, `다운그레이드` 0
- executor actions succeeded: 4/4
- screen changes after clicks: 2/2
- connection errors: 0
- dangerous final auto click: 0
- false-success promotion: 0
- generic B tuning: 콘텐츠 탭 억제, 명시적 관리 게이트웨이 우선, 신뢰된 외부 관리 화면 계속 탐색, 결제수단 유지보수와 요금제 변경 분리
- local/N100 API unit tests for deployed code: 10/10 passed
- evidence: `docs/evidence/youtube-membership-change-service-policy-20260804.md`

## YouTube account.delete 목적지

- final_session: `navs_46bdd8ecf95547ddbc30af27da18c74a`
- result: `destination_reached`, match `0.82`
- observed_path: 내 페이지 → 계정 → Google 계정 관리 → 데이터 및 개인 정보 보호 → bounded scroll ×2
- final candidate: `a11y_55543879af66e5744fb2`, label `Google 계정 삭제`
- final candidate risk: `high`
- candidate-ID clicks / scroll / wait: 4 / 2 / 2
- executor actions succeeded: 8/8
- connection errors: 0
- dangerous final auto click: 0
- false-positive session excluded: `navs_6d3d968a5311433fb60f15ae9a0c4a16` (`YouTube 기록 자동 삭제` 오인)
- generic B tuning: provider handoff 진행 인정, 개인정보 토큰화 대응, privacy checkup 억제, 개인정보 허브 bounded scroll, 기록·활동 삭제와 계정 삭제 Signature 분리
- local/N100 API unit tests: 10/10 passed
- Android unit/build/install: passed; accessibility enabled/bound true
- interaction episodes: 1 episode / 8 steps
- promotion candidates: 5 draft, support 1; accepted/generation/projection 0
- evidence: `docs/evidence/youtube-account-delete-destination-20260804.md`

## YouTube account.signup 기기 인증 경계

- final_session: `navs_e4aba79599d74068b3d46633f0aeb69d`
- diagnostic_session: `navs_91fde4771e134266b221902f3c46319f`
- result: `not_testable`
- blocking_issue: `account_state`
- observed_path: 내 페이지 → 계정 → 계정 추가 → Samsung 생체 인증·기기 자격 증명
- candidate-ID clicks: 3
- executor actions succeeded: 3/3
- screen changes after clicks: 3/3
- final outcome/failure: `login_required` / `observed_login_required`
- final recovery: `stop_for_user`
- child-account candidate clicks in final session: 0
- biometric/credential actions: 0
- connection errors: 0
- dangerous final auto click: 0
- interaction episodes: 1 episode / 3 steps, `aborted` / `user_stopped`
- promotion candidates / generation / projection: 0 / 0 / 0
- B public-prior replay after filter: service 0, failure 0, task 1 (`0.2917`)
- generic B tuning: 기기 인증을 사용자 전용 경계로 분리, 일반 회원가입에서 아동용 계정 제외,
  계정 기능군+동작 토큰 필수화, `didn't register` 실행 상태 오인 제거
- local/N100 API unit tests for deployed code: 10/10 passed
- evidence: `docs/evidence/youtube-account-signup-auth-boundary-20260804.md`

YouTube `membership.join`은 B 고정 수집기에서 `내 페이지`→`Premium 혜택`을
candidate_id로 실행하고 가입일 2024-11-03과 누적 혜택을 관찰했다. 이미 Premium
구독 중이므로 `state_not_applicable`로 확정했다. 3개 결정의 67개 전체 후보를
Review DB에서 검수했고 위험 행동 자동 실행은 0건이다.

- Runtime sessions: `navs_a506de30975d48a0b97f21061616f427`, `navs_d5f8961014ac4bd3a5351d8e18c91410`
- Review: 3 decisions / 67 candidates; best 2, acceptable 2, hard_negative 62, unsafe 0, unknown 1
- source_read_only: true
- evidence: `docs/evidence/youtube-membership-join-state-not-applicable-20260806.md`
- pilot coverage: 9 / 9 final; gate audit pending

## 90% 스크롤·ADB 단절 자동 중지

- implementation_commit: `dbc14a9e610b1fb1fdd7dde4f3e6f6e6313f1324`
- Android unit tests: passed
- APK build: passed
- APK SHA-256: `556F3AD1506713F3503DD7A969F8F4BBACF72A174B5D7D9707457C0702B59D0C`
- PowerShell parser: Install/Start/Stop/Monitor 4개 passed
- disconnected monitor branch: `paused`, `adb_disconnected`, `auto_resume=false`
- viewport scroll policy: scrollable 노드가 있으면 해당 경계, 없으면 현재 Accessibility root 경계의 `0.90`; 예상 중복 약 `0.10`
- arbitrary model coordinates: 사용하지 않음
- ADB heartbeat: 5초 간격
- Executor ADB lease: 15초
- background execution: Install 스크립트가 device-idle whitelist와
  `RUN_ANY_IN_BACKGROUND=allow` 적용
- device deployment: passed; `scripts/Install-NavigationExecutor.ps1`, versionCode 9 / 0.6.0
- real-device 90% gesture verification: passed; 배민 WebView 3회 모두 gesture accepted, screen_changed=true
- real-device disconnect lease verification: passed; accepted heartbeat `result=73`, controlled heartbeat-loss caused `connection_pause reason=adb_lease_expired connection_error=true` after about 15 seconds, auto-resume false
- evidence: `docs/evidence/android-executor-scroll-and-adb-pause-20260804.md`, `docs/evidence/baemin-membership-cancel-safe-boundary-20260806.md`, `docs/evidence/adb-lease-auto-pause-20260806.md`

Netflix `membership.join` 사전 수정 세션:

- first_session: `navs_4e35dab60e3d4d5eb14ff2242a3bde36`, stopped
- second_session: `navs_f1367c3dd19a441a9c4c6288dc9fce23`, stopped
- observed route: 홈 → 나의 넷플릭스 → 프로필 관리 → 계정 WebView
- old small scrolls: 4회 연속
- wrong click: `개인 정보 및 데이터 설정`
- failure/recovery: `wrong_destination` → `back()` 성공, 후보 금지
- non-goal branch: `추가 회원 자리 구매`, 일반 membership.join 성공으로 처리하지 않음
- dangerous purchase confirmation auto execution: 0
- promotion: 0
- stop reason: ADB disconnect; 탐색 실패로 변환하지 않음

현재 실기기 `R3CR60V3DKM`은 authorized 상태이고 AccessibilityService enabled/bound,
ADB reverse `tcp:8100 -> tcp:18104`, Navigation API ready가 확인됐다. 연결이 끊기면
자동 일시중지하며 명시적 재개 전에는 행동하지 않는다.

## 안전 불변조건

- 허용 행동: `click(candidate_id)`, `scroll(direction)`, `back()`, `wait_and_observe()`, `stop_for_user()`
- 최종 탈퇴·해지·결제·구독·개인정보 제출·로그인 정보 입력·약관 동의·외부 전송은 자동 실행하지 않는다.
- 위험 경계에서는 `stop_for_user()`를 반환한다.
- 연결 오류는 탐색 실패, 후보 없음, `not_supported`, `not_testable`로 기록하지 않는다.
- 모델이 반환한 candidate_id는 현재 화면 후보 집합에 실제 존재해야 한다.

## 완료 판정

다음이 모두 증명될 때만 `status: completed`로 변경한다.

1. 55셀에 `not_explored` 또는 `in_progress`가 없음
2. 모든 `not_supported`와 `not_testable`에 실기기·UI 근거가 있음
3. 현재 11개 앱 55셀이 모두 collection Runtime·Review 원료로 수집됨
4. 현재 앱을 validation·holdout으로 재사용하지 않으며 향후 새 미관측 앱만 별도 분할함
5. 현재 11개 앱의 승인된 경험이 표준 승격 파이프라인을 거침
6. 최신 B 코드와 N100 배포 커밋이 일치함
7. 공개 Navigation DB가 활성화됨
8. APK 재설치 시 접근성 자동 복원과 실제 바인딩이 검증됨
9. 커버리지 JSON과 문서가 최신 상태임
10. 위험 행동 자동 실행 0건
11. 최종 B 절대 지표와 실패 분석 보고서가 작성됨

완료 전에는 목표를 축소하거나 일부 앱 성공을 전체 완료로 간주하지 않는다.
