# Mappa tecnica — kindle-dashboard

> I vincoli operativi **non** sono qui: stanno in `.clinerules`.
> Questo file descrive architettura, invarianti e come intervenire senza romperli.

## Architettura

Flusso unidirezionale, nessun ciclo:

```
config.toml -> collect() -> PanelData -> render_panel() -> PNG / HTTP
                   ^
      sources/* (fetch_payload -> parse) + Cache (fallback)
```

| Modulo | Responsabilità | Non deve fare |
|---|---|---|
| `config.py` | leggere/validare il TOML, risolvere i percorsi | chiamare la rete |
| `schedule.py` | decidere fascia giorno/notte e intervallo (con clamp al confine) | leggere config o disegnare |
| `collect.py` | orchestra le tre sezioni, gestisce cache e `Sync` | disegnare |
| `sources/*` | `fetch_payload` (solo rete) + `parse` (solo trasformazione); `weather`, `marine`, `calendar`, `waste`, `trains` | formattare per lo schermo |
| `sources/values.py` | lettura tollerante dei valori JSON opzionali (`optional_float`, `series_int`, …) | contenere logica di dominio |
| `cache.py` | persistere l'ultimo payload buono | contenere modelli |
| `model.py` | dataclass immutabili | importare Pillow |
| `render/*` | disegnare `PanelData` | fare I/O di rete |
| `server.py` | HTTP + cache del PNG in memoria | contenere layout |
| `__main__.py` | CLI sottile | logica di dominio |

### Invarianti

1. **`fetch_payload` e `parse` restano separati** in ogni sorgente: è ciò che permette di salvare il
   payload grezzo in cache e ri-analizzarlo quando la fonte cade. Non unirli.
2. **Ogni sezione è indipendente**: un errore su una fonte non impedisce il disegno delle altre. Il
   fallimento si rappresenta con `Sync(error=..., stale=...)`, non con un'eccezione che risale.
3. **Tutti gli orari sono aware e nel fuso di `config.weather.timezone`**; `ZoneInfo` si crea solo in
   `timezone_utils.zone()`.
4. **L'ora mostrata è quella del PC** (baked nel PNG): il clock del Kindle non viene mai letto.
5. **Il renderer produce un'immagine "L"** alla risoluzione `panel.width/height` e non ridimensiona:
   il device non deve scalare nulla.
6. **Le larghezze di colonna si misurano con `font.getlength`**, mai con pixel fissi.
7. **L'intervallo di aggiornamento si calcola solo in `schedule.py`**: fascia corrente e clamp al
   prossimo cambio. Server e renderer leggono quel risultato, non lo ricalcolano. La stessa regola
   vale per la fascia notturna che decide `NOTTE` al posto dell'orologio: `is_night()` sta lì,
   `collect()` la applica ai dati raccolti e il server la **ricalcola all'istante del render** (i
   dati possono essere più vecchi di un'ora, l'orologio no); `python -m kindle_dashboard render`
   legge il valore di `collect()`, così anteprima e PNG servito mostrano la stessa cosa.
8. **Il vento è in nodi** (`wind_speed_unit=kn`): modello, header e striscia usano la stessa unità e
   nessuno converte nel renderer. La direzione si scrive a 16 settori (`NNE`) ed è **obbligatoria**:
   sulla riga del vento cede il nome tradizionale (`· Levante-Scirocco`), non la sigla. Il nome
   viene da `layout.wind_name()`, che usa lo stesso indice a 16 settori di `compass()`: gli
   intermedi sono composti dai due venti principali nell'ordine delle lettere della sigla
   (`OSO` = Ponente-Libeccio, `NNO` = Tramontana-Maestrale), così sigla e nome non possono
   divergere e si legge subito a quale punto cardinale il nome è legato. Il mare viene dalle
   coordinate di `[location]`, non da una sezione con coordinate proprie, e la sua
   classificazione (forza Douglas, parola, glifo) è una tabella sola in `sources/marine.py`.
