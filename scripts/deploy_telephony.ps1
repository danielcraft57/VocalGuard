<#
.SYNOPSIS
  Deploy ou mise a jour uniquement du service VocalGuard Telephony (modem, daemon :8090).

.DESCRIPTION
  - Archive le depot (comme deploy_to_rpi mais sans build frontend ni nginx)
  - Sync .env via .env.prod
  - pip install -r requirements.txt
  - Installe / met a jour vocalguard-telephony.service et redemarre

.PARAMETER RestartOnly
  Ne rebuild pas l'archive : redemarre seulement systemd sur le serveur (code deja a jour).

.EXAMPLE
  .\scripts\deploy_telephony.ps1 -AppServerName node11.lan -RunTests

.EXAMPLE
  .\scripts\deploy_telephony.ps1 -RestartOnly -RunTests
#>
param(
    [string]$AppServerName = "",
    [string]$AppServerUser = "",
    [string]$RemoteDir = "/opt/vocalguard",
    [switch]$NoSystemDeps,
    [switch]$RestartOnly,
    [switch]$RunTests
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Get-Item (Split-Path -Parent $PSScriptRoot)).FullName
$ArchivePath = Join-Path $env:TEMP "vocalguard_telephony_deploy.tar.gz"

if (-not $AppServerName -or $AppServerName.Trim() -eq "") {
    if ($env:RPI_APP_SERVER -and $env:RPI_APP_SERVER.Trim() -ne "") {
        $AppServerName = $env:RPI_APP_SERVER.Trim()
    } elseif ($env:RPI_SERVER -and $env:RPI_SERVER.Trim() -ne "") {
        $AppServerName = $env:RPI_SERVER.Trim()
    } else {
        $AppServerName = "node11.lan"
    }
}
if (-not $AppServerUser -or $AppServerUser.Trim() -eq "") {
    if ($env:RPI_APP_USER -and $env:RPI_APP_USER.Trim() -ne "") {
        $AppServerUser = $env:RPI_APP_USER.Trim()
    } elseif ($env:RPI_USER -and $env:RPI_USER.Trim() -ne "") {
        $AppServerUser = $env:RPI_USER.Trim()
    } else {
        $AppServerUser = "pi"
    }
}

$AppRemoteHost = "$AppServerUser@$AppServerName"

function Step([string]$text) { Write-Host $text -ForegroundColor Yellow }
function Ok([string]$text) { Write-Host $text -ForegroundColor Green }
function Info([string]$text) { Write-Host $text -ForegroundColor DarkGray }

function Invoke-SshStrict {
    param([string]$RemoteHost, [string]$Command, [switch]$CaptureOutput)
    if ($CaptureOutput) {
        $output = ssh "$RemoteHost" "$Command"
        if ($LASTEXITCODE -ne 0) { throw "Remote failed ${RemoteHost}: $Command" }
        return $output
    }
    ssh "$RemoteHost" "$Command"
    if ($LASTEXITCODE -ne 0) { throw "Remote failed ${RemoteHost}: $Command" }
}

function Copy-ScpStrict {
    param([string]$Source, [string]$Destination)
    scp -q "$Source" "$Destination"
    if ($LASTEXITCODE -ne 0) { throw "SCP failed: $Source -> $Destination" }
}

function Install-RemoteTelephonyService {
    param([string]$RemoteHost, [string]$RemoteDirPath, [string]$ServiceUser, [string]$VenvPython)
    $telephonyBindHost = '${TELEPHONY_BIND_HOST}'
    $telephonyBindPort = '${TELEPHONY_BIND_PORT}'
    $content = @"
[Unit]
Description=VocalGuard Telephony (modem, appels sortants, WebSocket audio)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$ServiceUser
Group=$ServiceUser
WorkingDirectory=$RemoteDirPath
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=$RemoteDirPath
Environment=TELEPHONY_BIND_HOST=127.0.0.1
Environment=TELEPHONY_BIND_PORT=8090
EnvironmentFile=-$RemoteDirPath/.env
ExecStart=$VenvPython -m uvicorn backend.telephony_daemon.main:app --host $telephonyBindHost --port $telephonyBindPort --log-config $RemoteDirPath/config/uvicorn_telephony_logging.yaml
Restart=always
RestartSec=5
LimitNOFILE=65536
StandardOutput=append:$RemoteDirPath/logs/vocalguard-telephony.log
StandardError=append:$RemoteDirPath/logs/vocalguard-telephony.log
SyslogIdentifier=vocalguard-telephony

[Install]
WantedBy=multi-user.target
"@
    $tmp = Join-Path $env:TEMP "vocalguard-telephony.service"
    Set-Content -Path $tmp -Value $content -Encoding UTF8
    scp -q $tmp "${RemoteHost}:/tmp/vocalguard-telephony.service"
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    ssh "$RemoteHost" "sudo mv /tmp/vocalguard-telephony.service /etc/systemd/system/vocalguard-telephony.service && sudo chown root:root /etc/systemd/system/vocalguard-telephony.service && sudo chmod 644 /etc/systemd/system/vocalguard-telephony.service" | Out-Null
    ssh "$RemoteHost" "sudo systemctl daemon-reload && sudo systemctl enable vocalguard-telephony.service && sudo systemctl restart vocalguard-telephony.service" | Out-Null
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Deploy TELEPHONY only -> $AppRemoteHost : $RemoteDir" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Step "[1] SSH"
ssh -o ConnectTimeout=8 "$AppRemoteHost" "echo OK" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "SSH inaccessible: $AppRemoteHost" }
Ok "SSH OK"

