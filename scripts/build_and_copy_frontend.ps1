# Build du frontend Next.js puis copie vers backend/web
# A lancer depuis la racine du projet VocalGuard.

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot + "\.."
$FrontendDir = Join-Path $ProjectRoot "frontend"
$OutDir = Join-Path $FrontendDir "out"
$BackendWeb = Join-Path $ProjectRoot "backend\web"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Build frontend + copie vers backend/web" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Build Next.js (export statique -> frontend/out)
Push-Location $FrontendDir
try {
    Write-Host "Lancement: npm run build dans frontend..." -ForegroundColor Yellow
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Erreur: le build Next.js a echoue." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

if (-not (Test-Path $OutDir)) {
    Write-Host "Erreur: le dossier frontend/out n'existe pas apres le build." -ForegroundColor Red
    exit 1
}

# 2. Nettoyer backend/web puis copier
Write-Host "Copie de frontend/out vers backend/web..." -ForegroundColor Yellow
if (Test-Path $BackendWeb) {
    Get-ChildItem $BackendWeb -Exclude "README.md" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $BackendWeb | Out-Null
Copy-Item -Path (Join-Path $OutDir "*") -Destination $BackendWeb -Recurse -Force

Write-Host "Termine. Le front est a jour dans backend/web." -ForegroundColor Green
Write-Host "Relance le backend (uvicorn backend.main:app --reload) puis ouvre http://localhost:8000/" -ForegroundColor Gray
