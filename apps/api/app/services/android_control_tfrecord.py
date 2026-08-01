from __future__ import annotations

import gzip
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


WANTED_FEATURES = {
    "episode_id",
    "goal",
    "accessibility_trees",
    "screenshot_widths",
    "screenshot_heights",
    "actions",
    "step_instructions",
}


@dataclass(frozen=True)
class DecodedRect:
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0


@dataclass(frozen=True)
class DecodedAccessibilityNode:
    unique_id: int
    bounds_in_screen: DecodedRect
    class_name: str = ""
    content_description: str = ""
    hint_text: str = ""
    package_name: str = ""
    text: str = ""
    view_id_resource_name: str = ""
    is_clickable: bool = False
    is_editable: bool = False
    is_enabled: bool = False
    is_password: bool = False
    is_visible_to_user: bool = False
    tooltip_text: str = ""


@dataclass(frozen=True)
class DecodedFeature:
    bytes_values: tuple[bytes, ...] = ()
    int_values: tuple[int, ...] = ()


def iter_gzip_tfrecord_examples(paths: Iterable[str | Path]) -> Iterator[dict[str, DecodedFeature]]:
    for raw_path in paths:
        path = Path(raw_path)
        with gzip.open(path, "rb") as handle:
            while True:
                length_bytes = handle.read(8)
                if not length_bytes:
                    break
                if len(length_bytes) != 8:
                    raise ValueError(f"Truncated TFRecord length header: {path}")
                record_length = struct.unpack("<Q", length_bytes)[0]
                if len(handle.read(4)) != 4:
                    raise ValueError(f"Truncated TFRecord length checksum: {path}")
                payload = handle.read(record_length)
                if len(payload) != record_length:
                    raise ValueError(f"Truncated TFRecord payload: {path}")
                if len(handle.read(4)) != 4:
                    raise ValueError(f"Truncated TFRecord payload checksum: {path}")
                yield decode_tf_example(payload)


def decode_tf_example(payload: bytes | memoryview) -> dict[str, DecodedFeature]:
    view = memoryview(payload)
    features_message = next(
        (value for field, wire, value in _iter_fields(view) if field == 1 and wire == 2),
        None,
    )
    if not isinstance(features_message, memoryview):
        return {}
    result: dict[str, DecodedFeature] = {}
    for field, wire, entry in _iter_fields(features_message):
        if field != 1 or wire != 2 or not isinstance(entry, memoryview):
            continue
        key = ""
        feature_message = None
        for entry_field, entry_wire, entry_value in _iter_fields(entry):
            if entry_field == 1 and entry_wire == 2 and isinstance(entry_value, memoryview):
                key = _decode_string(entry_value)
            elif entry_field == 2 and entry_wire == 2 and isinstance(entry_value, memoryview):
                feature_message = entry_value
        if key not in WANTED_FEATURES or feature_message is None:
            continue
        result[key] = _decode_feature(feature_message)
    return result


def decode_accessibility_forest(payload: bytes | memoryview) -> list[DecodedAccessibilityNode]:
    nodes: list[DecodedAccessibilityNode] = []
    for field, wire, window in _iter_fields(memoryview(payload)):
        if field != 1 or wire != 2 or not isinstance(window, memoryview):
            continue
        tree = next(
            (value for number, kind, value in _iter_fields(window) if number == 11 and kind == 2),
            None,
        )
        if not isinstance(tree, memoryview):
            continue
        for tree_field, tree_wire, node_message in _iter_fields(tree):
            if tree_field == 1 and tree_wire == 2 and isinstance(node_message, memoryview):
                nodes.append(_decode_node(node_message))
    return nodes


