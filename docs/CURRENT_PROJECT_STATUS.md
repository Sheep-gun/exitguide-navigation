# ExitGuide Navigation 현재 프로젝트 현황

기준일: 2026-08-02
기준 저장소: `Sheep-gun/exitguide-navigation`, `agent/gold-recorder`
운영 API: A100 서버의 FastAPI와 공개 HTTPS 터널

## 현재 제품 정의

ExitGuide Navigation은 앱별 좌표나 Gold 클릭 배열을 재생하는 매크로가 아니다. 처음 보는 Android 앱에서도 현재 화면을 AccessibilityService·OCR·필요 시 EXAONE 4.5 VLM으로 해석하고, K-EXAONE이 매 화면에서 현재 후보 ID 중 다음 Hermes 행동을 결정하는 목적 기반 Navigation Agent다.

```text
목적 입력
→ 대상 앱 대기
→ 현재 화면 관찰
→ Gold·기능 그래프·AndroidControl 검색
→ K-EXAONE Hermes 계획
→ Python 안전 검사
→ 저위험 중간 행동만 실행
→ 새 화면을 다시 관찰
→ 최종 목적지에서 자동 종료
→ 최종 상태 변경은 사용자가 직접 실행
```

운영 상태 머신은 다음 계약을 따른다.

```text
IDLE → WAITING_FOR_TARGET_APP → OBSERVING → RETRIEVING → PLANNING
→ SAFETY_CHECK → EXECUTING_SAFE_ACTION → OBSERVING
→ DESTINATION_REACHED → WAITING_FOR_USER_FINAL_ACTION → FINISHED
```

## 구현 완료 범위

### Android 앱

- AccessibilityService의 텍스트·contentDescription·resource ID·역할·상태·계층·bounds 수집
- 접근성에서 빠진 문구를 위한 OCR 후보와 좌표 매핑
- 목적 입력 후 대상 앱을 열고 플로팅 시작 아이콘을 누르는 대기 UX
- 클릭, 화면 단위 스크롤, 뒤로가기, 화면 변화 재관찰
- 무한 피드·반복 화면·동일 행동·과도한 스크롤·앱 이탈 차단
- 로그인·프로필 선택·CAPTCHA·본인 인증과 위험 경계에서 사용자 요청
- 목적지 도착 즉시 자동 탐색을 끝내고 최종 버튼명만 안내
- 결제·구독 신청/해지 확정·회원 탈퇴·삭제·환불 제출·동의 확정 자동 실행 금지
- USB 포트 역방향 연결 없이 공개 HTTPS API를 사용하는 배포 설정

### K-EXAONE Navigation Policy

- 현재 화면에서 실제로 발견된 후보 ID만 허용하는 Hermes `plan_navigation_step`
- `click`, `scroll_forward`, `back`, `wait_and_observe`, `mark_destination`, `stop_for_user` 제한 행동
- 최종 목적지를 먼저 만들고 현재 단계·이력·예상 다음 기능을 함께 판단
- Human Gold·기능 그래프·AndroidControl을 명령이 아닌 근거로 입력
- 매 화면 재관찰과 K-EXAONE 재판단; production 경로 replay 기본값 `false`
- 잘못된 후보 ID, 임의 좌표, 다중 호출, 스키마 불일치 거부
- Hermes 전송 형식의 정확한 단일 `<tool_call>` 래퍼 호환과 1회 구조 교정 재요청
- 모델 장애 시 휴리스틱 클릭으로 바꾸지 않는 fail-closed 기본값
- 모든 검색 근거·후보·입력 해시·모델 행동·안전 판정을 남기는 retrieval trace

제공된 K-EXAONE endpoint에는 공개된 가중치 학습/fine-tuning job API가 확인되지 않았다. 따라서 현재 구현은 K-EXAONE을 파인튜닝했다고 주장하지 않으며, 검색 기반 in-context learning과 별도 후보 재랭커를 사용한다. 향후 학습 가능한 SFT·선호 자료는 이미 생성한다.

### EXAONE 4.5 VLM

- A100의 `EXAONE-4.5-33B` OpenAI 호환 비전 endpoint 연결
- 이름 없는 아이콘, WebView/Canvas, OCR 충돌, 시각 중심 팝업, 정체 화면에서만 선택 호출
- 후보 bounds 기반 crop과 element ID를 유지하는 구조화 시각 라벨
- 화면 지문·모델 버전 기반 SQLite 캐시
- 원본 이미지 대신 라벨·신뢰도·모델 버전을 보존하고 이미지 비저장
- redacted YouTube 상단 도구 모음 실호출에서 알림·검색 아이콘 2/2 식별

### 학습·검색 데이터

- Human Gold 21개를 화면 선택 예제 92개와 선호 쌍 1,871개로 변환
- 앱 누수 방지 분할: train 64개/5개 앱, validation 23개/Netflix, test 5개/Google Play Store
- SFT JSONL, positive/negative 선호학습 자료, 실패·무변화·복구 표본
- FTS 기반 Human Gold 검색과 train-only 기능 전이 검색
- Human Gold로 학습한 작은 pairwise 후보 재랭커
- 런타임 학습 큐: `runtime → shadow → 자동 품질 검사 → verified_candidate`
- 기능 그래프: `shadow → verified_candidate → verified → trusted`; Human Gold는 자동 생성하지 않음

