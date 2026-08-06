#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 GENERATION_DIR EXPECTED_OLD_RUNTIME_SHA256 EXPECTED_OLD_REVIEW_SHA256" >&2
  exit 2
fi

generation_dir="$(readlink -f "$1")"
expected_old_runtime_sha="$2"
expected_old_review_sha="$3"
generation_root="$(readlink -f /srv/exitguide/runtime/navigation-collection-generations)"
active_env=/srv/exitguide/runtime/navigation-runtime-coverage-v2.env
service=exitguide-navigation-api.service

case "$generation_dir" in
  "$generation_root"/*) ;;
  *) echo "generation path escapes the allowed root: $generation_dir" >&2; exit 2 ;;
esac

manifest="$generation_dir/manifest.json"
generation_env="$generation_dir/navigation-runtime-generation.env"
runtime_db="$generation_dir/navigation-runtime-v1.sqlite"
review_db="$generation_dir/navigation-human-review-v1.sqlite"
for required in "$manifest" "$generation_env" "$runtime_db" "$review_db" "$active_env"; do
  [[ -f "$required" ]] || { echo "missing required file: $required" >&2; exit 2; }
done

python3 - "$manifest" "$runtime_db" "$review_db" <<'PY'
import json,sqlite3,sys
manifest_path,runtime_path,review_path=sys.argv[1:]
manifest=json.load(open(manifest_path,encoding='utf-8'))
assert manifest['status']=='prepared'
assert manifest['policy']['activation_status']=='not_activated'
for path,table in ((runtime_path,'navigation_sessions'),(review_path,'navigation_human_reviews')):
    connection=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
    assert connection.execute('pragma quick_check').fetchone()[0]=='ok'
    assert not connection.execute('pragma foreign_key_check').fetchall()
    assert connection.execute('select count(*) from '+table).fetchone()[0]==0
    connection.close()
PY

old_runtime_db="$(awk -F= '$1=="NAVIGATION_RUNTIME_DB_PATH" {print substr($0,index($0,"=")+1)}' "$active_env" | tail -1)"
old_review_db="$(awk -F= '$1=="NAVIGATION_REVIEW_DB_PATH" {print substr($0,index($0,"=")+1)}' "$active_env" | tail -1)"
[[ -n "$old_runtime_db" ]] || { echo "active Runtime path is missing" >&2; exit 2; }
if [[ -z "$old_review_db" ]]; then
  old_review_db="$(dirname "$old_runtime_db")/navigation-human-review-v1.sqlite"
fi
old_runtime_db="$(readlink -f "$old_runtime_db")"
old_review_db="$(readlink -f "$old_review_db")"
[[ -f "$old_runtime_db" && -f "$old_review_db" ]] || {
  echo "active Runtime or Review DB is missing" >&2
  exit 2
}

actual_old_runtime_sha="$(sha256sum "$old_runtime_db" | awk '{print $1}')"
actual_old_review_sha="$(sha256sum "$old_review_db" | awk '{print $1}')"
[[ "$actual_old_runtime_sha" == "$expected_old_runtime_sha" ]] || {
  echo "active Runtime hash changed: $actual_old_runtime_sha" >&2
  exit 3
}
[[ "$actual_old_review_sha" == "$expected_old_review_sha" ]] || {
  echo "active Review hash changed: $actual_old_review_sha" >&2
  exit 3
}

active_sessions="$(sqlite3 "$old_runtime_db" "select count(*) from navigation_sessions where status='active';")"
[[ "$active_sessions" == 0 ]] || {
  echo "cannot roll over with active Runtime sessions: $active_sessions" >&2
  exit 3
}

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_env="/srv/exitguide/runtime/backups/navigation-runtime-coverage-v2-pre-${timestamp}.env"
archive_dir="/srv/exitguide/runtime/collection-generations/frozen-${timestamp}"
mkdir -p "$(dirname "$backup_env")" "$archive_dir"
cp -p "$active_env" "$backup_env"

rollback() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    install -o exitguide -g exitguide-admin -m 0640 "$backup_env" "$active_env" || true
    chmod 0640 "$old_runtime_db" "$old_review_db" || true
    sudo systemctl restart "$service" || true
  fi
  exit "$rc"
}
trap rollback EXIT

sudo systemctl stop "$service"
post_stop_runtime_sha="$(sha256sum "$old_runtime_db" | awk '{print $1}')"
post_stop_review_sha="$(sha256sum "$old_review_db" | awk '{print $1}')"
[[ "$post_stop_runtime_sha" == "$expected_old_runtime_sha" ]] || {
  echo "Runtime changed during rollover: $post_stop_runtime_sha" >&2
  exit 3
}
[[ "$post_stop_review_sha" == "$expected_old_review_sha" ]] || {
  echo "Review changed during rollover: $post_stop_review_sha" >&2
  exit 3
}
post_stop_active_sessions="$(sqlite3 "$old_runtime_db" "select count(*) from navigation_sessions where status='active';")"
[[ "$post_stop_active_sessions" == 0 ]] || {
  echo "Runtime gained an active session during rollover: $post_stop_active_sessions" >&2
  exit 3
}
sqlite3 "$old_runtime_db" "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 "$old_review_db" "PRAGMA wal_checkpoint(TRUNCATE);"
checkpointed_runtime_sha="$(sha256sum "$old_runtime_db" | awk '{print $1}')"
checkpointed_review_sha="$(sha256sum "$old_review_db" | awk '{print $1}')"
[[ "$checkpointed_runtime_sha" == "$expected_old_runtime_sha" ]] || {
  echo "checkpoint revealed Runtime data outside the frozen hash: $checkpointed_runtime_sha" >&2
  exit 3
}
[[ "$checkpointed_review_sha" == "$expected_old_review_sha" ]] || {
  echo "checkpoint revealed Review data outside the frozen hash: $checkpointed_review_sha" >&2
  exit 3
}
sqlite3 "$old_runtime_db" ".backup '$archive_dir/navigation-runtime-v1.sqlite'"
sqlite3 "$old_review_db" ".backup '$archive_dir/navigation-human-review-v1.sqlite'"
cp -p "$active_env" "$archive_dir/previous-active.env"

install -o exitguide -g exitguide-admin -m 0640 "$generation_env" "$active_env"
sudo systemctl start "$service"

health_json=""
for _ in $(seq 1 30); do
  if health_json="$(curl -fsS http://100.77.172.25:8100/health 2>/dev/null)"; then
    break
  fi
  sleep 1
done
[[ -n "$health_json" ]] || {
  echo "Navigation API did not become healthy within 30 seconds" >&2
  exit 4
}
status_json="$(curl -fsS http://100.77.172.25:8100/v1/navigation/status)"
review_json="$(curl -fsS 'http://100.77.172.25:8100/v1/navigation/review/status?reviewer=codex-yanggeon')"
python3 - "$health_json" "$status_json" "$review_json" <<'PY'
import json,sys
health,status,review=map(json.loads,sys.argv[1:])
assert health=={'status':'ok','service':'exitguide-navigation'}
assert status['ready'] is True
assert status['runtime_db']['schema_version']==5
assert status['runtime_db']['sessions']==0
assert status['runtime_db']['decisions']==0
assert status['runtime_db']['observations']==0
assert review['ready'] is True
assert review['source_read_only'] is True
assert review['counts']['sessions']==0
assert review['counts']['decisions']==0
assert review['counts']['reviewed']==0
PY

chmod 0440 "$old_runtime_db" "$old_review_db"
chmod 0440 "$archive_dir/navigation-runtime-v1.sqlite" "$archive_dir/navigation-human-review-v1.sqlite" "$archive_dir/previous-active.env"
chmod 0550 "$archive_dir"

export generation_dir timestamp backup_env archive_dir old_runtime_db old_review_db
export actual_old_runtime_sha actual_old_review_sha runtime_db review_db
python3 - <<'PY'
import hashlib,json,os,pathlib
def sha(path):
    digest=hashlib.sha256()
    with open(path,'rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()
receipt={
  'schema_version':'navigation-runtime-generation-activation.v1',
  'status':'active',
  'generation_dir':os.environ['generation_dir'],
  'activated_at':os.environ['timestamp'],
  'previous_environment_backup':os.environ['backup_env'],
  'previous_generation_archive':{
    'path':os.environ['archive_dir'],
    'runtime_sha256':sha(os.path.join(os.environ['archive_dir'],'navigation-runtime-v1.sqlite')),
    'review_sha256':sha(os.path.join(os.environ['archive_dir'],'navigation-human-review-v1.sqlite')),
    'verification_mode':'sqlite immutable read-only',
  },
  'previous_runtime':{'path':os.environ['old_runtime_db'],'sha256':os.environ['actual_old_runtime_sha']},
  'previous_review':{'path':os.environ['old_review_db'],'sha256':os.environ['actual_old_review_sha']},
  'active_runtime':{'path':os.environ['runtime_db'],'sha256':sha(os.environ['runtime_db'])},
  'active_review':{'path':os.environ['review_db'],'sha256':sha(os.environ['review_db'])},
  'health':'passed',
  'runtime_counts':{'sessions':0,'decisions':0,'observations':0},
  'review_counts':{'reviewed':0},
}
path=pathlib.Path(os.environ['generation_dir'])/'activation-receipt.json'
path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
path.chmod(0o440)
print(json.dumps(receipt,ensure_ascii=False,sort_keys=True))
PY
chgrp exitguide-admin "$generation_dir/activation-receipt.json"

trap - EXIT
