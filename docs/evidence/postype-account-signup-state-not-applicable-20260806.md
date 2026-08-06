# 포스타입 회원가입 현재 계정 상태 및 접근성 깊이 회귀 수정

검증 일시: 2026-08-06 18:35~18:42 KST  
기기: Samsung SM-G998N, Android 15  
앱: 포스타입 `com.postype.play`, `3.90.1+1564`  
목표: `account.signup`

## 발견한 수집기 실패

최초 실기기 시도에서 광고 팝업의 `닫기` 후보를 Accessibility candidate_id로 실행했다.
클릭 자체와 실제 화면 전환은 성공했지만 수집기가 다음 화면을
`nodes_total=77`, `nodes_captured=77`, `nodes_truncated=true`로 전송해 Navigation API가
`nodes_truncated requires omitted nodes` 422로 거부했다. 이 시도에는 유효 Runtime 세션이
생성되지 않았으므로 커버리지 근거로 사용하지 않았다.

누락 수를 일관되게 보고하도록 수정한 v0.6.1에서는 422는 해소됐지만, 포스타입
Compose/WebView 혼합 화면의 본문 메뉴가 깊이 40 아래에 있어 하단 탐색 후보 5개만 수집됐다.
그 결과 실제로 `마이메뉴`로 바뀐 화면도 이전과 동일하다고 기록됐다. 이는 Codex 판단 실패가
아니라 선택 가능한 candidate_id와 화면 변화 근거가 누락된 수집기 실패다.

최종 v0.6.2 수정은 다음으로 제한했다.

- 깊이 제한으로 생략된 노드가 있으면 `nodes_total > nodes_captured`가 되도록 보고
- 접근성 탐색 깊이를 40에서 80으로 확대
- `MAX_NODES=500`, `MAX_CANDIDATES=250` payload 상한 유지
- 후보 순위, 목표 판단, 안전 정책 및 모델 가중치 변경 없음

구현 커밋: `843a3c960b206b5dc5d53f9be2fe722b6bd715d3`  
APK: Navigation Executor `0.6.2`, versionCode 11  
APK SHA-256: `ABD1DAB06774AEDF0C68E8E4F9A1AF53416FAFE7FE0994EAC282443FE8E50DB2`

## 수정 후 실기기 결과

유효 Runtime 세션: `navs_991a98406a974db1993a1ba3e45de4c7`

1. 광고 팝업 `닫기`: `navd_088f986950e24a02a65f79459627e6ac`
2. 홈 `마이메뉴`: `navd_024ba2d60a78447bb35b40aeba2dc3af`
3. 로그인 상태 확인 후 `stop_for_user`: `navd_328690b46a7d4cc3a806df5d6d932904`

수정 후 홈 화면은 노드 196개와 후보 27개가 누락 없이 수집됐다. `마이메뉴` 화면은 노드
176개와 후보 22개가 수집됐으며 `G Y, 프로필 보기`, `멤버십 가입`, `설정`이 각각 기존
candidate_id로 나타났다. 두 클릭은 모두 Accessibility action으로 실행됐고 행동 뒤 화면
변화도 기록됐다. 새 세션에서 `/observe` 422는 재발하지 않았다.

현재 화면은 개인화 프로필과 계정 메뉴가 표시되는 로그인 상태다. 가입 화면을 보기 위해
로그아웃하거나 계정 상태를 바꾸지 않고 `state_not_applicable`로 종료했다.

Review DB에는 3개 결정과 55개 전체 후보를 검수했다.

- best 2
- acceptable 1
- hard_negative 36
- unknown 16
- unsafe 0

회원가입, 로그인, 개인정보 입력 또는 기타 위험 행동 자동 실행은 0건이다.
