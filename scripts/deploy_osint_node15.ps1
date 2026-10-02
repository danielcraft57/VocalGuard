# Deploy du worker OSINT VocalGuard (PhoneInfoga + reputation) sur node15.
# Usage: powershell -File scripts/deploy_osint_node15.ps1
#        powershell -File scripts/deploy_osint_node15.ps1 -InternalToken "xxx"
#
# Cles optionnelles (preservees si deja dans .env.osint distant) :
#   HUHU_API_KEY, TELLOWS_API_KEY, TELLOWS_PARTNER, SPAM_NUMBERS_API_KEY,
#   IPQS_API_KEY, TRUECALLER_INSTALLATION_ID, NUMVERIFY_API_KEY,
#   OSINT_REPUTATION_DISABLE=phoneintel,truecaller

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

# venv + outils reputation
ssh $Remote @"
set -e
cd $RemoteRoot
if [ ! -d venv ]; then python3 -m venv venv; fi
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q 'fastapi>=0.115' 'uvicorn[standard]>=0.30' 'pydantic>=2.10' 'httpx>=0.27' loguru phonenumbers
# PhoneIntel (Tellows/SpamCalls/c-qui) + truecallerpy (session optionnelle)
./venv/bin/pip install -q phoneintel truecallerpy || true
./venv/bin/phoneintel --credits >/dev/null 2>&1 || ./venv/bin/python -c 'import phoneintel; print("phoneintel ok")' || echo 'WARN phoneintel'
./venv/bin/python -c 'import truecallerpy; print("truecallerpy ok")' || echo 'WARN truecallerpy'
"@

# Token + merge env (ne pas ecraser les cles API existantes)
$existingEnvRaw = ssh $Remote "cat $RemoteRoot/.env.osint 2>/dev/null || true"
$existingMap = @{}
foreach ($line in ($existingEnvRaw -split "`n")) {
    $t = "$line".Trim()
    if ($t -match '^\s*#' -or -not $t) { continue }
    if ($t -match '^([A-Za-z0-9_]+)=(.*)$') {
        $existingMap[$Matches[1]] = $Matches[2]
    }
}

if ($InternalToken) {
    $token = $InternalToken
} elseif ($existingMap.ContainsKey("OSINT_INTERNAL_TOKEN") -and $existingMap["OSINT_INTERNAL_TOKEN"]) {
    $token = $existingMap["OSINT_INTERNAL_TOKEN"]
} else {
    $token = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
    Write-Host "Nouveau token OSINT genere."
}

$plToken = ""
if ($existingMap.ContainsKey("PROSPECTLAB_API_TOKEN") -and $existingMap["PROSPECTLAB_API_TOKEN"]) {
    $plToken = $existingMap["PROSPECTLAB_API_TOKEN"]
}
if (-not $plToken) {
    Write-Host "Creation / reuse token ProspectLab (VocalGuard-OSINT)..."
    $plToken = (ssh $Remote "cd /opt/prospectlab; ./env/bin/python /tmp/ensure_prospectlab_osint_token.py").Trim()
}

function Get-EnvOrEmpty([string]$key) {
    if ($existingMap.ContainsKey($key)) { return $existingMap[$key] }
    return ""
}

$envLines = @(
    "OSINT_INTERNAL_TOKEN=$token",
    "PHONEINFOGA_BIN=$RemoteRoot/bin/phoneinfoga",
    "PHONEINFOGA_API_URL=http://127.0.0.1:5011",
    "PHONEINTEL_BIN=$RemoteRoot/venv/bin/phoneintel",
    "PROSPECTLAB_URL=http://127.0.0.1:5000",
    "PROSPECTLAB_API_TOKEN=$plToken"
)

# Cles optionnelles preservees / place-holders
$optionalKeys = @(
    "HUHU_API_KEY",
    "HUHU_API_URL",
    "TELLOWS_API_KEY",
    "TELLOWS_PARTNER",
    "TELLOWS_API_HOST",
    "SPAM_NUMBERS_API_KEY",
    "SPAM_NUMBERS_API_URL",
    "IPQS_API_KEY",
    "TRUECALLER_INSTALLATION_ID",
    "NUMVERIFY_API_KEY",
    "OSINT_REPUTATION_DISABLE"
)
foreach ($k in $optionalKeys) {
    $v = Get-EnvOrEmpty $k
    if ($v -ne "") {
        $envLines += "$k=$v"
    }
}

$envContent = ($envLines -join "`n") + "`n"
$envTmp = Join-Path $env:TEMP "vocalguard-osint.env"
Set-Content -Path $envTmp -Value $envContent -NoNewline -Encoding ascii
scp $envTmp "${Remote}:${RemoteRoot}/.env.osint"
Remove-Item $envTmp

# Liberer 5011 si un phoneinfoga de test tourne
ssh $Remote "pkill -f 'phoneinfoga serve' 2>/dev/null || true"

ssh $Remote "sudo cp /tmp/vocalguard-osint.service /etc/systemd/system/vocalguard-osint.service"
ssh $Remote "sudo systemctl daemon-reload"
ssh $Remote "sudo systemctl enable vocalguard-osint"
ssh $Remote "sudo systemctl restart vocalguard-osint"
Start-Sleep -Seconds 5

$healthPy = @'
import urllib.request, json
print(json.dumps(json.loads(urllib.request.urlopen("http://127.0.0.1:8110/health", timeout=8).read().decode()), indent=2))
'@
$healthTmp = Join-Path $env:TEMP "osint_health_check.py"
Set-Content -Path $healthTmp -Value $healthPy -Encoding UTF8
scp $healthTmp "${Remote}:/tmp/osint_health_check.py"
ssh $Remote "systemctl is-active vocalguard-osint; python3 /tmp/osint_health_check.py; rm -f /tmp/osint_health_check.py"
Remove-Item $healthTmp

Write-Host ""
Write-Host "=== OK ==="
Write-Host "Providers actifs sans cle : tellows (HTML), spamcalls (+ phoneintel si OK)."
Write-Host "Pour brancher les APIs, ajouter dans ${RemoteRoot}/.env.osint puis restart :"
Write-Host "  HUHU_API_KEY=..."
Write-Host "  TELLOWS_API_KEY=...   TELLOWS_PARTNER=..."
Write-Host "  SPAM_NUMBERS_API_KEY=..."
Write-Host "  IPQS_API_KEY=..."
Write-Host "  TRUECALLER_INSTALLATION_ID=..."
Write-Host ""
Write-Host "Sur node14 (.env) :"
Write-Host "  OSINT_SERVICE_URL=http://${OsintServerName}:8110"
Write-Host "  OSINT_INTERNAL_TOKEN=$token"
Write-Host "Puis redemarrer vocalguard / celery worker."
