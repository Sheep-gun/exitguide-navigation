# Shared App Knowledge Contract v0.9.1

이 디렉터리는 팀 공통 스키마 v0.9.1의 개발 기준본입니다.

- 원본 패키지: `exitguide-app-knowledge-schema-v0.9.1-codex-fixed-20260803-022107.zip`
- 패키지 SHA-256: `5D8C12992F06B6F63460DF195C61AEFADD2839F80A6FCDD2B5ADA55AF16CF038`
- 상태: 개발 기준 고정본. N100 운영 DB에 적용된 상태는 아닙니다.
- JSON Schema dialect: Draft 2020-12

Navigation의 과거 Decision Case를 변환할 때는 다음 규칙을 지킵니다.

1. `navigation-goal-crosswalk.v1.json`으로 기존 Navigation goal ID를 공통 goal ID로 변환합니다.
2. 과거 기록에 전체 화면 후보가 없으면 `candidate_set_status=unavailable`, `candidates=[]`로 기록합니다.
3. 없는 후보, 점수, 모델 호출, 검색 근거를 추정해서 채우지 않습니다.
4. `candidate_set_status=unavailable`인 기록은 canonical transition으로 자동 승격할 수 없습니다.
5. 원본 SQLite는 읽기 전용으로 열고 변환 결과는 별도 JSONL로 생성합니다.

`interaction-episode.v1.json`은 실행 경험, `knowledge-promotion.v1.json`은 검증을 통과한 경험의 승격 절차를 각각 규정합니다. 두 계층을 분리해 Human Gold도 자동 실행 경로가 아니라 높은 신뢰도의 경험 근거로만 사용합니다.
