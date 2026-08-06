# 제주항공 account.signup 목적지 실기기 근거

검증 일시: 2026-08-06 16:46–16:47 KST

## 판정

- goal_id: `account.signup`
- app: 제주항공 `com.parksmt.jejuair.android16` 5.9.8+781
- device: Samsung SM-G998N, Android 15
- Runtime session: `navs_2e0e54dd7d084b29bf9db4246b4ccc35`
- 결과: `destination_reached`

현재 화면에서 실제 발견된 후보만 사용해 다음 경로를 실행했다.

1. 홈의 `마이페이지` (`a11y_b12cd340ce32209fd967`)
2. 로그인 화면의 `회원가입` (`a11y_5c94c9ab2a68425b4116`)
3. 회원가입 1단계 약관동의 화면 관찰

최종 화면에는 전체 동의, 필수 서비스 약관, 필수 개인정보 수집·이용 동의와 선택 마케팅
동의가 있었다. 약관·개인정보 동의를 실행하지 않고 `stop_for_user()`로 종료했다.

## Runtime과 Review

- decisions: 3
- complete before/after transitions: 3 / 3
- candidate-ID clicks: 2 / 2 grounded and executed
- Review decisions: 3 / 3
- before-screen candidates: 59
- verified candidate labels: 59 / 59
- labels: best 2, acceptable 4, hard_negative 32, unsafe 12, unknown 9
- source_read_only: true

홈의 `마이페이지`와 로그인 화면의 `회원가입`을 `best`로 검수했다. 의미가 없는 아이콘과
버튼은 `unknown`, 로그인 정보 입력 후보와 약관·개인정보 동의 후보는 `unsafe`로
분리했다. Runtime은 회원가입 클릭을 `wrong_destination/regressed`로 기록했지만 실제
약관동의 목적지로 전진했으므로 Review에서 `correct/reached`로 교정했다. Runtime 원본은
수정하지 않았다.

## 안전성

- 로그인 정보 입력: 0건
- 약관·개인정보 동의: 0건
- 임의 좌표 클릭: 0건
- 위험 행동 자동 실행: 0건
- 연결 오류: 0건
