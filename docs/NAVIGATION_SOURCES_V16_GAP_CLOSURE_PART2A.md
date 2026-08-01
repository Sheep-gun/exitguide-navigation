# Navigation Sources V16 — Gap Closure Part 2A

- 검증일: **2026-07-30**
- 범위: `NAVIGATION_SOURCES_V16_PART2.md`의 도메인 7~9에 남아 있던 terminal/source gap 10개
- 검증 원칙: FCC, FAA, eCFR, NRC의 공식 1차 출처만 사용
- 제외 범위: independent fixture, answer, failure, evaluation 및 implementation code는 열람하지 않음

## 1. 판정 기준

이 문서의 상태는 “그럴듯한 메뉴 이름이 존재하는가”가 아니라, 해당 terminal이 표현하는 **역할(role), 자산(asset), 상태(state), 관할(jurisdiction), 전이(transition)**를 공식 출처가 어느 정도 직접 뒷받침하는지를 뜻한다.

- `resolved`: terminal의 핵심 행위와 전이를 현재 접근 가능한 공식 규정 또는 공식 절차가 직접 뒷받침한다.
- `partially_resolved`: 공식 근거는 확인했으나 특정 서비스·대역·면허 유형에만 적용되거나, terminal의 동사·범위가 공식 절차보다 넓다.
- `unresolved`: terminal을 정당화할 직접 공식 근거를 찾지 못했다.

제품 UI의 존재는 ontology 근거와 별도로 판정했다. 따라서 공식 제출 절차가 이메일·우편·일반 전자제출로 완결되는 경우, 전용 UI 화면을 확인하지 못했더라도 ontology gap은 해결될 수 있다. 반대로 화면이나 버튼 이름이 확인되더라도 특정 제도에만 적용되면 범용 terminal은 해결된 것으로 보지 않았다.

## 2. 상태 요약

| 도메인 | 대상 수 | resolved | partially_resolved | unresolved |
|---|---:|---:|---:|---:|
| 7. `wireless_spectrum_license_ops` | 4 | 0 | 4 | 0 |
| 8. `commercial_space_launch_licensing_ops` | 2 | 0 | 2 | 0 |
| 9. `radioactive_materials_license_ops` | 4 | 2 | 2 | 0 |
| **합계** | **10** | **2** | **8** | **0** |

## 3. 도메인 7 — Wireless Spectrum License Operations

### 3.1 `wireless_spectrum_license_ops.frequency_coordination_attach`

**판정: `partially_resolved`**

- 공식 근거: `[S1]`
- 접근 관찰: FCC 공식 PDF 본문을 정상 추출했다. 문서는 Commission-certified frequency coordinator가 인증 결과를 신청서에 첨부하도록 명시한다.
- 관할: Part 90의 모든 무선 서비스에 대한 범용 절차가 아니라, 해당 Public Notice가 다루는 vacated 800 MHz channel 신청 맥락이다.
- 역할: 신청인, Commission-certified frequency coordinator.
- 자산: 무선국 신청서, 위치, 주파수, 조정 인증서.
- 상태·전이: 후보 위치·주파수 선정 → frequency coordination 및 충돌 해결 → coordinator certification → 인증서를 신청서에 첨부 → 신청 제출.
- 제품 UI 존재: **확인하지 못함.** 출처는 “attach” 의무를 직접 확인하지만, 2026년 현재 ULS의 구체적인 첨부 화면·필드·버튼은 보여주지 않는다.
- ontology 근거: “공인 조정자가 생성한 인증 결과를 신청에 붙인다”는 terminal의 행위와 역할·자산·전이는 직접 지지된다.
- 제한: 특정 대역·절차의 근거를 전체 wireless licensing에 일반화할 수 없다. terminal에 `service_or_band_scope`를 필수 조건으로 두거나, 서비스별 하위 terminal로 분해하기 전에는 `resolved`로 올리지 않는다.

### 3.2 `wireless_spectrum_license_ops.buildout_certification_submit`

**판정: `partially_resolved`**

