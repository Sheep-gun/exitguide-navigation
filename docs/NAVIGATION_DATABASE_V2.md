# ExitGuide Navigation Database V2

이 문서는 범용 Navigation Agent가 사용하는 기능 카탈로그, 검증 데이터, 자동 탐색으로 발견한 경로를 서로 다른 신뢰 계층으로 관리하는 기준을 정의한다. 핵심 원칙은 **기능 지식은 넓게 축적하되, 모델이 만든 추측을 정답으로 자동 승격하지 않고, 실제 상태 변경의 최종 클릭은 항상 사용자에게 남기는 것**이다.

## 1. 권위 있는 원본과 런타임 데이터

검토 가능한 기능 지식의 단일 원본은 `fixtures/navigation/function-catalog.v1.json`이다. 파일명은 기존 참조 경로를 유지하기 위해 `v1`이지만, 파일 내부 `catalog_version`은 `2.0.0`이며 V2 스키마를 사용한다.

API는 원본 JSON의 버전과 SHA-256이 바뀌면 `.artifacts/navigation-function-catalog.sqlite`를 다시 만든다. SQLite는 검색 속도를 위한 파생 인덱스일 뿐이므로 직접 편집하거나 정답 원본으로 취급하지 않는다. 앱별 탐색 그래프와 경로 성능은 별도의 `.artifacts/universal-navigation.sqlite`에 저장한다. 즉, 다음 세 계층을 섞지 않는다.

| 계층 | 역할 | 정답 여부 |
|---|---|---|
| 기능 카탈로그 JSON | 앱을 가로질러 재사용하는 기능, 별칭, 문맥, 목적, 공통 기능 경로 | 사람 검토 후 canonical truth |
| 앱별 기능 그래프·경로 SQLite | 실제 탐색 중 관찰한 화면 fingerprint, 기능 간선, 경로, 성공·실패·시간 | 승인 전에는 `shadow`; 앱 버전별 경험 데이터 |
| `.artifacts/` 보고서·제안 | audit, benchmark, Gym, K-EXAONE 제안 | 임시 산출물; canonical truth가 아님 |

앱별 픽셀 좌표, 특정 기기의 절대 위치, 사용자 계정 정보와 화면 원문은 공통 카탈로그에 넣지 않는다. 기능 카탈로그는 “어디를 누른다”가 아니라 “그 메뉴가 어떤 기능이고 어떤 상태·위험을 뜻하는가”를 표현한다.

## 2. Catalog V2 현재 스냅샷

아래 값은 2026-07-30 기준으로 현재 JSON을 `Audit-NavigationCatalog.ps1 -Gate`로 다시 계산한 결과다. 품질 gate는 `pass`, 품질 점수는 `100.0`이다. 이 점수는 스키마·커버리지·안전 메타데이터 품질 점수이며 실제 Android 앱 정확도 점수가 아니다.

| 항목 | 현재 값 |
|---|---:|
| 카탈로그 버전 | `2.0.0` |
| 기능(function) | 232 |
| 사용자 목적(intent) | 177 |
| 도메인 | 28 |
| 메뉴 별칭 | 2,224 |
| 긍정·부정 문맥 | 1,533 |
| 목적 표현 패턴 | 1,061 |
| 복수 단서 목적 규칙 | 347 |
| 목적별 기능 경로 단계 | 592 |
| UI role 힌트 | 696 |
| 상태 단서 | 298 |
| 위험 단서 | 264 |
| 최종 목적 기능 | 177 |
| 상태 변경 기능 | 47 |

위험도 분포는 `low` 111개, `medium` 85개, `high` 36개다. 자동화 정책은 `safe_navigation` 108개, `never_auto` 121개, `conditional` 3개다. 따라서 기능 수가 늘더라도 자동 클릭 가능 기능이 무제한으로 늘어나는 구조가 아니다.

### 2.1 도메인 28개

| 도메인 | 기능 수 | 도메인 | 기능 수 |
|---|---:|---|---:|
| `accessibility` | 3 | `account` | 18 |
| `android_system` | 24 | `authentication` | 14 |
| `billing` | 7 | `commerce` | 12 |
| `communication` | 6 | `consent` | 4 |
| `content` | 13 | `files` | 7 |
| `finance` | 9 | `health` | 2 |
| `health_insurance` | 4 | `insurance` | 21 |
| `legal` | 4 | `marketing` | 2 |
| `media` | 4 | `navigation` | 8 |
| `notification` | 5 | `onboarding` | 5 |
| `privacy` | 14 | `refund` | 3 |
| `security` | 6 | `settings` | 10 |
| `subscription` | 9 | `support` | 5 |
| `system` | 4 | `travel` | 9 |

