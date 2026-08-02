# EGL Navigation Agent 학습 아키텍처

## 목표

ExitGuide Navigation은 사전 좌표 경로가 없는 Android 앱에서도 현재 화면을 해석하고, 사용자의 목적에 가장 적합한 다음 메뉴를 동적으로 선택해 최종 목적지까지 안내하는 범용 Navigation Agent를 목표로 한다.

Gold는 좌표와 클릭 순서를 그대로 재생하는 매크로가 아니다. Gold는 특정 목적과 화면에서 어떤 후보를 선택해야 했는지, 어떤 후보가 실패했는지, 선택 이후 어떤 화면에 도착했는지를 담는 의미 기반 정답 데이터다. K-EXAONE은 Gold와 범용 기능 지식을 참고해 현재 화면의 후보 중 다음 행동을 결정한다.

## 구성 요소와 책임

| 구성 요소 | 책임 |
| --- | --- |
| Android AccessibilityService | 화면의 텍스트, 역할, 상태, 계층, 좌표와 클릭 가능 후보 수집 |
| OCR | 접근성 트리에서 누락되거나 잘린 화면 문구 보충 |
| EXAONE 4.5 VLM | 이름 없는 아이콘, 이미지 버튼, WebView, Canvas, 팝업과 시각 상태 해석 |
| K-EXAONE | 사용자 목적, 현재 화면 맥락, 후보와 검색 근거를 보고 다음 행동 선택 |
| 범용 기능 카탈로그 | 회원가입, 탈퇴, 구독, 알림 등 기능 의미와 동의어, 기능 간 관계 제공 |
| AndroidControl | 처음 보는 앱에서 목적을 중간 기능으로 분해하는 범용 탐색 사전 근거 제공 |
| 앱 기능 그래프 | 실제로 관찰된 화면, 메뉴, 행동과 화면 전환 관계 저장 |
| Human Gold | 실제 앱에서 성공하고 사람이 독립 검증한 고품질 선택 사례 제공 |
| Android 안전 실행기 | 모델이 선택한 클릭, 스크롤, 뒤로가기를 정책 검사 후 실행 |

요약하면 EXAONE 4.5는 눈, K-EXAONE은 판단하는 두뇌, Gold·AndroidControl·기능 그래프는 기억, Android 실행기는 손이다.

## 온라인 Navigation 워크플로우

```mermaid
flowchart TD
    A["사용자 목적 입력"] --> B["대상 앱을 열고 탐색 시작"]
    B --> C["현재 화면 관찰"]
    C --> D["AccessibilityService로 텍스트·역할·상태·좌표 추출"]
    D --> E["OCR로 누락 문구 보충"]
    E --> F{"후보 또는 화면 의미가 불명확한가?"}
    F -- "예" --> G["EXAONE 4.5 VLM으로 아이콘·화면·팝업 분석"]
    F -- "아니오" --> H["통합 후보 목록 생성"]
    G --> H
    H --> I["Human Gold·앱 그래프·기능 카탈로그·AndroidControl 검색"]
    I --> J["K-EXAONE이 다음 행동 선택"]
    J --> K{"안전 정책을 통과하는가?"}
    K -- "아니오" --> L["자동 실행 중단 후 사용자 행동 요청"]
    K -- "예" --> M["클릭·스크롤·뒤로가기 실행"]
    M --> N["변경된 화면 재관찰"]
    N --> O{"최종 목적지인가?"}
    O -- "아니오" --> C
    O -- "예" --> P["탐색 자동 종료"]
    P --> Q["최종 버튼과 필요한 설명 표시"]
    Q --> R["상태 변경 버튼은 사용자가 직접 클릭"]
```

Accessibility 정보만으로 의미와 대상을 확정할 수 있으면 VLM 호출을 생략한다. OCR로도 해결되지 않는 이름 없는 아이콘, 접근성 정보가 비어 있는 화면, 시각 상태가 중요한 선택지, 반복 탐색 또는 저신뢰 상황에서만 VLM을 호출한다. 동일한 화면과 후보의 시각 분석 결과는 화면 지문과 모델 버전으로 캐시한다.

## 후보 선택 계약

화면 분석기는 모델에 좌표만 전달하지 않는다. 접근성, OCR, VLM 정보를 같은 후보 ID에 결합한다.

```json
{
  "goal": "유튜브 프리미엄을 해지하고 싶어",
  "screen_context": "유튜브 마이페이지",
  "candidates": [
    {
      "id": "c1",
      "accessibility_label": "시청 기록",
      "role": "button",
      "enabled": true
    },
    {
      "id": "c2",
      "accessibility_label": "구매 항목 및 멤버십",
      "role": "button",
      "enabled": true
    },
    {
      "id": "c3",
      "accessibility_label": "",
      "visual_label": "설정",
      "icon_type": "gear",
      "role": "image_button",
      "enabled": true
    }
  ]
}
```

K-EXAONE은 Hermes 도구 호출 규격에 맞춘 구조화된 결정을 반환한다.

