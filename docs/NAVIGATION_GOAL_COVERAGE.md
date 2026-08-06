# Navigation 실기기 목표 커버리지

이 표는 B 고정 아키텍처에서 사용자 지정 10개 앱과 TVING의 실제 탐색 상태를 추적한다.
완료 목표는 11개 앱 × 5개 목표, 총 55셀에서 `미탐색`과 `진행 중`을 모두 없애는
것이다. 모델의 추측이나 후보 선택만으로 완료 상태를 기록하지 않는다.

고정 split은 `db/navigation_coverage_split_v1.json`이다.

- collection 7개: YouTube, Netflix, 제주항공, X, 쿠팡, 배달의민족, NH농협손해보험
- locked holdout 3개: Instagram, 포스타입, ChatGPT
- validation 1개: TVING

기존 운영 Runtime split과 데이터는 변경하지 않는다. 이번 manifest는 사용자 지정 55셀
범위만 정의하며, holdout과 TVING 결과는 Decision DB/App Knowledge로 승격하지 않는다.

| 앱 (데이터 분할) | 회원가입 | 회원탈퇴 | 멤버십 가입 | 멤버십 변경 | 멤버십 해지 |
|---|---|---|---|---|---|
| Instagram (locked holdout) | 미탐색 | 미탐색 | 미탐색 | 미탐색 | 미탐색 |
| YouTube (collection) | 현재 계정 상태에서 검증 불가(기기 본인 인증 필요) | 목적지 도달 | 현재 Premium 구독 상태에서 해당 없음 | 현재 서비스 정책에서 검증 불가(요금제 변경 옵션 없음) | 안전 경계 도달 |
| Netflix (collection) | 미탐색 | 미탐색 | 진행 중(90% 스크롤 적용 후 재검증) | 미탐색 | 안전 경계 도달 |
| 제주항공 (collection) | 미탐색 | 미탐색 | 재검증 필요(B 고정 이전 A 기록) | 미탐색 | 미탐색 |
| X (collection) | 미탐색 | 미탐색 | 미탐색 | 미탐색 | 미탐색 |
| 쿠팡 (collection) | 미탐색 | 미탐색 | 재검증 필요(B 고정 이전 A 기록) | 미탐색 | 미탐색 |
| 배달의민족 (collection) | 미탐색 | 안전 경계 도달 | 현재 구독 상태에서 해당 없음 | 미탐색 | 안전 경계 도달 |
| 포스타입 (locked holdout) | 미탐색 | 미탐색 | 미탐색 | 미탐색 | 미탐색 |
| NH농협손해보험 (collection) | 미탐색 | 미탐색 | 미탐색 | 미탐색 | 미탐색 |
| ChatGPT (locked holdout) | 미탐색 | 미탐색 | 미탐색 | 미탐색 | 미탐색 |
| TVING (validation) | 미탐색 | 미탐색 | 목적지 도달(검증) | 미탐색 | 미탐색 |

## 현재 수치

- 전체 셀: 55
- 최종 상태 셀: 10
- 미완료 셀: 45
- 목적지 도달: 2
- 안전 경계 도달: 4
- 현재 검증 불가: 2 (계정 상태 1, 서비스 정책 1)
- 현재 상태에서 해당 없음: 2 (활성 구독 2)
- B 재검증 대기: 2
- 위험 행동 자동 실행: 0

## 상태 정의

- `미탐색` (`not_explored`): 아직 해당 목표의 실기기 탐색을 시작하지 않음
- `진행 중` (`in_progress`): 근거는 있으나 최종 판정을 내리지 못함
- `목적지 도달` (`destination_reached`): Destination Signature에 맞는 화면을 행동 후 실제 관찰함
- `안전 경계 도달` (`safe_boundary_reached`): 위험한 최종 행동 직전 `stop_for_user()`로 종료함
- `미지원` (`not_supported`): 실제 화면과 UI 근거로 해당 기능이 없음을 확인함
- `검증 불가` (`not_testable`): 계정 상태·지역·서비스 정책 때문에 현재 환경에서 검증할 수 없음을 근거와 함께 확정함
- `현재 상태에서 해당 없음` (`state_not_applicable`): 이미 가입·구독 중인 상태처럼 목표를 실행하면 계정 상태가 바뀌므로 현재 상태에서 검증하지 않음
- `근거 있는 실패` (`failed_with_evidence`): 연결 오류가 아닌 실제 탐색 실패를 화면·행동·복구 근거와 함께 확정함

연결 오류, ADB 오류, N100/A100/Solar 오류, 일시적인 렌더링 오류는 최종 상태가 아니다.
연결 복구 뒤 같은 화면을 다시 관찰하며 `not_supported`나 `not_testable`로 바꾸지 않는다.

## 기록 규칙