도메인은 제품 카테고리가 아니라 기능 의미의 상위 분류다. 예를 들어 항공사 앱의 예약 취소는 `travel`, 쇼핑 앱의 주문 취소는 `commerce`, Android 설정에서 앱 권한을 바꾸는 것은 `android_system`으로 분리한다.

## 3. Function과 Intent 모델

### 3.1 Function

기능 하나는 최소한 다음 정보를 가진다.

- `function_id`: 앱과 언어에 독립적인 안정 ID. 예: `subscription.cancel.entry`.
- `domain`: 위 28개 의미 도메인 중 하나.
- `name_ko`, `name_en`, `description`: 사람이 검토하는 표준 이름과 기능 설명.
- `aliases`: 실제 UI에서 보이는 메뉴 이름과 표현 변형.
- `positive_context`, `negative_context`: 같은 단어가 다른 기능으로 오인되는 것을 막는 주변 문맥.
- `risk_level`, `automation_policy`, `terminal`, `state_changing`: 안전 경계.
- `scope`, `node_kind`, `stop_policy`: 기능이 존재하는 범위, 그래프 역할, 자동화 정지 시점.
- `role_hints`, `state_cues`, `risk_cues`: 접근성 노드의 역할·상태와 화면 문구를 해석하는 구조화 단서.
- `legacy_tags`: 기존 규칙 기반 기능 태그와의 하위 호환 연결.

### 3.2 Intent

Intent는 사용자의 목적을 기능 그래프로 바꾸는 단위다.

- `intent_id`: 예: `subscription_cancellation`.
- `patterns`: “구독 해지”, “turn off auto renew” 같은 직접 표현.
- `goal_rules`: “멤버십 + 갱신 + 않”처럼 문장 속 여러 단서가 함께 있을 때 적용하는 규칙.
- `route`: 앱을 가로질러 자주 나타나는 기능 관문과 가중치. 이는 고정 좌표 경로가 아니라 `account.entry → billing.manage → subscription.manage → subscription.cancel.entry` 같은 의미 경로다.
- `terminal_function`: 탐색을 끝내야 하는 목적 기능.
- `avoid_functions`: 콘텐츠의 “구독” 탭과 유료 구독 관리처럼 혼동하면 안 되는 기능.

공통 `gateway_rules`는 전체 메뉴, 마이페이지, 로그인·회원가입 통합 진입점처럼 여러 intent가 공유하는 안전한 관문을 런타임 경로에 삽입한다. 앱별 실제 순서가 다르면 탐색 그래프가 그 차이를 학습하며, 공통 카탈로그가 앱별 고정 경로를 강요하지 않는다.

## 4. Android 시스템과 인앱 기능의 분리

V2는 Android OS 설정과 앱 내부 메뉴를 같은 단어 사전으로 뭉개지 않는다.

| 구분 | 현재 규모 | 예시 |
|---|---:|---|
| `domain=android_system` | 24 기능 | 앱 정보, 앱 알림, 권한 관리자, 접근성 서비스, 다른 앱 위에 표시, 배터리, 캐시, 기본 앱, 제거, 강제 종료 |
| 그 외 인앱·교차 앱 도메인 | 208 기능 | 회원가입, 구독, 주문, 보험, 파일, 메시지, 여행, 금융, 개인정보, 고객센터 |

`scope`는 더 세밀한 자원 경계를 표현한다. 현재 232개 기능 모두 scope가 명시되어 있다.

- 일반 인앱 기능: `in_app` 169개.
- Android 설정 화면: `android_system` 20개.
- Android에서 파괴 대상 자원을 명확히 한 기능: `installed_app`, `running_app`, `local_app_cache`, `local_app_data` 각 1개. 이 네 기능까지 합쳐 `android_system` 도메인 24개가 된다.
- 업무 자원 범위: `travel_booking` 5개, `published_content` 4개, `order`·`credential`·`conversation`·`financial_transaction`·`account_identity` 각 3개, `payment_card`·`cloud_storage`·`health_data`·`recurring_charge` 각 2개, 그 밖의 단일 자원 scope.

SQLite 런타임 인덱스와 catalog 검색 결과에도 `scope`가 보존된다. 다만 scope 자체를 정답으로 사용하지는 않는다. 현재 후보 매칭은 별칭, 긍정·부정 문맥, locale, UI role, 상태 단서를 함께 보며, Android/인앱 경계 역시 현재 패키지·화면 문맥과 함께 판단해야 한다. 예를 들어 인앱의 “알림 설정”과 Android의 “이 앱의 알림”은 이름이 비슷해도 서로 다른 기능 ID다.

