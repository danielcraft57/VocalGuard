<#
.SYNOPSIS
  Lance les tests telephony : pytest local, smoke sur SSH (node14), ou checks HTTP vers node14.

.PARAMETER Mode
  Unit       — pytest backend/tests (sans modem, offline).
  RemoteSsh  — connexion SSH vers le Pi et execution de smoke_telephony_stack.sh dans RemoteDir.
  Endpoints  — depuis ta machine : GET /health API + daemon + POST interne si token connu.
  Stack      — meme checks via scripts/test_api_stack.py (Python, portable Linux/macOS/Windows).

.PARAMETER FetchTokenFromRemote
  (Endpoints) Lit TELEPHONY_INTERNAL_TOKEN sur le serveur via SSH (aligne avec l’API sur node14).

.PARAMETER StrictInternalPost
  (Endpoints) Echoue si le POST interne n’est pas 202 ; sinon un 401 n’est qu’un avertissement (token local ≠ serveur).

.EXAMPLE
  .\scripts\run_telephony_tests.ps1 -Mode Unit

.EXAMPLE
  .\scripts\run_telephony_tests.ps1 -Mode RemoteSsh -RemoteHost node14.lan

.EXAMPLE
  .\scripts\run_telephony_tests.ps1 -Mode Endpoints -RemoteHost node14.lan -FetchTokenFromRemote

.EXAMPLE
  .\scripts\run_telephony_tests.ps1 -Mode Endpoints -RemoteHost node14.lan -InternalToken "meme_secret_que_sur_pi"

.EXAMPLE
  .\scripts\run_telephony_tests.ps1 -Mode Stack -RemoteHost node14.lan
#>
param(
    [ValidateSet("Unit", "RemoteSsh", "Endpoints", "Stack")]
    [string]$Mode = "Unit",
    [string]$RemoteHost = "node14.lan",
    [string]$RemoteUser = "pi",
    [string]$RemoteDir = "/opt/vocalguard",
    [int]$ApiPort = 8000,
    [int]$TelephonyPort = 8090,
    [string]$EnvFile = "",
    [string]$InternalToken = "",
    [switch]$FetchTokenFromRemote,
    [switch]$StrictInternalPost
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Get-Item (Split-Path -Parent $PSScriptRoot)).FullName

function Find-PythonExe {
    $candidates = @(
        (Join-Path $ProjectDir "venv\Scripts\python.exe"),
        (Join-Path $ProjectDir ".venv\Scripts\python.exe")
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    throw "Python introuvable (creer venv ou activer conda)."
}

function Read-DotEnvToken {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return "" }
    foreach ($line in Get-Content $Path -Encoding UTF8) {
        $t = $line.Trim()
        if ($t -match '^\s*#' -or $t -eq "") { continue }
        if ($t -match '^\s*TELEPHONY_INTERNAL_TOKEN\s*=\s*(.+)$') {
            $v = $Matches[1].Trim().Trim('"').Trim("'")
            return $v
        }
    }
    return ""
}

function Get-RemoteInternalToken {
    param([string]$Remote, [string]$Dir)
    try {
        $raw = ssh -o ConnectTimeout=10 "$Remote" "grep -E '^TELEPHONY_INTERNAL_TOKEN=' ${Dir}/.env 2>/dev/null | head -1"
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return "" }
        $line = $raw.Trim()
        if ($line -match '^\s*TELEPHONY_INTERNAL_TOKEN\s*=\s*(.+)$') {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    } catch {
        return ""
    }
    return ""
}

