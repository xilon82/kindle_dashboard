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
| dati pannello | `dashboard.log` (2.765 B, ultima scrittura 2026-11-01 18:16), `panel.png` (21.530 B, 2026-10-31 18:27) | `G:\dashboard\` |
| fbink | `G:\koreader\fbink`, 1.063.032 B | `G:\koreader\` |
| firma della build fbink | il binario contiene `Image support is disabled` all'offset **278.700** | ricerca binaria sul file |
| versione firmware | **non disponibile** via USB: `G:\system\` non contiene `version.txt` | elenco `G:\system\` |

Cosa **non** si può sapere dal mount USB (serve il comando `inventory` sul device): `/proc`,
`/sys`, presenza di `curl`/`file`/`rtcwake`, geometria del framebuffer, stato del Wi-Fi, proprietà
`lipc`. Sono esattamente le voci raccolte dal nuovo comando `inventory` della §8.

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
6. `eips -i` ha prodotto solo l'intestazione `Fixed framebuffer info`: **la geometria del
   framebuffer non è registrata** (l'output multi-riga è stato collassato in una riga sola). Serve
   rileggerla per intero con il nuovo `inventory`.
7. La versione del firmware resta ignota: `uname` dà il kernel (`2.6.31-rt11-lab126`, build
   `#5 Sat Jan 12 20:39:09 PST 2013`), non il firmware Lab126. Va letto `/etc/version` sul device.

## 6. Diagnosi per fase

| Fase | Stato | Prova / motivo |
|---|---|---|
| Endpoint e header (PC) | **Verificato** | `server.py:131-160`: `/panel.png` `image/png`, `Content-Length`, `no-store`; nessun redirect, nessuna autenticazione |
| Download device → PC | **Verificato** | `panel.png` 21.530 B sul device; log `png: 19721 byte`; `wget` in `/usr/bin` |
| Integrità del PNG | **Verificato** | `mode=L bit_depth=8 interlace=none`, cioè il caso più semplice da decodificare |
| Decodifica/disegno con `eips` | **Fallito** | 4 formati, `exit=0`, schermo bianco (§5) |
| Disegno con `fbink` di KOReader | **Fallito** | build MINIMAL senza supporto immagini (messaggio + stringa nel binario) |
| Framework fermato per liberare lo schermo | **Fallito e rischioso** | schermo bianco, USB non più esposta, riavvio del device |
| Browser | **Verificato dall'uso reale** | pagina con meta refresh e PNG statico; nessun JS |
| Wi-Fi on/off | **Non testato** | nessun comando eseguito; `cmState` mai letto |
| RTC / sospensione / risveglio | **Non testato** | nessun comando eseguito; `rtcWakeup` mai impostato |
| Ciclo completo periodico | **Non testato** | dipende dai due precedenti |

**Diagnosi**: il blocco è al passo 4 (disegno sul framebuffer), non al passo 1-2. Le prove
disponibili non permettono di stabilire se `eips` non disegna perché (a) la sintassi/opzioni di
questa versione sono diverse, (b) l'immagine deve avere una geometria esattamente uguale al
framebuffer, o (c) il framework possiede lo schermo e `eips` scrive su un framebuffer che viene
subito ridisegnato. Le tre ipotesi si distinguono con l'inventario (§8, E1) e con i test E2-E3:
la (c) richiederebbe di nuovo di fermare il framework, quindi resta l'ultima e solo con approvazione.

## 7. Perché il browser resta la baseline

Il browser non è una scorciatoia presa senza prove: è l'unico percorso con una prova di successo
ripetuta, e non richiede nulla sul device (né binari, né framework fermato, né USB occupata). Il
suo costo è noto solo a metà: la batteria con la pagina aperta per ore **non è stata misurata**.

Due dettagli che l'indagine ha chiarito e che vanno tenuti fermi:

- la tela servita al browser è **600x720**, quindi un test nativo deve usare **600x800** (o la
  geometria reale del framebuffer): confrontare un PNG 600x720 con uno schermo 600x800 non dice
  nulla sulla capacità di `eips`, dice solo che l'immagine è più corta;