## 5. `scope`·`node_kind`·`stop_policy`·상태·위험·locale

### 5.1 `scope`: 무엇을 대상으로 하는가

`scope`는 UI 위치가 아니라 조작 대상의 경계다. `in_app`, `android_system`, `order`, `payment_card`, `travel_booking`, `financial_transaction`, `credential`처럼 기능이 영향을 미치는 자원을 표시한다. 같은 “삭제”라도 `published_content` 삭제와 `local_app_data` 삭제를 구분하고, 위험 평가와 독립 benchmark를 해당 자원에 맞게 만든다.

### 5.2 `node_kind`: 그래프에서 어떤 역할인가

| 종류 | 현재 수 | 의미 |
|---|---:|---|
| `destination` | 126 | 목적 기능이 있는 화면 또는 읽기 전용 목적지 |
| `hub` | 54 | 여러 하위 기능으로 갈라지는 공통 관문 |
| `state_change` | 39 | 설정값·권한·계정 상태 등을 바꾸는 동작 |
| `destructive_action` | 8 | 삭제, 제거, 강제 종료 등 되돌리기 어렵거나 파괴적인 동작 |
| `action_entry` | 5 | 상태 변경 절차에 들어가기 직전의 진입점 |

`terminal=true`는 해당 intent에서 목적지를 판정할 수 있다는 뜻이고, `node_kind`는 그 목적지의 성격을 설명한다. 둘은 같은 필드가 아니다.

### 5.3 `stop_policy`: 자동화가 어디에서 멈추는가

| 정책 | 현재 수 | 실행 의미 |
|---|---:|---|
| `on_destination_screen` | 178 | 안전한 화면·관문까지 이동하거나 목적 화면에서 정지 |
| `before_action` | 53 | 상태 변경 버튼을 누르기 전에 정지 |
| `stop_before_action` | 1 | Android 권한 변경처럼 명시적으로 실행 직전 강제 정지 |

V2 원본은 모든 기능에 정지 정책을 명시한다. `before_action` 계열 54개는 자동 실행 후보가 될 수 없다. 카탈로그 validator는 `state_changing=true`인데 `automation_policy`가 `never_auto`가 아니거나, 정지 정책이 실행 전 정지가 아니면 import 자체를 거부한다. `high` 위험도 역시 `never_auto`가 아니면 거부한다.

### 5.4 상태 모델

상태는 메뉴 이름에 섞어 쓰지 않고 `state_cues`로 분리한다. 현재 298개의 구조화 상태 단서가 있다.

- 접근성 속성: `enabled`, `checkable`, `checked`, `selected`의 true/false.
- 화면 텍스트 상태: 켜짐/꺼짐, 허용됨/차단됨, 활성/만료, 처리 중/완료처럼 기능별 의미 상태.
- 후보 매칭: 라벨과 주변 문맥만 비슷한 버튼보다 현재 상태까지 일치하는 버튼에 추가 근거를 준다.
- 비활성·보이지 않는 항목: 목적과 이름이 같아도 실행 후보가 아니라 대기, 스크롤, 복구 판단의 근거가 된다.

상태 단서는 화면의 일시적 사실이지 canonical 성공 여부가 아니다. 모델이 “완료된 것 같다”고 말한 결과만으로 경로를 승인하지 않는다.

### 5.5 위험 모델

위험은 `risk_level`, `automation_policy`, `state_changing`, `risk_cues`, `stop_policy`를 함께 사용한다. 현재 위험 단서는 264개다.

- `risk_cues`: 결제 금액, 외부 전송, 영구 삭제, 권한 부여, 위치 공유, 계정 종료처럼 실행 결과를 설명하는 문구.
- `positive_context`/`negative_context`: “주문 취소”와 “취소된 주문”, “구독 해지”와 “해지 완료”를 구분한다.
- `never_auto`: 목적과 정확히 맞아도 자동 클릭하지 않는다.
- 위험한 유사 버튼은 점수 경쟁에서 이기는 것으로 충분하지 않다. 안전 정책이 선택 가능성보다 먼저 적용된다.

### 5.6 locale 모델

별칭은 locale과 함께 저장되며 현재 분포는 다음과 같다.

| locale | 별칭 수 |
|---|---:|
| `ko` | 742 |
| `ko-KR` | 417 |
| `en` | 646 |
| `en-US` | 419 |

`ko`·`en`은 기존 범용 별칭, `ko-KR`·`en-US`는 V2에서 보강한 지역별 실제 UI 표현이다. 요청 locale과 정확히 일치하면 가장 높은 locale 근거, 같은 언어 계열이면 낮은 추가 근거를 주며, 다른 locale의 별칭도 fallback 후보로 남긴다. NFKC와 Unicode 토큰화를 사용하므로 한글·라틴 이외 문자를 ASCII로 강제 변환하지 않는다. 새 언어를 추가할 때는 기존 한국어·영어 목록에 섞지 말고 해당 BCP 47 locale 키로 추가한다.

