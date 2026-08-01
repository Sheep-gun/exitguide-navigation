from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
API_ROOT = ROOT / "apps" / "api"
MATERIALIZER_PATH = SCRIPTS / "Expand-NavigationCatalog.py"
CANONICAL_CATALOG_PATH = (
    ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
)
CANONICAL_EQUIVALENCE_PATH = CANONICAL_CATALOG_PATH.with_name(
    "function-equivalence.v1.json"
)

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from app.services.navigation_function_catalog import (  # noqa: E402
    NavigationFunctionCatalog,
)
from navigation_alias_context_overrides import (  # noqa: E402
    apply_alias_context_overrides,
    strip_alias_context_overrides,
)
from navigation_catalog_v16_data import (  # noqa: E402
    V16_FUNCTIONS,
    project_catalog_to_v15,
    project_equivalence_to_v15,
)


Materializer = Callable[[Path, Path], object]

EXPECTED_AUDIT_COUNTS = {
    "physical_function_count": 3118,
    "logical_function_count": 3108,
    "physical_intent_count": 2900,
    "logical_intent_count": 2890,
    "physical_default_terminal_count": 2898,
    "logical_default_terminal_count": 2888,
    "equivalence_class_count": 10,
    "equivalence_alias_count": 10,
}


def _load_materializer() -> Materializer:
    spec = importlib.util.spec_from_file_location(
        "expand_navigation_catalog_v16_materialization",
        MATERIALIZER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load materializer: {MATERIALIZER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    materialize = getattr(module, "materialize_catalog", None)
    if not callable(materialize):
        raise AssertionError(
            "Expand-NavigationCatalog.py must expose the public contract "
            "materialize_catalog(catalog_path, equivalence_path)"
        )
    return materialize


def _canonical_payload_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_canonical_pair(destination: Path) -> tuple[Path, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    catalog_path = destination / CANONICAL_CATALOG_PATH.name
    equivalence_path = destination / CANONICAL_EQUIVALENCE_PATH.name
    canonical = json.loads(CANONICAL_CATALOG_PATH.read_text(encoding="utf-8"))
    equivalence = json.loads(
        CANONICAL_EQUIVALENCE_PATH.read_text(encoding="utf-8")
    )
    if canonical.get("catalog_version") == "16.0.0":
        canonical = project_catalog_to_v15(canonical)
        equivalence = project_equivalence_to_v15(equivalence)
        _write_json(catalog_path, canonical)
        _write_json(equivalence_path, equivalence)
    else:
        shutil.copyfile(CANONICAL_CATALOG_PATH, catalog_path)
        shutil.copyfile(CANONICAL_EQUIVALENCE_PATH, equivalence_path)
    return catalog_path, equivalence_path


def _assert_alias_overrides_were_globally_regenerated(
    materialized: dict[str, Any],
    canonical_v15: dict[str, Any],
) -> None:
    metadata = materialized.get("alias_context_overrides")
    assert isinstance(metadata, dict)
    assert metadata.get("version") == "1.1.0"

    source_projection = strip_alias_context_overrides(materialized)
    assert metadata.get("source_catalog_sha256") == _canonical_payload_sha256(
        source_projection
    )
    assert apply_alias_context_overrides(source_projection) == materialized

    previous = canonical_v15.get("alias_context_overrides")
    assert isinstance(previous, dict)
    assert metadata.get("source_catalog_sha256") != previous.get(
        "source_catalog_sha256"
    )


def _assert_equivalence_projection(
    catalog_path: Path,
    equivalence_path: Path,
    temporary_root: Path,
) -> None:
    equivalence = json.loads(equivalence_path.read_text(encoding="utf-8"))
    classes = equivalence["classes"]
    alias_count = sum(len(item["alias_function_ids"]) for item in classes)
    assert (len(classes), alias_count) == (10, 10)

    audit_counts = equivalence["audit_counts"]
    for key, expected in EXPECTED_AUDIT_COUNTS.items():
        assert audit_counts[key] == expected, (key, audit_counts[key], expected)

    equivalence_members = {
        function_id
        for item in classes
        for function_id in (
            item["canonical_function_id"],
            *item["alias_function_ids"],
        )
    }
    v16_terminals = {
        str(item["function_id"])
        for item in V16_FUNCTIONS
        if bool(item["terminal"])
    }
    assert len(v16_terminals) == 240
    assert v16_terminals.isdisjoint(equivalence_members)

    runtime = NavigationFunctionCatalog(
        temporary_root / "materialized-v16.sqlite",
        catalog_path,
        equivalence_path=equivalence_path,
    )
    stats = runtime.stats()
    for key, expected in EXPECTED_AUDIT_COUNTS.items():
        assert stats[key] == expected, (key, stats[key], expected)


def _expect_fail_closed(
    materialize: Materializer,
    catalog_path: Path,
    equivalence_path: Path,
    expected_error_fragment: str,
) -> None:
    before = (catalog_path.read_bytes(), equivalence_path.read_bytes())
    try:
        materialize(catalog_path, equivalence_path)
    except ValueError as error:
        assert expected_error_fragment.casefold() in str(error).casefold(), str(error)
    else:
        raise AssertionError(
            f"invalid materialization input was accepted; expected "
            f"{expected_error_fragment!r}"
        )
    assert catalog_path.read_bytes() == before[0]
    assert equivalence_path.read_bytes() == before[1]


def main() -> None:
    canonical_before = {
        CANONICAL_CATALOG_PATH: CANONICAL_CATALOG_PATH.read_bytes(),
        CANONICAL_EQUIVALENCE_PATH: CANONICAL_EQUIVALENCE_PATH.read_bytes(),
    }
    try:
        materialize = _load_materializer()
        canonical_v15 = project_catalog_to_v15(
            json.loads(canonical_before[CANONICAL_CATALOG_PATH].decode("utf-8"))
        )

        with TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)

            catalog_path, equivalence_path = _copy_canonical_pair(
                temporary_root / "valid"
            )
            materialize(catalog_path, equivalence_path)
            catalog_first = catalog_path.read_bytes()
            equivalence_first = equivalence_path.read_bytes()
            materialized = json.loads(catalog_first.decode("utf-8"))

            functions = materialized["functions"]
            intents = materialized["intents"]
            assert materialized["catalog_version"] == "16.0.0"
            assert len({str(item["domain"]) for item in functions}) == 191
            assert len(functions) == 3118
            assert sum(bool(item["terminal"]) for item in functions) == 2900
            assert len(intents) == 2900
            _assert_alias_overrides_were_globally_regenerated(
                materialized,
                canonical_v15,
            )
            _assert_equivalence_projection(
                catalog_path,
                equivalence_path,
                temporary_root,
            )

            materialize(catalog_path, equivalence_path)
            assert catalog_path.read_bytes() == catalog_first
            assert equivalence_path.read_bytes() == equivalence_first

            partial_catalog_path, partial_equivalence_path = _copy_canonical_pair(
                temporary_root / "partial-v16"
            )
            partial = json.loads(partial_catalog_path.read_text(encoding="utf-8"))
            partial["functions"].append(copy.deepcopy(V16_FUNCTIONS[0]))
            _write_json(partial_catalog_path, partial)
            _expect_fail_closed(
                materialize,
                partial_catalog_path,
                partial_equivalence_path,
                "partial V16",
            )

            tampered_catalog_path, tampered_equivalence_path = _copy_canonical_pair(
                temporary_root / "tampered-equivalence"
            )
            tampered = json.loads(
                tampered_equivalence_path.read_text(encoding="utf-8")
            )
            tampered["classes"][0]["rationale"] += " [tampered]"
            _write_json(tampered_equivalence_path, tampered)
            _expect_fail_closed(
                materialize,
                tampered_catalog_path,
                tampered_equivalence_path,
                "integrity",
            )
    finally:
        for path, expected in canonical_before.items():
            assert path.read_bytes() == expected, f"canonical fixture changed: {path}"

    print("navigation catalog V16 materialization checks ok")


if __name__ == "__main__":
    main()
