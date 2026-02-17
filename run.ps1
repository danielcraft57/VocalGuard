# Script de démarrage PowerShell pour VocalGuard

Write-Host "Démarrage de VocalGuard..." -ForegroundColor Green

# Détecter et utiliser conda si disponible, sinon utiliser venv
$USE_CONDA = $false
$CONDA_ENV_NAME = "vocalguard"
$PYTHON_CMD = "python"

# Vérifier si conda est disponible
if (Get-Command conda -ErrorAction SilentlyContinue) {
    # Vérifier si l'environnement conda existe
    $condaEnvs = conda env list
    if ($condaEnvs -match "^${CONDA_ENV_NAME}\s") {
        $USE_CONDA = $true
        Write-Host "Environnement conda '${CONDA_ENV_NAME}' détecté" -ForegroundColor Green
    }
}

if ($USE_CONDA) {
    Write-Host "Utilisation de l'environnement conda '${CONDA_ENV_NAME}'..." -ForegroundColor Green
    
    # Utiliser conda run pour vérifier et installer les dépendances
    Write-Host "Vérification des dépendances (loguru + aiosqlite)..." -ForegroundColor Green
    $depsCheck = conda run -n $CONDA_ENV_NAME python -c "import loguru, aiosqlite" 2>&1
    if ($LASTEXITCODE -ne 0 -or $depsCheck -match "ModuleNotFoundError|ImportError") {
        Write-Host "Installation des dépendances..." -ForegroundColor Yellow
        conda run -n $CONDA_ENV_NAME python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Erreur lors de la mise à jour de pip" -ForegroundColor Red
            exit 1
        }
        
        # Installer les dépendances une par une pour mieux gérer les erreurs
        Write-Host "Installation des dépendances principales..." -ForegroundColor Yellow
        conda run -n $CONDA_ENV_NAME python -m pip install fastapi uvicorn pydantic pydantic-settings sqlalchemy alembic aiosqlite loguru python-dotenv pyyaml jinja2 httpx aiohttp pyserial
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Erreur lors de l'installation des dépendances principales" -ForegroundColor Red
            exit 1
        }
        
        # Installer whisper depuis GitHub si la version PyPI ne fonctionne pas
        Write-Host "Installation de whisper..." -ForegroundColor Yellow
        conda run -n $CONDA_ENV_NAME python -m pip install git+https://github.com/openai/whisper.git
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Tentative d'installation de whisper depuis PyPI..." -ForegroundColor Yellow
            conda run -n $CONDA_ENV_NAME python -m pip install openai-whisper --no-build-isolation
        }
        
        # Installer les autres dépendances audio
        Write-Host "Installation des dépendances audio..." -ForegroundColor Yellow
        conda run -n $CONDA_ENV_NAME python -m pip install vosk pyttsx3 gtts soundfile librosa numpy
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Erreur lors de l'installation des dépendances audio" -ForegroundColor Red
            exit 1
        }
        
        # Installer pyaudio (peut nécessiter des dépendances système)
        Write-Host "Installation de pyaudio..." -ForegroundColor Yellow
        conda run -n $CONDA_ENV_NAME python -m pip install pyaudio
        # Ne pas échouer si pyaudio ne s'installe pas (dépendances système)
        
        # Installer les dépendances optionnelles
        Write-Host "Installation des dépendances optionnelles..." -ForegroundColor Yellow
        conda run -n $CONDA_ENV_NAME python -m pip install truecallerpy
        # Ne pas échouer si truecallerpy ne s'installe pas
        
        Write-Host "Vérification finale des dépendances..." -ForegroundColor Green
        $finalCheck = conda run -n $CONDA_ENV_NAME python -c "import loguru; import fastapi; print('OK')" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Erreur: certaines dépendances essentielles ne sont pas installées" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "Dépendances déjà installées" -ForegroundColor Green
    }
    
    # Utiliser conda run pour lancer l'application
    $PYTHON_CMD = "conda run -n ${CONDA_ENV_NAME} python"
} else {
    # Utiliser venv
    # Vérifier si l'environnement virtuel existe
    if (-not (Test-Path "venv")) {
        Write-Host "Création de l'environnement virtuel..." -ForegroundColor Yellow
        python -m venv venv
    }
    
    # Activer l'environnement virtuel
    Write-Host "Activation de l'environnement virtuel..." -ForegroundColor Green
    & "venv\Scripts\Activate.ps1"
    
    # Vérifier si les dépendances sont installées
    if (-not (Test-Path "venv\.installed")) {
        Write-Host "Installation des dépendances..." -ForegroundColor Yellow
        pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Erreur lors de la mise à jour de pip" -ForegroundColor Red
            exit 1
        }
        pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Erreur lors de l'installation des dépendances" -ForegroundColor Red
            exit 1
        }
        New-Item -ItemType File -Path "venv\.installed" -Force | Out-Null
    }
}

# Créer les dossiers nécessaires
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
New-Item -ItemType Directory -Force -Path "audio_cache" | Out-Null
New-Item -ItemType Directory -Force -Path "data" | Out-Null

# Vérifier la configuration
if (-not (Test-Path "config\config.yaml")) {
    Write-Host "Création du fichier de configuration..." -ForegroundColor Yellow
    Copy-Item "config\config.example.yaml" "config\config.yaml"
    Write-Host "Veuillez éditer config\config.yaml avant de continuer" -ForegroundColor Yellow
    exit 1
}

# Lancer l'application
Write-Host "Lancement de VocalGuard..." -ForegroundColor Green
Invoke-Expression "$PYTHON_CMD -m vocalguard.main"

