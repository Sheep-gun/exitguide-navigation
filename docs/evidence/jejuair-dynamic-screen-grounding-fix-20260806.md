# 제주항공 동적 화면 candidate_id 접지 수정 실기기 근거

검증 일시: 2026-08-06 16:36–16:47 KST

## 재현된 문제

제주항공 시작 이미지 팝업에서 후보는 다음 두 개로 안정적으로 유지됐다.

- 콘텐츠 이미지: `a11y_06eba0e174844040aad8`
- 닫기 아이콘: `a11y_57006442febb7d9949e5`, view_id `imgClose`

그러나 같은 화면의 Accessibility root class가 `u4.i`, `ViewPager`, `RecyclerView`로
번갈아 보고돼 화면 지문이 세 종류로 변했다. 닫기 명령은 수집기에 저장됐지만 실행 전에
화면 지문이 바뀌어 폐기됐다. 클릭·Runtime session·성공 기록은 생성되지 않았다.

메인 화면에서도 자동 캐러셀 광고가 바뀌며 전체 화면 지문이 계속 달라졌지만 하단의
`마이페이지` candidate_id는 동일하게 유지됐다.

## 수정

- 화면 지문에서 실제 Activity가 아닌 불안정한 Accessibility root class를 제외했다.
- 후보 Signature에 candidate_id를 포함했다.
- click 명령은 전체 화면 지문이 달라도 정확한 candidate_id가 현재 후보 집합에 계속
  존재할 때만 처리한다.
- 실제 실행 직전에는 기존 Accessibility node fingerprint 검사를 그대로 수행한다.
- scroll, back, wait, stop처럼 candidate_id로 접지되지 않는 행동은 전체 화면 지문이
  바뀌면 계속 거부한다.

구현 커밋: `15fa09eab03913c19a0fdaf9ccc9259a52be40f1`

## 검증

- Android `testDebugUnitTest`: passed
- Android `assembleDebug`: passed
- `scripts/Install-NavigationExecutor.ps1`: 설치·접근성 enabled/bound·후보 수집·API ready passed
- APK SHA-256: `D5F083C065093D90AAC6A02576F2AF14252D6EE0F7BC81DE7127D62D94AFF678`

실기기 회원가입 세션에서 `마이페이지` 명령의 기대 화면 지문은
`d8baca378c8b90edff8f558c43ea775f0ce1eb6b331def693104776992ca10fc`, 행동 후 관찰 시
화면 지문은 `7d1e226ce914763f4bb5b285b6cfa2e061cd00a6deb6cf8033d5283fc9e695dd`로
달랐다. 동일 `a11y_b12cd340ce32209fd967` 후보가 현재 화면에 남아 있었고
Accessibility action이 성공해 로그인·회원가입 화면으로 이동했다.

앱별 경로 하드코딩, 임의 좌표, Gold 재생은 사용하지 않았다.

