# Restart FF9 and load a given slot/file using only guarded steps.
# Every confirm is checked by ff9_step.py (screen classification, title pointer double-check,
# cloud-screen abort). Exits non-zero if any guard aborts.
param([int]$File = 1, [int]$Up = 0, [string]$Shots, [string]$Launch)
$ErrorActionPreference = "Stop"
$step = Join-Path $PSScriptRoot "ff9_step.py"
function Step([string[]]$a) { python -P $step $Shots @a | Select-Object -Last 1; if ($LASTEXITCODE -ne 0) { throw "guard stopped at: $($a -join ' ')" } }
$p = Get-Process FF9 -ErrorAction SilentlyContinue
if ($p) { [void]$p.CloseMainWindow(); Start-Sleep -Seconds 4; if (-not $p.HasExited) { $p | Stop-Process }; Start-Sleep -Seconds 2 }
& $Launch | Out-Null
Step @("wait_title", "15")                       # Down only, until the title menu is recognised
Step @("title_load")
Step @("confirm", "save_slots,load_files")         # slot 1
Start-Sleep -Seconds 2
Step @("keys", "Up", "Up", "Up", "--wait", "1")    # FILE01 at the top of the list
for ($i = 1; $i -lt $File; $i++) { Step @("keys", "Down", "--wait", "0.4") }
Step @("snap", "file_selected_$File")
