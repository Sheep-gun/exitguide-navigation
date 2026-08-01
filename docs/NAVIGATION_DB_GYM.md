# Navigation DB Gym

Navigation DB Gym은 휴대폰을 연결하지 않고도 ExitGuide의 범용 메뉴 DB를 반복 평가·개선하는 로컬 테스트 벤치다. 특정 앱의 좌표나 고정 경로를 정답으로 외우는 대신, 사용자 목적·화면 단계·버튼 별칭·주변 문맥·안전 정책을 교차 검증한다.

## 데이터 구조

검토 가능한 원본은 `fixtures/navigation/function-catalog.v1.json`이다. API는 원본의 버전과 SHA-256이 달라지면 다음 정보를 SQLite 런타임 인덱스로 다시 만든다.

- 기능 정의: 기능 ID, 설명, 위험도, 자동화 정책, 최종 목적지 여부
- 별칭: 한국어·영어 메뉴 이름과 표기 변형
- 문맥: 같은 이름을 구분하는 긍정·부정 문구
- 목적 패턴: 사용자의 직접적인 목적 표현
- 목적 조합 규칙: `계정+없애`, `활동+기록+지우`처럼 자연어 문장에서도 동작하는 복수 단서
- 기능 그래프: 목적별로 가능한 공통 관문과 중간 기능
- 회피 기능: 콘텐츠 구독과 유료 구독처럼 혼동하면 안 되는 분기

SQLite 파일은 `.artifacts/` 아래 생성되는 캐시다. 직접 수정하지 않고 항상 JSON 원본을 수정한다.

## 평가 분할

