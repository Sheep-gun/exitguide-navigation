# Navigation 작업 흐름

## 1. 역할 경계

### 양건 / 이 저장소

- 앱별 목적과 모범 경로 정의
- Android 화면 구조 수집
- Upstage 경로 Vector Store 운영
- 현재 화면과 경로 단계 매칭
- K-EXAONE 다음 행동 판단
- 플로팅 안내와 경로 성공 여부 확인

### 김군협 / Terms 저장소

- 약관 원문과 공개 데이터 수집
- 약관 조항 라벨링
- Upstage 약관 Vector Store 운영
- 약관 요약과 동의·미동의 방향성 반환

### 공동 통합 지점

- 공통 `goal_id` 목록
- Navigation API 및 Terms API의 요청 식별자
- 최종 앱에서 보여줄 안내 우선순위
- 해지·삭제·결제 등 최종 행동의 사용자 확인 정책

## 2. 개발 순서

### 단계 A — 클라우드 연결

1. Upstage API 키를 로컬 `.env`에 추가한다.
2. `egl-sandbox-yanggeon` Vector Store를 만든다.
3. 샘플 경로 문서를 업로드하고 인덱싱 완료를 확인한다.
4. 자연어 검색이 올바른 단계와 출처를 반환하는지 테스트한다.
5. 검증 후 `egl-routes-prod` Vector Store를 만든다.

### 단계 B — 모범 경로 파이프라인

1. `data/routes/_template.md`를 복사한다.
2. 실제 앱에서 목적을 한 번 수행한다.
3. 각 화면의 대표 문구, 올바른 UI 요소, 방해 요소와 예상 다음 화면을 기록한다.
4. 파일 이름과 `route_id`를 규칙에 맞춘다.
5. 사람이 경로를 검수한 뒤 Git에 커밋한다.
6. sandbox에 업로드해 검색 품질을 확인한다.
7. 통과한 파일만 prod에 올린다.

### 단계 C — Navigation API

1. Android에서 `app_package`, `app_version`, `locale`, `goal`과 현재 UI 노드를 받는다.
2. Upstage File Search에 앱·목적·플랫폼 속성 필터와 현재 화면 문구를 전달한다.
3. 상위 검색 결과와 현재 UI 노드를 K-EXAONE 프롬프트에 넣는다.
4. K-EXAONE은 `target_element_id`, 경고, 확신도와 최종 확인 여부를 JSON으로 반환한다.
5. 백엔드는 반환된 요소가 현재 화면에 실제로 존재하는지 재검증한다.
6. 통과한 결과만 모바일 앱에 전달한다.

### 단계 D — Android 경로 수집과 안내

1. AccessibilityService가 활성 창의 UI 트리를 읽는다.
2. 기록 모드에서 화면 변화와 사용자가 선택한 노드를 저장한다.
3. 좌표는 해당 순간 강조용으로만 사용하고 DB의 주 선택자로 사용하지 않는다.
4. 접근성 정보가 부족한 화면만 별도 비전 분석 대상으로 표시한다.
5. 해지·삭제·결제 확정 같은 최종 행동은 `requires_user_confirmation=true`로 반환한다.

### 단계 E — Terms 통합

1. Navigation 결과에서 약관 또는 결제 안내 화면이 감지되면 Terms API를 호출한다.
2. Navigation은 다음 행동을, Terms는 약관 요약과 사용자 목적 충돌 여부를 반환한다.
3. 최종 앱은 두 결과를 한 플로팅 카드에 합친다.

## 3. 경로 파일 규칙

파일 이름:

```text
{app}_{platform}_{goal}_{locale}_v{version}.md
```

예:

```text
youtube_android_cancel_subscription_ko_v1.md
```

Upstage 파일 속성은 최대 16개 안에서 다음 키를 우선 사용한다.

```text
kind
app
package
platform
locale
goal
route_version
status
```

하나의 파일에는 앱·목적·플랫폼·언어·경로 버전 한 조합만 넣는다. Upstage가 자동 청킹하므로 모든 앱 경로를 한 파일에 합치지 않는다.

## 4. Vector Store 운영 규칙

```text
egl-sandbox-yanggeon  개인 실험과 실패 허용
egl-routes-prod       사람 검수가 끝난 활성 경로만 등록
```

경로 갱신 순서:

1. Git에서 새 버전 파일을 만든다.
2. sandbox에 업로드하고 검색 테스트를 통과시킨다.
3. prod에 새 파일을 추가한다.
4. 인덱싱 상태가 `completed`인지 확인한다.
5. 새 버전 검색이 성공한 뒤 이전 파일을 prod에서 제거한다.

## 5. Git 작업 규칙

- `main`은 검수된 문서와 통과한 코드만 유지한다.
- 기능 작업은 `feature/<기능명>` 브랜치에서 한다.
- 경로 원본을 Upstage에만 두지 않고 반드시 Git에 보관한다.
- `.env`, 원본 사용자 화면, 개인 계정 정보는 커밋하지 않는다.
- 같은 `route_id`는 한 사람이 한 번에 수정한다.

## 6. MVP 완료 조건

- 대상 앱 3개, 앱당 목적 2개 이상
- 각 경로의 검색 결과가 올바른 앱·목적·단계를 반환
- 현재 화면의 실제 요소 ID만 안내
- 우회·유지·일시정지 버튼 경고
- UI가 달라졌을 때 확신도 저하와 검수 필요 상태 반환
- 최종 확정 행동은 사용자가 직접 확인
- Terms API가 없어도 Navigation 단독 데모 가능
- Terms API 연결 시 약관 요약을 함께 표시
