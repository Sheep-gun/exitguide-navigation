from app.config import Settings
from app.services import llm as llm_service
from app.services.demo_quality import build_demo_quality


def main() -> None:
    assert_quality_calibration_never_calls_live_provider()
    print("demo quality checks ok")


def assert_quality_calibration_never_calls_live_provider() -> None:
    original_post = llm_service.httpx.post

    def forbidden_post(*args, **kwargs):
        raise AssertionError("demo quality must not call a live LLM provider")

    llm_service.httpx.post = forbidden_post
    try:
        quality = build_demo_quality(
            Settings(
                ocr_provider="mock",
                llm_provider="exaone",
                exaone_api_key="non-secret-test-key",
                exaone_model="test-model",
            )
        )
    finally:
        llm_service.httpx.post = original_post

    assert quality.status == "pass"
    assert quality.summary.scenarios_passed == 10
    assert quality.summary.flows_passed == 4
    assert quality.summary.synthetic_passed == 15


if __name__ == "__main__":
    main()
