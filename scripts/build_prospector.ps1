# Build VocalGuard Prospector (.exe Windows) + raccourci bureau optionnel
param(
    [string]$OutputDir = "dist",
    [switch]$DesktopShortcut
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $PSBoundParameters.ContainsKey("DesktopShortcut")) {
    $DesktopShortcut = $true
}

Write-Host "=== VocalGuard Prospector — build PyInstaller ==="

$iconPath = Join-Path $RepoRoot "desktop/assets/commercial_studio.ico"
$lineIcon = Join-Path $RepoRoot "desktop/assets/line_phone.ico"
$envExample = Join-Path $RepoRoot "desktop/prospector.env.example"
$cfgExample = Join-Path $RepoRoot "config/config.example.yaml"
$alembicIni = Join-Path $RepoRoot "desktop/prospector/alembic.ini"
$alembicDir = Join-Path $RepoRoot "desktop/prospector/alembic"

if (-not (Test-Path $iconPath)) {
    if (Test-Path $lineIcon) { $iconPath = $lineIcon }
    else { throw "Icone introuvable sous desktop/assets/" }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python introuvable."
}

& python -m pip install -q -r desktop/requirements-studio.txt

$distPath = Join-Path $RepoRoot $OutputDir
$workPath = Join-Path $RepoRoot "build/prospector"
if (Test-Path $workPath) { Remove-Item -Recurse -Force $workPath }

$addData = @(
    "${iconPath};desktop/assets"
)
if (Test-Path $lineIcon) {
    $addData += "${lineIcon};desktop/assets"
}
if (Test-Path $alembicIni) {
    $addData += "${alembicIni};desktop/prospector"
}
if (Test-Path $alembicDir) {
    $addData += "${alembicDir};desktop/prospector/alembic"
}
if (Test-Path $cfgExample) {
    $addData += "${cfgExample};config"
}

$pyArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--windowed",
    "--name", "VocalGuard-Prospector",
    "--icon", $iconPath,
    "--paths", $RepoRoot,
    "--distpath", $distPath,
    "--workpath", $workPath,
    "--specpath", (Join-Path $RepoRoot "build"),
    "--hidden-import=desktop.prospector.db.models",
    "--hidden-import=desktop.prospector.db.migrate",
    "--hidden-import=desktop.prospector.campaign_store",
    "--hidden-import=desktop.prospector.call_recorder",
    "--hidden-import=desktop.modem_local_call",
    "--hidden-import=desktop.audio_core",
    "--hidden-import=desktop.studio_ui_material",
    "--hidden-import=desktop.studio_env",
    "--hidden-import=backend.core.modem_handler",
    "--hidden-import=backend.core.config",
    "--hidden-import=logging.config",
    "--collect-submodules=sounddevice",
    "--collect-submodules=websockets"
)
foreach ($pair in $addData) {
    $pyArgs += "--add-data"
    $pyArgs += $pair
}
$pyArgs += "desktop/prospector/app.py"

& python @pyArgs

$exeDir = Join-Path $distPath "VocalGuard-Prospector"
$exe = Join-Path $exeDir "VocalGuard-Prospector.exe"
if (-not (Test-Path $exe)) {
    Write-Host "Echec build — voir build/prospector"
    exit 1
}

Write-Host ""
Write-Host "OK : $exe"

if (Test-Path $envExample) {
    Copy-Item $envExample (Join-Path $exeDir "prospector.env.example") -Force
    Write-Host "Exemple env : $(Join-Path $exeDir 'prospector.env.example')"
    $envLive = Join-Path $exeDir "prospector.env"
    if (-not (Test-Path $envLive)) {
        Copy-Item $envExample $envLive -Force
        Write-Host "prospector.env cree (ajoute PROSPECTLAB_TOKEN avant sync)"
    }
}
if (Test-Path $cfgExample) {
    $cfgDst = Join-Path $exeDir "config"
    New-Item -ItemType Directory -Force -Path $cfgDst | Out-Null
    Copy-Item $cfgExample (Join-Path $cfgDst "config.example.yaml") -Force
}

$launcher = Join-Path $exeDir "Lancer-Prospector.bat"
@"
@echo off
setlocal
cd /d "%~dp0"
echo Double-cliquez VocalGuard-Prospector.exe ou ce fichier.
start "" "%~dp0VocalGuard-Prospector.exe"
"@ | Set-Content -Encoding ASCII $launcher
Write-Host "Lanceur : $launcher"

if ($DesktopShortcut) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $lnk = Join-Path $desktop "VocalGuard Prospector.lnk"
    $WshShell = New-Object -ComObject WScript.Shell
    $sc = $WshShell.CreateShortcut($lnk)
    $sc.TargetPath = $exe
    $sc.WorkingDirectory = $exeDir
    $sc.IconLocation = "$iconPath,0"
    $sc.Description = "VocalGuard Prospector"
    $sc.Save()
    Write-Host "Raccourci bureau : $lnk"
}

Write-Host "Variables utiles (prospector.env a cote de l'exe) :"
Write-Host "  VG_VOICE_API=http://node14.lan:8000/api/v1"
Write-Host "  VG_PROSPECTOR_RECORD_CALLS=1"
Write-Host "  MODEM_COM=COM3"
