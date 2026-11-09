# Lance VocalGuard Prospector (conda vocalguard)
# Option : $HotReload = $true pour surveiller les .py et relancer l'appli (dev)
param(
    [switch]$HotReload
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$req = Join-Path $Root "desktop\requirements-studio.txt"
conda run -n vocalguard python -m pip install -q -r $req
if ($HotReload) {
    $env:VG_PROSPECTOR_HOT_RELOAD = "1"
    try {
        conda run -n vocalguard python -m desktop.prospector
    } finally {
        Remove-Item Env:VG_PROSPECTOR_HOT_RELOAD -ErrorAction SilentlyContinue
    }
} else {
    conda run -n vocalguard python -m desktop.prospector
}
