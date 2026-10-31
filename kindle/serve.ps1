<#
.SYNOPSIS
    Avvia il server del pannello scrivendo l'output in cache\server.log.

.DESCRIPTION
    Serve all'avvio automatico (kindle\autostart.ps1): partendo senza finestra, senza un file di log
    gli errori (porta occupata, config non valida) non sarebbero visibili da nessuna parte.
    Si può lanciare anche a mano.
#>
[CmdletBinding()]
param()

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "cache"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "server.log"

Set-Location $repoRoot
# PowerShell 5.1 decodifica l'output dei comandi nativi con la codepage della console, e Python su
# una pipe scrive con la codepage ANSI: senza queste due righe gli accenti nel log si corrompono.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
"--- avvio $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ---" | Add-Content -LiteralPath $log -Encoding utf8

# Niente $ErrorActionPreference = "Stop": con i comandi nativi lo stderr diventerebbe un errore
# terminante e il messaggio (es. "porta occupata") non arriverebbe mai nel log.
& python -m kindle_dashboard serve 2>&1 | ForEach-Object { "$_" } | Add-Content -LiteralPath $log -Encoding utf8
