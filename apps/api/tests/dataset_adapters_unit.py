import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from app.services.dataset_adapters.aihub import _parse_source_xml, convert_aihub_terms
from app.services.dataset_adapters.open_terms_archive import convert_open_terms_archive
from app.services.dataset_adapters.validation import validate_normalized_jsonl


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        output_root = root / "output"
        aihub_root = root / "aihub"
        _write_aihub_fixture(aihub_root)
        aihub_manifest = convert_aihub_terms(aihub_root, output_root)
        assert aihub_manifest["document_count"] == 2
        assert aihub_manifest["label_counts"] == {"advantageous": 1, "disadvantageous": 1}
        assert aihub_manifest["repaired_source_count"] == 1
        assert aihub_manifest["source_parse_mode_counts"] == {"repaired_xml_declaration": 1, "xml": 1}
        aihub_records = _read_jsonl(output_root / "aihub_legal_regulation_terms" / "documents.jsonl")
        assert aihub_records[0]["locale"] == "ko-KR"
        assert aihub_records[0]["category"] == "온라인서비스"
        assert aihub_records[0]["provenance"]["raw_category"] == "39. 온라인서비스"
        assert aihub_records[0]["annotations"][0]["label"] == "advantageous"
        assert aihub_records[1]["annotations"][0]["label"] == "disadvantageous"
        aihub_validation = validate_normalized_jsonl(
            output_root / "aihub_legal_regulation_terms" / "documents.jsonl",
            output_root / "aihub_legal_regulation_terms" / "manifest.json",
            "aihub_legal_regulation_terms",
        )
        assert aihub_validation["unique_record_count"] == 2
        _check_malformed_aihub_sources()

        ota_zip = root / "ota.zip"
        _write_ota_fixture(ota_zip)
        ota_manifest = convert_open_terms_archive(ota_zip, output_root)
        assert ota_manifest["all_version_count"] == 3
        assert ota_manifest["document_count"] == 2
        assert ota_manifest["service_count"] == 1
        ota_records = _read_jsonl(output_root / "open_terms_archive_contrib" / "documents-latest.jsonl")
        assert {record["text"] for record in ota_records} == {"latest terms", "privacy text"}
        assert {record["document_type"] for record in ota_records} == {"terms_of_service", "privacy_policy"}

    print("dataset adapter checks ok")


def _write_aihub_fixture(root: Path) -> None:
    samples = {
        "training": ("TS_2.약관.zip", "TL_2.약관.zip", "01.유리", "1", "001_온라인서비스"),
        "validation": ("VS_2.약관.zip", "VL_2.약관.zip", "02.불리", "2", "002_개인정보취급방침"),
    }
    for split, (source_name, label_name, label_dir, code, stem) in samples.items():
        source_path = root / split / source_name
        label_path = root / split / label_name
        source_path.parent.mkdir(parents=True, exist_ok=True)
        category = "39. 온라인서비스" if code == "1" else "24. 개인정보취급방침"
        declaration = '(?xml version="1.0" encoding="UTF-8"?)\n' if split == "validation" else ""
        xml = f"{declaration}<root><file><category>{category}</category><name>{stem}.pdf</name><cn>제1조 테스트 약관 {split}</cn></file></root>"
        label = {
            "clauseField": "39" if code == "1" else "24",
            "ftcCnclsns": "2" if code == "1" else "1",
            "clauseArticle": ["제1조 테스트"],
            "dvAntageous": code,
            "comProvision": ["표준 조항"],
        }
        with ZipFile(source_path, "w") as archive:
            archive.writestr(f"source/{label_dir}/{stem}_가공.xml", xml)
        with ZipFile(label_path, "w") as archive:
            archive.writestr(f"label/{label_dir}/{stem}_가공.json", json.dumps(label, ensure_ascii=False))


def _write_ota_fixture(path: Path) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("root/Service/Terms of Service/2025-01-01T00-00-00Z.md", "old terms")
        archive.writestr("root/Service/Terms of Service/2026-01-01T00-00-00Z.md", "latest terms")
        archive.writestr("root/Service/Privacy Policy/2026-02-01T00-00-00Z.md", "privacy text")


def _check_malformed_aihub_sources() -> None:
    pseudo_xml = """(root)
(file)
(category)
(!(CDATA(
18. 화재보험
)))
(category)
(name)
008_화재보험.pdf
(name)
(cn)
(!(CDATA(
제1조 복구된 약관
)))
(cn)
(file)
(root)
""".encode()
    category, original_name, text, mode, raw_category = _parse_source_xml(
        pseudo_xml,
        "source/01.유리/008_화재보험_가공.xml",
    )
    assert category == "화재보험"
    assert original_name == "008_화재보험.pdf"
    assert text == "제1조 복구된 약관"
    assert mode == "pseudo_xml"
    assert raw_category == "18. 화재보험"

    broken_closing_tags = """<root><file>
<category>
<![CDATA[
31. 사이버몰
]]>
< category>
<name>
006_사이버몰.pdf
< name>
<cn>
제1조 닫는 태그 복구
< cn>
</file></root>
""".encode()
    category, original_name, text, mode, _ = _parse_source_xml(
        broken_closing_tags,
        "source/01.유리/006_사이버몰_가공.xml",
    )
    assert category == "사이버몰"
    assert original_name == "006_사이버몰.pdf"
    assert text == "제1조 닫는 태그 복구"
    assert mode == "pseudo_xml"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    main()
