from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree
from zipfile import ZipFile

from app.services.dataset_adapters.common import (
    STAGING_SCHEMA_VERSION,
    NormalizedTermsRecord,
    normalize_text,
    sha256_file,
    sha256_text,
    stable_record_id,
    write_jsonl,
    write_manifest,
)


SOURCE_ID = "aihub_legal_regulation_terms"
SOURCE_URL = "https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=580"
ARCHIVE_NAMES = {
    "training": ("TS_2.약관.zip", "TL_2.약관.zip"),
    "validation": ("VS_2.약관.zip", "VL_2.약관.zip"),
}
LABEL_BY_DIRECTORY = {
    "01.유리": "advantageous",
    "02.불리": "disadvantageous",
}
EXPECTED_CODE_BY_LABEL = {
    "advantageous": "1",
    "disadvantageous": "2",
}
CATEGORY_PATTERN = re.compile(r"^(?P<code>\d+)\.\s*(?P<name>.+)$")
CATEGORY_NAME_ALIASES = {
    "국내외여행": "국내외 여행",
    "입소,입주,입점계약": "입소, 입주, 입점계약",
    "자동차리스및렌트": "자동차 리스 및 렌트",
    "통신,방송서비스": "통신, 방송서비스",
    "통신방송서비스": "통신, 방송서비스",
}


