# Deploy du service STT VocalGuard (Whisper via whisper-server + FastAPI).
# Cible par defaut : node15.lan (Pi 5).
# Usage: powershell -File scripts/deploy_stt.ps1
#        powershell -File scripts/deploy_stt.ps1 -SttServerName serv2.lan -WhisperThreads 2

param(
    [string]$SttServerName = "node15.lan",
    [string]$SttUser = "pi",
    [string]$Engine = "whisper",
    [string]$WhisperModel = "base",
    [string]$WhisperThreads = "4",
    [string]$WhisperBeamSize = "1",
    [string]$WhisperBestOf = "1",
    [string]$WhisperServerPort = "8101",
    [string]$ModelSourceHost = "serv2.lan",
    [string]$ModelSourceUser = "pi",
    [string]$VoskModelDir = "vosk-model-fr-0.22",
    [string]$InternalToken = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RemoteRoot = "/opt/vocalguard-stt"
$Remote = "${SttUser}@${SttServerName}"
# Mappe le label (tiny/base/small) vers le bin ggml quantifie.
$ModelMap = @{
    "tiny"  = "ggml-tiny-q5_1.bin"
    "base"  = "ggml-base-q5_1.bin"
    "small" = "ggml-small-q5_1.bin"
}
$WhisperModelKey = $WhisperModel.Trim().ToLowerInvariant()
if ($ModelMap.ContainsKey($WhisperModelKey)) {
    $ModelName = $ModelMap[$WhisperModelKey]
} else {
    $ModelName = "ggml-${WhisperModelKey}-q5_1.bin"
}
$DefaultPrompt = "Messagerie telephonique francaise. Bonjour, Monsieur, Madame, entreprise, merci, a bientot, rappelez-moi au 0X XX XX XX XX."

Write-Host "=== Deploy STT sur $Remote (engine=$Engine model=$WhisperModel -> $ModelName threads=$WhisperThreads) ==="

# Sync code minimal
$staging = Join-Path $env:TEMP "vocalguard-stt-sync"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path $staging | Out-Null
Copy-Item -Recurse (Join-Path $RepoRoot "backend") (Join-Path $staging "backend")
Copy-Item (Join-Path $RepoRoot "requirements.txt") (Join-Path $staging "requirements.txt")
Copy-Item (Join-Path $RepoRoot "scripts\systemd\vocalguard-stt.service") (Join-Path $staging "vocalguard-stt.service")
Copy-Item (Join-Path $RepoRoot "scripts\systemd\vocalguard-whisper.service") (Join-Path $staging "vocalguard-whisper.service")
Copy-Item (Join-Path $RepoRoot "scripts\setup_whisper_cpp.sh") (Join-Path $staging "setup_whisper_cpp.sh")

ssh $Remote "sudo mkdir -p $RemoteRoot/vosk-models $RemoteRoot/whisper-models $RemoteRoot/scripts"
ssh $Remote "sudo chown -R ${SttUser}:${SttUser} $RemoteRoot"

scp -r "$staging\backend" "${Remote}:${RemoteRoot}/"
scp "$staging\requirements.txt" "${Remote}:${RemoteRoot}/"
scp "$staging\vocalguard-stt.service" "${Remote}:/tmp/vocalguard-stt.service"
scp "$staging\vocalguard-whisper.service" "${Remote}:/tmp/vocalguard-whisper.service"
scp "$staging\setup_whisper_cpp.sh" "${Remote}:${RemoteRoot}/scripts/setup_whisper_cpp.sh"

Remove-Item -Recurse -Force $staging

if ($Engine -eq "vosk") {
    $modelCheck = ssh $Remote "test -d $RemoteRoot/vosk-models/$VoskModelDir/am && echo ok"
    if ($modelCheck -notmatch "ok") {
        Write-Host "Copie modele $VoskModelDir depuis ${ModelSourceUser}@${ModelSourceHost}..."
        ssh $Remote "rsync -az --info=progress2 ${ModelSourceUser}@${ModelSourceHost}:/opt/vocalguard/vosk-models/$VoskModelDir/ $RemoteRoot/vosk-models/$VoskModelDir/"
    }
}

if ($Engine -eq "whisper") {
    $ggmlCheck = ssh $Remote "test -f $RemoteRoot/whisper-models/$ModelName && echo ok"
    if ($ggmlCheck -notmatch "ok") {
        Write-Host "Tentative copie $ModelName depuis ${ModelSourceUser}@${ModelSourceHost}..."
        $copied = ssh $Remote "rsync -az ${ModelSourceUser}@${ModelSourceHost}:/opt/vocalguard-stt/whisper-models/$ModelName $RemoteRoot/whisper-models/$ModelName; echo ok"
        if ($copied -notmatch "ok") {
            Write-Host "Copie LAN echouee, le setup telechargera le modele."
        }
    }
    Write-Host "Build / verif whisper.cpp (cli+server) sur $SttServerName..."
    ssh $Remote "chmod +x $RemoteRoot/scripts/setup_whisper_cpp.sh"
    ssh $Remote "STT_BASE_PATH=$RemoteRoot STT_WHISPER_GGML_NAME=$ModelName bash $RemoteRoot/scripts/setup_whisper_cpp.sh"

    # Ajuste threads/beam du unit whisper-server selon les params deploy
    $whisperUnit = @"
[Unit]
Description=VocalGuard Whisper.cpp server (modele en RAM)
After=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/opt/vocalguard-stt
EnvironmentFile=-/opt/vocalguard-stt/.env.stt
Environment=LD_LIBRARY_PATH=/opt/vocalguard-stt/whisper.cpp/build/bin
ExecStart=/opt/vocalguard-stt/whisper.cpp/build/bin/whisper-server -m /opt/vocalguard-stt/whisper-models/$ModelName -l fr -t $WhisperThreads -bs $WhisperBeamSize -bo $WhisperBestOf --host 127.0.0.1 --port $WhisperServerPort --inference-path /inference
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"@
    $unitTmp = Join-Path $env:TEMP "vocalguard-whisper.service"
    Set-Content -Path $unitTmp -Value $whisperUnit -NoNewline
    scp $unitTmp "${Remote}:/tmp/vocalguard-whisper.service"
    Remove-Item $unitTmp
}

ssh $Remote @"
set -e
cd $RemoteRoot
if [ ! -d venv ]; then python3 -m venv venv; fi
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q 'fastapi>=0.115' 'uvicorn[standard]>=0.30' 'pydantic>=2.10' 'python-multipart>=0.0.9' soundfile loguru httpx pydub audioop-lts numpy edge-tts
"@

$existingTokenRaw = ssh $Remote "grep -E '^STT_INTERNAL_TOKEN=' $RemoteRoot/.env.stt 2>/dev/null || true"
$existingToken = if ($null -ne $existingTokenRaw) { "$existingTokenRaw".Trim() } else { "" }
if ($InternalToken) {
    $token = $InternalToken
} elseif ($existingToken -match '^STT_INTERNAL_TOKEN=(.+)$') {
    $token = $Matches[1].Trim()
} else {
    $token = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
}

$serverUrl = "http://127.0.0.1:$WhisperServerPort"
$envContent = @"
STT_ENGINE=$Engine
STT_WHISPER_MODEL=$WhisperModel
STT_WHISPER_DEVICE=cpu
STT_WHISPER_COMPUTE=int8
STT_WHISPER_LANGUAGE=fr
STT_WHISPER_THREADS=$WhisperThreads
STT_WHISPER_BEAM_SIZE=$WhisperBeamSize
STT_WHISPER_BEST_OF=$WhisperBestOf
STT_WHISPER_PROMPT=$DefaultPrompt
STT_WHISPER_SERVER_URL=$serverUrl
STT_WHISPER_CPP_BIN=/opt/vocalguard-stt/whisper.cpp/build/bin/whisper-cli
STT_WHISPER_CPP_MODEL=/opt/vocalguard-stt/whisper-models/$ModelName
STT_VOSK_MODEL_PATH=vosk-models/$VoskModelDir
STT_INTERNAL_TOKEN=$token
"@
$envTmp = Join-Path $env:TEMP "vocalguard-stt.env"
Set-Content -Path $envTmp -Value $envContent -NoNewline
scp $envTmp "${Remote}:${RemoteRoot}/.env.stt"
Remove-Item $envTmp
Write-Host "Token STT -> $RemoteRoot/.env.stt"
Write-Host "Sur le serveur API (node14): STT_SERVICE_URL=http://${SttServerName}:8100 et STT_INTERNAL_TOKEN=$token"

if ($Engine -eq "whisper") {
    ssh $Remote "sudo cp /tmp/vocalguard-whisper.service /etc/systemd/system/vocalguard-whisper.service"
    ssh $Remote "sudo systemctl daemon-reload"
    ssh $Remote "sudo systemctl enable vocalguard-whisper"
    ssh $Remote "sudo systemctl restart vocalguard-whisper"
    Write-Host "Attente whisper-server..."
    Start-Sleep -Seconds 12
    ssh $Remote "curl -s -m 3 http://127.0.0.1:$WhisperServerPort/ | head -c 200; echo"
}

ssh $Remote "sudo cp /tmp/vocalguard-stt.service /etc/systemd/system/vocalguard-stt.service"
ssh $Remote "sudo systemctl daemon-reload"
ssh $Remote "sudo systemctl enable vocalguard-stt"
ssh $Remote "sudo systemctl restart vocalguard-stt"

Start-Sleep -Seconds 8
ssh $Remote "curl -s http://127.0.0.1:8100/health"
Write-Host ""
Write-Host "=== STT deploy termine sur $SttServerName ==="
