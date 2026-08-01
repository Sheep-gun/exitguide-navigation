# Navigation function equivalence audit

## 결론

현재 캐노니컬 `fixtures/navigation/function-catalog.v1.json`(`catalog_version = 15.0.0`)에는 서로 다른 `function_id`가 같은 사용자 목적지를 나타내는 **진정한 동치 그룹이 10개** 있다. 이 그룹은 20개 물리 ID를 10개 논리 목적지로 축약한다. 권장안은 행을 즉시 삭제하는 하드 병합이 아니라, 기존 ID를 계속 입력으로 받아들이는 **캐노니컬 ID + 호환 alias ID 오버레이**다.

- 현재 물리 카탈로그: 함수 2,866개, intent 2,660개
- 동치 오버레이 적용 후 논리 카탈로그: 함수 2,856개, intent 2,650개
- 물리 행을 유지하는 1차 배포에서는 외부에 보이는 기존 개수와 ID가 바뀌지 않는다.
- v13·v14·v15가 각각 추가한 함수 252개·intent 240개에서는 새 `true_equivalent`가 발견되지 않았다. 10개 그룹 모두 v13 이전 영역에 있다.
- 정책이 다른 동치 그룹은 더 느슨한 쪽이 아니라 `state_changing`의 OR, 가장 높은 위험도, 가장 제한적인 자동화/중단 정책으로 합친다.

이 물리·논리 개수와 동치성 판정은 카탈로그 구조 감사 결과이지 참조 커버리지, resolver 정확도, 실제 기기 정확도의 근거가 아니다. 해당 지표는 [Navigation DB Gym](NAVIGATION_DB_GYM.md)에서 서로 분리해 보고한다.

`commerce.cart`와 `shopping.cart`는 `true_equivalent`다. `contacts.emergency`와 `android_safety.emergency_contacts`도 `true_equivalent`다. 반면 이름 일부가 같아도 작업 경계, 대상 자산, 공개 상대, 또는 사용자 결과가 다르면 병합하지 않았다.

## 범위와 판정 방법

감사 입력은 현재 캐노니컬과 `scripts/navigation_catalog_v13_data.py`, `scripts/navigation_catalog_v14_data.py`, `scripts/navigation_catalog_v15_data.py`의 소스 정의다. 실제 소비 방식을 확인하기 위해 `apps/api/app/services/navigation_function_catalog.py`의 `function()`, `plan_goal()`, `match_candidate()`, `_route_with_terminal_override()`도 읽었다. 독립 fixture, 정답, 실패 산출물, 테스트 기대값은 동등성 판정에 사용하지 않았다.

문자열 비교는 Unicode NFKC 정규화, 대소문자 접기, 구두점/공백 정규화를 적용했다. 후보는 다음 순서로 넓혔다.

1. 영어 이름 완전 일치 14쌍, 한국어 이름 완전 일치 16쌍, 합집합 19쌍을 추출했다.
2. 이름과 alias를 함께 비교해 영어 완전 일치 표현이 2개 이상인 34쌍, 영어·한국어 양쪽에 일치 표현이 있는 100쌍을 검토했다.
3. 완전 이름 일치 또는 영어 표현 2개 이상 일치 조건을 만족한 40쌍을 연결 성분으로 묶어 37개 고신호 그룹을 만들었다.
4. 반복된 `function_id` 말단, terminal 의미, route의 진입점·종점, positive/negative context를 대조해 14개 의미 후보를 추가했다.

최종 감사 대상은 51개 의미 그룹이며 판정은 `true_equivalent` 10개, `context_distinct` 26개, `parent-child` 8개, `unsafe_to_merge` 7개다. 양 언어에서 한 단어만 겹친 나머지 저신호 충돌도 확인했다. `profile`, `game`, `ticket`, `report`, `cache`, `backup`, `history`, `invoice` 같은 일반 UI 명사는 목적지 동치의 증거가 아니었다. 다만 처방전/복약과 두 spam sibling은 route·결과 차이를 명시할 가치가 있어 저신호 집합에서 비동치 항목으로 추가했다.

판정 기준은 다음과 같다.

