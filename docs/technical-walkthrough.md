# Come funziona — percorso tecnico

Documento didattico: spiega **come** è fatto il progetto e **perché** ogni scelta è stata presa,
includendo le cose che non hanno funzionato. Non è una guida per l'utente (quella è `README.md`) né
la mappa tecnica sintetica (quella è `AGENTS.md`): qui i dettagli sono raccontati e motivati, con i
riferimenti al codice.

Tutto ciò che è scritto qui è stato **verificato** eseguendo il codice o provando il device; dove
qualcosa non è ancora confermato è dichiarato esplicitamente.

---

## 1. Obiettivo e vincoli

Il dispositivo: **Kindle 4** (2011), schermo e-ink 600×800 @ 167 dpi, firmware basato su
`Linux 2.6.31-rt11-lab126`, jailbroken con KUAL e KOReader. Non ha Python, non ha un browser moderno,
non ha una GPU: è un display molto lento che consuma quasi nulla quando non cambia nulla.

Il progetto nasce da un vincolo forte: **il Kindle non deve eseguire codice del progetto**. Non c'è
un interprete Python, e compilare Pillow per ARM con le dipendenze dell'epoca è impraticabile. Quindi:

```
PC (Windows, sempre accesso)                    Kindle (thin client)
raccolta dati → rendering PNG 600×720  ───────▶ browser che ricarica la pagina
servito via HTTP sulla LAN                      (nessun codice sul device)
```

Conseguenze di progetto:

- tutta la logica sta sul PC, in Python 3.11+ con **sole dipendenze `pillow` e `tzdata`**;
- il PNG è prodotto **alla risoluzione del pannello**: il device non ridimensiona, non impagina,
  non interpreta CSS oltre il minimo;
- l'aggiornamento è un `<meta http-equiv="refresh">`: una tecnologia del 1996, ma l'unica cosa che
  il browser del Kindle capisce in modo affidabile.

### Perché il browser e non il framebuffer

La strada "nativa" (disegnare i pixel direttamente sul framebuffer) è stata tentata e **scartata con
prove concrete**:

| Tentativo | Esito reale |
|---|---|
| `fbink` incluso in KOReader | `[FBInk] Image support is disabled in this FBInk build!` — è compilato MINIMAL, senza supporto immagini |
| `eips -g` (tool nativo, `/usr/sbin/eips`) | schermo bianco con PNG in **4 formati** (grigi, RGB, 1-bit, JPEG), pur con exit code 0 |
| `/etc/init.d/framework stop` per liberare lo schermo | schermo bianco, **unità USB non più esposta**, riavvio del device |

Morale tecnica: **exit code 0 non è la prova che un'immagine sia stata disegnata**, e fermare il
framework toglie anche la modalità "archivio USB" (la gestisce il framework), quindi non è nemmeno
un'uscita di sicurezza. Il browser, invece, funziona e lascia il device in uno stato normale.

---

## 2. Architettura

Flusso unidirezionale, nessun ciclo:

```
config.toml
    │
    ▼
collect() ──► PanelData ──► render_panel() ──► PNG ──► HTTP ──► browser del Kindle
    │
    ├── sources/weather.fetch_payload() → parse()
    ├── sources/calendar.fetch_payload() → parse_events()
    └── sources/trains.fetch_payload() → parse() → fetch_trip_stops()
                    │
                    └── Cache (ultimo payload buono, su disco)
```

| Modulo | Responsabilità | Cosa **non** deve fare |
|---|---|---|
| `config.py` | leggere e validare il TOML, risolvere i percorsi | chiamare la rete |
| `schedule.py` | fascia giorno/notte e intervallo di ricarica (con clamp) | leggere config, disegnare |
| `collect.py` | orchestra le tre sezioni, gestisce la cache e i `Sync` | disegnare |
| `sources/*` | `fetch_payload` (solo rete) e `parse` (solo trasformazione) | formattare per lo schermo |
| `cache.py` | persistere l'ultimo payload buono | contenere modelli |
| `model.py` | dataclass immutabili | importare Pillow |
| `render/*` | disegnare `PanelData` | fare I/O di rete |
| `server.py` | HTTP e ciclo di vita del PNG | contenere layout |
| `__main__.py` | CLI sottile (`render`, `serve`, `resolve-station`) | logica di dominio |

### Le tre invarianti che tengono in piedi tutto

