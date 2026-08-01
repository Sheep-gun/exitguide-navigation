import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from app.resource_paths import get_resource_root
from app.schemas import (
    CancellationFlowEntry,
    CollectionCoverageTarget,
    CollectionRegistryCatalog,
    CollectionRegistryMetadata,
    CollectionRegistryQualityResponse,
    CollectionRegistrySummary,
    DocumentSourceEntry,
    FlowStepEntry,
    ReviewTaskEntry,
    ServiceRegistryEntry,
)


ROOT = get_resource_root()
COLLECTION_REGISTRY_PATH = ROOT / "fixtures" / "collection-registry" / "registry.json"
DEFAULT_COLLECTION_DB_PATH = ROOT / ".artifacts" / "collection-registry.sqlite"
FORBIDDEN_PUBLIC_PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "phone": re.compile(r"\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b"),
    "url_query": re.compile(r"https?://[^\s?#]+[?][^\s]+"),
    "private_key": re.compile(r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "token": re.compile(r"\b(access_token|refresh_token|auth_token|sessionid|cookie)\b", re.IGNORECASE),
}
COVERAGE_TARGETS = {
    "services_total": ("Services", 3),
    "document_sources_total": ("Document sources", 6),
    "terms_sources": ("Terms document sources", 1),
    "privacy_sources": ("Privacy document sources", 1),
    "help_sources": ("Help document sources", 1),
    "review_tasks": ("Review tasks", 2),
    "flows": ("Manual cancellation or consent flows", 2),
}


