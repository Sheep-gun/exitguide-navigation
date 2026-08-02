# ExitGuide Navigation DB Redesign

기존 앱별 완성 경로·대형 기능 카탈로그 방식과 분리한 Navigation Agent 실험이다. 이 저장소의 런타임은 **현재 화면에서 발견된 후보만** 다루며, 과거의 화면별 의사결정 결과를 검색해 다음 행동을 선택한다. 앱 이름으로 경로를 재생하거나 임의 좌표를 생성하지 않는다.

## 시스템을 한눈에 보기

> **EXAONE 4.5 VLM = 눈** — 화면 전체 의미, 아이콘, 영역, 주변 문맥을 해석
>
> **Solar Pro 3 LLM = 두뇌** — 목적과 현재 상태를 바탕으로 다음 행동을 계획하고 후보 가치를 평가
>
> **N100 신규 DB = 기억** — 과거의 유사 화면·후보·선택·결과·실패 경험을 검색하고 축적
>
> **Navigation API = 신경계 및 통제 장치** — 눈·두뇌·기억을 연결하고, 후보 ID 제한과 위험 행동 차단을 담당
>
> **Android 앱/실행기 = 손과 몸** — 승인된 클릭·스크롤·뒤로가기만 실제 실행

## N100에 구축된 현재 DB

Canonical SQLite: `/home/kyle/exitguide/imports/yanggeon/20260802-navigation-db-redesign/output/navigation-decision-v1.sqlite`

| 계층 | 테이블 | 현재 행 수 | 역할 |
|---|---|---:|---|
| Goal Ontology | `goals`, `goal_phrases`, `goal_relations` | 6 / 41 / 4 | 한국어 목적을 회원가입·회원탈퇴·멤버십 목적과 조건으로 정규화 |
| Destination Signature | `destination_signatures` | 6 | 화면 전체 의미 특징으로 목적지 판정 |
| Semantic Screen State | `semantic_screens`, `screen_observations` | 73 / 73 | 앱·좌표 독립 화면 상태와 Accessibility/OCR/VLM 관찰 |
| Affordance Memory | `affordance_roles`, `affordance_role_aliases`, `affordances` | 14 / 76 / 1,525 | 화면에 실제 존재한 전체 후보와 기능 역할 |
| Transition Outcome | `decision_cases`, `transition_outcomes` | 74 / 74 | 한 화면에서 한 후보를 선택한 결과와 목적지 거리 변화 |
| Failure & Recovery | `recovery_memories` | 11 | 금지 후보, 반복 실패와 안전 복구 행동 |
| Evidence & Confidence | `evidence_records` | 222 | Human Gold·실기기·합성·모델 추론의 출처와 신뢰도 |
| Leakage Control | `evaluation_app_splits` | 8 | 앱 단위 train/validation/test 분리 |

DB 파일 크기는 1,912,832 bytes이고 schema version은 1이다. 기존 대형 AndroidControl 색인, 앱별 Gold 매크로, 전체 기능 카탈로그, Terms RAG는 이 실험의 런타임 의존성이 아니다. Human Gold는 화면별 고신뢰 의사결정 사례로 분해된 결과만 사용한다.

상세 스키마와 인덱스는 [Navigation Decision DB 설계](docs/NAVIGATION_DECISION_DB_V1.md), SQL은 [navigation_decision_v1.sql](db/navigation_decision_v1.sql)에서 확인할 수 있다.

## 최종 Navigation Agent 흐름

```mermaid
flowchart TD
    USER["사용자 자연어 목적"] --> GOAL_INPUT["Navigation API<br/>사용자 목적과 허용 goal_id 목록 준비"]
    GOAL_DB["Goal Ontology DB<br/>기능 카탈로그"] --> GOAL_INPUT
    GOAL_INPUT --> GOAL["Solar Pro 3<br/>표준 goal_id 1개 반환"]
    GOAL --> GOAL_CHECK["Navigation API<br/>DB에 실제 존재하는 goal_id인지 검사<br/>없는 ID는 거부"]
    GOAL_CHECK --> DEST["Destination Signature DB<br/>goal_id에 맞는 최종 목적지 설정"]

    SCREEN["현재 Android 화면"] --> VIEW["Accessibility/OCR + EXAONE 4.5<br/>현재 화면과 후보 파악"]
    DEST --> K2["Navigation API의 K²식 Planner<br/>다음 중간 목표 결정"]
    VIEW --> K2
    MEMORY["Decision Memory DB<br/>과거 선택·결과를 판단 근거로 제공"] --> K2

    K2 --> CLEAR{"중간 목표와 기능적으로 동일한<br/>안전 후보가 하나뿐인가?"}
    CLEAR -->|"누가 봐도 명확"| FAST["엄격한 fast path"]
    CLEAR -->|"조금이라도 애매"| VDROID["Solar Pro 3 + V-Droid식 평가<br/>DB 근거와 전체 후보를 함께 비교"]
    MEMORY --> VDROID
    FAST --> CHOOSE["다음 행동 선택"]
    VDROID --> CHOOSE

    CHOOSE --> SAFE["Python 안전 검사<br/>실재 후보 확인 · 위험 행동 차단"]
    SAFE -->|"위험"| STOP["사용자에게 최종 행동 요청"]
    SAFE -->|"안전"| EXECUTE["Android 실행기가 행동 실행"]

    EXECUTE --> VERIFY["DroidRun식 Navigation API<br/>행동 후 새 화면과 결과 확인"]
    VERIFY --> RESULT{"행동 결과"}
    RESULT -->|"목적지 도달"| STOP
    RESULT -->|"진전"| RECORD["성공 경험 기록"]
    RECORD --> SCREEN
    RESULT -->|"실패·반복"| RECOVERY["MobileUse식 Navigation API<br/>필요할 때만 복구"]
    RECOVERY --> SCREEN
    RESULT -->|"연결 오류"| WAIT["연결 복구 후 다시 관찰"]
    WAIT --> SCREEN
```

