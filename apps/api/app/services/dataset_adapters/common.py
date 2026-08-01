from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


STAGING_SCHEMA_VERSION = "1.0"
SUPPORTED_RECORD_TYPES = {
    "terms_document",
    "terms_clause",
    "privacy_policy_document",
    "privacy_policy_segment",
    "consumer_guidance",
    "privacy_qa",
}


@dataclass(frozen=True)
class NormalizedTermsRecord:
    record_id: str
    source_id: str
    split: str
    locale: str
    service_name: str
    document_type: str
    category: str
    version_at: str
    text: str
    content_sha256: str
    review_status: str
    license_notes: str
    provenance: dict[str, str]
    annotations: list[dict[str, object]] = field(default_factory=list)
    schema_version: str = STAGING_SCHEMA_VERSION
    record_type: str = "terms_document"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_text(value: str) -> str:
    lines = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_record_id(source_id: str, source_locator: str) -> str:
    digest = hashlib.sha256(f"{source_id}:{source_locator}".encode("utf-8")).hexdigest()[:16]
    return f"nd_{digest}"


def write_jsonl(records: Iterable[NormalizedTermsRecord], output_path: Path) -> tuple[int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count, output_path.stat().st_size


def write_manifest(output_path: Path, payload: dict[str, object]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def input_file_descriptor(path: Path) -> dict[str, object]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
