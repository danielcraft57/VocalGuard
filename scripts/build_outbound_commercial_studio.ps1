# Build VocalGuard Commercial Studio (.exe Windows)
param(
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "=== VocalGuard Commercial Studio — build PyInstaller ==="

$iconPath = Join-Path $RepoRoot "desktop/assets/commercial_studio.ico"
$envExample = Join-Path $RepoRoot "desktop/studio.env.example"
$iconGen = Join-Path $RepoRoot "desktop/assets/generate_studio_icon.py"
if (Test-Path $iconGen) {
    & python $iconGen
}
if (-not (Test-Path $iconPath)) {
    throw "Icone introuvable: $iconPath"
}

$pip = "pip"
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m pip install -q -r desktop/requirements-studio.txt
} else {
    throw "Python introuvable."
}

$distPath = Join-Path $RepoRoot $OutputDir
$workPath = Join-Path $RepoRoot "build/outbound_studio"
if (Test-Path $workPath) { Remove-Item -Recurse -Force $workPath }

& python -m PyInstaller `
    --noconfirm `
    --windowed `
    --name "VocalGuard-Commercial-Studio" `
    --icon $iconPath `
    --add-data "${iconPath};desktop/assets" `
    --paths $RepoRoot `
    --distpath $distPath `
    --workpath $workPath `
    --specpath (Join-Path $RepoRoot "build") `
    --hidden-import=desktop.commercial_pipeline `
    --hidden-import=desktop.audio_core `
    --hidden-import=desktop.live_listen `
    --hidden-import=desktop.speech_gate `
    --hidden-import=desktop.studio_recording `
    --hidden-import=desktop.studio_ui_material `
    --hidden-import=backend.voice.turn_vad `
    --collect-submodules=sounddevice `
    desktop/outbound_studio.py

$exe = Join-Path $distPath "VocalGuard-Commercial-Studio/VocalGuard-Commercial-Studio.exe"
if (Test-Path $exe) {
    Write-Host ""
    Write-Host "OK : $exe"
    $launcher = Join-Path (Split-Path $exe) "Lancer-Commercial-Studio.bat"
    $psHelper = Join-Path (Split-Path $exe) "run_gui_wait_ctrl_c.ps1"
    Copy-Item (Join-Path $RepoRoot "scripts/run_gui_wait_ctrl_c.ps1") $psHelper -Force
    @"
@echo off
setlocal
cd /d "%~dp0"
set VG_STT_URL=http://node15.lan:8100
set VG_VOICE_API=http://node14.lan:8000/api/v1
REM set VG_STT_TOKEN=votre_token
echo Ctrl+C ici ferme le Commercial Studio.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_gui_wait_ctrl_c.ps1" -ExePath "%~dp0VocalGuard-Commercial-Studio.exe"
exit /b %ERRORLEVEL%
"@ | Set-Content -Encoding ASCII $launcher
    Write-Host "Lanceur : $launcher"
    if (Test-Path $envExample) {
        Copy-Item $envExample (Join-Path (Split-Path $exe) "studio.env.example") -Force
    }
    Write-Host "Variables utiles au lancement (raccourci ou .env local) :"
    Write-Host "  VG_STT_URL=http://node15.lan:8100"
    Write-Host "  VG_VOICE_API=http://node14.lan:8000/api/v1"
    Write-Host "  VG_STT_TOKEN=<STT_INTERNAL_TOKEN>"
} else {
    Write-Host "Echec build — voir build/outbound_studio"
    exit 1
}
