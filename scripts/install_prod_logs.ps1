param(
    [string]$AppServerName = "",
    [string]$AppServerUser = "",
    [string]$RemoteDir = "/opt/vocalguard",
    [switch]$RunMaintenanceNow
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$ProjectDir = (Get-Item (Split-Path -Parent $ScriptDir)).FullName

if (-not $AppServerName -or $AppServerName.Trim() -eq "") {
    if ($env:RPI_APP_SERVER -and $env:RPI_APP_SERVER.Trim() -ne "") {
        $AppServerName = $env:RPI_APP_SERVER.Trim()
    } else {
        $AppServerName = "node14.lan"
    }
}
if (-not $AppServerUser -or $AppServerUser.Trim() -eq "") {
    if ($env:RPI_APP_USER -and $env:RPI_APP_USER.Trim() -ne "") {
        $AppServerUser = $env:RPI_APP_USER.Trim()
    } else {
        $AppServerUser = "pi"
    }
}

$AppRemoteHost = "${AppServerUser}@${AppServerName}"
$venvPython = "$RemoteDir/venv/bin/python"

$scriptFiles = @(
    "install_logrotate.sh",
    "logrotate\vocalguard",
    "prod_log_maintenance.sh",
    "install_prod_log_maintenance_celery.sh",
    "cleanup_prod_logs.sh"
)

$pythonFiles = @(
    "backend\celery_app.py",
    "backend\workers\maintenance_tasks.py"
)

Write-Host "=== Install logs Celery prod -> $AppRemoteHost ===" -ForegroundColor Cyan

ssh "$AppRemoteHost" "mkdir -p $RemoteDir/scripts/logrotate $RemoteDir/data"
if ($LASTEXITCODE -ne 0) { throw "mkdir distant echoue" }

foreach ($rel in $scriptFiles) {
    $local = Join-Path $ScriptDir $rel
    if (-not (Test-Path $local)) { throw "Fichier manquant: $local" }
    $remote = if ($rel -like "logrotate\*") {
        "$RemoteDir/scripts/logrotate/vocalguard"
    } else {
        "$RemoteDir/scripts/$(Split-Path -Leaf $rel)"
    }
    scp -q $local "${AppRemoteHost}:$remote"
    if ($LASTEXITCODE -ne 0) { throw "scp echoue: $rel" }
}

foreach ($rel in $pythonFiles) {
    $local = Join-Path $ProjectDir $rel
    if (-not (Test-Path $local)) { throw "Fichier manquant: $local" }
    $remoteRel = ($rel -replace '\\', '/')
    scp -q $local "${AppRemoteHost}:$RemoteDir/$remoteRel"
    if ($LASTEXITCODE -ne 0) { throw "scp echoue: $rel" }
}

$beatUnit = @"
[Unit]
Description=VocalGuard Celery Beat (taches planifiees)
After=network-online.target vocalguard-celery.service
Wants=network-online.target

[Service]
Type=simple
User=$AppServerUser
Group=$AppServerUser
WorkingDirectory=$RemoteDir
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=$RemoteDir
Environment=APP_DIR=$RemoteDir
EnvironmentFile=-$RemoteDir/.env
ExecStart=$venvPython -m celery -A backend.celery_app.celery_app beat --loglevel=info
Restart=always
RestartSec=5
StandardOutput=append:$RemoteDir/logs/vocalguard-celery-beat.log
StandardError=append:$RemoteDir/logs/vocalguard-celery-beat.log
SyslogIdentifier=vocalguard-celery-beat

[Install]
WantedBy=multi-user.target
"@

$tmpBeat = Join-Path $env:TEMP "vocalguard-celery-beat.service"
Set-Content -Path $tmpBeat -Value $beatUnit -Encoding UTF8
scp -q $tmpBeat "${AppRemoteHost}:/tmp/vocalguard-celery-beat.service"
Remove-Item $tmpBeat -Force -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0) { throw "scp beat unit echoue" }

$remoteCmd = "chmod +x $RemoteDir/scripts/install_logrotate.sh $RemoteDir/scripts/prod_log_maintenance.sh $RemoteDir/scripts/install_prod_log_maintenance_celery.sh $RemoteDir/scripts/cleanup_prod_logs.sh; APP_DIR=$RemoteDir bash $RemoteDir/scripts/install_prod_log_maintenance_celery.sh; sudo mv /tmp/vocalguard-celery-beat.service /etc/systemd/system/vocalguard-celery-beat.service; sudo chown root:root /etc/systemd/system/vocalguard-celery-beat.service; sudo chmod 644 /etc/systemd/system/vocalguard-celery-beat.service; sudo systemctl daemon-reload; sudo systemctl enable vocalguard-celery-beat.service; sudo systemctl restart vocalguard-celery.service; sudo systemctl restart vocalguard-celery-beat.service"

ssh "$AppRemoteHost" $remoteCmd
if ($LASTEXITCODE -ne 0) { throw "Installation Celery Beat echoue" }

if ($RunMaintenanceNow.IsPresent) {
    Write-Host "Declenchement maintenance via Celery..." -ForegroundColor Yellow
    ssh "$AppRemoteHost" "cd $RemoteDir; source venv/bin/activate; python -m celery -A backend.celery_app.celery_app call backend.workers.maintenance_tasks.run_log_maintenance"
    if ($LASTEXITCODE -ne 0) { throw "Maintenance Celery echoue" }
}

Write-Host ""
Write-Host "OK - logrotate + Celery Beat installes sur $AppServerName" -ForegroundColor Green
Write-Host "Planification: 03:15 Europe/Paris (beat_schedule log-maintenance-daily)" -ForegroundColor Gray
Write-Host "Verifier: ssh $AppRemoteHost systemctl status vocalguard-celery-beat" -ForegroundColor Gray
