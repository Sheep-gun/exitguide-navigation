from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
import sys

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_review import NavigationReviewStore  # noqa: E402
from app.services.navigation_runtime_store import NavigationRuntimeStore  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_status(path: Path, metadata_table: str) -> dict[str, Any]:
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as connection:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign_key_errors = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        metadata = dict(connection.execute(f"SELECT key,value FROM {metadata_table}"))
    if quick_check != "ok" or foreign_key_errors:
        raise ValueError(
            f"SQLite integrity failure: {path} quick_check={quick_check} "
            f"foreign_key_errors={foreign_key_errors}"
        )
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "byte_size": path.stat().st_size,
        "user_version": user_version,
        "schema_version": metadata.get("schema_version"),
        "quick_check": quick_check,
        "foreign_key_errors": foreign_key_errors,
    }


def prepare_generation(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir.expanduser().resolve()
    plan_path = args.plan.expanduser().resolve()
    if not plan_path.is_file():
        raise FileNotFoundError(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if output_dir.exists():
        manifest_path = output_dir / "manifest.json"
        if not manifest_path.is_file():
            raise FileExistsError(f"generation directory exists without manifest: {output_dir}")
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("generation_id") != args.generation_id:
            raise FileExistsError(f"generation id conflict: {output_dir}")
        return existing

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent)
    )
    try:
        runtime_path = temporary / "navigation-runtime-v1.sqlite"
        review_path = temporary / "navigation-human-review-v1.sqlite"
        screen_artifact_dir = temporary / "screen-artifacts"
        screen_artifact_dir.mkdir()
        NavigationRuntimeStore(
            runtime_path,
            server_release_id=args.server_release_id,
            screen_artifact_dir=screen_artifact_dir,
        )
        NavigationReviewStore(runtime_path, review_path)

        final_runtime = output_dir / runtime_path.name
        final_review = output_dir / review_path.name
        final_artifacts = output_dir / screen_artifact_dir.name
        environment = "\n".join(
            (
                f"NAVIGATION_RUNTIME_DB_PATH={final_runtime}",
                f"NAVIGATION_REVIEW_DB_PATH={final_review}",
                f"NAVIGATION_SCREEN_ARTIFACT_DIR={final_artifacts}",
                f"NAVIGATION_SERVER_RELEASE_ID={args.server_release_id}",
                "",
            )
        )
        (temporary / "navigation-runtime-generation.env").write_text(
            environment,
            encoding="utf-8",
        )

        manifest = {
            "schema_version": "navigation-runtime-generation.v1",
            "generation_id": args.generation_id,
            "status": "prepared",
            "created_at": now(),
            "source_code_commit": args.source_code_commit,
            "server_release_id": args.server_release_id,
            "base_snapshot": args.base_snapshot,
            "recollection_plan": {
                "path": str(plan_path),
                "sha256": file_sha256(plan_path),
                "schema_version": plan.get("schema_version"),
                "strict_completion_blockers": len(
                    plan.get("strict_completion_blockers", [])
                ),
            },
            "policy": {
                "append_only_runtime": True,
                "runtime_and_review_separate": True,
                "previous_generation_mutation_allowed": False,
                "direct_runtime_to_decision_allowed": False,
                "credentials_collected": False,
                "dangerous_final_action_auto_execution": False,
                "activation_status": "not_activated",
            },
            "runtime": sqlite_status(
                runtime_path,
                "navigation_runtime_metadata",
            ),
            "review": sqlite_status(
                review_path,
                "navigation_review_metadata",
            ),
            "environment_file": {
                "path": str(output_dir / "navigation-runtime-generation.env"),
                "sha256": file_sha256(
                    temporary / "navigation-runtime-generation.env"
                ),
            },
        }
        # Paths in the integrity records describe their final immutable
        # generation location rather than the temporary build directory.
        manifest["runtime"]["path"] = str(final_runtime)
        manifest["review"]["path"] = str(final_review)
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_dir)
        if os.name != "nt":
            output_dir.chmod(0o750)
            final_artifacts.chmod(0o750)
            final_runtime.chmod(0o660)
            final_review.chmod(0o660)
            (output_dir / "navigation-runtime-generation.env").chmod(0o640)
            (output_dir / "manifest.json").chmod(0o440)
        manifest["generation_dir"] = str(output_dir)
        return manifest
    except Exception:
        if temporary.exists() and temporary.parent == output_dir.parent:
            shutil.rmtree(temporary)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Prepare an isolated Runtime/Review generation without activating it"
    )
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--generation-id", required=True)
    result.add_argument("--base-snapshot", required=True)
    result.add_argument("--plan", type=Path, required=True)
    result.add_argument("--source-code-commit", required=True)
    result.add_argument("--server-release-id", required=True)
    return result


if __name__ == "__main__":
    print(
        json.dumps(
            prepare_generation(parser().parse_args()),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
