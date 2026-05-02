param(
    [string]$AppServerName = "",
    [string]$AppServerUser = "",
    [string]$NginxServerName = "",
    [string]$NginxServerUser = "",
    [string[]]$DomainAliases = @(),
    [string]$RemoteDir = "/opt/vocalguard",
    [switch]$SkipFrontendBuild,
    [switch]$RestartService,
    [bool]$InstallServices = $true,
    [bool]$EnableFrontendService = $false,
    [bool]$EnableModemTestService = $false,
    [switch]$NoSystemDeps,
    [switch]$ConfigureNginx,
    [switch]$EnableHttps,
    [switch]$FixNginxLegacyWarnings,
    [string]$CertbotEmail = "",
    [string]$CertbotCertName = "vocalguard-multidomain",
    [switch]$HealthCheck,
    [bool]$EnableTelephonyDaemon = $false
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Get-Item (Split-Path -Parent $PSScriptRoot)).FullName
$ArchivePath = Join-Path $env:TEMP "vocalguard_deploy.tar.gz"
# Renseigne par le bloc ConfigureNginx : sert aux health checks (SSL auto si cert deja sur le serveur).
$script:NginxVocalguardUsesSsl = $null

# Priorité paramètres > variables d'environnement > defaults
if (-not $AppServerName -or $AppServerName.Trim() -eq "") {
    if ($env:RPI_APP_SERVER -and $env:RPI_APP_SERVER.Trim() -ne "") {
        $AppServerName = $env:RPI_APP_SERVER.Trim()
    } elseif ($env:RPI_SERVER -and $env:RPI_SERVER.Trim() -ne "") {
        # compat legacy
        $AppServerName = $env:RPI_SERVER.Trim()
    } else {
        $AppServerName = "node11.lan"
    }
}
if (-not $AppServerUser -or $AppServerUser.Trim() -eq "") {
    if ($env:RPI_APP_USER -and $env:RPI_APP_USER.Trim() -ne "") {
        $AppServerUser = $env:RPI_APP_USER.Trim()
    } elseif ($env:RPI_USER -and $env:RPI_USER.Trim() -ne "") {
        # compat legacy
        $AppServerUser = $env:RPI_USER.Trim()
    } else {
        $AppServerUser = "pi"
    }
}
if (-not $NginxServerName -or $NginxServerName.Trim() -eq "") {
    if ($env:RPI_NGINX_SERVER -and $env:RPI_NGINX_SERVER.Trim() -ne "") {
        $NginxServerName = $env:RPI_NGINX_SERVER.Trim()
    } else {
        $NginxServerName = "node12.lan"
    }
}
if (-not $NginxServerUser -or $NginxServerUser.Trim() -eq "") {
    if ($env:RPI_NGINX_USER -and $env:RPI_NGINX_USER.Trim() -ne "") {
        $NginxServerUser = $env:RPI_NGINX_USER.Trim()
} else {
        $NginxServerUser = "pi"
    }
}

# Domain aliases: paramètres > variable d'env > defaults historiques
if (($DomainAliases | Measure-Object).Count -eq 0) {
    if ($env:RPI_DOMAIN_ALIASES -and $env:RPI_DOMAIN_ALIASES.Trim() -ne "") {
        $DomainAliases = $env:RPI_DOMAIN_ALIASES.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
    } else {
        $DomainAliases = @(
            "vocalguard.danielcraft.fr",
            "phone.danielcraft.fr",
            "repondeur.danielcraft.fr"
        )
    }
}
$AppRemoteHost = "$AppServerUser@$AppServerName"
$NginxRemoteHost = "$NginxServerUser@$NginxServerName"

function Step([string]$text) { Write-Host $text -ForegroundColor Yellow }
function Ok([string]$text) { Write-Host $text -ForegroundColor Green }
function Info([string]$text) { Write-Host $text -ForegroundColor DarkGray }
function Warn([string]$text) { Write-Host $text -ForegroundColor Red }