- 공식 근거: `[S2]`
- 접근 관찰: FCC 공식 PDF 본문을 정상 추출했다. 700 MHz licensee가 ULS에서 construction notification을 전자 제출하고, buildout/coverage 충족 여부를 인증하며, coverage map과 supporting documentation을 첨부하는 절차가 확인됐다.
- 관할: Lower 700 MHz의 특정 EA/CMA/REAG license 및 해당 buildout benchmark.
- 역할: licensee 또는 그 권한을 가진 filer/certifier.
- 자산: call sign, license, benchmark, coverage map, supporting documentation, construction notification.
- 상태·전이: buildout obligation 진행 중 → 충족 여부 및 측정자료 확인 → ULS `Notify the FCC`에서 해당 notification purpose 선택 → 충족/미충족 인증 및 자료 첨부 → FCC 제출 기록 생성.
- 제품 UI 존재: **제한적으로 확인됨.** 공식 문서에 ULS의 `Notify the FCC`와 특정 purpose label이 기재되어 있다. 다만 현재 화면을 직접 캡처한 자료는 아니며, 모든 서비스에 동일한 UI가 적용된다는 근거도 아니다.
- ontology 근거: buildout의 충족 상태, call sign 단위 신고, 전자 인증, 지도·증빙 첨부라는 핵심 요소가 직접 뒷받침된다.
- 제한: 대역별 performance requirement와 제출 기한이 다르다. 범용 terminal에는 `radio_service`, `benchmark_type`, `deadline`, `evidence_required`를 관할별로 바인딩해야 한다.

### 3.3 `wireless_spectrum_license_ops.license_cancellation_request`

**판정: `partially_resolved`**

- 공식 근거: `[S3]`, `[S4]`
- 접근 관찰: 두 FCC 공식 PDF의 본문을 정상 추출했다. Form 601 지침은 application purpose `CA`를 “Cancellation of License”로 정의하고, call sign의 모든 facility가 취소된다는 점과 서명 항목을 명시한다. 별도 Public Notice는 cancellation application이 granted되면 ULS가 licensee에게 notice를 생성하는 전이를 확인한다.
- 관할: FCC Wireless Telecommunications Bureau의 Form 601/ULS 기반 면허 업무.
- 역할: licensee, 권한을 위임받은 filer/agent, 서명권자.
- 자산: FRN, call sign, 전체 license와 그 아래의 facilities, 서명·제출일.
- 상태·전이: active license → `CA` 목적의 신청 작성·서명·제출 → FCC grant → license cancelled 및 ULS notice. 일부 시설만 제거하는 modification과 전체 면허 cancellation이 구분된다.
- 제품 UI 존재: **과거 Form 601/ULS 수준에서 확인됨.** 그러나 `[S3]`는 오래된 판본이며, 2026년 현재 입력 화면과 필드 배치는 확인하지 못했다.
- ontology 근거: “권한 있는 주체가 call sign 전체의 자발적 취소를 신청한다”는 행위와 grant 후 상태 전이는 직접 지지된다.
- 제한: 현재 시스템 UI와 최신 서비스별 예외를 검증하지 못했다. 문서 연령과 화면 불확실성 때문에 `resolved`로 판정하지 않는다.

### 3.4 `wireless_spectrum_license_ops.discontinuance_notice_file`

**판정: `partially_resolved`**

- 공식 근거: `[S5]`
- 접근 관찰: FCC 공식 PDF 본문을 정상 추출했다. Cellular Geographic Service Area에서 permanent discontinuance가 180일 동안 지속된 뒤 10일 이내 Form 601로 FCC에 알리는 절차와 자동 종료 효과가 확인됐다.
- 관할: Part 22 Cellular Service. 다른 wireless service의 discontinuance 기간·신고 방식은 동일하다고 볼 수 없다.
- 역할: cellular licensee 또는 권한 있는 filer.
- 자산: call sign/license, CGSA 또는 해당 cellular service, discontinuance date, Form 601 notification.
- 상태·전이: service active → 영구 중단 시작 → 180일 경과 → 10일 이내 discontinuance notice 제출 → license가 자동 종료된 상태로 반영. 일부 site-based cancellation notification과는 구별된다.
- 제품 UI 존재: **확인하지 못함.** Form 601 제출이라는 채널은 확인되지만 현재 ULS 메뉴·버튼은 출처에 없다.
- ontology 근거: 영구 중단, 법정 기간, notice filing, automatic termination의 인과 전이는 직접 뒷받침된다.
- 제한: 서비스별 규칙이 크게 다른데 terminal 이름은 이를 드러내지 않는다. `service_rule`, `discontinuance_period`, `notice_deadline`, `termination_effect`를 jurisdiction profile로 분리해야 한다.