1. **`fetch_payload` e `parse` sono separati** in ogni sorgente.
   Non è pedanteria: è ciò che permette di salvare il **payload grezzo** in cache e ri-analizzarlo
   con il codice nuovo quando la fonte cade. Se le due cose fossero fuse, la cache dovrebbe
   contenere modelli (fragili da serializzare) invece che la risposta originale.

2. **Ogni sezione è indipendente.** Un errore su una fonte non deve impedire il disegno delle altre.
   Il fallimento si rappresenta con `Sync(error=..., stale=...)` e finisce *scritto sul pannello*;
   non è un'eccezione che risale. Nel caso peggiore si vedono i dati vecchi con la dicitura `(cache)`.

3. **L'intervallo di aggiornamento si calcola in un solo posto** (`schedule.refresh_seconds`):
   server e renderer leggono quel risultato, non lo ricalcolano. Due implementazioni della stessa
   regola divergono sempre, e il disallineamento si scopre solo in produzione.

---

## 3. Modello dati

`model.py` contiene solo dataclass `frozen` (immutabili): una volta costruito un `PanelData`, nessuno
può mutarlo di nascosto mentre viene disegnato in un thread del server.

```python
PanelData(
    generated_at,        # quando sono stati raccolti i dati (footer: "dati HH:MM")
    timezone,
    rendered_at,         # quando è stato disegnato il PNG (l'orologio grande)
    night,               # modalità notte: al posto dell'ora compare NOTTE
    weather, weather_sync,
    events, events_sync,
    departures, departures_sync,
    location_name, board_name,
)
```

Due timestamp distinti, non uno: l'**orologio** deve essere quello del render (il PNG è ridisegnato a
ogni richiesta), mentre il **footer** deve dire quanto sono vecchi i dati. Se fossero lo stesso campo,
il primo mostrerebbe un'ora sbagliata ogni volta che i dati vengono riusati.

---

## 4. Le fonti dati (e le trappole vere)

### 4.1 Client HTTP (`sources/http.py`)

Solo standard library: `urllib.request`. Caratteristiche:

- **User-Agent identificabile** (`kindle-dashboard/0.1`). Non è cortesia formale: alcune API
  comunitarie (Transitous) rispondono **403** a richieste anonime.
- **timeout 10 s** e **un solo retry**, con attesa progressiva, e solo per errori transitori:
  un `HTTP 4xx` non migliora ritentando, quindi si interrompe subito.
- Tutti gli errori diventano `SourceError` con il nome dell'host e il codice: è il tipo che
  `collect.py` intercetta per attivare la cache.
- Decodifica con `utf-8-sig` (tollera un eventuale BOM senza rompere il parsing JSON).

### 4.2 Meteo — Open-Meteo (`sources/weather.py`)

`https://api.open-meteo.com/v1/forecast`, **nessuna API key**. Parametri usati:

```
latitude, longitude,
current=temperature_2m,weather_code,apparent_temperature,precipitation,wind_speed_10m
daily=weather_code,temperature_2m_max,temperature_2m_min
timezone=Europe/Rome, forecast_days=3,
temperature_unit=celsius, wind_speed_unit=kmh, precipitation_unit=mm
```

`parse()` costruisce `WeatherNow` (ora) e `DayForecast[]` (giorni). I codici **WMO** (0–99) sono
mappati in due direzioni: una descrizione italiana (`label`) e una **famiglia di icona**
(`icon_kind` → `sun`, `partly`, `cloud`, `rain`, `drizzle`, `snow`, `storm`, `fog`). Tenere separate
le due cose evita che il renderer conosca i codici numerici.

### 4.3 Treni — Transitous/MOTIS (`sources/trains.py`)

**Prima trappola, documentata perché è costata tempo**: ViaggiaTreno (l'API "ufficiosa" di
Trenitalia) **non è più usabile da uno script**. La richiesta
`/infomobilita/resteasy/viaggiatreno/partenze/<stazione>/<epoch>` risponde `301 → 400` e imposta i
cookie `ak_bmsc`: è **Akamai Bot Manager**, che richiede un token ottenuto eseguendo JavaScript.
Nessun `User-Agent` aiuta.

