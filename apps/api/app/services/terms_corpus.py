import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from app.resource_paths import get_resource_root
from app.schemas import (
    TermsChunk,
    TermsCorpusCatalog,
    TermsCorpusMetadata,
    TermsCorpusQualityResponse,
    TermsCorpusSummary,
    TermsCoverageTarget,
    TermsDocument,
    TermsSearchResponse,
    TermsSearchResult,
)


ROOT = get_resource_root()
TERMS_CORPUS_PATH = ROOT / "fixtures" / "terms-corpus" / "documents.json"
DEFAULT_DB_PATH = ROOT / ".artifacts" / "terms-corpus.sqlite"
MAX_CHUNK_CHARS = 700
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]{2,}")
FORBIDDEN_PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "phone": re.compile(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b"),
    "private_key": re.compile(r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----"),
}
LOCAL_SIGNAL_RULES = {
    "자동 갱신": ("auto_renewal", "자동 갱신"),
    "다음 결제": ("billing_notice", "다음 결제"),
    "해지": ("cancellation", "해지"),
    "환불": ("refund", "환불"),
    "제3자": ("third_party_sharing", "제3자"),
    "광고성": ("marketing_consent", "광고성"),
    "마케팅": ("marketing_consent", "마케팅"),
    "전체 동의": ("bundled_consent", "전체 동의"),
    "기본 선택": ("preselected_optional", "기본 선택"),
    "위치 기반": ("location_ads", "위치 기반"),
    "동의 철회": ("withdrawal", "동의 철회"),
}
COVERAGE_TARGETS = {
    "documents_total": ("Total terms documents", 3),
    "subscription_terms": ("Subscription terms documents", 1),
    "privacy_policy": ("Privacy policy documents", 1),
    "location_terms": ("Location terms documents", 1),
    "third_party": ("Third-party sharing tags", 1),
    "marketing": ("Marketing tags", 1),
    "cancellation": ("Cancellation tags", 1),
}


def load_terms_corpus() -> TermsCorpusCatalog:
    payload = json.loads(TERMS_CORPUS_PATH.read_text(encoding="utf-8-sig"))
    metadata = TermsCorpusMetadata.model_validate(payload)
    documents = [TermsDocument.model_validate(document) for document in payload["documents"]]
    _validate_terms_documents(documents)
    chunks = chunk_terms_documents(documents)
    return TermsCorpusCatalog(
        description=payload["description"],
        metadata=metadata,
        summary=_summarize_terms_corpus(documents, chunks),
        documents=documents,
    )


def search_terms_corpus(query: str, top_k: int = 8) -> TermsSearchResponse:
    catalog = load_terms_corpus()
    query_terms = _tokenize(query)
    if not query_terms:
        return TermsSearchResponse(query=query, total=0, results=[])

    chunks = chunk_terms_documents(catalog.documents)
    results: list[TermsSearchResult] = []
    for chunk in chunks:
        haystack = " ".join([chunk.service_name, chunk.document_type, chunk.heading, chunk.text, " ".join(chunk.tags)])
        haystack_terms = set(_tokenize(haystack))
        matched = sorted(term for term in query_terms if term in haystack_terms or term in haystack)
        if not matched:
            continue
        score = len(matched) * 10
        score += sum(3 for signal in chunk.signals if any(term in signal for term in matched))
        score += sum(2 for tag in chunk.tags if any(term in tag for term in matched))
        results.append(TermsSearchResult(chunk=chunk, score=score, matched_terms=matched))

    results.sort(key=lambda result: (-result.score, result.chunk.document_id, result.chunk.section_id))
    limited = results[: max(1, min(top_k, 25))]
    return TermsSearchResponse(query=query, total=len(results), results=limited)


def search_terms_corpus_sqlite(query: str, top_k: int = 8, db_path: Path = DEFAULT_DB_PATH) -> TermsSearchResponse:
    query_terms = _tokenize(query)
    if not query_terms:
        return TermsSearchResponse(query=query, total=0, results=[])
    if not db_path.exists():
        return search_terms_corpus(query=query, top_k=top_k)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        fts_query = " OR ".join(f'"{term}"' for term in query_terms)
        try:
            rows = connection.execute(
                """
                SELECT
                  c.id, c.document_id, c.section_id, d.service_name, d.document_type,
                  c.heading, c.text, c.tags_json, c.signals_json,
                  bm25(terms_chunks_fts) AS rank
                FROM terms_chunks_fts
                JOIN terms_chunks c ON c.id = terms_chunks_fts.id
                JOIN terms_documents d ON d.id = c.document_id
                WHERE terms_chunks_fts MATCH ?
                ORDER BY rank ASC, c.document_id, c.section_id
                LIMIT ?
                """,
                (fts_query, max(1, min(top_k, 25))),
            ).fetchall()
        except sqlite3.OperationalError:
            return _search_sqlite_lexical(connection, query, query_terms, top_k)
    finally:
        connection.close()

    results = [_row_to_search_result(row, query_terms) for row in rows]
    return TermsSearchResponse(query=query, total=len(results), results=results)


def build_terms_corpus_quality() -> TermsCorpusQualityResponse:
    catalog = load_terms_corpus()
    targets = _build_coverage_targets(catalog.summary)
    warnings = [
        f"{target.label}: {target.actual}/{target.target}"
        for target in targets
        if not target.passed
    ]
    return TermsCorpusQualityResponse(
        status="pass" if not warnings else "warn",
        metadata=catalog.metadata,
        summary=catalog.summary,
        coverage_targets=targets,
        warnings=warnings,
    )


def chunk_terms_documents(documents: list[TermsDocument]) -> list[TermsChunk]:
    chunks: list[TermsChunk] = []
    for document in documents:
        for section in document.sections:
            for index, text in enumerate(_split_text(section.text)):
                chunk_id = _stable_chunk_id(document.id, section.id, index, text)
                chunks.append(
                    TermsChunk(
                        id=chunk_id,
                        document_id=document.id,
                        section_id=section.id,
                        service_name=document.service_name,
                        document_type=document.document_type,
                        heading=section.heading,
                        text=text,
                        tags=document.tags,
                        signals=_detect_local_signals(" ".join([section.heading, text])),
                    )
                )
    return chunks


def build_terms_corpus_sqlite(output_path: Path = DEFAULT_DB_PATH, extra_documents: list[TermsDocument] | None = None) -> Path:
    catalog = load_terms_corpus()
    documents = list(catalog.documents)
    if extra_documents is None:
        extra_documents = _load_registered_terms_documents(output_path)
    if extra_documents:
        documents.extend(extra_documents)
        _validate_terms_documents(documents, require_public_fixture=False, require_captured=False)
    chunks = chunk_terms_documents(documents)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(output_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
            DROP TABLE IF EXISTS terms_chunks_fts;
            DROP TABLE IF EXISTS terms_signals;
            DROP TABLE IF EXISTS terms_document_tags;
            DROP TABLE IF EXISTS terms_chunks;
            DROP TABLE IF EXISTS terms_sections;
            DROP TABLE IF EXISTS terms_documents;

            CREATE TABLE terms_documents (
              id TEXT PRIMARY KEY,
              service_name TEXT NOT NULL,
              provider_name TEXT NOT NULL,
              document_type TEXT NOT NULL,
              locale TEXT NOT NULL,
              source_url TEXT NOT NULL,
              collected_at TEXT NOT NULL,
              collection_method TEXT NOT NULL,
              retrieval_status TEXT NOT NULL,
              public_fixture_allowed INTEGER NOT NULL,
              raw_personal_data INTEGER NOT NULL,
              license_notes TEXT NOT NULL,
              tags_json TEXT NOT NULL
            );

            CREATE TABLE terms_sections (
              id TEXT NOT NULL,
              document_id TEXT NOT NULL,
              heading TEXT NOT NULL,
              text TEXT NOT NULL,
              PRIMARY KEY (document_id, id),
              FOREIGN KEY (document_id) REFERENCES terms_documents(id) ON DELETE CASCADE
            );

            CREATE TABLE terms_chunks (
              id TEXT PRIMARY KEY,
              document_id TEXT NOT NULL,
              section_id TEXT NOT NULL,
              heading TEXT NOT NULL,
              text TEXT NOT NULL,
              tags_json TEXT NOT NULL,
              signals_json TEXT NOT NULL,
              FOREIGN KEY (document_id) REFERENCES terms_documents(id) ON DELETE CASCADE,
              FOREIGN KEY (document_id, section_id) REFERENCES terms_sections(document_id, id) ON DELETE CASCADE
            );

            CREATE TABLE terms_signals (
              chunk_id TEXT NOT NULL,
              signal TEXT NOT NULL,
              FOREIGN KEY (chunk_id) REFERENCES terms_chunks(id) ON DELETE CASCADE
            );

            CREATE TABLE terms_document_tags (
              document_id TEXT NOT NULL,
              tag TEXT NOT NULL,
              PRIMARY KEY (document_id, tag),
              FOREIGN KEY (document_id) REFERENCES terms_documents(id) ON DELETE CASCADE
            );

            CREATE VIRTUAL TABLE terms_chunks_fts USING fts5(
              id UNINDEXED,
              document_id UNINDEXED,
              section_id UNINDEXED,
              service_name,
              heading,
              text,
              tags,
              signals
            );

            CREATE INDEX idx_terms_documents_type_locale
              ON terms_documents(document_type, locale);
            CREATE INDEX idx_terms_documents_collection
              ON terms_documents(collection_method, collected_at);
            CREATE INDEX idx_terms_chunks_document
              ON terms_chunks(document_id, section_id);
            CREATE INDEX idx_terms_signals_signal
              ON terms_signals(signal);
            CREATE INDEX idx_terms_document_tags_tag
              ON terms_document_tags(tag);
            """
        )
        connection.executemany(
            """
            INSERT INTO terms_documents (
              id, service_name, provider_name, document_type, locale, source_url,
              collected_at, collection_method, retrieval_status, public_fixture_allowed,
              raw_personal_data, license_notes, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    document.id,
                    document.service_name,
                    document.provider_name,
                    document.document_type,
                    document.locale,
                    document.source_url,
                    document.collected_at,
                    document.collection_method,
                    document.retrieval_status,
                    int(document.public_fixture_allowed),
                    int(document.raw_personal_data),
                    document.license_notes,
                    json.dumps(document.tags, ensure_ascii=False),
                )
                for document in documents
            ],
        )
        connection.executemany(
            """
            INSERT INTO terms_sections (id, document_id, heading, text)
            VALUES (?, ?, ?, ?)
            """,
            [
                (section.id, document.id, section.heading, section.text)
                for document in documents
                for section in document.sections
            ],
        )
        connection.executemany(
            """
            INSERT INTO terms_chunks (id, document_id, section_id, heading, text, tags_json, signals_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk.id,
                    chunk.document_id,
                    chunk.section_id,
                    chunk.heading,
                    chunk.text,
                    json.dumps(chunk.tags, ensure_ascii=False),
                    json.dumps(chunk.signals, ensure_ascii=False),
                )
                for chunk in chunks
            ],
        )
        connection.executemany(
            "INSERT INTO terms_signals (chunk_id, signal) VALUES (?, ?)",
            [(chunk.id, signal) for chunk in chunks for signal in chunk.signals],
        )
        connection.executemany(
            "INSERT INTO terms_document_tags (document_id, tag) VALUES (?, ?)",
            [(document.id, tag) for document in documents for tag in sorted(set(document.tags))],
        )
        connection.executemany(
            """
            INSERT INTO terms_chunks_fts (id, document_id, section_id, service_name, heading, text, tags, signals)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk.id,
                    chunk.document_id,
                    chunk.section_id,
                    chunk.service_name,
                    chunk.heading,
                    chunk.text,
                    " ".join(chunk.tags),
                    " ".join(chunk.signals),
                )
                for chunk in chunks
            ],
        )
        connection.commit()
    finally:
        connection.close()

    return output_path


