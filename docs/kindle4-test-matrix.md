# Kindle 4 — matrice dei test

Compagna di `docs/kindle4-investigation.md`. Ogni riga è una fase **separata**: un fallimento non
contagia le altre, e «non testato» non significa «fallito».

Legenda: **Verificato** = c'è una prova ripetibile nel repository o nel log; **Fallito** = c'è una
prova di errore; **Non testato** = nessuno l'ha ancora eseguito (serve un'azione sul device).

Ultimo aggiornamento: **2026-11-14**, dopo `inventory` (§4.1 della relazione) e il test dei formati
con `images` (§5.2). Le righe R1-R5 sono state rieseguite con il framework avviato.

## Download e integrità

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| D1 | `/panel.png` raggiungibile e con header corretti | **Verificato** | `server.py:131-160`: 200, `image/png`, `Content-Length`, `Cache-Control: no-store`; nessun redirect, nessuna auth | provato leggendo il codice e con i test HTTP del repository, non dal device in questa sessione |
| D2 | Il device scarica davvero il PNG | **Verificato** | `G:\dashboard\panel.png` (21.530 B); log: `png: 19721 byte`; `wget` in `/usr/bin/wget`; `check` 2026-11-14 fallito perché il server non era in ascolto, non per la rete | il ciclo completo con server acceso non è ancora stato rifatto |
| D3 | Il PNG è nel formato più semplice | **Verificato** | `kindle/inspect_png.py`: `mode=L bit_depth=8 color_type=0(grayscale) interlace=none` | vale per il file scaricato a ottobre; il renderer non è cambiato da allora (`panel.py:202`) |
| D4 | HTTP 200 con HTML di errore invece del PNG | **Parziale** | `dashboard.sh.template` verifica dimensione ≥ 1000 B e presenza della firma `PNG` prima di dire «OK» | la verifica non ha ancora potuto passare: `check` si ferma prima, senza server in ascolto |
| D5 | File vuoto o troncato | **Non testato** | — | richiede di servire apposta un file rotto; `check` lo intercetterebbe come «non PNG» |
| D6 | `/panel.png?h=800` per il client nativo | **Verificato** | `requested_height` validato (test), PNG servito dal container `600x800 L 8 bit` | il disegno a 800 sul device va confermato |

## Rendering nativo

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| R1 | `eips -g` con grigi 8 bit | **Verificato** | `immagine test_l.png exit=0` e scheda visibile a schermo (2026-11-14, framework avviato) | il formato L 8 bit è quello del pannello |
| R2 | `eips -g` con RGB | **Fallito (deformata)** | `immagine test_rgb.png exit=0` ma immagine **deformata** | accettato dal decoder, reso male: l'exit code non basta |
| R3 | `eips -g` con 1 bit | **Fallito (rifiutato)** | `exit=1 -> eips: paint_image> cannot open "…":8bit only` | il vincolo è la profondità, non il formato contenitore |
| R4 | `eips -g` con JPEG | **Verificato** | `immagine test.jpg exit=0` e immagine visibile | — |
| R5 | `eips -c` + `eips -f -g` (sintassi attuale) | **Verificato** | è il comando usato da `images`: immagini visibili, output ed exit nel log | — |
| R6 | Help/opzioni della versione di `eips` presente | **Non testato** | — | serve una shell: `eips 2>&1 \| head -n 40` |
| R7 | Geometria del framebuffer | **Verificato** | `inventory` 2026-11-14: 600x800, 8 bpp, `grayscale: 1`, `line_length: 600`, formato `Y8` | — |
| R8 | `fbink` di KOReader | **Fallito** | `[FBInk] Image support is disabled in this FBInk build!`; `FBInk 92e1270 … Image=No`; stringa nel binario (offset 278.700) | nessuna opzione la aggira: è una build MINIMAL |
| R9 | `fbink` completo (altra build) | **Non testato** | — | richiede installare un binario: approvazione esplicita, compatibilità firmware ignota |
| R10 | Framework fermato per liberare lo schermo | **Fallito e rischioso** | log: `framework fermato` → `framework riavviato`; schermo bianco, USB non esposta, riavvio; **falsava** il test `eips` del 2026-10-31 | non ripetere: non serve a disegnare |
| R11 | Comandi diagnostici su BusyBox 1.7.2 | **Parziale** | `inventory` ha rivelato `command -v`, `grep -E` e `wget -T` assenti; script corretto e verificato in container | la versione corretta non è ancora stata eseguita sul device |
| R12 | `eips -g` con palette indicizzata | **Fallito (rifiutato)** | `immagine test_p.png exit=1 -> …:8bit only` | come R3 |
| R13 | Persistenza dopo l'uscita da KUAL | **Verificato** | il ciclo ha disegnato 9 volte in 2m17s **dopo** l'uscita da KUAL | il pannello copre l'interfaccia a ogni giro |
| R14 | Ciclo periodico con stop | **Verificato** | giro da 15 s prima, 30 s poi; pid verificato (`kill -0`), stop immediato con `kill`, pid rimosso | — |
| R15 | Immagine a schermo intero (800 px) | **Verificato** | 600x800 `L` sul device, PNG `h=800` dal server, warm-up elimina la minibar | la minabar della home non è nostra; si può riservare spazio in alto (§5.5) |

