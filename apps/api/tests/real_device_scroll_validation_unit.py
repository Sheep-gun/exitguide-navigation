from __future__ import annotations

import copy
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = ROOT / "scripts" / "Validate-RealDeviceObservationCorpus.py"


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "exitguide_real_device_scroll_validator_test",
        VALIDATOR_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


Mutation = Callable[[dict[str, Any]], None]


def _validate_case(
    *,
    mutate_screen: Mutation | None = None,
    mutate_transition: Mutation | None = None,
    mutate_typed_screen: Mutation | None = None,
    mutate_typed_transition: Mutation | None = None,
    include_root_bounds: bool = False,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    screen_payload: dict[str, Any] = {
        "screen_id": "screen-source",
        "scrollable_regions": [[0, 100, 1080, 2100]],
    }
    transition_payload: dict[str, Any] = {
        "transition_id": "transition-scroll",
        "source_screen_id": "screen-source",
        "target_screen_id": "screen-target",
        "action_type": "scroll_forward",
        "auto_executed": True,
        "coordinates": [540, 1940, 540, 380],
        "scroll_direction": "forward",
        "scroll_distance": 1560,
    }
    if mutate_screen:
        mutate_screen(screen_payload)
    if mutate_transition:
        mutate_transition(transition_payload)

    typed_screen: dict[str, Any] = {
        "screen_id": "screen-source",
        "scrollable_regions": copy.deepcopy(screen_payload.get("scrollable_regions", [])),
    }
    typed_transition: dict[str, Any] = {
        "source_screen_id": transition_payload.get("source_screen_id", "screen-source"),
        "action_type": transition_payload.get("action_type", "scroll_forward"),
        "auto_executed": 1 if transition_payload.get("auto_executed") is True else 0,
        "coordinates": copy.deepcopy(transition_payload.get("coordinates")),
        "scroll_direction": transition_payload.get("scroll_direction", ""),
        "scroll_distance": transition_payload.get("scroll_distance"),
    }
    if mutate_typed_screen:
        mutate_typed_screen(typed_screen)
    if mutate_typed_transition:
        mutate_typed_transition(typed_transition)

    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            CREATE TABLE screens (
              screen_id TEXT NOT NULL,
              scrollable_regions_json TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE TABLE elements (
              element_id TEXT NOT NULL,
              screen_id TEXT NOT NULL,
              bounds_json TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE TABLE transitions (
              transition_id TEXT NOT NULL,
              event_sequence INTEGER NOT NULL,
              source_screen_id TEXT NOT NULL,
              action_type TEXT NOT NULL,
              auto_executed INTEGER NOT NULL,
              coordinates_json TEXT,
              scroll_direction TEXT,
              scroll_distance REAL,
              payload_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO screens VALUES (?, ?, ?)",
            (
                typed_screen["screen_id"],
                json.dumps(typed_screen["scrollable_regions"]),
                json.dumps(screen_payload),
            ),
        )
        if include_root_bounds:
            root_payload = {
                "element_id": "root-container",
                "screen_id": "screen-source",
                "parent_id": None,
                "bounds": [0, 100, 1080, 2100],
            }
            connection.execute(
                "INSERT INTO elements VALUES (?, ?, ?, ?)",
                (
                    "root-container",
                    "screen-source",
                    json.dumps(root_payload["bounds"]),
                    json.dumps(root_payload),
                ),
            )
        connection.execute(
            "INSERT INTO transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "transition-scroll",
                1,
                typed_transition["source_screen_id"],
                typed_transition["action_type"],
                typed_transition["auto_executed"],
                json.dumps(typed_transition["coordinates"]),
                typed_transition["scroll_direction"],
                typed_transition["scroll_distance"],
                json.dumps(transition_payload),
            ),
        )
        columns = {
            table: {
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            for table in ("screens", "elements", "transitions")
        }
        errors: list[dict[str, str]] = []
        checks: dict[str, Any] = {}
        VALIDATOR._validate_auto_scroll_distances(
            connection,
            columns,
            errors,
            checks,
            Path("scroll-validation-test.sqlite"),
        )
        return errors, checks
    finally:
        connection.close()


def _codes(errors: list[dict[str, str]]) -> set[str]:
    return {item["code"] for item in errors}


def test_valid_78_percent_scroll_is_accepted() -> None:
    errors, checks = _validate_case()
    assert errors == [], errors
    assert checks["auto_scroll_transition_count"] == 1
    assert checks["auto_scroll_validated_count"] == 1
    assert checks["auto_scroll_target_region_ratio"] == {
        "minimum": 0.72,
        "maximum": 0.85,
        "target": 0.78,
    }


def test_exact_72_and_85_percent_boundaries_are_accepted() -> None:
    for coordinates, distance in (
        ([540, 900, 540, 180], 720),
        ([540, 900, 540, 50], 850),
    ):
        errors, checks = _validate_case(
            mutate_screen=lambda value: value.update(scrollable_regions=[[0, 0, 1080, 1000]]),
            mutate_transition=lambda value, coordinates=coordinates, distance=distance: value.update(
                coordinates=coordinates,
                scroll_distance=distance,
            ),
        )
        assert errors == [], errors
        assert checks["auto_scroll_validated_count"] == 1


def test_root_structural_bounds_are_a_fail_closed_fallback() -> None:
    errors, checks = _validate_case(
        mutate_screen=lambda value: value.update(scrollable_regions=[]),
        include_root_bounds=True,
    )
    assert errors == [], errors
    assert checks["auto_scroll_validated_count"] == 1

    errors, checks = _validate_case(
        mutate_screen=lambda value: value.update(scrollable_regions=[]),
        include_root_bounds=False,
    )
    assert "auto_scroll_region_evidence_missing" in _codes(errors)
    assert checks["auto_scroll_validated_count"] == 0


def test_missing_or_divergent_coordinate_and_distance_evidence_is_rejected() -> None:
    errors, _ = _validate_case(
        mutate_transition=lambda value: value.pop("coordinates"),
        mutate_typed_transition=lambda value: value.update(coordinates=[540, 1940, 540, 380]),
    )
    assert "auto_scroll_coordinates_missing_or_invalid" in _codes(errors)

    errors, _ = _validate_case(
        mutate_typed_transition=lambda value: value.update(coordinates=[540, 1940, 540, 390]),
    )
    assert "auto_scroll_coordinate_evidence_inconsistent" in _codes(errors)

    errors, _ = _validate_case(
        mutate_typed_transition=lambda value: value.update(scroll_distance=1500),
    )
    assert "auto_scroll_distance_evidence_inconsistent" in _codes(errors)

    errors, _ = _validate_case(
        mutate_transition=lambda value: value.update(scroll_distance=1500),
    )
    assert "auto_scroll_distance_inconsistent" in _codes(errors)


def test_direction_source_and_region_attestations_must_agree() -> None:
    errors, _ = _validate_case(
        mutate_transition=lambda value: value.update(
            coordinates=[540, 380, 540, 1940],
            scroll_distance=1560,
        ),
    )
    assert "auto_scroll_direction_invalid" in _codes(errors)

    errors, _ = _validate_case(
        mutate_typed_transition=lambda value: value.update(source_screen_id="screen-other"),
    )
    assert "auto_scroll_source_screen_missing" in _codes(errors)

    errors, _ = _validate_case(
        mutate_typed_screen=lambda value: value.update(scrollable_regions=[[0, 0, 1080, 2200]]),
    )
    assert "auto_scroll_region_evidence_inconsistent" in _codes(errors)


def test_short_overshooting_horizontal_and_outside_gestures_are_rejected() -> None:
    cases = (
        ([540, 1500, 540, 500], 1000, "auto_scroll_not_near_page"),
        ([540, 2000, 540, 200], 1800, "auto_scroll_not_near_page"),
        ([540, 1940, 800, 380], 1560, "auto_scroll_not_near_page"),
        ([1200, 1940, 1200, 380], 1560, "auto_scroll_coordinates_outside_region"),
    )
    for coordinates, distance, expected_code in cases:
        errors, checks = _validate_case(
            mutate_transition=lambda value, coordinates=coordinates, distance=distance: value.update(
                coordinates=coordinates,
                scroll_distance=distance,
            )
        )
        assert expected_code in _codes(errors), (expected_code, errors)
        assert checks["auto_scroll_validated_count"] == 0


def test_payload_only_scroll_cannot_evade_typed_validation() -> None:
    errors, checks = _validate_case(
        mutate_typed_transition=lambda value: value.update(action_type="click")
    )
    assert "auto_scroll_declaration_inconsistent" in _codes(errors)
    assert checks["auto_scroll_transition_count"] == 1
    assert checks["auto_scroll_validated_count"] == 0


def main() -> None:
    test_valid_78_percent_scroll_is_accepted()
    test_exact_72_and_85_percent_boundaries_are_accepted()
    test_root_structural_bounds_are_a_fail_closed_fallback()
    test_missing_or_divergent_coordinate_and_distance_evidence_is_rejected()
    test_direction_source_and_region_attestations_must_agree()
    test_short_overshooting_horizontal_and_outside_gestures_are_rejected()
    test_payload_only_scroll_cannot_evade_typed_validation()
    print("Real-device automatic scroll validation checks ok")


if __name__ == "__main__":
    main()