function Invoke-SshStrict {
    param(
        [string]$RemoteHost,
        [string]$Command,
        [switch]$CaptureOutput
    )
    if ($CaptureOutput) {
        $output = ssh "$RemoteHost" "$Command"
        if ($LASTEXITCODE -ne 0) {
            throw "Remote command failed on ${RemoteHost}: $Command"
        }
        return $output
    }
    ssh "$RemoteHost" "$Command"
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed on ${RemoteHost}: $Command"
    }
}

function Copy-ScpStrict {
    param(
        [string]$Source,
        [string]$Destination
    )
    scp -q "$Source" "$Destination"
    if ($LASTEXITCODE -ne 0) {
        throw "SCP failed: $Source -> $Destination"
    }
}

function Install-RemoteService {
    param(
        [string]$RemoteHost,
        [string]$ServiceName,
        [string]$Content,
        [bool]$Enable = $true,
        [bool]$Start = $true
    )
    $tmpLocal = Join-Path $env:TEMP "$ServiceName"
    Set-Content -Path $tmpLocal -Value $Content -Encoding UTF8
    scp -q $tmpLocal "${RemoteHost}:/tmp/$ServiceName"
    Remove-Item $tmpLocal -Force -ErrorAction SilentlyContinue
    ssh "$RemoteHost" "sudo mv /tmp/$ServiceName /etc/systemd/system/$ServiceName && sudo chown root:root /etc/systemd/system/$ServiceName && sudo chmod 644 /etc/systemd/system/$ServiceName" | Out-Null
    ssh "$RemoteHost" "sudo systemctl daemon-reload" | Out-Null
    if ($Enable) { ssh "$RemoteHost" "sudo systemctl enable $ServiceName" | Out-Null }
    if ($Start) { ssh "$RemoteHost" "sudo systemctl restart $ServiceName" | Out-Null }
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "App server:   $AppRemoteHost" -ForegroundColor Cyan
Write-Host "Nginx server: $NginxRemoteHost" -ForegroundColor Cyan
Write-Host "Target dir: $RemoteDir" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Step "[1/8] SSH connectivity check"
ssh -o ConnectTimeout=5 "$AppRemoteHost" "echo OK" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "SSH inaccessible (app): $AppRemoteHost" }
if ($ConfigureNginx) {
    ssh -o ConnectTimeout=5 "$NginxRemoteHost" "echo OK" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "SSH inaccessible (nginx): $NginxRemoteHost" }
}
Ok "SSH OK (app$(if ($ConfigureNginx) { ' + nginx' } else { '' }))"

if (-not $SkipFrontendBuild) {
    Step "[2/8] Build frontend and sync into backend/web"
    & (Join-Path $ProjectDir "scripts\build_and_copy_frontend.ps1")
    Ok "Frontend built"
} else {
    Step "[2/8] Frontend build skipped"
}

Step "[3/8] Remote bootstrap (dirs + python + venv)"
ssh "$AppRemoteHost" "sudo mkdir -p $RemoteDir && sudo chown -R ${AppServerUser}:${AppServerUser} $RemoteDir && sudo chmod 775 $RemoteDir"
$venvExists = (ssh "$AppRemoteHost" "test -d $RemoteDir/venv && echo yes || echo no").Trim()

if (-not $NoSystemDeps) {
    ssh "$AppRemoteHost" "sudo apt-get update -qq && sudo apt-get install -y python3-venv python3-pip python3-dev portaudio19-dev libasound2-dev rsync" | Out-Null
    if ($ConfigureNginx) {
        ssh "$NginxRemoteHost" "sudo apt-get update -qq && sudo apt-get install -y nginx" | Out-Null
    }
}
if ($venvExists -eq "no") {
    ssh "$AppRemoteHost" "cd $RemoteDir && python3 -m venv venv" | Out-Null
}
ssh "$AppRemoteHost" "cd $RemoteDir && mkdir -p logs data audio_cache recordings && chmod -R u+rwX,g+rwX logs data audio_cache recordings" | Out-Null
Ok "Remote bootstrap ready"

