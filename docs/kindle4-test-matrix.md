# Kindle 4 — matrice dei test

Unica matrice del percorso nativo: compagna di `docs/kindle4-investigation.md` e di
`docs/kindle4-wifi-suspend-investigation.md` (la matrice Wi-Fi/RTC separata è stata assorbita qui).
Ogni riga è una fase **separata**: un fallimento non contagia le altre, e «non testato» non significa
«fallito».

Legenda: **Verificato** = c'è una prova ripetibile nel repository o nel log; **Fallito** = c'è una
prova di errore; **Non testato** = nessuno l'ha ancora eseguito (serve un'azione sul device).

Ultimo aggiornamento: **2026-11-25**. Le righe sono state rieseguite sul device; **contare i download
riusciti, non l'exit code del ciclo**: i venti giri del 25/11 sono arrivati in fondo con venti
`download fallito`, perché `HOST=` puntava al PC di sviluppo (`.14`) e non al server (`.187`).

## Download e integrità

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| D1 | `/panel.png` raggiungibile e con header corretti | **Verificato** | `server.py:131-160`: 200, `image/png`, `Content-Length`, `Cache-Control: no-store`; nessun redirect, nessuna auth | provato leggendo il codice e con i test HTTP del repository, non dal device in questa sessione |
| D2 | Il device scarica davvero il PNG | **Verificato** | `G:\dashboard\panel.png`; log `panel: scaricato panel.png (…)` in ogni giro dei run del 2026-11-15; `wget` in `/usr/bin/wget` | dal 24/11 i run hanno avuto zero download: dipendeva dal server spento, non dalla rete |
| D3 | Il PNG è nel formato più semplice | **Verificato** | `kindle/inspect_png.py`: `mode=L bit_depth=8 color_type=0(grayscale) interlace=none` | vale per il file scaricato a ottobre; il renderer non è cambiato da allora (`panel.py:202`) |
| D4 | HTTP 200 con HTML di errore invece del PNG | **Verificato** | `dashboard.sh.template` verifica dimensione ≥ 1000 B e firma `PNG` prima di dire «OK»; nei cicli reali non è mai comparso `panel: download non PNG` | la prova diretta (servire apposta una pagina HTML) non è stata fatta |
| D5 | File vuoto o troncato | **Non testato** | — | richiede di servire apposta un file rotto; `check` lo intercetterebbe come «non PNG» |
| D6 | `/panel.png?h=800` per il client nativo | **Verificato** | `requested_height` validato (test); PNG servito dal container `600x800 L 8 bit`; disegnato a schermo intero dal ciclo | — |

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
| R11 | Comandi diagnostici su BusyBox 1.7.2 | **Verificato** | `inventory` ha rivelato `command -v`, `grep -E` e `wget -T` assenti; gli script li evitano e girano sul device (`inventory`, `loop`, `cycle`); `tests/test_kindle_scripts.py` impedisce di reintrodurli | — |
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
| W1 | Stato radio in sola lettura | **Verificato** | `inventory`: `wifi_state exit=0: CONNECTED` | lettura, non prova di spegnimento |
| W2 | Spegnimento radio (`wirelessEnable 0`) | **Verificato** | `wifi_off: richiesto`, poi `cmState = NA` | — |
| W3 | Riaccensione e ritorno a `CONNECTED` | **Verificato** | `wifi_on: CONNECTED (dopo 6 s)`; ciclo off/on completo **31 s** | — |
| W4 | Radio davvero spenta (non solo IP) | **Parziale** | `cmState` passa a `NA` | non misura il consumo della radio |

