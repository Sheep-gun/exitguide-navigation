# Instagram membership.cancel 실기기 근거

- 앱: Instagram `com.instagram.android`
- 앱 버전: `441.0.0.43.81+384710428`
- 목표: `membership.cancel`
- Runtime 세션: `navs_e447611ae40e4f028cd02a18b2746a88`
- 보조 상태 근거: `navs_561dbfc760df4d84912ee67c91992ed6`
- 판정: `state_not_applicable`
- 차단 조건: `account_state`

독립 해지 세션에서 프로필 → 옵션 → 계정 센터 → 구독을 탐색했다. 프로필 상단의
`Threads에서 프로필 보기` 후보를 옵션으로 잘못 선택해 Google Play 외부 화면으로
이동한 실패를 기록했고, `back()`으로 Instagram 프로필에 복구했다. 이후 실제 옵션 후보를
선택해 동일 경로를 재개했다.

구독 화면에서 Meta Verified를 확인한 결과 활성 구독 관리가 아니라 `1개월 무료 이용하기`
가입 화면이었다. 별도 변경 세션에서 Instagram Plus도 신규 무료 체험 화면임을 확인했으므로
현재 두 상품 모두 해지 제어가 없는 비구독 상태다. 무료 체험 CTA는 `unsafe`로 검수하고
실행하지 않았다.

Review DB에서 9개 의사결정의 162개 후보를 전부 검수했다. 라벨 분포는 `best 7`,
`acceptable 5`, `hard_negative 145`, `unsafe 1`, `unknown 4`다. 외부 이동 1건과 복구
1건을 보존했고 연결 오류는 0건, 위험 행동 자동 실행은 0건이다. 수집기 코드는 변경하지
않았다.

