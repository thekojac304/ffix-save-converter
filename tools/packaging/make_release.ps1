# Build the v0.1.0-beta Windows x64 release candidate into release/ (local only; nothing is uploaded).
# Usage: powershell -File tools/packaging/make_release.ps1 [-Work <scratch dir>]
param([string]$Work = (Join-Path $env:TEMP "ffix-release-build"), [string]$Label = "")
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Version = "0.1.0-beta"
$Name = "ffix-convert-$Version-win-x64"
$Rel = Join-Path $Root ("release\v$Version" + $(if ($Label) { "-$Label" } else { "" }))
$Stage = Join-Path $Rel $Name
if (Test-Path $Rel) { throw "$Rel already exists; remove it yourself to rebuild" }

python -m PyInstaller (Join-Path $Root "tools\packaging\ffix-convert.spec") --distpath (Join-Path $Work "dist") --workpath (Join-Path $Work "work") --noconfirm --clean 2>&1 | Select-Object -Last 1
New-Item -ItemType Directory -Force (Join-Path $Stage "THIRD_PARTY_LICENSES") | Out-Null
Copy-Item (Join-Path $Work "dist\ffix-convert.exe") $Stage
foreach ($d in "LICENSE", "README.md", "COMPATIBILITY.md", "CHANGELOG.md", "TESTING.md", "NOTICES.md") { Copy-Item (Join-Path $Root $d) $Stage }
Rename-Item (Join-Path $Stage "LICENSE") "LICENSE.txt"

# usage text straight from the built executable
$help = @()
foreach ($a in @(@("--help"), @("inspect", "--help"), @("convert", "--help"), @("verify", "--help"))) {
  $help += "> ffix-convert $($a -join ' ')"; $help += (& (Join-Path $Stage "ffix-convert.exe") @a | Out-String); $help += ""
}
$help -join "`r`n" | Out-File -Encoding utf8 (Join-Path $Stage "USAGE.txt")

# third-party license texts
$L = Join-Path $Stage "THIRD_PARTY_LICENSES"
Copy-Item (Join-Path $Root "research\repos\Albeoris_Memoria\LICENSE") (Join-Path $L "Memoria-MIT.txt")
Copy-Item (Join-Path $Root "research\repos\nintendogamer15_ffix-save-editor\LICENSE") (Join-Path $L "ffix-save-editor-MIT.txt")
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

# safety: no save files, discs, screenshots, or personal data in the package
$bad = Get-ChildItem $Stage -Recurse -File | Where-Object { $_.Extension -match '^\.(mcr|mcd|srm|gme|psv|mcs|vmp|dat|sav|bin|cue|chd|iso|m3u|png|jpg|jpeg|bmp|gif)$' }
if ($bad) { throw "forbidden files in package: $($bad.Name -join ', ')" }
if (-not (Test-Path (Join-Path $Stage "LICENSE.txt"))) { throw "LICENSE.txt missing from package" }
$leak = Get-ChildItem $Stage -Recurse -File -Include *.txt, *.md | Select-String -Pattern ([regex]::Escape($env:USERNAME)) -List
if ($leak) { throw "local user name found in: $($leak.Path -join ', ')" }

$Zip = Join-Path $Rel "$Name.zip"
Compress-Archive -Path $Stage -DestinationPath $Zip
$lines = @()
foreach ($f in @($Zip, (Join-Path $Stage "ffix-convert.exe"))) { $lines += "$((Get-FileHash $f -Algorithm SHA256).Hash.ToLower())  $([IO.Path]::GetFileName($f))" }
$lines -join "`n" | Out-File -Encoding ascii (Join-Path $Rel "SHA256SUMS.txt")
Get-Content (Join-Path $Rel "SHA256SUMS.txt")
Get-ChildItem $Stage -Recurse -File | Select-Object @{n="file";e={$_.FullName.Substring($Stage.Length + 1)}}, Length | Format-Table -AutoSize | Out-String