| 판정 | 기준 | 런타임 처리 |
|---|---|---|
| `true_equivalent` | 같은 사용자 목적지와 같은 최종 효과를 가리키며 차이가 namespace/세대/표현에 그침 | 하나의 캐노니컬 ID로 축약하되 기존 ID를 alias로 유지 |
| `context_distinct` | 표현은 겹치지만 앱 영역, 대상 자산, 수신자 또는 route 문맥이 다름 | 별도 ID 유지, context/negative context로 구별 |
| `parent-child` | 한쪽이 상위 화면·범용 범주·asset-scope superset이고 다른 쪽이 그 안의 subtype 또는 최종 작업 | 계층/route edge로 연결하되 동일 ID로 축약하지 않음 |
| `unsafe_to_merge` | 합치면 다른 결과를 실행하거나 동의·결제·공개·삭제 경계를 흐릴 수 있음 | 명시적 비동치 제약과 회귀 probe 유지 |

## 현재 캐노니컬과 v15 소스 규모

| 지표 | 현재 v15 | v14 기준 | 변화 |
|---|---:|---:|---:|
| 함수 행 | 2,866 | 2,614 | +252 |
| intent 행 | 2,660 | 2,420 | +240 |
| terminal 함수 행 | 2,660 | 2,420 | +240 |
| state-changing 함수 행 | 1,462 | 1,306 | +156 |
| alias 문자열 | 46,061 | 40,442 | +5,619 |
| route step | 5,086 | 4,606 | +480 |
| intent가 쓰는 고유 terminal ID | 2,658 | 2,418 | +240 |
| intent route에 직접 나타나지 않는 함수 ID | 29 | 29 | 0 |

`navigation_catalog_v15_data.py`는 12개 도메인 hub, 240개 terminal, 240개 intent를 만든다. terminal 중 156개는 state-changing이고 84개는 민감한 read다. 각 intent는 `hub -> terminal` 두 단계이며 최종 활성화는 `never_auto`, `before_action`, 사용자 소유 press 경계를 갖는다. 따라서 v15 목적지를 기존의 일반 UI 표현과 문자열이 겹친다는 이유만으로 흡수해서는 안 된다.

## `true_equivalent`: 캐노니컬 ID와 alias ID

아래의 “보수 정책”은 동치 클래스가 노출해야 할 최소 안전 envelope다. 표기는 `risk_level / state / automation_policy / stop_policy` 순서다. `read`는 `state_changing = false`, `write`는 `true`다.

| # | 캐노니컬 ID | 호환 alias ID | 동일 목적지 근거 | route 소비 | 보수 정책 |
|---:|---|---|---|---|---|
| 1 | `commerce.cart` | `shopping.cart` | 영어·한국어 이름이 같고 영어 표현 2개, 한국어 표현 3개가 겹치는 동일 장바구니 화면이다. | 각 ID가 별도 intent의 terminal이자 route 종점이다. | `low / read / safe_navigation / on_destination_screen` |
| 2 | `communication.conversation.mute` | `messaging.mute` | `Mute conversation`/`대화 알림 끄기`와 최종 음소거 효과가 같다. 두 intent 모두 확인 후 action 전 중단을 요구한다. | 각 1개 intent; 기존 ID가 avoid에도 1회 쓰인다. | `medium / write / never_auto / before_action` |
| 3 | `communication.conversation.archive` | `messaging.archive` | archive/hide/move-to-archive alias와 받은편지함에서 대화를 보관하는 최종 효과가 같다. 두 intent의 실행 경계도 같다. | 각 1개 intent; 기존 ID가 avoid에도 1회 쓰인다. | `medium / write / never_auto / before_action` |
| 4 | `communication.conversation.delete` | `messaging.delete` | 같은 대화 삭제 동작이며 영어·한국어 이름과 삭제 범위/복구 불가 문맥이 일치한다. | 각 1개 intent; 기존 ID가 avoid에도 2회 쓰인다. | `high / write / never_auto / before_action` |
| 5 | `contacts.emergency` | `android_safety.emergency_contacts` | 영어·한국어 이름이 같고 영어 표현 4개, 한국어 표현 3개가 겹친다. 모두 긴급 연락처 열람 목적지다. | 각 ID가 별도 세대 intent의 terminal/종점이다. | `high / read / never_auto / before_action` |
| 6 | `government.appointment` | `government_digital.office_appointment` | 관공서 대면 방문 일정을 예약하는 최종 결과가 같고 영어 이름과 관리 alias가 정확히 겹친다. | 각 1개 intent/route 종점이다. | `high / write / never_auto / before_action` |
| 7 | `safety.sos` | `android_safety.sos` | 같은 긴급 SOS 도움 요청이며 영어·한국어 이름, 사용자 소유 action, stop 경계가 같다. | 각 1개 intent/route 종점이다. | `high / write / never_auto / before_action` |
| 8 | `health.lab_results` | `digital_health.lab_results` | 같은 검사일·수치·기준 범위·의료진 판독 결과를 여는 민감정보 목적지다. | 각 1개 intent/route 종점이다. | `high / read / never_auto / before_action` |
| 9 | `safety.check_in` | `android_safety.safety_check` | 한국어 이름과 “지정 시간까지 무응답이면 선택한 사람에게 위치 알림”이라는 최종 효과가 같다. | 각 1개 intent/route 종점이다. | `high / write / never_auto / before_action` |
| 10 | `health.emergency_profile` | `android_safety.emergency_info` | 혈액형·알레르기·긴급 연락처를 담은 잠금 화면용 긴급 의료정보를 열람하는 동일 목적지다. | 각 1개 intent/route 종점이다. | `high / read / never_auto / before_action` |

