# Kindle 4 — matrice Wi-Fi, RTC, sospensione e ripresa

Compagna di `docs/kindle4-wifi-suspend-investigation.md`. Ogni riga è una fase **separata**: un fallimento non
contagia le altre, e «non testato» non significa «fallito».

Legenda: **Verificato** = c'è una prova ripetibile; **Fallito** = c'è una prova di errore; **Non testato** = nessuno l'ha ancora eseguito.

Ultimo aggiornamento: **2026-11-15**, dopo Wi-Fi on/off, sospensione RTC e ciclo autonomo su 3 giri.
Il ripiego batteria (`powerd_test -s` quando `capacity` manca) è implementato ma **non ancora provato
sul device**: la riga C9 dice cosa manca.

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
| C2 | 20 cicli senza interventi | **Non testato** | — | cadenza reale (`refresh_seconds`) e misura batteria |
| C9 | Lettura batteria per la misura di autonomia | **Non testato** | `inventory` usa `capacity` e, se manca, `powerd_test -s` (via `sed`) | il ripiego non è mai stato eseguito: serve un `inventory` prima e dopo i 20 giri |
| C3 | Server offline / IP cambiato nel ciclo | **Parziale** | `check` registra fallimento e non sovrascrive l'ultima immagine valida | non eseguito nel ciclo reale |
| C4 | Errori gestiti senza lasciare il device in stato strano | **Parziale** | nessuna voce ferma il framework; `suspend_rtc` sospende solo dopo aver scritto l'allarme; `wifi_on` ha un timeout di 60 s | se il driver scarta l'allarme senza errore, il device può restare addormentato fino al tasto: il recupero è USB |
| C5 | Rollback | **Verificato per costruzione** | basta non avere una voce di avvio automatico; il ciclo si ferma con **Ferma ciclo** | il file `STOP` resta finché non si riavvia il ciclo |

## Come aggiornare questa matrice

Dopo ogni esperimento: sostituire lo stato, aggiungere **la riga di log o il comando** che lo prova
e togliere la limitazione corrispondente. La prova vera è il log con l'output **più** l'osservazione
dello schermo.