# Kindle 4 — matrice dei test

Compagna di `docs/kindle4-investigation.md`. Ogni riga è una fase **separata**: un fallimento non
contagia le altre, e «non testato» non significa «fallito».

Legenda: **Verificato** = c'è una prova ripetibile nel repository o nel log; **Fallito** = c'è una
prova di errore; **Non testato** = nessuno l'ha ancora eseguito (serve un'azione sul device).

Ultimo aggiornamento di questa matrice: audit iniziale sulla branch
`investigation/kindle4-render-wake` (Kindle collegato via USB, server non in ascolto).

## Download e integrità

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| D1 | `/panel.png` raggiungibile e con header corretti | **Verificato** | `server.py:131-160`: 200, `image/png`, `Content-Length`, `Cache-Control: no-store`; nessun redirect, nessuna auth | provato leggendo il codice e con i test HTTP del repository, non dal device in questa sessione |
| D2 | Il device scarica davvero il PNG | **Verificato** | `G:\dashboard\panel.png` (21.530 B); log: `png: 19721 byte`; `wget` in `/usr/bin/wget` | il server non era in ascolto durante l'audit: prova storica, non ripetuta oggi |
| D3 | Il PNG è nel formato più semplice | **Verificato** | `kindle/inspect_png.py`: `mode=L bit_depth=8 color_type=0(grayscale) interlace=none` | vale per il file scaricato a ottobre; il renderer non è cambiato da allora (`panel.py:202`) |
| D4 | HTTP 200 con HTML di errore invece del PNG | **Parziale** | `dashboard.sh.template` ora verifica dimensione ≥ 1000 B e presenza della firma `PNG` prima di dire «OK» | la nuova verifica non è ancora stata eseguita sul device |
| D5 | File vuoto o troncato | **Non testato** | — | richiede di servire apposta un file rotto; `check` lo intercetterebbe come «non PNG» |

## Rendering nativo

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| R1 | `eips -g` con grigi 8 bit | **Fallito** | log: `test test_l.png exit=0`, schermo bianco | il formato non era la causa (D3) |
| R2 | `eips -g` con RGB | **Fallito** | log: `test test_rgb.png exit=0`, schermo bianco | idem |
| R3 | `eips -g` con 1 bit | **Fallito** | log: `test test_1.png exit=0`, schermo bianco | idem |
| R4 | `eips -g` con JPEG | **Fallito** | log: `test test.jpg exit=0`, schermo bianco | idem |
| R5 | `eips -c` + `eips -f -g` (sintassi attuale) | **Non testato** | comando `images` aggiunto in questa branch, registra output ed exit | serve eseguirlo da KUAL |
| R6 | Help/opzioni della versione di `eips` presente | **Non testato** | — | serve una shell: `eips 2>&1 \| head -n 40` |
| R7 | Geometria del framebuffer | **Non testato** | il vecchio log ha solo `eips -i: \|Fixed framebuffer info\|` (output collassato) | il nuovo `inventory` lo registra per intero |
| R8 | `fbink` di KOReader | **Fallito** | `[FBInk] Image support is disabled in this FBInk build!`; la stringa è nel binario (offset 278.700) | nessuna opzione la aggira: è una build MINIMAL |
| R9 | `fbink` completo (altra build) | **Non testato** | — | richiede installare un binario: approvazione esplicita, compatibilità firmware ignota |
| R10 | Framework fermato per liberare lo schermo | **Fallito e rischioso** | log: `framework fermato` → `framework riavviato`; effetto noto: schermo bianco, USB non esposta, riavvio | non ripetere senza un motivo nuovo |

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
| W2 | Riaccensione e ritorno a `CONNECTED` | **Non testato** | — | `cmState` mai letto |
| W3 | Radio davvero spenta (non solo IP) | **Non testato** | — | richiede lettura dello stato radio, non solo assenza di traffico |

## RTC, sospensione e ripresa

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| S1 | `rtcWakeup` accettato dal firmware | **Non testato** | — | sintassi e unità da verificare prima |
| S2 | Ingresso in sospensione vera | **Non testato** | — | `powerd_test` non usato |
| S3 | Risveglio all'orario programmato | **Non testato** | — | un reboot non è una ripresa |
| S4 | Il processo riprende dopo il wake | **Non testato** | — | nessun loop implementato di proposito |
| S5 | Wi-Fi ripristinato dopo il wake | **Non testato** | — | dipende da W1-W2 |

## Ciclo completo e robustezza

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| C1 | Ciclo completo (wake → Wi-Fi → PNG → display → Wi-Fi off → sleep) | **Non testato** | — | dipende da R5-R7 e S1-S5 |
| C2 | 20 cicli senza interventi | **Non testato** | — | nessun loop con lock implementato |
| C3 | Server offline / IP cambiato | **Parziale** | `check` registra il fallimento e non sovrascrive l'ultima immagine valida | non eseguito sul device |
| C4 | Errori gestiti senza lasciare il device in stato strano | **Parziale** | nessuna voce tocca framework, Wi-Fi o sospensione | vale per la diagnostica, non per un ciclo nativo |
| C5 | Rollback | **Verificato per costruzione** | basta non avere una voce di avvio automatico: il pannello nel browser non richiede installazione | non esiste ancora nulla da rimuovere |

## Come aggiornare questa matrice

Dopo ogni esperimento: sostituire lo stato, aggiungere **la riga di log o il comando** che lo prova
e togliere la limitazione corrispondente. Un `exit=0` da solo non è una prova di disegno: la prova
di R1-R4 è «schermo bianco **e** exit 0», cioè proprio il caso in cui l'exit code mente.
