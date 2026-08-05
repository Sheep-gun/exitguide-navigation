# ExitGuide 수집기 v6: Codex 조작·원본 우선 구조

## 한 줄 요약

수집기는 화면과 모든 후보를 기록하고 Codex가 고른 행동만 실행한다. EXAONE이나 기존 점수 계산기는 수집 중 행동을 고르지 않는다. 되돌릴 수 없는 최종 행동과 반복 오염만 최소 안전장치가 차단한다.

## 전체 역할

1. **실행기 앱**: EXAONE 1.2B Q8 + Value Head가 휴대폰 안에서 후보를 고르는 최종 데모 앱이다.
2. **수집기 앱**: Codex가 실기기를 조작할 때 행동 전후 화면, 전체 후보, 선택 근거와 결과를 보존한다.
3. **N100 API·DB**: 수집 원본과 사람/Codex 검토 결과를 분리 저장한다.
4. **오프라인 교사 평가**: 저장된 원본을 EXAONE 4.5 등에 다시 입력해 shadow 결과를 만든다. 수집기 자체에는 EXAONE이 필요 없다.

## 수집 흐름

```text
접근성 화면 읽기
-> 앱 내부 latest-screen.json 저장
-> Codex가 후보와 화면 지문을 읽음
-> ADB로 후보 행동과 선택 근거 전달
-> 서버가 후보 존재 여부와 최종 위험 행동 검사
-> 앱이 행동 실행
-> 행동 후 화면과 결과 기록
-> 다음 화면에서 반복
```

기존 서버 점수 계산과 자동 후보 선택 코드는 비교·회귀용으로 남아 있지만 수집기 v6의 기본 실행 경로에서는 사용하지 않는다.

## Codex가 읽는 화면

디버그 APK 기준:

```bash
adb exec-out run-as com.exitguide.navigation.executor \
  cat files/collector/latest-screen.json
```

파일에는 목표, 앱 패키지·버전, 화면 지문, 세션 단계, 사전 상태, 접근성 화면 원본과 전체 후보가 들어간다. 화면 지문이 바뀐 뒤 도착한 오래된 명령은 실행하지 않는다.

## 수집 시작

```bash
adb shell am broadcast \
  -a com.exitguide.navigation.executor.ADB_START_NAVIGATION \
  --es goal "회원 탈퇴 메뉴 찾기" \
  --es collector_alias "codex-kyle" \
  --es account_state "logged_in" \
  --es service_state "active" \
  --es start_surface "마이페이지" \
  --es precondition_status "ready" \
  --es reset_method "app_relaunch" \
  --ez reset_verified true \
  --es precondition_source "codex" \
  --ef precondition_confidence 0.95
```

## Codex 행동 명령

```bash
adb shell am broadcast \
  -a com.exitguide.navigation.executor.ADB_OPERATOR_ACTION \
  --es action_name "click" \
  --es candidate_id "후보_ID" \
  --es command_id "고유_명령_ID" \
  --es expected_screen_fingerprint "latest-screen의_화면_지문" \
  --es reason_codes "goal_match,stage_forward" \
  --es reason_text "회원정보에서 탈퇴 메뉴로 전진" \
  --es review_status "provisional"
```

허용 행동은 `click`, `scroll`, `back`, `wait_and_observe`, `stop_for_user`다. `scroll`은 `--es direction up|down`을 함께 보낸다.

## 최소 안전장치

- 화면 지문과 후보 ID가 현재 화면과 일치해야 한다.
- 결제·구매·가입 완료·동의 확정·영구 삭제·탈퇴 확정 등 되돌릴 수 없는 최종 행동은 차단한다.
- `회원탈퇴`, `구독 해지` 같은 메뉴 진입 문구 자체는 차단하지 않는다. 확인 문구와 함께 나타난 최종 버튼만 차단한다.
- 같은 화면에서 같은 행동을 세 번 연속 지시하면 해당 세션을 `loop_detected`로 닫는다.
- 세션은 행동 15회 또는 10분에서 끊어 오염 범위를 제한한다.
- 오래된 화면 명령, 현재 화면에 없는 후보, 허용 목록 밖 행동은 실행하지 않는다.

