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
    ├── sources/marine.fetch_payload() → parse()
    ├── sources/calendar.fetch_payload() → parse_events()
    ├── sources/waste.fetch_payload() → parse()
    └── sources/trains.fetch_payload() → parse() → fetch_trip_stops()
                    │
                    └── Cache (ultimo payload buono, su disco)
```

| Modulo | Responsabilità | Cosa **non** deve fare |
|---|---|---|
| `config.py` | leggere e validare il TOML, risolvere i percorsi | chiamare la rete |
| `schedule.py` | fascia giorno/notte e intervallo di ricarica (con clamp) | leggere config, disegnare |
| `collect.py` | orchestra le cinque sezioni (meteo, mare, calendario, differenziata, treni), gestisce la cache e i `Sync` | disegnare |
| `sources/*` | `fetch_payload` (solo rete) e `parse` (solo trasformazione) | formattare per lo schermo |
| `cache.py` | persistere l'ultimo payload buono | contenere modelli |
| `model.py` | dataclass immutabili | importare Pillow |
| `render/*` | disegnare `PanelData` | fare I/O di rete |
| `server.py` | HTTP e ciclo di vita del PNG | contenere layout |
| `__main__.py` | CLI sottile (`render`, `serve`, `resolve-station`) | logica di dominio |

### Le invarianti che tengono in piedi tutto

L'elenco completo è in `AGENTS.md` (dieci voci, comprese le regole di misura e di cedimento del
renderer). Qui le tre che, se saltano, si vedono subito nel PNG.

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
    sea, sea_sync,        # None = mare spento o senza dati: nessun blocco disegnato
    events, events_sync,
    waste, waste_sync,   # None = colonna differenziata spenta, () = configurata ma vuota
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
current=temperature_2m,weather_code,apparent_temperature,precipitation,
        relative_humidity_2m,wind_speed_10m,wind_direction_10m
daily=weather_code,temperature_2m_max,temperature_2m_min,
      wind_speed_10m_max,wind_direction_10m_dominant,sunrise,sunset
hourly=precipitation_probability
timezone=Europe/Rome, forecast_days=3,
temperature_unit=celsius, wind_speed_unit=kn, precipitation_unit=mm
```

Il vento è in **nodi** (`wind_speed_unit=kn`) perché il pannello è nautico: l'unità si chiede
all'API, non si converte nel renderer, altrimenti header e striscia potrebbero divergere.

La **probabilità di pioggia** non è un campo "corrente": è il massimo di `precipitation_probability`
nelle **prossime sei ore** (`_RAIN_WINDOW_HOURS`), trovando l'ora corrente nel prefisso ISO
`YYYY-MM-DDTHH` delle serie orarie (le serie arrivano già nel fuso richiesto, quindi non serve
interpretare date). Guardare la giornata intera farebbe leggere un temporale serale come "piove
adesso".

`parse()` costruisce `WeatherNow` (ora) e `DayForecast[]` (giorni). I codici **WMO** (0–99) sono
mappati in due direzioni: una descrizione italiana (`label`) e una **famiglia di icona**
(`icon_kind` → `sun`, `partly`, `cloud`, `rain`, `drizzle`, `snow`, `storm`, `fog`). Tenere separate
le due cose evita che il renderer conosca i codici numerici.

I campi aggiunti dopo (`wind_direction_10m`, `wind_speed_10m_max`, `sunrise`/`sunset`,
`relative_humidity_2m`, la probabilità di pioggia) si leggono con gli helper di
`sources/values.py`: un payload in cache scritto prima esiste ancora e deve restare ri-analizzabile,
altrimenti il fallback smetterebbe di funzionare proprio quando serve. È anche il motivo per cui il
pannello sa disegnare una riga di dettagli con due pezzi invece di tre.

### 4.3 Mare — Open-Meteo Marine (`sources/marine.py`)

`https://marine-api.open-meteo.com/v1/marine`, **nessuna API key**, stesse coordinate di
`[location]` (una sezione `[sea]` con coordinate proprie sarebbe una seconda verità da tenere
allineata). Il punto richiesto viene agganciato alla griglia del modello d'onda: per Santa Marinella
(42.0342/11.8542) la risposta arriva da 42.0417/11.8750, circa 1.8 km al largo.

```
current=wave_height,sea_surface_temperature
daily=wave_height_max
timezone=Europe/Rome, forecast_days=3
```

`parse()` produce `SeaNow` + `SeaDay[]`. Lo **stato del mare** è la scala Douglas, in una tabella
sola con tre letture: `state_force` (il grado, `F3` nella striscia), `state_label` (la parola,
`mosso`, usata nell'header dove lo spazio c'è) e `state_kind` (la famiglia di glifo: `sea_calm`,
`sea_slight`, `sea_moderate`, `sea_rough`). Le soglie sono in metri di altezza d'onda significativa
(0.1 / 0.5 / 1.25 / 2.5 / 4 / 6 / 9) e si confrontano con l'altezza **arrotondata al decimale
mostrato**: senza quel `round`, `0.48 m` verrebbe scritto `0.5m` e classificato "quasi calmo",
mentre `0.50 m` è "poco mosso" — due stati diversi dietro lo stesso numero.

Perché due grafie: nella colonna da 185 px `F3` costa 15 px contro i 75 di `poco mosso`, ed è
l'unico modo per tenere insieme altezza d'onda, vento e direzione. Sulla riga grande dell'header,
dove lo spazio abbonda, la parola si legge di sfuggita meglio di un numero.

Due dettagli che sembrano cavilli e non lo sono:

- **accoppiamento per data, non per indice**: la striscia delle previsioni prende il mare da
  `{day: SeaDay}`; se un giorno manca, le colonne non si spostano;
- **la sezione spenta non produce errore** (`Sync()` vuoto), così il renderer distingue "non
  configurata" da "configurata ma caduta" e scrive `mare n.d.` solo nel secondo caso.

### 4.4 Treni — Transitous/MOTIS (`sources/trains.py`)

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

### 4.5 Calendario — ICS di Google (`sources/calendar.py`)

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

### 4.6 Raccolta differenziata (`sources/waste.py`)

Il calendario del comune è un ICS **pubblico** (`.../ical/<id>/public/basic.ics`) con una forma
diversa da quella degli eventi: un `VEVENT` all-day per ogni giorno di raccolta, il materiale nel
titolo (`Umido`, `Secco`, `Plastica`, `Carta`), nessuna `RRULE`. Non serve un secondo parser:
`waste.fetch_payload` riusa `calendar.fetch_payload` (stessa validazione "è davvero un iCal") e
`waste.parse` chiama `calendar.parse_events` su una finestra che parte dalla mezzanotte di oggi.

L'unica logica propria è l'**allineamento della finestra**: il risultato ha esattamente `days`
elementi, uno per giorno, con `kinds` vuoto quando quel giorno non si raccoglie nulla. Così il
renderer non deve calcolare buchi e la domenica — che nel calendario reale è sempre scoperta —
compare come `niente` invece di sparire. Il `limit` passato a `parse_events` è `days * 4` perché il
suo tetto conta le occorrenze, non i giorni, e un giorno può avere più materiali.

### 4.7 Cache e degrado (`collect.py` + `cache.py`)

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
sistema, accetta un override da configurazione (`[render] font`/`font_bold`) e **non fallisce mai**.

La ricerca è **multipiattaforma**: `%WINDIR%\Fonts` su Windows, `/System/Library/Fonts` e
`/Library/Fonts` su macOS, `/usr/share/fonts/truetype/{dejavu,liberation,noto}` (più
`/usr/share/fonts/TTF` e `/usr/local/share/fonts`) su Linux. Il primo nome di entrambe le liste è
**Liberation Sans**, cioè il font che il `Dockerfile` installa nel container; dopo vengono i Segoe UI
di Windows, Verdana, Arial, Tahoma e infine DejaVu e Noto come riserva di copertura. Il criterio non è
«il font più bello» né «il primo che il sistema offre»: è **lo stesso font del device**, perché è
quello che il renderer misura. L'ordine dei nomi conta più di quello delle cartelle: `load()` scorre
`name` esterno e `directory` interno, perché iterando prima le cartelle vinceva `dejavu/` (che su
Debian precede `liberation/`) e la lista dei nomi diventava decorativa.

**Il bug che ha imposto questa ricerca**: guardando solo la cartella di Windows, il container
ricadeva su `ImageFont.load_default(size)`, il font incorporato di Pillow, che non ha le accentate
né il segno di moltiplicazione: sul pannello si leggevano `Mamma e pap□a` e `Visita casa □mamma`.
Ora `missing_glyphs()` confronta il bounding box di ogni carattere con quello di un codepoint
inesistente (U+E000, che Pillow disegna sempre identico) e `load()` preferisce il primo candidato che
copre `REQUIRED_GLYPHS` (`°·…×àèéìòù`). `tests/test_fonts.py` impedisce il ritorno del difetto.

**Il secondo bug, meno visibile e più insidioso**: la copertura dei glifi non basta. Le colonne si
dimensionano con `font.getlength`, quindi un font più largo di quello vero non «ruba» pixel: supera il
budget e il testo diventa ellissi. Con `fonts-dejavu-core` il PNG del container mostrava
`04:37 REG 12…`, `SAB 18°/…`, `Ale incontro y…` e `poco mosso` senza altezza d'onda, mentre
l'anteprima sullo stesso `PanelData` era integra: DejaVu Sans Bold è ~1,30x il Segoe UI Semibold (il
regular ~1,17x). Misurando i candidati Debian sullo stesso testo:

| Font | larghezza vs Segoe UI Semibold (regular / bold) | inchiostro a 22 px |
|---|---|---|
| `fonts-liberation` | 1,05x / 1,15x | 6,9% / 9,2% |
| `fonts-open-sans` | 1,07x / 1,13x | 7,9% / 9,7% |
| `fonts-dejavu-core` | 1,17x / 1,30x | 6,9% / 9,5% |
| DejaVu Sans **Condensed** (`fonts-dejavu-extra`) | 1,05x / 1,16x | 6,6% / — |

Liberation Sans vince perché è la più stretta e mantiene il peso del tratto (6,9% di inchiostro, come
DejaVu: nessuna regressione di leggibilità rispetto a prima). Il `Dockerfile` installa
`fonts-liberation` e `fonts-dejavu-core` come riserve di sistema.

**Il terzo bug è quello che ha cambiato la diagnosi**: il PNG del container tornava sovrapponibile
all'anteprima solo finché il PC usava lo stesso font, e non lo faceva. Con Liberation in fondo alla
lista dei nomi, l'host di sviluppo sceglieva il Segoe UI Semibold, più stretto di ~1,09-1,15x: lo
stesso `REG 12519` misura 89 px in Segoe e 102 px in Liberation, `SAB 18°/12°` 99 px contro 111,
`poco mosso 0.8m` 151 px contro 164 (numeri misurati a 19 px, uguali su Windows e nel container, che è
il punto). L'anteprima era quindi **ottimistica**: mostrava righe integre dove il Kindle avrebbe
troncato, e ogni volta che una riga stava «appena al bordo» la sorpresa arrivava sul device. La
correzione non è allargare le colonne: è far **misurare al PC lo stesso file** del device. Da qui la
decisione di **spedire il font con il pannello**: `kindle_dashboard/render/fonts/` contiene
`LiberationSans-Regular.ttf`, `LiberationSans-Bold.ttf` e `OFL.txt` (SIL OFL 1.1, obbligatoria accanto
ai binari), `shipped_font()` è la prima scelta di `load()`, `[tool.setuptools.package-data]` la porta
nel pacchetto e `*.ttf binary` in `.gitattributes` evita che git normalizzi un binario. I due file
sono quelli di Debian `fonts-liberation`, cioè esattamente ciò che il device disegnava già: il Kindle
non cambia, il PC si allinea. Segue una regola utile anche fuori da questo progetto: «vicino» lo
decide la misura, non l'occhio. `tests/test_fonts.py` tiene fermi l'esistenza del file, la licenza
accanto, il fatto che `load()` usi quello e l'ordine dei ripieghi; la diagnosi è una riga:
`python -c "from kindle_dashboard.render import fonts; print(fonts.load(19).path)"` deve stampare un
percorso dentro il repo, non `C:\WINDOWS\Fonts\…`. Aggiornare il font (o cambiarlo con uno più largo)
significa rifare **tutte** le misure: si rigenera `preview.png` e si guarda, non si torna a tarare a
occhio.

Restano due troncamenti che sono **del layout**, non del font: gli eventi oltre ~26 caratteri nella
colonna da 60% e le fermate che eccedono la riga dei treni. Quelli vanno affrontati con le regole di
cedimento, non cambiando font.

Attenzione alle conseguenze sui layout: con un font diverso cambiano **tutte** le misure, quindi le
regole di cedimento (icona del titolo, riga dei dettagli, colonne dei treni) vanno tenute: sono l'unico
modo perché il pannello resti leggibile anche quando il font non è quello su cui è tarato.

Scelta da conoscere: nei **ripieghi Windows** anche il "regular" è il semibold (`seguisb.ttf`), perché
su e-ink un tratto di 1 px sparisce o sfarfalla. Il font primario è invece `LiberationSans-Regular`,
che ha il 6,9% di inchiostro misurato: più sottile del semibold ma non al punto da scomparire, ed è
ciò che il device mostra. Se una sera il testo piccolo sul Kindle sembrasse troppo chiaro, il
discorso è di peso del font, non di layout.

### 5.3 Testo che ci sta: `fit_text` e `getlength`

`layout.fit_text(text, font, max_width)` accorcia con ellissi **misurando** il testo con
`font.getlength()`. Non è pedanteria: con larghezze fisse "a occhio" l'ora si sovrapponeva al nome del
treno nel PNG (bug reale, scoperto guardando l'immagine e non dal linter). Le colonne della tabella
treni (`_measure_columns`) sono misurate sul font reale, con un tetto percentuale per non sbilanciare
la destinazione.

`layout.wrap_text(text, font, max_width, lines=2)` è il passo successivo: spezza il testo su uno
spazio (mai dentro una parola) e lascia l'ellissi all'ultima riga, così il numero di righe è noto
**prima** di disegnare e la riga può essere alta il giusto. L'agenda lo usa per il riassunto degli
eventi: 227 px di colonna su una riga non bastano per `Visita casa ×mamma e papà`, ma su due righe
sì. Il dettaglio che rende la cosa sicura è l'ordine dei passi in `_draw_events`: prima si contano gli
eventi che ci starebbero su una riga sola (`room // row`), si riserva una riga a ciascuno e solo lo
spazio **avanzato** diventa una seconda riga; se non basta si torna a `lines=1` con l'ellissi.
Senza questa prenotazione un evento lungo si sarebbe preso la riga del successivo: sull'e-ink, dove
il pannello si guarda di sfuggita, un evento che sparisce è peggio di una parola tagliata.

`render/layout.py` ospita anche le etichette della rosa dei venti: `compass()` scrive la direzione a
16 settori (`NNE`) e `wind_name()` il nome tradizionale (`Tramontana-Grecale`) dallo **stesso
indice**, così sigla e nome non possono divergere. Gli intermedi seguono le lettere della sigla — la
prima dà il primo nome, il resto il secondo (`OSO` = Ponente-Libeccio, `NNO` =
Tramontana-Maestrale) — e si legge subito a quale cardinale il nome è legato.

### 5.4 Icone vettoriali (`render/icons.py`)

I glifi sono disegnati con primitive Pillow: cerchi pieni, ellissi, poligoni, linee con spessore
proporzionale alla dimensione (`max(3, size // 14)`). **Niente emoji**: i font di sistema non le
garantiscono e su e-ink arriverebbero a colori o come quadratini.

- **meteo**: otto famiglie WMO (`sun`, `partly`, `cloud`, `drizzle`, `rain`, `snow`, `storm`, `fog`);
  il glifo dipende solo dalla famiglia, quindi il renderer non conosce i codici numerici;
- **mare**: quattro livelli di agitazione (`sea_calm`, `sea_slight`, `sea_moderate`, `sea_rough`),
  presi dalla stessa tabella Douglas che produce forza e parola;
- **righe di dettaglio**: `person`, `humidity`, `umbrella`, `wind`, `sunrise`, `sunset`,
  `arrow_up`/`arrow_down`;
- **titoli di sezione**: `calendar`, `waste`, `train`.

Regola comune: dove il glifo è piccolo si disegna **pieno**, senza contorno. A 20 px un tratto da
3 px mangia la forma: è la ragione per cui la persona è un busto stilizzato, l'umidità è una goccia
fatta di un triangolo sovrapposto a un cerchio e il treno è un frontale con due ruote.

**Secondo tono.** Gli elementi che stanno *dietro* sono in `_PALE` (`#8c8c8c`, metà scala
dell'immagine in grigi) e quelli davanti in nero: il sole raggiato di `partly`, la **calotta di sole
senza raggi** che in `cloud`/`rain`/`drizzle`/`snow` esce da dietro la nuvola (`_cloud_with_sun`), il
lampo di `storm`, le righe di `fog`. È l'alternativa ai contorni, che a 20 px mangerebbero il disegno;
il resto resta nero pieno, perché un grigio debole su e-ink si sbiadisce.

Il secondo tono colora **il pezzo che nella sagoma originale sta dietro**, non aggiunge un elemento:
la prima versione metteva un sole raggiato in più e si leggevano due soli nello stesso glifo. In
`_cloud_with_sun` la geometria è quella di sempre (due cerchi e una base) e cambia solo il
riempimento del cerchio alto a destra, che è il sole coperto.

I glifi di sezione (`calendar`, `waste`, `train`) seguono la geometria di **Bootstrap Icons** (MIT)
tradotta in primitive: calendario con anelli e riga bianca dell'intestazione, bidone con tre stecche
bianche, treno con finestrino e feritoia. Le librerie di icone si guardano per le proporzioni, non si
importano: il progetto resta senza asset esterni.

### 5.5 Impaginazione: un budget verticale, non un layout libero

```
margin 22 → data (sx) · luogo (dx)
          → orologio (sx) · icona meteo + temperatura (dx)            _CLOCK_BAND_PX = 94
          → riga dettagli: umidità · pioggia · percepita (dx)
          → alba/tramonto · vento (sx) │ descrizione · mare (dx)      _STATUS_ROW_PX = 26
──────────────── divider (_section_rule: nessun titolo "METEO")
          3 colonne: icona + giorno/temperature + riga del mare       _FORECAST_ROW_SEA_PX = 58
────────────────
CALENDARIO │ DIFFERENZIATA    due colonne quando `[waste]` è configurata, icona nel titolo
           │                  (_CALENDAR_ROW_PX = 44, _EVENTS_SHARE = 0.60,
           │                   gutter _COLUMN_GUTTER_PX = 16) e il divisore scende fino alla regola
────────────────  dei treni
TRENI      ancorato al fondo: `footer_top - _trains_height`, icona nel titolo
           (_TRAIN_ROW_PX = 44, + _STOPS_ROW_PX = 26 con fermate)
footer     "dati HH:MM · treni in tempo reale"
```

Regola: **i treni sono ancorati al fondo**, perché sono il dato con la scadenza più stretta. L'altezza
del blocco viene da `_trains_height` (titolo, una riga per partenza, la riga delle fermate dove ci
sono, oppure la riga del messaggio quando l'elenco è vuoto) e `render_panel` passa
`footer_top - altezza` sia a `_draw_trains` sia come limite `bottom` dell'agenda: se il calendario non
ci sta si troncano le sue righe, non i treni. Prima il blocco partiva dalla `y` restituita
dall'agenda e lasciava ~70 px di bianco sopra il footer; con l'agenda vuota restava addirittura a metà
pagina.

I titoli delle sezioni hanno un'icona (`calendar`, `waste`, `train`) allineata al centro
dell'inchiostro del titolo. `_title_icon` decide se c'è spazio: se il titolo con `· agg. HH:MM` non ci
sta, l'icona **non viene disegnata** e il testo resta intero — nella colonna della differenziata
(216 px con `_EVENTS_SHARE = 0.60`) a 600×720 l'icona entra nel caso normale e cede quando c'è
`· agg.`, a 600×800 quel suffisso si tronca.

Si ingrandiscono **le intestazioni, non il contenuto**: `title_font` 19 e `_TITLE_ROW_PX` 56 per le
righe di titolo, mentre eventi e differenziata restano su `body_font`/`text_font` e righe da 44 px.
La prima versione gonfiava anche il contenuto e i riepiloghi degli eventi si troncavano troppo: la
colonna eventi è preziosa e la sua larghezza non va spesa per i titoli. Il divisore verticale fra le
due colonne arriva fino alla regola orizzontale dei treni (`bottom + _RULE_TOP_PX`): chiude il blocco
e non lascia una linea che si ferma a metà.

Il blocco agenda (`_draw_agenda`) disegna **due colonne solo se `PanelData.waste` non è `None`**:
la colonna eventi prende il 60% di `content_width - gutter`, la differenziata il resto, e il
divisore verticale è alto quanto il contenuto. Con `[waste]` spenta il calendario resta a tutta
larghezza come prima, quindi non esistono due layout da mantenere.

### 5.6 Righe miste testo+icona (`_draw_inline`)

Ogni riga fatta di testo e glifi è una sequenza di `_Segment`: o un `text`, o un `icon`, più un
`required` che dice se il pezzo può cadere. `_draw_inline` misura i pezzi con `font.getlength` e
allinea le icone al **centro dell'inchiostro** del testo (`_icon_top`), non al bordo del riquadro del
font: sopra le maiuscole c'è "cielo" tipografico (8 px su un font da 20) e un glifo appoggiato al
riquadro sembra sollevato rispetto alle lettere.

`_fit_inline` è la politica di cedimento generica: toglie i pezzi non obbligatori **dal fondo**, poi
accorcia l'ultimo testo con l'ellissi. Per le due colonne dell'intestazione c'è
`_draw_balanced_row`: misura prima il blocco destro (è allineato al bordo) e dà al sinistro lo spazio
che resta. È ciò che permette a `Tramontana-Maestrale` di convivere con la riga del mare senza che
uno dei due sparisca.

### 5.7 La riga dei dettagli del meteo

Sotto la temperatura grande, allineati a destra, ci sono **umidità, pioggia e percepita** in
quest'ordine, con `detail_font` (20 px bold) e icone da 20 px. A 16 px — la misura di footer, fermate
e striscia mare — la riga si leggeva male e sul PNG l'ombrello sembrava una freccia.

Il cedimento è deciso in `_draw_now_details`, **a coppie intere** e in ordine di importanza:

1. riga piena, se sta fra orologio e bordo;
2. via la **percepita**: la temperatura reale è già scritta grande sopra;
3. via la **pioggia**: resta l'umidità come ancora della riga.

Non si lascia decidere ai singoli `required`, che toglierebbero solo il numero lasciando l'icona
orfana. E l'umidità è un campo opzionale, così una cache scritta prima del campo si disegna lo stesso
con due pezzi invece di tre.

### 5.8 Riga delle fermate con priorità

`_stop_line(tokens, font, max_width)` riceve coppie `(testo, è_prioritaria)`: finché la riga non ci
sta si rimuove **l'ultima fermata non prioritaria**, mai quelle elencate in `stop_priority`. Sui dati
veri il risultato è:

```
Aurelia 22:17 · S.Pietro 22:24 · Trastevere 22:29 · Ostiense 22:36     (Tuscolana scartata)
```

`_stop_label` toglie il prefisso città (`ROMA S.PIETRO` → `S.Pietro`), che è già nel titolo della
sezione.

### 5.9 Modalità notte nel renderer

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

Le tre chiavi di `[schedule]` sono l'esempio concreto di un errore silenzioso: messe in `[server]`
(capitava, perché anche `host` e `port` sono lì) il TOML le accettava, `_section` leggeva solo
`[schedule]` e il pannello applicava i default senza dirlo. Per questo `_SECTION_KEYS` elenca le chiavi
ammesse per sezione: una chiave sconosciuta, o una chiave nota di un'altra sezione, producono
`ConfigError` con l'indicazione di dove va. La distinzione che tiene il sistema usabile è fra **sezione
assente** (spegne una parte del pannello, non è un errore) e **chiave sbagliata** (errore, perché lì
l'intenzione era scrivere qualcosa che non ha effetto).

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

I payload veri stanno in `tests/fixtures/` (`weather_openmeteo.json`, `marine_openmeteo.json`,
`transitous_stoptimes.json`, `transitous_trip.json`, `transitous_geocode.json`, `calendar.ics`,
`waste.ics`); `conftest.py` espone `read_fixture`, `load_json`, `rome`.

| File | Cosa copre |
|---|---|
| `test_render.py` | dimensioni/mode, determinismo, sezioni vuote, troncamenti, priorità fermate, `NOTTE`, segmenti testo+icona, riga dei dettagli (ordine e cedimento), punti cardinali e nomi dei venti |
| `test_schedule.py` | confini 22:59/23:00 e 06:29/06:30, mezzanotte, clamp, intervalli |
| `test_config.py` | valori, errori parlanti, override da ambiente, `stop_details`, `[schedule]`, `[sea]`, chiave sconosciuta o nella sezione sbagliata, `config.example.toml` che si carica davvero, allineamento fra `_SECTION_KEYS` e dataclass |
| `test_sea.py` | parsing Open-Meteo Marine, scala Douglas (forza e parola), campi mancanti, coordinate della richiesta |
| `test_weather.py` | parsing Open-Meteo (nodi, direzione del vento, umidità), campi mancanti, codici WMO, unità e campi della richiesta |
| `test_trains.py` | partenze passate, ritardo, binario, cancellazioni, filtro, fermate da `/trip` |
| `test_collect.py` | sezioni non configurate, fallback su cache con `stale=True` (meteo, differenziata, mare) |
| `test_calendar.py` | `BYDAY`/`COUNT`, `EXDATE`, override `RECURRENCE-ID`, annullato, `TZID` sconosciuto, URL embed |
| `test_waste.py` | ricorrenze e giorni della differenziata |
| `test_server.py` | `/health`, `/panel.png`, `/panel.html`, 404, porta non rubabile, guardia anti-doppione |

Il numero di test non è scritto qui apposta: cambia a ogni modifica e un conteggio fisso invecchia
subito (era già successo). Il totale lo stampa `python -m pytest -q`.

---

## 10. I bug reali (sintomo → causa → correzione)

| Sintomo | Causa | Correzione |
|---|---|---|
| `ZoneInfoNotFoundError: 'Europe/Rome'` | Windows non ha il database IANA | dipendenza `tzdata` |
| I test non importano il package | pytest non aggiunge la root al `sys.path` | `pythonpath = ["."]` |
| L'ora si sovrappone al nome del treno | colonne a pixel fissi | larghezze da `getlength` |
| `0.5m` mostrato come "quasi calmo" | soglie Douglas sul valore pieno, numero arrotondato a 1 decimale | classificazione sull'altezza arrotondata (`_state`) |
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
  sources/values.py    lettura tollerante dei campi JSON opzionali
  sources/weather.py   Open-Meteo: fetch + parse + codici WMO (vento in nodi)
  sources/marine.py    Open-Meteo Marine: onde e scala Douglas (forza/parola/glifo)
  sources/trains.py    Transitous: stoptimes, trip, geocode
  sources/calendar.py  parser ICS (folding, RRULE, EXDATE, RECURRENCE-ID)
  sources/waste.py     raccolta differenziata: finestra allineata ai giorni
  render/fonts.py      ricerca TTF multipiattaforma: glifi richiesti e metriche vicine
  render/icons.py      glifi vettoriali: meteo (due toni), mare, umidità, vento, persona,
                       alba/tramonto, frecce, sezioni
  render/layout.py     fit_text, divider, etichette di data, punti cardinali e nomi dei venti
  render/panel.py      composizione del pannello (righe miste testo+icona)
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
- scrivere una nuova fonte (maree, qualità dell'aria…) seguendo la checklist in `AGENTS.md`.






