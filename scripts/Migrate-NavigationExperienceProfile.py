from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
PROFILE_SCHEMA = ROOT / "db" / "navigation_experience_profile_v1.sqlite.sql"
PROFILE_ID = "exitguide.navigation-experience.v1"
PROFILE_VERSION = "1.0.0"
SCHEME_ID = "exitguide.goal-ontology.core-v1"
SCHEME_URI = "https://exitguide.ai/navigation/goal-schemes/core-v1"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
DEFAULT_LANGUAGE_TAG = "ko-KR"

SKOS = "http://www.w3.org/2004/02/skos/core#"
PROV = "http://www.w3.org/ns/prov#"
RLDS = "https://github.com/google-research/rlds#"
ANDROID_A11Y = (
    "https://developer.android.com/reference/android/view/accessibility/"
    "AccessibilityNodeInfo"
)
SCHEMA_BASE = "https://exitguide.ai/schemas/"

LANGUAGE_TAG_PATTERN = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")

AGENTS = {
    "human_gold": (
        "agent.human-gold-curator",
        "https://exitguide.ai/provenance/agents/human-gold-curator",
        "person",
        "Human Gold curator",
    ),
    "real_device": (
        "agent.real-device-recorder",
        "https://exitguide.ai/provenance/agents/real-device-recorder",
        "software",
        "ExitGuide real-device recorder",
    ),
    "synthetic": (
        "agent.synthetic-generator",
        "https://exitguide.ai/provenance/agents/synthetic-generator",
        "software",
        "ExitGuide synthetic-data generator",
    ),
    "model_inference": (
        "agent.model-inference",
        "https://exitguide.ai/provenance/agents/model-inference",
        "software",
        "ExitGuide model inference",
    ),
}

STANDARD_MAPPINGS = (
    ("goals", "goal_id", "W3C SKOS", f"{SKOS}notation", "exact", "Stable goal notation"),
    ("goals", "goal_id", "W3C SKOS", f"{SKOS}Concept", "exact", "Goal row is a SKOS concept"),
    ("goal_phrases", "canonical", "W3C SKOS", f"{SKOS}prefLabel", "exact", "One preferred label per goal and language"),
    ("goal_phrases", "synonym", "W3C SKOS", f"{SKOS}altLabel", "exact", "Alternative natural-language label"),
    ("goal_relations", "related", "W3C SKOS", f"{SKOS}related", "exact", "Symmetric associative relation"),
    ("goal_relations", "specialization", "W3C SKOS", f"{SKOS}broader", "close", "Direction is documented by the ExitGuide profile"),
    ("decision_cases", "screen_id", "Google RLDS", f"{RLDS}observation", "close", "Semantic screen is the step observation"),
    ("decision_cases", "chosen_action", "Google RLDS", f"{RLDS}action", "exact", "Bounded ExitGuide action"),
    ("experience_steps", "reward", "Google RLDS", f"{RLDS}reward", "exact", "Domain reward derived from progress_label"),
    ("experience_steps", "is_first", "Google RLDS", f"{RLDS}is_first", "exact", "Episode boundary flag"),
    ("experience_steps", "is_last", "Google RLDS", f"{RLDS}is_last", "exact", "Episode boundary flag"),
    ("experience_steps", "is_terminal", "Google RLDS", f"{RLDS}is_terminal", "exact", "Environment terminal, not truncation"),
    ("screen_observations", "accessibility_json", "Android SDK", ANDROID_A11Y, "close", "Normalized privacy-safe subset"),
    ("evidence_provenance", "entity_uri", "W3C PROV-O", f"{PROV}Entity", "exact", "Evidence-backed DB entity"),
    ("evidence_provenance", "generated_by_activity_id", "W3C PROV-O", f"{PROV}wasGeneratedBy", "exact", "Collection or inference activity"),
    ("evidence_provenance", "attributed_to_agent_id", "W3C PROV-O", f"{PROV}wasAttributedTo", "exact", "Responsible human or software agent"),
    ("evidence_provenance", "derived_from_ref", "W3C PROV-O", f"{PROV}wasDerivedFrom", "close", "Legacy source reference"),
    ("api_payloads", "schema", "JSON Schema", JSON_SCHEMA_DIALECT, "exact", "Portable record validation dialect"),
    ("destination_signatures", "*", "ExitGuide", "https://exitguide.ai/ns/destinationSignature", "extension", "No general navigation-memory standard"),
    ("transition_outcomes", "progress_label", "ExitGuide", "https://exitguide.ai/ns/progressLabel", "extension", "Semantic goal-distance result"),
    ("recovery_memories", "*", "ExitGuide", "https://exitguide.ai/ns/recoveryMemory", "extension", "Failure and recovery policy"),
    ("affordances", "dangerous_final", "ExitGuide", "https://exitguide.ai/ns/dangerousFinal", "extension", "Mandatory user handoff policy"),
)

