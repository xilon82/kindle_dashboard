<#
.SYNOPSIS
    Rende il pannello raggiungibile dalla LAN: rete Private + regola firewall per la porta del server.

.DESCRIPTION
    Va eseguito come amministratore (non funziona da cmd.exe: e' un cmdlet PowerShell).
    Non tocca il Kindle e non installa nulla: cambia solo la categoria della rete attiva e aggiunge
    una regola firewall in ingresso per la porta TCP del pannello, letta da config.toml.

.PARAMETER Port
    Porta da aprire. Se omessa viene letta da config.toml.

.PARAMETER NetworkName
    Nome della rete da riclassificare. Se omesso si usa la prima rete attiva.

.PARAMETER AnyProfile
    Non riclassifica la rete: apre la porta su tutti i profili (-Profile Any).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\kindle\allow-lan.ps1 -WhatIf

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\kindle\allow-lan.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [int]$Port = 0,
    [string]$NetworkName = "",
    [switch]$AnyProfile
)

$ErrorActionPreference = "Stop"

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if ($Port -le 0) {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    Push-Location $repoRoot
    try {
        $portFromConfig = @(& python -c "from kindle_dashboard.config import load_config; print(load_config().server.port)")
    } catch {
        $portFromConfig = @()
    } finally {
        Pop-Location
    }
    if ($portFromConfig.Count -ge 1 -and "$($portFromConfig[0])".Trim() -match '^\d+$') {
        $Port = [int]"$($portFromConfig[0])".Trim()
    } else {
        $Port = 8787
        Write-Warning "porta non letta da config.toml, uso il default $Port"
    }
}

$profiles = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue)
if ($profiles.Count -eq 0) {
    throw "nessuna rete attiva trovata: collega il PC alla Wi-Fi (2.4 GHz) e riprova"
}
$target = if ($NetworkName) {
    $profiles | Where-Object { $_.Name -eq $NetworkName } | Select-Object -First 1
} else {
    $profiles | Select-Object -First 1
}
if (-not $target) {
    throw "rete '$NetworkName' non trovata. Reti attive: $(($profiles | ForEach-Object { $_.Name }) -join ', ')"
}

$ruleName = "kindle-dashboard $Port"
$rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
$needProfileChange = (-not $AnyProfile) -and ($target.NetworkCategory.ToString() -eq "Public")
$ruleProfiles = if ($AnyProfile) { "Any" } else { "Private,Domain" }
$needRuleChange = $true
if ($rule) {
    # Il profilo è un flag enum: confronto gli insiemi, non l'ordine delle parole.
    $existingProfiles = (($rule.Profile.ToString() -split ",") | ForEach-Object { $_.Trim() } | Sort-Object) -join ","
    $wantedProfiles = (($ruleProfiles -split ",") | ForEach-Object { $_.Trim() } | Sort-Object) -join ","
    $needRuleChange = $existingProfiles -ne $wantedProfiles
}

Write-Host ("rete:    {0} ({1})" -f $target.Name, $target.NetworkCategory)
Write-Host ("porta:   {0}" -f $Port)
if (-not $rule) {
    Write-Host ("regola:  {0} -> da creare (profili: {1})" -f $ruleName, $ruleProfiles)
} elseif ($needRuleChange) {
    Write-Host ("regola:  {0} -> da aggiornare a profili: {1}" -f $ruleName, $ruleProfiles)
} else {
    Write-Host ("regola:  {0} -> presente (profili: {1})" -f $ruleName, $ruleProfiles)
}
if ($needProfileChange) {
    Write-Host "rete Public: va riclassificata Private, altrimenti la regola non si applica"
}

if (($needProfileChange -or $needRuleChange) -and -not $WhatIfPreference) {
    if (-not (Test-Admin)) {
        Write-Warning "questo script serve amministratore: apri PowerShell con 'Esegui come amministratore' oppure lancia"
        Write-Warning "  powershell -Command `"Start-Process powershell -Verb RunAs -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File','$PSCommandPath'`""
        exit 1
    }
}

if ($needProfileChange) {
    if ($PSCmdlet.ShouldProcess($target.Name, "classificare la rete come Private")) {
        Set-NetConnectionProfile -Name $target.Name -NetworkCategory Private
        Write-Host "rete riclassificata Private"
    }
}

if (-not $rule) {
    if ($PSCmdlet.ShouldProcess($ruleName, "creare regola firewall TCP $Port ($ruleProfiles)")) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile $ruleProfiles | Out-Null
        Write-Host "regola firewall creata"
    }
} elseif ($needRuleChange) {
    if ($PSCmdlet.ShouldProcess($ruleName, "portare i profili della regola a $ruleProfiles")) {
        Set-NetFirewallRule -DisplayName $ruleName -Profile $ruleProfiles
        Write-Host "regola firewall aggiornata"
    }
}

if (-not $WhatIfPreference) {
    $check = Get-NetConnectionProfile -Name $target.Name -ErrorAction SilentlyContinue
    if ($check) {
        Write-Host ("stato rete: {0}" -f $check.NetworkCategory)
    }
    if (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue) {
        Write-Host "stato regola: presente"
    }
    $ip = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -First 1 -ExpandProperty IPAddress
    Write-Host ""
    Write-Host "Ora dal telefono (stesso SSID 2.4 GHz) apri: http://${ip}:$Port/panel.png"
}