### AndroidControl v3

- 공식 20/20 shard, 성공 시연 15,283개에서 행동 단계 83,848개 정규화
- 목적·화면·행동·다음 화면, terminal, back, 위험도와 기능 태그 복원
- FTS5 83,848행과 bilingual function-cue 64차원 벡터 83,848개
- portable SQLite 1,242,562,560 bytes, `PRAGMA integrity_check=ok`
- SHA-256 `96d3d47e5e707da66cd5b57f1cc32ab2bade62b647e09d9a28a2b7a6d2875e71`
- 원본은 서버 영구 작업공간, 런타임은 같은 체크섬의 `/tmp` 로컬 SSD 읽기 전용 복사본 사용
- 현재 화면·목적 Top-K가 K-EXAONE 입력에 실제 포함됨
- 과거 사례의 target이 현재 후보에 없으면 미래 기능 방향으로만 표시해 잘못된 현재 버튼 매핑 방지

## 운영 DB 스냅샷

SQLite `quick_check=ok`, 2026-08-02 기준이다.

| 데이터 | 수량 |
| --- | ---: |
| 앱 | 42 |
| 화면 | 988 |
| 행동 후보 | 19,266 |
| 실제 전이 | 451 |
| 탐색 세션/단계 | 136 / 917 |
| 탐색 시도/frontier | 440 / 884 |
| 발견 경로 | 56 |
| shadow / verified_candidate / stale | 43 / 6 / 7 |
| Gold 기록/단계 | 40 / 202 |
| Human Gold / rejected / cancelled | 21 / 7 / 11 |
| 학습 예제 | 92 |

현재 trusted 경로가 0개인 것은 오류가 아니다. 기존 6개는 독립 검증 1회의 `verified_candidate`이며, 충분한 반복 검증 없이 높은 등급을 만들어내지 않는다. 등급은 K-EXAONE 검색 근거의 강도일 뿐 고정 클릭 명령이 아니다.

## 평가 원칙과 현재 결과

- source recording을 항상 검색에서 제외
- 기본 test 평가는 평가 앱 전체를 제외하는 leave-one-app-out
- Gold/verified route/좌표 replay 0
- 버튼 순서 변경, 동의어, 이름 없는 목표, 위험 decoy를 동일 정책에 적용
- 최우선 기준: 위험 행동 0 → 목적지 정확도 → 오클릭 → 복구 → 시간

상세 구성별 수치와 실패 사례는 [Navigation Agent 평가 보고서](NAVIGATION_AGENT_EVALUATION.md)에 기록한다. 현재 완료된 누수 방지 기준선은 휴리스틱 Top-1 48%, 전체 K-EXAONE 구성 Top-1 72%로 **24%p 개선**, 목적지 판별 100%, 위험 행동 자동 실행 0건이다. VLM은 이미지가 없는 25개 policy 사례에 허위로 합산하지 않고 2개 실화면 아이콘 subset으로 별도 보고한다. Netflix 연속 경로의 평균 진행률은 후보 잡음 제거 전 14.1429%에서 29.1429%로 개선됐지만 목적지 도달은 아직 0%다. Google Play Store 연속 평가는 이름 없는 첫 아이콘 단계에서 외부 K-EXAONE inference timeout으로 종료됐다. 연속 경로 완주가 현재의 가장 큰 성능 한계다.

## portable 백업

백업 도구는 다음을 checksum manifest가 있는 하나의 archive로 만든다.

- 일관된 Navigation SQLite snapshot
- AndroidControl portable v3 index
- SFT·선호·학습 큐·평가·VLM label·재랭커·APK 산출물
- 재생성 코드, 계약, fixture와 운영 문서

다음은 제외한다.

- `.env`, API 키와 credentials
- AndroidControl 원본 20개 shard
- 원본 스크린샷·이미지
- 모델 가중치, venv, node_modules와 빌드 캐시

`Create-NavigationPortableBackup.py`와 `Restore-NavigationPortableBackup.py`는 archive 생성, 체크섬 검증, 경로 탈출 방지, 실제 복원과 SQLite 검증을 자동화한다.

## 남은 최종 게이트

1. 최종 Agent-only·trajectory 보고서 고정
2. portable archive를 서버에서 생성하고 별도 위치에 복사한 뒤 실제 복원 검증
3. 전체 API 검사, TypeScript, Android 설정 검사와 APK 재빌드
4. Git 비밀값 검사, 커밋·푸시와 GitHub Actions 확인
5. 마지막에만 실기기 APK smoke test

## 관련 문서

- [학습 아키텍처](NAVIGATION_AGENT_LEARNING_ARCHITECTURE.md)
- [범용 Agent 런타임](UNIVERSAL_NAVIGATION_AGENT.md)
- [AndroidControl](ANDROID_CONTROL.md)
- [Agent 평가](NAVIGATION_AGENT_EVALUATION.md)
- [K-EXAONE 기능 확인](K_EXAONE_CAPABILITY_AUDIT.md)
- [API 계약](API_CONTRACT.md)
