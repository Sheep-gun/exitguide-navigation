# ChatGPT account.signup 실기기 근거

- 앱: ChatGPT `com.openai.chatgpt`
- 앱 버전: `1.2026.209+2620919`
- 목표: `account.signup`
- Runtime 세션: `navs_4fd7e143eb6a4cf1beeea0a77e2fea0a`
- 판정: `state_not_applicable`
- 차단 조건: `account_state`

ChatGPT 홈에서 플랜 업그레이드, 임시 채팅, 메뉴, 대화 입력 등 로그인 후 기능을 실제
관찰했다. 회원가입 화면을 보기 위해 로그아웃하거나 계정 상태를 바꾸지 않았다.

초기 `stop_for_user()` 뒤 `latest-screen.json`의 세션 바인딩을 확인하기 위해
`wait_and_observe()`를 한 번 수행했다. 이 진단 관찰은 성공 경로로 승격하지 않는다.
Review DB에서 2개 의사결정의 16개 후보를 전부 검수했고 모두 현재 회원가입 목표의
`hard_negative`다. 연결 오류와 회원가입 실행은 0건이다.

