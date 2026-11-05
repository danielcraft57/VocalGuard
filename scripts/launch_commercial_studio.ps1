# Lance Commercial Studio (dev). Ctrl+C ferme sans question O/N de cmd.
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$env:VG_STT_URL = "http://node15.lan:8100"
$env:VG_VOICE_API = "http://node14.lan:8000/api/v1"

if (-not $env:CONDA_DEFAULT_ENV) {
    $activate = Join-Path $env:USERPROFILE "miniconda3\Scripts\activate.bat"
    if (Test-Path -LiteralPath $activate) {
        cmd /c "call `"$activate`" vocalguard && cd /d `"$RepoRoot`" && python desktop/outbound_studio.py"
        exit $LASTEXITCODE
    }
}

python -m pip install -q -r desktop/requirements-studio.txt 2>$null
python desktop/outbound_studio.py
exit $LASTEXITCODE
