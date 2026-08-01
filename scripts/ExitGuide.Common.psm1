$script:ExitGuideExcludedDirectoryNames = @(
  ".git",
  ".tools",
  ".logs",
  ".artifacts",
  "node_modules",
  ".venv",
  "__pycache__",
  ".expo"
)

function Get-ExitGuideRepoRoot {
  return Split-Path -Parent $PSScriptRoot
}

function Resolve-ExitGuideGitCommand {
  param([string]$RepoRoot = (Get-ExitGuideRepoRoot))

  $PathGit = Get-Command git -ErrorAction SilentlyContinue
  if ($PathGit) {
    return $PathGit.Source
  }

  $ToolsDir = Join-Path $RepoRoot ".tools"
  if (-not (Test-Path -LiteralPath $ToolsDir)) {
    return $null
  }

  $LocalGit = Get-ChildItem -LiteralPath $ToolsDir -Filter "git.exe" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\mingit-[^\\]+\\cmd\\git\.exe$" } |
    Sort-Object FullName -Descending |
    Select-Object -First 1

  if ($LocalGit) {
    return $LocalGit.FullName
  }

  return $null
}

function Resolve-ExitGuideGhCommand {
  param([string]$RepoRoot = (Get-ExitGuideRepoRoot))

  $PathGh = Get-Command gh -ErrorAction SilentlyContinue
  if ($PathGh) {
    return $PathGh.Source
  }

  $ToolsDir = Join-Path $RepoRoot ".tools"
  if (-not (Test-Path -LiteralPath $ToolsDir)) {
    return $null
  }

  $LocalGh = Get-ChildItem -LiteralPath $ToolsDir -Filter "gh.exe" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\gh-[^\\]+\\bin\\gh\.exe$" } |
    Sort-Object FullName -Descending |
    Select-Object -First 1

  if ($LocalGh) {
    return $LocalGh.FullName
  }

  return $null
}

function Import-ExitGuideEnvFile {
  param(
    [string]$EnvFile = (Join-Path (Get-ExitGuideRepoRoot) ".env")
  )

  if (-not (Test-Path -LiteralPath $EnvFile)) {
    return 0
  }

  $Imported = 0
  foreach ($Line in (Get-Content -LiteralPath $EnvFile -Encoding UTF8)) {
    if ($Line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
      continue
    }

    $Name = $Matches[1]
    $Value = $Matches[2].Trim()
    if (
      $Value.Length -ge 2 -and
      (($Value.StartsWith('"') -and $Value.EndsWith('"')) -or ($Value.StartsWith("'") -and $Value.EndsWith("'")))
    ) {
      $Value = $Value.Substring(1, $Value.Length - 2)
    }

    if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($Name, "Process"))) {
      [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
      $Imported++
    }
  }

  return $Imported
}

function Test-ExitGuideChildPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $true)]
    [string]$Parent
  )

  $ResolvedParent = [System.IO.Path]::GetFullPath($Parent).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
  $ResolvedPath = [System.IO.Path]::GetFullPath($Path)
  $ParentPrefix = $ResolvedParent + [System.IO.Path]::DirectorySeparatorChar

  if (
    $ResolvedPath.Equals($ResolvedParent, [System.StringComparison]::OrdinalIgnoreCase) -or
    $ResolvedPath.StartsWith($ParentPrefix, [System.StringComparison]::OrdinalIgnoreCase)
  ) {
    return $true
  }

  throw "Path is outside $ResolvedParent`: $ResolvedPath"
}

function Get-ExitGuideSourceFiles {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [string[]]$ExcludedDirectoryNames = $script:ExitGuideExcludedDirectoryNames
  )

  foreach ($Item in Get-ChildItem -LiteralPath $Root -Force) {
    if ($Item.PSIsContainer) {
      if ($ExcludedDirectoryNames -contains $Item.Name) {
        continue
      }
      Get-ExitGuideSourceFiles -Root $Item.FullName -ExcludedDirectoryNames $ExcludedDirectoryNames
    } elseif ($Item.Extension -ne ".pyc") {
      $Item
    }
  }
}

