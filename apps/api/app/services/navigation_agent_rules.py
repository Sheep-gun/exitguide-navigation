from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


RULE_INDEX_SCHEMA = "navigation-agent-rules.v1"
READABLE_STATUSES = {"observed", "validated", "enforced"}
KNOWN_STATUSES = READABLE_STATUSES | {"deprecated"}


@dataclass(frozen=True)
class AgentRule:
    rule_id: str
    goal_id: str
    status: str
    evidence_count: int
    updated_batch: str
    tags: tuple[str, ...]
    summary: str
    path: str
    sha256: str


def _parse_value(raw: str) -> object:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        return [
            item.strip().strip("\"'")
            for item in value[1:-1].split(",")
            if item.strip()
        ]
    unquoted = value.strip("\"'")
    if unquoted.isdigit():
        return int(unquoted)
    return unquoted


def parse_rule_document(path: str | Path, *, root: str | Path | None = None) -> tuple[AgentRule, str]:
    source = Path(path).resolve()
    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"agent rule front matter is missing: {source}")
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as error:
        raise ValueError(f"agent rule front matter is not closed: {source}") from error
    metadata: dict[str, object] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, raw = line.partition(":")
        if not separator:
            raise ValueError(f"invalid agent rule metadata line: {line}")
        metadata[key.strip()] = _parse_value(raw)
    required = {"rule_id", "goal_id", "status", "evidence_count", "updated_batch"}
    missing = sorted(required - metadata.keys())
    if missing:
        raise ValueError(f"agent rule metadata is missing: {', '.join(missing)}")
    status = str(metadata["status"])
    if status not in KNOWN_STATUSES:
        raise ValueError(f"unsupported agent rule status: {status}")
    body = "\n".join(lines[end + 1 :]).strip()
    relative = source.name if root is None else source.relative_to(Path(root).resolve()).as_posix()
    tags_value = metadata.get("tags", [])
    tags = tuple(str(item) for item in tags_value) if isinstance(tags_value, list) else ()
    rule = AgentRule(
        rule_id=str(metadata["rule_id"]),
        goal_id=str(metadata["goal_id"]),
        status=status,
        evidence_count=int(metadata["evidence_count"]),
        updated_batch=str(metadata["updated_batch"]),
        tags=tags,
        summary=str(metadata.get("summary", "")),
        path=relative,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    return rule, body


def build_rule_index(rule_dir: str | Path, *, generation_id: str = "git-working-tree") -> dict[str, object]:
    root = Path(rule_dir).resolve()
    parsed = [
        parse_rule_document(path, root=root)
        for path in sorted(root.rglob("*.md"))
        if path.name.upper() != "README.MD"
    ]
    identifiers = [rule.rule_id for rule, _ in parsed]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("agent rule_id values must be unique")
    return {
        "schema_version": RULE_INDEX_SCHEMA,
        "generation_id": generation_id,
        "rules": [
            {
                "rule_id": rule.rule_id,
                "goal_id": rule.goal_id,
                "status": rule.status,
                "evidence_count": rule.evidence_count,
                "updated_batch": rule.updated_batch,
                "tags": list(rule.tags),
                "summary": rule.summary,
                "path": rule.path,
                "sha256": rule.sha256,
            }
            for rule, _ in parsed
        ],
    }


def write_rule_index(
    rule_dir: str | Path,
    index_path: str | Path,
    *,
    generation_id: str = "git-working-tree",
    fts_path: str | Path | None = None,
) -> dict[str, object]:
    root = Path(rule_dir).resolve()
    payload = build_rule_index(root, generation_id=generation_id)
    target = Path(index_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if fts_path is not None:
        _write_fts(root, payload, Path(fts_path).resolve())
    return payload


def _write_fts(root: Path, index: dict[str, object], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    connection = sqlite3.connect(target)
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE rule_search USING fts5("
            "rule_id UNINDEXED, goal_id, status UNINDEXED, tags, summary, body)"
        )
        for item in index["rules"]:
            path = root / str(item["path"])
            _, body = parse_rule_document(path, root=root)
            connection.execute(
                "INSERT INTO rule_search(rule_id, goal_id, status, tags, summary, body) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    item["rule_id"],
                    item["goal_id"],
                    item["status"],
                    " ".join(item.get("tags", [])),
                    item.get("summary", ""),
                    body,
                ),
            )
        connection.commit()
    finally:
        connection.close()


class NavigationAgentRuleStore:
    """Read-only, non-executable rule retrieval for shadow safety context."""

    def __init__(self, index_path: str | Path, *, mode: str = "shadow") -> None:
        if mode not in {"shadow"}:
            raise ValueError(f"unsupported agent rule retrieval mode: {mode}")
        self.index_path = Path(index_path).expanduser().resolve()
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != RULE_INDEX_SCHEMA:
            raise ValueError("agent rule index schema mismatch")
        self.mode = mode
        self.generation_id = str(payload.get("generation_id", "unknown"))
        self.rules = tuple(AgentRule(
            rule_id=str(item["rule_id"]),
            goal_id=str(item["goal_id"]),
            status=str(item["status"]),
            evidence_count=int(item.get("evidence_count", 0)),
            updated_batch=str(item.get("updated_batch", "")),
            tags=tuple(str(tag) for tag in item.get("tags", [])),
            summary=str(item.get("summary", "")),
            path=str(item["path"]),
            sha256=str(item["sha256"]),
        ) for item in payload.get("rules", []))

    def consult(self, goal_id: str | None, *, screen_terms: Iterable[str] = ()) -> tuple[AgentRule, ...]:
        normalized_goal = (goal_id or "").strip()
        selected = [
            rule
            for rule in self.rules
            if rule.status in READABLE_STATUSES and rule.goal_id in {"*", normalized_goal}
        ]
        tokens = {
            token.casefold()
            for value in screen_terms
            for token in str(value).replace("/", " ").split()
            if len(token) >= 2
        }
        pattern_candidates = [
            rule
            for rule in self.rules
            if rule.status in READABLE_STATUSES
            and rule.goal_id.startswith("pattern.")
            and any(tag.casefold() in tokens for tag in rule.tags)
        ][:3]
        by_id = {rule.rule_id: rule for rule in (*selected, *pattern_candidates)}
        return tuple(by_id[key] for key in sorted(by_id))

    def status(self) -> dict[str, object]:
        return {
            "enabled": True,
            "mode": self.mode,
            "generation_id": self.generation_id,
            "rules": len(self.rules),
            "runtime_execution_allowed": False,
        }
