import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, get_args
from urllib.parse import urlparse, urlunparse

from pydantic import ValidationError

from app.schemas import (
    TermsCaptureImportItem,
    TermsCaptureImportResponse,
    TermsCollectionMethod,
    TermsDocument,
    TermsDocumentType,
    TermsRetrievalStatus,
    TermsSection,
)
from app.services.terms_corpus import DEFAULT_DB_PATH, FORBIDDEN_PATTERNS, ROOT, build_terms_corpus_sqlite


IMPORTER_VERSION = "terms_ingestion_v1"
MIN_CAPTURE_TEXT_CHARS = 80
MAX_CAPTURE_TEXT_CHARS = 200_000
MAX_CAPTURE_FILE_BYTES = 2_000_000
MAX_CAPTURE_RECORDS_PER_RUN = 500
MAX_TOTAL_CAPTURE_TEXT_CHARS = 2_000_000
VALID_COLLECTION_METHODS = set(get_args(TermsCollectionMethod))
VALID_DOCUMENT_TYPES = set(get_args(TermsDocumentType))
VALID_RETRIEVAL_STATUSES = set(get_args(TermsRetrievalStatus))
SUCCESS_RETRIEVAL_STATUSES = {"captured", "success", "ok", "complete", "completed"}
REJECTED_RETRIEVAL_STATUSES = {
    "failed",
    "partial",
    "blocked",
    "login_required",
    "captcha",
    "timeout",
    "needs_review",
    "error",
}
CAPTURE_FORBIDDEN_PATTERNS = {
    "resident_registration": re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b"),
    "foreigner_registration": re.compile(r"\b\d{6}[-\s]?[5-8]\d{6}\b"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    "cookie_or_session": re.compile(r"\b(cookie|sessionid|session_id|access_token|refresh_token|auth_token)\b", re.IGNORECASE),
    "order_or_payment_id": re.compile(r"(주문|결제|고객|회원)\s*(번호|id|ID)\s*[:=]\s*[A-Za-z0-9_-]{6,}"),
}

DOCUMENT_TYPE_RULES = [
    ("privacy_policy", ["개인정보", "privacy", "personal information"]),
    ("subscription_terms", ["구독", "자동 갱신", "정기 결제", "subscription"]),
    ("location_terms", ["위치정보", "위치 기반", "location"]),
    ("cancellation_policy", ["해지", "환불", "취소", "cancel", "refund"]),
    ("marketing_terms", ["마케팅", "광고성", "혜택 알림", "marketing"]),
    ("terms_of_service", ["이용약관", "서비스 약관", "terms of service"]),
]
TAG_RULES = {
    "subscription": ["구독", "자동 갱신", "정기 결제"],
    "renewal": ["자동 갱신", "갱신"],
    "cancellation": ["해지", "취소"],
    "refund": ["환불"],
    "privacy": ["개인정보", "privacy"],
    "third_party": ["제3자", "제삼자", "third party"],
    "marketing": ["마케팅", "광고성", "혜택 알림"],
    "location": ["위치정보", "위치 기반", "location"],
    "billing_notice": ["결제 예정", "다음 결제", "정기 결제"],
}


def ingest_terms_captures(input_path: Path, output_path: Path = DEFAULT_DB_PATH) -> TermsCaptureImportResponse:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    capture_files = _collect_capture_files(input_path)

    items: list[TermsCaptureImportItem] = []
    imported_documents: list[TermsDocument] = []
    imported_items_by_document_id: dict[str, TermsCaptureImportItem] = {}
    _existing_documents, seen_hashes = _load_current_imported_documents(output_path)
    total_text_chars = 0

    for capture_file in capture_files:
        for index, record in enumerate(_read_capture_records(capture_file)):
            item, document = _normalize_capture_record(record, capture_file, index, seen_hashes)
            items.append(item)
            if document:
                total_text_chars += sum(len(section.text) for section in document.sections)
                if total_text_chars > MAX_TOTAL_CAPTURE_TEXT_CHARS:
                    raise ValueError(f"terms capture text exceeds run limit: {MAX_TOTAL_CAPTURE_TEXT_CHARS}")
                imported_documents.append(document)
                imported_items_by_document_id[document.id] = item

    _write_document_registry(output_path, imported_documents, imported_items_by_document_id)
    build_terms_corpus_sqlite(output_path)
    _write_ingestion_tables(output_path, input_path, items)

    return TermsCaptureImportResponse(
        input_path=str(input_path),
        output_path=str(output_path),
        capture_count=len(items),
        imported_document_count=sum(1 for item in items if item.status == "imported"),
        rejected_count=sum(1 for item in items if item.status == "rejected"),
        duplicate_count=sum(1 for item in items if item.status == "duplicate"),
        items=items,
    )


def _collect_capture_files(input_path: Path) -> list[Path]:
    if not input_path.exists():
        raise FileNotFoundError(f"terms capture path does not exist: {input_path}")
    if input_path.is_file():
        if input_path.stat().st_size > MAX_CAPTURE_FILE_BYTES:
            raise ValueError(f"terms capture file is too large: {input_path}")
        return [input_path]
    files = sorted(path for path in input_path.rglob("*.json") if path.is_file())
    if not files:
        raise FileNotFoundError(f"no JSON capture files found under: {input_path}")
    oversized = [path for path in files if path.stat().st_size > MAX_CAPTURE_FILE_BYTES]
    if oversized:
        raise ValueError(f"terms capture file is too large: {oversized[0]}")
    return files


def _read_capture_records(capture_file: Path) -> list[dict[str, Any]]:
    payload = json.loads(capture_file.read_text(encoding="utf-8-sig"))
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and isinstance(payload.get("captures"), list):
        records = payload["captures"]
    elif isinstance(payload, dict):
        records = [payload]
    else:
        raise ValueError(f"unsupported capture JSON shape: {capture_file}")

    normalized: list[dict[str, Any]] = []
    if len(records) > MAX_CAPTURE_RECORDS_PER_RUN:
        raise ValueError(f"too many capture records in one run: {len(records)}")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"capture record must be an object: {capture_file}")
        normalized.append(record)
    return normalized


