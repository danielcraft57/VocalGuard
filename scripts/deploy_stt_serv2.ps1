# Compat : redirige vers deploy_stt.ps1 (cible historique serv2).
# Preferer : powershell -File scripts/deploy_stt.ps1
param(
    [string]$SttServerName = "serv2.lan",
    [string]$SttUser = "pi",
    [string]$Engine = "whisper",
    [string]$WhisperModel = "small",
    [string]$WhisperThreads = "2",
    [string]$ModelSourceHost = "node15.lan",
    [string]$ModelSourceUser = "pi",
    [string]$VoskModelDir = "vosk-model-fr-0.22",
    [string]$InternalToken = ""
)

Write-Host "NOTE: deploy_stt_serv2.ps1 est obsolete; utilise deploy_stt.ps1 (defaut node15)."
& (Join-Path $PSScriptRoot "deploy_stt.ps1") `
    -SttServerName $SttServerName `
    -SttUser $SttUser `
    -Engine $Engine `
    -WhisperModel $WhisperModel `
    -WhisperThreads $WhisperThreads `
    -ModelSourceHost $ModelSourceHost `
    -ModelSourceUser $ModelSourceUser `
    -VoskModelDir $VoskModelDir `
    -InternalToken $InternalToken
