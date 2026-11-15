# Kindle 4 — matrice Wi-Fi, RTC, sospensione e ripresa

Compagna di `docs/kindle4-wifi-suspend-investigation.md`. Ogni riga è una fase **separata**: un fallimento non
contagia le altre, e «non testato» non significa «fallito».

Legenda: **Verificato** = c'è una prova ripetibile; **Fallito** = c'è una prova di errore; **Non testato** = nessuno l'ha ancora eseguito.

Ultimo aggiornamento: **2026-11-15**, dopo il primo `cycle 20`: si è interrotto al giro 14 per un
**riavvio del device** durante la sospensione, con il Kindle attaccato alla USB del PC. Il ripiego
batteria è implementato e il valore letto è corretto, ma non è stato forzato: righe C2, C4 e C9.

## Wi-Fi

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| W1 | `cmState` letto da `inventory` | **Verificato** | `wifi_state exit=0: CONNECTED` | lettura, non prova di spegnimento |
| W2 | Spegnimento radio (`wirelessEnable 0`) | **Verificato** | `wifi_off: richiesto`, poi `cmState = NA` | — |
| W3 | Riaccensione e ritorno a `CONNECTED` | **Verificato** | `wifi_on: CONNECTED (dopo 6 s)`; ciclo completo **31 s** | — |
| W4 | Radio davvero spenta (non solo IP) | **Parziale** | `cmState` passa a `NA` | non misura il consumo della radio |

## RTC, sospensione e ripresa

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| S1 | Wake RTC programmato sul device | **Verificato** | `powerd` **non** ha proprietà RTC (9 nomi rifiutati); si usa `rtc1/wakealarm` con `since_epoch + N` | la rilettura è vuota (driver non supporta `cat`) |
| S2 | Ingresso in sospensione vera | **Verificato** | `echo mem > /sys/power/state`, standby confermato | — |
| S3 | Risveglio all'orario programmato | **Verificato** | sospeso 13:55:25, risvegliato 13:56:26 (**61 s**) | — |
| S4 | Il processo riprende dopo il wake | **Verificato** | `suspend_rtc: risvegliato, uptime=7854.21` (uptime continuo, non reboot) | — |
| S5 | Wi-Fi dopo il wake | **Verificato** | il download riesce 5 s dopo il risveglio, senza riaccendere la radio | — |

## Ciclo completo e robustezza

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| C1 | Ciclo completo (wake → PNG → display → sleep) | **Verificato** | 3 giri: sospensione 90 s, risveglio 92/91/91 s, uptime continuo, download riuscito | manca la misura batteria |
| C8 | Ciclo autonomo con sospensione RTC | **Verificato (3 giri)** | `cycle 3`: `/next` → sospensione → aggiornamento, stop automatico al limite | i 20 cicli e l'autonomia restano da misurare |
| C2 | 20 cicli senza interventi | **Fallito (1 tentativo)** | `cycle 20` interrotto al **giro 14**: il device si è riavviato ~30 s dopo una sospensione da 30 s (fallback perché `/next` falliva). Dopo il boot `rtc1 since_epoch=3057`, `dmesg` con `wdog: Abnormal reset detected but saved buffer invalid`; **Ferma ciclo** ha poi trovato `loop: non in esecuzione` (pid orfano rimosso) | il Kindle era attaccato alla **USB del PC**: ripetere con caricatore e USB staccata |
| C9 | Lettura batteria per la misura di autonomia | **Parziale** | `inventory`: `batteria exit=0: 95`, coerente con `powerd_status ... Battery Level: 95%`; `comandi: … sed=/bin/sed` | non si sa se il 95 viene da `capacity` o dal ripiego (`powerd_test -s`): il ripiego è provato solo in container |
| C3 | Server offline / IP cambiato nel ciclo | **Parziale** | nel `cycle 20` due `download fallito` (22:44 e 22:46 del device): il ciclo ha tenuto l'ultimo PNG e ha continuato (`cycle: aggiornato`), poi `/next` è caduto sul fallback da 30 s | non è stato forzato fermando il server; è capitato per una caduta reale |
| C4 | Errori gestiti senza lasciare il device in stato strano | **Fallito in un caso reale** | la sospensione si è chiusa con un **riavvio** (`wdog: Abnormal reset detected`), non con una ripresa; `rtc1 since_epoch` è ripartito da zero | causa da isolare: sospensione con USB del PC collegata (gadget/charger, `arcotg_udc`/`pmic` nel `dmesg`)? sleep da 30 s? Il recupero resta USB + log |
| C5 | Rollback | **Verificato per costruzione** | basta non avere una voce di avvio automatico; il ciclo si ferma con **Ferma ciclo** | il file `STOP` resta finché non si riavvia il ciclo |

## Come aggiornare questa matrice

Dopo ogni esperimento: sostituire lo stato, aggiungere **la riga di log o il comando** che lo prova
e togliere la limitazione corrispondente. La prova vera è il log con l'output **più** l'osservazione
dello schermo.