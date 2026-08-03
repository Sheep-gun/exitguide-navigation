# Navigation Executor 최초 실기기 통합 검증

검증 일시: 2026-08-03 17:10~17:17 KST

## 범위와 격리

- 기기: Samsung SM-S936N, Android 16
- 앱: YouTube `21.31.524+1561190182`
- 목표: `membership.cancel`
- 통합 커밋: `9dd708ac18c43e6380296f530beb8cf30af7d9fa`
- 설치 APK SHA-256: `9904ec6f102ada2dc12fd30c7110bc49b043ed4c6ace694b64c8ee876a16f44a`
- 격리 Runtime DB: `/home/kyle/exitguide/runtime/executor-validation-d19a1b5/navigation-runtime-v4.sqlite`
- 검증 세션: `navs_621004748f79471daedecfe7fe2e4de6`
- 기존 Decision DB는 읽기 전용이었고 이 검증 경험을 승격하지 않았다.

## 완료 조건 결과

| 조건 | 결과 | 근거 |
|---|---|---|
| Accessibility 후보 수집 | passed | YouTube 첫 화면에서 노드 82개·후보 22개, 다음 화면에서 노드 113개·후보 27개 |
| candidate_id 기반 실제 클릭 | passed | 현재 후보 집합에 존재한 ID로 3회 클릭, 모두 `executor_action_succeeded=true` |
| 행동 전후 화면 변화 검증 | passed | 3회 클릭 모두 `screen_changed=true`; 실행되지 않은 scroll은 `false`로 기록 |
| 애매한 화면 스크린샷의 VLM 전달 | passed | `visual_context ready required=true`, `visualScreenshot=true`, `perception=exaone_4_5` |
| VLM candidate_id allowlist | passed | 성공한 EXAONE 응답이 기존 후보 27개 중 8개 ID만 주석화; 선택된 클릭 ID도 입력 후보 집합에 존재 |
| 실행 실패와 판단 실패 분리 | passed | 마지막 단계가 planner 성공, executor 실패, 화면 무변화, 연결 정상, `executor_action_not_executed`로 분리 저장 |
| 동일 커밋 APK 통합 테스트 | passed | 설치 APK 해시가 고정 빌드 해시와 일치하고 위 흐름이 한 설치본에서 완료됨 |

위험·최종·고위험 후보 자동 실행은 0건이다. 화면 이미지는 마스킹된 요청으로만 전달했으며 검증 산출물에는 저장하지 않았다.

## A100 및 N100 연결

- EXAONE 4.5 모델을 A100 로컬 SSD의 `/workspace/exitguide-local/models/EXAONE-4.5-33B`에서 기동했다.
- A100 vLLM `/v1/models`와 짧은 추론은 HTTP 200이었고 짧은 추론 시간은 1.221초였다.
- N100 `exitguide-a100-vlm-tunnel.service`를 새 A100 SSH port 30000으로 교체했고 `active`를 확인했다.
- N100 `127.0.0.1:18000`에서 EXAONE 4.5 모델 조회가 HTTP 200이었다.

## 냉정한 결론

Executor 이관·연결을 증명하는 최초 통합 게이트는 통과했다. Accessibility 후보, OCR·스크린샷, EXAONE 4.5, candidate_id 클릭, 행동 후 관찰, 실패 분리, 위험 차단이 같은 APK에서 실제로 이어졌다.

이번 실행의 탐색 품질은 성공하지 못했다. 계정 옵션 도움말을 선택해 Google 고객센터로 이동했고 최종적으로 안전 정지했다. 또한 네 번의 시각 요청 중 두 번은 EXAONE 응답 JSON 파싱 실패로 구조화 입력 fallback이 사용됐다. 따라서 이 세션은 성공 Transition이나 Decision Memory로 승격하지 않는다. 후속 수집에서는 `계정 옵션 자세히 알아보기` 같은 도움말 후보의 역할·외부 이동 위험과 VLM strict JSON 안정성을 개선 대상으로 다룬다.

## 근거 경로

- Android 로그: `docs/evidence/android-executor-device-20260803.log`
- Navigation API 로그: `/home/kyle/exitguide/runtime/executor-validation-d19a1b5/navigation-api.log`
- A100 VLM 로그: `/workspace/exitguide-local/logs/exaone/server-20260803-165142.log`
- 격리 Runtime DB: `/home/kyle/exitguide/runtime/executor-validation-d19a1b5/navigation-runtime-v4.sqlite`
