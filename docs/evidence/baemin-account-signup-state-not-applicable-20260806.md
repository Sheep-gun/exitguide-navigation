# 배달의민족 account.signup 현재 계정 상태 실기기 근거

검증 일시: 2026-08-06 15:50–15:51 KST

## 판정

- goal_id: `account.signup`
- app: 배달의민족 `com.sampleapp` 16.16.0+26001143
- device: Samsung SM-G998N, Android 15
- Runtime session: `navs_b4d7f60df1fc4a2cbf649b7fe39757cc`
- 결과: `state_not_applicable`
- blocking_issue: `account_state`

배민 홈에서 현재 화면 후보 `하단탭바 마이배민탭`
(`a11y_32dc4ed0a0559e54efe8`)을 candidate_id로 실행했다. 행동은 Accessibility
action으로 성공했고 화면 지문이 바뀌었다. 도착한 마이배민 화면에서 개인화된 계정명과
쿠폰·포인트가 표시돼 현재 계정이 로그인 상태임을 직접 확인했다.

회원가입 화면을 보기 위해 로그아웃하거나 계정 상태를 변경하지 않았다. 현재 상태에서는
회원가입 검증이 적용되지 않으므로 `stop_for_user()`로 종료했다.

## Runtime과 Review

- decisions: 2
- complete before/after transitions: 2 / 2
- candidate-ID click: 1 / 1 grounded and executed
- screen change after click: true
- Review decisions: 2 / 2
- before-screen candidates: 58
- verified candidate labels: 58 / 58
- label distribution: best 1, hard_negative 56, unknown 1
- source_read_only: true

첫 화면에서는 마이배민 탭을 `best`로 검수했다. 개인화된 마이배민 화면에서는 계정 상태를
이미 확인했으므로 후보를 추가로 누르지 않았다. 빈 의미 후보 1개는 `unknown`, 나머지는
현재 회원가입 목표와 무관한 `hard_negative`로 검수했다. Runtime의 중간·종료 판정은
각각 `unknown`과 `blocked`였으므로 Review DB에서 실제 결과를 `advanced`와 `reached`로
교정했다.

## 안전성

- 로그아웃: 0건
- 계정 상태 변경: 0건
- 로그인 정보 입력: 0건
- 위험 행동 자동 실행: 0건
- 연결 오류: 0건

Runtime 원본은 수정하지 않았고 Review 라벨만 별도 Review DB에 저장했다.
