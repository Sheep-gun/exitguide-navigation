#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="$repo_root/.artifacts/android-control/raw"
parallel=4
download_all=0
declare -a shards=()

usage() {
  cat <<'EOF'
Usage: scripts/Get-AndroidControl.sh [--all] [--shard N] [--parallel N] [--destination PATH]

Downloads Google Research AndroidControl metadata and optionally one or all
official GZIP TFRecord shards. Partial files are resumable and final files are
recorded in manifest.sha256 and manifest.sizes.tsv.
EOF
}

while (($#)); do
  case "$1" in
    --all)
      download_all=1
      shift
      ;;
    --shard)
      [[ $# -ge 2 ]] || { echo "--shard requires a value" >&2; exit 2; }
      shards+=("$2")
      shift 2
      ;;
    --parallel)
      [[ $# -ge 2 ]] || { echo "--parallel requires a value" >&2; exit 2; }
      parallel="$2"
      shift 2
      ;;
    --destination)
      [[ $# -ge 2 ]] || { echo "--destination requires a value" >&2; exit 2; }
      destination="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$parallel" =~ ^[1-9][0-9]*$ ]] || { echo "--parallel must be positive" >&2; exit 2; }
for shard in "${shards[@]}"; do
  [[ "$shard" =~ ^[0-9]+$ ]] && ((shard >= 0 && shard <= 19)) || {
    echo "--shard must be between 0 and 19: $shard" >&2
    exit 2
  }
done

mkdir -p "$destination"
destination="$(cd "$destination" && pwd)"
base_url="https://storage.googleapis.com/gresearch/android_control"

download_one() {
  local name="$1"
  local final="$destination/$name"
  local partial="$final.part"
  if [[ -s "$final" ]]; then
    echo "already downloaded: $name"
    return 0
  fi
  echo "downloading: $name"
  curl \
    --fail \
    --location \
    --retry 8 \
    --retry-delay 2 \
    --retry-all-errors \
    --continue-at - \
    --output "$partial" \
    "$base_url/$name"
  mv -f "$partial" "$final"
  echo "completed: $name"
}

export destination base_url
export -f download_one

download_one "splits.json"
download_one "test_subsplits.json"

if ((download_all)); then
  shards=({0..19})
fi

if ((${#shards[@]})); then
  shard_names=()
  while IFS= read -r shard; do
    printf -v name 'android_control-%05d-of-00020' "$shard"
    shard_names+=("$name")
  done < <(printf '%s\n' "${shards[@]}" | sort -nu)

  printf '%s\n' "${shard_names[@]}" \
    | xargs -P "$parallel" -I '{}' bash -c 'download_one "$1"' _ '{}'
fi

(
  cd "$destination"
  find . -maxdepth 1 -type f \
    \( -name 'splits.json' -o -name 'test_subsplits.json' -o -name 'android_control-*-of-00020' \) \
    -printf '%f\n' \
    | sort \
    | xargs -r sha256sum > manifest.sha256
  {
    printf 'name\tbytes\n'
    find . -maxdepth 1 -type f \
      \( -name 'splits.json' -o -name 'test_subsplits.json' -o -name 'android_control-*-of-00020' \) \
      -printf '%f\t%s\n' \
      | sort
  } > manifest.sizes.tsv
)

echo "AndroidControl download ready: $destination"
