<#
.SYNOPSIS
    Attiva o disattiva l'avvio automatico del server del pannello all'accesso a Windows.

.DESCRIPTION
    Usa la cartella "Esecuzione automatica" dell'utente: nessun privilegio di amministratore, e la
    disattivazione è immediata (basta -Disable, che cancella la scorciatoia).
    L'avvio automatico ha effetto dal prossimo accesso a Windows: per avviare subito si usa
    kindle\serve.ps1 oppure python -m kindle_dashboard serve.

.PARAMETER Enable
    Crea la scorciatoia di avvio.

.PARAMETER Disable
    Rimuove la scorciatoia di avvio.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\kindle\autostart.ps1 -Enable

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\kindle\autostart.ps1 -Disable
#>
[CmdletBinding()]
param(
    [switch]$Enable,
    [switch]$Disable
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serveScript = Join-Path $PSScriptRoot "serve.ps1"
$shortcutPath = Join-Path ([Environment]::GetFolderPath("Startup")) "kindle-dashboard.lnk"
$logPath = Join-Path $repoRoot "cache\server.log"

function Get-Port {
    Push-Location $repoRoot
    try {
        $value = @(& python -c "from kindle_dashboard.config import load_config; print(load_config().server.port)")
    } finally {
        Pop-Location
    }
    if ($value.Count -ge 1 -and "$($value[0])".Trim() -match '^\d+$') {
        return [int]"$($value[0])".Trim()
    }
    return 8787
}

function Show-Status {
    if (Test-Path -LiteralPath $shortcutPath) {
        Write-Host "avvio automatico: ATTIVO"
        Write-Host "scorciatoia:      $shortcutPath"
        $port = Get-Port
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener) {
            Write-Host "server:           in ascolto su porta $port (pid $($listener.OwningProcess))"
        } else {
            Write-Host "server:           non in ascolto (partirà al prossimo accesso)"
        }
        Write-Host "log:              $logPath"
    } else {
        Write-Host "avvio automatico: DISATTIVATO"
    }
}

if ($Enable) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = (Get-Command powershell.exe).Source
    $shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$serveScript`""
    $shortcut.WorkingDirectory = $repoRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = "kindle-dashboard: server del pannello"
    $shortcut.Save()
    Write-Host "avvio automatico attivato: $shortcutPath"
    Write-Host "log del server:            $logPath"
    Show-Status
    return
}

if ($Disable) {
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
        Write-Host "avvio automatico disattivato (scorciatoia rimossa)"
    } else {
        Write-Host "avvio automatico già disattivato"
    }
    return
}

Show-Status
