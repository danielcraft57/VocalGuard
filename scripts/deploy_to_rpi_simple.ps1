# Deploiement simplifie VocalGuard sur Raspberry Pi
# Transfere les dossiers/fichiers essentiels sans detruire venv ni .env.

$ErrorActionPreference = "Stop"

if (-not $env:RPI_HOST -or $env:RPI_HOST.Trim() -eq "") {
    $RPI_HOST = Read-Host "Entrez l'utilisateur et l'hote (ex: pi@raspberrypi.local)"
} else {
    $RPI_HOST = $env:RPI_HOST
}

$RPI_DIR = "~/VocalGuard"
$PROJECT_DIR = (Get-Item (Split-Path -Parent $PSScriptRoot)).FullName

Write-Host "Deploiement VocalGuard (simple) -> $RPI_HOST" -ForegroundColor Cyan
Write-Host ""

# Repertoire sans tout supprimer
ssh "$RPI_HOST" "mkdir -p $RPI_DIR"
$venvExists = ssh "$RPI_HOST" "test -d $RPI_DIR/venv && echo yes || echo no"

# Venv uniquement si absent
if ($venvExists -eq "no") {
    Write-Host "Creation venv..." -ForegroundColor Yellow
    ssh "$RPI_HOST" "cd $RPI_DIR && python3 -m venv venv"
}

# Elements a synchroniser (dossiers et fichiers a la racine VocalGuard)
$toSync = @(
    "backend",
    "scripts",
    "config",
    "docs",
    "frontend",
    "requirements.txt",
    "setup.py",
    "README.md",
    "CHANGELOG.md",
    "env.example",
    "ollama_shell.py",
    "run.sh",
    "run_backend.sh",
    ".gitignore",
    ".cursorrules"
)

# Fichiers optionnels
$optional = @("Dockerfile", "docker-compose.yml", "ollama-preload.sh", "ollama-preload.service")

Write-Host "Transfert des fichiers..." -ForegroundColor Yellow
foreach ($item in $toSync) {
    $localPath = Join-Path $PROJECT_DIR $item
    if (Test-Path $localPath) {
        $dest = "${RPI_HOST}:${RPI_DIR}/"
        if (Test-Path $localPath -PathType Container) {
            scp -r -q "$localPath" $dest 2>$null
        } else {
            scp -q "$localPath" $dest 2>$null
        }
    }
}
foreach ($item in $optional) {
    $localPath = Join-Path $PROJECT_DIR $item
    if (Test-Path $localPath) {
        scp -q "$localPath" "${RPI_HOST}:${RPI_DIR}/" 2>$null
    }
}

Write-Host "Dependances (pip)..." -ForegroundColor Yellow
ssh "$RPI_HOST" "cd $RPI_DIR && source venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt"

Write-Host "Configuration (.env)..." -ForegroundColor Yellow
ssh "$RPI_HOST" "cd $RPI_DIR && if [ ! -f .env ]; then cp env.example .env; fi && sed -i 's|OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://127.0.0.1:11434|' .env 2>/dev/null || true"

Write-Host "Termine. ssh $RPI_HOST -> cd $RPI_DIR && source venv/bin/activate" -ForegroundColor Green