캐노니컬 ID는 더 이른 세대이며 더 일반적인 namespace를 우선했다. 이 선택은 안전 우선순위가 아니다. 안전 envelope는 항상 두 정의 중 더 제한적인 값을 별도로 계산한다. 10개 그룹 중 3개는 현재 함수 안전 메타데이터 중 적어도 하나가 다르다. mute/archive는 구형 함수 행만 `state_changing = false`, `stop_policy = on_destination_screen`이지만 두 intent는 이미 `user_confirmation_required`와 `stop_before_action`을 요구한다. SOS는 위험도가 `high`와 `medium`으로 다르다. 병합 결과는 각각 write/before-action과 high를 채택해야 한다.

`government.appointment` 클래스는 “관공서 방문 예약 화면/작업”이라는 목적지 수준에서만 동치다. 실제 기관, 서비스 유형, 사건 번호, 날짜를 서로 대체한다는 뜻이 아니므로 이 필드와 세대별 route provenance는 반드시 보존한다.

10개 그룹 모두 두 ID가 각각 하나의 intent terminal과 route 종점으로 소비되므로 총 20개 물리 intent가 10개 논리 intent가 된다. route gateway는 세대별로 다를 수 있으므로 terminal만 캐노니컬화하고 원래 intent가 고른 gateway 변형은 보존한다.

## 런타임 matching과 goal-plan 구현

초기 구현의 `match_candidate()`는 모든 함수 행을 독립적으로 채점해 동치 ID가 top-k 두 자리를 차지할 수 있었고, `function()`·`plan_goal()`·route도 raw ID만 사용했다. 현재 v15에서는 아래 오버레이를 적용해 물리 ID 호환성을 유지하면서 외부 결과와 경로를 논리 대표 ID로 정규화한다.

적용한 구현은 다음과 같다.

1. 카탈로그 옆에 `canonical_function_id -> member_ids`와 `alias_function_id -> canonical_function_id`의 비순환 equivalence map을 둔다. 각 alias는 정확히 한 클래스에만 속하게 한다.
2. `match_candidate()`는 기존대로 각 멤버의 alias, locale, positive/negative context, state cue를 **독립 채점**한다. 이후 캐노니컬 ID로 그룹화하고 클래스 점수는 멤버 점수의 합이 아니라 `max`로 정한다. 합산하면 alias가 많은 중복 클래스가 부당하게 유리해진다.
3. 반환 목록은 클래스당 한 항목만 남긴다. 외부 `function_id`는 캐노니컬 ID로 하되 `matched_function_id` 또는 `source_alias_id`와 matched alias/context 증거를 함께 보존한다.
4. 멤버의 negative context를 한 정의에 무조건 합치지 않는다. 현재 일부 세대별 정의는 서로를 구분하도록 교차 negative context를 갖기 때문에, 먼저 멤버별로 점수를 낸 뒤 축약해야 한다.
5. `function(id)`는 alias-aware lookup으로 바꾸되, 호출자가 원하면 raw 정의와 캐노니컬 정의를 모두 조회할 수 있게 한다.
6. goal text는 기존 intent alias와 rule로 먼저 매칭해 원래 intent/route 변형을 선택한다. 그 다음 default terminal, rule terminal, route step, `avoid_functions`를 모두 캐노니컬화한다. 즉, 서로 다른 gateway를 가진 세대별 route를 먼저 하나로 평탄화하지 않는다.
7. route에서 같은 클래스가 여러 번 나오면 최대 weight를 유지하고 terminal을 마지막에 둔다. 캐노니컬화 후 terminal과 같은 클래스가 된 avoid 항목은 제거한다. 그렇지 않으면 “선호하면서 동시에 회피”하는 모순이 생긴다.
8. gateway trigger, graph edge, 캐시 키, 텔레메트리에도 같은 canonicalization을 적용한다. 로그와 저장 이력에는 `observed/raw ID`와 `canonical ID`를 함께 남겨 회귀와 구버전 재현성을 보장한다.

