# 11개 앱 골든 라벨 동결 및 표준 승격 감사

## 결론

현재 설치된 11개 앱의 55개 목표 셀은 Runtime 원료와 Review 골든 라벨로 동결했다.
원본 DB를 수정하지 않고 `interaction-episode.v1`과 Review 스냅샷을 생성했으며,
그 결과만으로 불변 App Knowledge 세대와 별도 staging Decision DB를 만들었다.

일반화 성능 개선은 아직 입증되지 않았다. 현재 11개 앱은 모두 collection에 사용됐기
때문에 동일 앱으로 활성화 승인을 내리지 않는다. 앞으로 처음 설치하는 미관측 앱으로
검증한 뒤에만 staging 세대의 운영 활성화를 검토한다.

## 원료 동결

- source commit: `6aaf94ffe2f918830d7c2eb4b5d2f38a0f73e9c0`
- snapshot: `training_snapshot_d983e65055f5427fdb8d3dbe`
- snapshot path: `/srv/exitguide/runtime/navigation-training-snapshots/training_snapshot_d983e65055f5427fdb8d3dbe`
- 앱 / 커버리지 셀: 11 / 55
- Runtime 세션 / Interaction Episode / 행동: 66 / 66 / 233
- Review 결정 / 후보 라벨: 233 / 4,213
- 후보 라벨 분포: best 154, acceptable 80, hard_negative 3,516, unsafe 93, unknown 370
- 제외된 과거 근거 세션: 6 (미검수, 후보 전체 라벨 누락 또는 observation 누락)
- 위험 행동 자동 실행: 0
- Runtime source access: read-only
- Review source access: read-only

원본 해시:

- Runtime coverage DB: `7af6bd7b765d79c1c0a14f415765f651878b578f89f2fd62b1538caf63ffc4ea`
- 보존 Runtime v1: `777aadde29ce42026c0ceabe707d03a203245fdbb7a8a23bbe066cefa0ad87c6`
- 보존 TVING Runtime: `489cf2240a9e0e67b72fe74fe52db89e4eda8f1d134e5277cbea19d008b28bc6`
- Review DB: `8ad8e3687188a4b340817f5e9fa6489b6baf2175245d23d3172afb48097a4c3a`
- Interaction Episode: `62fba5717294fe3ee0b08cd0dea0bf9d3fb2389e6c49db3b60251b6986e7f7cc`
- Review snapshot: `85312d285549af3adc519772f992f7c56529c71e859b3752aa8a44508d856680`

## Review 절대 지표

이 수치는 collection 원료의 검수 품질 지표이며, 미관측 앱 일반화 지표가 아니다.

- 전체 행동 판단 correct 또는 acceptable: 223 / 233 (95.7%)
- 세션 첫 행동 correct 또는 acceptable: 64 / 66 (97.0%)
- wrong 행동: 10 / 233 (4.3%)
- 진행 판단: advanced 143, reached 71, unchanged 14, regressed 4, unknown 1
- 모든 후보 inventory 검수: 4,213 / 4,213
- 위험 후보 자동 실행: 0

## 승격 결과

표준 경로:

`Runtime → interaction-episode.v1 → Review → knowledge-promotion.v1 → source consistency replay → App Knowledge generation → staging Decision DB`

- promotion candidates: 127
- draft 보존: 123
- accepted: 4
- generation: `generation_1a106b2e1925d28eaa56b973`
- generation path: `/srv/exitguide/runtime/navigation-app-knowledge-generations/training_snapshot_d983e65055f5427fdb8d3dbe/generation_1a106b2e1925d28eaa56b973`
- accepted units:
  - Netflix `account.delete`: 문맥이 다른 하향 스크롤 2건
  - 제주항공 `membership.join`: `마이페이지` 진입 2건
  - X `account.signup`: 탐색 서랍 진입 2건
  - NH농협손해보험 `membership.change`: 인증 전 팝업 닫기 2건

동일 before/after fingerprint를 가진 재실행은 독립 support로 계산하지 않는다. 이 규칙으로
Netflix 동일 화면 클릭 4종과 배달의민족 동일 스크롤 재실행이 자동 승인에서 제외됐다.
재실행 기록은 검증 provenance로 보존되지만 일반화 다양성으로 간주하지 않는다.

배달의민족의 실제 packageName은 `com.sampleapp`이다. 실기기 package metadata의
version `16.16.0`, `split_baemincall.apk`, `com.baemin...RootContainerActivity`로 확인했으므로
테스트 앱 오염이 아니다.

## staging 투영

- base Decision DB SHA-256: `3891d4cc4d44b10d5363e0134937eab215663f115cb0809d9e232bead82fd9c1`
- staging Decision DB: `/srv/exitguide/runtime/navigation-decision-staging/training_snapshot_d983e65055f5427fdb8d3dbe.sqlite`
- staging SHA-256: `0e81685ac3836ceb5cb6058f4d15ac9b223ea28ce3f722f574f87746a6848f30`
- Decision cases: 88 → 96
- SQLite quick_check: ok
- foreign key errors: 0
- projection 중 Runtime 접근: false
- 운영 Decision DB 변경: 없음

## 재수집 판단

오래된 승격 결과의 문제는 원료 전체의 폐기가 아니라 표준 계층 우회와 중복 support 계산이었다.
검수되지 않은 과거 세션 6개는 제외했고, 현재 55셀에는 완전 검수된 대체 근거가 있으므로 즉시
재수집할 셀은 없다.

다만 `state_not_applicable` 또는 `not_testable`을 실제 경로 근거로 강화하려면 사용자가
로그아웃·미구독·활성 구독 등 필요한 계정 상태를 준비한 뒤 새 Runtime/Review 세대로 다시
수집할 수 있다. 기존 스냅샷과 판정은 덮어쓰지 않는다.

## 활성화 게이트

현재 generation과 staging DB는 운영에 활성화하지 않는다. 다음 조건이 필요하다.

1. 현재 11개와 겹치지 않는 새 앱을 validation으로 지정한다.
2. 기존 운영 DB와 staging DB를 동일한 고정 validation 사례로 평가한다.
3. 위험 행동 자동 실행 0건을 유지한다.
4. 정확도·복구·행동 수가 비열화되지 않았음을 확인한다.
5. 통과한 경우에만 원자적 활성화하고, 실패하면 staging을 폐기하지 않고 원인 분석 자료로 보존한다.

