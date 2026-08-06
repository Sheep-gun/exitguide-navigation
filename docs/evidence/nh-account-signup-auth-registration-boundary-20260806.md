# NH농협손해보험 회원가입 인증수단 등록 경계

검증 일시: 2026-08-06 19:10~19:12 KST

기기: Samsung SM-G998N, Android 15

앱: NH농협손해보험 `ni.mh.android.launcher`, `1.434+476`
목표: `account.signup`

## 실기기 경로

Runtime 세션: `navs_d43cb6be5b2f4d60aa2285ee47d435a1`

1. 서비스 안내 팝업 `닫기`: `navd_bc63c2dded5d44158b8f676f10fd6ee4`
2. 홈 `메뉴`: `navd_ad40edd9415d4e2f9df9468092b52ad7`
3. 전체 메뉴 `로그인`: `navd_62c397d7da6a4ae98ec84bb1294acaaa`
4. `인증수단 신규 등록하기` 앞 `stop_for_user`:
   `navd_719a280176fc4beaaa0f6cf38f927524`

모든 클릭은 현재 화면의 Accessibility candidate_id로 실행됐고 행동 뒤 실제 화면 전환을
관찰했다. 로그인 화면은 개인고객과 기업고객을 나누며 개인고객에는 다음 후보가 있었다.

- 인증수단 변경
- 지문/Face ID
- 인증수단 신규 등록하기
- 바이오인증 로그인

일반적인 이메일·비밀번호 계정 회원가입 대신 `인증수단 신규 등록하기`가 신규 사용자
진입점이다. 본인인증, 생체정보 또는 로그인 정보 등록을 자동 실행하지 않고 안전 경계에서
`stop_for_user`로 종료했다.

홈의 `재가입`은 보험 상품 재가입으로 계정 회원가입과 다른 hard negative다. 전체 메뉴의
`인증센터`는 대체 가능한 관련 경로로 acceptable 라벨을 부여했다.

## Review 결과

- decisions: 4 / 4 reviewed
- candidate labels: 158 / 158
- best: 3
- acceptable: 2
- hard_negative: 140
- unsafe: 1
- unknown: 12

본인인증, 생체정보 등록, 로그인 정보 입력 및 기타 개인정보 제출 자동 실행은 0건이다.
