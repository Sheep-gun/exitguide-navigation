#!/usr/bin/env bash
set -euo pipefail

ROOT="${EXITGUIDE_PUBLIC_ROOT:-/home/exitnav/workspace/universal-navigation-api}"
API_PORT="${EXITGUIDE_PUBLIC_API_PORT:-8100}"
INCOMING="$ROOT/incoming"
ARCHIVE="$INCOMING/source.tar.gz"
RUNTIME_ENV="$INCOMING/runtime.env"
INSTALLER="$INCOMING/install-public-api.sh"
RELEASES="$ROOT/releases"
RUNTIME="$ROOT/runtime"
LOGS="$ROOT/logs"
BIN="$ROOT/bin"
VENV="$ROOT/venv"
CURRENT="$ROOT/current"
API_SESSION="exitnav-public-api"
TUNNEL_SESSION="exitnav-public-tunnel"
API_LOG="$LOGS/api.log"
TUNNEL_LOG="$LOGS/cloudflared.log"
CLOUDFLARED="$BIN/cloudflared"
PRESERVE_TUNNEL="${EXITGUIDE_PRESERVE_TUNNEL:-0}"

case "$ROOT" in
  /home/exitnav/workspace/*) ;;
  *)
    echo "Refusing public API root outside /home/exitnav/workspace" >&2
    exit 1
    ;;
esac

for required in "$ARCHIVE" "$RUNTIME_ENV" "$INSTALLER"; do
  if [[ ! -f "$required" ]]; then
    echo "Missing deployment input: $required" >&2
    exit 1
  fi
done

for command_name in python3 curl tar tmux; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command is unavailable: $command_name" >&2
    exit 1
  fi
done

mkdir -p "$RELEASES" "$RUNTIME" "$LOGS" "$BIN" "$ROOT/data"
release_id="$(date -u +%Y%m%dT%H%M%SZ)"
release_dir="$RELEASES/$release_id"
mkdir -p "$release_dir"
tar -xf "$ARCHIVE" -C "$release_dir"
install -m 600 "$RUNTIME_ENV" "$release_dir/.env"

if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check -q -r "$release_dir/apps/api/requirements.txt"

ln -sfn "$release_dir" "$CURRENT"

if [[ ! -x "$CLOUDFLARED" ]]; then
  tmp_binary="$BIN/cloudflared.download"
  curl -fsSL --retry 3 \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o "$tmp_binary"
  chmod 755 "$tmp_binary"
  "$tmp_binary" --version >/dev/null
  mv "$tmp_binary" "$CLOUDFLARED"
fi

tmux kill-session -t "$API_SESSION" 2>/dev/null || true
: >"$API_LOG"
tmux new-session -d -s "$API_SESSION" \
  "cd '$CURRENT' && exec '$VENV/bin/python' -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port '$API_PORT' >>'$API_LOG' 2>&1"

api_ready=false
api_ready_timeout_seconds="${EXITGUIDE_API_READY_TIMEOUT_SECONDS:-600}"
if [[ ! "$api_ready_timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
  echo "EXITGUIDE_API_READY_TIMEOUT_SECONDS must be a positive integer." >&2
  exit 1
fi
for _ in $(seq 1 "$api_ready_timeout_seconds"); do
  if curl -fsS --max-time 2 "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
    api_ready=true
    break
  fi
  sleep 1
done
if [[ "$api_ready" != true ]]; then
  echo "Navigation API did not become ready. See $API_LOG" >&2
  exit 1
fi

public_url=""
if [[ "$PRESERVE_TUNNEL" == "1" ]] \
  && tmux has-session -t "$TUNNEL_SESSION" 2>/dev/null \
  && [[ -s "$RUNTIME/public-url.txt" ]]; then
  public_url="$(tr -d '\r\n' <"$RUNTIME/public-url.txt")"
  if [[ -z "$public_url" ]] || ! curl -fsS --max-time 5 "$public_url/health" >/dev/null 2>&1; then
    public_url=""
  fi
fi

if [[ -z "$public_url" ]]; then
  tmux kill-session -t "$TUNNEL_SESSION" 2>/dev/null || true
  : >"$TUNNEL_LOG"
  tmux new-session -d -s "$TUNNEL_SESSION" \
    "exec '$CLOUDFLARED' tunnel --no-autoupdate --url 'http://127.0.0.1:$API_PORT' >>'$TUNNEL_LOG' 2>&1"

  for _ in $(seq 1 60); do
    public_url="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | tail -1 || true)"
    if [[ -n "$public_url" ]] && curl -fsS --max-time 5 "$public_url/health" >/dev/null 2>&1; then
      break
    fi
    public_url=""
    sleep 1
  done
fi
if [[ -z "$public_url" ]]; then
  echo "Public HTTPS tunnel did not become ready. See $TUNNEL_LOG" >&2
  exit 1
fi

printf '%s\n' "$public_url" >"$RUNTIME/public-url.txt"
chmod 644 "$RUNTIME/public-url.txt"

echo "PUBLIC_API_URL=$public_url"
echo "API_SESSION=$API_SESSION"
echo "TUNNEL_SESSION=$TUNNEL_SESSION"
echo "RELEASE_ID=$release_id"
