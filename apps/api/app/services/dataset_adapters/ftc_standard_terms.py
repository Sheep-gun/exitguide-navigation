from __future__ import annotations

import io
import json
import re
import struct
import unicodedata
import zlib
from collections import Counter
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree
from zipfile import ZipFile

import olefile

from app.services.dataset_adapters.common import (
    STAGING_SCHEMA_VERSION,
    NormalizedTermsRecord,
    input_file_descriptor,
    normalize_text,
    sha256_file,
    sha256_text,
    stable_record_id,
    write_jsonl,
    write_manifest,
)


SOURCE_ID = "ftc_standard_terms"
SOURCE_URL = "https://www.ftc.go.kr/www/selectBbsNttList.do?bordCd=201&key=202"
OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
ZIP_MAGIC = b"PK\x03\x04"
HWP_PARA_TEXT_TAG = 67


def convert_ftc_standard_terms(source_dir: Path, output_root: Path) -> dict[str, object]:
    attachments_dir = source_dir / "attachments"
    attachments = sorted(attachments_dir.glob("attachment-*.bin"))
    if len(attachments) != 93:
        raise ValueError(f"Expected 93 FTC attachments, found {len(attachments)}")
    crawl_index_path = source_dir / "crawl-index.json"
    crawl_index = json.loads(crawl_index_path.read_text(encoding="utf-8"))
    download_links = list(crawl_index.get("download_links", []))
    if len(download_links) != len(attachments):
        raise ValueError("FTC attachment count does not match crawl-index download links")

    output_dir = output_root / SOURCE_ID
    output_path = output_dir / "documents.jsonl"
    parse_modes: Counter[str] = Counter()
    content_hashes: set[str] = set()

    def records() -> Iterator[NormalizedTermsRecord]:
        for index, path in enumerate(attachments):
            payload = path.read_bytes()
            if payload.startswith(OLE_MAGIC):
                text = extract_hwp_text(payload)
                parse_mode = "hwp_ole_bodytext"
            elif payload.startswith(ZIP_MAGIC):
                text = extract_hwpx_text(payload)
                parse_mode = "hwpx_xml"
            else:
                raise ValueError(f"Unknown FTC attachment format: {path.name}")
            text = normalize_text(text)
            if len(text) < 100:
                raise ValueError(f"FTC attachment yielded too little text: {path.name} ({len(text)} chars)")
            source_url = download_links[index]
            record = NormalizedTermsRecord(
                record_id=stable_record_id(SOURCE_ID, source_url),
                source_id=SOURCE_ID,
                split="all",
                locale="ko-KR",
                service_name="Korea Fair Trade Commission",
                document_type="standard_terms",
                category="standard_terms",
                version_at="",
                text=text,
                content_sha256=sha256_text(text),
                review_status="needs_review",
                license_notes="Public attachment reuse and redistribution conditions require review.",
                provenance={
                    "source_url": source_url,
                    "source_file": path.name,
                    "source_parse_mode": parse_mode,
                },
            )
            parse_modes[parse_mode] += 1
            content_hashes.add(record.content_sha256)
            yield record

    document_count, output_bytes = write_jsonl(records(), output_path)
    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "conversion_scope": "all_downloaded_standard_terms_attachments",
        "decision_method": "file_signature_probe_and_rule_based_format_extraction",
        "document_count": document_count,
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "parse_mode_counts": dict(sorted(parse_modes.items())),
        "input_index": input_file_descriptor(crawl_index_path),
        "input_files": [input_file_descriptor(path) for path in attachments],
        "output": {"name": output_path.name, "bytes": output_bytes, "sha256": sha256_file(output_path)},
        "review_status": "needs_review",
        "license_notes": "Public attachment reuse and redistribution conditions require review.",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def extract_hwp_text(payload: bytes) -> str:
    with olefile.OleFileIO(io.BytesIO(payload)) as document:
        header = document.openstream("FileHeader").read()
        flags = struct.unpack_from("<I", header, 36)[0]
        compressed = bool(flags & 1)
        section_names = sorted(
            ("/".join(path) for path in document.listdir() if path[:1] == ["BodyText"] and path[-1].startswith("Section")),
            key=_section_number,
        )
        paragraphs: list[str] = []
        for section_name in section_names:
            section = document.openstream(section_name).read()
            if compressed:
                section = zlib.decompress(section, -15)
            paragraphs.extend(_extract_hwp_records(section))
    return normalize_text("\n".join(paragraphs))


def extract_hwpx_text(payload: bytes) -> str:
    paragraphs: list[str] = []
    with ZipFile(io.BytesIO(payload)) as archive:
        section_names = sorted(
            name for name in archive.namelist() if name.startswith("Contents/section") and name.endswith(".xml")
        )
        for section_name in section_names:
            root = ElementTree.fromstring(archive.read(section_name))
            for paragraph in root.iter():
                if _local_name(paragraph.tag) != "p":
                    continue
                values = [node.text or "" for node in paragraph.iter() if _local_name(node.tag) == "t"]
                text = normalize_text("".join(values))
                if text:
                    paragraphs.append(text)
    return _clean_hwp_text("\n".join(paragraphs))


def _extract_hwp_records(section: bytes) -> list[str]:
    paragraphs: list[str] = []
    offset = 0
    while offset + 4 <= len(section):
        record_header = struct.unpack_from("<I", section, offset)[0]
        offset += 4
        tag_id = record_header & 0x3FF
        size = (record_header >> 20) & 0xFFF
        if size == 0xFFF:
            if offset + 4 > len(section):
                break
            size = struct.unpack_from("<I", section, offset)[0]
            offset += 4
        if offset + size > len(section):
            break
        record = section[offset : offset + size]
        offset += size
        if tag_id != HWP_PARA_TEXT_TAG or not record:
            continue
        text = _decode_hwp_paragraph(record)
        if text:
            paragraphs.append(text)
    return paragraphs


def _decode_hwp_paragraph(payload: bytes) -> str:
    """Decode PARA_TEXT while skipping HWP's fixed-width inline controls."""
    code_units = struct.unpack(f"<{len(payload) // 2}H", payload[: len(payload) // 2 * 2])
    characters: list[str] = []
    index = 0
    while index < len(code_units):
        code = code_units[index]
        if code in {10, 13}:
            characters.append("\n")
            index += 1
        elif code == 9:
            characters.append("\t")
            index += 8
        elif 0 < code < 32:
            index += 8
        else:
            characters.append(chr(code))
            index += 1
    return _clean_hwp_text("".join(characters))


def _clean_hwp_text(value: str) -> str:
    cleaned = "".join(
        character
        for character in value
        if character in "\n\t" or not unicodedata.category(character).startswith("C")
    )
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return normalize_text(cleaned)


def _section_number(value: str) -> int:
    match = re.search(r"Section(\d+)$", value)
    return int(match.group(1)) if match else 0


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