안전장치는 후보를 대신 고르는 판단기가 아니다. 최종 사고와 무한 반복만 막는다.

## 학습에 저장하는 정보

- 행동 전·후 화면과 전체 후보
- 앱·버전·기기·수집기 버전
- 계정 상태, 서비스 상태, 시작 화면
- 사전 조건 준비 여부, 초기화 방법과 확인 여부
- Codex 명령 ID, 선택 근거 코드·설명, 검수 상태
- 실제 실행 성공 여부, 화면 변화와 진행 결과
- 명확한 종료 사유
- 후보별 학습 라벨

후보별 라벨은 다음 다섯 가지다.

- `best`: 현재 화면의 최선 후보
- `acceptable`: 정답은 아니어도 합리적인 후보
- `hard_negative`: 그럴듯하지만 잘못된 후보
- `unsafe`: 실행하면 안 되는 후보
- `unknown`: 현재 증거로 판단 불가

라벨은 Runtime DB가 아니라 별도 Review DB의 `navigation_candidate_labels`에 저장한다. 원본 실행 기록은 수정하지 않는다.

## 데이터 분할

`collection`, `validation`, `locked_holdout`은 앱 단위 `navigation_dataset_split_manifest`에서 관리한다. 각 판단 행에 분할값을 반복해서 쓰지 않는다. 잠긴 시험 앱은 기본 shadow 내보내기와 학습에서 제외한다.

## EXAONE shadow 평가

```bash
python scripts/export_navigation_shadow_cases.py \
  --runtime-db /path/navigation_runtime.sqlite \
  --review-db /path/navigation_reviews.sqlite \
  --output /path/navigation-shadow-cases.jsonl
```

내보낸 JSONL에는 모델 점수 대신 원본 화면·후보, Codex 선택과 이유, 실제 결과, 검토 라벨만 들어간다. EXAONE 버전·LoRA 버전·양자화·프롬프트·지연시간·예측 점수는 별도의 shadow 결과 파일에 기록한다. 그래야 수집 원본과 특정 모델의 판단이 섞이지 않는다.

## LoRA와 DB의 관계

LoRA가 공통 화면 의미와 절차 패턴을 흡수하면 휴대폰 런타임 DB는 줄일 수 있다. 그렇다고 DB 전체를 없애지는 않는다.

- LoRA로 흡수: 공통 버튼 의미, 절차 단계, 전진·후퇴 패턴
- DB에 유지: 앱 버전별 예외, 최신 경로, 위험 근거, 실패·복구 증거, 평가용 원본
- 제거 후보: LoRA가 안정적으로 처리하고 재현 근거로도 쓰이지 않는 중복 설명

경량화는 LoRA 학습과 잠긴 시험 앱 평가가 끝난 뒤 한다. 그 전에는 원본을 삭제하지 않는다.

## 구현 위치와 상태

- Android: `apps/android-executor`
- API 계약: `apps/api/app/navigation_contracts.py`
- Runtime 기록: `apps/api/app/services/navigation_runtime.py`
- 후보 라벨: `apps/api/app/services/navigation_review.py`
- shadow 내보내기: `scripts/export_navigation_shadow_cases.py`
- 수집기 버전: `0.6.0`
- 빌드 ID: `navigation-runtime-v6-codex-operator`
- N100 API 배포 코드: `/srv/exitguide/runtime/navigation-api-code-codex-operator-v6-88e06b8`
- N100 APK: `/srv/exitguide/releases/navigation-executor/88e06b8/navigation-executor-debug.apk`
- 기존 Runtime DB는 이동·변환·삭제하지 않았다.

이 문서가 수집기·학습 데이터·안전 경계에 대한 현재 기준이다. 과거 자동 점수 기반 문서는 실험 기록으로만 해석한다.
