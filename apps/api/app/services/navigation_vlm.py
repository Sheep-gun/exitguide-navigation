from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.resource_paths import get_resource_root
from app.schemas import UniversalNavigationCandidate, UniversalNavigationObserveRequest
from app.services.provider_errors import compact_text, response_error_detail
from app.services.universal_navigation_graph import sanitize_text


UNNAMED_LABEL_MARKERS = (
    "이름 없는",
    "라벨 없는",
    "unnamed",
    "unlabeled",
    "unknown icon",
)


@dataclass(frozen=True)
class VisualCandidateMeaning:
    element_id: str
    visual_label: str
    role: str
    confidence: float


@dataclass(frozen=True)
class NavigationVisualHint:
    screen_summary: str
    candidates: tuple[VisualCandidateMeaning, ...]
    model: str
    cache_hit: bool = False

    def prompt_payload(self) -> dict[str, object]:
        return {
            "source": "exaone_4_5_vlm",
            "screen_summary": self.screen_summary,
            "candidate_semantics": [
                {
                    "element_id": item.element_id,
                    "visual_label": item.visual_label,
                    "role": item.role,
                    "confidence": round(item.confidence, 4),
                }
                for item in self.candidates
            ],
            "model": self.model,
            "cache_hit": self.cache_hit,
        }


def needs_visual_reasoning(
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
) -> bool:
    if request.visual_context is None:
        return False
    if any(
        any(marker in candidate.label.casefold() for marker in UNNAMED_LABEL_MARKERS)
        for candidate in candidates
    ):
        return True
    for element in request.screen.elements:
        role = element.role.casefold()
        view_id = (element.view_id or "").casefold()
        if "webview" in role or "webview" in view_id or "canvas" in role:
            return True
        if element.clickable and not (element.text or element.content_description or element.view_id):
            return True
    return False


