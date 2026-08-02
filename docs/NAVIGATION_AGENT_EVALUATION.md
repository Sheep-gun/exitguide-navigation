# Navigation Agent 평가 보고서

평가 기준일은 2026-08-02이다. 이 보고서는 Human Gold 클릭 배열을 재생하는 경로 재현율이 아니라, 현재 화면에서 K-EXAONE이 새 Hermes 행동을 결정하는 **Agent-only** 성능을 측정한다. 결과가 좋은 단일 화면 평가와 아직 부족한 연속 경로 평가를 분리해 기록한다.

## 평가 계약

- 평가 source recording은 검색 근거에서 제외한다.
- 기본 test는 앱 전체를 제외하는 leave-one-app-out이다.
- Human Gold, verified route와 절대 좌표를 실행 명령으로 재생하지 않는다.
- 검색 결과는 K-EXAONE 프롬프트 근거로만 전달한다.
- K-EXAONE은 현재 화면에 실제로 존재하는 candidate ID 중 하나만 Hermes `plan_navigation_step`으로 선택한다.
- Python 안전 제어기를 통과한 행동만 실행 결과로 센다.
- 위험한 모델 제안, 안전 제어기 차단, 실제 자동 실행을 별도 지표로 구분한다.
- 25개 policy case에는 원본, 순서 반전, 동의어, 이름 없는 목표, 위험 decoy 변형을 동일하게 적용한다.

## 단일 화면 구성 비교

| 구성 | Top-1 | Top-3 | 목적지 판별 | 위험 행동 자동 실행 | 평균 Planner 지연 | 오류 |
|---|---:|---:|---:|---:|---:|---:|
| 1. 휴리스틱 | 48% | 48% | 100% | 0% | 3,386.828 ms | 0 |
| 2. K-EXAONE | 44% | 44% | 100% | 0% | 4,445.568 ms | 0 |
| 3. K-EXAONE + Human Gold 검색 | 44% | 44% | 100% | 0% | 4,407.577 ms | 0 |
| 4. K-EXAONE + AndroidControl 검색 | 44% | 44% | 100% | 0% | 8,255.542 ms | 1 |
| 5. K-EXAONE + Gold + AndroidControl + 기능 그래프 + 학습 재랭커 | **72%** | **72%** | **100%** | **0%** | 8,879.892 ms | 0 |

전체 구성은 휴리스틱보다 Top-1이 **24%p 향상**했다. K-EXAONE 단독이나 단일 검색원만으로는 기준선을 넘지 못했으며, 여러 근거와 train-only pairwise 재랭커를 함께 썼을 때 개선됐다. 따라서 특정 검색 DB 하나의 효과로 과장하지 않는다.

전체 구성의 변형별 Top-1은 다음과 같다.

| 변형 | 사례 | Top-1 | 위험 행동 자동 실행 |
|---|---:|---:|---:|
| 원본 | 5 | 80% | 0% |
| 순서 반전 | 5 | 80% | 0% |
| 동의어 | 5 | 40% | 0% |
| 이름 없는 목표 | 5 | 80% | 0% |
| 위험 decoy | 5 | 80% | 0% |

남은 7개 오답은 모두 held-out Google Play Store에 집중됐다. 5개는 이름 없는 상단 우측 계정 아이콘 대신 `내 페이지`를 선택한 동일 첫 화면 변형이고, 2개는 동의어 변형에서 `일반 메뉴`와 `푸시 및 소식` 대신 각각 `정보`, `계정 및 기기 환경설정`을 선택한 경우다. 이름 없는 아이콘은 화면 이미지가 없는 이 평가에서는 VLM으로 보완할 수 없으므로 별도 실화면 VLM 평가와 구분한다.

## 연속 경로 평가

연속 경로 평가는 첫 단계부터 마지막 목적지 판별까지 모두 맞아야 성공한다. 단일 화면 Top-1보다 훨씬 엄격하다.

| split / 앱 | trajectory | 목적지 도달 | 평균 경로 진행률 | 위험 자동 실행 | 모델 제안 위험 | 오류 |
|---|---:|---:|---:|---:|---:|---:|
| validation / Netflix | 20 | 0% | **29.1429%** | 0% | 0% | 0 |
| test / Google Play Store, 35초 설정 | 4 | 0% | 0% | 0% | 0% | 4 |
| test / Google Play Store, 45초 재시도 | 4 | 0% | 0% | 0% | 0% | 4 |

Netflix는 후보 잡음 제거와 목적 도메인 충돌 feature 추가 전 14.1429%였던 평균 경로 진행률이 29.1429%로 개선됐지만, 완주율은 아직 0%다. 주요 실패는 가입 목적에서 `로그인` 대신 `시작하기`, 계정/구독 목적에서 `나의 넷플릭스` 대신 알림·앱 설정·추가 회원·결제 내역을 선택한 것이다.

Google Play Store trajectory는 첫 화면의 이름 없는 계정 아이콘에서 K-EXAONE API가 모든 변형에 대해 wall-clock deadline을 넘겼다. 35초 런타임 설정은 Hermes 구조 교정 1회를 위해 시도당 17.5초, 45초 재시도는 시도당 22.5초를 배정한다. 두 번 모두 4/4 timeout이므로 이 결과는 시각 의미 선택 정확도가 아니라 외부 inference 안정성 실패로 기록한다. 운영 런타임은 오류 시 Python 휴리스틱 클릭으로 넘어가지 않고 `stop_for_user`로 fail closed한다.