| 분할 | 목적 | 수정 원칙 |
|---|---|---|
| development | 검토된 공통 메뉴와 자동 생성 변형 | 기능 추가와 함께 확장 가능 |
| public_web | 서비스 운영사의 공식 도움말에서 확인한 실제 메뉴 경로 | 출처 URL·수집일·앱/플랫폼을 유지하고 의미 단위로만 정규화 |
| public_insurance | 국내 보험사·국민건강보험공단의 공식 메뉴와 업무 흐름 | 청구·납입·대출·해지·사고/출동 등은 실행 직전 정지하고 실제 단말에서 재검증 |
| public_productivity_system | Google 공식 도움말에서 확인한 Gmail·Calendar·Maps·Android 기능 흐름 | 공식 문서의 기능명과 순서만 정규화하고 좌표·개인정보는 저장하지 않음 |
| independent_core | 앱·Android·계정·결제·콘텐츠 등 수작업 독립 표현 | 카탈로그 문장을 복사하지 않고 화면 상태와 안전 경계를 함께 고정 |
| alias_collision_adversarial | 같은 단어가 서로 다른 기능을 뜻하는 충돌 화면 | 목적·범위·상태 문맥으로 구분하고 위험 자동 클릭은 항상 0% 유지 |
| independent_coverage | 카탈로그의 모든 목적·기능 참조를 외부 표현으로 덮는 커버리지 팩 | 새 기능을 추가하면 독립 증거도 함께 추가하여 100% 참조 커버리지 유지 |
| independent_recovery | 오류·오프라인·인증·WebView·무한피드·아이콘·스크롤·뒤로가기 | 일시 상태에서 복구한 뒤에도 최종 동작은 사용자에게 남김 |
| independent_long_tail_v3 | 생산성·통신·지도·공공·금융·안전·건강 등 v3 장기꼬리 기능 | 221개 목적과 239개 기능을 독립 표현과 다단계 화면으로 검증 |
| independent_broad_services_v4 | 브라우저·메시지·통화·스토어·Android·교통·쇼핑·의료·구직·부동산·공공요금 | 163개 신규 목적과 179개 기능을 혼동 선택지·상태·안전 경계와 함께 검증 |
| independent_service_gaps_v5 | 음식주문·식당예약·숙박·항공탐색·티켓·승차호출·소매금융·전자정부·의료기관·업무관리·택배 | 136개 신규 목적과 147개 기능을 별도 작성한 한·영 표현, 복구 상태, 사용자 최종 클릭 경계로 검증 |
| independent_open_world_v6 | 차량·주차·인사급여·피트니스·가정서비스·민원·반려동물·식료품 멤버십 | 113개 신규 목적과 121개 기능을 452개 다단계 화면으로 검증 |
| independent_long_tail_v7 | 데이팅·전자도서관·뷰티예약·보육·전자서명·크리에이터·가상자산·스포츠팀 | 120개 신규 목적과 128개 기능을 480개 단계, 18개 UI 표면, 16개 상태로 검증 |
| independent_enterprise_ops_v8 | 자격증명·회계·CRM·상담티켓·POS/재고·현장공사·기사배차·장애온콜 | 138개 목적을 한·영 각각 평가한 276개 사례와 1,104개 단계로 146개 기능 전체를 검증 |
| independent_cross_domain_v9 | 코드 저장소·모임·후원·공용 EV 충전·식단·번역·운전자 규정·숙박 호스트·출입관리·농업 운영 | 184개 목적을 한·영 각각 평가한 368개 사례와 1,472개 단계로 194개 기능 전체를 검증 |
| independent_operational_v10 | 임대관리·창고·설비정비·제조품질·연구실·교사업무·법률실무·식당운영·돌봄·가정에너지·가계도·조달 | 218개 목적을 평가한 218개 사례와 872개 단계로 230개 기능 전체를 검증 |
| independent_critical_ops_v11 | 임상진료팀·약국조제·보험손해사정·항공승무·통신현장·ITSM/CMDB·보안관제·사회복지·상속재산·항만물류·임상시험·재난대응 | 230개 목적을 평가한 230개 사례와 920개 단계로 242개 기능 전체를 검증 |
| independent_specialized_ops_v12 | 수의·치과·재가진료·항공정비·철도·통관·전력망·폐기물·광산안전·선거·연구과제·교정 사례관리 | 240개 목적을 평가한 240개 사례와 960개 단계로 252개 기능 전체를 검증 |
| independent_regulated_systems_v13 | 혈액·장기이식·방사선치료·법원·IP 도켓·식품검사·건축허가·상하수도·원전·파이프라인·박물관·항공교통관제 | 240개 목적을 평가한 240개 사례와 960개 단계로 252개 기능 전체를 검증 |
| independent_institutional_systems_v14 | 진단검사실·수술실·의료수익주기·주택담보대출·금융범죄준수·대학학사·인체연구감독·긴급통신배차·공중보건감시·발전소·토지등기·우편망 | 960개 사례와 960개 최종 경계 단계로 240개 목적과 252개 기능 전체를 검증 |
| independent_authority_systems_v15 | 공항 에어사이드·연방 기록 처분·DOJ FOIA·댐 안전·NLRB 대표 사건·특수교육·연금·선거자금·수출통제·방송국 준수·앱스토어 릴리스·도메인 등록 | 960개 사례와 960개 경계 단계로 240개 목적과 252개 기능을 검증하며, 840개 `stop`·120개 `no_click` 및 최종 위험 클릭 0회를 강제 |
| holdout | 자연스러운 우회 표현과 여러 단계 경로 | `frozen=true`; 점수를 올리기 위해 정답 문장을 그대로 추가하지 않음 |
| adversarial | 광고, 동음이의어, 유사 버튼, 위험 최종 동작 | 실패 유형을 일반 규칙으로 고침 |
| real-device-gold | 실제 단말에서 사람이 확인한 화면·경로 | 개인정보를 제거한 뒤에만 추가 |

현재 canonical은 v15(`catalog_version = 15.0.0`, SHA-256 `e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24`)로, 179개 영역·2,866개 물리 기능·2,660개 물리 intent를 포함한다. [기능 동등성 감사](NAVIGATION_FUNCTION_EQUIVALENCE_AUDIT.md)의 오버레이를 적용하면 2,856개 논리 기능·2,650개 논리 intent이며, canonicalize한 고유 default terminal은 2,648개다.

다음 확장 후보 v16은 canonical과 분리된 `navigation_catalog_v16_data.py`에서만 생성한다. 12개 신규 영역의 hub 12개·terminal 240개·intent 240개로 구성되고, 민감 조회 84개와 결과 변경 156개를 구분한다. 검증된 공식 1차 URL 127개를 모든 terminal에 연결해 고아 출처는 0개이며, 근거가 약했던 명칭 16개를 정제 문서의 새 ID로 정확히 교체했다. 의미 1,440개·충돌 720개·복구 960개·역할/자산 격리 720개 프로브와 기존 v15 equivalence 충돌 0개를 통과했다. 격리 병합 예상치는 191개 영역·3,118개 기능·2,900개 intent지만, 별도 봉인 독립 팩과 전체 과거 회귀가 끝나기 전에는 canonical로 승격하지 않는다.