equivalence validator는 클래스 순환, 다중 소속, 존재하지 않는 ID, terminal/non-terminal 혼합을 거부해야 한다. terminal/non-terminal 관계는 `true_equivalent`가 아니라 별도의 `parent-child` edge로만 표현한다. 또한 합성 안전 envelope가 어느 멤버보다 느슨해지지 않는지 검증해야 한다.

## 개수, 안전 정책, 호환성 영향

| 배포 방식 | 함수 수 | intent 수 | 영향 |
|---|---:|---:|---|
| 현재 물리 v15 | 2,866 | 2,660 | 기준선 |
| 권장 1차: alias 오버레이 | 물리 2,866 / 논리 2,856 | 물리 2,660 / 논리 2,650 | 기존 ID와 intent를 모두 수용하고 결과만 캐노니컬화 |
| 후속 하드 병합 | 2,856 | 2,650 | 함수 행 10개, terminal intent 행 10개 제거 가능 |
| 참고: v13 물리 기준 하드 병합 환산 | 2,352 | 2,170 | 과거 2,362/2,180 기준에서 같은 감소량 |

현재 2,660개 intent가 참조하는 default terminal ID는 2,658개다. 10개 동치 클래스까지 canonicalize하면 고유 default terminal 목적지는 2,648개가 된다. 위 표의 2,650은 “각 동치 쌍의 세대별 intent 행도 하나로 합친다”는 하드 병합 행 수이며, 고유 terminal 목적지 수와는 다른 지표다.

안전 합성 규칙은 다음과 같다.

- `state_changing`: 멤버 중 하나라도 `true`이면 `true`.
- `risk_level`: 멤버 중 가장 높은 등급.
- `automation_policy`: 가장 제한적인 정책. 현재 불일치에서는 `never_auto`를 유지한다.
- `stop_policy`: 가장 이른 안전 중단점. 현재 불일치에서는 `before_action`을 유지한다.
- 확인 문구, 사용자 소유 press, 민감정보 공개 제한도 합집합으로 보존한다.

하드 삭제 전에는 모든 alias ID와 기존 intent 이름을 입력 호환 계층에 남겨야 한다. 저장된 plan, 캐시, deep link, 분석 대시보드, 모델 출력이 과거 ID를 포함할 수 있기 때문이다. 스키마에는 캐노니컬 ID를 새로 쓰되 raw ID를 병기하고, alias hit 비율과 구버전 호출이 충분히 낮아진 뒤에만 물리 행 제거를 검토한다.

## `parent-child`: 같은 영역이지만 다른 작업 경계

| 상위/진입 ID | 하위/최종 ID | 판정 근거 |
|---|---|---|
| `navigation.menu` | `navigation.drawer` | `menu`는 18개 route가 쓰는 전체 기능 목록·프로필 메뉴·drawer의 범용 gateway이고 `drawer`는 route 미소비인 측면 패널 subtype이다. 모든 앱에서 같은 surface라고 보장할 수 없다. |
| `android.defaults.apps` | `android_connectivity.default_apps` | 전자는 기본 앱 선택 화면/영역, 후자는 특정 기본값을 확정하는 상태 변경 경계다. |
| `auth.login.entry` | `auth.login` | 전자는 로그인 화면 진입, 후자는 자격 증명 제출이다. 화면 도착과 인증 실행을 합치면 안 된다. |
| `android.permission.manage` | `system.permission` | 전자는 권한 관리 페이지, 후자는 권한 허용/거부 상태 변경이다. |
| `order.return.entry` | `shopping.return_item` | 전자는 반품 흐름 진입, 후자는 상품 반품 제출/실행 경계다. |
| `support.help` | `support.faq` | `support.help -> support.faq`가 실제 route에 나타나는 허브-하위 목적지 관계다. |
| `safety.report_spam` | `messaging.mark_spam` | 전자는 일반 안전 영역의 스팸 신고, 후자는 문자/대화에 한정된 신고·차단 endpoint다. 메시지 문맥에서는 결과가 같을 수 있지만 범용 canonical로 만들 수 없다. |
| `family_store.content_rating` | `parental.content_rating` | 전자는 가족 계정의 앱·게임·영화 등급 제한, 후자는 gaming scope의 성인 게임 제한이다. 후자가 asset 범위상 하위다. |

