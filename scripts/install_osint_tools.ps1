# Script PowerShell pour installer les outils OSINT via WSL

Write-Host "Installation des outils OSINT pour VocalGuard via WSL..." -ForegroundColor Green

# Vérifier si WSL est disponible
$wslAvailable = Get-Command wsl -ErrorAction SilentlyContinue

if (-not $wslAvailable) {
    Write-Host "WSL n'est pas installé. Veuillez installer WSL et Kali Linux d'abord." -ForegroundColor Red
    exit 1
}

# Vérifier quelle distribution WSL est disponible
Write-Host "Vérification des distributions WSL disponibles..." -ForegroundColor Yellow
wsl --list

# Demander quelle distribution utiliser
$distro = Read-Host "Quelle distribution WSL utiliser? (par défaut: kali-linux)"

if ([string]::IsNullOrWhiteSpace($distro)) {
    $distro = "kali-linux"
}

Write-Host "Utilisation de la distribution: $distro" -ForegroundColor Green

# Copier le script d'installation dans WSL
Write-Host "Copie du script d'installation dans WSL..." -ForegroundColor Yellow
wsl -d $distro bash -c "mkdir -p ~/vocalguard-scripts"

# Exécuter l'installation dans WSL
Write-Host "Exécution de l'installation dans WSL..." -ForegroundColor Yellow
wsl -d $distro bash -c @"
cd ~
curl -fsSL https://raw.githubusercontent.com/sundowndev/phoneinfoga/master/install.sh | bash || {
    echo 'Installation de PhoneInfoga via Go...'
    export PATH=\$PATH:\$HOME/go/bin
    go install -v github.com/sundowndev/phoneinfoga/v2@latest
}

# Installer truecallerpy
pip3 install --user truecallerpy

# Installer theHarvester
sudo apt-get update
sudo apt-get install -y theharvester

echo 'Installation terminée!'
"@

Write-Host "Installation terminée!" -ForegroundColor Green
Write-Host "Vous pouvez maintenant utiliser les outils OSINT dans VocalGuard" -ForegroundColor Green

