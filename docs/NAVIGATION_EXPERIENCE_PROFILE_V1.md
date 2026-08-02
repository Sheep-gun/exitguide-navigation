# ExitGuide Navigation Experience Profile v1

## 결정

Navigation Agent 전체를 포괄하는 단일 표준은 없으므로 계층별 기존 규격을 사용하고,
규격이 없는 목적지·진행도·위험·복구만 ExitGuide 확장으로 정의한다.

이 Profile은 기존 Navigation Decision DB v1을 삭제하거나 재작성하지 않는다. v1 파일을
읽기 전용으로 복사한 뒤 표준 매핑 sidecar를 추가하며 SQLite `user_version=2`로 구분한다.
기존 Retriever가 사용하는 테이블명과 컬럼은 그대로 유지된다.

## 규격 매핑

| ExitGuide 계층 | 기준 규격 | 구현 | 매핑 수준 |
|---|---|---|---|
| Goal Ontology | [W3C SKOS](https://www.w3.org/TR/skos-reference/) | `goal_standard_concepts`, `goal_label_mappings`, `goal_relation_mappings` | 정식 표준 |
| 언어·locale | [BCP 47 / RFC 5646](https://www.rfc-editor.org/rfc/rfc5646) | `language_tag` 및 변환기 검증 | 정식 표준 |
| Android 화면 원본 | [AccessibilityNodeInfo](https://developer.android.com/reference/android/view/accessibility/AccessibilityNodeInfo) | `accessibility_json`의 정규화·비식별 subset | Android 플랫폼 규격 |
| 행동 경험 | [Google RLDS](https://github.com/google-research/rlds) | `experience_episodes`, `experience_steps`, `rlds_experience_steps_v1` | 연구계 de facto 형식 |
| 출처·검증 | [W3C PROV-O](https://www.w3.org/TR/prov-o/) | `provenance_agents`, `provenance_activities`, `evidence_provenance` | 정식 표준 |
| JSON 계약 | [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) | `db/contracts/*.schema.json` | 정식 표준 |
| API 계약 | [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.1.html) | FastAPI/Pydantic 계약과 JSON Schema ID 사용 | 산업 표준 |

`standard_term_mappings`가 각 로컬 필드와 외부 규격 URI의 관계를 DB 내부에도 보존한다.
`exact`, `close`, `extension`을 구분하므로 ExitGuide 확장을 표준 필드처럼 오인하지 않는다.

## ExitGuide 전용 확장

다음에는 범용 규격이 없어 기존 설계를 버전이 있는 확장으로 유지한다.

| 확장 | 저장 위치 | 규칙 |
|---|---|---|
| Destination Signature | `destination_signatures` | 제목·문구·버튼·상태의 required/optional/forbidden/terminal 조합 |
| 의미적 진행도 | `transition_outcomes.progress_label` | `reached`, `advanced`, `unchanged`, `regressed`, `unknown` |
| 위험한 최종 행동 | `affordances.dangerous_final` | 클릭 사례 0건, 런타임은 `stop_for_user`로 전환 |
| 실패·복구 | `recovery_memories` | 실패 signature, 금지 후보, 복구 행동과 실제 복구 결과 |
| 연결 상태 분리 | `transition_outcomes.connectivity_status` | 연결 실패일 때 화면 전이·진행도를 추정하지 않음 |

## 계층별 수집 규격

### 1. Goal Ontology

- `goal_id`는 SKOS `notation`, 각 목표는 `skos:Concept`로 취급한다.
- 목표와 언어마다 `skos:prefLabel`은 정확히 하나만 둔다.
- 유사 표현은 `skos:altLabel`로 저장한다.
- `related`는 `skos:related`로 매핑한다.
- 반대 목적과 선행 조건은 SKOS에 없는 ExitGuide 관계로 분리한다.
- Solar가 반환한 `goal_id`는 반드시 현재 활성 Concept allowlist에 존재해야 한다.

### 2. Destination Signature

- 단일 버튼명이 아니라 화면 전체 의미 특징의 조합으로 저장한다.
- `required_features_json`, `optional_features_json`, `forbidden_features_json`,
  `terminal_features_json`은 JSON 배열이어야 한다.
- 최종 확인·결제·탈퇴 확정 의미는 `terminal`로 기록하고 자동 클릭하지 않는다.
- Signature 변경은 기존 행 수정 대신 `version`을 증가시킨다.

### 3. Semantic Screen State

- Accessibility, OCR, VLM 원본은 각 JSON Schema를 통과해야 한다.
- Accessibility는 `node_id`, 부모 ID, label, role, 클릭·스크롤 가능 여부를 기본 subset으로 사용한다.
- DB에는 임의 클릭 좌표를 학습값으로 저장하지 않는다. 실제 실행은 현재 화면에서 발견한 후보 ID만 사용한다.
- OCR/VLM이 없으면 빈 객체로 남기며 모델 추론으로 위조하지 않는다.
- `app_package`는 출처·누수 방지용이고 semantic fingerprint 생성의 정답 키로 사용하지 않는다.

### 4. Affordance Memory

- 현재 화면의 전체 후보를 저장하며 선택 후보만 저장하지 않는다.
- 후보는 label, icon 의미, 부모 문맥, 주변 문구, 위치 bucket, 기능 역할을 함께 갖는다.
- `candidate_key`는 한 화면 안에서 유일해야 한다.
- `chosen_affordance_id`는 해당 decision case의 동일 화면 후보를 가리켜야 한다.

### 5. Transition Outcome / RLDS

- 경로 전체는 `experience_episodes`, 각 화면의 결정은 `experience_steps`로 표현한다.
- Step의 `observation`은 현재 semantic screen, `action`은 승인된 다섯 행동 중 하나다.
- `is_first`, `is_last`, `is_terminal`을 분리한다. 연결 중단이나 사용자 이관은 `is_last`일 수 있지만 환경 terminal은 아니다.
- ExitGuide 진행도 reward는 `reached=1.0`, `advanced=0.5`, `unchanged=0.0`,
  `regressed=-0.5`, `unknown=NULL`이다. 이는 학습 정답이 아니라 Retriever의 정렬 보조값이다.

### 6. Failure and Recovery

- `device_disconnected`, `transport_error`, `not_observed`는 탐색 실패와 별도 집계한다.
- 연결 상태가 `observed`가 아니면 `next_screen_id`, `state_changed`, 진행도를 기록하지 않는다.
- 실패 후보의 반복 금지와 복구 행동은 실제 관찰 결과가 있을 때만 저장한다.

### 7. Evidence and Confidence / PROV-O

- DB 객체는 PROV Entity, 수집·추론은 Activity, 사람·수집기·모델은 Agent로 매핑한다.
- Human Gold, 실기기, 합성, 모델 추론을 같은 provenance로 합치지 않는다.
- `verification_count`, confidence, 앱 버전, 언어, 마지막 검증 시각을 보존한다.
- Human Gold는 높은 신뢰도의 Episode/Step 사례이며 앱별 클릭 매크로로 제공하지 않는다.

## 스키마 파일

- SQLite 확장: `db/navigation_experience_profile_v1.sqlite.sql`
- PostgreSQL 15+ 확장: `db/navigation_experience_profile_v1.postgresql.sql`
- 휴대 가능한 레코드 계약: `db/contracts/navigation_experience_profile.v1.schema.json`
- 관찰 계약: `db/contracts/android_accessibility_observation.v1.schema.json`,
  `ocr_observation.v1.schema.json`, `vlm_observation.v1.schema.json`

PostgreSQL에서는 core 테이블을 동일한 키로 반입한 후 PostgreSQL 확장 SQL을 한 트랜잭션으로
적용한다. SQLite JSON text는 `jsonb`, 정수 boolean은 `boolean`, RFC3339 text 시각은
`timestamptz`로 사용한다. JSON 검색에는 GIN 인덱스를 사용한다.

## 안전한 변환

```powershell
.\.venv\Scripts\python.exe scripts\Migrate-NavigationExperienceProfile.py `
  --source .artifacts\integration\navigation-decision-v1.sqlite `
  --target .artifacts\integration\navigation-decision-v2.sqlite `
  --report .artifacts\integration\navigation-profile-migration.json
```

변환기는 다음 조건을 강제한다.

- source는 schema version 1이고 필수 테이블이 있어야 한다.
- source와 target은 달라야 하며 기존 target을 덮어쓰지 않는다.
- SQLite backup API로 새 파일을 만든 뒤 profile만 추가한다.
- 변환 전후 source SHA-256이 같아야 한다.
- foreign key 및 `quick_check` 실패 시 생성 중인 target을 폐기한다.

기존 26.8MB 원본부터 재생성할 경우 기존
`Migrate-NavigationDecisionDb.py`로 v1을 만든 다음 위 변환기를 적용한다. AndroidControl,
앱별 route serving 상태, 전체 기능 카탈로그는 어느 단계에서도 반입하지 않는다.

## 품질 게이트

`Validate-NavigationExperienceProfile.py`가 다음을 자동 검사한다.

- SQLite 무결성·foreign key·schema/profile version
- SKOS Concept·label·relation 전수 매핑과 목표/언어별 단일 prefLabel
- BCP 47 언어 태그
- Accessibility/OCR/VLM JSON Schema
- RLDS Episode/Step 경계, source 연결, terminal과 reward 의미
- 앱 단위 split 누수
- 현재 화면 밖 후보 선택
- 연결 오류와 탐색 결과 혼동
- 위험 최종 클릭 0건
- 모든 evidence의 PROV Activity/Agent 연결
- RFC3339 시각, 이메일·전화번호·원시 element ID·좌표 비노출

이 검증은 DB 구조와 데이터 품질만 확인한다. 첫 행동 정확도, 목적지 도달률, 처음 보는 앱
성공률은 앱 완전 분리 오프라인 A/B와 실기기 평가 전에는 통과했다고 간주하지 않는다.