`independent-evidence-systems-v16.json`은 후보 구현과 분리해 작성한 960개 봉인 사례다. 한·영 positive 각 240개가 240개 terminal을 정확히 두 번씩 덮고, 이전 세대와의 충돌 240개, v16 내부 충돌 120개, 권한·대상·관할·상태·승인 등이 부족한 안전 기권 120개를 포함한다. 전 사례는 `tuning_allowed=false`, 위험 정답 클릭 0, 자동 최종 실행 0, 사용자 최종 실행 경계를 사용한다. 대표 목표·production 별칭/패턴/goal-rule의 exact·장문 포함·고유사도 복사와 내부 ID·좌표·고정 UI 경로 누출을 별도 검사하며, 현재 Git 원본 문서 SHA를 반영한 canonical seal은 `5b319eb660d59b7f586e69908c469f91d101661f48cd74c13252746a06b4465d`이다.

v15 `full` 실행은 2,660개 목적 각각에 대해 별칭, 언어, UI 역할, 버튼 순서, 안전한 유사 메뉴를 결정론적으로 변형한다. 이 자동 변형은 모두 원본 카탈로그에서 파생되므로 독립 정확도로 주장하지 않는다. 의도적인 의미 충돌은 자동 생성 세트가 아니라 adversarial 세트에서 관리한다. 목적·기능 수는 카탈로그 확장에 따라 증가하므로 보고서의 `catalog_stats`를 최종 기준으로 삼는다.

`development-goal-paraphrase-exhaustive-v1`은 모든 2,660개 intent를 한국어·영어로 한 번씩 문장화한 5,320개 카탈로그 파생 개발 사례다. 역할·대상·상태·행동·도착 조건을 8개 문장 구조에 균등 배치하며, 정규화 길이 4 이상인 별칭·목적 패턴의 직접 복사와 단순 감싸기, 중복, 불투명 대체문을 금지한다. 짧아서 일반 문장과 충돌하기 쉬운 1~3자 원문이 남은 사례 89개와 resolver `goal_rules` 어휘가 action에 남은 사례 4,366개는 별도 결합도 지표로 공개하고 상한 회귀 gate를 적용한다. 2026-07-30 기준 resolver 진단은 정답 253개, 안전한 generic 1,300개, 오답 3,767개이고 카탈로그 정책 자체의 안전 위반은 0개다. 보호 경계가 필요한 목적이 잘못된 비보호 기능으로 해석된 845개는 실행된 위험 클릭이 아니라 **목적 판정 경계 불일치**로 별도 집계하며 이 수도 증가하지 못하게 한다. 이 낮은 수치는 넓은 장문 일반화 공백을 드러내는 **카탈로그 결합 튜닝용 기준선**이며 독립 표현 일반화 정확도 증거가 아니다. 생성 결정성·금지 복사·전체 intent/언어/문장군 커버리지·위험 기능의 `never_auto` 경계와 resolver 처리량을 매 피드백 주기에서 함께 검사한다.

공식 문서와 수작업 독립 팩 20개를 합치면 현재 4,645개 케이스·12,007개 단계가 2,660개 목적과 2,866개 물리 기능을 모두 한 번 이상 참조한다. 한국어·영어, click·scroll·back·stop·no-click, screen·dialog·drawer·bottom sheet·WebView·scroll view·무한 피드·시스템 dialog, 로딩·오프라인·오류·재로그인·권한·복구·확인 필요 상태를 포함한다. 이 커버리지는 “경우의 수가 독립 데이터에 표현되어 있다”는 증거이며, 에이전트가 그 경로를 성공했다는 뜻은 아니다. 성공률·Top-1·목적지 판정은 동일한 케이스를 실제로 실행한 DB Gym 지표로 별도 측정한다.

`fixtures/navigation/db-gym/public-web.v1.json`에는 18개 공식 도움말 출처에서 정규화한 12개 서비스, 19개 경로, 73개 화면 단계가 있다. YouTube·Netflix·Spotify의 구독/재생/기록과 Instagram·TikTok·X·Uber·LinkedIn·Reddit·Discord·Snapchat·Google의 계정 삭제·데이터 다운로드 경로를 포함한다. 웹 문서는 UI 좌표의 영구 정답이 아니라 실제 서비스 용어와 기능 순서를 보강하는 증거이며, 앱 업데이트 후에는 공식 문서와 실제 단말 gold를 다시 대조한다.

