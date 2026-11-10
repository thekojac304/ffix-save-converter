# Test the packaged desktop app (v0.3) through Windows UI Automation, the interface screen readers use.
# Run with Windows PowerShell 5.1 (it ships the UI Automation client):
#   powershell -File smoke_test_gui.ps1 -App "<package folder>" -Work <empty folder> -Card15 <15-save card>
#              -Card13 <13-save card> -Pc <PC SavedData_ww.dat with several saves>
# Every case starts the real exe with its own settings file and output folder, works only through accessible
# controls (names, ValuePattern, SelectionItemPattern, InvokePattern), and checks the files it wrote with the
# packaged command line.
param([string]$App, [string]$Work, [string]$Card15, [string]$Card13, [string]$Pc)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$AE = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]
$CT = [System.Windows.Automation.ControlType]
$results = [ordered]@{}
$Cli = Join-Path $App "ffix-convert.exe"

function Wait-For([scriptblock]$cond, [int]$seconds = 30) {
  $end = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $end) { $r = & $cond; if ($r) { return $r }; Start-Sleep -Milliseconds 250 }
  return $null
}
function Find-Typed($root, $type, [string]$name) {
  if (-not $root) { return $null }
  $c = New-Object System.Windows.Automation.AndCondition(
    (New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty, $type)),
    (New-Object System.Windows.Automation.PropertyCondition($AE::NameProperty, $name)))
  return $root.FindFirst($TS::Descendants, $c)
}
function Find-Like($root, [string]$pattern) {
  if (-not $root) { return $null }
  foreach ($e in $root.FindAll($TS::Descendants, [System.Windows.Automation.Condition]::TrueCondition)) {
    if ($e.Current.Name -like $pattern) { return $e }
  }
  return $null
}
function Invoke($e) { $e.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
function Check($name, $ok) { $results[$name] = if ($ok) { "PASS" } else { "FAIL" } }

function Start-App([string]$label, [string]$file, [string]$out) {
  $ini = Join-Path $Work "$label.ini"
  $p = Start-Process -FilePath (Join-Path $App "FFIX Save Converter.exe") -PassThru `
       -ArgumentList "--settings `"$ini`" --out-folder `"$out`" `"$file`""
  $procId = [int]$p.Id
  $get = { $c = New-Object System.Windows.Automation.PropertyCondition(
             [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $procId)
           [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
             [System.Windows.Automation.TreeScope]::Children, $c) }.GetNewClosure()
  $win = Wait-For $get 40
  Check "$label window opens" ($win -and $win.Current.Name -eq "FFIX Save Converter")
  return @{ p = $p; get = $get }
}
function Close-App($label, $a) {
  $win = & $a.get
  if ($win) { $win.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern).Close() }
  Check "$label closes cleanly" (Wait-For { $a.p.HasExited } 20)
  if (-not $a.p.HasExited) { $a.p | Stop-Process -Force }
}
function Convert-Button($a, [string]$name, [int]$seconds = 60) {
  return Wait-For { $w = & $a.get; if ($w) { $b = Find-Typed $w $CT::Button $name; if ($b -and $b.Current.IsEnabled) { $b } } } $seconds
}
function Dump($a, $label) {
  $w = & $a.get
  if ($w) { foreach ($e in $w.FindAll($TS::Descendants, (New-Object System.Windows.Automation.PropertyCondition($AE::ControlTypeProperty, $CT::Text)))) {
    Write-Output "  [$label] $($e.Current.Name)" } }
}

New-Item -ItemType Directory -Force $Work | Out-Null

# --- A: a full PS1 memory card into a new PC save file ----------------------------------------------------------
$dA = Join-Path $Work "A"; New-Item -ItemType Directory -Force $dA | Out-Null
$cA = Join-Path $dA "card15.srm"; Copy-Item $Card15 $cA; $hA = (Get-FileHash $cA).Hash
$a = Start-App "A" $cA (Join-Path $dA "out")
try {
  $w = & $a.get
  Check "A lists 15 saves" (Wait-For { Find-Like (& $a.get) "*15 Final Fantasy IX saves (FILE01*FILE15)*" } 60)
  Check "A convert-all is the default" ((Find-Typed (& $a.get) $CT::RadioButton "Convert all 15 saves").GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Current.IsSelected)
  Check "A placement shown" (Wait-For { Find-Like (& $a.get) "They go into slot 1, files 1*15." } 60)
  $b = Convert-Button $a "Convert 15 saves"
  Check "A Convert enabled" $b
  if ($b) {
    Invoke $b
    $done = Wait-For { Find-Like (& $a.get) "*15 saves converted and checked*" } 90
    Check "A converts and verifies" $done
    if (-not $done) { Dump $a "A" }
    $out = Join-Path $dA "out\card15 (PC save)\SavedData_ww.dat"
    Check "A output written" (Test-Path $out)
    if (Test-Path $out) {
      $j = & $Cli inspect $out --json | Out-String | ConvertFrom-Json
      Check "A output has slot 1 files 1-15" ((($j.saves | ForEach-Object { $_.id }) -join ",") -eq ((1..15 | ForEach-Object { "1/$_" }) -join ","))
      $bad = 0; foreach ($n in 1..15) { & $Cli verify $cA $out --source-slot $n --converted-slot "1/$n" | Out-Null; if ($LASTEXITCODE -ne 0) { $bad++ } }
      Check "A every save verifies with the CLI" ($bad -eq 0)
    }
  }
} finally { Close-App "A" $a }
Check "A source unchanged" ((Get-FileHash $cA).Hash -eq $hA)

# --- B: add a 13-save card to an existing PC save file (in place, backup first) ------------------------------------
$dB = Join-Path $Work "B"; New-Item -ItemType Directory -Force (Join-Path $dB "pc") | Out-Null
$cB = Join-Path $dB "card13.srm"; Copy-Item $Card13 $cB
$pB = Join-Path $dB "pc\SavedData_ww.dat"; Copy-Item $Pc $pB; $hB = (Get-FileHash $pB).Hash
$before = (& $Cli inspect $pB --json | Out-String | ConvertFrom-Json).saves.Count
$a = Start-App "B" $cB (Join-Path $dB "out")
try {
  $r = Wait-For { Find-Typed (& $a.get) $CT::RadioButton "Add to my existing PC save" } 60
  Check "B existing-file choice offered" $r
  $r.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
  $e = Wait-For { Find-Typed (& $a.get) $CT::Edit "Existing file" } 20
  $e.SetFocus()
  $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($pB)
  $r.SetFocus()                                                   # leaving the field confirms the path
  $b = Convert-Button $a "Convert 13 saves"
  Check "B Convert enabled" $b
  Check "B says existing saves are kept" (Find-Like (& $a.get) "*$before saves already in the file are kept*")
  if ($b) {
    Invoke $b
    $done = Wait-For { Find-Like (& $a.get) "*13 saves converted and checked*" } 90
    Check "B converts and verifies" $done
    if (-not $done) { Dump $a "B" }
    $after = (& $Cli inspect $pB --json | Out-String | ConvertFrom-Json).saves.Count
    Check "B file holds old and new saves" ($after -eq $before + 13)
    $bak = Get-ChildItem (Join-Path $dB "pc") -Filter "SavedData_ww.dat.bak-*" | Select-Object -First 1
    Check "B verified backup of the previous file" ($bak -and (Get-FileHash $bak.FullName).Hash -eq $hB)
  }
} finally { Close-App "B" $a }

# --- C: a PC file with more than 15 saves into several PS1 memory cards -------------------------------------------
$dC = Join-Path $Work "C"; New-Item -ItemType Directory -Force $dC | Out-Null
$big = Join-Path $dC "big\SavedData_ww.dat"
& $Cli batch $Card15 --out $big | Out-Null
& $Cli batch $Card13 --into $big --in-place --force | Out-Null
Check "C 28-save PC file prepared with the CLI" ((& $Cli inspect $big --json | Out-String | ConvertFrom-Json).saves.Count -eq 28)
$a = Start-App "C" $big (Join-Path $dC "out")
try {
  Check "C plans two memory cards" (Wait-For { Find-Like (& $a.get) "They fill 2 new memory cards*" } 60)
  $b = Convert-Button $a "Convert 28 saves"
  Check "C Convert enabled" $b
  if ($b) {
    Invoke $b
    $done = Wait-For { Find-Like (& $a.get) "*28 saves converted and checked*" } 120
    Check "C converts and verifies" $done
    $folder = Join-Path $dC "out\SavedData_ww (PS1 memory cards)"
    $names = (Get-ChildItem $folder -File | ForEach-Object { $_.Name } | Sort-Object) -join ","
    Check "C two cards and a manifest" ($names -eq "conversion-manifest.json,conversion-manifest.txt,FFIX-PS1-Card-01.mcr,FFIX-PS1-Card-02.mcr")
    $n1 = (& $Cli inspect (Join-Path $folder "FFIX-PS1-Card-01.mcr") --json | Out-String | ConvertFrom-Json).saves.Count
    $n2 = (& $Cli inspect (Join-Path $folder "FFIX-PS1-Card-02.mcr") --json | Out-String | ConvertFrom-Json).saves.Count
    Check "C cards hold 15 + 13 saves" ($n1 -eq 15 -and $n2 -eq 13)
    & $Cli verify $big (Join-Path $folder "FFIX-PS1-Card-02.mcr") --source-slot "2/13" --converted-slot 13 | Out-Null
    Check "C last save verifies with the CLI" ($LASTEXITCODE -eq 0)
  }
} finally { Close-App "C" $a }

# --- D: keyboard only: Alt+C converts, Alt+M goes back ---------------------------------------------------------------
Add-Type -AssemblyName System.Windows.Forms
$dD = Join-Path $Work "D"; New-Item -ItemType Directory -Force $dD | Out-Null
$cD = Join-Path $dD "card13.srm"; Copy-Item $Card13 $cD
$a = Start-App "D" $cD (Join-Path $dD "out")
try {
  $b = Convert-Button $a "Convert 13 saves"
  Check "D Convert button is keyboard-focusable" ($b -and $b.Current.IsKeyboardFocusable)
  (& $a.get).SetFocus()
  Start-Sleep -Milliseconds 500
  [System.Windows.Forms.SendKeys]::SendWait("%c")
  $done = Wait-For { Find-Like (& $a.get) "*13 saves converted and checked*" } 90
  Check "D Alt+C converts" $done
  if ($done) {
    Start-Sleep -Milliseconds 500; (& $a.get).SetFocus(); Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait("%m")
    Check "D Alt+M returns to the steps" (Wait-For { Find-Typed (& $a.get) $CT::Button "Convert 13 saves" } 30)
  }
} finally { Close-App "D" $a }

$results.GetEnumerator() | ForEach-Object { "{0,-44} {1}" -f $_.Key, $_.Value }
$fail = @($results.Values | Where-Object { $_ -ne "PASS" }).Count
"`n$($results.Count - $fail) passed, $fail failed"
