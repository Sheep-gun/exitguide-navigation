import json
from typing import Any

import httpx


def response_error_detail(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        return compact_text(response.text)

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            status = error.get("status")
            message = error.get("message")
            if status and message:
                return compact_text(f"{status}: {message}")
            if message:
                return compact_text(str(message))
        detail = body.get("detail")
        if isinstance(detail, str):
            return compact_text(detail)

    return compact_text(json.dumps(body, ensure_ascii=False))


def compact_json(value: Any) -> str:
    return compact_text(json.dumps(value, ensure_ascii=False, default=str))


def compact_text(value: str | None, limit: int = 360) -> str:
    compacted = " ".join((value or "").split())
    if not compacted:
        return "empty response body"
    if len(compacted) <= limit:
        return compacted
    return f"{compacted[: limit - 1]}..."


def extract_model_json_text(content: str) -> str:
    parsed = load_model_json(content)
    return json.dumps(parsed, ensure_ascii=False)


def load_model_json(content: str) -> Any:
    cleaned = _strip_json_fence(content)
    decoder = json.JSONDecoder()
    first_error: json.JSONDecodeError | None = None

    for candidate in _json_candidates(cleaned):
        try:
            value, _index = decoder.raw_decode(candidate)
            return value
        except json.JSONDecodeError as exc:
            first_error = first_error or exc

    if first_error:
        raise first_error
    return json.loads(cleaned)


def _json_candidates(content: str) -> list[str]:
    candidates = [content.strip()]
    for opener in ("{", "["):
        start = content.find(opener)
        while start >= 0:
            candidate = content[start:].strip()
            if candidate not in candidates:
                candidates.append(candidate)
            start = content.find(opener, start + 1)
    return [candidate for candidate in candidates if candidate]


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped
