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

### E8 — Ciclo autonomo (in corso)

Il ciclo completo non usa una cadenza fissa: chiede al server `/next` (secondi al prossimo
aggiornamento, calcolati da `schedule.py`) e usa quel valore come durata della sospensione RTC.
Sequenza a ogni giro: `update_panel` → `draw_panel` → `/next` → `suspend_rtc` → risveglio.

Lo stop è quello di `loop` (`STOP` + `kill`): il processo muore prima di sospendersi, quindi non
resta un device addormentato con un aggiornamento in coda. Se `suspend_rtc` fallisce, il ciclo
attende con `sleep` invece di girare a vuoto.

Criterio di completamento: **20 cicli** con cadenza reale (90 s giorno, 3600 s notte), server
offline gestito (l'ultimo PNG resta), stop manuale, misura di autonomia su un periodo significativo.

#### E8.1 — Tre giri reali (2026-11-15)

```
14:17:32 cycle: avvio (giri=3, 0=infinito)
14:17:36 loop: scaricato panel.png (33185 byte)
14:17:36/41/46 cycle: disegnato (warm-up)
14:18:06 cycle: sospensione 90 s
14:19:38 suspend_rtc: risvegliato, uptime=9157.24
14:19:43 loop: scaricato panel.png (33630 byte)
14:19:44 cycle: aggiornato (giro 1)
14:21:30 suspend_rtc: risvegliato, uptime=9180.51   (giro 2)
14:23:22 suspend_rtc: risvegliato, uptime=9204.13   (giro 3)
14:23:28 cycle: raggiunto il limite di 3 giri
```

Fatti verificati:

- tre sospensioni da 90 s e tre risvegli dopo **92/91/91 s**;
- **uptime continuo** (9157 → 9180 → 9204): sono riprese, non riavvii;
- **il Wi-Fi resta associato dopo il risveglio**: il download riesce 5 s dopo, senza
  riconnessione. Non serve `wifi_off` a ogni giro: il standby spegne già la radio;
- il ciclo si ferma da solo al limite di giri, senza corsa contro la sospensione.

Resta da misurare l'autonomia reale (20 cicli) e da decidere se avviare il ciclo all'accensione.

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