class ExaoneNavigationVlm:
    """Ambiguity-only EXAONE 4.5 screen interpreter with a metadata-only cache."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        cache_path = Path(settings.navigation_vlm_cache_path)
        self.cache_path = cache_path if cache_path.is_absolute() else get_resource_root() / cache_path

    def analyze(
        self,
        *,
        request: UniversalNavigationObserveRequest,
        candidates: list[UniversalNavigationCandidate],
    ) -> NavigationVisualHint | None:
        visual = request.visual_context
        if not self.settings.navigation_vlm_enabled or visual is None:
            return None
        if not needs_visual_reasoning(request, candidates):
            return None
        try:
            image_bytes = base64.b64decode(visual.image_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("visual context is not valid base64") from exc
        if not image_bytes or len(image_bytes) > 1_100_000:
            raise RuntimeError("visual context exceeds the ambiguity-analysis limit")
        cache_key = self._cache_key(image_bytes, request, candidates)
        cached = self._cached(cache_key)
        if cached is not None:
            return NavigationVisualHint(
                screen_summary=cached.screen_summary,
                candidates=cached.candidates,
                model=cached.model,
                cache_hit=True,
            )

        candidate_ids = [candidate.element_id for candidate in candidates]
        prompt = _visual_prompt(request, candidates)
        image_url = f"data:{visual.content_type};base64,{visual.image_base64}"
        payload = {
            "model": self.settings.navigation_vlm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are EXAONE 4.5 acting only as ExitGuideLab's visual perception module. "
                        "Identify the visual meaning of the supplied candidate regions. Do not choose or click "
                        "an action. Return strict JSON and never invent candidate IDs."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "temperature": 0.0,
            "max_tokens": 900,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        response = None
        try:
            response = httpx.post(
                f"{self.settings.navigation_vlm_base_url.rstrip('/')}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.settings.navigation_vlm_timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            hint = _parse_visual_hint(content, candidate_ids, self.settings.navigation_vlm_model)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"EXAONE 4.5 VLM HTTP {exc.response.status_code}: {response_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"EXAONE 4.5 VLM connection failed: {compact_text(str(exc))}") from exc
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"EXAONE 4.5 VLM returned invalid JSON: {compact_text(str(exc))}") from exc
        self._store(cache_key, hint)
        return hint

    def _cache_key(
        self,
        image_bytes: bytes,
        request: UniversalNavigationObserveRequest,
        candidates: list[UniversalNavigationCandidate],
    ) -> str:
        payload = json.dumps(
            {
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "model": self.settings.navigation_vlm_model,
                "app_package": request.app_package,
                "candidate_ids": [candidate.element_id for candidate in candidates],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _connect(self) -> sqlite3.Connection:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.cache_path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS navigation_vlm_cache (
              cache_key TEXT PRIMARY KEY,
              model TEXT NOT NULL,
              result_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        return connection

    def _cached(self, cache_key: str) -> NavigationVisualHint | None:
        if not self.cache_path.is_file():
            return None
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT result_json FROM navigation_vlm_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return _parse_visual_hint(row[0], None, self.settings.navigation_vlm_model)

    def _store(self, cache_key: str, hint: NavigationVisualHint) -> None:
        # Only model output is cached. The privacy-masked screenshot is never
        # persisted by the API or embedded in the database.
        result_json = json.dumps(
            {
                "screen_summary": hint.screen_summary,
                "candidates": [
                    {
                        "element_id": item.element_id,
                        "visual_label": item.visual_label,
                        "role": item.role,
                        "confidence": item.confidence,
                    }
                    for item in hint.candidates
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT OR REPLACE INTO navigation_vlm_cache(cache_key, model, result_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    cache_key,
                    hint.model,
                    result_json,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
        finally:
            connection.close()


def apply_visual_hints(
    candidates: list[UniversalNavigationCandidate],
    hint: NavigationVisualHint | None,
) -> list[UniversalNavigationCandidate]:
    if hint is None:
        return candidates
    meanings = {
        item.element_id: item
        for item in hint.candidates
        if item.confidence >= 0.55 and item.visual_label
    }
    enhanced: list[UniversalNavigationCandidate] = []
    for candidate in candidates:
        meaning = meanings.get(candidate.element_id)
        is_unnamed = any(marker in candidate.label.casefold() for marker in UNNAMED_LABEL_MARKERS)
        if meaning is None or not is_unnamed:
            enhanced.append(candidate)
            continue
        enhanced.append(
            candidate.model_copy(
                update={
                    "label": sanitize_text(meaning.visual_label)[:500],
                    "role": sanitize_text(meaning.role or candidate.role)[:80],
                }
            )
        )
    return enhanced


def _visual_prompt(
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
) -> str:
    element_by_id = {element.id: element for element in request.screen.elements}
    payload = {
        "task": "Describe only candidate icons or controls whose accessibility meaning is incomplete.",
        "screen": {
            "width": request.visual_context.width if request.visual_context else 0,
            "height": request.visual_context.height if request.visual_context else 0,
            "window_title": sanitize_text(request.screen.window_title),
        },
        "candidates": [
            {
                "element_id": candidate.element_id,
                "current_label": candidate.label,
                "role": candidate.role,
                "bounds": element_by_id.get(candidate.element_id).bounds
                if element_by_id.get(candidate.element_id)
                else None,
            }
            for candidate in candidates
        ],
        "output_schema": {
            "screen_summary": "string",
            "candidates": [
                {
                    "element_id": "one supplied ID",
                    "visual_label": "short functional label",
                    "role": "button|tab|menu|image|unknown",
                    "confidence": "number from 0 to 1",
                }
            ],
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _parse_visual_hint(
    raw: object,
    candidate_ids: list[str] | None,
    model: str,
) -> NavigationVisualHint:
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL)
        payload = json.loads(text)
    elif isinstance(raw, dict):
        payload = raw
    else:
        raise ValueError("VLM result must be a JSON object")
    if not isinstance(payload, dict) or set(payload) != {"screen_summary", "candidates"}:
        raise ValueError("VLM result does not match the strict schema")
    summary = payload["screen_summary"]
    items = payload["candidates"]
    if not isinstance(summary, str) or not isinstance(items, list):
        raise ValueError("VLM result fields have invalid types")
    allowed = set(candidate_ids) if candidate_ids is not None else None
    meanings: list[VisualCandidateMeaning] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {
            "element_id",
            "visual_label",
            "role",
            "confidence",
        }:
            raise ValueError("VLM candidate does not match the strict schema")
        element_id = item["element_id"]
        label = item["visual_label"]
        role = item["role"]
        confidence = item["confidence"]
        if not all(type(value) is str for value in (element_id, label, role)):
            raise ValueError("VLM candidate string fields are invalid")
        if type(confidence) not in {int, float} or not math.isfinite(float(confidence)):
            raise ValueError("VLM candidate confidence is invalid")
        if allowed is not None and element_id not in allowed:
            raise ValueError("VLM invented a candidate ID")
        if element_id in seen or not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("VLM candidate is duplicated or has invalid confidence")
        seen.add(element_id)
        meanings.append(
            VisualCandidateMeaning(
                element_id=element_id,
                visual_label=sanitize_text(label)[:500],
                role=sanitize_text(role)[:80],
                confidence=float(confidence),
            )
        )
    return NavigationVisualHint(
        screen_summary=sanitize_text(summary)[:1000],
        candidates=tuple(meanings),
        model=model,
    )
