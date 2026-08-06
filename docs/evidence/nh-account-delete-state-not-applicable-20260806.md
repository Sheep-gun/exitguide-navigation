# NH농협손해보험 회원탈퇴 현재 계정 상태

검증 일시: 2026-08-06 19:13~19:15 KST

기기: Samsung SM-G998N, Android 15

앱: NH농협손해보험 `ni.mh.android.launcher`, `1.434+476`
목표: `account.delete`

## 실기기 경로

Runtime 세션: `navs_0b176df434394e6f9ef1b45a1d6112b3`

1. 서비스 안내 팝업 `닫기`: `navd_639e08e640b34fa9b2ca93c141487d5a`
2. 홈 `메뉴`: `navd_0e28cc08ad6b43adb7e3a0c46d1eb381`

전체 메뉴가 열리자 `로그인` 후보가 표시됐다. Navigation API는 행동 뒤 화면을
`login_required`로 판정하고 세션을 `safe_user_handoff`로 자동 종료했다. `latest-screen`의
session_id가 비어 보인 것은 기록 실패가 아니라 이 자동 종료 결과였으며 Runtime에는 두 행동,
실행 성공과 두 번의 화면 변화가 모두 저장됐다.

현재 로그아웃 상태에서는 회원탈퇴가 적용되지 않는다. 로그인이나 본인인증을 실행하지 않고
`state_not_applicable`로 확정했다.

## Review 결과

- decisions: 2 / 2 reviewed
- candidate labels: 82 / 82
- best: 2
- hard_negative: 72
- unknown: 8
- unsafe: 0

로그인, 본인인증, 회원탈퇴 또는 개인정보 제출 자동 실행은 0건이다.
