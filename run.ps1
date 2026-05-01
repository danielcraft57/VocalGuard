# Script de démarrage PowerShell pour VocalGuard
param(
    [switch]$SingleWindow
)

Write-Host "Démarrage de VocalGuard..." -ForegroundColor Green

$PROJECT_ROOT = (Get-Location).Path

function Stop-VocalGuardProcesses {
    param(
        [string]$Reason = "Nettoyage des processus"
    )

    try {
        $stale = Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -and (
                (
                    $_.Name -match "python|python.exe|pythonw.exe|celery.exe|conda.exe" -and
                    (
                        $_.CommandLine -match [regex]::Escape($PROJECT_ROOT) -or
                        $_.CommandLine -match "backend\.main:app" -or
                        $_.CommandLine -match "celery\s+-A\s+backend\.celery_app\.celery_app\s+worker" -or
                        $_.CommandLine -match "conda\s+run\s+-n\s+vocalguard"
                    )
                ) -or
                (
                    $_.Name -match "cmd.exe|powershell.exe|pwsh.exe" -and
                    (
                        $_.CommandLine -match "backend\.main:app" -or
                        $_.CommandLine -match "celery\s+-A\s+backend\.celery_app\.celery_app\s+worker" -or
                        $_.CommandLine -match "conda\s+activate\s+vocalguard"
                    )
                )
            )
        }

        if ($stale -and $stale.Count -gt 0) {
            Write-Host "$Reason..." -ForegroundColor Yellow
            foreach ($p in $stale) {
                try {
                    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
                    Write-Host (" - PID {0} stoppé ({1})" -f $p.ProcessId, $p.Name) -ForegroundColor DarkGray
                } catch {
                    # ignorer
                }
            }
        }
    } catch {
        Write-Host "Impossible de nettoyer automatiquement les processus (continuation)." -ForegroundColor Yellow
    }
}

