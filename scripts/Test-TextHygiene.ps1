$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiRoot = Join-Path $RepoRoot "apps/api"
$Python = Join-Path $ApiRoot ".venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

@"
from pathlib import Path
import sys

repo_root = Path(r"$RepoRoot")
search_roots = [
    ".editorconfig",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "README.md",
    "apps/api/app",
    "apps/api/README.md",
    "apps/api/tests",
    "apps/mobile/README.md",
    "apps/mobile/src",
    "apps/web-demo",
    "docs",
    "scripts",
    ".github",
]

text_suffixes = {
    ".css",
    ".example",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".psm1",
    ".py",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
text_filenames = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
}

skip_parts = {
    ".artifacts",
    ".expo",
    ".git",
    ".logs",
    ".tools",
    ".venv",
    "__pycache__",
    "node_modules",
}

forbidden = [
    ("\ufffd", "Unicode replacement character"),
    ("\u00c2\u00b7", "mojibake middle dot"),
    ("\u00e2\u0080\u00a2", "mojibake bullet"),
]


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    return data.decode("utf-8", errors="replace")


failures = []
for root in search_roots:
    full_root = repo_root / root
    if not full_root.exists():
        continue

    paths = [full_root] if full_root.is_file() else full_root.rglob("*")
    for path in paths:
        if not path.is_file() or (path.suffix.lower() not in text_suffixes and path.name not in text_filenames):
            continue
        if any(part in skip_parts for part in path.relative_to(repo_root).parts):
            continue

        text = read_text(path)
        for pattern, label in forbidden:
            start = 0
            while True:
                index = text.find(pattern, start)
                if index == -1:
                    break
                line = text.count("\n", 0, index) + 1
                rel = path.relative_to(repo_root)
                failures.append(f"{rel}:{line} contains {label}")
                start = index + max(1, len(pattern))

if failures:
    for failure in failures[:50]:
        print(failure)
    if len(failures) > 50:
        print(f"... and {len(failures) - 50} more")
    raise SystemExit(f"{len(failures)} text hygiene issue(s) found.")

print("Text hygiene checks passed.")
"@ | & $Python -

if ($LASTEXITCODE -ne 0) {
  throw "Text hygiene checks failed with exit code $LASTEXITCODE"
}