현재 가장 큰 제품 한계는 이 연속 경로 완주율이다. 단일 화면 72%를 실제 앱 목적지 도달률로 해석하면 안 된다. 다음 개선 우선순위는 (1) 실화면 VLM을 사용한 이름 없는 첫 아이콘 해석, (2) 동의어 목적의 중간 기능 분해, (3) K endpoint 지연 안정화, (4) 실제 앱 업데이트 화면으로 연속 경로 회귀 확대다.

## EXAONE 4.5 VLM 별도 평가

25개 policy case에는 이미지가 없으므로 VLM 수치를 억지로 합산하지 않았다. A100의 `EXAONE-4.5-33B`에 개인정보가 제거된 295×140 도구 모음 이미지를 보내 이름 없는 `bell`, `search` 두 후보를 검사했다.

- 2/2 후보 의미 일치, 정확도 100%
- 전송 이미지 701 bytes, redacted=true
- 원본 이미지 persisted=false
- 캐시에는 화면 설명과 후보별 의미 라벨만 저장

표본이 2개뿐이므로 일반 VLM 정확도 주장이 아니라 실제 adapter·서버·응답 정규화가 연결됐다는 smoke evidence로만 사용한다.

## AndroidControl 런타임 근거

공식 AndroidControl 20개 shard를 15,283 episode, 83,848 행동 단계로 정규화했다. portable SQLite v3에는 같은 수의 FTS 행과 64차원 의미 벡터, 전이 메타데이터가 있으며 15,274개 terminal step을 기록한다.

- index bytes: 1,242,562,560
- SHA-256: `96d3d47e5e707da66cd5b57f1cc32ab2bade62b647e09d9a28a2b7a6d2875e71`
- `PRAGMA integrity_check=ok`
- warm 20 query: p50 231.230 ms, p90 300.485 ms, max 306.235 ms
- 20/20 query에서 Top-5 반환

Agent-only 전체 구성에서는 AndroidControl 검색 hit 100%였고 검색 사례가 K-EXAONE 입력 근거와 retrieval trace에 포함된다. hit는 검색이 실행됐다는 뜻이며 정답 선택을 보장한다는 뜻은 아니다.

## 학습 재랭커

재랭커는 현재 화면 후보만 정렬하며 클릭하지 않는다. K-EXAONE이 최종 Hermes 행동을 생성하는 계약은 유지한다.

- 학습 click example 41개, preference pair 5,331개
- 전체 indexed Gold example 92개
- training pair accuracy 96.1921%
- training pair log loss 0.114289
- train Top-1 62.9268%
- held-out validation Top-1 52.8571%
- artifact SHA-256: `4cb861f700c51f74bede7db560f4d1753640229f11245039ce1ac3f78e6f79d9`

split은 앱 단위로 고정되어 있으며 validation/test 앱의 정답은 학습 pair에 넣지 않는다.

## 안전성·상태·시나리오 검사

자동 검사는 다음을 포함한다.

- 위험한 최종 결제·구매·해지·탈퇴·삭제·토글 차단
- 모델이 위험 후보를 제안해도 실행 행동은 `stop_for_user`
- 임의 좌표와 존재하지 않는 candidate ID 거부
- 동일 화면·동일 행동 반복과 무한 피드 스크롤 제한
- 페이지 단위 스크롤, backtracking, 시간·행동·깊이 budget
- 로그인·프로필 선택·CAPTCHA·본인 인증에서 사용자 요청
- destination 도달 시 자동 조작 종료와 최종 버튼 사용자 직접 실행
- 매 화면 재관찰·재검색·K-EXAONE 재계획
- 현재 후보 재랭킹만 허용하고 Gold·verified route replay 금지
- retrieval 후보, 근거, 입력 SHA, Hermes 출력, 안전 판정 저장
- 기능 그래프 `runtime → shadow → verified_candidate → verified → trusted` 승격

## 재현 명령과 원시 산출물

서버 평가 예시는 다음과 같다.

```bash
python scripts/Run-NavigationAgentOnlyEval.py \
  --database /home/exitnav/workspace/universal-navigation-api/data/universal-navigation.sqlite \
  --output artifacts/navigation-evaluation/comparison-05-full.json \
  --provider exaone --split test \
  --android-control-index /tmp/exitguide-android-control.sqlite \
  --policy-reranker fixtures/navigation/navigation-policy-reranker-v1.json
```

연속 경로는 같은 명령에 `--trajectory`를 추가한다. 저장소 밖의 원시 결과는 `.artifacts/navigation-evaluation/`, VLM 결과는 `.artifacts/navigation-vlm/live-toolbar-smoke.json`, APK는 `.artifacts/apk/exitguide-ai-overlay-release.apk`에 보관한다. Git에는 대용량·민감 산출물 대신 코드, 재현 스크립트, 작은 모델 아티팩트, manifest와 이 보고서를 커밋한다.

## 결론

전체 에이전트 구성은 누수 방지 단일 화면 평가에서 휴리스틱보다 명확히 개선됐고 위험 행동 자동 실행은 0이다. AndroidControl, Gold, 기능 그래프와 K-EXAONE Hermes planner가 실제 런타임에 연결됐으며 EXAONE 4.5 VLM adapter도 실호출로 확인했다. 다만 처음 보는 앱의 연속 경로 완주는 아직 검증되지 않았다. 따라서 현재 산출물은 **범용 Agent 아키텍처와 안전 실행 기반이 완성된 개발 빌드**이며, 연속 경로 목적지 성공률을 다음 성능 게이트로 삼는다.
