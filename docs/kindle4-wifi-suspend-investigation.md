# Kindle 4 — Wi-Fi, RTC, sospensione e ripresa

Branch: `investigation/kindle4-wifi-suspend`.

Obiettivo: completare il ciclo nativo aggiungendo la gestione energetica (Wi-Fi on/off, sospensione RTC, ripresa), senza compromettere il ciclo di disegno già verificato.

Questa indagine parte dal ciclo già verificato: download → verifica PNG → disegno → warm-up → stop immediato, server nel container, `h=800` per 600x800.

## Situazione di partenza (2026-11-14)

| Componente | Stato | Nota |
|---|---|---|
| `eips` | **Verificato** | disegna 600x800 `L` 8 bit con framework avviato |
| Ciclo | **Verificato** | download → verifica → disegno; warm-up 3×5 s; stop immediato |
| Server | **Container** | `docker compose up -d`, `0.0.0.0:8787`, healthcheck OK |
| PNG nativo | **Verificato** | `?h=800` → 600x800 `L` 8 bit; warm-up 3×5 s |
| Wi-Fi | **CONNECTED** (da `inventory`) | `cmState` letto; rete PC è `Public` → serve regola firewall |
| RTC | **Presente** | `rtc0` = `mxc_rtc`, `rtc1` = `pmic_rtc`; `/sys/power/state` = `standby mem` |
| BusyBox | **1.7.2** | no `command -v`, no `grep -E`, no `wget -T` (già gestiti) |
| Shell | **ash** | `trap 0` non scatta su `kill` → pid rimosso a mano |
| Framework | **Non toccato** | non si ferma mai; warm-up mitiga i ridisegni |

## Prossimi esperimenti (in ordine)

### E6 — Wi-Fi on/off (richiede approvazione)

Comandi candidati da verificare con `inventory`:
```sh
lipc-get-prop com.lab126.wifid cmState          # CONNECTED
lipc-set-prop com.lab126.cmd wirelessEnable 0   # spegne
# timeout per tornare a CONNECTED
lipc-set-prop com.lab126.cmd wirelessEnable 1   # riaccende
```

- La sessione SSH via Wi-Fi muore alla disconnessione: serve canale di recupero (USB + `inventory`).
- Misurare 10 cicli: accensione → `CONNECTED` → download → disegno → spegnimento.

### E7 — RTC, sospensione, ripresa (fatto il 2026-11-15)

Il risveglio RTC **funziona**, ma non per la strada documentata altrove:

| Tentativo | Esito |
|---|---|
| `lipc-set-prop com.lab126.powerd rtcWakeup N` (+ 8 nomi alternativi, con e senza `-i`) | **tutti RIFIUTATI**: su questo firmware `powerd` non ha proprietà RTC |
| `powerd_test -h` | **non è help**: simula «power button held» e spegne lo schermo |
| `powerd_test s` | stampa l'usage; la sintassi giusta è **`powerd_test -s`** (stato: `Active`, `defer_suspend`, batteria) |
| `/sys/class/rtc/rtc0/wakealarm` | **non esiste** (`mxc_rtc`) |
| `/sys/class/rtc/rtc1/wakealarm` | esiste (`pmic_rtc`) e **accetta scrittura** |
| rilettura di `wakealarm` | **vuota** (`pmic_rtc` non supporta la lettura dell'allarme) |

La strada giusta: `rtc1` conta dall'accensione (`since_epoch=7655`), quindi si scrive
**`since_epoch + N`**, non un epoch Unix, e si entra in standby con `echo mem > /sys/power/state`.
La rilettura vuota non significa «non armato»: la sospensione lo dimostra.

Prova reale (2026-11-15):

```
13:55:25 suspend_rtc: base=7859 wakealarm=7919 (tra 60 s), riletto=vuoto
13:55:25 suspend_rtc: rilettura non supportata dal driver, provo comunque la sospensione
13:55:25 suspend_rtc: sospensione...
13:56:26 suspend_rtc: risvegliato, uptime=7854.21 0.00 59 59
```

Sospensione di **61 secondi** e **uptime continuo**: è una ripresa, non un riavvio. Entrambi gli RTC
sono `enabled` per il wake a livello di device (`rtc_wakeup`). `powerd` entra da solo in standby dopo
~600 s di inattività (`Remaining time in this state`), quindi un ciclo reale deve usare questo
meccanismo, non un timeout proprio.

### E8 — 20 cicli completi + batteria

Criterio di completamento: 20 cicli consecutivi con cadenza reale (`refresh_seconds`: 90 s giorno, 3600 s notte), server offline gestito, stop manuale, rollback banale, misura di autonomia su periodo significativo.

## Vincoli di sicurezza

- **Nessun comando** che spegne Wi-Fi, sospende o riavvia senza tua approvazione esplicita.
- Canale di recupero sempre USB + `inventory` (SSH muore con il Wi-Fi).
- Log su `G:\dashboard\dashboard.log` leggibile con framework avviato.
- `config.xml` dichiara il menu KUAL; le nuove voci (`Wi-Fi off`, `Suspend`, `Resume`, `Cycle 20x`) si aggiungono con `menu.json`.
- Nessun binario installato; solo script `sh` compatibili BusyBox 1.7.2.

## Deliverable in questa branch

- `docs/kindle4-wifi-suspend-investigation.md` (questo documento)
- `docs/kindle4-wifi-suspend-test-matrix.md` (matrice analoga a quella del rendering)
- Aggiornamenti a `dashboard.sh.template`: `wifi_off`, `wifi_on`, `suspend`, `resume`, `cycle` (con lock pid)
- Aggiornamenti a `menu.json`: voci per pilotare i test da KUAL
- Aggiornamenti a `README.md`, `AGENTS.md`, `.clinerules` per le nuove regole

---

**Stato attuale**: E4 chiuso (ciclo con download verificato). Prossimo: E6 con la tua approvazione.