# Lance une GUI et la tue si la console recoit Ctrl+C ou se ferme.
param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath
)

$ErrorActionPreference = "Stop"
$proc = $null
try {
    if (-not (Test-Path -LiteralPath $ExePath)) {
        Write-Error "Introuvable : $ExePath"
        exit 1
    }
    $proc = Start-Process -FilePath $ExePath -PassThru
    while ($null -ne $proc -and -not $proc.HasExited) {
        Start-Sleep -Milliseconds 250
    }
    if ($null -ne $proc) {
        exit [int]$proc.ExitCode
    }
    exit 0
}
finally {
    if ($null -ne $proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