## 4. 도메인 8 — Commercial Space Launch Licensing Operations

### 4.1 `commercial_space_launch_licensing_ops.launch_mission_authorization_request`

**판정: `partially_resolved`**

- 공식 근거: `[S6]`, `[S7]`
- 접근 관찰: 두 eCFR 페이지 모두 본문을 정상 로드했다. 접근 당시 §450.213은 2026-07-27 기준 최신 상태로 표시됐다. §450.3은 vehicle operator license 자체가 하나 이상의 launch/reentry를 authorize할 수 있음을 규정한다.
- 관할: FAA, 14 CFR Part 450의 vehicle operator license.
- 역할: Part 450 licensee/operator와 FAA/AST 검토자.
- 자산: license, 특정 mission의 vehicle·payload·trajectory·site·schedule 및 flight-analysis 정보.
- 상태·전이: operator license 유효 → mission-specific information을 원칙적으로 60일 전 제출 → updated flight analysis를 원칙적으로 30일 전 제출 → FAA가 review/rehearsal/safety-critical operation에 참여할 수 있도록 일정 갱신 → 허가 범위 안에서 mission 수행 준비.
- 제품 UI 존재: **전용 UI 없음이 공식 절차에 가깝다.** §450.213은 이메일 첨부 또는 license에서 합의한 다른 방법으로 mission-specific information을 제출하도록 한다.
- ontology 근거: mission별 정보 제출과 FAA의 사전 검토 전이는 직접 확인된다.
- 제한: 공식 체계는 매 mission마다 별도의 “authorization request”를 반드시 발급받는 구조라고 단정할 수 없다. 이미 발급된 vehicle operator license가 여러 mission을 authorize할 수 있기 때문이다. 따라서 exact terminal은 과도하게 좁거나 잘못 명명됐다. `preflight_mission_information_submit` 또는 `mission_specific_information_update`로 재명명하면 근거 적합도가 높아진다.

### 4.2 `commercial_space_launch_licensing_ops.launch_readiness_certify`

**판정: `partially_resolved`**

- 공식 근거: `[S8]`
- 접근 관찰: eCFR 본문을 정상 로드했으며, 접근 당시 2026-07-16 기준 최신 상태로 표시됐다. §450.155는 readiness를 평가하는 절차와 기준의 문서화·구현을 직접 요구한다.
- 관할: FAA, 14 CFR Part 450 launch/reentry safety program.
- 역할: operator/license applicant, safety organization, safety-critical personnel, 필요 시 FAA 참여자.
- 자산: vehicle, launch/reentry site, safety-critical personnel·system·software·procedure·equipment·property·service, mishap response plan.
- 상태·전이: mission planned → readiness criteria 적용 및 관련 요소 평가 → readiness meeting을 포함할 수 있는 검토 → ready/not-ready 판단 → 안전상 미해결 사항을 처리한 뒤 operation 진행.
- 제품 UI 존재: **확인하지 못함.** 규정은 operator가 자체 절차를 문서화·구현하도록 하며, FAA 전용 “certify” 버튼이나 단일 제출 화면을 규정하지 않는다.
- ontology 근거: readiness assessment의 역할, 평가 대상 자산, 준비 상태 전이는 강하게 뒷받침된다.
- 제한: exact terminal의 `certify`라는 단일 공식 행위는 확인되지 않았다. `launch_readiness_assess`와 `launch_readiness_record`를 분리하거나, operator-specific procedure에 `certification_required`가 있을 때만 certify terminal을 활성화하는 편이 정확하다.

## 5. 도메인 9 — Radioactive Materials License Operations

### 5.1 `radioactive_materials_license_ops.leak_test_result_certify`

**판정: `partially_resolved`**

