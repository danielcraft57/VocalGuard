# Script de déploiement de VocalGuard sur Raspberry Pi
# PowerShell version

$ErrorActionPreference = "Stop"

# Configuration
# Remarque: pour éviter de stocker des hôtes ou mots de passe sensibles
# dans le dépôt git, on lit d'abord la variable d'environnement RPI_HOST.
# Si elle n'est pas définie, on demande la valeur à l'utilisateur.
if (-not $env:RPI_HOST -or $env:RPI_HOST.Trim() -eq "") {
    $RPI_HOST = Read-Host "Entrez l'utilisateur et l'hôte du Raspberry Pi (ex: pi@raspberrypi.local)"
} else {
    $RPI_HOST = $env:RPI_HOST
}

$RPI_DIR = "~/VocalGuard"
# Obtenir le répertoire du projet VocalGuard (parent du dossier scripts)
$PROJECT_DIR = (Get-Item (Split-Path -Parent $PSScriptRoot)).FullName

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Déploiement de VocalGuard sur Raspberry Pi" -ForegroundColor Cyan
Write-Host "Hôte: $RPI_HOST" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Vérifier la connexion SSH
Write-Host "[1/8] Vérification de la connexion SSH..." -ForegroundColor Yellow
try {
    $result = ssh -o ConnectTimeout=5 "$RPI_HOST" "echo 'Connexion OK'" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Connexion échouée"
    }
    Write-Host "✅ Connexion SSH OK" -ForegroundColor Green
} catch {
    Write-Host "❌ Impossible de se connecter à $RPI_HOST" -ForegroundColor Red
    Write-Host "   Vérifiez que:" -ForegroundColor Yellow
    Write-Host "   - Le Raspberry Pi est allumé" -ForegroundColor Yellow
    Write-Host "   - SSH est activé" -ForegroundColor Yellow
    Write-Host "   - La clé SSH est configurée" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Supprimer et recréer le répertoire sur le RPi
Write-Host "[2/8] Nettoyage et création du répertoire sur le Raspberry Pi..." -ForegroundColor Yellow
Write-Host "   Suppression de l'ancien répertoire (s'il existe)..." -ForegroundColor Gray
# Supprimer le contenu avec sudo si nécessaire, puis le dossier
ssh "$RPI_HOST" "sudo rm -rf $RPI_DIR/* $RPI_DIR/.* 2>/dev/null || true; rm -rf $RPI_DIR 2>/dev/null || true" | Out-Null
ssh "$RPI_HOST" "mkdir -p $RPI_DIR" | Out-Null
Write-Host "✅ Répertoire créé: $RPI_DIR" -ForegroundColor Green
Write-Host ""

# Vérifier Python
Write-Host "[3/8] Vérification de Python..." -ForegroundColor Yellow
$pythonVersion = ssh "$RPI_HOST" "python3 --version 2>&1" | Select-Object -First 1
if (-not $pythonVersion) {
    Write-Host "❌ Python3 n'est pas installé sur le Raspberry Pi" -ForegroundColor Red
    exit 1
}
Write-Host "✅ $pythonVersion détecté" -ForegroundColor Green
Write-Host ""

# Vérifier pip
Write-Host "[4/8] Vérification de pip..." -ForegroundColor Yellow
$pipCheck = ssh "$RPI_HOST" "python3 -m pip --version 2>&1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️ pip n'est pas installé, installation..." -ForegroundColor Yellow
    ssh "$RPI_HOST" "sudo apt-get update && sudo apt-get install -y python3-pip" | Out-Null
}
Write-Host "✅ pip disponible" -ForegroundColor Green
Write-Host ""

# Créer l'environnement virtuel
Write-Host "[5/8] Création de l'environnement virtuel..." -ForegroundColor Yellow
$venvExists = ssh "$RPI_HOST" "test -d $RPI_DIR/venv && echo 'exists' || echo 'not exists'"
if ($venvExists -eq "not exists") {
    ssh "$RPI_HOST" "cd $RPI_DIR && python3 -m venv venv" | Out-Null
    Write-Host "✅ Environnement virtuel créé" -ForegroundColor Green
} else {
    Write-Host "✅ Environnement virtuel existe déjà" -ForegroundColor Green
}
Write-Host ""

# Synchroniser les fichiers avec rsync (si disponible) ou scp
Write-Host "[6/8] Synchronisation des fichiers..." -ForegroundColor Yellow
Write-Host "   (Cela peut prendre quelques minutes...)" -ForegroundColor Gray

