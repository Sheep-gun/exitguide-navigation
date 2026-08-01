from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.dataset_adapters.aihub import convert_aihub_terms
from app.services.dataset_adapters.consumer_guidance import convert_consumer_guidance
from app.services.dataset_adapters.coverage import build_source_coverage
from app.services.dataset_adapters.ftc_standard_terms import convert_ftc_standard_terms
from app.services.dataset_adapters.hf_terms import convert_hf_online_terms
from app.services.dataset_adapters.open_terms_archive import convert_open_terms_archive
from app.services.dataset_adapters.princeton import convert_princeton_policies
from app.services.dataset_adapters.privacy_corpora import convert_privacy_corpora
from app.services.dataset_adapters.privacyqa import convert_privacyqa
from app.services.dataset_adapters.tosdr import convert_tosdr_sources
from app.services.dataset_adapters.validation import validate_normalized_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize public terms datasets into staging JSONL files.")
    parser.add_argument("--aihub-root", type=Path, required=True)
    parser.add_argument("--open-terms-archive-zip", type=Path, required=True)
    parser.add_argument("--public-raw-root", type=Path, required=True)
    parser.add_argument("--source-inventory", type=Path, required=True)
    parser.add_argument("--princeton-database", type=Path)
    parser.add_argument("--skip-princeton", action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if not args.skip_princeton and not args.princeton_database:
        parser.error("--princeton-database is required unless --skip-princeton is used")
    output_root = args.output_root.resolve()
    raw_root = args.public_raw_root.resolve()

    conversions = {
        "aihub": convert_aihub_terms(args.aihub_root.resolve(), output_root),
        "open_terms_archive": convert_open_terms_archive(
            args.open_terms_archive_zip.resolve(),
            output_root,
        ),
        "consumer_guidance": convert_consumer_guidance(raw_root, output_root),
        "ftc_standard_terms": convert_ftc_standard_terms(raw_root / "ftc_standard_terms", output_root),
        "hf_online_terms": convert_hf_online_terms(raw_root / "hf_online_terms_of_service", output_root),
        "tosdr": convert_tosdr_sources(raw_root, output_root),
        "privacy_corpora": convert_privacy_corpora(raw_root, output_root),
        "privacyqa": convert_privacyqa(raw_root / "privacyqa_emnlp", output_root),
    }
    if not args.skip_princeton:
        conversions["princeton"] = convert_princeton_policies(args.princeton_database.resolve(), output_root)

    validations = {
        f"{source_id}:{data_file}": validate_normalized_jsonl(
            output_root / source_id / data_file,
            output_root / source_id / manifest,
            source_id,
        )
        for source_id, data_file, manifest in _validation_targets(include_princeton=not args.skip_princeton)
    }
    coverage = build_source_coverage(args.source_inventory.resolve(), raw_root, output_root)
    results = {"conversions": conversions, "validations": validations, "coverage": coverage}
    rendered = json.dumps(results, ensure_ascii=False, indent=2)
    (output_root / "last-conversion-summary.json").write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def _validation_targets(include_princeton: bool) -> list[tuple[str, str, str]]:
    targets = [
        ("aihub_legal_regulation_terms", "documents.jsonl", "manifest.json"),
        ("open_terms_archive_contrib", "documents-latest.jsonl", "manifest.json"),
        ("data_go_kr_kca_standard_answers", "records.jsonl", "manifest.json"),
        ("data_go_kr_ftc_consumer_model_cases", "records.jsonl", "manifest.json"),
        ("ftc_standard_terms", "documents.jsonl", "manifest.json"),
        ("hf_online_terms_of_service", "segments.jsonl", "manifest.json"),
        ("tosdr_zenodo_raw_2023", "documents.jsonl", "manifest.json"),
        ("tosdr_terms_corpus_github", "documents.jsonl", "manifest.json"),
        ("usableprivacy_opp_115", "documents.jsonl", "manifest.json"),
        ("usableprivacy_mapp", "documents.jsonl", "manifest.json"),
        ("usableprivacy_optoutchoice_2017", "documents.jsonl", "manifest.json"),
        ("usableprivacy_acl_coling_2014", "documents.jsonl", "manifest.json"),
        ("usableprivacy_app_350", "documents.jsonl", "manifest.json"),
        ("usableprivacy_app_350", "segments.jsonl", "segments-manifest.json"),
        ("usableprivacy_optoutchoice_2020", "documents.jsonl", "manifest.json"),
        ("usableprivacy_optoutchoice_2020", "segments.jsonl", "segments-manifest.json"),
        ("privacyqa_emnlp", "qa-segments.jsonl", "manifest.json"),
    ]
    if include_princeton:
        targets.append(("princeton_leuven_privacy_policies", "documents.jsonl", "manifest.json"))
    return targets


if __name__ == "__main__":
    main()
