#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 CODE_WORKTREE VENV_DIR" >&2
  exit 2
fi

code_dir=$(readlink -f "$1")
venv_dir=$(readlink -f "$2")
runtime_root=/home/kyle/exitguide/runtime
runtime_db=$runtime_root/navigation-runtime-v1.sqlite
service_name=exitguide-navigation-api.service
service_file=$code_dir/deploy/n100/exitguide-navigation-api.service
code_link=$runtime_root/navigation-api-current-code
venv_link=$runtime_root/navigation-api-current-venv

case "$code_dir" in
  /home/kyle/exitguide/worktrees/navigation-collector-*) ;;
  *) echo "refusing unexpected code worktree: $code_dir" >&2; exit 2 ;;
esac
case "$venv_dir" in
  /home/kyle/exitguide/runtime/navigation-api-venv-*) ;;
  *) echo "refusing unexpected venv: $venv_dir" >&2; exit 2 ;;
esac

test -f "$service_file"
test -x "$venv_dir/bin/python"
test -x "$venv_dir/bin/uvicorn"
test -f "$runtime_db"

terms_before=$(
  curl -fsS --max-time 10 http://127.0.0.1:8010/v1/rag/status |
    "$venv_dir/bin/python" -c 'import json,sys; print(json.load(sys.stdin).get("ready"))'
)
test "$terms_before" = True

install -d -m 2770 "$runtime_root/backups" "$runtime_root/tmp"
stamp=$(date +%Y%m%d-%H%M%S)
runtime_backup=$runtime_root/backups/navigation-runtime-v1.pre-v3-$stamp.sqlite
unit_backup=$runtime_root/backups/$service_name.pre-collector-$stamp
migration_test=$runtime_root/tmp/navigation-runtime-v3-migration-test-$stamp.sqlite

RUNTIME_DB="$runtime_db" RUNTIME_BACKUP="$runtime_backup" "$venv_dir/bin/python" <<'PY'
import os
import sqlite3

source = sqlite3.connect(os.environ["RUNTIME_DB"])
target = sqlite3.connect(os.environ["RUNTIME_BACKUP"])
source.backup(target)
assert target.execute("PRAGMA quick_check").fetchone()[0] == "ok"
target.close()
source.close()
PY

cp --preserve=mode,timestamps "$runtime_backup" "$migration_test"
PYTHONPATH="$code_dir/apps/api" MIGRATION_TEST="$migration_test" "$venv_dir/bin/python" <<'PY'
import os
from app.services.navigation_runtime_store import NavigationRuntimeStore

status = NavigationRuntimeStore(os.environ["MIGRATION_TEST"]).status()
assert status["ready"] is True
assert status["schema_version"] == 3
print("migration_copy_status", status)
PY

sudo cp --preserve=mode,timestamps /etc/systemd/system/$service_name "$unit_backup"
old_code_target=$(readlink "$code_link" 2>/dev/null || true)
old_venv_target=$(readlink "$venv_link" 2>/dev/null || true)

swap_link() {
  local target=$1
  local link=$2
  local next=$link.next
  rm -f "$next"
  ln -s "$target" "$next"
  mv -Tf "$next" "$link"
}

restore_link() {
  local old_target=$1
  local link=$2
  if [[ -n "$old_target" ]]; then
    swap_link "$old_target" "$link"
  else
    rm -f "$link"
  fi
}

rollback() {
  echo "deployment failed; restoring previous service and runtime DB" >&2
  sudo systemctl stop "$service_name" || true
  sudo install -m 0644 "$unit_backup" /etc/systemd/system/$service_name
  cp --preserve=mode,timestamps "$runtime_backup" "$runtime_db"
  restore_link "$old_code_target" "$code_link"
  restore_link "$old_venv_target" "$venv_link"
  sudo systemctl daemon-reload
  sudo systemctl restart "$service_name" || true
}
trap rollback ERR

swap_link "$code_dir" "$code_link"
swap_link "$venv_dir" "$venv_link"
sudo install -m 0644 "$service_file" /etc/systemd/system/$service_name
sudo systemctl daemon-reload
sudo systemctl restart "$service_name"

for _ in $(seq 1 20); do
  if curl -fsS --max-time 5 http://100.77.172.25:8100/health >/dev/null; then
    break
  fi
  sleep 1
done

status_json=$(curl -fsS --max-time 10 http://100.77.172.25:8100/v1/navigation/status)
STATUS_JSON="$status_json" "$venv_dir/bin/python" <<'PY'
import json
import os

status = json.loads(os.environ["STATUS_JSON"])
assert status["ready"] is True
assert status["research_models_ready"] is True
assert status["runtime_db"]["schema_version"] == 3
assert status["dataset_split"]["enabled"] is True
assert status["dataset_split"]["counts"]["locked_holdout"] >= 3
assert status["dataset_split"]["locked_holdout_access_enabled"] is False
print("navigation_status", json.dumps(status, ensure_ascii=False, sort_keys=True))
PY

terms_after=$(
  curl -fsS --max-time 10 http://127.0.0.1:8010/v1/rag/status |
    "$venv_dir/bin/python" -c 'import json,sys; print(json.load(sys.stdin).get("ready"))'
)
test "$terms_after" = True

trap - ERR
echo "navigation collector deployed"
echo "runtime backup: $runtime_backup"