`fixtures/navigation/db-gym/public-insurance.v1.json`에는 KB손해보험·삼성화재·DB손해보험·현대해상·교보생명·국민건강보험공단의 공식 안내 17개에서 정규화한 27개 보험 업무 경로, 46개 화면 단계가 있다. 공통 기능 그래프는 계약조회·변경·해지, 보험금 청구·처리현황·필요서류, 보험료 납입, 증명서·보험증권, 해지환급금, 계약대출, 사고접수·고장출동, 지점, 보장분석, 건강보험 자격·검진·환급을 구분한다. 문서 기반 메뉴는 좌표가 아니며 실제 앱 버전 검증 전에는 `documented.*` 서비스 식별자로 유지한다.

`fixtures/navigation/db-gym/public-productivity-system.v1.json`에는 Google 공식 1차 문서 29개에서 정규화한 Gmail·Calendar·Maps·Android 경로 55개와 화면 단계 176개가 있다. 한국어 28개·영어 27개이며, 최종 상태 변경이나 위험 기능을 정답 클릭으로 둔 케이스는 0개다. 공식 문서는 기능 의미와 공개된 메뉴 흐름의 근거이지 현재 단말 UI 좌표나 접근성 트리의 증거는 아니다.

`fixtures/navigation/db-gym/independent-broad-services-v4.json`은 163개 사례·652단계로 v4 신규 목적 163개와 신규 기능 179개를 모두 덮는다. 같은 도메인의 혼동 선택지, 아이콘 전용·비활성·비가시 요소, drawer·sheet·dialog·WebView·스크롤, 로그인·오프라인·로딩·권한·오류·복구 상태를 포함하며 위험·상태 변경 목적지 131개는 모두 최종 활성화 전에 멈춘다.

`fixtures/navigation/db-gym/independent-service-gaps-v5.json`은 136개 사례·544단계로 v5 신규 목적 136개와 신규 기능 147개를 모두 덮는다. 한국어·영어를 68개씩 포함하고, 107개 위험·상태 변경 목적은 전부 최종 클릭 전에 `no_click`으로 멈춘다. 이 팩은 `tuning_allowed=false`인 평가 전용 자료다. 실패 문장·정답 라벨은 자동 제안이나 K-EXAONE 분석 입력에서 제외되며, 점수는 일반화 공백을 드러내는 용도로만 사용한다.

`fixtures/navigation/db-gym/independent-open-world-v6.json`은 113개 사례·452단계로 v6의 113개 목적과 121개 기능을 덮는다. `fixtures/navigation/db-gym/independent-long-tail-v7.json`은 120개 사례·480단계로 v7의 120개 목적과 128개 기능을 덮는다. 두 팩 모두 `frozen=true`, `tuning_allowed=false`이며 위험 최종 동작을 정답 클릭으로 두지 않는다.

`fixtures/navigation/db-gym/independent-enterprise-ops-v8.json`은 v8의 138개 목적을 한국어와 영어로 각각 한 번씩 평가한 276개 사례·1,104단계다. 146개 기능, 18개 UI 표면, 18개 변형, 16개 화면 상태를 모두 참조하고 위험 최종 단계 274개는 전부 `stop` 또는 `no_click`이다. SHA-256으로 봉인되며 별칭·패턴·규칙 문장의 복사 여부도 별도 단위 검사에서 거부한다.

`fixtures/navigation/db-gym/independent-cross-domain-v9.json`은 v9의 184개 목적을 한국어와 영어로 각각 한 번씩 평가한 368개 사례·1,472단계다. 194개 기능과 12개 UI 표면을 모두 참조하고 결과를 바꾸는 최종 단계 338개는 전부 `stop` 또는 `no_click`이다. 위험 요소를 정답 클릭으로 둔 사례는 0개이며, 별칭·목적 패턴·규칙 문장의 복사와 근접 복사를 단위 검사에서 거부한다.

`fixtures/navigation/db-gym/independent-operational-v10.json`은 v10의 218개 목적을 한·영 균형 표현으로 평가한 218개 사례·872단계다. 신규 허브 12개와 terminal 218개를 포함한 기능 230개를 모두 참조하고, 12개 UI 표면·13개 화면 상태·4개 전환 유형을 포함한다. 복구 단서와 역할 반전 단서는 각각 654개, 동음이의 메뉴 방해 선택지는 218개이며, 위험 요소의 정답 클릭은 0개다. 최종 동작은 전부 `stop` 또는 `no_click`으로 사용자에게 남긴다.