이 여덟 그룹은 alias로 축약하지 않고 route, representational subtype 또는 scope 계층 edge를 명시해야 한다. 특히 상위 화면 도달을 최종 action 성공으로 간주하지 않아야 한다.

## `context_distinct`: 표현은 비슷하지만 목적지가 다름

| # | ID 그룹 | 구별 근거 |
|---:|---|---|
| 1 | `android.app.data_usage` ↔ `settings.data_usage` | Android의 앱별 데이터 사용량과 일반/앱 내부 데이터 절약 설정은 scope가 다르다. |
| 2 | `android.app.info` ↔ `system.app_info` | OS의 앱별 권한·저장공간 허브와 앱 자체의 About/버전 화면이다. Android intent의 negative context도 후자를 배제한다. |
| 3 | `android.app.storage_cache` ↔ `settings.storage` | OS 앱별 저장공간/캐시와 앱 내부 다운로드·저장공간 설정이다. |
| 4 | `android_safety.hub` ↔ `safety.hub` | 기기 긴급·안전 허브와 신고·차단 중심 일반 안전 허브다. |
| 5 | `browser.bookmarks` ↔ `content.saved` | 저장한 웹페이지와 여러 콘텐츠 유형의 저장 목록이다. |
| 6 | `browser.tabs` ↔ `navigation.tabs` | 브라우저 세션 탭과 일반 UI 내비게이션 탭이다. `navigation.tabs`는 browser 문맥을 명시적으로 배제한다. |
| 7 | `commerce.wishlist` ↔ `content.saved` | 상품 위시리스트와 범용 저장 콘텐츠다. |
| 8 | `aviation_maintenance_ops.hub` ↔ `food_establishment_inspection.hub` | `in progress`, `closed` 같은 수명주기 표현만 같고 항공 정비와 식품업소 검사가 다르다. |
| 9 | `aviation_maintenance_ops.hub` ↔ `freight_forwarding_customs_ops.hub` | `planned`, `released`, `closed`는 일반 상태어이며 정비 자산과 화물 통관 자산이 다르다. |
| 10 | `aviation_maintenance_ops.hub` ↔ `utility_grid_field_ops.hub` | `work order`, `closed`만 겹치며 항공기 정비와 현장 유틸리티 작업이다. |
| 11 | `building_permit_code_enforcement.hub` ↔ `food_establishment_inspection.hub` | permit/inspection 표현은 같아도 건축 코드와 식품 영업 규제 대상이 다르다. |
| 12 | `dental_practice_ops.hub` ↔ `veterinary_practice_ops.hub` | `scheduled`, `treated` 같은 상태어만 같고 환자 종류와 진료 기록 체계가 다르다. |
| 13 | `pipeline_control_integrity_ops.hub` ↔ `water_wastewater_plant_ops.hub` | `normal`, `alarm`은 운전 상태어이며 파이프라인과 수처리 설비가 다르다. |
| 14 | `rail_operations.hub` ↔ `utility_grid_field_ops.hub` | `switch`, `dispatcher`가 겹쳐도 철도 관제와 유틸리티 현장 배차는 다르다. |
| 15 | `blood_bank_transfusion_ops.compatibility_result_review` ↔ `organ_transplant_coordination.compatibility_result_review` | 같은 말단 이름이지만 혈액 수혈 적합성 결과와 장기 이식 적합성 결과다. |
| 16 | `environmental_waste_ops.inspection_history` ↔ `mining_site_safety_ops.inspection_history` ↔ `building_permit_code_enforcement.inspection_history` | 폐기물, 광산 안전, 건축 코드의 서로 다른 규제 검사 기록이다. |
| 17 | `civic_local.inspection_schedule` ↔ `building_permit_code_enforcement.inspection_schedule` | 일반 지방 행정 검사 일정과 건축 허가/코드 검사의 일정이다. |
| 18 | `food_establishment_inspection.permit_status_view` ↔ `building_permit_code_enforcement.permit_status_view` | 식품업소 영업 허가와 건축 허가의 대상·기관·후속 조치가 다르다. |
| 19 | `dental_practice_ops.treatment_plan_review` ↔ `radiation_therapy_ops.treatment_plan_review` | 치과 치료 계획과 방사선 치료 계획은 임상 scope와 안전 경계가 다르다. |
| 20 | `communication.conversation.search` ↔ `messaging.search` | 현재 대화 안의 텍스트 검색과 전체 메시지/받은편지함 검색이다. 두 정의의 negative context도 교차 구별한다. |
| 21 | `delivery.instructions` ↔ `parcel_courier.driver_instructions` | 음식·라스트마일 주문 메모와 소포별 기사 배송 위치 지시다. negative context가 scope를 명시한다. |
| 22 | `delivery.order_tracking` ↔ `order.tracking` ↔ `shopping.track_package` | 음식 배달원의 실시간 위치, 일반 주문 배송 상태, 쇼핑 소포 추적은 route root와 시간축이 다르다. |
| 23 | `telecom.voicemail` ↔ `calls.voicemail` | 전자는 carrier/mobile-plan 문맥의 기기 음성사서함 서비스·설정이고, 후자는 통화 앱의 음성 메시지/부재중 녹음함이다. 정책도 `low/safe_navigation/on_destination_screen`과 `high/never_auto/before_action`으로 달라 scope 확인 없이 합칠 수 없다. |
| 24 | `digital_health.prescriptions` ↔ `health.medications` | 전자는 처방일·의료기관이 있는 전자 처방전 목록, 후자는 약 이름·용량·복약 일정 중심의 현재 복약 목록이다. 둘 다 민감한 read지만 문서와 복약 상태는 다르다. |
| 25 | `email.spam` ↔ `safety.report_spam`/`messaging.mark_spam` | `email.spam`은 `email.hub` 아래의 read-only 스팸 메일함이고 나머지는 발신자/메시지를 신고·차단하는 write action이다. |
| 26 | `calls.caller_id_spam` ↔ `safety.report_spam`/`messaging.mark_spam` | 전자는 통화 앱의 발신자 식별·스팸 전화 감지/보호 설정이고, 나머지는 이미 도착한 메시지를 신고하는 action이다. |

