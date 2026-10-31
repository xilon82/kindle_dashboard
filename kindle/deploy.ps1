<#
.SYNOPSIS
    Copia l'estensione KUAL "Dashboard" sul Kindle collegato via USB.

.DESCRIPTION
    Rileva l'unita' del Kindle (unita' con le cartelle documents\ e system\), legge porta e
    cadenza di aggiornamento da config.toml tramite il pacchetto Python (una sola fonte di
    verita'), genera dashboard.sh con IP e porta del PC.

.PARAMETER KindleDrive
    Unita' del Kindle, es. "G:\". Se omessa viene cercata automaticamente.

.PARAMETER HostAddress
    IP del PC raggiungibile dal Kindle. Se omesso viene preso il primo IPv4 non loopback.

.PARAMETER OpenFirewall
    Crea la regola firewall in ingresso per la porta del pannello (richiede PowerShell admin).

.PARAMETER AnyProfile
    Con -OpenFirewall apre la porta su tutti i profili di rete. Da usare solo se non vuoi
    riclassificare la rete domestica come Private.

.PARAMETER DryRun
    Mostra cosa verrebbe scritto senza toccare il Kindle.

.PARAMETER TestImages
    Copia anche le varianti di formato (cache\testimages) in <kindle>:\dashboard\test, usate dalla
    voce di menu "Test immagini" per capire quale formato digerisce eips.
#>
[CmdletBinding()]
param(
    [string]$KindleDrive = "",
    [string]$HostAddress = "",
    [switch]$OpenFirewall,
    [switch]$AnyProfile,
    [switch]$TestImages,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$sourceDir = Join-Path $PSScriptRoot "extensions\dashboard"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    $settings = @(& python -c "from kindle_dashboard.config import load_config; c = load_config(); print(c.server.port)")
} finally {
    Pop-Location
}
if ($settings.Count -lt 1) {
    throw "lettura di config.toml fallita (output: $settings). Esegui prima: python -m kindle_dashboard render"
}
$port = [int]$settings[0]

if (-not $KindleDrive) {
    $drive = Get-PSDrive -PSProvider FileSystem | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.Root "documents")) -and
        (Test-Path -LiteralPath (Join-Path $_.Root "system"))
    } | Select-Object -First 1
    if (-not $drive) {
        throw "Kindle non trovato: collegalo via USB (deve comparire come unita' con documents\ e system\)"
    }
    $KindleDrive = $drive.Root
}

if (-not $HostAddress) {
    $HostAddress = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -First 1 -ExpandProperty IPAddress
}
if (-not $HostAddress) {
    throw "nessun indirizzo IPv4 trovato: passa -HostAddress con l'IP del PC"
}

$template = [System.IO.File]::ReadAllText(
    (Join-Path $sourceDir "dashboard.sh.template"),
    [System.Text.Encoding]::UTF8
)
$rendered = $template.Replace("__HOST__", $HostAddress).Replace("__PORT__", "$port")
$rendered = $rendered -replace "`r`n", "`n"
if (-not $rendered.EndsWith("`n")) { $rendered += "`n" }

$target = Join-Path $KindleDrive "extensions\dashboard"
$scriptPath = Join-Path $target "dashboard.sh"
Write-Host "Kindle:  $KindleDrive"
Write-Host "PC:      http://${HostAddress}:$port/panel.png"
Write-Host "Destinazione: $scriptPath"

if ($DryRun) {
    Write-Host "`n--- DryRun: nessuna scrittura. Prime righe di dashboard.sh ---"
    Write-Host (($rendered -split "`n")[0..7] -join "`n")
    return
}

New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceDir "config.xml") -Destination $target -Force
Copy-Item -LiteralPath (Join-Path $sourceDir "menu.json") -Destination $target -Force
[System.IO.File]::WriteAllText($scriptPath, $rendered, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Estensione copiata in $target"

if ($TestImages) {
    $testSource = Join-Path $repoRoot "cache\testimages"
    if (Test-Path -LiteralPath $testSource) {
        $testTarget = Join-Path $KindleDrive "dashboard\test"
        New-Item -ItemType Directory -Force -Path $testTarget | Out-Null
        Copy-Item -Path (Join-Path $testSource "*") -Destination $testTarget -Force
        Write-Host "varianti di test copiate in $testTarget"
    } else {
        Write-Warning "cartella $testSource assente: rigenera preview.png e le varianti prima di usare -TestImages"
    }
}

if ($OpenFirewall) {
    $ruleName = "kindle-dashboard $port"
    $profiles = if ($AnyProfile) { "Any" } else { "Private,Domain" }
    if (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue) {
        Write-Host "regola firewall gia' presente: $ruleName"
    } else {
        try {
            New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile $profiles | Out-Null
            Write-Host "regola firewall creata: $ruleName (profili: $profiles)"
        } catch {
            Write-Warning "firewall non modificato (serve PowerShell come amministratore): $($_.Exception.Message)"
        }
    }
}

# Windows classifica molte reti domestiche come Public: in quel caso una regola Private non basta.
$networkProfile = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -First 1
if ($networkProfile -and $networkProfile.NetworkCategory.ToString() -eq "Public") {
    Write-Warning "la rete '$($networkProfile.Name)' e' classificata Public: la regola Private non verra' applicata."
    Write-Warning "consigliato (PowerShell admin): powershell -ExecutionPolicy Bypass -File .\kindle\allow-lan.ps1"
    Write-Warning "in alternativa: .\kindle\deploy.ps1 -OpenFirewall -AnyProfile"
}

Write-Host ""
Write-Host "Sul PC:  python -m kindle_dashboard serve"
Write-Host "Sul Kindle: KUAL > Dashboard > Avvia pannello"
Write-Host "Log del device: /mnt/us/dashboard/dashboard.log"