RELATION_MAPPINGS = {
    "related": (f"{SKOS}related", "exact"),
    "specialization": (f"{SKOS}broader", "close"),
    "opposite": ("https://exitguide.ai/ns/oppositeGoal", "extension"),
    "prerequisite": ("https://exitguide.ai/ns/prerequisiteGoal", "extension"),
}

REWARDS = {
    "reached": 1.0,
    "advanced": 0.5,
    "unchanged": 0.0,
    "regressed": -0.5,
    "unknown": None,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rfc3339(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return utc_now()
    text = text.replace(" ", "T", 1)
    if text.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", text):
        return text
    return f"{text}+00:00"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def language_tag(value: str | None) -> str:
    candidate = str(value or DEFAULT_LANGUAGE_TAG).strip().replace("_", "-")
    return candidate if LANGUAGE_TAG_PATTERN.fullmatch(candidate) else DEFAULT_LANGUAGE_TAG


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _verify_source(connection: sqlite3.Connection) -> dict[str, str]:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) != 1:
        raise ValueError("source must be Navigation Decision DB schema version 1")
    required = {
        "navigation_db_metadata", "goals", "goal_phrases", "goal_relations",
        "screen_observations", "decision_cases", "transition_outcomes",
        "evidence_records", "evaluation_app_splits",
    }
    missing = sorted(table for table in required if not _table_exists(connection, table))
    if missing:
        raise ValueError(f"source is missing required tables: {', '.join(missing)}")
    return dict(connection.execute("SELECT key,value FROM navigation_db_metadata"))


def _seed_profile(connection: sqlite3.Connection, created_at: str) -> None:
    connection.execute(
        "INSERT INTO navigation_standard_profiles VALUES (?,?,?,?,?,?)",
        (PROFILE_ID, PROFILE_VERSION, "ExitGuide Navigation Experience Profile v1",
         JSON_SCHEMA_DIALECT, DEFAULT_LANGUAGE_TAG, created_at),
    )
    for entity, field, standard, uri, kind, notes in STANDARD_MAPPINGS:
        connection.execute(
            "INSERT INTO standard_term_mappings VALUES (?,?,?,?,?,?,?)",
            (stable_id("map", entity, field, uri), entity, field, standard, uri, kind, notes),
        )


def _seed_skos(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO goal_concept_schemes VALUES (?,?,?,?,?)",
        (SCHEME_ID, SCHEME_URI, "ExitGuide Core Navigation Goals", "1.0.0", DEFAULT_LANGUAGE_TAG),
    )
    for row in connection.execute("SELECT goal_id,active FROM goals ORDER BY goal_id").fetchall():
        goal_id = str(row["goal_id"])
        connection.execute(
            "INSERT INTO goal_standard_concepts VALUES (?,?,?,?,?)",
            (goal_id, SCHEME_ID,
             f"https://exitguide.ai/navigation/goals/{quote(goal_id, safe='')}",
             goal_id, "active" if int(row["active"]) else "deprecated"),
        )
    phrase_rows = connection.execute(
        """
        SELECT phrase_id,goal_id,locale,phrase,phrase_kind,confidence
        FROM goal_phrases
        ORDER BY goal_id,locale,confidence DESC,length(phrase),phrase,phrase_id
        """
    ).fetchall()
    preferred_groups: set[tuple[str, str]] = set()
    for row in phrase_rows:
        kind = str(row["phrase_kind"])
        group = (str(row["goal_id"]), language_tag(row["locale"]))
        if kind in {"canonical", "synonym"} and group not in preferred_groups:
            property_uri, mapping_kind = f"{SKOS}prefLabel", "exact"
            preferred_groups.add(group)
        elif kind in {"canonical", "synonym"}:
            property_uri, mapping_kind = f"{SKOS}altLabel", "exact"
        else:
            property_uri = f"https://exitguide.ai/ns/{quote(kind, safe='')}Label"
            mapping_kind = "extension"
        connection.execute(
            "INSERT INTO goal_label_mappings VALUES (?,?,?,?)",
            (row["phrase_id"], property_uri, language_tag(row["locale"]), mapping_kind),
        )
    for row in connection.execute(
        "SELECT source_goal_id,target_goal_id,relation_type FROM goal_relations"
    ).fetchall():
        predicate_uri, mapping_kind = RELATION_MAPPINGS[str(row["relation_type"])]
        connection.execute(
            "INSERT INTO goal_relation_mappings VALUES (?,?,?,?,?)",
            (row["source_goal_id"], row["target_goal_id"], row["relation_type"],
             predicate_uri, mapping_kind),
        )


def _seed_observation_contracts(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT observation_id,accessibility_json FROM screen_observations"
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(str(row["accessibility_json"] or "{}"))
        except json.JSONDecodeError:
            payload = {}
        profile = (
            "android_accessibility_node_subset_v1"
            if isinstance(payload, dict) and isinstance(payload.get("elements"), list)
            else "not_available"
        )
        connection.execute(
            "INSERT INTO observation_contracts VALUES (?,?,?,?,?,?)",
            (
                row["observation_id"],
                f"{SCHEMA_BASE}android-accessibility-observation.v1.schema.json",
                profile,
                f"{SCHEMA_BASE}ocr-observation.v1.schema.json",
                f"{SCHEMA_BASE}vlm-observation.v1.schema.json",
                "semantic-redaction-v1",
            ),
        )


def _episode_rows(connection: sqlite3.Connection) -> dict[tuple[str, str], list[sqlite3.Row]]:
    rows = connection.execute(
        """
        SELECT c.*, o.outcome_type, o.connectivity_status, o.progress_label,
               o.observed_at AS outcome_observed_at,
               COALESCE((
                   SELECT so.locale FROM screen_observations AS so
                   WHERE so.screen_id=c.screen_id
                     AND so.app_package=c.source_app_package
                   ORDER BY so.captured_at DESC LIMIT 1
               ), 'ko-KR') AS locale,
               COALESCE((
                   SELECT so.app_version FROM screen_observations AS so
                   WHERE so.screen_id=c.screen_id
                     AND so.app_package=c.source_app_package
                   ORDER BY so.captured_at DESC LIMIT 1
               ), '') AS app_version,
               COALESCE((
                   SELECT es.split FROM evaluation_app_splits AS es
                   WHERE es.app_package=c.source_app_package
                     AND es.split_version='app-disjoint-v1'
               ), 'unassigned') AS app_split
        FROM decision_cases AS c
        LEFT JOIN transition_outcomes AS o ON o.case_id=c.case_id
        ORDER BY c.source_type,c.source_record_id,c.source_step_ordinal
        """
    ).fetchall()
    grouped: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["source_type"]), str(row["source_record_id"]))].append(row)
    return grouped