이 그룹은 ID를 유지한 채 대상 명사와 주변 문맥을 강화해야 한다. 공통 한 단어를 alias에서 모두 제거할 필요는 없지만, 단독 표현일 때는 fail-closed하거나 추가 문맥을 요구해야 한다.

## `unsafe_to_merge`: 결과가 달라질 수 있는 충돌

| ID 그룹 | 위험 | 필요한 보호 |
|---|---|---|
| `refund.entry`, `app_store.refund_request`, `order.cancel.entry`, `shopping.cancel_order` | 출고 전 주문 취소, 완료 구매 환불, 앱스토어 환불, 각 흐름 진입이 한 표현군에 섞인다. 결제·정산 결과와 state boundary가 다르다. | 상품/스토어, 주문 상태, `cancel` 대 `refund`, entry 대 submit을 명시하고 별도 terminal을 유지한다. |
| `auth.two_factor` ↔ `security.two_factor` | 로그인 중 2단계 인증 challenge와 보안 설정에서 MFA를 켜고 끄는 작업이다. 현재 intent도 한 ID를 terminal로 쓰면서 다른 ID를 rule terminal/avoid로 구별한다. | 인증 challenge와 설정 변경을 절대 같은 canonical ID로 만들지 않는다. |
| `privacy.contacts_sync` ↔ `contacts.sync` | 친구 찾기를 위한 주소록 업로드/공개와 계정·기기 연락처 동기화는 데이터 수신자와 결과가 다르다. | 공개 상대, 계정, 업로드 목적을 확인하고 별도 동의를 유지한다. |
| `privacy.location_sharing` ↔ `maps.location_sharing` | 개인정보 설정의 위치 공유 제어와 특정 수신자에게 보내는 실시간 지도 공유 세션이다. | 수신자, 기간, 앱 scope를 확인하고 각각의 high-risk write 경계를 유지한다. |
| `parental.purchase_approval` ↔ `family_store.purchase_approval` | gaming/보호자 설정의 ask-to-buy 정책·요청 화면과 family-store의 특정 자녀 구매 승인 실행이 섞일 수 있다. scope, node kind, 위험도도 다르다. | 요청 목록 열람/정책 설정/개별 승인 action을 분리하고 가격·자녀·승인자를 다시 확인한다. |
| `government.identity_login` ↔ `government_digital.identity_verify` | 공동인증서·간편인증 기반 공공 로그인 진입과 신분증·여권·사회보장번호·셀카를 제출하는 identity proofing은 lifecycle이 다르다. | sign-in과 ID proof 제출을 분리하고, 동일 영어 이름보다 수단과 제출 결과를 우선한다. |
| `parental.family_sharing` ↔ `family_store.family_library` | gaming-only 가족 게임 공유 read destination과 가족 계정 전체 구매 콘텐츠 library의 state change는 asset 범위와 실행 결과가 다르다. | 게임 열람/공유와 가족 library 설정을 분리하고 멤버·콘텐츠 범위를 확인한다. |