## RTC, sospensione e ripresa

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| S1 | Wake RTC programmato sul device | **Verificato** | `powerd` **non** ha proprietà RTC (9 nomi rifiutati); si usa `rtc1/wakealarm` con `since_epoch + N` | la rilettura è vuota (il driver non supporta `cat`) |
| S2 | Ingresso in sospensione vera | **Verificato** | `echo mem > /sys/power/state`, standby confermato | — |
| S3 | Risveglio all'orario programmato | **Verificato** | sospeso 13:55:25, risvegliato 13:56:26 (**61 s**); in un ciclo reale `dmesg`: `Battery: Resume - TimeSuspended(secs)=89` | — |
| S4 | Il processo riprende dopo il wake | **Verificato** | `suspend_rtc: risvegliato, uptime=7854.21` (uptime continuo, non reboot) | — |
| S5 | Wi-Fi dopo il wake | **Verificato** | il download riesce 5 s dopo il risveglio, senza riaccendere la radio | — |

## Ciclo completo e robustezza

| ID | Caso | Stato | Prova | Limitazione |
|---|---|---|---|---|
| C1 | Ciclo completo (wake → PNG → display → sleep) | **Verificato** | `cycle 3`: sospensione 90 s, risvegli a 92/91/91 s, uptime continuo, download riuscito | manca la misura di batteria |
| C2 | 20 cicli senza interventi | **Verificato (run completi), ma attenzione** | 2026-11-15 15:27–16:05 e 21:34–22:12: 20 giri, risvegli ~91 s, uptime continuo, nessun `download fallito`. 2026-11-24/25 (08:02, 22:51, 23:44, 08:58): 20 giri raggiunti con **tutti i download falliti** (`HOST=` puntava a `.14`, il server è `.187`) e sospensioni da 30 s — sospensione provata, pannello no. Un tentativo del 15/11 si è interrotto al giro 14 con un riavvio (`wdog`), USB del PC collegata | manca la batteria prima/dopo di un run **con download riusciti** |
| C3 | Server offline / indirizzo cambiato | **Verificato** | i run del 24–25/11 sono la prova su larga scala: il ciclo tiene l'ultimo PNG e continua a girare | ha funzionato, ma svegliando il device ogni 30 s: da lì il backoff (C10) |
| C4 | Errori gestiti senza lasciare il device in stato strano | **Parziale** | con il caricatore le riprese sono corrette (`dmesg`: `PM: resume of devices complete after 1248 msecs`, uptime continuo); una sospensione con la USB del PC collegata si è chiusa con un riavvio (`wdog: Abnormal reset detected`) | causa del riavvio da isolare (USB/gadget/charger) |
| C5 | Rollback | **Verificato per costruzione** | nessuna voce di avvio automatico: il ciclo si ferma con **Ferma ciclo**; il browser non richiede installazione | il file `STOP` resta finché non si riavvia il ciclo (che lo rimuove) |
| C6 | Ciclo di ripiego senza sospensione | **Verificato** | 6 giri a 30 s (~3 min) con `panel: scaricato` + disegno, stop immediato, pid rimosso | serve a chi non si fida dell'RTC, non è la cadenza normale |
| C7 | Uso dell'interfaccia mentre il ciclo gira | **Parziale** | il pannello copre KUAL a ogni giro; lo stop è immediato; warm-up di 3 disegni a 5 s | resta una corsa fra due disegni |
| C9 | Lettura batteria per la misura di autonomia | **Verificato** | `inventory` 2026-11-15: `batteria exit=0: <vuoto>` (nessun `capacity`) e poi `95`/`97` dal ripiego `powerd_test -s`; `dmesg`: `Battery: Resume … RSOC=97` | il valore va letto **prima e dopo** un run con download riusciti: non è ancora stato fatto |
| C10 | Backoff con il server irraggiungibile | **Non testato** | codice: dopo 3 download falliti l'attesa va a 300 → 600 → 1200 → 1800 s; `/next` muto → `[panel] refresh_seconds` (90 s) | da provare sul device fermando il server apposta |

## Come aggiornare questa matrice

Dopo ogni esperimento: sostituire lo stato, aggiungere **la riga di log o il comando** che lo prova
e togliere la limitazione corrispondente. Un `exit=0` non prova che l'immagine sia *corretta*:
`test_rgb.png` esce 0 ed è deformata. La prova vera è il log con l'output (per 1-bit e palette dice
`8bit only`) **più** l'osservazione dello schermo.