# Nettoyage préventif: tuer les anciens processus Python/Celery/Conda liés à VocalGuard
Stop-VocalGuardProcesses -Reason "Arrêt des anciens processus Python/Celery/Conda"

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
    
    # Vérifier la version Python de l'environnement conda (prod = 3.13)
    $pyVersionOutput = conda run -n $CONDA_ENV_NAME python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Python detecte dans '${CONDA_ENV_NAME}': $pyVersionOutput" -ForegroundColor Cyan
        if ($pyVersionOutput -notmatch "Python 3\.13") {
            Write-Host "ATTENTION: la production cible Python 3.13. Adaptez l'environnement conda avant de deployer." -ForegroundColor Yellow
        }
    } else {
        Write-Host "Impossible de verifier la version Python de l'environnement conda." -ForegroundColor Yellow
    }
    
    # Installer/mettre à jour les dépendances depuis requirements.txt (évite les oublis: python-multipart, openpyxl, redis, etc.)
    Write-Host "Installation/MAJ des dépendances (requirements.txt)..." -ForegroundColor Green
    conda run -n $CONDA_ENV_NAME python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Erreur lors de la mise à jour de pip" -ForegroundColor Red
        exit 1
    }
    conda run -n $CONDA_ENV_NAME python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Erreur lors de l'installation des dépendances via requirements.txt" -ForegroundColor Red
        exit 1
    }

    # Whisper: installer depuis GitHub uniquement s'il n'est pas déjà installé.
    Write-Host "Vérification de whisper..." -ForegroundColor Green
    $whisperCheck = conda run -n $CONDA_ENV_NAME python -c "import whisper; print(getattr(whisper, '__version__', 'installed'))" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host ("Whisper déjà installé ({0}) - installation ignorée." -f (($whisperCheck | Select-Object -Last 1).ToString().Trim())) -ForegroundColor DarkGray
    } else {
        Write-Host "Installation de whisper (GitHub)..." -ForegroundColor Green
        conda run -n $CONDA_ENV_NAME python -m pip install --upgrade git+https://github.com/openai/whisper.git
        # Ne pas échouer si whisper ne s'installe pas ici (dépendances lourdes)
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
    $PYTHON_CMD = (Resolve-Path "venv\Scripts\python.exe").Path
    
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

# Nettoyer les logs à chaque démarrage (demande user)
Get-ChildItem -Path "logs" -Filter "*.log" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

# Nettoyage Redis (file Celery) pour éviter les tâches résiduelles entre redémarrages.
# Cible prioritaire: CELERY_BROKER_URL / CELERY_RESULT_BACKEND depuis .env, sinon fallback db 2.
try {
    Write-Host "Nettoyage de la file Redis Celery..." -ForegroundColor Yellow
    $redisCleanupPy = @'
import os
from pathlib import Path
from urllib.parse import urlparse

try:
    from redis import Redis
except Exception as e:
    print(f"[redis-cleanup] redis package indisponible: {e}")
    raise SystemExit(0)

env_path = Path(".env")
env_map = {}
if env_path.exists():
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env_map[k.strip()] = v.strip().strip('"').strip("'")

broker = env_map.get("CELERY_BROKER_URL") or os.environ.get("CELERY_BROKER_URL") or "redis://127.0.0.1:6379/2"
backend = env_map.get("CELERY_RESULT_BACKEND") or os.environ.get("CELERY_RESULT_BACKEND") or broker

def flush_if_redis(url: str) -> None:
    if not url or not url.startswith("redis://"):
        print(f"[redis-cleanup] skip (non-redis): {url}")
        return
    p = urlparse(url)
    db = 0
    if p.path and p.path != "/":
        try:
            db = int(p.path.lstrip("/"))
        except Exception:
            db = 0
    r = Redis(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        db=db,
        username=p.username,
        password=p.password,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    r.ping()
    r.flushdb()
    print(f"[redis-cleanup] FLUSHDB ok -> {p.hostname}:{p.port or 6379}/{db}")

seen = set()
for u in (broker, backend):
    if u in seen:
        continue
    seen.add(u)
    try:
        flush_if_redis(u)
    except Exception as e:
        print(f"[redis-cleanup] échec sur {u}: {e}")
'@

    $redisCleanupScript = Join-Path (Get-Location).Path "logs\redis_cleanup.py"
    Set-Content -Path $redisCleanupScript -Value $redisCleanupPy -Encoding UTF8

    try {
        if ($USE_CONDA) {
            conda run -n $CONDA_ENV_NAME python $redisCleanupScript
        } else {
            & $PYTHON_CMD $redisCleanupScript
        }
    } finally {
        Remove-Item -Path $redisCleanupScript -Force -ErrorAction SilentlyContinue
    }
} catch {
    Write-Host "Nettoyage Redis ignoré (continuation)." -ForegroundColor Yellow
}

# Vérifier la configuration
if (-not (Test-Path "config\config.yaml")) {
    Write-Host "Création du fichier de configuration..." -ForegroundColor Yellow
    Copy-Item "config\config.example.yaml" "config\config.yaml"
    Write-Host "Veuillez éditer config\config.yaml avant de continuer" -ForegroundColor Yellow
    exit 1
}

# Vérifier npm
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "npm introuvable. Installez Node.js pour lancer le frontend." -ForegroundColor Red
    exit 1
}

# Lancer backend + frontend dans 2 fenêtres PowerShell
$FRONTEND_DIR = Join-Path $PROJECT_ROOT "frontend"

if (-not (Test-Path $FRONTEND_DIR)) {
    Write-Host "Dossier frontend introuvable: $FRONTEND_DIR" -ForegroundColor Red
    exit 1
}

if ($SingleWindow) {
    Write-Host "Lancement de VocalGuard en mode une seule fenêtre..." -ForegroundColor Green
} else {
    Write-Host "Lancement de VocalGuard sur 3 fenêtres..." -ForegroundColor Green
}

if ($USE_CONDA) {
    # Eviter "conda run" en parallèle (Windows: conflits de fichiers __conda_tmp_*.txt)
    # et éviter aussi "&&" (non supporté en PowerShell 5).
    # On initialise conda dans la session PowerShell enfant via le hook officiel, puis conda activate.
    $backendLaunch = "Set-Location '$PROJECT_ROOT'; Invoke-Expression ((conda shell.powershell hook) | Out-String); conda activate $CONDA_ENV_NAME; python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
    $celeryLaunch = "Set-Location '$PROJECT_ROOT'; Invoke-Expression ((conda shell.powershell hook) | Out-String); conda activate $CONDA_ENV_NAME; python -m celery -A backend.celery_app.celery_app worker --loglevel=info --pool=solo"
} else {
    $backendLaunch = "Set-Location '$PROJECT_ROOT'; & '$PYTHON_CMD' -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
    $celeryLaunch = "Set-Location '$PROJECT_ROOT'; & '$PYTHON_CMD' -m celery -A backend.celery_app.celery_app worker --loglevel=info --pool=solo"
}

$frontendLaunch = "Set-Location '$FRONTEND_DIR'; npm.cmd run dev"

if ($SingleWindow) {
    # Backend et Celery en arrière-plan (fenêtres masquées), frontend au premier plan.
    $backendOut = Join-Path $PROJECT_ROOT "logs\backend.log"
    $backendErr = Join-Path $PROJECT_ROOT "logs\backend.err.log"
    $celeryOut = Join-Path $PROJECT_ROOT "logs\celery.log"
    $celeryErr = Join-Path $PROJECT_ROOT "logs\celery.err.log"

    $backendProc = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendLaunch) -WindowStyle Hidden -PassThru -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr
    $celeryProc = Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $celeryLaunch) -WindowStyle Hidden -PassThru -RedirectStandardOutput $celeryOut -RedirectStandardError $celeryErr

    Write-Host "Backend: http://localhost:8000 (arrière-plan)" -ForegroundColor Cyan
    Write-Host "Celery: worker OSINT actif (arrière-plan)" -ForegroundColor Cyan
    Write-Host "Frontend: http://localhost:3000 (fenêtre courante)" -ForegroundColor Cyan
    Write-Host "Logs backend: logs\backend.log (erreurs: logs\backend.err.log)" -ForegroundColor DarkGray
    Write-Host "Logs celery: logs\celery.log (erreurs: logs\celery.err.log)" -ForegroundColor DarkGray
    Write-Host "Arrête avec Ctrl+C (ça coupe front + backend + celery)." -ForegroundColor Yellow

    try {
        Invoke-Expression $frontendLaunch
    } finally {
        Write-Host "Arrêt des processus backend/celery..." -ForegroundColor Yellow
        try {
            if ($backendProc -and -not $backendProc.HasExited) {
                Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {}
        try {
            if ($celeryProc -and -not $celeryProc.HasExited) {
                Stop-Process -Id $celeryProc.Id -Force -ErrorAction SilentlyContinue
            }
        } catch {}
        Stop-VocalGuardProcesses -Reason "Nettoyage final (Ctrl+C)"
    }
} else {
    Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", $backendLaunch)
    Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", $frontendLaunch)
    Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command", $celeryLaunch)

    Write-Host "Backend: http://localhost:8000" -ForegroundColor Cyan
    Write-Host "Frontend: http://localhost:3000" -ForegroundColor Cyan
    Write-Host "Celery: worker OSINT actif (pool=solo)" -ForegroundColor Cyan
    Write-Host "Trois fenêtres ont été ouvertes (backend + frontend + celery)." -ForegroundColor Green
    Write-Host "Appuie sur Ctrl+C dans cette fenêtre pour tout nettoyer." -ForegroundColor Yellow

    try {
        while ($true) {
            Start-Sleep -Seconds 1
        }
    } finally {
        Stop-VocalGuardProcesses -Reason "Nettoyage final (Ctrl+C)"
    }
}