이 일곱 그룹은 단순히 “아직 확신이 낮다”가 아니라, 잘못 병합했을 때 다른 사용자 결과를 실행할 수 있으므로 명시적인 비동치 회귀 항목이어야 한다.

## v13 전용 충돌 검토

v13 소스는 72개 official source, 61개 collision family, 732개 생성 collision probe를 선언한다. `_COLLISION_TARGET_IDS`와 `COLLISION_AVOIDS`는 `unit`, `patient`, `donor`, `permit`, `plan`, `inspection`, `match`, `issue`처럼 여러 산업에서 재사용되는 표현을 의도적으로 분리한다.

v13 신규 함수와 v13 이전 함수 사이에는 정규화된 영어·한국어 완전 이름 중복이 0건이다. 영어 exact alias 교차 45쌍도 모두 v13 hub의 일반 상태·역할어에서 생겼고 v13 terminal 교차는 0건이다. 두 개 이상의 영어 표현이 겹친 경우도 terminal 동치가 아니라 다음 hub 충돌뿐이었다.

- `building_permit_code_enforcement.hub` ↔ `food_establishment_inspection.hub`: permit/inspection/closed/violation/plan 상태어
- `aviation_maintenance_ops.hub` ↔ `food_establishment_inspection.hub`: `in progress`, `closed`
- `pipeline_control_integrity_ops.hub` ↔ `water_wastewater_plant_ops.hub`: `normal`, `alarm`

v13-이전 간 동일 terminal leaf는 4쌍(신규 terminal 3개), v13 내부 동일 leaf는 2그룹이다. 이를 의미 그룹으로 접으면 위 `context_distinct` 15~19번의 5개 그룹이며 모두 대상 자산이 다르다. 결론적으로 v13의 252개 함수와 240개 intent는 동치 병합 감소량을 만들지 않으며, v13의 fail-closed 안전 정책과 collision avoid를 그대로 보존해야 한다.

## 적용 순서와 완료 조건

1. 10개 `true_equivalent` 클래스만 reviewable equivalence map으로 추가한다.
2. 안전 envelope validator와 alias-aware `function()`을 먼저 적용한다.
3. candidate 결과를 클래스 단위로 dedupe하고 raw/canonical ID를 함께 관측한다.
4. goal terminal, rules, route, avoids, gateway/graph index를 캐노니컬화한다.
5. 8개 `parent-child`, 26개 `context_distinct`, 7개 `unsafe_to_merge`를 비동치 회귀 집합으로 고정한다.
6. 기존 ID로 만든 plan의 route·`stop_policy`·확인 경계가 보존되는지 확인한 뒤 오버레이를 기본값으로 켠다.
7. 물리 행 삭제는 alias 호출률, 저장 데이터 마이그레이션, 텔레메트리 소비자 호환성이 확인된 별도 버전에서만 수행한다.

완료 기준은 동일 목적지가 top-k를 중복 점유하지 않고, 모든 과거 ID가 같은 캐노니컬 목적지로 해석되며, 어떤 동치 클래스도 기존 멤버보다 느슨한 안전 정책을 갖지 않는 것이다.
