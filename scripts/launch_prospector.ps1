# Lance VocalGuard Prospector (conda vocalguard)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$req = Join-Path $Root "desktop\requirements-studio.txt"
conda run -n vocalguard python -m pip install -q -r $req
conda run -n vocalguard python -m desktop.prospector.app
