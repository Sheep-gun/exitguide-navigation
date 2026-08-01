from collections.abc import Iterable
from hashlib import sha256


def stable_trace_id(prefix: str, parts: Iterable[object]) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    digest = sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"
