# Navigation Decision DB v1

## 목적

Navigation Decision DB는 앱별 완성 경로나 방대한 기능명 목록을 저장하지 않는다. 기본 단위는 다음 질문에 대한 관찰 사례다.

> 이 목적과 이 의미적 화면 상태에서, 현재 발견된 전체 후보 중 어떤 행동을 선택했으며 다음 관찰에서 무엇이 달라졌는가?

v1의 범위는 `회원가입`, `회원탈퇴`, `멤버십 가입·관리·변경·해지`다. 기존 Navigation DB, Human Gold, 앱별 경로는 삭제하지 않고 별도 마이그레이션 원본 및 비교 기준으로만 보존한다.

## 이번 단계의 경계

이번 단계는 DB 구축 단계다. 다음 항목만 검증한다.

- 원본과 반입본의 SHA-256 일치
- SQLite `quick_check`와 외래키 위반 0건
- 스키마 제약, 인덱스, FTS 생성
- Human Gold 경로가 화면별 의사결정 사례로 분해됐는지
- 전체 후보와 선택 후보가 같은 화면에 귀속되는지
- 행동과 다음 화면 관찰이 분리돼 저장되는지
- 연결 실패가 탐색 실패로 기록되지 않는지
- 위험한 최종 행동이 `stop_for_user` 경계로 표현되는지
- 앱 단위 train/validation/test 분리
- 원시 좌표·원시 element ID·명백한 이메일/전화번호를 새 DB에 넣지 않는지

첫 행동 정확도, 전체 다음 행동 정확도, 목적지 도달률 및 복구율은 이 단계의 합격 기준이 아니다. K² 계층 계획, 후보 가치 평가, 행동 후 검증, 선택적 복구를 구현하고 Planner에 연결한 다음 동일한 앱 분리 정책으로 평가한다.

## 반입 원칙

반입 원본은 `legacy-universal-navigation-v2.sqlite` 하나다. 이 파일은 읽기 전용 마이그레이션 소스이며 런타임 DB로 사용하지 않는다.

반입하지 않는 항목:

- 기존 대형 외부 행동 예시 인덱스와 원시 레코드
- 전체 기능 카탈로그 JSON/SQLite
- 앱별 Gold 경로의 런타임 재생 정책
- 기존 route cache의 serving 상태
- Terms DB 및 Terms 서비스 데이터
- APK, 영상, raw XML, screenshot, 환경 변수와 비밀값

Human Gold는 경로 매크로가 아니라 높은 신뢰도의 화면별 선택 사례로만 변환한다. `cancelled`와 `rejected` 기록은 긍정 사례로 승격하지 않는다. 실기기 탐색의 명시적 `failed` 클릭은 실패·복구 메모리로 별도 변환한다.

## 스키마 계층

### Goal Ontology

- `goals`: 표준 목적, family, operation, 위험 등급, 최종 행동 정책
- `goal_phrases`: 한국어·영어 자연어 표현과 신뢰도
- `goal_relations`: 가입↔탈퇴, 가입↔해지와 같은 반대 목적 및 관계

앱 이름은 목적 정규화 근거로 사용하지 않는다.

### Destination Signature

- `destination_signatures`: 필수 의미 그룹, 보조 특징, 금지 특징, 최종 버튼 특징, 임계값

단일 버튼명이 아니라 제목·문구·버튼·현재 상태의 조합을 저장한다. 콘텐츠 구독 피드와 유료 멤버십 관리 화면처럼 이름이 비슷한 화면을 `forbidden_features_json`으로 구분한다.

### Semantic Screen State

- `semantic_screens`: 앱·좌표 독립 의미 fingerprint, 제목, 영역 역할, 깊이, 로그인 상태, Native/WebView 구분
- `screen_observations`: 앱 버전·locale·출처별 Accessibility/OCR/VLM 관찰

마이그레이션 데이터는 Accessibility와 OCR을 정규화한다. 기존 기록에 VLM 관찰이 없으면 빈 객체로 두며 모델 추론으로 채우지 않는다.

### Affordance Memory

- `affordance_roles`: 소형 기능 역할 집합
- `affordance_role_aliases`: 역할별 표현과 금지 문맥
- `affordances`: 화면의 전체 후보, 텍스트·아이콘 의미·역할·주변 관계·위치 bucket·위험도

전체 기능 카탈로그를 복사하지 않는다. v1은 핵심 목적에 필요한 14개 역할과 76개 별칭만 seed한다.

### Decision and Transition

- `decision_cases`: 정규화 목적, 세부 조건, 화면, 전체 후보 중 실제 행동, 출처 앱과 step provenance
- `transition_outcomes`: 다음 화면, 상태 변화, 목적지 Signature 일치도, 진행 여부, 실패 유형

허용 행동은 다음 다섯 가지로 제한한다.

- `click(candidate_id)`
- `scroll(direction)`
- `back()`
- `wait_and_observe()`
- `stop_for_user()`

`click`은 같은 화면의 `affordances` 행을 반드시 참조한다. 나머지 행동은 후보 ID를 가질 수 없도록 DB 제약으로 막는다.

### Failure and Recovery

- `recovery_memories`: 금지 후보, 실패 signature, 복구 행동, 복구 관찰 결과

`transition_outcomes.connectivity_status`는 `observed`, `device_disconnected`, `transport_error`, `not_observed`로 분리한다. 연결이 실패한 경우 다음 화면·상태 변화·진행도를 기록할 수 없도록 제약한다.

### Evidence and Confidence

- `evidence_records`: Human Gold, 실기기, 합성, 모델 추론을 구분하고 검증 횟수·앱 버전·locale·마지막 검증일을 저장
- `evaluation_app_splits`: 앱 단위 누수 방지 split

이번 스키마는 사용하지 않는 외부 행동 예시 출처를 허용하지 않는다.

## 주요 인덱스

- 목적 정규화: `(locale, normalized_phrase, confidence)`
- 목적지 Signature: `(goal_id, match_threshold)`
- 화면 관찰: `(app_package, locale, app_version, screen_id)`
- 후보 검색: `(screen_id, normalized_label, role)`
- 의사결정 검색: `(goal_id, screen_id, evidence_weight)`
- 앱 누수 차단: `(source_app_package, goal_id, source_type)`
- 성공 전이: 관찰 완료 및 `advanced/reached` 부분 인덱스
- 복구 검색: `(goal_id, failure_signature, recovered)`
- 출처 검증: `(entity_type, entity_id, confidence, last_verified_at)`

FTS5는 목적 문구와 의사결정 사례의 lexical cold start에만 사용한다. FTS 결과만으로 행동을 확정하지 않는다.

## SQLite와 PostgreSQL

v1 실험 DB는 배포와 오프라인 재생이 간단한 SQLite로 시작한다. PostgreSQL로 옮길 때의 대응은 다음과 같다.

- `TEXT` JSON + `json_valid` → `jsonb`
- FTS5 → `tsvector` + GIN
- `INTEGER` boolean → `boolean`
- 부분 인덱스는 동일한 `WHERE` 조건으로 유지
- SQLite 단일 writer → API writer와 read replica 또는 트랜잭션 격리

기본 키와 참조 구조는 PostgreSQL에서도 그대로 유지한다. 모델은 어느 DB에도 직접 접속하지 않고 Navigation API가 생성한 제한된 evidence packet만 받는다.

## 재현 명령

N100 전용 worktree에서 다음과 같이 실행한다.

```bash
python3 scripts/Migrate-NavigationDecisionDb.py \
  --source /home/kyle/exitguide/imports/yanggeon/20260802-navigation-db-redesign/source/legacy-universal-navigation-v2.sqlite \
  --target /home/kyle/exitguide/imports/yanggeon/20260802-navigation-db-redesign/output/navigation-decision-v1.sqlite \
  --report /home/kyle/exitguide/imports/yanggeon/20260802-navigation-db-redesign/manifests/migration-report.json \
  --split-manifest /home/kyle/exitguide/imports/yanggeon/20260802-navigation-db-redesign/manifests/app-splits.json

python3 scripts/Validate-NavigationDecisionDb.py \
  --database /home/kyle/exitguide/imports/yanggeon/20260802-navigation-db-redesign/output/navigation-decision-v1.sqlite \
  --expected-source-sha256 c03452621df17ad3d40472e3bd6634d5a33d8473130f229b02dea43f58dd0c9f \
  --output /home/kyle/exitguide/imports/yanggeon/20260802-navigation-db-redesign/manifests/db-validation-report.json
```

변환기는 기존 target 파일을 덮어쓰지 않는다. 재실행은 새 출력 경로를 사용해야 한다.

## 알려진 데이터 한계

- 멤버십 가입 Human Gold는 한 앱뿐이라 범용 근거로 사용할 수 없다.
- 멤버십 관리 목적은 명시적인 검증 사례가 아직 없다.
- 기존 좌표를 버리므로 위치 bucket과 부모·주변 의미를 모든 과거 사례에서 완전히 복원할 수 없다.
- VLM 관찰이 없는 과거 화면은 Accessibility/OCR만으로 표현된다.
- 실패 기록은 멤버십 해지에 편중돼 있다.

이 한계를 해결한다는 이유로 정적 데이터를 대량 생성하지 않는다. Agent 메커니즘과 오프라인 trajectory replay가 준비된 뒤 실제 실패 유형에 필요한 관찰만 추가한다.

## 런타임 전환 조건

이번 산출물은 격리 실험 DB다. 공유 `runtime/rag.env`, Terms 서비스, 기존 Navigation DB를 변경하지 않는다. 신규 DB를 런타임에 연결하려면 별도 검토에서 다음을 확인해야 한다.

1. DB schema version과 SHA-256 고정
2. 외부 행동 예시 색인·legacy route·Gold macro fallback 비활성화
3. K-EXAONE에 전달되는 evidence packet에서 앱 이름과 절대 좌표 제거
4. 현재 화면 후보 allowlist 검사
5. 위험한 최종 행동 `stop_for_user` 강제
6. 행동 후 새 관찰이 없으면 transition 성공을 기록하지 않음
7. 앱 분리 오프라인 trajectory 평가 통과
8. 사용자 승인 후 실기기 검증
