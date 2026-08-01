# Public Dataset Inventory

이 문서는 ExitGuide 백엔드 약관/동의 데이터베이스 구축을 위해 확인한 공개 데이터셋 목록과 2026-07-15 현재 수집·정규화 결과를 기록한다.

원본 파일은 Git에 넣지 않는다. 자동 다운로드 결과는 `.artifacts/public-datasets/raw`, 사용자 수동 다운로드는 `Downloads`에 보존한다. 실행 결과와 정규화 출력은 `.artifacts` 아래에 남기고 저장소에는 adapter, 검증 코드, 인벤토리만 추적한다.

## 현재 결과 요약

- 인벤토리 소스: 23개
- 전문 변환 완료: 인벤토리 15개 + Open Terms Archive 전체본 1개
- 전문·조항·Q&A 출력: 18개 JSONL, 총 660,055레코드
- 전수 검증: JSON, 필수 필드, ID 유일성, 본문 SHA-256, 출력 SHA-256 모두 통과
- 메타데이터 전용: 3개
- 보조자료 구조화: MAPS URL 441,626건, GDPR 매핑 121행, FSDK 1,200,341행 profile
- 계정 원본 부재: Kaggle 1개, 동일 GitHub mirror 9,496건으로 대체
- 범위 미정 보류: Common Crawl/Internet Archive 1개
- 용도 분류: 전문 corpus 후보 12개, 별도 근거 2개, 평가 전용 2개, 수집 시드 4개, RAG 제외 2개
- 국내 약관 조항화: AI Hub 223,024 section, 공정위 1,703 section
- 생성형 AI 사용: 없음

정규화와 상태 분류는 스크립트로 자동 처리하고, 개발자가 manifest, 건수, 형식, 주요 표본을 확인했다. 모든 전문 출력은 아직 검색에 사용할 수 없는 `needs_review` 상태다.

## 전문 변환 결과

| 소스 | 형식 | 결과 |
| --- | --- | ---: |
| AI Hub 법률·규정 019 | XML + JSON | 문서 9,000 |
| Open Terms Archive contrib | Markdown ZIP | 최신 문서 874 |
| 공정거래위원회 표준약관 | HWP 81 + HWPX 12 | 문서 93 |
| 한국소비자원 표준상담 | CSV | 안내 1,332 |
| 공정위 소비자 민원 사례 | CSV | 안내 568 |
| ToS;DR Zenodo | CSV 관계형 데이터 | 문서 12,338 |
| ToS;DR GitHub mirror | TXT ZIP | 문서 9,496 |
| Hugging Face online ToS | JSONL | 조항 25,929 |
| OPP-115 / MAPP / OptOut 2017 / ACL | HTML·TXT·XML ZIP | 문서 1,394 |
| APP-350 | HTML + YAML | 문서 349, 조항 15,507 |
| OptOutChoice 2020 | SQLite + JSONL | 문서 688, 조항 1,151 |
| PrivacyQA | TSV형 CSV ZIP | Q&A 구간 247,350 |
| Princeton-Leuven | XZ 내부 SQLite | 본문 333,986, 시점 provenance 1,071,487 |

Princeton 원본 3.29GB는 48.2GB SQLite로 확장됐고, 고유 정책 행을 기준으로 만든 JSONL은 약 4.0GB다. 정규화 후 동일 본문은 6,005건이며 원본 행과 스냅샷 provenance는 유지했다.

AI Hub 원천 XML 162건은 선언 또는 태그가 손상되어 있었다. adapter는 76건의 선언을 복구하고, 85건을 의사-XML로 파싱했으며, 태그가 전혀 없는 1건은 원문 텍스트로 보존했다. 공정위 HWP는 제어 레코드를 제외하고 본문만 추출하도록 전량 재검증했다.

로컬 보고서:

- source 상태: `.artifacts/normalized-datasets/source-coverage.json`
- 전수 검증: `.artifacts/normalized-datasets/validation-summary.json`
- source별 manifest: `.artifacts/normalized-datasets/<source-id>/manifest.json`

## 용도 분류와 국내 약관 조항화

다운로드한 자료를 모두 “약관 조항”으로 취급하지 않는다. `fixtures/public-datasets/processing-roles.json`은 23개 인벤토리 소스와 Open Terms Archive 전체본을 다음 축으로 분류한다.

| 용도 | 처리 원칙 | 예시 |
| --- | --- | --- |
| `corpus_candidate` | 라이선스·개인정보·품질 검토 후 검색 후보 | AI Hub, 공정위 표준약관, ToS;DR, 개인정보처리방침 전문 |
| `supporting_evidence` | 약관 검색과 분리된 상담·분쟁 근거 인덱스 | 한국소비자원 상담, 공정위 민원 사례 |
| `evaluation_only` | 검색 품질 측정에만 사용 | PrivacyQA, 불공정 조항 분류셋 |
| `crawl_seed` | 실제 원문 수집 대상 URL로만 사용 | MAPS, Open Terms Archive 목록 |
| `source_metadata` | 출처와 구조 설명용 | API 문서, corpus 디렉터리 |
| `excluded_from_rag` | 약관 본문이 아니므로 제외 | FSDK telemetry, GDPR 매핑 보조자료 |