- 공식 근거: `[S9]`, `[S10]`
- 접근 관찰: eCFR §35.2067은 본문을 정상 로드했으며 접근 당시 2026-07-09 기준 최신 상태로 표시됐다. NRC §34.27 페이지도 정상 로드됐다. 두 출처는 tester/performer, source 식별정보, 결과, 날짜 및 기록 보존을 확인한다.
- 관할: 의료용 byproduct material의 Part 35와 industrial radiography의 Part 34. source 유형별 규정이 다르다.
- 역할: licensee, leak test 수행자 또는 NRC/Agreement State가 허용한 testing service, RSO/source custodian.
- 자산: sealed source의 model·serial number, radionuclide·activity, test date, result, performer identity, 보존 기록.
- 상태·전이: leak-test due → 자격 있는 주체가 sampling/testing → 결과 기록 → 기준 미만이면 continued use 가능 → 누출 기준 이상이면 즉시 사용 중지·격리 및 규정상 보고.
- 제품 UI 존재: **확인하지 못함.** 공식 근거는 licensee의 기록 의무이며, NRC 공통 제품 화면에서 결과를 “certify”하는 절차는 제시하지 않는다.
- ontology 근거: 시험 주체, source asset, pass/fail 상태와 fail 이후의 제한 전이는 직접 지지된다.
- 제한: 의료·산업용 등 프로그램별 기준과 주기가 다르고, 공통된 독립 `certify` submission은 확인되지 않았다. terminal을 `leak_test_result_record`로 낮추고, 프로그램별로 `report_leaking_source` 전이를 추가하는 편이 공식 구조에 가깝다.

### 5.2 `radioactive_materials_license_ops.radioactive_material_shipment_authorize`

**판정: `partially_resolved`**

- 공식 근거: `[S11]`, `[S12]`, `[S13]`
- 접근 관찰: NRC LVS overview, transportation shipping 안내, 10 CFR §37.71 페이지 모두 정상 로드됐다. LVS overview에는 공급자가 입력하고, license image와 possession limit을 확인하며, 오류 시 regulator에 문의하고, 이상이 없으면 verification complete 상태로 진행하는 실제 시스템 흐름이 제시된다.
- 관할: §37.71의 Category 1/Category 2 quantities transfer와 NRC transportation/package 요구사항. 모든 방사성 물질 shipment에 동일하게 적용되는 단일 절차는 아니다.
- 역할: transferor/supplier licensee, recipient licensee, NRC 또는 Agreement State licensing authority, shipping/transport 담당자.
- 자산: recipient license, material type·form·quantity·location, LVS verification, package Certificate of Compliance, package inspection/test/seal/leak/radiation-measurement 기록.
- 상태·전이: transfer proposed → recipient authority와 possession limits 확인 → verification clear/blocked → package 및 운송 요건 확인 → clear이면 transfer/shipment 진행, 문제 있으면 regulator 확인 전 중단.
- 제품 UI 존재: **부분 확인됨.** LVS는 license verification을 위한 웹 제품 흐름을 제공한다. 그러나 license verification과 package/transport 검사를 합쳐 최종 “shipment authorize”를 실행하는 단일 NRC 화면은 확인되지 않았다.
- ontology 근거: recipient 자격 검증과 package readiness가 shipment 전제라는 핵심 행위는 직접 뒷받침된다.
- 제한: terminal이 내부 사업자 승인, §37 transfer verification, DOT/NRC package compliance를 하나로 합치고 있다. `recipient_license_verify`, `package_compliance_check`, `shipment_release_authorize`로 분해하고, 마지막 단계는 조직 내부 통제로 표시해야 한다.

### 5.3 `radioactive_materials_license_ops.medical_event_report_submit`

**판정: `resolved`**

