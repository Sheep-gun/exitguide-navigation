# K-EXAONE endpoint 기능 감사

기준일: 2026-08-02

## 결론

현재 제공된 K-EXAONE endpoint는 OpenAI 호환 chat completion과 Hermes tool call을 생성하는 **추론 endpoint**로 정상 사용한다. ExitGuide의 agent-only 평가에서도 실제 모델 호출과 구조화 행동 생성이 확인됐다.

반면 현재 공개된 Friendli API 목록과 제공 endpoint 응답에서는 이 K-EXAONE 배포의 가중치를 학습하는 training/fine-tuning job 기능을 확인하지 못했다. 따라서 ExitGuide는 K-EXAONE을 파인튜닝했다고 주장하지 않는다.

현재 구현은 다음 세 층으로 구분한다.

1. K-EXAONE: 매 화면의 현재 후보와 검색 근거를 보고 Hermes 다음 행동 생성
2. 검색 기반 in-context learning: Human Gold·기능 그래프·AndroidControl Top-K 제공
3. 로컬 policy reranker: Human Gold의 positive/negative 선호 쌍으로 학습한 경량 후보 정렬기

3번은 K-EXAONE 가중치 학습이 아니다. K-EXAONE은 재랭커가 줄인 실제 후보 목록에서도 최종 행동을 직접 결정한다.

## 확인 근거

- Friendli 공식 문서 인덱스: <https://friendli.ai/docs/llms.txt>
- API reference: <https://friendli.ai/docs/openapi/introduction>
- Model API tool calling: <https://friendli.ai/docs/guides/tool-calling>
- Dedicated endpoint API: <https://friendli.ai/docs/openapi/dedicated/overview>
- Dataset API: <https://friendli.ai/docs/openapi/dataset/overview>

2026-08-02 공식 인덱스에는 Model API·Dedicated·Container의 추론, Dataset·File 관리, endpoint 배포·버전 관리가 열거되어 있다. Dataset 설명은 향후 학습 자료 관리 용도를 포함하지만, 제공 K-EXAONE 배포에 대해 학습 job을 생성하고 완료된 checkpoint를 연결하는 공개 training/fine-tuning endpoint는 목록에 없다.

비밀값을 출력하지 않는 읽기 전용 probe도 수행했다. 제공 inference base URL의 `models`, `fine_tuning/jobs`, `fine-tuning/jobs`에 GET/OPTIONS를 보냈을 때 모두 동일한 JSON 역직렬화 400 응답을 반환했다. 이 gateway 응답만으로 경로 부재를 단정하지는 않으며, 공개 API 목록에 학습 계약이 없다는 사실과 함께 보수적으로 판단한다. 실제 chat completion과 Hermes 호출은 별도 평가에서 성공했다.

## 준비된 향후 학습 산출물

- SFT 화면별 행동 예제 92개
- 선호학습 positive/negative 쌍 1,871개
- 앱 단위 train·validation·test 분할
- 현재 화면 후보, 정답·오답, 행동 결과, 예상 다음 기능, 위험도
- 데이터·스키마 버전과 source recording provenance

향후 대회 측이 K-EXAONE 학습 API나 학습 가능한 checkpoint를 제공하면 새 학습 job을 별도 버전으로 만들고, 기본 모델과 튜닝 모델을 동일한 leakage-controlled agent-only 세트에서 비교한다. 그 전까지 모델 학습이라는 표현은 위 경량 재랭커에만 한정한다.