`Process-PublicCorpus.ps1`은 한국어 법률 조 번호를 규칙 기반으로 찾아 원문 offset을 보존한 section을 만든다. AI Hub 라벨은 NFKC·공백·구두점 정규화 후 정확 포함 관계를 우선 사용하고, 충분히 긴 표본만 문자 5-gram target recall 0.72 이상이면서 차점과 0.05 이상 차이가 날 때 연결한다. 애매한 결과는 연결하지 않는다.

| 소스 | 문서 | section | 라벨 연결 | 검토 대기 |
| --- | ---: | ---: | ---: | ---: |
| 공정위 표준약관 | 93 | 1,703 | 해당 없음 | 12 |
| AI Hub 019 약관 | 9,000 | 223,024 | 10,200개 중 4,916개 | 8,614 |

AI Hub의 남은 라벨 5,284개는 낮은 점수 4,875개, 짧은 표본 403개, 애매한 후보 6개로 자동 연결하지 않았다. section과 review queue는 `.artifacts/processed-corpus/<source-id>/`, 역할 보고서는 `.artifacts/processed-corpus/source-role-report.json`에 있다. 모든 section은 `needs_review`, `search_eligible: false`이며 자동 승인되지 않았다.

사람 검토용으로 정상·경계·실패 유형을 source별 최대 8건씩 뽑은 143건 패킷을 `.artifacts/review-packets/public-corpus-v1`에 생성했다. AI Hub 114건, 공정위 29건이며 검토 결정 열은 모두 비어 있다.

## 수집 정책

- 약관 전문, 개인정보처리방침 전문, 원문 CSV/ZIP/HWP/PDF는 Git에 커밋하지 않는다.
- 라이선스와 재배포 조건을 확인하기 전에는 원문 일부도 fixture로 승격하지 않는다.
- 한국 서비스 직접 크롤링은 이후 OpenClaw/manual capture 경로로 별도 수집하고, `docs/DATA_COLLECTION_POLICY.md`의 redaction/import 규칙을 따른다.
- 대용량 archive는 전체 mirror보다 도메인, 서비스군, 기간을 정한 타깃 수집을 우선한다.

## Codex가 직접 수집한 소스

