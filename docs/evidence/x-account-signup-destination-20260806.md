# X account.signup 목적지 실기기 근거

검증 일시: 2026-08-06 16:02–16:08 KST

## 판정

- goal_id: `account.signup`
- app: X `com.twitter.android` 12.12.0-release.0+312120000
- device: Samsung SM-G998N, Android 15
- preliminary session: `navs_2c2acccc7d9448188046e77f1bff7478`
- final session: `navs_b85b3a4af1704006b7fedef41da928d7`
- 결과: `destination_reached`

로그인된 피드에서 `탐색 서랍 보기`를 candidate_id로 실행했다. 첫 세션에서는 로그인
상태만 확인하고 너무 일찍 중단했다. Review에서 이 종료를 `wrong`으로 교정하고 계정 옵션을
더 조사했다.

두 번째 세션에서는 계정명과 합쳐진 `기타 옵션` 후보를 눌렀지만 자기 프로필로 이동했다.
이 후보를 `hard_negative`로 검수하고 `back()`으로 복구했다. 탐색 서랍을 다시 연 뒤 독립
`기타 옵션` 후보를 선택하자 다음 두 후보가 표시됐다.

- `새 계정 만들기` (`a11y_4be3da5e851eec44fe71`)
- `기존 계정 추가하기` (`a11y_0529aba24540e86fb9b9`)

`새 계정 만들기`를 account.signup의 `best`, `기존 계정 추가하기`를 다른 기능의
`hard_negative`로 검수했다. 개인정보 입력 흐름은 시작하지 않고 `stop_for_user()`로
종료했다.

## Runtime과 Review

- decisions: 8 (preliminary 2, final 6)
- complete before/after transitions: 8 / 8
- final-session candidate-ID clicks: 4 / 4 grounded and executed
- recovery actions: 1 / 1 successful
- Review decisions: 8 / 8
- before-screen candidates: 166
- verified candidate labels: 166 / 166
- labels: best 8, acceptable 2, hard_negative 154, unknown 2
- wrong actions: 2 (premature stop, profile wrong destination)
- source_read_only: true

## 안전성

- 새 계정 만들기 클릭: 0건
- 개인정보 입력: 0건
- 로그인 정보 입력: 0건
- 위험 행동 자동 실행: 0건
- 연결 오류: 0건

Runtime 원본은 수정하지 않았고 Review 라벨만 별도 Review DB에 저장했다.