if (-not $RestartOnly) {
    Step "[2] Archive (sans frontend build)"
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
            --exclude=scripts/experimental `
            --exclude=*.db `
            --exclude=.env `
            --exclude=.env.prod `
            .
    } finally {
        Pop-Location
    }
    if (-not (Test-Path $ArchivePath)) { throw "Archive build failed" }
    Ok "Archive: $ArchivePath"

    Step "[3] Upload + extract"
    ssh "$AppRemoteHost" "mkdir -p $RemoteDir && sudo chown -R ${AppServerUser}:${AppServerUser} $RemoteDir 2>/dev/null || true"
    Copy-ScpStrict -Source $ArchivePath -Destination "${AppRemoteHost}:${RemoteDir}/vocalguard_telephony.tar.gz"
    Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "cd $RemoteDir && tar -xzf vocalguard_telephony.tar.gz && rm -f vocalguard_telephony.tar.gz"
    Remove-Item $ArchivePath -Force -ErrorAction SilentlyContinue
    Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "sudo chown -R ${AppServerUser}:${AppServerUser} $RemoteDir && chmod +x $RemoteDir/scripts/*.sh 2>/dev/null || true"
    Ok "Code synchronise"

    Step "[4] venv + dossiers"
    $venvExists = (ssh "$AppRemoteHost" "test -d $RemoteDir/venv && echo yes || echo no").Trim()
    if (-not $NoSystemDeps) {
        Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "sudo apt-get update -qq && sudo apt-get install -y python3-venv python3-pip python3-dev portaudio19-dev libasound2-dev"
    }
    if ($venvExists -eq "no") {
        Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "cd $RemoteDir && python3 -m venv venv"
    }
    Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "cd $RemoteDir && mkdir -p logs data audio_cache recordings && chmod -R u+rwX,g+rwX logs data audio_cache recordings"

    Step "[5] .env (production)"
    $localEnvProd = Join-Path $ProjectDir ".env.prod"
    $localEnvProdExample = Join-Path $ProjectDir ".env.prod.example"
    $localEnvFallback = Join-Path $ProjectDir "env.example"
    if (Test-Path $localEnvProd) {
        Copy-ScpStrict -Source $localEnvProd -Destination "${AppRemoteHost}:${RemoteDir}/.env.prod"
        Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "cd $RemoteDir && cp .env .env.backup.before_telephony_deploy 2>/dev/null || true && cp .env.prod .env && chmod 600 .env"
    } elseif (Test-Path $localEnvProdExample) {
        Info ".env.prod absent -> .env.prod.example"
        Copy-ScpStrict -Source $localEnvProdExample -Destination "${AppRemoteHost}:${RemoteDir}/.env"
    } elseif (Test-Path $localEnvFallback) {
        Copy-ScpStrict -Source $localEnvFallback -Destination "${AppRemoteHost}:${RemoteDir}/.env"
    } else {
        throw "Fichier env manquant (.env.prod / .env.prod.example / env.example)"
    }
    Ok ".env synchronise"

    Step "[6] pip install"
    Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "cd $RemoteDir && source venv/bin/activate && python -m pip install -q --upgrade pip && python -m pip install -q -r requirements.txt && python -m compileall backend -q"
    Ok "Dependencies OK"

    Step "[7] systemd vocalguard-telephony"
    $venvPy = "$RemoteDir/venv/bin/python"
    Install-RemoteTelephonyService -RemoteHost $AppRemoteHost -RemoteDirPath $RemoteDir -ServiceUser $AppServerUser -VenvPython $venvPy
    Ok "Service vocalguard-telephony active"
} else {
    Step "[restart-only] systemctl restart vocalguard-telephony"
    Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "sudo systemctl restart vocalguard-telephony.service && sudo systemctl status vocalguard-telephony --no-pager -n 15"
    Ok "Telephony redemarre"
}

if ($RunTests) {
    Step "[tests] pytest + smoke sur le serveur"
    Invoke-SshStrict -RemoteHost $AppRemoteHost -Command "cd $RemoteDir && source venv/bin/activate && sed -i 's/\r$//' scripts/smoke_telephony_stack.sh 2>/dev/null; bash scripts/smoke_telephony_stack.sh $RemoteDir"
}

Write-Host ""
Ok "Deploy telephony termine."
Write-Host "Verification locale depuis ton PC:" -ForegroundColor Yellow
Write-Host "  .\scripts\run_telephony_tests.ps1 -Mode Endpoints -RemoteHost $AppServerName" -ForegroundColor White
