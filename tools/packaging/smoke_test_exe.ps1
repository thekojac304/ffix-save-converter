# Smoke-test the packaged ffix-convert.exe in an isolated folder (no Python involved). A one-file build is copied
# into the work folder; a folder build (with _internal next to it) is run where it is.
# Usage: pwsh -File smoke_test_exe.ps1 -Exe <path to ffix-convert.exe> -Work <empty folder> -Fixtures <fixtures dir>
# Needs PowerShell 7: Windows PowerShell 5.1 turns the expected error output of the refusal cases into a stop.
param([string]$Exe, [string]$Work, [string]$Fixtures)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $Work | Out-Null
if (Test-Path (Join-Path (Split-Path $Exe) "_internal")) {
  $Run = (Resolve-Path $Exe).Path
} else {
  Copy-Item $Exe (Join-Path $Work "ffix-convert.exe"); $Run = Join-Path $Work "ffix-convert.exe"
}
[IO.File]::WriteAllBytes((Join-Path $Work "notasave.dat"), [byte[]](1..200 | ForEach-Object { $_ }))
Copy-Item (Join-Path $Fixtures "ps1\originals\user_retroarch\user_Final_Fantasy_IX.srm") (Join-Path $Work "card.srm")
Copy-Item (Join-Path $Fixtures "pc\originals\repos\ff9SaveLib_testdata_SavedData_ww.dat") (Join-Path $Work "pc.dat")
$h0 = (Get-FileHash (Join-Path $Work "card.srm")).Hash; $h1 = (Get-FileHash (Join-Path $Work "pc.dat")).Hash
Push-Location $Work
$env:PYTHONPATH = ""; $env:PYTHONHOME = ""
$results = [ordered]@{}; $log = New-Object System.Text.StringBuilder

function Invoke-Case([string]$name, [int]$expect, [string[]]$argv) {
  $out = & $Run @argv 2>&1 | Out-String
  $code = $LASTEXITCODE
  [void]$log.AppendLine("> ffix-convert $($argv -join ' ')   [exit $code, expected $expect]")
  [void]$log.AppendLine($out)
  $results[$name] = if ($code -eq $expect) { "PASS" } else { "FAIL (exit $code)" }
}

Invoke-Case "version"            0 @("--version")
Invoke-Case "inspect PS1 card"   0 @("inspect", "card.srm")
Invoke-Case "inspect PC file"    0 @("inspect", "pc.dat")
Invoke-Case "PS1 -> PC"          0 @("convert", "card.srm", "--source", "13", "--out", "a.dat")
Invoke-Case "PC -> PS1"          0 @("convert", "pc.dat", "--source", "1/1", "--out", "b.mcr")
Invoke-Case "PS1->PC->PS1"       0 @("convert", "a.dat", "--out", "a_back.mcr")
Invoke-Case "verify PS1 rt"      0 @("verify", "card.srm", "a_back.mcr", "--source-slot", "13")
Invoke-Case "PC->PS1->PC"        0 @("convert", "b.mcr", "--out", "b_back.dat")
Invoke-Case "verify PC rt"       0 @("verify", "pc.dat", "b_back.dat", "--source-slot", "1/1")
Invoke-Case "into existing card" 0 @("convert", "pc.dat", "--source", "1/2", "--into", "b.mcr", "--dest", "2", "--out", "c.mcr")
Invoke-Case "batch card -> PC"   0 @("batch", "card.srm", "--out", "batch\SavedData_ww.dat")
Invoke-Case "batch PC -> cards"  0 @("batch", "pc.dat", "--out", "cards")
Invoke-Case "batch dry run"      0 @("batch", "pc.dat", "--dry-run", "--json")
Invoke-Case "batch needs approval to replace" 2 @("batch", "card.srm", "--into", "batch\SavedData_ww.dat", "--in-place", "--force", "--slot", "1")
Invoke-Case "recover: nothing to undo" 0 @("recover", "cards")
Invoke-Case "refuse overwrite"   2 @("convert", "card.srm", "--source", "13", "--out", "a.dat")
Invoke-Case "refuse in-place w/o force" 2 @("convert", "pc.dat", "--source", "1/2", "--into", "b.mcr", "--in-place", "--dest", "3")
Invoke-Case "invalid input"      2 @("inspect", "notasave.dat")
Invoke-Case "ambiguous source"   2 @("convert", "card.srm")
Invoke-Case "missing file"       2 @("inspect", "nope.mcr")
Pop-Location

$results["sources unchanged"] = if (((Get-FileHash (Join-Path $Work "card.srm")).Hash -eq $h0) -and ((Get-FileHash (Join-Path $Work "pc.dat")).Hash -eq $h1)) { "PASS" } else { "FAIL" }
$cardB = [IO.File]::ReadAllBytes((Join-Path $Work "b.mcr")); $cardC = [IO.File]::ReadAllBytes((Join-Path $Work "c.mcr"))
$same = $true; for ($i = 0x2000; $i -lt 0x4000; $i++) { if ($cardB[$i] -ne $cardC[$i]) { $same = $false; break } }
$results["unrelated block preserved"] = if ($same) { "PASS" } else { "FAIL" }
$log.ToString() | Out-File -Encoding utf8 (Join-Path $Work "smoke_log.txt")
$results.GetEnumerator() | ForEach-Object { "{0,-28} {1}" -f $_.Key, $_.Value }
$fail = @($results.Values | Where-Object { $_ -ne "PASS" }).Count
"`n$($results.Count - $fail) passed, $fail failed"
exit $fail