def _normalize_capture_record(
    record: dict[str, Any],
    source_path: Path,
    index: int,
    seen_hashes: dict[str, str],
) -> tuple[TermsCaptureImportItem, TermsDocument | None]:
    errors: list[str] = []
    warnings: list[str] = []

    capture_id = _pick_string(record, "capture_id", "id") or f"{source_path.stem}_{index + 1}"
    source_url = _pick_string(record, "source_url", "url", "page_url", "canonical_url")
    source_url, url_warning = _sanitize_source_url(source_url)
    if url_warning:
        warnings.append(url_warning)
    service_name = _pick_string(record, "service_name", "site_name", "title", "name") or "Unknown Service"
    provider_name = _pick_string(record, "provider_name", "operator_name", "company_name") or service_name
    collection_method = _normalize_collection_method(record)
    retrieval_status = _normalize_retrieval_status(record)
    locale = _pick_string(record, "locale") or "ko-KR"
    raw_text = _extract_capture_text(record)
    clean_text = _clean_text(raw_text)
    content_sha256 = _sha256(clean_text) if clean_text else None

    if not _valid_http_url(source_url):
        errors.append("source_url must be an http(s) URL")
    if retrieval_status != "captured":
        errors.append(f"retrieval_status must be captured; got {retrieval_status}")
    if locale != "ko-KR":
        errors.append(f"locale must be ko-KR; got {locale}")
    if len(clean_text) < MIN_CAPTURE_TEXT_CHARS:
        errors.append(f"capture text must be at least {MIN_CAPTURE_TEXT_CHARS} characters")
    if len(clean_text) > MAX_CAPTURE_TEXT_CHARS:
        errors.append(f"capture text must be at most {MAX_CAPTURE_TEXT_CHARS} characters")
    if bool(record.get("raw_personal_data")):
        errors.append("raw_personal_data captures cannot be imported")
    _check_forbidden_text(clean_text, errors)
    _check_forbidden_metadata(record, errors)
    if bool(record.get("public_fixture_allowed")):
        warnings.append("public_fixture_allowed is ignored for imported captures")

    base_item = {
        "capture_id": capture_id,
        "source_path": _storage_path(source_path),
        "source_url": source_url,
        "collection_method": collection_method,
        "content_sha256": content_sha256,
        "document_id": None,
    }

    if errors:
        return TermsCaptureImportItem(status="rejected", errors=errors, warnings=warnings, **base_item), None

    if content_sha256 in seen_hashes:
        warnings.append(f"duplicate content of {seen_hashes[content_sha256]}")
        return (
            TermsCaptureImportItem(
                status="duplicate",
                errors=[],
                warnings=warnings,
                document_id=seen_hashes[content_sha256],
                **{key: value for key, value in base_item.items() if key != "document_id"},
            ),
            None,
        )

    document_type = _normalize_document_type(record, clean_text)
    document_id = _stable_document_id(service_name, document_type, content_sha256 or capture_id)
    sections = _build_sections(record, clean_text)
    tags = _infer_tags(record, clean_text, document_type)
    collected_at = _pick_string(record, "collected_at", "retrieved_at", "captured_at") or _now_iso()
    license_notes = (
        _pick_string(record, "license_notes", "license", "rights")
        or "Imported capture. Review source terms and copyright before promoting into repository fixtures."
    )

    try:
        document = TermsDocument(
            id=document_id,
            service_name=service_name,
            provider_name=provider_name,
            document_type=document_type,
            locale=_pick_string(record, "locale") or "ko-KR",
            source_url=source_url,
            collected_at=collected_at,
            collection_method=collection_method,
            retrieval_status=retrieval_status,
            public_fixture_allowed=False,
            raw_personal_data=False,
            license_notes=license_notes,
            tags=tags,
            sections=sections,
        )
    except ValidationError as exc:
        return TermsCaptureImportItem(status="rejected", errors=[str(exc)], warnings=warnings, **base_item), None

    seen_hashes[content_sha256 or document_id] = document_id
    return (
        TermsCaptureImportItem(
            status="imported",
            errors=[],
            warnings=warnings,
            document_id=document_id,
            **{key: value for key, value in base_item.items() if key != "document_id"},
        ),
        document,
    )


