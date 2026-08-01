# ExitGuide Roadmap

이 로드맵은 앱 완성도가 아니라 **검수 가능한 약관·동의 데이터베이스와 근거 기반 판단 체계**를 기준으로 우선순위를 정한다.

## 현재 판단

Android 앱과 FastAPI 데모는 제품 가설을 시험하기에 충분하다. 현재 가장 큰 위험은 데이터 부족 자체보다, 수집된 원본이 사용자 안내에 사용 가능한 corpus로 승격되는 과정이 아직 이어지지 않았다는 점이다.

확인된 구조적 간극:

1. 공개 전문·조항·Q&A 18개 출력 660,055건은 공통 JSONL로 정규화됐지만 terms corpus API는 여전히 합성 문서 3개만 검색한다.
2. AI Hub·공정위 조항 분할과 review queue는 완성됐지만, 라이선스·개인정보 검토를 통과한 운영 corpus는 아직 없다.
3. source/version/review audit와 `approved_for_search` 검색 gate는 구현됐으며, 다음 병목은 실제 검토와 소규모 승인 corpus 구성이다.
4. 현재 quality endpoint의 `pass`는 합성 seed coverage를 뜻하며 운영 corpus의 정확도나 안전성을 뜻하지 않는다.
5. consent case 14개는 규칙 calibration용이며 retrieval, OCR, provider 평가셋과 분리해야 한다.
6. 공개 데이터는 영어·다국어 비중이 높지만 현재 terms importer는 `ko-KR`만 허용한다.

따라서 다음 순서는 `대량 파싱 → RAG`가 아니라 `정규화 → 검수 → 검색 기준선 → 수집 확장 → 화면 분석 연결`이다.

## 완료된 기반

- [x] Android-first Expo 앱과 FastAPI API
- [x] 단일 화면 및 2-6장 화면 흐름 분석
- [x] deterministic mock/rule baseline과 합성 화면 15개
- [x] consent calibration case 14개
- [x] 합성 terms 문서·section·chunk·signal 구조
- [x] SQLite/FTS5 corpus builder와 lexical search 함수
- [x] OpenClaw/manual capture JSON importer
- [x] content hash 중복 제거와 source/version 기록
- [x] 서비스·문서·해지 흐름·review task registry seed
- [x] 공개 데이터 소스 23개 인벤토리와 20개 소스 원본 수집
- [x] AI Hub 019 약관 9,000건과 Open Terms Archive 최신본 874건 정규화
- [x] 공정위·공공데이터·ToS;DR·UsablePrivacy·PrivacyQA adapter 구현
- [x] Princeton 본문 333,986건과 스냅샷 provenance 1,071,487건 변환
- [x] 전문·조항·Q&A 18개 출력 660,055건 전수 hash 검증
- [x] 24개 source의 데이터 형식·처리 역할·RAG 정책 분류
- [x] AI Hub·공정위 9,093문서를 224,727개 section으로 조항화
- [x] 조항 품질 보고서와 annotation/문서 구조 review queue 생성
- [x] 정상·경계·실패 유형별 결정적 사람 검토 패킷 143건 생성
- [x] 검토 CSV/source 이용 조건 validator와 content-hash 검증
- [x] 통과 section을 검색 비노출 `pending_review` registry로 옮기는 dry-run/apply importer
- [x] current `approved_for_search` version만 검색하는 SQLite gate와 review audit CLI
- [x] 메타데이터 전용·보조자료·원문 부재·대용량 보류 상태 보고서 생성
- [x] streaming ZIP adapter, 안정 ID, 입력/출력 hash, 전수 JSONL 검증
- [x] Solar Pro 3 데모 workflow 6개 저장
- [x] API, unit, OpenAPI, docs, mobile, web, archive 검증 루틴

## Phase 1: 공통 정규화 계층

우선순위: **P0, 다음 구현 블록**

목표는 모든 collector와 공개 데이터 adapter가 같은 staging record를 생성하게 만드는 것이다.