## 6. 사용자 최종 클릭 원칙

자동 탐색의 목적은 **최종 행동을 대신 실행하는 것**이 아니라 **최종 목적 기능이 있는 화면과 버튼을 확인하는 것**이다.

1. 콜드 탐색 중에는 `low` 위험, 클릭 가능, 비체크형인 안전한 관문만 자동으로 탐색할 수 있다.
2. 목표 기능을 발견하면 `phase=destination_reached`, `automation.action=stop`, `safe_to_execute=false`로 탐색을 끝낸다.
3. 해지, 삭제, 결제, 송금, 권한 부여, 외부 제출 등 상태 변경 버튼은 사용자가 직접 누른다.
4. 저장 경로를 재사용하는 안내 모드에서는 중간 단계도 `automation.action=none`이며 사용자가 직접 누른다. 저장 경로가 현재 화면과 다르면 자동으로 비슷한 버튼을 강행하지 않고 재탐색 또는 뒤로 가기를 요청한다.
5. 최종 버튼의 라벨을 찾았다는 사실과 실제 상태 변경이 성공했다는 사실을 구분한다. 후자는 사람 검증 또는 신뢰 가능한 benchmark gold가 있어야 한다.

이 원칙은 UI의 신뢰감을 높이기 위한 제품 결정이면서, 잘못된 결제·탈퇴·권한 변경을 막는 데이터 불변식이다. 정확도나 속도를 높이기 위해 완화하지 않는다.

## 7. Benchmark 계층과 수치 해석

### 7.1 독립 정답 benchmark

`fixtures/navigation/db-gym/independent-core.v2.json`은 카탈로그 별칭이나 route에서 자동 생성하지 않은 고정 정답 세트다.

| 항목 | 현재 값 |
|---|---:|
| 고정 케이스 | 70 |
| 화면 단계 | 210 |
| 독립적으로 다루는 intent | 68 |
| 기대 function | 105 |
| locale | `ko-KR`, `en-US` |
| 사용자 상태 | 6종 |
| 속성 | `frozen=true`, `catalog_derived=false`, `source_kind=fixed_independent` |

이 세트의 문장·메뉴·기대 행동을 현재 카탈로그가 쉽게 맞히도록 자동 복사해서는 안 된다. 실패가 나오면 일반화 가능한 별칭, 문맥, 공통 관문, 안전 정책을 수정하고 같은 원인이 다른 케이스에서도 해결되는지 확인한다. 독립 benchmark 성능만이 “현재 카탈로그 밖에서 작성된 질문과 화면에도 동작했다”는 근거가 될 수 있다. 그래도 합성 화면이므로 실제 앱 정확도와 동일하지 않다.

그 밖의 고정 세트는 다음과 같다.

| 세트 | 케이스 | 단계 | 성격 |
|---|---:|---:|---|
| cross-app development | 33 | 33 | 사람이 고른 단일 화면 메뉴 경쟁; 개발 회귀용 |
| holdout | 10 | 25 | 우회 표현·다단계 경로, frozen |
| adversarial | 12 | 12 | 광고, 동음이의어, 유사 버튼, 위험 동작 |
| public web | 19 | 73 | 공식 도움말 18개 출처에서 정규화한 경로 |
| public insurance | 27 | 46 | 공식 안내 17개 출처에서 정규화한 보험 업무 경로 |
| alias-collision adversarial | 75 | 78 | 별칭 충돌·상태 문맥·위험 유사 버튼을 겨냥한 frozen 독립 세트 |
| real-device gold | 0 | 0 | 아직 실제 단말 검증 표본 없음 |

공식 도움말은 실제 서비스 용어와 기능 순서를 뒷받침하지만 앱 버전의 현재 접근성 트리나 좌표를 증명하지 않는다.

Alias-collision 세트는 67개 intent와 71개 기대 function을 다루며 `ko-KR` 69개, `en-US` 6개다. Catalog의 정확한 goal pattern을 그대로 복사한 케이스는 0개이고, 위험 요소를 기대 click으로 둔 케이스도 0개다. fixture 작성 직후의 격리 실행 기준 성공은 4/75(5.13%), 목적 해석 실패는 58건이었다. 이 낮은 값은 실패한 독립 holdout이 실제 일반화 공백을 드러낸다는 뜻이지 fixture를 catalog 문장으로 오염시켜 없애야 할 값이 아니다. 이후의 권위 있는 통합 수치는 최신 Gym 보고서의 `alias_collision_adversarial` split에서 확인한다.

