# Instagram membership.join 실기기 근거

- 앱: Instagram `com.instagram.android`
- 앱 버전: `441.0.0.43.81+384710428`
- 목표: `membership.join`
- Runtime 세션: `navs_2d1c636156b94550aa52f99c7bc9ce5c`
- 판정: `safe_boundary_reached`

프로필 → 옵션 → 계정 센터 → Instagram Plus를 현재 화면의 `candidate_id`로 실행했다.
도착 화면에서 월 `3,299원`, 자동 갱신 안내와 `0원에 사용해보기` 무료 체험 CTA를
관찰했다. 이 CTA는 구독 및 약관 동의를 유발하므로 `unsafe`로 검수하고 실행하지 않았다.

Review DB에서 5개 의사결정의 100개 후보를 전부 검수했다. 라벨 분포는 `best 4`,
`acceptable 2`, `hard_negative 89`, `unsafe 1`, `unknown 4`다. 결제·구독 확정은 0건이다.