```json
{
  "action": "click",
  "candidate_id": "c2",
  "reason": "구독 해지 목적은 멤버십 관리 기능과 가장 직접적으로 연결된다.",
  "confidence": 0.94
}
```

Android 실행기는 후보 ID를 현재 화면의 실제 요소와 다시 대조하고 안전 정책을 통과한 경우에만 행동을 실행한다. 모델이 임의의 좌표를 만들어 클릭하도록 허용하지 않는다.

## Gold 데이터 구조

Gold는 `좌표 A 클릭 → 좌표 B 클릭`이 아니라 `목적 + 현재 화면 + 전체 후보 + 올바른 선택 + 결과` 단위로 저장한다.

```json
{
  "app_package": "com.google.android.youtube",
  "app_version": "21.29.366",
  "locale": "ko-KR",
  "goal": "프리미엄 구독 해지",
  "target_function": "subscription.cancel.entry",
  "screen_fingerprint": "screen_123",
  "screen_context": "마이페이지",
  "candidates": [
    "시청 기록",
    "설정",
    "구매 항목 및 멤버십",
    "내 동영상"
  ],
  "correct_candidate": "구매 항목 및 멤버십",
  "incorrect_candidates": [
    "시청 기록",
    "내 동영상"
  ],
  "expected_next_function": "subscription.management",
  "outcome": "success",
  "verification": "human_gold"
}
```

성공 경로뿐 아니라 잘못 누른 후보, 화면 변화가 없었던 행동, 무한 피드 스크롤, 광고·이벤트 배너, 목적과 반대되는 메뉴와 되돌아간 경로도 부정 표본으로 보존한다. 이 자료는 같은 오답을 반복하지 않도록 후보 점수를 낮추고 복구 행동을 학습하는 데 사용한다.

## 학습 데이터 축적 워크플로우

```mermaid
flowchart LR
    A["실제 또는 에뮬레이터 탐색"] --> B["화면과 전체 후보 저장"]
    B --> C["모델의 선택과 판단 근거 저장"]
    C --> D["행동 후 화면 변화와 결과 저장"]
    D --> E{"목적지 성공 여부"}
    E -- "성공" --> F["성공 선택 사례"]
    E -- "실패" --> G["오답·무변화·복구 사례"]
    F --> H["개인정보 제거와 사람 검토"]
    G --> H
    H --> I["Human Gold 또는 검증 후보 승격"]
    I --> J["검색 DB와 평가 세트 반영"]
    J --> K["K-EXAONE에 유사 사례 제공"]
    K --> L["새 앱·새 UI에서 재평가"]
    L --> A
```

데이터를 DB에 저장하는 것만으로 K-EXAONE의 가중치가 학습되는 것은 아니다. 초기 단계에서는 현재 상황과 유사한 Gold를 검색해 프롬프트에 제공하는 RAG·few-shot 방식으로 사용한다. 사람 검증 데이터가 충분히 쌓이면 앱 단위 누출이 없는 학습·개발·테스트 분할을 만든 뒤 파인튜닝 가능성과 효과를 별도로 평가한다.

## DB 계층과 조회 우선순위

1. **Human Gold와 검증된 앱 기능 그래프**: 같은 앱·버전·locale·목적에서 가장 강한 경험 근거
2. **같은 앱의 관찰 그래프**: 검증되지 않았지만 실제 화면에서 관찰된 후보와 전이
3. **범용 기능 카탈로그**: 기능 의미, 동의어, 중간 기능과 최종 기능 관계
4. **AndroidControl**: 처음 보는 앱에서 탐색 방향을 잡는 교차 앱 사전 근거
5. **K-EXAONE 판단**: 현재 후보와 위 근거를 종합해 다음 행동 결정

Gold가 있는 경우에도 좌표 경로를 재생하지 않는다. 현재 화면에서 동일 의미의 후보가 실제로 관찰되는지 검증하고, K-EXAONE을 매 의미 결정에 참여시킨다. 캐시 가능한 것은 VLM의 구조화 시각 라벨과 검색 인덱스 결과뿐이며, 최종 행동 결정 자체를 캐시해 모델 판단을 건너뛰지 않는다.

## EXAONE 4.5 VLM 활용

### 실시간 인식

- 이름 없는 톱니바퀴, 연필, 프로필, 종, 닫기 아이콘 분류
- WebView·Canvas와 이미지 기반 메뉴 해석
- 팝업, 프로모션 배너와 실제 앱 메뉴 구분
- 선택·비활성·체크·토글 등 시각 상태 보충
- OCR 오인식과 접근성 정보 불일치 감지
- 탐색 정체 시 전체 화면의 기능 맥락 재분석

### 오프라인 교사 모델

A100 지원 기간에는 스크린샷 또는 개인정보를 제거한 후보 crop을 VLM으로 분석해 다음 구조화 정보를 생성한다.

- 화면 종류와 현재 탐색 단계
- 후보의 시각 라벨과 아이콘 종류
- 메뉴 기능과 위험 수준
- 최종 목적지 가능성
- 접근성·OCR·VLM 결과의 일치 여부
- 모델 버전, 분석 신뢰도와 사람 검증 여부