Step "[4/8] Create release archive"
Push-Location $ProjectDir
try {
    tar -czf $ArchivePath `
        --exclude=venv `
        --exclude=.git `
        --exclude=node_modules `
        --exclude=frontend/.next `
        --exclude=frontend/out `
        --exclude=logs `
        --exclude=audio_cache `
        --exclude=data `
        --exclude=recordings `
        --exclude=*.db `
        --exclude=.env `
        --exclude=.env.prod `
        .
} finally {
    Pop-Location
}
if (-not (Test-Path $ArchivePath)) { throw "Archive build failed" }
Ok "Archive ready: $ArchivePath"

Step "[5/8] Upload and extract code"
scp -q $ArchivePath "${AppRemoteHost}:${RemoteDir}/vocalguard_release.tar.gz"
ssh "$AppRemoteHost" "cd $RemoteDir && tar -xzf vocalguard_release.tar.gz && rm -f vocalguard_release.tar.gz" | Out-Null
Remove-Item $ArchivePath -Force -ErrorAction SilentlyContinue
ssh "$AppRemoteHost" "sudo chown -R ${AppServerUser}:${AppServerUser} $RemoteDir && sudo find $RemoteDir -type d -exec chmod 775 {} \; && sudo find $RemoteDir -type f -exec chmod 664 {} \;" | Out-Null
ssh "$AppRemoteHost" "cd $RemoteDir && chmod +x run.sh run_backend.sh scripts/*.sh 2>/dev/null || true" | Out-Null
Ok "Code uploaded"

Step "[6/8] Sync production env (.env.prod -> .env)"
$localEnvProd = Join-Path $ProjectDir ".env.prod"
$localEnvProdExample = Join-Path $ProjectDir ".env.prod.example"
$localEnvFallback = Join-Path $ProjectDir "env.example"
if (Test-Path $localEnvProd) {
    Info "Using local .env.prod"
    scp -q $localEnvProd "${AppRemoteHost}:${RemoteDir}/.env.prod"
    ssh "$AppRemoteHost" "cd $RemoteDir && [ -f .env ] && cp .env .env.backup.\$(date +%Y%m%d%H%M%S) || true && cp .env.prod .env && chmod 600 .env" | Out-Null
} elseif (Test-Path $localEnvProdExample) {
    Info ".env.prod absent, fallback to .env.prod.example"
    scp -q $localEnvProdExample "${AppRemoteHost}:${RemoteDir}/.env"
} elseif (Test-Path $localEnvFallback) {
    Info ".env.prod absent, fallback to env.example"
    scp -q $localEnvFallback "${AppRemoteHost}:${RemoteDir}/.env"
} else {
    throw "Missing local .env.prod / .env.prod.example / env.example"
}
ssh "$AppRemoteHost" "cd $RemoteDir && grep -q '^VG_ENV=' .env || echo 'VG_ENV=prod' >> .env" | Out-Null
ssh "$AppRemoteHost" "cd $RemoteDir && grep -q '^PUBLIC_BASE_URL=' .env || echo 'PUBLIC_BASE_URL=https://$NginxServerName' >> .env" | Out-Null
ssh "$AppRemoteHost" "cd $RemoteDir && grep -q '^DATABASE_URL=postgresql' .env || echo 'WARNING: DATABASE_URL is not PostgreSQL in .env'" | Out-Null
Ok "Production env synced"

Step "[7/8] Install Python dependencies (venv)"
Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "cd $RemoteDir && source venv/bin/activate && python -m pip install -q --upgrade pip && python -m pip install -q -r requirements.txt"
Ok "Dependencies installed"

Step "[8/9] PostgreSQL readiness and service"
ssh "$AppRemoteHost" "cd $RemoteDir && source venv/bin/activate && python -m compileall backend -q" | Out-Null
if ($RestartService) {
    ssh "$AppRemoteHost" "sudo systemctl restart vocalguard; sudo systemctl try-restart vocalguard-telephony 2>/dev/null || true; sudo systemctl status vocalguard --no-pager -n 20" | Out-Host
    Ok "Service restarted"
} else {
    Info "Service restart skipped (use -RestartService)"
}

if ($InstallServices) {
    Step "[services] Generate and install systemd units"
    $serviceUser = $AppServerUser
    $serviceGroup = $AppServerUser
    $venvPython = "$RemoteDir/venv/bin/python"
    $frontendDir = "$RemoteDir/frontend"

    $telephonyUnitExtra = ""
    if ($EnableTelephonyDaemon) {
        $telephonyUnitExtra = @"

After=vocalguard-telephony.service
Wants=vocalguard-telephony.service
"@
    }

    $vocalguardService = @"
[Unit]
Description=VocalGuard API
After=network-online.target
Wants=network-online.target
$telephonyUnitExtra

[Service]
Type=simple
User=$serviceUser
Group=$serviceGroup
WorkingDirectory=$RemoteDir
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=$RemoteDir
EnvironmentFile=-$RemoteDir/.env
ExecStart=$venvPython -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:$RemoteDir/logs/vocalguard.log
StandardError=append:$RemoteDir/logs/vocalguard.log
SyslogIdentifier=vocalguard

[Install]
WantedBy=multi-user.target
"@
    Install-RemoteService -RemoteHost $AppRemoteHost -ServiceName "vocalguard.service" -Content $vocalguardService -Enable $true -Start $true

    $telephonyBindHost = '${TELEPHONY_BIND_HOST}'
    $telephonyBindPort = '${TELEPHONY_BIND_PORT}'
    $telephonyService = @"
[Unit]
Description=VocalGuard Telephony (modem, appels sortants, WebSocket audio)
After=network-online.target
Wants=network-online.target
Before=vocalguard.service

[Service]
Type=simple
User=$serviceUser
Group=$serviceGroup
WorkingDirectory=$RemoteDir
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=$RemoteDir
Environment=TELEPHONY_BIND_HOST=127.0.0.1
Environment=TELEPHONY_BIND_PORT=8090
EnvironmentFile=-$RemoteDir/.env
ExecStart=$venvPython -m uvicorn backend.telephony_daemon.main:app --host $telephonyBindHost --port $telephonyBindPort
Restart=always
RestartSec=5
StandardOutput=append:$RemoteDir/logs/vocalguard-telephony.log
StandardError=append:$RemoteDir/logs/vocalguard-telephony.log
SyslogIdentifier=vocalguard-telephony

[Install]
WantedBy=multi-user.target
"@
    if ($EnableTelephonyDaemon) {
        Install-RemoteService -RemoteHost $AppRemoteHost -ServiceName "vocalguard-telephony.service" -Content $telephonyService -Enable $true -Start $true
    } else {
        ssh "$AppRemoteHost" "sudo systemctl disable --now vocalguard-telephony.service 2>/dev/null || true" | Out-Null
        Info "vocalguard-telephony.service desactive (EnableTelephonyDaemon=false)."
    }

    $celeryService = @"
[Unit]
Description=VocalGuard Celery Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$serviceUser
Group=$serviceGroup
WorkingDirectory=$RemoteDir
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=$RemoteDir
EnvironmentFile=-$RemoteDir/.env
ExecStart=$venvPython -m celery -A backend.celery_app.celery_app worker --loglevel=info --pool=solo
Restart=always
RestartSec=5
StandardOutput=append:$RemoteDir/logs/vocalguard-celery.log
StandardError=append:$RemoteDir/logs/vocalguard-celery.log
SyslogIdentifier=vocalguard-celery

[Install]
WantedBy=multi-user.target
"@
    Install-RemoteService -RemoteHost $AppRemoteHost -ServiceName "vocalguard-celery.service" -Content $celeryService -Enable $true -Start $true

    if ($EnableFrontendService) {
        $frontendService = @"
[Unit]
Description=VocalGuard Frontend (Next.js)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$serviceUser
Group=$serviceGroup
WorkingDirectory=$frontendDir
Environment=NODE_ENV=production
EnvironmentFile=-$RemoteDir/.env
ExecStart=/usr/bin/env bash -lc 'cd "$frontendDir" && npm run start -- --hostname 0.0.0.0 --port 3000'
Restart=always
RestartSec=5
StandardOutput=append:$RemoteDir/logs/vocalguard-frontend.log
StandardError=append:$RemoteDir/logs/vocalguard-frontend.log
SyslogIdentifier=vocalguard-frontend

[Install]
WantedBy=multi-user.target
"@
        Install-RemoteService -RemoteHost $AppRemoteHost -ServiceName "vocalguard-frontend.service" -Content $frontendService -Enable $true -Start $true
    } else {
        Info "Frontend service disabled (EnableFrontendService=false)."
        ssh "$AppRemoteHost" "sudo systemctl disable --now vocalguard-frontend.service 2>/dev/null || true" | Out-Null
    }

    if ($EnableModemTestService) {
        $modemService = @"
[Unit]
Description=VocalGuard Modem Test
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$serviceUser
Group=$serviceGroup
WorkingDirectory=$RemoteDir
Environment=PYTHONUNBUFFERED=1
Environment=USE_MODEM_VOICE_MODE=1
EnvironmentFile=-$RemoteDir/.env
ExecStart=$venvPython $RemoteDir/scripts/test_modem_answer_play_record.py
Restart=on-failure
StandardOutput=append:$RemoteDir/logs/test_modem_answer_play_record.log
StandardError=append:$RemoteDir/logs/test_modem_answer_play_record.log

[Install]
WantedBy=multi-user.target
"@
        Install-RemoteService -RemoteHost $AppRemoteHost -ServiceName "vocalguard-test-modem.service" -Content $modemService -Enable $true -Start $true
    } else {
        ssh "$AppRemoteHost" "sudo systemctl disable --now vocalguard-test-modem.service 2>/dev/null || true" | Out-Null
    }

    ssh "$AppRemoteHost" "sudo systemctl daemon-reload && sudo systemctl status vocalguard vocalguard-celery vocalguard-telephony --no-pager -n 10 2>/dev/null || sudo systemctl status vocalguard vocalguard-celery --no-pager -n 10" | Out-Host
    Ok "Systemd services installed/updated"
}

if ($ConfigureNginx) {
    Step "[9/9] Nginx reverse-proxy optimization (dedicated host)"
    $serverNames = @($NginxServerName) + $DomainAliases | Select-Object -Unique
    $serverNameLine = ($serverNames -join " ")
    $proxyTarget = if ($AppServerName -and $AppServerName.Trim() -ne "") { "${AppServerName}:8000" } else { "127.0.0.1:8000" }

    $nginxOutgoingWs = ""
    if ($EnableTelephonyDaemon) {
        $telephonyWsTarget = if ($AppServerName -and $AppServerName.Trim() -ne "") { "${AppServerName}:8090" } else { "127.0.0.1:8090" }
        $nginxOutgoingWs = @"

    location /ws/outgoing-call/ {
        proxy_pass http://$telephonyWsTarget;
        proxy_http_version 1.1;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        proxy_set_header Upgrade `$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
"@
    }

    $nginxConfigHttp = @"
