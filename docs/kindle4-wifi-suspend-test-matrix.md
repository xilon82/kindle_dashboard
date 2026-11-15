# Kindle 4 — matrice Wi-Fi, RTC, sospensione e ripresa

Compagna di `docs/kindle4-wifi-suspend-investigation.md`. Ogni riga è una fase **separata**: un fallimento non
contagia le altre, e «non testato» non significa «fallito».

Legenda: **Verificato** = c'è una prova ripetibile; **Fallito** = c'è una prova di errore; **Non testato** = nessuno l'ha ancora eseguito.

Ultimo aggiornamento: **2026-11-14**, branch `investigation/kindle4-wifi-suspend` creato.

## Wi-Fi

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| W1 | `cmState` letto da `inventory` | **Verificato** | `wifi_state exit=0: CONNECTED` | lettura, non prova di spegnimento |
| W2 | Spegnimento radio (`wirelessEnable 0`) | **Non testato** | — | richiede approvazione e canale di recupero |
| W3 | Riaccensione e ritorno a `CONNECTED` | **Non testato** | — | ciclo on/off non eseguito |
| W3 | Radio davvero spenta (non solo IP) | **Non testato** | — | richiede lettura stato radio, non solo assenza traffico |

## RTC, sospensione e ripresa

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| S1 | Wake RTC programmato sul device | **Verificato** | `powerd` **non** ha proprietà RTC (9 nomi rifiutati); si usa `rtc1/wakealarm` con `since_epoch + N` | la rilettura è vuota (driver non supporta `cat`) |
| S2 | Ingresso in sospensione vera | **Verificato** | `echo mem > /sys/power/state`, standby confermato | — |
| S3 | Risveglio all'orario programmato | **Verificato** | sospeso 13:55:25, risvegliato 13:56:26 (**61 s**) | — |
| S4 | Il processo riprende dopo il wake | **Verificato** | `suspend_rtc: risvegliato, uptime=7854.21` (uptime continuo, non reboot) | — |
| S5 | Wi-Fi ripristinato dopo il wake | **Non testato** | — | dipende da W2-W3 |

## Ciclo completo e robustezza

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| C1 | Ciclo completo (wake → Wi-Fi → PNG → display → Wi-Fi off → sleep) | **Non testato** | disegno verificato (R1-R5, R13-R15, C6) | restano Wi-Fi on/off e RTC |
| C2 | 20 cicli senza interventi | **Non testato** | — | cadenza reale (`refresh_seconds`) e misura batteria |
| C3 | Server offline / IP cambiato nel ciclo | **Parziale** | `check` registra fallimento e non sovrascrive l'ultima immagine valida | non eseguito nel ciclo reale |
| C4 | Errori gestiti senza lasciare il device in stato strano | **Parziale** | nessuna voce tocca framework, Wi-Fi o sospensione | vale per la diagnostica, non per un ciclo nativo |
| C5 | Rollback | **Verificato per costruzione** | basta non avere una voce di avvio automatico; il ciclo si ferma con **Ferma ciclo** | il file `STOP` resta finché non si riavvia il ciclo |

## Come aggiornare questa matrice

Dopo ogni esperimento: sostituire lo stato, aggiungere **la riga di log o il comando** che lo prova
e togliere la limitazione corrispondente. La prova vera è il log con l'output **più** l'osservazione
dello schermo.