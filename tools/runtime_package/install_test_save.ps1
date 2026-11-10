# Installs the converted test save for FINAL FANTASY IX (Steam, vanilla).
# Safe by design: it never overwrites a file. An existing save is renamed first and the
# rename is recorded so collect_and_restore.ps1 can put it back.
param([string]$Source = "")
$ErrorActionPreference = "Stop"
$pkg = $PSScriptRoot
if (-not $Source) { $Source = Join-Path $pkg "PC\SavedData_ww.dat" }
$dir = Join-Path $env:USERPROFILE "AppData\LocalLow\SquareEnix\FINAL FANTASY IX\Steam\EncryptedSavedData"
$target = Join-Path $dir "SavedData_ww.dat"
$state = Join-Path $pkg "results\installed.json"

if (Get-Process -Name FF9 -ErrorAction SilentlyContinue) { throw "Close FINAL FANTASY IX first." }
if (Test-Path $state) { throw "A test save is already installed (results\installed.json). Run collect_and_restore.ps1 first." }

$backup = $null
if (Test-Path $target) {
    $backup = "$target.before-test-$(Get-Date -Format yyyyMMdd-HHmmss)"
    Rename-Item -Path $target -NewName (Split-Path $backup -Leaf)
    Write-Host "Your existing save was renamed to: $backup"
}
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
Copy-Item -Path $Source -Destination $target
$hash = (Get-FileHash $target -Algorithm SHA256).Hash
@{ target = $target; backup = $backup; installed_sha256 = $hash; installed_at = (Get-Date).ToString("o") } |
    ConvertTo-Json | Set-Content -Path $state -Encoding UTF8
Write-Host "Test save installed at $target"
Write-Host "IMPORTANT: do NOT use the Cloud option on the title screen while testing."
