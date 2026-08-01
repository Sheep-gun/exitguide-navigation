$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $RepoRoot "apps/web-demo"
$HtmlPath = Join-Path $WebRoot "index.html"
$NavigationHtmlPath = Join-Path $WebRoot "navigation.html"
$DarkPatternHtmlPath = Join-Path $WebRoot "dark-pattern.html"
$Node = Join-Path $RepoRoot ".tools/node-v24.15.0-win-x64/node.exe"
$VenvPython = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"

if (-not (Test-Path $HtmlPath)) {
  throw "Web demo index.html was not found."
}
if (-not (Test-Path $NavigationHtmlPath)) {
  throw "Navigation MVP page was not found."
}
if (-not (Test-Path $DarkPatternHtmlPath)) {
  throw "Dark Pattern MVP page was not found."
}

$Html = Get-Content -Raw -Encoding UTF8 -LiteralPath $HtmlPath
$NavigationHtml = Get-Content -Raw -Encoding UTF8 -LiteralPath $NavigationHtmlPath
$DarkPatternHtml = Get-Content -Raw -Encoding UTF8 -LiteralPath $DarkPatternHtmlPath
foreach ($RequiredText in @("ExitGuide AI Demo", "Demo scenarios", "Flow checks", "Synthetic uploads", "Proof Card", "Quality gate", "Highest-risk screen")) {
  if (-not $Html.Contains($RequiredText)) {
    throw "Web demo is missing required text: $RequiredText"
  }
}

foreach ($RequiredMarkup in @('role="status"', 'aria-live="polite"', 'type="url"', "button:focus-visible", 'aria-label="Readiness checks"')) {
  if (-not $Html.Contains($RequiredMarkup)) {
    throw "Web demo is missing accessibility markup: $RequiredMarkup"
  }
}

foreach ($RequiredText in @("EGL Navigation MVP", "/v1/navigation/guide", 'id="detour"', "terms_hint", "handleElementClick")) {
  if (-not $NavigationHtml.Contains($RequiredText)) {
    throw "Navigation MVP is missing required text: $RequiredText"
  }
}

foreach ($RequiredContract in @("target_element_id", "last_confirmed_state_id", "failed_element_ids", "requires_user_confirmation")) {
  if (-not $NavigationHtml.Contains($RequiredContract)) {
    throw "Navigation MVP is missing contract field: $RequiredContract"
  }
}

foreach ($RequiredText in @("EGL Dark Pattern MVP", "/v1/dark-pattern/inspect", "currentAnalysis.findings", "default_selected", "renderFinding")) {
  if (-not $DarkPatternHtml.Contains($RequiredText)) {
    throw "Dark Pattern MVP is missing required text: $RequiredText"
  }
}

if (-not $NavigationHtml.Contains("dark_pattern")) {
  throw "Navigation MVP does not render integrated dark-pattern results."
}

$DynamicButtonTypeCount = ([regex]::Matches($Html, "button\.type\s*=\s*[""']button[""']")).Count
if ($DynamicButtonTypeCount -lt 3) {
  throw "Web demo should set type=button on dynamic scenario, flow, and synthetic buttons."
}

if ($Html -match "radial-gradient") {
  throw "Web demo should not use decorative radial-gradient backgrounds."
}

if ($Html -match "letter-spacing:\s*-") {
  throw "Web demo should not use negative letter spacing."
}

$RadiusMatches = [regex]::Matches($Html, "border-radius:\s*(\d+)px")
foreach ($Match in $RadiusMatches) {
  $Radius = [int]$Match.Groups[1].Value
  if ($Radius -gt 8 -and $Radius -lt 100) {
    throw "Web demo rectangular UI border radius should stay at 8px or less."
  }
}

if (Test-Path $Node) {
  $ScriptMatch = [regex]::Match($Html, "(?s)<script>\s*(.*?)\s*</script>")
  if (-not $ScriptMatch.Success) {
    throw "Web demo JavaScript block was not found."
  }

  $TempScript = Join-Path ([System.IO.Path]::GetTempPath()) ("exitguide-web-demo-" + [System.Guid]::NewGuid().ToString("N") + ".js")
  try {
    Set-Content -Encoding UTF8 -LiteralPath $TempScript -Value $ScriptMatch.Groups[1].Value
    & $Node --check $TempScript
    if ($LASTEXITCODE -ne 0) {
      throw "Web demo JavaScript syntax check failed with exit code $LASTEXITCODE"
    }
  }
  finally {
    Remove-Item -LiteralPath $TempScript -Force -ErrorAction SilentlyContinue
  }
}

if (Test-Path $VenvPython) {
  $Listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), 0)
  $Listener.Start()
  $Port = $Listener.LocalEndpoint.Port
  $Listener.Stop()

  $Process = Start-Process -FilePath $VenvPython -ArgumentList @("-m", "http.server", "$Port", "--bind", "127.0.0.1") -WorkingDirectory $WebRoot -WindowStyle Hidden -PassThru
  try {
    $Response = $null
    for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {
      try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2
        break
      }
      catch {
        Start-Sleep -Milliseconds 300
      }
    }

    if (-not $Response -or $Response.StatusCode -ne 200) {
      throw "Web demo HTTP smoke check failed."
    }
    if (-not $Response.Content.Contains("Goal-first dark-pattern guidance.")) {
      throw "Web demo HTTP smoke check returned unexpected content."
    }
  }
  finally {
    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
  }
}

Write-Host "Web demo checks passed."
