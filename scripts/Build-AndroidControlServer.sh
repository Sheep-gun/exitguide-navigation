#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${EXITGUIDE_NAV_ROOT:-/home/exitnav/workspace/universal-navigation-api}"
RELEASE="${EXITGUIDE_NAV_RELEASE:-$ROOT/current}"
RAW="${ANDROID_CONTROL_RAW_DIR:-$ROOT/.artifacts/android-control/raw}"
OUTPUT="${ANDROID_CONTROL_INDEX_PATH:-$ROOT/.artifacts/android-control/navigation-examples.sqlite}"
PYTHON="${EXITGUIDE_NAV_PYTHON:-$ROOT/venv/bin/python}"

test -x "$PYTHON"
test -d "$RAW"
test -f "$RELEASE/scripts/Build-AndroidControlIndex.py"

partial_count=$(find "$RAW" -maxdepth 1 -type f -name '*.part' | wc -l)
shard_count=$(find "$RAW" -maxdepth 1 -type f -name 'android_control-*' ! -name '*.part' | wc -l)
if [[ "$partial_count" -ne 0 || "$shard_count" -ne 20 ]]; then
  echo "AndroidControl download is incomplete: shards=$shard_count partials=$partial_count" >&2
  exit 2
fi

mkdir -p "$(dirname "$OUTPUT")"
temporary="$OUTPUT.building"
rm -f "$temporary" "$temporary-shm" "$temporary-wal"

cd "$RELEASE"
PYTHONPATH=apps/api "$PYTHON" scripts/Build-AndroidControlIndex.py \
  --input "$RAW" \
  --format official-tfrecord \
  --source-split official \
  --output "$temporary"

PYTHONPATH=apps/api "$PYTHON" scripts/Build-AndroidControlSemanticVectors.py \
  --index "$temporary"

"$PYTHON" - "$temporary" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
connection = sqlite3.connect(path)
try:
    count = int(connection.execute("SELECT COUNT(*) FROM android_control_steps").fetchone()[0])
    episodes = int(connection.execute("SELECT COUNT(DISTINCT episode_id) FROM android_control_steps").fetchone()[0])
    vectors = int(connection.execute(
        "SELECT COUNT(*) FROM android_control_steps WHERE length(semantic_vector) > 0"
    ).fetchone()[0])
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
finally:
    connection.close()
if count <= 0 or episodes <= 0 or vectors != count or integrity != "ok":
    raise SystemExit(
        f"invalid AndroidControl index: records={count} episodes={episodes} "
        f"vectors={vectors} integrity={integrity}"
    )
print(
    f"verified AndroidControl index: records={count} episodes={episodes} "
    f"vectors={vectors} integrity={integrity}"
)
PY

mv -f "$temporary" "$OUTPUT"
sha256sum "$OUTPUT" > "$OUTPUT.sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUTPUT.built-at"
echo "AndroidControl index ready: $OUTPUT"
