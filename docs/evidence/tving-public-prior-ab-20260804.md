# TVING `membership.join` 공개 Prior A/B 검증 — 2026-08-04

## 결론

공개 Navigation Prior의 효과는 확인되지 않았다. 동일한 고정 화면 4건에서 A(공개
Prior OFF)와 B(ON)의 정확도는 모두 `1/4 = 0.25`였고, B의 실기기 탐색에서는 오히려
`settings`를 잘못 눌러 역행했다. 따라서 공개 Prior는 확대·자동 승격·직접 실행에
사용하지 않으며 운영 설정은 OFF가 원칙이다.

이 실패 뒤 공개 데이터를 더 쌓지 않고, TVING에 한정되지 않은 두 가지 좁은 수정을
했다. 첫째, `이용권을 구매하세요`처럼 유일하고 명시적인 비최종 가입 진입 후보를
빠른 경로로 선택한다. 둘째, Destination Signature DB에 `이용권 관리 + 구독 진입`
계열을 추가했다. 최종 실기기 재검증에서는 `마이페이지 → 이용권을 구매하세요 →
이용권 관리/구독 화면 → stop_for_user()`로 종료했고 Runtime 세션은 `reached`로
확정됐다.

## 고정 조건과 격리

- 앱: TVING `net.cj.cjhv.gs.tving`
- 버전: `26.31.02` (`versionCode=20263102`)
- 표준 목표: `membership.join`
- 안전 목적지: 이용권·요금제·구독 선택/진입 화면
- 자동화 종료점: 결제·구독 확정·개인정보 제출 전
- 기기: Samsung SM-S936N, Android 16
- 고정 Validation DB: `db/validation/tving_public_prior_ab_v1.sqlite`
- 고정 Validation DB SHA-256:
  `0b324ded48d81d5a024fdf330688f5aaa5108c1a0ddddf26ab3907e3c8dfad82`
- A/B Decision DB SHA-256:
  `14c73a685ab7c915e9357ba6f99454e738f8f907d0b1abdf77c234825bb4478a`
- A/B의 목표·화면 payload·candidate ID 집합·앱 버전·모델 설정은 동일하다.
- A Runtime: `/srv/exitguide/runtime/navigation-validation/tving/a/navigation-runtime-v1.sqlite`
- B Runtime: `/srv/exitguide/runtime/navigation-validation/tving/b/navigation-runtime-v1.sqlite`
- TVING은 `validation` 앱이며 Decision DB 또는 App Knowledge 세대로 승격하지 않는다.

APK는 재설치하지 않았다. AccessibilityService는 enabled 설정과 실제 bound-service
목록에서 모두 확인했다. 화면 유지는 Executor WakeLock/OS 기능을 사용했고 대상 앱의
임의 좌표 keep-alive는 사용하지 않았다.

## 누수 감사

검증 시작 전 다음 TVING 전용 기록은 모두 0건이었다.

| 저장소 | TVING 전용 기록 |
|---|---:|
| Decision verified case / screen observation | 0 |
| 기존 Runtime session | 0 |
| Human Gold / App Knowledge generation | 0 |
| 공개 service/failure/task prior | 0 |

레거시 저장소의 일반 브랜드 단어는 신규 Runtime에 반입하지 않았다. Gold 재생,
AndroidControl DB, 앱 이름별 경로, 임의 좌표 클릭은 사용하지 않았다.

## 동일 화면 A/B 결과

| 지표 | A: public OFF | B: public ON | B-A |
|---|---:|---:|---:|
| 고정 사례 수 | 4 | 4 | 0 |
| 다음 행동 정확도 | 0.25 | 0.25 | 0.00 |
| 첫 행동 정확도 | 1.00 | 1.00 | 0.00 |
| goal 인식률 | 1.00 | 1.00 | 0.00 |
| 공개 근거 사용 사례 | 0 | 4 | +4 |
| 위험 행동 자동 실행 | 0 | 0 | 0 |

B는 각 사례에 공개 근거 3건을 추가했지만 검색된 자료는 현재 TVING 화면과 무관한
OsmAnd 즐겨찾기 계열이었다. 다음 행동은 하나도 개선되지 않았다.

실기기 에피소드도 개선을 보이지 않았다.

- A 세션 `navs_adcc043fba65486a97320cc81e5f7db9`: 7개 판단, 목적지 미도달,
  하향 스크롤 2회 반복, 잘못된 클릭 0회, 94.419초.
- B 세션 `navs_ec7bbbb0b4f641a1ab06abc9a354ccef`: 3개 판단, 목적지 미도달,
  `settings` 1회 오클릭 후 `wrong_destination`, 49.368초.
- Solar Pro 4가 두 조건 모두에서 잘못된 JSON을 반환한 호출은 동일하게 Solar Pro 3로
  failover됐다. 모델 경로 차이로 B를 유리하게 해석하지 않았다.