server {
    listen 80;
    listen [::]:80;
    server_name $serverNameLine;

    client_max_body_size 25m;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location /_next/ {
        proxy_pass http://$proxyTarget;
        proxy_http_version 1.1;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        expires 1h;
        add_header Cache-Control "public, max-age=3600";
    }
"@ + $nginxOutgoingWs + @"

    location /ws/ {
        proxy_pass http://$proxyTarget;
        proxy_http_version 1.1;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        proxy_set_header Upgrade `$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / {
        proxy_pass http://$proxyTarget;
        proxy_http_version 1.1;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
"@

    $nginxConfigHttps = @"
server {
    listen 80;
    listen [::]:80;
    server_name $serverNameLine;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://`$host`$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name $serverNameLine;

    ssl_certificate /etc/letsencrypt/live/$CertbotCertName/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$CertbotCertName/privkey.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 25m;

    location /_next/ {
        proxy_pass http://$proxyTarget;
        proxy_http_version 1.1;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        expires 1h;
        add_header Cache-Control "public, max-age=3600";
    }
"@ + $nginxOutgoingWs + @"

    location /ws/ {
        proxy_pass http://$proxyTarget;
        proxy_http_version 1.1;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        proxy_set_header Upgrade `$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / {
        proxy_pass http://$proxyTarget;
        proxy_http_version 1.1;
        proxy_set_header Host `$host;
        proxy_set_header X-Real-IP `$remote_addr;
        proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto `$scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
"@

    # HTTPS si -EnableHttps OU certificat Let's Encrypt deja present (evite vhost 80 seul apres deploy puis SNI 443 -> autre site)
    $useNginxSsl = $false
    $runCertbot = $false
    if ($EnableHttps) {
        $useNginxSsl = $true
        $runCertbot = $true
    } else {
        try {
            $certProbeRaw = Invoke-SshStrict -RemoteHost $NginxRemoteHost -Command "test -f /etc/letsencrypt/live/$CertbotCertName/fullchain.pem && echo yes || echo no" -CaptureOutput
            $certProbe = ($certProbeRaw | Out-String).Trim()
            if ($certProbe -eq "yes") {
                $useNginxSsl = $true
                $runCertbot = $false
                Info "Certificat $CertbotCertName deja sur $NginxServerName : vhost vocalguard HTTP+HTTPS (sans certbot)."
            }
        } catch {
            Info "Sonde certificat nginx ignoree: $_"
        }
    }

    if ($useNginxSsl -and $runCertbot) {
        if (-not $CertbotEmail -or $CertbotEmail.Trim() -eq "") {
            if ($env:CERTBOT_EMAIL -and $env:CERTBOT_EMAIL.Trim() -ne "") {
                $CertbotEmail = $env:CERTBOT_EMAIL.Trim()
            } else {
                throw "EnableHttps requires -CertbotEmail or env CERTBOT_EMAIL."
            }
        }
        $certbotDomains = @(
            $serverNames | Where-Object {
                $_ -match "^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$" -and
                $_ -notmatch "\.(lan|local|home|internal)$"
            }
        )
        if (($certbotDomains | Measure-Object).Count -eq 0) {
            throw "EnableHttps: no public domain available for certbot (current server names: $serverNameLine)"
        }
        if (-not $NoSystemDeps) {
            Invoke-SshStrict -RemoteHost $NginxRemoteHost -Command "sudo apt-get update -qq && sudo apt-get install -y certbot"
        }
        $domainArgs = ($certbotDomains | ForEach-Object { "-d $_" }) -join " "
        Invoke-SshStrict -RemoteHost $NginxRemoteHost -Command "sudo mkdir -p /var/www/html/.well-known/acme-challenge && sudo certbot certonly --webroot -w /var/www/html --non-interactive --agree-tos --email '$CertbotEmail' --cert-name '$CertbotCertName' --expand $domainArgs"
        Ok "HTTPS : certbot cert '$CertbotCertName' renouvelle ou etendu."
    }

    $tmpNginx = Join-Path $env:TEMP "vocalguard_nginx.conf"
    if ($useNginxSsl) {
        Set-Content -Path $tmpNginx -Value $nginxConfigHttps -Encoding UTF8
        $script:NginxVocalguardUsesSsl = $true
    } else {
        Set-Content -Path $tmpNginx -Value $nginxConfigHttp -Encoding UTF8
        $script:NginxVocalguardUsesSsl = $false
    }
    Copy-ScpStrict -Source $tmpNginx -Destination "${NginxRemoteHost}:/tmp/vocalguard_nginx.conf"
    Remove-Item $tmpNginx -Force -ErrorAction SilentlyContinue
    Invoke-SshStrict -RemoteHost $NginxRemoteHost -Command "sudo mv /tmp/vocalguard_nginx.conf /etc/nginx/sites-available/vocalguard && sudo ln -sf /etc/nginx/sites-available/vocalguard /etc/nginx/sites-enabled/vocalguard && sudo nginx -t && sudo systemctl reload nginx"

    if ($FixNginxLegacyWarnings) {
        Info "Applying optional cleanup on legacy nginx vhosts (safe best-effort)"
        $cleanupCmd = "if [ -f /etc/nginx/sites-enabled/danielcraft.fr ]; then " +
            "sudo sed -i -E 's/listen ([0-9]+) ssl http2;/listen \1 ssl;/g' /etc/nginx/sites-enabled/danielcraft.fr; " +
            "sudo sed -i -E 's/listen \[::\]:([0-9]+) ssl http2;/listen [::]:\1 ssl;/g' /etc/nginx/sites-enabled/danielcraft.fr; " +
            "grep -q 'http2 on;' /etc/nginx/sites-enabled/danielcraft.fr || sudo sed -i '/listen \[::\]:443 ssl;/a\    http2 on;' /etc/nginx/sites-enabled/danielcraft.fr; " +
            "sudo sed -i -E 's/^\s*ssl_stapling\s+on;/    # ssl_stapling on; # disabled by deploy script (no OCSP in cert)/' /etc/nginx/sites-enabled/danielcraft.fr; " +
            "sudo sed -i -E 's/^\s*ssl_stapling_verify\s+on;/    # ssl_stapling_verify on; # disabled by deploy script (no OCSP in cert)/' /etc/nginx/sites-enabled/danielcraft.fr; " +
            "fi; " +
            "sudo nginx -t && sudo systemctl reload nginx"
        Invoke-SshStrict -RemoteHost $NginxRemoteHost -Command $cleanupCmd
    }

    if ($useNginxSsl) {
        Ok "Nginx vocalguard : HTTPS actif (cert $CertbotCertName) -> $proxyTarget"
    } else {
        Ok "Nginx vocalguard : HTTP seulement -> $proxyTarget"
    }
    Ok "Nginx configured on $NginxServerName -> $proxyTarget"
}

if ($HealthCheck) {
    Step "[health] End-to-end checks"
    $checks = @()
    $primaryPublicDomain = if ($DomainAliases.Count -gt 0) { $DomainAliases[0] } else { $NginxServerName }
    $useSslForNginx = if ($null -ne $script:NginxVocalguardUsesSsl) { $script:NginxVocalguardUsesSsl } else { $EnableHttps }

    # 1) backend direct (plusieurs essais : uvicorn peut refuser la connexion juste apres restart systemd)
    $backendOk = $false
    $backendDetail = ""
    for ($attempt = 0; $attempt -lt 8; $attempt++) {
        try {
            $raw = Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "curl -fsS http://127.0.0.1:8000/health" -CaptureOutput
            $backendOk = $true
            $backendDetail = ($raw | Out-String).Trim()
            break
        } catch {
            $backendDetail = $_.Exception.Message
            if ($attempt -lt 7) {
                Start-Sleep -Seconds 3
            }
        }
    }
    $checks += [pscustomobject]@{
        Name = "Backend direct ($AppServerName)"
        Ok = $backendOk
        Detail = $backendDetail
    }

    # 2) nginx local (edge -> app)
    if ($ConfigureNginx) {
        try {
            $localHealthCommand = if ($useSslForNginx) {
                "curl -fsS -k -H 'Host: $primaryPublicDomain' https://127.0.0.1/health"
            } else {
                "curl -fsS http://127.0.0.1/health"
            }
            $raw = Invoke-SshStrict -RemoteHost $NginxRemoteHost -Command $localHealthCommand -CaptureOutput
            $checks += [pscustomobject]@{
                Name = "Nginx local ($NginxServerName)"
                Ok = $true
                Detail = ($raw | Out-String).Trim()
            }
        } catch {
            $checks += [pscustomobject]@{
                Name = "Nginx local ($NginxServerName)"
                Ok = $false
                Detail = $_.Exception.Message
            }
        }
    }

    # 3) nginx public hostname
    if ($ConfigureNginx) {
        try {
            $hostnameHealthCommand = if ($useSslForNginx) {
                "curl -fsS https://$primaryPublicDomain/health"
            } else {
                "curl -fsS http://$NginxServerName/health"
            }
            $raw = Invoke-SshStrict -RemoteHost $NginxRemoteHost -Command $hostnameHealthCommand -CaptureOutput
            $checks += [pscustomobject]@{
                Name = if ($useSslForNginx) { "Nginx public https ($primaryPublicDomain)" } else { "Nginx hostname ($NginxServerName)" }
                Ok = $true
                Detail = ($raw | Out-String).Trim()
            }
        } catch {
            $checks += [pscustomobject]@{
                Name = "Nginx hostname ($NginxServerName)"
                Ok = $false
                Detail = $_.Exception.Message
            }
        }
    }

    # 4) alias hostnames (forced Host header on nginx local)
    if ($ConfigureNginx -and $DomainAliases.Count -gt 0) {
        foreach ($domain in $DomainAliases) {
            try {
                $aliasHealthCommand = if ($useSslForNginx) {
                    "curl -fsS -k -H 'Host: $domain' https://127.0.0.1/health"
                } else {
                    "curl -fsS -H 'Host: $domain' http://127.0.0.1/health"
                }
                $raw = Invoke-SshStrict -RemoteHost $NginxRemoteHost -Command $aliasHealthCommand -CaptureOutput
                $checks += [pscustomobject]@{
                    Name = if ($useSslForNginx) { "Nginx alias https ($domain)" } else { "Nginx alias ($domain)" }
                    Ok = $true
                    Detail = ($raw | Out-String).Trim()
                }
            } catch {
                $checks += [pscustomobject]@{
                    Name = "Nginx alias ($domain)"
                    Ok = $false
                    Detail = $_.Exception.Message
                }
            }
        }
    }

Write-Host ""
    Write-Host "Health check summary:" -ForegroundColor Yellow
    $failed = 0
    foreach ($c in $checks) {
        if ($c.Ok) {
            Ok ("  [OK] {0} -> {1}" -f $c.Name, $c.Detail)
        } else {
            Warn ("  [KO] {0} -> {1}" -f $c.Name, $c.Detail)
            $failed += 1
        }
    }
    if ($failed -eq 0) {
        Ok "All health checks passed."
    } else {
        throw "Health checks failed: $failed"
    }
}

Write-Host ""
Write-Host "Deploy complete." -ForegroundColor Green
Write-Host "Quick checks:" -ForegroundColor Yellow
Write-Host "  ssh $AppRemoteHost" -ForegroundColor White
Write-Host "  cd $RemoteDir && source venv/bin/activate" -ForegroundColor White
Write-Host "  grep '^DATABASE_URL=' .env" -ForegroundColor White
Write-Host "  curl http://localhost:8000/health" -ForegroundColor White
if ($ConfigureNginx) {
    Write-Host "  ssh $NginxRemoteHost" -ForegroundColor White
    Write-Host "  curl -I http://$NginxServerName" -ForegroundColor White
}
