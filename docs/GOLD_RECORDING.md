# 실기기 Human Gold 기록

## 목적

Gold 기록 모드는 정답 경로를 사용자가 직접 수행하면서 각 화면의 전체 후보와 실제 선택을 수집한다. 자동 탐색 성공 로그를 곧바로 Gold로 승격하지 않으며, 사람의 완료 확인과 별도 검수를 모두 통과한 기록만 `human_gold`가 된다.

## 휴대폰 사용 순서

1. ExitGuide에서 목적을 구체적으로 입력한다. 예: `유튜브 알림 수신을 끄고 싶어`.
2. `실기기 Gold 기록 시작`을 누른다.
3. 대상 앱을 열고 플로팅 `▶` 아이콘을 누른다.
4. 올바른 메뉴 경로를 사용자가 직접 클릭하고 스크롤한다. 기록 모드는 어떤 버튼도 자동으로 누르지 않는다.
5. 최종 목적지 화면에 도착하면 빨간 `REC` 아이콘을 눌러 ExitGuide로 돌아온다.
6. `목적지 도착 · Gold 기록 완료`를 누른다. 기록은 `review_pending` 상태가 된다.

완료 버튼은 최종 상태 변경 버튼을 대신 누르지 않는다. 결제, 탈퇴 확정, 동의 철회 같은 최종 행위는 계속 사용자 소유다.

## `저장 중`과 누락 클릭 복구

일반 접근성 클릭 이벤트가 들어오면 플로팅 아이콘은 즉시 `저장 중`으로 바뀌고, 서버 저장이 끝난 뒤 `REC`로 돌아온다. Compose·WebView·커스텀 UI가 클릭 이벤트를 생략하더라도 화면의 의미 구조가 달라지면 같은 표시가 나타난다.

이때 화면 변화 자체를 정답 클릭으로 저장하지는 않는다. 새 화면의 제목·주요 문맥이 직전 화면의 **고유한 저위험 후보 하나**와 일치하고, 전후 화면이 구조적으로 충분히 다를 때만 해당 후보를 클릭한 것으로 복구한다. 중간 로딩 화면에서는 원래 화면과의 연결을 유지한 채 `저장 중` 상태로 기다린다. 타이머, 가격, 광고 회전처럼 동일 화면에서 숫자나 콘텐츠 일부만 바뀐 경우에는 Gold 클릭을 만들지 않는다.

## 저장 데이터

- 앱 패키지, 앱 버전, locale, 사용자 목적, 추론된 최종 기능
- 화면 fingerprint와 개인정보를 제거한 구조 정보
- 화면에서 관찰한 전체 후보와 위험도
- 사용자가 실제 선택한 후보, 클릭 또는 스크롤 동작
- 다음 화면 fingerprint와 전환 결과
- 최종 목적지 확인 여부, 안전 종료 여부, 검수자와 메모

좌표는 정답의 핵심 표현으로 사용하지 않는다. UI가 이동해도 재학습할 수 있도록 버튼의 의미, 역할, 화면 문맥과 후보 간 순위를 학습 데이터로 만든다.

## 검수와 승격

로컬 Navigation DB가 `.artifacts/universal-navigation.sqlite`인 예시:

```powershell
python scripts/Review-NavigationGoldRecording.py `
  --database .artifacts/universal-navigation.sqlite `
  --recording-id <RECORDING_ID> `
  --decision human_gold `
  --reviewer YangGeon `
  --notes "실기기에서 최종 목적지 확인" `
  --confirm I_REVIEWED_THE_DESTINATION
```

잘못된 경로는 `--decision rejected`로 남긴다. `human_gold` 승격은 `destination_correct=true`와 `safe_stop=true`인 검수 대기 기록에만 허용된다.

## K-EXAONE 학습용 내보내기

```powershell
python scripts/Export-NavigationGoldTraining.py `
  --database .artifacts/universal-navigation.sqlite `
  --output .artifacts/training/navigation-human-gold.jsonl
```

각 JSONL 행은 한 화면에서의 후보 순위 학습 사례다. `correct_candidate`, `incorrect_candidate_ids`, 목적, 앱/버전, 화면 문맥, 다음 화면과 결과를 포함한다. 기본값은 검수된 `human_gold`만 내보낸다.

## 상태 수명주기

```text
recording -> review_pending -> human_gold
                           -> rejected
recording -> cancelled
```

`review_pending`과 `human_gold`는 기존 승인 경로의 즉시 재생과 별개다. Gold는 K-EXAONE 후보 선택 학습·평가 근거이며, 자동 탐색기의 serving route로 자동 승격되지 않는다.