### 7.2 Catalog-derived metamorphic 수치

Goal robustness는 검토된 intent pattern에 존댓말·요청문 wrapper, 구두점, 공백, 대소문자 등의 결정론적 변형을 적용한 **catalog-derived** 시험이다. 현재 재실행 결과는 다음과 같다.

| 모드 | 케이스 | intent | 현재 결과 |
|---|---:|---:|---:|
| `fast` | 708 | 177 | 100.00% |
| `full` | 4,244 | 177 | 100.00% |

이 100%는 “카탈로그에 이미 등록된 목적 표현이 형식 변형에도 같은 intent로 유지된다”는 안정성 증거다. 원본 pattern과 기대 intent가 같은 카탈로그에서 나오므로, 처음 보는 사용자 표현·실제 앱 메뉴·실기 성공률에 대한 독립 정확도 주장이 아니다. 보고서도 `catalog_derived=true`, `independent_accuracy_claim=false`로 이를 명시한다.

### 7.3 DB Gym의 혼합 수치

DB Gym 보고서는 출처별 수치를 반드시 분리해서 읽는다.

- `fixed_independent`: 사람이 고정한 development, holdout, adversarial, 공개 근거, 독립 core, real-device gold.
- `catalog_self_generated`: 현재 intent route와 aliases로 만든 변형. 카탈로그 내부 일관성과 모든 intent 실행 가능성을 찾는 데 유용하지만 독립 정확도가 아니다.
- `synthetic_independent`: 카탈로그에서 기대 라벨을 뽑지 않고 별도 fixture가 정한 UI 상태 스트레스. 실제 앱은 아니지만 presentation 일반화에 대한 별도 근거다.

`full`은 catalog route 변형과 기본 96개의 합성 차원 케이스를 추가한다. `deep`은 intent당 최소 6개 catalog route 변형과 기본 256개의 합성 차원 케이스를 사용하고, 선언된 차원 값과 가능한 2-way 조합을 모두 덮어야 gate를 통과한다. 합성 차원은 locale, 로그인 상태, 화면 surface, loading/error/permission 상태, enabled/disabled/checked/icon-only 상태, Activity 종류, 기기·Android·방향, 기대 행동(click/stop/scroll/back/no-click)을 교차한다.

현재 소스에서 실행 시 만들어지는 규모는 다음과 같다. 이는 입력 규모이지 정확도 결과가 아니다.

| Gym 모드 | 고정 케이스 | catalog-generated | synthetic-independent | 전체 케이스 | gold 단계 |
|---|---:|---:|---:|---:|---:|
| `fast` | 101 | 0 | 0 | 101 | 189 |
| `full` 기본값 | 246 | 531 (`177 intent × 3`) | 96 | 873 | 2,334 |
| `deep` 기본값 | 246 | 1,062 (`177 intent × 6`) | 256 | 1,564 | 4,255 |

`full`과 `deep`의 고정 246개는 기존 fast 101개, independent core 70개, alias-collision adversarial 75개로 구성된다. `fast`는 빠른 회귀를 위해 뒤의 두 대형 frozen 세트를 로드하지 않는다. 합성 차원 모델은 10개 차원과 가능한 789개 값 쌍을 정의하며, 현재 생성기는 64개 이상의 케이스에서 이 2-way 조합을 모두 덮는다. 따라서 기본 `full` 96개와 `deep` 256개는 모두 pairwise 100% coverage를 목표로 한다.

최종 Top-1, 목적지, stateful route, unsafe/wrong click 결과는 생성 규모로 추정하지 않고 각 실행이 남긴 최신 `fast-report.json`, `full-report.json`, `deep-report.json`에서 확인한다. 아직 완료되지 않은 full/deep 실행을 과거 artifact나 catalog-derived 점수로 대신 보고하지 않는다.

전체 Top-1이 높더라도 `catalog_generated`만 높고 `fixed_independent`가 낮으면 DB가 실제로 좋아진 것이 아니다. 반대로 독립 실패는 숨기지 않고 다음 개선의 입력으로 사용한다. 실제 앱 성능 주장은 `real_device_gold` 분할이 채워진 뒤에만 한다.

## 8. Self-feedback: quarantine → test → human promotion

K-EXAONE과 자동 분석기는 정답 생성기가 아니라 실패 원인 분석기다. 되먹임 루프는 다음 순서를 지킨다.

