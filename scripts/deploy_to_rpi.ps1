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
    [switch]$HealthCheck
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Get-Item (Split-Path -Parent $PSScriptRoot)).FullName
$ArchivePath = Join-Path $env:TEMP "vocalguard_deploy.tar.gz"

# Priorité paramètres > variables d'environnement > defaults
if (-not $AppServerName -or $AppServerName.Trim() -eq "") {
    if ($env:RPI_APP_SERVER -and $env:RPI_APP_SERVER.Trim() -ne "") {
        $AppServerName = $env:RPI_APP_SERVER.Trim()
    } elseif ($env:RPI_SERVER -and $env:RPI_SERVER.Trim() -ne "") {
        # compat legacy
        $AppServerName = $env:RPI_SERVER.Trim()
    } else {
        $AppServerName = "app-node.lan"
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
        $NginxServerName = "edge-node.lan"
    }
}
if (-not $NginxServerUser -or $NginxServerUser.Trim() -eq "") {
    if ($env:RPI_NGINX_USER -and $env:RPI_NGINX_USER.Trim() -ne "") {
        $NginxServerUser = $env:RPI_NGINX_USER.Trim()
} else {
        $NginxServerUser = "pi"
    }
}
$AppRemoteHost = "$AppServerUser@$AppServerName"
$NginxRemoteHost = "$NginxServerUser@$NginxServerName"

function Step([string]$text) { Write-Host $text -ForegroundColor Yellow }
function Ok([string]$text) { Write-Host $text -ForegroundColor Green }
function Info([string]$text) { Write-Host $text -ForegroundColor DarkGray }
function Warn([string]$text) { Write-Host $text -ForegroundColor Red }

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
ssh "$AppRemoteHost" "cd $RemoteDir && source venv/bin/activate && pip install -q --upgrade pip && pip install -q -r requirements.txt" | Out-Null
Ok "Dependencies installed"

Step "[8/9] PostgreSQL readiness and service"
ssh "$AppRemoteHost" "cd $RemoteDir && source venv/bin/activate && python -m compileall backend -q" | Out-Null
if ($RestartService) {
    ssh "$AppRemoteHost" "sudo systemctl restart vocalguard && sudo systemctl status vocalguard --no-pager -n 20" | Out-Host
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

    $vocalguardService = @"
[Unit]
Description=VocalGuard API
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

    ssh "$AppRemoteHost" "sudo systemctl daemon-reload && sudo systemctl status vocalguard vocalguard-celery --no-pager -n 10" | Out-Host
    Ok "Systemd services installed/updated"
}

if ($ConfigureNginx) {
    Step "[9/9] Nginx reverse-proxy optimization (dedicated host)"
    $serverNames = @($NginxServerName) + $DomainAliases | Select-Object -Unique
    $serverNameLine = ($serverNames -join " ")
    $proxyTarget = if ($AppServerName -and $AppServerName.Trim() -ne "") { "${AppServerName}:8000" } else { "127.0.0.1:8000" }

    $nginxConfig = @"
server {
    listen 80;
    listen [::]:80;
    server_name $serverNameLine;

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
    $tmpNginx = Join-Path $env:TEMP "vocalguard_nginx.conf"
    Set-Content -Path $tmpNginx -Value $nginxConfig -Encoding UTF8
    scp -q $tmpNginx "${NginxRemoteHost}:/tmp/vocalguard_nginx.conf"
    Remove-Item $tmpNginx -Force -ErrorAction SilentlyContinue
    ssh "$NginxRemoteHost" "sudo mv /tmp/vocalguard_nginx.conf /etc/nginx/sites-available/vocalguard && sudo ln -sf /etc/nginx/sites-available/vocalguard /etc/nginx/sites-enabled/vocalguard && sudo nginx -t && sudo systemctl reload nginx"
    Ok "Nginx configured on $NginxServerName -> $proxyTarget"
}

if ($HealthCheck) {
    Step "[health] End-to-end checks"
    $checks = @()

    # 1) backend direct
    try {
        $raw = ssh "$AppRemoteHost" "curl -fsS http://127.0.0.1:8000/health"
        $checks += [pscustomobject]@{
            Name = "Backend direct ($AppServerName)"
            Ok = $true
            Detail = ($raw | Out-String).Trim()
        }
    } catch {
        $checks += [pscustomobject]@{
            Name = "Backend direct ($AppServerName)"
            Ok = $false
            Detail = $_.Exception.Message
        }
    }

    # 2) nginx local (edge -> app)
    if ($ConfigureNginx) {
        try {
            $raw = ssh "$NginxRemoteHost" "curl -fsS http://127.0.0.1/health"
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
            $raw = ssh "$NginxRemoteHost" "curl -fsS http://$NginxServerName/health"
            $checks += [pscustomobject]@{
                Name = "Nginx hostname ($NginxServerName)"
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
                $raw = ssh "$NginxRemoteHost" "curl -fsS -H 'Host: $domain' http://127.0.0.1/health"
                $checks += [pscustomobject]@{
                    Name = "Nginx alias ($domain)"
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