def _validate_terms_documents(
    documents: list[TermsDocument],
    *,
    require_public_fixture: bool = True,
    require_captured: bool = True,
) -> None:
    errors: list[str] = []
    ids = [document.id for document in documents]
    duplicate_ids = sorted(document_id for document_id, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate document id(s): {', '.join(duplicate_ids)}")

    for document in documents:
        if document.locale != "ko-KR":
            errors.append(f"{document.id} locale must be ko-KR")
        if require_public_fixture and not document.public_fixture_allowed:
            errors.append(f"{document.id} is not allowed in public fixtures")
        if document.raw_personal_data:
            errors.append(f"{document.id} contains raw personal data")
        if require_captured and document.retrieval_status != "captured":
            errors.append(f"{document.id} retrieval_status must be captured")
        section_ids = [section.id for section in document.sections]
        duplicate_section_ids = sorted(section_id for section_id, count in Counter(section_ids).items() if count > 1)
        if duplicate_section_ids:
            errors.append(f"{document.id} duplicate section id(s): {', '.join(duplicate_section_ids)}")
        for field_name, text in _iter_public_text(document):
            for label, pattern in FORBIDDEN_PATTERNS.items():
                if pattern.search(text):
                    errors.append(f"{document.id} {field_name} contains forbidden {label}-like text")

    if errors:
        raise ValueError("Invalid terms corpus: " + "; ".join(errors))


def _iter_public_text(document: TermsDocument):
    yield "license_notes", document.license_notes
    for section in document.sections:
        yield f"sections.{section.id}.heading", section.heading
        yield f"sections.{section.id}.text", section.text


def _summarize_terms_corpus(documents: list[TermsDocument], chunks: list[TermsChunk]) -> TermsCorpusSummary:
    return TermsCorpusSummary(
        document_count=len(documents),
        section_count=sum(len(document.sections) for document in documents),
        chunk_count=len(chunks),
        document_type_counts=dict(sorted(Counter(document.document_type for document in documents).items())),
        collection_method_counts=dict(sorted(Counter(document.collection_method for document in documents).items())),
        tag_counts=dict(sorted(Counter(tag for document in documents for tag in document.tags).items())),
    )


def _build_coverage_targets(summary: TermsCorpusSummary) -> list[TermsCoverageTarget]:
    actuals = {
        "documents_total": summary.document_count,
        "subscription_terms": summary.document_type_counts.get("subscription_terms", 0),
        "privacy_policy": summary.document_type_counts.get("privacy_policy", 0),
        "location_terms": summary.document_type_counts.get("location_terms", 0),
        "third_party": summary.tag_counts.get("third_party", 0),
        "marketing": summary.tag_counts.get("marketing", 0),
        "cancellation": summary.tag_counts.get("cancellation", 0),
    }
    return [
        TermsCoverageTarget(
            id=target_id,
            label=label,
            target=target,
            actual=actuals[target_id],
            passed=actuals[target_id] >= target,
        )
        for target_id, (label, target) in COVERAGE_TARGETS.items()
    ]


def _split_text(text: str) -> list[str]:
    normalized = " ".join(text.split())
    if len(normalized) <= MAX_CHUNK_CHARS:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + MAX_CHUNK_CHARS)
        chunks.append(normalized[start:end].strip())
        start = end
    return [chunk for chunk in chunks if chunk]


