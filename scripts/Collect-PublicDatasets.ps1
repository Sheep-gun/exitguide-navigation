param(
  [string]$InventoryPath = "",
  [string]$OutputRoot = "",
  [switch]$MetadataOnly,
  [int]$HttpTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$CommonModule = Join-Path $PSScriptRoot "ExitGuide.Common.psm1"
Import-Module $CommonModule -Force

$RepoRoot = Get-ExitGuideRepoRoot

if (-not $InventoryPath) {
  $InventoryPath = Join-Path $RepoRoot "fixtures/public-datasets/sources.json"
}

if (-not $OutputRoot) {
  $OutputRoot = Join-Path $RepoRoot ".artifacts/public-datasets"
}

if (-not [System.IO.Path]::IsPathRooted($InventoryPath)) {
  $InventoryPath = Join-Path $RepoRoot $InventoryPath
}

if (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
  $OutputRoot = Join-Path $RepoRoot $OutputRoot
}

Test-ExitGuideChildPath -Path $InventoryPath -Parent $RepoRoot | Out-Null
Test-ExitGuideChildPath -Path $OutputRoot -Parent $RepoRoot | Out-Null

if (-not (Test-Path -LiteralPath $InventoryPath)) {
  throw "Dataset inventory not found: $InventoryPath"
}

$LocalPython = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"
$Python = $null
if (Test-Path -LiteralPath $LocalPython) {
  $Python = $LocalPython
} else {
  $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($PythonCommand) {
    $Python = $PythonCommand.Source
  }
}

if (-not $Python) {
  throw "Python was not found. Run .\scripts\Bootstrap-Windows.ps1 first or install Python."
}

$MetadataOnlyArg = if ($MetadataOnly) { "1" } else { "0" }

$Script = @'
from __future__ import annotations

import datetime as _dt
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


INVENTORY_PATH = Path(sys.argv[1]).resolve()
OUTPUT_ROOT = Path(sys.argv[2]).resolve()
METADATA_ONLY = sys.argv[3] == "1"
HTTP_TIMEOUT_SECONDS = int(sys.argv[4])

USER_AGENT = "ExitGuide-PublicDatasetCollector/2026.07 (+local research)"
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def safe_filename(value: str, fallback: str = "download.bin") -> str:
    name = os.path.basename((value or "").strip()) or fallback
    name = urllib.parse.unquote(name)
    name = INVALID_FILENAME_CHARS.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = fallback
    if len(name) > 180:
        root, ext = os.path.splitext(name)
        name = root[: 180 - len(ext)] + ext
    return name


def source_dir(source_id: str) -> Path:
    path = OUTPUT_ROOT / "raw" / source_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def result_dir() -> Path:
    path = OUTPUT_ROOT / "results"
    path.mkdir(parents=True, exist_ok=True)
    return path


def request_for(url: str, referer: str | None = None) -> urllib.request.Request:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    }
    if referer:
        headers["Referer"] = referer
    return urllib.request.Request(url, headers=headers)


def decode_text(data: bytes, headers: dict[str, str]) -> str:
    content_type = headers.get("content-type", "")
    match = re.search(r"charset=([^;\s]+)", content_type, re.IGNORECASE)
    encodings = []
    if match:
        encodings.append(match.group(1).strip('"'))
    encodings.extend(["utf-8", "cp949", "euc-kr", "latin-1"])
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
        except LookupError:
            continue
    return data.decode("utf-8", errors="replace")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_disposition_filename(headers: dict[str, str]) -> str | None:
    value = headers.get("content-disposition", "")
    if not value:
        return None
    match = re.search(r"filename\*=([^']*)''([^;]+)", value, re.IGNORECASE)
    if match:
        return urllib.parse.unquote(match.group(2))
    match = re.search(r'filename="?([^";]+)"?', value, re.IGNORECASE)
    if match:
        return urllib.parse.unquote(match.group(1))
    return None


def infer_filename(url: str, headers: dict[str, str], fallback: str = "download.bin") -> str:
    disposition_name = content_disposition_filename(headers)
    if disposition_name:
        return safe_filename(disposition_name, fallback=fallback)
    parsed = urllib.parse.urlparse(url)
    basename = os.path.basename(parsed.path)
    return safe_filename(basename, fallback=fallback)


