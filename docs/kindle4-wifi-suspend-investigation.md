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

## Esperimenti (in ordine)

### E6 — Wi-Fi on/off (verificato il 2026-11-15)

Comandi verificati con `inventory`:
```sh
lipc-get-prop com.lab126.wifid cmState          # CONNECTED
lipc-set-prop com.lab126.cmd wirelessEnable 0   # spegne -> cmState = NA
lipc-set-prop com.lab126.cmd wirelessEnable 1   # riaccende -> CONNECTED in 6 s
```

- La sessione SSH via Wi-Fi muore alla disconnessione: il canale di recupero è USB + `inventory`.
- Ciclo off/on misurato: **31 s**. È il motivo per cui il ciclo autonomo non spegne la radio a ogni
  giro: 31 s su 90 di cadenza sarebbero un terzo del tempo, e lo standby la spegne già.
- Il consumo reale della radio non è misurato (matrice W4): `cmState = NA` prova lo stato, non i mA.

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

### E8 — Ciclo autonomo (3 giri verificati)

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

#### E8.2 — Vent'anni giri: un run completo e uno interrotto (2026-11-15)

Run completo (21:34:44–22:12:24):

- 20 giri, un risveglio ogni ~91 s (90 s di sospensione + aggiornamento), uptime 30995 → 31430
  continuo, nessun `download fallito`, `raggiunto il limite di 20 giri` e `cycle: terminato`.

Tentativo interrotto (22:21:28–22:46, giro 14):

```
22:21:28 cycle: avvio (giri=20, 0=infinito)
22:46:08 cycle: aggiornato (giro 14)
22:46:23 cycle: sospensione 30 s   (fallback: /next falliva)
22:46:23 suspend_rtc: sospensione...
23:37:04 loop: non in esecuzione   (dopo il riavvio: pid orfano)
```

Fatti:

- il ciclo si è fermato al **giro 14 di 20**, e non per lo stop: il device si è **riavviato** ~30 s
  dopo la sospensione. Prova: `rtc1 since_epoch=3057` all'inventario (boot ~51 min prima),
  `dmesg` con `wdog: Abnormal reset detected but saved buffer invalid`, `powerd_status` con
  `Battery Level: 95%` / `Charging: No`.
- due `download fallito` (22:44 e 22:46 del device) durante i giri 12-14: il ciclo ha tenuto l'ultimo
  PNG e ha continuato, come previsto (C3).
- la sospensione da **30 s** era il fallback usato perché `/next` non rispondeva; il Kindle era
  attaccato alla **USB del PC** (è così che il log veniva letto).
- ipotesi da verificare: sospendere con la USB del PC collegata (gadget `arcotg_udc` + PMIC, nel
  `dmesg` compaiono `chargerUsbHigh` e `charger times out`) può finire in reset.

Prove brevi (23:46 e 23:50), con il Kindle staccato dalla USB:

- una sospensione da 90 s ciascuna, ripresa corretta: `dmesg` con
  `PM: resume of devices complete after 1248 msecs` e
  `Battery: Resume - TimeSuspended(secs)=89, RSOC=97, capacity=97%`; uptime 3625/3728 continuo;
- fermate a mano dopo un giro, con `loop: fermato (pid …)`: lo stop uccide il processo prima della
  sospensione successiva.

Conclusione: il ciclo da 20 giri **ha funzionato per intero** quando il server rispondeva; il
fallimento era isolato al tentativo con la USB del PC collegata. Manca la batteria prima/dopo di un run
completo: va rifatto con caricatore e USB staccata, leggendo il log solo alla fine.

#### E8.3 — Venti giri con l'indirizzo sbagliato (2026-11-24/25)

Quattro run da 20 giri sono arrivati in fondo **senza aggiornare il pannello**: `HOST=` sul device era
`192.168.1.14`, cioè il **PC di sviluppo**, dove non ascolta nessuno; il pannello gira sul server
`192.168.1.187`, che invece stava rispondendo. Il log di ognuno è una ripetizione di:

```
2026-11-25T09:11:00 panel: download fallito (tengo l'ultimo panel.png)
2026-11-25T09:11:00 cycle: aggiornato (giro 15)
2026-11-25T09:11:15 cycle: sospensione 30 s        <- /next muto: ripiego
2026-11-25T09:11:15 suspend_rtc: base=815067 wakealarm=815097 (tra 30 s), riletto=vuoto
2026-11-25T09:11:46 suspend_rtc: risvegliato, uptime=656365.41 …
```

Fatti:

- **20 giri raggiunti** (`cycle: raggiunto il limite di 20 giri`) con uptime continuo: la sospensione
  RTC ha retto ~20 risvegli di fila anche in queste condizioni;
- **zero download riusciti**: il pannello a schermo era quello del giorno prima;
- cadenza di **30 s** invece di 90, perché il ripiego di `/next` era `LOOP_SECONDS`. Con un indirizzo
  che non risponde il device si svegliava ogni 30 s per ore: proprio il consumo che il ciclo doveva
  evitare.

Correzioni (in `dashboard.sh.template`, non solo nei documenti): il ciclo conta i download falliti e
dopo tre passa ad attese crescenti (300 → 600 → 1200 → 1800 s); il ripiego di `/next` è
`[panel] refresh_seconds` (90 s), renderizzato da `deploy.ps1` come `REFRESH_SECONDS`; il prefisso di
log di `update_panel` è passato da `loop:` a `panel:` (le righe storiche citate sopra restano quelle
del log originale). `deploy.ps1` ora prova `http://<host>:<porta>/health` prima di scrivere, e
`[server] device_host` fissa l'indirizzo invece di lasciarlo al DHCP.

## Vincoli di sicurezza

- **Nessun comando** che spegne Wi-Fi, sospende o riavvia senza tua approvazione esplicita.
- Canale di recupero sempre USB + `inventory` (SSH muore con il Wi-Fi).
- Log su `G:\dashboard\dashboard.log` leggibile con framework avviato.
- `config.xml` dichiara il menu KUAL; le voci (`Wi-Fi off`, `Wi-Fi on`, `Test Wi-Fi cycle`, `Suspend RTC (60s)`, `Resume check`, `Test RTC cycle (60s)`, `RTC info`, `RTC test arm`, `Avvia ciclo RTC`, `Test ciclo RTC (3 giri)`, `Test ciclo RTC (20 giri)`) si aggiungono con `menu.json`.
- Nessun binario installato; solo script `sh` compatibili BusyBox 1.7.2.

## Deliverable in questa branch

- `docs/kindle4-wifi-suspend-investigation.md` (questo documento)
- `docs/kindle4-test-matrix.md` (matrice unica: qui sono confluite le righe Wi-Fi/RTC/ciclo)
- Aggiornamenti a `dashboard.sh.template`: `wifi_off`, `wifi_on`, `wifi_cycle`, `suspend_rtc`, `resume_check`, `rtc_info`, `rtc_arm`, `rtc_cycle`, `cycle` (lock pid, backoff, ripiego di cadenza)
- Aggiornamenti a `menu.json`: voci per pilotare i test da KUAL, con il ciclo nativo in testa
- Aggiornamenti a `README.md`, `AGENTS.md`, `.clinerules` per le nuove regole

---

**Stato attuale**: E6, E7 ed E8 sono chiusi. Il ciclo nativo è la visualizzazione predefinita
(`Avvia pannello (ciclo RTC)`); il browser resta il ripiego. Restano due cose, e sono misure, non
decisioni: la **batteria prima/dopo** di un run da 20 giri con i download che riescono (matrice C2/C9)
e il **backoff** con il server spento provato sul device (C10).