`Goal Ontology DB`는 기능 카탈로그, `Destination Signature DB`는 목표에 맞는 최종 목적지,
`Decision Memory DB`는 과거 선택과 결과 경험이다. 모두 N100 Navigation Decision DB 안의
서로 다른 데이터 계층이다.

Navigation API가 Goal Ontology DB에서 허용된 `goal_id` 목록을 읽어 Solar에 전달한다.
Solar는 그중 하나만 반환하고, Navigation API는 그 ID가 DB에 실제 존재하는지 검사한다.
없는 ID는 거부한다. Solar classifier가 실패하거나 사용할 수 없을 때만 Python 문구 매칭을
명시적인 fallback으로 사용한다.

중간 목적지를 만드는 주체는 **Navigation API 내부의 K²식 Planner**다. K²는 별도 모델명이
아니라 최종 목표를 현재 화면에서 검증 가능한 sub-goal로 나누는 계획 구조이며, Solar Pro 3는
그 구조 안에서 추론하는 엔진이다. DB는 판단 주체가 아니라 K²/V-Droid 판단에 과거 성공·실패
근거를 제공한다. fast path는 안전하고 금지되지 않은 후보 중 하나만 중간 목표의 기능 역할과
사실상 동일하고 경쟁 후보와도 명확히 구분될 때만 허용한다. 이 조건을 하나라도 만족하지 못하면
Solar가 DB 근거와 현재 전체 후보를 함께 평가한다. 어느 경로든 행동 후 검증은 생략하지 않는다.

허용 행동은 `click(candidate_id)`, `scroll(direction)`, `back()`, `wait_and_observe()`, `stop_for_user()`뿐이다. `click`은 관찰된 후보 ID가 아니면 안전 행동으로 대체되고, 결제·탈퇴 확정·해지 확정·개인정보 제출은 항상 `stop_for_user()`로 전환된다. 연결 오류는 UI 탐색 실패와 별도 상태로 저장한다.

## AndroidWorld 상위 연구를 적용한 위치

- K²-Agent: 상위 목적을 즉시 검증 가능한 sub-goal과 기대 결과로 분해한다.
- V-Droid: 모델이 좌표를 생성하지 않고, 현재 화면에서 열거된 후보 각각의 가치를 검증한다.
- DroidRun/Mobilerun: 실행 성공 여부를 다음 화면 관찰로 판정하고 공유 상태와 Transition Outcome에 기록한다.
- MobileUse: 매 단계가 아니라 낮은 신뢰도·반복·무변화·역행 시에만 action/trajectory/global reflection을 호출한다.

논문의 벤치마크 데이터나 학습 가중치를 복제했다고 주장하지 않는다. 구조와 입출력 경계를 가져와 Solar Pro 3·EXAONE 4.5·N100 DB에 맞게 구현했다. 근거, 구현 대응표, 아직 검증하지 못한 부분은 [AndroidWorld 연구 기반 아키텍처](docs/ANDROIDWORLD_RESEARCH_ARCHITECTURE.md)에 정리돼 있다.

## 코드 구성

