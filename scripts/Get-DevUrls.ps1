$ErrorActionPreference = "Stop"

$ipLines = ipconfig | Select-String -Pattern "IPv4"
$ips = foreach ($line in $ipLines) {
  if ($line.Line -match "(\d{1,3}(?:\.\d{1,3}){3})") {
    $Matches[1]
  }
}

$lanIp = $ips |
  Where-Object { $_ -notlike "127.*" -and $_ -notlike "169.254.*" } |
  Select-Object -First 1

if (-not $lanIp) {
  Write-Host "No LAN IPv4 address found. Check your network connection."
  exit 1
}

Write-Host "API local:      http://127.0.0.1:8010"
Write-Host "API for phone:  http://$lanIp`:8010"
Write-Host "Web demo:       http://127.0.0.1:8020"
Write-Host "Expo local:     http://127.0.0.1:8081"
Write-Host "Expo for phone: exp://$lanIp`:8081"