switch ($Mode) {
    "Unit" {
        $py = Find-PythonExe
        Set-Location $ProjectDir
        & $py -m pytest @(
            "backend/tests/test_telephony_pipeline.py",
            "backend/tests/telephony_daemon",
            "-q",
            "--tb=short"
        )
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "OK pytest telephony (local)." -ForegroundColor Green
    }
    "RemoteSsh" {
        $rh = "${RemoteUser}@${RemoteHost}"
        Write-Host "SSH $rh -> bash scripts/smoke_telephony_stack.sh $RemoteDir" -ForegroundColor Yellow
        # CRLF dans le script copie depuis Windows casse « set -o pipefail » sous bash sur le Pi
        $remoteCmd = "cd $RemoteDir && chmod +x scripts/smoke_telephony_stack.sh 2>/dev/null; " +
            "sed -i 's/\r$//' scripts/smoke_telephony_stack.sh 2>/dev/null; " +
            "bash scripts/smoke_telephony_stack.sh $RemoteDir"
        ssh -o ConnectTimeout=10 "$rh" $remoteCmd
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "OK smoke distant." -ForegroundColor Green
    }
    "Endpoints" {
        $api = "http://${RemoteHost}:${ApiPort}"
        $tel = "http://${RemoteHost}:${TelephonyPort}"
        Write-Host "GET $api/health" -ForegroundColor Yellow
        try {
            $h = Invoke-RestMethod -Uri "$api/health" -TimeoutSec 10
            $h | ConvertTo-Json -Compress
        } catch {
            Write-Host "ECHEC API: $_" -ForegroundColor Red
            exit 1
        }
        Write-Host "GET $tel/health" -ForegroundColor Yellow
        try {
            $th = Invoke-RestMethod -Uri "$tel/health" -TimeoutSec 5
            $th | ConvertTo-Json -Compress
        } catch {
            Write-Host "ATTENTION daemon (8090): $_ — normal si telephony arrete." -ForegroundColor DarkYellow
        }
        $tok = $InternalToken.Trim()
        if (-not $tok -and $FetchTokenFromRemote) {
            $tok = Get-RemoteInternalToken -Remote "${RemoteUser}@${RemoteHost}" -Dir $RemoteDir
            if ($tok) {
                Write-Host "Token lu sur le serveur ($RemoteDir/.env) pour le POST interne." -ForegroundColor DarkGray
            }
        }
        if (-not $tok) {
            $envPath = if ($EnvFile -ne "") { $EnvFile } else { Join-Path $ProjectDir ".env" }
            $tok = Read-DotEnvToken -Path $envPath
        }
        if (-not $tok) {
            $prod = Join-Path $ProjectDir ".env.prod"
            $tok = Read-DotEnvToken -Path $prod
        }
        if ($tok) {
            Write-Host "POST $api/api/v1/internal/telephony-events" -ForegroundColor Yellow
            $body = @{
                event_type = "call.session.log"
                timestamp  = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                data       = @{
                    call_id       = 1
                    phone_number  = "000"
                    message       = "run_telephony_tests.ps1 Endpoints"
                    level         = "info"
                }
                source     = "LocalEndpointsCheck"
            } | ConvertTo-Json -Depth 5 -Compress
            try {
                $r = Invoke-WebRequest -Uri "$api/api/v1/internal/telephony-events" -Method POST `
                    -Headers @{ "X-VocalGuard-Internal" = $tok; "Content-Type" = "application/json" } `
                    -Body $body -TimeoutSec 15 -UseBasicParsing
                Write-Host "HTTP $($r.StatusCode) (POST interne OK)" -ForegroundColor Green
            } catch {
                $code = $null
                try {
                    $resp = $_.Exception.Response
                    if ($resp) { $code = [int]$resp.StatusCode }
                } catch { }
                if ($code -eq 401) {
                    Write-Host "401 Non autorise : le TELEPHONY_INTERNAL_TOKEN du PC ne correspond pas au .env sur node14." -ForegroundColor Yellow
                    Write-Host "  Utilise : -FetchTokenFromRemote   ou   -InternalToken '<valeur du Pi>'" -ForegroundColor DarkYellow
                    if ($StrictInternalPost) { exit 1 }
                } else {
                    Write-Host "ECHEC POST interne: $_" -ForegroundColor Red
                    exit 1
                }
            }
        } else {
            Write-Host "Pas de token — skip POST interne (ajoute -FetchTokenFromRemote ou -InternalToken)." -ForegroundColor DarkYellow
        }
        Write-Host "OK checks endpoints -> $RemoteHost" -ForegroundColor Green
    }
    "Stack" {
        $py = Find-PythonExe
        $apiOrigin = "http://${RemoteHost}:${ApiPort}"
        $daemonOrigin = "http://${RemoteHost}:${TelephonyPort}"
        $ef = if ($EnvFile -ne "") { $EnvFile } else { Join-Path $ProjectDir ".env" }
        Write-Host "python scripts/test_api_stack.py -> $apiOrigin" -ForegroundColor Yellow
        Set-Location $ProjectDir
        & $py (Join-Path $ProjectDir "scripts/test_api_stack.py") @(
            "--api-origin", $apiOrigin,
            "--daemon-url", $daemonOrigin,
            "--env-file", $ef
        )
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "OK test_api_stack.py" -ForegroundColor Green
    }
}