9. **Le righe miste testo+icona passano da `_draw_inline`**: i pezzi sono `_Segment` con `required`
   falso quando possono cedere (temperatura dell'acqua, nome del vento, frecce di alba/tramonto).
   Larghezze sempre da `font.getlength`, mai pixel scelti a occhio, e le icone si allineano al
   **centro dell'inchiostro** del testo via `_icon_top`, non al bordo del riquadro del font. Le
   righe 5 e 6 dell'intestazione sono a due colonne dentro `_draw_balanced_row`: il blocco destro si
   misura per primo (è allineato al bordo) e quello sinistro riceve lo spazio che resta.
10. **La riga dei dettagli del meteo (umidità, pioggia, percepita) usa `detail_font`**, non
   `small_font`: è nello slack sotto la temperatura grande, dove i 16 px degli elenchi si leggevano
   male, mentre `small_font` resta per footer, fermate e striscia mare. Il cedimento è deciso in
   `_draw_now_details` **a coppie intere** — prima la percepita, poi la pioggia — perché lasciarlo ai
   singoli `required` lascerebbe un'icona senza numero. L'umidità è opzionale (`optional_int`), così
   una cache scritta prima del campo resta disegnabile.
11. **Le icone hanno due toni**: nero per l'elemento principale, `_PALE` (`#8c8c8c`, metà scala
   dell'immagine in grigi) per quello che sta **dietro** — il sole coperto di `partly` (con i raggi) e
   la calotta di sole *senza raggi* di `cloud`/`rain`/`drizzle`/`snow` (via `_cloud_with_sun`), il
   lampo di `storm`, le righe di `fog`. Serve a separare due forme che si toccano senza contorni, che a
   20 px mangerebbero il disegno; altrove i glifi restano pieni e neri, perché un grigio debole su
   e-ink sparisce. Non è un'ombra decorativa né un secondo elemento: il secondo tono va sul pezzo che
   nella sagoma originale sta dietro, altrimenti si leggono due soli nello stesso glifo. Le icone dei
   titoli (`_column_title(..., icon=...)`) passano da `_title_icon`, che restituisce `(0, 0)` quando il
   titolo con `· agg. HH:MM` non ci starebbe: l'icona è decorazione e cede **prima del testo**, che
   porta l'informazione. I glifi di sezione (`calendar`, `waste`, `train`) seguono la geometria di
   Bootstrap Icons (MIT) tradotta in primitive — corpo pieno e ritagli bianchi, nessun asset esterno.
12. **I font si cercano su ogni piattaforma, devono coprire i caratteri del pannello e il primo
   candidato è quello che il container installa**: `fonts.font_directories()` guarda Windows
   (`%WINDIR%\Fonts`), macOS e Linux (`/usr/share/fonts/truetype/{dejavu,liberation,noto}`, più
   `/usr/share/fonts/TTF` e `/usr/local/share/fonts`); `REQUIRED_GLYPHS` (`°·…×àèéìòù`) è il minimo
   che il font scelto deve avere e `missing_glyphs()` lo verifica confrontando il bounding box di
   ogni carattere con quello di U+E000, che Pillow disegna sempre uguale. Senza questi controlli il
   container ricadeva sul font incorporato e stampava quadrati al posto delle accentate (bug visto sul
   device).
   La copertura non basta: le colonne si dimensionano con `font.getlength`, quindi un font più largo
   non «ruba» pixel, **diventa ellissi**. Nel container il bold di DejaVu Sans è ~1,30x il Segoe UI
   Semibold (regular ~1,17x) e tagliava `REG 12519` in `REG 12…`, `SAB 18°/12°` in `SAB 18°/…` e
   `poco mosso 0.8m` in `poco mosso`; Liberation Sans, che ha la metrica di Arial, sta in 1,09-1,15x.
   Per questo il `Dockerfile` installa `fonts-liberation` (primario) e `fonts-dejavu-core` (riserva di
   copertura), e per questo `_REGULAR_CANDIDATES`/`_BOLD_CANDIDATES` mettono **Liberation Sans in
   testa anche sull'host di sviluppo**: la scelta non è «un font vicino a quello del device» ma
   «lo stesso font», perché un font più stretto del vero (prima era il Segoe UI Semibold, 89 px contro
   i 102 px di `REG 12519`) non lascia spazio in più: nasconde un troncamento che il Kindle mostra.
   Le voci Windows restano come fallback per le installazioni senza Liberation, che non è un font di
   serie; `tests/test_fonts.py` tiene fermo che il primo nome sia quello del `Dockerfile`. In `load()`
   i candidati sono ordinati **per nome e poi per cartella**: con il ciclo cartella-major la prima
   cartella di `font_directories()` (`dejavu` su Debian) vinceva su tutto e la lista dei nomi non
   contava nulla. Cambiare font cambia tutte le misure, quindi le regole di cedimento non vanno
   allentate «perché tanto il font è quello».

### Configurazione

TOML con sezioni `panel`, `location`, `weather`, `calendar`, `trains`, `render`, `server`, `cache`.
`load_config()` restituisce dataclass immutabili; un valore non valido produce `ConfigError` con il
nome della sezione coinvolta. `calendar.ics_url` può arrivare da `KDASH_ICS_URL` solo se il file non
lo specifica. Una sezione assente disattiva la relativa parte del pannello, non è un errore.

## Come estendere

### Nuova fonte dati
1. `sources/<nome>.py`: `fetch_payload(...)` (usa `sources/http.get_json`/`get_text`) e
   `parse(payload, ...)` che restituisce dataclass di `model.py` o lancia `SourceError`. Per i campi
   opzionali usa gli helper di `sources/values.py`: una cache scritta prima di un campo nuovo deve
   restare ri-analizzabile.
2. Modello in `model.py` (frozen) + campo in `PanelData` e relativo `Sync`.
3. Sezione TOML in `config.py` (dataclass + helper `_str`/`_int`/`_number`) e in `config.example.toml`.
4. `collect.py`: `_<nome>(config, cache, moment)` sul modello di `_weather` (fetch → store → parse,
   `except SourceError` → cache), poi valorizza `PanelData`.
5. Blocco di disegno in `render/panel.py` e chiamata dentro `render_panel`.
6. `tests/test_<nome>.py` con fixture registrata.

### Nuovo blocco nel pannello
1. `_draw_<blocco>(draw, style, data, y) -> int` in `render/panel.py`.
2. Usa `style.px()` per le misure e `fit_text()` per i testi: righe e larghezze dai font. Per una
   riga mista testo+icona usa `_draw_inline` con segmenti `_Segment` (`required=False` sui pezzi che
   possono cedere): il troncamento vive lì e non va duplicato.
3. Rispetta il budget verticale (`_TITLE_ROW_PX` per il titolo, costante di riga dedicata): il blocco
   treni è **ancorato** al fondo (`footer_top - _trains_height`) e l'agenda riceve lo spazio che
   resta, così i treni non restano a metà pagina quando gli eventi sono pochi. Una sezione che si
   riconosce dalle icone può fare a meno del titolo e usare `_section_rule` (solo separatore): la
   striscia meteo lo fa e guadagna una riga.
4. Aggiorna `tests/test_render.py` e rigenera `preview.png`.
5. Il blocco agenda (`_draw_agenda`) ha due colonne solo quando `PanelData.waste` non è `None`: le
   larghezze vengono da `_EVENTS_SHARE` e `_COLUMN_GUTTER_PX`, non da pixel scelti a occhio.
6. **Il riassunto di un evento va a capo su due righe** (`layout.wrap_text`, passo
   `_CALENDAR_LINE_PX`) ma solo con lo spazio che avanza: `_draw_events` conta prima quanti eventi
   stanno su una riga sola (`room // row`) e riserva una riga a ciascuno, poi concede la seconda
   riga solo a chi ci sta dentro il margine. La regola non è cosmetica: senza prenotazione un evento
   lungo si prende lo spazio del successivo e lo fa sparire, che è peggio dell'ellissi che si voleva
   evitare. `wrap_text(text, font, width, lines=1)` è il ritorno all'ellissi quando non c'è spazio.

### Nuovo comando CLI
1. `commands.add_parser(..., parents=[common])` in `_build_parser()` (il parent fornisce `--config`).
2. `_cmd_<nome>(args) -> int` con `set_defaults(handler=...)`; errori utente su stderr e exit code
   diverso da zero.

### Nuova opzione di configurazione
Aggiungila alla dataclass, a `config.example.toml` e alla tabella in `README.md`: le tre cose devono
restare allineate.

## Test e verifica

| Comando | Cosa copre |
|---|---|
| `python -m pytest -q` | parsing, ricorrenze ICS, raccolta differenziata, mare (scala Douglas), config, pianificazione giorno/notte, cache, render, HTTP |
| `python -m ruff check .` | stile (line-length 110, regole E/F/I/UP/B/SIM/RUF) |
| `python -m kindle_dashboard render -o preview.png` | verifica visiva reale |

- Fixture in `tests/fixtures/`; `conftest.py` espone `read_fixture`, `load_json`, `rome`.
- Isolamento obbligatorio: `monkeypatch` di `fetch_payload`/`get_json`, `tmp_path` per la cache,
  `FakeService` + `build_server()` per l'HTTP. Niente rete, niente filesystem utente, niente `G:\`.
- I test del renderer asseriscono dimensioni, mode e contenuto: niente snapshot fragili sui pixel.
- Il gate si esegue nel **venv**: il container di produzione non contiene `tests/` (escluso da
  `.dockerignore`) e non installa `pytest`. `docker compose run --rm dashboard pytest` non è un
  comando valido: l'`ENTRYPOINT` è la CLI (`python -m kindle_dashboard`). Vedi `docs/docker.md`.

## Verifiche sul device (aggiornato alle prove reali)

Confermato su un Kindle 4 (`Linux kindle 2.6.31-rt11-lab126`, FBInk lo identifica come
`Tequila on Yoshi`):

- `wget` presente (`/usr/bin/wget`): il download del PNG funziona.
- `eips` esiste ma in **`/usr/sbin/eips`** (non `/usr/bin`), e **non mostra immagini**: con quattro
  formati (grigi, RGB, 1-bit, JPEG) lo schermo resta bianco pur con exit code 0.
- il `fbink` incluso in KOReader è **MINIMAL**: `[FBInk] Image support is disabled in this FBInk
  build!`.
- `/etc/init.d/framework stop` libera lo schermo ma porta a **schermo bianco, unità USB non più
  esposta e riavvio** del device: non è una strada percorribile qui.
- KUAL elenca l'estensione solo se `config.xml` contiene
  `<menus><menu type="json" dynamic="true">menu.json</menu></menus>`.

Conseguenza di progetto: **la visualizzazione passa dal browser** (`/panel.html` con meta refresh);
l'estensione KUAL è solo diagnostica (`Verifica server`, `Diagnostica`). Non reintrodurre il disegno
nativo su questo hardware senza una prova concreta che funzioni.

Ancora da confermare: comportamento della batteria con la pagina aperta per ore.

## File → per chi

| File | Destinatario |
|---|---|
| `README.md` | utente: installazione, configurazione, troubleshooting |
| `.clinerules` | chi scrive codice: vincoli e gate di commit |
| `AGENTS.md` | agenti/sviluppatori: architettura, estensioni, mappa dei test |
| `docs/technical-walkthrough.md` | chi studia il progetto: percorso tecnico narrato, con i bug reali |
| `docs/venv.md` | chi sviluppa: cosa isola un venv, come crearlo, vantaggi e limiti |
| `docs/docker.md` | chi fa deploy: scelte dell'immagine, volumi, comandi, rollback, trappole |
| `config.example.toml` | utente: modello di configurazione commentato |
| `tests/` | sviluppatori: comportamento atteso, da aggiornare con le modifiche |
| `kindle/` | deploy: estensione KUAL + script host |
