# Script de deploiement de VocalGuard sur Raspberry Pi (PowerShell)
# Synchronise le code sans detruire venv, .env, logs ni recordings.

$ErrorActionPreference = "Stop"

if (-not $env:RPI_HOST -or $env:RPI_HOST.Trim() -eq "") {
    $RPI_HOST = Read-Host "Entrez l'utilisateur et l'hote du Raspberry Pi (ex: pi@raspberrypi.local)"
} else {
    $RPI_HOST = $env:RPI_HOST
}

$RPI_DIR = "~/VocalGuard"
$PROJECT_DIR = (Get-Item (Split-Path -Parent $PSScriptRoot)).FullName

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Deploiement VocalGuard sur Raspberry Pi" -ForegroundColor Cyan
Write-Host "Hote: $RPI_HOST" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# [1] Connexion SSH
Write-Host "[1/6] Verification de la connexion SSH..." -ForegroundColor Yellow
$sshTest = ssh -o ConnectTimeout=5 "$RPI_HOST" "echo OK" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Impossible de se connecter a $RPI_HOST" -ForegroundColor Red
    Write-Host "  Verifiez: Pi allume, SSH active, cle SSH (ssh-copy-id $RPI_HOST)" -ForegroundColor Yellow
    exit 1
}
Write-Host "Connexion SSH OK" -ForegroundColor Green
Write-Host ""

# [2] Creer le repertoire distant sans rien supprimer (preserve venv, .env, logs)
Write-Host "[2/6] Repertoire distant..." -ForegroundColor Yellow
ssh "$RPI_HOST" "mkdir -p $RPI_DIR"
$venvExists = ssh "$RPI_HOST" "test -d $RPI_DIR/venv && echo yes || echo no"
if ($venvExists -eq "yes") {
    Write-Host "  $RPI_DIR existe, venv conserve" -ForegroundColor Gray
} else {
    Write-Host "  $RPI_DIR cree (premier deploiement)" -ForegroundColor Gray
}
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# [3] Python / pip (verification rapide, pas d'install si deja la)
Write-Host "[3/6] Python et pip..." -ForegroundColor Yellow
$pyVer = ssh "$RPI_HOST" "python3 --version 2>&1"
if (-not $pyVer) {
    Write-Host "Python3 absent sur le Pi" -ForegroundColor Red
    exit 1
}
$pipOk = ssh "$RPI_HOST" "python3 -m pip --version 2>&1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installation de pip..." -ForegroundColor Gray
    ssh "$RPI_HOST" "sudo apt-get update -qq && sudo apt-get install -y python3-pip" | Out-Null
}
Write-Host "  $pyVer, pip OK" -ForegroundColor Gray
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# [4] Venv : creer uniquement s'il n'existe pas
Write-Host "[4/6] Environnement virtuel..." -ForegroundColor Yellow
if ($venvExists -eq "no") {
    ssh "$RPI_HOST" "cd $RPI_DIR && python3 -m venv venv"
    Write-Host "  venv cree" -ForegroundColor Gray
} else {
    Write-Host "  venv existant conserve" -ForegroundColor Gray
}
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# [5] Sync fichiers (tar + scp) en excluant ce qu'on preserve
Write-Host "[5/6] Synchronisation des fichiers..." -ForegroundColor Yellow
$tempArchive = "$env:TEMP\vocalguard_deploy.tar.gz"
$tarCmd = Get-Command tar -ErrorAction SilentlyContinue
if (-not $tarCmd) {
    Write-Host "  tar requis (Git pour Windows ou WSL)" -ForegroundColor Red
    exit 1
}

Push-Location $PROJECT_DIR
try {
    tar -czf $tempArchive `
        --exclude=venv `
        --exclude=__pycache__ `
        --exclude=.git `
        --exclude=node_modules `
        --exclude=frontend/.next `
        --exclude=frontend/out `
        --exclude=audio_cache `
        --exclude=logs `
        --exclude=recordings `
        --exclude=*.db `
        --exclude=.env `
        .
} finally {
    Pop-Location
}

if (-not (Test-Path $tempArchive)) {
    Write-Host "  Echec creation archive" -ForegroundColor Red
    exit 1
}

scp -q $tempArchive "${RPI_HOST}:${RPI_DIR}/vocalguard_deploy.tar.gz"
if ($LASTEXITCODE -ne 0) {
    Remove-Item $tempArchive -ErrorAction SilentlyContinue
    Write-Host "  Echec transfert scp" -ForegroundColor Red
    exit 1
}

ssh "$RPI_HOST" "cd $RPI_DIR && tar -xzf vocalguard_deploy.tar.gz && rm -f vocalguard_deploy.tar.gz"
Remove-Item $tempArchive -ErrorAction SilentlyContinue
Write-Host "  Fichiers mis a jour (venv, .env, logs non ecrases)" -ForegroundColor Gray
Write-Host "OK" -ForegroundColor Green
Write-Host ""

# [6] Deps et config
Write-Host "[6/6] Dependances et configuration..." -ForegroundColor Yellow
ssh "$RPI_HOST" "cd $RPI_DIR && source venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt"
Write-Host "  pip install -r requirements.txt (incrementale)" -ForegroundColor Gray
ssh "$RPI_HOST" "cd $RPI_DIR && if [ -f env.example ] && [ ! -f .env ]; then cp env.example .env; fi"
Write-Host "  .env conserve ou cree depuis env.example" -ForegroundColor Gray
Write-Host "OK" -ForegroundColor Green
Write-Host ""

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Deploiement termine" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Sur le Pi:" -ForegroundColor Yellow
Write-Host "  ssh $RPI_HOST" -ForegroundColor White
Write-Host "  cd $RPI_DIR && source venv/bin/activate" -ForegroundColor White
Write-Host "  python scripts/test_modem_answer_play_record.py   # test modem" -ForegroundColor White
Write-Host "  ./run_backend.sh                                   # backend complet" -ForegroundColor White
Write-Host ""
