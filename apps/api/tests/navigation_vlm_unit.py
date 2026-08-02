import base64
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.schemas import UniversalNavigationCandidate, UniversalNavigationObserveRequest
from app.services import navigation_vlm as module
from app.services.navigation_vlm import ExaoneNavigationVlm, apply_visual_hints


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def main() -> None:
    assert_vlm_runs_only_for_ambiguous_redacted_context_and_caches_metadata()
    assert_vlm_cannot_invent_candidate_ids()
    print("navigation VLM checks ok")


def assert_vlm_runs_only_for_ambiguous_redacted_context_and_caches_metadata() -> None:
    with TemporaryDirectory() as temporary_directory:
        calls: list[dict] = []
        original_post = module.httpx.post

        def fake_post(url, *, headers, json, timeout):
            calls.append(json)
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json_dumps(
                                    {
                                        "screen_summary": "계정 화면의 상단 도구 모음",
                                        "candidates": [
                                            {
                                                "element_id": "gear",
                                                "visual_label": "설정",
                                                "role": "button",
                                                "confidence": 0.94,
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }
            )

        module.httpx.post = fake_post
        try:
            cache = Path(temporary_directory) / "vlm.sqlite"
            settings = Settings(
                navigation_vlm_enabled=True,
                navigation_vlm_base_url="http://127.0.0.1:8000/v1",
                navigation_vlm_model="EXAONE-4.5-33B",
                navigation_vlm_cache_path=str(cache),
            )
            request = visual_request()
            candidate = UniversalNavigationCandidate(
                element_id="gear",
                element_key="gear-key",
                label="이름 없는 상단 오른쪽 아이콘",
                role="image",
                risk_level="low",
            )
            provider = ExaoneNavigationVlm(settings)
            first = provider.analyze(request=request, candidates=[candidate])
            second = provider.analyze(request=request, candidates=[candidate])
        finally:
            module.httpx.post = original_post

        assert first is not None and first.cache_hit is False
        assert second is not None and second.cache_hit is True
        assert len(calls) == 1
        enhanced = apply_visual_hints([candidate], first)
        assert enhanced[0].label == "설정"
        connection = sqlite3.connect(cache)
        try:
            stored = connection.execute("SELECT result_json FROM navigation_vlm_cache").fetchone()[0]
        finally:
            connection.close()
        assert visual_request().visual_context.image_base64 not in stored
        assert "설정" in stored


def assert_vlm_cannot_invent_candidate_ids() -> None:
    try:
        module._parse_visual_hint(
            {
                "screen_summary": "screen",
                "candidates": [
                    {
                        "element_id": "invented",
                        "visual_label": "설정",
                        "role": "button",
                        "confidence": 0.9,
                    }
                ],
            },
            ["gear"],
            "EXAONE-4.5-33B",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("VLM invented candidate ID was accepted")


def visual_request() -> UniversalNavigationObserveRequest:
    image = base64.b64encode(b"privacy-masked-jpeg-fixture").decode("ascii")
    return UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": "vlm-request",
            "session_id": "vlm-session",
            "app_package": "com.example.app",
            "app_version": "1",
            "locale": "ko-KR",
            "goal_text": "알림 설정을 끄고 싶어",
            "operation_mode": "explore",
            "screen": {
                "activity_name": "MainActivity",
                "window_title": "계정",
                "elements": [
                    {
                        "id": "gear",
                        "role": "image",
                        "clickable": True,
                        "enabled": True,
                        "visible": True,
                        "bounds": [900, 50, 1050, 200],
                    }
                ],
            },
            "visual_context": {
                "content_type": "image/jpeg",
                "image_base64": image,
                "width": 540,
                "height": 1200,
                "redacted": True,
            },
        }
    )


def json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    main()
