# ExitGuide Navigation

ExitGuideLab의 목적 기반 UI 내비게이션 모듈이다. 사용자의 목적과 현재 Android 화면 구조를 받아, 앱을 대신 조작하지 않고 다음에 선택할 실제 UI 요소와 목적을 방해하는 선택지를 메시지형 플로팅 UI로 안내한다.

## 담당 범위

- 담당: 양건
- 이 저장소: 앱별 모범 경로 수집·검색, 현재 화면 매칭, 다음 행동 판단, AccessibilityService, 메시지형 플로팅 안내, 경로 이탈 복구
- 김군협의 `exitguide` 저장소: 약관 데이터 수집·라벨링·검색·요약
- 최종 통합: Navigation API와 Terms API를 최종 ExitGuide 앱 또는 통합 백엔드에서 조합

## 핵심 흐름

```text
사용자 목적 + 현재 Accessibility 화면 구조
                    ↓
       Upstage File Search에서 모범 경로 검색
                    ↓
     검색 결과 + 현재 화면을 K-EXAONE에 전달
                    ↓
 실제 화면의 다음 UI 요소·경고·확신도를 JSON으로 반환
                    ↓
 플로팅 UI가 “현재 화면에서 ○○을 누르세요”라고 안내
                    ↓
 사용자가 직접 선택하고 다음 화면을 Accessibility로 재검증
                    ↓
 경로 불일치 시 재정렬 또는 안전한 복귀 후 대체 후보 탐색
```

K-EXAONE은 최종 판단 모델로 사용한다. Upstage의 `/responses`가 아니라 File Search의 `/vector_stores/{id}/search`를 호출해 검색 결과만 가져오고, 그 결과를 K-EXAONE에 전달한다.

## 제품 원칙

- AccessibilityService는 현재 화면을 읽는 기본 센서다.
- 스크린샷 비전 분석은 접근성 정보가 부족할 때만 사용한다.
- ExitGuide는 버튼을 자동 클릭하지 않고 사용자가 직접 행동한다.
- 모델은 현재 화면에 실제로 존재하는 요소 ID만 안내할 수 있다.
- 예상하지 못한 화면에서는 먼저 다른 알려진 경로 단계와 재정렬한다.
- 재정렬할 수 없을 때만 안전성이 검증된 `뒤로 가기` 또는 `닫기`를 요청한다.
- 실패한 후보는 같은 세션에서 제외하고 검증된 대체 후보를 최대 1회 추가 시도한다.
- 두 후보가 모두 실패하면 추측을 중단하고 경로 업데이트 대상으로 기록한다.

## 데이터 저장 원칙

- 검수된 모범 경로 원본: `data/routes/*.md`
- 변경 이력과 협업: Git/GitHub
- 런타임 의미 검색: Upstage `egl-routes-prod` Vector Store
- 개인 실험: Upstage `egl-sandbox-yanggeon` Vector Store
- 고정 화면 좌표는 경로의 기준으로 사용하지 않는다.
- 화면 텍스트, 접근성 View ID, 역할, 주변 문구와 예상 다음 화면을 의미 기반 선택자로 저장한다.
- 각 단계에는 실패 시 복귀 방법, 복귀 안전성, 예상 이전 화면과 최대 재시도 횟수를 함께 저장한다.

## 저장소 구조

```text
exitguide-navigation/
├─ data/routes/                  # 검수된 모범 경로 Markdown 원본
├─ docs/PRODUCT_SPEC.md          # 화면 인식·안내·복구 제품 규칙
├─ docs/WORKFLOW.md              # 개발·수집·배포 작업 흐름
├─ docs/INTEGRATION_CONTRACT.md  # 최종 앱과의 API 계약
├─ .env.example                  # 환경변수 이름과 예시
└─ .env                          # 로컬 자격정보, Git 제외
```

구현이 시작되면 다음 디렉터리를 추가한다.

```text
apps/api/       # Python FastAPI navigation backend
apps/mobile/    # Android AccessibilityService와 플로팅 UI
scripts/        # Upstage 업로드·재색인·검증 자동화
tests/          # 경로 검색과 안전 규칙 테스트
```

## 환경 설정

`.env.example`을 기준으로 로컬 `.env`를 사용한다.

```dotenv
EXAONE_API_KEY=
EXAONE_BASE_URL=https://api.friendli.ai/dedicated/v1
EXAONE_MODEL=

UPSTAGE_API_KEY=
UPSTAGE_BASE_URL=https://api.upstage.ai/v2
UPSTAGE_ROUTE_VECTOR_STORE_ID=
UPSTAGE_ROUTE_SANDBOX_VECTOR_STORE_ID=
```

실제 키가 들어 있는 `.env`는 Git에 포함하지 않는다.

## MVP 시연

- [Navigation·다크패턴 통합 MVP 시연 영상](MVP.mp4)
- Windows 실행 파일: `dist/EGL-Navigation-MVP.exe`

## 현재 상태

- [x] navigation 전용 Git 저장소 분리
- [x] K-EXAONE Dedicated Endpoint 로컬 설정 이전
- [x] 모범 경로 문서 형식과 팀 통합 계약 정의
- [x] 화면 인식형 메시지 내비게이션과 경로 복구 원칙 정의
- [x] Upstage API 키 등록, Solar Pro 3 및 Vector Store 검색 권한 확인
- [x] `egl-routes-prod`, `egl-sandbox-yanggeon` Vector Store 생성
- [x] Navigation·다크패턴 통합 MVP 실행 파일 및 시연 영상 추가
- [ ] Upstage Agent Files 업로드 프로젝트 권한 확인
- [ ] 모범 경로 업로드·검색 스크립트 구현
- [ ] FastAPI Navigation API 구현
- [ ] AccessibilityService 기반 경로 수집 모드 구현
- [ ] 플로팅 안내와 실기기 검증
- [ ] 군협의 Terms API와 통합

제품 동작은 [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md), 구현 순서는 [docs/WORKFLOW.md](docs/WORKFLOW.md)를 따른다.