def download_url(url: str, destination_dir: Path, default_filename: str | None = None, referer: str | None = None) -> dict:
    started_at = utc_now()
    if METADATA_ONLY:
        return {
            "url": url,
            "status": "metadata_only",
            "started_at": started_at,
            "finished_at": utc_now(),
        }

    if default_filename:
        existing_path = destination_dir / safe_filename(default_filename, fallback="download.bin")
        if existing_path.exists():
            return {
                "url": url,
                "status": "existing",
                "path": str(existing_path),
                "bytes": existing_path.stat().st_size,
                "sha256": sha256_file(existing_path),
                "started_at": started_at,
                "finished_at": utc_now(),
            }

    try:
        request = request_for(url, referer=referer)
        response = urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS)
        headers = {key.lower(): value for key, value in response.headers.items()}
        status_code = getattr(response, "status", 200)
        filename = safe_filename(default_filename or infer_filename(url, headers), fallback="download.bin")
        path = destination_dir / filename
        if path.exists():
            response.close()
            return {
                "url": url,
                "status": "existing",
                "status_code": status_code,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "content_type": headers.get("content-type"),
                "started_at": started_at,
                "finished_at": utc_now(),
            }
        digest = hashlib.sha256()
        total_bytes = 0
        temp_path = path.with_name(path.name + ".part")
        path.parent.mkdir(parents=True, exist_ok=True)
        with response:
            with temp_path.open("wb") as handle:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    handle.write(chunk)
                    digest.update(chunk)
                    total_bytes += len(chunk)
        temp_path.replace(path)
        return {
            "url": url,
            "status": "downloaded",
            "status_code": status_code,
            "path": str(path),
            "bytes": total_bytes,
            "sha256": digest.hexdigest(),
            "content_type": headers.get("content-type"),
            "started_at": started_at,
            "finished_at": utc_now(),
        }
    except urllib.error.HTTPError as exc:
        return {
            "url": url,
            "status": "failed",
            "error": f"HTTP {exc.code}: {exc.reason}",
            "started_at": started_at,
            "finished_at": utc_now(),
        }
    except Exception as exc:
        return {
            "url": url,
            "status": "failed",
            "error": str(exc),
            "started_at": started_at,
            "finished_at": utc_now(),
        }


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_direct_files(source: dict) -> dict:
    out = source_dir(source["id"])
    artifacts = []
    for item in source.get("files", []):
        artifacts.append(download_url(item["url"], out, default_filename=item.get("filename")))
    return {"artifacts": artifacts}


def collect_web_page(source: dict) -> dict:
    out = source_dir(source["id"])
    artifacts = []
    urls = source.get("urls") or [source.get("url")]
    for index, url in enumerate([u for u in urls if u], start=1):
        parsed = urllib.parse.urlparse(url)
        extension = ".json" if parsed.path.endswith(".json") else ".html"
        default_name = f"page-{index}{extension}"
        artifacts.append(download_url(url, out, default_filename=default_name))
    return {"artifacts": artifacts}


def parse_json_ld_content_url(page_text: str) -> str | None:
    match = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', page_text)
    if match:
        return html.unescape(match.group(1))
    return None


def collect_data_go_kr_file_page(source: dict) -> dict:
    out = source_dir(source["id"])
    artifacts = []
    page_url = source["url"]
    page_result = download_url(page_url, out, default_filename="fileData-page.html")
    artifacts.append(page_result)
    content_url = None

    page_path = page_result.get("path")
    if page_path and Path(page_path).exists():
        data = Path(page_path).read_bytes()
        page_text = decode_text(data, {"content-type": page_result.get("content_type") or ""})
        content_url = parse_json_ld_content_url(page_text)

    if content_url:
        artifacts.append(download_url(content_url, out, referer=page_url))
    else:
        artifacts.append({
            "url": page_url,
            "status": "failed",
            "error": "contentUrl was not found in page JSON-LD",
            "started_at": utc_now(),
            "finished_at": utc_now(),
        })

    save_json(out / "parsed-metadata.json", {"source_url": page_url, "content_url": content_url})
    return {"artifacts": artifacts, "content_url": content_url}


