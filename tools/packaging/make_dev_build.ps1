# Build the Windows x64 development package (desktop app + command line) into release/ (local only).
# Usage: pwsh -File tools/packaging/make_dev_build.ps1 [-Work <scratch dir>] [-Label <suffix>]
param([string]$Work = (Join-Path $env:TEMP "ffix-dev-build"), [string]$Label = "")
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Version = (python -P -c "import sys; sys.path.insert(0, r'$Root\src'); import ffix_conv; print(ffix_conv.__version__)").Trim()
$Name = "FFIX-Save-Converter-$Version-win-x64"
$Rel = Join-Path $Root ("release\v$Version" + $(if ($Label) { "-$Label" } else { "" }))
$Stage = Join-Path $Rel $Name
if (Test-Path $Rel) { throw "$Rel already exists; remove it yourself to rebuild" }

python -m PyInstaller (Join-Path $PSScriptRoot "ffix-save-converter.spec") --distpath (Join-Path $Work "dist") --workpath (Join-Path $Work "work") --noconfirm --clean 2>&1 | Select-Object -Last 1
New-Item -ItemType Directory -Force $Rel | Out-Null
Copy-Item -Recurse (Join-Path $Work "dist\FFIX Save Converter") $Stage
Copy-Item (Join-Path $Root "LICENSE") (Join-Path $Stage "LICENSE.txt")
foreach ($d in "README.md", "COMPATIBILITY.md", "CHANGELOG.md", "TESTING.md", "NOTICES.md") { Copy-Item (Join-Path $Root $d) $Stage }
foreach ($d in "GUI_GUIDE.md", "BATCH.md") { Copy-Item (Join-Path $Root "docs\$d") $Stage }

$help = @()
foreach ($a in @(@("--help"), @("inspect", "--help"), @("convert", "--help"), @("verify", "--help"))) {
  $help += "> ffix-convert $($a -join ' ')"; $help += (& (Join-Path $Stage "ffix-convert.exe") @a | Out-String); $help += ""
}
$help -join "`r`n" | Out-File -Encoding utf8 (Join-Path $Stage "COMMAND-LINE.txt")

# third-party license texts
$L = Join-Path $Stage "THIRD_PARTY_LICENSES"
New-Item -ItemType Directory -Force $L | Out-Null
Copy-Item (Join-Path $Root "research\repos\Albeoris_Memoria\LICENSE") (Join-Path $L "Memoria-MIT.txt")
Copy-Item (Join-Path $Root "research\repos\nintendogamer15_ffix-save-editor\LICENSE") (Join-Path $L "ffix-save-editor-MIT.txt")
Copy-Item (Join-Path $PSScriptRoot "third_party\*") $L
$py = python -c "import sys,os;print(os.path.join(sys.base_prefix,'LICENSE.txt'))"
Copy-Item $py (Join-Path $L "Python-LICENSE.txt")
$files = python -c "import importlib.metadata as m,os
for d,pre in (('cryptography','cryptography-'),('cffi','cffi-'),('pyinstaller','PyInstaller-')):
    dist=m.distribution(d)
    for f in dist.files or []:
        s=str(f)
        if 'licenses' in s.replace(os.sep,'/') and s.split('/')[-1].upper().startswith(('LICENSE','COPYING')):
            print(pre+s.split('/')[-1]+'|'+str(dist.locate_file(f)))"
foreach ($line in $files) { $n, $p = $line -split "\|", 2; $dest = $n; if ($dest -notmatch "\.txt$") { $dest += ".txt" }; Copy-Item $p (Join-Path $L $dest) }

# safety: no saves, discs, screenshots or personal data; license present
$bad = Get-ChildItem $Stage -Recurse -File | Where-Object { $_.Extension -match '^\.(mcr|mcd|srm|gme|psv|mcs|vmp|dat|sav|bin|cue|chd|iso|m3u|png|jpg|jpeg|bmp|gif)$' }
if ($bad) { throw "forbidden files in package: $($bad.FullName -join ', ')" }
foreach ($need in "LICENSE.txt", "FFIX Save Converter.exe", "ffix-convert.exe", "THIRD_PARTY_LICENSES\LGPL-3.0.txt") {
  if (-not (Test-Path (Join-Path $Stage $need))) { throw "$need missing from package" }
}
$leak = Get-ChildItem $Stage -Recurse -File -Include *.txt, *.md | Select-String -Pattern ([regex]::Escape($env:USERNAME)) -List
if ($leak) { throw "local user name found in: $($leak.Path -join ', ')" }

$Zip = Join-Path $Rel "$Name.zip"
Compress-Archive -Path $Stage -DestinationPath $Zip
$lines = @()
foreach ($f in @($Zip, (Join-Path $Stage "FFIX Save Converter.exe"), (Join-Path $Stage "ffix-convert.exe"))) {
  $lines += "$((Get-FileHash $f -Algorithm SHA256).Hash.ToLower())  $([IO.Path]::GetFileName($f))"
}
$lines -join "`n" | Out-File -Encoding ascii (Join-Path $Rel "SHA256SUMS.txt")
Get-Content (Join-Path $Rel "SHA256SUMS.txt")
$size = (Get-ChildItem $Stage -Recurse -File | Measure-Object Length -Sum).Sum
"folder: {0:N1} MB in {1} files; zip: {2:N1} MB" -f ($size / 1MB), (Get-ChildItem $Stage -Recurse -File).Count, ((Get-Item $Zip).Length / 1MB)