`fixtures/navigation/db-gym/independent-critical-ops-v11.json`은 v11의 230개 목적을 한·영 균형 표현으로 평가한 230개 사례·920단계다. 신규 허브 12개와 terminal 230개를 포함한 기능 242개를 모두 참조한다. 16개 UI 표면·17개 화면 상태·4개 전환 유형을 포함하고, 복구 단서 1,840개, 잘못된 역할·기록 단서 1,380개, 동음이의 방해 선택지 230개를 제공한다. 위험 요소의 정답 클릭은 0개이며 최종 행동은 115개 `stop`과 115개 `no_click`으로 모두 사용자에게 남긴다.

`fixtures/navigation/db-gym/independent-specialized-ops-v12.json`은 v12의 240개 목적을 한·영 균형 표현으로 평가한 240개 사례·960단계다. 신규 허브 12개와 terminal 240개를 포함한 기능 252개를 모두 참조한다. 20개 UI 표면·23개 화면 상태·8개 전환 유형, 복구 단서 2,160개, 잘못된 역할·기록 방해 선택지 1,680개, 동음이의 방해 선택지 480개를 포함한다. 위험 요소의 정답 클릭은 0개이며 최종 행동은 120개 `stop`과 120개 `no_click`으로 모두 사용자에게 남긴다. 원본 카탈로그와 독립 세트는 서로의 문구를 공유하지 않고 ID·고정 안전 정책만 별도 계약 검사로 대조한다.

`development-goal-char-retrieval.v1.json`은 기존 resolver가 보류한 자연어 목적을 위한 경량 문자·단어 TF-IDF 검색기의 개발용 안전 gate다. 검색기는 후보별 176개 feature, feature별 64개 posting, 질의별 144개 feature, 512개 캐시로 상한을 고정하고 부정문을 절대 채택하지 않는다. v15에서는 후보 2,690개, feature 163,017개, posting 441,679개를 인덱싱하며 전용 검사에서 cold build 16.98초, warm p95 1.7ms, 추정 인덱스 83,235,833바이트, 관측 peak 173,574,994바이트였다. 개발 세트에서 채택한 4개 후보는 모두 정답이었다. 이 검색기는 독립 정확도나 실제 단말 정확도의 근거로 사용하지 않는다.

`fixtures/navigation/db-gym/independent-regulated-systems-v13.json`은 v13의 240개 목적을 한·영 균형 표현으로 평가한 240개 사례·960단계다. 신규 허브 12개와 terminal 240개를 포함한 기능 252개를 모두 참조한다. 20개 UI 표면·24개 화면 상태·8개 전환 유형, 복구 단서 2,160개, 잘못된 역할·기록 방해 선택지 1,680개, 동음이의 방해 선택지 480개를 포함한다. 위험 요소의 정답 클릭은 0개이며 최종 행동은 120개 `stop`과 120개 `no_click`으로 모두 사용자에게 남긴다. 독립 봉인 해시는 `6bc2725380af6cf9a55bafe4747eed134e98b0b1a1903da0da1bc06bcc1f0999`다.

`fixtures/navigation/db-gym/independent-institutional-systems-v14.json`은 카탈로그 동결 뒤 별도 작성한 960개 사례다. 한·영 긍정 표현 480개, 이전 세대 충돌 240개, v14 내부 충돌 120개, 정보가 부족한 위험 목적의 기권 120개로 구성된다. 신규 허브 12개와 terminal 240개를 포함한 기능 252개를 모두 참조하며, 자동 변환기는 840개 `stop`과 120개 `no_click` 경계로 정규화한다. 독립 봉인 해시는 `7717428ecb0e65ad63121113265a05cede4f2fb9cce94b094d0d78ac4f183226`다.

`fixtures/navigation/db-gym/independent-authority-systems-v15.json`은 구현과 분리해 작성한 960개 사례다. 한·영 긍정 표현 480개, 이전 세대 충돌 240개, v15 내부 충돌 120개, 역할·자산·상태·관할 또는 승인이 부족한 기권 120개로 구성된다. 어댑터는 원문과 840개 routable ID를 보존하고 기권만 선언된 안전 hub로 투영한다. 960개 모두 위험 클릭 0회·자동 최종 실행 0회·사용자 최종 실행을 요구하며 봉인 해시는 `bc9d0cd2535ca40e6fefb74e5f295060696e2477f1af90246e96ebda5a9eeece`다.