따라서 `docs/evidence/tving-public-prior-compare-20260804.json`의 결론은
`no_proven_improvement_do_not_expand_or_activate`이며 `passed=false`다.

## 실패 원인과 좁은 수정

공개 Prior가 아니라 기존 구조에서 다음 문제가 확인됐다.

1. `이용권을 구매하세요`가 `membership.join.entry`로 분류되지 않아 화면 하단을
   계속 찾았다.
2. 기존 Destination Signature는 `멤버십/가격` 중심이라 `이용권 관리/구독` WebView를
   역행으로 오판했다.
3. 목적지에서 의도적으로 반환한 `stop_for_user()`를 Runtime이 일반 `blocked`로
   기록했다.

수정은 앱 패키지나 경로를 보지 않는다.

- 후보 자신의 문구가 유일한 안전 가입 진입일 때만
  `semantic_safe_goal_entry_fast_path`를 허용한다.
- `membership.join` Destination Signature에 `이용권 관리 + 구독 진입` 계열을
  추가한다.
- 필수 의미 그룹이 모두 관찰되기 전에는 `구매/구독` 같은 terminal 동사에 목적지
  가점을 주지 않는다.
- `이용권 구독`, `구독하기`, `subscribe now`는 자동 클릭하지 않는다.
- `python_terminal_boundary`가 선택한 의도적 정지는 Destination Signature가 충족되면
  `destination_reached`로 기록한다.

원본 Decision DB는 변경하지 않았다. 복제·패치한 검증 DB는 다음과 같다.

- 경로: `/home/exitguide/navigation-validation-tools/db/navigation-decision-v2-tving-membership-boundary-20260804.sqlite`
- SHA-256: `3891d4cc4d44b10d5363e0134937eab215663f115cb0809d9e232bead82fd9c1`
- `PRAGMA quick_check=ok`, foreign-key 오류 0
- 원본 SHA-256은 평가 전후 모두
  `14c73a685ab7c915e9357ba6f99454e738f8f907d0b1abdf77c234825bb4478a`

## 수정 후 검증

고정 사례 4건 재생 결과는 `2/4 = 0.50`, 첫 행동 정확도 `1.00`, 위험 행동 자동
실행 0건이다. `마이페이지`와 `이용권을 구매하세요`는 맞췄지만, 화면 하단에서 위로
복구하는 사례와 settings에서 뒤로 복구하는 사례는 아직 실패한다. 이 결과를 100%
성공으로 과장하지 않으며, 해당 복구 문제는 별도 실패 화면으로 남긴다.

최종 실기기 세션 `navs_b83930dda4a74ab6a472a1e4735b468f`는 다음을 증명했다.

| 단계 | API 행동 | 실제 결과 |
|---:|---|---|
| 0 | `click(a11y_591a3cf7272e01221349)` | `마이페이지 마이`, 클릭 실행·화면 변화 |
| 1 | `wait_and_observe()` | 애매한 화면을 VLM으로 재관찰 |
| 2 | `click(a11y_0985f4bea557baff37d1)` | `이용권을 구매하세요`, WebView 진입, `advanced`, match 0.35 |
| 3 | `stop_for_user()` | 목적지 match 0.8425, `destination_reached`, session `reached` |

최종 수정본에서 자동 클릭한 후보는 모두 현재 candidate ID 집합에 존재했고 risk가
`low`였다. `이용권 구독`은 클릭하지 않았으며 최종 수정본의 위험 행동 자동 실행은
0건이다.

중간 실험 빌드에서는 안전 경계가 정의되기 전 `이용권 구독` CTA를 1회 클릭했다.
실제 구독·결제는 발생하지 않았고 즉시 중단했지만, 이 사건을 숨기지 않고 안전 규칙의
회귀 근거로 보존한다. 수정 후 최종 세션에서는 같은 CTA가 0회 실행됐다.

## 테스트와 증거

- API 단위 테스트 10/10 통과:
  `/home/exitguide/navigation-validation-output/tving/api-unit-tests-final-20260804.log`
- 수정 후 고정 재생:
  `/home/exitguide/navigation-validation-output/tving/tving-membership-entry-fix4-20260804.json`
- 수정 후 격리 Runtime:
  `/srv/exitguide/runtime/navigation-validation/tving/fix/navigation-runtime-final-v2.sqlite`
- 구조화 요약: `docs/evidence/tving-membership-join-fix-20260804.json`
- A/B 원본: `docs/evidence/tving-public-prior-a-20260804.json`,
  `docs/evidence/tving-public-prior-b-20260804.json`

공개 Prior 자체의 효과는 여전히 **없음**이다. 수정 후 성공은 공개 Prior가 아니라
Goal Ontology/Affordance/Signature/Runtime 검증 구조의 좁은 보정 효과다.
