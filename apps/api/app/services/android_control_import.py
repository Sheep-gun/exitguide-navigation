from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator

from app.services.android_control_index import AndroidControlStepRecord
from app.services.android_control_tfrecord import (
    DecodedFeature,
    decode_accessibility_forest,
    iter_gzip_tfrecord_examples,
)


def iter_official_tfrecords(
    paths: Iterable[str | Path],
    *,
    source_split: str = "",
    episode_limit: int | None = None,
) -> Iterator[AndroidControlStepRecord]:
    """Stream Google's official GZIP TFRecords into a screenshot-free schema."""
    filenames = [str(Path(path)) for path in paths]
    if not filenames:
        raise ValueError("At least one AndroidControl TFRecord path is required")
    for episode_number, features in enumerate(iter_gzip_tfrecord_examples(filenames)):
        if episode_limit is not None and episode_number >= episode_limit:
            break
        episode_id = _first_feature_text(features, "episode_id") or str(episode_number)
        goal = _first_feature_text(features, "goal")
        actions = [_decode_action(value) for value in _feature_bytes(features, "actions")]
        step_instructions = [_decode_text(value) for value in _feature_bytes(features, "step_instructions")]
        trees = list(_feature_bytes(features, "accessibility_trees"))
        widths = _feature_ints(features, "screenshot_widths")
        heights = _feature_ints(features, "screenshot_heights")
        last_app_name = ""
        for step_index, action in enumerate(actions):
            action_type = _clean(action.get("action_type", "unknown")).lower()
            if action_type == "open_app":
                last_app_name = _clean(action.get("app_name", "")) or last_app_name
            forest = None
            if step_index < len(trees):
                forest = decode_accessibility_forest(trees[step_index])
            nodes = forest or []
            width = widths[step_index] if step_index < len(widths) else 0
            height = heights[step_index] if step_index < len(heights) else 0
            target_text = _target_text(action, nodes, width=width, height=height)
            app_name = _app_name(nodes) or last_app_name
            yield AndroidControlStepRecord(
                episode_id=episode_id,
                goal=goal,
                step_index=step_index,
                step_instruction=step_instructions[step_index] if step_index < len(step_instructions) else "",
                action_type=action_type,
                target_text=target_text,
                screen_text=_screen_text(nodes),
                app_name=app_name,
                source_split=source_split,
            )


def _feature_bytes(features: dict[str, DecodedFeature], name: str) -> list[bytes]:
    feature = features.get(name, DecodedFeature())
    return list(feature.bytes_values)


def _feature_ints(features: dict[str, DecodedFeature], name: str) -> list[int]:
    feature = features.get(name, DecodedFeature())
    return list(feature.int_values)


def _first_feature_text(features: dict[str, DecodedFeature], name: str) -> str:
    byte_values = _feature_bytes(features, name)
    if byte_values:
        return _decode_text(byte_values[0])
    int_values = _feature_ints(features, name)
    return str(int_values[0]) if int_values else ""


def _decode_text(value: bytes) -> str:
    return value.decode("utf-8", errors="replace").strip()


def _decode_action(value: bytes) -> dict[str, object]:
    payload = json.loads(_decode_text(value))
    if not isinstance(payload, dict):
        raise ValueError("AndroidControl action must decode to a JSON object")
    return payload


def _target_text(action: dict[str, object], nodes: list[object], *, width: int, height: int) -> str:
    action_type = _clean(action.get("action_type", "")).lower()
    if action_type in {"click", "long_press"}:
        point = _action_point(action, width=width, height=height)
        if point is None:
            return ""
        node = _smallest_enclosing_node(nodes, *point)
        if node is None:
            return ""
        return _node_label(node)
    if action_type == "open_app":
        return _clean(action.get("app_name", ""))
    if action_type == "scroll":
        direction = _clean(action.get("direction", ""))
        return f"scroll {direction}".strip()
    if action_type == "navigate_back":
        return "Back"
    if action_type == "navigate_home":
        return "Home"
    if action_type == "input_text":
        # Do not copy typed values into the retrieval index.
        return "text input"
    if action_type == "wait":
        return "wait"
    return action_type


def _action_point(action: dict[str, object], *, width: int, height: int) -> tuple[float, float] | None:
    try:
        x = float(action["x"])
        y = float(action["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if width > 0 and 0.0 <= x <= 1.0:
        x *= width
    if height > 0 and 0.0 <= y <= 1.0:
        y *= height
    return x, y


def _smallest_enclosing_node(nodes: list[object], x: float, y: float):
    matches: list[tuple[int, int, object]] = []
    for node in nodes:
        if bool(getattr(node, "is_password", False)) or not bool(getattr(node, "is_visible_to_user", True)):
            continue
        bounds = getattr(node, "bounds_in_screen", None)
        if bounds is None or not (bounds.left <= x <= bounds.right and bounds.top <= y <= bounds.bottom):
            continue
        area = max(1, int(bounds.right - bounds.left) * int(bounds.bottom - bounds.top))
        label_penalty = 0 if _node_label(node) else 1
        matches.append((label_penalty, area, node))
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], item[1]))
    return matches[0][2]


def _node_label(node: object) -> str:
    if bool(getattr(node, "is_password", False)):
        return ""
    for attribute in ("text", "content_description", "hint_text", "tooltip_text"):
        value = _clean(getattr(node, attribute, ""))
        if value:
            return value[:300]
    view_id = _clean(getattr(node, "view_id_resource_name", ""))
    if view_id:
        return view_id.rsplit("/", 1)[-1].replace("_", " ")[:300]
    return ""


def _screen_text(nodes: list[object]) -> str:
    labels: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        if bool(getattr(node, "is_password", False)) or bool(getattr(node, "is_editable", False)):
            continue
        if not bool(getattr(node, "is_visible_to_user", True)):
            continue
        label = _node_label(node)
        normalized = label.lower()
        if not label or normalized in seen:
            continue
        seen.add(normalized)
        labels.append(label)
        if len(labels) >= 120:
            break
    return " | ".join(labels)[:4000]


def _app_name(nodes: list[object]) -> str:
    packages = Counter(
        _clean(getattr(node, "package_name", ""))
        for node in nodes
        if _clean(getattr(node, "package_name", ""))
    )
    return packages.most_common(1)[0][0] if packages else ""


def _clean(value: object) -> str:
    return " ".join(str(value if value is not None else "").split())