def convert_aihub_terms(source_root: Path, output_root: Path) -> dict[str, object]:
    archives = _discover_archives(source_root)
    output_dir = output_root / SOURCE_ID
    output_path = output_dir / "documents.jsonl"

    label_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    parse_mode_counts: Counter[str] = Counter()
    content_hashes: set[str] = set()
    record_ids: set[str] = set()

    def records() -> Iterator[NormalizedTermsRecord]:
        for split, (source_archive, label_archive) in archives.items():
            for record in _iter_split_records(split, source_archive, label_archive):
                if record.record_id in record_ids:
                    raise ValueError(f"Duplicate normalized record ID: {record.record_id}")
                record_ids.add(record.record_id)
                label = str(record.annotations[0]["label"])
                label_counts[label] += 1
                category_counts[record.category] += 1
                split_counts[split] += 1
                parse_mode_counts[record.provenance["source_parse_mode"]] += 1
                content_hashes.add(record.content_sha256)
                yield record

    document_count, output_bytes = write_jsonl(records(), output_path)
    input_archives = [path for pair in archives.values() for path in pair]
    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "conversion_scope": "all_training_and_validation_terms",
        "document_count": document_count,
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "source_parse_mode_counts": dict(sorted(parse_mode_counts.items())),
        "repaired_source_count": document_count - parse_mode_counts.get("xml", 0),
        "split_counts": dict(sorted(split_counts.items())),
        "label_counts": dict(sorted(label_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "input_archives": [
            {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in input_archives
        ],
        "output": {
            "name": output_path.name,
            "bytes": output_bytes,
            "sha256": sha256_file(output_path),
        },
        "review_status": "needs_review",
        "license_notes": "Use and redistribution are subject to the AI Hub terms accepted by the downloader.",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def _discover_archives(source_root: Path) -> dict[str, tuple[Path, Path]]:
    if not source_root.is_dir():
        raise FileNotFoundError(f"AI Hub source directory was not found: {source_root}")

    discovered: dict[str, tuple[Path, Path]] = {}
    for split, names in ARCHIVE_NAMES.items():
        paths: list[Path] = []
        for name in names:
            matches = list(source_root.rglob(name))
            if len(matches) != 1:
                raise ValueError(f"Expected one {name} below {source_root}, found {len(matches)}")
            paths.append(matches[0])
        discovered[split] = (paths[0], paths[1])
    return discovered


def _iter_split_records(split: str, source_archive: Path, label_archive: Path) -> Iterator[NormalizedTermsRecord]:
    with ZipFile(source_archive) as source_zip, ZipFile(label_archive) as label_zip:
        sources = _entry_map(source_zip, ".xml")
        labels = _entry_map(label_zip, ".json")
        if sources.keys() != labels.keys():
            source_only = sorted(sources.keys() - labels.keys())[:5]
            label_only = sorted(labels.keys() - sources.keys())[:5]
            raise ValueError(f"AI Hub source/label mismatch for {split}: source_only={source_only}, label_only={label_only}")

        for stem in sorted(sources):
            source_entry = sources[stem]
            label_entry = labels[stem]
            annotation = _parse_label_json(label_zip.read(label_entry), label_entry)
            category, original_name, text, parse_mode, raw_category = _parse_source_xml(
                source_zip.read(source_entry),
                source_entry,
            )
            content_hash = sha256_text(text)
            locator = f"{split}:{source_entry}"
            yield NormalizedTermsRecord(
                record_id=stable_record_id(SOURCE_ID, locator),
                source_id=SOURCE_ID,
                split=split,
                locale="ko-KR",
                service_name="",
                document_type=_document_type_from_category(category),
                category=category,
                version_at="",
                text=text,
                content_sha256=content_hash,
                review_status="needs_review",
                license_notes="Use and redistribution are subject to the AI Hub terms accepted by the downloader.",
                provenance={
                    "source_url": SOURCE_URL,
                    "source_archive": source_archive.name,
                    "source_entry": source_entry,
                    "label_archive": label_archive.name,
                    "label_entry": label_entry,
                    "original_name": original_name,
                    "source_parse_mode": parse_mode,
                    "raw_category": raw_category,
                },
                annotations=[annotation],
            )


def _entry_map(archive: ZipFile, suffix: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for item in archive.infolist():
        if item.is_dir() or Path(item.filename).suffix.lower() != suffix:
            continue
        stem = _normalized_stem(item.filename)
        if stem in entries:
            raise ValueError(f"Duplicate normalized stem in {archive.filename}: {stem}")
        entries[stem] = item.filename
    return entries


def _normalized_stem(entry_name: str) -> str:
    return Path(entry_name).stem.removesuffix("_가공")


def _parse_source_xml(payload: bytes, entry_name: str) -> tuple[str, str, str, str, str]:
    decoded = payload.decode("utf-8-sig")
    root_index = decoded.find("<root")
    if root_index >= 0:
        try:
            declaration = decoded[:root_index].strip()
            root = ElementTree.fromstring(decoded[root_index:])
            raw_category = normalize_text(root.findtext("./file/category") or "")
            original_name = normalize_text(root.findtext("./file/name") or "")
            text = normalize_text(_strip_cdata_markers(root.findtext("./file/cn") or ""))
            parse_mode = (
                "xml"
                if not declaration or declaration == '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                else "repaired_xml_declaration"
            )
            if raw_category and text:
                category = _category_from_entry_name(entry_name)
                return category, original_name, text, parse_mode, raw_category
        except ElementTree.ParseError:
            pass

    raw_category = _extract_pseudo_xml_field(decoded, "category")
    original_name = _extract_pseudo_xml_field(decoded, "name")
    text = _extract_pseudo_xml_field(decoded, "cn")
    parse_mode = "pseudo_xml"
    if not text:
        text = normalize_text(decoded)
        parse_mode = "plain_text"
    fallback_name = _normalized_stem(entry_name)
    category = _category_from_entry_name(entry_name)
    original_name = original_name or f"{fallback_name}.pdf"
    if not category or not text:
        raise ValueError("AI Hub XML is missing category or document text")
    return category, original_name, text, parse_mode, raw_category


def _extract_pseudo_xml_field(payload: str, field_name: str) -> str:
    lines = payload.splitlines()
    start_index = None
    end_index = None
    for index, line in enumerate(lines):
        token = _pseudo_tag_token(line)
        if start_index is None and _is_pseudo_open_tag(token, field_name):
            start_index = index + 1
            continue
        if start_index is not None and (
            _is_pseudo_close_tag(token, field_name) or _is_pseudo_open_tag(token, field_name)
        ):
            end_index = index
            break
    if start_index is None:
        return ""
    if end_index is None:
        end_index = _find_structural_boundary(lines, start_index, field_name)
    return normalize_text(_strip_cdata_markers("\n".join(lines[start_index:end_index])))


def _find_structural_boundary(lines: list[str], start_index: int, field_name: str) -> int:
    structural_fields = {"root", "file", "category", "name", "cn"}
    for index in range(start_index, len(lines)):
        token = _pseudo_tag_token(lines[index]).lstrip("/")
        if token in structural_fields and token != field_name:
            return index
    return len(lines)


def _pseudo_tag_token(line: str) -> str:
    return re.sub(r"[\s<>()\[\]!]", "", line).lower()


def _is_pseudo_open_tag(token: str, field_name: str) -> bool:
    if token.startswith("/"):
        return False
    if field_name == "category":
        return token in {"category", "categㅇry"}
    return token == field_name


def _is_pseudo_close_tag(token: str, field_name: str) -> bool:
    if field_name == "category":
        return token in {"/category", "/categㅇry"}
    return token == f"/{field_name}"


def _strip_cdata_markers(value: str) -> str:
    lines = value.splitlines()
    while lines and (not lines[0].strip() or _is_cdata_boundary(lines[0])):
        lines.pop(0)
    while lines and (not lines[-1].strip() or _is_cdata_boundary(lines[-1])):
        lines.pop()
    return "\n".join(lines)


def _is_cdata_boundary(line: str) -> bool:
    token = _pseudo_tag_token(line).lstrip("/")
    if token == "cdata":
        return True
    return bool(line.strip()) and not re.search(r"[0-9A-Za-z\u3131-\u318E\uAC00-\uD7A3]", line)


def _category_from_entry_name(entry_name: str) -> str:
    stem = _normalized_stem(entry_name)
    category = stem.split("_", 1)[1] if "_" in stem else stem
    category = re.sub(r"(?:_PDF|_OCR)\s*$", "", category, flags=re.IGNORECASE).strip()
    return CATEGORY_NAME_ALIASES.get(category, category)


def _parse_label_json(payload: bytes, entry_name: str) -> dict[str, object]:
    data = json.loads(payload.decode("utf-8-sig"))
    directory_label = Path(entry_name).parts[-2]
    label = LABEL_BY_DIRECTORY.get(directory_label)
    if label is None:
        raise ValueError(f"Unknown AI Hub label directory: {directory_label}")
    raw_code = str(data.get("dvAntageous"))
    if raw_code != EXPECTED_CODE_BY_LABEL[label]:
        raise ValueError(f"AI Hub label code mismatch in {entry_name}: {raw_code}")
    return {
        "label": label,
        "raw_label_directory": directory_label,
        "dv_advantageous_code": raw_code,
        "ftc_conclusion_code": None if data.get("ftcCnclsns") is None else str(data.get("ftcCnclsns")),
        "clause_field_code": str(data.get("clauseField") or ""),
        "clause_articles": [normalize_text(str(value)) for value in data.get("clauseArticle", []) if normalize_text(str(value))],
        "comparison_provisions": [normalize_text(str(value)) for value in data.get("comProvision", []) if normalize_text(str(value))],
    }


def _document_type_from_category(category: str) -> str:
    match = CATEGORY_PATTERN.match(category)
    name = match.group("name") if match else category
    return "privacy_policy" if "개인정보" in name else "terms_of_service"