def _end_reason(rows: list[sqlite3.Row]) -> str:
    last = rows[-1]
    if str(last["chosen_action"]) == "stop_for_user":
        return "user_handoff"
    if any(str(row["outcome_type"]) == "destination_reached" for row in rows):
        return "destination_reached"
    if str(last["connectivity_status"] or "") != "observed":
        return "truncated"
    if str(last["progress_label"] or "") in {"unchanged", "regressed"}:
        return "failed"
    return "unknown"


def _seed_rlds(connection: sqlite3.Connection) -> None:
    for (source_type, source_record_id), rows in _episode_rows(connection).items():
        first, last = rows[0], rows[-1]
        episode_id = stable_id("episode", source_type, source_record_id)
        reason = _end_reason(rows)
        metadata = json.dumps(
            {"legacy_source_record_id": source_record_id, "profile": PROFILE_ID},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        connection.execute(
            """
            INSERT INTO experience_episodes(
                episode_id,goal_id,source_type,source_record_id,source_app_package,
                app_version,language_tag,split_version,split,started_at,ended_at,
                end_reason,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                episode_id, first["goal_id"], source_type, source_record_id,
                first["source_app_package"], str(first["app_version"] or ""),
                language_tag(first["locale"]), "app-disjoint-v1", first["app_split"],
                rfc3339(first["observed_at"]),
                rfc3339(last["outcome_observed_at"] or last["observed_at"]), reason, metadata,
            ),
        )
        for index, row in enumerate(rows):
            is_first = int(index == 0)
            is_last = int(index == len(rows) - 1)
            is_terminal = int(is_last and reason == "destination_reached")
            reward = REWARDS.get(str(row["progress_label"] or "unknown"))
            discount = 0.0 if is_terminal else 1.0
            connection.execute(
                "INSERT INTO experience_steps VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    row["case_id"], episode_id, int(row["source_step_ordinal"]),
                    is_first, is_last, is_terminal, reward, discount,
                    "exitguide_progress_v1", "{}",
                ),
            )


def _seed_provenance(connection: sqlite3.Connection) -> None:
    for agent_id, agent_uri, agent_type, name in AGENTS.values():
        connection.execute(
            "INSERT INTO provenance_agents VALUES (?,?,?,?)",
            (agent_id, agent_uri, agent_type, name),
        )
    evidence_rows = connection.execute(
        "SELECT * FROM evidence_records ORDER BY source_type,source_ref,evidence_id"
    ).fetchall()
    activities: dict[tuple[str, str], str] = {}
    for row in evidence_rows:
        source_type = str(row["source_type"])
        source_ref = str(row["source_ref"])
        key = (source_type, source_ref)
        agent_id = AGENTS[source_type][0]
        activity_id = activities.get(key)
        if activity_id is None:
            activity_id = stable_id("activity", source_type, source_ref)
            activities[key] = activity_id
            generated_at = rfc3339(row["last_verified_at"])
            attributes = json.dumps(
                {"app_package": row["app_package"], "app_version": row["app_version"],
                 "language_tag": language_tag(row["locale"])},
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
            connection.execute(
                "INSERT INTO provenance_activities VALUES (?,?,?,?,?,?,?,?)",
                (
                    activity_id,
                    f"https://exitguide.ai/provenance/activities/{quote(activity_id, safe='')}",
                    f"collection.{source_type}", agent_id, source_ref,
                    generated_at, generated_at, attributes,
                ),
            )
        entity_uri = (
            "https://exitguide.ai/navigation/entities/"
            f"{quote(str(row['entity_type']), safe='')}/{quote(str(row['entity_id']), safe='')}"
        )
        connection.execute(
            "INSERT INTO evidence_provenance VALUES (?,?,?,?,?,?)",
            (
                row["evidence_id"], entity_uri, activity_id, agent_id, source_ref,
                rfc3339(row["last_verified_at"]),
            ),
        )


def migrate(source: Path, target: Path) -> dict[str, object]:
    source = source.resolve()
    target = target.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing target: {target}")
    if source == target:
        raise ValueError("source and target must be different files")
    target.parent.mkdir(parents=True, exist_ok=True)
    source_hash = file_sha256(source)
    created_target = False
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    source_connection.row_factory = sqlite3.Row
    try:
        source_metadata = _verify_source(source_connection)
        target_connection = sqlite3.connect(target)
        created_target = True
        try:
            source_connection.backup(target_connection)
            target_connection.row_factory = sqlite3.Row
            target_connection.execute("PRAGMA foreign_keys = ON")
            if target_connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("copied v1 database failed SQLite quick_check")
            target_connection.executescript(PROFILE_SCHEMA.read_text(encoding="utf-8"))
            created_at = utc_now()
            with target_connection:
                _seed_profile(target_connection, created_at)
                _seed_skos(target_connection)
                _seed_observation_contracts(target_connection)
                _seed_rlds(target_connection)
                _seed_provenance(target_connection)
                metadata = {
                    "schema_version": "2",
                    "standards_profile": PROFILE_ID,
                    "standards_profile_version": PROFILE_VERSION,
                    "profile_source_sha256": source_hash,
                    "upstream_legacy_source_sha256": source_metadata.get("source_sha256", ""),
                    "json_schema_dialect": JSON_SCHEMA_DIALECT,
                    "transform_version": "navigation-experience-profile-migration-v1",
                    "profile_created_at": created_at,
                }
                target_connection.executemany(
                    """
                    INSERT INTO navigation_db_metadata(key,value) VALUES (?,?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value
                    """,
                    metadata.items(),
                )
            if target_connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("profile migration created foreign-key violations")
            if target_connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("profile database failed SQLite quick_check")
            counts = {
                table: int(target_connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in (
                    "goals", "goal_standard_concepts", "goal_label_mappings",
                    "screen_observations", "observation_contracts", "decision_cases",
                    "experience_episodes", "experience_steps", "evidence_records",
                    "evidence_provenance", "provenance_activities",
                )
            }
        finally:
            target_connection.close()
    except Exception:
        source_connection.close()
        if created_target and target.exists():
            target.unlink()
        raise
    else:
        source_connection.close()
    return {
        "profile_id": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "schema_version": 2,
        "source": {"path": str(source), "sha256": source_hash, "read_only": True},
        "target": {"path": str(target), "sha256": file_sha256(target), "bytes": target.stat().st_size},
        "counts": counts,
        "source_preserved": file_sha256(source) == source_hash,
        "generated_at": utc_now(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add ExitGuide Navigation Experience Profile v1 to a copied Decision DB v1"
    )
    parser.add_argument("--source", type=Path, required=True, help="read-only Navigation Decision DB v1")
    parser.add_argument("--target", type=Path, required=True, help="new schema-version-2 SQLite file")
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = migrate(args.source, args.target)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