def _normalize_collection_method(record: dict[str, Any]) -> TermsCollectionMethod:
    raw_value = (_pick_string(record, "collection_method", "capture_method") or "").lower()
    source_tool = (_pick_string(record, "source_tool", "tool", "agent") or "").lower()
    if raw_value in VALID_COLLECTION_METHODS:
        return raw_value  # type: ignore[return-value]
    if "openclaw" in source_tool or "openclaw" in raw_value:
        return "openclaw"
    if "manual" in source_tool or "manual" in raw_value:
        return "manual"
    return "imported"


def _normalize_retrieval_status(record: dict[str, Any]) -> TermsRetrievalStatus:
    raw_value = (_pick_string(record, "retrieval_status", "status") or "").lower()
    if raw_value in VALID_RETRIEVAL_STATUSES:
        return raw_value  # type: ignore[return-value]
    if raw_value in SUCCESS_RETRIEVAL_STATUSES:
        return "captured"
    if raw_value in REJECTED_RETRIEVAL_STATUSES or not raw_value:
        return "needs_review"
    return "needs_review"


def _normalize_document_type(record: dict[str, Any], clean_text: str) -> TermsDocumentType:
    raw_value = (_pick_string(record, "document_type", "terms_type", "type") or "").lower()
    if raw_value in VALID_DOCUMENT_TYPES:
        return raw_value  # type: ignore[return-value]

    haystack = " ".join(
        [
            _pick_string(record, "title", "service_name", "source_url", "url"),
            clean_text[:5000],
        ]
    ).lower()
    for document_type, keywords in DOCUMENT_TYPE_RULES:
        if any(keyword.lower() in haystack for keyword in keywords):
            return document_type  # type: ignore[return-value]
    return "unknown"


def _extract_capture_text(record: dict[str, Any]) -> str:
    text = _pick_string(record, "raw_text", "text", "markdown", "content", "body_text", "page_text")
    if text:
        return text
    html = _pick_string(record, "html", "raw_html", "page_html")
    if html:
        return _strip_html(html)
    return ""


def _strip_html(html: str) -> str:
    without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return re.sub(r"\s+", " ", without_tags).strip()