1. **기준선 고정**: catalog audit, goal robustness, DB Gym을 실행하고 보고서·실패 ID·baseline을 보존한다.
2. **실패 분류**: 목적 해석 실패, 별칭 누락, 공통 관문 누락, 의미 충돌, 목적지 조기 판정, 불필요한 스크롤, 잘못된 뒤로 가기, 위험 동작 시도, 경로 재사용 실패 등으로 묶는다.
3. **Quarantine**: 결정론적 제안과 K-EXAONE 제안은 `.artifacts/navigation-db-gym/*-suggestions.json` 또는 `exaone-proposals.json`에만 둔다. 이 단계의 값은 canonical truth와 SQLite index를 수정하지 않는다.
4. **Test first**: 실제 실패 ID를 인용하는 최소 회귀 케이스를 만든다. 기대 행동과 기대 function은 기존 고정 증거 또는 사람이 확인한 화면으로 정한다. 모델의 답을 기대값으로 복사하지 않는다.
5. **개발 세트 검증**: 후보 alias·context guard·goal rule·route function을 임시 적용해 해당 실패뿐 아니라 collision, holdout, adversarial, 안전 gate를 함께 실행한다.
6. **Human promotion**: 사람이 증거, 범용성, 안전성을 검토한 뒤에만 `function-catalog.v1.json` 또는 검토된 고정 fixture로 승격한다.
7. **전체 회귀**: audit → goal robustness fast/full → Gym fast/full/deep 순으로 실행하고, 이전 baseline과 정확도·오클릭·경로 시간 변화를 비교한다.

K-EXAONE 제안 도구는 알려진 function ID와 실제 실패 case ID만 허용하며 결과에 `review_required=true`, `auto_apply=false`를 강제한다. 허용되는 제안도 alias, 문맥 guard, intent pattern, goal rule, route function, terminal guard, regression case, 자동화 정책 강화뿐이다. 모델이 benchmark 기대값을 바꾸거나 경로를 자동 승인하는 동작은 허용하지 않는다.

승격을 거부해야 하는 예시는 다음과 같다.

- 한 케이스의 전체 문장을 alias로 복사해 점수만 올리는 변경.
- 특정 앱·버전의 픽셀 좌표를 공통 기능 카탈로그에 넣는 변경.
- 독립 holdout 정답을 보고 같은 문구를 학습 데이터로 유출하는 변경.
- 오답을 없애기 위해 기대값을 모델 출력에 맞추는 변경.
- Top-1을 높이기 위해 `never_auto` 또는 실행 전 정지 정책을 완화하는 변경.

## 9. 발견 경로의 lifecycle과 승인 기준

자동 탐색으로 성공해 보이는 경로도 처음부터 재사용하지 않는다.

| 상태 | 의미 | K-EXAONE 검색 근거에 사용 |
|---|---|---|
| `shadow` | 새로 발견됐거나 표본이 부족한 임시 경로 | 아니요 |
| `verified_candidate` | 독립적인 깨끗한 목적지 검증 1회 | 약한 근거 |
| `verified` | 독립적인 깨끗한 목적지 검증 2회 이상 | 중간 근거 |
| `trusted` | 최소 성능 표본과 모든 안전 gate를 반복 통과 | 강한 근거 |
| `rejected` | 사람/Gold 검증에서 오답·위험·오클릭 확인 | 아니요 |
| `stale` | 앱 업데이트·화면 불일치로 무효화 | 아니요 |

기본 `trusted` 승격 최소 표본은 3개다. 표본은 `benchmark_gold`, `human_gold` 또는 읽기 호환용 `device_gold`처럼 신뢰 가능한 verification level이어야 한다. `runtime_inferred` 성공이나 시간 측정만으로는 correctness 표본이 되지 않는다. 과거 DB의 `approved`는 마이그레이션 시 `trusted`로 정규화한다.

승격 조건은 다음을 모두 만족해야 한다.

- 동일 앱, 앱 버전, locale, 시작 화면 fingerprint, target function의 경로일 것.
- 신뢰 가능한 표본이 3개 이상일 것.
- 모든 신뢰 표본에서 목적지 정답, 안전 정지, 성공이 확인될 것.
- 실패 0건, 위험 자동 클릭 0건, 잘못된 클릭 0건일 것.
- UI 불일치로 `stale` 또는 검토 실패로 `rejected`가 된 경로는 시간 로그만으로 부활하지 않을 것.

`trusted` 이후에도 사람 검증에서 한 번이라도 잘못된 목적지·오클릭·위험 실행이 확인되면 `rejected`로 내려가고 검색에서 제외된다. 앱 버전이 바뀌면 이전 버전 근거를 그대로 신뢰하지 않고 새 version signature에서 다시 검증한다. 어떤 상태에서도 좌표·클릭 배열을 매크로처럼 실행하지 않으며 K-EXAONE이 현재 화면 후보를 새로 판단한다.