```text
apps/api/app/navigation_main.py                 FastAPI 진입점
apps/api/app/navigation_contracts.py            후보·행동·관찰 계약
apps/api/app/services/navigation_decision_memory.py  신규 DB Retriever
apps/api/app/services/navigation_research_policy.py  계층 계획·후보 검증·선택적 복구
apps/api/app/services/navigation_model_clients.py    Solar Pro 3 / EXAONE 4.5 어댑터
apps/api/app/services/navigation_runtime.py          결정→실행 후 검증 흐름
apps/api/app/services/navigation_runtime_store.py    승격 전 append-only 경험 저장
apps/android-executor/                         후보 ID 전용 Accessibility 실행기
db/navigation_decision_v1.sql                   검증된 기억 스키마
db/navigation_runtime_v1.sql                    런타임 관찰 스키마
scripts/Migrate-NavigationDecisionDb.py         기존 기록의 결정 단위 변환기
scripts/Evaluate-NavigationRuntimeOffline.py    앱 분리 오프라인 A/B 평가기
```

API 계약은 [Navigation API v1](docs/NAVIGATION_API_V1.md)에 있다.
Android 실행 계약과 설치 방법은 [Android Executor v1](docs/ANDROID_EXECUTOR_V1.md)에 있다.

### 실기기 경험 수집 상태

Android Executor는 `/decide → 안전 실행 → /observe` 루프를 최대 15단계·10분까지 자율 수행한다. runtime schema v3는 각 단계의 before/after 화면, 전체 후보, 후보별 점수, 실제 선택, 실행 상태, 연결 상태, 목적지 거리 변화, 실패와 복구 힌트 및 고정된 앱 데이터 분할을 정규화해 저장한다. 연결 오류는 탐색 실패와 분리되고, 위험한 최종 행동은 서버와 기기 양쪽에서 `stop_for_user`로 차단된다. 수집 중에는 좌표 기반 keep-alive 대신 Android wake-lock을 유지하며 종료 시 해제한다. 수집 세션은 `GET /v1/navigation/sessions/{session_id}/episode`로 확인할 수 있다.

## 로컬 검증

```bash
python -m pip install -r apps/api/requirements.txt
python apps/api/tests/navigation_decision_memory_unit.py
python apps/api/tests/navigation_experience_profile_unit.py
python apps/api/tests/navigation_interaction_adapter_unit.py
python apps/api/tests/navigation_research_architecture_unit.py
python apps/api/tests/navigation_runtime_unit.py
cd apps/android-executor
./gradlew testDebugUnitTest assembleDebug
```

실기기 테스트 전 단계에서는 모델 미연결 fallback과 기록된 화면으로 계약·안전성만 검증한다. 실제 성공률 개선 여부는 앱 단위 완전 분리 A/B 평가와 실기기 검증 전에는 확정하지 않는다.

## 현재 결과에 대한 냉정한 결론

74개 변환 사례를 source app 제외 방식으로 다시 재생한 진단 결과는 첫 행동 0.7778, 전체 positive next-action exact match 0.4603, 기록된 실패 클릭 회피 0.8182, 위험 행동 자동 클릭 0건이었다. 이는 **최종 A/B가 아니라 runtime 방향성 검사**다. 전체 다음 행동 정확도 46.03%는 아직 낮고 기존 방식보다 개선됐다고 말할 근거도 없다. 따라서 정적 데이터를 더 쌓지 않고, 실제 Solar Pro 3/EXAONE 4.5 endpoint를 연결한 앱 분리 A/B와 실패 지점 분석을 먼저 수행한다. 재현 조건과 미충족 기준은 [오프라인 평가 보고서](docs/OFFLINE_AB_EVALUATION.md)에 있다.

2026-08-02 실모델 smoke에서는 EXAONE 4.5가 합성 화면 후보 ID를 3/3 보존했고 약 4.5초에 응답했다. 기존 K-EXAONE은 단일 Hermes 호출도 56.7~92.0초가 걸려 폐기했고, Solar Pro 3로 교체했다. N100에서 Solar Pro 3의 단순 응답은 약 0.50초, 강제 Hermes tool call은 약 0.59초, 실제 계획+전체 후보 평가는 4.21~6.17초였다. DB가 확신한 첫 fast path는 약 0.018초, 정상 history가 있는 두 번째 fast path도 약 0.021초에 Solar 없이 결정했다. 관찰된 `no_change` 뒤에는 Solar로 escalation했고, 위험 해지 확정은 `stop_for_user()`로 차단했다. 선택 품질은 앱 분리 A/B 전까지 개선됐다고 결론 내리지 않는다. 상세 결과는 [실모델 smoke 보고서](docs/LIVE_MODEL_SMOKE_2026-08-02.md)에 있다.

## 표준화 Profile

기존 DB를 보존하면서 W3C SKOS, RLDS, Android Accessibility, W3C PROV-O,
JSON Schema를 적용하는 규격과 변환기를 추가했다. 규격과 수집 규칙은
[Navigation Experience Profile v1](docs/NAVIGATION_EXPERIENCE_PROFILE_V1.md), 실제 현재 데이터의
부족분은 [DB 품질 보고서](docs/NAVIGATION_DB_QUALITY_REPORT_2026-08-03.md)를 기준으로 한다.