## Browser (baseline)

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| B1 | Pagina con PNG e meta refresh | **Verificato dall'uso reale** | `server.py:105-124`; nessun JavaScript | non misurato: quanto resta stabile per ore |
| B2 | Refresh senza input manuale | **Verificato** | `<meta http-equiv="refresh">` + `/panel.png?t=<epoch>` | il device deve avere la pagina in primo piano |
| B3 | Il pannello sopravvive a blocco/sospensione | **Non testato** | — | dipende dal firmware e dal timeout schermo |
| B4 | Consumo batteria con la pagina aperta | **Non testato** | — | serve una misura di più ore, non una stima |
| B5 | Screensaver/UI che coprono il pannello | **Parziale** | `preventScreenSaver=1 -> ok` nel log | nessuna prova di durata oltre la sessione |

## Wi-Fi

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| W1 | Spegnimento radio (`wirelessEnable 0`) | **Non testato** | — | richiede approvazione e un canale di recupero (SSH muore) |
| W2 | Riaccensione e ritorno a `CONNECTED` | **Non testato** | — | il ciclo on/off non è stato eseguito |
| W3 | Radio davvero spenta (non solo IP) | **Non testato** | — | richiede lettura dello stato radio, non solo assenza di traffico |
| W4 | Stato radio in sola lettura | **Verificato** | `inventory` 2026-11-14: `cmState` → `CONNECTED` | lettura, non prova di spegnimento |

## RTC, sospensione e ripresa

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| S1 | `rtcWakeup` accettato dal firmware | **Non testato** | RTC presenti: `rtc0` = `mxc_rtc`, `rtc1` = `pmic_rtc`; `/sys/power/state` = `standby mem` | sintassi e unità da verificare prima |
| S2 | Ingresso in sospensione vera | **Non testato** | il kernel dichiara `standby mem` | `powerd_test` non usato |
| S3 | Risveglio all'orario programmato | **Non testato** | — | un reboot non è una ripresa |
| S4 | Il processo riprende dopo il wake | **Non testato** | — | nessun loop implementato di proposito |
| S5 | Wi-Fi ripristinato dopo il wake | **Non testato** | — | dipende da W1-W2 |

## Ciclo completo e robustezza

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| C1 | Ciclo completo (wake → Wi-Fi → PNG → display → Wi-Fi off → sleep) | **Non testato** | il disegno è verificato (R1/R5) | restano da provare Wi-Fi on/off e RTC (S1-S5) |
| C2 | 20 cicli senza interventi | **Non testato** | — | nessun loop con lock implementato |
| C3 | Server offline / IP cambiato | **Parziale** | `check` registra il fallimento e non sovrascrive l'ultima immagine valida | non eseguito sul device |
| C4 | Errori gestiti senza lasciare il device in stato strano | **Parziale** | nessuna voce tocca framework, Wi-Fi o sospensione | vale per la diagnostica, non per un ciclo nativo |
| C5 | Rollback | **Verificato per costruzione** | nessuna voce di avvio automatico: il ciclo si ferma con **Ferma ciclo** e il browser non richiede installazione | il file `STOP` resta finché non si riavvia il ciclo (che lo rimuove) |
| C6 | Ciclo periodico con download | **Verificato** | 6 giri a 30 s (~3 min) con `scaricato` + `disegnato`, stop immediato, pid rimosso | cadenza da test (30 s), non quella reale di `refresh_seconds` |
| C7 | Uso dell'interfaccia mentre il ciclo gira | **Parziale** | il pannello copre KUAL a ogni giro; lo stop è immediato; warm-up di 3 disegni a 5 s | resta una corsa fra due disegni: per un uso reale serve l'intervallo di `refresh_seconds` |

## Come aggiornare questa matrice

Dopo ogni esperimento: sostituire lo stato, aggiungere **la riga di log o il comando** che lo prova
e togliere la limitazione corrispondente. Un `exit=0` non prova che l'immagine sia *corretta*:
`test_rgb.png` esce 0 ed è deformata. La prova vera è il log con l'output (per 1-bit e palette dice
`8bit only`) **più** l'osservazione dello schermo.