def _decode_feature(message: memoryview) -> DecodedFeature:
    for field, wire, value in _iter_fields(message):
        if field == 1 and wire == 2 and isinstance(value, memoryview):
            values = tuple(
                bytes(item)
                for number, kind, item in _iter_fields(value)
                if number == 1 and kind == 2 and isinstance(item, memoryview)
            )
            return DecodedFeature(bytes_values=values)
        if field == 3 and wire == 2 and isinstance(value, memoryview):
            integers: list[int] = []
            for number, kind, item in _iter_fields(value):
                if number != 1:
                    continue
                if kind == 0 and isinstance(item, int):
                    integers.append(item)
                elif kind == 2 and isinstance(item, memoryview):
                    integers.extend(_packed_varints(item))
            return DecodedFeature(int_values=tuple(integers))
    return DecodedFeature()


def _decode_node(message: memoryview) -> DecodedAccessibilityNode:
    values: dict[int, list[int | memoryview]] = {}
    for field, _, value in _iter_fields(message):
        values.setdefault(field, []).append(value)
    rect_message = _first_view(values, 2)
    return DecodedAccessibilityNode(
        unique_id=_first_int(values, 1),
        bounds_in_screen=_decode_rect(rect_message) if rect_message is not None else DecodedRect(),
        class_name=_first_string(values, 3),
        content_description=_first_string(values, 4),
        hint_text=_first_string(values, 5),
        package_name=_first_string(values, 6),
        text=_first_string(values, 7),
        view_id_resource_name=_first_string(values, 10),
        is_clickable=bool(_first_int(values, 14)),
        is_editable=bool(_first_int(values, 15)),
        is_enabled=bool(_first_int(values, 16)),
        is_password=bool(_first_int(values, 20)),
        is_visible_to_user=bool(_first_int(values, 23)),
        tooltip_text=_first_string(values, 31),
    )


def _decode_rect(message: memoryview) -> DecodedRect:
    values = {field: int(value) for field, wire, value in _iter_fields(message) if wire == 0}
    return DecodedRect(
        left=values.get(1, 0),
        top=values.get(2, 0),
        right=values.get(3, 0),
        bottom=values.get(4, 0),
    )


def _iter_fields(message: memoryview) -> Iterator[tuple[int, int, int | memoryview]]:
    position = 0
    length = len(message)
    while position < length:
        key, position = _read_varint(message, position)
        field_number = key >> 3
        wire_type = key & 0x07
        if field_number <= 0:
            raise ValueError("Invalid protobuf field number")
        if wire_type == 0:
            value, position = _read_varint(message, position)
        elif wire_type == 1:
            end = position + 8
            if end > length:
                raise ValueError("Truncated protobuf fixed64 field")
            value = int.from_bytes(message[position:end], "little")
            position = end
        elif wire_type == 2:
            item_length, position = _read_varint(message, position)
            end = position + item_length
            if end > length:
                raise ValueError("Truncated protobuf length-delimited field")
            value = message[position:end]
            position = end
        elif wire_type == 5:
            end = position + 4
            if end > length:
                raise ValueError("Truncated protobuf fixed32 field")
            value = int.from_bytes(message[position:end], "little")
            position = end
        else:
            raise ValueError(f"Unsupported protobuf wire type: {wire_type}")
        yield field_number, wire_type, value


def _read_varint(message: memoryview, position: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while position < len(message) and shift < 70:
        byte = int(message[position])
        position += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, position
        shift += 7
    raise ValueError("Truncated or oversized protobuf varint")


def _packed_varints(message: memoryview) -> list[int]:
    values: list[int] = []
    position = 0
    while position < len(message):
        value, position = _read_varint(message, position)
        values.append(value)
    return values


def _first_int(values: dict[int, list[int | memoryview]], field: int) -> int:
    items = values.get(field, ())
    return int(items[0]) if items and isinstance(items[0], int) else 0


def _first_view(values: dict[int, list[int | memoryview]], field: int) -> memoryview | None:
    items = values.get(field, ())
    return items[0] if items and isinstance(items[0], memoryview) else None


def _first_string(values: dict[int, list[int | memoryview]], field: int) -> str:
    value = _first_view(values, field)
    return _decode_string(value) if value is not None else ""


def _decode_string(value: memoryview) -> str:
    return bytes(value).decode("utf-8", errors="replace").strip()