Alternativa scelta: **Transitous** (`https://api.transitous.org`), servizio comunitario basato su
MOTIS che aggrega feed GTFS/GTFS-RT europei (per l'Italia, feed Trenitalia). Nessuna chiave, JSON
pulito. Tre endpoint:

| Endpoint | Uso | Campi sfruttati |
|---|---|---|
| `/api/v1/stoptimes?stopId=<id>&n=<n>` | tabellone delle partenze | `place.scheduledDeparture`, `place.departure`, `place.track`, `place.tz`, `displayName`, `tripTo.name`, `headsign`, `cancelled`, `tripCancelled`, `realTime`, `departureTimestampReason` |
| `/api/v1/trip?tripId=<id>` | fermate intermedie di una corsa | `legs[0].intermediateStops[].name`, `.arrival` |
| `/api/v1/geocode?text=<nome>&type=STOP` | stazione → `stop_id` (comando `resolve-station`) | `name`, `id` |

Dettagli che contano:

- gli orari arrivano in **UTC** (`...Z`) e vengono convertiti nel fuso della riga (`place.tz`);
- il **ritardo** è `departure − scheduledDeparture` (il primo è l'orario stimato/effettivo);
- `departureTimestampReason` vale `OBSERVED`, `PREDICTED` o `NO_RT_DATA`: distingue il dato reale
  dalla programmazione ed è ciò che accende la dicitura *treni in tempo reale* nel footer;
- la **destinazione** mostrata è l'etichetta commerciale (`tripTo.name`, es. `ROMA TERMINI`). Sul
  campo reale si è visto che una corsa etichettata "Roma Termini" può fermarsi **prima**, a Ostiense
  o Tuscolana: per questo esiste `stop_details`, che recupera l'elenco fermate con una richiesta
  **per treno** e le filtra per parola chiave (`destinations`);
- se il dettaglio di un treno fallisce, quel treno resta nel pannello **senza** la riga delle
  fermate: degrado locale, non perdita della sezione.

### 4.4 Calendario — ICS di Google (`sources/calendar.py`)

Si usa l'**indirizzo segreto iCal** (`.../ical/<id>/private-<token>/basic.ics`): niente OAuth, niente
dipendenze, solo un file di testo con le regole RFC 5545. Il parser è scritto a mano e gestisce:

- **line folding**: le righe che iniziano con spazio/tab continuano la precedente;
- blocchi `BEGIN:VEVENT … END:VEVENT` e proprietà con parametri
  (`DTSTART;TZID=Europe/Rome:20261102T101500`);
- tre forme di data: solo data (`VALUE=DATE` → evento "tutto il giorno"), data-ora locale/TZID,
  data-ora UTC con suffisso `Z`;
- **`RRULE`**: `FREQ` DAILY/WEEKLY/MONTHLY/YEARLY con `INTERVAL`, `COUNT`, `UNTIL` e `BYDAY` per le
  ricorrenze settimanali (il caso reale: "ogni lunedì e mercoledì"), con un tetto di iterazioni;
- **`EXDATE`** (occorrenze cancellate), **`RECURRENCE-ID`** (occorrenza spostata: sostituisce
  l'originale invece di duplicarla), **`STATUS:CANCELLED`**;
- `TZID` sconosciuto → si ricade sul fuso del pannello: meglio un orario approssimato che una
  sezione vuota.

**Seconda trappola**: se in `ics_url` finisce la pagina **embed** di Google
(`/calendar/embed?src=…`, quella degli iframe) si ottiene `HTTP 401` e HTML, non un ICS. Il codice la
riconosce e scrive sul pannello *"calendario: serve l'URL iCal, non la pagina embed"*. E se il
calendario lo **sottoscrivi** e non è tuo, Google non fornisce l'indirizzo iCal: verificato con
quattro varianti di URL pubblico, tutte `404`.

### 4.5 Cache e degrado (`collect.py` + `cache.py`)

Per ogni sezione: `fetch → store(payload, istante) → parse`. Se il fetch fallisce: `load()` della
cache, `parse` del payload salvato e `Sync(stale=True, updated_at=<quando>)`. Sul pannello il titolo
della sezione mostra `· agg. HH:MM` e il footer aggiunge *alcuni dati dalla cache*.
La scrittura della cache è **atomica** (file temporaneo + `replace`) perché il server può leggere
mentre una richiesta scrive.

---

## 5. Il renderer (`render/`)

### 5.1 Tela e sistema di misura

`Image.new("L", size, "white")`: **scala di grigi 8 bit**, non "1" (bianco/nero puro). I pannelli
e-ink mostrano ~16 livelli, quindi l'antialiasing del testo resta leggibile senza dithering. Il PNG
viene poi scalato dal browser, l'unico che conosce il suo viewport: per questo il canvas è
**600×720** e non 600×800 (la barra degli indirizzi "mangia" ~70 px).

Tutte le misure derivano da un solo fattore:

```python
scale = height / 800          # _BASE_HEIGHT
style.px(44)  → round(44 * scale)
```

Cambiando la risoluzione in configurazione il layout si adatta senza toccare le costanti. Dettaglio:
`DEFAULT_SIZE = (600, 800)` in `render/panel.py` è solo il default della funzione; CLI e server
passano sempre `config.panel.width/height`.

### 5.2 Font

`fonts.load(size, bold=…)` è una funzione pura con `@functools.cache`: cerca in ordine i TTF di
sistema (Segoe UI Semibold, Verdana, Segoe UI, Arial, Tahoma), accetta un override da configurazione
(`[render] font`/`font_bold`) e **non fallisce mai**: se non trova nulla usa
`ImageFont.load_default(size)`.

Scelta controintuitiva ma voluta: anche il "regular" è **semibold**. Su e-ink un tratto di 1 px
sparisce o sfarfalla; in semibold il testo resta nero e leggibile.

### 5.3 Testo che ci sta: `fit_text` e `getlength`

`layout.fit_text(text, font, max_width)` accorcia con ellissi **misurando** il testo con
`font.getlength()`. Non è pedanteria: con larghezze fisse "a occhio" l'ora si sovrapponeva al nome del
treno nel PNG (bug reale, scoperto guardando l'immagine e non dal linter). Le colonne della tabella
treni (`_measure_columns`) sono misurate sul font reale, con un tetto percentuale per non sbilanciare
la destinazione.

### 5.4 Icone meteo vettoriali (`render/icons.py`)

Otto glifi (`sun`, `partly`, `cloud`, `drizzle`, `rain`, `snow`, `storm`, `fog`) disegnati con
primitive Pillow: cerchi pieni, ellissi, poligoni, linee con spessore proporzionale alla dimensione
(`max(3, size // 14)`). **Niente emoji**: i font di sistema non le garantiscono e su e-ink
arriverebbero a colori o come quadratini. Il glifo dipende solo dalla famiglia WMO, quindi il
renderer non conosce i codici numerici.

### 5.5 Impaginazione: un budget verticale, non un layout libero

```
margin 22 → data → orologio → condizioni meteo
──────────────── divider
METEO      3 colonne (icona + giorni)
────────────────
CALENDARIO max 3 righe          (_CALENDAR_ROW_PX = 44)
────────────────
TRENI      spazio riservato in fondo (_TRAIN_ROW_PX = 44, + _STOPS_ROW_PX = 26 con fermate)
footer     "dati HH:MM · treni in tempo reale"
```

Regola: **i treni hanno lo spazio riservato in fondo**, perché sono il dato con la scadenza più
stretta; se il calendario non ci sta si troncano le sue righe, non i treni. `render_panel` calcola
l'altezza del blocco treni *prima* di disegnare e passa un limite (`bottom`) al blocco calendario.

### 5.6 Riga delle fermate con priorità

`_stop_line(tokens, font, max_width)` riceve coppie `(testo, è_prioritaria)`: finché la riga non ci
sta si rimuove **l'ultima fermata non prioritaria**, mai quelle elencate in `stop_priority`. Sui dati
veri il risultato è:

```
Aurelia 22:17 · S.Pietro 22:24 · Trastevere 22:29 · Ostiense 22:36     (Tuscolana scartata)
```

`_stop_label` toglie il prefisso città (`ROMA S.PIETRO` → `S.Pietro`), che è già nel titolo della
sezione.

### 5.7 Modalità notte nel renderer

`_clock_label(data)` restituisce `NOTTE` se `data.night`, altrimenti `HH:MM`. Tutto il resto del
layout resta identico: nessun rimescolamento tra giorno e notte, quindi l'occhio ritrova subito le
stesse posizioni.

---

## 6. Il server (`server.py`)

- **`ThreadingHTTPServer` con `allow_reuse_address = False`.** Su Windows il default (`True`) consente
  a una seconda istanza di **rubare la porta** a quella già in ascolto: il processo nuovo parte, la
  versione vecchia continua a servire e sembra che le modifiche non abbiano effetto (bug reale,
  costato un paio di "riavvii" fantasma). Ora una seconda istanza fallisce con `WinError 10048` e la
  CLI stampa *"porta 8787 non disponibile: chiudi l'istanza già in ascolto"*.
- **Endpoint**: `/panel.png`, `/panel.html` (equivalente a `/`), `/health`; tutto il resto 404.
- **`PanelService`**: un `Lock` protegge raccolta + rendering; l'immagine viene serializzata in un
  `BytesIO` con `PNG, optimize=True`.
- **Nessun TTL sui dati**, solo una **guardia anti-doppione di 5 s**: se telefono e Kindle chiedono il
  PNG nello stesso istante si raccoglie una volta sola. Un TTL "vero" (es. 300 s) creerebbe il
  disallineamento classico: pagina ricaricata a 88 s → dati ancora in cache, ricaricata a 178 s →
  freschi; aggiornamento reale ogni 180 s e irregolare.
- **HTML** (`html_panel`): `meta refresh` con l'intervallo da `schedule`, `viewport`,
  `img { max-width:100%; max-height:100vh }` e il **cache-buster** `/panel.png?t=<epoch>`. Quest'ultimo
  sembra un dettaglio e non lo è: i browser mobili ignorano `Cache-Control: no-store` su un `<img>`
  con URL fisso e continuano a mostrare la versione vecchia.
- **Robustezza**: un'eccezione durante il rendering produce un `500` con testo breve; il server resta
  in piedi.

---

## 7. Giorno e notte (`schedule.py`)

```python
Schedule(night_start=23:00, night_end=06:30, day_seconds=90, night_seconds=3600)
```

Tre funzioni pure:

- `is_night(moment, schedule)` → gestisce la finestra che **scavalca la mezzanotte** (23:00 → 06:30);
- `next_boundary(moment, schedule)` → primo istante futuro di cambio fascia (oggi o domani);
- `refresh_seconds(moment, schedule)` → intervallo della fascia corrente **tagliato al confine**:

```
intervallo = max(1, min(intervallo_della_fascia, secondi_al_confine))
```

Il clamp non è un vezzo: senza di esso chi ricarica alle **06:29** (ancora notte) riceverebbe un
intervallo di un'ora e resterebbe in modalità notte fino alle **07:29**. Con il clamp:

| Ora | Fascia | Intervallo |
|---|---|---|
| 12:00 | giorno | 90 s |
| 22:59 | giorno | **60 s** (al confine) |
| 23:00 | notte | 3600 s |
| 06:29 | notte | **60 s** |
| 06:29:50 | notte | **10 s** |
| 06:30 | giorno | 90 s |

Effetto collaterale utile: la data a mezzanotte non resta indietro, perché il primo refresh notturno
cade esattamente sul confine delle 23:00 e poi ogni ora.

Configurazione collegata (una sola fonte di verità):

```toml
[panel]
refresh_seconds = 90            # pagina + dati
[schedule]
night_start = "23:00"
night_end = "06:30"
night_refresh_seconds = 3600
```

`night_start == night_end` è rifiutato con `ConfigError` (sarebbe ambiguo) e il formato è validato
come `HH:MM`.

---

## 8. Il lato device

### 8.1 Che cosa è stato provato (cronologia delle verità)

1. **`fbink` di KOReader** → `[FBInk] Image support is disabled in this FBInk build!`. È la build
   MINIMAL: KOReader non ha bisogno delle immagini, quindi la sua copia non sa disegnare PNG.
2. **`eips`** (il tool nativo): esiste, ma in **`/usr/sbin/eips`**, non in `/usr/bin`. Con quattro
   formati di immagine (grigi, RGB, 1-bit, JPEG) lo schermo **resta bianco** e l'exit code è **0**.
3. **Fermare il framework** per liberare il framebuffer (`/etc/init.d/framework stop`): schermo bianco,
   **unità USB non più esposta** (è il framework a gestire la modalità archivio), riavvio del device.
4. **Browser + pagina HTML**: funziona, e il device resta in uno stato normale.

Da qui la decisione: il device è un **thin client HTTP**, l'estensione KUAL diventa **diagnostica**.

### 8.2 Estensione KUAL (`kindle/extensions/dashboard/`)

- `config.xml`: oltre a `<information>` (nome, versione, autore, id) deve contenere

  ```xml
  <menus><menu type="json" dynamic="true">menu.json</menu></menus>
  ```

  **Senza questo blocco KUAL non elenca l'estensione**, senza errori né voci grigie: la differenza
  rispetto all'estensione di KOReader (che funziona) era tutta lì.
- `menu.json`: voci con `action` assoluto (`/mnt/us/extensions/dashboard/dashboard.sh`) e `params`.
  Voci attuali: *Verifica server*, *Diagnostica*, *Tieni schermo acceso*, *Riattiva salvascherino*.
- `dashboard.sh` (generato da `deploy.ps1` da un template): **non disegna niente**. Risolve i binari
  con `command -v` (il `PATH` di KUAL è ridotto), scrive tutto in `/mnt/us/dashboard/dashboard.log`,
  verifica la raggiungibilità del PC con `wget` e comanda `preventScreenSaver` via `lipc-set-prop`.
- `deploy.ps1`: trova da solo l'unità del Kindle (quella con `documents\` e `system\`), legge la porta
  da `config.toml` **tramite il pacchetto Python** (una sola fonte di verità) e scrive lo script in
  **UTF-8 senza BOM con line ending LF** — `sh` non tollera `\r`.

### 8.3 Rete e firewall (la parte che fa perdere più tempo)

- Il Kindle 4 ha **solo Wi-Fi 2.4 GHz**; il PC può stare anche sul 5 GHz dello stesso router (verificato:
  le due bande sono sulla stessa LAN).
- Windows classifica spesso la rete domestica come **Public**: una regola firewall `-Profile Private`
  **non si applica**. `kindle\allow-lan.ps1` fa le due cose insieme (rete → Private, regola TCP
  mirata) e si rifiuta di partire senza privilegi di amministratore, stampando il comando esatto per
  elevarli.
- Le regole larghe preesistenti (`python.exe` su profilo `Public`) aprivano *qualsiasi* porta di
  Python: sono state disabilitate, lasciando la regola `kindle-dashboard 8787`.
- I cmdlet PowerShell **non esistono in `cmd.exe`**: per questo le operazioni di setup sono script
  (`.ps1`) e non righe da incollare, che si incollano anche attaccate quando si perdono gli a capo.

---

## 9. Test: come sono isolati

Strategia: **nessun test tocca la rete, il filesystem utente o il device**. Tre strumenti:

- `monkeypatch.setattr(sources.weather, "fetch_payload", ...)` per iniettare payload registrati;
- `tmp_path` di pytest per cache e file di configurazione;
- `FakeService` + `build_server(..., port=0)` per provare l'HTTP su una porta effimera reale.

I payload veri stanno in `tests/fixtures/` (`weather_openmeteo.json`, `transitous_stoptimes.json`,
`transitous_trip.json`, `transitous_geocode.json`, `calendar.ics`); `conftest.py` espone `read_fixture`,
`load_json`, `rome`.

| File | Test | Cosa copre |
|---|---|---|
| `test_schedule.py` | 17 | confini 22:59/23:00 e 06:29/06:30, mezzanotte, clamp, intervalli |
| `test_weather.py` | 13 | parsing Open-Meteo, campi mancanti, codici WMO |
| `test_trains.py` | 10 | partenze passate, ritardo, binario, cancellazioni, filtro, fermate da `/trip` |
| `test_render.py` | 10 | dimensioni/mode, determinismo, sezioni vuote, troncamenti, priorità fermate, `NOTTE` |
| `test_config.py` | 9 | valori, errori parlanti, override da ambiente, `stop_details`, `[schedule]` |
| `test_calendar.py` | 6 | `BYDAY`/`COUNT`, `EXDATE`, override `RECURRENCE-ID`, annullato, `TZID` sconosciuto, URL embed |
| `test_server.py` | 5 | `/health`, `/panel.png`, `/panel.html`, 404, porta non rubabile, guardia anti-doppione |
| `test_collect.py` | 2 | sezioni non configurate, fallback su cache con `stale=True` |

Totale **72**, con `python -m pytest -q`.

---

## 10. I bug reali (sintomo → causa → correzione)

| Sintomo | Causa | Correzione |
|---|---|---|
| `ZoneInfoNotFoundError: 'Europe/Rome'` | Windows non ha il database IANA | dipendenza `tzdata` |
| I test non importano il package | pytest non aggiunge la root al `sys.path` | `pythonpath = ["."]` |
| L'ora si sovrappone al nome del treno | colonne a pixel fissi | larghezze da `getlength` |
| `Image support is disabled in this FBInk build` | build MINIMAL di KOReader | `eips`, poi il browser |
| `eips` esce con 0 e lo schermo resta bianco | il firmware non rende i PNG | passaggio al browser |
| Schermo bianco + USB sparita + riavvio | framework fermato = niente modalità archivio | non fermare il framework |
| "Dashboard" invisibile in KUAL | `config.xml` senza `<menus>` | blocco `<menus>` |
| "già in esecuzione" e nulla parte | `dashboard.pid` orfano | liveness con `kill -0` |
| Le modifiche "non hanno effetto" | una seconda istanza rubava la porta | `allow_reuse_address = False` |
| Il telefono mostra il pannello vecchio | `<img>` con URL fisso | cache-buster `?t=<epoch>` |
| Il deploy "riuscito" non copiava nulla | `Select-Object -First N` ha ucciso lo script | non filtrare l'output |
| Accenti corrotti negli script del Kindle | `Get-Content -Raw` legge UTF-8 come ANSI | `ReadAllText(..., UTF8)` + LF |

---

## 11. Comandi

| Scopo | Comando |
|---|---|
| installare | `python -m pip install -e .` |
| stile | `python -m ruff check .` |
| test | `python -m pytest -q` |
| anteprima giorno | `python -m kindle_dashboard render -o preview.png` |
| anteprima notte | `python -m kindle_dashboard render --night -o preview-night.png` |
| server | `python -m kindle_dashboard serve` |
| trovare uno `stop_id` | `python -m kindle_dashboard resolve-station "Santa Marinella"` |
| deploy estensione | `.\kindle\deploy.ps1 [-DryRun] [-TestImages]` |
| rete + firewall (admin) | `powershell -ExecutionPolicy Bypass -File .\kindle\allow-lan.ps1 [-AnyProfile]` |

---

## 12. Mappa dei file

```
kindle_dashboard/
  config.py            TOML → dataclass immutabili, validazione, ICS da ambiente
  schedule.py          giorno/notte e intervallo (clamp al confine)
  model.py             dataclass frozen condivise
  collect.py           orchestrazione, cache, Sync
  cache.py             ultimo payload buono su disco (scrittura atomica)
  server.py            HTTP, PanelService, html_panel
  __main__.py          CLI: render / serve / resolve-station
  sources/http.py      urllib con UA, timeout, retry mirato
  sources/weather.py   Open-Meteo: fetch + parse + codici WMO
  sources/trains.py    Transitous: stoptimes, trip, geocode
  sources/calendar.py  parser ICS (folding, RRULE, EXDATE, RECURRENCE-ID)
  render/fonts.py      ricerca TTF con fallback
  render/icons.py      glifi meteo vettoriali
  render/layout.py     fit_text, divider, etichette di data
  render/panel.py      composizione del pannello
kindle/                estensione KUAL + deploy.ps1 + allow-lan.ps1
tests/                 pytest con fixture registrate
docs/                  questo documento
```

---

## 13. Come studiarlo (percorso suggerito)

1. **`schedule.py`** (~50 righe): è il pezzo più piccolo e contiene una regola non banale (clamp al
   confine). Leggilo con `tests/test_schedule.py`: il test **è** la specifica.
2. **`sources/trains.py`**: mostra la separazione `fetch_payload`/`parse` e il degrado per singolo
   treno. Cambia il filtro destinazioni e guarda come cambia `preview.png`.
3. **`render/panel.py`**: il tema è "misurare invece di stimare" (`getlength`, budget verticale).
   Ogni modifica va guardata sull'immagine, non solo verificata dai test.
4. **`server.py` + `html_panel`**: ciclo di vita della richiesta, cache-buster, perché non c'è un TTL.
5. **`collect.py`**: politica di fallback; poi `tests/test_collect.py` per vedere come si simula un guasto.

Esercizi per fissare i concetti:

- aggiungere `[calendar] refresh_seconds` separato, per scaricare l'ICS meno spesso (e misurare i byte);
- aggiungere un TTL "imminente" per le API quando un treno parte entro 10 minuti;
- provare `panel.height` a 700/740 e misurare con uno script il margine libero sotto il footer;
- scrivere una nuova fonte (rifiuti, maree…) seguendo la checklist in `AGENTS.md`.






