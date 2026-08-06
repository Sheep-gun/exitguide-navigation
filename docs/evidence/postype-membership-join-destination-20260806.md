# 포스타입 멤버십 가입 목적지 실기기 검증

검증 일시: 2026-08-06 18:56~18:59 KST  
기기: Samsung SM-G998N, Android 15  
앱: 포스타입 `com.postype.play`, `3.90.1+1564`  
목표: `membership.join`

## 실기기 경로

Runtime 세션: `navs_3c98efe467604f91a2f181217d5e42aa`

1. 광고 팝업 `닫기`: `navd_f76bacf3234741c48126858ae6e737df`
2. 홈 `마이메뉴`: `navd_78ddb7fdd3a6435cb08b4c5c01648f72`
3. 마이메뉴 `멤버십 가입`: `navd_31b9f72bb80d4c72b42e474eec953709`
4. 목적지 관찰 후 `stop_for_user`: `navd_a36d8f08205c48b3a9432715447fb503`

모든 클릭은 현재 화면에서 수집한 Accessibility candidate_id로 실행됐고 행동 뒤 실제 화면
전환을 관찰했다. 마지막 화면에는 다음 의미 특징이 함께 존재했다.

- 화면 제목 `멤버십 가입`
- 현재 플랜 `★영덕이 멤버십★`
- 가입 금액 `2,000원/월`
- `가입 내역`
- `가입 중인 멤버십`

이 조합을 멤버십 가입·현황 목적지로 판단했다. 현재 계정은 이미 한 멤버십에 가입 중이었다.
추가 플랜 선택, 결제 또는 구독 확정은 실행하지 않고 `stop_for_user`로 종료했다.

## Review 결과

- decisions: 4 / 4 reviewed
- candidate labels: 64 / 64
- best: 3
- acceptable: 1
- hard_negative: 42
- unknown: 18
- unsafe: 0

유료 플랜 선택, 결제 또는 구독 확정 자동 실행은 0건이다.