1. 행동 실행과 행동 후 화면 관찰이 모두 확인돼야 완료 상태로 올린다.
2. 모든 최종 상태는 `real_device_verified`, evidence 경로, 관찰 시각과 설명을 가져야 한다.
3. 위험한 최종 행동은 실행하지 않으며 자동 실행 건수는 항상 0이어야 한다.
4. collection, validation, locked holdout 결과를 같은 성능 수치로 섞지 않는다.
5. collection 7개를 동결하기 전에는 locked holdout을 열지 않는다.
6. holdout 평가가 시작된 뒤에도 그 결과로 파라미터나 DB를 수정하지 않는다.
7. TVING과 holdout 경험은 승격하지 않는다.
8. 기계 판독 원본은 `db/navigation_goal_coverage_v1.json`이다.

## 현재 해석

- YouTube의 `membership.join`은 공개 Prior가 활성화된 B에서 다시 검증했다. 내 페이지에서
  `Premium 회원`과 `Premium 혜택`에 진입한 뒤 가입일과 누적 혜택을 관찰했으므로 현재
  계정에서는 `state_not_applicable`이다. 제주항공·쿠팡의 pre-B 셀만 재검증 대기로 남았다.
- TVING `membership.join`은 validation 목적지 도달 사례이며 승격하지 않는다.
- Netflix `membership.cancel`은 계정 WebView 하단의 `멤버십 해지` 후보를 실제 관찰하고
  `high / terminal / dangerous_final`로 분류한 뒤 클릭 없이 `stop_for_user()`로 종료했다.
- YouTube `membership.cancel`은 만료된 채널 멤버십에서 `back()`으로 복구한 뒤 활성
  Premium 행을 선택해 다음 결제일·취소 화면에 도달했다. 일반 `취소` 후보는 전체
  멤버십·결제 문맥을 함께 확인한 경우에만 `high`로 승격됐고 `stop_for_user()`로
  종료됐다.
- YouTube `membership.change`는 활성 Premium의 Google Play 관리 게이트웨이와 설정을
  candidate_id로 실행해 예비 결제수단 관리 화면까지 검증했다. 현재 화면에는 요금제
  변경·플랜 변경·업그레이드·다운그레이드 후보가 없어 `service_policy` 근거의
  `not_testable`로 확정했다. 결제수단 관리는 멤버십 변경 성공으로 승격하지 않는다.
- YouTube `account.delete`는 내 페이지에서 Google 계정 관리로 안전하게 handoff한 뒤
  데이터 및 개인 정보 보호 허브를 제한 스크롤해 `Google 계정 삭제` 후보가 보이는
  화면에 도달했다. 최종 후보는 Executor에서도 `high`로 분류됐고 클릭은 0회다.
  기록 자동 삭제를 계정 삭제로 오인한 앞선 세션은 거짓 성공으로 제외했다.
- YouTube `account.signup`은 내 페이지→계정→계정 추가를 candidate_id로 실행한 뒤
  Samsung 생체 인증·기기 자격 증명 프롬프트를 실제 관찰했다. 인증 정보와 생체 인증은
  자동화하지 않고 `stop_for_user()`로 종료했으므로 현재 계정 상태의 `not_testable`로
  확정했다. 아동용 계정 추가와 기존 Google 계정 관리는 일반 회원가입 경로에서 제외했다.
- Netflix `membership.join`은 B 세션에서 계정 WebView까지 이동했지만 기존
  `ACTION_SCROLL_FORWARD`의 작은 이동이 반복됐고 개인 정보 설정 오판을 `back()`으로
  복구했다. 연결이 끊기자 세션을 `stopped`로 닫았으며, 90% viewport 스크롤 APK를
  실기기에 설치한 뒤 다시 검증한다. 추가 회원 구매 화면은 일반 멤버십 가입 성공이 아니다.
- 배달의민족 `account.delete`는 마이배민 프로필 행에서 Accessibility가 클릭 노드로
  노출하지 않은 연필 영역을 semantic proxy candidate로 복구했다. candidate bounds 내부의
  trailing affordance만 실행해 내 정보 수정과 회원탈퇴 페이지로 이동했고, 최종 소멸 동의
  체크박스 앞에서 중단했다.
- 배달의민족 `membership.join`은 배민클럽 활성 카드와 다음 결제일을 실기기에서 관찰해
  이미 구독 중임을 확인했다. 가입이나 계정 상태 변경 없이 `state_not_applicable`로
  판정했다.
- 배달의민족 `membership.cancel`은 `배민클럽 이용 중 변경`을 해지 경로로 오인한 실제
  hard negative를 수집하고 닫기로 복구했다. WebView가 scrollable 노드를 노출하지 않아도
  candidate 화면 경계로 90% gesture를 실행하도록 보완한 뒤, 세 번의 큰 스크롤로 하단
  `해지하기` 안전 경계를 발견했다. 버튼은 실행하지 않았다.
- 과거 TVING A/B는 검색 오류 진단 자료일 뿐 런타임 승자 선택에 사용하지 않는다.
- 공개 Navigation DB가 활성화된 B를 고정하고 절대 지표·고정 replay·holdout 회귀로 평가한다.
