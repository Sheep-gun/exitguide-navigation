# Instagram membership.change 실기기 근거

- 앱: Instagram `com.instagram.android`
- 앱 버전: `441.0.0.43.81+384710428`
- 목표: `membership.change`
- Runtime 세션: `navs_561dbfc760df4d84912ee67c91992ed6`
- 판정: `state_not_applicable`
- 차단 조건: `account_state`

프로필 → 옵션 → 계정 센터 → 구독 → Instagram Plus를 현재 화면의 `candidate_id`로
실행했다. 활성 플랜 관리·변경 제어 대신 신규 무료 체험과 월 요금만 표시돼 현재 계정은
Instagram Plus 비구독 상태로 판정했다. 계정 상태를 바꾸기 위한 가입은 실행하지 않았다.

Review DB에서 6개 의사결정의 103개 후보를 전부 검수했다. 라벨 분포는 `best 5`,
`acceptable 3`, `hard_negative 90`, `unsafe 1`, `unknown 4`다. 구독·결제·플랜 변경 실행은
0건이다.