def collect_github_repo_zip(source: dict) -> dict:
    out = source_dir(source["id"])
    repo = source["repo"]
    api_url = f"https://api.github.com/repos/{repo}"
    artifacts = []
    default_branch = source.get("branch")
    api_result = download_url(api_url, out, default_filename="github-repository.json")
    artifacts.append(api_result)

    api_path = api_result.get("path")
    if api_path and Path(api_path).exists():
        try:
            api_payload = json.loads(Path(api_path).read_text(encoding="utf-8"))
            default_branch = default_branch or api_payload.get("default_branch")
        except Exception:
            default_branch = default_branch or "main"
    default_branch = default_branch or "main"
    zip_url = f"https://codeload.github.com/{repo}/zip/refs/heads/{default_branch}"
    zip_name = f"{repo.replace('/', '__')}-{default_branch}.zip"
    artifacts.append(download_url(zip_url, out, default_filename=zip_name, referer=api_url))
    return {"artifacts": artifacts, "default_branch": default_branch}


def collect_huggingface_dataset_files(source: dict) -> dict:
    out = source_dir(source["id"])
    repo = source["repo"]
    api_url = f"https://huggingface.co/api/datasets/{repo}"
    artifacts = []
    api_result = download_url(api_url, out, default_filename="huggingface-dataset.json")
    artifacts.append(api_result)
    include = set(source.get("include") or [])
    selected_files = []

    api_path = api_result.get("path")
    if api_path and Path(api_path).exists():
        try:
            api_payload = json.loads(Path(api_path).read_text(encoding="utf-8"))
            for sibling in api_payload.get("siblings", []):
                filename = sibling.get("rfilename")
                if filename and (not include or filename in include):
                    selected_files.append(filename)
        except Exception as exc:
            artifacts.append({
                "url": api_url,
                "status": "failed",
                "error": f"Could not parse Hugging Face API payload: {exc}",
                "started_at": utc_now(),
                "finished_at": utc_now(),
            })

    if include:
        missing = sorted(include.difference(selected_files))
        for filename in missing:
            artifacts.append({
                "url": f"https://huggingface.co/datasets/{repo}/resolve/main/{filename}",
                "status": "failed",
                "error": "file listed in inventory but not found in API siblings",
                "started_at": utc_now(),
                "finished_at": utc_now(),
            })

    for filename in selected_files:
        url = f"https://huggingface.co/datasets/{repo}/resolve/main/{urllib.parse.quote(filename)}"
        artifacts.append(download_url(url, out, default_filename=safe_filename(filename), referer=api_url))

    return {"artifacts": artifacts, "selected_files": selected_files}