- [x] 문서 단위 canonical staging schema 1.0 정의
- [ ] `source`, `document`, `version`, `section`, `annotation`, `license` 경계 분리
- [ ] `locale`과 원문 언어를 보존하고 사용자 검색 언어와 분리
- [x] ZIP을 압축 해제하지 않고 streaming 처리하는 adapter 기반 추가
- [x] adapter output을 `.artifacts/normalized-datasets/<source-id>/`에 재현 가능하게 저장
- [ ] adapter version과 수집 시각을 staging record에 추가
- [x] 원본·출력 hash, source URL, archive entry provenance 기록
- [x] AI Hub XML/JSON adapter 구현
- [x] Open Terms Archive Markdown 최신본 adapter 구현
- [x] 한국소비자원 상담 답변 adapter 구현
- [x] ToS;DR 2023 CSV adapter 구현
- [x] OPP-115와 관련 UsablePrivacy adapter 구현
- [x] 공정거래위원회 HWP/HWPX parser 구현 및 전량 변환
- [x] Princeton 대용량 SQLite streaming adapter 구현
- [x] AI Hub·공정위 한국어 조 번호 sectioning과 원문 offset 보존

완료 기준:

- 서로 다른 형식의 소스 3개 이상이 같은 schema로 변환된다.
- 초기 100개 이상 문서가 batch 재실행 시 같은 ID와 hash를 만든다.
- 필수 provenance 누락과 금지 개인정보 패턴이 0건이다.
- 실패 record는 성공 record와 분리되고 원인을 재현할 수 있다.

## Phase 2: Review와 검색 승인 gate

우선순위: **P0**

목표는 수집 성공과 사용자 안내 사용 승인을 분리하는 것이다.

- [ ] 문서 상태 machine 구현
- [x] `pending_review`, `approved_for_search`, `rejected_*`, `deprecated` 검색 상태 정의
- [x] 상태 결정 reason, reviewer, event 시각 audit 저장
- [ ] structured license 상태 추가: `unknown`, `research_only`, `redistributable`, `blocked`
- [ ] 개인정보·secret·session·거래 식별자 검사 결과 저장
- [ ] 현재 version과 superseded version 조회 구현
- [x] `approved_for_search`인 current version만 검색 table에 반영
- [x] CLI로 review 결정을 기록
- [x] fixture 공개 승격과 로컬 검색 승인을 별도 권한으로 분리

완료 기준:

- pending/rejected/deprecated 문서는 검색 결과에 나타나지 않는다.
- 승인과 거절의 대상 version, 사유, 시각을 모두 재현할 수 있다.
- importer 입력의 `public_fixture_allowed` 값이 승인 결과를 바꾸지 못한다.
- review gate 회귀 테스트가 SQLite와 API 경로를 함께 검증한다.

## Phase 3: Retrieval 기준선과 평가셋

우선순위: **P1**

목표는 RAG 도입 전에 현재 검색 품질을 숫자로 알 수 있게 만드는 것이다.

- [ ] `/v1/terms-corpus/search`를 승인된 SQLite corpus에 연결
- [ ] fixture-only demo 검색과 운영 corpus 검색 mode 분리
- [ ] corpus와 겹치지 않는 질문-근거 gold set 작성
- [ ] 한국어 해지·환불·자동갱신·선택동의·계정삭제 query 최소 30개 구성
- [ ] `Recall@5`, `MRR`, source/version 일치율 측정
- [ ] 검색 결과에 source URL, document version, section ID, content hash 포함
- [ ] lexical FTS5 baseline 기록
- [ ] 필요할 때만 vector search와 reranker를 같은 평가셋으로 비교
- [ ] 근거 없음과 검색 실패를 명시적으로 반환

완료 기준:

- 모든 검색 결과가 원문 section과 provenance로 역추적된다.
- 동일 corpus/version에서 평가 결과가 재현된다.
- vector/LLM 도입 여부가 감이 아니라 baseline 대비 개선으로 결정된다.
- gold set에서 출처에 없는 사용자 조언이 0건이다.

