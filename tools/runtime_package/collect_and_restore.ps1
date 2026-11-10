# Copies the save the game wrote during testing into results\ (evidence for analysis),
# removes the test save, and puts back any save that install_test_save.ps1 renamed.
$ErrorActionPreference = "Stop"
$pkg = $PSScriptRoot
$state = Join-Path $pkg "results\installed.json"
if (Get-Process -Name FF9 -ErrorAction SilentlyContinue) { throw "Close FINAL FANTASY IX first." }
if (-not (Test-Path $state)) { throw "Nothing to restore: results\installed.json not found." }
$s = Get-Content $state -Raw | ConvertFrom-Json
$stamp = Get-Date -Format yyyyMMdd-HHmmss
if (Test-Path $s.target) {
    $evidence = Join-Path $pkg "results\SavedData_ww.after-test-$stamp.dat"
    Copy-Item -Path $s.target -Destination $evidence
    Write-Host "Saved the game's file for analysis: $evidence"
    Remove-Item -Path $s.target
}
if ($s.backup -and (Test-Path $s.backup)) {
    Rename-Item -Path $s.backup -NewName "SavedData_ww.dat"
    Write-Host "Your original save is back in place."
}
Rename-Item -Path $state -NewName "installed.done-$stamp.json"
Write-Host "Done."
