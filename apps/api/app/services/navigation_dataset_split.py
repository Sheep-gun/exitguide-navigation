from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_SPLITS = frozenset({"collection", "validation", "locked_holdout"})


class DatasetSplitAccessError(ValueError):
    """Raised when collection would violate the locked app-disjoint split."""


@dataclass(frozen=True)
class DatasetSplitEntry:
    app_package: str
    app_name: str
    split: str
    reason: str
    existing_decision_cases: int
    available_on_device: bool
    priority_app: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "app_package": self.app_package,
            "app_name": self.app_name,
            "split": self.split,
            "reason": self.reason,
            "existing_decision_cases": self.existing_decision_cases,
            "available_on_device": self.available_on_device,
            "priority_app": self.priority_app,
        }


class NavigationDatasetSplitManifest:
    """Immutable, app-disjoint collection/validation/holdout assignment."""

    def __init__(
        self,
        *,
        manifest_version: str,
        digest: str,
        entries: list[DatasetSplitEntry],
        source_path: Path,
    ) -> None:
        self.manifest_version = manifest_version
        self.digest = digest
        self.entries = tuple(entries)
        self.source_path = source_path
        self._by_package = {entry.app_package: entry for entry in entries}

    @classmethod
    def load(cls, path: str | Path) -> "NavigationDatasetSplitManifest":
        source_path = Path(path).expanduser().resolve()
        raw = source_path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("dataset split manifest must be a JSON object")
        manifest_version = str(payload.get("manifest_version", "")).strip()
        if not manifest_version:
            raise ValueError("dataset split manifest_version is required")
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ValueError("dataset split entries must be a non-empty list")
        entries: list[DatasetSplitEntry] = []
        seen: set[str] = set()
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                raise ValueError("dataset split entry must be an object")
            app_package = str(raw_entry.get("app_package", "")).strip()
            split = str(raw_entry.get("split", "")).strip()
            if not app_package or app_package in seen:
                raise ValueError("dataset split app_package must be non-empty and unique")
            if split not in ALLOWED_SPLITS:
                raise ValueError(f"unsupported dataset split for {app_package}: {split}")
            existing_cases = int(raw_entry.get("existing_decision_cases", 0))
            if existing_cases < 0:
                raise ValueError("existing_decision_cases cannot be negative")
            if split == "locked_holdout" and existing_cases != 0:
                raise ValueError(f"contaminated app cannot be locked holdout: {app_package}")
            entries.append(
                DatasetSplitEntry(
                    app_package=app_package,
                    app_name=str(raw_entry.get("app_name", app_package)).strip() or app_package,
                    split=split,
                    reason=str(raw_entry.get("reason", "")).strip(),
                    existing_decision_cases=existing_cases,
                    available_on_device=bool(raw_entry.get("available_on_device", False)),
                    priority_app=bool(raw_entry.get("priority_app", False)),
                )
            )
            seen.add(app_package)
        holdout_count = sum(entry.split == "locked_holdout" for entry in entries)
        # During supervised raw collection every currently installed app may be
        # a collection source. Once a holdout cohort is introduced it must
        # still contain at least three app-disjoint entries.
        if 0 < holdout_count < 3:
            raise ValueError(
                "dataset split manifest requires either zero or at least three "
                "locked holdout apps"
            )
        return cls(
            manifest_version=manifest_version,
            digest=hashlib.sha256(raw).hexdigest(),
            entries=entries,
            source_path=source_path,
        )

    def entry_for(self, app_package: str) -> DatasetSplitEntry | None:
        return self._by_package.get(app_package)

    def require_collection_access(
        self,
        app_package: str,
        *,
        allow_locked_holdout: bool,
    ) -> DatasetSplitEntry:
        entry = self.entry_for(app_package)
        if entry is None:
            raise DatasetSplitAccessError(
                f"app_package_not_assigned_to_dataset_split:{app_package}"
            )
        if entry.split == "locked_holdout" and not allow_locked_holdout:
            raise DatasetSplitAccessError(f"locked_holdout_access_denied:{app_package}")
        return entry

    def status(self, *, allow_locked_holdout: bool) -> dict[str, Any]:
        counts = {
            split: sum(entry.split == split for entry in self.entries)
            for split in sorted(ALLOWED_SPLITS)
        }
        return {
            "enabled": True,
            "manifest_version": self.manifest_version,
            "sha256": self.digest,
            "counts": counts,
            "locked_holdout_access_enabled": allow_locked_holdout,
        }