def _build_sections(record: dict[str, Any], clean_text: str) -> list[TermsSection]:
    raw_sections = record.get("sections")
    if isinstance(raw_sections, list):
        sections = _sections_from_payload(raw_sections)
        if sections:
            return sections
    return _auto_sections(clean_text)


def _sections_from_payload(raw_sections: list[Any]) -> list[TermsSection]:
    sections: list[TermsSection] = []
    used_ids: set[str] = set()
    for index, raw_section in enumerate(raw_sections, start=1):
        if not isinstance(raw_section, dict):
            continue
        heading = _pick_string(raw_section, "heading", "title", "name") or f"본문 {index}"
        text = _clean_text(_pick_string(raw_section, "text", "content", "body"))
        if not text:
            continue
        section_id = _unique_section_id(_slug(_pick_string(raw_section, "id") or heading), index, used_ids)
        sections.append(TermsSection(id=section_id, heading=heading, text=text))
    return sections


def _auto_sections(clean_text: str) -> list[TermsSection]:
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    if not lines:
        return []

    sections: list[TermsSection] = []
    used_ids: set[str] = set()
    heading = "본문"
    body: list[str] = []

    for line in lines:
        if _looks_like_heading(line):
            if body:
                index = len(sections) + 1
                section_id = _unique_section_id(_slug(heading), index, used_ids)
                sections.append(TermsSection(id=section_id, heading=heading, text=" ".join(body)))
                body = []
            heading = line
        else:
            body.append(line)

    if body:
        index = len(sections) + 1
        section_id = _unique_section_id(_slug(heading), index, used_ids)
        sections.append(TermsSection(id=section_id, heading=heading, text=" ".join(body)))

    if sections:
        return sections
    return [TermsSection(id="section_001", heading="본문", text=clean_text)]


def _looks_like_heading(line: str) -> bool:
    if len(line) > 80:
        return False
    if re.match(r"^(제\s*\d+\s*조|제\d+조|\d+[\.\)]|[IVX]+[\.\)])", line, re.IGNORECASE):
        return True
    return line.endswith(("안내", "고지", "제공", "해지", "환불", "처리", "수집", "철회", "동의"))


def _infer_tags(record: dict[str, Any], clean_text: str, document_type: str) -> list[str]:
    raw_tags = record.get("tags")
    tags = {str(tag).strip().lower().replace(" ", "_") for tag in raw_tags if str(tag).strip()} if isinstance(raw_tags, list) else set()
    if document_type != "unknown":
        tags.add(document_type)
    for tag, keywords in TAG_RULES.items():
        if any(keyword.lower() in clean_text.lower() for keyword in keywords):
            tags.add(tag)
    return sorted(tags)


