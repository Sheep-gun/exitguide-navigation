#!/usr/bin/env python3
"""Run a privacy-scoped EXAONE 4.5 navigation-perception smoke test.

The supplied crop is transformed in memory and is never written to disk. The
VLM adapter persists only its normalized text result in the configured cache.
Candidate bounds are accepted in original screenshot coordinates and remapped
to the cropped/downscaled image sent to the model.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import Settings  # noqa: E402
from app.schemas import UniversalNavigationCandidate, UniversalNavigationObserveRequest  # noqa: E402
from app.services.navigation_vlm import ExaoneNavigationVlm  # noqa: E402


def _box(raw: str) -> tuple[int, int, int, int]:
    values = tuple(int(value.strip()) for value in raw.split(","))
    if len(values) != 4 or values[2] <= values[0] or values[3] <= values[1]:
        raise argparse.ArgumentTypeError("bounds must be left,top,right,bottom")
    return values


def _candidate(raw: str) -> tuple[str, tuple[int, int, int, int]]:
    identifier, separator, bounds = raw.partition(":")
    if not separator or not identifier.strip():
        raise argparse.ArgumentTypeError("candidate must be id:left,top,right,bottom")
    return identifier.strip(), _box(bounds)


def _expected(raw: str) -> tuple[str, str]:
    identifier, separator, label = raw.partition("=")
    if not separator or not identifier.strip() or not label.strip():
        raise argparse.ArgumentTypeError("expected label must be id=semantic label")
    return identifier.strip(), label.strip()


def _mapped_bounds(
    bounds: tuple[int, int, int, int],
    crop: tuple[int, int, int, int],
    scale: float,
) -> list[int]:
    left, top, right, bottom = bounds
    crop_left, crop_top, _crop_right, _crop_bottom = crop
    return [
        round((left - crop_left) * scale),
        round((top - crop_top) * scale),
        round((right - crop_left) * scale),
        round((bottom - crop_top) * scale),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--crop", required=True, type=_box)
    parser.add_argument("--candidate", action="append", required=True, type=_candidate)
    parser.add_argument("--expected", action="append", default=[], type=_expected)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000/v1")
    parser.add_argument("--model", default="EXAONE-4.5-33B")
    parser.add_argument("--goal", default="알림 설정을 열고 싶어")
    parser.add_argument("--max-width", type=int, default=720)
    parser.add_argument(
        "--cache",
        type=Path,
        default=REPOSITORY_ROOT / ".artifacts" / "vlm-smoke-cache.sqlite",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional privacy-safe JSON report path. The image and its path are never written.",
    )
    arguments = parser.parse_args()

    with Image.open(arguments.image) as source:
        source_width, source_height = source.size
        left, top, right, bottom = arguments.crop
        if left < 0 or top < 0 or right > source_width or bottom > source_height:
            parser.error("crop falls outside the source image")
        cropped = source.convert("RGB").crop(arguments.crop)
    scale = min(1.0, arguments.max_width / cropped.width)
    if scale < 1.0:
        cropped = cropped.resize(
            (round(cropped.width * scale), round(cropped.height * scale)),
            Image.Resampling.LANCZOS,
        )
    output = io.BytesIO()
    cropped.save(output, format="JPEG", quality=88, optimize=True)
    image_bytes = output.getvalue()
    if len(image_bytes) > 1_100_000:
        parser.error("in-memory crop is too large for the VLM adapter")

    elements = []
    candidates = []
    for identifier, source_bounds in arguments.candidate:
        mapped = _mapped_bounds(source_bounds, arguments.crop, scale)
        elements.append(
            {
                "id": identifier,
                "role": "image",
                "clickable": True,
                "enabled": True,
                "visible": True,
                "bounds": mapped,
            }
        )
        candidates.append(
            UniversalNavigationCandidate(
                element_id=identifier,
                element_key=f"smoke:{identifier}",
                label="이름 없는 아이콘",
                role="image",
                risk_level="low",
            )
        )

    request = UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": "vlm-live-smoke",
            "session_id": "vlm-live-smoke",
            "app_package": "smoke.redacted.toolbar",
            "app_version": "1",
            "locale": "ko-KR",
            "goal_text": arguments.goal,
            "operation_mode": "explore",
            "screen": {
                "activity_name": "RedactedToolbar",
                "window_title": "앱 상단 도구 모음",
                "elements": elements,
            },
            "visual_context": {
                "content_type": "image/jpeg",
                "image_base64": base64.b64encode(image_bytes).decode("ascii"),
                "width": cropped.width,
                "height": cropped.height,
                "redacted": True,
            },
        }
    )
    settings = Settings(
        navigation_vlm_enabled=True,
        navigation_vlm_base_url=arguments.base_url,
        navigation_vlm_model=arguments.model,
        navigation_vlm_timeout_seconds=90.0,
        navigation_vlm_cache_path=str(arguments.cache),
    )
    hint = ExaoneNavigationVlm(settings).analyze(request=request, candidates=candidates)
    if hint is None:
        raise RuntimeError("VLM did not run for ambiguous candidates")
    expected = dict(arguments.expected)
    actual = {
        item.element_id: item.visual_label
        for item in hint.candidates
    }
    matches = {
        identifier: bool(
            identifier in actual
            and label.casefold() in actual[identifier].casefold()
        )
        for identifier, label in expected.items()
    }
    report = {
        "schema_version": 1,
        "evaluation_mode": "privacy_safe_live_vlm_smoke",
        "model": arguments.model,
        "goal": arguments.goal,
        "image_sent": {
            "width": cropped.width,
            "height": cropped.height,
            "bytes": len(image_bytes),
            "redacted": True,
            "persisted": False,
        },
        "expected_labels": expected,
        "matched": matches,
        "case_count": len(expected),
        "matched_count": sum(matches.values()),
        "accuracy": (
            round(sum(matches.values()) / len(expected), 6)
            if expected
            else None
        ),
        "result": hint.prompt_payload(),
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