| ID | 소스 | 내용 | 결과 | 로컬 기록 |
| --- | --- | --- | --- | --- |
| `ftc_standard_terms` | [공정거래위원회 표준약관 게시판](https://www.ftc.go.kr/www/selectBbsNttList.do?bordCd=201&key=202) | 국내 표준약관 첨부파일 | 수집 완료 | 104 files, 18.93 MB |
| `data_go_kr_kca_standard_answers` | [한국소비자원 표준상담 답변](https://www.data.go.kr/data/15144809/fileData.do) | 소비자 상담/분쟁 안내 데이터 | 수집 완료 | 3 files, 1.63 MB |
| `data_go_kr_ftc_consumer_model_cases` | [공정거래위원회 소비자 민원학습 데이터](https://www.data.go.kr/data/15098335/fileData.do) | 소비자 민원/상담 사례 데이터 | 수집 완료 | 3 files, 0.88 MB |
| `usableprivacy_opp_115` | [OPP-115](https://usableprivacy.org/data) | 웹 개인정보처리방침 115개와 주석 | 수집 완료 | 1 file, 94.51 MB |
| `usableprivacy_mapp` | [MAPP Corpus](https://usableprivacy.org/data) | 모바일 앱 개인정보 선호/정책 관련 corpus | 수집 완료 | 1 file, 2.19 MB |
| `usableprivacy_fsdk` | [FSDK](https://usableprivacy.org/data) | 개인정보 관련 SDK 보조 데이터 | 수집 완료 | 1 file, 4.42 MB |
| `usableprivacy_opp115_gdpr` | [OPP-115 GDPR annotations](https://usableprivacy.org/data) | OPP-115 GDPR 대응 주석 | 수집 완료 | 1 file, 0.08 MB |
| `usableprivacy_optoutchoice_2020` | [Opt-out Choice 2020](https://usableprivacy.org/data) | opt-out 선택지/동의 관련 데이터 | 수집 완료 | 1 file, 30.59 MB |
| `usableprivacy_app_350` | [APP-350](https://usableprivacy.org/data) | Android 앱 개인정보처리방침 350개와 주석 | 수집 완료 | 1 file, 7.11 MB |
| `usableprivacy_maps_policies` | [MAPS Policies Dataset](https://usableprivacy.org/data) | 모바일 앱 개인정보처리방침 URL 대량 색인 | 수집 완료 | 1 file, 16.11 MB |
| `usableprivacy_optoutchoice_2017` | [Opt-out Choice 2017](https://usableprivacy.org/data) | 이전 opt-out 선택지 데이터 | 수집 완료 | 1 file, 2.33 MB |
| `usableprivacy_acl_coling_2014` | [ACL/COLING 2014 corpus](https://usableprivacy.org/data) | 개인정보처리방침 corpus 및 보충 PDF | 수집 완료 | 2 files, 5.62 MB |
| `privacyqa_emnlp` | [PrivacyQA GitHub](https://github.com/AbhilashaRavichander/PrivacyQA_EMNLP) | 개인정보처리방침 Q&A corpus | 수집 완료 | 2 files, 10.54 MB |
| `tosdr_terms_corpus_github` | [ToS;DR terms corpus mirror](https://github.com/sonu-gupta/tosdr-terms-of-service-corpus) | ToS;DR 기반 약관 corpus mirror | 수집 완료 | 2 files, 129.84 MB |
| `tosdr_api_index` | [ToS;DR developer docs](https://docs.tosdr.org/developer), [legacy API docs](https://tosdr.github.io/tosdr.org/api.html) | ToS;DR API/legacy JSON 구조 문서 | 메타데이터 수집 완료 | 2 files, 0.32 MB |
| `tosdr_zenodo_raw_2023` | [Zenodo record 15012282](https://zenodo.org/records/15012282) | ToS;DR cases, topics, services, points, documents CSV | 수집 완료 | 6 files, 273.26 MB |
| `hf_online_terms_of_service` | [Hugging Face online_terms_of_service](https://huggingface.co/datasets/joelniklaus/online_terms_of_service) | 다국어 약관 불공정 조항 데이터 | 수집 완료 | 6 files, 9.26 MB |
| `opentermsarchive_datasets_page` | [Open Terms Archive datasets](https://opentermsarchive.org/en/datasets/) | 공개 terms archive directory와 GitHub org metadata | 메타데이터 수집 완료 | 2 files, 0.50 MB |
| `princeton_leuven_privacy_policies` | [Princeton-Leuven Longitudinal Corpus](https://privacypolicies.cs.princeton.edu/) | 대규모 longitudinal privacy policy corpus | 수동 원본 다운로드 및 전체 본문 변환 완료 | XZ 3.29 GB, SQLite 48.2 GB |
| `claudette_corpora_page` | [CLAUDETTE corpora](http://claudette.eui.eu/corpora/index.html) | 불공정 약관 조항 corpus directory | 메타데이터 수집 완료 | 1 file, 0.01 MB |

## 사용자 절차가 필요했던 소스

| ID | 소스 | 필요한 절차 | 이유 |
| --- | --- | --- | --- |
| `aihub_legal_regulation_terms` | [AI Hub 법률/규정 텍스트 분석 데이터](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=580) | AI Hub 로그인, 이용 신청, 약관 동의, 직접 다운로드 | 다운로드와 9,000건 정규화 완료. 재배포 조건은 별도 검토한다. |
| `kaggle_tosdr_terms_corpus` | [Kaggle ToS;DR terms corpus](https://www.kaggle.com/datasets/sonugpta/terms-of-service-corpus) | Kaggle 로그인 또는 API token | GitHub mirror를 우선 수집했고, Kaggle 원본은 계정 절차가 필요하다. |

## 대용량/타깃 수집 보류 소스

| ID | 소스 | 상태 | 처리 방침 |
| --- | --- | --- | --- |
| `common_crawl_wayback_privacy_terms` | [Common Crawl](https://commoncrawl.org/), Internet Archive | 공개 접근 가능하지만 전체 수집은 비효율적 | 서비스 domain list와 기간을 정한 뒤 필요한 약관/개인정보 URL만 추출한다. |

## 백엔드 활용 우선순위

1. AI Hub·공정위 review queue에서 구조 정상 문서 표본을 확인하고 라이선스·개인정보 상태를 구조화한다.
2. 승인 가능한 국내 section의 작은 1차 corpus를 만들되 전체 일괄 승인은 하지 않는다.
3. 한국소비자원·공정위 사례를 국내 해지·환불 retrieval 평가 질문의 근거 후보로 쓴다.
4. 승인 corpus로 FTS5 기준선과 `Recall@5`, MRR, 출처 일치율을 측정한다.
5. Open Terms Archive와 MAPS URL은 실제 서비스 수집 target seed로 사용한다.

## 재실행

```powershell
.\scripts\Collect-PublicDatasets.ps1
```

메타데이터 수집만 확인할 때:

```powershell
.\scripts\Collect-PublicDatasets.ps1 -MetadataOnly
```

수동 다운로드 원본을 다시 정규화하고 전수 검증할 때:

```powershell
.\scripts\Convert-PublicTermsDatasets.ps1
```

국내 약관 조항화와 review queue를 재생성할 때:

```powershell
.\scripts\Process-PublicCorpus.ps1
.\scripts\New-PublicCorpusReviewPacket.ps1
```