# Vérifier si rsync est disponible
$rsyncAvailable = Get-Command rsync -ErrorAction SilentlyContinue
if ($rsyncAvailable) {
    # Utiliser rsync (plus rapide)
    $excludes = @(
        "--exclude=venv",
        "--exclude=__pycache__",
        "--exclude=*.pyc",
        "--exclude=.env",
        "--exclude=*.db",
        "--exclude=.git",
        "--exclude=audio_cache",
        "--exclude=logs",
        "--exclude=data"
    )
    $excludeArgs = $excludes -join " "
    & rsync -avz --progress $excludeArgs "$PROJECT_DIR/" "${RPI_HOST}:${RPI_DIR}/"
} else {
    # Fallback: utiliser scp pour les fichiers essentiels
    Write-Host "   rsync non disponible, utilisation de scp..." -ForegroundColor Yellow
    Write-Host "   (Installation de rsync recommandée pour un déploiement plus rapide)" -ForegroundColor Yellow
    
    # Créer une archive temporaire
    $tempArchive = "$env:TEMP\vocalguard_deploy.tar.gz"
    Write-Host "   Création de l'archive..." -ForegroundColor Gray
    
    # Utiliser tar via WSL ou Git Bash si disponible
    $tarCmd = Get-Command tar -ErrorAction SilentlyContinue
    if ($tarCmd) {
        # Créer l'archive en excluant les dossiers
        # Utiliser --transform pour ne garder que le contenu du projet VocalGuard
        Push-Location $PROJECT_DIR
        $excludes = @(
            'venv', '__pycache__', '*.pyc', '.env', '*.db', '.git', 
            'audio_cache', 'logs', 'data', 'node_modules',
            'V1', 'V2', 'V3', 'V4', 'V5', 'V6',
            'coaching', 'formations', 'Mes CV', 'Notariat', 
            'portfolio-projects', 'prospection', 'prospectlab',
            'scripts/Data', 'scripts/*.py', 'scripts/*.txt', 'scripts/*.json', 'scripts/*.md'
        )
        $excludeArgs = ($excludes | ForEach-Object { "--exclude=$_" }) -join ' '
        
        # Créer l'archive avec seulement les fichiers du projet VocalGuard
        $vocalguardFiles = @(
            'vocalguard', 'scripts/test_*.py', 'scripts/deploy_*.ps1', 'scripts/deploy_*.sh',
            'docs', 'config', 'requirements.txt', 'setup.py', 'README.md', 
            'LICENSE', 'CHANGELOG.md', 'env.example', 'ollama_shell.py',
            'ollama-preload.sh', 'ollama-preload.service', 'run.sh', 'run.ps1',
            'Dockerfile', 'docker-compose.yml', '.gitignore', '.cursorrules'
        )
        
        # Créer une archive avec seulement les fichiers nécessaires
        $fileList = @()
        foreach ($pattern in $vocalguardFiles) {
            $files = Get-ChildItem -Path $PROJECT_DIR -Filter $pattern -Recurse -ErrorAction SilentlyContinue | Where-Object { -not $_.PSIsContainer }
            $fileList += $files.FullName | ForEach-Object { $_.Replace($PROJECT_DIR + '\', '') }
        }
        
        # Créer un fichier temporaire avec la liste des fichiers à inclure
        $fileListPath = "$env:TEMP\vocalguard_files.txt"
        $fileList | Out-File -FilePath $fileListPath -Encoding UTF8
        
        # Créer l'archive avec les fichiers listés
        tar -czf $tempArchive -T $fileListPath 2>&1 | Out-Null
        
        Remove-Item $fileListPath -ErrorAction SilentlyContinue
        Pop-Location
        
        # Transférer l'archive
        scp $tempArchive "${RPI_HOST}:${RPI_DIR}/vocalguard_deploy.tar.gz"
        
        # Extraire sur le RPi
        ssh "$RPI_HOST" "cd $RPI_DIR && tar -xzf vocalguard_deploy.tar.gz && rm vocalguard_deploy.tar.gz"
        
        # Nettoyer
        Remove-Item $tempArchive -ErrorAction SilentlyContinue
    } else {
        Write-Host "   ⚠️ tar non disponible, transfert manuel requis" -ForegroundColor Yellow
        Write-Host "   Vous pouvez utiliser WinSCP ou FileZilla pour transférer les fichiers" -ForegroundColor Yellow
    }
}
Write-Host "✅ Fichiers synchronisés" -ForegroundColor Green
Write-Host ""

# Installer les dépendances
Write-Host "[7/8] Installation des dépendances..." -ForegroundColor Yellow
Write-Host "   (Cela peut prendre plusieurs minutes...)" -ForegroundColor Gray
ssh "$RPI_HOST" "cd $RPI_DIR && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"
Write-Host "✅ Dépendances installées" -ForegroundColor Green
Write-Host ""

# Créer le fichier .env
Write-Host "[8/8] Configuration de l'environnement..." -ForegroundColor Yellow
ssh "$RPI_HOST" "cd $RPI_DIR && if [ ! -f .env ]; then cp env.example .env; fi"

# Configurer Ollama pour utiliser localhost
ssh "$RPI_HOST" "cd $RPI_DIR && sed -i 's|OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://127.0.0.1:11434|' .env"

Write-Host "✅ Configuration créée" -ForegroundColor Green
Write-Host ""

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ Déploiement terminé avec succès!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pour tester le système:" -ForegroundColor Yellow
Write-Host "  ssh $RPI_HOST" -ForegroundColor White
Write-Host "  cd $RPI_DIR" -ForegroundColor White
Write-Host "  source venv/bin/activate" -ForegroundColor White
Write-Host "  python scripts/test_ollama_voice.py" -ForegroundColor White
Write-Host ""
Write-Host "Ou lancer VocalGuard complet:" -ForegroundColor Yellow
Write-Host "  python -m vocalguard.main" -ForegroundColor White
Write-Host ""