원본 이미지보다 구조화된 결과를 우선 보존한다. 지원 기간 종료 전에 필요한 DB, redacted crop과 평가 결과를 용량이 작은 형태로 반출한다. 기존 화면에 원본 또는 안전하게 가공된 이미지가 남아 있지 않으면 VLM으로 소급 분석할 수 없으므로 앞으로의 관찰 스키마에 시각 provenance를 포함한다.

## 안전 경계

- 자동 탐색은 보이고 활성화된 저위험 중간 메뉴에만 허용한다.
- 결제, 탈퇴, 해지 확정, 환불, 동의, 권한 변경, 토글, 체크박스, 라디오 버튼과 텍스트 입력은 자동 실행하지 않는다.
- 최종 목적지에 도착하면 탐색을 종료하고 최종 상태 변경은 사용자가 직접 수행한다.
- K-EXAONE과 VLM의 결과는 신뢰도와 근거를 기록하며, 화면과 후보를 식별할 수 없으면 추측 클릭 대신 중단 또는 복구한다.
- 민감 정보가 포함된 원본 스크린샷은 저장하지 않거나 저장 전 마스킹하며, 학습 자료에는 출처와 검증 상태를 남긴다.

## 현재 기반 현황

2026-08-02 운영 서버와 파생 학습 DB 기준으로 다음 연결이 실제 동작한다.

- 승인된 Human Gold 21개를 화면별 후보 선택 예제 92개와 선호 쌍 1,871개로 변환
- 앱 누수 방지 분할: train 64개(5개 앱), validation 23개(Netflix), test 5개(Google Play Store)
- 공식 AndroidControl 20개 shard에서 정규화한 83,848개 행동 단계
- AndroidControl SQLite FTS5와 64차원 의미 벡터 83,848개, `PRAGMA quick_check=ok`
- AndroidControl portable index SHA-256: `96d3d47e5e707da66cd5b57f1cc32ab2bade62b647e09d9a28a2b7a6d2875e71`
- Human Gold·기능 그래프·AndroidControl Top-K를 K-EXAONE 입력에 넣는 런타임 검색기
- 검색 후보·근거·모델 입력 해시·Hermes 출력·Python 안전 판정을 남기는 retrieval trace
- K-EXAONE의 후보 ID 기반 Hermes 행동과 fail-closed 실행 계약
- EXAONE 4.5 VLM 선택 호출, 후보 crop 좌표 매핑, 구조화 라벨 캐시와 개인정보 비저장 계약
- 실제 EXAONE 4.5 시각 smoke에서 YouTube 상단의 이름 없는 알림·검색 아이콘 2/2 식별
- 성공·실패·무변화·복구 기록을 `runtime → shadow → 자동 품질 검사 → verified_candidate → verified → trusted`로 관리하는 학습 큐와 기능 그래프 승격 게이트

제공된 K-EXAONE endpoint는 실제 inference와 Hermes 행동 생성에 사용된다. 2026-08-02 Friendli 공식 API 목록에는 inference, dataset, file, endpoint 관리 API는 있지만 해당 제공 모델의 가중치를 학습시키는 training/fine-tuning job API가 공개되어 있지 않다. 따라서 이 저장소는 K-EXAONE을 파인튜닝했다고 주장하지 않는다. 현재 방식은 검색 기반 in-context learning과 별도 학습 재랭커이며, 향후 파인튜닝에 바로 투입할 수 있도록 SFT·선호학습 자료와 앱 단위 분할을 보존한다.

## 현재 한계와 다음 개선 우선순위

1. Human Gold가 21개라 unseen 앱 평가의 절대 표본 수가 작다. 추가 Gold는 자동 평가에서 반복 실패가 확인된 기능만 선별한다.
2. EXAONE 4.5 VLM은 실제 이미지가 있는 화면에서만 평가할 수 있다. 기존 Gold 중 원본 이미지가 없는 단계에 시각 성능을 소급해 주장하지 않는다.
3. policy-only held-out 평가는 버튼 순서·동의어·무라벨·위험 decoy를 검사하지만, 실제 장기 trajectory와 제조사별 접근성 차이는 마지막 실기기 smoke로 따로 확인한다.
4. K-EXAONE endpoint 지연·타임아웃은 정확도와 탐색 시간을 함께 제한한다. Python이 대신 후보를 고르지 않고 중단하므로 안전성은 유지되지만 목적지 도달률이 낮아질 수 있다.
5. 다음 데이터 개선은 실패 유형별 재랭커 학습, 시각 provenance가 있는 redacted 평가 화면 확대, 앱 단위 held-out 확대 순으로 수행한다.

핵심 전환은 `Gold 좌표 경로 암기·재생`에서 `현재 화면 후보 분석 → 유사 경험 검색 → K-EXAONE 의미 판단 → 안전 실행 → 결과 재학습`으로 이동하는 것이다. 이 구조가 Gold가 없는 앱에서도 경험을 축적하며 개선되는 범용 Navigation Agent의 기준 구조다.