여러 승인 경로의 순위는 정확도와 안전을 속도보다 먼저 비교한다. 그 다음 충분한 표본, 성공률, 제어 가능 시간 p90·p50, 전체 TCD p90·p50, 클릭·스크롤·뒤로 가기 수, 최근 성공 시각 순으로 본다. 빠른 오답 경로는 최적 경로가 될 수 없다.

## 10. 실행 명령

모든 명령은 저장소 루트에서 실행한다. 보고서 경로를 새 폴더로 지정하면 이전 결과와 섞이지 않는다.

### 10.1 Catalog audit

```powershell
.\scripts\Audit-NavigationCatalog.ps1 -Gate
```

검사 범위는 참조 무결성, 중복 ID, 별칭·pattern 충돌, 최소 커버리지, 28개 도메인, 상태·위험 메타데이터, orphan 비율, 상태 변경 안전 불변식이다. 결과는 `.artifacts/navigation-catalog-quality/catalog-quality-report.json`에 기록된다.

### 10.2 목적 해석 metamorphic 회귀

```powershell
.\scripts\Evaluate-NavigationGoalRobustness.ps1 -Mode fast -Gate
.\scripts\Evaluate-NavigationGoalRobustness.ps1 -Mode full -Gate
```

기본 최소 정확도는 99.5%다. 이 시험은 catalog-derived 안정성 gate이며 독립 실기 정확도 gate가 아니다.

### 10.3 Navigation DB Gym

```powershell
# 기존 고정 101개/189단계의 빠른 회귀
.\scripts\Run-NavigationDbGym.ps1 -Mode fast -Gate

# frozen 독립 세트 + intent당 3개 catalog route 변형 + 96개 합성 차원 케이스
.\scripts\Run-NavigationDbGym.ps1 -Mode full -GeneratedVariants 3 -Gate

# frozen 독립 세트 + intent당 최소 6개 route 변형 + 256개 합성 차원
# 10개 차원/789개 가능한 pair 전체 coverage gate
.\scripts\Run-NavigationDbGym.ps1 -Mode deep -GeneratedVariants 6 -SyntheticCases 256 -Gate
```

이전 결과와 비교할 때는 별도 output과 baseline을 지정한다.

```powershell
.\scripts\Run-NavigationDbGym.ps1 -Mode deep `
  -GeneratedVariants 6 `
  -SyntheticCases 256 `
  -OutputDir .artifacts\navigation-db-gym-candidate `
  -Baseline .artifacts\navigation-db-gym-baseline\deep-report.json `
  -Gate
```

Gym gate의 핵심 기준은 위험 자동 클릭 0%, 잘못된 클릭 2% 이하, 전체 Top-1·목적지 정확도 90% 이상, holdout Top-1 80% 이상, stateful case 성공률 90% 이상이다. `deep`은 이에 더해 선언된 합성 차원 값과 가능한 차원 쌍의 100% coverage를 요구한다. 합성 TCD는 회귀용 비용 모델이며 실제 휴대전화 속도가 아니다.

### 10.4 K-EXAONE 검토 후보

```powershell
.\scripts\Propose-NavigationDbChanges.ps1 `
  -Report .artifacts\navigation-db-gym\full-report.json
```

출력은 quarantine 제안일 뿐 자동 적용되지 않는다.

## 11. 핸드폰 없이 검증 가능한 범위

노트북만으로 다음을 충분히 반복할 수 있다.

- JSON 스키마, 참조 무결성, 28개 도메인과 메타데이터 커버리지.
- 한국어·영어 목적 해석, 문장 wrapper·구두점·공백 변형 안정성.
- 별칭·긍정/부정 문맥·locale·role·상태 단서를 이용한 메뉴 후보 순위.
- 고정 독립 화면에서 click/stop/scroll/back/no-click 선택.
- loading, error, permission denied, disabled, checked, icon-only, dialog, sheet, drawer, endless feed 같은 합성 상태.
- 위험 버튼 자동 클릭 0, 사용자 최종 클릭, route lifecycle의 trusted evidence 조건.
- 앱별 경로 캐시의 버전·fingerprint 분리, synthetic TCD와 회귀 시간 비교.
- K-EXAONE 제안의 schema 제한과 `auto_apply=false` 보장.

다음 항목은 실제 Android 기기와 `real-device gold` 없이는 완료됐다고 주장할 수 없다.