- `Cache-Control: no-store` non basta sui browser mobili: l'HTML usa `/panel.png?t=<epoch>`
  (`server.py:105`), altrimenti si continua a vedere il pannello vecchio. Qualunque client nativo
  dovrà fare lo stesso (URL con timestamp) per non mostrare un'immagine stantia.

## 8. Prossimi esperimenti, in ordine

Nessuno di questi passi è stato eseguito in questa sessione. Ognuno indica cosa serve e cosa
potrebbe rompersi. Le scritture sul Kindle (`deploy.ps1` senza `-DryRun`) richiedono il tuo ok.

### E1 — Inventario completo (sola lettura, rischio nullo)

```powershell
python kindle\make_test_images.py        # rigenera cache\testimages con la scheda e il timestamp
.\kindle\deploy.ps1 -DryRun              # controlla host/porta prima di scrivere
.\kindle\deploy.ps1 -TestImages          # copia estensione + varianti (scrive su G:\)
```

Sul Kindle: **KUAL → Dashboard → Inventario**. Poi leggi il risultato dal PC:

```powershell
Get-Content G:\dashboard\dashboard.log -Tail 40
```

Risponde alle domande aperte: `/etc/version`, presenza di `curl`/`file`/`od`/`tail`, geometria del
framebuffer da `eips -i`, `cmState`, proprietà `preventScreenSaver`, build di `fbink`. Non cambia
niente sul device.

### E2 — Formati con `eips`, senza fermare il framework

**KUAL → Dashboard → Test immagini (eips)**. Lo script pulisce lo schermo (`eips -c`), disegna ogni
variante (`eips -f -g`), registra `exit` e output e aspetta 3 s fra un file e l'altro: si fa in
tempo a guardare. Al termine rileggi il log.

Esito atteso, in base alle prove vecchie: `exit=0` per tutti e quattro. La novità è l'**output**
del comando e la verifica visiva fatta con la scheda nuova (timestamp, rampa di grigi, righe da
1 px, etichette `ALTO`/`BASSO`): se compare anche solo la scheda, il disegno funziona e il problema
era il formato; se non compare nulla, il problema è nel comando o nel possesso dello schermo.

### E3 — Immagine vera, due geometrie

Con `panel.png` già sul device: **KUAL → Dashboard → Mostra panel.png**.

Poi le varianti del PNG reale, per separare contenuto e geometria:

```powershell
python -m kindle_dashboard render -o panel.png          # 600x720, la tela del browser
python kindle\make_test_images.py --source panel.png   # varianti di quel PNG
python kindle\make_test_images.py --size 600x800       # scheda nativa
.\kindle\deploy.ps1 -TestImages
```

Se una geometria funziona e l'altra no, la conclusione è utile e va scritta qui: significa che
`eips` accetta solo la dimensione del framebuffer.

### E4 — Solo se E2/E3 non disegnano: help e versione di `eips`

Serve una shell sul device (SSH o seriale). Comandi **in sola lettura**:

```sh
eips 2>&1 | head -n 40          # uso e opzioni supportate da *questa* versione
eips -i                          # geometria del framebuffer, per intero
cat /etc/version                 # firmware Lab126
```

Confronto utile con le fonti esterne già citate nel mandato (`wiki.mobileread.com/wiki/Eips` e la
discussione sulle differenze fra versioni). **Non** installare il fbink completo né altri binari
senza approvazione: una build sbagliata su questo hardware non ha un canale di recupero comodo.

### E5 — Wi-Fi acceso/spento (richiede approvazione)

Da provare solo **dopo** che il disegno funziona, altrimenti si misura un ciclo che non mostra
niente. Comandi candidati (da verificare prima con `lipc-get-prop`):

```sh
lipc-set-prop com.lab126.cmd wirelessEnable 0
lipc-set-prop com.lab126.cmd wirelessEnable 1
lipc-get-prop com.lab126.wifid cmState          # atteso CONNECTED, con timeout massimo
```

La sessione SSH via Wi-Fi muore alla disconnessione: prima servono accesso USB o un secondo canale
di controllo. Nessuno script di questa branch spegne la radio.

### E6 — RTC, sospensione, ciclo

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
