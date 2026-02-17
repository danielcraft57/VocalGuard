# Script de déploiement simplifié de VocalGuard sur Raspberry Pi
# Transfère uniquement les fichiers du projet VocalGuard

$ErrorActionPreference = "Stop"

# Remarque: pour éviter de stocker des hôtes ou mots de passe sensibles
# dans le dépôt, on privilégie la variable d'environnement RPI_HOST.
if (-not $env:RPI_HOST -or $env:RPI_HOST.Trim() -eq "") {
    $RPI_HOST = Read-Host "Entrez l'utilisateur et l'hôte du Raspberry Pi (ex: pi@raspberrypi.local)"
} else {
    $RPI_HOST = $env:RPI_HOST
}

$RPI_DIR = "~/VocalGuard"
$PROJECT_DIR = (Get-Item (Split-Path -Parent $PSScriptRoot)).FullName

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Déploiement de VocalGuard sur Raspberry Pi" -ForegroundColor Cyan
Write-Host "Hôte: $RPI_HOST" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Nettoyer le répertoire distant
Write-Host "[1/6] Nettoyage du répertoire distant..." -ForegroundColor Yellow
ssh "$RPI_HOST" "sudo rm -rf $RPI_DIR/* $RPI_DIR/.* 2>/dev/null || true; rm -rf $RPI_DIR 2>/dev/null || true; mkdir -p $RPI_DIR" | Out-Null
Write-Host "✅ Répertoire nettoyé" -ForegroundColor Green
Write-Host ""

# Vérifier Python
Write-Host "[2/6] Vérification de Python..." -ForegroundColor Yellow
$pythonVersion = ssh "$RPI_HOST" "python3 --version 2>&1" | Select-Object -First 1
Write-Host "✅ $pythonVersion" -ForegroundColor Green
Write-Host ""

# Créer venv
Write-Host "[3/6] Création de l'environnement virtuel..." -ForegroundColor Yellow
ssh "$RPI_HOST" "cd $RPI_DIR && python3 -m venv venv" | Out-Null
Write-Host "✅ venv créé" -ForegroundColor Green
Write-Host ""

# Transférer les fichiers essentiels avec scp
Write-Host "[4/6] Transfert des fichiers..." -ForegroundColor Yellow
Write-Host "   (Cela peut prendre quelques minutes...)" -ForegroundColor Gray

# Liste des fichiers/dossiers à transférer
$itemsToTransfer = @(
    "vocalguard",
    "scripts",
    "docs",
    "config",
    "requirements.txt",
    "setup.py",
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "env.example",
    "ollama_shell.py",
    "ollama-preload.sh",
    "ollama-preload.service",
    "run.sh",
    "Dockerfile",
    "docker-compose.yml",
    ".gitignore",
    ".cursorrules"
)

foreach ($item in $itemsToTransfer) {
    $localPath = Join-Path $PROJECT_DIR $item
    if (Test-Path $localPath) {
        Write-Host "   Transfert: $item" -ForegroundColor Gray
        if (Test-Path $localPath -PathType Container) {
            # C'est un dossier
            scp -r "$localPath" "${RPI_HOST}:${RPI_DIR}/" 2>&1 | Out-Null
        } else {
            # C'est un fichier
            scp "$localPath" "${RPI_HOST}:${RPI_DIR}/" 2>&1 | Out-Null
        }
    }
}

Write-Host "✅ Fichiers transférés" -ForegroundColor Green
Write-Host ""

# Installer les dépendances
Write-Host "[5/6] Installation des dépendances..." -ForegroundColor Yellow
Write-Host "   (Cela peut prendre plusieurs minutes...)" -ForegroundColor Gray
ssh "$RPI_HOST" "cd $RPI_DIR && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt" 2>&1 | Out-Null
Write-Host "✅ Dépendances installées" -ForegroundColor Green
Write-Host ""

# Configuration
Write-Host "[6/6] Configuration..." -ForegroundColor Yellow
ssh "$RPI_HOST" "cd $RPI_DIR && if [ ! -f .env ]; then cp env.example .env; fi && sed -i 's|OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://127.0.0.1:11434|' .env" | Out-Null
Write-Host "✅ Configuration créée" -ForegroundColor Green
Write-Host ""

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ Déploiement terminé!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pour tester:" -ForegroundColor Yellow
Write-Host "  ssh $RPI_HOST" -ForegroundColor White
Write-Host "  cd $RPI_DIR" -ForegroundColor White
Write-Host "  source venv/bin/activate" -ForegroundColor White
Write-Host "  python scripts/test_ollama_voice.py" -ForegroundColor White
Write-Host ""