- 실제 앱이 AccessibilityService에 노출하는 텍스트, content description, bounds, clickable/checked 상태.
- 커스텀 캔버스, WebView, 아이콘 전용 버튼, OEM별 Android 설정 화면에서의 인식률.
- 앱 업데이트·A/B 테스트·로그인 상태·지역·구독 상태에 따른 실제 분기.
- 자동 탐색 클릭·스크롤·뒤로 가기의 실제 화면 전환과 복구 성공.
- 네트워크 로딩, 외부 브라우저·스토어·다른 앱 전환, 권한 dialog의 실제 동작.
- 실제 TCD p50·p90, 오클릭률, 최종 목적지 성공률.

현재 `real-device-gold.v1.json`에는 0개 케이스가 있으므로, 데스크톱 결과가 좋아도 “실제 앱에서 검증 완료”라고 표현하지 않는다. 실기 gold에는 앱 package·version, locale, 기기 모델, Android 버전, 검증자, 검증 시각, 단계별 기대 function·label·action과 근거가 필요하다. 이름, 이메일, 전화번호, 주소, 결제정보, 메시지, 토큰 등은 저장 전에 제거한다.

## 12. 데이터 추가 체크리스트

### 기능(function)

- [ ] 기존 function으로 표현할 수 없는 의미인지 먼저 검색했다.
- [ ] 안정적인 `domain.function` 형태의 ID와 28개 도메인을 선택했다.
- [ ] Android 시스템 기능인지 인앱 기능인지 분리하고 정확한 `scope`를 지정했다.
- [ ] `node_kind`, `terminal`, `state_changing`, `risk_level`, `automation_policy`, `stop_policy`가 서로 모순되지 않는다.
- [ ] 상태 변경 또는 high-risk 기능은 `never_auto`이며 실행 전에 정지한다.
- [ ] 한국어·영어 표준 이름, 설명, 실제 UI 별칭을 locale별로 넣었다.
- [ ] 이름이 같은 다른 기능을 구분할 positive/negative context를 넣었다.
- [ ] button/menuitem/tab/switch/image 등 `role_hints`를 넣었다.
- [ ] enabled/checked/selected와 기능별 텍스트 상태를 `state_cues`로 넣었다.
- [ ] 결제·삭제·전송·권한·위치·계정 영향 문구를 `risk_cues`로 넣었다.
- [ ] 특정 앱 좌표, 화면 전체 문장, 개인정보를 넣지 않았다.

### 목적(intent)과 기능 경로

- [ ] 사용자 목적을 직접 표현하는 짧고 자연스러운 pattern을 두 언어 이상에서 준비했다.
- [ ] 단일 단어 충돌을 피하기 위한 복수 단서 `goal_rules`를 준비했다.
- [ ] `terminal_function`이 실제로 사용자가 찾는 기능이고 최종 실행 버튼과 구분된다.
- [ ] route는 좌표가 아니라 공통 기능 관문이며 단계 가중치가 목적지로 갈수록 높다.
- [ ] 동음이의 기능과 위험 최종 버튼을 `avoid_functions`에 넣었다.
- [ ] 전체 문장 암기 대신 여러 앱에 재사용 가능한 표현만 승격했다.

### 증거와 시험

- [ ] 새 지식의 출처, 수집일, 앱/플랫폼, 검토자를 기록했다.
- [ ] catalog 수정 전에 독립 또는 최소 회귀 케이스를 만들었다.
- [ ] 정상 상태뿐 아니라 signed-out, loading, error, disabled, icon-only, scroll, backtrack, dangerous decoy를 포함했다.
- [ ] 모델이 만든 기대값을 정답으로 사용하지 않았다.
- [ ] `Audit-NavigationCatalog.ps1 -Gate`를 통과했다.
- [ ] goal robustness fast/full을 통과했다.
- [ ] DB Gym fast/full/deep에서 독립 분할, holdout, adversarial, unsafe/wrong click을 따로 확인했다.
- [ ] 이전 baseline보다 독립 정확도·안전·TCD가 악화되지 않았다.
- [ ] 실제 앱 성능을 주장할 항목은 별도 real-device gold로 확인했다.

### 발견 경로

- [ ] 새 경로는 `shadow`로 저장했다.
- [ ] 앱 version signature와 시작 화면 fingerprint가 일치한다.
- [ ] 신뢰 가능한 독립 표본 3개 이상에서 목적지·안전 정지를 확인했다.
- [ ] 실패, 위험 자동 클릭, 잘못된 클릭이 모두 0이다.
- [ ] UI 불일치가 발생하면 `stale`, 사람 검증 실패면 `rejected`로 내렸다.
- [ ] 속도는 정확도와 안전을 통과한 경로 사이에서만 비교했다.

이 체크리스트를 통과한 데이터만 canonical catalog 또는 승인 경로로 승격한다. 나머지는 모두 quarantine, development 또는 `shadow` 상태로 남긴다.
