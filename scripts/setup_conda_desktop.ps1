# Cree / met a jour l'env conda vocalguard-desktop (GUI Line Phone + Studio).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$EnvName = "vocalguard-desktop"
$ReqPhone = Join-Path $RepoRoot "desktop\requirements-line-phone.txt"
$ReqStudio = Join-Path $RepoRoot "desktop\requirements-studio.txt"

Write-Host "Creation / verification de l'environnement conda $EnvName (Python 3.12)..."

$exists = $false
$envList = conda env list
foreach ($line in $envList) {
    if ($line -match "^$EnvName\s") {
        $exists = $true
        break
    }
}

if (-not $exists) {
    conda create -n $EnvName python=3.12 -y
}

Write-Host "Installation des paquets pip (Line Phone + Studio)..."
conda run -n $EnvName python -m pip install --upgrade pip
conda run -n $EnvName python -m pip install -r $ReqPhone
conda run -n $EnvName python -m pip install -r $ReqStudio

Write-Host "OK. Lance ensuite : scripts\launch_line_phone.ps1"
Write-Host "Ou : conda activate $EnvName puis python desktop\line_phone.py"
