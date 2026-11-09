# Lance VocalGuard Line Phone (modem USB local + casque).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $env:CONDA_DEFAULT_ENV) {
    $activate = Join-Path $env:USERPROFILE "miniconda3\Scripts\activate.bat"
    if (Test-Path -LiteralPath $activate) {
        cmd /c "call `"$activate`" vocalguard && cd /d `"$RepoRoot`" && python -m pip install -q -r desktop/requirements-studio.txt && python desktop/line_phone.py"
        exit $LASTEXITCODE
    }
}

python -m pip install -q -r desktop/requirements-studio.txt
python desktop/line_phone.py
exit $LASTEXITCODE
