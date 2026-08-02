# N100 모델 연결 구성

## 연결 구조

```text
Navigation API (N100, 127.0.0.1:8100)
  ├─ Solar Pro 3 API (Upstage 외부 인증 API)
  └─ 127.0.0.1:18000/v1
       └─ exitguide-a100-vlm-tunnel.service
            └─ A100 EXAONE 4.5 (127.0.0.1:8000/v1)
```

A100의 vLLM 포트를 인터넷이나 LAN에 공개하지 않는다. N100의 전용 SSH 키는
`permitopen="127.0.0.1:8000"` 제한으로 등록하며, 셸·에이전트·X11 접근에는
사용하지 않는다. 터널은 부팅 시 자동으로 시작되고 연결이 끊기면 systemd가
재시작한다.

## N100 파일과 서비스

- 터널 서비스: `exitguide-a100-vlm-tunnel.service`
- Navigation API: `exitguide-navigation-api.service`
- 터널 키/known_hosts: `/srv/exitguide/secrets/navigation-a100-tunnel/`
- 비밀이 아닌 Navigation 설정: `/srv/exitguide/secrets/navigation-api.env`
- Solar Pro 3 인증 설정: `/srv/exitguide/secrets/navigation-planner.env`
- A100 VLM URL: `http://127.0.0.1:18000/v1`

실제 비밀값은 Git에 넣지 않으며 상태 출력에도 노출하지 않는다.

## 검증 결과 (2026-08-02)

- N100에서 A100 `/v1/models`: `EXAONE-4.5-33B` 확인
- Navigation API VLM 실호출: HTTP 200, `perception_provider=exaone_4_5`
- N100에서 Solar Pro 3 단순 인증 실호출: HTTP 200, 약 0.50초
- N100에서 Solar Pro 3 강제 Hermes tool call: HTTP 200, 약 0.59초
- Navigation API 상태: `research_models_ready=true`, `serving_mode=research_models`
- 저신뢰 DB 화면에서 Solar 계획+전체 후보 평가: HTTP 200, 2회 측정 4.212~6.166초, 발견 후보 `settings` 선택
- 고신뢰 DB fast path: HTTP 200, 0.018초, Solar 호출 없이 `signup` 선택
- 위험한 멤버십 해지 확정 화면: HTTP 200, 0.024초, `stop_for_user()` 반환
- Navigation API와 A100 터널 모두 `active`, 서비스 재시작 후 warning 로그 없음

위 결과는 연결·계약·안전 smoke이며 범용 성공률 A/B는 아니다. 모델 연결 완료가
Navigation 정확도 개선을 의미하지는 않는다. 정적 데이터를 늘리기
전에 오프라인 A/B와 실기기 평가로 별도 검증해야 한다.

## 운영 확인

```bash
systemctl status exitguide-a100-vlm-tunnel.service
systemctl status exitguide-navigation-api.service
curl -fsS http://127.0.0.1:18000/v1/models
curl -fsS http://127.0.0.1:8100/v1/navigation/status
```

A100은 2026-08-14까지의 임시 할당이므로 그 이후에는 새 GPU 엔드포인트로
터널 대상을 교체하거나 별도의 상시 VLM 호스팅을 준비해야 한다.
