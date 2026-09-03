# Deploy du worker OSINT VocalGuard (PhoneInfoga) sur node15.
# Usage: powershell -File scripts/deploy_osint_node15.ps1
#        powershell -File scripts/deploy_osint_node15.ps1 -InternalToken "xxx"

param(
    [string]$OsintServerName = "node15.lan",
    [string]$OsintUser = "pi",
    [string]$InternalToken = "",
    [string]$PhoneinfogaVersion = "v2.11.0"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RemoteRoot = "/opt/vocalguard-osint"
$Remote = "${OsintUser}@${OsintServerName}"

Write-Host "=== Deploy OSINT worker sur $Remote ==="

$staging = Join-Path $env:TEMP "vocalguard-osint-sync"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path $staging | Out-Null
New-Item -ItemType Directory -Path (Join-Path $staging "backend") | Out-Null
Copy-Item -Recurse (Join-Path $RepoRoot "backend\osint_worker") (Join-Path $staging "backend\osint_worker")
Copy-Item (Join-Path $RepoRoot "scripts\systemd\vocalguard-osint.service") (Join-Path $staging "vocalguard-osint.service")
Copy-Item (Join-Path $RepoRoot "scripts\ensure_prospectlab_osint_token.py") (Join-Path $staging "ensure_prospectlab_osint_token.py")

ssh $Remote "sudo mkdir -p $RemoteRoot/bin"
ssh $Remote "sudo chown -R ${OsintUser}:${OsintUser} $RemoteRoot"

scp -r "$staging\backend" "${Remote}:${RemoteRoot}/"
scp "$staging\vocalguard-osint.service" "${Remote}:/tmp/vocalguard-osint.service"
scp "$staging\ensure_prospectlab_osint_token.py" "${Remote}:/tmp/ensure_prospectlab_osint_token.py"
Remove-Item -Recurse -Force $staging

# Binaire PhoneInfoga Go (arm64) si absent / trop vieux
$binCheck = ssh $Remote "test -x $RemoteRoot/bin/phoneinfoga; $RemoteRoot/bin/phoneinfoga version 2>/dev/null"
Write-Host "PhoneInfoga actuel: $binCheck"
if ($binCheck -notmatch "2\.11") {
    Write-Host "Telechargement PhoneInfoga $PhoneinfogaVersion (Linux_arm64)..."
    ssh $Remote @"
set -e
cd /tmp
curl -fsSL -o phoneinfoga_Linux_arm64.tar.gz "https://github.com/sundowndev/phoneinfoga/releases/download/$PhoneinfogaVersion/phoneinfoga_Linux_arm64.tar.gz"
tar xzf phoneinfoga_Linux_arm64.tar.gz
install -m 755 phoneinfoga $RemoteRoot/bin/phoneinfoga
rm -f phoneinfoga_Linux_arm64.tar.gz phoneinfoga
$RemoteRoot/bin/phoneinfoga version
"@
}

# venv leger
ssh $Remote @"
set -e
cd $RemoteRoot
if [ ! -d venv ]; then python3 -m venv venv; fi
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q 'fastapi>=0.115' 'uvicorn[standard]>=0.30' 'pydantic>=2.10' 'httpx>=0.27' loguru phonenumbers
"@

# Token
$existingTokenRaw = ssh $Remote "grep -E '^OSINT_INTERNAL_TOKEN=' $RemoteRoot/.env.osint 2>/dev/null || true"
$existingToken = if ($null -ne $existingTokenRaw) { "$existingTokenRaw".Trim() } else { "" }
if ($InternalToken) {
    $token = $InternalToken
} elseif ($existingToken -match '^OSINT_INTERNAL_TOKEN=(.+)$') {
    $token = $Matches[1].Trim()
} else {
    $token = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
    Write-Host "Nouveau token OSINT genere."
}

$existingPlRaw = ssh $Remote "grep -E '^PROSPECTLAB_API_TOKEN=' $RemoteRoot/.env.osint 2>/dev/null || true"
$plToken = ""
if ("$existingPlRaw".Trim() -match '^PROSPECTLAB_API_TOKEN=(.+)$') {
    $plToken = $Matches[1].Trim()
}
if (-not $plToken) {
    Write-Host "Creation / reuse token ProspectLab (VocalGuard-OSINT)..."
    $plToken = (ssh $Remote "cd /opt/prospectlab; ./env/bin/python /tmp/ensure_prospectlab_osint_token.py").Trim()
}

$envContent = @"
OSINT_INTERNAL_TOKEN=$token
PHONEINFOGA_BIN=$RemoteRoot/bin/phoneinfoga
PHONEINFOGA_API_URL=http://127.0.0.1:5011
PROSPECTLAB_URL=http://127.0.0.1:5000
PROSPECTLAB_API_TOKEN=$plToken
"@
$envTmp = Join-Path $env:TEMP "vocalguard-osint.env"
Set-Content -Path $envTmp -Value $envContent -NoNewline
scp $envTmp "${Remote}:${RemoteRoot}/.env.osint"
Remove-Item $envTmp

# Liberer 5011 si un phoneinfoga de test tourne
ssh $Remote "pkill -f 'phoneinfoga serve' 2>/dev/null || true"

ssh $Remote "sudo cp /tmp/vocalguard-osint.service /etc/systemd/system/vocalguard-osint.service"
ssh $Remote "sudo systemctl daemon-reload"
ssh $Remote "sudo systemctl enable vocalguard-osint"
ssh $Remote "sudo systemctl restart vocalguard-osint"
Start-Sleep -Seconds 3
ssh $Remote "systemctl is-active vocalguard-osint; curl -s http://127.0.0.1:8110/health"

Write-Host ""
Write-Host "=== OK ==="
Write-Host "Sur node14 (.env) :"
Write-Host "  OSINT_SERVICE_URL=http://${OsintServerName}:8110"
Write-Host "  OSINT_INTERNAL_TOKEN=$token"
Write-Host "Puis redemarrer vocalguard / celery worker."