def _write_ingestion_tables(output_path: Path, input_path: Path, items: list[TermsCaptureImportItem]) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    run_id = "tir_" + _sha256(f"{input_path}:{output_path}:{now}")[:12]
    connection = sqlite3.connect(output_path)
    try:
        ensure_terms_registry_tables(connection)
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS terms_ingestion_runs (
              run_id TEXT PRIMARY KEY,
              importer_version TEXT NOT NULL,
              input_path TEXT NOT NULL,
              output_path TEXT NOT NULL,
              capture_count INTEGER NOT NULL,
              imported_document_count INTEGER NOT NULL,
              rejected_count INTEGER NOT NULL,
              duplicate_count INTEGER NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS terms_capture_staging (
              run_id TEXT NOT NULL,
              capture_id TEXT NOT NULL,
              source_path TEXT NOT NULL,
              source_url TEXT NOT NULL,
              collection_method TEXT,
              content_sha256 TEXT,
              imported_document_id TEXT,
              status TEXT NOT NULL,
              errors_json TEXT NOT NULL,
              warnings_json TEXT NOT NULL,
              ingested_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_terms_capture_staging_hash
            ON terms_capture_staging(content_sha256);

            CREATE INDEX IF NOT EXISTS idx_terms_capture_staging_status
            ON terms_capture_staging(status);
            """
        )
        connection.execute(
            """
            INSERT INTO terms_ingestion_runs (
              run_id, importer_version, input_path, output_path, capture_count,
              imported_document_count, rejected_count, duplicate_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                IMPORTER_VERSION,
                _storage_path(input_path),
                _storage_path(output_path),
                len(items),
                sum(1 for item in items if item.status == "imported"),
                sum(1 for item in items if item.status == "rejected"),
                sum(1 for item in items if item.status == "duplicate"),
                now,
            ),
        )
        connection.executemany(
            """
            INSERT INTO terms_capture_staging (
              run_id, capture_id, source_path, source_url, collection_method,
              content_sha256, imported_document_id, status, errors_json, warnings_json,
              ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    item.capture_id,
                    item.source_path,
                    item.source_url,
                    item.collection_method,
                    item.content_sha256,
                    item.document_id,
                    item.status,
                    json.dumps(item.errors, ensure_ascii=False),
                    json.dumps(item.warnings, ensure_ascii=False),
                    now,
                )
                for item in items
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _load_current_imported_documents(output_path: Path) -> tuple[list[TermsDocument], dict[str, str]]:
    if not output_path.exists():
        return [], {}

    connection = sqlite3.connect(output_path)
    connection.row_factory = sqlite3.Row
    try:
        ensure_terms_registry_tables(connection)
        current_rows = connection.execute(
            """
            SELECT document_json
            FROM terms_document_versions
            WHERE is_current = 1 AND review_status = 'approved_for_search'
            ORDER BY version_id
            """
        ).fetchall()
        hash_rows = connection.execute(
            """
            SELECT content_sha256, version_id
            FROM terms_document_versions
            WHERE content_sha256 IS NOT NULL
            """
        ).fetchall()
        documents = [TermsDocument.model_validate(json.loads(row["document_json"])) for row in current_rows]
        existing_hashes = {row["content_sha256"]: row["version_id"] for row in hash_rows}
        return documents, existing_hashes
    finally:
        connection.close()


def _write_document_registry(
    output_path: Path,
    documents: list[TermsDocument],
    items_by_document_id: dict[str, TermsCaptureImportItem],
) -> None:
    if not documents:
        return

    now = _now_iso()
    connection = sqlite3.connect(output_path)
    try:
        ensure_terms_registry_tables(connection)
        for document in documents:
            item = items_by_document_id[document.id]
            source_id = _source_id_for_document(document)
            version_id = document.id
            previous_version = connection.execute(
                """
                SELECT version_id
                FROM terms_document_versions
                WHERE source_id = ? AND is_current = 1
                ORDER BY collected_at DESC, created_at DESC
                LIMIT 1
                """,
                (source_id,),
            ).fetchone()
            previous_version_id = previous_version[0] if previous_version else None
            connection.execute(
                """
                INSERT INTO terms_sources (
                  source_id, service_name, provider_name, document_type, canonical_url,
                  source_url, collection_policy_status, robots_checked_at, robots_allowed,
                  license_review_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                  service_name = excluded.service_name,
                  provider_name = excluded.provider_name,
                  source_url = excluded.source_url
                """,
                (
                    source_id,
                    document.service_name,
                    document.provider_name,
                    document.document_type,
                    _canonicalize_url(document.source_url),
                    document.source_url,
                    "pending_review",
                    "",
                    0,
                    "pending_review",
                    now,
                ),
            )
            connection.execute(
                "UPDATE terms_document_versions SET is_current = 0 WHERE source_id = ?",
                (source_id,),
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO terms_document_versions (
                  version_id, source_id, collected_at, collector, collector_version,
                  retrieval_status, http_status, final_url, content_sha256, text_sha256,
                  locale, is_current, supersedes_version_id, review_status,
                  document_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    source_id,
                    document.collected_at,
                    document.collection_method,
                    IMPORTER_VERSION,
                    document.retrieval_status,
                    "",
                    document.source_url,
                    item.content_sha256 or _document_text_sha256(document),
                    _document_text_sha256(document),
                    document.locale,
                    1,
                    previous_version_id,
                    "pending_review",
                    document.model_dump_json(),
                    now,
                ),
            )
        connection.commit()
    finally:
        connection.close()


def ensure_terms_registry_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS terms_sources (
          source_id TEXT PRIMARY KEY,
          service_name TEXT NOT NULL,
          provider_name TEXT NOT NULL,
          document_type TEXT NOT NULL,
          canonical_url TEXT NOT NULL,
          source_url TEXT NOT NULL,
          collection_policy_status TEXT NOT NULL,
          robots_checked_at TEXT NOT NULL,
          robots_allowed INTEGER NOT NULL,
          license_review_status TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS terms_document_versions (
          version_id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL,
          collected_at TEXT NOT NULL,
          collector TEXT NOT NULL,
          collector_version TEXT NOT NULL,
          retrieval_status TEXT NOT NULL,
          http_status TEXT NOT NULL,
          final_url TEXT NOT NULL,
          content_sha256 TEXT NOT NULL,
          text_sha256 TEXT NOT NULL,
          locale TEXT NOT NULL,
          is_current INTEGER NOT NULL,
          supersedes_version_id TEXT,
          review_status TEXT NOT NULL,
          document_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY (source_id) REFERENCES terms_sources(source_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS terms_review_events (
          event_id TEXT PRIMARY KEY,
          version_id TEXT NOT NULL,
          reviewer TEXT NOT NULL,
          decision TEXT NOT NULL,
          reason TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY (version_id) REFERENCES terms_document_versions(version_id) ON DELETE CASCADE
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_terms_document_versions_content_sha
          ON terms_document_versions(content_sha256);
        CREATE INDEX IF NOT EXISTS idx_terms_document_versions_source_current
          ON terms_document_versions(source_id, is_current);
        CREATE INDEX IF NOT EXISTS idx_terms_sources_canonical
          ON terms_sources(canonical_url, document_type);
        """
    )


def _check_forbidden_text(text: str, errors: list[str]) -> None:
    for label, pattern in FORBIDDEN_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"capture text contains forbidden {label}-like text")
    for label, pattern in CAPTURE_FORBIDDEN_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"capture text contains forbidden {label}-like text")