## Phase 4: OpenClaw 서비스별 수집

우선순위: **P1**

목표는 실제 한국 서비스의 공개 약관과 해지 안내를 같은 intake 경로로 누적하는 것이다.

- [ ] OpenClaw capture contract를 canonical staging schema에 맞춤
- [ ] 실제 서비스 registry와 우선순위 score 작성
- [ ] 약관, 개인정보처리방침, 환불 정책, 도움말, 해지 안내를 문서 유형별 수집
- [ ] robots/접근 정책, rate limit, retry, timeout 기록
- [ ] login/captcha/blocked/partial 상태를 성공과 분리
- [ ] content hash 기반 변경 감지와 새 version 생성
- [ ] 자동 수집 실패 대상의 manual capture 절차 제공
- [ ] 우선 서비스 10개로 end-to-end pilot 수행

완료 기준:

- collector 종류와 무관하게 같은 review queue로 들어온다.
- 재수집 시 변경된 문서만 새 version으로 생성된다.
- 차단·부분 수집을 완전한 문서로 오인하지 않는다.
- 실제 서비스 문서가 승인 전 검색과 앱 분석에 노출되지 않는다.

## Phase 5: 화면 분석과 근거 결합

우선순위: **P2**

목표는 화면 판단이 관련 약관 section을 근거로 제시하도록 만드는 것이다.

- [ ] 화면 신호를 retrieval query로 변환
- [ ] 서비스, 문서 유형, locale, 최신 version filter 적용
- [ ] 분석 응답에 evidence section과 citation 필드 추가
- [ ] rule 결과와 retrieved evidence의 충돌 처리
- [ ] 근거 부족 시 추측 대신 `needs_check` 반환
- [ ] Solar Pro는 애매한 section 분류·요약에 제한적으로 사용
- [ ] model output schema validation과 unsupported-claim 검사
- [ ] end-to-end 평가 case 최소 20개 구성

완료 기준:

- 안내의 핵심 문장마다 화면 또는 문서 근거가 연결된다.
- 모델을 끄더라도 lexical search와 rule 기반 기본 안내가 동작한다.
- provider 실패가 조용한 fallback이 아니라 명확한 상태로 노출된다.
- 평가셋에서 법적 단정과 출처 없는 권리 주장이 0건이다.

## Phase 6: 제품 확장

우선순위: **P3, 데이터 경로 안정화 이후**

- [ ] 모바일 tab/component 분리와 navigation 정리
- [ ] 실제 Android APK 회귀 테스트
- [ ] share sheet 기반 화면 전달
- [ ] 서비스별 해지/동의 흐름 지도
- [ ] Proof Card의 근거 citation 표시
- [ ] browser extension 또는 desktop capture companion 검토
- [ ] 반복 패턴의 local classifier/on-device rule 실험
- [ ] 개인정보 저장 정책 확정 후 사용자 선호 개인화 검토

## 다음 세 작업 블록

1. 생성된 143건 체크리스트를 사람이 확인하고 license·privacy·parse·annotation 상태를 작성한다.
2. 검토 완료 section을 validator로 확인하고 dry-run 후 작은 국내 corpus를 pending registry에 넣는다.
3. 승인 corpus와 분리된 gold 질문을 만든 뒤 lexical retrieval의 `Recall@5`, MRR, 출처 일치율을 기록한다.

각 블록은 코드, 재생성 script, fixture 또는 작은 sample, unit test, 문서 갱신을 함께 완료해야 한다.

## 당분간 하지 않을 것

- 전체 원본을 무조건 vector DB에 넣기
- 대량 문서를 처음부터 전부 LLM으로 파싱하기
- review 없이 실제 사이트 문서를 공개 fixture로 승격하기
- raw dataset을 main Git history에 직접 넣기
- 앱 디자인 polish를 데이터 품질보다 먼저 진행하기
- 특정 회사가 불법 또는 악의적이라고 단정하기