def _stable_chunk_id(document_id: str, section_id: str, index: int, text: str) -> str:
    digest = hashlib.sha256(f"{document_id}:{section_id}:{index}:{text}".encode("utf-8")).hexdigest()[:12]
    return f"tc_{digest}"


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _detect_local_signals(text: str) -> list[str]:
    return sorted({signal_id for label, (signal_id, _source) in LOCAL_SIGNAL_RULES.items() if label in text})


def _load_registered_terms_documents(output_path: Path) -> list[TermsDocument]:
    if not output_path.exists():
        return []
    connection = sqlite3.connect(output_path)
    connection.row_factory = sqlite3.Row
    try:
        has_versions_table = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'terms_document_versions'
            """
        ).fetchone()
        if not has_versions_table:
            return []
        rows = connection.execute(
            """
            SELECT document_json
            FROM terms_document_versions
            WHERE is_current = 1 AND review_status = 'approved_for_search'
            ORDER BY version_id
            """
        ).fetchall()
        return [TermsDocument.model_validate(json.loads(row["document_json"])) for row in rows]
    finally:
        connection.close()


def _search_sqlite_lexical(
    connection: sqlite3.Connection,
    query: str,
    query_terms: list[str],
    top_k: int,
) -> TermsSearchResponse:
    rows = connection.execute(
        """
        SELECT
          c.id, c.document_id, c.section_id, d.service_name, d.document_type,
          c.heading, c.text, c.tags_json, c.signals_json, 0 AS rank
        FROM terms_chunks c
        JOIN terms_documents d ON d.id = c.document_id
        """
    ).fetchall()
    results: list[TermsSearchResult] = []
    for row in rows:
        haystack = " ".join(
            [
                row["service_name"],
                row["document_type"],
                row["heading"],
                row["text"],
                row["tags_json"],
                row["signals_json"],
            ]
        )
        matched = sorted(term for term in query_terms if term in haystack.lower())
        if matched:
            results.append(_row_to_search_result(row, matched))
    results.sort(key=lambda result: (-result.score, result.chunk.document_id, result.chunk.section_id))
    return TermsSearchResponse(query=query, total=len(results), results=results[: max(1, min(top_k, 25))])


def _row_to_search_result(row: sqlite3.Row, matched_terms: list[str]) -> TermsSearchResult:
    tags = json.loads(row["tags_json"])
    signals = json.loads(row["signals_json"])
    chunk = TermsChunk(
        id=row["id"],
        document_id=row["document_id"],
        section_id=row["section_id"],
        service_name=row["service_name"],
        document_type=row["document_type"],
        heading=row["heading"],
        text=row["text"],
        tags=tags,
        signals=signals,
    )
    score = 100 + len(matched_terms) * 10 + len(signals) * 2
    return TermsSearchResult(chunk=chunk, score=score, matched_terms=matched_terms)
