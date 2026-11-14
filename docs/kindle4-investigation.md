# Kindle 4: indagine sul percorso senza browser

Branch: `investigation/kindle4-render-wake`.
Obiettivo: capire **dove** si blocca il ciclo senza browser e separare le fasi che oggi vengono
confuse in un unico «non funziona»: download, decodifica, disegno, interazione con il framework,
Wi-Fi, sospensione, risveglio.

Questo documento distingue sempre tre livelli: **verificato** (con la prova accanto), **fallito**
(con l'errore) e **non testato** (perché serve un'azione sul device che non è stata fatta).

## 1. Metodo

1. Audit del codice e degli script del repository, letto **prima** di proporre qualunque modifica.
   `tests/test_kindle_scripts.py` tiene allineati `menu.json` e i rami del `case` e impone i finali
   di riga LF; la **sintassi `sh` non è stata eseguita** su una shell POSIX (sul PC di sviluppo non
   ce n'è una disponibile), quindi va confermata dal primo `inventory` sul device.
2. Prove eseguibili da PC: struttura del PNG, endpoint, header HTTP, generazione delle varianti.
3. Inventario del Kindle **in sola lettura** tramite il mount USB (`G:\`): file presenti, log
   storico, binari installati. Nessuna scrittura sul device, nessun comando eseguito sul firmware.
4. Tutto ciò che richiede SSH, Wi-Fi spento/acceso, sospensione o risveglio RTC è classificato
   *non testato* e descritto come esperimento con approvazione esplicita.

Prova negativa importante: durante l'audit **nessun processo era in ascolto sulla porta 8787**
(`Get-NetTCPConnection -LocalPort 8787 -State Listen` vuoto), quindi il ciclo
download → render → display non è stato rieseguito in questa sessione. Il download dal device è
però già provato dal log (§4) e dal file `panel.png` scaricato.

## 2. Architettura attuale (quella che funziona)

```
config.toml -> collect() -> PanelData -> render_panel() -> PNG in memoria -> HTTP -> browser del Kindle
                    ^
        sources/* (fetch_payload -> parse) + Cache (ultimo payload buono)
```

| Componente | File | Cosa fa, in concreto |
|---|---|---|
| raccolta | `kindle_dashboard/collect.py:23` | orchestra le sezioni; ogni fonte fallisce da sola e ricade sulla cache |
| disegno | `kindle_dashboard/render/panel.py:192` | `render_panel()` compone header, meteo, agenda, treni, footer |
| tela | `kindle_dashboard/render/panel.py:202` | `Image.new("L", size, "white")`: **grigi 8 bit**, non 1 bit |
| scala layout | `kindle_dashboard/render/panel.py:221` | `scale = height / 800`, tutte le misure derivano da qui |
| PNG | `kindle_dashboard/server.py:65` | `image.save(buffer, format="PNG", optimize=True)` |
| servizio | `kindle_dashboard/server.py:26` | `PanelService`: lock unico, raccolta al massimo ogni 5 s (`:23`) |
| rotte | `kindle_dashboard/server.py:131` | `/panel.png`, `/health`, `/panel.html` e `/`, il resto 404 |
| header | `kindle_dashboard/server.py:154` | `Content-Type`, `Content-Length`, `Cache-Control: no-store` |
| pagina | `kindle_dashboard/server.py:105` | `<meta http-equiv="refresh">` + `<img src="/panel.png?t=<epoch>">` |
| risoluzione | `kindle_dashboard/config.py:21` | default **600x720**, non 600x800 (vedi §3) |
| cadenza | `kindle_dashboard/schedule.py:22` | giorno/notte e clamp al prossimo cambio di fascia |
| estensione | `kindle/extensions/dashboard/dashboard.sh.template` | solo diagnostica: nessun disegno del pannello |

Non c'è JavaScript, non c'è autenticazione, non ci sono redirect: il browser del Kindle riceve una
pagina statica con un `<img>` e un refresh meta. È il pezzo di infrastruttura più povero possibile,
ed è per questo che funziona su NetFront.

## 3. Cosa produce il server (verificato sul PC)

Ispezione fatta con `python kindle/inspect_png.py` (nuovo strumento di questa branch):

```
docs\preview.png:            PNG 600x800 mode=L bit_depth=8 color_type=0(grayscale) interlace=none
G:\dashboard\panel.png:      PNG 600x800 mode=L bit_depth=8 color_type=0(grayscale) interlace=none
cache\testimages\test_1.png: PNG 600x800 mode=1 bit_depth=1 color_type=0(grayscale) interlace=none
cache\testimages\test_p.png: PNG 600x800 mode=P bit_depth=4 color_type=3(indexed)    interlace=none
cache\testimages\test_rgb.png: PNG 600x800 mode=RGB bit_depth=8 color_type=2(truecolor) interlace=none
```

Conseguenze, in ordine di importanza per l'indagine:

1. **Il PNG del pannello è già nel formato più semplice possibile** per un decoder minimale:
   grigi 8 bit, nessun alpha, nessuna palette, nessun interlacciamento. Se `eips` non lo mostra,
   **non è (solo) un problema di formato**: le varianti RGB/1 bit/palette servono a dimostrarlo,
   non a «trovare quello giusto».
2. La tela del pannello è **600x720**, non 600x800: l'altezza è ridotta perché nel browser la barra
   degli indirizzi toglie ~70 px (`config.toml`, sezione `[panel]`). Un disegno nativo a schermo
   intero vorrebbe invece 600x800 o la geometria reale del framebuffer: sono due target diversi e
   non vanno confusi. `docs/preview.png` è 600x800 perché è un'immagine di documentazione.

## 4. Inventario del device (letto via USB, sola lettura)

Il Kindle era montato come unità `G:\` durante l'audit. Contenuto della radice:

```
system/  documents/  developer/  dashboard/  koreader/  extensions/
```

| Voce | Valore osservato | Come |
|---|---|---|
| estensioni KUAL | `koreader`, `dashboard` (+ `KUAL.cfg`) | `G:\extensions\` |
| script deployato | `dashboard.sh`, `config.xml`, `menu.json` | `G:\extensions\dashboard\` |
| dati pannello | `dashboard.log`, `panel.png` (21.530 B, 2026-10-31 18:27) | `G:\dashboard\` |
| fbink | `G:\koreader\fbink`, 1.063.032 B | `G:\koreader\` |
| firma della build fbink | il binario contiene `Image support is disabled` all'offset **278.700** | ricerca binaria sul file |
| versione firmware (via USB) | **non disponibile**: `G:\system\` non contiene `version.txt` | elenco `G:\system\` |

### 4.1 Inventario eseguito sul device (2026-11-14, da KUAL, sola lettura)

Il comando `inventory` ha risposto a tutte le voci che il mount USB non espone. Valori reali, dal
log (`2026-11-14T11:08`):

| Voce | Valore | Riga di prova |
|---|---|---|
| firmware | `System Software Version: 001-H303_yoshi-354363`, build `Thu May 30 11:05:42 UTC 2019` | `version exit=0` |
| kernel | `Linux kindle 2.6.31-rt11-lab126 #5 … armv7l` | `uname exit=0` |
| CPU / RAM | ARMv7 rev 5, BogoMIPS 799.53, `MemTotal: 256112 kB` | `cpu exit=0`, `memoria exit=0` |
| disco | `/dev/mmcblk0p1` 348,8 MB, 219,4 MB usati, 111,8 MB liberi | `disco exit=0` |
| framebuffer | **600x800, 8 bpp, `grayscale: 1`, `line_length: 600`**, formato `Y8` | `eips_info exit=0`, `fbink_version exit=0` |
| fbink | `FBInk 92e1270 for Kindle [Draw=Yes, Bitmap=Yes, … Image=No, …]` | `fbink_version exit=0` |
| Wi-Fi | `cmState = CONNECTED` | `wifi_state exit=0` |
| salvascherino | `preventScreenSaver = 1` (già disattivato da una sessione precedente) | `screen_saver exit=0` |
| sospensione | `/sys/power/state` = `standby mem`; RTC `rtc0` = `mxc_rtc`, `rtc1` = `pmic_rtc` | `power_state`, `rtc` |
| TLS | `OpenSSL 0.9.8j 07 Jan 2009` | `openssl exit=0` |
| shell | `BusyBox v1.7.2 (2019-05-30)`: **niente `command -v`, niente `grep -E`, `wget` senza `-T`** | `comandi`, `wget_help`, `processi exit=1` |
| assenti | `curl`, `file`, `ip`, `ifconfig`, `rtcwake`, `powerd_test`, `od` (dalla lista cercata) | `comandi` |

Conseguenze dirette:

1. **Il framebuffer accetta esattamente ciò che produciamo**: 600x800, 8 bpp, scala di grigi. Il PNG
   del pannello è `L` 8 bit non interlacciato (D3) e la tela servita al browser è 600x720: il test
   nativo corretto è quindi **600x800**, che è il default di `kindle/make_test_images.py`.
2. **`fbink` dichiara `Image=No`**: la build MINIMAL non è un'ipotesi, è la configurazione compilata.
3. **BusyBox 1.7.2 è vecchio**: `command -v` non esiste, `grep` non ha `-E`, `wget` non ha `-T`.
   Il primo giro di `inventory` ha rivelato tutti e tre i limiti (vedi `which_list`, `processi` e
   `check`); lo script ora non usa più queste opzioni e il timeout del download è un watchdog in
   background.
4. **Wi-Fi connesso e salvascherino disattivato** al momento del test: `check` è fallito perché sul
   PC **non c'era il server in ascolto** (`Get-NetTCPConnection -LocalPort 8787` vuoto), non per la
   rete. La rete resta quella del PC (`192.168.1.14`) letta da `deploy.ps1`.

Cosa **non** si può sapere dal mount USB: `/proc`, `/sys`, presenza di `curl`/`file`/`rtcwake`,
geometria del framebuffer, stato del Wi-Fi, proprietà `lipc`. Sono esattamente le voci raccolte dal
comando `inventory` della §8 e riportate qui sopra.

## 5. Il log del device: cosa è già stato provato

Citazioni letterali da `G:\dashboard\dashboard.log` (l'ordine è quello del file):

```
[FBInk] Image support is disabled in this FBInk build!
[CLI] Failed to display that image!
2026-10-31T20:19:33 entry: once | eips=/usr/sbin/eips fbink=/mnt/us/koreader/fbink wget=/usr/bin/wget
2026-10-31T20:19:46 uname: Linux kindle 2.6.31-rt11-lab126 #5 Sat Jan 12 20:39:09 PST 2013 armv7l unknown
2026-10-31T20:19:46 eips nel filesystem: eips eiputs
2026-10-31T20:19:46 eips -i: |Fixed framebuffer info|
2026-10-31T20:19:46 fbink -v: [FBInk] Detected a Kindle 4 (0x0E => Tequila on Yoshi)
2026-10-31T20:19:46 png: 19721 byte
2026-10-31T20:19:46 draw di prova exit=0
2026-10-31T20:27:26 framework fermato
2026-10-31T20:27:27 pannello aggiornato
2026-10-31T20:43:56 test test_l.png exit=0
2026-10-31T20:44:04 test test_rgb.png exit=0
2026-10-31T20:44:12 test test_1.png exit=0
2026-10-31T20:44:20 test test.jpg exit=0
2026-10-31T20:44:29 framework riavviato
2026-11-01T20:16:01 preventScreenSaver=1 -> ok
```

Lettura di queste righe:

1. **Il download funziona**: `png: 19721 byte` e il file da 21.530 B sul device. `wget` è in
   `/usr/bin/wget`. Il collo di bottiglia non è la rete locale né l'endpoint.
2. **`fbink` dichiara da solo il motivo del fallimento**: la build MINIMAL di KOReader non ha il
   supporto immagini. Non è un nostro errore di sintassi e non c'è opzione che lo aggiri: la
   stringa è compilata dentro il binario (offset 278.700), non nel nostro comando.
3. **`eips` restituisce `exit=0` in tutti e quattro i formati** (L, RGB, 1 bit, JPEG) e lo schermo
   resta bianco. La prova è nel log, quindi non serve ripeterla per crederci: serve ripeterla
   **registrando anche l'output** e il nome del comando esatto, che il vecchio script non salvava.
   Per questo `images` e `show` scrivono `exit` + output su una riga.
4. **`framework fermato` → `framework riavviato`**: il test è stato fatto fermando il framework.
   È l'unica riga in cui il device è stato lasciato senza interfaccia; l'effetto collaterale già
   documentato (schermo bianco, unità USB non esposta fino al riavvio) rende questa strada una
   prova da non ripetere senza un motivo nuovo.
5. **Nessuna riga su Wi-Fi, RTC o sospensione**: quei passi non sono mai stati eseguiti. Non sono
   falliti: sono *non testati*.
6. `eips -i` del vecchio test era stato collassato in una riga (`|Fixed framebuffer info|`): **la
   geometria non era registrata**. Il nuovo `inventory` la riporta per intero (§5.1).
7. La versione del firmware non era disponibile via USB: `uname` dà il kernel, non il firmware
   Lab126. Ora è letta da `/etc/version` (§5.1).

### 5.1 Secondo giro (2026-11-14, comando `inventory` da KUAL)

```
2026-11-14T11:08:18 version exit=0: System Software Version: 001-H303_yoshi-354363|Thu May 30 11:05:42 UTC 2019
2026-11-14T11:08:19 eips_info exit=0: |Fixed framebuffer info| … xres: 600  yres: 800  bits_per_pixel: 8  grayscale: 1 … line_length: 600
2026-11-14T11:08:19 fbink_version exit=0: … FBInk 92e1270 for Kindle [Draw=Yes, Bitmap=Yes, Fonts=Yes, Unifont=No, OpenType=Yes, Image=No, …]
2026-11-14T11:08:19 processi exit=1: grep: invalid option -- 'E'
2026-11-14T11:08:20 wifi_state exit=0: CONNECTED
2026-11-14T11:08:20 screen_saver exit=0: 1
```

Le ultime due righe raccontano due cose diverse e vanno tenute separate:

- `cmState = CONNECTED` e `preventScreenSaver = 1` sono **stato reale del device** (Wi-Fi connesso,
  salvascherino disattivato da una sessione precedente).
- `processi exit=1` e il `comandi:` con tutto `ASSENTE` erano **bug del nostro script** su questa
  build: `grep` non conosce `-E` e la shell non ha `command -v`. Sono stati corretti (ricerca nel
  `PATH` fatta a mano; `grep -e … -e …`), insieme a `wget -T`, che `wget_help` ha dimostrato non
  esistere (ora il timeout è un watchdog in background).

Il valore più importante è la geometria: **600x800, 8 bpp, `grayscale: 1`, formato `Y8`**. È
esattamente il formato del PNG del pannello, quindi il formato giusto c'era già.

### 5.2 Il test dei formati, rifatto senza fermare il framework (2026-11-14)

```
2026-11-14T11:14:10 === immagini ===
2026-11-14T11:14:11 immagine test.jpg exit=0
2026-11-14T11:14:14 immagine test_1.png exit=1 -> eips: paint_image> cannot open "...":8bit only
2026-11-14T11:14:17 immagine test_l.png exit=0
2026-11-14T11:14:21 immagine test_p.png exit=1 -> eips: paint_image> cannot open "...":8bit only
2026-11-14T11:14:24 immagine test_rgb.png exit=0
2026-11-14T11:14:27 === fine immagini ===
```

Risultato visivo (osservato sullo schermo): le immagini passano e si vedono; l'ultima, `test_rgb.png`,
è **deformata**. Lettura:

- `eips` **disegna** con il framework avviato: grigi 8 bit (`test_l.png`) e JPEG sono visibili;
- il vincolo reale è **8 bit**: 1-bit e palette indicizzata (4 bit) sono rifiutati con `8bit only`, non
  con un errore di sintassi;
- RGB 8 bit viene accettato (`exit=0`) ma reso male: l'exit code prova che il file è stato letto, non
  che l'immagine sia corretta;
- il vecchio «schermo bianco» era quindi un **test falsato**: girava dopo `framework fermato`, ed è
  l'unica variabile cambiata fra i due giri oltre ai nomi dei file.

Il pannello produce `L` 8 bit: è il caso che funziona. Il prossimo passo non è più «capire se `eips`
disegna», ma «far girare un ciclo nativo e verificarlo» (§8, E2-E3).

### 5.3 Il framework ridisegna all'uscita di KUAL; il ciclo in background lo recupera (2026-11-14)

`Mostra panel.png` ha disegnato il pannello **e poi lo ha perso**: `eips` funziona, ma quando KUAL
esce il framework ridisegna la schermata e copre l'immagine. Nel log: `show panel.png exit=0` due
volte, nessun errore.

Con un ciclo in background (`loop`, 15 s) il pannello viene ripreso al giro successivo:

```
2026-11-14T11:30:48 loop: avvio ogni 15 s
2026-11-14T11:30:49 loop: disegnato panel.png
… nove giri fino alle 11:33:05 …
2026-11-14T11:33:16 loop: stop richiesto (pid 3011)
2026-11-14T11:33:20 loop: terminato
```

Conclusioni:

- il processo in background **sopravvive all'uscita di KUAL**: ha continuato a disegnare per oltre
  due minuti, quindi il disegno periodico è possibile **senza** fermare il framework;
- il pid file con `kill -0` ha impedito il doppio avvio e lo stop ha funzionato; dopo il test lo stop
  è stato reso immediato (`kill` + `trap` che rimuove il pid), perché aspettare la fine del `sleep`
  rendeva una corsa fermarlo mentre il pannello ricopriva KUAL;
- resta un **costo d'uso**: mentre il ciclo gira, il pannello copre l'interfaccia a ogni giro, quindi
  KUAL è raggiungibile solo nella finestra fra due disegni. Per un ciclo reale l'intervallo deve
  venire da `refresh_seconds` (90 s di giorno, 3600 s di notte) e lo stop deve restare immediato.

## 6. Diagnosi per fase

| Fase | Stato | Prova / motivo |
|---|---|---|
| Endpoint e header (PC) | **Verificato** | `server.py:131-160`: `/panel.png` `image/png`, `Content-Length`, `no-store`; nessun redirect, nessuna autenticazione |
| Download device → PC | **Verificato** | `panel.png` 21.530 B sul device; log `png: 19721 byte`; `wget` in `/usr/bin` |
| Integrità del PNG | **Verificato** | `mode=L bit_depth=8 interlace=none`, cioè il caso più semplice da decodificare |
| Geometria del framebuffer | **Verificato** | `inventory` 2026-11-14: 600x800, 8 bpp, `grayscale: 1`, `line_length: 600`, formato `Y8` |
| Decodifica/disegno con `eips`, L 8 bit | **Verificato** | `test_l.png` → `exit=0` e **visibile**; il pannello è `L` 8 bit (§5.2) |
| Disegno con `eips`, JPEG | **Verificato** | `test.jpg` → `exit=0` e visibile |
| Disegno con `eips`, RGB 8 bit | **Parziale** | `test_rgb.png` → `exit=0` ma **deformato**: accettato dal decoder, reso male |
| Disegno con `eips`, 1-bit / palette | **Fallito (rifiutato)** | `eips: paint_image> cannot open "…":8bit only` |
| Disegno con `fbink` di KOReader | **Fallito** | `FBInk 92e1270 … Image=No`: build senza supporto immagini |
| Framework fermato per liberare lo schermo | **Fallito e rischioso** | schermo bianco, USB non più esposta, riavvio; **falsava** il test `eips` (§5.2) |
| Persistenza del disegno dopo l'uscita da KUAL | **Verificato** | il ciclo `loop` ha disegnato 9 volte in 2m17s **dopo** l'uscita da KUAL (§5.3) |
| Ciclo di disegno periodico (senza download) | **Verificato** | giro da 15 s, pid verificato con `kill -0`, stop immediato |
| Interazione con l'interfaccia Amazon | **Parziale** | il pannello copre KUAL a ogni giro: l'interfaccia si usa solo fra due disegni |
| Browser | **Verificato dall'uso reale** | pagina con meta refresh e PNG statico; nessun JS |
| Wi-Fi: stato radio (lettura) | **Verificato** | `lipc-get-prop com.lab126.wifid cmState` → `CONNECTED` |
| Wi-Fi on/off | **Non testato** | nessun comando eseguito; nessuno script di questa branch spegne la radio |
| RTC e sospensione: meccanismo | **Parziale** | `/sys/power/state` = `standby mem`; `rtc0` = `mxc_rtc`, `rtc1` = `pmic_rtc`; `rtcWakeup` mai impostato |
| Risveglio RTC / ripresa del processo | **Non testato** | nessun comando eseguito |
| Compatibilità BusyBox 1.7.2 | **Verificato** | `command -v`, `grep -E` e `wget -T` assenti: script adattato e verificato in container |
| Ciclo completo periodico | **Non testato** | dipende dai passi precedenti |

**Diagnosi (aggiornata al 2026-11-14)**: disegno e persistenza sono **verificati**: `eips` disegna
immagini 8 bit con il framework avviato, e un ciclo in background le riprende dopo l'uscita da KUAL.
Il vecchio «schermo bianco» era un test falsato dal `framework stop` (due variabili insieme). Restano
da dimostrare il **download dal PC nel ciclo**, il **Wi-Fi on/off** e la **ripresa RTC**: nessuno dei
tre è stato eseguito. Il vincolo di formato (solo 8 bit, RGB reso male) non tocca il pannello.

## 7. Perché il browser resta la baseline

Il browser è la baseline **per scelta prudente, non perché il framebuffer sia inutilizzabile**: è
l'unico percorso con una prova di successo ripetuta, non richiede nulla sul device e non può
lasciarlo in uno stato strano. Il disegno nativo ha ora due prove (`images` §5.2 e `loop` §5.3), ma
non un ciclo completo: mancano download dal PC, Wi-Fi on/off, ripresa RTC e una misura di batteria.
In più il pannello nativo copre l'interfaccia mentre è a schermo. Il costo del browser è noto solo a
metà: la batteria con la pagina aperta per ore **non è stata misurata**.

Due dettagli che l'indagine ha chiarito e che vanno tenuti fermi:

- la tela servita al browser è **600x720**, quindi un test nativo deve usare **600x800** (o la
  geometria reale del framebuffer): confrontare un PNG 600x720 con uno schermo 600x800 non dice
  nulla sulla capacità di `eips`, dice solo che l'immagine è più corta;
- `Cache-Control: no-store` non basta sui browser mobili: l'HTML usa `/panel.png?t=<epoch>`
  (`server.py:105`), altrimenti si continua a vedere il pannello vecchio. Qualunque client nativo
  dovrà fare lo stesso (URL con timestamp) per non mostrare un'immagine stantia.

## 8. Prossimi esperimenti, in ordine

E1 ed E2 sono stati eseguiti il 2026-11-14 (risultati in §4.1 e §5.2); restano E3-E6. Ognuno indica
cosa serve e cosa potrebbe rompersi; le scritture sul Kindle (`deploy.ps1` senza `-DryRun`) richiedono
il tuo ok.

### E1 — Inventario completo (fatto il 2026-11-14, sola lettura)

```powershell
python kindle\make_test_images.py        # rigenera cache\testimages con la scheda e il timestamp
.\kindle\deploy.ps1 -DryRun              # controlla host/porta prima di scrivere
.\kindle\deploy.ps1 -TestImages          # copia estensione + varianti (scrive su G:\)
```

Sul Kindle: **KUAL → Dashboard → Inventario**, poi leggi il log dal PC (`Get-Content
G:\dashboard\dashboard.log -Tail 40`). Risultato: §4.1. Ha rivelato anche i tre limiti del BusyBox
1.7.2, corretti nello script.

### E2 — Formati con `eips`, senza fermare il framework (fatto il 2026-11-14)

**KUAL → Dashboard → Test immagini (eips)**: `eips -c`, poi `eips -f -g` su ogni variante, con `exit`
e output nel log e 3 s fra un file e l'altro. Risultato: §5.2 — **disegna** (grigi 8 bit e JPEG),
rifiuta 1-bit e palette (`8bit only`), rende male l'RGB.

### E3 — Immagine vera, geometria nativa (fatto il 2026-11-14)

`Mostra panel.png` (600x800 `L`) ha disegnato il pannello integro: **la geometria non è un problema**.
L'immagine spariva all'uscita da KUAL, e un ciclo in background l'ha ripresa (§5.3). Per confrontare
le due tele dello stesso contenuto si può generare un PNG 600x720 e uno 600x800 (con un
`config` di prova che ha `height = 800`, senza toccare quello di produzione), ma il test decisivo è
già passato.

### E4 — Ciclo con download dal PC (prossimo)

Il ciclo attuale ridisegna lo stesso `panel.png` (contenuto del 31/10). Il passo successivo è
scaricarlo dal server a ogni giro, con le stesse regole di `check`: file temporaneo, verifica
dimensione+firma PNG, poi `eips`. Servono:

- **server acceso** sul PC (`python -m kindle_dashboard serve`) e raggiungibile dal device:
  prima si prova **KUAL → Verifica server**; se fallisce per firewall, `kindle\allow-lan.ps1` da
  PowerShell **amministratore** (la rete è `Public`, regola `Private` inapplicabile);
- nessuna gestione Wi-Fi in questo passo: il device è già connesso (`cmState CONNECTED`);
- stop immediato fra un giro e l'altro, come ora.

### E5 — Solo se serve: help e versione di `eips`

`inventory` ora registra anche `eips_help` (uso della versione installata), quindi non serve SSH.
Comandi comunque utili da shell, **in sola lettura**:

```sh
eips 2>&1 | head -n 40
eips -i
cat /etc/version
```

Confronto con le fonti esterne già citate nel mandato (`wiki.mobileread.com/wiki/Eips` e la
discussione sulle differenze fra versioni). **Non** installare il fbink completo né altri binari
senza approvazione.

### E6 — Wi-Fi acceso/spento (richiede approvazione)

Da provare solo **dopo** che il disegno funziona, altrimenti si misura un ciclo che non mostra
niente. Comandi candidati (da verificare prima con `lipc-get-prop`):

```sh
lipc-set-prop com.lab126.cmd wirelessEnable 0
lipc-set-prop com.lab126.cmd wirelessEnable 1
lipc-get-prop com.lab126.wifid cmState          # atteso CONNECTED, con timeout massimo
```

La sessione SSH via Wi-Fi muore alla disconnessione: prima servono accesso USB o un secondo canale
di controllo. Nessuno script di questa branch spegne la radio.

### E7 — RTC, sospensione, ciclo completo

Non implementato di proposito. Prima va verificato il meccanismo (`lipc-set-prop -i
com.lab126.powerd rtcWakeup <secondi>`, `powerd_test` per osservare gli stati), poi un singolo
risveglio breve, poi un ciclo con lock, uscita manuale e log; 20 cicli e una misura di batteria su
più ore sono il criterio per parlare di autonomia. Un reboot non è una ripresa.

## 9. Cosa è cambiato in questa branch

| File | Perché |
|---|---|
| `kindle/inspect_png.py` | ispezione del PNG (formato, profondità, interlace) senza guardare il file a occhio |
| `kindle/make_test_images.py` | genera la scheda di prova con **data e ora** e le varianti di formato in `cache/testimages` |
| `kindle/extensions/dashboard/dashboard.sh.template` | nuove voci `inventory` (sola lettura), `images`, `show`; `check` con timeout 10 s e verifica «è davvero un PNG»; log con exit code |
| `kindle/extensions/dashboard/menu.json` | tre voci nuove per pilotare i test da KUAL, senza SSH |
| `kindle/deploy.ps1` | messaggi corretti: come generare le varianti e che il pannello si apre nel browser (la voce «Avvia pannello» non esiste più) |
| `docs/kindle4-investigation.md`, `docs/kindle4-test-matrix.md` | questo rapporto e la matrice dei test |

Non toccati: endpoint, renderer, modello, configurazione, pagina HTML, cadenza di aggiornamento.
Nessun comando ferma il framework, spegne il Wi-Fi o sospende il device, e nessun binario è stato
installato o sostituito.

Segreti: l'URL iCal privato (`config.toml`, ignorato da git) e l'IP del PC non compaiono in questo
documento; nel log del device restano host e porta del server, che sono dati di rete locale.