def ftc_page_url(base_url: str, page_index: int) -> str:
    parsed = urllib.parse.urlparse(base_url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["pageIndex"] = [str(page_index)]
    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def collect_ftc_standard_terms(source: dict) -> dict:
    out = source_dir(source["id"])
    pages_dir = out / "pages"
    attachments_dir = out / "attachments"
    pages_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir.mkdir(parents=True, exist_ok=True)

    artifacts = []
    download_links = []
    max_pages = int(source.get("max_pages") or 1)
    base_url = source["url"]

    for page_index in range(1, max_pages + 1):
        url = ftc_page_url(base_url, page_index)
        page_result = download_url(url, pages_dir, default_filename=f"page-{page_index}.html")
        artifacts.append(page_result)
        page_path = page_result.get("path")
        if not page_path or not Path(page_path).exists():
            continue
        page_bytes = Path(page_path).read_bytes()
        page_text = decode_text(page_bytes, {"content-type": page_result.get("content_type") or ""})
        for raw_link in re.findall(r'(?:https?://[^"\'<> ]+)?(?:/www/)?downloadBbsFile\.do\?[^"\'<> ]+', page_text):
            link = urllib.parse.urljoin(url, html.unescape(raw_link))
            if link not in download_links:
                download_links.append(link)

    attachment_results = []
    for index, link in enumerate(download_links, start=1):
        fallback = f"attachment-{index:03d}.bin"
        attachment_results.append(download_url(link, attachments_dir, default_filename=fallback, referer=base_url))

    artifacts.extend(attachment_results)
    crawl_index = {
        "base_url": base_url,
        "max_pages": max_pages,
        "download_link_count": len(download_links),
        "download_links": download_links,
    }
    save_json(out / "crawl-index.json", crawl_index)
    return {"artifacts": artifacts, "download_link_count": len(download_links)}


def collect_manual(source: dict) -> dict:
    return {
        "artifacts": [],
        "note": "Manual account, large-scale mirroring, or targeted crawl planning is required before collection."
    }


COLLECTORS = {
    "direct_files": collect_direct_files,
    "web_page": collect_web_page,
    "data_go_kr_file_page": collect_data_go_kr_file_page,
    "github_repo_zip": collect_github_repo_zip,
    "huggingface_dataset_files": collect_huggingface_dataset_files,
    "ftc_standard_terms": collect_ftc_standard_terms,
    "manual_required": collect_manual,
}


def summarize_source_status(source: dict, details: dict) -> str:
    collector = source.get("collector")
    access = source.get("access", "")
    if collector == "manual_required":
        if "deferred_large" in access:
            return "deferred_large"
        return "manual_required"

    artifacts = details.get("artifacts", [])
    if not artifacts:
        return "no_artifacts"
    statuses = [item.get("status") for item in artifacts]
    failed = [status for status in statuses if status == "failed"]
    successful = [
        status
        for status in statuses
        if status in {"downloaded", "existing", "metadata_only"}
    ]
    if failed and successful:
        return "partial"
    if failed and not successful:
        return "failed"
    if all(status == "metadata_only" for status in statuses):
        return "metadata_only"
    return "collected"


def write_markdown_summary(path: Path, result: dict) -> None:
    lines = [
        "# Public Dataset Collection Result",
        "",
        f"- Started: {result['started_at']}",
        f"- Finished: {result['finished_at']}",
        f"- Inventory: `{result['inventory_path']}`",
        f"- Output root: `{result['output_root']}`",
        f"- Metadata only: `{result['metadata_only']}`",
        "",
        "| Source | Access | Collector | Status | Artifacts |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for source in result["sources"]:
        artifact_count = len(source.get("artifacts", []))
        lines.append(
            f"| `{source['id']}` | `{source.get('access', '')}` | `{source.get('collector', '')}` | `{source['status']}` | {artifact_count} |"
        )
    lines.append("")
    lines.append("Raw files remain outside Git under `.artifacts/public-datasets/raw`.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    started_at = utc_now()
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    source_results = []
    for source in inventory.get("sources", []):
        source_started = utc_now()
        collector_name = source.get("collector")
        collector = COLLECTORS.get(collector_name)
        if not collector:
            details = {
                "artifacts": [],
                "error": f"Unknown collector: {collector_name}",
            }
        else:
            details = collector(source)
        status = summarize_source_status(source, details)
        source_results.append({
            "id": source.get("id"),
            "name": source.get("name"),
            "category": source.get("category"),
            "priority": source.get("priority"),
            "access": source.get("access"),
            "collector": collector_name,
            "status": status,
            "started_at": source_started,
            "finished_at": utc_now(),
            **details,
        })
        print(f"{source.get('id')}: {status}")
        sys.stdout.flush()
        time.sleep(0.2)

    result = {
        "schema_version": inventory.get("schema_version"),
        "started_at": started_at,
        "finished_at": utc_now(),
        "inventory_path": str(INVENTORY_PATH),
        "output_root": str(OUTPUT_ROOT),
        "metadata_only": METADATA_ONLY,
        "sources": source_results,
    }

    result_path = result_dir() / "public_dataset_collection_result.json"
    summary_path = result_dir() / "public_dataset_collection_result.md"
    save_json(result_path, result)
    write_markdown_summary(summary_path, result)
    print(f"wrote {result_path}")
    print(f"wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$env:PYTHONDONTWRITEBYTECODE = "1"
$Script | & $Python - $InventoryPath $OutputRoot $MetadataOnlyArg $HttpTimeoutSeconds
if ($LASTEXITCODE -ne 0) {
  throw "Public dataset collection failed with exit code $LASTEXITCODE"
}