function Copy-ExitGuideSourceToStaging {
  param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [Parameter(Mandatory = $true)]
    [string]$Staging
  )

  New-Item -ItemType Directory -Path $Staging -Force | Out-Null

  foreach ($File in (Get-ExitGuideSourceFiles -Root $RepoRoot)) {
    $Relative = $File.FullName.Substring($RepoRoot.Length).TrimStart([char[]]@('\', '/'))
    $Target = Join-Path $Staging $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
    Copy-Item -LiteralPath $File.FullName -Destination $Target -Force
  }
}

function Test-ExitGuideArchiveClean {
  param([Parameter(Mandatory = $true)][string]$ArchivePath)

  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $Archive = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
  $EscapedNames = $script:ExitGuideExcludedDirectoryNames | ForEach-Object { [System.Text.RegularExpressions.Regex]::Escape($_) }
  $ForbiddenPathPattern = "(^|[\\/])($($EscapedNames -join '|'))([\\/]|$)"
  $ForbiddenSensitivePathPatterns = @(
    "(^|[\\/])\.env$",
    "(^|[\\/])\.env\.(local|production|development|test)$",
    "(^|[\\/])(id_rsa|id_dsa|id_ecdsa|id_ed25519)$",
    "\.(pem|pfx|p12|key)$",
    "(^|[\\/])terms[-_ ]?captures?([\\/]|$)",
    "(^|[\\/])terms[-_ ]?corpus\.sqlite$",
    "(^|[\\/])(raw[-_ ]?captures?|raw[-_ ]?ocr|ocr[-_ ]?raw|unredacted|private[-_ ]?captures?)([\\/]|$)",
    "(^|[\\/])(captures|screenshots)[\\/](raw|unredacted)([\\/]|$)"
  )
  $TextExtensions = @(
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
    ".txt",
    ".yaml",
    ".yml"
  )
  $SensitiveContentPatterns = @(
    "-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----",
    "sk-[A-Za-z0-9][A-Za-z0-9_-]{20,}",
    "AIza[0-9A-Za-z_-]{20,}",
    "ghp_[0-9A-Za-z]{20,}",
    "github_pat_[0-9A-Za-z_]{20,}"
  )

  try {
    $ForbiddenEntry = $Archive.Entries |
      Where-Object { $_.FullName -match $ForbiddenPathPattern } |
      Select-Object -First 1

    if ($ForbiddenEntry) {
      throw "Archive contains excluded path: $($ForbiddenEntry.FullName)"
    }

    foreach ($Pattern in $ForbiddenSensitivePathPatterns) {
      $SensitiveEntry = $Archive.Entries |
        Where-Object { $_.FullName -match $Pattern } |
        Select-Object -First 1
      if ($SensitiveEntry) {
        throw "Archive contains sensitive/raw path: $($SensitiveEntry.FullName)"
      }
    }

    foreach ($Entry in $Archive.Entries) {
      if ($Entry.Length -gt 512KB) {
        continue
      }
      $Extension = [System.IO.Path]::GetExtension($Entry.FullName).ToLowerInvariant()
      if ($TextExtensions -notcontains $Extension) {
        continue
      }
      $Stream = $Entry.Open()
      $Reader = $null
      try {
        $Reader = [System.IO.StreamReader]::new($Stream, [System.Text.Encoding]::UTF8, $true)
        $Text = $Reader.ReadToEnd()
      }
      finally {
        if ($Reader) {
          $Reader.Dispose()
        } else {
          $Stream.Dispose()
        }
      }

      foreach ($Pattern in $SensitiveContentPatterns) {
        if ($Text -match $Pattern) {
          throw "Archive contains sensitive-looking content in $($Entry.FullName)"
        }
      }
    }
  }
  finally {
    $Archive.Dispose()
  }

  return $true
}

Export-ModuleMember -Function `
  Get-ExitGuideRepoRoot, `
  Resolve-ExitGuideGitCommand, `
  Resolve-ExitGuideGhCommand, `
  Import-ExitGuideEnvFile, `
  Test-ExitGuideChildPath, `
  Get-ExitGuideSourceFiles, `
  Copy-ExitGuideSourceToStaging, `
  Test-ExitGuideArchiveClean