- 공식 근거: `[S14]`, `[S15]`, `[S18]`
- 접근 관찰: eCFR의 section canonical URL은 일부 요청에서 자동화 방지 화면을 반환했다. 다만 NRC 공식 legacy 경로 `[S15]`를 통해 현재 eCFR Part 35 본문으로 이동하여 §35.3045 전문을 확인했다. §30.6 NRC 페이지는 정상 로드되어 우편·직접 전달·허용된 전자 제출 채널을 확인했다.
- 관할: NRC medical use licensee, 10 CFR Part 35 및 제출 방식에 관한 §30.6. Agreement State 관할에서는 해당 주 규칙을 별도 확인해야 한다.
- 역할: medical use licensee, authorized user/prescribing physician, referring physician, affected individual 또는 responsible relative, NRC Operations Center 및 관할 Regional Office.
- 자산: event determination, dose·administration facts, event description, cause, health-effect assessment, corrective action, notification certification, 비식별 written report.
- 상태·전이: event discovered·criteria met → 다음 calendar day까지 NRC Operations Center에 전화 통보 → 원칙적으로 24시간 내 physician 및 individual 통보 → discovery 후 15일 이내 관할 Regional Office에 서면 보고 → 개인 식별정보를 제외한 NRC report와 별도의 individual notification record 관리.
- 제품 UI 존재: **전용 medical-event UI는 확인하지 못함.** 일반 전자 제출이 practicable한 경우 EIE를 사용할 수 있고, 그 밖에는 규정된 우편·전달 방식이 가능하다.
- ontology 근거: 누가, 어떤 사건을, 어느 관할에, 어떤 순서와 기한으로 통보·제출하는지가 공식 규정에 직접 규정돼 있다. 전용 제품 화면이 없다는 사실은 이 terminal의 제출 ontology를 약화시키지 않는다.
- 제한: 실제 운용 시 NRC jurisdiction과 Agreement State jurisdiction을 먼저 분기해야 하며, 개인정보가 들어간 patient notification과 NRC 제출본을 같은 payload로 취급하면 안 된다.

### 5.4 `radioactive_materials_license_ops.decommissioning_plan_submit`

**판정: `resolved`**

- 공식 근거: `[S16]`, `[S17]`, `[S18]`
- 접근 관찰: NRC의 10 CFR §30.36 페이지, decommissioning process 안내, §30.6 제출 방식 페이지를 모두 정상 로드했다. 규정과 NRC 절차 안내가 trigger, notification, plan 제출, 승인, 실행, final survey/release 전이를 서로 일관되게 설명한다.
- 관할: NRC materials license under 10 CFR Part 30. 특정 facility·material category나 Agreement State 관할에는 추가 규정이 있을 수 있다.
- 역할: licensee/responsible officer, decommissioning manager와 방사선안전 담당자, NRC project manager/reviewer.
- 자산: license·licensed premises, buildings/areas/equipment, contamination and radiological condition, planned decommissioning activities, worker/public/environment protection method, final radiation survey, release criteria, cost estimate·funding assurance.
- 상태·전이: decommissioning trigger 발생 → 원칙적으로 60일 내 NRC 통보 및 해체 시작 또는 plan 필요성 판단 → plan이 요구되면 원칙적으로 12개월 내 제출 → NRC review·approval/license amendment → 승인된 plan에 따라 해체 → final survey 및 release criteria 입증 → license termination 또는 site release.
- 제품 UI 존재: **전용 plan-submission 화면은 확인하지 못함.** §30.6의 공식 communication channel과 NRC project-management 절차가 제출·검토를 뒷받침한다.
- ontology 근거: plan 필요 조건, 제출 시점, 필수 구성요소, 승인 전이, 최종 survey/release까지 exact terminal이 요구하는 역할·자산·상태·관할·전이가 충분히 확인됐다.
- 제한: `plan_required` 여부는 모든 종료에 자동으로 true가 아니며 §30.36(g)의 조건으로 판정해야 한다. 제품에서는 `notify_and_begin_decommissioning`과 `decommissioning_plan_submit`을 동일 단계로 합치지 않아야 한다.

## 6. 공식 출처 레지스트리

아래 URL은 모두 2026-07-30에 실제 접근 또는 공식 경로를 통한 본문 확인을 수행했다. PDF의 발행 연도가 오래된 경우에는 해당 terminal의 제한에 별도로 기록했다.