def load_collection_registry() -> CollectionRegistryCatalog:
    payload = json.loads(COLLECTION_REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    metadata = CollectionRegistryMetadata.model_validate(payload)
    services = [ServiceRegistryEntry.model_validate(item) for item in payload["services"]]
    document_sources = [DocumentSourceEntry.model_validate(item) for item in payload["document_sources"]]
    cancellation_flows = [CancellationFlowEntry.model_validate(item) for item in payload["cancellation_flows"]]
    flow_steps = [FlowStepEntry.model_validate(item) for item in payload["flow_steps"]]
    review_tasks = [ReviewTaskEntry.model_validate(item) for item in payload["review_tasks"]]
    _validate_collection_registry(services, document_sources, cancellation_flows, flow_steps, review_tasks)
    return CollectionRegistryCatalog(
        description=payload["description"],
        metadata=metadata,
        summary=_summarize_collection_registry(services, document_sources, cancellation_flows, flow_steps, review_tasks),
        services=services,
        document_sources=document_sources,
        cancellation_flows=cancellation_flows,
        flow_steps=flow_steps,
        review_tasks=review_tasks,
    )


def build_collection_registry_quality() -> CollectionRegistryQualityResponse:
    catalog = load_collection_registry()
    targets = _build_coverage_targets(catalog.summary)
    warnings = [
        f"{target.label}: {target.actual}/{target.target}"
        for target in targets
        if not target.passed
    ]
    return CollectionRegistryQualityResponse(
        status="pass" if not warnings else "warn",
        metadata=catalog.metadata,
        summary=catalog.summary,
        coverage_targets=targets,
        warnings=warnings,
    )


def build_collection_registry_sqlite(output_path: Path = DEFAULT_COLLECTION_DB_PATH) -> Path:
    catalog = load_collection_registry()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(output_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
            DROP TABLE IF EXISTS review_tasks;
            DROP TABLE IF EXISTS flow_steps;
            DROP TABLE IF EXISTS cancellation_flows;
            DROP TABLE IF EXISTS document_sources;
            DROP TABLE IF EXISTS service_platforms;
            DROP TABLE IF EXISTS service_aliases;
            DROP TABLE IF EXISTS services;

            CREATE TABLE services (
              service_id TEXT PRIMARY KEY,
              service_name TEXT NOT NULL,
              country TEXT NOT NULL,
              language TEXT NOT NULL,
              category TEXT NOT NULL,
              official_website_url TEXT NOT NULL,
              app_store_url TEXT NOT NULL,
              play_store_url TEXT NOT NULL,
              developer_name TEXT NOT NULL,
              priority_score INTEGER NOT NULL,
              collection_status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE service_aliases (
              service_id TEXT NOT NULL,
              alias TEXT NOT NULL,
              PRIMARY KEY (service_id, alias),
              FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE CASCADE
            );

            CREATE TABLE service_platforms (
              service_id TEXT NOT NULL,
              platform TEXT NOT NULL,
              PRIMARY KEY (service_id, platform),
              FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE CASCADE
            );

            CREATE TABLE document_sources (
              document_id TEXT PRIMARY KEY,
              service_id TEXT NOT NULL,
              document_type TEXT NOT NULL,
              source_url TEXT NOT NULL,
              source_domain TEXT NOT NULL,
              language TEXT NOT NULL,
              country_or_region TEXT NOT NULL,
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              last_fetched_at TEXT NOT NULL,
              http_status INTEGER NOT NULL,
              content_hash TEXT NOT NULL,
              is_active INTEGER NOT NULL,
              robots_allowed INTEGER NOT NULL,
              manual_review_required INTEGER NOT NULL,
              FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE CASCADE
            );

            CREATE TABLE cancellation_flows (
              flow_id TEXT PRIMARY KEY,
              service_id TEXT NOT NULL,
              user_goal TEXT NOT NULL,
              platform TEXT NOT NULL,
              payment_channel TEXT NOT NULL,
              country_or_region TEXT NOT NULL,
              app_version TEXT NOT NULL,
              last_verified_at TEXT NOT NULL,
              verification_method TEXT NOT NULL,
              confidence REAL NOT NULL,
              status TEXT NOT NULL,
              requires_login INTEGER NOT NULL,
              requires_customer_support INTEGER NOT NULL,
              estimated_steps_count INTEGER NOT NULL,
              notes TEXT NOT NULL,
              FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE CASCADE
            );

            CREATE TABLE flow_steps (
              step_id TEXT PRIMARY KEY,
              flow_id TEXT NOT NULL,
              step_order INTEGER NOT NULL,
              screen_name TEXT NOT NULL,
              action_type TEXT NOT NULL,
              instruction_text TEXT NOT NULL,
              button_or_link_text TEXT NOT NULL,
              expected_result TEXT NOT NULL,
              screenshot_path TEXT NOT NULL,
              ocr_text TEXT NOT NULL,
              ux_friction_label TEXT NOT NULL,
              risk_note TEXT NOT NULL,
              FOREIGN KEY (flow_id) REFERENCES cancellation_flows(flow_id) ON DELETE CASCADE
            );

            CREATE TABLE review_tasks (
              review_task_id TEXT PRIMARY KEY,
              entity_type TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              service_id TEXT NOT NULL,
              priority INTEGER NOT NULL,
              reason TEXT NOT NULL,
              status TEXT NOT NULL,
              reviewer_note TEXT NOT NULL,
              created_at TEXT NOT NULL,
              completed_at TEXT NOT NULL,
              FOREIGN KEY (service_id) REFERENCES services(service_id) ON DELETE CASCADE
            );

            CREATE INDEX idx_document_sources_service_type
              ON document_sources(service_id, document_type);
            CREATE INDEX idx_review_tasks_status_priority
              ON review_tasks(status, priority DESC);
            CREATE INDEX idx_cancellation_flows_service_goal
              ON cancellation_flows(service_id, user_goal);
            """
        )
        connection.executemany(
            """
            INSERT INTO services (
              service_id, service_name, country, language, category,
              official_website_url, app_store_url, play_store_url, developer_name,
              priority_score, collection_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    service.service_id,
                    service.service_name,
                    service.country,
                    service.language,
                    service.category,
                    service.official_website_url,
                    service.app_store_url,
                    service.play_store_url,
                    service.developer_name,
                    service.priority_score,
                    service.collection_status,
                    service.created_at,
                    service.updated_at,
                )
                for service in catalog.services
            ],
        )
        connection.executemany(
            "INSERT INTO service_aliases (service_id, alias) VALUES (?, ?)",
            [(service.service_id, alias) for service in catalog.services for alias in service.service_aliases],
        )
        connection.executemany(
            "INSERT INTO service_platforms (service_id, platform) VALUES (?, ?)",
            [(service.service_id, platform) for service in catalog.services for platform in service.platforms],
        )
        connection.executemany(
            """
            INSERT INTO document_sources (
              document_id, service_id, document_type, source_url, source_domain,
              language, country_or_region, first_seen_at, last_seen_at, last_fetched_at,
              http_status, content_hash, is_active, robots_allowed, manual_review_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    source.document_id,
                    source.service_id,
                    source.document_type,
                    source.source_url,
                    source.source_domain,
                    source.language,
                    source.country_or_region,
                    source.first_seen_at,
                    source.last_seen_at,
                    source.last_fetched_at,
                    source.http_status,
                    source.content_hash,
                    int(source.is_active),
                    int(source.robots_allowed),
                    int(source.manual_review_required),
                )
                for source in catalog.document_sources
            ],
        )
        connection.executemany(
            """
            INSERT INTO cancellation_flows (
              flow_id, service_id, user_goal, platform, payment_channel, country_or_region,
              app_version, last_verified_at, verification_method, confidence, status,
              requires_login, requires_customer_support, estimated_steps_count, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    flow.flow_id,
                    flow.service_id,
                    flow.user_goal,
                    flow.platform,
                    flow.payment_channel,
                    flow.country_or_region,
                    flow.app_version,
                    flow.last_verified_at,
                    flow.verification_method,
                    flow.confidence,
                    flow.status,
                    int(flow.requires_login),
                    int(flow.requires_customer_support),
                    flow.estimated_steps_count,
                    flow.notes,
                )
                for flow in catalog.cancellation_flows
            ],
        )
        connection.executemany(
            """
            INSERT INTO flow_steps (
              step_id, flow_id, step_order, screen_name, action_type, instruction_text,
              button_or_link_text, expected_result, screenshot_path, ocr_text,
              ux_friction_label, risk_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    step.step_id,
                    step.flow_id,
                    step.step_order,
                    step.screen_name,
                    step.action_type,
                    step.instruction_text,
                    step.button_or_link_text,
                    step.expected_result,
                    step.screenshot_path,
                    step.ocr_text,
                    step.ux_friction_label,
                    step.risk_note,
                )
                for step in catalog.flow_steps
            ],
        )
        connection.executemany(
            """
            INSERT INTO review_tasks (
              review_task_id, entity_type, entity_id, service_id, priority, reason,
              status, reviewer_note, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    task.review_task_id,
                    task.entity_type,
                    task.entity_id,
                    task.service_id,
                    task.priority,
                    task.reason,
                    task.status,
                    task.reviewer_note,
                    task.created_at,
                    task.completed_at,
                )
                for task in catalog.review_tasks
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return output_path


def _validate_collection_registry(
    services: list[ServiceRegistryEntry],
    document_sources: list[DocumentSourceEntry],
    cancellation_flows: list[CancellationFlowEntry],
    flow_steps: list[FlowStepEntry],
    review_tasks: list[ReviewTaskEntry],
) -> None:
    errors: list[str] = []
    service_ids = {service.service_id for service in services}
    flow_ids = {flow.flow_id for flow in cancellation_flows}
    document_ids = {source.document_id for source in document_sources}

    _append_duplicate_errors("service", [service.service_id for service in services], errors)
    _append_duplicate_errors("document source", [source.document_id for source in document_sources], errors)
    _append_duplicate_errors("flow", [flow.flow_id for flow in cancellation_flows], errors)
    _append_duplicate_errors("flow step", [step.step_id for step in flow_steps], errors)
    _append_duplicate_errors("review task", [task.review_task_id for task in review_tasks], errors)

    for service in services:
        _validate_url(service.official_website_url, f"{service.service_id}.official_website_url", errors)
        for url_field in (service.app_store_url, service.play_store_url):
            if url_field:
                _validate_url(url_field, f"{service.service_id}.store_url", errors)
        if service.language != "ko" or service.country != "KR":
            errors.append(f"{service.service_id} must be ko/KR in this seed registry")
        _check_public_text(service.model_dump_json(), service.service_id, errors)

    for source in document_sources:
        if source.service_id not in service_ids:
            errors.append(f"{source.document_id} references unknown service {source.service_id}")
        _validate_url(source.source_url, f"{source.document_id}.source_url", errors)
        parsed = urlparse(source.source_url)
        if parsed.netloc.lower() != source.source_domain.lower():
            errors.append(f"{source.document_id} source_domain does not match source_url")
        if source.language != "ko" or source.country_or_region != "KR":
            errors.append(f"{source.document_id} must be ko/KR in this seed registry")
        _check_public_text(source.model_dump_json(), source.document_id, errors)

    for flow in cancellation_flows:
        if flow.service_id not in service_ids:
            errors.append(f"{flow.flow_id} references unknown service {flow.service_id}")
        if flow.estimated_steps_count != len([step for step in flow_steps if step.flow_id == flow.flow_id]):
            errors.append(f"{flow.flow_id} estimated_steps_count does not match flow_steps")
        _check_public_text(flow.model_dump_json(), flow.flow_id, errors)

    for step in flow_steps:
        if step.flow_id not in flow_ids:
            errors.append(f"{step.step_id} references unknown flow {step.flow_id}")
        _check_public_text(step.model_dump_json(), step.step_id, errors)

    for task in review_tasks:
        if task.service_id not in service_ids:
            errors.append(f"{task.review_task_id} references unknown service {task.service_id}")
        if task.entity_type == "document_source" and task.entity_id not in document_ids:
            errors.append(f"{task.review_task_id} references unknown document source {task.entity_id}")
        if task.entity_type == "flow" and task.entity_id not in flow_ids:
            errors.append(f"{task.review_task_id} references unknown flow {task.entity_id}")
        _check_public_text(task.model_dump_json(), task.review_task_id, errors)

    if errors:
        raise ValueError("Invalid collection registry: " + "; ".join(errors))


def _summarize_collection_registry(
    services: list[ServiceRegistryEntry],
    document_sources: list[DocumentSourceEntry],
    cancellation_flows: list[CancellationFlowEntry],
    flow_steps: list[FlowStepEntry],
    review_tasks: list[ReviewTaskEntry],
) -> CollectionRegistrySummary:
    return CollectionRegistrySummary(
        service_count=len(services),
        document_source_count=len(document_sources),
        review_task_count=len(review_tasks),
        flow_count=len(cancellation_flows),
        flow_step_count=len(flow_steps),
        platform_counts=dict(sorted(Counter(platform for service in services for platform in service.platforms).items())),
        document_type_counts=dict(sorted(Counter(source.document_type for source in document_sources).items())),
        review_status_counts=dict(sorted(Counter(task.status for task in review_tasks).items())),
        collection_status_counts=dict(sorted(Counter(service.collection_status for service in services).items())),
    )


def _build_coverage_targets(summary: CollectionRegistrySummary) -> list[CollectionCoverageTarget]:
    actuals = {
        "services_total": summary.service_count,
        "document_sources_total": summary.document_source_count,
        "terms_sources": summary.document_type_counts.get("terms", 0),
        "privacy_sources": summary.document_type_counts.get("privacy", 0),
        "help_sources": summary.document_type_counts.get("help", 0),
        "review_tasks": summary.review_task_count,
        "flows": summary.flow_count,
    }
    return [
        CollectionCoverageTarget(
            id=target_id,
            label=label,
            target=target,
            actual=actuals[target_id],
            passed=actuals[target_id] >= target,
        )
        for target_id, (label, target) in COVERAGE_TARGETS.items()
    ]


def _append_duplicate_errors(label: str, ids: list[str], errors: list[str]) -> None:
    duplicates = sorted(item_id for item_id, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate {label} id(s): {', '.join(duplicates)}")


def _validate_url(value: str, field_name: str, errors: list[str]) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append(f"{field_name} must be an http(s) URL")
    if parsed.query or parsed.fragment:
        errors.append(f"{field_name} must not contain query or fragment data")


def _check_public_text(text: str, label: str, errors: list[str]) -> None:
    for pattern_label, pattern in FORBIDDEN_PUBLIC_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"{label} contains forbidden {pattern_label}-like text")
