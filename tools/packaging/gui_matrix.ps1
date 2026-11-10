# Check the packaged desktop app in light and dark themes, at several window sizes and Windows scale factors, and
# run scripted conversions (the app's --automate mode drives the real window) for the decisions a user can face.
#   pwsh -File gui_matrix.ps1 -App "<package folder>" -Work <empty folder> -Card15 <card> -Card13 <card> -Pc <PC file>
#        [-Memoria <fixtures\memoria\runtime_20261106>]
# Writes <Work>\matrix.json and a screenshot per case; prints PASS/FAIL lines.
param([string]$App, [string]$Work, [string]$Card15, [string]$Card13, [string]$Pc, [string]$Memoria = "")
$ErrorActionPreference = "Stop"
$Exe = Join-Path $App "FFIX Save Converter.exe"
$Cli = Join-Path $App "ffix-convert.exe"
New-Item -ItemType Directory -Force $Work | Out-Null
$results = [ordered]@{}
function Check($name, $ok, $detail = "") { $results[$name] = if ($ok) { "PASS" } else { "FAIL $detail" } }

function Run-Gui([string[]]$argv, [hashtable]$envs = @{}) {
  $old = @{}
  foreach ($k in $envs.Keys) { $old[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $envs[$k]) }
  try {
    $p = Start-Process -FilePath $Exe -ArgumentList $argv -PassThru -Wait
    return $p.ExitCode
  } finally {
    foreach ($k in $envs.Keys) { [Environment]::SetEnvironmentVariable($k, $old[$k]) }
  }
}

# --- appearance: theme x size x scale --------------------------------------------------------------------------
$card = Join-Path $Work "card15.srm"; Copy-Item $Card15 $card
foreach ($theme in "light", "dark") {
  foreach ($size in "520x460", "800x780", "1280x1000") {
    foreach ($scale in "1", "1.25", "1.5", "2") {
      $name = "$theme-$size-x$scale"
      $res = Join-Path $Work "smoke-$name.json"
      Run-Gui @("--smoke", "`"$res`"", "--theme", $theme, "--size", $size, "`"$card`"") @{ QT_SCALE_FACTOR = $scale } | Out-Null
      if (-not (Test-Path $res)) { Check "appearance $name" $false "no result"; continue }
      $j = Get-Content $res -Raw | ConvertFrom-Json
      $okTheme = ($j.dark -eq ($theme -eq "dark"))
      $okLayout = (@($j.layout_problems).Count -eq 0)
      Check "appearance $name" ($okTheme -and $okLayout -and $j.convert_enabled) ("dark=$($j.dark) dpr=$($j.dpr) problems=$(@($j.layout_problems) -join '; ')")
    }
  }
}

# --- scripted decisions ------------------------------------------------------------------------------------------------
function Run-Job([string]$name, [hashtable]$job) {
  $job.result = Join-Path $Work "job-$name.json"
  $job.screenshot = Join-Path $Work "job-$name.png"
  $job.settings = Join-Path $Work "job-$name.ini"
  $jf = Join-Path $Work "job-$name-in.json"
  $job | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $jf
  Run-Gui @("--automate", "`"$jf`"") | Out-Null
  return Get-Content $job.result -Raw | ConvertFrom-Json
}

# replacing occupied PC places needs the explicit tick, and makes a verified backup
$d = Join-Path $Work "replace"; New-Item -ItemType Directory -Force $d | Out-Null
$pcR = Join-Path $d "SavedData_ww.dat"; Copy-Item $Pc $pcR; $h = (Get-FileHash $pcR).Hash
$c13 = Join-Path $d "card13.srm"; Copy-Item $Card13 $c13
$r = Run-Job "replace-refused" @{ source = $c13; dest = "existing"; into = $pcR; advanced = @{ pc_slot = 2 } }
Check "occupied slot: Convert stays disabled without approval" (-not $r.convert_enabled -and $r.warnings -match "replace")
Check "occupied slot: file unchanged without approval" ((Get-FileHash $pcR).Hash -eq $h)
$r = Run-Job "replace-approved" @{ source = $c13; dest = "existing"; into = $pcR; advanced = @{ pc_slot = 2 }; replace = $true }
Check "occupied slot: replaced after approval" ($r.ok -and $r.backups[0] -and (Get-FileHash $r.backups[0]).Hash -eq $h)

# one damaged save: the window offers to leave it out and converts the rest
$d = Join-Path $Work "damaged"; New-Item -ItemType Directory -Force $d | Out-Null
$bytes = [IO.File]::ReadAllBytes($Card13); $bytes[4 * 8192 + 0x400] = $bytes[4 * 8192 + 0x400] -bxor 0xFF
$bad = Join-Path $d "damaged.srm"; [IO.File]::WriteAllBytes($bad, $bytes)
$r = Run-Job "damaged-refused" @{ source = $bad; out_folder = (Join-Path $d "out") }
Check "damaged save: explained and Convert disabled" (-not $r.convert_enabled -and $r.problems -match "FILE04 looks damaged")
$r = Run-Job "damaged-left-out" @{ source = $bad; out_folder = (Join-Path $d "out"); leave_out_problems = $true }
Check "damaged save: the other 12 convert" ($r.ok -and $r.convert_text -eq "&Convert 12 saves")

# cancel before the write: nothing is written
$d = Join-Path $Work "cancel"; New-Item -ItemType Directory -Force $d | Out-Null
$r = Run-Job "cancel" @{ source = $card; out_folder = (Join-Path $d "out"); cancel = $true }
Check "cancel: nothing written" ((-not $r.ok) -and $r.result_text -match "Nothing was changed" -and -not (Test-Path (Join-Path $d "out\card15 (PC save)")))

# Memoria: a damaged sidecar blocks until lossy conversion is chosen in Advanced
if ($Memoria -and (Test-Path (Join-Path $Memoria "sidecar_cases"))) {
  $d = Join-Path $Work "memoria"; Copy-Item -Recurse (Join-Path $Memoria "sidecar_cases") $d
  $src = Join-Path $d "SavedData_ww.dat"
  $r = Run-Job "memoria-refused" @{ source = $src; out_folder = (Join-Path $Work "memoria-out") }
  Check "Memoria: damaged data file blocks the batch" (-not $r.convert_enabled -and $r.problems -match "damaged Memoria data file")
  $r = Run-Job "memoria-lossy" @{ source = $src; out_folder = (Join-Path $Work "memoria-out"); advanced = @{ lossy = $true } }
  Check "Memoria: lossy conversion converts all 5" ($r.ok -and $r.convert_text -eq "&Convert 5 saves")
  if ($r.ok) {
    $cardOut = $r.outputs[0]
    $bad = 0; foreach ($n in 1, 2, 3, 5) { & $Cli verify $src $cardOut --source-slot "1/$n" --converted-slot $n | Out-Null; if ($LASTEXITCODE -ne 0) { $bad++ } }
    Check "Memoria: sidecar-reconciled saves verify with the CLI" ($bad -eq 0)
  }
}

$results | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Work "matrix.json")
$results.GetEnumerator() | ForEach-Object { "{0,-58} {1}" -f $_.Key, $_.Value }
$fail = @($results.Values | Where-Object { $_ -ne "PASS" }).Count
"`n$($results.Count - $fail) passed, $fail failed"