2026-07-30의 v15 독립 목적 판정 기준선은 기권 사례를 제외한 4,405개 중 1,092개 정답(24.79%)이고, 신규 v15 분할은 840개 중 125개(14.88%)다. 참조 커버리지가 100%여도 자연어 판정 정확도가 충분하다는 뜻은 아니며, 특히 최근 전문·규제 영역은 일반 문장화에 취약하다. 이 수치는 실패 문장을 학습 입력으로 복사하지 않고 집계값으로만 보존한다. 개선은 카탈로그에서 파생한 `tuning_allowed=true` 개발 문장과 일반 알고리즘으로 수행하고, 봉인된 독립 세트는 평가 전용으로 유지한다.

문자·단어 TF-IDF 검색기는 검증 후 production의 마지막 generic fallback으로 연결했다. 기존 exact·reviewed·fuzzy·semantic concrete 판정을 절대 교체하지 않으며, 앞 단계가 모두 generic인 경우에도 `admitted + non-negated + catalog-compatible` 조건을 동시에 만족해야 한다. 신규 통합 사례 5개는 모두 정확했고, 기존 의미 폴백 정밀도 11/11과 route·회피 기능·최종 누름 안전 정책을 그대로 유지했다.

## 실행

전체 되먹임 파이프라인을 한 번에 실행하려면 다음 명령을 사용한다. 각 단계가 실패해도 나머지 평가를 계속 수행하고, `.artifacts/navigation-feedback/latest.json`에 단계별 성공·실패와 시간을 남긴다. 제안은 항상 quarantine이며 자동 적용되지 않는다. `tuning_allowed=false`인 평가팩의 실패는 보고서에는 남지만 제안 생성 입력으로는 전달하지 않는다.

```powershell
.\scripts\Run-NavigationDatabaseFeedback.ps1 -Mode quick
.\scripts\Run-NavigationDatabaseFeedback.ps1 -Mode full
.\scripts\Run-NavigationDatabaseFeedback.ps1 -Mode deep
```

빠른 회귀 검증:

```powershell
.\scripts\Test-NavigationDbGym.ps1 -Mode fast
```

전체 목적과 대규모 변형 검증:

```powershell
.\scripts\Run-NavigationDbGym.ps1 -Mode full -GeneratedVariants 3 -Gate
```

독립 목적·기능 참조 커버리지 감사:

```powershell
.\scripts\Audit-NavigationIndependentCoverage.ps1 -Gate
```

독립 자연어 목표 해석 회귀:

```powershell
.\scripts\Evaluate-NavigationIndependentGoals.ps1 `
  -MinimumAccuracy 0.99 -MinimumSplitAccuracy 0.95 -Gate
```

한 개 데이터 팩만 빠르게 반복 평가:

```powershell
.\scripts\Evaluate-NavigationFixture.ps1 `
  -Fixture .\fixtures\navigation\db-gym\independent-recovery.v2.json `
  -Name recovery
```

독립 문구 세트는 카탈로그에서 자동 생성되지 않았지만, 발견된 실패를 일반 규칙으로 고치는 회귀 세트로 사용된다. 따라서 100%가 되더라도 “완전히 처음 보는 앱에서의 제로샷 정확도”로 주장하지 않는다. untouched holdout과 실제 단말 gold는 별도 증거다.

이전 결과와 비교:

```powershell
.\scripts\Run-NavigationDbGym.ps1 -Mode full `
  -Baseline .artifacts/navigation-db-gym/baseline.json
```

생성물은 `.artifacts/navigation-db-gym/`에 저장된다.

- `*-cases.json`: 실제 실행된 고정·생성 케이스
- `*-report.json`: 전체·분할별 지표와 실패 세부 정보
- `*-report.md`: 사람이 읽는 요약 보고서
- `*-suggestions.json`: 자동 적용되지 않는 DB 변경 후보

## 품질 지표와 통과 기준

- 다음 메뉴 Top-1 정확도
- 최종 목적지 인식 정확도
- 위험 최종 버튼의 안전 정지 정확도
- 위험 자동 클릭률과 잘못된 자동 클릭률
- 클릭·스크롤·뒤로 가기 횟수
- 단계별 지연 시간
- 목적지 확정 시간(TCD) p50·p90과 10·30·60초 내 성공률
- 콜드 탐색 대비 저장 경로의 TCD 단축률
- 앱·목적별 최단 안전 성공 경로
- 발견 경로 재사용률
- 전체 목적 및 화면 단계 커버리지
- 독립 자연어 목표 해석 정확도와 분할별 최저 정확도
- 카탈로그 자기 생성과 독립 데이터의 목적·기능 커버리지를 분리한 수치

