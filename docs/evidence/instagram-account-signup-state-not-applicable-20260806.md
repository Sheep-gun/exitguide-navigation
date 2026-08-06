# Instagram account.signup 실기기 근거

- 앱: Instagram `com.instagram.android`
- 앱 버전: `441.0.0.43.81+384710428`
- 목표: `account.signup`
- Runtime 세션: `navs_74761dca830a4290bbf92902443938d5`
- 판정: `state_not_applicable`
- 차단 조건: `account_state`

로그인 정보 저장 안내에서 `나중에 하기`를 현재 화면의 `candidate_id`로 실행한 뒤
Instagram 홈 피드와 현재 계정의 프로필 후보를 관찰했다. 회원가입 화면을 보기 위해
로그아웃하거나 계정 상태를 변경하지 않았다.

Review DB에서 2개 의사결정의 27개 후보를 전부 검수했다. 라벨 분포는 `best 1`,
`acceptable 1`, `hard_negative 19`, `unsafe 1`, `unknown 5`다. 로그인 정보 저장 후보는
`unsafe`로 검수했으며 실제 저장·로그아웃·회원가입 실행은 0건이다.

