# B 고정 이전 커버리지 재검증 대장

## 원칙

공개 Navigation DB가 항상 활성화된 B를 최종 구조로 고정하기 전에 A 런타임으로 얻은
판정은 원본 Runtime과 문서에서 삭제하지 않는다. 다만 B 절대 성능의 완료 근거로도 세지
않는다. 해당 셀을 `in_progress`로 되돌린 뒤 동일 목표를 B로 다시 실행한다.

A 결과를 B의 기준선이나 정답 경로로 재생하지 않는다. 재검증은 현재 Accessibility 후보,
Decision DB, 공개 Navigation DB, 필요 시 Solar/VLM을 사용하는 정상 B 탐색으로 수행한다.

## 재검증 대상

| 앱 | 목표 | 기존 판정 | 기존 Runtime | 현재 처리 |
|---|---|---|---|---|
| YouTube | `membership.join` | 이미 Premium이라 `not_testable` | `navs_4add085e43b54c808ad3f70b76a9f50d` | `in_progress`, B 재검증 대기 |
| 제주항공 | `membership.join` | J 멤버스 가입 안내 `destination_reached` | `navs_a22e45b9ba144c58b56e08707c0149f9` | `in_progress`, B 재검증 대기 |
| 쿠팡 | `membership.join` | WOW 이용 중이라 `not_testable` | `navs_5e1847b33ae8486eb7b7c202a47bebcd` | `in_progress`, B 재검증 대기 |

세 기록은 모두 2026-08-03 수집분이다. 이후 B 고정 상태에서 실기기 근거가 생성된 YouTube
회원가입·회원탈퇴·멤버십 변경·해지, Netflix 멤버십 해지, TVING 멤버십 가입 결과는 이
대상에 포함하지 않는다.

## 재검증 완료 조건

각 셀은 다음을 새 B 세션으로 증명한 뒤에만 최종 상태로 복원한다.

1. N100 상태에서 `public_prior.enabled=true`
2. 현재 화면의 candidate_id만 사용
3. 행동 실행과 행동 후 화면 변화 분리 기록
4. 연결 오류를 탐색 실패로 처리하지 않음
5. 위험 행동 자동 실행 0건
6. collection 경험은 표준 episode·promotion 파이프라인만 사용

기존 A 기록은 비교·진단 자료로만 보존하며 B 재검증의 검색 또는 자동 경로 재생 데이터로
승격하지 않는다.