def _check_forbidden_metadata(record: dict[str, Any], errors: list[str]) -> None:
    public_metadata = " ".join(
        _pick_string(record, key)
        for key in (
            "capture_id",
            "id",
            "source_url",
            "url",
            "page_url",
            "canonical_url",
            "service_name",
            "provider_name",
            "license_notes",
        )
    )
    _check_forbidden_text(public_metadata, errors)


def _pick_string(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
        else:
            text = str(value).strip()
        if text:
            return text
    return ""


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _sanitize_source_url(value: str) -> tuple[str, str | None]:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value, None
    sanitized = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            "",
            "",
        )
    )
    if parsed.query or parsed.fragment:
        return sanitized, "source_url query/fragment stripped before storage"
    return sanitized, None


def _canonicalize_url(value: str) -> str:
    sanitized, _warning = _sanitize_source_url(value)
    return sanitized.rstrip("/")


def _stable_document_id(service_name: str, document_type: str, content_key: str) -> str:
    digest = _sha256(f"{service_name}:{document_type}:{content_key}")[:12]
    slug = _slug(service_name) or "service"
    return f"terms_{slug}_{document_type}_{digest}"


def _unique_section_id(base: str, index: int, used_ids: set[str]) -> str:
    candidate = base or f"section_{index:03d}"
    if candidate not in used_ids:
        used_ids.add(candidate)
        return candidate
    suffix = 2
    while f"{candidate}_{suffix}" in used_ids:
        suffix += 1
    unique = f"{candidate}_{suffix}"
    used_ids.add(unique)
    return unique


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value.lower()).strip("_")
    return re.sub(r"_+", "_", slug)[:48]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _document_text_sha256(document: TermsDocument) -> str:
    text = "\n".join(
        [document.service_name, document.provider_name, document.document_type, document.source_url]
        + [section.heading + "\n" + section.text for section in document.sections]
    )
    return _sha256(text)


def _source_id_for_document(document: TermsDocument) -> str:
    digest = _sha256(
        "|".join(
            [
                _canonicalize_url(document.source_url),
                document.document_type,
                document.service_name.lower(),
            ]
        )
    )[:16]
    return f"ts_{digest}"


def _storage_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return f"{resolved.name}#{_sha256(str(resolved))[:8]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