- `[S1]` FCC, DA-14-1904: [Public Notice on frequency coordination certifications](https://docs.fcc.gov/public/attachments/DA-14-1904A1.pdf)
- `[S2]` FCC, DA-13-1278: [700 MHz construction notification procedures](https://docs.fcc.gov/public/attachments/DA-13-1278A1.pdf)
- `[S3]` FCC: [FCC Form 601 instructions](https://docs.fcc.gov/public/attachments/DOC-298965A1.pdf)
- `[S4]` FCC, DA-16-1039: [ULS notice after granted cancellation applications](https://docs.fcc.gov/public/attachments/DA-16-1039A1.pdf)
- `[S5]` FCC, DA-18-414: [Cellular permanent-discontinuance notification](https://docs.fcc.gov/public/attachments/DA-18-414A1.pdf)
- `[S6]` eCFR: [14 CFR §450.213 — Pre-flight reporting](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450/subpart-D/section-450.213)
- `[S7]` eCFR: [14 CFR §450.3 — Scope of a vehicle operator license](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450/subpart-A/section-450.3)
- `[S8]` eCFR: [14 CFR §450.155 — Readiness](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450/subpart-C/section-450.155)
- `[S9]` eCFR: [10 CFR §35.2067 — Records of leak tests](https://www.ecfr.gov/current/title-10/chapter-I/part-35/subpart-L/section-35.2067)
- `[S10]` NRC: [10 CFR §34.27 — Leak testing and replacement of sealed sources](https://www.nrc.gov/reading-rm/doc-collections/cfr/part034/part034-0027.html)
- `[S11]` NRC: [License Verification System overview](https://www.nrc.gov/security/byproduct/ismp/lvs/overview.html)
- `[S12]` NRC: [Shipping requirements for radioactive materials](https://www.nrc.gov/materials/transportation/shipping)
- `[S13]` NRC: [10 CFR §37.71 — Additional requirements for transfer of Category 1 and Category 2 quantities](https://www.nrc.gov/reading-rm/doc-collections/cfr/part037/part037-0071.html)
- `[S14]` eCFR: [10 CFR §35.3045 — Report and notification of a medical event](https://www.ecfr.gov/current/title-10/part-35/section-35.3045)
- `[S15]` NRC: [Official NRC route to current §35.3045 text](https://www.nrc.gov/reading-rm/doc-collections/cfr/part035/part035-3045)
- `[S16]` NRC: [10 CFR §30.36 — Expiration and termination of licenses and decommissioning](https://www.nrc.gov/reading-rm/doc-collections/cfr/part030/part030-0036)
- `[S17]` NRC: [The decommissioning process](https://www.nrc.gov/waste/decommissioning/process)
- `[S18]` NRC: [10 CFR §30.6 — Communications](https://www.nrc.gov/reading-rm/doc-collections/cfr/part030/part030-0006.html)

## 7. URL 정규화 및 품질 감사

정규화 규칙은 scheme/host 소문자화, fragment 및 query 제거, default port 제거, 중복 slash 축약, root 이외 trailing slash 제거로 정의했다.

- 레지스트리 URL 수: **18**
- 정규화 후 고유 URL 수: **18**
- 정규화 URL 중복 수: **0**
- 비공식·2차 출처 수: **0**
- terminal 수: **10**
- 상태 합계 검산: **2 resolved + 8 partially_resolved + 0 unresolved = 10**

## 8. 후속 모델링 결론

이번 closure에서 억지로 범용 terminal을 확정하지 않았다. FCC 4개는 실제 제출 행위가 존재하지만 서비스·대역별 차이가 커서 jurisdiction profile 없이 공통 terminal로 사용하기 어렵다. FAA 2개는 “별도 mission authorization” 및 “단일 readiness certification”이라는 현재 이름이 공식 Part 450 구조보다 강한 표현이다. NRC에서는 medical-event written report와 decommissioning-plan submission만 exact terminal 수준으로 충분히 닫혔다.

따라서 다음 ontology 개정에서는 다음 원칙을 적용하는 것이 안전하다.

1. FCC terminal에는 `radio_service`, `band`, `rule_part`, `deadline_rule`을 필수 scope로 둔다.
2. FAA의 mission terminal은 license authorization과 mission-specific information submission을 분리한다.
3. FAA readiness는 `assess/record`를 기본으로 하고, 별도 operator procedure가 있을 때만 `certify`를 허용한다.
4. NRC leak test는 `record result`와 `report leaking source`를 분리한다.
5. NRC shipment는 recipient-license verification, package compliance, internal shipment release를 서로 다른 transition으로 둔다.
6. 전용 제품 UI가 없다는 이유만으로 규정상 유효한 이메일·우편·일반 전자제출 terminal을 제거하지 않는다.
