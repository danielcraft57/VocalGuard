param(
    [string]$AppServerName = "",
    [string]$AppServerUser = "",
    [string]$RemoteDir = "/opt/vocalguard",
    [int]$MinSizeMb = 10,
    [switch]$SkipArchive,
    [switch]$DryRun,
    [switch]$NoLogrotate
)

$ErrorActionPreference = "Stop"
$ProjectDir = (Get-Item (Split-Path -Parent $PSScriptRoot)).FullName
$LocalScript = Join-Path $PSScriptRoot "cleanup_prod_logs.sh"
$LocalInstallLogrotate = Join-Path $PSScriptRoot "install_logrotate.sh"
$LocalLogrotateTemplate = Join-Path $PSScriptRoot "logrotate\vocalguard"

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

if (-not (Test-Path $LocalScript)) {
    throw "Script introuvable: $LocalScript"
}

Write-Host "=== Nettoyage logs prod -> $AppRemoteHost ===" -ForegroundColor Cyan
Write-Host "RemoteDir: $RemoteDir | Seuil: ${MinSizeMb} Mo" -ForegroundColor Gray

scp -q $LocalScript "${AppRemoteHost}:/tmp/cleanup_prod_logs.sh"
if ($LASTEXITCODE -ne 0) { throw "scp echoue vers $AppRemoteHost" }

if (-not $NoLogrotate) {
    if (-not (Test-Path $LocalInstallLogrotate)) { throw "Script introuvable: $LocalInstallLogrotate" }
    if (-not (Test-Path $LocalLogrotateTemplate)) { throw "Template introuvable: $LocalLogrotateTemplate" }
    ssh "$AppRemoteHost" "mkdir -p $RemoteDir/scripts/logrotate"
    if ($LASTEXITCODE -ne 0) { throw "mkdir distant echoue" }
    scp -q $LocalInstallLogrotate "${AppRemoteHost}:$RemoteDir/scripts/install_logrotate.sh"
    if ($LASTEXITCODE -ne 0) { throw "scp install_logrotate echoue" }
    scp -q $LocalLogrotateTemplate "${AppRemoteHost}:$RemoteDir/scripts/logrotate/vocalguard"
    if ($LASTEXITCODE -ne 0) { throw "scp logrotate template echoue" }
}

$installLogrotateFlag = if ($NoLogrotate) { "0" } else { "1" }
$skipArchiveFlag = if ($SkipArchive.IsPresent) { "1" } else { "0" }
$dryRunFlag = if ($DryRun.IsPresent) { "1" } else { "0" }

$remoteCmd = "chmod +x /tmp/cleanup_prod_logs.sh $RemoteDir/scripts/install_logrotate.sh 2>/dev/null; APP_DIR=$RemoteDir MIN_SIZE_MB=$MinSizeMb SKIP_ARCHIVE=$skipArchiveFlag DRY_RUN=$dryRunFlag INSTALL_LOGROTATE=$installLogrotateFlag bash /tmp/cleanup_prod_logs.sh; rm -f /tmp/cleanup_prod_logs.sh"

ssh "$AppRemoteHost" $remoteCmd
if ($LASTEXITCODE -ne 0) { throw "Nettoyage distant echoue" }

Write-Host ""
Write-Host "OK - logs nettoyes sur $AppServerName" -ForegroundColor Green