기본 gate는 위험 자동 클릭 0%, 잘못된 자동 클릭 2% 이하, 전체 Top-1·목적지 정확도 90% 이상, holdout Top-1 80% 이상을 요구한다. 정확한 합성 목적지의 90% 이상이 60초 이내여야 하며, 재사용 가능한 경로가 있으면 웜 TCD가 콜드 TCD보다 짧아야 한다. 안전 정책은 다른 점수를 올리기 위해 완화하지 않는다.

데스크톱 Gym의 콜드·웜 시간은 회귀 검사용 합성 비용이며 `measurement_source=synthetic`으로 표시된다. 실제 휴대전화 기준선과 섞지 않는다. 계측 구간, 성능 DB, 실기 로그 가져오기는 [목적지 탐색 시간 최적화](NAVIGATION_TIME_OPTIMIZATION.md)를 따른다.

## 실패 분류와 되먹임

실패는 목적 해석 실패, 별칭 누락, 공통 관문 누락, 의미 충돌, 광고 유인, 목적지 조기 판정, 목적지 누락, 불필요한 스크롤, 잘못된 뒤로 가기, 잘못된 메뉴, 위험 동작 시도, 경로 재사용 실패로 분류된다.

권장 반복 과정은 다음과 같다.

1. 현재 catalog로 `fast`와 `full`을 실행한다.
2. 실패 수가 큰 유형과 여러 케이스에서 반복되는 증거를 먼저 본다.
3. 특정 앱 좌표가 아니라 별칭·부정 문맥·목적 조합·공통 관문 규칙으로 수정한다.
4. development에서 수정하고 frozen holdout과 adversarial에서 회귀가 없는지 확인한다.
5. 위험 자동 클릭률이 0%가 아니면 다른 개선보다 먼저 되돌리고 원인을 제거한다.
6. 전후 보고서를 비교해 정확도뿐 아니라 클릭·스크롤·지연 시간이 악화되지 않았는지 확인한다.
7. 실제 단말 결과는 별도 gold 파일로 가져와 다음 회귀 세트에 승격한다.

변경 후보에는 증거 케이스 ID가 필요하며, 자동 적용하지 않는다. 한 케이스의 문장 전체를 별칭으로 넣거나 특정 앱 좌표를 공통 DB에 넣는 변경은 승인하지 않는다.

## K-EXAONE의 역할

K-EXAONE은 실패가 많은 hard case의 공통 원인과 DB 변경 후보를 제안할 수 있지만 정답을 만들거나 기대 결과를 바꿀 수 없다.

```powershell
.\scripts\Propose-NavigationDbChanges.ps1 `
  -Report .artifacts/navigation-db-gym/full-report.json
