# Git And GitHub Workflow

## Why Git May Not Work Locally

The Codex GitHub plugin is a GitHub API connector. It can inspect or update a GitHub repository when a repository such as `owner/name` is known.

It does not install `git.exe`, add Git to Windows PATH, or turn an extracted project folder into a local `.git` checkout. Local commands such as `git status`, `git branch`, `git commit`, and `git push` still require:

- Git installed on the machine
- the project folder initialized or cloned as a Git repository
- a remote configured if pushing to GitHub

Current local fallback when Git is unavailable:

- `scripts\New-WorkBlockArchive.ps1` creates branch-like timestamped source snapshots under `.artifacts\work-blocks`.
- `scripts\Get-ProjectStatus.ps1` reports Git availability, generated artifacts, quality status, and recent snapshots.
- `scripts\Test-All.ps1` remains the primary quality gate before each snapshot or transfer archive.
- `scripts\Complete-WorkBlock.ps1` runs the full gate, checks `git diff --check`, refreshes the transfer archive, creates a work-block snapshot, and prints Git status.
- `scripts\Test-ProjectStatus.ps1` keeps branch, commit, remote, and dirty working-tree reporting from regressing.

This workspace also supports a project-local portable MinGit under `.tools\mingit-*\cmd\git.exe`. `scripts\Bootstrap-Windows.ps1` installs it when `git.exe` is not on PATH, and the helper scripts use it automatically.
The same bootstrap installs a project-local GitHub CLI under `.tools\gh-*\bin\gh.exe` when `gh.exe` is not on PATH.

## Recommended Local Setup

1. Install Git for Windows. If `winget` is available:

```powershell
winget install --id Git.Git -e --source winget
```

Or install it from the official Git for Windows installer.

2. Open a new PowerShell window so PATH refreshes.
3. From the project root, run:

```powershell
git --version
git status
```

If this folder is still an extracted copy rather than a clone, initialize it:

```powershell
git init
git add .
git commit -m "Initial ExitGuide MVP"
.\scripts\New-DevBranch.ps1 -BranchName codex/demo-quality-hardening
```

If the repository already exists on GitHub, prefer cloning it instead of running `git init` over an extracted copy:

```powershell
git clone <repo-url>
cd <repo-folder>
.\scripts\New-DevBranch.ps1 -BranchName codex/demo-quality-hardening
```

## Branch Naming

Use the `codex/` prefix for development branches unless a user asks otherwise:

```powershell
.\scripts\New-DevBranch.ps1 -BranchName codex/flow-quality-gate
```

The helper refuses to run without local Git and refuses to create a branch outside a Git repository unless `-InitIfMissing` is explicitly provided.

Before ending a branch block, run:

```powershell
.\scripts\Complete-WorkBlock.ps1 -Label flow-quality-gate
```

Then review `git status`, stage only the intended files, and commit the block.

## Publish To GitHub

The repository can be created and pushed after one GitHub CLI login:

```powershell
.\.tools\gh-2.92.0\bin\gh.exe auth login --web --git-protocol https
.\scripts\Publish-GitHub.ps1 -RepositoryName exitguide -Visibility private
```

Use `-CreateDraftPullRequest` when a remote already has the default branch and the current `codex/` branch should open as a draft PR.
