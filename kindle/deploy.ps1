<#
.SYNOPSIS
    Copia l'estensione KUAL "Dashboard" sul Kindle collegato via USB.

.DESCRIPTION
    Rileva l'unita' del Kindle (unita' con le cartelle documents\ e system\) e genera dashboard.sh
    leggendo config.toml tramite il pacchetto Python (una sola fonte di verita'): porta, cadenza di
    aggiornamento e indirizzo con cui il device raggiunge il server.

    Prima di scrivere prova http://<host>:<port>/health. Un deploy "riuscito" verso un server spento
    produce un device che scarica nulla a ogni giro e mostra per sempre l'ultima immagine buona:
    e' successo per davvero (venti giri con venti `download fallito`), quindi la prova si fa qui.

.PARAMETER KindleDrive
    Unita' del Kindle, es. "G:\". Se omessa viene cercata automaticamente.

.PARAMETER HostAddress
    IP del server raggiungibile dal Kindle. Se omesso si usa `[server] device_host` di config.toml e,
    se anche quello e' vuoto, l'IPv4 della scheda che regge la rotta di default: con Docker/WSL
    attivi il primo IPv4 dell'elenco è un adattatore virtuale che il Kindle non può raggiungere.

.PARAMETER OpenFirewall
    Crea la regola firewall in ingresso per la porta del pannello (richiede PowerShell admin).

.PARAMETER AnyProfile
    Con -OpenFirewall apre la porta su tutti i profili di rete. Da usare solo se non vuoi
    riclassificare la rete domestica come Private.

.PARAMETER DryRun
    Mostra cosa verrebbe scritto senza toccare il Kindle.

.PARAMETER TestImages
    Copia anche le varianti di formato (cache\testimages) in <kindle>:\dashboard\test, usate dalla
    voce di menu "Test immagini (eips)" per capire quale formato digerisce eips. Se la cartella non
    esiste, generarla prima con: python kindle\make_test_images.py
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

# Il pannello gira nel container: qui serve solo leggere config.toml. Si usa il Python del venv se
# c'è (così il deploy funziona senza attivare la shell), altrimenti `python` nel PATH.
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

Push-Location $repoRoot
try {
    # Una sola chiamata: tre righe, una per valore, cosi' il parsing qui sotto non dipende dal
    # formato di stampa di Python (e un valore vuoto resta una riga vuota, non una riga in meno).
    $settings = @(& $pythonExe -c "from kindle_dashboard.config import load_config; c = load_config(); print(c.server.port); print(c.server.device_host); print(c.panel.refresh_seconds)")
    $settingsExit = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($settingsExit -ne 0 -or $settings.Count -lt 3) {
    throw ('lettura di config.toml fallita con ' + $pythonExe + ': controlla il file e che il venv abbia le dipendenze (python -m pip install -e ".[dev]").')
}
$port = [int]$settings[0]
$pinnedHost = "$($settings[1])".Trim()
# Cadenza diurna: il device la usa quando `/next` non risponde, cosi' il ripiego e' 90 s e non 30.
$refreshSeconds = [int]$settings[2]

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

$hostSource = "-HostAddress"
if (-not $HostAddress -and $pinnedHost) {
    # L'indirizzo fissato in config.toml vince sul rilevamento: e' quello che il router riserva al
    # server e non cambia quando il PC passa a un'altra rete o il DHCP assegna un IP diverso. Il
    # valore finito nel file generato la volta prima non e' una fonte di verita': si rilegge qui.
    $HostAddress = $pinnedHost
    $hostSource = "[server] device_host in config.toml"
}
if (-not $HostAddress) {
    # Con Docker/WSL attivi il primo IPv4 dell'elenco e' un adattatore virtuale (192.168.208.x) senza
    # gateway: il Kindle non lo raggiunge. La scheda giusta e' quella della rotta di default, cioe' la
    # rete con cui il PC esce davvero.
    $defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
        Sort-Object RouteMetric, InterfaceMetric |
        Select-Object -First 1
    if ($defaultRoute) {
        $HostAddress = Get-NetIPAddress -InterfaceIndex $defaultRoute.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike "169.254.*" } |
            Select-Object -First 1 -ExpandProperty IPAddress
        $hostSource = "scheda della rotta di default"
    }
}
if (-not $HostAddress) {
    $HostAddress = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -First 1 -ExpandProperty IPAddress
    $hostSource = "primo IPv4 disponibile"
}
if (-not $HostAddress) {
    throw "nessun indirizzo IPv4 trovato: passa -HostAddress con l'IP del server"
}

# Prova che vale piu' di ogni messaggio: con /health muto il Kindle non scarica nulla e il ciclo
# resta sull'ultima immagine buona dicendo solo `download fallito`. Si prova anche in DryRun, perche'
# la domanda vera del deploy e' "il device raggiungera' il server?".
$healthUrl = "http://${HostAddress}:$port/health"
try {
    $health = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
    $serverUp = ($health.StatusCode -eq 200)
} catch {
    $serverUp = $false
}

$template = [System.IO.File]::ReadAllText(
    (Join-Path $sourceDir "dashboard.sh.template"),
    [System.Text.Encoding]::UTF8
)
# Un segnaposto sparito dal template produrrebbe uno script che il device esegue lo stesso, con un
# valore sbagliato al posto giusto: meglio fermarsi qui.
foreach ($placeholder in @("__HOST__", "__PORT__", "__REFRESH__")) {
    if ($template -notmatch [regex]::Escape($placeholder)) {
        throw "dashboard.sh.template non contiene ${placeholder}: il file generato sarebbe sbagliato"
    }
}
$rendered = $template.Replace("__HOST__", $HostAddress).Replace("__PORT__", "$port").Replace("__REFRESH__", "$refreshSeconds")
$rendered = $rendered -replace "`r`n", "`n"
if (-not $rendered.EndsWith("`n")) { $rendered += "`n" }

$target = Join-Path $KindleDrive "extensions\dashboard"
$scriptPath = Join-Path $target "dashboard.sh"
Write-Host "Kindle:  $KindleDrive"
Write-Host "Server:  http://${HostAddress}:$port/panel.png (indirizzo da $hostSource)"
if ($serverUp) {
    Write-Host "health:  $healthUrl risponde"
} else {
    Write-Warning "health: $healthUrl non risponde - il Kindle scaricherebbe nulla a ogni giro."
    Write-Warning "avvia il server (docker compose up -d oppure .\kindle\serve.ps1) e rilancia il deploy."
}
Write-Host "Destinazione: $scriptPath"

# Windows classifica molte reti domestiche come Public: una regola limitata ai profili Private non
# verrebbe applicata. Se però esiste già una regola per questa porta su tutti i profili (quella di
# allow-lan.ps1), l'avviso sarebbe falso: si controlla prima di allarmare. Anche il DryRun lo stampa,
# perché è esattamente la domanda "il Kindle raggiungerà il server?".
$networkProfile = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -First 1
if ($networkProfile -and $networkProfile.NetworkCategory.ToString() -eq "Public") {
    $existingRule = Get-NetFirewallRule -DisplayName "kindle-dashboard $port" -ErrorAction SilentlyContinue
    if ($existingRule -and ("$($existingRule.Profile)" -match "Any")) {
        Write-Host "rete Public: la regola firewall per la porta $port copre tutti i profili, nessuna azione richiesta."
    } else {
        Write-Warning "la rete '$($networkProfile.Name)' e' classificata Public: la regola Private non verra' applicata."
        Write-Warning "consigliato (PowerShell admin): powershell -ExecutionPolicy Bypass -File .\kindle\allow-lan.ps1"
        Write-Warning "in alternativa: .\kindle\deploy.ps1 -OpenFirewall -AnyProfile"
    }
}

if ($DryRun) {
    Write-Host "`n--- DryRun: nessuna scrittura. Prime righe di dashboard.sh ---"
    Write-Host (($rendered -split "`n")[0..7] -join "`n")
    # HOST, PORT e REFRESH_SECONDS non sono nelle prime righe (sono commenti): stamparli è l'unica
    # verifica che il Kindle riceva l'indirizzo giusto invece dell'adattatore virtuale di Docker/WSL.
    Write-Host "`nValori renderizzati:"
    Write-Host ((($rendered -split "`n") | Where-Object { $_ -match "^(HOST|PORT|REFRESH_SECONDS)=" }) -join "`n")
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
        Write-Warning "cartella $testSource assente: generarla con python kindle\make_test_images.py"
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

Write-Host ""
Write-Host "Sul server: docker compose up -d  (oppure .\kindle\serve.ps1, senza Docker)"
Write-Host "Sul Kindle: KUAL > Dashboard > Avvia pannello (ciclo RTC); browser di ripiego su http://$HostAddress`:$port/panel.html"
Write-Host "Log del device: /mnt/us/dashboard/dashboard.log"