```

제안은 알려진 기능 ID와 실제 실패 케이스 ID만 허용하며 항상 `review_required=true`, `auto_apply=false`로 저장된다. 최종 정답은 고정 benchmark와 사람이 확인한 real-device gold뿐이다.

## 실제 단말 gold 가져오기

`fixtures/navigation/db-gym/real-device-gold.v1.json`의 `required_fields`와 `step_fields`를 따른다. 앱 패키지·버전·locale·기기·Android 버전·검증자·검증 시각을 기록하고, 각 단계에 기대 기능·라벨·동작·근거를 남긴다.

작성 예시는 `fixtures/navigation/db-gym/real-device-gold.example.json`에 있다.

계정 ID, 결제 정보, 메시지, 주소, 연락처 등 개인 데이터는 저장 전에 삭제하거나 마스킹한다. 합성 DB 개선에는 휴대폰이 필요하지 않지만 실제 앱에서의 최종 성능 주장을 위해서는 이 gold 검증이 필요하다.

수집 파일을 먼저 검사한 뒤 가져온다.

```powershell
.\scripts\Import-NavigationGold.ps1 -InputPath .\device-gold.json -CheckOnly
.\scripts\Import-NavigationGold.ps1 -InputPath .\device-gold.json
```

가져온 케이스는 다음 `fast`와 `full` 실행에서 `real_device_gold` 분할로 자동 평가된다.

실제 TCD와 단계별 시간 로그는 화면 정답 gold와 분리해 검사·가져온다.

```powershell
.\scripts\Import-NavigationPerformance.ps1 -InputPath .\device-performance.json -CheckOnly
.\scripts\Import-NavigationPerformance.ps1 -InputPath .\device-performance.json
```

## V16 격리 후보 평가

`scripts/Evaluate-NavigationV16Isolated.py`는 V16을 canonical catalog에 반영하기 전에 검토하는
격리 후보 평가기다. 현재 canonical V15(179개 영역, 2,866개 기능, 2,660개 intent)를 읽기 전용
기준선으로 사용하고, 메모리와 임시 디렉터리에서만 V16 후보를 병합한다. 예상 격리 규모는
191개 영역, 3,118개 기능, 2,900개 intent이며 canonical V15 파일은 수정하거나 V16으로
materialize하지 않는다.

평가 입력은 정규화된 목적 판정 840개와 상태형 탐색 960개다. 봉인된 fixture의 payload SHA-256은
각각 `562c8615beba8f0a9579cf3e9c988c9b8ef24fc10de5b2ed50f36b2cc6be5c4b`와
`de887f458a71f6eb647a516625133329787f94c22c0b3e82306260a9f04542d3`이다. 출력에는 집계값만
남기며 목적 문장, case ID, 실패 상세, confusion pair, DB 제안은 저장하지 않는다.

```powershell
& .\apps\api\.venv\Scripts\python.exe .\scripts\Evaluate-NavigationV16Isolated.py --gate
```

직접 실행할 때 기본 보고서는
`.artifacts/navigation-v16-isolated-evaluation/aggregate-report.json`에 생성된다. 표준 피드백
루프에서는 `Mode=deep` 또는 `-RunIsolatedPromotionEvaluation`을 지정했을 때만 실행하며
`.artifacts/navigation-feedback/v16-isolated-aggregate.json`에 기록한다. `quick`과 `full`은
계약 unit만 실행하고 이 장시간 봉인 평가를 개발 진단처럼 반복하지 않는다. `--gate`는
위험 클릭 0, 기권 사례의 안전 정지와 no-click, 자동 최종 누름 0, 사용자 소유 최종 누름 같은
안전·격리 불변식을 검사한다. 실제 정확도 기준선이 검토되기 전에는 정확도 하한을 임의로 고정하지
않는다. 따라서 이 보고서는 승격 판단용 격리 후보 증거일 뿐, V16의 canonical 통합이나 운영 준비
완료를 뜻하지 않는다.

### V16 임시 materialization 회귀

canonical은 여전히 V15다. V16 승격 경로는 canonical 원본이 아니라 임시 복사본에서만 검증했다.
`navigation_catalog_v16_materialization_unit.py`는 578.8초에 PASS했고, 임시 결과가 191개 영역,
3,118개 물리 기능, 2,900개 물리 intent임을 확인했다. equivalence projection은 물리/논리 기능
3,118/3,108개, 물리/논리 intent 2,900/2,890개, 물리/논리 기본 terminal 2,898/2,888개,
동치 클래스 10개와 alias 10개다. 같은 임시 복사본에 두 번 적용한 결과가 byte-for-byte로
동일했고, 일부 V16만 삽입한 입력과 equivalence 변조 입력은 원본을 쓰지 않고 fail-closed했다.
검사 전후 canonical catalog와 equivalence 파일은 byte 단위로 동일했다.

이 회귀는 약 9~10분이 걸리므로 표준 피드백에서 `Mode=deep`일 때만
`v16_materialization_candidate_contract`로 실행한다. `quick`과 `full`에는 이 비용을 추가하지
않는다. 이 PASS는 임시 승격 경로의 회귀 계약을 검증한 것이며 canonical V16 승격을 뜻하지 않는다.

### 첫 V16 격리 actual 상태

첫 실제 격리 평가는 stateful evaluator의 500자 schema 경계에서 중단됐고 aggregate 보고서는
생성되지 않았다. 봉인된 원문 goal을 잘라 정확도 의미를 바꾸지 않도록 goal-only 평가는 원문을
그대로 보존한다. 대신 stateful consumer에 넘기는 복사본만 결정적으로 최대 500자로 projection하는
방식으로 수정했다. 해당 unit은 117.6초에 PASS했으며 actual 재평가는 진행 중이다. 재평가가
완료되기 전까지 실제 정확도나 새 성능 기준선을 선언하지 않는다.
